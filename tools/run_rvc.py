#!/usr/bin/env python3
"""Run RVC inference only."""
import sys
import os
import argparse
import time

# Setup path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import soundfile as sf
from rvc import init_rvc, load_model, convert_audio, is_initialized

def main():
    parser = argparse.ArgumentParser(description="Run RVC inference")
    parser.add_argument("--input", required=True, help="Input audio path")
    parser.add_argument("--model", required=True, help="RVC model name (e.g., SilverWolf.pth)")
    parser.add_argument("--output", default="TEMP/rvc/rvc_output.wav", help="Output path")
    parser.add_argument("--pitch-shift", type=int, default=0, help="Pitch shift in semitones")
    parser.add_argument("--f0-method", default="rmvpe", help="F0 method (rmvpe, crepe, etc.)")
    args = parser.parse_args()

    # Ensure output dir exists
    os.makedirs(os.path.dirname(args.output), exist_ok=True)

    if not is_initialized():
        init_rvc()

    # Load model
    model_info = load_model(args.model)
    print(f"Loaded model: version={model_info.get('version')}, sr={model_info.get('tgt_sr')}")

    # Convert
    start = time.time()
    info, (sr, audio) = convert_audio(
        audio_path=args.input,
        pitch_shift=args.pitch_shift,
        f0_method=args.f0_method,
    )
    elapsed = time.time() - start

    duration = len(audio) / sr
    print(f"Converted {duration:.2f}s of audio in {elapsed:.2f}s")

    sf.write(args.output, audio, sr)
    print(f"Saved to {args.output}")

if __name__ == "__main__":
    main()
