"""RVC gRPC Service module.

NOTE: For external API access, use the HTTP API (rvc.api.voice_api) instead.
gRPC is used internally for Triton communication only.

The unified voice service exposes both TTS and RVC via HTTP:
- POST /synthesize - Full TTS + RVC pipeline
- POST /tts - TTS only
- POST /rvc - RVC only
- GET /health - Health check
- GET /status - Detailed status
"""

# Unified TTS+RVC gRPC service (internal use)
from .voice_server import VoiceServicer, serve as serve_voice
from .voice_client import VoiceClient, get_voice_client, synthesize, SynthesisResult, ServiceStatus

# Proto generation utility
from .generate_proto import generate_protos

__all__ = [
    # Unified gRPC service (internal use only)
    "VoiceServicer",
    "serve_voice",
    "VoiceClient",
    "get_voice_client",
    "synthesize",
    "SynthesisResult",
    "ServiceStatus",
    # Utility
    "generate_protos",
]
