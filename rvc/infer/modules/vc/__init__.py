"""Voice Conversion Module"""

from rvc.infer.modules.vc.pipeline import Pipeline
from rvc.infer.modules.vc.utils import load_hubert, get_index_path_from_model

__all__ = ["Pipeline", "load_hubert", "get_index_path_from_model"]
