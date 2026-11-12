"""
== Helper section ==
helpers' functions is used to organize the pipes system that puts all listeners in one place to make the edit easier in future.
every type of process in this project has its own helper file except flask because it doesn't require any listeners that is dependent on the pipes system.
common_listeners contains functions that are used in all client side process that is supported like webview or flask, it provides one interface that only
kill the process if the server decide to do it.
"""

from .server import *
from .webview import *
from utils import Pipes
import os

def common_listeners() -> None:
    """
    Creates the listeners that are participated in all client side process.
    """
    
    @Pipes.add_listener
    def kill_your_self(connection_id: str, data: dict) -> None:
        """
        When the server execute it, it will clean and clean the no longer needed process.
        ( Client Side Listener )
        """

        os._exit(0)