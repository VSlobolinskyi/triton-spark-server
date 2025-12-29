# Triton Spark TTS + RVC Integration Status

## Overview

This document tracks the integration of RVC (Retrieval-based Voice Conversion) into the Triton Spark TTS server.

## Directory Structure

```
triton-spark-server/
├── runtime/triton_trtllm/     # Triton inference server setup
├── sparktts/                  # Spark TTS model code
├── rvc-ready/                 # RVC files ready to use (no changes needed)
├── rvc-in-progress/           # RVC files needing modification
├── tools/
│   ├── download_all_assets.py # Unified asset downloader
│   └── setup_environment.py   # Environment setup script
├── requirements.txt           # Combined dependencies
└── questions_to_user.txt      # Pending questions/decisions
```

## Completed Steps

- [x] Analyzed both codebases (Triton/Spark + RVC)
- [x] Created folder structure (rvc-ready, rvc-in-progress)
- [x] Copied RVC inference library files to rvc-ready
- [x] Created TODO documentation for files needing changes
- [x] Combined dependency trees into requirements.txt
- [x] Created unified download_all_assets.py script
- [x] Created setup_environment.py for environment setup

## Pending Steps

- [ ] Answer questions in questions_to_user.txt
- [ ] Modify config.py (remove CLI args, simplify)
- [ ] Create rvc_init.py (standalone initialization)
- [ ] Modify modules.py (remove Gradio returns)
- [ ] Adapt workers.py (replace SparkTTS with TritonSparkTTS)
- [ ] Create simple test script for Colab
- [ ] Test end-to-end pipeline

## Dependency Summary

### From Triton/Spark (Priority)
- torch, torchaudio (from container or CUDA wheels)
- tritonclient
- einx==0.3.0
- omegaconf
- soundfile==0.12.1
- transformers

### From RVC (Additional)
- fairseq (git+https://github.com/One-sixth/fairseq.git)
- faiss-cpu
- pyworld==0.3.2
- praat-parselmouth
- torchcrepe==0.0.23
- onnxruntime-gpu

### Removed (UI/Training only)
- gradio
- matplotlib
- tensorboard
- torch-directml (AMD)

## Quick Start (After Setup)

```bash
# 1. Setup environment
python tools/setup_environment.py --colab  # or --container, --local

# 2. Download assets
python tools/download_all_assets.py

# 3. Download a voice model (optional)
python tools/download_all_assets.py --rvc-model "https://huggingface.co/path/to/model.zip"
```

## Files in rvc-ready/ (Ready to Use)

| Path | Description |
|------|-------------|
| `infer/lib/audio.py` | Audio loading with ffmpeg |
| `infer/lib/rmvpe.py` | RMVPE pitch extraction |
| `infer/lib/infer_pack/*.py` | Neural network models |
| `infer/modules/vc/pipeline.py` | Voice conversion pipeline |
| `infer/modules/vc/utils.py` | HuBERT loading, index lookup |
| `configs/v1/*.json` | RVC v1 model configs |
| `configs/v2/*.json` | RVC v2 model configs |
| `logs/mute/` | Required mute audio files |
| `tools/download_*.py` | Download scripts |

## Files in rvc-in-progress/ (Need Modification)

| File | Changes Needed | TODO File |
|------|----------------|-----------|
| `config.py` | Remove CLI args, simplify | `TODO_config.txt` |
| `rvc_inference/initialization.py` | Remove UI deps, create init func | `TODO_initialization.txt` |
| `rvc_inference/modules.py` | Remove Gradio returns | `TODO_modules.txt` |
| `processing/workers.py` | Replace SparkTTS with Triton | `TODO_workers.txt` |
| `processing/worker_manager.py` | Minor import fixes | - |
| `processing/utils.py` | Import path fixes | - |
