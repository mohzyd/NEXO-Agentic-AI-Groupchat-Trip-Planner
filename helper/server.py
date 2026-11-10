from utils import (
    Pipes, LocalStorage,
    get_runnable_path, TunnelResponse,
    Tunnel, get_random_port, Timer, TunnelsData
)
from uuid  import uuid4
import subprocess, threading

def create_server_listeners() -> None:

    @Pipes.add_listener
    def has_job(connection_id: str, data: dict) -> None:
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
        Pipes.send({}, listener="show_your_self", job="webview")

    @Pipes.add_listener
    def delete_chat(connection_id: str, data: dict) -> None:
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

        chat_id = f"chat_{uuid4().hex[ : 8]}" if reload_id is None else reload_id

        storage = LocalStorage("chats")
        if reload_id is None:
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
        else:
            with storage.sync_update() as data:
                created_chats = data.get("created_chats", [])
                for chat in created_chats:
                    if chat["chat_id"] == reload_id:
                        chat["expire_time"] = chat_data.get("expire_time", 0)
                        break

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
        if not isinstance(job, str) or len(job.strip()) == 0:
            return
        
        chat_id = job[6 : ]
        tunnel  = Tunnel.get_tunnel_by_name(f"tunnel-{chat_id}")

        with TunnelsData.lock:
            print(TunnelsData.tunnels)

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