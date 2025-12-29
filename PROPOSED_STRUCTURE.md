# Proposed Final Project Structure

## Overview

After RVC integration, this is the target structure. The `rvc-ready/` and `rvc-in-progress/` temporary folders will be merged into the main project, and `spark-rvc-inference-module/` (source clone) will be removed.

## Directory Structure

```
triton-spark-server/
├── .gitignore
├── .vscode/
│   └── settings.json
├── LICENSE
├── README.md
├── requirements.txt              # RVC dependencies (host Python)
├── setup.py
│
├── runtime/                      # Triton Inference Server (runs IN container)
│   └── triton_trtllm/
│       ├── client_grpc.py        # Original Triton client (reference)
│       ├── docker-compose.yml
│       ├── Dockerfile.server
│       ├── model_repo/
│       │   ├── audio_tokenizer/
│       │   ├── spark_tts/
│       │   ├── tensorrt_llm/
│       │   └── vocoder/
│       ├── README.md
│       ├── run.sh
│       ├── scripts/
│       │   ├── convert_checkpoint.py
│       │   └── fill_template.py
│       └── TritonSparkTTS.py
│
├── sparktts/                     # Spark TTS model code (used by container)
│   ├── models/
│   │   ├── audio_tokenizer.py
│   │   └── bicodec.py
│   ├── modules/
│   │   ├── blocks/
│   │   ├── encoder_decoder/
│   │   ├── fsq/
│   │   ├── speaker/
│   │   └── vq/
│   └── utils/
│
├── rvc/                          # RVC Voice Conversion (runs on HOST)
│   ├── __init__.py
│   ├── rvc_config.py             # Simplified config (from rvc-ready)
│   ├── rvc_init.py               # Initialization module (from rvc-ready)
│   ├── rvc_modules.py            # VC class without Gradio (from rvc-ready)
│   ├── triton_client.py          # Triton gRPC wrapper (from rvc-ready)
│   │
│   ├── infer/                    # RVC inference library
│   │   ├── lib/
│   │   │   ├── audio.py
│   │   │   ├── rmvpe.py
│   │   │   ├── slicer2.py
│   │   │   ├── infer_pack/
│   │   │   │   ├── attentions.py
│   │   │   │   ├── commons.py
│   │   │   │   ├── models.py
│   │   │   │   ├── modules.py
│   │   │   │   ├── transforms.py
│   │   │   │   └── modules/
│   │   │   │       └── F0Predictor/
│   │   │   └── jit/
│   │   │       ├── get_hubert.py
│   │   │       ├── get_rmvpe.py
│   │   │       └── get_synthesizer.py
│   │   └── modules/
│   │       └── vc/
│   │           ├── pipeline.py
│   │           └── utils.py
│   │
│   ├── processing/               # Async worker system
│   │   ├── __init__.py
│   │   ├── workers.py            # TTS + RVC workers
│   │   ├── worker_manager.py     # Worker lifecycle
│   │   ├── buffer_queue.py       # Ordered audio output
│   │   └── utils.py              # Helper functions
│   │
│   └── configs/                  # RVC model configs
│       ├── v1/
│       │   ├── 32k.json
│       │   ├── 40k.json
│       │   └── 48k.json
│       └── v2/
│           ├── 32k.json
│           └── 48k.json
│
├── assets/                       # Downloaded assets (gitignored)
│   ├── hubert/
│   │   └── hubert_base.pt
│   ├── rmvpe/
│   │   └── rmvpe.pt
│   └── weights/                  # RVC voice models (.pth)
│       └── .gitignore
│
├── logs/                         # RVC logs and index files
│   ├── mute/                     # Required mute audio files
│   │   ├── 0_gt_wavs/
│   │   ├── 1_16k_wavs/
│   │   ├── 2a_f0/
│   │   ├── 2b-f0nsf/
│   │   ├── 3_feature256/
│   │   └── 3_feature768/
│   └── .gitignore
│
├── tools/                        # Utility scripts
│   ├── download_all_assets.py    # Unified asset downloader
│   ├── setup_environment.py      # Environment setup
│   └── test_pipeline.py          # Pipeline test script
│
├── colab/                        # Colab notebooks
│   └── triton_spark_rvc.ipynb    # Main notebook
│
├── TEMP/                         # Temporary audio files (gitignored)
│   ├── spark/
│   └── rvc/
│
└── docs/                         # Documentation
    └── architecture.md           # Architecture overview
```

## What Gets Removed

After restructure, these will be deleted:
- `rvc-ready/` - Contents moved to `rvc/`
- `rvc-in-progress/` - Was working directory, no longer needed
- `spark-rvc-inference-module/` - Source clone, extracted what we need
- `INTEGRATION_STATUS.md` - Temporary tracking file
- `TODO.txt` - Temporary tracking file
- `rvc_collab_script.txt` - Merged into notebook
- `triton_collab_scritps.txt` - Merged into notebook
- Various TODO_*.txt files

## Environment Variables

```bash
# RVC Configuration
RVC_ROOT=./rvc                    # Path to RVC module
weight_root=./assets/weights      # Voice model files
index_root=./logs                 # Index files
rmvpe_root=./assets/rmvpe         # RMVPE model

# Triton Configuration
TRITON_SERVER_ADDR=localhost      # Triton server address
TRITON_SERVER_PORT=8001           # Triton gRPC port

# Worker Configuration
MODEL_UNLOAD_DELAY=30             # Seconds before unloading idle workers
```

## Import Structure

After restructure, imports will be:
```python
# RVC initialization and conversion
from rvc import init_rvc, load_model, convert_audio

# Or more explicitly
from rvc.rvc_init import init_rvc, get_vc, load_model, convert_audio
from rvc.rvc_config import RVCConfig
from rvc.triton_client import TritonSparkClient

# Processing workers
from rvc.processing import get_worker_manager, WorkerManager
from rvc.processing.utils import split_text_and_validate
```

## Migration Steps

1. Create `rvc/` directory structure
2. Move files from `rvc-ready/` to `rvc/`
3. Move `assets/` and `logs/` to root level
4. Update all import paths
5. Delete temporary directories
6. Delete `spark-rvc-inference-module/`
7. Update `.gitignore`
8. Test imports

## Notes

- `sparktts/` stays at root (used by Triton container)
- `runtime/` stays at root (Triton server config)
- `rvc/` is the new home for all RVC code
- `assets/` and `logs/` at root for easier path management
