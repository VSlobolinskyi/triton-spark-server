#!/usr/bin/env python3
"""Test RVC (Retrieval-based Voice Conversion) inference.

Usage:
    python -m tests.test_rvc --host localhost --port 8080 --input audio.wav
    python -m tests.test_rvc --host localhost --port 8080 --input audio.wav --output converted.wav
"""

import argparse
import sys
import time


def test_rvc_via_http(
    host: str,
    port: int,
    input_audio: str,
    pitch_shift: int = 0,
    f0_method: str = "rmvpe",
    index_rate: float = 0.75,
    output_path: str | None = None,
) -> bool:
    """Test RVC inference via HTTP API."""
    try:
        import requests
        import soundfile as sf

        print(f"Testing RVC via HTTP API...")
        print(f"  Host: {host}:{port}")
        print(f"  Input: {input_audio}")
        print(f"  Pitch shift: {pitch_shift}")
        print(f"  F0 method: {f0_method}")

        # Read input audio
        with open(input_audio, "rb") as f:
            audio_data = f.read()

        # Call RVC endpoint
        start_time = time.time()
        response = requests.post(
            f"http://{host}:{port}/rvc",
            data={
                "pitch_shift": pitch_shift,
                "f0_method": f0_method,
                "index_rate": index_rate,
            },
            files={
                "audio": ("input.wav", audio_data, "audio/wav")
            },
            timeout=120,
        )
        elapsed = time.time() - start_time

        if response.status_code != 200:
            print(f"  [FAIL] HTTP {response.status_code}: {response.text}")
            return False

        # Get timing from headers
        rvc_time = float(response.headers.get("X-RVC-Time", elapsed))

        # Save output
        output_file = output_path or "TEMP/rvc_test_output.wav"
        with open(output_file, "wb") as f:
            f.write(response.content)

        # Get duration
        audio, sr = sf.read(output_file)
        duration = len(audio) / sr

        print(f"  [OK] Converted {duration:.2f}s audio in {rvc_time:.2f}s")
        print(f"  [OK] Saved to {output_file}")

        return True

    except Exception as e:
        print(f"  [ERROR] RVC failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    parser = argparse.ArgumentParser(description="Test RVC inference")
    parser.add_argument("--host", default="localhost", help="HTTP API host")
    parser.add_argument("--port", type=int, default=8080, help="HTTP API port")
    parser.add_argument("--input", required=True, help="Input audio file (WAV)")
    parser.add_argument("--output", help="Output WAV file path")
    parser.add_argument("--pitch-shift", type=int, default=0, help="Pitch shift in semitones")
    parser.add_argument("--f0-method", default="rmvpe", choices=["rmvpe", "pm", "harvest"], help="F0 extraction method")
    parser.add_argument("--index-rate", type=float, default=0.75, help="Index rate (0-1)")
    args = parser.parse_args()

    print("=" * 50)
    print("RVC Inference Test")
    print("=" * 50)

    success = test_rvc_via_http(
        host=args.host,
        port=args.port,
        input_audio=args.input,
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
