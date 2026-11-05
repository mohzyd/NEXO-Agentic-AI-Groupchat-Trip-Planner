import os
from hashlib import sha256
from secrets import compare_digest, token_urlsafe
from threading import RLock
from time import time
from urllib.parse import urlparse
from uuid import uuid4

from flask import abort, request

from utils.local_storage import LocalStorage

from server.application import app
from server.room_manage import RoomManager


chat_storage = LocalStorage("chats")
room_manager = RoomManager(
    port=app.config["PORT"]
)

users = {}
connection_rooms = {}
recoverable_sessions = {}

chat_lock = RLock()
state_lock = RLock()

ADMIN_TOKEN = os.environ.get("CHAT_ADMIN_TOKEN")

LOCAL_ROOM_ID = "__local__"
LOCAL_HOSTNAMES = {"localhost", "127.0.0.1"}


def require_admin():

    if not ADMIN_TOKEN:
        abort(
            503,
            description="Room management is not configured."
        )

    authorization = request.headers.get(
        "Authorization",
        ""
    )

    supplied_token = authorization.removeprefix(
        "Bearer "
    )

    if not compare_digest(
        supplied_token,
        ADMIN_TOKEN
    ):

        abort(
            401,
            description="Unauthorized."
        )


def hash_token(token: str) -> str:

    return sha256(
        token.encode("utf-8")
    ).hexdigest()


def generate_identity():

    user_id = str(uuid4())
    recovery_token = token_urlsafe(32)

    user = {
        "userID": user_id,
        "nickname": "Anonymous",
        "token_hash": hash_token(recovery_token)
    }

    return user, recovery_token


def recover_identity(
    old_sid: str,
    recovery_token: str,
    room_id: str
):

    if not isinstance(old_sid, str):
        return None, None

    if not isinstance(recovery_token, str):
        return None, None

    if not isinstance(room_id, str):
        return None, None

    with state_lock:

        previous = recoverable_sessions.get(old_sid)

        if not previous:
            return None, None

        if previous["room_id"] != room_id:
            return None, None

        if time() > previous["expires_at"]:

            recoverable_sessions.pop(old_sid, None)

            return None, None

        supplied_hash = hash_token(recovery_token)

        if not compare_digest(
            supplied_hash,
            previous["token_hash"]
        ):

            return None, None

        recoverable_sessions.pop(old_sid)

        new_token = token_urlsafe(32)

        user = {
            "userID": previous["userID"],
            "nickname": previous["nickname"],
            "token_hash": hash_token(new_token)
        }

        return user, new_token


def get_current_room():

    hostname = urlparse(
        "//" + request.host
    ).hostname

    if not hostname:
        return None

    if hostname.lower() in LOCAL_HOSTNAMES:
        return LOCAL_ROOM_ID

    return room_manager.get_room_by_host(
        hostname
    )


def is_room_active(room_id: str) -> bool:

    return (
        room_id == LOCAL_ROOM_ID or
        room_manager.get_room(room_id) is not None
    )


def load_chat_messages(room_id: str):

    with chat_lock:

        history = chat_storage.get(
            room_id,
            []
        )

        if not isinstance(history, list):
            return []

        return history


def save_message(
    room_id: str,
    message: dict
):

    with chat_lock:

        with chat_storage.sync_update() as data:

            history = data.get(room_id, [])

            if not isinstance(history, list):
                history = []

            history.append(message)

            data.set(room_id, history)