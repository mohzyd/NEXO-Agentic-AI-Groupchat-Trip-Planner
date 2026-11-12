import json
import os
import re

from datetime import datetime, timezone
from decimal import Decimal
from hashlib import sha256
from secrets import compare_digest, token_urlsafe
from threading import RLock
from time import time
from uuid import uuid4

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request, send_from_directory
from flask_socketio import SocketIO, emit, join_room

from .ai_agent import ChatAIAgent, ChatAgentError
from .paypal_sandbox import PayPalSandbox, PayPalSandboxError, parse_amount
from utils.local_storage import LocalStorage
from utils import get_file_in_app_path

load_dotenv(get_file_in_app_path(".env"))

def run_chat_host(host="0.0.0.0", port=5000, debug=False, chat_id: str = None):
    """Create a Flask and Socket.IO app instance for one room.

    Room metadata and messages are loaded from local storage. Private-room
    passwords are checked only inside this worker.
    """

    # Expiration is stored as a Unix timestamp in milliseconds by the chat UI.

    db = LocalStorage("chats")
    history_db = LocalStorage("chats_history")
    loaded_chats = db.get("created_chats", [])


    for chat in loaded_chats:
        if chat.get("chat_id") == chat_id:
            chat_name = chat.get("name") or chat.get("short_name") or "Chat"
            privacy = chat.get("privacy")
            password = chat.get("password")
            expiry_time = chat.get("expire_time", chat.get("expiry_time"))
            break
    else:
        raise RuntimeError(f"Room {chat_id} not found in created_chats.")

    room_password = None

    ######
    if privacy == "private":
        if not isinstance(password, str):
            raise RuntimeError("Private room is missing its password.")

        room_password = password

    interface_path = get_file_in_app_path("interface")
    app = Flask(
        f"room_{chat_id}",
        template_folder=str(interface_path / "page"),
        static_folder=None
    )
    app.config.update(
        SECRET_KEY=os.environ.get(
            "FLASK_SECRET_KEY",
            str(uuid4())
        ),
        RECOVERY_EXPIRY=60 * 60 * 24 * 30
    )

    socketio = SocketIO(
        app,
        cors_allowed_origins="*",
        async_mode="threading"
    )
    users = {}
    recoverable_sessions = {}
    room_state = {"leader_user_id": None}
    payment_proposals = {}
    pending_payment_orders = {}
    creating_payment_checkouts = {}
    capturing_payment_orders = set()
    payment_state_key = f"payment_state:{chat_id}"
    state_lock = RLock()
    chat_lock = RLock()
    payment_lock = RLock()
    ai_agent = ChatAIAgent()
    paypal = PayPalSandbox()

    def restore_payment_state():
        saved = history_db.get(payment_state_key, {})
        if not isinstance(saved, dict):
            return

        leader_user_id = saved.get("leader_user_id")
        if isinstance(leader_user_id, str):
            room_state["leader_user_id"] = leader_user_id

        records = saved.get("proposals", [])
        if not isinstance(records, list):
            return

        for record in records:
            if not isinstance(record, dict):
                continue
            proposal_id = record.get("id")
            title = record.get("title")
            creator_id = record.get("created_by")
            try:
                target = parse_amount(record.get("target"))
            except PayPalSandboxError:
                continue
            if not all(isinstance(value, str) and value for value in (proposal_id, title, creator_id)):
                continue

            raw_pledges = record.get("pledges", {})
            pledges = {}
            if isinstance(raw_pledges, dict):
                for user_id, raw_amount in raw_pledges.items():
                    if not isinstance(user_id, str) or not user_id:
                        continue
                    try:
                        pledges[user_id] = parse_amount(raw_amount)
                    except PayPalSandboxError:
                        continue
            pledged_total = sum(pledges.values(), Decimal("0.00"))
            if pledged_total > target:
                continue

            status = "paid" if record.get("status") == "paid" else (
                "ready" if pledged_total == target else "collecting"
            )
            raw_paid_pledges = record.get("paid_pledges", {})
            paid_pledges = {
                user_id: True
                for user_id, is_paid in raw_paid_pledges.items()
                if (
                    isinstance(user_id, str) and user_id in pledges and
                    is_paid is True
                )
            } if isinstance(raw_paid_pledges, dict) else {}
            if status == "paid" and not raw_paid_pledges:
                status = "ready" if pledged_total == target else "collecting"
            elif pledged_total == target and all(paid_pledges.get(user_id) for user_id in pledges):
                status = "paid"
            elif pledged_total == target:
                status = "ready"
            payment_proposals[proposal_id] = {
                "id": proposal_id,
                "title": title,
                "target": target,
                "created_by": creator_id,
                "pledges": pledges,
                "paid_pledges": paid_pledges,
                "status": status
            }

        raw_orders = saved.get("pending_orders", {})
        if isinstance(raw_orders, dict):
            for order_id, order in raw_orders.items():
                if (
                    not isinstance(order_id, str) or
                    not isinstance(order, dict) or
                    not isinstance(order.get("proposal_id"), str) or
                    not isinstance(order.get("payer_user_id"), str)
                ):
                    continue
                proposal = payment_proposals.get(order["proposal_id"])
                if (
                    proposal and proposal["status"] != "paid" and
                    order["payer_user_id"] in proposal["pledges"] and
                    not proposal["paid_pledges"].get(order["payer_user_id"])
                ):
                    pending_payment_orders[order_id] = order

    restore_payment_state()

    def joined_user(sid):
        with state_lock:
            return users.get(sid)

    def persist_payment_state():
        with payment_lock:
            saved = {
                "leader_user_id": room_state["leader_user_id"],
                "proposals": [
                    {
                        "id": proposal["id"],
                        "title": proposal["title"],
                        "target": format(proposal["target"], ".2f"),
                        "created_by": proposal["created_by"],
                        "pledges": {
                            user_id: format(amount, ".2f")
                            for user_id, amount in proposal["pledges"].items()
                        },
                        "paid_pledges": proposal["paid_pledges"],
                        "status": proposal["status"]
                    }
                    for proposal in payment_proposals.values()
                ],
                "pending_orders": pending_payment_orders.copy()
            }
            with history_db.sync_update() as data:
                data.set(payment_state_key, saved)

    def public_payment_state():
        with payment_lock:
            proposals = []
            for proposal in payment_proposals.values():
                pledged = sum(proposal["pledges"].values(), Decimal("0.00"))
                paid = sum(
                    amount
                    for user_id, amount in proposal["pledges"].items()
                    if proposal["paid_pledges"].get(user_id)
                )
                pending_users = {
                    order["payer_user_id"]
                    for order in pending_payment_orders.values()
                    if order["proposal_id"] == proposal["id"]
                }
                pending_users.update(
                    creating_payment_checkouts.get(proposal["id"], set())
                )
                proposals.append({
                    "id": proposal["id"],
                    "title": proposal["title"],
                    "target": format(proposal["target"], ".2f"),
                    "pledged": format(pledged, ".2f"),
                    "paid": format(paid, ".2f"),
                    "pledges_by_user": {
                        user_id: format(amount, ".2f")
                        for user_id, amount in proposal["pledges"].items()
                    },
                    "paid_user_ids": [
                        user_id for user_id, is_paid in proposal["paid_pledges"].items()
                        if is_paid
                    ],
                    "pending_user_ids": list(pending_users),
                    "currency": paypal.currency,
                    "status": proposal["status"]
                })
            return {
                "leader_user_id": room_state["leader_user_id"],
                "proposals": proposals
            }

    def broadcast_payment_state():
        socketio.emit("payment_state", public_payment_state(), room=chat_id)

    def payment_error(sid, message):
        socketio.emit("payment_error", {"error": message}, to=sid)

    def recent_ai_context():
        history = load_chat_messages()
        context = []
        polls = {}
        for item in history:
            if not isinstance(item, dict):
                continue
            raw_message = item.get("message")
            try:
                payload = json.loads(raw_message)
            except (TypeError, ValueError):
                payload = {"text": raw_message}
            if not isinstance(payload, dict):
                continue

            if item.get("type") == "poll":
                poll_id = payload.get("id")
                options = payload.get("options")
                if (
                    isinstance(poll_id, str) and
                    isinstance(payload.get("question"), str) and
                    isinstance(options, list) and
                    2 <= len(options) <= 6 and
                    all(
                        isinstance(option, dict) and isinstance(option.get("text"), str)
                        for option in options
                    )
                ):
                    polls[poll_id] = {
                        "question": payload["question"][:120],
                        "options": [
                            {
                                "text": option.get("text", "")[:120],
                                "votes": 0
                            }
                            for option in options
                        ],
                        "votes_by_user": {},
                        "closed": (
                            bool(payload.get("closed")) or
                            (
                                isinstance(payload.get("endsAt"), (int, float)) and
                                payload["endsAt"] <= time() * 1000
                            )
                        )
                    }
            elif item.get("type") == "poll_update":
                poll = polls.get(payload.get("pollId"))
                option_index = payload.get("optionIndex")
                user_id = item.get("userID")
                if (
                    poll and
                    isinstance(option_index, int) and not isinstance(option_index, bool) and
                    0 <= option_index < len(poll["options"]) and
                    isinstance(user_id, str) and user_id not in poll["votes_by_user"]
                ):
                    poll["votes_by_user"][user_id] = option_index
                    poll["options"][option_index]["votes"] += 1
            elif item.get("type") == "text":
                text = payload.get("text")
                if isinstance(text, str) and text.strip():
                    nickname = item.get("nickname")
                    speaker = nickname.strip() if isinstance(nickname, str) and nickname.strip() else "Guest"
                    context.append({"content": f"{speaker}: {text[:1200]}"})

        poll_context = []
        for poll in polls.values():
            del poll["votes_by_user"]
            options = poll["options"]
            max_votes = max((option["votes"] for option in options), default=0)
            poll["winners"] = [
                option["text"] for option in options
                if max_votes > 0 and option["votes"] == max_votes
            ]
            poll_context.append({
                "content": "Poll results (computed from persisted votes): " + json.dumps(poll)
            })

        return context[-12:] + poll_context[-6:]

    def generate_ai_reply(context, sid):
        try:
            answer = ai_agent.respond(context)
            ai_message = {
                "userID": "nexo-ai",
                "nickname": "Nexo AI",
                "type": "text",
                "message": json.dumps({
                    "id": str(uuid4()),
                    "text": answer,
                    "isAI": True
                }),
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            save_message(ai_message)
            socketio.emit("new_message", ai_message, room=chat_id)
        except ChatAgentError as error:
            socketio.emit("ai_error", {"error": str(error)}, to=sid)
        except Exception as error:
            print(f"[Chat] AI reply failed: {error}")
            socketio.emit(
                "ai_error",
                {"error": "The AI reply could not be saved or sent."},
                to=sid
            )

    def suggest_trip_budget(context, sid):
        instruction = (
            "Estimate one realistic total budget for the group's trip, in "
            f"{paypal.currency}. Use only relevant preferences and poll results from the "
            "context. If details are missing, make a modest, clearly stated assumption "
            "instead of inventing specific prices. Keep the rationale to one short sentence. "
            "This is only a suggestion; do not imply that anyone agreed to it or paid."
        )
        try:
            answer = ai_agent.respond(
                context,
                response_instruction=instruction,
                response_mime_type="application/json",
                response_schema={
                    "type": "object",
                    "properties": {
                        "amount": {"type": "number"},
                        "rationale": {"type": "string"}
                    },
                    "required": ["amount", "rationale"],
                    "additionalProperties": False
                }
            )
            suggestion = json.loads(answer)
            if (
                not isinstance(suggestion, dict) or
                not {"amount", "rationale"}.issubset(suggestion) or
                not isinstance(suggestion["rationale"], str) or
                not suggestion["rationale"].strip()
            ):
                raise ValueError("Invalid budget suggestion shape.")
            amount = parse_amount(suggestion["amount"])
            socketio.emit("budget_suggestion", {
                "amount": format(amount, ".2f"),
                "currency": paypal.currency,
                "rationale": suggestion["rationale"].strip()[:500]
            }, to=sid)
        except (ChatAgentError, PayPalSandboxError, ValueError, TypeError) as error:
            message = str(error) if isinstance(error, (ChatAgentError, PayPalSandboxError)) else (
                "The AI returned an invalid budget suggestion. Please enter the budget manually."
            )
            socketio.emit("budget_suggestion_error", {"error": message}, to=sid)
        except Exception as error:
            print(f"[Chat] Trip budget suggestion failed: {error}")
            socketio.emit(
                "budget_suggestion_error",
                {"error": "The trip budget could not be suggested. Please enter it manually."},
                to=sid
            )
    def room_members():
        with state_lock:
            return [
                {"id": user["userID"], "name": user["nickname"]}
                for user in users.values()
                if user is not None
            ]

    def hash_token(token: str) -> str:
        """Hash a recovery token before keeping it in process memory."""

        return sha256(
            token.encode("utf-8")
        ).hexdigest()

    def recover_identity(old_sid, recovery_token):
        """Validate and rotate a disconnected member's recovery token."""

        if not isinstance(old_sid, str):
            return None, None

        if not isinstance(recovery_token, str):
            return None, None

        with state_lock:

            previous = recoverable_sessions.get(old_sid)

            if not previous:
                return None, None

            if time() > previous["expires_at"]:
                recoverable_sessions.pop(old_sid, None)
                return None, None

            if not compare_digest(
                hash_token(recovery_token),
                previous["token_hash"]
            ):
                return None, None

            recoverable_sessions.pop(old_sid)
            new_token = token_urlsafe(32)

            return {
                "userID": previous["userID"],
                "nickname": previous["nickname"],
                "token_hash": hash_token(new_token)
            }, new_token

    def load_chat_messages():
        """Load persisted history for this room from LocalStorage."""
        with chat_lock:
            messages = history_db.get(chat_id, None)
            if isinstance(messages, list):
                return messages

            legacy_history = db.get("chats_history", [])
            if isinstance(legacy_history, list):
                for room_history in legacy_history:
                    if (
                        isinstance(room_history, dict) and
                        room_history.get("chat_id") == chat_id
                    ):
                        messages = room_history.get("messages", [])
                        if isinstance(messages, list):
                            return messages

            return []

    def save_message(message):
        """Append a message to this room's LocalStorage history."""

        with chat_lock:
            with history_db.sync_update() as data:
                messages = data.get(chat_id, None)
                if not isinstance(messages, list):
                    messages = load_chat_messages()
                messages.append(message)
                data.set(chat_id, messages)

    def room_expired():
        """Return whether the configured room expiry time has passed."""
        if not expiry_time:
            return False
        if isinstance(expiry_time, (int, float)):
            expiry_timestamp = expiry_time / 1000
        elif isinstance(expiry_time, str):
            expiry_timestamp = datetime.fromisoformat(expiry_time).timestamp()
        else:
            raise TypeError("Room expiry must be a timestamp or ISO date string.")
        return time() >= expiry_timestamp

    @app.route("/")
    def index():
        """Render the chat page with configuration for this room."""

        if isinstance(expiry_time, (int, float)) and expiry_time > 0:
            ends_at = expiry_time
        elif expiry_time:
            ends_at = datetime.fromisoformat(expiry_time).timestamp() * 1000
        else:
            ends_at = None

        return render_template(
            "chat.html",
            chat_config={
                "name": chat_name,
                "roomID": chat_id,
                "requiresPassword": privacy == "private",
                "currency": paypal.currency,
                "endsAt": ends_at
            }
        )

    @app.route("/css/chat/<path:asset_path>")
    def chat_stylesheet(asset_path):
        return send_from_directory(
            interface_path / "css" / "chat",
            asset_path
        )

    @app.route("/js/chat/<path:asset_path>")
    def chat_script(asset_path):
        return send_from_directory(
            interface_path / "js" / "chat",
            asset_path
        )

    @app.route("/assets/<path:asset_path>")
    def chat_asset(asset_path):
        return send_from_directory(
            interface_path / "assets",
            asset_path
        )

    @app.route("/_health")
    def health():
        """Provide the readiness check used by the room manager."""

        return jsonify({"ready": True})

    @socketio.on("connect")
    def handle_connect():
        """Register a pending socket, including read-only expired rooms."""

        with state_lock:
            users[request.sid] = None

    @socketio.on("join")
    def handle_join(data):
        """Authorize a member, join the room, and send identity and history."""

        if not isinstance(data, dict):
            return

        sid = request.sid

        if privacy == "private":
            supplied_password = data.get("password")

            if not isinstance(supplied_password, str) or not compare_digest(
                supplied_password,
                room_password
            ):
                emit(
                    "join_error",
                    {"error": "Incorrect room password."},
                    to=sid
                )
                return

        with state_lock:

            if sid not in users or users[sid] is not None:
                return

            nickname = data.get("nickname", "Anonymous")

            if not isinstance(nickname, str):
                nickname = "Anonymous"

            nickname = nickname.strip() or "Anonymous"

            user, new_token = recover_identity(
                data.get("previousSID"),
                data.get("recoveryToken")
            )

            if user is None:

                new_token = token_urlsafe(32)
                user = {
                    "userID": str(uuid4()),
                    "nickname": nickname,
                    "token_hash": hash_token(new_token)
                }

            user["nickname"] = nickname
            users[sid] = user
            became_leader = False
            current_leader_id = room_state["leader_user_id"]
            leader_is_known = any(
                active_user and active_user["userID"] == current_leader_id
                for active_user in users.values()
            ) or any(
                session["userID"] == current_leader_id and time() <= session["expires_at"]
                for session in recoverable_sessions.values()
            )
            if not leader_is_known:
                room_state["leader_user_id"] = user["userID"]
                became_leader = True

        if became_leader:
            persist_payment_state()
        join_room(chat_id)

        emit(
            "identity",
            {
                "userID": user["userID"],
                "recoveryToken": new_token,
                "sid": sid,
                "roomID": chat_id,
                "leaderUserID": room_state["leader_user_id"]
            },
            to=sid
        )

        emit("members", room_members(), room=chat_id)
        emit(
            "message_history",
            load_chat_messages(),
            to=sid
        )
        emit("payment_state", public_payment_state(), to=sid)

        print(f"[Chat] {nickname} joined room {chat_id}")

    @socketio.on("message")
    def handle_message(data):
        """Persist and broadcast a validated message to room members."""

        if not isinstance(data, dict):
            return

        with state_lock:
            user = users.get(request.sid)

        if not user:
            return

        if room_expired():
            emit("room_read_only", {
                "error": "This room has expired; sending messages is disabled."
            }, to=request.sid)
            return

        message_content = data.get("message", "")

        if not isinstance(message_content, str):
            return

        message_type = data.get("type", "text")

        if (
            not isinstance(message_type, str) or
            message_type not in {"text", "image", "gif", "location", "poll", "poll_update"}
        ):
            emit("message_error", {"error": "Unsupported message type."}, to=request.sid)
            return

        if len(message_content.encode("utf-8")) > 900_000:
            emit("message_error", {"error": "Message is too large."}, to=request.sid)
            return

        message = {
            "userID": user["userID"],
            "nickname": user["nickname"],
            "type": message_type,
            "message": message_content,
            "timestamp": datetime.now(
                timezone.utc
            ).isoformat()
        }

        try:

            save_message(message)
            emit("new_message", message, room=chat_id)

        except Exception as error:

            print(f"[Chat] Message saving failed: {error}")
            emit(
                "message_error",
                {"error": "Failed to save message."},
                to=request.sid
            )
            return

        if message_type == "text":
            try:
                text_payload = json.loads(message_content)
            except ValueError:
                text_payload = {}
            text = text_payload.get("text") if isinstance(text_payload, dict) else None
            if isinstance(text, str) and re.search(r"(?<![\w@])@ai(?![\w])", text, re.IGNORECASE):
                socketio.start_background_task(
                    generate_ai_reply,
                    recent_ai_context(),
                    request.sid
                )

    @socketio.on("budget_suggest")
    def handle_budget_suggest():
        sid = request.sid
        user = joined_user(sid)
        if not user:
            socketio.emit(
                "budget_suggestion_error",
                {"error": "Join the chat before requesting a budget suggestion."},
                to=sid
            )
            return
        if user["userID"] != room_state["leader_user_id"]:
            socketio.emit(
                "budget_suggestion_error",
                {"error": "Only the chat leader can request a trip budget suggestion."},
                to=sid
            )
            return
        if room_expired():
            socketio.emit(
                "budget_suggestion_error",
                {"error": "This room has expired; budget suggestions are disabled."},
                to=sid
            )
            return
        socketio.start_background_task(suggest_trip_budget, recent_ai_context(), sid)

    @socketio.on("payment_propose")
    def handle_payment_propose(data):
        if not isinstance(data, dict):
            return
        user = joined_user(request.sid)
        if not user:
            payment_error(request.sid, "Join the chat before creating a payment proposal.")
            return
        if user["userID"] != room_state["leader_user_id"]:
            payment_error(request.sid, "Only the chat leader can create the trip budget proposal.")
            return
        if room_expired():
            payment_error(request.sid, "This room has expired; payment proposals are disabled.")
            return

        title = data.get("title", "")
        if not isinstance(title, str) or not title.strip():
            payment_error(request.sid, "Add a short description for the payment.")
            return
        try:
            target = parse_amount(data.get("target"))
        except PayPalSandboxError as error:
            payment_error(request.sid, str(error))
            return

        proposal_id = str(uuid4())
        proposal = {
            "id": proposal_id,
            "title": title.strip()[:120],
            "target": target,
            "created_by": user["userID"],
            "pledges": {},
            "paid_pledges": {},
            "status": "collecting"
        }
        with payment_lock:
            payment_proposals[proposal_id] = proposal

        message = {
            "userID": user["userID"],
            "nickname": user["nickname"],
            "type": "payment_request",
            "message": json.dumps({
                "id": proposal_id,
                "title": proposal["title"],
                "target": format(target, ".2f"),
                "currency": paypal.currency
            }),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        try:
            save_message(message)
        except Exception as error:
            with payment_lock:
                payment_proposals.pop(proposal_id, None)
            print(f"[Chat] Payment proposal saving failed: {error}")
            payment_error(request.sid, "The payment proposal could not be saved.")
            return
        persist_payment_state()
        socketio.emit("new_message", message, room=chat_id)
        broadcast_payment_state()

    @socketio.on("payment_pledge")
    def handle_payment_pledge(data):
        if not isinstance(data, dict):
            return
        user = joined_user(request.sid)
        if not user:
            payment_error(request.sid, "Join the chat before pledging.")
            return
        if room_expired():
            payment_error(request.sid, "This room has expired; pledges are disabled.")
            return

        proposal_id = data.get("proposal_id")
        if not isinstance(proposal_id, str):
            payment_error(request.sid, "Invalid payment proposal.")
            return
        try:
            amount = parse_amount(data.get("amount"))
        except PayPalSandboxError as error:
            payment_error(request.sid, str(error))
            return

        with payment_lock:
            proposal = payment_proposals.get(proposal_id)
            if not proposal or proposal["status"] != "collecting":
                payment_error(request.sid, "This proposal is no longer accepting pledges.")
                return
            if user["userID"] in proposal["pledges"]:
                payment_error(request.sid, "You have already pledged to this proposal.")
                return
            pledged = sum(proposal["pledges"].values(), Decimal("0.00"))
            if pledged + amount > proposal["target"]:
                payment_error(request.sid, "That pledge would exceed the proposal target.")
                return
            proposal["pledges"][user["userID"]] = amount
            if pledged + amount == proposal["target"]:
                proposal["status"] = "ready"
        persist_payment_state()
        broadcast_payment_state()

    @socketio.on("payment_checkout")
    def handle_payment_checkout(data):
        if not isinstance(data, dict):
            return
        sid = request.sid
        user = joined_user(sid)
        if not user:
            payment_error(sid, "Join the chat before starting checkout.")
            return
        if room_expired():
            payment_error(sid, "This room has expired; PayPal checkout is disabled.")
            return
        proposal_id = data.get("proposal_id")
        if not isinstance(proposal_id, str):
            payment_error(sid, "Invalid payment proposal.")
            return
        with payment_lock:
            proposal = payment_proposals.get(proposal_id)
            if not proposal or proposal["status"] != "ready":
                payment_error(sid, "The proposal must be fully pledged before members can pay.")
                return
            user_id = user["userID"]
            amount = proposal["pledges"].get(user_id)
            if amount is None:
                payment_error(sid, "You must pledge a contribution before checking out.")
                return
            if proposal["paid_pledges"].get(user_id):
                payment_error(sid, "Your contribution has already been paid.")
                return
            creating_users = creating_payment_checkouts.setdefault(proposal_id, set())
            if user_id in creating_users or any(
                order["proposal_id"] == proposal_id and order["payer_user_id"] == user_id
                for order in pending_payment_orders.values()
            ):
                payment_error(sid, "You already have a PayPal Sandbox checkout in progress.")
                return
            creating_users.add(user_id)
        persist_payment_state()

        try:
            order_id, approval_url, _ = paypal.create_order(
                amount,
                f"{proposal['title']} contribution",
                request.host_url.rstrip("/") + f"/?payment=success&proposal_id={proposal_id}",
                request.host_url.rstrip("/") + f"/?payment=cancelled&proposal_id={proposal_id}"
            )
        except PayPalSandboxError as error:
            with payment_lock:
                creating_payment_checkouts.get(proposal_id, set()).discard(user_id)
                if not creating_payment_checkouts.get(proposal_id):
                    creating_payment_checkouts.pop(proposal_id, None)
            persist_payment_state()
            payment_error(sid, str(error))
            broadcast_payment_state()
            return

        with payment_lock:
            creating_payment_checkouts.get(proposal_id, set()).discard(user_id)
            if not creating_payment_checkouts.get(proposal_id):
                creating_payment_checkouts.pop(proposal_id, None)
            pending_payment_orders[order_id] = {
                "proposal_id": proposal_id,
                "payer_user_id": user_id
            }
        persist_payment_state()
        socketio.emit(
            "payment_checkout",
            {"approval_url": approval_url},
            to=sid
        )
        broadcast_payment_state()

    @socketio.on("payment_cancel")
    def handle_payment_cancel(data):
        if not isinstance(data, dict):
            return
        user = joined_user(request.sid)
        proposal_id = data.get("proposal_id")
        order_id = data.get("order_id")
        if not isinstance(proposal_id, str) or not user:
            return
        with payment_lock:
            matching_orders = [
                pending_id
                for pending_id, order in pending_payment_orders.items()
                if (
                    order["proposal_id"] == proposal_id and
                    order["payer_user_id"] == user["userID"]
                )
            ]
            if isinstance(order_id, str):
                order = pending_payment_orders.get(order_id)
                if (
                    order is None or
                    order["proposal_id"] != proposal_id or
                    order["payer_user_id"] != user["userID"] or
                    order_id in capturing_payment_orders
                ):
                    return
                pending_payment_orders.pop(order_id, None)
            elif len(matching_orders) == 1:
                if matching_orders[0] in capturing_payment_orders:
                    return
                pending_payment_orders.pop(matching_orders[0], None)
            else:
                return
        persist_payment_state()
        broadcast_payment_state()

    @socketio.on("payment_capture")
    def handle_payment_capture(data):
        if not isinstance(data, dict):
            return
        sid = request.sid
        user = joined_user(sid)
        order_id = data.get("order_id")
        if not isinstance(order_id, str):
            payment_error(sid, "Invalid PayPal order.")
            return
        with payment_lock:
            order = pending_payment_orders.get(order_id)
            if not user or not order or user["userID"] != order["payer_user_id"]:
                payment_error(sid, "Only the member who started this checkout can complete it.")
                return
            proposal = payment_proposals.get(order["proposal_id"])
            payer_user_id = order["payer_user_id"]
            expected_amount = proposal["pledges"].get(payer_user_id) if proposal else None
            if (
                not proposal or
                proposal["status"] != "ready" or
                expected_amount is None or
                proposal["paid_pledges"].get(payer_user_id)
            ):
                payment_error(sid, "This PayPal checkout is no longer active.")
                return
            if order_id in capturing_payment_orders:
                payment_error(sid, "This Sandbox payment is already being confirmed.")
                return
            capturing_payment_orders.add(order_id)

        try:
            result = paypal.capture_order(order_id)
        except PayPalSandboxError as error:
            with payment_lock:
                capturing_payment_orders.discard(order_id)
            payment_error(sid, str(error))
            return

        try:
            capture = result["purchase_units"][0]["payments"]["captures"][0]
            captured_amount = parse_amount(capture["amount"]["value"])
            captured_currency = capture["amount"]["currency_code"]
        except (KeyError, IndexError, TypeError, PayPalSandboxError):
            with payment_lock:
                capturing_payment_orders.discard(order_id)
            payment_error(sid, "PayPal Sandbox did not complete the payment.")
            return
        if (
            capture.get("status") != "COMPLETED" or
            captured_amount != expected_amount or
            captured_currency != paypal.currency
        ):
            with payment_lock:
                capturing_payment_orders.discard(order_id)
            payment_error(sid, "PayPal Sandbox did not confirm the expected contribution amount.")
            return

        with payment_lock:
            capturing_payment_orders.discard(order_id)
            proposal["paid_pledges"][payer_user_id] = True
            pending_payment_orders.pop(order_id, None)
            if all(proposal["paid_pledges"].get(user_id) for user_id in proposal["pledges"]):
                proposal["status"] = "paid"
        persist_payment_state()
        broadcast_payment_state()

    @socketio.on("disconnect")
    def handle_disconnect():
        """Save temporary identity-recovery data after a member disconnects."""

        sid = request.sid

        with state_lock:

            user = users.pop(sid, None)

            if user:
                recoverable_sessions[sid] = {
                    "userID": user["userID"],
                    "nickname": user["nickname"],
                    "token_hash": user["token_hash"],
                    "expires_at": (
                        time() +
                        app.config["RECOVERY_EXPIRY"]
                    )
                }

        if user:
            socketio.emit("members", room_members(), room=chat_id)
            print(f"[Chat] Disconnected: {user['nickname']} from room {chat_id}")

    print(f"chat running on http://{host}:{port}")
    socketio.run(app, host=host, port=port, debug=debug, allow_unsafe_werkzeug=True)