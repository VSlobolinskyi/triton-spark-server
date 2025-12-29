#!/usr/bin/env python3
"""
Unified Asset Downloader for Triton Spark TTS + RVC

Downloads:
1. Spark-TTS-0.5B model from HuggingFace
2. RVC base models (HuBERT, RMVPE)
3. RVC pretrained models (optional)

Usage:
    python tools/download_all_assets.py [--spark-only] [--rvc-only] [--skip-pretrained]

Environment:
    SPARK_MODEL_DIR: Where to save Spark model (default: ./pretrained_models/Spark-TTS-0.5B)
    RVC_ROOT: Root directory for RVC assets (default: ./rvc-ready)
"""

import os
import sys
import argparse
import subprocess
from pathlib import Path
from typing import Optional

import requests


# =============================================================================
# Configuration
# =============================================================================

# HuggingFace model for Spark TTS
SPARK_HF_REPO = "SparkAudio/Spark-TTS-0.5B"

# RVC model download URLs
RVC_DOWNLOAD_LINK = "https://huggingface.co/lj1995/VoiceConversionWebUI/resolve/main/"

# Required RVC models
RVC_REQUIRED_MODELS = {
    "hubert": ["hubert_base.pt"],
    "rmvpe": ["rmvpe.pt"],
}

# Optional RVC pretrained models (for training, not needed for inference)
RVC_PRETRAINED_V1 = [
    "D32k.pth", "D40k.pth", "D48k.pth",
    "G32k.pth", "G40k.pth", "G48k.pth",
    "f0D32k.pth", "f0D40k.pth", "f0D48k.pth",
    "f0G32k.pth", "f0G40k.pth", "f0G48k.pth",
]


# =============================================================================
# Utility Functions
# =============================================================================

def download_file(url: str, dest_path: Path, desc: str = None) -> bool:
    """Download a file with progress indication."""
    if dest_path.exists():
        print(f"  [SKIP] {dest_path.name} already exists")
        return True

    dest_path.parent.mkdir(parents=True, exist_ok=True)
    print(f"  [DOWNLOAD] {desc or dest_path.name}...")

    try:
        with requests.get(url, stream=True) as r:
            r.raise_for_status()
            total = int(r.headers.get('content-length', 0))
            downloaded = 0

            with open(dest_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total:
                        pct = downloaded * 100 // total
                        print(f"\r  [DOWNLOAD] {desc or dest_path.name}... {pct}%", end="")

            print(f"\r  [DONE] {dest_path.name}" + " " * 20)
            return True

    except Exception as e:
        print(f"\n  [ERROR] Failed to download {url}: {e}")
        if dest_path.exists():
            dest_path.unlink()
        return False


def run_command(command: list, error_msg: str) -> bool:
    """Run a shell command."""
    try:
        subprocess.run(command, check=True)
        return True
    except subprocess.CalledProcessError:
        print(f"  [ERROR] {error_msg}")
        return False


# =============================================================================
# Spark TTS Download
# =============================================================================

def download_spark_model(model_dir: Path) -> bool:
    """Download Spark-TTS-0.5B from HuggingFace."""
    print("\n" + "=" * 60)
    print("Downloading Spark-TTS-0.5B Model")
    print("=" * 60)

    if (model_dir / "config.yaml").exists():
        print(f"  [SKIP] Model already exists at {model_dir}")
        return True

    model_dir.mkdir(parents=True, exist_ok=True)

    # Try huggingface-cli first
    try:
        print("  [INFO] Using huggingface-cli...")
        result = subprocess.run(
            ["huggingface-cli", "download", SPARK_HF_REPO, "--local-dir", str(model_dir)],
            check=True
        )
        print("  [DONE] Spark-TTS-0.5B downloaded successfully")
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass

    # Fallback to huggingface_hub Python API
    try:
        print("  [INFO] Using huggingface_hub Python API...")
        from huggingface_hub import snapshot_download
        snapshot_download(repo_id=SPARK_HF_REPO, local_dir=str(model_dir))
        print("  [DONE] Spark-TTS-0.5B downloaded successfully")
        return True
    except Exception as e:
        print(f"  [ERROR] Failed to download Spark model: {e}")
        return False


# =============================================================================
# RVC Assets Download
# =============================================================================

def download_rvc_assets(rvc_root: Path, include_pretrained: bool = False) -> bool:
    """Download RVC required assets."""
    print("\n" + "=" * 60)
    print("Downloading RVC Assets")
    print("=" * 60)

    success = True

    # Download required models
    for subdir, models in RVC_REQUIRED_MODELS.items():
        dest_dir = rvc_root / "assets" / subdir
        for model in models:
            url = f"{RVC_DOWNLOAD_LINK}{model}"
            if not download_file(url, dest_dir / model, f"{subdir}/{model}"):
                success = False

    # Download pretrained models (optional)
    if include_pretrained:
        print("\n  [INFO] Downloading pretrained models (optional)...")

        # Pretrained v1
        dest_dir = rvc_root / "assets" / "pretrained"
        for model in RVC_PRETRAINED_V1:
            url = f"{RVC_DOWNLOAD_LINK}pretrained/{model}"
            download_file(url, dest_dir / model, f"pretrained/{model}")

        # Pretrained v2
        dest_dir = rvc_root / "assets" / "pretrained_v2"
        for model in RVC_PRETRAINED_V1:
            url = f"{RVC_DOWNLOAD_LINK}pretrained_v2/{model}"
            download_file(url, dest_dir / model, f"pretrained_v2/{model}")

    if success:
        print("  [DONE] RVC assets downloaded successfully")
    return success


# =============================================================================
# RVC Voice Model Download
# =============================================================================

def download_rvc_voice_model(url: str, rvc_root: Path) -> bool:
    """
    Download and extract an RVC voice model from a zip URL.

    Args:
        url: URL to the zip file (e.g., HuggingFace)
        rvc_root: Root directory for RVC assets
    """
    import tempfile
    import zipfile
    import shutil

    print("\n" + "=" * 60)
    print(f"Downloading RVC Voice Model")
    print("=" * 60)

    zip_filename = Path(url).name
    weights_dir = rvc_root / "assets" / "weights"
    logs_dir = rvc_root / "logs"

    weights_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)

    # Download zip
    with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
        tmp_path = Path(tmp.name)

    if not download_file(url, tmp_path, zip_filename):
        return False

    # Extract
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            print(f"  [EXTRACT] Extracting {zip_filename}...")

            with zipfile.ZipFile(tmp_path, 'r') as zip_ref:
                zip_ref.extractall(tmpdir)

            # Move files to correct locations
            for f in tmpdir.rglob("*.pth"):
                dest = weights_dir / f.name
                print(f"  [MOVE] {f.name} -> assets/weights/")
                shutil.move(str(f), str(dest))

            for f in tmpdir.rglob("*.index"):
                dest = logs_dir / f.name
                print(f"  [MOVE] {f.name} -> logs/")
                shutil.move(str(f), str(dest))

        print("  [DONE] Voice model extracted successfully")
        return True

    except Exception as e:
        print(f"  [ERROR] Failed to extract: {e}")
        return False

    finally:
        if tmp_path.exists():
            tmp_path.unlink()


# =============================================================================
# Main
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Download Spark TTS and RVC assets"
    )
    parser.add_argument(
        "--spark-only", action="store_true",
        help="Only download Spark TTS model"
    )
    parser.add_argument(
        "--rvc-only", action="store_true",
        help="Only download RVC assets"
    )
    parser.add_argument(
        "--skip-pretrained", action="store_true",
        help="Skip RVC pretrained models (training only)"
    )
    parser.add_argument(
        "--rvc-model", type=str,
        help="URL to RVC voice model zip to download"
    )
    parser.add_argument(
        "--spark-dir", type=str,
        default=os.environ.get("SPARK_MODEL_DIR", "./pretrained_models/Spark-TTS-0.5B"),
        help="Directory for Spark model"
    )
    parser.add_argument(
        "--rvc-dir", type=str,
        default=os.environ.get("RVC_ROOT", "./rvc-ready"),
        help="Root directory for RVC assets"
    )

    args = parser.parse_args()

    spark_dir = Path(args.spark_dir)
    rvc_dir = Path(args.rvc_dir)

    print("=" * 60)
    print("Triton Spark TTS + RVC Asset Downloader")
    print("=" * 60)
    print(f"Spark model dir: {spark_dir}")
    print(f"RVC root dir:    {rvc_dir}")

    success = True

    # Download Spark model
    if not args.rvc_only:
        if not download_spark_model(spark_dir):
            success = False

    # Download RVC assets
    if not args.spark_only:
        if not download_rvc_assets(rvc_dir, include_pretrained=not args.skip_pretrained):
            success = False

    # Download specific RVC voice model if provided
    if args.rvc_model:
        if not download_rvc_voice_model(args.rvc_model, rvc_dir):
            success = False

    print("\n" + "=" * 60)
    if success:
        print("All downloads completed successfully!")
    else:
        print("Some downloads failed. Check errors above.")
        sys.exit(1)
    print("=" * 60)


if __name__ == "__main__":
    main()
