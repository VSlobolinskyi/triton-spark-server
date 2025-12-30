#!/usr/bin/env python3
"""
Generate Python gRPC code from proto files.

Run from the rvc/grpc directory:
    python generate_proto.py

Or from project root:
    python -m rvc.grpc.generate_proto
"""

import os
import subprocess
import sys


def generate_proto(grpc_dir: str, proto_name: str) -> bool:
    """Generate Python code from a single proto file."""
    proto_file = os.path.join(grpc_dir, proto_name)

    if not os.path.exists(proto_file):
        print(f"Warning: Proto file not found: {proto_file}")
        return False

    print(f"Generating gRPC code from: {proto_file}")

    cmd = [
        sys.executable, "-m", "grpc_tools.protoc",
        f"-I{grpc_dir}",
        f"--python_out={grpc_dir}",
        f"--grpc_python_out={grpc_dir}",
        proto_file,
    ]

    try:
        subprocess.run(cmd, check=True)
        base_name = proto_name.replace(".proto", "")
        print(f"  Generated: {base_name}_pb2.py, {base_name}_pb2_grpc.py")
        return True
    except subprocess.CalledProcessError as e:
        print(f"  Error: {e}")
        return False


def generate():
    """Generate all proto files."""
    grpc_dir = os.path.dirname(os.path.abspath(__file__))

    # Proto files to generate
    protos = [
        "rvc_service.proto",      # RVC-only service
        "voice_service.proto",    # Unified TTS+RVC service
    ]

    print("=" * 50)
    print("Generating gRPC Python code")
    print("=" * 50)

    success = 0
    for proto in protos:
        if generate_proto(grpc_dir, proto):
            success += 1

    print("=" * 50)
    print(f"Generated {success}/{len(protos)} proto files")

    if success == 0:
        print("Error: grpc_tools not installed? Run: pip install grpcio-tools")
        sys.exit(1)


if __name__ == "__main__":
    generate()
