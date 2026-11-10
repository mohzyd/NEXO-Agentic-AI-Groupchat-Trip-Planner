from utils import (
    WebViewCreationOptions,
    WebViewHandler,
    Pipes, ConnectionFlags,
    ServerPipeAlreadyExistsError,
    LocalStorage, Tunnel,
    get_file_in_app_path,
    get_runnable_path
)
from api.webview import API
from helper      import create_server_listeners, create_webview_listeners, common_listeners
from config      import APP_NAME, APP_DEBUG
from server      import run_chat_host
import argparse,   subprocess
import random, os, time
import threading

def create_child(child_job: str = "") -> None:
    if not isinstance(child_job, str) or len(child_job.strip()) == 0:
        return

    runnable_args = get_runnable_path()
    command = []

    command.extend(runnable_args)
    command.extend([
        "--type", "client",
        "--job", child_job
    ])

    subprocess.Popen(
        command,
        stdout=None,
        stderr=None
    )

def create_interface() -> None:
    interface_path = get_file_in_app_path("interface", "page", "webview.html")
    api            = API()
    WebViewHandler(
        options=WebViewCreationOptions(
            width=600, height=800, min_width=600, min_height=800,
            max_width=600, max_height=800, resizable=False,
            on_center=True, title=APP_NAME, api=api
        ),
        html_path=interface_path
    )

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--type", type=str, required=False, default="server")
    parser.add_argument("--job",  type=str,  required=False, default="")
    parser.add_argument("--portF", type=int, required=False, default=0)
    parser.add_argument("--chatIdF", type=str, required=False, default="")

    args   = parser.parse_args()

    if (args.type == "server"):
        try:
            server = Pipes(flags=ConnectionFlags.SERVER | ConnectionFlags.SERVER_EXIT_WHEN_IDLE)
            create_server_listeners()

            storage = LocalStorage("chats")
            with storage.sync_update() as data:
                created_chats = data.get("created_chats", [])

                for chat in created_chats:
                    chat["status"] = "Inactive"

                data.set("created_chats", created_chats)

            create_child("webview")
            server.keep_server_alive_until()
            server.send({}, listener="kill_your_self") # Asking all active process to close themselves
            Tunnel.close_all_tunnels()
            server.stop()

        except ServerPipeAlreadyExistsError:
            create_child("webview")

    elif args.type == "client":

        if args.job == "webview":
            
            try:
                checker = Pipes(
                    job_name="check_webview_" + str(random.random()),
                    flags=ConnectionFlags.CLIENT
                )

                response_event = threading.Event()
                response_data  = {}

                @Pipes.add_listener
                def server_has_job_response(connection_id: str, data: dict) -> None:
                    response_data.update(data)
                    response_event.set()
                
                checker.send({"job": "webview"}, listener="has_job")
                response_event.wait()
                has_job = response_data.get("exists", None)

                if has_job or has_job is None:
                    Pipes.send({}, listener="call_webview", sync=True)
                    Pipes.send({}, listener="__signout", sync=True)
                    time.sleep(2)
                    os._exit(0)
                    return

                Pipes.remove_listener("server_has_job_response")
                Pipes.send({"job": "webview"}, listener="__set_job")
                create_webview_listeners()
                common_listeners()
                create_interface()

            except Exception as e:
                if APP_DEBUG: print(f"[CLIENT WEBVIEW ERROR] {type(e).__name__} : {e}")

        elif args.job == "flask":

            try:
                Pipes(
                    job_name=f"flask-{args.chatIdF}",
                    flags=ConnectionFlags.CLIENT
                )

                Pipes.send({"created": True, "port": args.portF, "chat_id": args.chatIdF}, listener="flask_response")
                common_listeners()
                run_chat_host(
                    host="127.0.0.1",
                    port=args.portF,
                    chat_id=args.chatIdF
                )
            except Exception as e:
                if APP_DEBUG: print(f"[CLIENT FLASK ERROR] {type(e).__name__} : {e}")

if __name__ == "__main__":
    main()