# QuantumLogic

A composable static analysis framework for building project-specific code intelligence tools.

## Philosophy

QuantumLogic follows a **hierarchical composition model**:

```
┌─────────────────────────────────────────────────────────────┐
│  PROJECT MACROS (project-specific tools)                    │
│  analyze.js, schema.js, patterns.js, complexity.js, etc.    │
│  ↓ consume                                                  │
├─────────────────────────────────────────────────────────────┤
│  ORGANISMS (strategic reports)                              │
│  overview, health, refactor-plan                            │
│  ↓ compose                                                  │
├─────────────────────────────────────────────────────────────┤
│  MOLECULES (pattern detectors)                              │
│  dead-code, impact, hotspots, coupling, etc.                │
│  ↓ combine                                                  │
├─────────────────────────────────────────────────────────────┤
│  ATOMS (raw predicates)                                     │
│  DEFINES, CALLS, IMPORTS, MUTATES, COMPLEXITY, etc.         │
│  ↓ extract from                                             │
├─────────────────────────────────────────────────────────────┤
│  SOURCE CODE (Python, JS, etc.)                             │
└─────────────────────────────────────────────────────────────┘
```

### Framework vs Macros

| Aspect | QuantumLogic (Framework) | Macros |
|--------|--------------------------|--------|
| Purpose | Generic, reusable analysis | Project-specific tools |
| Scope | Language/pattern agnostic | Tuned for your codebase |
| Output | Structured predicates | Custom formatting |
| Updates | Rarely changes | Evolves with project |

**QuantumLogic** provides the building blocks.
**Macros** combine them for your specific needs.

## Quick Start

```bash
# Framework - generic analysis
node quantum-logic/atoms/index.js defines --path=src
node quantum-logic/molecules/index.js hotspots --path=src
node quantum-logic/organisms/index.js health --path=src

# Macros - project-specific (examples from this project)
node analyze.js calls my_function --path=src
node complexity.js --path=src --top=20
node patterns.js --path=src
```

## Core Concepts

### Atoms (Data Extraction)

Raw predicates extracted from source code. Language-specific parsers, universal concepts.

```
DEFINES(file, name, type, line)           # What exists
CALLS(file, caller, callee, line)         # What invokes what
IMPORTS(file, module, symbol, alias, line) # Dependencies
MUTATES(file, func, attribute, line)      # State changes
COMPLEXITY(file, func, cyc, cog, lines, nesting, params)
```

**Usage:**
```bash
node quantum-logic/atoms/index.js <atom> [--path=dir] [--format=predicate|json|tsv]

# Examples
node quantum-logic/atoms/index.js defines --path=rvc
node quantum-logic/atoms/index.js calls --path=rvc --format=json
```

### Molecules (Pattern Detection)

Composed queries that combine atoms to answer specific questions.

| Molecule | Atoms Combined | Question Answered |
|----------|----------------|-------------------|
| `dead-code` | DEFINES + CALLS | "What's never used?" |
| `impact` | CALLS + IMPORTS + DEFINES | "What breaks if I change X?" |
| `hotspots` | COMPLEXITY + MUTATES + IMPORTS | "Where are the problems?" |
| `risk-score` | COMPLEXITY × MUTATES | "What's dangerous to modify?" |
| `circular` | IMPORTS | "Are there dependency cycles?" |

**Usage:**
```bash
node quantum-logic/molecules/index.js <molecule> [target] [--path=dir]

# Examples
node quantum-logic/molecules/index.js hotspots --path=rvc
node quantum-logic/molecules/index.js impact TTSRVCPipeline --path=rvc
```

### Organisms (Strategic Reports)

High-level reports combining multiple molecules for decision-making.

| Organism | Purpose | Use Case |
|----------|---------|----------|
| `overview` | Full codebase summary | Onboarding, documentation |
| `health` | Quality score (A-F grade) | CI/CD gates, tech debt tracking |
| `refactor-plan` | Safe refactoring steps | Before major changes |

**Usage:**
```bash
node quantum-logic/organisms/index.js <organism> [target] [--path=dir]

# Examples
node quantum-logic/organisms/index.js overview --path=rvc
node quantum-logic/organisms/index.js health --path=rvc
node quantum-logic/organisms/index.js refactor-plan MyClass --path=rvc
```

## Building Project Macros

Macros are your project-specific tools that consume QuantumLogic.

### Macro Patterns

#### 1. Wrapper Macro
Simplify framework calls with project defaults:

```javascript
// my-health.js - Always check 'src' with custom thresholds
const { execSync } = require('child_process');

const output = execSync('node quantum-logic/organisms/index.js health --path=src',
  { encoding: 'utf8' });

// Apply project-specific thresholds
const score = extractScore(output);
if (score < 80) {
  console.error('Health check failed! Score:', score);
  process.exit(1);
}
```

#### 2. Composition Macro
Chain multiple framework calls:

```javascript
// security-audit.js - Combine atoms for security analysis
const { execSync } = require('child_process');

// Get all HTTP endpoints
const endpoints = runMolecule('endpoints', 'src');

// Check each handler for dangerous patterns
const calls = runAtom('calls', 'src');
const dangerous = ['eval', 'exec', 'subprocess.run', 'os.system'];

for (const endpoint of endpoints) {
  const handlerCalls = calls.filter(c => c.caller === endpoint.handler);
  const risks = handlerCalls.filter(c => dangerous.includes(c.callee));
  if (risks.length > 0) {
    console.warn(`⚠️ ${endpoint.route} calls dangerous: ${risks.map(r => r.callee)}`);
  }
}
```

#### 3. Extension Macro
Add project-specific logic:

```javascript
// find-grpc-issues.js - Project-specific pattern
const { runAtom, parsePredicates } = require('./quantum-logic/atoms/utils');

const inherits = parsePredicates(runAtom('inherits', 'src'));
const defines = parsePredicates(runAtom('defines', 'src'));

// Find gRPC servicers missing required methods
const servicers = inherits.filter(i => i.args[2].includes('Servicer'));
const required = ['Health', 'GetStatus'];

for (const servicer of servicers) {
  const methods = defines.filter(d =>
    d.args[1].startsWith(servicer.args[1] + '.') &&
    d.args[2] === 'method'
  );

  const methodNames = methods.map(m => m.args[1].split('.')[1]);
  const missing = required.filter(r => !methodNames.includes(r));

  if (missing.length > 0) {
    console.warn(`${servicer.args[1]} missing: ${missing.join(', ')}`);
  }
}
```

#### 4. Format Macro
Custom output for your workflow:

```javascript
// jira-export.js - Format for JIRA import
const { execSync } = require('child_process');

const hotspots = JSON.parse(
  execSync('node quantum-logic/molecules/index.js hotspots --path=src --format=json')
);

// Convert to JIRA-compatible CSV
console.log('Summary,Priority,Labels,Description');
for (const h of hotspots) {
  const priority = h.score > 50 ? 'High' : 'Medium';
  console.log(`"Refactor ${h.file}",${priority},tech-debt,"${h.reasons.join('; ')}"`);
}
```

### Macro Best Practices

1. **Import from QuantumLogic** - Don't duplicate parsing logic
2. **Project defaults** - Encode your paths, thresholds, patterns
3. **Specific output** - Format for your team's tools (Slack, JIRA, etc.)
4. **Combine insights** - Chain multiple framework calls for richer analysis

## Available Components

### Atoms (11)

| Atom | Predicate | Description |
|------|-----------|-------------|
| `defines` | `DEFINES(file, name, type, line)` | Functions, classes, methods |
| `calls` | `CALLS(file, caller, callee, line)` | Function/method calls |
| `imports` | `IMPORTS(file, module, symbol, alias, line)` | Import statements |
| `mutates` | `MUTATES(file, func, attr, line)` | Attribute assignments |
| `params` | `PARAMS(file, func, name, has_type, has_default, line)` | Function parameters |
| `returns` | `RETURNS(file, func, has_value, line)` | Return statements |
| `decorates` | `DECORATES(file, decorator, target, line)` | Decorator usage |
| `inherits` | `INHERITS(file, child, parent, line)` | Class inheritance |
| `files` | `FILES(path, name, type, depth)` | File structure |
| `exports` | `EXPORTS(file, symbol, line)` | Public API (__all__) |
| `complexity` | `COMPLEXITY(file, func, cyc, cog, lines, nest, params)` | Complexity metrics |

### Molecules (14)

| Molecule | Description |
|----------|-------------|
| `dead-code` | Find defined symbols never called |
| `impact` | What depends on a given symbol |
| `endpoints` | Map HTTP routes to handlers |
| `side-effects` | Functions that mutate state |
| `coupling` | Module interdependencies |
| `entry-points` | Find all external entry points |
| `orphans` | Files not imported anywhere |
| `hierarchy` | File/class/method tree view |
| `circular` | Circular dependencies |
| `duplicates` | Duplicate code detection |
| `patterns` | Architectural pattern detection |
| `risk-score` | Complexity × mutations ranking |
| `api-surface` | Public API complexity |
| `hotspots` | Multi-signal problem areas |

### Organisms (3)

| Organism | Description |
|----------|-------------|
| `overview` | Complete codebase summary |
| `health` | Health score with A-F grade |
| `refactor-plan` | Safe refactoring guide |

## Extending QuantumLogic

### Adding a New Atom

```javascript
// quantum-logic/atoms/my-atom.js
const { collectPythonFiles, createEmitter } = require('./utils');

function myAtom(scanPath) {
  const { emit } = createEmitter('MY_ATOM');
  const files = collectPythonFiles(scanPath);

  for (const file of files) {
    // Parse file and emit predicates
    emit(file, 'arg1', 'arg2', lineNumber);
  }
}

module.exports = myAtom;
```

### Adding a New Molecule

```javascript
// quantum-logic/molecules/my-molecule.js
const { runAtom, parsePredicates, printHeader } = require('./utils');

function myMolecule(scanPath) {
  printHeader('My Analysis');

  const defines = parsePredicates(runAtom('defines', scanPath));
  const calls = parsePredicates(runAtom('calls', scanPath));

  // Combine atoms and produce insights
  // ...
}

module.exports = myMolecule;
```

### Adding a New Organism

```javascript
// quantum-logic/organisms/my-organism.js
const { runMolecule, printHeader } = require('./utils');

function myOrganism(scanPath) {
  printHeader('My Report');

  // Run multiple molecules
  const hotspots = runMolecule('hotspots', scanPath);
  const deadCode = runMolecule('dead-code', scanPath);

  // Combine into strategic report
  // ...
}

module.exports = myOrganism;
```

## Output Formats

Atoms support three output formats via `--format`:

| Format | Use Case |
|--------|----------|
| `predicate` (default) | Human readable, grep-friendly |
| `json` | Programmatic consumption |
| `tsv` | Shell pipelines, spreadsheets |

```bash
# Grep-friendly
node quantum-logic/atoms/index.js calls --path=src | grep "dangerous_func"

# JSON for scripts
node quantum-logic/atoms/index.js defines --path=src --format=json | jq '.[] | .name'

# TSV for spreadsheets
node quantum-logic/atoms/index.js complexity --path=src --format=tsv > metrics.tsv
```

## Language Support

**Current:** Python

QuantumLogic is designed for multi-language support:
- Atoms are language-specific (parsing)
- Molecules are language-agnostic (work on predicates)
- Organisms are language-agnostic (work on molecules)

To add a new language, create language-specific atom parsers that emit the same predicates.

## Design Principles

1. **Composability** - Small pieces that combine predictably
2. **Predicate-based** - Uniform data format across all components
3. **Progressive detail** - Atoms → Molecules → Organisms → Macros
4. **Separation of concerns** - Framework = generic, Macros = specific
5. **Unix philosophy** - Do one thing well, combine with others
