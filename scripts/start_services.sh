#!/bin/bash
# =============================================================================
# Start Voice Services inside container
#
# This script runs INSIDE the udocker container and starts:
# 1. Triton Server (Spark TTS) on port 8001 (internal gRPC)
# 2. Voice HTTP API on port 8080 (external, wraps TTS + RVC)
#
# Usage (from notebook):
#   udocker --allow-root run ... voice_server /bin/bash /workspace/scripts/start_services.sh
#
# Environment variables:
#   RVC_MODEL         - RVC model filename (default: SilverWolf_e300_s6600.pth)
#   RVC_WORKERS       - Number of RVC workers (default: 2)
#   TRITON_MODEL_REPO - Triton model repository path
#   API_PORT          - HTTP API port (default: 8080)
# =============================================================================

set -e

# Configuration with defaults
RVC_MODEL="${RVC_MODEL:-SilverWolf_e300_s6600.pth}"
RVC_WORKERS="${RVC_WORKERS:-2}"
TRITON_MODEL_REPO="${TRITON_MODEL_REPO:-/workspace/triton/model_repo_test}"
API_PORT="${API_PORT:-8080}"

echo "=============================================="
echo "Starting Voice Services"
echo "=============================================="
echo "Triton Model Repo: $TRITON_MODEL_REPO"
echo "RVC Model: $RVC_MODEL"
echo "RVC Workers: $RVC_WORKERS"
echo "API Port: $API_PORT"
echo "=============================================="

cd /workspace

# Start Triton server in background (internal gRPC for TTS)
echo "Starting Triton server..."
tritonserver \
    --model-repository="$TRITON_MODEL_REPO" \
    --log-verbose=0 \
    &
TRITON_PID=$!

# Wait for Triton to be ready
echo "Waiting for Triton to start..."
for i in {1..60}; do
    if curl -s localhost:8000/v2/health/ready > /dev/null 2>&1; then
        echo "Triton server ready!"
        break
    fi
    sleep 2
done

# Start Voice HTTP API (combines TTS + RVC internally)
echo "Starting Voice HTTP API..."
python3 -m rvc.api.voice_api \
    --rvc-model "$RVC_MODEL" \
    --rvc-workers "$RVC_WORKERS" \
    --triton-addr localhost \
    --triton-port 8001 \
    --host 0.0.0.0 \
    --port "$API_PORT" \
    &
API_PID=$!

# Wait for API to be ready
echo "Waiting for Voice API to start..."
for i in {1..30}; do
    if curl -s localhost:$API_PORT/health > /dev/null 2>&1; then
        echo "Voice API ready!"
        break
    fi
    sleep 2
done

echo "=============================================="
echo "Services started!"
echo "  Voice API: http://localhost:$API_PORT"
echo "    POST /synthesize     - Full TTS + RVC"
echo "    POST /tts            - TTS only"
echo "    POST /rvc            - RVC only"
echo "    GET  /health         - Health check"
echo "    GET  /status         - Detailed status"
echo "  Triton (internal): localhost:8001 (gRPC)"
echo "=============================================="

# Keep running (wait for either process to exit)
wait -n $TRITON_PID $API_PID

# If we get here, one of the services died
echo "A service has stopped unexpectedly"
exit 1
