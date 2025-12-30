#!/usr/bin/env python3
"""
Worker Control Tool for RVC Pipeline

Commands:
    status      - Show status of all workers
    shutdown    - Shutdown all workers
    shutdown-rvc - Shutdown only RVC workers
    shutdown-tts - Shutdown only TTS workers

Usage:
    python tools/worker_control.py status
    python tools/worker_control.py shutdown-rvc
    python tools/worker_control.py shutdown-tts
    python tools/worker_control.py shutdown
"""

import os
import sys
import argparse

# Setup path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main():
    parser = argparse.ArgumentParser(
        description="Control RVC/TTS workers",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "command",
        choices=["status", "shutdown", "shutdown-rvc", "shutdown-tts"],
        help="Command to execute",
    )

    args = parser.parse_args()

    from rvc.processing.worker_manager import (
        get_worker_status,
        shutdown_rvc_workers,
        shutdown_tts_workers,
        shutdown_all_workers,
    )

    if args.command == "status":
        status = get_worker_status()
        if "error" in status:
            print(f"Status: {status['error']}")
            return 0

        print("Worker Status:")
        print(f"  Unload delay: {status['unload_delay']}s (0 = persist forever)")
        print(f"\n  TTS Workers: {len(status['tts_workers'])}")
        for wid, info in status["tts_workers"].items():
            active = "active" if info["active"] else "idle"
            print(f"    Worker {wid}: {active}")

        print(f"\n  RVC Workers: {len(status['rvc_workers'])}")
        for wid, info in status["rvc_workers"].items():
            active = "active" if info["active"] else "idle"
            print(f"    Worker {wid}: {active}")

    elif args.command == "shutdown-rvc":
        print("Shutting down RVC workers...")
        result = shutdown_rvc_workers()
        print(result)

    elif args.command == "shutdown-tts":
        print("Shutting down TTS workers...")
        result = shutdown_tts_workers()
        print(result)

    elif args.command == "shutdown":
        print("Shutting down all workers...")
        result = shutdown_all_workers()
        print(result)

    return 0


if __name__ == "__main__":
    sys.exit(main())
