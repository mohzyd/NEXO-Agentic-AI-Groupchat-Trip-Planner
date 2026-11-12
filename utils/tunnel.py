"""
===============[ Tunneling system ]===============

This system allows you to make an opened port on your device as a public URL that anyone can access it.
The life-time of the public URL is until the tunnel is closed, the process is terminated, or the host device is shutted down.

Please have a look at the Tunnel class and read the descriptions to understand how to use this system.
Have a nice day <3
"""
from __future__  import annotations
from .file       import get_local_app_data_path
from typing      import Tuple, Callable, Self
from dataclasses import dataclass
from queue       import Queue, Empty
from pathlib     import Path
import subprocess, requests
import threading,  atexit
import time, re,   config
import platform,   random



class TunnelsData:
    """
    Data class for storing tunnels information & any required information.
    """

    lock: threading.Lock       = threading.Lock()
    tunnels: dict[str, Tunnel] = {}
    ports:   set[int]          = set()

class ErrorCodes:
    """
    Error codes for tunnel operations. Helps to identify the problem.
    """

    SERVICE_NOT_AVAILABLE:       int = 0x01
    TUNNEL_ALREADY_CREATED:      int = 0x02
    TUNNEL_CREATING:             int = 0x03
    TUNNEL_TIMEOUT:              int = 0x04
    SERVICE_ALREADY_DOWNLOADING: int = 0x05
    SERVICE_NOT_FOUND:           int = 0x06

@dataclass
class TunnelResponse:
    """
    TunnelResponse class is a formula for all responses, makes it easier to handle your operations.
    """

    success:    bool              = False
    error_code: ErrorCodes | None = None
    reason:     str | None        = None
    url:        str | None        = None


class Tunnel:
    _created: bool = False
    _is_downloading: bool = False

    def __init__(
        self,
        *,
        name:    str = None,
        port:    int = None,
        timeout: int = 30
    ) -> None:
        """
        Initialize a new tunnel instance.
        
        Args:
            port: The port to use for the tunnel. If None, will raise a value error.
            timeout: The timeout in seconds for the tunnel creation process. Default is 30 seconds.
        """

        if (self._created):
            raise ValueError("Tunnel is already created")

        if not isinstance(name, str) or len(name.strip()) == 0:
            raise ValueError("Name must be a non-empty string")

        if (not self.__check_int_validality(port)):
            raise ValueError("Port must be an integer")

        with TunnelsData.lock:
            if port in TunnelsData.ports:
                raise ValueError("Port is already in use")

        if (not self.__check_int_validality(timeout)):
            raise ValueError("Timeout must be an integer")

        # greater timeout, better chance to connect. we should give the service its own time to establish.
        if (timeout < 5):
            raise ValueError("Timeout must be at least 5 seconds")

        self.name        = name.strip()
        self.port        = port
        self.timeout     = timeout
        self._created    = True
        self._closing    = False
        self.is_created  = False
        self.is_creating = False
        self.process     = None
        self.url         = None

        with TunnelsData.lock:
            TunnelsData.tunnels[self.name] = self
            TunnelsData.ports.add(self.port)

    def create_tunnel(self, callback: Callable[[TunnelResponse], None] = None) -> TunnelResponse:
        """
        Activate the tunnel, handle the tunnel creation process, returns a TunnelResponse object with url of the tunnel if successful.
        
        Returns:
            TunnelResponse: A response object containing the result of the tunnel creation process.
        """

        if (self.is_created):
            return TunnelResponse(
                reason="Tunnel is already created",
                error_code=ErrorCodes.TUNNEL_ALREADY_CREATED
            )

        if (self.is_creating):
            return TunnelResponse(
                reason="Tunnel in creating process.",
                error_code=ErrorCodes.TUNNEL_CREATING
            )

        self.is_creating    = True
        service_found, path = self.has_cloudflare_service()

        if (not service_found):
            self.is_creating = False
 
            return TunnelResponse(
                reason="Cloudflare tunnel service not found",
                error_code=ErrorCodes.SERVICE_NOT_AVAILABLE
            )

        self.process = subprocess.Popen(
            [path, "tunnel", "--url", f"http://127.0.0.1:{self.port}"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            creationflags=subprocess.CREATE_NO_WINDOW
        )

        threading.Thread(target=self.__creation_of_tunnel, args=(callback,), daemon=True).start()

        return TunnelResponse(
            success=True,
            reason="Tunnel in creation process"
        )

    def close(self) -> None:
        """
        Close the tunnel, handle the tunnel closing process.
        """

        if (self._closing or self.is_creating):
            return
        
        self._closing = True
        
        if (self.process and self.process.poll() is None):
            self.process.terminate()
            self.process.wait()
            self.process = None
            self.url     = None

        with TunnelsData.lock:
            TunnelsData.tunnels.pop(self.name, None)
            TunnelsData.ports.discard(self.port)
        
        self._created = False
        self._closing = False
        atexit.unregister(self.close)
        return

    def is_running(self) -> bool:
        """
        Check if the tunnel is running.
        
        Returns:
            bool: True if the tunnel is running, False otherwise.
        """

        return self.process is not None and self.process.poll() is None

    def get_url(self) -> str | None:
        """
        Get the URL of the tunnel.
        
        Returns:
            str | None: The URL of the tunnel if it's created, None otherwise.
        """
        
        return self.url if isinstance(self.url, str) else None

    @staticmethod
    def download_service(
        on_progress: Callable[[float, float],     None] | None = None,
        on_complete: Callable[[bool, str | None], None] | None = None
    ) -> TunnelResponse:
        """
        Download the cloudflare tunnel service.
        
        Args:
            callback (Callable[[bool, float, float | None, str | None] | None, optional): A callback function to be to send progress updates during the download. Will send None when the service provider doesn't provide content-length.
            
        Returns:
            TunnelResponse: A response object containing the result of the download.
        """
        
        if (Tunnel._is_downloading):
            return TunnelResponse(
                reason="Service is already being downloaded",
                error_code=ErrorCodes.SERVICE_ALREADY_DOWNLOADING
            )

        if (on_progress is not None and callable(on_progress)):
            progress_callback = lambda downloaded, total: on_progress(downloaded, total)
        else:
            progress_callback = lambda downloaded, total: None

        if (on_complete is not None and callable(on_complete)):
            complete_callback = lambda success, error: on_complete(success, error)
        else:
            complete_callback = lambda success, error: None

        machine = platform.machine().lower()
        url     = config.CLOUDFLARE_SERVICE_URLS.get(machine)

        if (url is None):
            Tunnel._is_downloading = False
            return TunnelResponse(
                reason=f"Unfortunately, we couldn't find a suitable service for your system machine \"{machine}\"",
                error_code=ErrorCodes.SERVICE_NOT_FOUND
            )

        destination = get_local_app_data_path() / f"{config.CLOUDFLARE_SERVICE_NAME}.exe"
        temp        = destination.with_name(f"{destination.name}_{random.random()}.tmp")
        destination.parent.mkdir(parents=True, exist_ok=True)

        threading.Thread(target=Tunnel.__download_logic, args=(progress_callback, complete_callback, url, destination, temp), daemon=True).start()
        return TunnelResponse(
            success=True
        )

    @staticmethod
    def has_cloudflare_service() -> Tuple[bool, str]:
        """
        Check if the cloudflare service is available.
        
        Returns:
            Tuple[bool, str]: A tuple containing a boolean indicating if the service is available and the path to the service if it is available.
        """

        storage_path = get_local_app_data_path()
        if not storage_path.exists():
            return False, f"Cloudflare service not found as \"{config.CLOUDFLARE_SERVICE_NAME}.exe\""
        
        if not storage_path.is_dir():
            return False, f"Cloudflare service not found as \"{config.CLOUDFLARE_SERVICE_NAME}.exe\""

        for file in storage_path.iterdir():
            if file.suffix != ".exe":
                continue

            if file.name in [f"{config.CLOUDFLARE_SERVICE_NAME}.exe", config.CLOUDFLARE_SERVICE_NAME]:
                return True, file.resolve()

        return False, f"Cloudflare service not found as \"{config.CLOUDFLARE_SERVICE_NAME}.exe\""

    @staticmethod
    def get_tunnel_by_name(name: str) -> Self | None:
        """
        Get a tunnel by its name.
        
        Args:
            name: The name of the tunnel to get.
            
        Returns:
            Self | None: The tunnel if it exists, None otherwise.
        """

        if not isinstance(name, str) or len(name.strip()) == 0:
            return None

        with TunnelsData.lock:
            return TunnelsData.tunnels.get(name)

    @staticmethod
    def close_all_tunnels() -> None:
        """
        Close all tunnels.
        """

        with TunnelsData.lock:
            tunnels = list(TunnelsData.tunnels.values())
        
        for tunnel in tunnels:
            tunnel.close()

    @staticmethod
    def __download_logic(
        on_progress: Callable[[float, float],     None],
        on_complete: Callable[[bool, str | None], None],
        url:         str  | None = None,
        destination: Path | None = None,
        temp:        Path | None = None
    ) -> None:
        """
        A private method to download the service from the given URL and save it to the destination path.
        Caution: This function should not be called directly, use "Tunnel.download_service" method instead.
        
        Args:
            callback:     A callback function to be called when the download is complete.
            url:          The URL to download the service from.
            destination:  The path to save the downloaded service.
            temp:         The temporary path to save the downloaded service.
        """

        if Tunnel._is_downloading or url is None or destination is None or temp is None:
            return

        Tunnel._is_downloading = True

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
                        on_progress(downloaded, total_size)

            if (total_size > 0) and downloaded != total_size:
                temp.unlink(missing_ok=True)
                on_complete(False, "Downloaded content doesn't match the expected size")
                return

            temp.replace(destination)
            on_complete(True, None)
            Tunnel._is_downloading = False

        except requests.RequestException:
            temp.unlink(missing_ok=True)
            on_complete(False, "Failed to download the service")
            Tunnel._is_downloading = False

    def __check_int_validality(self, value: int) -> bool:
        """
        A private method to check if the value is a valid integer.
        
        Args:
            value (int): The value to check.
        
        Returns:
            bool: True if the value is a valid integer, False otherwise.
        """

        return value is not None and isinstance(value, int)

    def __creation_of_tunnel(self, callback: Callable[[TunnelResponse], None] | None = None) -> None:
        """
        A private method to create a tunnel using the cloudflared service.
        
        Args:
            (Optional) callback (Callable[[TunnelResponse], None] | None): The callback function to execute when the tunnel is created.
        """

        if callback is not None and callable(callback):
            executor = lambda res: callback(res)
        else:
            executor = lambda res: None

        output_queue = Queue()
        url          = None
        start_time   = time.monotonic()

        threading.Thread(target=self.__extracting_url, args=(self.process, output_queue), daemon=True).start()

        while (time.monotonic() - start_time < self.timeout):
            remaining = self.timeout - (time.monotonic() - start_time)

            try:
                line = output_queue.get(timeout=remaining)
            except Empty:
                break

            if line is None:
                break

            match = re.search(r"https://[a-zA-Z0-9\-]+\.trycloudflare\.com", line)
            if match:
                url = match.group(0)
                break

        if (url is None):
            self.process.terminate()
            self.process.wait()
            self._created    = False
            self.process     = None
            self.is_creating = False

            executor(TunnelResponse(
                success=False,
                reason="Failed to create tunnel. Timeout reached.",
                error_code=ErrorCodes.TUNNEL_TIMEOUT
            ))

            return
        
        self.url         = url
        self.is_created  = True
        self.is_creating = False
        atexit.register(self.close)
        
        executor(TunnelResponse(
            success=True,
            url=url
        ))

        return

    def __extracting_url(self, process: subprocess.Popen, output_queue: Queue) -> None:
        """
        A private method to extract the URL from the process output.
        
        Args:
            process (subprocess.Popen): The process to extract the URL from.
            output_queue (Queue): The queue to put the URL in.
        """

        for line in iter(process.stdout.readline, ""):
            if line:
                output_queue.put(line)

        output_queue.put(None)