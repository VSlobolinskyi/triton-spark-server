"""
RVC gRPC Server

Wraps the RVCServer with multiprocessing workers to expose via gRPC.
Run as Docker container or standalone daemon.

Usage:
    python -m rvc.grpc.rvc_grpc_server --model SilverWolf_e300_s6600.pth --workers 2 --port 50051
"""

import os
import sys
import time
import signal
import logging
import argparse
import tempfile
from concurrent import futures
from typing import Optional
import io

import grpc
import soundfile as sf
import numpy as np

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from rvc.server.rvc_server import RVCServer, RVCJob, RVCResult

# Import generated proto modules (generated from rvc_service.proto)
try:
    from . import rvc_service_pb2
    from . import rvc_service_pb2_grpc
except ImportError:
    # Fallback for when running directly
    import rvc_service_pb2
    import rvc_service_pb2_grpc

logger = logging.getLogger(__name__)

# Global shutdown flag
_shutdown_requested = False


def signal_handler(signum, frame):
    """Handle shutdown signals."""
    global _shutdown_requested
    logger.info(f"Received signal {signum}, initiating shutdown...")
    _shutdown_requested = True


class RVCServicer(rvc_service_pb2_grpc.RVCServiceServicer):
    """gRPC servicer wrapping RVCServer."""

    def __init__(self, rvc_server: RVCServer):
        self.server = rvc_server
        self.start_time = time.time()
        self._job_counter = 0

    def Convert(self, request, context):
        """Convert audio directly (bytes in, bytes out)."""
        try:
            # Parse input audio
            if request.format == rvc_service_pb2.WAV:
                # WAV bytes
                audio_io = io.BytesIO(request.audio_data)
                audio, sample_rate = sf.read(audio_io)
            else:
                # Raw PCM float32
                audio = np.frombuffer(request.audio_data, dtype=np.float32)
                sample_rate = request.sample_rate or 16000

            # Create temp files for processing
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f_in:
                input_path = f_in.name
                sf.write(input_path, audio, sample_rate)

            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f_out:
                output_path = f_out.name

            try:
                # Submit job
                self._job_counter += 1
                job_id = self.server.submit_job(
                    input_audio_path=input_path,
                    output_audio_path=output_path,
                    pitch_shift=request.pitch_shift,
                    f0_method=request.f0_method or "rmvpe",
                    index_rate=request.index_rate or 0.75,
                    filter_radius=request.filter_radius or 3,
                    resample_sr=request.resample_sr or 0,
                    rms_mix_rate=request.rms_mix_rate or 0.25,
                    protect=request.protect or 0.33,
                )

                # Wait for result
                result = self.server.get_result(timeout=60.0)

                if result and result.success:
                    # Read output audio
                    output_audio, out_sr = sf.read(output_path)

                    # Convert to bytes
                    output_io = io.BytesIO()
                    sf.write(output_io, output_audio, out_sr, format='WAV')
                    audio_bytes = output_io.getvalue()

                    return rvc_service_pb2.ConvertResponse(
                        success=True,
                        audio_data=audio_bytes,
                        format=rvc_service_pb2.WAV,
                        sample_rate=out_sr,
                        processing_time=result.processing_time,
                        worker_id=result.worker_id,
                        request_id=request.request_id,
                    )
                else:
                    error_msg = result.error if result else "Timeout waiting for result"
                    return rvc_service_pb2.ConvertResponse(
                        success=False,
                        error=error_msg,
                        request_id=request.request_id,
                    )

            finally:
                # Cleanup temp files
                for f in [input_path, output_path]:
                    if os.path.exists(f):
                        os.unlink(f)

        except Exception as e:
            logger.error(f"Convert error: {e}")
            return rvc_service_pb2.ConvertResponse(
                success=False,
                error=str(e),
                request_id=request.request_id,
            )

    def SubmitJob(self, request, context):
        """Submit a file-based job for async processing."""
        try:
            job_id = self.server.submit_job(
                input_audio_path=request.input_path,
                output_audio_path=request.output_path,
                pitch_shift=request.pitch_shift,
                f0_method=request.f0_method or "rmvpe",
                index_rate=request.index_rate or 0.75,
                filter_radius=request.filter_radius or 3,
                resample_sr=request.resample_sr or 0,
                rms_mix_rate=request.rms_mix_rate or 0.25,
                protect=request.protect or 0.33,
            )

            return rvc_service_pb2.SubmitJobResponse(
                success=True,
                job_id=job_id,
            )

        except Exception as e:
            logger.error(f"SubmitJob error: {e}")
            return rvc_service_pb2.SubmitJobResponse(
                success=False,
                error=str(e),
            )

    def GetResult(self, request, context):
        """Get result of a submitted job."""
        try:
            timeout = request.timeout if request.timeout > 0 else 30.0
            result = self.server.get_result(timeout=timeout)

            if result:
                return rvc_service_pb2.GetResultResponse(
                    success=result.success,
                    job_id=result.job_id,
                    output_path=result.output_path or "",
                    processing_time=result.processing_time,
                    worker_id=result.worker_id,
                    error=result.error or "",
                )
            else:
                return rvc_service_pb2.GetResultResponse(
                    success=False,
                    timed_out=True,
                    error="Timeout waiting for result",
                )

        except Exception as e:
            logger.error(f"GetResult error: {e}")
            return rvc_service_pb2.GetResultResponse(
                success=False,
                error=str(e),
            )

    def ConvertStream(self, request_iterator, context):
        """Stream multiple conversions for pipeline efficiency."""
        for request in request_iterator:
            yield self.Convert(request, context)

    def GetStatus(self, request, context):
        """Get server status."""
        try:
            status = self.server.get_status()

            # Build worker status list
            workers = []
            for i in range(status.get("num_workers", 0)):
                workers.append(rvc_service_pb2.WorkerStatus(
                    worker_id=i,
                    alive=i < status.get("workers_alive", 0),
                    jobs_processed=0,  # TODO: track per-worker stats
                    avg_processing_time=0.0,
                ))

            return rvc_service_pb2.StatusResponse(
                running=status.get("running", False),
                model_name=status.get("model", ""),
                num_workers=status.get("num_workers", 0),
                workers_alive=status.get("workers_alive", 0),
                jobs_submitted=status.get("jobs_submitted", 0),
                jobs_completed=status.get("jobs_completed", 0),
                uptime=time.time() - self.start_time,
                workers=workers,
            )

        except Exception as e:
            logger.error(f"GetStatus error: {e}")
            return rvc_service_pb2.StatusResponse(running=False)

    def HealthCheck(self, request, context):
        """Health check for load balancers/orchestration."""
        try:
            status = self.server.get_status()
            workers_alive = status.get("workers_alive", 0)

            if workers_alive > 0:
                return rvc_service_pb2.HealthResponse(
                    healthy=True,
                    status="ready",
                    message=f"{workers_alive} workers ready",
                )
            elif self.server.is_running:
                return rvc_service_pb2.HealthResponse(
                    healthy=False,
                    status="loading",
                    message="Workers initializing",
                )
            else:
                return rvc_service_pb2.HealthResponse(
                    healthy=False,
                    status="error",
                    message="Server not running",
                )

        except Exception as e:
            return rvc_service_pb2.HealthResponse(
                healthy=False,
                status="error",
                message=str(e),
            )


def serve(
    model_name: str,
    num_workers: int = 2,
    port: int = 50051,
    max_workers: int = 10,
    startup_timeout: float = 120.0,
) -> None:
    """Start the RVC gRPC server.

    Args:
        model_name: RVC model file name
        num_workers: Number of RVC inference workers
        port: gRPC server port
        max_workers: Max gRPC thread pool workers
        startup_timeout: Timeout for RVC worker initialization
    """
    global _shutdown_requested

    # Setup signal handlers
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    logger.info("=" * 60)
    logger.info("RVC gRPC Server Starting")
    logger.info("=" * 60)
    logger.info(f"Model: {model_name}")
    logger.info(f"Workers: {num_workers}")
    logger.info(f"Port: {port}")

    # Initialize RVC server with multiprocessing workers
    rvc_server = RVCServer(model_name=model_name, num_workers=num_workers)

    if not rvc_server.start(timeout=startup_timeout):
        logger.error("Failed to start RVC server")
        sys.exit(1)

    logger.info("RVC workers initialized successfully")

    # Create gRPC server
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=max_workers))
    servicer = RVCServicer(rvc_server)
    rvc_service_pb2_grpc.add_RVCServiceServicer_to_server(servicer, server)

    server.add_insecure_port(f"[::]:{port}")
    server.start()

    logger.info(f"gRPC server listening on port {port}")
    logger.info("Server ready to accept requests")

    # Main loop
    try:
        while not _shutdown_requested:
            time.sleep(1.0)

            # Check worker health
            status = rvc_server.get_status()
            if status.get("workers_alive", 0) == 0:
                logger.error("All workers died, shutting down")
                break

    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")

    finally:
        logger.info("Shutting down gRPC server...")
        server.stop(grace=5)

        logger.info("Shutting down RVC workers...")
        rvc_server.shutdown()

        logger.info("Shutdown complete")


def main():
    parser = argparse.ArgumentParser(description="RVC gRPC Server")
    parser.add_argument("--model", required=True, help="RVC model name")
    parser.add_argument("--workers", type=int, default=2, help="Number of RVC workers")
    parser.add_argument("--port", type=int, default=50051, help="gRPC port")
    parser.add_argument("--timeout", type=float, default=120, help="Startup timeout")
    parser.add_argument("--log-level", default="INFO", help="Log level")

    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    serve(
        model_name=args.model,
        num_workers=args.workers,
        port=args.port,
        startup_timeout=args.timeout,
    )


if __name__ == "__main__":
    main()
