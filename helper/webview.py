from utils import Pipes, WebViewHandler

def create_webview_listeners() -> None:

    @Pipes.add_listener
    def show_your_self(connection_id: str, data: dict) -> None:
        is_visible = WebViewHandler.is_visible()
        if is_visible:
            return

        success, x, y = WebViewHandler.get_center_coordinate()
        if not success:
            return

        WebViewHandler.show()
        WebViewHandler.set_position(x, y)