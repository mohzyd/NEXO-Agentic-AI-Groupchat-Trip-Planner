"""
Webview listeners for the client-side process.
"""

from utils import Pipes, WebViewHandler

def create_webview_listeners() -> None:
    """
    Creates all the listeners for the Webview client-side process.
    """

    @Pipes.add_listener
    def show_your_self(connection_id: str, data: dict) -> None:
        """
        Shows the webview if it is not already visible.
        It will comes from the Server Side process when he asked for it.
        """

        is_visible = WebViewHandler.is_visible() # checking visibility
        if is_visible:
            return

        success, x, y = WebViewHandler.get_center_coordinate() # getting center coordinate
        if not success:
            return

        WebViewHandler.show() # showing webview
        WebViewHandler.set_position(x, y) # setting position