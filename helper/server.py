"""
Pipes system listeners for the server-side process.
"""

from utils import (
    get_runnable_path, TunnelResponse,
    Pipes,             LocalStorage,
    Tunnel,            get_random_port,
    Timer
)
from uuid     import uuid4
from datetime import datetime
import subprocess,   threading

def create_server_listeners() -> None:
    """
    Creates all the listeners for the server-side process.
    """

    @Pipes.add_listener
    def has_job(connection_id: str, data: dict) -> None:
        """
        Let's the client side check if the server has already this job or not.
        From Client Side it usually called like this:

        Py Example:
            Pipes.send({"job": "some_job_name"}, listener="has_job")

            # In the same side of the Client Side process it needs an callback to send the result in it.
            # You must have a function with name "server_has_job_response" to receive the result, it will send argument as this order:
            def server_has_job_response(connection_id: str, data: dict) -> None:
                print(data)  # {"exists": True/False}

            # You can release this function from listener list by calling Pipes.remove_listener("server_has_job_response") if you don't need it anymore.
        """

        job = data.get("job", "")

        if not isinstance(job, str) or len(job.strip()) == 0:
            return

        is_exists = Pipes.has_job(job)
        
        Pipes.send(
            {"exists": is_exists},
            listener="server_has_job_response",
            to_pipe_id=connection_id
        )

    @Pipes.add_listener
    def call_webview(connection_id: str, data: dict) -> None:
        """
        Calls the webview to show itself.
        In the main.py 'the entry point of the project' you will see the usage of it, the system will check if it already have a webview or not.
        If it have it already, the new process will ask the server to show the existing webview if it hidden.
        We don't want to create multiple webview windows.
        """

        Pipes.send({}, listener="show_your_self", job="webview")

    @Pipes.add_listener
    def delete_chat(connection_id: str, data: dict) -> None:
        """
        Deletes a chat by its ID.
        Server has the control of the chat lifecycle. Only the server can create, delete or reload the chat.
        Here the webview will ask the server to delete the chat and kill all related processes like cloudflare and flask processes.
        """

        chat_id = data.get("chat_id", None)
        
        if chat_id is None:
            Pipes.send({
                "success": False,
                "message": "Failed to delete chat \"No chat id provided\""
            }, listener="delete_chat_response", to_pipe_id=connection_id)
            return
        
        _remove_chat(chat_id)
        Pipes.send({}, listener="kill_your_self", job=f"flask-{chat_id}")
        
        Pipes.send({
            "success": True,
            "message": "Chat deleted successfully"
        }, listener="delete_chat_response", to_pipe_id=connection_id)

    @Pipes.add_listener
    def create_new_chat(connection_id: str, data: dict) -> None:
        """
        Creates a new chat.
        Server has the control of the chat lifecycle. Only the server can create, delete or reload the chat.
        Here the webview will ask the server to create a new chat and start the related processes like cloudflare and flask processes and set the timer if selected.
        The server will also pick a random port to run the chat on it. He will continue after reciving the accpetance response from flask that the chat is ready to use.
        """

        chat_data = data.get("data", None)
        reload_id = data.get("reload_id", None)

        if chat_data is None and reload_id is None:
            Pipes.send({
                "success": False,
                "message": "Failed to create chat \"No chat data provided\""
            }, listener="create_chat_response", to_pipe_id=connection_id)
            return

        port = get_random_port(timeout=5)
        
        if port is None:
            Pipes.send({
                "success": False,
                "message": "Failed to create chat \"No available port\""
            }, listener="create_chat_response", to_pipe_id=connection_id)
            return

        chat_id = f"chat_{uuid4().hex[ : 8]}" if reload_id is None else reload_id # Generate a unique chat id if the request is for creating new one otherwise it will use the provided chat id.
        storage = LocalStorage("chats")

        if reload_id is not None:
            is_active  = Pipes.has_job(f"flask-{reload_id}")
            is_expired = True

            for chat in storage.get("created_chats", []):
                if chat["chat_id"] == reload_id:
                    timestamp  = datetime.fromtimestamp(chat["expire_time"] / 1000) if chat["lifetime"] == False else None
                    delta      = (datetime.now() - timestamp).total_seconds() if timestamp is not None else None
                    is_expired = delta <= 0 if delta is not None else True
                    break

            if is_active or not is_expired:
                Pipes.send({
                    "success": False,
                    "message": "Failed to reload chat \"Chat already active or not expired\""
                }, listener="create_chat_response", to_pipe_id=connection_id)
                return

            with storage.sync_update() as data:
                created_chats = data.get("created_chats", [])
                for chat in created_chats:
                    if chat["chat_id"] == reload_id:
                        chat["expire_time"] = chat_data.get("expire_time", 0)
                        break

                data.set("created_chats", created_chats)
        else:
            with storage.sync_update() as data:
                created_chats = data.get("created_chats", [])
                created_chats.append({
                    "chat_id":     chat_id,
                    "name":        chat_data.get("chat_name", ""),
                    "short_name":  chat_data.get("short_name", ""),
                    "status":      "Inactive",
                    "privacy":     chat_data.get("privacy", "public"),
                    "password":    chat_data.get("password", ""),
                    "lifetime":    chat_data.get("lifetime", False),
                    "expire_time": chat_data.get("expire_time", 0),
                    "duration":    chat_data.get("duration", 0),
                    "created_at":  chat_data.get("created_at", ""),
                    "url":         None
                })

                data.set("created_chats", created_chats)

        command       = []
        runnable_args = get_runnable_path()
        
        command.extend(runnable_args)
        command.extend([
            "--type",     "client",
            "--job",      "flask",
            "--chatIdF",   chat_id,
            "--portF",     str(port)
        ])
        
        subprocess.Popen(
            command,
            stdout=None,
            stderr=None
        )

    @Pipes.add_listener
    def flask_response(connection_id: str, data: dict) -> None:
        """
        It's shows like it a listener for flask. Actually it is works with Server-Side process only.
        It receives the acceptance response from flask and let the server decide if it should continue or clean up.
        """

        created = data.get("created", False)
        port    = data.get("port", None)
        chat_id = data.get("chat_id", None)

        if not created or not port or chat_id is None:
            _remove_chat(chat_id)
            message = data.get("message", "Failed to create chat")
            Pipes.send({
                "success": False,
                "message": "Failed to create chat \"No chat ID provided\"" if chat_id is None else message
            }, listener="create_chat_response", job="webview")
            return

        event_holder = threading.Event()
        tunnel_url   = None

        def tunnel_response(response: TunnelResponse) -> None:
            nonlocal tunnel_url
            tunnel_url = response.url if response.success else None
            event_holder.set()

        tunnel = Tunnel(
            name=f"tunnel-{chat_id}",
            port=port,
            timeout=30
        )

        tunnel.create_tunnel(tunnel_response)
        event_holder.wait(timeout=35)

        if tunnel_url is None:
            _remove_chat(chat_id)
            Pipes.send({
                "success": False,
                "message": "Failed to create chat \"URL not provided\""
            }, listener="create_chat_response", job="webview")
            return
        
        remaining = None
        with LocalStorage("chats").sync_update() as data:
            created_chats = data.get("created_chats", [])
            for chat in created_chats:
                if chat.get("chat_id", "") == chat_id:
                    chat["url"]    = tunnel_url
                    chat["status"] = "Active"
                    remaining      = chat["expire_time"] if chat["lifetime"] == False else None
                    break
            
            data.set("created_chats", created_chats)

        if remaining is not None:
            Timer.set(f"timer-{chat_id}", remaining, lambda: Pipes.send({}, listener="kill_your_self", job=f"flask-{chat_id}"))

        Pipes.on_disconnect(f"flask-{chat_id}", lambda job: _flask_disconnection(job))
        Pipes.send({
            "success": True,
            "message": "Chat created successfully"
        }, listener="create_chat_response", job="webview")



    def _flask_disconnection(job: str) -> None:
        """
        A callback will be executed by the Pipes system when a process disconnects.
        It will clean up related process and remove the timer if it still exists. Also,
        it will update the chat status to "Inactive".

        This callback setted in the flask_response by Pipes.on_disconnect(the target process job name, the callback function).
        """

        if not isinstance(job, str) or len(job.strip()) == 0:
            return
        
        chat_id = job[6 : ] # extract the chat id from format "flask-CHAT_ID_HERE"
        tunnel  = Tunnel.get_tunnel_by_name(f"tunnel-{chat_id}")

        Timer.remove(f"timer-{chat_id}")
        if isinstance(tunnel, Tunnel):
            tunnel.close()

        with LocalStorage("chats").sync_update() as data:
            created_chats = data.get("created_chats", [])

            for chat in created_chats:
                if chat.get("chat_id", "") == chat_id:
                    chat["status"] = "Inactive"
                    break

            data.set("created_chats", created_chats)

    def _remove_chat(chat_id: str) -> None:
        storage = LocalStorage("chats")
        with storage.sync_update() as data:
            created_chats = data.get("created_chats", [])
            created_chats = [chat for chat in created_chats if chat.get("chat_id") != chat_id]
            data.set("created_chats", created_chats)