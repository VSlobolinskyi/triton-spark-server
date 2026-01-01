#!/usr/bin/env python3
"""Test Triton server connection.

Usage:
    python -m tests.test_connection --host localhost --port 8001
"""

import argparse
import sys


def test_triton_connection(host: str, port: int) -> bool:
    """Test connection to Triton server."""
    try:
        from rvc.triton_client import TritonSparkClient

        print(f"Connecting to Triton at {host}:{port}...")
        client = TritonSparkClient(server_addr=host, server_port=port)

        if client.is_server_ready():
            print("  [OK] Triton server is ready")
        else:
            print("  [FAIL] Triton server not ready")
            return False

        if client.is_model_ready():
            print("  [OK] Model is loaded")
        else:
            print("  [FAIL] Model not loaded")
            return False

        client.close()
        return True

    except Exception as e:
        print(f"  [ERROR] Connection failed: {e}")
        return False


def test_http_api_connection(host: str, port: int) -> bool:
    """Test connection to HTTP API."""
    try:
        import requests

        url = f"http://{host}:{port}/health"
        print(f"Connecting to HTTP API at {host}:{port}...")

        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            health = response.json()
            print(f"  [OK] API status: {health.get('status', 'unknown')}")
            print(f"  [OK] Triton ready: {health.get('triton_ready', 'N/A')}")
            print(f"  [OK] RVC ready: {health.get('rvc_ready', 'N/A')}")
            return True
        else:
            print(f"  [FAIL] HTTP {response.status_code}")
            return False

    except Exception as e:
        print(f"  [ERROR] Connection failed: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Test server connections")
    parser.add_argument("--host", default="localhost", help="Server host")
    parser.add_argument("--triton-port", type=int, default=8001, help="Triton gRPC port")
    parser.add_argument("--api-port", type=int, default=8080, help="HTTP API port")
    parser.add_argument("--triton-only", action="store_true", help="Only test Triton")
    parser.add_argument("--api-only", action="store_true", help="Only test HTTP API")
    args = parser.parse_args()

    print("=" * 50)
    print("Connection Tests")
    print("=" * 50)

    results = []

    if not args.api_only:
        print("\n[1] Triton Server")
        results.append(("Triton", test_triton_connection(args.host, args.triton_port)))

    if not args.triton_only:
        print("\n[2] HTTP API")
        results.append(("HTTP API", test_http_api_connection(args.host, args.api_port)))

    print("\n" + "=" * 50)
    print("Results")
    print("=" * 50)

    all_passed = True
    for name, passed in results:
        status = "PASS" if passed else "FAIL"
        print(f"  {name}: {status}")
        if not passed:
            all_passed = False

    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
