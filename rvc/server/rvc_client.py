"""
RVC Server Client - Connects to the RVC daemon via socket.

This client communicates with the rvc_server_daemon.py process.
"""

import os
import json
import socket
import struct
from typing import Optional
from dataclasses import dataclass

# Status file location (must match daemon)
STATUS_FILE = "TEMP/rvc_server_status.json"


@dataclass
class RVCResult:
    """Result of an RVC inference job."""
    job_id: int
    success: bool
    output_path: Optional[str] = None
    error: Optional[str] = None
    worker_id: int = -1
    processing_time: float = 0.0


class RVCClient:
    """
    Client for communicating with the RVC server daemon.

    Usage:
        client = RVCClient.connect()
        if client:
            job_id = client.submit_job("input.wav", "output.wav")
            result = client.get_result()
            client.close()
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 50051):
        self.host = host
        self.port = port
        self.socket = None

    def connect(self) -> bool:
        """Connect to the server."""
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.connect((self.host, self.port))
            return True
        except (ConnectionRefusedError, OSError):
            self.socket = None
            return False

    def close(self):
        """Close the connection."""
        if self.socket:
            self.socket.close()
            self.socket = None

    def _send(self, data: dict):
        """Send a message."""
        msg = json.dumps(data).encode('utf-8')
        self.socket.sendall(struct.pack('>I', len(msg)) + msg)

    def _recv(self) -> dict:
        """Receive a message."""
        raw_len = self.socket.recv(4)
        if not raw_len:
            return None
        msg_len = struct.unpack('>I', raw_len)[0]
        data = b''
        while len(data) < msg_len:
            chunk = self.socket.recv(min(msg_len - len(data), 4096))
            if not chunk:
                return None
            data += chunk
        return json.loads(data.decode('utf-8'))

    def submit_job(
        self,
        input_audio_path: str,
        output_audio_path: str,
        pitch_shift: int = 0,
        f0_method: str = "rmvpe",
        index_rate: float = 0.75,
        filter_radius: int = 3,
        resample_sr: int = 0,
        rms_mix_rate: float = 0.25,
        protect: float = 0.33,
    ) -> int:
        """Submit a job and return job_id."""
        self._send({
            "cmd": "submit",
            "input_path": input_audio_path,
            "output_path": output_audio_path,
            "pitch_shift": pitch_shift,
            "f0_method": f0_method,
            "index_rate": index_rate,
            "filter_radius": filter_radius,
            "resample_sr": resample_sr,
            "rms_mix_rate": rms_mix_rate,
            "protect": protect,
        })
        response = self._recv()
        if response and response.get("success"):
            return response["job_id"]
        raise RuntimeError(response.get("error", "Unknown error"))

    def get_result(self, timeout: float = 30.0) -> Optional[RVCResult]:
        """Get the next result."""
        self._send({
            "cmd": "get_result",
            "timeout": timeout,
        })
        response = self._recv()
        if response and response.get("success"):
            r = response["result"]
            return RVCResult(
                job_id=r["job_id"],
                success=r["success"],
                output_path=r.get("output_path"),
                error=r.get("error"),
                worker_id=r.get("worker_id", -1),
                processing_time=r.get("processing_time", 0.0),
            )
        return None

    def get_status(self) -> dict:
        """Get server status."""
        self._send({"cmd": "status"})
        response = self._recv()
        if response and response.get("success"):
            return response["status"]
        return {}

    @classmethod
    def from_status_file(cls) -> Optional["RVCClient"]:
        """
        Create a client from the status file.

        Returns None if daemon is not running.
        """
        if not os.path.exists(STATUS_FILE):
            return None

        try:
            with open(STATUS_FILE, "r") as f:
                status = json.load(f)

            if not status.get("running", False):
                return None

            port = status.get("port", 50051)
            client = cls(port=port)
            if client.connect():
                return client
            return None

        except (json.JSONDecodeError, IOError, KeyError):
            return None


def get_rvc_client() -> Optional[RVCClient]:
    """Get a connected RVC client, or None if daemon not running."""
    return RVCClient.from_status_file()


def is_daemon_running() -> bool:
    """Check if the RVC daemon is running."""
    client = get_rvc_client()
    if client:
        client.close()
        return True
    return False
