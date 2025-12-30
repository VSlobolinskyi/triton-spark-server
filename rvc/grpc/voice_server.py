"""
Unified Voice Service (TTS + RVC) gRPC Server

Combines Spark TTS and RVC voice conversion into a single service.
Connects to Triton for TTS and manages RVC workers internally.

Usage:
    python -m rvc.grpc.voice_server \
        --rvc-model SilverWolf.pth \
        --rvc-workers 2 \
        --triton-addr localhost \
        --triton-port 8001 \
        --port 50052
"""

import os
import sys
import io
import re
import time
import signal
import logging
import argparse
import tempfile
from concurrent import futures
from typing import Optional, List
from queue import Queue, Empty
import threading

import grpc
import numpy as np
import soundfile as sf

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from rvc.triton_client import TritonSparkClient
from rvc.server.rvc_server import RVCServer

# Import generated proto modules
try:
    from . import voice_service_pb2
    from . import voice_service_pb2_grpc
except ImportError:
    import voice_service_pb2
    import voice_service_pb2_grpc

logger = logging.getLogger(__name__)

# Global shutdown flag
_shutdown_requested = False


def signal_handler(signum, frame):
    """Handle shutdown signals."""
    global _shutdown_requested
    logger.info(f"Received signal {signum}, initiating shutdown...")
    _shutdown_requested = True


def split_into_sentences(text: str) -> List[str]:
    """Split text into sentences."""
    sentences = re.split(r'(?<=[.!?])\s+', text)
    return [s.strip() for s in sentences if s.strip()]


class VoiceServicer(voice_service_pb2_grpc.VoiceServiceServicer):
    """gRPC servicer for unified voice synthesis."""

    def __init__(
        self,
        tts_client: TritonSparkClient,
        rvc_server: Optional[RVCServer],
    ):
        self.tts_client = tts_client
        self.rvc_server = rvc_server
        self.start_time = time.time()
        self._request_counter = 0
        self._success_counter = 0
        self._fail_counter = 0
        self._lock = threading.Lock()

    def _get_reference_audio(self, request) -> tuple:
        """Extract reference audio from request. Returns (audio_array, sample_rate)."""
        if request.reference_audio:
            # Audio bytes provided
            audio_io = io.BytesIO(request.reference_audio)
            audio, sr = sf.read(audio_io)
            return audio.astype(np.float32), sr
        elif request.reference_audio_path:
            # File path provided
            audio, sr = sf.read(request.reference_audio_path)
            return audio.astype(np.float32), sr
        else:
            raise ValueError("No reference audio provided")

    def _run_tts(self, text: str, reference_audio: np.ndarray, reference_text: str) -> tuple:
        """Run TTS inference. Returns (audio_array, processing_time)."""
        start = time.time()
        audio = self.tts_client.inference(
            text=text,
            prompt_speech=reference_audio,
            prompt_text=reference_text,
        )
        return audio, time.time() - start

    def _run_rvc(self, audio: np.ndarray, request) -> tuple:
        """Run RVC conversion. Returns (audio_array, processing_time, worker_id)."""
        if self.rvc_server is None:
            return audio, 0.0, -1

        # Create temp files
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f_in:
            input_path = f_in.name
            sf.write(input_path, audio, 16000)

        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f_out:
            output_path = f_out.name

        try:
            # Submit job
            job_id = self.rvc_server.submit_job(
                input_audio_path=input_path,
                output_audio_path=output_path,
                pitch_shift=request.pitch_shift or 0,
                f0_method=request.f0_method or "rmvpe",
                index_rate=request.index_rate or 0.75,
                filter_radius=request.filter_radius or 3,
                resample_sr=request.resample_sr or 0,
                rms_mix_rate=request.rms_mix_rate or 0.25,
                protect=request.protect or 0.33,
            )

            # Wait for result
            result = self.rvc_server.get_result(timeout=60.0)

            if result and result.success:
                output_audio, _ = sf.read(output_path)
                return output_audio.astype(np.float32), result.processing_time, result.worker_id
            else:
                error = result.error if result else "Timeout"
                raise RuntimeError(f"RVC failed: {error}")

        finally:
            # Cleanup temp files
            for f in [input_path, output_path]:
                if os.path.exists(f):
                    try:
                        os.unlink(f)
                    except:
                        pass

    def _audio_to_bytes(self, audio: np.ndarray, sample_rate: int = 16000) -> bytes:
        """Convert audio array to WAV bytes."""
        audio_io = io.BytesIO()
        sf.write(audio_io, audio, sample_rate, format='WAV')
        return audio_io.getvalue()

    def Synthesize(self, request, context):
        """Main synthesis endpoint: text → voice-converted speech."""
        with self._lock:
            self._request_counter += 1

        try:
            total_start = time.time()

            # Get reference audio
            ref_audio, _ = self._get_reference_audio(request)

            # Run TTS
            tts_audio, tts_time = self._run_tts(
                text=request.text,
                reference_audio=ref_audio,
                reference_text=request.reference_text,
            )

            # Run RVC (unless skipped)
            if request.skip_rvc or self.rvc_server is None:
                final_audio = tts_audio
                rvc_time = 0.0
                worker_id = -1
            else:
                final_audio, rvc_time, worker_id = self._run_rvc(tts_audio, request)

            total_time = time.time() - total_start

            with self._lock:
                self._success_counter += 1

            return voice_service_pb2.SynthesizeResponse(
                success=True,
                audio_data=self._audio_to_bytes(final_audio),
                format=voice_service_pb2.WAV,
                sample_rate=16000,
                tts_time=tts_time,
                rvc_time=rvc_time,
                total_time=total_time,
                rvc_worker_id=worker_id,
                request_id=request.request_id,
            )

        except Exception as e:
            logger.error(f"Synthesize error: {e}")
            with self._lock:
                self._fail_counter += 1
            return voice_service_pb2.SynthesizeResponse(
                success=False,
                error=str(e),
                request_id=request.request_id,
            )

    def SynthesizeStream(self, request, context):
        """Stream synthesis: splits text into sentences, yields results as completed."""
        with self._lock:
            self._request_counter += 1

        try:
            # Get reference audio once
            ref_audio, _ = self._get_reference_audio(request)

            # Split text into sentences
            sentences = split_into_sentences(request.text)

            for i, sentence in enumerate(sentences):
                try:
                    sentence_start = time.time()

                    # Run TTS
                    tts_audio, tts_time = self._run_tts(
                        text=sentence,
                        reference_audio=ref_audio,
                        reference_text=request.reference_text,
                    )

                    # Run RVC
                    if request.skip_rvc or self.rvc_server is None:
                        final_audio = tts_audio
                        rvc_time = 0.0
                        worker_id = -1
                    else:
                        final_audio, rvc_time, worker_id = self._run_rvc(tts_audio, request)

                    total_time = time.time() - sentence_start

                    yield voice_service_pb2.SynthesizeResponse(
                        success=True,
                        audio_data=self._audio_to_bytes(final_audio),
                        format=voice_service_pb2.WAV,
                        sample_rate=16000,
                        tts_time=tts_time,
                        rvc_time=rvc_time,
                        total_time=total_time,
                        rvc_worker_id=worker_id,
                        sentence_index=i,
                        sentence_text=sentence,
                        is_final=(i == len(sentences) - 1),
                        request_id=request.request_id,
                    )

                except Exception as e:
                    logger.error(f"Sentence {i} error: {e}")
                    yield voice_service_pb2.SynthesizeResponse(
                        success=False,
                        error=str(e),
                        sentence_index=i,
                        sentence_text=sentence,
                        is_final=(i == len(sentences) - 1),
                        request_id=request.request_id,
                    )

            with self._lock:
                self._success_counter += 1

        except Exception as e:
            logger.error(f"SynthesizeStream error: {e}")
            with self._lock:
                self._fail_counter += 1
            yield voice_service_pb2.SynthesizeResponse(
                success=False,
                error=str(e),
                request_id=request.request_id,
            )

    def SynthesizeBatch(self, request, context):
        """Batch synthesis: process multiple texts with shared reference."""
        with self._lock:
            self._request_counter += 1

        try:
            # Get reference audio once
            ref_audio, _ = self._get_reference_audio(request)

            for i, text in enumerate(request.texts):
                try:
                    sentence_start = time.time()

                    # Run TTS
                    tts_audio, tts_time = self._run_tts(
                        text=text,
                        reference_audio=ref_audio,
                        reference_text=request.reference_text,
                    )

                    # Run RVC
                    if request.skip_rvc or self.rvc_server is None:
                        final_audio = tts_audio
                        rvc_time = 0.0
                        worker_id = -1
                    else:
                        final_audio, rvc_time, worker_id = self._run_rvc(tts_audio, request)

                    total_time = time.time() - sentence_start

                    yield voice_service_pb2.SynthesizeResponse(
                        success=True,
                        audio_data=self._audio_to_bytes(final_audio),
                        format=voice_service_pb2.WAV,
                        sample_rate=16000,
                        tts_time=tts_time,
                        rvc_time=rvc_time,
                        total_time=total_time,
                        rvc_worker_id=worker_id,
                        sentence_index=i,
                        sentence_text=text,
                        is_final=(i == len(request.texts) - 1),
                        request_id=request.request_id,
                    )

                except Exception as e:
                    logger.error(f"Batch item {i} error: {e}")
                    yield voice_service_pb2.SynthesizeResponse(
                        success=False,
                        error=str(e),
                        sentence_index=i,
                        sentence_text=text,
                        is_final=(i == len(request.texts) - 1),
                        request_id=request.request_id,
                    )

            with self._lock:
                self._success_counter += 1

        except Exception as e:
            logger.error(f"SynthesizeBatch error: {e}")
            with self._lock:
                self._fail_counter += 1
            yield voice_service_pb2.SynthesizeResponse(
                success=False,
                error=str(e),
                request_id=request.request_id,
            )

    def TTSOnly(self, request, context):
        """TTS-only endpoint for testing."""
        try:
            ref_audio, _ = self._get_reference_audio(request)

            tts_audio, processing_time = self._run_tts(
                text=request.text,
                reference_audio=ref_audio,
                reference_text=request.reference_text,
            )

            return voice_service_pb2.TTSResponse(
                success=True,
                audio_data=self._audio_to_bytes(tts_audio),
                format=voice_service_pb2.WAV,
                sample_rate=16000,
                processing_time=processing_time,
                request_id=request.request_id,
            )

        except Exception as e:
            logger.error(f"TTSOnly error: {e}")
            return voice_service_pb2.TTSResponse(
                success=False,
                error=str(e),
                request_id=request.request_id,
            )

    def RVCOnly(self, request, context):
        """RVC-only endpoint for converting existing audio."""
        if self.rvc_server is None:
            return voice_service_pb2.RVCResponse(
                success=False,
                error="RVC not available",
                request_id=request.request_id,
            )

        try:
            # Get input audio
            if request.audio_data:
                audio_io = io.BytesIO(request.audio_data)
                audio, sr = sf.read(audio_io)
            elif request.audio_path:
                audio, sr = sf.read(request.audio_path)
            else:
                raise ValueError("No audio provided")

            # Run RVC
            output_audio, processing_time, worker_id = self._run_rvc(
                audio.astype(np.float32), request
            )

            return voice_service_pb2.RVCResponse(
                success=True,
                audio_data=self._audio_to_bytes(output_audio),
                format=voice_service_pb2.WAV,
                sample_rate=16000,
                processing_time=processing_time,
                worker_id=worker_id,
                request_id=request.request_id,
            )

        except Exception as e:
            logger.error(f"RVCOnly error: {e}")
            return voice_service_pb2.RVCResponse(
                success=False,
                error=str(e),
                request_id=request.request_id,
            )

    def GetStatus(self, request, context):
        """Get server status."""
        tts_ready = self.tts_client.is_server_ready() if self.tts_client else False

        rvc_status = {}
        if self.rvc_server:
            rvc_status = self.rvc_server.get_status()

        workers = []
        for i in range(rvc_status.get("num_workers", 0)):
            workers.append(voice_service_pb2.WorkerStatus(
                worker_id=i,
                alive=i < rvc_status.get("workers_alive", 0),
                jobs_processed=0,
                avg_processing_time=0.0,
            ))

        with self._lock:
            total = self._request_counter
            success = self._success_counter
            failed = self._fail_counter

        return voice_service_pb2.StatusResponse(
            running=True,
            tts_ready=tts_ready,
            tts_model="spark_tts",
            triton_server=f"{self.tts_client.server_addr}:{self.tts_client.server_port}",
            rvc_ready=rvc_status.get("running", False),
            rvc_model=rvc_status.get("model", ""),
            rvc_workers=rvc_status.get("num_workers", 0),
            rvc_workers_alive=rvc_status.get("workers_alive", 0),
            total_requests=total,
            successful_requests=success,
            failed_requests=failed,
            uptime=time.time() - self.start_time,
            workers=workers,
        )

    def HealthCheck(self, request, context):
        """Health check for orchestration."""
        tts_healthy = self.tts_client.is_server_ready() if self.tts_client else False

        rvc_healthy = False
        if self.rvc_server:
            status = self.rvc_server.get_status()
            rvc_healthy = status.get("workers_alive", 0) > 0

        if tts_healthy and rvc_healthy:
            return voice_service_pb2.HealthResponse(
                healthy=True,
                status="ready",
                message="All services ready",
                tts_healthy=True,
                rvc_healthy=True,
            )
        elif tts_healthy or rvc_healthy:
            return voice_service_pb2.HealthResponse(
                healthy=False,
                status="degraded",
                message=f"TTS: {tts_healthy}, RVC: {rvc_healthy}",
                tts_healthy=tts_healthy,
                rvc_healthy=rvc_healthy,
            )
        else:
            return voice_service_pb2.HealthResponse(
                healthy=False,
                status="error",
                message="No services available",
                tts_healthy=False,
                rvc_healthy=False,
            )

    def LoadModel(self, request, context):
        """Load/change RVC model at runtime."""
        # This would require restarting RVC workers
        # For now, return not implemented
        return voice_service_pb2.LoadModelResponse(
            success=False,
            error="Runtime model loading not yet implemented",
        )


def serve(
    rvc_model: str,
    rvc_workers: int = 2,
    triton_addr: str = "localhost",
    triton_port: int = 8001,
    port: int = 50052,
    max_workers: int = 10,
    startup_timeout: float = 120.0,
) -> None:
    """Start the unified voice service.

    Args:
        rvc_model: RVC model file name
        rvc_workers: Number of RVC inference workers
        triton_addr: Triton server address for TTS
        triton_port: Triton gRPC port
        port: gRPC server port for this service
        max_workers: Max gRPC thread pool workers
        startup_timeout: Timeout for RVC worker initialization
    """
    global _shutdown_requested

    # Setup signal handlers
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    logger.info("=" * 60)
    logger.info("Unified Voice Service Starting")
    logger.info("=" * 60)
    logger.info(f"Triton (TTS): {triton_addr}:{triton_port}")
    logger.info(f"RVC Model: {rvc_model}")
    logger.info(f"RVC Workers: {rvc_workers}")
    logger.info(f"Service Port: {port}")

    # Initialize TTS client
    logger.info("Connecting to Triton server...")
    tts_client = TritonSparkClient(
        server_addr=triton_addr,
        server_port=triton_port,
    )

    if not tts_client.is_server_ready():
        logger.error("Triton server not ready!")
        sys.exit(1)

    logger.info("Triton TTS connected")

    # Initialize RVC server
    logger.info(f"Starting RVC with {rvc_workers} workers...")
    rvc_server = RVCServer(model_name=rvc_model, num_workers=rvc_workers)

    if not rvc_server.start(timeout=startup_timeout):
        logger.error("Failed to start RVC server")
        sys.exit(1)

    logger.info("RVC workers initialized")

    # Create gRPC server
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=max_workers))
    servicer = VoiceServicer(tts_client, rvc_server)
    voice_service_pb2_grpc.add_VoiceServiceServicer_to_server(servicer, server)

    server.add_insecure_port(f"[::]:{port}")
    server.start()

    logger.info(f"gRPC server listening on port {port}")
    logger.info("=" * 60)
    logger.info("Service ready to accept requests")
    logger.info("=" * 60)

    # Main loop
    try:
        while not _shutdown_requested:
            time.sleep(1.0)

            # Check component health
            if rvc_server:
                status = rvc_server.get_status()
                if status.get("workers_alive", 0) == 0:
                    logger.error("All RVC workers died, shutting down")
                    break

    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")

    finally:
        logger.info("Shutting down...")

        logger.info("Stopping gRPC server...")
        server.stop(grace=5)

        logger.info("Closing TTS client...")
        tts_client.close()

        logger.info("Shutting down RVC workers...")
        if rvc_server:
            rvc_server.shutdown()

        logger.info("Shutdown complete")


def main():
    parser = argparse.ArgumentParser(description="Unified Voice Service (TTS + RVC)")
    parser.add_argument("--rvc-model", required=True, help="RVC model name")
    parser.add_argument("--rvc-workers", type=int, default=2, help="Number of RVC workers")
    parser.add_argument("--triton-addr", default="localhost", help="Triton server address")
    parser.add_argument("--triton-port", type=int, default=8001, help="Triton gRPC port")
    parser.add_argument("--port", type=int, default=50052, help="Service gRPC port")
    parser.add_argument("--timeout", type=float, default=120, help="Startup timeout")
    parser.add_argument("--log-level", default="INFO", help="Log level")

    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    serve(
        rvc_model=args.rvc_model,
        rvc_workers=args.rvc_workers,
        triton_addr=args.triton_addr,
        triton_port=args.triton_port,
        port=args.port,
        startup_timeout=args.timeout,
    )


if __name__ == "__main__":
    main()
