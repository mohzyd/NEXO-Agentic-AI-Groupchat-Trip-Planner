from datetime import datetime, timezone
from time import time

from flask import request
from flask_socketio import emit, join_room

from server.application import app, socketio
from server.chat_state import (
    connection_rooms,
    generate_identity,
    get_current_room,
    is_room_active,
    load_chat_messages,
    recover_identity,
    recoverable_sessions,
    save_message,
    state_lock,
    users
)


@socketio.on("connect")
def handle_connect():

    room_id = get_current_room()

    if room_id is None or not is_room_active(room_id):
        return False

    with state_lock:

        users[request.sid] = None

        connection_rooms[request.sid] = room_id

    print(
        f"[Socket] Connected: {request.sid} "
        f"Room: {room_id}"
    )


@socketio.on("join")
def handle_join(data):

    if not isinstance(data, dict):
        return

    sid = request.sid

    with state_lock:

        if sid not in users:
            return

        if users[sid] is not None:
            return

        room_id = connection_rooms.get(sid)

        if room_id is None:
            return

        if not is_room_active(room_id):
            return

        nickname = data.get(
            "nickname",
            "Anonymous"
        )

        if not isinstance(nickname, str):
            nickname = "Anonymous"

        nickname = nickname.strip()

        if not nickname:
            nickname = "Anonymous"

        old_sid = data.get("previousSID")
        recovery_token = data.get("recoveryToken")

        user, new_token = recover_identity(
            old_sid,
            recovery_token,
            room_id
        )

        if user is None:
            user, new_token = generate_identity()

        user["nickname"] = nickname
        user["room_id"] = room_id

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
        load_chat_messages(room_id),
        to=sid
    )

    print(
        f"[Chat] {nickname} joined room {room_id}"
    )


@socketio.on("message")
def handle_message(data):

    if not isinstance(data, dict):
        return

    with state_lock:

        user = users.get(request.sid)

        if not user:
            return

        room_id = user["room_id"]

        if not is_room_active(room_id):
            return

        nickname = user["nickname"]
        user_id = user["userID"]

    message_content = data.get(
        "message",
        ""
    )

    if not isinstance(message_content, str):
        return

    message_type = data.get(
        "type",
        "text"
    )

    if not isinstance(message_type, str):
        return

    message = {
        "userID": user_id,
        "nickname": nickname,
        "type": message_type,
        "message": message_content,
        "timestamp": datetime.now(
            timezone.utc
        ).isoformat()
    }

    try:

        save_message(
            room_id,
            message
        )

        emit(
            "new_message",
            message,
            room=room_id
        )

    except Exception as error:

        print(
            f"[Chat] Message saving failed: {error}"
        )

        emit(
            "message_error",
            {
                "error": "Failed to save message."
            },
            to=request.sid
        )


@socketio.on("disconnect")
def handle_disconnect():

    sid = request.sid

    with state_lock:

        user = users.pop(sid, None)
        connection_rooms.pop(sid, None)

        if user:

            recoverable_sessions[sid] = {
                "userID": user["userID"],
                "nickname": user["nickname"],
                "token_hash": user["token_hash"],
                "room_id": user["room_id"],
                "expires_at": (
                    time() +
                    app.config["RECOVERY_EXPIRY"]
                )
            }

    if user:

        print(
            f"[Chat] Disconnected: "
            f"{user['nickname']} "
            f"from room {user['room_id']}"
        )