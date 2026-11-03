from config  import APP_DATA_FOLDER_NAME
from pathlib import Path
import sys


def get_file_in_app_path(*paths: str) -> Path:
    """
    A method that returns a full path for file inside the application directory,
    works even if the application is compiled to .exe
    """

    if (getattr(sys, 'frozen', False)):
        root_path = Path(sys.executable).resolve()
    else:
        root_path = Path(sys.argv[0]).parent.resolve()

    return root_path.joinpath(*paths).resolve()

def get_local_app_data_path() -> Path:
    """
    Returns the full path for the application data directory in the local app data folder.
    """
    return Path.home().joinpath("AppData", "local", APP_DATA_FOLDER_NAME).resolve()

def get_runnable_path() -> list[str]:
    """
    Returns the full path for the current running executable.
    """
    executable = str(Path(sys.executable).resolve())

    if (getattr(sys, 'frozen', False)):
        return [executable]
    
    script = str(Path(sys.argv[0]).resolve())
    return [executable, "-u", script]