"""Manage room workers, Cloudflare tunnels, room metadata, and expiry."""

import json
import os
import socket
import subprocess
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from secrets import token_urlsafe
from threading import RLock
from urllib.parse import urlparse
from uuid import uuid4

from utils.file import get_runnable_path
from utils.tunnel import Processes, Tunnel


class RoomManager:
    """Own the lifecycle and public metadata for all chat rooms."""

    def __init__(self):
        """Initialize empty room and hostname registries."""

        if Processes.all_processes is None:
            Processes.all_processes = []

        self.rooms = {}
        self.room_hosts = {}
        self.lock = RLock()

    @staticmethod
    def _find_available_port():
        """Return an available TCP port bound to the loopback interface."""

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
            listener.bind(("127.0.0.1", 0))
            return listener.getsockname()[1]

    @staticmethod
    def _stop_worker(worker):
        """Stop a room worker process, escalating to kill after a timeout."""

        if worker is None or worker.poll() is not None:
            return

        worker.terminate()

        try:
            worker.wait(timeout=5)
        except subprocess.TimeoutExpired:
            worker.kill()
            worker.wait()

    @staticmethod
    def _close_tunnel(tunnel):
        """Close a tunnel when it has successfully started a process."""

        if tunnel is None or getattr(tunnel, "process", None) is None:
            return

        try:
            tunnel.close()
        except Exception as error:
            print(f"[RoomManager] Tunnel cleanup failed: {error}")

    @staticmethod
    def _wait_for_worker(worker, port, timeout=15):
        """Poll a worker health endpoint until it is ready or fails."""

        deadline = time.monotonic() + timeout
        health_url = f"http://127.0.0.1:{port}/_health"

        while time.monotonic() < deadline:

            if worker.poll() is not None:
                raise RuntimeError("Room Flask worker exited before becoming ready.")

            try:
                with urllib.request.urlopen(health_url, timeout=0.5) as response:
                    if response.status == 200:
                        return
            except (OSError, urllib.error.URLError):
                time.sleep(0.1)

        raise TimeoutError("Room Flask worker did not become ready in time.")

    def create_room(self, groupchat: dict):
        """Start a room worker and tunnel, then register their room metadata."""

        if not isinstance(groupchat, dict):
            return None

        is_protected = groupchat.get("isProtected", False)
        encrypted_password = groupchat.get("encryptedPassword")
        lifetime = groupchat.get("lifetime")
        name = groupchat.get("name", "Anonymous Chat")

        if not isinstance(is_protected, bool):
            return None

        if is_protected and not isinstance(encrypted_password, str):
            return None

        if not isinstance(name, str) or not name.strip():
            return None

        created_at = datetime.now(timezone.utc)
        expires_at = (
            created_at + timedelta(minutes=lifetime)
            if lifetime is not None
            else None
        )
        room_id = uuid4().hex
        port = self._find_available_port()
        control_token = token_urlsafe(32)

        metadata = {
            "name": name.strip(),
            "isProtected": is_protected,
            "isInactive": False,
            "encryptedPassword": encrypted_password,
            "createdAt": created_at.isoformat(),
            "expiresAt": expires_at.isoformat() if expires_at else None,
            "lifetime": lifetime
        }

        worker_env = os.environ.copy()
        worker_env["ROOM_GROUPCHAT"] = json.dumps(metadata)
        worker_env["ROOM_CONTROL_TOKEN"] = control_token

        command = [
            *get_runnable_path(),
            "--type", "room",
            "--room-id", room_id,
            "--port", str(port)
        ]

        worker = None
        tunnel = None

        try:
            worker = subprocess.Popen(
                command,
                stdout=None,
                stderr=None,
                env=worker_env
            )

            self._wait_for_worker(worker, port)

            tunnel = Tunnel(port=port, timeout=30)
            response = tunnel.create_tunnel()

            if not response.success or not response.url:
                raise RuntimeError(response.reason or "Cloudflare tunnel creation failed.")

            hostname = urlparse(response.url).hostname

            if not hostname:
                raise RuntimeError("Cloudflare returned a URL without a hostname.")

            hostname = hostname.lower()
            room = {
                "room_id": room_id,
                "url": response.url,
                "hostname": hostname,
                "port": port,
                "worker": worker,
                "tunnel": tunnel,
                "groupchat": metadata,
                "control_token": control_token,
                "created_at": created_at,
                "expires_at": expires_at,
                "isInactive": False
            }

            with self.lock:
                if hostname in self.room_hosts:
                    raise RuntimeError("Cloudflare returned a duplicate room hostname.")

                self.rooms[room_id] = room
                self.room_hosts[hostname] = room_id

            print(f"[RoomManager] Created room {room_id}: {response.url}")
            return self.get_room(room_id)

        except Exception as error:
            print(f"[RoomManager] Room creation failed: {error}")
            self._close_tunnel(tunnel)
            self._stop_worker(worker)
            return None

    def _read_worker_details(self, room):
        """Read private live details from a worker using its control token."""

        req = urllib.request.Request(
            f"http://127.0.0.1:{room['port']}/_internal/details",
            headers={
                "X-Room-Control-Token": room["control_token"]
            }
        )

        try:
            with urllib.request.urlopen(req, timeout=2) as response:
                return json.loads(response.read().decode("utf-8"))
        except Exception:
            return {"memberCount": 0}

    def _public_room(self, room):
        """Build room metadata safe to return from the management API."""

        details = self._read_worker_details(room)
        groupchat = room["groupchat"]
        expires_at = room["expires_at"]
        seconds_left = (
            max(0, int((expires_at - datetime.now(timezone.utc)).total_seconds()))
            if expires_at is not None
            else None
        )
        is_expired = seconds_left == 0
        name = groupchat["name"]
        short_name = "".join(part[0] for part in name.split()[:3]).upper()

        return {
            "id": room["room_id"],
            "room_id": room["room_id"],
            "name": name,
            "short_name": short_name or name[:2].upper(),
            "url": room["url"],
            "status": (
                "Inactive" if room["isInactive"] else
                "Expired" if is_expired else
                "Active"
            ),
            "isInactive": room["isInactive"],
            "isExpired": is_expired,
            "isProtected": groupchat["isProtected"],
            "lifetime": expires_at is None,
            "created_at": room["created_at"].isoformat(),
            "expire_time": expires_at.isoformat() if expires_at else None,
            "seconds_remaining": seconds_left,
            "member_count": 0 if room["isInactive"] else details.get("memberCount", 0)
        }

    def get_room(self, room_id):
        """Return one room without closing its tunnel when its lifetime elapses."""

        with self.lock:
            room = self.rooms.get(room_id)

        if room is None:
            return None

        return self._public_room(room)

    def list_rooms(self):
        """Return public metadata for active and inactive rooms."""

        with self.lock:
            room_ids = list(self.rooms)

        return [
            room
            for room_id in room_ids
            if (room := self.get_room(room_id)) is not None
        ]

    def get_room_by_host(self, hostname):
        """Resolve an active public hostname to its room identifier."""

        if not isinstance(hostname, str):
            return None

        hostname = hostname.split(":")[0].lower()

        with self.lock:
            return self.room_hosts.get(hostname)

    def get_tunnel(self, room_id):
        """Return the managed tunnel object for a room, if present."""

        with self.lock:
            room = self.rooms.get(room_id)
            return room["tunnel"] if room else None

    def delete_room(self, room_id):
        """Soft-delete a room by stopping it and preserving its metadata."""

        with self.lock:
            room = self.rooms.get(room_id)

            if room is None:
                return None

            if room["isInactive"]:
                return room_id

            room["isInactive"] = True
            room["groupchat"]["isInactive"] = True
            self.room_hosts.pop(room["hostname"], None)

        self._close_tunnel(room["tunnel"])
        self._stop_worker(room["worker"])
        print(f"[RoomManager] Marked room inactive: {room_id}")
        return room_id

    def close_all_rooms(self):
        """Deactivate every room during manager shutdown."""

        with self.lock:
            room_ids = list(self.rooms)

        for room_id in room_ids:
            self.delete_room(room_id)
