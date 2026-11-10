from typing  import Any
from utils   import Tunnel, WebViewHandler, Pipes, LocalStorage
from webview import Window
from config  import APP_DATA_FOLDER_NAME, CLOUDFLARE_SERVICE_NAME
import json, pyperclip, threading

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
            lambda downloaded, total: self.send_to_frontend("downloadCloudflaredUpdate", {
                "downloaded": downloaded,
                "total":      total
            }),
            lambda success, reason: self.send_to_frontend("downloadCloudflaredUpdateComplete", {
                "success": success,
                "reason":  reason
            })
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
        
        return LocalStorage("chats").get("created_chats", [])

    def create_new_chat(self, data: dict) -> tuple[bool, dict[str, Any]]:
        """
        Create a new chat.
        
        Returns:
            tuple[bool, dict[str, Any]]: A tuple containing a boolean indicating success and a dictionary with the result data.
        """

        if hasattr(self, "_data_wating"):
            return False, "Already creating a chat."

        self._data_wating = True

        chat_name = str(data.get("chat_name", "")).strip()
        if len(chat_name) == 0 or chat_name.isspace():
            delattr(self, "_data_wating")
            return False, "Chat name is required."

        if not (6 <= len(chat_name) <= 24):
            return False, "Chat name must be between 6 and 24 characters."

        is_valid_password = (any(
            (65 <= ord(c) <= 90)     # Uppercase letters
            or (97 <= ord(c) <= 122) # Lowercase letters
            or (48 <= ord(c) <= 57)  # Digits
            for c in data.get("password", "")
        ) and len(data.get("password", "")) >= 6) if data.get("privacy", "public") == "private" else True

        if not is_valid_password:
            delattr(self, "_data_wating")
            return False, "Password must contain a letter or number and be at least 6 characters long."

        event    = threading.Event()
        response = {}

        @Pipes.add_listener 
        def create_chat_response(connection_id: str, data: dict) -> None:
            response.update(data)
            event.set()

        Pipes.send({"data": data}, listener="create_new_chat")
        
        responded = event.wait(timeout=45)
        Pipes.remove_listener("create_chat_response")
        success = response.get("success", False) if responded else False
        message = response.get("message", "") if responded else "An error occurred while creating the chat."

        delattr(self, "_data_wating")
        return success, message

    def delete_chat(self, chat_id: str) -> tuple[bool, str]:
        """
        Delete a chat permanently.
        
        Args:
            chat_id (str): The ID of the chat to delete.
            
        Returns:
            tuple[bool, str]: A tuple containing a boolean indicating success and a message.
        """
        
        if hasattr(self, "_remove_waiting"):
            return False, "Already removing a chat."
        
        self._remove_waiting = True

        if not isinstance(chat_id, str) or len(chat_id) == 0:
            delattr(self, "_remove_waiting")
            return False, "Invalid chat ID."

        event    = threading.Event()
        response = {}

        @Pipes.add_listener 
        def delete_chat_response(connection_id: str, data: dict) -> None:
            response.update(data)
            event.set()

        Pipes.send({"chat_id": chat_id}, listener="delete_chat")
        
        responded = event.wait(timeout=15)
        Pipes.remove_listener("delete_chat_response")
        success = response.get("success", False) if responded else False
        message = response.get("message", "") if responded else "An error occurred while deleting the chat."

        delattr(self, "_remove_waiting")
        return success, message

    def reload_chat(self, chat_id: str, timestamp: int) -> tuple[bool, str]:
        """
        Reload a chat.
        
        Args:
            chat_id (str): The ID of the chat to reload.
        """

        if hasattr(self, "_reload_wating"):
            return False, "Already reloading a chat."
            
        self._reload_wating = True

        if not isinstance(chat_id, str) or len(chat_id) == 0:
            delattr(self, "_reload_wating")
            return False, "Invalid chat ID."

        event    = threading.Event()
        response = {}

        @Pipes.add_listener 
        def create_chat_response(connection_id: str, data: dict) -> None:
            response.update(data)
            event.set()

        Pipes.send({"reload_id": chat_id, "data": { "expire_time": timestamp or 0 }}, listener="create_new_chat")
        
        responded = event.wait(timeout=45)
        Pipes.remove_listener("create_chat_response")
        success = response.get("success", False) if responded else False
        message = response.get("message", "") if responded else "An error occurred while creating the chat."

        delattr(self, "_reload_wating")
        return success, message


    def get_chat_by_id(self, chat_id: str) -> tuple[dict, bool, str]:
        """
        Get a chat by its ID.
        
        Args:
            chat_id (str): The ID of the chat to get.
            
        Returns:
            tuple[dict, bool, str]: A tuple containing the chat data, a boolean indicating success, and a message.
        """

        if not isinstance(chat_id, str) or len(chat_id) == 0:
            return {}, False, "Invalid chat ID."

        found = False
        chat  = {}

        with LocalStorage("chats").sync_update() as data:
            for chat_data in data.get("created_chats", []):
                if chat_data["chat_id"] == chat_id:
                    found = True
                    chat  = chat_data
                    break

        return chat, found, "Chat not found" if not found else ""

    def can_create_chat(self) -> bool:
        """
        Check if the user hit the maximum number of chats (the max is 4).
        
        Returns:
            bool: True if the user can create a new chat, False otherwise.
        """
        
        storage = LocalStorage("chats")
        
        if not storage.has("created_chats"):
            storage.set("created_chats", [])
            storage.save()

        can_create = len(storage.get("created_chats", [])) < 4
        return can_create

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