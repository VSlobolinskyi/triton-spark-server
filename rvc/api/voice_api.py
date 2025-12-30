"""
Voice Synthesis HTTP API

FastAPI server that exposes TTS + RVC as a simple HTTP API.
Internally uses Triton (gRPC) for TTS and direct RVC inference.

Usage:
    python -m rvc.api.voice_api \
        --rvc-model SilverWolf.pth \
        --rvc-workers 2 \
        --triton-addr localhost \
        --port 8000

Endpoints:
    POST /synthesize           - Text to voice-converted speech (single WAV)
    POST /synthesize/stream    - Streaming per-sentence chunks (for real-time playback)
    POST /tts                  - TTS only (no RVC)
    POST /rvc                  - RVC only (convert audio)
    GET  /health               - Health check
    GET  /status               - Detailed status
"""

import os
import sys
import io
import re
import time
import logging
import argparse
import tempfile
from typing import Optional, List
from contextlib import asynccontextmanager

import numpy as np
import soundfile as sf
from fastapi import FastAPI, HTTPException, UploadFile, File, Form, BackgroundTasks
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel, Field
import uvicorn

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from rvc.triton_client import TritonSparkClient
from rvc.server.rvc_server import RVCServer

logger = logging.getLogger(__name__)

# Global instances
_tts_client: Optional[TritonSparkClient] = None
_rvc_server: Optional[RVCServer] = None
_config = {}
_stats = {
    "requests": 0,
    "successful": 0,
    "failed": 0,
    "start_time": None,
}


# ============================================================================
# Request/Response Models
# ============================================================================

class SynthesizeRequest(BaseModel):
    """Request for voice synthesis."""
    text: str = Field(..., description="Text to synthesize")
    reference_text: str = Field("", description="Transcript of reference audio (optional)")
    pitch_shift: int = Field(0, ge=-12, le=12, description="Pitch shift in semitones")
    f0_method: str = Field("rmvpe", description="F0 extraction method")
    index_rate: float = Field(0.75, ge=0, le=1, description="Voice similarity")
    skip_rvc: bool = Field(False, description="Skip RVC, return TTS output only")


class SynthesizeResponse(BaseModel):
    """Response metadata for synthesis."""
    success: bool
    tts_time: float = 0.0
    rvc_time: float = 0.0
    total_time: float = 0.0
    audio_duration: float = 0.0
    sample_rate: int = 16000
    error: Optional[str] = None


class HealthResponse(BaseModel):
    """Health check response."""
    healthy: bool
    status: str
    tts_ready: bool
    rvc_ready: bool
    message: str = ""


class StatusResponse(BaseModel):
    """Detailed status response."""
    running: bool
    tts_ready: bool
    tts_model: str = "spark_tts"
    triton_server: str = ""
    rvc_ready: bool
    rvc_model: str = ""
    rvc_workers: int = 0
    rvc_workers_alive: int = 0
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    uptime: float = 0.0


# ============================================================================
# Lifespan Management
# ============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize and cleanup resources."""
    global _tts_client, _rvc_server, _stats

    logger.info("=" * 60)
    logger.info("Voice API Starting")
    logger.info("=" * 60)

    # Initialize TTS client
    triton_addr = _config.get("triton_addr", "localhost")
    triton_port = _config.get("triton_port", 8001)

    logger.info(f"Connecting to Triton at {triton_addr}:{triton_port}")
    _tts_client = TritonSparkClient(
        server_addr=triton_addr,
        server_port=triton_port,
    )

    if not _tts_client.is_server_ready():
        logger.warning("Triton server not ready - TTS will be unavailable")
    else:
        logger.info("Triton TTS connected")

    # Initialize RVC server
    rvc_model = _config.get("rvc_model")
    rvc_workers = _config.get("rvc_workers", 2)

    if rvc_model:
        logger.info(f"Starting RVC with {rvc_workers} workers...")
        _rvc_server = RVCServer(model_name=rvc_model, num_workers=rvc_workers)

        if _rvc_server.start(timeout=150.0):
            logger.info("RVC server ready")
            # Warmup workers to preload rmvpe
            logger.info("Warming up RVC workers...")
            _rvc_server.warmup(timeout=60.0)
        else:
            logger.warning("RVC server failed to start")
            _rvc_server = None
    else:
        logger.info("No RVC model specified - RVC disabled")

    _stats["start_time"] = time.time()

    logger.info("=" * 60)
    logger.info("Voice API Ready")
    logger.info("=" * 60)

    yield

    # Cleanup
    logger.info("Shutting down...")

    if _tts_client:
        _tts_client.close()

    if _rvc_server:
        _rvc_server.shutdown()

    logger.info("Shutdown complete")


# ============================================================================
# FastAPI App
# ============================================================================

app = FastAPI(
    title="Voice Synthesis API",
    description="TTS + RVC voice synthesis service",
    version="1.0.0",
    lifespan=lifespan,
)


# ============================================================================
# Helper Functions
# ============================================================================

def split_into_sentences(text: str) -> List[str]:
    """Split text into sentences."""
    sentences = re.split(r'(?<=[.!?])\s+', text)
    return [s.strip() for s in sentences if s.strip()]


def audio_to_wav_bytes(audio: np.ndarray, sample_rate: int = 16000) -> bytes:
    """Convert numpy audio to WAV bytes."""
    buffer = io.BytesIO()
    sf.write(buffer, audio, sample_rate, format='WAV')
    buffer.seek(0)
    return buffer.read()


def run_tts(text: str, reference_audio: np.ndarray, reference_text: str) -> tuple:
    """Run TTS inference. Returns (audio, time)."""
    start = time.time()
    audio = _tts_client.inference(
        text=text,
        prompt_speech=reference_audio,
        prompt_text=reference_text,
    )
    return audio, time.time() - start


def run_rvc(audio: np.ndarray, pitch_shift: int, f0_method: str, index_rate: float) -> tuple:
    """Run RVC conversion. Returns (audio, time)."""
    if _rvc_server is None:
        return audio, 0.0

    # Create temp files
    with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f_in:
        input_path = f_in.name
        sf.write(input_path, audio, 16000)

    with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f_out:
        output_path = f_out.name

    try:
        start = time.time()

        job_id = _rvc_server.submit_job(
            input_audio_path=input_path,
            output_audio_path=output_path,
            pitch_shift=pitch_shift,
            f0_method=f0_method,
            index_rate=index_rate,
            resample_sr=16000,  # Resample to match TTS output
        )

        result = _rvc_server.get_result(timeout=60.0)
        elapsed = time.time() - start

        if result and result.success:
            output_audio, _ = sf.read(output_path)
            return output_audio.astype(np.float32), elapsed
        else:
            raise RuntimeError(result.error if result else "Timeout")

    finally:
        for f in [input_path, output_path]:
            if os.path.exists(f):
                try:
                    os.unlink(f)
                except:
                    pass


# ============================================================================
# Endpoints
# ============================================================================

@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint."""
    tts_ready = _tts_client is not None and _tts_client.is_server_ready()
    rvc_ready = _rvc_server is not None and _rvc_server.is_running

    if tts_ready and rvc_ready:
        return HealthResponse(
            healthy=True,
            status="ready",
            tts_ready=True,
            rvc_ready=True,
            message="All services ready",
        )
    elif tts_ready or rvc_ready:
        return HealthResponse(
            healthy=True,
            status="degraded",
            tts_ready=tts_ready,
            rvc_ready=rvc_ready,
            message=f"TTS: {tts_ready}, RVC: {rvc_ready}",
        )
    else:
        return HealthResponse(
            healthy=False,
            status="error",
            tts_ready=False,
            rvc_ready=False,
            message="No services available",
        )


@app.get("/status", response_model=StatusResponse)
async def get_status():
    """Get detailed server status."""
    tts_ready = _tts_client is not None and _tts_client.is_server_ready()

    rvc_status = {}
    if _rvc_server:
        rvc_status = _rvc_server.get_status()

    uptime = time.time() - _stats["start_time"] if _stats["start_time"] else 0

    return StatusResponse(
        running=True,
        tts_ready=tts_ready,
        tts_model="spark_tts",
        triton_server=f"{_config.get('triton_addr', 'localhost')}:{_config.get('triton_port', 8001)}",
        rvc_ready=rvc_status.get("running", False),
        rvc_model=rvc_status.get("model", ""),
        rvc_workers=rvc_status.get("num_workers", 0),
        rvc_workers_alive=rvc_status.get("workers_alive", 0),
        total_requests=_stats["requests"],
        successful_requests=_stats["successful"],
        failed_requests=_stats["failed"],
        uptime=uptime,
    )


@app.post("/synthesize")
async def synthesize(
    text: str = Form(...),
    reference_text: str = Form(""),
    pitch_shift: int = Form(0),
    f0_method: str = Form("rmvpe"),
    index_rate: float = Form(0.75),
    skip_rvc: bool = Form(False),
    reference_audio: UploadFile = File(...),
):
    """
    Synthesize text with voice conversion.

    Automatically splits long text into sentences to avoid TTS length limits.
    Returns WAV audio file.
    """
    global _stats
    _stats["requests"] += 1

    try:
        # Read reference audio
        ref_bytes = await reference_audio.read()
        ref_buffer = io.BytesIO(ref_bytes)
        ref_audio, ref_sr = sf.read(ref_buffer)
        ref_audio = ref_audio.astype(np.float32)

        total_start = time.time()
        total_tts_time = 0.0
        total_rvc_time = 0.0

        # Split text into sentences to avoid TTS length limits
        sentences = split_into_sentences(text)
        audio_segments = []

        for sentence in sentences:
            if not sentence.strip():
                continue

            # TTS for this sentence
            tts_audio, tts_time = run_tts(sentence, ref_audio, reference_text)
            total_tts_time += tts_time

            # RVC for this sentence
            if skip_rvc or _rvc_server is None:
                segment_audio = tts_audio
            else:
                segment_audio, rvc_time = run_rvc(tts_audio, pitch_shift, f0_method, index_rate)
                total_rvc_time += rvc_time

            audio_segments.append(segment_audio)

        # Concatenate all segments
        if audio_segments:
            final_audio = np.concatenate(audio_segments)
        else:
            final_audio = np.array([], dtype=np.float32)

        total_time = time.time() - total_start

        _stats["successful"] += 1

        # Return audio as WAV
        wav_bytes = audio_to_wav_bytes(final_audio, 16000)

        return StreamingResponse(
            io.BytesIO(wav_bytes),
            media_type="audio/wav",
            headers={
                "X-TTS-Time": str(total_tts_time),
                "X-RVC-Time": str(total_rvc_time),
                "X-Total-Time": str(total_time),
                "X-Audio-Duration": str(len(final_audio) / 16000),
                "X-Sentences": str(len(sentences)),
            }
        )

    except Exception as e:
        _stats["failed"] += 1
        logger.error(f"Synthesis error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/synthesize/stream")
async def synthesize_stream(
    text: str = Form(...),
    reference_text: str = Form(""),
    pitch_shift: int = Form(0),
    f0_method: str = Form("rmvpe"),
    index_rate: float = Form(0.75),
    skip_rvc: bool = Form(False),
    reference_audio: UploadFile = File(...),
):
    """
    Streaming synthesis - yields audio chunks per sentence.

    For real-time playback: start playing audio as each sentence is ready,
    rather than waiting for the entire text to be processed.

    Returns multipart response with WAV chunks.
    """
    global _stats
    _stats["requests"] += 1

    try:
        # Read reference audio
        ref_bytes = await reference_audio.read()
        ref_buffer = io.BytesIO(ref_bytes)
        ref_audio, _ = sf.read(ref_buffer)
        ref_audio = ref_audio.astype(np.float32)

        # Split into sentences
        sentences = split_into_sentences(text)

        async def generate():
            for i, sentence in enumerate(sentences):
                if not sentence.strip():
                    continue
                try:
                    # TTS
                    tts_audio, tts_time = run_tts(sentence, ref_audio, reference_text)

                    # RVC
                    if skip_rvc or _rvc_server is None:
                        final_audio = tts_audio
                        rvc_time = 0.0
                    else:
                        final_audio, rvc_time = run_rvc(
                            tts_audio, pitch_shift, f0_method, index_rate
                        )

                    wav_bytes = audio_to_wav_bytes(final_audio, 16000)

                    # Yield as multipart chunk
                    yield (
                        f"--boundary\r\n"
                        f"Content-Type: audio/wav\r\n"
                        f"X-Sentence-Index: {i}\r\n"
                        f"X-Sentence-Text: {sentence[:50]}\r\n"
                        f"X-TTS-Time: {tts_time}\r\n"
                        f"X-RVC-Time: {rvc_time}\r\n"
                        f"Content-Length: {len(wav_bytes)}\r\n\r\n"
                    ).encode() + wav_bytes + b"\r\n"

                except Exception as e:
                    logger.error(f"Sentence {i} error: {e}")
                    continue

            yield b"--boundary--\r\n"
            _stats["successful"] += 1

        return StreamingResponse(
            generate(),
            media_type="multipart/mixed; boundary=boundary",
        )

    except Exception as e:
        _stats["failed"] += 1
        logger.error(f"Stream synthesis error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/tts")
async def tts_only(
    text: str = Form(...),
    reference_text: str = Form(""),
    reference_audio: UploadFile = File(...),
):
    """TTS only - no RVC conversion."""
    global _stats
    _stats["requests"] += 1

    try:
        ref_bytes = await reference_audio.read()
        ref_buffer = io.BytesIO(ref_bytes)
        ref_audio, _ = sf.read(ref_buffer)
        ref_audio = ref_audio.astype(np.float32)

        tts_audio, tts_time = run_tts(text, ref_audio, reference_text)

        _stats["successful"] += 1

        wav_bytes = audio_to_wav_bytes(tts_audio, 16000)

        return StreamingResponse(
            io.BytesIO(wav_bytes),
            media_type="audio/wav",
            headers={
                "X-Processing-Time": str(tts_time),
                "X-Audio-Duration": str(len(tts_audio) / 16000),
            }
        )

    except Exception as e:
        _stats["failed"] += 1
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/rvc")
async def rvc_only(
    pitch_shift: int = Form(0),
    f0_method: str = Form("rmvpe"),
    index_rate: float = Form(0.75),
    audio: UploadFile = File(...),
):
    """RVC only - convert existing audio."""
    global _stats
    _stats["requests"] += 1

    if _rvc_server is None:
        raise HTTPException(status_code=503, detail="RVC not available")

    try:
        audio_bytes = await audio.read()
        audio_buffer = io.BytesIO(audio_bytes)
        input_audio, sr = sf.read(audio_buffer)
        input_audio = input_audio.astype(np.float32)

        output_audio, rvc_time = run_rvc(input_audio, pitch_shift, f0_method, index_rate)

        _stats["successful"] += 1

        wav_bytes = audio_to_wav_bytes(output_audio, 16000)

        return StreamingResponse(
            io.BytesIO(wav_bytes),
            media_type="audio/wav",
            headers={
                "X-Processing-Time": str(rvc_time),
                "X-Audio-Duration": str(len(output_audio) / 16000),
            }
        )

    except Exception as e:
        _stats["failed"] += 1
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# CLI Entry Point
# ============================================================================

def main():
    parser = argparse.ArgumentParser(description="Voice Synthesis HTTP API")
    parser.add_argument("--rvc-model", help="RVC model name")
    parser.add_argument("--rvc-workers", type=int, default=2, help="Number of RVC workers")
    parser.add_argument("--triton-addr", default="localhost", help="Triton server address")
    parser.add_argument("--triton-port", type=int, default=8001, help="Triton gRPC port")
    parser.add_argument("--host", default="0.0.0.0", help="API host")
    parser.add_argument("--port", type=int, default=8000, help="API port")
    parser.add_argument("--log-level", default="INFO", help="Log level")

    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    # Store config for lifespan
    global _config
    _config = {
        "rvc_model": args.rvc_model,
        "rvc_workers": args.rvc_workers,
        "triton_addr": args.triton_addr,
        "triton_port": args.triton_port,
    }

    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
        log_level=args.log_level.lower(),
    )


if __name__ == "__main__":
    main()
