#!/usr/bin/env python3
"""Run TTS inference only."""
import sys
import os
import argparse
import time

# Setup path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import soundfile as sf
from rvc.triton_client import TritonSparkClient

def main():
    parser = argparse.ArgumentParser(description="Run TTS inference")
    parser.add_argument("--addr", default="localhost", help="Triton server address")
    parser.add_argument("--port", type=int, default=8001, help="Triton server port")
    parser.add_argument("--text", required=True, help="Text to synthesize")
    parser.add_argument("--reference-audio", required=True, help="Reference audio path")
    parser.add_argument("--reference-text", default="", help="Reference text")
    parser.add_argument("--output", default="TEMP/tts/tts_output.wav", help="Output path")
    args = parser.parse_args()

    # Ensure output dir exists
    os.makedirs(os.path.dirname(args.output), exist_ok=True)

    client = TritonSparkClient(server_addr=args.addr, server_port=args.port)

    start = time.time()
    wav = client.inference(
        text=args.text,
        prompt_speech=args.reference_audio,
        prompt_text=args.reference_text,
    )
    elapsed = time.time() - start

    duration = len(wav) / 16000
    print(f"Generated {duration:.2f}s of audio in {elapsed:.2f}s (RTF: {elapsed/duration:.2f})")

    sf.write(args.output, wav, 16000)
    print(f"Saved to {args.output}")
    client.close()

if __name__ == "__main__":
    main()
