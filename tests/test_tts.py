#!/usr/bin/env python3
"""Test TTS (Text-to-Speech) inference.

Usage:
    python -m tests.test_tts --host localhost --port 8001 --reference ref.wav
    python -m tests.test_tts --host localhost --port 8001 --reference ref.wav --output output.wav
"""

import argparse
import sys
import time


def test_tts_inference(
    host: str,
    port: int,
    reference_audio: str,
    text: str,
    reference_text: str = "",
    output_path: str | None = None,
) -> bool:
    """Test TTS inference via Triton gRPC."""
    try:
        import soundfile as sf
        from rvc.triton_client import TritonSparkClient

        print(f"Testing TTS inference...")
        print(f"  Host: {host}:{port}")
        print(f"  Reference: {reference_audio}")
        print(f"  Text: {text[:50]}...")

        # Connect
        client = TritonSparkClient(server_addr=host, server_port=port)
        if not client.is_server_ready():
            print("  [FAIL] Server not ready")
            return False

        # Run inference
        start_time = time.time()
        audio = client.inference(
            text=text,
            prompt_speech=reference_audio,
            prompt_text=reference_text,
        )
        elapsed = time.time() - start_time

        client.close()

        # Validate output
        if audio is None or len(audio) == 0:
            print("  [FAIL] No audio generated")
            return False

        duration = len(audio) / 16000
        print(f"  [OK] Generated {duration:.2f}s audio in {elapsed:.2f}s")
        print(f"  [OK] RTF: {elapsed/duration:.2f}x")

        # Save if requested
        if output_path:
            sf.write(output_path, audio, 16000)
            print(f"  [OK] Saved to {output_path}")

        return True

    except Exception as e:
        print(f"  [ERROR] TTS failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    parser = argparse.ArgumentParser(description="Test TTS inference")
    parser.add_argument("--host", default="localhost", help="Triton server host")
    parser.add_argument("--port", type=int, default=8001, help="Triton gRPC port")
    parser.add_argument("--reference", required=True, help="Reference audio file (16kHz WAV)")
    parser.add_argument("--reference-text", default="", help="Reference text (optional)")
    parser.add_argument("--text", default="Hello, this is a test of the text to speech system.", help="Text to synthesize")
    parser.add_argument("--output", help="Output WAV file path")
    args = parser.parse_args()

    print("=" * 50)
    print("TTS Inference Test")
    print("=" * 50)

    success = test_tts_inference(
        host=args.host,
        port=args.port,
        reference_audio=args.reference,
        text=args.text,
        reference_text=args.reference_text,
        output_path=args.output,
    )

    print("\n" + "=" * 50)
    print(f"Result: {'PASS' if success else 'FAIL'}")
    print("=" * 50)

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
