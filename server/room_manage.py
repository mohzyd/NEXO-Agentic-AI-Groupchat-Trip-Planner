
from threading import RLock
from urllib.parse import urlparse

from utils.tunnel import Tunnel


class RoomManager:

    def __init__(self, port):

        self.port = port

        self.rooms = {}
        self.room_hosts = {}

        self.lock = RLock()

    def create_room(self):

        tunnel = None

        try:

            tunnel = Tunnel(
                port=self.port,
                timeout=30
            )

            print("[RoomManager] Creating tunnel...")

            response = tunnel.create_tunnel()

            if not response.success:

                print(
                    f"[RoomManager] Tunnel failed: "
                    f"{response.reason}"
                )

                tunnel.close()

                return None

            public_url = response.url

            hostname = urlparse(public_url).hostname

            if not hostname:
                tunnel.close()
                return None

            hostname = hostname.lower()

            room_id = __import__("uuid").uuid4().hex

            room = {
                "room_id": room_id,
                "url": public_url,
                "hostname": hostname,
                "tunnel": tunnel
            }

            with self.lock:

                if hostname in self.room_hosts:

                    tunnel.close()

                    return None

                self.rooms[room_id] = room

                self.room_hosts[hostname] = room_id

            print("=" * 50)
            print(f"[RoomManager] Room created: {room_id}")
            print(f"[RoomManager] URL: {public_url}")
            print("=" * 50)

            return {
                "room_id": room_id,
                "url": public_url
            }

        except Exception as error:

            if tunnel is not None:
                tunnel.close()

            print(
                f"[RoomManager] Creation error: {error}"
            )

            return None

    def get_room(self, room_id):

        with self.lock:

            room = self.rooms.get(room_id)

            if room is None:
                return None

            return {
                "room_id": room["room_id"],
                "url": room["url"]
            }

    def get_room_by_host(self, hostname):

        if not isinstance(hostname, str):
            return None

        hostname = hostname.split(":")[0].lower()

        with self.lock:

            return self.room_hosts.get(hostname)

    def list_rooms(self):

        with self.lock:

            return [
                {
                    "room_id": room["room_id"],
                    "url": room["url"]
                }
                for room in self.rooms.values()
            ]

    def get_tunnel(self, room_id):

        with self.lock:

            room = self.rooms.get(room_id)

            if room is None:
                return None

            return room["tunnel"]

    def delete_room(self, room_id):

        with self.lock:

            room = self.rooms.pop(room_id, None)

            if room is None:
                return None

            self.room_hosts.pop(
                room["hostname"],
                None
            )

        tunnel = room["tunnel"]

        try:

            if tunnel.is_running():
                tunnel.close()

        except Exception as error:

            print(
                f"[RoomManager] Tunnel cleanup failed: {error}"
            )

        print(
            f"[RoomManager] Room deleted: {room_id}"
        )

        return room_id

    def close_all_rooms(self):

        with self.lock:

            room_ids = list(self.rooms.keys())

        for room_id in room_ids:

            self.delete_room(room_id)

        print("[RoomManager] All rooms closed.")