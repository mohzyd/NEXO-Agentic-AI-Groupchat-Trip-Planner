from pathlib import Path
import screeninfo
import webview
from utils.pipe import Pipes, ConnectionFlags
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

        if (options.on_center):
            monitors = screeninfo.get_monitors()
            for monitor in monitors:
                if (monitor.is_primary):
                    X = (monitor.width  - options.width)  // 2
                    Y = (monitor.height - options.height) // 2
                    break

        options.width  += 16
        options.height += 39

        WebViewHandler.__current_window = webview.create_window(
            title=options.title, url=html_path.as_uri(), js_api=options.api, width=options.width, height=options.height,
            x=X, y=Y, resizable=options.resizable, fullscreen=options.fullscreen, min_size=(options.min_width, options.min_height),
            hidden=options.hidden, frameless=options.frameless, shadow=options.use_shadow, on_top=options.on_top,
            minimized=options.minimized, maximized=options.maximized
        )
        WebViewHandler.__current_window._creation_options = options

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
        return True

    @classmethod
    def show(cls) -> bool:
        """
        Shows the current window.
        
        Returns:
            True if the window was shown, False otherwise.
        """

        if (not isinstance(cls.__current_window, webview.Window)):
            return False
        
        cls.__current_window.show()
        return True

    @classmethod
    def set_bounds(
        cls,
        x:      int | None = None,
        y:      int | None = None,
        width:  int | None = None,
        height: int | None = None
    ) -> bool:
        """
        Sets the bounds of the current window.
        
        Args:
            x:      The x coordinate of the window.
            y:      The y coordinate of the window.
            width:  The width of the window.
            height: The height of the window.
            
        Returns:
            True if the bounds were set, False otherwise.
        """
        
        if (not isinstance(cls.__current_window, webview.Window)):
            return False
        
        cls.__current_window.move(
            x if x is not None else cls.__current_window.x,
            y if y is not None else cls.__current_window.y
        )

        if (width is not None or height is not None):
            options = cls.__current_window._creation_options
            cls.__current_window.resize(
                width  if (width  is not None and (options.min_width  <= width  <= options.max_width))  else cls.__current_window.width,
                height if (height is not None and (options.min_height <= height <= options.max_height)) else cls.__current_window.height
            )
        
        return True