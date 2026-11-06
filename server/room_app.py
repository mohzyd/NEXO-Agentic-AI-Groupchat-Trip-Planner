"""Factory and runner for isolated per-room Flask-SocketIO chat servers."""

import os
import json
from datetime import datetime, timezone
from hashlib import sha256
from secrets import compare_digest, token_urlsafe
from threading import RLock
from time import time
from uuid import uuid4

from flask import Flask, jsonify, request, send_file
from flask_socketio import SocketIO, emit, join_room

from utils.local_storage import LocalStorage
from utils.encryption import Encryptor


def create_room_server(room_id: str):
    """Create a Flask and Socket.IO app instance for one room.

    Room metadata is provided through the ``ROOM_GROUPCHAT`` environment
    variable. Protected-room passwords are decrypted only inside this worker.
    """

    groupchat = json.loads(os.environ.get("ROOM_GROUPCHAT", "{}"))
    groupchat.setdefault("name", "Anonymous Chat")
    groupchat.setdefault("isProtected", False)
    groupchat.setdefault("expiresAt", None)
    control_token = os.environ.get("ROOM_CONTROL_TOKEN", "")

    room_password = None

    if groupchat["isProtected"]:
        encrypted_password = groupchat.get("encryptedPassword")

        if not isinstance(encrypted_password, str):
            raise RuntimeError("Protected room is missing its encrypted password.")

        room_password = Encryptor.decrypt(encrypted_password)

    app = Flask(f"room_{room_id}")
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

    chat_storage = LocalStorage("chats")
    users = {}
    recoverable_sessions = {}
    state_lock = RLock()
    chat_lock = RLock()

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

            history = chat_storage.get(room_id, [])
            return history if isinstance(history, list) else []

    def save_message(message):
        """Append a message to this room's LocalStorage history."""

        with chat_lock:

            with chat_storage.sync_update() as data:

                history = data.get(room_id, [])

                if not isinstance(history, list):
                    history = []

                history.append(message)
                data.set(room_id, history)

    def room_expired():
        """Return whether the configured room expiry time has passed."""

        expires_at = groupchat["expiresAt"]

        return bool(
            expires_at and
            time() >= datetime.fromisoformat(expires_at).timestamp()
        )

    def get_room_details():
        """Return room metadata and the current joined-member count."""

        with state_lock:
            member_count = sum(user is not None for user in users.values())

        expires_at = groupchat["expiresAt"]

        return {
            "room_id": room_id,
            "name": groupchat["name"],
            "isProtected": groupchat["isProtected"],
            "isExpired": room_expired(),
            "memberCount": member_count,
            "createdAt": groupchat.get("createdAt"),
            "expiresAt": expires_at,
            "secondsRemaining": (
                max(0, int(datetime.fromisoformat(expires_at).timestamp() - time()))
                if expires_at
                else None
            )
        }

    @app.route("/")
    def index():
        """Serve the chat client from the room's own public hostname."""

        return send_file(
            os.path.join(
                os.path.dirname(__file__),
                "chat_test.html"
            )
        )

    @app.route("/_health")
    def health():
        """Provide the readiness check used by the room manager."""

        return jsonify({"ready": True})

    @app.route("/api/room-details")
    def public_room_details():
        """Expose non-secret details for the room's browser client."""

        details = get_room_details()

        return jsonify(details)

    @app.route("/_internal/details")
    def internal_room_details():
        """Expose live worker details to the manager with token validation."""

        supplied_token = request.headers.get(
            "X-Room-Control-Token",
            ""
        )

        if not control_token or not compare_digest(supplied_token, control_token):
            return jsonify({"error": "Unauthorized."}), 403

        return jsonify(get_room_details())

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

        if groupchat["isProtected"]:
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

        join_room(room_id)

        emit(
            "identity",
            {
                "userID": user["userID"],
                "recoveryToken": new_token,
                "sid": sid,
                "roomID": room_id
            },
            to=sid
        )

        emit(
            "message_history",
            load_chat_messages(),
            to=sid
        )

        print(f"[Chat] {nickname} joined room {room_id}")

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

        if not isinstance(message_type, str):
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
            emit("new_message", message, room=room_id)

        except Exception as error:

            print(f"[Chat] Message saving failed: {error}")
            emit(
                "message_error",
                {"error": "Failed to save message."},
                to=request.sid
            )

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
            print(f"[Chat] Disconnected: {user['nickname']} from room {room_id}")

    return app, socketio


def run_room_server(room_id: str, port: int):
    """Run one room app on its assigned loopback port."""

    app, socketio = create_room_server(room_id)

    print(f"[Room {room_id}] Starting Flask-SocketIO on port {port}...")

    socketio.run(
        app,
        host="127.0.0.1",
        port=port,
        debug=False,
        use_reloader=False,
        allow_unsafe_werkzeug=True
    )