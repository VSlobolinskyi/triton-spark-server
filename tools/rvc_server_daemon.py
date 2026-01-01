#!/usr/bin/env python3
"""
RVC Server Daemon - Long-running process that keeps RVC workers alive.

This script starts the RVC server and keeps running until killed.
Run in background with: nohup python tools/rvc_server_daemon.py ... &

Usage:
    python tools/rvc_server_daemon.py --model SilverWolf_e300_s6600.pth --workers 2
"""

import os
import sys
import argparse
import logging
import time
import signal
import json
import socket
import threading
import struct

# Setup path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# PID file for tracking the daemon
PID_FILE = "TEMP/rvc_server.pid"
STATUS_FILE = "TEMP/rvc_server_status.json"
SOCKET_PORT = 50051  # Port for job submission

_shutdown_requested = False
_server = None  # Global server reference for socket handler


def signal_handler(signum, frame):
    """Handle shutdown signals."""
    global _shutdown_requested
    logger.info(f"Received signal {signum}, shutting down...")
    _shutdown_requested = True


def write_status(status: dict):
    """Write server status to file for other processes to read."""
    os.makedirs(os.path.dirname(STATUS_FILE), exist_ok=True)
    with open(STATUS_FILE, "w") as f:
        json.dump(status, f)


def cleanup():
    """Remove PID and status files."""
    if os.path.exists(PID_FILE):
        os.remove(PID_FILE)
    if os.path.exists(STATUS_FILE):
        os.remove(STATUS_FILE)


def send_message(sock, data: dict):
    """Send a JSON message with length prefix."""
    msg = json.dumps(data).encode('utf-8')
    sock.sendall(struct.pack('>I', len(msg)) + msg)


def recv_message(sock) -> dict:
    """Receive a JSON message with length prefix."""
    raw_len = sock.recv(4)
    if not raw_len:
        return None
    msg_len = struct.unpack('>I', raw_len)[0]
    data = b''
    while len(data) < msg_len:
        chunk = sock.recv(min(msg_len - len(data), 4096))
        if not chunk:
            return None
        data += chunk
    return json.loads(data.decode('utf-8'))


def handle_client(conn, addr):
    """Handle a client connection."""
    global _server
    logger.debug(f"Client connected: {addr}")

    try:
        while True:
            request = recv_message(conn)
            if request is None:
                break

            cmd = request.get("cmd")
            response = {"success": False, "error": "Unknown command"}

            if cmd == "submit":
                # Submit a job
                try:
                    job_id = _server.submit_job(
                        input_audio_path=request["input_path"],
                        output_audio_path=request["output_path"],
                        pitch_shift=request.get("pitch_shift", 0),
                        f0_method=request.get("f0_method", "rmvpe"),
                        index_rate=request.get("index_rate", 0.75),
                        filter_radius=request.get("filter_radius", 3),
                        resample_sr=request.get("resample_sr", 0),
                        rms_mix_rate=request.get("rms_mix_rate", 0.25),
                        protect=request.get("protect", 0.33),
                    )
                    response = {"success": True, "job_id": job_id}
                except Exception as e:
                    response = {"success": False, "error": str(e)}

            elif cmd == "get_result":
                # Get a result (blocking)
                timeout = request.get("timeout", 30.0)
                result = _server.get_result(timeout=timeout)
                if result:
                    response = {
                        "success": True,
                        "result": result.to_dict(),
                    }
                else:
                    response = {"success": False, "error": "Timeout"}

            elif cmd == "status":
                # Get server status
                response = {"success": True, "status": _server.get_status()}

            send_message(conn, response)

    except Exception as e:
        logger.error(f"Client error: {e}")
    finally:
        conn.close()
        logger.debug(f"Client disconnected: {addr}")


def socket_server_thread(port: int):
    """Run the socket server in a thread."""
    global _shutdown_requested

    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.bind(('127.0.0.1', port))
    server_socket.listen(5)
    server_socket.settimeout(1.0)  # Allow checking shutdown flag

    logger.info(f"Socket server listening on port {port}")

    while not _shutdown_requested:
        try:
            conn, addr = server_socket.accept()
            # Handle each client in a thread
            client_thread = threading.Thread(target=handle_client, args=(conn, addr))
            client_thread.daemon = True
            client_thread.start()
        except socket.timeout:
            continue
        except Exception as e:
            if not _shutdown_requested:
                logger.error(f"Socket server error: {e}")

    server_socket.close()
    logger.info("Socket server stopped")


def main():
    parser = argparse.ArgumentParser(description="RVC Server Daemon")
    parser.add_argument("--model", required=True, help="RVC model name")
    parser.add_argument("--workers", type=int, default=2, help="Number of workers")
    parser.add_argument("--timeout", type=float, default=120, help="Startup timeout")
    args = parser.parse_args()

    # Register signal handlers
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    # Write PID file
    os.makedirs(os.path.dirname(PID_FILE), exist_ok=True)
    with open(PID_FILE, "w") as f:
        f.write(str(os.getpid()))

    logger.info("=" * 60)
    logger.info("RVC Server Daemon Starting")
    logger.info("=" * 60)
    logger.info(f"PID: {os.getpid()}")
    logger.info(f"Model: {args.model}")
    logger.info(f"Workers: {args.workers}")

    # Import and start server
    global _server
    from rvc.server import RVCServer

    server = RVCServer(model_name=args.model, num_workers=args.workers)
    _server = server  # Set global for socket handler

    try:
        if not server.start(timeout=args.timeout):
            logger.error("Failed to start server")
            cleanup()
            return 1

        logger.info("Server started successfully!")
        logger.info("Server will run until killed (SIGTERM/SIGINT)")

        # Start socket server for IPC
        socket_thread = threading.Thread(target=socket_server_thread, args=(SOCKET_PORT,))
        socket_thread.daemon = True
        socket_thread.start()

        # Write initial status
        write_status({
            "running": True,
            "pid": os.getpid(),
            "port": SOCKET_PORT,
            "model": args.model,
            "num_workers": args.workers,
            "workers_alive": args.workers,
            "start_time": time.time(),
        })

        # Main loop - just keep alive and update status periodically
        while not _shutdown_requested:
            time.sleep(1.0)

            # Update status file
            status = server.get_status()
            status["pid"] = os.getpid()
            status["port"] = SOCKET_PORT
            write_status(status)

            # Check if workers are still alive
            if status["workers_alive"] == 0:
                logger.error("All workers died, shutting down")
                break

    except Exception as e:
        logger.error(f"Server error: {e}")
        return 1

    finally:
        logger.info("Shutting down server...")
        server.shutdown()
        cleanup()
        logger.info("Server shutdown complete")

    return 0


if __name__ == "__main__":
    sys.exit(main())
