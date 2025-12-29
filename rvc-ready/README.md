# RVC Ready - Files Ready for Use

These files can be used as-is without modification. They form the core RVC inference library.

## Structure

```
rvc-ready/
├── infer/                      # Core RVC inference library
│   ├── lib/                    # Low-level audio processing
│   │   ├── audio.py            # Audio loading/processing (ffmpeg-based)
│   │   ├── rmvpe.py            # RMVPE F0 extraction model
│   │   ├── slicer2.py          # Audio slicing utilities
│   │   ├── infer_pack/         # Neural network models
│   │   │   ├── attentions.py   # Attention mechanisms
│   │   │   ├── commons.py      # Common utilities
│   │   │   ├── models.py       # Synthesizer models (v1/v2)
│   │   │   ├── modules.py      # NN building blocks
│   │   │   ├── transforms.py   # Audio transforms
│   │   │   └── modules/F0Predictor/  # F0 prediction methods
│   │   └── jit/                # JIT compilation utilities
│   └── modules/vc/             # Voice conversion
│       ├── pipeline.py         # Main VC inference pipeline
│       └── utils.py            # VC utilities (hubert loading, index lookup)
├── configs/                    # RVC model configurations
│   ├── v1/                     # Version 1 configs (32k, 40k, 48k)
│   ├── v2/                     # Version 2 configs (32k, 48k)
│   └── inuse/                  # Active configs (copied at runtime)
├── assets/                     # Model weights storage (download required)
│   ├── hubert/                 # HuBERT model (hubert_base.pt)
│   ├── rmvpe/                  # RMVPE model (rmvpe.pt)
│   ├── weights/                # RVC voice models (.pth)
│   ├── indices/                # Feature indices (.index)
│   ├── pretrained/             # Pretrained v1 models
│   └── pretrained_v2/          # Pretrained v2 models
├── logs/mute/                  # Required mute audio files for inference
├── tools/
│   ├── download_assets.py      # Downloads hubert, rmvpe, pretrained models
│   └── download_model.py       # Downloads specific RVC voice models
```

## Usage

### 1. Download Required Assets
```bash
python tools/download_assets.py
```

This downloads:
- `hubert_base.pt` - HuBERT feature extractor
- `rmvpe.pt` - RMVPE pitch extraction model
- Pretrained v1/v2 models

### 2. Download Voice Models
```bash
python tools/download_model.py https://huggingface.co/path/to/model.zip
```

This extracts:
- `.pth` files to `assets/weights/`
- `.index` files to `logs/` or `assets/indices/`

## Environment Variables Required

These must be set before using the inference code:
```python
os.environ["weight_root"] = "assets/weights"
os.environ["index_root"] = "logs"
os.environ["rmvpe_root"] = "assets/rmvpe"
```

## Dependencies

Core dependencies (add to requirements.txt):
```
fairseq @ git+https://github.com/One-sixth/fairseq.git
faiss-cpu>=1.7.0
librosa==0.10.2
pyworld==0.3.2
praat-parselmouth>=0.4.2
torchcrepe==0.0.23
ffmpeg-python>=0.2.0
soundfile>=0.12.1
av>=9.0.0
numpy>=1.0,<2.0
scipy>=1.9.0
```
