"""
Simplified RVC Configuration for Triton Integration

Removed from original config.py:
- CLI argument parsing (argparse)
- DirectML/AMD support
- Singleton pattern
- Intel XPU support
- Runtime folder renaming logic

Configuration via:
- Constructor parameters
- Environment variables (RVC_ROOT, RVC_DEVICE, RVC_HALF)
"""

import os
import sys
import json
import shutil
import logging
from pathlib import Path
from multiprocessing import cpu_count

import torch

logger = logging.getLogger(__name__)

# Config file versions supported by RVC
VERSION_CONFIG_LIST = [
    "v1/32k.json",
    "v1/40k.json",
    "v1/48k.json",
    "v2/48k.json",
    "v2/32k.json",
]


class RVCConfig:
    """
    Simplified RVC configuration for Triton integration.

    Usage:
        # Auto-detect device
        config = RVCConfig()

        # Force specific device
        config = RVCConfig(device="cuda:1", is_half=True)

        # Via environment variables
        os.environ["RVC_DEVICE"] = "cuda:0"
        os.environ["RVC_HALF"] = "true"
        config = RVCConfig()
    """

    def __init__(self, device: str = None, is_half: bool = None):
        """
        Initialize RVC configuration.

        Args:
            device: Device to use (cuda:0, cpu). Auto-detected if None.
            is_half: Use half precision. Auto-detected if None.
        """
        # RVC root directory
        self.rvc_root = Path(os.environ.get("RVC_ROOT", "rvc-ready"))

        # Python command (for compatibility)
        self.python_cmd = sys.executable or "python"

        # CPU count
        self.n_cpu = cpu_count()

        # Device configuration
        self.device = self._resolve_device(device)
        self.is_half = self._resolve_half_precision(is_half)

        # GPU info
        self.gpu_name = None
        self.gpu_mem = None
        self._detect_gpu_info()

        # Adjust half precision based on GPU capabilities
        self._adjust_for_gpu()

        # Padding configuration (based on GPU memory and precision)
        self.x_pad, self.x_query, self.x_center, self.x_max = self._get_padding_config()

        # Load model configs
        self.json_config = self._load_config_json()

        # Preprocessing config
        self.preprocess_per = 3.7 if self.is_half else 3.0

        logger.info(
            f"RVC Config: device={self.device}, half={self.is_half}, "
            f"gpu={self.gpu_name}, gpu_mem={self.gpu_mem}GB"
        )

    def _resolve_device(self, device: str = None) -> str:
        """Resolve device from parameter, environment, or auto-detect."""
        # Parameter takes priority
        if device:
            return device

        # Then environment variable
        env_device = os.environ.get("RVC_DEVICE")
        if env_device:
            return env_device

        # Auto-detect
        if torch.cuda.is_available():
            return "cuda:0"

        # MPS for MacOS
        if hasattr(torch.backends, 'mps') and torch.backends.mps.is_available():
            try:
                torch.zeros(1).to(torch.device("mps"))
                return "mps"
            except Exception:
                pass

        return "cpu"

    def _resolve_half_precision(self, is_half: bool = None) -> bool:
        """Resolve half precision from parameter, environment, or auto-detect."""
        # Parameter takes priority
        if is_half is not None:
            return is_half

        # Then environment variable
        env_half = os.environ.get("RVC_HALF")
        if env_half is not None:
            return env_half.lower() in ("true", "1", "yes")

        # Auto-detect: half precision only for CUDA
        if "cuda" in self.device:
            return True

        return False

    def _detect_gpu_info(self):
        """Detect GPU name and memory if CUDA is available."""
        if not torch.cuda.is_available() or "cuda" not in self.device:
            return

        try:
            i_device = int(self.device.split(":")[-1])
            self.gpu_name = torch.cuda.get_device_name(i_device)
            self.gpu_mem = int(
                torch.cuda.get_device_properties(i_device).total_memory
                / 1024 / 1024 / 1024 + 0.4
            )
        except Exception as e:
            logger.warning(f"Failed to detect GPU info: {e}")

    def _adjust_for_gpu(self):
        """Adjust settings based on GPU capabilities."""
        if not self.gpu_name:
            return

        # Force fp32 for older/problematic GPUs
        old_gpus = ["P40", "P10", "1060", "1070", "1080"]
        gpu_upper = self.gpu_name.upper()

        if any(gpu in gpu_upper for gpu in old_gpus):
            logger.info(f"Found older GPU {self.gpu_name}, forcing fp32")
            self.is_half = False
        elif "16" in self.gpu_name and "V100" not in gpu_upper:
            # 16xx series (not V100-16GB)
            logger.info(f"Found GTX 16xx GPU {self.gpu_name}, forcing fp32")
            self.is_half = False

    def _get_padding_config(self) -> tuple:
        """Get padding configuration based on precision and GPU memory."""
        # Low memory config (4GB or less)
        if self.gpu_mem is not None and self.gpu_mem <= 4:
            return 1, 5, 30, 32

        # Half precision config (6GB+ VRAM)
        if self.is_half:
            return 3, 10, 60, 65

        # Full precision config (5GB+ VRAM)
        return 1, 6, 38, 41

    def _load_config_json(self) -> dict:
        """Load RVC model configuration files."""
        configs = {}

        for config_file in VERSION_CONFIG_LIST:
            src = self.rvc_root / "configs" / config_file
            dst = self.rvc_root / "configs" / "inuse" / config_file

            # Ensure directory exists
            dst.parent.mkdir(parents=True, exist_ok=True)

            # Copy config if not already in inuse
            if not dst.exists() and src.exists():
                shutil.copy(src, dst)

            # Load config
            if dst.exists():
                try:
                    with open(dst, "r") as f:
                        configs[config_file] = json.load(f)
                except Exception as e:
                    logger.warning(f"Failed to load config {config_file}: {e}")
            else:
                logger.warning(f"Config file not found: {src}")

        return configs

    def use_fp32_config(self):
        """Update config files to use fp32 instead of fp16."""
        for config_file in VERSION_CONFIG_LIST:
            if config_file not in self.json_config:
                continue

            # Update in-memory config
            self.json_config[config_file]["train"]["fp16_run"] = False

            # Update on-disk config
            config_path = self.rvc_root / "configs" / "inuse" / config_file
            if config_path.exists():
                try:
                    with open(config_path, "r") as f:
                        content = f.read().replace("true", "false")
                    with open(config_path, "w") as f:
                        f.write(content)
                    logger.info(f"Updated {config_file} to fp32")
                except Exception as e:
                    logger.warning(f"Failed to update config {config_file}: {e}")

        self.preprocess_per = 3.0


# Convenience function for quick initialization
def get_config(device: str = None, is_half: bool = None) -> RVCConfig:
    """Get RVC configuration instance."""
    return RVCConfig(device=device, is_half=is_half)
