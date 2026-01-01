"""
Triton Client Wrapper for Spark TTS

Provides a simple interface to Triton Inference Server running Spark TTS.
Designed to match the SparkTTS.inference() API signature for easy integration.

Usage:
    from triton_client import TritonSparkClient

    # Initialize client
    client = TritonSparkClient(server_addr="localhost", server_port=8001)

    # Run inference (same signature as SparkTTS.inference)
    wav = client.inference(
        text="Hello world",
        prompt_speech="reference.wav",  # or numpy array
        prompt_text="Reference text",
    )

    # Save output
    import soundfile as sf
    sf.write("output.wav", wav, 16000)
"""

import os
import logging
from typing import Union, Optional

import numpy as np
import soundfile as sf
import tritonclient.grpc as grpcclient
from tritonclient.utils import np_to_triton_dtype

logger = logging.getLogger(__name__)

# Spark TTS output sample rate
SPARK_SAMPLE_RATE = 16000


class TritonSparkClient:
    """
    Triton client wrapper for Spark TTS inference.

    Provides the same interface as SparkTTS for drop-in replacement.
    """

    def __init__(
        self,
        server_addr: str = None,
        server_port: int = None,
        model_name: str = "spark_tts",
        verbose: bool = False,
    ):
        """
        Initialize Triton client.

        Args:
            server_addr: Triton server address. Default from TRITON_SERVER_ADDR env or "localhost".
            server_port: Triton gRPC port. Default from TRITON_SERVER_PORT env or 8001.
            model_name: Name of the model in Triton model repository.
            verbose: Enable verbose logging from Triton client.
        """
        self.server_addr = server_addr or os.environ.get("TRITON_SERVER_ADDR", "localhost")
        self.server_port = server_port or int(os.environ.get("TRITON_SERVER_PORT", "8001"))
        self.model_name = model_name
        self.verbose = verbose

        self._url = f"{self.server_addr}:{self.server_port}"
        self._client = None

        logger.info(f"TritonSparkClient initialized: {self._url}, model={self.model_name}")

    def _ensure_connected(self):
        """Ensure client is connected to server."""
        if self._client is None:
            self._client = grpcclient.InferenceServerClient(
                url=self._url,
                verbose=self.verbose
            )
            # Check server is live
            if not self._client.is_server_live():
                raise ConnectionError(f"Triton server at {self._url} is not live")
            logger.info(f"Connected to Triton server at {self._url}")

    def _load_audio(self, audio_path: str, target_sr: int = 16000) -> np.ndarray:
        """Load audio file and resample if needed."""
        waveform, sample_rate = sf.read(audio_path)

        # Convert stereo to mono if needed
        if len(waveform.shape) > 1:
            waveform = waveform.mean(axis=1)

        # Resample if needed
        if sample_rate != target_sr:
            from scipy.signal import resample
            num_samples = int(len(waveform) * (target_sr / sample_rate))
            waveform = resample(waveform, num_samples)

        return waveform.astype(np.float32)

    def _prepare_inputs(
        self,
        reference_wav: np.ndarray,
        reference_text: str,
        target_text: str,
    ) -> tuple:
        """Prepare Triton inference inputs."""
        # Ensure 1D array
        if len(reference_wav.shape) > 1:
            reference_wav = reference_wav.flatten()

        # Prepare wav input with shape (1, num_samples)
        samples = reference_wav.reshape(1, -1).astype(np.float32)
        lengths = np.array([[len(reference_wav)]], dtype=np.int32)

        # Create inputs
        inputs = [
            grpcclient.InferInput(
                "reference_wav",
                samples.shape,
                np_to_triton_dtype(samples.dtype)
            ),
            grpcclient.InferInput(
                "reference_wav_len",
                lengths.shape,
                np_to_triton_dtype(lengths.dtype)
            ),
            grpcclient.InferInput("reference_text", [1, 1], "BYTES"),
            grpcclient.InferInput("target_text", [1, 1], "BYTES"),
        ]

        inputs[0].set_data_from_numpy(samples)
        inputs[1].set_data_from_numpy(lengths)

        # Text inputs
        ref_text_np = np.array([reference_text], dtype=object).reshape(1, 1)
        inputs[2].set_data_from_numpy(ref_text_np)

        tgt_text_np = np.array([target_text], dtype=object).reshape(1, 1)
        inputs[3].set_data_from_numpy(tgt_text_np)

        # Output
        outputs = [grpcclient.InferRequestedOutput("waveform")]

        return inputs, outputs

    def inference(
        self,
        text: str,
        prompt_speech: Union[str, np.ndarray],
        prompt_text: str,
        gender: Optional[str] = None,
        pitch: Optional[float] = None,
        speed: Optional[float] = None,
    ) -> np.ndarray:
        """
        Run TTS inference via Triton server.

        This method has the same signature as SparkTTS.inference() for compatibility.

        Args:
            text: Target text to synthesize.
            prompt_speech: Reference audio - file path or numpy array (16kHz).
            prompt_text: Transcript of the reference audio.
            gender: (Unused) Gender parameter for compatibility.
            pitch: (Unused) Pitch parameter for compatibility.
            speed: (Unused) Speed parameter for compatibility.

        Returns:
            np.ndarray: Generated audio waveform at 16kHz.

        Note:
            gender, pitch, speed parameters are accepted for API compatibility
            but not currently supported by Triton Spark TTS deployment.
        """
        self._ensure_connected()

        # Load reference audio if path provided
        if isinstance(prompt_speech, str):
            reference_wav = self._load_audio(prompt_speech, SPARK_SAMPLE_RATE)
        else:
            reference_wav = prompt_speech.astype(np.float32)

        # Prepare inputs
        inputs, outputs = self._prepare_inputs(
            reference_wav=reference_wav,
            reference_text=prompt_text,
            target_text=text,
        )

        # Run inference
        logger.debug(f"Running Triton inference: text='{text[:50]}...'")
        response = self._client.infer(
            model_name=self.model_name,
            inputs=inputs,
            outputs=outputs,
        )

        # Extract audio
        audio = response.as_numpy("waveform").reshape(-1)
        logger.debug(f"Inference complete: {len(audio)} samples ({len(audio)/SPARK_SAMPLE_RATE:.2f}s)")

        return audio

    def is_server_ready(self) -> bool:
        """Check if Triton server is ready to accept requests."""
        try:
            self._ensure_connected()
            return self._client.is_server_ready()
        except Exception as e:
            logger.warning(f"Server ready check failed: {e}")
            return False

    def is_model_ready(self) -> bool:
        """Check if the Spark TTS model is loaded and ready."""
        try:
            self._ensure_connected()
            return self._client.is_model_ready(self.model_name)
        except Exception as e:
            logger.warning(f"Model ready check failed: {e}")
            return False

    def get_model_metadata(self) -> dict:
        """Get model metadata from Triton server."""
        self._ensure_connected()
        return self._client.get_model_metadata(self.model_name, as_json=True)

    def close(self):
        """Close the client connection."""
        if self._client is not None:
            try:
                self._client.close()
            except Exception as e:
                logger.warning(f"Error closing client: {e}")
            self._client = None
            logger.info("Triton client closed")

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


# Convenience function for one-shot inference
def triton_tts(
    text: str,
    prompt_speech: Union[str, np.ndarray],
    prompt_text: str,
    server_addr: str = "localhost",
    server_port: int = 8001,
) -> np.ndarray:
    """
    One-shot TTS inference via Triton.

    Args:
        text: Text to synthesize.
        prompt_speech: Reference audio path or numpy array.
        prompt_text: Reference audio transcript.
        server_addr: Triton server address.
        server_port: Triton gRPC port.

    Returns:
        np.ndarray: Generated audio at 16kHz.
    """
    with TritonSparkClient(server_addr, server_port) as client:
        return client.inference(text, prompt_speech, prompt_text)
