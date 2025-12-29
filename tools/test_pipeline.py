#!/usr/bin/env python3
"""
Test Pipeline for Triton Spark TTS + RVC Integration

This script tests the full pipeline:
1. Triton Spark TTS (gRPC to container)
2. RVC voice conversion (host Python with CUDA)

Designed to run in Google Colab where Triton container is available.

Usage:
    # Basic test (requires Triton running and RVC assets downloaded)
    python tools/test_pipeline.py

    # With custom settings
    python tools/test_pipeline.py \
        --triton-addr localhost \
        --triton-port 8001 \
        --rvc-model "SilverWolf.pth" \
        --prompt-audio "path/to/reference.wav" \
        --prompt-text "Reference transcript" \
        --text "Hello, this is a test."

    # Test only Triton TTS (no RVC)
    python tools/test_pipeline.py --tts-only

    # Test only RVC (requires existing audio file)
    python tools/test_pipeline.py --rvc-only --input-audio "path/to/audio.wav"
"""

import os
import sys
import time
import argparse
import logging
from pathlib import Path

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("test_pipeline")


def setup_paths():
    """Add project root to Python path."""
    script_dir = Path(__file__).parent
    project_root = script_dir.parent

    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    os.chdir(project_root)
    logger.info(f"Working directory: {project_root}")

    return project_root, project_root / "rvc"


def test_triton_connection(addr: str, port: int) -> bool:
    """Test connection to Triton server."""
    logger.info(f"Testing Triton connection at {addr}:{port}...")

    try:
        from rvc.triton_client import TritonSparkClient

        client = TritonSparkClient(server_addr=addr, server_port=port)

        if client.is_server_ready():
            logger.info("✓ Triton server is ready")
        else:
            logger.error("✗ Triton server not ready")
            return False

        if client.is_model_ready():
            logger.info("✓ Spark TTS model is loaded")
        else:
            logger.error("✗ Spark TTS model not loaded")
            return False

        # Get model metadata
        try:
            metadata = client.get_model_metadata()
            logger.info(f"  Model: {metadata.get('name', 'unknown')}")
        except Exception as e:
            logger.warning(f"  Could not get model metadata: {e}")

        client.close()
        return True

    except Exception as e:
        logger.error(f"✗ Triton connection failed: {e}")
        return False


def test_rvc_initialization() -> bool:
    """Test RVC initialization."""
    logger.info("Testing RVC initialization...")

    try:
        from rvc.rvc_init import init_rvc, get_config, is_initialized

        if is_initialized():
            logger.info("  RVC already initialized")
        else:
            init_rvc()

        config = get_config()
        logger.info(f"✓ RVC initialized")
        logger.info(f"  Device: {config.device}")
        logger.info(f"  Half precision: {config.is_half}")
        logger.info(f"  GPU: {config.gpu_name or 'N/A'}")
        logger.info(f"  GPU Memory: {config.gpu_mem or 'N/A'} GB")

        return True

    except Exception as e:
        logger.error(f"✗ RVC initialization failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_tts_inference(
    addr: str,
    port: int,
    text: str,
    prompt_audio: str,
    prompt_text: str,
    output_path: str,
) -> bool:
    """Test Triton Spark TTS inference."""
    logger.info("Testing Triton Spark TTS inference...")
    logger.info(f"  Text: {text[:50]}{'...' if len(text) > 50 else ''}")
    logger.info(f"  Prompt audio: {prompt_audio}")

    try:
        import soundfile as sf
        from rvc.triton_client import TritonSparkClient

        client = TritonSparkClient(server_addr=addr, server_port=port)

        start_time = time.time()
        wav = client.inference(
            text=text,
            prompt_speech=prompt_audio,
            prompt_text=prompt_text,
        )
        elapsed = time.time() - start_time

        # Calculate stats
        duration = len(wav) / 16000
        rtf = elapsed / duration if duration > 0 else 0

        logger.info(f"✓ TTS inference complete")
        logger.info(f"  Generated: {len(wav)} samples ({duration:.2f}s)")
        logger.info(f"  Inference time: {elapsed:.2f}s")
        logger.info(f"  RTF: {rtf:.3f}")

        # Save output
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        sf.write(output_path, wav, 16000)
        logger.info(f"  Saved to: {output_path}")

        client.close()
        return True

    except Exception as e:
        logger.error(f"✗ TTS inference failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_rvc_inference(
    input_audio: str,
    rvc_model: str,
    output_path: str,
    pitch_shift: int = 0,
    f0_method: str = "rmvpe",
    index_path: str = "",
) -> bool:
    """Test RVC voice conversion."""
    logger.info("Testing RVC voice conversion...")
    logger.info(f"  Input: {input_audio}")
    logger.info(f"  Model: {rvc_model}")
    logger.info(f"  Pitch shift: {pitch_shift}")
    logger.info(f"  F0 method: {f0_method}")

    try:
        import soundfile as sf
        from rvc.rvc_init import init_rvc, load_model, convert_audio, is_initialized

        # Initialize if needed
        if not is_initialized():
            init_rvc()

        # Load model
        logger.info(f"  Loading RVC model...")
        model_info = load_model(rvc_model)
        logger.info(f"  Model version: {model_info.get('version', 'unknown')}")
        logger.info(f"  Target SR: {model_info.get('tgt_sr', 'unknown')}")

        # Auto-detect index if not provided
        if not index_path and model_info.get("index_path"):
            index_path = model_info["index_path"]
            logger.info(f"  Auto-detected index: {index_path}")

        # Convert
        start_time = time.time()
        info, (sr, audio) = convert_audio(
            audio_path=input_audio,
            pitch_shift=pitch_shift,
            f0_method=f0_method,
            index_path=index_path,
        )
        elapsed = time.time() - start_time

        if audio is None:
            logger.error(f"✗ RVC conversion failed: {info}")
            return False

        # Calculate stats
        duration = len(audio) / sr if sr else 0

        logger.info(f"✓ RVC conversion complete")
        logger.info(f"  Output: {len(audio)} samples ({duration:.2f}s @ {sr}Hz)")
        logger.info(f"  Conversion time: {elapsed:.2f}s")
        logger.info(f"  Info: {info.split(chr(10))[0]}")  # First line only

        # Save output
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        sf.write(output_path, audio, sr)
        logger.info(f"  Saved to: {output_path}")

        return True

    except Exception as e:
        logger.error(f"✗ RVC conversion failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_full_pipeline(
    addr: str,
    port: int,
    text: str,
    prompt_audio: str,
    prompt_text: str,
    rvc_model: str,
    pitch_shift: int = 0,
    f0_method: str = "rmvpe",
    index_path: str = "",
    output_dir: str = "./TEMP/test",
) -> bool:
    """Test full pipeline: Text → Triton TTS → RVC → Audio."""
    logger.info("=" * 60)
    logger.info("FULL PIPELINE TEST: Text → Triton TTS → RVC → Audio")
    logger.info("=" * 60)

    os.makedirs(output_dir, exist_ok=True)
    tts_output = os.path.join(output_dir, "tts_output.wav")
    rvc_output = os.path.join(output_dir, "rvc_output.wav")

    # Step 1: TTS
    logger.info("\n--- Step 1: Triton Spark TTS ---")
    start_total = time.time()

    if not test_tts_inference(addr, port, text, prompt_audio, prompt_text, tts_output):
        return False

    # Step 2: RVC
    logger.info("\n--- Step 2: RVC Voice Conversion ---")

    if not test_rvc_inference(tts_output, rvc_model, rvc_output, pitch_shift, f0_method, index_path):
        return False

    # Summary
    elapsed_total = time.time() - start_total
    logger.info("\n" + "=" * 60)
    logger.info("PIPELINE COMPLETE")
    logger.info("=" * 60)
    logger.info(f"Total time: {elapsed_total:.2f}s")
    logger.info(f"TTS output: {tts_output}")
    logger.info(f"RVC output: {rvc_output}")

    return True


def main():
    parser = argparse.ArgumentParser(
        description="Test Triton Spark TTS + RVC pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    # Triton settings
    parser.add_argument("--triton-addr", default="localhost", help="Triton server address")
    parser.add_argument("--triton-port", type=int, default=8001, help="Triton gRPC port")

    # RVC settings
    parser.add_argument("--rvc-model", default="", help="RVC model filename (e.g., 'SilverWolf.pth')")
    parser.add_argument("--pitch-shift", type=int, default=0, help="Pitch shift in semitones")
    parser.add_argument("--f0-method", default="rmvpe", choices=["rmvpe", "crepe", "harvest", "pm"])
    parser.add_argument("--index-path", default="", help="Path to .index file (auto-detected if empty)")

    # Input settings
    parser.add_argument("--text", default="Hello! This is a test of the Triton Spark TTS and RVC pipeline.")
    parser.add_argument("--prompt-audio", default="", help="Path to reference audio for TTS")
    parser.add_argument("--prompt-text", default="", help="Transcript of reference audio")
    parser.add_argument("--input-audio", default="", help="Input audio for RVC-only test")

    # Output settings
    parser.add_argument("--output-dir", default="./TEMP/test", help="Output directory")

    # Test modes
    parser.add_argument("--tts-only", action="store_true", help="Test only Triton TTS")
    parser.add_argument("--rvc-only", action="store_true", help="Test only RVC")
    parser.add_argument("--connection-only", action="store_true", help="Test only Triton connection")
    parser.add_argument("--skip-rvc-init", action="store_true", help="Skip RVC initialization test")

    args = parser.parse_args()

    # Setup
    project_root, rvc_ready = setup_paths()

    logger.info("=" * 60)
    logger.info("Triton Spark TTS + RVC Pipeline Test")
    logger.info("=" * 60)

    results = {}

    # Test 1: Triton connection
    logger.info("\n--- Test: Triton Connection ---")
    results["triton_connection"] = test_triton_connection(args.triton_addr, args.triton_port)

    if args.connection_only:
        return 0 if results["triton_connection"] else 1

    # Test 2: RVC initialization (unless skipped or TTS-only)
    if not args.tts_only and not args.skip_rvc_init:
        logger.info("\n--- Test: RVC Initialization ---")
        results["rvc_init"] = test_rvc_initialization()

    # Test 3: Based on mode
    if args.tts_only:
        # TTS only
        if not args.prompt_audio:
            logger.error("--prompt-audio required for TTS test")
            return 1

        logger.info("\n--- Test: TTS Only ---")
        tts_output = os.path.join(args.output_dir, "tts_output.wav")
        results["tts"] = test_tts_inference(
            args.triton_addr,
            args.triton_port,
            args.text,
            args.prompt_audio,
            args.prompt_text,
            tts_output,
        )

    elif args.rvc_only:
        # RVC only
        if not args.input_audio:
            logger.error("--input-audio required for RVC-only test")
            return 1
        if not args.rvc_model:
            logger.error("--rvc-model required for RVC test")
            return 1

        logger.info("\n--- Test: RVC Only ---")
        rvc_output = os.path.join(args.output_dir, "rvc_output.wav")
        results["rvc"] = test_rvc_inference(
            args.input_audio,
            args.rvc_model,
            rvc_output,
            args.pitch_shift,
            args.f0_method,
            args.index_path,
        )

    else:
        # Full pipeline
        if not args.prompt_audio:
            logger.error("--prompt-audio required for full pipeline test")
            return 1
        if not args.rvc_model:
            logger.error("--rvc-model required for full pipeline test")
            return 1

        results["full_pipeline"] = test_full_pipeline(
            args.triton_addr,
            args.triton_port,
            args.text,
            args.prompt_audio,
            args.prompt_text,
            args.rvc_model,
            args.pitch_shift,
            args.f0_method,
            args.index_path,
            args.output_dir,
        )

    # Summary
    logger.info("\n" + "=" * 60)
    logger.info("TEST RESULTS")
    logger.info("=" * 60)
    all_passed = True
    for test_name, passed in results.items():
        status = "✓ PASS" if passed else "✗ FAIL"
        logger.info(f"  {test_name}: {status}")
        if not passed:
            all_passed = False

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
