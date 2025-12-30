/**
 * Molecule: PATTERNS
 * Detect architectural patterns in the codebase
 */

const fs = require('fs');
const path = require('path');
const { runAtom, parsePredicates, printHeader, printSection } = require('./utils');

// Pattern definitions
const PATTERN_DEFS = {
    ipc: {
        grpc: {
            markers: ['grpc', 'InferenceServerClient', 'Servicer'],
            description: 'gRPC client/server',
        },
        http: {
            markers: ['FastAPI', 'Flask', 'requests.get', 'requests.post', 'httpx'],
            description: 'HTTP client/server',
        },
        queue: {
            markers: ['Queue', 'JoinableQueue', 'multiprocessing.Queue'],
            description: 'Queue-based IPC',
        },
        socket: {
            markers: ['socket.socket', 'SOCK_STREAM', 'bind(', 'listen('],
            description: 'Raw socket',
        },
    },
    process: {
        multiprocessing: {
            markers: ['Process(target=', 'Pool(', 'mp.Manager'],
            description: 'Multiprocessing workers',
        },
        threading: {
            markers: ['Thread(target=', 'threading.Lock', 'daemon=True'],
            description: 'Threading',
        },
        subprocess: {
            markers: ['subprocess.Popen', 'subprocess.run'],
            description: 'Subprocess management',
        },
    },
    structural: {
        singleton: {
            markers: ['_instance = None', 'global _', '@lru_cache'],
            description: 'Singleton pattern',
        },
        factory: {
            markers: ['def create_', 'def make_', 'def build_', 'Factory'],
            description: 'Factory pattern',
        },
        contextManager: {
            markers: ['def __enter__', 'def __exit__', '@contextmanager'],
            description: 'Context manager',
        },
    },
    clientServer: {
        client: {
            markers: ['class.*Client', 'def connect(', 'def close('],
            description: 'Client class',
        },
        server: {
            markers: ['class.*Server', 'def start(', 'def serve(', 'def listen('],
            description: 'Server class',
        },
    },
};

function patterns(scanPath) {
    printHeader('Architectural Patterns');

    const imports = parsePredicates(runAtom('imports', scanPath));
    const defines = parsePredicates(runAtom('defines', scanPath));
    const decorates = parsePredicates(runAtom('decorates', scanPath));
    const inherits = parsePredicates(runAtom('inherits', scanPath));

    // Get unique files
    const files = [...new Set([
        ...imports.map(i => i.args[0]),
        ...defines.map(d => d.args[0]),
    ])];

    // Analyze each file for patterns
    const results = new Map(); // pattern -> [files]

    for (const file of files) {
        try {
            const fullPath = path.resolve(file);
            const content = fs.readFileSync(fullPath, 'utf-8');

            for (const [category, patterns] of Object.entries(PATTERN_DEFS)) {
                for (const [name, def] of Object.entries(patterns)) {
                    const key = `${category}:${name}`;

                    for (const marker of def.markers) {
                        // Handle regex-like patterns
                        let found = false;
                        if (marker.includes('.*')) {
                            const regex = new RegExp(marker);
                            found = regex.test(content);
                        } else {
                            found = content.includes(marker);
                        }

                        if (found) {
                            if (!results.has(key)) {
                                results.set(key, {
                                    category,
                                    name,
                                    description: def.description,
                                    files: [],
                                });
                            }
                            if (!results.get(key).files.includes(file)) {
                                results.get(key).files.push(file);
                            }
                            break;
                        }
                    }
                }
            }
        } catch (e) {
            // Skip unreadable files
        }
    }

    // Also detect patterns from atoms

    // HTTP endpoints from decorators
    const httpEndpoints = decorates.filter(d =>
        d.args[1].match(/^(app|router)\.(get|post|put|delete|patch)$/)
    );
    if (httpEndpoints.length > 0) {
        const key = 'ipc:http-endpoints';
        results.set(key, {
            category: 'ipc',
            name: 'http-endpoints',
            description: `HTTP endpoints (${httpEndpoints.length} routes)`,
            files: [...new Set(httpEndpoints.map(e => e.args[0]))],
        });
    }

    // gRPC servicers from inheritance
    const grpcServicers = inherits.filter(i => i.args[2].includes('Servicer'));
    if (grpcServicers.length > 0) {
        const key = 'ipc:grpc-servicer';
        results.set(key, {
            category: 'ipc',
            name: 'grpc-servicer',
            description: `gRPC servicers (${grpcServicers.length})`,
            files: [...new Set(grpcServicers.map(s => s.args[0]))],
        });
    }

    // Dataclasses from decorators
    const dataclasses = decorates.filter(d => d.args[1] === 'dataclass');
    if (dataclasses.length > 0) {
        const key = 'structural:dataclass';
        results.set(key, {
            category: 'structural',
            name: 'dataclass',
            description: `Dataclasses (${dataclasses.length})`,
            files: [...new Set(dataclasses.map(d => d.args[0]))],
        });
    }

    // Print by category
    const categories = ['ipc', 'process', 'structural', 'clientServer'];

    for (const cat of categories) {
        const catResults = [...results.entries()].filter(([_, v]) => v.category === cat);

        if (catResults.length > 0) {
            const catName = {
                ipc: 'IPC Mechanisms',
                process: 'Process Management',
                structural: 'Structural Patterns',
                clientServer: 'Client-Server',
            }[cat];

            printSection(catName);

            for (const [key, data] of catResults) {
                const icon = {
                    ipc: '🔌',
                    process: '⚙️',
                    structural: '🏗️',
                    clientServer: '📡',
                }[cat];

                console.log(`  ${icon} \x1b[1m${data.description}\x1b[0m`);
                for (const file of data.files.slice(0, 3)) {
                    console.log(`     \x1b[90m${file}\x1b[0m`);
                }
                if (data.files.length > 3) {
                    console.log(`     \x1b[90m... and ${data.files.length - 3} more\x1b[0m`);
                }
            }
        }
    }

    // Pattern co-occurrence
    printSection('Pattern Relationships');

    const filePatterns = new Map(); // file -> [patterns]
    for (const [key, data] of results) {
        for (const file of data.files) {
            if (!filePatterns.has(file)) {
                filePatterns.set(file, []);
            }
            filePatterns.get(file).push(data.name);
        }
    }

    // Find files with multiple patterns
    const multiPattern = [...filePatterns.entries()]
        .filter(([_, patterns]) => patterns.length >= 2)
        .sort((a, b) => b[1].length - a[1].length);

    if (multiPattern.length > 0) {
        console.log('  Files with multiple patterns:');
        for (const [file, pats] of multiPattern.slice(0, 5)) {
            console.log(`    \x1b[36m${file}\x1b[0m`);
            console.log(`      ${pats.join(', ')}`);
        }
    } else {
        console.log('  \x1b[90mNo significant pattern co-occurrence\x1b[0m');
    }

    // Summary
    console.log(`\n\x1b[33mTotal: ${results.size} patterns detected across ${files.length} files\x1b[0m`);
}

module.exports = patterns;
