"""
Unified Voice Service Client

Client for communicating with the unified TTS+RVC voice service.
Provides simple API for text-to-speech with voice conversion.

Usage:
    from rvc.grpc import VoiceClient

    client = VoiceClient(host="localhost", port=50052)

    # Simple synthesis
    audio = client.synthesize(
        text="Hello world",
        reference_audio="reference.wav",
        reference_text="Reference text",
    )

    # Streaming synthesis (yields audio chunks per sentence)
    for chunk in client.synthesize_stream(text, reference_audio, reference_text):
        play_audio(chunk.audio)
"""

import os
import io
import logging
from typing import Optional, Union, Iterator, List
from dataclasses import dataclass

import grpc
import numpy as np
import soundfile as sf

# Import generated proto modules
try:
    from . import voice_service_pb2
    from . import voice_service_pb2_grpc
except ImportError:
    import voice_service_pb2
    import voice_service_pb2_grpc

logger = logging.getLogger(__name__)

DEFAULT_PORT = 50052


@dataclass
class SynthesisResult:
    """Result of a synthesis request."""
    success: bool
    audio: Optional[np.ndarray] = None
    sample_rate: int = 16000
    tts_time: float = 0.0
    rvc_time: float = 0.0
    total_time: float = 0.0
    rvc_worker_id: int = -1
    sentence_index: int = 0
    sentence_text: str = ""
    is_final: bool = True
    error: Optional[str] = None


@dataclass
class ServiceStatus:
    """Voice service status."""
    running: bool
    tts_ready: bool
    tts_model: str
    triton_server: str
    rvc_ready: bool
    rvc_model: str
    rvc_workers: int
    rvc_workers_alive: int
    total_requests: int
    successful_requests: int
    failed_requests: int
    uptime: float


class VoiceClient:
    """
    Client for unified voice synthesis service.

    Provides text-to-speech with voice conversion in a single call.
    """

    def __init__(
        self,
        host: str = None,
        port: int = None,
        timeout: float = 60.0,
    ):
        """
        Initialize voice client.

        Args:
            host: Server host. Default from VOICE_SERVER_HOST env or "localhost".
            port: Server port. Default from VOICE_SERVER_PORT env or 50052.
            timeout: Default timeout for operations in seconds.
        """
        self.host = host or os.environ.get("VOICE_SERVER_HOST", "localhost")
        self.port = port or int(os.environ.get("VOICE_SERVER_PORT", str(DEFAULT_PORT)))
        self.timeout = timeout

        self._channel: Optional[grpc.Channel] = None
        self._stub: Optional[voice_service_pb2_grpc.VoiceServiceStub] = None

        logger.info(f"VoiceClient initialized: {self.host}:{self.port}")

    def _ensure_connected(self):
        """Ensure client is connected to server."""
        if self._channel is None:
            self._channel = grpc.insecure_channel(
                f"{self.host}:{self.port}",
                options=[
                    ('grpc.max_send_message_length', 100 * 1024 * 1024),  # 100MB
                    ('grpc.max_receive_message_length', 100 * 1024 * 1024),
                ],
            )
            self._stub = voice_service_pb2_grpc.VoiceServiceStub(self._channel)
            logger.debug(f"Connected to voice server at {self.host}:{self.port}")

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
            logger.debug("Voice client connection closed")

    def is_server_ready(self) -> bool:
        """Check if server is ready to accept requests."""
        try:
            self._ensure_connected()
            response = self._stub.HealthCheck(
                voice_service_pb2.HealthRequest(),
                timeout=5.0,
            )
            return response.healthy
        except Exception as e:
            logger.warning(f"Health check failed: {e}")
            return False

    def get_status(self) -> ServiceStatus:
        """Get detailed server status."""
        self._ensure_connected()

        response = self._stub.GetStatus(
            voice_service_pb2.StatusRequest(),
            timeout=self.timeout,
        )

        return ServiceStatus(
            running=response.running,
            tts_ready=response.tts_ready,
            tts_model=response.tts_model,
            triton_server=response.triton_server,
            rvc_ready=response.rvc_ready,
            rvc_model=response.rvc_model,
            rvc_workers=response.rvc_workers,
            rvc_workers_alive=response.rvc_workers_alive,
            total_requests=response.total_requests,
            successful_requests=response.successful_requests,
            failed_requests=response.failed_requests,
            uptime=response.uptime,
        )

    def _prepare_reference_audio(
        self,
        reference_audio: Union[str, bytes, np.ndarray],
    ) -> tuple:
        """Prepare reference audio for request. Returns (bytes, format, sample_rate)."""
        if isinstance(reference_audio, str):
            # File path - read and convert to bytes
            audio, sr = sf.read(reference_audio)
            audio_io = io.BytesIO()
            sf.write(audio_io, audio, sr, format='WAV')
            return audio_io.getvalue(), voice_service_pb2.WAV, sr
        elif isinstance(reference_audio, np.ndarray):
            # Numpy array - convert to WAV bytes
            audio_io = io.BytesIO()
            sf.write(audio_io, reference_audio, 16000, format='WAV')
            return audio_io.getvalue(), voice_service_pb2.WAV, 16000
        else:
            # Assume bytes
            return reference_audio, voice_service_pb2.WAV, 16000

    def _parse_audio_response(self, audio_data: bytes) -> np.ndarray:
        """Parse audio bytes from response."""
        audio_io = io.BytesIO(audio_data)
        audio, _ = sf.read(audio_io)
        return audio.astype(np.float32)

    def synthesize(
        self,
        text: str,
        reference_audio: Union[str, bytes, np.ndarray],
        reference_text: str,
        pitch_shift: int = 0,
        f0_method: str = "rmvpe",
        index_rate: float = 0.75,
        filter_radius: int = 3,
        resample_sr: int = 0,
        rms_mix_rate: float = 0.25,
        protect: float = 0.33,
        skip_rvc: bool = False,
        request_id: str = "",
    ) -> SynthesisResult:
        """
        Synthesize text with voice conversion.

        Args:
            text: Text to synthesize
            reference_audio: Reference audio for voice cloning (path, bytes, or array)
            reference_text: Transcript of reference audio
            pitch_shift: Pitch shift in semitones (-12 to +12)
            f0_method: F0 extraction method
            index_rate: Voice similarity (0.0 to 1.0)
            filter_radius: Median filter radius (0-7)
            resample_sr: Output sample rate (0 = 16000)
            rms_mix_rate: Volume envelope mixing
            protect: Protect voiceless consonants
            skip_rvc: If True, return TTS output without RVC
            request_id: Optional request ID for tracking

        Returns:
            SynthesisResult with audio and timing info
        """
        self._ensure_connected()

        # Prepare reference audio
        ref_bytes, ref_format, ref_sr = self._prepare_reference_audio(reference_audio)

        try:
            response = self._stub.Synthesize(
                voice_service_pb2.SynthesizeRequest(
                    text=text,
                    reference_audio=ref_bytes,
                    reference_format=ref_format,
                    reference_sample_rate=ref_sr,
                    reference_text=reference_text,
                    pitch_shift=pitch_shift,
                    f0_method=f0_method,
                    index_rate=index_rate,
                    filter_radius=filter_radius,
                    resample_sr=resample_sr,
                    rms_mix_rate=rms_mix_rate,
                    protect=protect,
                    skip_rvc=skip_rvc,
                    request_id=request_id,
                ),
                timeout=self.timeout,
            )

            if response.success:
                return SynthesisResult(
                    success=True,
                    audio=self._parse_audio_response(response.audio_data),
                    sample_rate=response.sample_rate,
                    tts_time=response.tts_time,
                    rvc_time=response.rvc_time,
                    total_time=response.total_time,
                    rvc_worker_id=response.rvc_worker_id,
                )
            else:
                return SynthesisResult(
                    success=False,
                    error=response.error,
                )

        except grpc.RpcError as e:
            logger.error(f"Synthesize RPC error: {e}")
            return SynthesisResult(
                success=False,
                error=str(e),
            )

    def synthesize_stream(
        self,
        text: str,
        reference_audio: Union[str, bytes, np.ndarray],
        reference_text: str,
        pitch_shift: int = 0,
        f0_method: str = "rmvpe",
        index_rate: float = 0.75,
        filter_radius: int = 3,
        resample_sr: int = 0,
        rms_mix_rate: float = 0.25,
        protect: float = 0.33,
        skip_rvc: bool = False,
        request_id: str = "",
    ) -> Iterator[SynthesisResult]:
        """
        Stream synthesis - yields results per sentence as they complete.

        Args:
            Same as synthesize()

        Yields:
            SynthesisResult for each sentence
        """
        self._ensure_connected()

        ref_bytes, ref_format, ref_sr = self._prepare_reference_audio(reference_audio)

        try:
            responses = self._stub.SynthesizeStream(
                voice_service_pb2.SynthesizeRequest(
                    text=text,
                    reference_audio=ref_bytes,
                    reference_format=ref_format,
                    reference_sample_rate=ref_sr,
                    reference_text=reference_text,
                    pitch_shift=pitch_shift,
                    f0_method=f0_method,
                    index_rate=index_rate,
                    filter_radius=filter_radius,
                    resample_sr=resample_sr,
                    rms_mix_rate=rms_mix_rate,
                    protect=protect,
                    skip_rvc=skip_rvc,
                    request_id=request_id,
                ),
                timeout=self.timeout * 10,  # Longer timeout for streaming
            )

            for response in responses:
                if response.success:
                    yield SynthesisResult(
                        success=True,
                        audio=self._parse_audio_response(response.audio_data),
                        sample_rate=response.sample_rate,
                        tts_time=response.tts_time,
                        rvc_time=response.rvc_time,
                        total_time=response.total_time,
                        rvc_worker_id=response.rvc_worker_id,
                        sentence_index=response.sentence_index,
                        sentence_text=response.sentence_text,
                        is_final=response.is_final,
                    )
                else:
                    yield SynthesisResult(
                        success=False,
                        error=response.error,
                        sentence_index=response.sentence_index,
                        sentence_text=response.sentence_text,
                        is_final=response.is_final,
                    )

        except grpc.RpcError as e:
            logger.error(f"SynthesizeStream RPC error: {e}")
            yield SynthesisResult(
                success=False,
                error=str(e),
            )

    def synthesize_batch(
        self,
        texts: List[str],
        reference_audio: Union[str, bytes, np.ndarray],
        reference_text: str,
        pitch_shift: int = 0,
        f0_method: str = "rmvpe",
        **kwargs,
    ) -> Iterator[SynthesisResult]:
        """
        Batch synthesis - process multiple texts with shared reference.

        Args:
            texts: List of texts to synthesize
            reference_audio: Shared reference audio
            reference_text: Reference transcript
            ...other params same as synthesize()

        Yields:
            SynthesisResult for each text
        """
        self._ensure_connected()

        ref_bytes, ref_format, ref_sr = self._prepare_reference_audio(reference_audio)

        try:
            responses = self._stub.SynthesizeBatch(
                voice_service_pb2.BatchSynthesizeRequest(
                    texts=texts,
                    reference_audio=ref_bytes,
                    reference_format=ref_format,
                    reference_sample_rate=ref_sr,
                    reference_text=reference_text,
                    pitch_shift=pitch_shift,
                    f0_method=f0_method,
                    index_rate=kwargs.get('index_rate', 0.75),
                    filter_radius=kwargs.get('filter_radius', 3),
                    resample_sr=kwargs.get('resample_sr', 0),
                    rms_mix_rate=kwargs.get('rms_mix_rate', 0.25),
                    protect=kwargs.get('protect', 0.33),
                    skip_rvc=kwargs.get('skip_rvc', False),
                    request_id=kwargs.get('request_id', ''),
                ),
                timeout=self.timeout * len(texts),
            )

            for response in responses:
                if response.success:
                    yield SynthesisResult(
                        success=True,
                        audio=self._parse_audio_response(response.audio_data),
                        sample_rate=response.sample_rate,
                        tts_time=response.tts_time,
                        rvc_time=response.rvc_time,
                        total_time=response.total_time,
                        rvc_worker_id=response.rvc_worker_id,
                        sentence_index=response.sentence_index,
                        sentence_text=response.sentence_text,
                        is_final=response.is_final,
                    )
                else:
                    yield SynthesisResult(
                        success=False,
                        error=response.error,
                        sentence_index=response.sentence_index,
                        sentence_text=response.sentence_text,
                        is_final=response.is_final,
                    )

        except grpc.RpcError as e:
            logger.error(f"SynthesizeBatch RPC error: {e}")
            yield SynthesisResult(
                success=False,
                error=str(e),
            )

    def tts_only(
        self,
        text: str,
        reference_audio: Union[str, bytes, np.ndarray],
        reference_text: str,
        request_id: str = "",
    ) -> SynthesisResult:
        """TTS without RVC (for testing/comparison)."""
        self._ensure_connected()

        ref_bytes, ref_format, ref_sr = self._prepare_reference_audio(reference_audio)

        try:
            response = self._stub.TTSOnly(
                voice_service_pb2.TTSRequest(
                    text=text,
                    reference_audio=ref_bytes,
                    reference_format=ref_format,
                    reference_sample_rate=ref_sr,
                    reference_text=reference_text,
                    request_id=request_id,
                ),
                timeout=self.timeout,
            )

            if response.success:
                return SynthesisResult(
                    success=True,
                    audio=self._parse_audio_response(response.audio_data),
                    sample_rate=response.sample_rate,
                    tts_time=response.processing_time,
                    total_time=response.processing_time,
                )
            else:
                return SynthesisResult(
                    success=False,
                    error=response.error,
                )

        except grpc.RpcError as e:
            logger.error(f"TTSOnly RPC error: {e}")
            return SynthesisResult(
                success=False,
                error=str(e),
            )

    def rvc_only(
        self,
        audio: Union[str, bytes, np.ndarray],
        pitch_shift: int = 0,
        f0_method: str = "rmvpe",
        **kwargs,
    ) -> SynthesisResult:
        """RVC conversion only (for existing audio)."""
        self._ensure_connected()

        # Prepare audio
        if isinstance(audio, str):
            audio_array, sr = sf.read(audio)
            audio_io = io.BytesIO()
            sf.write(audio_io, audio_array, sr, format='WAV')
            audio_bytes = audio_io.getvalue()
        elif isinstance(audio, np.ndarray):
            audio_io = io.BytesIO()
            sf.write(audio_io, audio, 16000, format='WAV')
            audio_bytes = audio_io.getvalue()
        else:
            audio_bytes = audio

        try:
            response = self._stub.RVCOnly(
                voice_service_pb2.RVCRequest(
                    audio_data=audio_bytes,
                    format=voice_service_pb2.WAV,
                    sample_rate=16000,
                    pitch_shift=pitch_shift,
                    f0_method=f0_method,
                    index_rate=kwargs.get('index_rate', 0.75),
                    filter_radius=kwargs.get('filter_radius', 3),
                    resample_sr=kwargs.get('resample_sr', 0),
                    rms_mix_rate=kwargs.get('rms_mix_rate', 0.25),
                    protect=kwargs.get('protect', 0.33),
                    request_id=kwargs.get('request_id', ''),
                ),
                timeout=self.timeout,
            )

            if response.success:
                return SynthesisResult(
                    success=True,
                    audio=self._parse_audio_response(response.audio_data),
                    sample_rate=response.sample_rate,
                    rvc_time=response.processing_time,
                    total_time=response.processing_time,
                    rvc_worker_id=response.worker_id,
                )
            else:
                return SynthesisResult(
                    success=False,
                    error=response.error,
                )

        except grpc.RpcError as e:
            logger.error(f"RVCOnly RPC error: {e}")
            return SynthesisResult(
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
        """Destructor."""
        self.close()


def get_voice_client(
    host: str = None,
    port: int = None,
) -> Optional[VoiceClient]:
    """
    Get a connected voice client, or None if server not available.
    """
    client = VoiceClient(host=host, port=port)
    if client.connect():
        return client
    client.close()
    return None


# Convenience function for one-shot synthesis
def synthesize(
    text: str,
    reference_audio: Union[str, bytes, np.ndarray],
    reference_text: str,
    host: str = "localhost",
    port: int = DEFAULT_PORT,
    **kwargs,
) -> np.ndarray:
    """
    One-shot voice synthesis.

    Args:
        text: Text to synthesize
        reference_audio: Reference audio for cloning
        reference_text: Reference transcript
        host: Server host
        port: Server port
        **kwargs: Additional synthesis parameters

    Returns:
        np.ndarray: Generated audio at 16kHz

    Raises:
        RuntimeError: If synthesis fails
    """
    with VoiceClient(host, port) as client:
        result = client.synthesize(
            text=text,
            reference_audio=reference_audio,
            reference_text=reference_text,
            **kwargs,
        )
        if result.success:
            return result.audio
        else:
            raise RuntimeError(f"Synthesis failed: {result.error}")
