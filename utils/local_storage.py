from contextlib  import contextmanager
from .file       import get_local_app_data_path
from .encryption import Encryptor
from filelock    import FileLock
from config      import APP_STORAGES, APP_DEBUG
from typing      import get_args, Any, Iterator
import json



class _StorageSupplyHandle:
    _NOT_FOUND = object() # Sentinel value to indicate that a key was not found in case None is a valid value in the storage

    def __init__(self, data: dict) -> None:
        """
        Initialize the storage handle with the given data.
        Caution: Shouldn't be used directly. Used by the LocalStorage class.
        """

        self.__data   = data
        self.__closed = False

    def has(self, key: str) -> bool:
        """
        Check if a key exists in the storage. Allowed to use dot notation for nested keys.
        """
        
        value = self.__get_nested(key)
        return True if value is not self._NOT_FOUND else False

    def get(self, key: str, default: Any = None) -> Any:
        """
        Get a value from the storage. Allowed to use dot notation for nested keys.
        """

        value = self.__get_nested(key)
        return value if value is not self._NOT_FOUND else default

    def set(self, key: str, value: Any) -> None:
        """
        Set a value in the storage. Allowed to use dot notation for nested keys.
        """

        if self.__closed:
            raise RuntimeError("[LocalStorage] Cannot modify storage after it has been closed.")

        if not isinstance(key, str) or len(key.strip()) == 0:
            raise ValueError("[LocalStorage] Key must be a non-empty string.")

        key = key.strip()

        if key.startswith(".") or key.endswith("."):
            raise ValueError("[LocalStorage] Key cannot start or end with a dot.")

        keys    = key.split(".")
        current = self.__data

        for key in keys[ : -1]: # Making the root if not exists
            if key not in current:
                current[key] = {}
            current = current[key]

        current[keys[-1]] = value

    def _close(self) -> None:
        """
        Close the storage handle to prevent further modifications.
        """
        self.__closed = True

    def __get_nested(self, key: str) -> Any:
        """
        Get a nested value from the current data using dot notation.
        """

        if not isinstance(key, str) or len(key.strip()) == 0:
            return self._NOT_FOUND

        key = key.strip()

        if key.startswith("."):
            key = key[1 : ]

        if key.endswith("."):
            key = key[ : -1]

        keys    = key.split(".")
        current = self.__data

        for key in keys:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                return self._NOT_FOUND

        return current

        

class LocalStorage:
    _NOT_FOUND = object()

    def __init__(self, target_storage: APP_STORAGES):
        """
        Initialize the LocalStorage instance.
        
        Args:
            target_storage: The type of storage to use (e.g., "chats").
             - Allowed list exists in config file.
        """
        
        if target_storage not in get_args(APP_STORAGES):
            raise ValueError(f"[LocalStorage] Invalid storage type. Expected one of: {get_args(APP_STORAGES)}, got: {target_storage}")

        self.storage_path     = get_local_app_data_path() / f"{target_storage}.txt"
        self.__ensure_dependencies()
        self.__current_data   = self.load()
        self.__come_from_sync = False


    @contextmanager
    def sync_update(self) -> Iterator[_StorageSupplyHandle]:
        """
        Context manager for synchronized updates to the storage.
        Helps prevent race conditions when multiple threads try to update the storage simultaneously.

        Usage:
            with storage.sync_update() as data:
                # Use your handling logic here
                # Example
                if data.has("num"):
                    data.set("num", data.get("num") + 1)
        """

        with self.locker:
            data   = self.load()
            handle = _StorageSupplyHandle(data)
            self.__come_from_sync = True
            
            try:
                yield handle
                self.save(data)
                self.__current_data = data
            finally:
                handle._close()
                self.__come_from_sync = False

    def has(self, key: str) -> bool:
        """
        Check if a key exists in the storage.
        """

        return _StorageSupplyHandle(self.__current_data).has(key) 

    def get(self, key: str, default: Any = None) -> Any:
        """
        Get a value from the storage. Allowed to use dot notation for nested keys.
        """

        return _StorageSupplyHandle(self.__current_data).get(key, default)

    def set(self, key: str, value: Any) -> None:
        """
        Set a value in the storage. Allowed to use dot notation for nested keys.
        """

        with self.sync_update() as data:
            data.set(key, value)

    def load(self) -> dict:
        """
        Load and decrypt the storage file.
        """
        with self.locker:
            with self.storage_path.open("r") as file:
                data_string = file.read()

        if not data_string.strip():
            return {}

        try:
            decrypted_data = Encryptor.decrypt(data_string)
            loaded_data    = json.loads(decrypted_data)

            if not isinstance(loaded_data, dict):
                if APP_DEBUG: print(f"[LocalStorage] Invalid data format in storage file. Expected dict, got {type(loaded_data)}")
                return {}

            return loaded_data

        except Exception as e:
            if APP_DEBUG: print(f"[LocalStorage] Error decrypting data: {e}")
            return {}

    def save(self, data: dict | None = None) -> None:
        """
        Save the current data to the storage file.
        """
        try:
            data_string    = json.dumps(self.__current_data if data is None else data)
            encrypted_data = Encryptor.encrypt(data_string)

            if self.__come_from_sync:
                with self.storage_path.open("w") as file:
                    file.write(encrypted_data)
                return
            
            with self.locker:
                with self.storage_path.open("w") as file:
                    file.write(encrypted_data)

            self.__current_data = self.load()
        except Exception as e:
            if APP_DEBUG: print(f"[LocalStorage] Error saving data: {e}")

    def __ensure_dependencies(self):
        """
        Ensure both the storage file and its lock are created and accessible.
        """

        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self.storage_path.touch(exist_ok=True)

        lock_path   = self.storage_path.with_suffix('.lock')
        self.locker = FileLock(str(lock_path.resolve()))