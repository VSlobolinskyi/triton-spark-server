"""
RVC Voice Conversion Module

Cleaned up version of infer/modules/vc/modules.py.
Removed Gradio-style return values, simplified API.
"""

import os
import traceback
import logging
from io import BytesIO
from typing import Tuple, Optional, Generator

import numpy as np
import soundfile as sf
import torch

from infer.lib.audio import load_audio, wav2
from infer.lib.infer_pack.models import (
    SynthesizerTrnMs256NSFsid,
    SynthesizerTrnMs256NSFsid_nono,
    SynthesizerTrnMs768NSFsid,
    SynthesizerTrnMs768NSFsid_nono,
)
from infer.modules.vc.pipeline import Pipeline
from infer.modules.vc.utils import load_hubert, get_index_path_from_model

logger = logging.getLogger(__name__)


class VC:
    """
    Voice Conversion class for RVC inference.

    This is a cleaned-up version without Gradio dependencies.
    """

    def __init__(self, config):
        """
        Initialize VC with configuration.

        Args:
            config: RVCConfig instance with device, is_half, etc.
        """
        self.config = config

        # Model state
        self.n_spk = None
        self.tgt_sr = None
        self.net_g = None
        self.pipeline = None
        self.cpt = None  # Checkpoint
        self.version = None
        self.if_f0 = None
        self.hubert_model = None

        # Current model info
        self.current_model = None

    def get_vc(self, sid: str) -> dict:
        """
        Load an RVC voice model.

        Args:
            sid: Model filename (e.g., "SilverWolf.pth") or empty string to unload.

        Returns:
            dict with model info:
                - n_spk: Number of speakers
                - tgt_sr: Target sample rate
                - version: Model version (v1/v2)
                - if_f0: Whether F0 is used (1 or 0)
                - index_path: Auto-detected index file path
        """
        logger.info(f"Loading model: {sid}")

        # Handle model unload
        if sid == "" or sid == []:
            return self._unload_model()

        # Resolve model path
        weight_root = os.environ.get("weight_root", "assets/weights")
        if os.path.isabs(sid):
            model_path = sid
        else:
            model_path = os.path.join(weight_root, sid)

        if not os.path.exists(model_path):
            raise FileNotFoundError(f"Model not found: {model_path}")

        logger.info(f"Loading from: {model_path}")

        # Load checkpoint
        self.cpt = torch.load(model_path, map_location="cpu")
        self.tgt_sr = self.cpt["config"][-1]
        self.cpt["config"][-3] = self.cpt["weight"]["emb_g.weight"].shape[0]  # n_spk
        self.if_f0 = self.cpt.get("f0", 1)
        self.version = self.cpt.get("version", "v1")

        # Select synthesizer class based on version and f0
        synthesizer_class = {
            ("v1", 1): SynthesizerTrnMs256NSFsid,
            ("v1", 0): SynthesizerTrnMs256NSFsid_nono,
            ("v2", 1): SynthesizerTrnMs768NSFsid,
            ("v2", 0): SynthesizerTrnMs768NSFsid_nono,
        }

        self.net_g = synthesizer_class.get(
            (self.version, self.if_f0), SynthesizerTrnMs256NSFsid
        )(*self.cpt["config"], is_half=self.config.is_half)

        # Remove encoder (not needed for inference)
        del self.net_g.enc_q

        # Load weights and move to device
        self.net_g.load_state_dict(self.cpt["weight"], strict=False)
        self.net_g.eval().to(self.config.device)

        if self.config.is_half:
            self.net_g = self.net_g.half()
        else:
            self.net_g = self.net_g.float()

        # Create pipeline
        self.pipeline = Pipeline(self.tgt_sr, self.config)
        self.n_spk = self.cpt["config"][-3]

        # Find index file
        index_path = get_index_path_from_model(sid)
        logger.info(f"Index path: {index_path}")

        self.current_model = sid

        return {
            "n_spk": self.n_spk,
            "tgt_sr": self.tgt_sr,
            "version": self.version,
            "if_f0": self.if_f0,
            "index_path": index_path,
        }

    def _unload_model(self) -> dict:
        """Unload current model and free memory."""
        if self.hubert_model is not None:
            logger.info("Unloading model and clearing cache")

            # Clean up references
            del self.net_g, self.n_spk, self.hubert_model, self.tgt_sr
            self.hubert_model = None
            self.net_g = None
            self.n_spk = None
            self.tgt_sr = None

            if torch.cuda.is_available():
                torch.cuda.empty_cache()

            # Additional cleanup
            if self.cpt is not None:
                self.if_f0 = self.cpt.get("f0", 1)
                self.version = self.cpt.get("version", "v1")

                # Create temporary net_g to properly clean up
                synthesizer_class = {
                    ("v1", 1): SynthesizerTrnMs256NSFsid,
                    ("v1", 0): SynthesizerTrnMs256NSFsid_nono,
                    ("v2", 1): SynthesizerTrnMs768NSFsid,
                    ("v2", 0): SynthesizerTrnMs768NSFsid_nono,
                }
                temp_net = synthesizer_class.get(
                    (self.version, self.if_f0), SynthesizerTrnMs256NSFsid
                )(*self.cpt["config"], is_half=self.config.is_half)
                del temp_net, self.cpt

                if torch.cuda.is_available():
                    torch.cuda.empty_cache()

        self.current_model = None
        return {"status": "unloaded"}

    def vc_single(
        self,
        sid: int,
        input_audio_path: str,
        f0_up_key: int,
        f0_file: Optional[str],
        f0_method: str,
        file_index: str,
        file_index2: str,
        index_rate: float,
        filter_radius: int,
        resample_sr: int,
        rms_mix_rate: float,
        protect: float,
    ) -> Tuple[str, Tuple[int, np.ndarray]]:
        """
        Convert a single audio file.

        Args:
            sid: Speaker ID (usually 0)
            input_audio_path: Path to input audio file
            f0_up_key: Pitch shift in semitones
            f0_file: Optional pre-computed F0 file
            f0_method: Pitch extraction method (pm, harvest, crepe, rmvpe)
            file_index: Path to feature index file
            file_index2: Fallback index path
            index_rate: Feature search ratio (0-1)
            filter_radius: Median filter radius for pitch
            resample_sr: Output sample rate (0 = no resampling)
            rms_mix_rate: Volume envelope scaling
            protect: Consonant protection (0 = max, 0.5 = none)

        Returns:
            Tuple of (info_message, (sample_rate, audio_array))
        """
        if input_audio_path is None:
            return "You need to upload an audio", (None, None)

        f0_up_key = int(f0_up_key)

        try:
            # Load and normalize audio
            audio = load_audio(input_audio_path, 16000)
            audio_max = np.abs(audio).max() / 0.95
            if audio_max > 1:
                audio /= audio_max

            times = [0, 0, 0]

            # Load HuBERT model if needed
            if self.hubert_model is None:
                self.hubert_model = load_hubert(self.config)

            # Clean up index path
            if file_index:
                file_index = (
                    file_index.strip(" ")
                    .strip('"')
                    .strip("\n")
                    .strip('"')
                    .strip(" ")
                    .replace("trained", "added")
                )
            elif file_index2:
                file_index = file_index2
            else:
                file_index = ""

            # Run voice conversion pipeline
            audio_opt = self.pipeline.pipeline(
                self.hubert_model,
                self.net_g,
                sid,
                audio,
                input_audio_path,
                times,
                f0_up_key,
                f0_method,
                file_index,
                index_rate,
                self.if_f0,
                filter_radius,
                self.tgt_sr,
                resample_sr,
                rms_mix_rate,
                self.version,
                protect,
                f0_file,
            )

            # Determine output sample rate
            if self.tgt_sr != resample_sr >= 16000:
                tgt_sr = resample_sr
            else:
                tgt_sr = self.tgt_sr

            # Build info message
            index_info = (
                f"Index: {file_index}"
                if file_index and os.path.exists(file_index)
                else "Index not used"
            )

            info = (
                f"Success.\n{index_info}\n"
                f"Time: npy={times[0]:.2f}s, f0={times[1]:.2f}s, infer={times[2]:.2f}s"
            )

            return info, (tgt_sr, audio_opt)

        except Exception:
            info = traceback.format_exc()
            logger.warning(info)
            return info, (None, None)

    def vc_multi(
        self,
        sid: int,
        dir_path: str,
        opt_root: str,
        paths: list,
        f0_up_key: int,
        f0_method: str,
        file_index: str,
        file_index2: str,
        index_rate: float,
        filter_radius: int,
        resample_sr: int,
        rms_mix_rate: float,
        protect: float,
        format1: str,
    ) -> Generator[str, None, None]:
        """
        Convert multiple audio files.

        Args:
            sid: Speaker ID
            dir_path: Directory containing input files (or empty if using paths)
            opt_root: Output directory
            paths: List of input file paths
            f0_up_key: Pitch shift
            f0_method: Pitch extraction method
            file_index: Index file path
            file_index2: Fallback index
            index_rate: Index mixing ratio
            filter_radius: Pitch filter radius
            resample_sr: Output sample rate
            rms_mix_rate: Volume envelope mix
            protect: Consonant protection
            format1: Output format (wav, flac, mp3)

        Yields:
            Progress info after each file
        """
        try:
            # Clean up paths
            dir_path = dir_path.strip(" ").strip('"').strip("\n").strip('"').strip(" ")
            opt_root = opt_root.strip(" ").strip('"').strip("\n").strip('"').strip(" ")
            os.makedirs(opt_root, exist_ok=True)

            # Get file list
            try:
                if dir_path:
                    paths = [
                        os.path.join(dir_path, name) for name in os.listdir(dir_path)
                    ]
                else:
                    # Handle both path objects and strings
                    paths = [
                        p.name if hasattr(p, 'name') else p
                        for p in paths
                    ]
            except Exception:
                traceback.print_exc()
                paths = [p.name if hasattr(p, 'name') else p for p in paths]

            infos = []

            for path in paths:
                info, opt = self.vc_single(
                    sid,
                    path,
                    f0_up_key,
                    None,
                    f0_method,
                    file_index,
                    file_index2,
                    index_rate,
                    filter_radius,
                    resample_sr,
                    rms_mix_rate,
                    protect,
                )

                if "Success" in info:
                    try:
                        tgt_sr, audio_opt = opt
                        output_name = os.path.basename(path)

                        if format1 in ["wav", "flac"]:
                            output_path = os.path.join(
                                opt_root, f"{output_name}.{format1}"
                            )
                            sf.write(output_path, audio_opt, tgt_sr)
                        else:
                            output_path = os.path.join(
                                opt_root, f"{output_name}.{format1}"
                            )
                            with BytesIO() as wavf:
                                sf.write(wavf, audio_opt, tgt_sr, format="wav")
                                wavf.seek(0, 0)
                                with open(output_path, "wb") as outf:
                                    wav2(wavf, outf, format1)
                    except Exception:
                        info += traceback.format_exc()

                infos.append(f"{os.path.basename(path)} -> {info}")
                yield "\n".join(infos)

            yield "\n".join(infos)

        except Exception:
            yield traceback.format_exc()
