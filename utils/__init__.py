from .file import *
from .pipe import *
from .tunnel import *
from .webview import *
from .encryption import *
from .local_storage import *
from typing import Callable
from datetime import datetime
import socket, time, random
import threading



def get_random_port(timeout: int | None = None) -> int | None:
    """
    Get a random available port.
    
    Args:
        timeout (int | None): The timeout in seconds.
    
    Returns:
        int | None: The random available port, or None if no port is available.
    """

    if not isinstance(timeout, int) or timeout < 3:
        timeout = 3

    start_time = time.monotonic()

    while time.monotonic() - start_time < timeout:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                ran_port = random.randint(1024, 65535)
                sock.bind(("127.0.0.1", ran_port))
                return ran_port
        except OSError:
            pass

    return None

class Timer:
    _list: dict[str, threading.Timer] = {}

    @staticmethod
    def set(id: str, timestamp: int, callback: Callable[[], None]) -> None:
        if not isinstance(id, str) or len(id.strip()) == 0:
            return

        if not isinstance(timestamp, int) or timestamp == 0:
            return

        if not callable(callback):
            return

        target_time = datetime.fromtimestamp(timestamp / 1000)
        now         = datetime.now()
        delta       = (target_time - now).total_seconds()

        if delta <= 0:
            return

        timer = threading.Timer(delta, callback)
        timer.start()
        
        Timer._list[id] = timer

    @staticmethod
    def remove(id: str) -> None:
        if not isinstance(id, str) or len(id.strip()) == 0:
            return

        timer = Timer._list.pop(id, None)

        if timer is None:
            return

        timer.cancel()