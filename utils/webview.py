from pathlib import Path
import screeninfo, webview, threading

class WebViewCreationOptions:
    """
    Provides options for creating a webview window.
    """

    def __init__(
        self, title: str  = "Main Window", api:        object = None,
        width:       int  = 800,           height:     int    = 600,   x:           int   = None,
        y:           int  = None,          resizable:  bool   = True,  fullscreen:  bool  = False,
        min_width:   int  = 800,           min_height: int    = 600,   hidden:      bool  = False,
        frameless:   bool = False,         use_shadow: bool   = True,  on_top:      bool  = False,
        on_center:   bool = False,         minimized:  bool   = False, maximized:   bool  = False,
        max_width:   int  = 800,           max_height: int    = 600
    ) -> None:
        self.title      = title
        self.api        = api               # API object to expose to the webview
        self.width      = width
        self.height     = height
        self.x          = x
        self.y          = y
        self.resizable  = resizable
        self.fullscreen = fullscreen
        self.min_width  = min_width
        self.min_height = min_height
        self.hidden     = hidden            # Hide the window on creation
        self.frameless  = frameless
        self.use_shadow = use_shadow
        self.on_top     = on_top            # Keep the window on top of other windows or processes (like taskbar)
        self.on_center  = on_center         # Center the window on the screen
        self.minimized  = minimized         # Minimize the window on creation
        self.maximized  = maximized         # Maximize the window on creation


class WebViewHandler:
    __current_window: webview.Window | None = None
    __visible: bool = False
    __lock: threading.Lock = threading.Lock()

    def __init__(
        self,
        options: WebViewCreationOptions = WebViewCreationOptions(),
        *,
        html_path: Path
    ) -> None:
        """
        Creates a webview window with the given options and html path.
        html path should be written as a keyword argument as html_path=Your Path as String or Path object.
        * NOTE: each webview window can only be created once per process because it requires a main thread.

        raises:
            TypeError:         If options is not an instance of WebViewCreationOptions or html_path is not an instance of Path.
            RuntimeError:      If a window is already created.
            FileNotFoundError: If html_path does not exist or is not a file.
        """

        if (not isinstance(options, WebViewCreationOptions)):
            raise TypeError("options must be an instance of WebViewCreationOptions")

        if (isinstance(html_path, str)):
            html_path = Path(html_path)

        if (not isinstance(html_path, Path)):
            raise TypeError("html_path must be an instance of Path")

        if (isinstance(WebViewHandler.__current_window, webview.Window)):
            raise RuntimeError("Window already created. You can only create one window per process.")

        if (not html_path.exists() or not html_path.is_file()):
            raise FileNotFoundError("html_path must be a valid file")

        X, Y = options.x, options.y

        options.width  += 16
        options.height += 39

        if (options.on_center):
            _, x, y = self.get_center_coordinate(options.width, options.height)
            X, Y = x, y

        WebViewHandler.__visible = (not options.hidden and not options.minimized)

        WebViewHandler.__current_window = webview.create_window(
            title=options.title, url=html_path.as_uri(), js_api=options.api, width=options.width, height=options.height,
            x=X, y=Y, resizable=options.resizable, fullscreen=options.fullscreen, min_size=(options.min_width, options.min_height),
            hidden=options.hidden, frameless=options.frameless, shadow=options.use_shadow, on_top=options.on_top,
            minimized=options.minimized, maximized=options.maximized
        )
        WebViewHandler.__current_window._creation_options = options

        WebViewHandler.__setup_events()
        webview.start(debug=True)

    @staticmethod
    def get_current_window() -> webview.Window | None:
        """
        Returns the current window.
        """

        return WebViewHandler.__current_window

    @classmethod
    def set_title(cls, title: str) -> bool:
        """
        Sets the title of the current window.
        
        Args:
            title: The title to set.
            
        Returns:
            True if the title was set, False otherwise.
        """

        if (not isinstance(cls.__current_window, webview.Window)):
            return False

        if (not isinstance(title, str)):
            title = str(title)

        cls.__current_window.set_title(title)
        return True

    @classmethod
    def hide(cls) -> bool:
        """
        Hides the current window.
        
        Returns:
            True if the window was hidden, False otherwise.
        """

        if (not isinstance(cls.__current_window, webview.Window)):
            return False
        
        cls.__current_window.hide()

        with cls.__lock:
            cls.__visible = False

        return True

    @classmethod
    def show(cls) -> bool:
        """
        Shows the current window.
        
        Returns:
            True if the window was shown, False otherwise.
        """

        window = cls.__current_window
        
        if (not isinstance(window, webview.Window)):
            return False
        
        window.restore()
        window.show()
        window.on_top = True
        window.on_top = window._creation_options.on_top

        with cls.__lock:
            cls.__visible = True

        return True

    @classmethod
    def set_position(
        cls,
        x: int | None = None,
        y: int | None = None,
    ) -> bool:
        """
        Sets the position of the current window.
        
        Args:
            x: The x coordinate of the window.
            y: The y coordinate of the window.
            
        Returns:
            True if the position was set, False otherwise.
        """

        window = cls.__current_window
        
        if (not isinstance(window, webview.Window)):
            return False
        
        window.move(
            x if x is not None else window.x,
            y if y is not None else window.y
        )
        
        return True

    @classmethod
    def is_visible(cls) -> bool:
        """
        Checks if the current window is visible.
        
        Returns:
            True if the window is visible, False otherwise.
        """
        
        with WebViewHandler.__lock:
            return WebViewHandler.__visible

    @classmethod
    def get_center_coordinate(
        cls,
        width:  int | None = None,
        height: int | None = None
    ) -> tuple[bool, int | None, int | None]:
        if width is None or height is None:
            width  = cls.__current_window._creation_options.width  if width  is None else width
            height = cls.__current_window._creation_options.height if height is None else height

        if not isinstance(width, int) or not isinstance(height, int):
            return False, None, None
        
        monitors = screeninfo.get_monitors()
        for monitor in monitors:
            if (monitor.is_primary):
                X = (monitor.width  - width)  // 2
                Y = (monitor.height - height) // 2
                break
        
        return True, X, Y

    @staticmethod
    def __on_minimized() -> None:
        """
        Called when the window is minimized by webview.
        """
        
        with WebViewHandler.__lock:
            WebViewHandler.__visible = False
    
    @staticmethod
    def __on_restored() -> None:
        """
        Called when the window is restored by webview.
        """
        
        with WebViewHandler.__lock:
            WebViewHandler.__visible = True

    @staticmethod
    def __setup_events() -> None:
        """
        Sets up the events for the created webview window.
        
        Args:
            window: The window to set up the events for ( will be passed by webview ).
        """

        window = WebViewHandler.__current_window

        if not window:
            return

        window.events.minimized += WebViewHandler.__on_minimized
        window.events.restored  += WebViewHandler.__on_restored