#!/usr/bin/env python3
"""Test full TTS + RVC pipeline.

Usage:
    python -m tests.test_pipeline --host localhost --port 8080 --reference ref.wav
    python -m tests.test_pipeline --host localhost --port 8080 --reference ref.wav --output output.wav
"""

import argparse
import sys
import time


def test_full_pipeline(
    host: str,
    port: int,
    reference_audio: str,
    text: str,
    reference_text: str = "",
    pitch_shift: int = 0,
    f0_method: str = "rmvpe",
    index_rate: float = 0.75,
    output_path: str | None = None,
) -> bool:
    """Test full TTS + RVC pipeline via HTTP API."""
    try:
        import requests
        import soundfile as sf

        print(f"Testing full pipeline (TTS + RVC)...")
        print(f"  Host: {host}:{port}")
        print(f"  Reference: {reference_audio}")
        print(f"  Text: {text[:50]}...")

        # Read reference audio
        with open(reference_audio, "rb") as f:
            ref_audio_data = f.read()

        # Call synthesize endpoint
        start_time = time.time()
        response = requests.post(
            f"http://{host}:{port}/synthesize",
            data={
                "text": text,
                "reference_text": reference_text,
                "pitch_shift": pitch_shift,
                "f0_method": f0_method,
                "index_rate": index_rate,
                "skip_rvc": False,
            },
            files={
                "reference_audio": ("reference.wav", ref_audio_data, "audio/wav")
            },
            timeout=120,
        )
        total_time = time.time() - start_time

        if response.status_code != 200:
            print(f"  [FAIL] HTTP {response.status_code}: {response.text}")
            return False

        # Get timing from headers
        tts_time = float(response.headers.get("X-TTS-Time", 0))
        rvc_time = float(response.headers.get("X-RVC-Time", 0))

        # Save output
        output_file = output_path or "TEMP/pipeline_test_output.wav"
        with open(output_file, "wb") as f:
            f.write(response.content)

        # Get duration
        audio, sr = sf.read(output_file)
        duration = len(audio) / sr

        print(f"  [OK] TTS time: {tts_time:.2f}s")
        print(f"  [OK] RVC time: {rvc_time:.2f}s")
        print(f"  [OK] Total time: {total_time:.2f}s")
        print(f"  [OK] Audio duration: {duration:.2f}s")
        print(f"  [OK] Saved to {output_file}")

        return True

    except Exception as e:
        print(f"  [ERROR] Pipeline failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_tts_only(
    host: str,
    port: int,
    reference_audio: str,
    text: str,
    reference_text: str = "",
    output_path: str | None = None,
) -> bool:
    """Test TTS-only mode (skip RVC)."""
    try:
        import requests
        import soundfile as sf

        print(f"Testing TTS only (skip_rvc=True)...")

        with open(reference_audio, "rb") as f:
            ref_audio_data = f.read()

        start_time = time.time()
        response = requests.post(
            f"http://{host}:{port}/synthesize",
            data={
                "text": text,
                "reference_text": reference_text,
                "skip_rvc": True,
            },
            files={
                "reference_audio": ("reference.wav", ref_audio_data, "audio/wav")
            },
            timeout=60,
        )
        elapsed = time.time() - start_time

        if response.status_code != 200:
            print(f"  [FAIL] HTTP {response.status_code}: {response.text}")
            return False

        tts_time = float(response.headers.get("X-TTS-Time", elapsed))

        output_file = output_path or "TEMP/tts_only_test_output.wav"
        with open(output_file, "wb") as f:
            f.write(response.content)

        audio, sr = sf.read(output_file)
        duration = len(audio) / sr

        print(f"  [OK] TTS time: {tts_time:.2f}s")
        print(f"  [OK] Audio duration: {duration:.2f}s")
        print(f"  [OK] Saved to {output_file}")

        return True

    except Exception as e:
        print(f"  [ERROR] TTS only failed: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Test full TTS + RVC pipeline")
    parser.add_argument("--host", default="localhost", help="HTTP API host")
    parser.add_argument("--port", type=int, default=8080, help="HTTP API port")
    parser.add_argument("--reference", required=True, help="Reference audio file (16kHz WAV)")
    parser.add_argument("--reference-text", default="", help="Reference text (optional)")
    parser.add_argument("--text", default="Hello, this is a test of the full voice synthesis pipeline.", help="Text to synthesize")
    parser.add_argument("--output", help="Output WAV file path")
    parser.add_argument("--pitch-shift", type=int, default=0, help="Pitch shift in semitones")
    parser.add_argument("--f0-method", default="rmvpe", help="F0 extraction method")
    parser.add_argument("--index-rate", type=float, default=0.75, help="Index rate")
    parser.add_argument("--tts-only", action="store_true", help="Test TTS only (skip RVC)")
    args = parser.parse_args()

    print("=" * 50)
    print("Pipeline Test")
    print("=" * 50)

    if args.tts_only:
        success = test_tts_only(
            host=args.host,
            port=args.port,
            reference_audio=args.reference,
            text=args.text,
            reference_text=args.reference_text,
            output_path=args.output,
        )
    else:
        success = test_full_pipeline(
            host=args.host,
            port=args.port,
            reference_audio=args.reference,
            text=args.text,
            reference_text=args.reference_text,
            pitch_shift=args.pitch_shift,
            f0_method=args.f0_method,
            index_rate=args.index_rate,
            output_path=args.output,
        )

    print("\n" + "=" * 50)
    print(f"Result: {'PASS' if success else 'FAIL'}")
    print("=" * 50)

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
