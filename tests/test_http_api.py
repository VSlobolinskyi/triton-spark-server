#!/usr/bin/env python3
"""Test HTTP API endpoints - main test for Colab.

Usage:
    python -m tests.test_http_api --host localhost --port 8080
    python -m tests.test_http_api --host localhost --port 8080 --reference ref.wav --full
"""

import argparse
import sys
import time


def test_health(host: str, port: int) -> bool:
    """Test /health endpoint."""
    try:
        import requests

        print("Testing /health endpoint...")
        response = requests.get(f"http://{host}:{port}/health", timeout=10)

        if response.status_code == 200:
            health = response.json()
            print(f"  Status: {health.get('status', 'unknown')}")
            print(f"  Triton ready: {health.get('triton_ready', 'N/A')}")
            print(f"  RVC ready: {health.get('rvc_ready', 'N/A')}")
            return health.get("status") == "healthy"
        else:
            print(f"  [FAIL] HTTP {response.status_code}")
            return False

    except Exception as e:
        print(f"  [ERROR] {e}")
        return False


def test_status(host: str, port: int) -> bool:
    """Test /status endpoint."""
    try:
        import requests

        print("Testing /status endpoint...")
        response = requests.get(f"http://{host}:{port}/status", timeout=10)

        if response.status_code == 200:
            status = response.json()
            print(f"  RVC Model: {status.get('rvc_model', 'N/A')}")
            print(f"  RVC Workers: {status.get('rvc_workers', 'N/A')}")
            print(f"  Triton: {status.get('triton_addr', 'N/A')}:{status.get('triton_port', 'N/A')}")
            return True
        else:
            print(f"  [FAIL] HTTP {response.status_code}")
            return False

    except Exception as e:
        print(f"  [ERROR] {e}")
        return False


def test_synthesize(host: str, port: int, reference_audio: str, text: str) -> bool:
    """Test /synthesize endpoint."""
    try:
        import requests
        import soundfile as sf

        print("Testing /synthesize endpoint...")
        print(f"  Text: {text[:40]}...")

        with open(reference_audio, "rb") as f:
            ref_audio_data = f.read()

        start_time = time.time()
        response = requests.post(
            f"http://{host}:{port}/synthesize",
            data={
                "text": text,
                "reference_text": "",
                "pitch_shift": 0,
                "f0_method": "rmvpe",
                "index_rate": 0.75,
                "skip_rvc": False,
            },
            files={
                "reference_audio": ("reference.wav", ref_audio_data, "audio/wav")
            },
            timeout=120,
        )
        elapsed = time.time() - start_time

        if response.status_code == 200:
            tts_time = float(response.headers.get("X-TTS-Time", 0))
            rvc_time = float(response.headers.get("X-RVC-Time", 0))

            # Save temporarily to get duration
            output_path = "TEMP/api_test_synthesize.wav"
            with open(output_path, "wb") as f:
                f.write(response.content)

            audio, sr = sf.read(output_path)
            duration = len(audio) / sr

            print(f"  TTS: {tts_time:.2f}s, RVC: {rvc_time:.2f}s, Total: {elapsed:.2f}s")
            print(f"  Audio: {duration:.2f}s @ {sr}Hz")
            return True
        else:
            print(f"  [FAIL] HTTP {response.status_code}: {response.text[:100]}")
            return False

    except Exception as e:
        print(f"  [ERROR] {e}")
        import traceback
        traceback.print_exc()
        return False


def test_tts_endpoint(host: str, port: int, reference_audio: str, text: str) -> bool:
    """Test /tts endpoint."""
    try:
        import requests
        import soundfile as sf

        print("Testing /tts endpoint...")

        with open(reference_audio, "rb") as f:
            ref_audio_data = f.read()

        response = requests.post(
            f"http://{host}:{port}/tts",
            data={
                "text": text,
                "reference_text": "",
            },
            files={
                "reference_audio": ("reference.wav", ref_audio_data, "audio/wav")
            },
            timeout=60,
        )

        if response.status_code == 200:
            tts_time = float(response.headers.get("X-TTS-Time", 0))
            print(f"  TTS time: {tts_time:.2f}s")
            return True
        else:
            print(f"  [FAIL] HTTP {response.status_code}")
            return False

    except Exception as e:
        print(f"  [ERROR] {e}")
        return False


def test_rvc_endpoint(host: str, port: int, input_audio: str) -> bool:
    """Test /rvc endpoint."""
    try:
        import requests

        print("Testing /rvc endpoint...")

        with open(input_audio, "rb") as f:
            audio_data = f.read()

        response = requests.post(
            f"http://{host}:{port}/rvc",
            data={
                "pitch_shift": 0,
                "f0_method": "rmvpe",
                "index_rate": 0.75,
            },
            files={
                "audio": ("input.wav", audio_data, "audio/wav")
            },
            timeout=60,
        )

        if response.status_code == 200:
            rvc_time = float(response.headers.get("X-RVC-Time", 0))
            print(f"  RVC time: {rvc_time:.2f}s")
            return True
        else:
            print(f"  [FAIL] HTTP {response.status_code}")
            return False

    except Exception as e:
        print(f"  [ERROR] {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Test HTTP API endpoints")
    parser.add_argument("--host", default="localhost", help="API host")
    parser.add_argument("--port", type=int, default=8080, help="API port")
    parser.add_argument("--reference", help="Reference audio for synthesis tests")
    parser.add_argument("--text", default="Hello, this is a test.", help="Text for synthesis")
    parser.add_argument("--full", action="store_true", help="Run full tests including synthesis")
    args = parser.parse_args()

    print("=" * 60)
    print("HTTP API Tests")
    print("=" * 60)

    results = []

    # Always test health and status
    print("\n[1] Health Check")
    results.append(("health", test_health(args.host, args.port)))

    print("\n[2] Status")
    results.append(("status", test_status(args.host, args.port)))

    # Full tests require reference audio
    if args.full:
        if not args.reference:
            print("\n[ERROR] --reference required for full tests")
            sys.exit(1)

        print("\n[3] Synthesize (TTS + RVC)")
        results.append(("synthesize", test_synthesize(args.host, args.port, args.reference, args.text)))

        print("\n[4] TTS Only")
        results.append(("tts", test_tts_endpoint(args.host, args.port, args.reference, args.text)))

        # RVC needs input audio - use the TTS output
        import os
        tts_output = "TEMP/api_test_synthesize.wav"
        if os.path.exists(tts_output):
            print("\n[5] RVC Only")
            results.append(("rvc", test_rvc_endpoint(args.host, args.port, tts_output)))

    # Summary
    print("\n" + "=" * 60)
    print("Results Summary")
    print("=" * 60)

    all_passed = True
    for name, passed in results:
        status = "PASS" if passed else "FAIL"
        symbol = "[OK]" if passed else "[X]"
        print(f"  {symbol} {name}: {status}")
        if not passed:
            all_passed = False

    print("\n" + "=" * 60)
    print(f"Overall: {'ALL TESTS PASSED' if all_passed else 'SOME TESTS FAILED'}")
    print("=" * 60)

    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
