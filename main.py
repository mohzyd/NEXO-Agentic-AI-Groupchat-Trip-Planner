from utils import (
    WebViewCreationOptions,
    WebViewHandler,
    Pipes, ConnectionFlags,
    ServerPipeAlreadyExistsError,
    get_file_in_app_path,
    get_runnable_path
)
from api.webview import API
from helper      import create_server_listeners
from config      import APP_NAME, APP_DEBUG
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
    parser.add_argument("--job", type=str,  required=False, default="")
    parser.add_argument("--room-id", type=str, required=False, default="")
    parser.add_argument("--port", type=int, required=False)

    args   = parser.parse_args()

    if args.type == "room":
        if not args.room_id or not args.port:
            parser.error("room workers require --room-id and --port")

        from server.room_app import run_room_server

        run_room_server(args.room_id, args.port)

    elif args.type == "server":
        try:
            server = Pipes(flags=ConnectionFlags.SERVER | ConnectionFlags.SERVER_EXIT_WHEN_IDLE)
            create_server_listeners()
            pipe_deadline = time.monotonic() + 5
            while not server.server_exists() and time.monotonic() < pipe_deadline:
                time.sleep(0.05)
            if not server.server_exists():
                raise RuntimeError("Pipe server did not become ready.")

            create_child("flask")
            create_child("webview")
            server.keep_server_alive_until()

        except ServerPipeAlreadyExistsError:
            create_child("webview")

    elif args.type == "client":

        if args.job == "flask":
            from server.main import run_server

            run_server()

        elif args.job == "webview":
            
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
                    Pipes.send({}, listener="__signout")
                    time.sleep(2)
                    os._exit(0)
                    return

                Pipes.remove_listener("server_has_job_response")
                Pipes.send({"job": "webview"}, listener="__set_job")
                create_interface()

            except Exception as e:
                if APP_DEBUG: print(f"[CLIENT ERROR] {type(e).__name__} : {e}")



if __name__ == "__main__":
    main()