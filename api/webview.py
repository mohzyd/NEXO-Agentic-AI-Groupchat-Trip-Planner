from typing import Any
from utils  import Tunnel, WebViewHandler
from webview import Window
import pyperclip

class API:
    def get_data(self) -> dict[str, Any]:
        return {
            "hasRequirement": self.is_cloudservice_installed().get("status", False)
        }

    def is_cloudservice_installed(self) -> dict[str, Any]:
        return {
            "status": False,
            "message": "Cloudflared could not be detected. Check its location and try again."
        }

    def start_cloudservice_download(self) -> tuple[bool, str]:
        response = Tunnel.download_service(lambda is_downloading, downloaded, total, message: API.send_to_frontend("window.downloadCloudflaredUpdate", is_downloading, downloaded, total, message))
        print("response", response)
        return response.success, response.reason

    def copy_text_to_clipboard(self, text: str) -> tuple[bool, str]:
        if not isinstance(text, str) or len(text.strip()) == 0:
            return False, "Can not copy an non-string or empty string."

        try:
            pyperclip.copy(text)
            return True, ""
        except (
                pyperclip.PyperclipException,
                pyperclip.PyperclipWindowsException,
                pyperclip.PyperclipTimeoutException
            ) as e:
            return False, "An error occurred: " + str(e)

    @staticmethod
    def send_to_frontend(to_method: str = "", *args) -> None:
        if not isinstance(to_method, str) or len(to_method.strip()) == 0:
            return
        
        webview = WebViewHandler.get_current_window()

        if isinstance(webview, Window):
            one_line_args = ", ".join(str(arg) for arg in args)
            try:
                webview.evaluate_js(f"{to_method}({one_line_args})")
                print("send to", to_method, "with args:", one_line_args)
            except Exception as e:
                print(f"[WebView] Error sending to frontend: {e}")