#!/usr/bin/env python3
"""
Test RVC Server with Multi-Process Workers

This script tests the full TTS + RVC pipeline using:
- Triton Spark TTS (gRPC client)
- RVC Server with multiple worker processes

Usage:
    python tools/test_rvc_server.py \
        --triton-addr localhost \
        --triton-port 8001 \
        --rvc-model "SilverWolf_e300_s6600.pth" \
        --prompt-audio "references/reference.wav" \
        --num-rvc-workers 2
"""

import os
import sys
import time
import argparse
import logging
import re
from concurrent.futures import ThreadPoolExecutor

# Setup path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import soundfile as sf

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("test_rvc_server")

# Default test text
DEFAULT_TEST_TEXT = """
Hello! This is the first sentence of our test. It should be processed by the TTS worker first.
The second sentence comes next, demonstrating the parallel processing capabilities.
Now we have a third sentence to add more work for the RVC workers.
Fourth sentence here, which will be queued for voice conversion.
The fifth sentence continues our comprehensive test of the pipeline.
Sentence number six is being processed through the system.
Here comes the seventh sentence for additional testing.
The eighth sentence adds more content to our test batch.
Ninth sentence in our sequence of test utterances.
And finally, the tenth sentence completes our test batch.
""".strip()


def split_into_sentences(text: str) -> list:
    """Split text into sentences."""
    sentences = re.split(r'(?<=[.!?])\s+', text)
    return [s.strip() for s in sentences if s.strip()]


def run_tts_inference(
    client,
    sentence: str,
    index: int,
    prompt_audio: str,
    prompt_text: str,
    output_dir: str,
) -> tuple:
    """Run TTS inference for a single sentence."""
    output_path = os.path.join(output_dir, f"tts_fragment_{index}.wav")

    try:
        wav = client.inference(
            text=sentence,
            prompt_speech=prompt_audio,
            prompt_text=prompt_text,
        )
        sf.write(output_path, wav, samplerate=16000)
        return index, output_path, None
    except Exception as e:
        return index, None, str(e)


def run_pipeline_test(
    triton_addr: str,
    triton_port: int,
    prompt_audio: str,
    prompt_text: str,
    rvc_model: str,
    num_rvc_workers: int,
    text: str,
    pitch_shift: int = 0,
    f0_method: str = "rmvpe",
):
    """Run the full TTS + RVC pipeline test."""
    from rvc.triton_client import TritonSparkClient
    from rvc.server import start_rvc_server, shutdown_rvc_server

    # Create output directories
    tts_dir = "./TEMP/spark"
    rvc_dir = "./TEMP/rvc"
    os.makedirs(tts_dir, exist_ok=True)
    os.makedirs(rvc_dir, exist_ok=True)

    # Split text into sentences
    sentences = split_into_sentences(text)
    num_sentences = len(sentences)
    logger.info(f"Processing {num_sentences} sentences")

    # Initialize Triton client
    logger.info(f"Connecting to Triton at {triton_addr}:{triton_port}")
    tts_client = TritonSparkClient(server_addr=triton_addr, server_port=triton_port)

    if not tts_client.is_server_ready():
        logger.error("Triton server not ready!")
        return False

    # Start RVC server
    logger.info(f"Starting RVC server with {num_rvc_workers} workers...")
    try:
        rvc_server = start_rvc_server(
            model_name=rvc_model,
            num_workers=num_rvc_workers,
            timeout=120.0,
        )
    except Exception as e:
        logger.error(f"Failed to start RVC server: {e}")
        return False

    logger.info("RVC server ready!")

    # =========================================================================
    # Phase 1: TTS Processing
    # =========================================================================
    logger.info("\n" + "=" * 60)
    logger.info("PHASE 1: TTS Processing")
    logger.info("=" * 60)

    tts_start = time.time()
    tts_results = []

    # Process TTS sequentially (Triton handles batching internally)
    for i, sentence in enumerate(sentences):
        logger.info(f"TTS [{i+1}/{num_sentences}]: {sentence[:40]}...")

        try:
            wav = tts_client.inference(
                text=sentence,
                prompt_speech=prompt_audio,
                prompt_text=prompt_text,
            )
            output_path = os.path.join(tts_dir, f"fragment_{i}.wav")
            sf.write(output_path, wav, samplerate=16000)
            tts_results.append((i, output_path, None))
            logger.info(f"  Saved: {output_path}")
        except Exception as e:
            logger.error(f"  Error: {e}")
            tts_results.append((i, None, str(e)))

    tts_elapsed = time.time() - tts_start
    logger.info(f"TTS completed in {tts_elapsed:.2f}s")

    # =========================================================================
    # Phase 2: RVC Processing (Parallel)
    # =========================================================================
    logger.info("\n" + "=" * 60)
    logger.info("PHASE 2: RVC Processing (Parallel)")
    logger.info("=" * 60)

    rvc_start = time.time()

    # Submit all RVC jobs
    job_ids = []
    for i, tts_path, error in tts_results:
        if tts_path and os.path.exists(tts_path):
            rvc_output = os.path.join(rvc_dir, f"fragment_{i}.wav")
            job_id = rvc_server.submit_job(
                input_audio_path=tts_path,
                output_audio_path=rvc_output,
                pitch_shift=pitch_shift,
                f0_method=f0_method,
            )
            job_ids.append((i, job_id))
            logger.info(f"Submitted RVC job {job_id} for fragment {i}")

    logger.info(f"Submitted {len(job_ids)} RVC jobs, waiting for results...")

    # Collect results
    rvc_results = rvc_server.get_all_results(
        expected_count=len(job_ids),
        timeout=300.0,
    )

    rvc_elapsed = time.time() - rvc_start

    # =========================================================================
    # Results Summary
    # =========================================================================
    logger.info("\n" + "=" * 60)
    logger.info("RESULTS")
    logger.info("=" * 60)

    # Sort results by job_id
    rvc_results.sort(key=lambda r: r.job_id)

    successful = 0
    failed = 0
    worker_stats = {}

    for result in rvc_results:
        status = "✓" if result.success else "✗"
        logger.info(f"{status} Fragment {result.job_id}:")
        logger.info(f"    Worker: {result.worker_id}")
        logger.info(f"    Time: {result.processing_time:.2f}s")

        if result.success:
            logger.info(f"    Output: {result.output_path}")
            successful += 1
            worker_stats[result.worker_id] = worker_stats.get(result.worker_id, 0) + 1
        else:
            logger.info(f"    Error: {result.error}")
            failed += 1

    total_elapsed = tts_elapsed + rvc_elapsed

    logger.info("\n" + "=" * 60)
    logger.info("SUMMARY")
    logger.info("=" * 60)
    logger.info(f"Total sentences: {num_sentences}")
    logger.info(f"Successful: {successful}")
    logger.info(f"Failed: {failed}")
    logger.info(f"TTS time: {tts_elapsed:.2f}s")
    logger.info(f"RVC time: {rvc_elapsed:.2f}s")
    logger.info(f"Total time: {total_elapsed:.2f}s")
    logger.info(f"Average per sentence: {total_elapsed / num_sentences:.2f}s")

    logger.info(f"\nWorker distribution:")
    for worker_id, count in sorted(worker_stats.items()):
        logger.info(f"  Worker {worker_id}: {count} fragments")

    # Cleanup
    logger.info("\nShutting down RVC server...")
    shutdown_rvc_server()
    tts_client.close()

    return successful == len(job_ids)


def main():
    parser = argparse.ArgumentParser(
        description="Test RVC Server with parallel workers",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    # Triton settings
    parser.add_argument("--triton-addr", default="localhost", help="Triton server address")
    parser.add_argument("--triton-port", type=int, default=8001, help="Triton gRPC port")

    # RVC settings
    parser.add_argument("--rvc-model", required=True, help="RVC model name")
    parser.add_argument("--num-rvc-workers", type=int, default=2, help="Number of RVC workers")
    parser.add_argument("--pitch-shift", type=int, default=0, help="Pitch shift in semitones")
    parser.add_argument("--f0-method", default="rmvpe", help="F0 method")

    # Input settings
    parser.add_argument("--prompt-audio", required=True, help="Reference audio for TTS")
    parser.add_argument("--prompt-text", default="", help="Reference text (optional)")
    parser.add_argument("--text", default=DEFAULT_TEST_TEXT, help="Text to synthesize")
    parser.add_argument("--text-file", help="File containing text to synthesize")

    args = parser.parse_args()

    # Load text from file if provided
    text = args.text
    if args.text_file:
        with open(args.text_file, "r", encoding="utf-8") as f:
            text = f.read()

    logger.info("=" * 60)
    logger.info("RVC Server Pipeline Test")
    logger.info("=" * 60)
    logger.info(f"Triton: {args.triton_addr}:{args.triton_port}")
    logger.info(f"RVC Model: {args.rvc_model}")
    logger.info(f"RVC Workers: {args.num_rvc_workers}")
    logger.info(f"Prompt Audio: {args.prompt_audio}")

    success = run_pipeline_test(
        triton_addr=args.triton_addr,
        triton_port=args.triton_port,
        prompt_audio=args.prompt_audio,
        prompt_text=args.prompt_text,
        rvc_model=args.rvc_model,
        num_rvc_workers=args.num_rvc_workers,
        text=text,
        pitch_shift=args.pitch_shift,
        f0_method=args.f0_method,
    )

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
