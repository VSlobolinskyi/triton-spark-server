# Triton Spark TTS + RVC Server

## Project Overview

This project provides a parallel TTS (Text-to-Speech) + RVC (Retrieval-based Voice Conversion) pipeline using:
- Triton Inference Server for Spark TTS
- Custom RVC server with multiprocessing workers for parallel voice conversion

---

## Code Analysis: QuantumLogic + Macros

**USE THESE FIRST before grep/glob/read.** Semantic code intelligence tools that understand your codebase structure.

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  macros/  (project-specific tools)                          │
│  analyze.js, schema.js, patterns.js, grpc-audit.js, etc.    │
│  ↓ consume                                                  │
├─────────────────────────────────────────────────────────────┤
│  quantum-logic/  (generic framework)                        │
│  Organisms → Molecules → Atoms                              │
│  See quantum-logic/README.md for full docs                  │
└─────────────────────────────────────────────────────────────┘
```

### Quick Start

```bash
# List available macros
node macros/index.js

# 1. Project structure overview
node macros/generate-structure.js              # Full project tree → struct.txt

# 2. Codebase health (uses QuantumLogic)
node quantum-logic/organisms/index.js health --path=rvc

# 3. Find hotspots
node quantum-logic/molecules/index.js hotspots --path=rvc

# 4. Derive new macros for your project
node quantum-logic/derive-macros.js --path=rvc --generate
```

### When to Use What

| Task | Use This | NOT This |
|------|----------|----------|
| List macros | `node macros/index.js` | - |
| Get project tree | `node macros/generate-structure.js` | ls/find/tree |
| Codebase health | `node quantum-logic/organisms/index.js health` | manual review |
| Find hotspots | `node quantum-logic/molecules/index.js hotspots` | grep |
| Find call sites | `node macros/analyze.js calls func_name` | grep |
| Class hierarchy | `node macros/analyze.js classes --path=rvc` | reading files |
| Rename codebase | `node macros/replace.js "old" "new" --dry-run` | sed |
| gRPC services | `node macros/grpc-audit.js` | grep |
| API endpoints | `node macros/api-docs.js` | reading files |

### Project Macros

```bash
# LIST ALL MACROS
node macros/index.js

# STRUCTURE
node macros/generate-structure.js                  # Full project tree → struct.txt
node macros/schema.js --path=rvc --mode=structure  # File/class/method hierarchy
node macros/schema.js --path=rvc --mode=api        # Public API with signatures

# ANALYSIS
node macros/analyze.js imports --path=rvc          # Module dependency graph
node macros/analyze.js classes --path=rvc          # Class hierarchy with methods
node macros/analyze.js calls submit_job            # Find all call sites
node macros/analyze.js exports --path=rvc          # Public API (__all__)
node macros/analyze.js dataflow TTSRVCPipeline     # Instance attributes & mutations

# PATTERNS (auto-generated from QuantumLogic)
node macros/grpc-audit.js                          # gRPC servicers and methods
node macros/api-docs.js                            # HTTP API documentation
node macros/model-audit.js                         # ML/Triton model usage
node macros/worker-audit.js                        # Multiprocessing workers
node macros/resource-audit.js                      # Context managers

# REFACTORING
node macros/replace.js "old" "new" --dry-run       # Preview project-wide replace
node macros/replace.js "old" "new"                 # Execute replace
node macros/refactor.js usages Symbol --path=rvc   # Find all usages of symbol
node macros/refactor.js duplicates --path=rvc      # Find duplicate code blocks

# DEPENDENCIES & COMPLEXITY
node macros/deps.js --path=rvc                     # Full dependency graph
node macros/deps.js impact module --path=rvc       # What breaks if I change this?
node macros/complexity.js --path=rvc --top=20      # Top 20 complex functions
```

### QuantumLogic Framework (Generic)

```bash
# ORGANISMS (strategic reports)
node quantum-logic/organisms/index.js overview --path=rvc      # Full codebase summary
node quantum-logic/organisms/index.js health --path=rvc        # Health score (A-F grade)
node quantum-logic/organisms/index.js refactor-plan X --path=rvc  # Safe refactoring guide

# MOLECULES (pattern detection)
node quantum-logic/molecules/index.js hotspots --path=rvc      # Multi-signal problem areas
node quantum-logic/molecules/index.js risk-score --path=rvc    # Complexity × mutations
node quantum-logic/molecules/index.js api-surface --path=rvc   # Public API complexity
node quantum-logic/molecules/index.js dead-code --path=rvc     # Unused functions
node quantum-logic/molecules/index.js circular --path=rvc      # Circular dependencies
node quantum-logic/molecules/index.js impact X --path=rvc      # What depends on symbol
node quantum-logic/molecules/index.js patterns --path=rvc      # Architectural patterns

# ATOMS (raw predicates)
node quantum-logic/atoms/index.js defines --path=rvc    # DEFINES(file, name, type, line)
node quantum-logic/atoms/index.js calls --path=rvc      # CALLS(file, caller, callee, line)
node quantum-logic/atoms/index.js mutates --path=rvc    # MUTATES(file, func, attr, line)
node quantum-logic/atoms/index.js complexity --path=rvc # COMPLEXITY(file, func, cyc, ...)
```

### Deriving New Macros

QuantumLogic can analyze your codebase and suggest project-specific macros:

```bash
# See what macros would be useful
node quantum-logic/derive-macros.js --path=rvc

# Generate the suggested macros
node quantum-logic/derive-macros.js --path=rvc --generate
```

### Using QuantumLogic in Custom Macros

```javascript
// In macros/*.js files:
const ql = require('../quantum-logic');

// Get parsed predicates
const defines = ql.atom('defines', 'rvc');
const calls = ql.atom('calls', 'rvc');

// Run molecules/organisms
const output = ql.molecule('hotspots', 'rvc');
const health = ql.organism('health', 'rvc');

// Helpers
const byFile = ql.groupBy(defines, 'file');
const filtered = ql.filter(calls, { contains: 'TTSRVCPipeline' });
```

---

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

## Key Directories

- `triton/` - Triton Inference Server for Spark TTS
  - `triton/model_repo/` - Model repository (spark_tts, vocoder, audio_tokenizer)
  - `triton/run.sh` - Build/run script (stages 0-5)
- `rvc/` - RVC inference and server code
  - `rvc/api/` - Voice HTTP API (FastAPI, external-facing)
  - `rvc/server/` - RVC server with multiprocessing workers
  - `rvc/processing/` - Pipeline, workers, buffer management
  - `rvc/infer/` - Core RVC inference code
- `sparktts/` - Spark TTS model code (audio tokenizer, vocoder)
- `tests/` - Test scripts for Colab
- `tools/` - CLI utilities (download_all_assets.py, rvc_server_control.py)
- `scripts/` - Container startup scripts
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

## Deployment

### Docker
```bash
docker-compose -f docker-compose.voice.yml up -d
```

### Colab/udocker
See `colab/triton_spark_rvc_unified.ipynb`

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `RVC_MODEL` | `SilverWolf_e300_s6600.pth` | RVC model filename |
| `RVC_WORKERS` | `2` | Number of parallel RVC workers |
| `API_PORT` | `8080` | Voice HTTP API port |
| `TRITON_MODEL_REPO` | `/workspace/triton/model_repo_test` | Triton model repo |
