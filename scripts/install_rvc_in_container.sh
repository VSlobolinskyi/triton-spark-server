#!/bin/bash
# =============================================================================
# Install RVC dependencies inside Triton container
# Run this AFTER the base Triton container is set up (Cell 2.2 in notebook)
#
# Usage (from notebook):
#   udocker --allow-root run ... triton_server /bin/bash /workspace/scripts/install_rvc_in_container.sh
# =============================================================================

set -e

echo "=============================================="
echo "Installing RVC dependencies in Triton container"
echo "=============================================="

# RVC core dependencies
pip install --no-cache-dir \
    faiss-cpu>=1.7.0 \
    pyworld==0.3.2 \
    praat-parselmouth>=0.4.2 \
    torchcrepe==0.0.23 \
    ffmpeg-python>=0.2.0 \
    av>=9.0.0 \
    onnxruntime-gpu>=1.13.0 \
    numba>=0.56.0 \
    joblib>=1.1.0

# gRPC for RVC server
pip install --no-cache-dir \
    grpcio>=1.50.0 \
    grpcio-tools>=1.50.0

# fairseq from git (required for HuBERT)
pip install --no-cache-dir git+https://github.com/One-sixth/fairseq.git

echo "=============================================="
echo "RVC dependencies installed successfully"
echo "=============================================="

# Verify key imports
python3 -c "
import torch
import faiss
import pyworld
import parselmouth
import torchcrepe
import grpc
print('All RVC dependencies verified!')
print(f'  PyTorch: {torch.__version__}')
print(f'  CUDA available: {torch.cuda.is_available()}')
print(f'  gRPC: {grpc.__version__}')
"
