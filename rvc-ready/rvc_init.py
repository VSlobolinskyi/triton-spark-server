"""
RVC Initialization Module for Triton Spark Server

Clean initialization without Gradio dependencies.
Sets up environment variables, loads config, creates VC instance.

Usage:
    from rvc_init import init_rvc, get_vc, load_model, convert_audio

    # Initialize once at startup
    init_rvc(device="cuda:0")

    # Load a voice model
    load_model("SilverWolf.pth")

    # Convert audio
    info, (sr, audio) = convert_audio(
        audio_path="input.wav",
        pitch_shift=0,
        f0_method="rmvpe"
    )
"""

import os
import sys
import logging
import warnings
from pathlib import Path
from typing import Optional, Tuple, Union

import numpy as np
import torch

logger = logging.getLogger(__name__)

# Global instances
_config = None
_vc = None
_initialized = False


def init_rvc(
    device: str = None,
    is_half: bool = None,
    weight_root: str = None,
    index_root: str = None,
    rmvpe_root: str = None,
    rvc_root: str = None,
) -> None:
    """
    Initialize RVC system.

    This must be called before any other RVC functions.
    Safe to call multiple times - subsequent calls are ignored.

    Args:
        device: Torch device (e.g., "cuda:0", "cpu"). Auto-detected if None.
        is_half: Use half precision. Auto-detected if None (True for CUDA).
        weight_root: Path to RVC voice models (.pth files).
        index_root: Path to index files (.index files).
        rmvpe_root: Path to RMVPE model directory.
        rvc_root: Root path of rvc-ready folder.

    Example:
        init_rvc(device="cuda:0", is_half=True)
    """
    global _config, _vc, _initialized

    if _initialized:
        logger.debug("RVC already initialized, skipping")
        return

    # Determine RVC root directory
    if rvc_root is None:
        rvc_root = os.environ.get("RVC_ROOT")
        if rvc_root is None:
            # Try to find rvc-ready relative to this file
            this_dir = Path(__file__).parent
            if this_dir.name == "rvc-ready":
                rvc_root = str(this_dir)
            else:
                rvc_root = "rvc-ready"

    rvc_root = str(Path(rvc_root).resolve())

    # Set environment variables for RVC internals
    os.environ["RVC_ROOT"] = rvc_root
    os.environ["weight_root"] = weight_root or os.path.join(rvc_root, "assets", "weights")
    os.environ["index_root"] = index_root or os.path.join(rvc_root, "logs")
    os.environ["rmvpe_root"] = rmvpe_root or os.path.join(rvc_root, "assets", "rmvpe")

    # Create required directories
    required_dirs = [
        os.environ["weight_root"],
        os.environ["index_root"],
        os.path.join(rvc_root, "assets", "hubert"),
        os.path.join(rvc_root, "configs", "inuse", "v1"),
        os.path.join(rvc_root, "configs", "inuse", "v2"),
    ]
    for path in required_dirs:
        os.makedirs(path, exist_ok=True)

    # Suppress noisy loggers
    logging.getLogger("numba").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("fairseq").setLevel(logging.WARNING)

    # Suppress warnings
    warnings.filterwarnings("ignore")

    # Set random seed for reproducibility
    torch.manual_seed(114514)

    # Add rvc-ready to Python path for imports
    if rvc_root not in sys.path:
        sys.path.insert(0, rvc_root)

    # Import and create config
    from rvc_config import RVCConfig
    _config = RVCConfig(device=device, is_half=is_half)

    # Import and create VC
    from rvc_modules import VC
    _vc = VC(_config)

    _initialized = True
    logger.info(
        f"RVC initialized: device={_config.device}, half={_config.is_half}, "
        f"weight_root={os.environ['weight_root']}"
    )


def get_vc():
    """
    Get the VC instance.

    Returns:
        VC: The voice conversion instance.

    Raises:
        RuntimeError: If init_rvc() has not been called.
    """
    if not _initialized:
        raise RuntimeError("RVC not initialized. Call init_rvc() first.")
    return _vc


def get_config():
    """
    Get the RVC config instance.

    Returns:
        RVCConfig: The configuration instance.

    Raises:
        RuntimeError: If init_rvc() has not been called.
    """
    if not _initialized:
        raise RuntimeError("RVC not initialized. Call init_rvc() first.")
    return _config


def is_initialized() -> bool:
    """Check if RVC has been initialized."""
    return _initialized


def load_model(model_name: str) -> dict:
    """
    Load an RVC voice model.

    Args:
        model_name: Name of the model file (e.g., "SilverWolf.pth").
                   Can be just the filename or full path.

    Returns:
        dict: Model info containing:
            - n_spk: Number of speakers
            - tgt_sr: Target sample rate
            - version: Model version (v1/v2)
            - if_f0: Whether F0 is used
            - index_path: Auto-detected index file path (if found)

    Example:
        info = load_model("SilverWolf.pth")
        print(f"Model loaded: {info['version']}, {info['tgt_sr']}Hz")
    """
    vc = get_vc()
    return vc.get_vc(model_name)


def convert_audio(
    audio_path: str,
    speaker_id: int = 0,
    pitch_shift: int = 0,
    f0_method: str = "rmvpe",
    index_path: str = "",
    index_rate: float = 0.75,
    filter_radius: int = 3,
    resample_sr: int = 0,
    rms_mix_rate: float = 0.25,
    protect: float = 0.33,
    f0_file: str = None,
) -> Tuple[str, Tuple[int, np.ndarray]]:
    """
    Convert audio using the loaded RVC model.

    Args:
        audio_path: Path to input audio file.
        speaker_id: Speaker ID (usually 0 for single-speaker models).
        pitch_shift: Semitones to shift pitch. Positive = higher, negative = lower.
                    Common: +12 for male→female, -12 for female→male.
        f0_method: Pitch extraction method:
                   - "rmvpe": Best quality, recommended (default)
                   - "crepe": Good quality, slower
                   - "harvest": Fast, decent quality
                   - "pm": Fastest, lower quality
        index_path: Path to feature index file (.index). Empty = no index.
        index_rate: How much to use the index (0.0-1.0). Higher = more similar to training voice.
        filter_radius: Median filter radius for pitch (0-7). Higher = smoother pitch.
        resample_sr: Output sample rate. 0 = use model's native rate.
        rms_mix_rate: Volume envelope mix (0.0-1.0). 0 = use input envelope, 1 = use output.
        protect: Consonant/breathing protection (0.0-0.5). Lower = more protection.
        f0_file: Optional path to pre-computed F0 file.

    Returns:
        Tuple of (info_message, (sample_rate, audio_array)):
            - info_message: Status string with timing info
            - sample_rate: Output audio sample rate
            - audio_array: NumPy array of audio samples (float32)

    Example:
        info, (sr, audio) = convert_audio(
            "input.wav",
            pitch_shift=0,
            f0_method="rmvpe",
            index_rate=0.75
        )
        if "Success" in info:
            sf.write("output.wav", audio, sr)
    """
    vc = get_vc()
    return vc.vc_single(
        sid=speaker_id,
        input_audio_path=audio_path,
        f0_up_key=pitch_shift,
        f0_file=f0_file,
        f0_method=f0_method,
        file_index=index_path,
        file_index2="",  # Fallback index (unused)
        index_rate=index_rate,
        filter_radius=filter_radius,
        resample_sr=resample_sr,
        rms_mix_rate=rms_mix_rate,
        protect=protect,
    )


def convert_audio_batch(
    audio_paths: list,
    output_dir: str,
    speaker_id: int = 0,
    pitch_shift: int = 0,
    f0_method: str = "rmvpe",
    index_path: str = "",
    index_rate: float = 0.75,
    filter_radius: int = 3,
    resample_sr: int = 0,
    rms_mix_rate: float = 0.25,
    protect: float = 0.33,
    output_format: str = "wav",
):
    """
    Convert multiple audio files.

    Args:
        audio_paths: List of input audio file paths.
        output_dir: Directory to save converted files.
        output_format: Output format (wav, flac, mp3).
        ... (same as convert_audio)

    Yields:
        str: Progress info after each file.
    """
    vc = get_vc()
    yield from vc.vc_multi(
        sid=speaker_id,
        dir_path="",
        opt_root=output_dir,
        paths=audio_paths,
        f0_up_key=pitch_shift,
        f0_method=f0_method,
        file_index=index_path,
        file_index2="",
        index_rate=index_rate,
        filter_radius=filter_radius,
        resample_sr=resample_sr,
        rms_mix_rate=rms_mix_rate,
        protect=protect,
        format1=output_format,
    )


def cleanup():
    """
    Clean up RVC resources and free GPU memory.

    Call this when shutting down or when you need to free memory.
    After cleanup, you must call init_rvc() again to use RVC.
    """
    global _config, _vc, _initialized

    if _vc is not None:
        # Trigger model cleanup
        try:
            _vc.get_vc("")
        except Exception:
            pass

    _config = None
    _vc = None
    _initialized = False

    if torch.cuda.is_available():
        torch.cuda.empty_cache()

    logger.info("RVC cleaned up")
