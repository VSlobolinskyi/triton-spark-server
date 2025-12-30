#!/usr/bin/env node
/**
 * patterns.js - Detect architectural patterns in Python codebase
 *
 * Helps identify existing solutions to avoid reinventing the wheel.
 * Analyzes code for common patterns like client-server, IPC, singletons, etc.
 *
 * Usage:
 *   node patterns.js [command] [--path=dir]
 *
 * Commands:
 *   all          - Run all pattern detections (default)
 *   ipc          - Find IPC mechanisms (socket, grpc, queue, http)
 *   singleton    - Find singleton/global state patterns
 *   client       - Find client classes (things that connect to servers)
 *   server       - Find server classes (things that listen/serve)
 *   factory      - Find factory/builder patterns
 *   process      - Find process/thread management
 *   similar      - Find similar implementations (potential duplication)
 */

const fs = require('fs');
const path = require('path');

// Parse arguments
const args = process.argv.slice(2);
const command = args.find(a => !a.startsWith('--')) || 'all';
const getArg = (name, def) => {
    const arg = args.find(a => a.startsWith(`--${name}=`));
    return arg ? arg.split('=')[1] : def;
};

const targetPath = getArg('path', '.');
const maxDepth = parseInt(getArg('depth', '10'));

// Pattern definitions
const PATTERNS = {
    // IPC mechanisms
    ipc: {
        socket: {
            imports: ['socket', 'socketserver'],
            patterns: [
                /socket\.socket\s*\(/,
                /\.bind\s*\(\s*\(/,
                /\.listen\s*\(/,
                /\.accept\s*\(/,
                /SOCK_STREAM|SOCK_DGRAM/,
            ],
            description: 'Raw socket communication',
        },
        grpc: {
            imports: ['grpc', 'tritonclient.grpc', 'grpcclient'],
            patterns: [
                /grpc\./,
                /InferenceServerClient/,
                /\.infer\s*\(/,
            ],
            description: 'gRPC client/server',
        },
        queue: {
            imports: ['multiprocessing.Queue', 'queue.Queue', 'asyncio.Queue'],
            patterns: [
                /Queue\s*\(/,
                /\.put\s*\(/,
                /\.get\s*\(/,
                /JoinableQueue/,
            ],
            description: 'Queue-based IPC',
        },
        http: {
            imports: ['requests', 'httpx', 'aiohttp', 'flask', 'fastapi', 'uvicorn'],
            patterns: [
                /requests\.(get|post|put|delete)/,
                /httpx\.(get|post)/,
                /app\s*=\s*(Flask|FastAPI)/,
            ],
            description: 'HTTP client/server',
        },
        pipe: {
            imports: ['subprocess.PIPE', 'os.pipe'],
            patterns: [
                /subprocess\.Popen/,
                /PIPE/,
                /os\.pipe\s*\(/,
            ],
            description: 'Pipe/subprocess communication',
        },
        file: {
            imports: [],
            patterns: [
                /STATUS_FILE|PID_FILE|LOCK_FILE/i,
                /\.json\s*['"].*status/i,
                /fcntl\.flock/,
            ],
            description: 'File-based IPC (status files, locks)',
        },
    },

    // Process management
    process: {
        multiprocessing: {
            imports: ['multiprocessing', 'Process', 'Pool'],
            patterns: [
                /Process\s*\(target=/,
                /Pool\s*\(/,
                /\.start\s*\(\)/,
                /\.join\s*\(\)/,
                /mp\.Manager/,
            ],
            description: 'Multiprocessing workers',
        },
        threading: {
            imports: ['threading', 'Thread'],
            patterns: [
                /Thread\s*\(target=/,
                /threading\.Lock/,
                /daemon\s*=\s*True/,
            ],
            description: 'Threading',
        },
        subprocess: {
            imports: ['subprocess'],
            patterns: [
                /subprocess\.Popen/,
                /subprocess\.run/,
                /start_new_session/,
            ],
            description: 'Subprocess management',
        },
        signal: {
            imports: ['signal'],
            patterns: [
                /signal\.signal/,
                /SIGTERM|SIGINT|SIGKILL/,
            ],
            description: 'Signal handling',
        },
    },

    // Structural patterns
    structural: {
        singleton: {
            imports: [],
            patterns: [
                /_instance\s*=\s*None/,
                /global\s+_\w+/,
                /def\s+get_\w+\(\).*:\s*\n\s*global/,
                /@lru_cache.*\n.*def\s+get_/,
            ],
            description: 'Singleton/global instance pattern',
        },
        factory: {
            imports: [],
            patterns: [
                /def\s+create_\w+\s*\(/,
                /def\s+make_\w+\s*\(/,
                /def\s+build_\w+\s*\(/,
                /Factory\s*\(/,
            ],
            description: 'Factory/builder pattern',
        },
        contextManager: {
            imports: ['contextlib'],
            patterns: [
                /def\s+__enter__/,
                /def\s+__exit__/,
                /@contextmanager/,
            ],
            description: 'Context manager pattern',
        },
        dataclass: {
            imports: ['dataclass'],
            patterns: [
                /@dataclass/,
            ],
            description: 'Dataclass pattern',
        },
    },

    // Client-server patterns
    clientServer: {
        client: {
            imports: [],
            patterns: [
                /class\s+\w*Client\w*/,
                /def\s+connect\s*\(/,
                /def\s+close\s*\(/,
                /def\s+send\s*\(/,
                /def\s+recv\s*\(/,
            ],
            description: 'Client classes',
        },
        server: {
            imports: [],
            patterns: [
                /class\s+\w*Server\w*/,
                /def\s+start\s*\(/,
                /def\s+shutdown\s*\(/,
                /def\s+listen\s*\(/,
                /def\s+serve\s*\(/,
            ],
            description: 'Server classes',
        },
        daemon: {
            imports: [],
            patterns: [
                /daemon/i,
                /PID_FILE/,
                /start_new_session/,
                /nohup/,
            ],
            description: 'Daemon/background process',
        },
    },
};

// Collect Python files
function collectPythonFiles(dir, depth = 0) {
    if (depth > maxDepth) return [];

    const files = [];
    try {
        const entries = fs.readdirSync(dir, { withFileTypes: true });
        for (const entry of entries) {
            const fullPath = path.join(dir, entry.name);
            if (entry.name.startsWith('.') || entry.name === '__pycache__' ||
                entry.name === 'node_modules' || entry.name === 'venv' ||
                entry.name === '.git') continue;

            if (entry.isDirectory()) {
                files.push(...collectPythonFiles(fullPath, depth + 1));
            } else if (entry.name.endsWith('.py')) {
                files.push(fullPath);
            }
        }
    } catch (e) { /* ignore */ }
    return files;
}

// Analyze a file for patterns
function analyzeFile(filePath, patternCategory) {
    const content = fs.readFileSync(filePath, 'utf-8');
    const lines = content.split('\n');
    const results = [];

    for (const [patternName, config] of Object.entries(patternCategory)) {
        const matches = [];

        // Check imports
        for (const imp of config.imports) {
            const importRegex = new RegExp(`(from\\s+\\S*${imp}|import\\s+\\S*${imp})`, 'i');
            for (let i = 0; i < lines.length; i++) {
                if (importRegex.test(lines[i])) {
                    matches.push({ line: i + 1, text: lines[i].trim(), type: 'import' });
                }
            }
        }

        // Check patterns
        for (const pattern of config.patterns) {
            for (let i = 0; i < lines.length; i++) {
                if (pattern.test(lines[i])) {
                    matches.push({ line: i + 1, text: lines[i].trim(), type: 'pattern' });
                }
            }
        }

        if (matches.length > 0) {
            results.push({
                pattern: patternName,
                description: config.description,
                matches: matches,
            });
        }
    }

    return results;
}

// Find similar implementations across files
function findSimilarImplementations(files) {
    const signatures = new Map(); // signature -> [files]

    for (const filePath of files) {
        const content = fs.readFileSync(filePath, 'utf-8');
        const relPath = path.relative(process.cwd(), filePath);

        // Look for class definitions with their methods
        const classMatches = content.matchAll(/class\s+(\w+).*?(?=class\s+\w+|$)/gs);
        for (const match of classMatches) {
            const className = match[1];
            const classBody = match[0];

            // Extract method names
            const methods = [...classBody.matchAll(/def\s+(\w+)\s*\(/g)]
                .map(m => m[1])
                .filter(m => !m.startsWith('_'))
                .sort()
                .join(',');

            if (methods) {
                const sig = methods;
                if (!signatures.has(sig)) {
                    signatures.set(sig, []);
                }
                signatures.get(sig).push({ file: relPath, class: className });
            }
        }
    }

    // Find duplicates (same method signatures)
    const similar = [];
    for (const [sig, locations] of signatures) {
        if (locations.length > 1) {
            similar.push({
                methods: sig.split(','),
                locations: locations,
            });
        }
    }

    return similar;
}

// Format and print results
function printResults(title, results) {
    console.log(`\n${'═'.repeat(60)}`);
    console.log(`📊 ${title}`);
    console.log('═'.repeat(60));

    if (results.length === 0) {
        console.log('  No patterns found.');
        return;
    }

    for (const result of results) {
        console.log(`\n📁 ${result.file}`);
        for (const pattern of result.patterns) {
            console.log(`  ┌─ ${pattern.pattern} (${pattern.description})`);
            for (const match of pattern.matches.slice(0, 5)) {
                const typeIcon = match.type === 'import' ? '📦' : '🔍';
                console.log(`  │  ${typeIcon} L${match.line}: ${match.text.substring(0, 70)}`);
            }
            if (pattern.matches.length > 5) {
                console.log(`  │  ... and ${pattern.matches.length - 5} more`);
            }
            console.log(`  └─`);
        }
    }
}

// Print relationship map between patterns
function printRelationshipMap(allResults) {
    console.log(`\n${'═'.repeat(60)}`);
    console.log('🗺️  PATTERN RELATIONSHIP MAP');
    console.log('═'.repeat(60));

    // Group files by their patterns
    const patternToFiles = new Map();
    for (const result of allResults) {
        for (const pattern of result.patterns) {
            const key = pattern.pattern;
            if (!patternToFiles.has(key)) {
                patternToFiles.set(key, []);
            }
            patternToFiles.get(key).push(result.file);
        }
    }

    // Find co-occurring patterns
    const cooccurrence = new Map();
    for (const result of allResults) {
        const patterns = result.patterns.map(p => p.pattern);
        for (let i = 0; i < patterns.length; i++) {
            for (let j = i + 1; j < patterns.length; j++) {
                const key = [patterns[i], patterns[j]].sort().join(' + ');
                cooccurrence.set(key, (cooccurrence.get(key) || 0) + 1);
            }
        }
    }

    // Print pattern distribution
    console.log('\n📈 Pattern Distribution:');
    const sorted = [...patternToFiles.entries()].sort((a, b) => b[1].length - a[1].length);
    for (const [pattern, files] of sorted) {
        console.log(`  ${pattern}: ${files.length} file(s)`);
    }

    // Print common combinations
    console.log('\n🔗 Common Pattern Combinations:');
    const sortedCooc = [...cooccurrence.entries()]
        .filter(([_, count]) => count > 1)
        .sort((a, b) => b[1] - a[1]);

    if (sortedCooc.length === 0) {
        console.log('  No significant pattern combinations found.');
    } else {
        for (const [combo, count] of sortedCooc.slice(0, 10)) {
            console.log(`  ${combo}: ${count} file(s)`);
        }
    }
}

// Main execution
function main() {
    console.log('Pattern Detector');
    console.log(`Command: ${command}`);
    console.log(`Scanning: ${path.resolve(targetPath)}`);
    console.log('═'.repeat(60));

    const pythonFiles = collectPythonFiles(targetPath);
    console.log(`Found ${pythonFiles.length} Python files`);

    if (pythonFiles.length === 0) {
        console.log('No Python files found.');
        return;
    }

    let allResults = [];

    // Run based on command
    const runCategory = (name, category) => {
        const results = [];
        for (const filePath of pythonFiles) {
            const fileResults = analyzeFile(filePath, category);
            if (fileResults.length > 0) {
                results.push({
                    file: path.relative(process.cwd(), filePath),
                    patterns: fileResults,
                });
            }
        }
        printResults(name, results);
        allResults = allResults.concat(results);
    };

    switch (command) {
        case 'ipc':
            runCategory('IPC Mechanisms', PATTERNS.ipc);
            break;
        case 'process':
            runCategory('Process Management', PATTERNS.process);
            break;
        case 'singleton':
        case 'factory':
        case 'structural':
            runCategory('Structural Patterns', PATTERNS.structural);
            break;
        case 'client':
        case 'server':
        case 'clientserver':
            runCategory('Client-Server Patterns', PATTERNS.clientServer);
            break;
        case 'similar':
            const similar = findSimilarImplementations(pythonFiles);
            console.log(`\n${'═'.repeat(60)}`);
            console.log('🔄 SIMILAR IMPLEMENTATIONS');
            console.log('═'.repeat(60));
            if (similar.length === 0) {
                console.log('  No similar implementations found.');
            } else {
                for (const item of similar) {
                    console.log(`\nClasses with methods: [${item.methods.join(', ')}]`);
                    for (const loc of item.locations) {
                        console.log(`  📄 ${loc.file} → ${loc.class}`);
                    }
                }
            }
            break;
        case 'all':
        default:
            runCategory('IPC Mechanisms', PATTERNS.ipc);
            runCategory('Process Management', PATTERNS.process);
            runCategory('Structural Patterns', PATTERNS.structural);
            runCategory('Client-Server Patterns', PATTERNS.clientServer);
            printRelationshipMap(allResults);

            // Also check for similar implementations
            const simResults = findSimilarImplementations(pythonFiles);
            if (simResults.length > 0) {
                console.log(`\n${'═'.repeat(60)}`);
                console.log('⚠️  POTENTIAL DUPLICATIONS');
                console.log('═'.repeat(60));
                for (const item of simResults) {
                    console.log(`\nClasses with methods: [${item.methods.join(', ')}]`);
                    for (const loc of item.locations) {
                        console.log(`  📄 ${loc.file} → ${loc.class}`);
                    }
                }
            }
            break;
    }
}

main();
