"""
RVC Inference Server with Multi-Process Workers

Architecture:
- Main server process manages worker pool
- Each worker is a separate process with its own RVC model in GPU memory
- Jobs distributed via multiprocessing Queue
- Results returned via result Queue

This achieves true parallelism by bypassing Python's GIL.
"""

import os
import sys
import time
import signal
import logging
import tempfile
from multiprocessing import Process, Queue, Event, Value
from ctypes import c_int
from queue import Empty
from typing import Optional, Tuple, Dict, Any
import json

# Setup path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import soundfile as sf

logger = logging.getLogger(__name__)


class RVCJob:
    """Represents an RVC inference job."""

    def __init__(
        self,
        job_id: int,
        input_audio_path: str,
        output_audio_path: str,
        pitch_shift: int = 0,
        f0_method: str = "rmvpe",
        index_rate: float = 0.75,
        filter_radius: int = 3,
        resample_sr: int = 0,
        rms_mix_rate: float = 0.25,
        protect: float = 0.33,
    ):
        self.job_id = job_id
        self.input_audio_path = input_audio_path
        self.output_audio_path = output_audio_path
        self.pitch_shift = pitch_shift
        self.f0_method = f0_method
        self.index_rate = index_rate
        self.filter_radius = filter_radius
        self.resample_sr = resample_sr
        self.rms_mix_rate = rms_mix_rate
        self.protect = protect

    def to_dict(self) -> dict:
        return {
            "job_id": self.job_id,
            "input_audio_path": self.input_audio_path,
            "output_audio_path": self.output_audio_path,
            "pitch_shift": self.pitch_shift,
            "f0_method": self.f0_method,
            "index_rate": self.index_rate,
            "filter_radius": self.filter_radius,
            "resample_sr": self.resample_sr,
            "rms_mix_rate": self.rms_mix_rate,
            "protect": self.protect,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "RVCJob":
        return cls(**data)


class RVCResult:
    """Result of an RVC inference job."""

    def __init__(
        self,
        job_id: int,
        success: bool,
        output_path: Optional[str] = None,
        error: Optional[str] = None,
        worker_id: int = -1,
        processing_time: float = 0.0,
    ):
        self.job_id = job_id
        self.success = success
        self.output_path = output_path
        self.error = error
        self.worker_id = worker_id
        self.processing_time = processing_time

    def to_dict(self) -> dict:
        return {
            "job_id": self.job_id,
            "success": self.success,
            "output_path": self.output_path,
            "error": self.error,
            "worker_id": self.worker_id,
            "processing_time": self.processing_time,
        }


def rvc_worker_process(
    worker_id: int,
    model_name: str,
    job_queue: Queue,
    result_queue: Queue,
    shutdown_event: Event,
    ready_event: Event,
):
    """
    Worker process that loads RVC model and processes jobs.

    Each worker has its own copy of the model in GPU memory.
    This allows true parallel processing across workers.
    """
    # Setup logging for this worker
    logging.basicConfig(
        level=logging.INFO,
        format=f"%(asctime)s [Worker {worker_id}] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    worker_logger = logging.getLogger(f"rvc_worker_{worker_id}")

    worker_logger.info(f"Starting RVC worker {worker_id}")

    try:
        # Import RVC modules (each process gets fresh imports)
        from rvc import init_rvc, load_model, get_vc

        # Initialize RVC
        worker_logger.info("Initializing RVC...")
        init_rvc()

        # Load the model
        worker_logger.info(f"Loading model: {model_name}")
        model_info = load_model(model_name)
        worker_logger.info(f"Model loaded: version={model_info.get('version')}, sr={model_info.get('tgt_sr')}")

        # Get VC instance
        vc = get_vc()

        # Signal that we're ready
        ready_event.set()
        worker_logger.info("Worker ready, waiting for jobs...")

        # Process jobs
        while not shutdown_event.is_set():
            try:
                # Get job with timeout
                job_data = job_queue.get(timeout=0.5)

                if job_data is None:
                    # Shutdown signal
                    worker_logger.info("Received shutdown signal")
                    break

                job = RVCJob.from_dict(job_data)
                worker_logger.info(f"Processing job {job.job_id}: {job.input_audio_path}")

                start_time = time.time()

                try:
                    # Run RVC inference
                    output_info, output_audio = vc.vc_single(
                        sid=0,
                        input_audio_path=job.input_audio_path,
                        f0_up_key=job.pitch_shift,
                        f0_file=None,
                        f0_method=job.f0_method,
                        file_index="",
                        file_index2="",
                        index_rate=job.index_rate,
                        filter_radius=job.filter_radius,
                        resample_sr=job.resample_sr,
                        rms_mix_rate=job.rms_mix_rate,
                        protect=job.protect,
                    )

                    # Save output
                    if isinstance(output_audio, tuple) and len(output_audio) >= 2:
                        sf.write(job.output_audio_path, output_audio[1], output_audio[0])

                    processing_time = time.time() - start_time
                    worker_logger.info(f"Job {job.job_id} completed in {processing_time:.2f}s")

                    result = RVCResult(
                        job_id=job.job_id,
                        success=True,
                        output_path=job.output_audio_path,
                        worker_id=worker_id,
                        processing_time=processing_time,
                    )

                except Exception as e:
                    processing_time = time.time() - start_time
                    worker_logger.error(f"Job {job.job_id} failed: {e}")
                    result = RVCResult(
                        job_id=job.job_id,
                        success=False,
                        error=str(e),
                        worker_id=worker_id,
                        processing_time=processing_time,
                    )

                result_queue.put(result.to_dict())

            except Empty:
                continue
            except Exception as e:
                worker_logger.error(f"Unexpected error: {e}")
                continue

        worker_logger.info("Worker shutting down")

    except Exception as e:
        worker_logger.error(f"Worker initialization failed: {e}")
        ready_event.set()  # Signal ready (with failure)

    finally:
        # Cleanup
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except:
            pass


class RVCServer:
    """
    RVC Inference Server with multiple worker processes.

    Usage:
        server = RVCServer(model_name="SilverWolf.pth", num_workers=2)
        server.start()

        # Submit jobs
        job_id = server.submit_job(input_path, output_path, pitch_shift=0)

        # Get result
        result = server.get_result(timeout=30)

        server.shutdown()
    """

    def __init__(
        self,
        model_name: str,
        num_workers: int = 2,
    ):
        self.model_name = model_name
        self.num_workers = num_workers

        self.workers = []
        self.job_queue = Queue()
        self.result_queue = Queue()
        self.shutdown_event = Event()
        self.ready_events = []

        self.job_counter = Value(c_int, 0)
        self.is_running = False

        logger.info(f"RVCServer initialized: model={model_name}, workers={num_workers}")

    def start(self, timeout: float = 120.0) -> bool:
        """
        Start the server and all worker processes.

        Args:
            timeout: Maximum time to wait for workers to be ready.

        Returns:
            True if all workers started successfully.
        """
        if self.is_running:
            logger.warning("Server already running")
            return True

        logger.info(f"Starting {self.num_workers} RVC workers...")

        # Create and start worker processes
        for i in range(self.num_workers):
            ready_event = Event()
            self.ready_events.append(ready_event)

            worker = Process(
                target=rvc_worker_process,
                args=(
                    i,
                    self.model_name,
                    self.job_queue,
                    self.result_queue,
                    self.shutdown_event,
                    ready_event,
                ),
                daemon=True,
            )
            worker.start()
            self.workers.append(worker)
            logger.info(f"Started worker process {i} (pid={worker.pid})")

        # Wait for all workers to be ready
        logger.info("Waiting for workers to initialize...")
        start_time = time.time()

        for i, ready_event in enumerate(self.ready_events):
            remaining_timeout = timeout - (time.time() - start_time)
            if remaining_timeout <= 0:
                logger.error("Timeout waiting for workers")
                self.shutdown()
                return False

            if not ready_event.wait(timeout=remaining_timeout):
                logger.error(f"Worker {i} failed to start")
                self.shutdown()
                return False

        self.is_running = True
        logger.info(f"All {self.num_workers} workers ready!")
        return True

    def submit_job(
        self,
        input_audio_path: str,
        output_audio_path: str,
        pitch_shift: int = 0,
        f0_method: str = "rmvpe",
        index_rate: float = 0.75,
        filter_radius: int = 3,
        resample_sr: int = 0,
        rms_mix_rate: float = 0.25,
        protect: float = 0.33,
    ) -> int:
        """
        Submit a job for RVC processing.

        Returns:
            Job ID for tracking.
        """
        if not self.is_running:
            raise RuntimeError("Server not running")

        with self.job_counter.get_lock():
            job_id = self.job_counter.value
            self.job_counter.value += 1

        job = RVCJob(
            job_id=job_id,
            input_audio_path=input_audio_path,
            output_audio_path=output_audio_path,
            pitch_shift=pitch_shift,
            f0_method=f0_method,
            index_rate=index_rate,
            filter_radius=filter_radius,
            resample_sr=resample_sr,
            rms_mix_rate=rms_mix_rate,
            protect=protect,
        )

        self.job_queue.put(job.to_dict())
        logger.debug(f"Submitted job {job_id}")
        return job_id

    def get_result(self, timeout: float = 30.0) -> Optional[RVCResult]:
        """
        Get the next available result.

        Args:
            timeout: Maximum time to wait for a result.

        Returns:
            RVCResult or None if timeout.
        """
        try:
            result_data = self.result_queue.get(timeout=timeout)
            return RVCResult(
                job_id=result_data["job_id"],
                success=result_data["success"],
                output_path=result_data.get("output_path"),
                error=result_data.get("error"),
                worker_id=result_data.get("worker_id", -1),
                processing_time=result_data.get("processing_time", 0.0),
            )
        except Empty:
            return None

    def get_all_results(self, expected_count: int, timeout: float = 300.0) -> list:
        """
        Get all results for a batch of jobs.

        Args:
            expected_count: Number of results to collect.
            timeout: Maximum total time to wait.

        Returns:
            List of RVCResult objects.
        """
        results = []
        start_time = time.time()

        while len(results) < expected_count:
            remaining = timeout - (time.time() - start_time)
            if remaining <= 0:
                logger.warning(f"Timeout: got {len(results)}/{expected_count} results")
                break

            result = self.get_result(timeout=min(remaining, 1.0))
            if result:
                results.append(result)

        return results

    def get_status(self) -> dict:
        """Get server status."""
        return {
            "running": self.is_running,
            "model": self.model_name,
            "num_workers": self.num_workers,
            "workers_alive": sum(1 for w in self.workers if w.is_alive()),
            "jobs_submitted": self.job_counter.value,
            "pending_results": self.result_queue.qsize(),
        }

    def shutdown(self, timeout: float = 10.0):
        """Shutdown the server and all workers."""
        if not self.is_running and not self.workers:
            return

        logger.info("Shutting down RVC server...")

        # Signal shutdown
        self.shutdown_event.set()

        # Send shutdown signals to job queue
        for _ in range(self.num_workers):
            try:
                self.job_queue.put(None, timeout=1.0)
            except:
                pass

        # Wait for workers to finish
        for i, worker in enumerate(self.workers):
            worker.join(timeout=timeout / self.num_workers)
            if worker.is_alive():
                logger.warning(f"Worker {i} didn't terminate, killing...")
                worker.terminate()
                worker.join(timeout=1.0)

        self.workers = []
        self.ready_events = []
        self.is_running = False

        logger.info("RVC server shutdown complete")


# Global server instance
_server: Optional[RVCServer] = None


def get_rvc_server() -> Optional[RVCServer]:
    """Get the global RVC server instance."""
    return _server


def start_rvc_server(
    model_name: str,
    num_workers: int = 2,
    timeout: float = 120.0,
) -> RVCServer:
    """
    Start the global RVC server.

    Args:
        model_name: RVC model file name.
        num_workers: Number of worker processes.
        timeout: Timeout for worker initialization.

    Returns:
        RVCServer instance.
    """
    global _server

    if _server is not None:
        if _server.is_running:
            logger.warning("Server already running, returning existing instance")
            return _server
        else:
            _server.shutdown()

    _server = RVCServer(model_name=model_name, num_workers=num_workers)

    if not _server.start(timeout=timeout):
        raise RuntimeError("Failed to start RVC server")

    return _server


def shutdown_rvc_server():
    """Shutdown the global RVC server."""
    global _server

    if _server is not None:
        _server.shutdown()
        _server = None


def get_rvc_server_status() -> dict:
    """Get status of the global RVC server."""
    global _server

    if _server is None:
        return {"running": False, "error": "No server initialized"}

    return _server.get_status()
