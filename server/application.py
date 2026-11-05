import os
from uuid import uuid4

from flask import Flask
from flask_socketio import SocketIO


class FlaskConf:

    SECRET_KEY = os.environ.get(
        "FLASK_SECRET_KEY",
        str(uuid4())
    )

    DEBUG = False

    HOST = "127.0.0.1"
    PORT = 5000

    SOCKETIO_CORS_ALLOWED_ORIGINS = "*"

    RECOVERY_EXPIRY = 60 * 60 * 24 * 30


app = Flask(__name__)
app.config.from_object(FlaskConf)

socketio = SocketIO(
    app,
    cors_allowed_origins=app.config[
        "SOCKETIO_CORS_ALLOWED_ORIGINS"
    ],
    async_mode="threading"
)