import os
from pathlib import Path

from fairseq import checkpoint_utils


def get_index_path_from_model(sid):
    """Find index file matching the model name."""
    index_root = os.getenv("index_root", "logs")
    return next(
        (
            f
            for f in [
                os.path.join(root, name)
                for root, _, files in os.walk(index_root, topdown=False)
                for name in files
                if name.endswith(".index") and "trained" not in name
            ]
            if sid.split(".")[0] in f
        ),
        "",
    )


def load_hubert(config):
    """Load HuBERT model for feature extraction."""
    # Determine hubert path from environment or relative to project root
    rvc_root = os.environ.get("RVC_ROOT", "rvc")
    project_root = Path(rvc_root).parent

    hubert_path = os.path.join(project_root, "assets", "hubert", "hubert_base.pt")

    # Fallback to relative path if absolute doesn't exist
    if not os.path.exists(hubert_path):
        hubert_path = "assets/hubert/hubert_base.pt"

    models, _, _ = checkpoint_utils.load_model_ensemble_and_task(
        [hubert_path],
        suffix="",
    )
    hubert_model = models[0]
    hubert_model = hubert_model.to(config.device)
    if config.is_half:
        hubert_model = hubert_model.half()
    else:
        hubert_model = hubert_model.float()
    return hubert_model.eval()
