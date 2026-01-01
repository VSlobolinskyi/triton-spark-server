#!/usr/bin/env python3
"""
RVC Server Control Tool

Commands:
    start       - Start the RVC server daemon in background
    stop        - Stop the RVC server daemon
    status      - Show server status
    test        - Run a quick test inference

Usage:
    python tools/rvc_server_control.py start --model SilverWolf_e300_s6600.pth --workers 2
    python tools/rvc_server_control.py status
    python tools/rvc_server_control.py test --input TEMP/spark/fragment_0.wav
    python tools/rvc_server_control.py stop
"""

import os
import sys
import argparse
import logging
import time
import subprocess
import signal
import json

# Setup path
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, PROJECT_DIR)
os.chdir(PROJECT_DIR)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# Files for daemon communication
PID_FILE = "TEMP/rvc_server.pid"
STATUS_FILE = "TEMP/rvc_server_status.json"
LOG_FILE = "TEMP/rvc_server.log"


def get_daemon_pid():
    """Get PID of running daemon, or None if not running."""
    if not os.path.exists(PID_FILE):
        return None
    try:
        with open(PID_FILE, "r") as f:
            pid = int(f.read().strip())
        # Check if process is actually running
        os.kill(pid, 0)  # Doesn't kill, just checks
        return pid
    except (ValueError, OSError, ProcessLookupError):
        # Process not running, clean up stale PID file
        if os.path.exists(PID_FILE):
            os.remove(PID_FILE)
        return None


def get_daemon_status():
    """Get status from daemon status file."""
    if not os.path.exists(STATUS_FILE):
        return None
    try:
        with open(STATUS_FILE, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return None


def cmd_start(args):
    """Start the RVC server daemon in background."""
    # Check if already running
    pid = get_daemon_pid()
    if pid is not None:
        status = get_daemon_status()
        print(f"RVC server already running (PID: {pid})")
        if status:
            print(f"  Model: {status.get('model', 'unknown')}")
            print(f"  Workers: {status.get('workers_alive', 0)}/{status.get('num_workers', 0)}")
        return 0

    print(f"Starting RVC server daemon...")
    print(f"  Model: {args.model}")
    print(f"  Workers: {args.workers}")
    print(f"  Timeout: {args.timeout}s")

    # Create TEMP directory
    os.makedirs("TEMP", exist_ok=True)

    # Start daemon in background
    daemon_script = os.path.join(SCRIPT_DIR, "rvc_server_daemon.py")
    cmd = [
        sys.executable, daemon_script,
        "--model", args.model,
        "--workers", str(args.workers),
        "--timeout", str(args.timeout),
    ]

    # Open log file
    log_file = open(LOG_FILE, "w")

    # Start subprocess (detached)
    process = subprocess.Popen(
        cmd,
        stdout=log_file,
        stderr=subprocess.STDOUT,
        start_new_session=True,  # Detach from parent
    )

    print(f"  Daemon PID: {process.pid}")
    print(f"  Log file: {LOG_FILE}")
    print(f"\nWaiting for workers to initialize...")

    # Wait for server to be ready (check status file)
    start_time = time.time()
    timeout = args.timeout + 10  # Extra buffer

    while time.time() - start_time < timeout:
        time.sleep(1.0)

        # Check if process died
        if process.poll() is not None:
            print(f"\nDaemon exited unexpectedly. Check {LOG_FILE} for errors.")
            # Print last lines of log
            log_file.close()
            with open(LOG_FILE, "r") as f:
                lines = f.readlines()
                print("\nLast log lines:")
                for line in lines[-20:]:
                    print(f"  {line.rstrip()}")
            return 1

        # Check status file
        status = get_daemon_status()
        if status and status.get("running", False):
            workers_alive = status.get("workers_alive", 0)
            num_workers = status.get("num_workers", 0)
            if workers_alive > 0:
                print(f"\nServer started successfully!")
                print(f"  PID: {status.get('pid')}")
                print(f"  Workers: {workers_alive}/{num_workers}")
                log_file.close()
                return 0

        # Show progress
        elapsed = int(time.time() - start_time)
        print(f"  Loading... ({elapsed}s)", end="\r")

    print(f"\nTimeout waiting for server to start. Check {LOG_FILE} for errors.")
    log_file.close()
    return 1


def cmd_stop(args):
    """Stop the RVC server daemon."""
    pid = get_daemon_pid()

    if pid is None:
        print("RVC server is not running")
        return 0

    print(f"Stopping RVC server (PID: {pid})...")

    try:
        os.kill(pid, signal.SIGTERM)

        # Wait for process to exit
        for _ in range(10):
            time.sleep(0.5)
            try:
                os.kill(pid, 0)
            except OSError:
                print("Server stopped")
                return 0

        # Force kill if still running
        print("Server not responding, force killing...")
        os.kill(pid, signal.SIGKILL)
        time.sleep(1)
        print("Server killed")

    except ProcessLookupError:
        print("Server already stopped")

    # Clean up files
    for f in [PID_FILE, STATUS_FILE]:
        if os.path.exists(f):
            os.remove(f)

    return 0


def cmd_status(args):
    """Show server status."""
    pid = get_daemon_pid()
    status = get_daemon_status()

    print("RVC Server Status:")

    if pid is None:
        print("  Status: NOT RUNNING")
        return 0

    print(f"  Status: RUNNING")
    print(f"  PID: {pid}")

    if status:
        print(f"  Model: {status.get('model', 'unknown')}")
        print(f"  Workers: {status.get('workers_alive', 0)}/{status.get('num_workers', 0)}")
        print(f"  Jobs submitted: {status.get('jobs_submitted', 0)}")
    else:
        print("  (status file not found)")

    return 0


def cmd_test(args):
    """Run a test inference using the running server."""
    # This still uses the in-process API for testing
    # The daemon handles the actual server
    pid = get_daemon_pid()

    if pid is None:
        print("RVC server is not running. Start it first with:")
        print("  python tools/rvc_server_control.py start --model <model>")
        return 1

    if not os.path.exists(args.input):
        print(f"Input file not found: {args.input}")
        return 1

    # For test, we need to connect to the daemon's server
    # Since we can't directly access the daemon's server instance,
    # we'll do a simple file-based job submission
    print("Test command requires the pipeline. Use:")
    print(f"  python tools/test_rvc_server.py --prompt-audio {args.input}")
    return 0


def main():
    parser = argparse.ArgumentParser(
        description="RVC Server Control",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # Start command
    start_parser = subparsers.add_parser("start", help="Start the RVC server daemon")
    start_parser.add_argument("--model", required=True, help="RVC model name")
    start_parser.add_argument("--workers", type=int, default=2, help="Number of workers")
    start_parser.add_argument("--timeout", type=float, default=120, help="Startup timeout")

    # Stop command
    subparsers.add_parser("stop", help="Stop the RVC server daemon")

    # Status command
    subparsers.add_parser("status", help="Show server status")

    # Test command (simplified)
    test_parser = subparsers.add_parser("test", help="Show how to test")
    test_parser.add_argument("--input", required=True, help="Input audio path")

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        return 0

    if args.command == "start":
        return cmd_start(args)
    elif args.command == "stop":
        return cmd_stop(args)
    elif args.command == "status":
        return cmd_status(args)
    elif args.command == "test":
        return cmd_test(args)
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
