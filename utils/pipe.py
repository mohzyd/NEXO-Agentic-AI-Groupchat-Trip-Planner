"""
===============[ Pipes system ]===============
Sometimes when you trying to build a new project, at the end, you realize that you need to separate your action in different processes.
For example, you want to build an interface, and you want to handle some actions but the problem when the user closed the interface,
suddenly the process will be terminated and all the actions will be stopped. In this case the system appears. Now you can separate
your actions into different processes and communicate between them using pipes that even if the user closed the interface, your
actions will still be executed until you decide when it stops.

-- Main methods:

 1: Creating a pipe:
   A pipe can be created in three ways:
   from utils.pipe import Pipes, ConnectionFlags

   Pipes(flags=ConnectionFlags.SERVER) - Creates a server pipe that will be precent until the user's device shutdown
   Pipes(flags=ConnectionFlags.SERVER | ConnectionFlags.SERVER_EXIT_WHEN_IDLE) - Creates a server pipe that will be closed when no clients are connected
   Pipes(flags=ConnectionFlags.CLIENT, job_name="your process goal (webview, flask, download_file, etc)") - Creates a client connection

 2: Adding/Removing listeners:
  from utils.pipe import Pipes

  1 - @Pipes.add_listener -- this will take the function name as the listener name
  2 - @Pipes.add_listener(name="sum") -- this will use the given name as the listener name
  def calculate(connection_id: str, data: dict) -> None:
    a, b = data.get("num_1", 0), data.get("num_2", 0)
    result = a + b
    Pipes.send({"result": result}, to_pipe_id=connection_id, listener="print_result")

  3 - Pipes.add_listener(calculate)
  4 - Pipes.add_listener(calculate, name="sum")

  * NOTE: you should write keyword argument "name" when you're tring to assign custom name.

  in removing:
    - in default -> Pipes.remove_listener("calculate")
    - with custom name -> Pipes.remove_listener("sum")

 3: Sending data:
    - Pipes.send({"key": "value"}, to_pipe_id="connection_id (optional and provided from executed listener)", listener="listener_name", sync=Boolean)
    - sync: if True, the function will wait for the data to be sent, if False, it will send the data in a thread and continue

 4: Exiting:
    my_pipe = Pipes(flags=ConnectionFlags.SERVER)
    my_pipe.exit()
    * NOTE: the exit method should executed from an instance not from the class.

-------

This a simple overview of how the system works and how to use it.
You can have a look at the class and see the methods with its own descriptions.

Have a nice day <3
"""

from typing      import Callable
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
    """
    An exception raised when a server pipe (independent process) already created and running.
    Throws when trying to create a new server pipe.
    """

    pass

class ServerPipeNotFoundError(Exception):
    """
    An exception raised when a server pipe (independent process) is not created yet.
    Throws when trying to create new client connection.
    """
    
    pass

class ConnectionFlags(IntFlag):
    """
    Flags to determine the type of connection you want from the pipes.
      - SERVER: To create a new server pipe.
        * SERVER_EXIT_WHEN_IDLE: To let the server decide if it should destory it self or not ( based on connection, if there aren't any connections, it will destroy itself ).
      - CLIENT: To create a new client connection.
    """
    
    SERVER                 = 0x1
    SERVER_EXIT_WHEN_IDLE  = 0x2
    CLIENT                 = 0x4

@dataclass
class ConnectionData:
    """
    A template for any client connection data. Mostly will used inside server process to separate clients, and in client-side just for server-side connection.

    Caution: Better not to used outside of Pipes class. let the class manage it.

    Attributes:
        id         ( String         ) -> A random unique identifier for each connection.
        handle     ( PyHANDLE | int ) -> A handle to the pipe connection, setted by the pipe library.
        connected  ( bool           ) -> A flag to determine if the connection is connected or not.
        job        ( String         ) -> A string to determine the job of the connection.
        write_lock ( threading.Lock ) -> A lock to prevent multiple threads from writing to the same connection.
    """

    id:         str
    handle:     pywintypes.HANDLEType | int
    connected:  bool           = False
    job:        str            = "unknown"
    write_lock: threading.Lock = field(default_factory=threading.Lock)

class PipeData:
    """
    A data saver class. Used to store all relevant data needed for the pipes system.

    Caution: Better not to used outside of Pipes class. let the class manage it.

    Attributes:
        lock            ( threading.RLock           ) -> A reentrant lock to prevent multiple threads from accessing the same data.
        listeners       ( dict[str, Callable]       ) -> A dictionary of listeners to be called when a message is received.
        connections     ( dict[str, ConnectionData] ) -> A dictionary of connections to be managed.
        client_job      ( str                       ) -> A string to determine the job of the client.
        is_server       ( bool                      ) -> A flag to determine if the current instance is a server or not.
        running         ( bool                      ) -> A flag to determine if the current instance is running or not.
        exit_when_idle  ( bool                      ) -> A flag to determine if the server should exit when idle or not.
        watcher_started ( bool                      ) -> A flag to determine if the watcher thread is started or not.
        exit_registered ( bool                      ) -> A flag to determine if the exit handler is registered or not.
    """

    lock:            threading.RLock           = threading.RLock()
    listeners:       dict[str, Callable]       = {}
    connections:     dict[str, ConnectionData] = {}
    on_disconnect:   dict[str, Callable]       = {}
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
        """
        Creates a server pipe. This will only executed from constructor, otherwise it will skipped.

        Args:
            exit_when_idle (bool): If True, the server will exit when no clients are connected.
        """

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
        """
        Creates a client pipe. This will only executed from constructor, otherwise it will skipped.

        Args:
            job_name (str): The name of the job to connect to.
        """
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

        self.__unregister_exit()

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
        """
        Sends data through the pipe.

        Args:
            data       (dict):       The data to send.
            listener   (str | None): The listener to send the data to.
            job        (str | None): The job to send the data to, if it provided as None, it will be sent to all running connected clients.
            to_pipe_id (str | None): The pipe ID to send the data to.
            sync       (bool):       If True, the data will be sent synchronously.

        if both job and to_pipe_id aren't provided, the data will be sent automatically to server-side and will be handled there.
        """

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
    def on_disconnect(job: str, fn: Callable[[], None]) -> None:
        """
        Registers a function to be called when a connection is lost.
        
        args:
            job: str
                The job to register the disconnect handler for.
            fn: Callable
                The function to call when the connection is lost.
        """
        
        with PipeData.lock:
            PipeData.on_disconnect[job] = fn

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
        """
        The main server loop that handles incoming connections and data.
        Warning: this method runs in a separate thread and should not be called directly. Also, it must be executed once by the Pipes system.
        """

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
        """
        The client loop that handles incoming data from a connected pipe.
        Warning: this method runs in a separate thread and should not be called directly. Also, it must be executed once by each connected pipe.
        """

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
        """
        Routes a message to the specified job or all jobs.
        Warning: this method should not be called outside the send method.
        """
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
        """
        Starts the idle watcher thread. Will be executed once and only if the SERVER_EXIT_WHEN_IDLE flag is setted.
        Warning: this method should not be called outside the Pipes system.
        """

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
                        with PipeData.lock:
                            PipeData.running = False
        
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
            
            disconnection_fn = PipeData.on_disconnect.pop(connection.job, None)
            if disconnection_fn is not None:
                disconnection_fn(connection.job)

        if handle is not None:
            try:
                win32file.CloseHandle(handle)
            except pywintypes.error:
                pass

    def __register_exit(self) -> None:
        """
        Registers the exit handler for the pipes system.
        Warning: this method should not be called outside the Pipes system.
        """

        with PipeData.lock:
            if PipeData.exit_registered:
                return
            
            PipeData.exit_registered = True
        
        atexit.register(self.__on_exit)

    def __unregister_exit(self) -> None:
        """
        Unregisters the exit handler for the pipes system.
        Warning: this method should not be called outside the Pipes system.
        """

        with PipeData.lock:
            if not PipeData.exit_registered:
                return
            
            PipeData.exit_registered = False
        
        atexit.unregister(self.__on_exit)

    @classmethod
    def __on_get_job(cls, connection: ConnectionData, data: dict) -> None:
        """
        A built-in listener that returns its own job when asked for it.
        Used in client-side. It helps the server-side to identify the client's job.
        """

        if not PipeData.is_server:
            cls.send({"job": PipeData.client_job}, listener="__set_job", job=APP_PIPE_SERVER_JOB)

    @classmethod
    def __on_set_job(cls, connection: ConnectionData, data: dict) -> None:
        """
        A built-in listener that updates the connection's job.
        Used in server-side. It updates the connection's job when the client sends its job.
        """

        job = data.get("job")
        if PipeData.is_server and isinstance(job, str) and len(job.strip()) > 0:
            connection.job = job
            cls.__log(f"[SERVER] Job updated to \"{job}\" for connection \"{connection.id}\"")

    @classmethod
    def __on_signout(cls, connection: ConnectionData, data: dict) -> None:
        """
        A built-in listener that drops the connection when the client signs out.
        Used in server-side.
        """

        if PipeData.is_server:
            cls.__drop(connection)
            cls.__log(f"[SERVER] Connection \"{connection.id}\" signed out")

    def __on_exit(self) -> None:
        """
        A method that executed automatically when the client process shuts down.
        It helps the server to drop the connection in short time.
        """

        if not PipeData.is_server:
            try:
                self.send({}, listener="__signout", job=APP_PIPE_SERVER_JOB, sync=True)
            except Exception as e:
                self.__log(f"[LOG] Failed to signout on exit: {e}")

    @staticmethod
    def __to_bytes(data: str) -> bytes:
        """
        A method to convert a string to bytes. It used when creating new payload.
        """

        if not isinstance(data, str) or data.strip() == "":
            return b""
        
        try:
            return data.encode("utf-8")
        except UnicodeEncodeError:
            return b""

    @staticmethod
    def __to_str(data: bytes) -> str:
        """
        A method to convert bytes to string. It used when parsing payload.
        """

        if not isinstance(data, bytes) or len(data) == 0:
            return ""

        try:
            return data.decode("utf-8")
        except UnicodeDecodeError:
            return ""

    @staticmethod
    def __new_payload(data: dict) -> bytes:
        """
        A method to create a new payload from a dictionary.
        
        Returns:
            bytes: The payload as bytes to travling in pipes.
        """
        try:
            return Pipes.__to_bytes(json.dumps(data))
        except Exception:
            return b""

    @staticmethod    
    def __parse_payload(data: bytes) -> dict:
        """
        A method to parse a payload from bytes to dictionary.
        
        Returns:
            dict: The payload as dictionary (recived data from pipes).
        """
        try:
            return json.loads(Pipes.__to_str(data))
        except Exception:
            return {}

    @staticmethod
    def __log(message: str) -> None:
        """
        A method prints a debugging messages when APP_PIPE_DEBUG_ENABLED is True.
        Better to be disabled in production mode.
        """
        if not APP_PIPE_DEBUG_ENABLED:
            return

        print(f"[PIPE] {message}")
