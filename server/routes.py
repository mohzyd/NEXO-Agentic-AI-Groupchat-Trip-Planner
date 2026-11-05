import os
from secrets import compare_digest

from flask import Blueprint, abort, jsonify, request, send_file

from server.application import socketio
from server.chat_state import (
    connection_rooms,
    recoverable_sessions,
    require_admin,
    room_manager,
    state_lock,
    users
)
from server.runtime_control import PIPE_SHUTDOWN_TOKEN, shutdown_event


blueprint = Blueprint("chat", __name__)


@blueprint.route("/")
def index():

    return send_file(
        os.path.join(
            os.path.dirname(__file__),
            "test.html"
        )
    )


@blueprint.route(
    "/internal/shutdown",
    methods=["POST"]
)
def internal_shutdown():

    supplied_token = request.headers.get(
        "X-Shutdown-Token",
        ""
    )

    if not compare_digest(
        supplied_token,
        PIPE_SHUTDOWN_TOKEN
    ):
        abort(403)

    print("[Server] Shutdown requested through Pipes.")

    shutdown_event.set()

    return jsonify({
        "success": True
    }), 200


@blueprint.route(
    "/api/rooms",
    methods=["POST"]
)
def create_room():

    require_admin()

    room = room_manager.create_room()

    if room is None:

        return jsonify({
            "error": "Failed to create chat room."
        }), 500

    return jsonify(room), 201


@blueprint.route(
    "/api/rooms",
    methods=["GET"]
)
def list_rooms():

    require_admin()

    return jsonify({
        "rooms": room_manager.list_rooms()
    })


@blueprint.route(
    "/api/rooms/<room_id>",
    methods=["GET"]
)
def get_room(room_id):

    require_admin()

    room = room_manager.get_room(room_id)

    if room is None:

        return jsonify({
            "error": "Room not found."
        }), 404

    return jsonify(room)


@blueprint.route(
    "/api/rooms/<room_id>",
    methods=["DELETE"]
)
def delete_room(room_id):

    require_admin()

    deleted_room = room_manager.delete_room(
        room_id
    )

    if deleted_room is None:

        return jsonify({
            "error": "Room not found."
        }), 404

    with state_lock:

        affected_sids = [
            sid
            for sid, connected_room in connection_rooms.items()
            if connected_room == room_id
        ]

        for sid in affected_sids:

            users.pop(sid, None)
            connection_rooms.pop(sid, None)

        expired_sessions = [
            sid
            for sid, session in recoverable_sessions.items()
            if session["room_id"] == room_id
        ]

        for sid in expired_sessions:

            recoverable_sessions.pop(
                sid,
                None
            )

    for sid in affected_sids:

        socketio.server.disconnect(
            sid,
            namespace="/"
        )

    return jsonify({
        "success": True,
        "room_id": deleted_room,
        "disconnected_users": len(affected_sids)
    })