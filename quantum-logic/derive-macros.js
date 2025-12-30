#!/usr/bin/env node
/**
 * QuantumLogic: Macro Derivation
 *
 * Analyzes a codebase and suggests project-specific macros based on detected patterns.
 *
 * Usage:
 *   node quantum-logic/derive-macros.js [--path=dir] [--generate]
 *
 * Options:
 *   --path=dir    Directory to analyze (default: .)
 *   --generate    Generate suggested macro files
 */

const { execSync } = require('child_process');
const fs = require('fs');
const path = require('path');

const QUANTUM_LOGIC_PATH = __dirname;

// Parse arguments
const args = process.argv.slice(2);
let scanPath = '.';
let shouldGenerate = false;

for (const arg of args) {
    if (arg.startsWith('--path=')) {
        scanPath = arg.slice(7);
    } else if (arg === '--generate') {
        shouldGenerate = true;
    }
}

// Helpers
function runAtom(atom) {
    try {
        return execSync(`node "${path.join(QUANTUM_LOGIC_PATH, 'atoms', 'index.js')}" ${atom} --path=${scanPath}`,
            { encoding: 'utf8', maxBuffer: 50 * 1024 * 1024 })
            .split('\n')
            .filter(l => l.startsWith(atom.toUpperCase()))
            .map(l => {
                const m = l.match(/^(\w+)\((.*)\)$/);
                return m ? { predicate: m[1], args: m[2].split(',').map(s => s.trim()) } : null;
            })
            .filter(Boolean);
    } catch (e) {
        return [];
    }
}

function runMolecule(molecule) {
    try {
        return execSync(`node "${path.join(QUANTUM_LOGIC_PATH, 'molecules', 'index.js')}" ${molecule} --path=${scanPath}`,
            { encoding: 'utf8', maxBuffer: 50 * 1024 * 1024 });
    } catch (e) {
        return '';
    }
}

// Pattern detectors
const MACRO_DETECTORS = {
    // gRPC patterns → grpc-audit macro
    grpc: {
        name: 'grpc-audit',
        description: 'Audit gRPC services, methods, and client usage',
        detect: (atoms) => {
            const inherits = atoms.inherits.filter(i => i.args[2].includes('Servicer'));
            const imports = atoms.imports.filter(i => i.args[1] === 'grpc');
            return inherits.length > 0 || imports.length > 0;
        },
        details: (atoms) => {
            const servicers = atoms.inherits.filter(i => i.args[2].includes('Servicer'));
            const grpcImports = atoms.imports.filter(i => i.args[1] === 'grpc');
            return {
                servicers: servicers.map(s => ({ name: s.args[1], file: s.args[0] })),
                filesUsingGrpc: [...new Set(grpcImports.map(i => i.args[0]))].length,
            };
        },
        template: () => `


// Find all gRPC servicers
const inherits = ql.atom('inherits', '${scanPath}');
const servicers = inherits.filter(i => i.args[2].includes('Servicer'));

// Find servicer methods
const defines = ql.atom('defines', '${scanPath}');
for (const svc of servicers) {
    const methods = defines.filter(d =>
        d.args[1].startsWith(svc.args[1] + '.') &&
        d.args[2] === 'method'
    );
    console.log(\`\\n\${svc.args[1]} (\${svc.args[0]})\`);
    methods.forEach(m => console.log(\`  - \${m.args[1].split('.')[1]}\`));
}
`,
    },

    // HTTP API patterns → api-docs macro
    httpApi: {
        name: 'api-docs',
        description: 'Generate API documentation from FastAPI/Flask endpoints',
        detect: (atoms) => {
            const decorates = atoms.decorates.filter(d =>
                d.args[1].match(/^(app|router)\.(get|post|put|delete|patch)$/)
            );
            return decorates.length > 0;
        },
        details: (atoms) => {
            const endpoints = atoms.decorates.filter(d =>
                d.args[1].match(/^(app|router)\.(get|post|put|delete|patch)$/)
            );
            return {
                endpoints: endpoints.map(e => ({
                    method: e.args[1].split('.')[1].toUpperCase(),
                    handler: e.args[2],
                    file: e.args[0],
                })),
            };
        },
        template: () => `


// Find all HTTP endpoints
const decorates = ql.atom('decorates', '${scanPath}');
const endpoints = decorates.filter(d =>
    d.args[1].match(/^(app|router)\\.(get|post|put|delete|patch)$/)
);

console.log('# API Endpoints\\n');
for (const ep of endpoints) {
    const method = ep.args[1].split('.')[1].toUpperCase();
    console.log(\`## \${method} /\${ep.args[2]}\`);
    console.log(\`Handler: \${ep.args[2]} (\${ep.args[0]}:\${ep.args[3]})\`);
    console.log();
}
`,
    },

    // Triton/ML patterns → model-audit macro
    triton: {
        name: 'model-audit',
        description: 'Audit ML model usage, Triton clients, and inference calls',
        detect: (atoms) => {
            const imports = atoms.imports.filter(i =>
                i.args[1].includes('triton') ||
                i.args[1] === 'torch' ||
                i.args[2]?.includes('InferenceServerClient')
            );
            return imports.length > 0;
        },
        details: (atoms) => {
            const tritonImports = atoms.imports.filter(i => i.args[1].includes('triton'));
            const torchImports = atoms.imports.filter(i => i.args[1] === 'torch');
            return {
                tritonFiles: [...new Set(tritonImports.map(i => i.args[0]))],
                torchFiles: [...new Set(torchImports.map(i => i.args[0]))].length,
            };
        },
        template: () => `


// Find Triton client usage
const imports = ql.atom('imports', '${scanPath}');
const calls = ql.atom('calls', '${scanPath}');

const tritonClients = imports.filter(i => i.args[1].includes('triton'));
const inferenceCalls = calls.filter(c =>
    c.args[2].includes('infer') || c.args[2].includes('predict')
);

console.log('Triton Client Locations:');
tritonClients.forEach(t => console.log(\`  \${t.args[0]}\`));

console.log('\\nInference Calls:');
inferenceCalls.forEach(c => console.log(\`  \${c.args[0]}:\${c.args[3]} - \${c.args[2]}\`));
`,
    },

    // Queue/Worker patterns → worker-audit macro
    workers: {
        name: 'worker-audit',
        description: 'Audit multiprocessing workers, queues, and job flow',
        detect: (atoms) => {
            const imports = atoms.imports.filter(i =>
                i.args[1] === 'multiprocessing' ||
                i.args[2]?.includes('Queue') ||
                i.args[2]?.includes('Process')
            );
            return imports.length > 0;
        },
        details: (atoms) => {
            const queueImports = atoms.imports.filter(i => i.args[2]?.includes('Queue'));
            const processImports = atoms.imports.filter(i => i.args[2]?.includes('Process'));
            return {
                queueFiles: [...new Set(queueImports.map(i => i.args[0]))],
                processFiles: [...new Set(processImports.map(i => i.args[0]))],
            };
        },
        template: () => `


// Find worker/queue patterns
const imports = ql.atom('imports', '${scanPath}');
const defines = ql.atom('defines', '${scanPath}');
const calls = ql.atom('calls', '${scanPath}');

// Queue usage
const queueCalls = calls.filter(c =>
    c.args[2].includes('.put') || c.args[2].includes('.get')
);

// Worker functions
const workerFuncs = defines.filter(d =>
    d.args[1].toLowerCase().includes('worker')
);

console.log('Worker Functions:');
workerFuncs.forEach(w => console.log(\`  \${w.args[1]} (\${w.args[0]})\`));

console.log('\\nQueue Operations:');
const byFile = {};
queueCalls.forEach(c => {
    if (!byFile[c.args[0]]) byFile[c.args[0]] = [];
    byFile[c.args[0]].push(c);
});
Object.entries(byFile).forEach(([file, ops]) => {
    console.log(\`  \${file}: \${ops.length} queue ops\`);
});
`,
    },

    // Dataclass patterns → schema-export macro
    dataclasses: {
        name: 'schema-export',
        description: 'Export dataclass schemas as JSON/TypeScript types',
        detect: (atoms) => {
            const decorates = atoms.decorates.filter(d => d.args[1] === 'dataclass');
            return decorates.length >= 3; // Only if significant usage
        },
        details: (atoms) => {
            const dataclasses = atoms.decorates.filter(d => d.args[1] === 'dataclass');
            return {
                dataclasses: dataclasses.map(d => ({ name: d.args[2], file: d.args[0] })),
            };
        },
        template: () => `

const fs = require('fs');

// Find all dataclasses
const decorates = ql.atom('decorates', '${scanPath}');
const defines = ql.atom('defines', '${scanPath}');

const dataclasses = decorates.filter(d => d.args[1] === 'dataclass');

console.log('// TypeScript interfaces from Python dataclasses\\n');

for (const dc of dataclasses) {
    // Find class attributes (simplified)
    console.log(\`interface \${dc.args[2]} {\`);
    console.log(\`  // From \${dc.args[0]}:\${dc.args[3]}\`);
    console.log(\`  // TODO: Parse actual fields\`);
    console.log(\`}\\n\`);
}
`,
    },

    // Singleton patterns → singleton-audit macro
    singletons: {
        name: 'singleton-audit',
        description: 'Find and audit global singletons and their usage',
        detect: (atoms) => {
            const mutates = atoms.mutates.filter(m => m.args[2].startsWith('global '));
            return mutates.length >= 5;
        },
        details: (atoms) => {
            const globalMutations = atoms.mutates.filter(m => m.args[2].startsWith('global '));
            const globals = [...new Set(globalMutations.map(m => m.args[2]))];
            return { globals, mutationCount: globalMutations.length };
        },
        template: () => `


// Find global singleton patterns
const mutates = ql.atom('mutates', '${scanPath}');

const globalMuts = mutates.filter(m => m.args[2].startsWith('global '));
const byGlobal = {};

globalMuts.forEach(m => {
    const g = m.args[2];
    if (!byGlobal[g]) byGlobal[g] = [];
    byGlobal[g].push({ func: m.args[1], file: m.args[0] });
});

console.log('Global Singletons:\\n');
Object.entries(byGlobal).forEach(([global, usages]) => {
    console.log(\`\${global}:\`);
    usages.forEach(u => console.log(\`  - \${u.func} (\${u.file})\`));
    console.log();
});
`,
    },

    // Context manager patterns → resource-audit macro
    contextManagers: {
        name: 'resource-audit',
        description: 'Audit context managers and resource lifecycle',
        detect: (atoms) => {
            const defines = atoms.defines.filter(d =>
                d.args[1].includes('__enter__') || d.args[1].includes('__exit__')
            );
            return defines.length >= 2;
        },
        details: (atoms) => {
            const enters = atoms.defines.filter(d => d.args[1].includes('__enter__'));
            const classes = enters.map(e => e.args[1].split('.')[0]);
            return { contextManagers: [...new Set(classes)] };
        },
        template: () => `


// Find context managers
const defines = ql.atom('defines', '${scanPath}');

const enters = defines.filter(d => d.args[1].includes('__enter__'));
const exits = defines.filter(d => d.args[1].includes('__exit__'));

console.log('Context Managers:\\n');
enters.forEach(e => {
    const cls = e.args[1].split('.')[0];
    console.log(\`\${cls} (\${e.args[0]})\`);

    // Check if properly paired
    const hasExit = exits.some(x => x.args[1].startsWith(cls + '.'));
    if (!hasExit) {
        console.log(\`  ⚠️  Missing __exit__!\`);
    }
});
`,
    },

    // Test patterns → test-coverage macro
    tests: {
        name: 'test-coverage',
        description: 'Analyze test coverage and find untested functions',
        detect: (atoms) => {
            const testFiles = atoms.defines.filter(d =>
                d.args[0].includes('test') || d.args[1].startsWith('test_')
            );
            return testFiles.length > 0;
        },
        details: (atoms) => {
            const testFuncs = atoms.defines.filter(d => d.args[1].startsWith('test_'));
            return { testCount: testFuncs.length };
        },
        template: () => `


// Find tests and what they call
const defines = ql.atom('defines', '${scanPath}');
const calls = ql.atom('calls', '${scanPath}');

const testFuncs = defines.filter(d => d.args[1].startsWith('test_'));
const allFuncs = defines.filter(d => d.args[2] === 'function' && !d.args[1].startsWith('test_'));

// Find what tests call
const testedFuncs = new Set();
testFuncs.forEach(t => {
    const testCalls = calls.filter(c => c.args[1] === t.args[1]);
    testCalls.forEach(c => testedFuncs.add(c.args[2]));
});

const untested = allFuncs.filter(f => !testedFuncs.has(f.args[1]));

console.log(\`Tests: \${testFuncs.length}\`);
console.log(\`Functions: \${allFuncs.length}\`);
console.log(\`Potentially untested: \${untested.length}\\n\`);

untested.slice(0, 20).forEach(f => console.log(\`  \${f.args[1]} (\${f.args[0]})\`));
`,
    },
};

// Main analysis
function analyze() {
    console.log('═'.repeat(60));
    console.log('QuantumLogic: Macro Derivation');
    console.log('═'.repeat(60));
    console.log(`Analyzing: ${scanPath}\n`);

    // Collect atoms
    console.log('Collecting atoms...');
    const atoms = {
        defines: runAtom('defines'),
        calls: runAtom('calls'),
        imports: runAtom('imports'),
        mutates: runAtom('mutates'),
        decorates: runAtom('decorates'),
        inherits: runAtom('inherits'),
    };

    console.log(`  defines: ${atoms.defines.length}`);
    console.log(`  calls: ${atoms.calls.length}`);
    console.log(`  imports: ${atoms.imports.length}`);
    console.log(`  decorates: ${atoms.decorates.length}`);
    console.log();

    // Detect applicable macros
    console.log('─'.repeat(60));
    console.log('Suggested Macros:');
    console.log('─'.repeat(60));

    const suggested = [];

    for (const [key, detector] of Object.entries(MACRO_DETECTORS)) {
        if (detector.detect(atoms)) {
            const details = detector.details(atoms);
            suggested.push({ key, ...detector, details });

            console.log(`\n✓ ${detector.name}`);
            console.log(`  ${detector.description}`);

            // Show details
            for (const [k, v] of Object.entries(details)) {
                if (Array.isArray(v)) {
                    console.log(`  ${k}: ${v.length} items`);
                    v.slice(0, 3).forEach(item => {
                        const display = typeof item === 'object' ? JSON.stringify(item) : item;
                        console.log(`    - ${display}`);
                    });
                    if (v.length > 3) console.log(`    ... and ${v.length - 3} more`);
                } else {
                    console.log(`  ${k}: ${v}`);
                }
            }
        }
    }

    if (suggested.length === 0) {
        console.log('\nNo specific macro patterns detected.');
        console.log('The codebase may benefit from generic analysis tools.');
    }

    // Generate if requested
    if (shouldGenerate && suggested.length > 0) {
        console.log('\n' + '─'.repeat(60));
        console.log('Generating macro files...');
        console.log('─'.repeat(60));

        // Ensure macros directory exists
        const macrosDir = path.join(path.dirname(QUANTUM_LOGIC_PATH), 'macros');
        if (!fs.existsSync(macrosDir)) {
            fs.mkdirSync(macrosDir, { recursive: true });
        }

        for (const macro of suggested) {
            const filename = path.join(macrosDir, `${macro.name}.js`);
            const content = `#!/usr/bin/env node
/**
 * ${macro.name} - ${macro.description}
 *
 * Auto-generated by QuantumLogic derive-macros
 * Based on detected patterns in: ${scanPath}
 */

const ql = require('../quantum-logic');

${macro.template()}
`;
            console.log(`  Creating: macros/${macro.name}.js`);

            if (!fs.existsSync(filename)) {
                fs.writeFileSync(filename, content);
                console.log(`    ✓ Created`);
            } else {
                console.log(`    ⚠ Already exists, skipping`);
            }
        }
    }

    // Summary
    console.log('\n' + '═'.repeat(60));
    console.log(`Summary: ${suggested.length} macro patterns detected`);

    if (!shouldGenerate && suggested.length > 0) {
        console.log('\nRun with --generate to create macro files:');
        console.log(`  node quantum-logic/derive-macros.js --path=${scanPath} --generate`);
    }

    return suggested;
}

analyze();
