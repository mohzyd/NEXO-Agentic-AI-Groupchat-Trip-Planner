from typing      import Callable, Any
from dataclasses import dataclass, field
from enum        import IntFlag
from config      import (
    APP_PIPE_DEBUG_ENABLED,
    APP_PIPE_NAME,
    APP_PIPE_CONNECTION_TYPE,
    APP_PIPE_TYPE,
    APP_PIPE_WAIT,
    APP_PIPE_ALLOWED_CLIENT,
    APP_PIPE_IN_BUFFER_SIZE,
    APP_PIPE_OUT_BUFFER_SIZE,
    APP_PIPE_MAX_BYTE_READ,
    APP_PIPE_POLL_INTERVAL,
    APP_PIPE_IDLE_CHECK_INTERVAL,
    APP_PIPE_IDLE_MAX_RETRIES,
    APP_PIPE_ERROR_SEM_TIMEOUT,
    APP_PIPE_ERROR_PIPE_CONNECTED,
    APP_PIPE_ERROR_MORE_DATA,
    APP_PIPE_BROKEN_CODES,
    APP_PIPE_SERVER_JOB,
    APP_PIPE_ALL_JOBS
)
import json,      atexit,    threading
import win32pipe, win32file, pywintypes
import uuid,      time,      os


class ServerPipeAlreadyExistsError(Exception):
    pass

class ServerPipeNotFoundError(Exception):
    pass

class ConnectionFlags(IntFlag):
    SERVER                 = 0x1
    SERVER_EXIT_WHEN_IDLE  = 0x2
    CLIENT                 = 0x4

@dataclass
class ConnectionData:
    id:         str
    handle:     Any
    connected:  bool           = False
    job:        str            = "unknown"
    write_lock: threading.Lock = field(default_factory=threading.Lock)

class PipeData:
    lock:            threading.RLock           = threading.RLock()
    listeners:       dict[str, Callable]       = {}
    connections:     dict[str, ConnectionData] = {}
    client_job:      str                       = ""
    is_server:       bool                      = False
    running:         bool                      = False
    exit_when_idle:  bool                      = False
    watcher_started: bool                      = False
    exit_registered: bool                      = False

class Pipes:
    __created: bool = False

    def __init__(
        self,
        *,
        job_name: str = '',
        flags: ConnectionFlags | None = None
    ) -> None:
        """
        Initializes a new pipe connection.
        Only one pipe can be created per process.
        
        Raises:
            RuntimeError:                  If a pipe already exists in this process
            TypeError:                     If flags is not a ConnectionFlags type
            ValueError:                    If flags are invalid (SERVER/CLIENT conflict, missing job_name, etc.)
            ServerPipeAlreadyExistsError:  If a server pipe already exists globally
            ServerPipeNotFoundError:       If a client pipe trying to be created but server pipe not found.

        Args:
            job_name: The name of the job to connect to (required for CLIENT mode)
            flags:    Connection flags (SERVER, CLIENT, SERVER_EXIT_WHEN_IDLE)
        """

        if self.__created:
            raise RuntimeError("Only one pipe allowed on each process.")

        if flags is None or not isinstance(flags, ConnectionFlags):
            raise TypeError("\"flags\" must be a ConnectionFlags type")

        is_server      = bool(flags & ConnectionFlags.SERVER)
        is_client      = bool(flags & ConnectionFlags.CLIENT)
        exit_when_idle = bool(flags & ConnectionFlags.SERVER_EXIT_WHEN_IDLE)

        if is_server and is_client:
            raise ValueError("\"SERVER\" and \"CLIENT\" cannot be used together")

        if exit_when_idle and not is_server:
            raise ValueError("\"SERVER_EXIT_WHEN_IDLE\" requires \"SERVER\"")

        if is_server:
            self.create_server(exit_when_idle)
            return

        if not isinstance(job_name, str) or len(job_name.strip()) == 0:
            raise ValueError("\"job_name\" must be a non-empty string")

        if is_client:
            self.create_client(job_name)

    def create_server(self, exit_when_idle: bool = False) -> None:
        if self.__created: return
        self.__created = True

        if self.server_exists():
            raise ServerPipeAlreadyExistsError("Server: A server pipe is already running.")
        
        PipeData.is_server      = True
        PipeData.running        = True
        PipeData.exit_when_idle = exit_when_idle
        self.__register_exit()
        threading.Thread(target=self.__server_loop, daemon=True).start()

    def create_client(self, job_name: str) -> None:
        if self.__created: return
        self.__created = True

        if not self.server_exists():
            raise ServerPipeNotFoundError("Client: No server pipe is running.")

        try:
            handle = win32file.CreateFile(
                APP_PIPE_NAME,
                win32file.GENERIC_READ | win32file.GENERIC_WRITE,
                0, None,
                win32file.OPEN_EXISTING,
                0, None
            )

            win32pipe.SetNamedPipeHandleState(
                handle, win32pipe.PIPE_READMODE_MESSAGE, None, None
            )
        except pywintypes.error as e:
            raise ServerPipeNotFoundError(f"Client: Failed to connect to server pipe: {e}")

        PipeData.client_job = job_name
        connection          = ConnectionData(id=APP_PIPE_SERVER_JOB, handle=handle, connected=True)

        with PipeData.lock:
            PipeData.connections[APP_PIPE_SERVER_JOB] = connection

        PipeData.is_server = False
        PipeData.running   = True
        self.__register_exit()
        threading.Thread(target=self.__client_loop, args=(connection,), daemon=True).start()

    def server_exists(self) -> bool:
        """
        Checks whether a server is running.
        """

        try:
            win32pipe.WaitNamedPipe(APP_PIPE_NAME, 1)
            return True
        except pywintypes.error as e:
            return e.winerror == APP_PIPE_ERROR_SEM_TIMEOUT

    def stop(self) -> None:
        """
        Stops the pipe server or client.
        """

        with PipeData.lock:
            PipeData.running = False
            connections = list(PipeData.connections.values())

        for connection in connections:
            self.__drop(connection)

    def disconnect_job(self, job: str) -> None:
        """
        Disconnects a specific job.
        Used in Server Side

        Args:
            job (str): The job to disconnect.
        """

        if not PipeData.is_server or not isinstance(job, str) or len(job.strip()) == 0:
            return

        with PipeData.lock:
            for connection in list(PipeData.connections.values()):
                if connection.job == job:
                    self.__drop(connection)
                    break

    @classmethod
    def send(
        cls,
        data:       dict,
        listener:   str | None = None,
        job:        str | None = None,
        to_pipe_id: str | None = None,
        sync:       bool       = False
    ) -> None:
        if not isinstance(data, dict):
            data = {}

        if isinstance(listener, str) and len(listener.strip()) > 0:
            data["_toListenerName"] = listener

        if PipeData.is_server:
            job = APP_PIPE_ALL_JOBS if job is None else job
            data["_fromJob"] = APP_PIPE_SERVER_JOB
        else:
            job = APP_PIPE_SERVER_JOB if job is None else job
            data["_toJob"]  = job
            data["fromJob"] = PipeData.client_job

        payload = cls.__new_payload(data)
        cls.__route(payload, job, to_pipe_id, sync)

    @classmethod
    def set_job(cls, job: str) -> None:
        """
        Sets the job for the current process.
        """
        
        if not isinstance(job, str) or len(job.strip()) == 0:
            return

        with PipeData.lock:
            server_connection = PipeData.connections.get(APP_PIPE_SERVER_JOB)
        
        if not PipeData.is_server and server_connection is not None and server_connection.connected:
            cls.send({"job": job}, listener="__set_job", job=APP_PIPE_SERVER_JOB)

    @staticmethod
    def add_listener(
        listener: Callable | None = None,
        *,
        name: str | None = None
    ) -> Callable:
        """
        Registers a listener function to be called when a message is received.
        It can be used as a decorator or called directly.
        
        You can use it in 4 ways:
        * @Pipes.add_listener                     -- will take the function name as the listener identifier
        * @Pipes.add_listener(name="my_listener") -- will use the provided name as the listener identifier
        * Pipes.add_listener(my_listener)
        * Pipes.add_listener(my_listener, name="my_listener")

        args:
            listener: Callable | None = None
                The listener function to register.
            name: str | None = None
                The name to register the listener under.

        returns:
            Callable
                The registered listener function.
        """
        
        def register(fn: Callable) -> Callable:
            choosen_name = name or fn.__name__

            with PipeData.lock:
                PipeData.listeners[choosen_name] = fn
            
            return fn
        
        return register(listener) if listener is not None else register

    @staticmethod
    def remove_listener(target: str | Callable) -> None:
        """
        Removes a listener function from the list of registered listeners.
        
        args:
            target: str | Callable
                The listener function or name to remove.
        """

        target = target if isinstance(target, str) else getattr(target, "__name__", None)

        if target is None:
            return

        with PipeData.lock:
            PipeData.listeners.pop(target, None)

    @staticmethod
    def has_job(job: str) -> bool:
        """
        Checks if a job is exists.
        Setted for server side only.
        
        args:
            job: str
                The job to check.
        
        returns:
            bool
                True if the job exists, False otherwise.
        """

        with PipeData.lock:
            if not PipeData.is_server:
                return False

            return any(connection.job == job for connection in PipeData.connections.values())

    def keep_server_alive_until(self) -> None:
        """
        Keeps the server alive until the process is terminated.
        """
        with PipeData.lock:
            if not PipeData.is_server:
                return

        while PipeData.running:
            time.sleep(1)

    @classmethod
    def __server_loop(cls) -> None:
        while PipeData.running:
            connection = None

            try:
                handle = win32pipe.CreateNamedPipe(
                    APP_PIPE_NAME,
                    APP_PIPE_CONNECTION_TYPE,
                    APP_PIPE_TYPE | APP_PIPE_WAIT,
                    APP_PIPE_ALLOWED_CLIENT,
                    APP_PIPE_OUT_BUFFER_SIZE,
                    APP_PIPE_IN_BUFFER_SIZE,
                    0, None
                )

                new_id     = f"pipe_{uuid.uuid4().hex[ : 12]}"
                connection = ConnectionData(id=new_id, handle=handle)

                with PipeData.lock:
                    PipeData.connections[new_id] = connection
                
                try:
                    win32pipe.ConnectNamedPipe(handle, None)
                except pywintypes.error as e:
                    if e.winerror != APP_PIPE_ERROR_PIPE_CONNECTED:
                        raise

                connection.connected = True
                threading.Thread(target=cls.__client_loop, args=(connection, ), daemon=True).start()
                cls.send({}, listener="__get_job", to_pipe_id=new_id)
                cls.__start_watcher()
            except pywintypes.error as e:
                cls.__log(f"[ERROR] Pipe creation/connection failed: {e}")
                if connection is not None:
                    cls.__drop(connection)
                time.sleep(0.5)

    @classmethod
    def __client_loop(cls, connection: ConnectionData) -> None:
        try:
            while PipeData.running and connection.connected:
                try:
                    _, available, _ = win32pipe.PeekNamedPipe(connection.handle, 0)
                    
                    if available == 0:
                        time.sleep(APP_PIPE_POLL_INTERVAL)
                        continue

                    message = []

                    while True:
                        result, data = win32file.ReadFile(connection.handle, APP_PIPE_MAX_BYTE_READ)

                        if data:
                            message.append(data)
                        
                        if result != APP_PIPE_ERROR_MORE_DATA:
                            message = b"".join(message)
                            break

                    message = cls.__parse_payload(message)

                    if message:
                        target = message.pop("_toJob", None)

                        # Pass the message to the target job
                        if PipeData.is_server and target and target != APP_PIPE_SERVER_JOB:
                            forwarded = cls.__new_payload(message)
                            cls.__route(forwarded, target, None, connection.id, sync=False)
                        
                        # Handles the message on local process
                        if not PipeData.is_server or target in [None, APP_PIPE_SERVER_JOB, APP_PIPE_ALL_JOBS]:
                            name = message.pop("_toListenerName", None)

                            internal = {
                                "__get_job": cls.__on_get_job,
                                "__set_job": cls.__on_set_job,
                                "__signout": cls.__on_signout
                            }.get(name)

                            if internal is not None and callable(internal):
                                internal(connection, message)
                                continue

                            # Post the message to listener that given by name or all listeners if there isn't name
                            with PipeData.lock:
                                if name is None:
                                    targets = list(PipeData.listeners.values())
                                else:
                                    fn      = PipeData.listeners.get(name)
                                    targets = [fn] if fn else []

                            if name is not None and len(targets) == 0:
                                cls.__log(f"[WARNING] No listener registered with \"{name}\"")
                            
                            for fn in targets:
                                try:
                                    fn(connection.id, dict(message))
                                except Exception as e:
                                    cls.__log(f"[ERROR] Listener \"{getattr(fn, '__name__', fn)}\" failed to execute: {e}")

                except pywintypes.error as e:
                    if getattr(e, "winerror", None) in APP_PIPE_BROKEN_CODES:
                        cls.__log(f"[LOG] Connection lost with \"{connection.id}\" with code \"{e.winerror}\"")
                        break
                    cls.__log(f"[LOG] Unexpected pipe error on \"{connection.id}\" : {e}")
                    time.sleep(0.1)

                except Exception as e:
                    cls.__log(f"[LOG] Unexpected error on \"{connection.id}\" : {e}")
                    break
        finally:
            cls.__drop(connection)

    @staticmethod
    def __route(
        payload: bytes,
        job: str,
        to_pipe_id: str | None = None,
        exclude:    str | None = None,
        sync:       bool       = False
    ) -> None:
        if not isinstance(payload, bytes) or not payload:
            return

        def send_message() -> None:
            with PipeData.lock:
                if not PipeData.is_server:
                    connection = PipeData.connections.get(APP_PIPE_SERVER_JOB)
                    targets    = [connection] if connection else []
                else:
                    connections = list(PipeData.connections.values())
                    if to_pipe_id:
                        targets = [conn for conn in connections if conn.id == to_pipe_id]
                    else:
                        targets = [
                            conn for conn in connections
                            if conn.connected and conn.id != exclude and (job == APP_PIPE_ALL_JOBS or conn.job == job)
                        ]

            for target in targets:
                if not target.connected or target.handle is None:
                    continue

                try:
                    with target.write_lock:
                        win32file.WriteFile(target.handle, payload)
                except pywintypes.error as e:
                    if getattr(e, "winerror", None) not in APP_PIPE_BROKEN_CODES:
                        Pipes.__log(f"[ERROR] Failed to send message to \"{target.id}\" connection will dropped: {e}")
                    target.connected = False # Will be cleaned up by __client_loop

        if sync:
            send_message()
        else:
            threading.Thread(target=send_message, daemon=True).start()

    @classmethod
    def __start_watcher(cls) -> None:
        with PipeData.lock:
            if PipeData.watcher_started or not PipeData.exit_when_idle:
                return
            PipeData.watcher_started = True

        def watch() -> None:
            retry_count = 0
            while PipeData.running:
                time.sleep(APP_PIPE_IDLE_CHECK_INTERVAL)

                with PipeData.lock:
                    clients = [client for client in PipeData.connections.values() if client.connected]
                
                if clients:
                    cls.__log(f"[IDLE CHECK]:\n\t-Connected Clients: \"{len(clients)}\"\n\t-With Jobs: {[client.job for client in clients]}")
                    retry_count = 0
                else:
                    retry_count += 1
                    cls.__log(f"[IDLE CHECK] retrying... [{retry_count}/{APP_PIPE_IDLE_MAX_RETRIES}]")

                    if retry_count >= APP_PIPE_IDLE_MAX_RETRIES:
                        cls.__log(f"[IDLE CHECK] [{retry_count}/{APP_PIPE_IDLE_MAX_RETRIES}]: No clients connected, exiting...")
                        cls.stop(cls)
                        os._exit(0)
        
        threading.Thread(target=watch, daemon=True).start()

    @staticmethod
    def __drop(connection: ConnectionData) -> None:
        """
        Forget a connection and close its handle.
        
        args:
            connection: ConnectionData
                The connection to forget.
        """

        with PipeData.lock:
            if PipeData.connections.get(connection.id) is connection:
                del PipeData.connections[connection.id]
            handle, connection.handle = connection.handle, None

        if handle is not None:
            try:
                win32file.CloseHandle(handle)
            except pywintypes.error:
                pass

    def __register_exit(self) -> None:
        with PipeData.lock:
            if PipeData.exit_registered:
                return
            
            PipeData.exit_registered = True
        
        atexit.register(self.__on_exit)

    def __unregister_exit(self) -> None:
        with PipeData.lock:
            if not PipeData.exit_registered:
                return
            
            PipeData.exit_registered = False
        
        atexit.unregister(self.__on_exit)

    @classmethod
    def __on_get_job(cls, connection: ConnectionData, data: dict) -> None:
        if not PipeData.is_server:
            cls.send({"job": PipeData.client_job}, listener="__set_job", job=APP_PIPE_SERVER_JOB)

    @classmethod
    def __on_set_job(cls, connection: ConnectionData, data: dict) -> None:
        job = data.get("job")
        if PipeData.is_server and isinstance(job, str) and len(job.strip()) > 0:
            connection.job = job
            cls.__log(f"[SERVER] Job updated to \"{job}\" for connection \"{connection.id}\"")

    @classmethod
    def __on_signout(cls, connection: ConnectionData, data: dict) -> None:
        if PipeData.is_server:
            cls.__drop(connection)
            cls.__log(f"[SERVER] Connection \"{connection.id}\" signed out")

    def __on_exit(self) -> None:
        if not PipeData.is_server:
            try:
                self.send({}, listener="__signout", job=APP_PIPE_SERVER_JOB, sync=True)
            except Exception as e:
                self.__log(f"[LOG] Failed to signout on exit: {e}")

    @staticmethod
    def __to_bytes(data: str) -> bytes:
        if not isinstance(data, str) or data.strip() == "":
            return b""
        
        try:
            return data.encode("utf-8")
        except UnicodeEncodeError:
            return b""

    @staticmethod
    def __to_str(data: bytes) -> str:
        if not isinstance(data, bytes) or len(data) == 0:
            return ""

        try:
            return data.decode("utf-8")
        except UnicodeDecodeError:
            return ""

    @staticmethod
    def __new_payload(data: dict) -> bytes:
        try:
            return Pipes.__to_bytes(json.dumps(data))
        except Exception:
            return b""

    @staticmethod    
    def __parse_payload(data: bytes) -> dict:
        try:
            return json.loads(Pipes.__to_str(data))
        except Exception:
            return {}

    @staticmethod
    def __log(message: str) -> None:
        if not APP_PIPE_DEBUG_ENABLED:
            return

        print(f"[PIPE] {message}")
