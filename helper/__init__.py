from .server import *
from .webview import *
from utils import Pipes
import os

def common_listeners() -> None:
    
    @Pipes.add_listener
    def kill_your_self(connection_id: str, data: dict) -> None:
        os._exit(0)