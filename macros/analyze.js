#!/usr/bin/env node
/**
 * Python Codebase Analyzer - Semantic projections for understanding code
 *
 * Usage:
 *   node analyze.js imports [--path=dir]     Show import dependency graph
 *   node analyze.js classes [--path=dir]     Show class hierarchy and methods
 *   node analyze.js calls <function>         Show call graph for a function
 *   node analyze.js exports [--path=dir]     Show module public API (__all__)
 *   node analyze.js dataflow <class>         Show data flow through a class
 *
 * Examples:
 *   node analyze.js imports --path=rvc
 *   node analyze.js classes --path=rvc/processing
 *   node analyze.js calls TTSRVCPipeline.process
 *   node analyze.js exports --path=rvc
 */

const fs = require('fs');
const path = require('path');

// Parse arguments
const args = process.argv.slice(2);
let command = null;
let target = null;
let searchPath = '.';

for (const arg of args) {
    if (arg.startsWith('--path=')) {
        searchPath = arg.slice(7);
    } else if (command === null) {
        command = arg;
    } else if (target === null) {
        target = arg;
    }
}

// Security: Ensure we only operate within the project directory
const scriptDir = path.dirname(path.dirname(path.resolve(__filename))); // Go up from macros/
const resolvedSearchPath = path.resolve(searchPath);

if (!resolvedSearchPath.startsWith(scriptDir)) {
    console.error(`Error: Search path must be within project directory.`);
    process.exit(1);
}

searchPath = resolvedSearchPath;

// Directories to skip
const skipDirs = new Set([
    'node_modules', '.git', '__pycache__', '.venv', 'venv',
    'dist', 'build', '.eggs', 'pretrained_models', 'assets', 'logs', 'TEMP'
]);

// Get all Python files recursively
function getPythonFiles(dir) {
    const files = [];
    try {
        const entries = fs.readdirSync(dir, { withFileTypes: true });
        for (const entry of entries) {
            const fullPath = path.join(dir, entry.name);
            if (entry.isDirectory()) {
                if (!skipDirs.has(entry.name) && !entry.name.startsWith('.')) {
                    files.push(...getPythonFiles(fullPath));
                }
            } else if (entry.isFile() && entry.name.endsWith('.py')) {
                files.push(fullPath);
            }
        }
    } catch (err) { }
    return files;
}

// Simple Python parser (regex-based, not full AST)
function parseImports(content) {
    const imports = [];

    // from X import Y
    const fromImportRe = /^from\s+([\w.]+)\s+import\s+(.+)$/gm;
    let match;
    while ((match = fromImportRe.exec(content)) !== null) {
        const module = match[1];
        const names = match[2].split(',').map(s => s.trim().split(/\s+as\s+/)[0].trim());
        imports.push({ type: 'from', module, names });
    }

    // import X
    const importRe = /^import\s+([\w.]+)(?:\s+as\s+\w+)?$/gm;
    while ((match = importRe.exec(content)) !== null) {
        imports.push({ type: 'import', module: match[1], names: [] });
    }

    return imports;
}

function parseClasses(content) {
    const classes = [];
    const classRe = /^class\s+(\w+)(?:\(([^)]*)\))?:/gm;
    let match;
    while ((match = classRe.exec(content)) !== null) {
        const name = match[1];
        const bases = match[2] ? match[2].split(',').map(s => s.trim()) : [];

        // Find methods in this class (simplified - looks for def after class)
        const classStart = match.index;
        const methods = [];
        const methodRe = /^    def\s+(\w+)\s*\(/gm;
        methodRe.lastIndex = classStart;
        let methodMatch;
        while ((methodMatch = methodRe.exec(content)) !== null) {
            // Stop if we hit another class or non-indented code
            const between = content.slice(classStart, methodMatch.index);
            if (between.includes('\nclass ')) break;
            methods.push(methodMatch[1]);
        }

        classes.push({ name, bases, methods });
    }
    return classes;
}

function parseExports(content) {
    const allMatch = content.match(/__all__\s*=\s*\[([\s\S]*?)\]/);
    if (!allMatch) return null;

    const items = allMatch[1].match(/["'](\w+)["']/g);
    return items ? items.map(s => s.replace(/["']/g, '')) : [];
}

function parseFunctions(content) {
    const functions = [];
    const funcRe = /^def\s+(\w+)\s*\(([^)]*)\)/gm;
    let match;
    while ((match = funcRe.exec(content)) !== null) {
        functions.push({ name: match[1], params: match[2] });
    }
    return functions;
}

function parseCalls(content, targetFunc) {
    const calls = [];
    // Look for function/method calls
    const callRe = new RegExp(`\\b${targetFunc}\\s*\\(`, 'g');
    let match;
    while ((match = callRe.exec(content)) !== null) {
        // Get line number
        const lineNum = content.slice(0, match.index).split('\n').length;
        calls.push({ line: lineNum });
    }
    return calls;
}

// Commands
function cmdImports() {
    const files = getPythonFiles(searchPath);
    const graph = new Map(); // module -> [dependencies]

    console.log(`\nImport Dependency Graph (${path.relative(scriptDir, searchPath) || '.'})`);
    console.log('═'.repeat(60));

    for (const file of files) {
        const content = fs.readFileSync(file, 'utf8');
        const imports = parseImports(content);
        const relPath = path.relative(scriptDir, file);
        const moduleName = relPath.replace(/\.py$/, '').replace(/[\\\/]/g, '.').replace(/\.__init__$/, '');

        const localImports = imports
            .filter(i => i.module.startsWith('rvc') || i.module.startsWith('sparktts') || i.module.startsWith('.'))
            .map(i => i.module);

        if (localImports.length > 0) {
            graph.set(moduleName, localImports);
        }
    }

    // Print as tree
    for (const [module, deps] of [...graph.entries()].sort()) {
        console.log(`\n${module}`);
        for (const dep of deps) {
            console.log(`  └── ${dep}`);
        }
    }

    console.log(`\n${'─'.repeat(60)}`);
    console.log(`Modules analyzed: ${graph.size}`);
}

function cmdClasses() {
    const files = getPythonFiles(searchPath);

    console.log(`\nClass Hierarchy (${path.relative(scriptDir, searchPath) || '.'})`);
    console.log('═'.repeat(60));

    const allClasses = [];

    for (const file of files) {
        const content = fs.readFileSync(file, 'utf8');
        const classes = parseClasses(content);
        const relPath = path.relative(scriptDir, file);

        for (const cls of classes) {
            allClasses.push({ ...cls, file: relPath });
        }
    }

    // Group by inheritance
    for (const cls of allClasses.sort((a, b) => a.name.localeCompare(b.name))) {
        const bases = cls.bases.length > 0 ? ` (${cls.bases.join(', ')})` : '';
        console.log(`\n${cls.name}${bases}`);
        console.log(`  File: ${cls.file}`);

        if (cls.methods.length > 0) {
            console.log(`  Methods:`);
            const publicMethods = cls.methods.filter(m => !m.startsWith('_'));
            const privateMethods = cls.methods.filter(m => m.startsWith('_') && !m.startsWith('__'));
            const magicMethods = cls.methods.filter(m => m.startsWith('__'));

            if (publicMethods.length > 0) {
                console.log(`    Public: ${publicMethods.join(', ')}`);
            }
            if (privateMethods.length > 0) {
                console.log(`    Private: ${privateMethods.join(', ')}`);
            }
            if (magicMethods.length > 0) {
                console.log(`    Magic: ${magicMethods.join(', ')}`);
            }
        }
    }

    console.log(`\n${'─'.repeat(60)}`);
    console.log(`Classes found: ${allClasses.length}`);
}

function cmdExports() {
    const files = getPythonFiles(searchPath);

    console.log(`\nModule Exports / Public API (${path.relative(scriptDir, searchPath) || '.'})`);
    console.log('═'.repeat(60));

    for (const file of files) {
        const content = fs.readFileSync(file, 'utf8');
        const exports = parseExports(content);
        const relPath = path.relative(scriptDir, file);

        if (exports && exports.length > 0) {
            console.log(`\n${relPath}`);
            console.log(`  __all__ = [`);
            for (const exp of exports) {
                console.log(`    "${exp}",`);
            }
            console.log(`  ]`);
        }
    }
}

function cmdCalls() {
    if (!target) {
        console.error('Usage: node analyze.js calls <function_name>');
        process.exit(1);
    }

    const files = getPythonFiles(searchPath);

    console.log(`\nCall Sites for: ${target}`);
    console.log('═'.repeat(60));

    let totalCalls = 0;

    for (const file of files) {
        const content = fs.readFileSync(file, 'utf8');
        const calls = parseCalls(content, target);
        const relPath = path.relative(scriptDir, file);

        if (calls.length > 0) {
            console.log(`\n${relPath}`);
            for (const call of calls) {
                // Get the line content
                const lines = content.split('\n');
                const lineContent = lines[call.line - 1].trim();
                console.log(`  L${call.line}: ${lineContent.substring(0, 70)}${lineContent.length > 70 ? '...' : ''}`);
            }
            totalCalls += calls.length;
        }
    }

    console.log(`\n${'─'.repeat(60)}`);
    console.log(`Total call sites: ${totalCalls}`);
}

function cmdDataflow() {
    if (!target) {
        console.error('Usage: node analyze.js dataflow <ClassName>');
        process.exit(1);
    }

    const files = getPythonFiles(searchPath);

    console.log(`\nData Flow Analysis: ${target}`);
    console.log('═'.repeat(60));

    for (const file of files) {
        const content = fs.readFileSync(file, 'utf8');
        const relPath = path.relative(scriptDir, file);

        // Find class definition
        const classRe = new RegExp(`^class\\s+${target}\\b[^:]*:`, 'm');
        const classMatch = content.match(classRe);

        if (classMatch) {
            console.log(`\nDefined in: ${relPath}`);

            // Find __init__ to see instance variables
            const initMatch = content.match(/def __init__\s*\([^)]*\):[^]*?(?=\n    def |\nclass |\n[^\s]|$)/);
            if (initMatch) {
                const selfAttrs = initMatch[0].match(/self\.(\w+)\s*=/g);
                if (selfAttrs) {
                    console.log(`\nInstance Attributes (from __init__):`);
                    const attrs = [...new Set(selfAttrs.map(s => s.match(/self\.(\w+)/)[1]))];
                    for (const attr of attrs) {
                        console.log(`  • self.${attr}`);
                    }
                }
            }

            // Find methods that modify state
            const methodRe = /def (\w+)\s*\([^)]*\):[^]*?(?=\n    def |\nclass |\n[^\s]|$)/g;
            let methodMatch;
            const mutations = [];

            while ((methodMatch = methodRe.exec(content)) !== null) {
                const methodName = methodMatch[1];
                const methodBody = methodMatch[0];
                const selfWrites = methodBody.match(/self\.(\w+)\s*=/g);
                if (selfWrites && methodName !== '__init__') {
                    const attrs = [...new Set(selfWrites.map(s => s.match(/self\.(\w+)/)[1]))];
                    mutations.push({ method: methodName, attrs });
                }
            }

            if (mutations.length > 0) {
                console.log(`\nState Mutations:`);
                for (const m of mutations) {
                    console.log(`  ${m.method}() modifies: ${m.attrs.join(', ')}`);
                }
            }
        }

        // Find where class is instantiated
        const instRe = new RegExp(`${target}\\s*\\(`, 'g');
        const lines = content.split('\n');
        const instantiations = [];

        for (let i = 0; i < lines.length; i++) {
            if (instRe.test(lines[i]) && !lines[i].includes('class ')) {
                instantiations.push({ line: i + 1, content: lines[i].trim() });
            }
            instRe.lastIndex = 0;
        }

        if (instantiations.length > 0 && !classMatch) {
            console.log(`\n${relPath}`);
            console.log(`  Instantiated:`);
            for (const inst of instantiations) {
                console.log(`    L${inst.line}: ${inst.content.substring(0, 60)}${inst.content.length > 60 ? '...' : ''}`);
            }
        }
    }
}

// Main
if (!command) {
    console.log(`
Python Codebase Analyzer - Semantic projections

Usage:
  node analyze.js <command> [options]

Commands:
  imports [--path=dir]     Show import dependency graph
  classes [--path=dir]     Show class hierarchy and methods
  calls <function>         Show call sites for a function
  exports [--path=dir]     Show module public API (__all__)
  dataflow <class>         Show data flow through a class

Options:
  --path=dir               Directory to analyze (default: current)

Examples:
  node analyze.js imports --path=rvc
  node analyze.js classes --path=rvc/processing
  node analyze.js calls process --path=rvc
  node analyze.js dataflow TTSRVCPipeline
`);
    process.exit(0);
}

switch (command) {
    case 'imports':
        cmdImports();
        break;
    case 'classes':
        cmdClasses();
        break;
    case 'calls':
        cmdCalls();
        break;
    case 'exports':
        cmdExports();
        break;
    case 'dataflow':
        cmdDataflow();
        break;
    default:
        console.error(`Unknown command: ${command}`);
        process.exit(1);
}
