# Triton Spark TTS + RVC Server

## Project Overview

This project provides a parallel TTS (Text-to-Speech) + RVC (Retrieval-based Voice Conversion) pipeline using:
- Triton Inference Server for Spark TTS
- Custom RVC server with multiprocessing workers for parallel voice conversion

## Utility Scripts

### replace.js
**Purpose:** Project-wide find and replace (like Ctrl+Shift+H in VSCode)

\`\`\`bash
# Usage
node replace.js "pattern" "replacement" [--path=dir] [--ext=py,js] [--dry-run]

# Examples
node replace.js "from infer\." "from rvc.infer." --ext=py
node replace.js "oldFunc" "newFunc" --path=src --dry-run
node replace.js "console\.log\((.*)\)" "logger.info(\$1)" --ext=js,ts
\`\`\`

### analyze.js
**Purpose:** Semantic code projections - understand codebase from different angles

\`\`\`bash
# Import dependency graph - shows how modules depend on each other
node analyze.js imports --path=rvc

# Class hierarchy - shows classes, inheritance, methods (public/private/magic)
node analyze.js classes --path=rvc/processing

# Call sites - find where a function/method is called
node analyze.js calls submit_job

# Module exports - shows __all__ public API definitions
node analyze.js exports --path=rvc

# Data flow - shows instance attributes and what methods mutate state
node analyze.js dataflow TTSRVCPipeline
\`\`\`

### schema.js
**Purpose:** Generate logical projections showing structure without implementation details

\`\`\`bash
# Show class/function signatures only (default)
node schema.js --path=rvc/server --mode=signatures

# Show file/class/method hierarchy
node schema.js --path=rvc --mode=structure

# Show public API (__all__ exports with their signatures)
node schema.js --path=rvc --mode=api

# Show dataclasses and type definitions
node schema.js --path=rvc --mode=types

# Output to file for later reference
node schema.js --path=rvc --mode=signatures --output=SCHEMA.txt
\`\`\`

### patterns.js
**Purpose:** Detect architectural patterns to avoid reinventing the wheel

\`\`\`bash
# Run all pattern detections
node patterns.js --path=rvc

# Find IPC mechanisms (socket, grpc, queue, http, file)
node patterns.js ipc --path=rvc

# Find process/thread management patterns
node patterns.js process --path=rvc

# Find client-server patterns
node patterns.js clientserver --path=rvc

# Find similar implementations (potential duplication)
node patterns.js similar --path=rvc

# Find singleton/factory patterns
node patterns.js structural --path=rvc
\`\`\`

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│  Container (Docker/udocker)                             │
│  ┌─────────────────┐    ┌─────────────────────────────┐ │
│  │ Triton Server   │◄───│ Voice HTTP API (:8080)      │ │
│  │ (Spark TTS)     │    │ - FastAPI wrapper           │ │
│  │ :8001 gRPC      │    │ - TTS + RVC combined        │ │
│  │ (internal)      │    │ - N parallel RVC workers    │ │
│  └─────────────────┘    └─────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘
                                   ▲
                                   │ HTTP
                                   ▼
                            External clients
```

- **Triton Server**: Runs Spark TTS internally (gRPC on port 8001)
- **Voice HTTP API**: External-facing FastAPI server (port 8080)
- **RVC**: Runs inline within the HTTP API (multiprocessing workers)

## Voice HTTP API

### Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/synthesize` | Full TTS + RVC pipeline |
| `POST` | `/synthesize/stream` | Streaming audio response |
| `POST` | `/tts` | TTS only (no voice conversion) |
| `POST` | `/rvc` | RVC only (convert existing audio) |
| `GET` | `/health` | Health check |
| `GET` | `/status` | Detailed status |

### Python Client Usage

```python
import requests

API_URL = "http://localhost:8080"

# Full synthesis (TTS + RVC)
with open("reference.wav", "rb") as f:
    response = requests.post(
        f"{API_URL}/synthesize",
        data={
            "text": "Hello world!",
            "reference_text": "",
            "pitch_shift": 0,
            "f0_method": "rmvpe",
            "index_rate": 0.75,
        },
        files={"reference_audio": ("ref.wav", f, "audio/wav")}
    )

# Save result
with open("output.wav", "wb") as f:
    f.write(response.content)

# Get timing from headers
tts_time = float(response.headers.get("X-TTS-Time", 0))
rvc_time = float(response.headers.get("X-RVC-Time", 0))
```

## Docker Deployment

```bash
# Build unified voice service
docker build -f Dockerfile.voice -t voice-server .

# Start with docker-compose
docker-compose -f docker-compose.voice.yml up -d

# Check status
docker-compose -f docker-compose.voice.yml ps

# View logs
docker-compose -f docker-compose.voice.yml logs -f voice

# Stop services
docker-compose -f docker-compose.voice.yml down
```

## Colab/udocker Deployment

For Google Colab, use the unified notebook:

```bash
# See colab/triton_spark_rvc_unified.ipynb
# Runs both Triton and Voice API in single udocker container
```

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `RVC_MODEL` | `SilverWolf_e300_s6600.pth` | RVC model filename in weights/ |
| `RVC_WORKERS` | `2` | Number of parallel RVC workers |
| `API_PORT` | `8080` | Voice HTTP API port |
| `TRITON_MODEL_REPO` | `/workspace/triton/model_repo_test` | Triton model repo path |

## Key Directories

- `triton/` - Triton Inference Server for Spark TTS
  - `triton/model_repo/` - Model repository (spark_tts, vocoder, audio_tokenizer)
  - `triton/run.sh` - Build/run script (stages 0-5)
  - `triton/scripts/` - Checkpoint conversion scripts
- `rvc/` - RVC inference and server code
  - `rvc/api/` - Voice HTTP API (FastAPI, external-facing)
  - `rvc/server/` - RVC server with multiprocessing workers
  - `rvc/processing/` - Pipeline, workers, buffer management
  - `rvc/infer/` - Core RVC inference code
  - `rvc/grpc/` - gRPC definitions (internal Triton communication)
- `sparktts/` - Spark TTS model code (audio tokenizer, vocoder)
- `tests/` - Test scripts for Colab
  - `tests/test_http_api.py` - HTTP API endpoint tests
  - `tests/test_pipeline.py` - Full TTS+RVC pipeline test
  - `tests/test_connection.py` - Server connection tests
- `tools/` - CLI utilities
  - `tools/download_all_assets.py` - Download models and assets
  - `tools/setup_environment.py` - Environment setup
  - `tools/rvc_server_control.py` - RVC server control
- `scripts/` - Container startup scripts
  - `scripts/start_services.sh` - Starts Triton + Voice API
- `colab/` - Jupyter notebooks for Colab deployment

## Testing (from Colab)

```bash
# Test API health and status
python -m tests.test_http_api --host localhost --port 8080

# Full test with synthesis
python -m tests.test_http_api --host localhost --port 8080 --reference ref.wav --full

# Test individual components
python -m tests.test_connection --host localhost
python -m tests.test_tts --host localhost --port 8001 --reference ref.wav
python -m tests.test_rvc --host localhost --port 8080 --input audio.wav
python -m tests.test_pipeline --host localhost --port 8080 --reference ref.wav
```

## Common Commands

```bash
# Start RVC server (local development)
python tools/rvc_server_control.py start --model SilverWolf_e300_s6600.pth --workers 2

# Check server status
python tools/rvc_server_control.py status

# Stop RVC server
python tools/rvc_server_control.py stop
```

### complexity.js
**Purpose:** Identify complexity hotspots for refactoring priorities

\`\`\`bash
# Analyze all files, show top 20 complex functions
node complexity.js --path=rvc --top=20

# Analyze single file
node complexity.js --file=rvc/processing/pipeline.py

# Find functions above complexity threshold
node complexity.js --path=rvc --threshold=15

# Analyze specific function
node complexity.js --function=process --path=rvc
\`\`\`

### deps.js
**Purpose:** Dependency graph analysis with impact assessment

\`\`\`bash
# Show full dependency graph
node deps.js --path=rvc

# Impact analysis - what breaks if I change this?
node deps.js impact rvc_server --path=rvc

# What does this module depend on?
node deps.js depends pipeline --path=rvc

# Find circular dependencies
node deps.js circular --path=rvc

# Coupling metrics (stability analysis)
node deps.js coupling --path=rvc

# Suggest layer structure
node deps.js layers --path=rvc
\`\`\`

### refactor.js
**Purpose:** Safe refactoring helper

\`\`\`bash
# Find all usages of a symbol
node refactor.js usages RVCClient --path=rvc

# Preview rename operation
node refactor.js rename old_name new_name --path=rvc --dry-run

# Find duplicate code blocks
node refactor.js duplicates --path=rvc

# Find unused definitions
node refactor.js unused --path=rvc

# Check safety of moving a symbol
node refactor.js move RVCClient rvc.client --path=rvc
\`\`\`
