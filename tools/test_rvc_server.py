#!/usr/bin/env python3
"""
Test RVC Server Pipeline

Tests the full TTS + RVC pipeline with parallel processing.

Usage (with existing RVC server - fast):
    # First start RVC server separately:
    python tools/rvc_server_control.py start --model "SilverWolf_e300_s6600.pth" --workers 2

    # Then run pipeline (will use existing server):
    python tools/test_rvc_server.py \
        --triton-addr localhost \
        --triton-port 8001 \
        --prompt-audio "references/reference.wav"

Usage (start new RVC server - slower first run):
    python tools/test_rvc_server.py \
        --triton-addr localhost \
        --triton-port 8001 \
        --rvc-model "SilverWolf_e300_s6600.pth" \
        --prompt-audio "references/reference.wav" \
        --num-rvc-workers 2
"""

import os
import sys
import argparse
import logging

# Setup path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

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


def main():
    parser = argparse.ArgumentParser(
        description="Test RVC Server Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    # Triton settings
    parser.add_argument("--triton-addr", default="localhost", help="Triton server address")
    parser.add_argument("--triton-port", type=int, default=8001, help="Triton gRPC port")

    # RVC settings
    parser.add_argument("--rvc-model", default=None, help="RVC model name (optional if server already running)")
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

    # Import pipeline and server utilities
    from rvc.processing.pipeline import TTSRVCPipeline
    from rvc.server import get_rvc_server

    # Check for existing server
    existing_server = get_rvc_server()
    using_existing = existing_server is not None and existing_server.is_running

    logger.info("=" * 60)
    logger.info("RVC Server Pipeline Test")
    logger.info("=" * 60)
    logger.info(f"Triton: {args.triton_addr}:{args.triton_port}")
    if using_existing:
        logger.info(f"RVC Server: Using existing server (already running)")
    else:
        logger.info(f"RVC Model: {args.rvc_model or 'None (TTS-only mode)'}")
        logger.info(f"RVC Workers: {args.num_rvc_workers}")
    logger.info(f"Prompt Audio: {args.prompt_audio}")

    # Run pipeline
    with TTSRVCPipeline(
        triton_addr=args.triton_addr,
        triton_port=args.triton_port,
        rvc_model=args.rvc_model,
        num_rvc_workers=args.num_rvc_workers,
        pitch_shift=args.pitch_shift,
        f0_method=args.f0_method,
    ) as pipeline:

        results, stats = pipeline.process(
            text=text,
            prompt_audio=args.prompt_audio,
            prompt_text=args.prompt_text,
        )

    # Print results
    logger.info("\n" + "=" * 60)
    logger.info("RESULTS")
    logger.info("=" * 60)

    worker_stats = {}
    for result in results:
        status = "✓" if result.rvc_success else "✗"
        logger.info(f"{status} Fragment {result.fragment_id}:")
        logger.info(f"    Sentence: {result.sentence[:40]}...")
        if result.tts_path:
            logger.info(f"    TTS: {result.tts_path} ({result.tts_time:.2f}s)")
        if result.rvc_path:
            logger.info(f"    RVC: {result.rvc_path} ({result.rvc_time:.2f}s, worker {result.rvc_worker_id})")
            worker_stats[result.rvc_worker_id] = worker_stats.get(result.rvc_worker_id, 0) + 1
        if result.error:
            logger.info(f"    Error: {result.error}")

    logger.info("\n" + "=" * 60)
    logger.info("SUMMARY")
    logger.info("=" * 60)
    logger.info(f"Total sentences: {stats.total_sentences}")
    logger.info(f"TTS completed: {stats.tts_completed}")
    logger.info(f"TTS failed: {stats.tts_failed}")
    logger.info(f"RVC completed: {stats.rvc_completed}")
    logger.info(f"RVC failed: {stats.rvc_failed}")
    logger.info(f"Total pipeline time: {stats.total_time:.2f}s")
    logger.info(f"Average per sentence: {stats.avg_time_per_sentence:.2f}s")

    if worker_stats:
        logger.info(f"\nWorker distribution:")
        for worker_id, count in sorted(worker_stats.items()):
            logger.info(f"  Worker {worker_id}: {count} fragments")

    success = stats.rvc_completed == stats.tts_completed
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
