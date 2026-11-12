"""
Utilities section, contains base tools that are the application needs to run.
When importing everything from this folder in this file __init__.py, it's helping to call a tool only from the main folder name like:
    -   "from utils import Pipes"
"""

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
    """
    It manages timers for the application by setting the timestamp in format of MS (milliseconds) and its callback with id.
    It will execute the callback when the time reached. It works on RAM Level, this means that if the process witch has the implementation of it is closed,
    the timer data will be lost and never executed.
    """

    _list: dict[str, threading.Timer] = {} # holds the timers to delete it later if needed

    @staticmethod
    def set(id: str, timestamp: int, callback: Callable[[], None]) -> None:
        """
        Set a timer with the given id, timestamp, and callback.
        
        Args:
            id (str): The id of the timer.
            timestamp (int): The timestamp in milliseconds.
            callback (Callable[[], None]): The callback to execute when the timer is triggered.
        """

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
        """
        Remove a timer with the given id.
        
        Args:
            id (str): The id of the timer to remove.
        """

        if not isinstance(id, str) or len(id.strip()) == 0:
            return

        timer = Timer._list.pop(id, None)

        if timer is None:
            return

        timer.cancel()