"""
TTS + RVC Pipeline Processor

Handles parallel processing of TTS and RVC:
- TTS producer thread processes sentences sequentially
- RVC submitter thread forwards results to RVC server immediately
- RVC server workers process in parallel

Usage:
    from rvc.processing.pipeline import TTSRVCPipeline

    pipeline = TTSRVCPipeline(
        triton_addr="localhost",
        triton_port=8001,
        rvc_model="SilverWolf.pth",
        num_rvc_workers=2,
    )

    results = pipeline.process(
        text="Hello world. This is a test.",
        prompt_audio="reference.wav",
    )

    pipeline.shutdown()
"""

import os
import re
import time
import logging
import threading
from queue import Queue, Empty
from dataclasses import dataclass
from typing import Optional, List

import soundfile as sf

from rvc.triton_client import TritonSparkClient
from rvc.server import RVCServer, start_rvc_server, shutdown_rvc_server, get_rvc_server

logger = logging.getLogger(__name__)


@dataclass
class PipelineResult:
    """Result of processing a single fragment."""
    fragment_id: int
    sentence: str
    tts_path: Optional[str] = None
    rvc_path: Optional[str] = None
    tts_success: bool = False
    rvc_success: bool = False
    tts_time: float = 0.0
    rvc_time: float = 0.0
    rvc_worker_id: int = -1
    error: Optional[str] = None


@dataclass
class PipelineStats:
    """Overall pipeline statistics."""
    total_sentences: int = 0
    tts_completed: int = 0
    tts_failed: int = 0
    rvc_completed: int = 0
    rvc_failed: int = 0
    total_time: float = 0.0

    @property
    def avg_time_per_sentence(self) -> float:
        if self.total_sentences == 0:
            return 0.0
        return self.total_time / self.total_sentences


def split_into_sentences(text: str) -> List[str]:
    """Split text into sentences."""
    sentences = re.split(r'(?<=[.!?])\s+', text)
    return [s.strip() for s in sentences if s.strip()]


class TTSRVCPipeline:
    """
    Parallel TTS + RVC processing pipeline.

    TTS and RVC run concurrently - as soon as TTS finishes a sentence,
    it's immediately submitted to RVC for processing.
    """

    def __init__(
        self,
        triton_addr: str = "localhost",
        triton_port: int = 8001,
        rvc_model: str = None,
        num_rvc_workers: int = 2,
        pitch_shift: int = 0,
        f0_method: str = "rmvpe",
        tts_output_dir: str = "./TEMP/spark",
        rvc_output_dir: str = "./TEMP/rvc",
    ):
        """
        Initialize the pipeline.

        Args:
            triton_addr: Triton server address for TTS.
            triton_port: Triton gRPC port.
            rvc_model: RVC model filename.
            num_rvc_workers: Number of RVC worker processes.
            pitch_shift: Pitch shift in semitones.
            f0_method: F0 extraction method.
            tts_output_dir: Directory for TTS output files.
            rvc_output_dir: Directory for RVC output files.
        """
        self.triton_addr = triton_addr
        self.triton_port = triton_port
        self.rvc_model = rvc_model
        self.num_rvc_workers = num_rvc_workers
        self.pitch_shift = pitch_shift
        self.f0_method = f0_method
        self.tts_output_dir = tts_output_dir
        self.rvc_output_dir = rvc_output_dir

        self.tts_client: Optional[TritonSparkClient] = None
        self.rvc_server: Optional[RVCServer] = None
        self._initialized = False

    def initialize(self, timeout: float = 120.0) -> bool:
        """
        Initialize TTS client and RVC server.

        Args:
            timeout: Timeout for RVC server initialization.

        Returns:
            True if initialization successful.
        """
        if self._initialized:
            return True

        # Create output directories
        os.makedirs(self.tts_output_dir, exist_ok=True)
        os.makedirs(self.rvc_output_dir, exist_ok=True)

        # Initialize TTS client
        logger.info(f"Connecting to Triton at {self.triton_addr}:{self.triton_port}")
        self.tts_client = TritonSparkClient(
            server_addr=self.triton_addr,
            server_port=self.triton_port,
        )

        if not self.tts_client.is_server_ready():
            logger.error("Triton server not ready!")
            return False

        # Initialize RVC server
        if self.rvc_model:
            logger.info(f"Starting RVC server with {self.num_rvc_workers} workers...")
            try:
                self.rvc_server = start_rvc_server(
                    model_name=self.rvc_model,
                    num_workers=self.num_rvc_workers,
                    timeout=timeout,
                )
            except Exception as e:
                logger.error(f"Failed to start RVC server: {e}")
                return False

            logger.info("RVC server ready!")

        self._initialized = True
        return True

    def _tts_producer(
        self,
        sentences: List[str],
        prompt_audio: str,
        prompt_text: str,
        tts_to_rvc_queue: Queue,
        tts_complete_event: threading.Event,
        results: List[PipelineResult],
    ):
        """TTS producer thread - processes sentences and queues for RVC."""
        num_sentences = len(sentences)

        for i, sentence in enumerate(sentences):
            result = results[i]
            result.sentence = sentence

            logger.info(f"TTS [{i+1}/{num_sentences}]: {sentence[:40]}...")

            try:
                start_time = time.time()
                wav = self.tts_client.inference(
                    text=sentence,
                    prompt_speech=prompt_audio,
                    prompt_text=prompt_text,
                )
                output_path = os.path.join(self.tts_output_dir, f"fragment_{i}.wav")
                sf.write(output_path, wav, samplerate=16000)
                elapsed = time.time() - start_time

                result.tts_path = output_path
                result.tts_success = True
                result.tts_time = elapsed

                logger.info(f"  TTS done: {output_path} ({elapsed:.2f}s) -> queued for RVC")

                # Queue for RVC processing
                tts_to_rvc_queue.put((i, output_path, None))

            except Exception as e:
                logger.error(f"  TTS Error: {e}")
                result.tts_success = False
                result.error = str(e)
                tts_to_rvc_queue.put((i, None, str(e)))

        tts_complete_event.set()
        logger.info("TTS producer finished")

    def _rvc_submitter(
        self,
        tts_to_rvc_queue: Queue,
        tts_complete_event: threading.Event,
        submitted_count: List[int],  # Use list for mutable reference
    ):
        """RVC submitter thread - forwards TTS results to RVC server."""
        while True:
            try:
                item = tts_to_rvc_queue.get(timeout=0.5)
                i, tts_path, error = item

                if error:
                    logger.warning(f"  Skipping fragment {i} due to TTS error")
                    continue

                if tts_path and os.path.exists(tts_path):
                    rvc_output = os.path.join(self.rvc_output_dir, f"fragment_{i}.wav")
                    job_id = self.rvc_server.submit_job(
                        input_audio_path=tts_path,
                        output_audio_path=rvc_output,
                        pitch_shift=self.pitch_shift,
                        f0_method=self.f0_method,
                    )
                    submitted_count[0] += 1
                    logger.info(f"  RVC job {job_id} submitted for fragment {i}")

            except Empty:
                if tts_complete_event.is_set() and tts_to_rvc_queue.empty():
                    break
                continue

        logger.info("RVC submitter finished")

    def process(
        self,
        text: str,
        prompt_audio: str,
        prompt_text: str = "",
        timeout: float = 300.0,
    ) -> tuple:
        """
        Process text through the TTS + RVC pipeline.

        Args:
            text: Text to synthesize.
            prompt_audio: Reference audio path for TTS.
            prompt_text: Reference text (optional).
            timeout: Maximum time to wait for results.

        Returns:
            Tuple of (results: List[PipelineResult], stats: PipelineStats)
        """
        if not self._initialized:
            if not self.initialize():
                raise RuntimeError("Pipeline initialization failed")

        sentences = split_into_sentences(text)
        num_sentences = len(sentences)

        logger.info(f"Processing {num_sentences} sentences")

        # Initialize results
        results = [PipelineResult(fragment_id=i, sentence="") for i in range(num_sentences)]
        stats = PipelineStats(total_sentences=num_sentences)

        pipeline_start = time.time()

        # TTS-only mode (no RVC)
        if self.rvc_server is None:
            for i, sentence in enumerate(sentences):
                results[i].sentence = sentence
                logger.info(f"TTS [{i+1}/{num_sentences}]: {sentence[:40]}...")

                try:
                    start_time = time.time()
                    wav = self.tts_client.inference(
                        text=sentence,
                        prompt_speech=prompt_audio,
                        prompt_text=prompt_text,
                    )
                    output_path = os.path.join(self.tts_output_dir, f"fragment_{i}.wav")
                    sf.write(output_path, wav, samplerate=16000)

                    results[i].tts_path = output_path
                    results[i].tts_success = True
                    results[i].tts_time = time.time() - start_time
                    stats.tts_completed += 1

                except Exception as e:
                    results[i].error = str(e)
                    stats.tts_failed += 1

            stats.total_time = time.time() - pipeline_start
            return results, stats

        # Full TTS + RVC pipeline
        tts_to_rvc_queue = Queue()
        tts_complete_event = threading.Event()
        submitted_count = [0]

        # Start TTS producer
        tts_thread = threading.Thread(
            target=self._tts_producer,
            args=(sentences, prompt_audio, prompt_text, tts_to_rvc_queue, tts_complete_event, results),
        )
        tts_thread.start()

        # Start RVC submitter
        rvc_thread = threading.Thread(
            target=self._rvc_submitter,
            args=(tts_to_rvc_queue, tts_complete_event, submitted_count),
        )
        rvc_thread.start()

        # Wait for threads to complete
        tts_thread.join()
        rvc_thread.join()

        logger.info(f"All {submitted_count[0]} RVC jobs submitted, waiting for results...")

        # Collect RVC results
        rvc_results = self.rvc_server.get_all_results(
            expected_count=submitted_count[0],
            timeout=timeout,
        )

        # Map RVC results back to pipeline results
        for rvc_result in rvc_results:
            idx = rvc_result.job_id
            if 0 <= idx < len(results):
                results[idx].rvc_success = rvc_result.success
                results[idx].rvc_path = rvc_result.output_path
                results[idx].rvc_time = rvc_result.processing_time
                results[idx].rvc_worker_id = rvc_result.worker_id
                if not rvc_result.success and rvc_result.error:
                    results[idx].error = rvc_result.error

        # Calculate stats
        for r in results:
            if r.tts_success:
                stats.tts_completed += 1
            else:
                stats.tts_failed += 1
            if r.rvc_success:
                stats.rvc_completed += 1
            elif r.tts_success:  # Only count as RVC failed if TTS succeeded
                stats.rvc_failed += 1

        stats.total_time = time.time() - pipeline_start

        return results, stats

    def shutdown(self):
        """Shutdown the pipeline and release resources."""
        if self.tts_client:
            self.tts_client.close()
            self.tts_client = None

        if self.rvc_server:
            shutdown_rvc_server()
            self.rvc_server = None

        self._initialized = False
        logger.info("Pipeline shutdown complete")

    def __enter__(self):
        self.initialize()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.shutdown()
        return False
