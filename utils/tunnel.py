from typing      import List, Self, Tuple, Callable
from dataclasses import dataclass
from .file       import get_local_app_data_path
from pathlib     import Path
import subprocess, requests, threading
import time, re, config, platform, random

class Processes:
    """
    A class to manage tunnels processes and holds their ports to avoid conflicts.
    """
    all_processes: List[subprocess.Popen] | None = None
    ports_in_use: set[int] | None                = None

class ErrorCodes:
    """
    Error codes for tunnel operations. Helps to identify the problem.
    """
    SERVICE_NOT_AVAILABLE: int       = 0x01
    TUNNEL_ALREADY_CREATED: int      = 0x02
    TUNNEL_CREATING: int             = 0x03
    TUNNEL_TIMEOUT: int              = 0x04
    INVALID_PORT_NUMBER: int         = 0x05
    TUNNEL_NOT_FOUND: int            = 0x06
    SERVICE_ALREADY_DOWNLOADING: int = 0x07
    SERVICE_NOT_FOUND: int           = 0x08

@dataclass
class Response:
    """
    Response class is a formula for all responses, makes it easier to handle your operations.
    """
    success: bool                 = False
    error_code: ErrorCodes | None = None
    reason: str | None            = None
    url: str | None               = None


class Tunnel:
    __closing: bool        = False
    __is_downloading: bool = False
    
    def __init__(
        self,
        *,
        port: int    = None,
        timeout: int = 30
    ) -> None:
        """
        Initialize a new tunnel instance.
        
        Args:
            port: The port to use for the tunnel. If None, will raise a value error.
            timeout: The timeout in seconds for the tunnel creation process. Default is 30 seconds.
        """

        if (not self.__check_int_validality(port)):
            raise ValueError("Port must be an integer")

        if (not self.__check_int_validality(timeout)):
            raise ValueError("Timeout must be an integer")

        # greater timeout, better chance to connect. we should give the service its own time to establish.
        if (timeout < 5):
            raise ValueError("Timeout must be at least 5 seconds")

        if (Processes.ports_in_use is None):
            Processes.ports_in_use = set()

        if (port in Processes.ports_in_use):
            raise ValueError("Port is already in use")

        self.port        = port
        self.timeout     = timeout
        self.is_created  = False
        self.is_creating = False
        self.is_closed   = False
        self.url         = None

        # Add port to the holding list to prevent multiple tunnels refered to the same port.
        Processes.ports_in_use.add(port)

    def __del__(self) -> None:
        if (Processes.ports_in_use is not None):
            Processes.ports_in_use.discard(self.port)

    def create_tunnel(self) -> Response:
        """
        Activate the tunnel, handle the tunnel creation process, returns a Response object with url of the tunnel if successful.
        
        Returns:
            Response: A response object containing the result of the tunnel creation process.
        """

        if (self.is_created):
            return Response(
                reason="Tunnel is already created",
                error_code=ErrorCodes.TUNNEL_ALREADY_CREATED
            )

        if (self.is_creating):
            return Response(
                reason="Tunnel in creating process.",
                error_code=ErrorCodes.TUNNEL_CREATING
            )

        self.is_creating    = True
        service_found, path = self.__has_cloudflare_service()

        if (not service_found):
            del self.is_creating
 
            return Response(
                reason="Cloudflare tunnel service not found",
                error_code=ErrorCodes.SERVICE_NOT_AVAILABLE
            )

        self.process = subprocess.Popen(
            [path, "tunnel", "--url", f"http://127.0.0.1:{self.port}"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )

        url        = None
        start_time = time.time()

        while (time.time() - start_time < self.timeout):
            line = self.process.stdout.readline()

            if not line:
                continue

            match = re.search(r"https://[a-zA-Z0-9\-]+\.trycloudflare\.com", line)
            if match:
                url = match.group(0)
                break

        if (url is None):
            self.process.terminate()
            self.process.wait()
            del self.process
            del self.is_creating

            return Response(
                reason="Failed to create tunnel. Timeout reached.",
                error_code=ErrorCodes.TUNNEL_TIMEOUT
            )
        
        self.url                     = url
        self.process.parent_instance = self
        Processes.all_processes.append(self.process)
        self.is_created = True
        del self.is_creating
        
        return Response(
            success=True,
            url=url
        )

    def close(self) -> Self:
        """
        Close the tunnel, handle the tunnel closing process.
        
        Returns:
            Self: The current instance of the tunnel, allowing for method chaining.
        """

        if (self.__closing):
            return self
        
        self.__closing = True
        
        if (self.process and self.process.poll() is None):
            self.is_closed = True
            Processes.all_processes.remove(self.process)
            self.process.terminate()
            self.process.wait()
            del self.process
        
        self.__closing = False
        return self

    def is_running(self) -> bool:
        """
        Check if the tunnel is running.
        
        Returns:
            bool: True if the tunnel is running, False otherwise.
        """

        return not self.is_closed

    @staticmethod
    def close_all_tunnels() -> None:
        """
        Closing all tunnels that are currently running.
        """

        processes_to_close = Processes.all_processes.copy()
        Processes.all_processes.clear()

        for process in processes_to_close:
            if (process.parent_instance is not None and isinstance(process.parent_instance, Tunnel)):
                process.parent_instance.is_closed = True

            process.terminate()
            process.wait()

    @staticmethod
    def download_service(callback: Callable[[bool, float, float | None, str | None], None] | None = None) -> Response:
        """
        Download the cloudflare tunnel service.
        
        Args:
            callback (Callable[[bool, float, float | None, str | None] | None, optional): A callback function to be to send progress updates during the download. Will send None when the service provider doesn't provide content-length.
            
        Returns:
            Response: A response object containing the result of the download.
        """
        
        if (Tunnel.__is_downloading):
            return Response(
                reason="Service is already being downloaded",
                error_code=ErrorCodes.SERVICE_ALREADY_DOWNLOADING
            )

        if (callback is not None and callable(callback)):
            executor = lambda is_downloading, downloaded, total, message: callback(is_downloading, downloaded, total, message)
        else:
            executor = lambda is_downloading, downloaded, total, message: None

        machine = platform.machine().lower()
        url     = config.CLOUDFLARE_SERVICE_URLS.get(machine)

        if (url is None):
            Tunnel.__is_downloading = False
            return Response(
                reason=f"Unfortunately, we couldn't find a suitable service for your system machine \"{machine}\"",
                error_code=ErrorCodes.SERVICE_NOT_FOUND
            )

        destination = get_local_app_data_path() / f"{config.CLOUDFLARE_SERVICE_NAME}.exe"
        temp        = destination.with_name(f"{destination.name}_{random.random()}.tmp")
        destination.parent.mkdir(parents=True, exist_ok=True)

        threading.Thread(target=Tunnel.__download_logic, args=(executor, url, destination, temp), daemon=True).start()
        return Response(
            success=True
        )

    @staticmethod
    def __download_logic(
        callback: Callable[[bool, float, float | None, str | None], None],
        url:         str  | None = None,
        destination: Path | None = None,
        temp:        Path | None = None
    ) -> None:
        if Tunnel.__is_downloading or url is None or destination is None or temp is None:
            return

        Tunnel.__is_downloading = True

        try:
            with requests.get(url, stream=True, timeout=(10, 30)) as response:
                response.raise_for_status()
                total_size = int(response.headers.get("content-length", 0))
                downloaded = 0

                with temp.open("wb") as file:
                    for chunk in response.iter_content(chunk_size=1024*16):
                        if not chunk:
                            continue

                        file.write(chunk)
                        downloaded += len(chunk)
                        callback(True, downloaded, total_size, None)

            if (total_size > 0) and downloaded != total_size:
                raise OSError("Downloaded content doesn't match the expected size")

            temp.replace(destination)
            callback(True, 0, None, None)
            Tunnel.__is_downloading = False

        except (requests.RequestException, OSError):
            temp.unlink(missing_ok=True)
            callback(False, 0, None, "Failed to download the service")
            Tunnel.__is_downloading = False

    @staticmethod
    def get_tunnel_on_port(port: int) -> Response:
        """
        Get the tunnel url that is running on the specified port.
        
        Args:
            port (int): The port number to check.
            
        Returns:
            Response: A response object containing the result of the check.
        """
        if not Tunnel.__check_int_validality(port):
            return Response(
                reason="Port number must be an integer",
                error_code=ErrorCodes.INVALID_PORT_NUMBER
            )

        copy_all_processes = Processes.all_processes.copy()

        for process in copy_all_processes:
            if process.parent_instance is None or not isinstance(process.parent_instance, Tunnel):
                continue

            if isinstance(process.parent_instance.port, int) and process.parent_instance.port == port:
                return Response(
                    success=True,
                    url=process.parent_instance.url
                )
        
        return Response(
            reason="No tunnel found on the specified port",
            error_code=ErrorCodes.TUNNEL_NOT_FOUND
        )


    def __check_int_validality(self, value: int) -> bool:
        """
        Check if the value is a valid integer.
        
        Args:
            value (int): The value to check.
        
        Returns:
            bool: True if the value is a valid integer, False otherwise.
        """

        return value is not None and isinstance(value, int)

    def __has_cloudflare_service(self) -> Tuple[bool, str | None]:
        """
        Check if the cloudflare service is available.
        
        Returns:
            Tuple[bool, str | None]: A tuple containing a boolean indicating if the service is available and the path to the service if it is available.
        """

        storage_path = get_local_app_data_path()
        if not storage_path.exists():
            return False, None
        
        if not storage_path.is_dir():
            return False, None

        for file in storage_path.iterdir():
            if file.suffix != ".exe":
                continue

            if file.name in config.CLOUDFLARE_SERVICE_NAME:
                return True, file.resolve()

        return False, None