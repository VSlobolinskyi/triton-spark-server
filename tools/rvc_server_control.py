#!/usr/bin/env python3
"""
RVC Server Control Tool

Commands:
    start       - Start the RVC server with specified workers
    stop        - Stop the RVC server
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

# Setup path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def cmd_start(args):
    """Start the RVC server."""
    from rvc.server import start_rvc_server, get_rvc_server_status

    print(f"Starting RVC server...")
    print(f"  Model: {args.model}")
    print(f"  Workers: {args.workers}")
    print(f"  Timeout: {args.timeout}s")

    try:
        server = start_rvc_server(
            model_name=args.model,
            num_workers=args.workers,
            timeout=args.timeout,
        )

        status = server.get_status()
        print(f"\nServer started successfully!")
        print(f"  Workers alive: {status['workers_alive']}/{status['num_workers']}")
        return 0

    except Exception as e:
        print(f"Failed to start server: {e}")
        return 1


def cmd_stop(args):
    """Stop the RVC server."""
    from rvc.server import shutdown_rvc_server, get_rvc_server

    server = get_rvc_server()
    if server is None or not server.is_running:
        print("Server is not running")
        return 0

    print("Stopping RVC server...")
    shutdown_rvc_server()
    print("Server stopped")
    return 0


def cmd_status(args):
    """Show server status."""
    from rvc.server import get_rvc_server_status

    status = get_rvc_server_status()

    print("RVC Server Status:")
    if not status.get("running", False):
        print("  Status: NOT RUNNING")
        if "error" in status:
            print(f"  Note: {status['error']}")
    else:
        print(f"  Status: RUNNING")
        print(f"  Model: {status.get('model', 'unknown')}")
        print(f"  Workers: {status.get('workers_alive', 0)}/{status.get('num_workers', 0)}")
        print(f"  Jobs submitted: {status.get('jobs_submitted', 0)}")
        print(f"  Pending results: {status.get('pending_results', 0)}")

    return 0


def cmd_test(args):
    """Run a test inference."""
    from rvc.server import get_rvc_server, start_rvc_server

    if not os.path.exists(args.input):
        print(f"Input file not found: {args.input}")
        return 1

    # Get or start server
    server = get_rvc_server()
    if server is None or not server.is_running:
        if not args.model:
            print("Server not running. Specify --model to start it.")
            return 1

        print(f"Starting server with model: {args.model}")
        server = start_rvc_server(
            model_name=args.model,
            num_workers=args.workers,
        )

    # Submit test job
    output_path = args.output or "TEMP/rvc/test_output.wav"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    print(f"Submitting test job...")
    print(f"  Input: {args.input}")
    print(f"  Output: {output_path}")
    print(f"  Pitch shift: {args.pitch_shift}")

    start_time = time.time()
    job_id = server.submit_job(
        input_audio_path=args.input,
        output_audio_path=output_path,
        pitch_shift=args.pitch_shift,
        f0_method=args.f0_method,
    )

    # Wait for result
    result = server.get_result(timeout=60)

    if result is None:
        print("Timeout waiting for result")
        return 1

    total_time = time.time() - start_time

    if result.success:
        print(f"\nTest completed successfully!")
        print(f"  Output: {result.output_path}")
        print(f"  Worker: {result.worker_id}")
        print(f"  Processing time: {result.processing_time:.2f}s")
        print(f"  Total time: {total_time:.2f}s")
        return 0
    else:
        print(f"\nTest failed: {result.error}")
        return 1


def main():
    parser = argparse.ArgumentParser(
        description="RVC Server Control",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # Start command
    start_parser = subparsers.add_parser("start", help="Start the RVC server")
    start_parser.add_argument("--model", required=True, help="RVC model name")
    start_parser.add_argument("--workers", type=int, default=2, help="Number of workers")
    start_parser.add_argument("--timeout", type=float, default=120, help="Startup timeout")

    # Stop command
    subparsers.add_parser("stop", help="Stop the RVC server")

    # Status command
    subparsers.add_parser("status", help="Show server status")

    # Test command
    test_parser = subparsers.add_parser("test", help="Run a test inference")
    test_parser.add_argument("--input", required=True, help="Input audio path")
    test_parser.add_argument("--output", help="Output audio path")
    test_parser.add_argument("--model", help="RVC model (if server not running)")
    test_parser.add_argument("--workers", type=int, default=2, help="Number of workers")
    test_parser.add_argument("--pitch-shift", type=int, default=0, help="Pitch shift")
    test_parser.add_argument("--f0-method", default="rmvpe", help="F0 method")

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
