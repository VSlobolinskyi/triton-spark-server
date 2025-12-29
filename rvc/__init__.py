"""
RVC (Retrieval-based Voice Conversion) Module

This module provides voice conversion functionality integrated with Triton Spark TTS.

Quick Start:
    from rvc import init_rvc, load_model, convert_audio

    # Initialize RVC
    init_rvc()

    # Load a voice model
    load_model("SilverWolf.pth")

    # Convert audio
    info, (sr, audio) = convert_audio("input.wav")

For Triton TTS:
    from rvc import TritonSparkClient

    client = TritonSparkClient()
    wav = client.inference("Hello world", "reference.wav", "Reference text")
"""

from rvc.rvc_init import (
    init_rvc,
    get_vc,
    get_config,
    is_initialized,
    load_model,
    convert_audio,
    convert_audio_batch,
    cleanup,
)

from rvc.rvc_config import RVCConfig, get_config as get_rvc_config
from rvc.rvc_modules import VC
from rvc.triton_client import TritonSparkClient, triton_tts

__all__ = [
    # Initialization
    "init_rvc",
    "get_vc",
    "get_config",
    "is_initialized",
    "cleanup",
    # Conversion
    "load_model",
    "convert_audio",
    "convert_audio_batch",
    # Classes
    "RVCConfig",
    "VC",
    "TritonSparkClient",
    # Convenience
    "triton_tts",
    "get_rvc_config",
]
