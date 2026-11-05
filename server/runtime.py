import atexit
import threading
import urllib.request

from utils.pipe import ConnectionFlags, Pipes

from server.application import app, socketio
from server.chat_state import (
    connection_rooms,
    recoverable_sessions,
    room_manager,
    state_lock,
    users
)
from server.runtime_control import PIPE_SHUTDOWN_TOKEN


pipe = Pipes(
    flags=ConnectionFlags.CLIENT,
    job_name="flask"
)


@Pipes.add_listener(name="flask_shutdown")
def handle_pipe_shutdown(connection_id, data):

    print("[Pipe] Shutdown command received.")

    def request_shutdown():

        try:

            req = urllib.request.Request(
                f"http://127.0.0.1:{app.config['PORT']}/internal/shutdown",
                headers={
                    "X-Shutdown-Token": PIPE_SHUTDOWN_TOKEN
                },
                method="POST"
            )

            urllib.request.urlopen(
                req,
                timeout=5
            ).close()

        except Exception as error:

            print(
                f"[Pipe] Shutdown request failed: {error}"
            )

    threading.Thread(
        target=request_shutdown,
        daemon=True
    ).start()


_shutdown_lock = threading.RLock()
_shutdown_started = False


def shutdown():

    global _shutdown_started

    with _shutdown_lock:

        if _shutdown_started:
            return

        _shutdown_started = True

    print("[Server] Closing all chat rooms...")

    try:

        room_manager.close_all_rooms()

    except Exception as error:

        print(
            f"[Server] Room shutdown failed: {error}"
        )

    with state_lock:

        users.clear()
        connection_rooms.clear()
        recoverable_sessions.clear()

    print("[Server] Shutdown complete.")


atexit.register(shutdown)


def run_server():

    print("[Server] Starting Flask-SocketIO...")
    print(f"[Server] Async mode: {socketio.async_mode}")
    print(f"[Server] Address: http://{app.config['HOST']}:{app.config['PORT']}")

    try:

        Pipes.send(
            {
                "status": "starting",
                "port": app.config["PORT"]
            },
            listener="flask_status"
        )

        socketio.run(
            app,
            host=app.config["HOST"],
            port=app.config["PORT"],
            debug=False,
            use_reloader=False,
            allow_unsafe_werkzeug=True
        )

    except Exception as error:

        print(f"[Server] Startup/runtime error: {error}")
        raise

    finally:

        shutdown()