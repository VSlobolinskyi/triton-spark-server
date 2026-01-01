#!/usr/bin/env python3
"""
Environment Setup Script for Triton Spark TTS + RVC

This script sets up the Python environment with all required dependencies.
Designed to work in:
- Google Colab
- Triton Docker container
- Local development

Usage:
    python tools/setup_environment.py [--colab] [--container] [--local]
"""

import os
import sys
import subprocess
import argparse
from pathlib import Path


def run_cmd(cmd: str, desc: str = None, check: bool = True) -> bool:
    """Run a shell command."""
    if desc:
        print(f"\n[STEP] {desc}")
    print(f"  $ {cmd}")

    result = subprocess.run(cmd, shell=True, capture_output=not sys.stdout.isatty())
    if result.returncode != 0 and check:
        print(f"  [ERROR] Command failed with code {result.returncode}")
        if result.stderr:
            print(f"  {result.stderr.decode()}")
        return False
    return True


def setup_colab():
    """Setup for Google Colab environment."""
    print("=" * 60)
    print("Setting up Colab Environment")
    print("=" * 60)

    # Install fairseq from git (required for HuBERT)
    run_cmd(
        "pip install git+https://github.com/One-sixth/fairseq.git",
        "Installing fairseq (for HuBERT)"
    )

    # Install main requirements
    run_cmd(
        "pip install -r requirements.txt",
        "Installing main requirements"
    )

    print("\n[DONE] Colab environment setup complete!")
    print("\nNext steps:")
    print("  1. Run: python tools/download_all_assets.py")
    print("  2. Start Triton server (see triton_collab_scritps.txt)")


def setup_container():
    """Setup for Triton Docker container (additional deps only)."""
    print("=" * 60)
    print("Setting up Triton Container Environment")
    print("=" * 60)

    # Container already has torch, torchaudio, triton deps
    # Just need RVC-specific packages

    # fairseq for HuBERT
    run_cmd(
        "pip install git+https://github.com/One-sixth/fairseq.git",
        "Installing fairseq (for HuBERT)"
    )

    # RVC inference dependencies
    rvc_deps = [
        "faiss-cpu>=1.7.0",
        "pyworld==0.3.2",
        "praat-parselmouth>=0.4.2",
        "torchcrepe==0.0.23",
        "ffmpeg-python>=0.2.0",
        "av>=9.0.0",
        "python-dotenv>=1.0.0",
        "onnxruntime-gpu>=1.13.0",
    ]

    run_cmd(
        f"pip install {' '.join(rvc_deps)}",
        "Installing RVC dependencies"
    )

    print("\n[DONE] Container environment setup complete!")


def setup_local():
    """Setup for local development."""
    print("=" * 60)
    print("Setting up Local Development Environment")
    print("=" * 60)

    # Check Python version
    if sys.version_info < (3, 11):
        print("[WARNING] Python 3.11+ recommended for RVC")

    # Install PyTorch with CUDA
    print("\n[INFO] PyTorch with CUDA should be installed separately:")
    print("  pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121")

    # Install fairseq
    run_cmd(
        "pip install git+https://github.com/One-sixth/fairseq.git",
        "Installing fairseq (for HuBERT)"
    )

    # Install main requirements
    run_cmd(
        "pip install -r requirements.txt",
        "Installing main requirements"
    )

    print("\n[DONE] Local environment setup complete!")


def verify_installation():
    """Verify key packages are installed."""
    print("\n" + "=" * 60)
    print("Verifying Installation")
    print("=" * 60)

    packages = [
        ("torch", "PyTorch"),
        ("torchaudio", "TorchAudio"),
        ("fairseq", "FairSeq (HuBERT)"),
        ("librosa", "Librosa"),
        ("faiss", "FAISS"),
        ("pyworld", "PyWorld"),
        ("parselmouth", "Praat-Parselmouth"),
        ("torchcrepe", "TorchCREPE"),
        ("tritonclient", "Triton Client"),
    ]

    all_ok = True
    for pkg, name in packages:
        try:
            __import__(pkg)
            print(f"  [OK] {name}")
        except ImportError:
            print(f"  [MISSING] {name}")
            all_ok = False

    # Check CUDA
    try:
        import torch
        if torch.cuda.is_available():
            print(f"  [OK] CUDA available: {torch.cuda.get_device_name(0)}")
        else:
            print("  [WARNING] CUDA not available")
    except Exception as e:
        print(f"  [ERROR] CUDA check failed: {e}")

    return all_ok


def main():
    parser = argparse.ArgumentParser(description="Setup environment for Triton Spark TTS + RVC")
    parser.add_argument("--colab", action="store_true", help="Setup for Google Colab")
    parser.add_argument("--container", action="store_true", help="Setup for Triton container")
    parser.add_argument("--local", action="store_true", help="Setup for local development")
    parser.add_argument("--verify", action="store_true", help="Only verify installation")

    args = parser.parse_args()

    # Change to project root
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    os.chdir(project_root)
    print(f"Working directory: {project_root}")

    if args.verify:
        verify_installation()
        return

    # Auto-detect environment if not specified
    if not any([args.colab, args.container, args.local]):
        if os.path.exists("/content"):
            args.colab = True
        elif os.path.exists("/opt/tritonserver"):
            args.container = True
        else:
            args.local = True

    if args.colab:
        setup_colab()
    elif args.container:
        setup_container()
    else:
        setup_local()

    verify_installation()


if __name__ == "__main__":
    main()
