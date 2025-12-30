"""RVC Server module for persistent multi-process inference."""

from .rvc_server import (
    RVCServer,
    RVCJob,
    RVCResult,
    get_rvc_server,
    start_rvc_server,
    shutdown_rvc_server,
    get_rvc_server_status,
)

from .rvc_client import (
    RVCClient,
    get_rvc_client,
    is_daemon_running,
)

__all__ = [
    # Server (in-process)
    "RVCServer",
    "RVCJob",
    "RVCResult",
    "get_rvc_server",
    "start_rvc_server",
    "shutdown_rvc_server",
    "get_rvc_server_status",
    # Client (connects to daemon)
    "RVCClient",
    "get_rvc_client",
    "is_daemon_running",
]
