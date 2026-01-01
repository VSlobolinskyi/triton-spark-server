"""
Worker Manager for Triton Spark TTS + RVC Pipeline

Manages persistent TTS and RVC workers with configurable unload delay.
Adapted for Triton architecture:
- TTS workers connect via gRPC (no local model loading)
- RVC workers use CUDA streams for parallel inference
"""

import threading
import time
import logging
import os
from queue import Queue

from rvc.processing.workers import persistent_rvc_worker, persistent_tts_worker

logger = logging.getLogger(__name__)

# Get model delay from environment variable or use default
DEFAULT_MODEL_DELAY = int(os.environ.get("MODEL_UNLOAD_DELAY", 30))

# Triton server configuration
DEFAULT_TRITON_ADDR = os.environ.get("TRITON_SERVER_ADDR", "localhost")
DEFAULT_TRITON_PORT = int(os.environ.get("TRITON_SERVER_PORT", 8001))


class WorkerManager:
    """
    Manages persistent TTS and RVC workers with configurable unload delay.

    For Triton architecture:
    - TTS workers: Lightweight gRPC clients, fast to create/destroy
    - RVC workers: Hold GPU resources via CUDA streams, benefit from persistence
    """

    def __init__(
        self,
        unload_delay: int = DEFAULT_MODEL_DELAY,
        triton_addr: str = DEFAULT_TRITON_ADDR,
        triton_port: int = DEFAULT_TRITON_PORT,
    ):
        """
        Initialize the worker manager.

        Args:
            unload_delay: Time in seconds to keep workers alive after processing completes.
            triton_addr: Triton server address.
            triton_port: Triton gRPC port.
        """
        self.unload_delay = unload_delay
        self.triton_addr = triton_addr
        self.triton_port = triton_port

        # Worker tracking
        self.tts_workers = {}  # {worker_id: {'thread': thread, 'last_used': timestamp}}
        self.rvc_workers = {}  # {worker_id: {'thread': thread, 'last_used': timestamp}}
        self.tts_job_queues = {}  # {worker_id: Queue()}
        self.rvc_job_queues = {}  # {worker_id: Queue()}
        self.tts_active = {}  # {worker_id: Event()}
        self.rvc_active = {}  # {worker_id: Event()}

        self.manager_lock = threading.Lock()
        self.shutdown_event = threading.Event()

        # Start unload monitor thread
        self.monitor_thread = threading.Thread(target=self._monitor_workers, daemon=True)
        self.monitor_thread.start()

        logger.info(
            f"WorkerManager initialized: unload_delay={unload_delay}s, "
            f"triton={triton_addr}:{triton_port}"
        )

    def _monitor_workers(self):
        """Background thread that monitors worker usage and unloads idle workers."""
        while not self.shutdown_event.is_set():
            # Skip unload checks if delay is 0 or negative (persist forever)
            if self.unload_delay <= 0:
                time.sleep(1)
                continue

            current_time = time.time()

            with self.manager_lock:
                # Check TTS workers
                for worker_id in list(self.tts_workers.keys()):
                    worker_info = self.tts_workers[worker_id]
                    if (
                        not self.tts_active[worker_id].is_set()
                        and current_time - worker_info["last_used"] > self.unload_delay
                    ):
                        logger.info(
                            f"Unloading idle TTS worker {worker_id} after {self.unload_delay}s"
                        )
                        self._shutdown_tts_worker(worker_id, worker_info)

                # Check RVC workers
                for worker_id in list(self.rvc_workers.keys()):
                    worker_info = self.rvc_workers[worker_id]
                    if (
                        not self.rvc_active[worker_id].is_set()
                        and current_time - worker_info["last_used"] > self.unload_delay
                    ):
                        logger.info(
                            f"Unloading idle RVC worker {worker_id} after {self.unload_delay}s"
                        )
                        self._shutdown_rvc_worker(worker_id, worker_info)

            # Check every second
            time.sleep(1)

    def _shutdown_tts_worker(self, worker_id, worker_info):
        """Shutdown a TTS worker (must hold manager_lock)."""
        self.tts_job_queues[worker_id].put(None)
        worker_info["thread"].join(timeout=5)
        del self.tts_workers[worker_id]
        del self.tts_job_queues[worker_id]
        del self.tts_active[worker_id]

    def _shutdown_rvc_worker(self, worker_id, worker_info):
        """Shutdown an RVC worker (must hold manager_lock)."""
        self.rvc_job_queues[worker_id].put(None)
        worker_info["thread"].join(timeout=5)
        del self.rvc_workers[worker_id]
        del self.rvc_job_queues[worker_id]
        del self.rvc_active[worker_id]

    def get_tts_worker(self, worker_id: int) -> Queue:
        """
        Get or create a TTS worker.

        For Triton, TTS workers are lightweight gRPC clients.
        No model_dir or device needed - connects to Triton server.

        Args:
            worker_id: Unique worker ID.

        Returns:
            Queue: Job queue for the worker.
        """
        with self.manager_lock:
            if worker_id in self.tts_workers:
                logger.info(f"Reusing existing TTS worker {worker_id}")
                self.tts_workers[worker_id]["last_used"] = time.time()
                self.tts_active[worker_id].set()
                return self.tts_job_queues[worker_id]

            # Create new worker
            logger.info(f"Creating new TTS worker {worker_id} -> {self.triton_addr}:{self.triton_port}")
            job_queue = Queue()
            active_event = threading.Event()
            active_event.set()

            self.tts_job_queues[worker_id] = job_queue
            self.tts_active[worker_id] = active_event

            thread = threading.Thread(
                target=persistent_tts_worker,
                args=(
                    worker_id,
                    job_queue,
                    active_event,
                    self.triton_addr,
                    self.triton_port,
                    self,
                ),
                daemon=True,
            )
            thread.start()

            self.tts_workers[worker_id] = {"thread": thread, "last_used": time.time()}

            return job_queue

    def get_rvc_worker(self, worker_id: int, cuda_stream=None) -> Queue:
        """
        Get or create an RVC worker.

        Args:
            worker_id: Unique worker ID.
            cuda_stream: CUDA stream for this worker's GPU operations.

        Returns:
            Queue: Job queue for the worker.
        """
        with self.manager_lock:
            if worker_id in self.rvc_workers:
                logger.info(f"Reusing existing RVC worker {worker_id}")
                self.rvc_workers[worker_id]["last_used"] = time.time()
                self.rvc_active[worker_id].set()
                return self.rvc_job_queues[worker_id]

            # Create new worker
            logger.info(f"Creating new RVC worker {worker_id} (stream={cuda_stream is not None})")
            job_queue = Queue()
            active_event = threading.Event()
            active_event.set()

            self.rvc_job_queues[worker_id] = job_queue
            self.rvc_active[worker_id] = active_event

            thread = threading.Thread(
                target=persistent_rvc_worker,
                args=(worker_id, cuda_stream, job_queue, active_event, self),
                daemon=True,
            )
            thread.start()

            self.rvc_workers[worker_id] = {"thread": thread, "last_used": time.time()}

            return job_queue

    def mark_tts_worker_idle(self, worker_id: int):
        """Mark a TTS worker as idle."""
        with self.manager_lock:
            if worker_id in self.tts_workers:
                self.tts_workers[worker_id]["last_used"] = time.time()
                self.tts_active[worker_id].clear()

    def mark_rvc_worker_idle(self, worker_id: int):
        """Mark an RVC worker as idle."""
        with self.manager_lock:
            if worker_id in self.rvc_workers:
                self.rvc_workers[worker_id]["last_used"] = time.time()
                self.rvc_active[worker_id].clear()

    def update_unload_delay(self, delay: int):
        """Update the unload delay."""
        with self.manager_lock:
            self.unload_delay = delay
            logger.info(f"Updated worker unload delay to {delay}s")

    def update_triton_config(self, addr: str = None, port: int = None):
        """Update Triton server configuration."""
        with self.manager_lock:
            if addr:
                self.triton_addr = addr
            if port:
                self.triton_port = port
            logger.info(f"Updated Triton config: {self.triton_addr}:{self.triton_port}")

    def shutdown_rvc_workers(self):
        """Shut down all RVC workers (keeps TTS workers running)."""
        with self.manager_lock:
            worker_ids = list(self.rvc_workers.keys())
            if not worker_ids:
                logger.info("No RVC workers to shut down")
                return

            logger.info(f"Shutting down {len(worker_ids)} RVC worker(s)")
            for worker_id in worker_ids:
                worker_info = self.rvc_workers[worker_id]
                self._shutdown_rvc_worker(worker_id, worker_info)

            logger.info("All RVC workers shut down")

    def shutdown_tts_workers(self):
        """Shut down all TTS workers (keeps RVC workers running)."""
        with self.manager_lock:
            worker_ids = list(self.tts_workers.keys())
            if not worker_ids:
                logger.info("No TTS workers to shut down")
                return

            logger.info(f"Shutting down {len(worker_ids)} TTS worker(s)")
            for worker_id in worker_ids:
                worker_info = self.tts_workers[worker_id]
                self._shutdown_tts_worker(worker_id, worker_info)

            logger.info("All TTS workers shut down")

    def get_worker_status(self) -> dict:
        """Get status of all workers."""
        with self.manager_lock:
            return {
                "tts_workers": {
                    wid: {
                        "active": self.tts_active[wid].is_set(),
                        "last_used": info["last_used"],
                    }
                    for wid, info in self.tts_workers.items()
                },
                "rvc_workers": {
                    wid: {
                        "active": self.rvc_active[wid].is_set(),
                        "last_used": info["last_used"],
                    }
                    for wid, info in self.rvc_workers.items()
                },
                "unload_delay": self.unload_delay,
            }

    def shutdown(self):
        """Shut down all workers and the manager."""
        logger.info("Shutting down WorkerManager")
        self.shutdown_event.set()

        with self.manager_lock:
            # Signal all workers to shut down
            for queue in self.tts_job_queues.values():
                queue.put(None)
            for queue in self.rvc_job_queues.values():
                queue.put(None)

            # Wait for workers to finish
            for worker_info in self.tts_workers.values():
                worker_info["thread"].join(timeout=5)
            for worker_info in self.rvc_workers.values():
                worker_info["thread"].join(timeout=5)

        self.monitor_thread.join(timeout=5)
        logger.info("WorkerManager shutdown complete")


# Global worker manager instance
_worker_manager = None


def get_worker_manager(
    unload_delay: int = None,
    triton_addr: str = None,
    triton_port: int = None,
) -> WorkerManager:
    """
    Get or create the global worker manager.

    Args:
        unload_delay: Time in seconds to keep workers alive after processing.
        triton_addr: Triton server address.
        triton_port: Triton gRPC port.

    Returns:
        WorkerManager: The global worker manager instance.
    """
    global _worker_manager

    if _worker_manager is None:
        _worker_manager = WorkerManager(
            unload_delay=unload_delay or DEFAULT_MODEL_DELAY,
            triton_addr=triton_addr or DEFAULT_TRITON_ADDR,
            triton_port=triton_port or DEFAULT_TRITON_PORT,
        )
    else:
        # Update config if provided
        if unload_delay is not None and unload_delay != _worker_manager.unload_delay:
            _worker_manager.update_unload_delay(unload_delay)
        if triton_addr or triton_port:
            _worker_manager.update_triton_config(triton_addr, triton_port)

    return _worker_manager


def set_worker_unload_delay(delay: int) -> str:
    """
    Set the worker unload delay.

    Args:
        delay: New delay in seconds.

    Returns:
        str: Confirmation message.
    """
    if not isinstance(delay, int) or delay < 0:
        return "Invalid delay value. Please provide a positive integer."

    get_worker_manager(unload_delay=delay)
    return f"Worker unload delay set to {delay} seconds"


def get_current_worker_unload_delay() -> int:
    """
    Get the current worker unload delay.

    Returns:
        int: Current delay in seconds.
    """
    manager = get_worker_manager()
    return manager.unload_delay


def shutdown_rvc_workers() -> str:
    """
    Shut down all RVC workers.

    Returns:
        str: Status message.
    """
    global _worker_manager
    if _worker_manager is None:
        return "No worker manager initialized"

    _worker_manager.shutdown_rvc_workers()
    return "RVC workers shut down"


def shutdown_tts_workers() -> str:
    """
    Shut down all TTS workers.

    Returns:
        str: Status message.
    """
    global _worker_manager
    if _worker_manager is None:
        return "No worker manager initialized"

    _worker_manager.shutdown_tts_workers()
    return "TTS workers shut down"


def shutdown_all_workers() -> str:
    """
    Shut down all workers (both TTS and RVC).

    Returns:
        str: Status message.
    """
    global _worker_manager
    if _worker_manager is None:
        return "No worker manager initialized"

    _worker_manager.shutdown()
    _worker_manager = None
    return "All workers shut down"


def get_worker_status() -> dict:
    """
    Get status of all workers.

    Returns:
        dict: Worker status including active state and last used time.
    """
    global _worker_manager
    if _worker_manager is None:
        return {"error": "No worker manager initialized"}

    return _worker_manager.get_worker_status()
