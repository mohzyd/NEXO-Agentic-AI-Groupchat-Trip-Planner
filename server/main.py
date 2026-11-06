"""Local Flask control API for managing isolated chat-room workers.

The control API is bound to the loopback interface. Each public chat room is
served by a separate Flask-SocketIO worker and Cloudflare tunnel managed by
:class:`server.room_manage.RoomManager`.
"""

import atexit
import os
import threading
import urllib.request
from secrets import compare_digest, token_urlsafe
from threading import Event, RLock

from flask import Flask, abort, jsonify, request
from utils.encryption import Encryptor
from utils.pipe import ConnectionFlags, Pipes
from werkzeug.serving import make_server

from server.room_manage import RoomManager


class FlaskConf:
    """Configuration for the private room-management API."""

    SECRET_KEY = os.environ.get("FLASK_SECRET_KEY", token_urlsafe(32))
    DEBUG = False
    HOST = "127.0.0.1"
    PORT = 5000


app = Flask(__name__)
app.config.from_object(FlaskConf)
room_manager = RoomManager()
ADMIN_TOKEN = os.environ.get("CHAT_ADMIN_TOKEN",token_urlsafe(32))
PIPE_SHUTDOWN_TOKEN = token_urlsafe(32)
shutdown_event = Event()


def require_admin() -> None:
    """Abort unless the request has the configured manager bearer token."""

    if not ADMIN_TOKEN:
        abort(
            503,
            description="Room management is not configured."
        )

    supplied_token = request.headers.get("Authorization", "")

    if not compare_digest(supplied_token, ADMIN_TOKEN):
        abort(401, description="Unauthorized.")


@app.route("/")
def index():
    """Return a small status response for the loopback manager service."""

    return jsonify({"service": "room manager", "status": "running"})


@app.route("/internal/shutdown", methods=["POST"])
def internal_shutdown():
    """Accept the authenticated shutdown request sent by the pipe listener."""

    supplied_token = request.headers.get("X-Shutdown-Token", "")

    if not compare_digest(supplied_token, PIPE_SHUTDOWN_TOKEN):
        abort(403)

    print("[Server] Shutdown requested through Pipes.")
    shutdown_event.set()

    return jsonify({"success": True}), 200


@app.route("/api/rooms", methods=["POST"])
def create_room():
    """Create a room from JSON settings and the protection request header.

    ``X-Room-Protected`` accepts ``true`` or ``false`` and defaults to false.
    A protected room's password is encrypted before it is passed to the room
    manager. The manager returns public metadata only, never the ciphertext.
    """

    require_admin()
    payload = request.get_json(silent=True)

    if not isinstance(payload, dict):
        return jsonify({"error": "Expected a JSON room configuration."}), 400

    name = payload.get("name", payload.get("chat_name", "Anonymous Chat"))

    if not isinstance(name, str) or not name.strip() or len(name.strip()) > 40:
        return jsonify({"error": "Room name must contain 1 to 40 characters."}), 400

    protection_header = request.headers.get(
        "X-Room-Protected",
        "false"
    ).strip().lower()

    if protection_header not in {"true", "false"}:
        return jsonify({"error": "X-Room-Protected must be true or false."}), 400

    is_protected = protection_header == "true"
    password = payload.get("password")

    if is_protected:
        if not isinstance(password, str) or not 6 <= len(password) <= 128:
            return jsonify({
                "error": "Protected rooms require a 6 to 128 character password."
            }), 400
        encrypted_password = Encryptor.encrypt(password)
    else:
        encrypted_password = None

    lifetime = payload.get("lifetime")

    if lifetime is not None and (
        isinstance(lifetime, bool) or
        not isinstance(lifetime, int) or
        lifetime not in {30, 60, 180}
    ):
        return jsonify({
            "error": "Lifetime must be 30, 60, 180 minutes, or null."
        }), 400

    groupchat = {
        "name": name.strip(),
        "isProtected": is_protected,
        "encryptedPassword": encrypted_password,
        "lifetime": lifetime
    }
    room = room_manager.create_room(groupchat)

    if room is None:
        return jsonify({"error": "Failed to create chat room."}), 500

    return jsonify(room), 201


@app.route("/api/rooms", methods=["GET"])
def list_rooms():
    """List active and inactive room metadata for the manager client."""

    require_admin()
    return jsonify({"rooms": room_manager.list_rooms()})


@app.route("/api/rooms/<room_id>", methods=["GET"])
def get_room(room_id: str):
    """Return safe details for one room, including inactive status."""

    require_admin()
    room = room_manager.get_room(room_id)

    if room is None:
        return jsonify({"error": "Room not found."}), 404

    return jsonify(room)


@app.route("/api/rooms/<room_id>", methods=["DELETE"])
def delete_room(room_id: str):
    """Deactivate a room without deleting its persisted message history."""

    require_admin()
    deactivated_room = room_manager.delete_room(room_id)

    if deactivated_room is None:
        return jsonify({"error": "Room not found."}), 404

    return jsonify({
        "success": True,
        "room_id": deactivated_room,
        "isInactive": True
    })


pipe = Pipes(
    flags=ConnectionFlags.CLIENT,
    job_name="flask"
)


@Pipes.add_listener(name="flask_shutdown")
def handle_pipe_shutdown(connection_id: str, data: dict) -> None:
    """Forward the pipe shutdown event to the local control API."""

    print("[Pipe] Shutdown command received.")

    def request_shutdown() -> None:
        """Send the authenticated local shutdown request asynchronously."""

        try:
            req = urllib.request.Request(
                f"http://127.0.0.1:{app.config['PORT']}/internal/shutdown",
                headers={"X-Shutdown-Token": PIPE_SHUTDOWN_TOKEN},
                method="POST"
            )

            urllib.request.urlopen(req, timeout=5).close()
        except Exception as error:
            print(f"[Pipe] Shutdown request failed: {error}")

    threading.Thread(target=request_shutdown, daemon=True).start()


_shutdown_lock = RLock()
_shutdown_started = False


def shutdown() -> None:
    """Deactivate rooms and release their tunnel and worker processes."""

    global _shutdown_started

    with _shutdown_lock:
        if _shutdown_started:
            return
        _shutdown_started = True

    print("[Server] Closing all chat rooms...")

    try:
        room_manager.close_all_rooms()
    except Exception as error:
        print(f"[Server] Room shutdown failed: {error}")

    print("[Server] Shutdown complete.")


atexit.register(shutdown)


def run_server() -> None:
    """Run the loopback-only manager API until shutdown is requested."""

    http_server = None
    print("[Server] Starting local room manager...")
    print(f"[Server] Address: http://{app.config['HOST']}:{app.config['PORT']}")

    try:
        Pipes.send(
            {"status": "starting", "port": app.config["PORT"]},
            listener="flask_status"
        )

        http_server = make_server(
            app.config["HOST"],
            app.config["PORT"],
            app,
            threaded=True
        )

        def stop_when_requested() -> None:
            """Stop the serving loop after the shutdown event is set."""

            shutdown_event.wait()
            http_server.shutdown()

        threading.Thread(target=stop_when_requested, daemon=True).start()
        http_server.serve_forever()

    except Exception as error:
        print(f"[Server] Startup/runtime error: {error}")
        raise

    finally:
        if http_server is not None:
            http_server.server_close()
        shutdown()


if __name__ == "__main__":
    run_server()
