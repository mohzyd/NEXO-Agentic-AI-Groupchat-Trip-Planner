from server.application import app, socketio
from server.routes import blueprint
from server.runtime import (
    PIPE_SHUTDOWN_TOKEN,
    pipe,
    run_server,
    shutdown
)
from server.runtime_control import shutdown_event

import server.socket_handlers as _socket_handlers


app.register_blueprint(blueprint)


if __name__ == "__main__":
    run_server()
