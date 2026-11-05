from secrets import token_urlsafe
from threading import Event


PIPE_SHUTDOWN_TOKEN = token_urlsafe(32)
shutdown_event = Event()