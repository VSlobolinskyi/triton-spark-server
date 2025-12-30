"""
RVC gRPC Client

Client for communicating with the RVC gRPC server (Docker or standalone).
Mirrors the TritonSparkClient pattern for consistency.

Usage:
    from rvc.grpc import RVCGrpcClient

    client = RVCGrpcClient(host="localhost", port=50051)
    if client.is_server_ready():
        # Convert audio bytes directly
        result = client.convert(audio_bytes, pitch_shift=0)

        # Or use file-based async processing
        job_id = client.submit_job("input.wav", "output.wav")
        result = client.get_result(timeout=30.0)
"""

import os
import io
import logging
from typing import Optional, Union
from dataclasses import dataclass

import grpc
import numpy as np
import soundfile as sf

# Import generated proto modules
try:
    from . import rvc_service_pb2
    from . import rvc_service_pb2_grpc
except ImportError:
    import rvc_service_pb2
    import rvc_service_pb2_grpc

logger = logging.getLogger(__name__)

# Default RVC server port
DEFAULT_RVC_PORT = 50051


@dataclass
class RVCConvertResult:
    """Result of a direct audio conversion."""
    success: bool
    audio: Optional[np.ndarray] = None
    sample_rate: int = 16000
    processing_time: float = 0.0
    worker_id: int = -1
    error: Optional[str] = None


@dataclass
class RVCJobResult:
    """Result of a file-based job."""
    success: bool
    job_id: int = -1
    output_path: Optional[str] = None
    processing_time: float = 0.0
    worker_id: int = -1
    error: Optional[str] = None
    timed_out: bool = False


class RVCGrpcClient:
    """
    gRPC client for RVC voice conversion server.

    Mirrors the TritonSparkClient interface for consistency:
    - connect() / close() for connection management
    - is_server_ready() for health checks
    - convert() for direct audio conversion
    - submit_job() / get_result() for async file-based processing
    """

    def __init__(
        self,
        host: str = None,
        port: int = None,
        timeout: float = 30.0,
    ):
        """
        Initialize RVC gRPC client.

        Args:
            host: Server host. Default from RVC_SERVER_HOST env or "localhost".
            port: Server port. Default from RVC_SERVER_PORT env or 50051.
            timeout: Default timeout for operations in seconds.
        """
        self.host = host or os.environ.get("RVC_SERVER_HOST", "localhost")
        self.port = port or int(os.environ.get("RVC_SERVER_PORT", str(DEFAULT_RVC_PORT)))
        self.timeout = timeout

        self._channel: Optional[grpc.Channel] = None
        self._stub: Optional[rvc_service_pb2_grpc.RVCServiceStub] = None

        logger.info(f"RVCGrpcClient initialized: {self.host}:{self.port}")

    def _ensure_connected(self):
        """Ensure client is connected to server."""
        if self._channel is None:
            self._channel = grpc.insecure_channel(
                f"{self.host}:{self.port}",
                options=[
                    ('grpc.max_send_message_length', 50 * 1024 * 1024),  # 50MB
                    ('grpc.max_receive_message_length', 50 * 1024 * 1024),
                ],
            )
            self._stub = rvc_service_pb2_grpc.RVCServiceStub(self._channel)
            logger.debug(f"Connected to RVC server at {self.host}:{self.port}")

    def connect(self) -> bool:
        """Explicitly connect to server. Returns True if healthy."""
        try:
            self._ensure_connected()
            return self.is_server_ready()
        except Exception as e:
            logger.warning(f"Failed to connect: {e}")
            return False

    def close(self):
        """Close the client connection."""
        if self._channel is not None:
            self._channel.close()
            self._channel = None
            self._stub = None
            logger.debug("RVC client connection closed")

    def is_server_ready(self) -> bool:
        """Check if server is ready to accept requests."""
        try:
            self._ensure_connected()
            response = self._stub.HealthCheck(
                rvc_service_pb2.HealthRequest(),
                timeout=5.0,
            )
            return response.healthy and response.status == "ready"
        except Exception as e:
            logger.warning(f"Health check failed: {e}")
            return False

    def is_server_live(self) -> bool:
        """Check if server is reachable (may still be loading)."""
        try:
            self._ensure_connected()
            response = self._stub.HealthCheck(
                rvc_service_pb2.HealthRequest(),
                timeout=5.0,
            )
            return response.status in ("ready", "loading")
        except Exception:
            return False

    def get_status(self) -> dict:
        """Get detailed server status."""
        try:
            self._ensure_connected()
            response = self._stub.GetStatus(
                rvc_service_pb2.StatusRequest(),
                timeout=self.timeout,
            )
            return {
                "running": response.running,
                "model": response.model_name,
                "num_workers": response.num_workers,
                "workers_alive": response.workers_alive,
                "jobs_submitted": response.jobs_submitted,
                "jobs_completed": response.jobs_completed,
                "uptime": response.uptime,
            }
        except Exception as e:
            logger.warning(f"Get status failed: {e}")
            return {"running": False, "error": str(e)}

    def convert(
        self,
        audio: Union[bytes, np.ndarray, str],
        sample_rate: int = 16000,
        pitch_shift: int = 0,
        f0_method: str = "rmvpe",
        index_rate: float = 0.75,
        filter_radius: int = 3,
        resample_sr: int = 0,
        rms_mix_rate: float = 0.25,
        protect: float = 0.33,
        request_id: str = "",
    ) -> RVCConvertResult:
        """
        Convert audio using RVC model.

        Args:
            audio: Audio data - file path, WAV bytes, or numpy array
            sample_rate: Sample rate (required if numpy array)
            pitch_shift: Pitch shift in semitones (-12 to +12)
            f0_method: F0 extraction method
            index_rate: Voice similarity (0.0 to 1.0)
            filter_radius: Median filter radius (0-7)
            resample_sr: Output sample rate (0 = same as input)
            rms_mix_rate: Volume envelope mixing (0.0 to 1.0)
            protect: Protect voiceless consonants (0.0 to 0.5)
            request_id: Optional request ID for tracking

        Returns:
            RVCConvertResult with converted audio
        """
        self._ensure_connected()

        # Prepare audio data
        if isinstance(audio, str):
            # File path - read and convert to WAV bytes
            audio_array, sr = sf.read(audio)
            sample_rate = sr
            audio_io = io.BytesIO()
            sf.write(audio_io, audio_array, sample_rate, format='WAV')
            audio_bytes = audio_io.getvalue()
            audio_format = rvc_service_pb2.WAV
        elif isinstance(audio, np.ndarray):
            # Numpy array - convert to WAV bytes
            audio_io = io.BytesIO()
            sf.write(audio_io, audio, sample_rate, format='WAV')
            audio_bytes = audio_io.getvalue()
            audio_format = rvc_service_pb2.WAV
        else:
            # Assume WAV bytes
            audio_bytes = audio
            audio_format = rvc_service_pb2.WAV

        try:
            response = self._stub.Convert(
                rvc_service_pb2.ConvertRequest(
                    audio_data=audio_bytes,
                    format=audio_format,
                    sample_rate=sample_rate,
                    pitch_shift=pitch_shift,
                    f0_method=f0_method,
                    index_rate=index_rate,
                    filter_radius=filter_radius,
                    resample_sr=resample_sr,
                    rms_mix_rate=rms_mix_rate,
                    protect=protect,
                    request_id=request_id,
                ),
                timeout=self.timeout,
            )

            if response.success:
                # Parse output audio
                audio_io = io.BytesIO(response.audio_data)
                output_audio, out_sr = sf.read(audio_io)

                return RVCConvertResult(
                    success=True,
                    audio=output_audio,
                    sample_rate=out_sr,
                    processing_time=response.processing_time,
                    worker_id=response.worker_id,
                )
            else:
                return RVCConvertResult(
                    success=False,
                    error=response.error,
                )

        except grpc.RpcError as e:
            logger.error(f"Convert RPC error: {e}")
            return RVCConvertResult(
                success=False,
                error=str(e),
            )

    def submit_job(
        self,
        input_path: str,
        output_path: str,
        pitch_shift: int = 0,
        f0_method: str = "rmvpe",
        index_rate: float = 0.75,
        filter_radius: int = 3,
        resample_sr: int = 0,
        rms_mix_rate: float = 0.25,
        protect: float = 0.33,
    ) -> int:
        """
        Submit a file-based job for async processing.

        Args:
            input_path: Path to input audio file
            output_path: Path for output audio file
            ... (same params as convert)

        Returns:
            Job ID for tracking

        Raises:
            RuntimeError if submission fails
        """
        self._ensure_connected()

        try:
            response = self._stub.SubmitJob(
                rvc_service_pb2.SubmitJobRequest(
                    input_path=input_path,
                    output_path=output_path,
                    pitch_shift=pitch_shift,
                    f0_method=f0_method,
                    index_rate=index_rate,
                    filter_radius=filter_radius,
                    resample_sr=resample_sr,
                    rms_mix_rate=rms_mix_rate,
                    protect=protect,
                ),
                timeout=self.timeout,
            )

            if response.success:
                return response.job_id
            else:
                raise RuntimeError(f"Job submission failed: {response.error}")

        except grpc.RpcError as e:
            raise RuntimeError(f"Submit job RPC error: {e}")

    def get_result(self, job_id: int = 0, timeout: float = None) -> Optional[RVCJobResult]:
        """
        Get result of a submitted job.

        Args:
            job_id: Specific job ID (0 = get any completed result)
            timeout: Max wait time (default: self.timeout)

        Returns:
            RVCJobResult or None if timed out
        """
        self._ensure_connected()

        try:
            response = self._stub.GetResult(
                rvc_service_pb2.GetResultRequest(
                    job_id=job_id,
                    timeout=timeout or self.timeout,
                ),
                timeout=(timeout or self.timeout) + 5,  # Add buffer for RPC
            )

            if response.timed_out:
                return None

            return RVCJobResult(
                success=response.success,
                job_id=response.job_id,
                output_path=response.output_path or None,
                processing_time=response.processing_time,
                worker_id=response.worker_id,
                error=response.error or None,
            )

        except grpc.RpcError as e:
            logger.error(f"Get result RPC error: {e}")
            return RVCJobResult(
                success=False,
                error=str(e),
            )

    def __enter__(self):
        """Context manager entry."""
        self._ensure_connected()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()

    def __del__(self):
        """Destructor - ensure connection is closed."""
        self.close()


def get_rvc_grpc_client(
    host: str = None,
    port: int = None,
) -> Optional[RVCGrpcClient]:
    """
    Get a connected RVC gRPC client, or None if server not available.

    Convenience function that checks if server is ready before returning.
    """
    client = RVCGrpcClient(host=host, port=port)
    if client.connect():
        return client
    client.close()
    return None
