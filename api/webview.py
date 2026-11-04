from typing  import Any
from utils   import Tunnel, WebViewHandler
from webview import Window
from config  import APP_DATA_FOLDER_NAME, CLOUDFLARE_SERVICE_NAME
import json, pyperclip

class API:
    def get_data(self) -> dict[str, Any]:
        """
        Get the data for the webview setup.
        
        Returns:
            dict[str, Any]: A dictionary containing the data for the webview setup.
        """

        return {
            "hasRequirement":         self.is_cloudservice_installed().get("status", False),
            "appDataFileName":        APP_DATA_FOLDER_NAME,
            "cloudflaredServiceName": f"{CLOUDFLARE_SERVICE_NAME}.exe",
            "chats":                  self.load_chats()
        }

    def is_cloudservice_installed(self) -> dict[str, Any]:
        """
        Check if the cloudflare service is installed.
        
        Returns:
            dict[str, Any]: A dictionary containing the status and message.
        """

        found, message = Tunnel.has_cloudflare_service()
        
        return {
            "status": found,
            "message": message if not found else ""
        }

    def start_cloudservice_download(self) -> tuple[bool, str]:
        """
        Download the cloudflare service.
        
        Returns:
            tuple[bool, str]: A tuple containing a boolean indicating success and a string with the result message.
        """

        response = Tunnel.download_service(
            lambda is_downloading, downloaded, total, message: API.send_to_frontend("downloadCloudflaredUpdate",
                {
                    "isDownloading": is_downloading,
                    "downloaded":    downloaded,
                    "total":         total,
                    "message":       message
                }
            )
        )

        return response.success, response.reason

    def copy_text_to_clipboard(self, text: str) -> tuple[bool, str]:
        """
        Copy text to the clipboard.
        
        Args:
            text (str): The text to copy to the clipboard.
            
        Returns:
            tuple[bool, str]: A tuple containing a boolean indicating success and a string with the result message.
        """

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

    def load_chats(self) -> list[dict[str, Any]]:
        """
        Load the chats from the database.
        
        Returns:
            list[dict[str, Any]]: A list of dictionaries containing the chats.
        """

        #TODO: should be implemented when the chat system is ready
        # For now, just return an empty list
        return []

    def create_new_chat(self) -> tuple[bool, str]:
        """
        Create a new chat.
        
        Returns:
            tuple[bool, str]: A tuple containing a boolean indicating success and a string with the result message.
        """

        #TODO: should be implemented when the chat system is ready
        # For now, just reject the request
        return False, "Not implemented yet."

    def can_create_chat(self) -> bool:
        """
        Check if the user hit the maximum number of chats (the max is 4).
        
        Returns:
            bool: True if the user can create a new chat, False otherwise.
        """
        
        #TODO: check if user already reached the maximum number of chats (the max is 4)
        # For now, just return True
        return True

    @staticmethod
    def send_to_frontend(action: str = "", data: dict[str, Any] | None = None) -> None:
        """
        Send data to the frontend (webview page).

        Args:
            action (str): The action to send to the frontend  "should be present in the frontend as window.API.on(action name, callback(data))".
            data (dict[str, Any] | None): The data to send to the frontend. It will be passed as the first argument to the callback.
        """

        if not isinstance(action, str) or len(action.strip()) == 0:
            return
        
        webview = WebViewHandler.get_current_window()

        if isinstance(webview, Window):
            try:
                data_json = json.dumps(data or {}, ensure_ascii=False)
                js_action = json.dumps(action)
                js_data   = json.dumps(data_json, ensure_ascii=False)
                script    = f"window.API.pyExecutor({js_action}, {js_data})"

                webview.evaluate_js(script)
            except Exception as e:
                print(f"[WebView] Error sending to frontend: {e}")