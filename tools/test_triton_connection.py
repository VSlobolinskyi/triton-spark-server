#!/usr/bin/env python3
"""Test Triton server connection."""
import sys
import os
import argparse

# Setup path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rvc.triton_client import TritonSparkClient

def main():
    parser = argparse.ArgumentParser(description="Test Triton connection")
    parser.add_argument("--addr", default="localhost", help="Triton server address")
    parser.add_argument("--port", type=int, default=8001, help="Triton server port")
    args = parser.parse_args()

    client = TritonSparkClient(server_addr=args.addr, server_port=args.port)

    if client.is_server_ready():
        print("Triton server is ready!")
    else:
        print("Triton server not ready - check server_log.txt")

    if client.is_model_ready():
        print("Spark TTS model is loaded!")
    else:
        print("Spark TTS model not loaded - check server_log.txt")

    client.close()

if __name__ == "__main__":
    main()
