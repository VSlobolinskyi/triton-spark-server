#!/usr/bin/env python3
"""
Test Persistent Workers for Triton Spark TTS + RVC Pipeline

Tests the full pipeline with persistent TTS and RVC workers:
- 1 TTS worker (connects to Triton via gRPC)
- N RVC workers (parallel processing with CUDA streams)

Usage:
    python tools/test_persistent_workers.py \
        --triton-addr localhost \
        --triton-port 8001 \
        --rvc-model "SilverWolf_e300_s6600.pth" \
        --prompt-audio "references/reference.wav" \
        --num-rvc-workers 2

    # With custom text file:
    python tools/test_persistent_workers.py \
        --text-file "path/to/text.txt" \
        --num-rvc-workers 2
"""

import os
import sys
import time
import argparse
import logging
import threading
from queue import Queue, PriorityQueue
from multiprocessing import Value
from ctypes import c_int

import torch

# Setup path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("test_workers")

# Default large text for testing
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
    import re
    sentences = re.split(r'(?<=[.!?])\s+', text)
    return [s.strip() for s in sentences if s.strip()]


def run_persistent_workers_test(
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
    """
    Run the persistent workers test.

    Args:
        triton_addr: Triton server address
        triton_port: Triton gRPC port
        prompt_audio: Path to reference audio
        prompt_text: Reference text (optional)
        rvc_model: RVC model name
        num_rvc_workers: Number of RVC workers to spawn
        text: Text to synthesize
        pitch_shift: Pitch shift in semitones
        f0_method: F0 extraction method
    """
    from rvc.processing.worker_manager import get_worker_manager
    from rvc.rvc_init import init_rvc, load_model, get_vc

    # Clean up temp directories
    os.makedirs("./TEMP/spark", exist_ok=True)
    os.makedirs("./TEMP/rvc", exist_ok=True)

    # Initialize RVC
    logger.info("Initializing RVC...")
    init_rvc()

    # Load RVC model
    logger.info(f"Loading RVC model: {rvc_model}")
    model_info = load_model(rvc_model)
    logger.info(f"  Model version: {model_info.get('version', 'unknown')}")
    logger.info(f"  Target SR: {model_info.get('tgt_sr', 'unknown')}")

    # Get VC instance for parameters
    vc = get_vc()

    # Get worker manager
    logger.info(f"Getting worker manager (Triton: {triton_addr}:{triton_port})")
    manager = get_worker_manager(
        unload_delay=0,  # 0 = persist forever (like Spark TTS)
        triton_addr=triton_addr,
        triton_port=triton_port,
    )

    # Split text into sentences
    sentences = split_into_sentences(text)
    num_sentences = len(sentences)
    logger.info(f"Processing {num_sentences} sentences with {num_rvc_workers} RVC workers")

    # Create shared queues and events
    queue_lock = threading.Lock()
    sentence_queue = PriorityQueue()
    tts_to_rvc_queue = Queue()
    rvc_results_queue = Queue()

    # Add sentences to priority queue (priority = index for order)
    for i, sentence in enumerate(sentences):
        sentence_queue.put((i, i, sentence))

    processed_count = Value(c_int, 0)

    # Create completion events
    tts_complete_events = [threading.Event()]  # 1 TTS worker
    rvc_complete_events = [threading.Event() for _ in range(num_rvc_workers)]
    processing_complete = threading.Event()

    # Create CUDA streams for RVC workers
    cuda_streams = []
    if torch.cuda.is_available():
        for i in range(num_rvc_workers):
            stream = torch.cuda.Stream()
            cuda_streams.append(stream)
            logger.info(f"Created CUDA stream for RVC worker {i}")
    else:
        cuda_streams = [None] * num_rvc_workers
        logger.warning("CUDA not available, RVC workers will run sequentially")

    # Get TTS worker
    logger.info("Starting TTS worker...")
    tts_queue = manager.get_tts_worker(0)

    # Get RVC workers
    logger.info(f"Starting {num_rvc_workers} RVC workers...")
    rvc_queues = []
    for i in range(num_rvc_workers):
        rvc_queue = manager.get_rvc_worker(i, cuda_streams[i])
        rvc_queues.append(rvc_queue)

    # Prepare TTS job
    tts_job = (
        queue_lock,
        sentence_queue,
        num_sentences,
        processed_count,
        0,  # base_fragment_num
        prompt_audio,
        prompt_text,
        tts_to_rvc_queue,
        tts_complete_events,
        num_rvc_workers,
    )

    # Prepare RVC job parameters
    rvc_job_base = (
        tts_to_rvc_queue,
        rvc_results_queue,
        rvc_complete_events,
        tts_complete_events,
        0,  # spk_item (speaker index)
        pitch_shift,  # vc_transform
        f0_method,
        "",  # file_index1
        "",  # file_index2
        0.75,  # index_rate
        3,  # filter_radius
        0,  # resample_sr (0 = use model's target SR)
        0.25,  # rms_mix_rate
        0.33,  # protect
        processing_complete,
    )

    # Submit jobs
    start_time = time.time()

    logger.info("Submitting TTS job...")
    tts_queue.put(tts_job)

    logger.info("Submitting RVC jobs...")
    for i, rvc_queue in enumerate(rvc_queues):
        rvc_queue.put(rvc_job_base)

    # Wait for processing to complete
    logger.info("Waiting for processing to complete...")
    processing_complete.wait(timeout=300)  # 5 minute timeout

    elapsed = time.time() - start_time

    # Collect results
    results = []
    while not rvc_results_queue.empty():
        results.append(rvc_results_queue.get())

    # Sort by index
    results.sort(key=lambda x: x[0])

    # Print results
    logger.info("\n" + "=" * 60)
    logger.info("RESULTS")
    logger.info("=" * 60)

    successful = 0
    failed = 0
    for idx, tts_path, rvc_path, success, info in results:
        status = "✓" if success else "✗"
        logger.info(f"{status} Sentence {idx + 1}:")
        if tts_path:
            logger.info(f"    TTS: {tts_path}")
        if rvc_path:
            logger.info(f"    RVC: {rvc_path}")
        if not success:
            logger.info(f"    Error: {info}")
        if success:
            successful += 1
        else:
            failed += 1

    logger.info("\n" + "=" * 60)
    logger.info("SUMMARY")
    logger.info("=" * 60)
    logger.info(f"Total sentences: {num_sentences}")
    logger.info(f"Successful: {successful}")
    logger.info(f"Failed: {failed}")
    logger.info(f"Total time: {elapsed:.2f}s")
    logger.info(f"Average time per sentence: {elapsed / num_sentences:.2f}s")
    logger.info(f"RVC workers used: {num_rvc_workers}")

    return successful == num_sentences


def main():
    parser = argparse.ArgumentParser(
        description="Test persistent TTS and RVC workers",
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
    logger.info("Persistent Workers Test")
    logger.info("=" * 60)
    logger.info(f"Triton: {args.triton_addr}:{args.triton_port}")
    logger.info(f"RVC Model: {args.rvc_model}")
    logger.info(f"RVC Workers: {args.num_rvc_workers}")
    logger.info(f"Prompt Audio: {args.prompt_audio}")

    success = run_persistent_workers_test(
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
