#!/usr/bin/env node
/**
 * flow.js - Data flow analyzer
 *
 * Traces how data moves through the codebase:
 * - Function call chains (A calls B calls C)
 * - Parameter propagation (what gets passed where)
 * - Return value usage (what happens to results)
 * - State mutations (what modifies what)
 *
 * Usage:
 *   node flow.js trace <function_name>     # Trace calls to/from function
 *   node flow.js chain <function_name>     # Show full call chain
 *   node flow.js params <param_name>       # Track parameter through codebase
 *   node flow.js state <class_name>        # Show state mutations in class
 *   node flow.js endpoints --path=rvc      # Map entry points to internal calls
 */

const fs = require('fs');
const path = require('path');

// ANSI colors
const colors = {
    reset: '\x1b[0m',
    bright: '\x1b[1m',
    red: '\x1b[31m',
    green: '\x1b[32m',
    yellow: '\x1b[33m',
    blue: '\x1b[34m',
    magenta: '\x1b[35m',
    cyan: '\x1b[36m',
    gray: '\x1b[90m',
};

function colorize(text, color) {
    return `${colors[color] || ''}${text}${colors.reset}`;
}

function printHeader(text) {
    console.log(colorize('═'.repeat(60), 'cyan'));
    console.log(colorize(text, 'bright'));
    console.log(colorize('═'.repeat(60), 'cyan'));
}

function printSection(text) {
    console.log('\n' + colorize('─'.repeat(60), 'gray'));
    console.log(colorize(`📊 ${text}`, 'yellow'));
    console.log(colorize('─'.repeat(60), 'gray'));
}

// Parse command line
const args = process.argv.slice(2);
let command = args[0] || 'help';
let target = args[1];
let scanPath = '.';

// Extract --path argument
args.forEach((arg, i) => {
    if (arg.startsWith('--path=')) {
        scanPath = arg.split('=')[1];
    }
});

// Collect Python files
function collectPythonFiles(dir, files = []) {
    const entries = fs.readdirSync(dir, { withFileTypes: true });
    for (const entry of entries) {
        const fullPath = path.join(dir, entry.name);
        if (entry.isDirectory()) {
            if (!['__pycache__', '.git', 'node_modules', '.venv', 'venv', 'assets', 'pretrained_models'].includes(entry.name)) {
                collectPythonFiles(fullPath, files);
            }
        } else if (entry.name.endsWith('.py')) {
            files.push(fullPath);
        }
    }
    return files;
}

// Parse function definitions with their parameters
function parseFunctions(content, filePath) {
    const functions = [];
    const lines = content.split('\n');

    // Match function definitions
    const funcRegex = /^(\s*)def\s+(\w+)\s*\(([^)]*)\)/;
    const classRegex = /^class\s+(\w+)/;

    let currentClass = null;

    lines.forEach((line, idx) => {
        const classMatch = line.match(classRegex);
        if (classMatch) {
            currentClass = classMatch[1];
        }

        const funcMatch = line.match(funcRegex);
        if (funcMatch) {
            const indent = funcMatch[1].length;
            const name = funcMatch[2];
            const params = funcMatch[3].split(',').map(p => p.trim().split(':')[0].split('=')[0].trim()).filter(p => p && p !== 'self' && p !== 'cls');

            functions.push({
                name,
                fullName: currentClass && indent > 0 ? `${currentClass}.${name}` : name,
                params,
                line: idx + 1,
                file: filePath,
                className: indent > 0 ? currentClass : null,
            });
        }

        // Reset class if we're back at indent 0
        if (line.match(/^\S/) && !line.match(classRegex) && !line.startsWith('#') && line.trim()) {
            if (!line.startsWith('def ') && !line.startsWith('@')) {
                currentClass = null;
            }
        }
    });

    return functions;
}

// Find function calls within content
function findCalls(content, filePath) {
    const calls = [];
    const lines = content.split('\n');

    // Match function/method calls
    const callRegex = /(\w+(?:\.\w+)*)\s*\(/g;

    lines.forEach((line, idx) => {
        // Skip comments and strings (basic)
        if (line.trim().startsWith('#')) return;

        let match;
        while ((match = callRegex.exec(line)) !== null) {
            const callName = match[1];
            // Filter out keywords and common builtins
            if (!['if', 'for', 'while', 'with', 'except', 'print', 'len', 'str', 'int', 'float', 'list', 'dict', 'set', 'tuple', 'range', 'enumerate', 'zip', 'map', 'filter', 'isinstance', 'hasattr', 'getattr', 'setattr', 'type', 'super', 'open', 'class', 'def', 'return', 'yield', 'raise', 'assert'].includes(callName.split('.')[0])) {
                calls.push({
                    name: callName,
                    line: idx + 1,
                    file: filePath,
                    context: line.trim(),
                });
            }
        }
    });

    return calls;
}

// Find what function a line is inside
function findContainingFunction(content, lineNum) {
    const lines = content.split('\n');
    const funcRegex = /^(\s*)def\s+(\w+)/;
    const classRegex = /^class\s+(\w+)/;

    let currentFunc = null;
    let currentClass = null;
    let funcIndent = 0;

    for (let i = 0; i < lineNum && i < lines.length; i++) {
        const line = lines[i];

        const classMatch = line.match(classRegex);
        if (classMatch) {
            currentClass = classMatch[1];
        }

        const funcMatch = line.match(funcRegex);
        if (funcMatch) {
            funcIndent = funcMatch[1].length;
            currentFunc = funcMatch[2];
        }

        // Check if we've exited the function
        if (currentFunc && i > 0) {
            const currentIndent = line.match(/^(\s*)/)[1].length;
            if (line.trim() && currentIndent <= funcIndent && !line.trim().startsWith('@') && !line.trim().startsWith('#')) {
                if (!line.match(funcRegex)) {
                    currentFunc = null;
                }
            }
        }
    }

    return currentClass && currentFunc ? `${currentClass}.${currentFunc}` : currentFunc;
}

// COMMAND: trace - Show calls to and from a function
function traceFunction(funcName) {
    printHeader(`Flow Trace: ${funcName}`);

    const files = collectPythonFiles(scanPath);
    const callsTo = [];
    const callsFrom = [];
    let definition = null;

    files.forEach(file => {
        const content = fs.readFileSync(file, 'utf-8');
        const relPath = path.relative('.', file);

        // Find definition
        const functions = parseFunctions(content, relPath);
        const func = functions.find(f => f.name === funcName || f.fullName === funcName);
        if (func) {
            definition = func;
        }

        // Find calls to this function
        const calls = findCalls(content, relPath);
        calls.forEach(call => {
            if (call.name === funcName || call.name.endsWith('.' + funcName)) {
                const caller = findContainingFunction(content, call.line);
                callsTo.push({
                    ...call,
                    caller: caller || '<module>',
                });
            }
        });

        // Find calls FROM this function (if we found its definition)
        if (func) {
            const lines = content.split('\n');
            const funcStart = func.line;
            let funcEnd = lines.length;

            // Find end of function
            const funcIndent = lines[funcStart - 1].match(/^(\s*)/)[1].length;
            for (let i = funcStart; i < lines.length; i++) {
                const line = lines[i];
                const indent = line.match(/^(\s*)/)[1].length;
                if (line.trim() && indent <= funcIndent && i > funcStart) {
                    funcEnd = i;
                    break;
                }
            }

            // Get calls within function body
            const funcContent = lines.slice(funcStart, funcEnd).join('\n');
            const innerCalls = findCalls(funcContent, relPath);
            innerCalls.forEach(call => {
                callsFrom.push({
                    ...call,
                    line: call.line + funcStart,
                });
            });
        }
    });

    // Print definition
    if (definition) {
        printSection('Definition');
        console.log(`  ${colorize('📍', 'green')} ${definition.file}:${definition.line}`);
        console.log(`  ${colorize('Parameters:', 'cyan')} ${definition.params.length ? definition.params.join(', ') : '(none)'}`);
        if (definition.className) {
            console.log(`  ${colorize('Class:', 'cyan')} ${definition.className}`);
        }
    } else {
        console.log(colorize(`\n  ⚠️  Definition not found for: ${funcName}`, 'yellow'));
    }

    // Print incoming calls
    printSection(`Calls TO ${funcName} (${callsTo.length})`);
    if (callsTo.length === 0) {
        console.log(colorize('  (no calls found)', 'gray'));
    } else {
        // Group by caller
        const byCaller = {};
        callsTo.forEach(c => {
            if (!byCaller[c.caller]) byCaller[c.caller] = [];
            byCaller[c.caller].push(c);
        });

        Object.entries(byCaller).forEach(([caller, calls]) => {
            console.log(`\n  ${colorize('←', 'green')} ${colorize(caller, 'bright')}`);
            calls.forEach(c => {
                console.log(`     ${colorize(c.file, 'gray')}:${c.line}`);
            });
        });
    }

    // Print outgoing calls
    printSection(`Calls FROM ${funcName} (${callsFrom.length})`);
    if (callsFrom.length === 0) {
        console.log(colorize('  (no calls found)', 'gray'));
    } else {
        // Deduplicate by name
        const unique = [...new Set(callsFrom.map(c => c.name))];
        unique.forEach(name => {
            const count = callsFrom.filter(c => c.name === name).length;
            console.log(`  ${colorize('→', 'blue')} ${name}${count > 1 ? colorize(` (×${count})`, 'gray') : ''}`);
        });
    }
}

// COMMAND: chain - Build call chain from entry point
function buildCallChain(funcName, maxDepth = 5) {
    printHeader(`Call Chain: ${funcName}`);

    const files = collectPythonFiles(scanPath);
    const allFunctions = [];
    const allCalls = [];

    // Collect all functions and calls
    files.forEach(file => {
        const content = fs.readFileSync(file, 'utf-8');
        const relPath = path.relative('.', file);

        allFunctions.push(...parseFunctions(content, relPath));

        const calls = findCalls(content, relPath);
        calls.forEach(call => {
            const caller = findContainingFunction(content, call.line);
            if (caller) {
                allCalls.push({
                    from: caller,
                    to: call.name.split('.').pop(), // Get just the function name
                    file: relPath,
                    line: call.line,
                });
            }
        });
    });

    // Build call graph
    const callGraph = {};
    allCalls.forEach(call => {
        if (!callGraph[call.from]) callGraph[call.from] = new Set();
        callGraph[call.from].add(call.to);
    });

    // DFS to build chain
    function buildTree(name, depth = 0, visited = new Set()) {
        if (depth > maxDepth || visited.has(name)) {
            return { name, children: [], truncated: depth > maxDepth, circular: visited.has(name) };
        }

        visited.add(name);
        const children = [];

        // Find what this function calls
        const called = callGraph[name] || new Set();
        called.forEach(child => {
            // Only include if it's a defined function in our codebase
            if (allFunctions.some(f => f.name === child || f.fullName === child)) {
                children.push(buildTree(child, depth + 1, new Set(visited)));
            }
        });

        return { name, children };
    }

    const tree = buildTree(funcName);

    // Print tree
    function printTree(node, prefix = '', isLast = true) {
        const connector = isLast ? '└── ' : '├── ';
        const extension = isLast ? '    ' : '│   ';

        let label = node.name;
        if (node.circular) label += colorize(' (circular)', 'red');
        if (node.truncated) label += colorize(' (max depth)', 'yellow');

        console.log(prefix + connector + colorize(label, node.children.length ? 'cyan' : 'gray'));

        node.children.forEach((child, i) => {
            printTree(child, prefix + extension, i === node.children.length - 1);
        });
    }

    console.log('\n' + colorize(funcName, 'bright'));
    tree.children.forEach((child, i) => {
        printTree(child, '', i === tree.children.length - 1);
    });

    if (tree.children.length === 0) {
        console.log(colorize('  (no internal calls found)', 'gray'));
    }
}

// COMMAND: params - Track a parameter name through the codebase
function trackParam(paramName) {
    printHeader(`Parameter Flow: ${paramName}`);

    const files = collectPythonFiles(scanPath);
    const occurrences = [];

    files.forEach(file => {
        const content = fs.readFileSync(file, 'utf-8');
        const relPath = path.relative('.', file);
        const lines = content.split('\n');

        // Find functions that have this parameter
        const functions = parseFunctions(content, relPath);
        functions.forEach(func => {
            if (func.params.includes(paramName)) {
                occurrences.push({
                    type: 'param',
                    func: func.fullName,
                    file: relPath,
                    line: func.line,
                });
            }
        });

        // Find where it's passed as argument
        const argRegex = new RegExp(`(\\w+)\\s*\\([^)]*\\b${paramName}\\s*=`, 'g');
        const posArgRegex = new RegExp(`(\\w+)\\s*\\([^)]*\\b${paramName}\\b`, 'g');

        lines.forEach((line, idx) => {
            if (line.includes(paramName) && !line.trim().startsWith('#')) {
                const func = findContainingFunction(content, idx + 1);

                // Check if it's being passed as kwarg
                if (argRegex.test(line)) {
                    occurrences.push({
                        type: 'kwarg',
                        func: func || '<module>',
                        file: relPath,
                        line: idx + 1,
                        context: line.trim(),
                    });
                }
            }
        });
    });

    // Group by type
    const asParam = occurrences.filter(o => o.type === 'param');
    const asArg = occurrences.filter(o => o.type === 'kwarg');

    printSection(`Defined as Parameter (${asParam.length})`);
    asParam.forEach(o => {
        console.log(`  ${colorize('📥', 'green')} ${o.func} ${colorize(`(${o.file}:${o.line})`, 'gray')}`);
    });

    printSection(`Passed as Argument (${asArg.length})`);
    asArg.forEach(o => {
        console.log(`  ${colorize('📤', 'blue')} in ${o.func} ${colorize(`(${o.file}:${o.line})`, 'gray')}`);
    });
}

// COMMAND: state - Show state mutations in a class
function analyzeState(className) {
    printHeader(`State Analysis: ${className}`);

    const files = collectPythonFiles(scanPath);
    let classFile = null;
    let classContent = null;
    const mutations = [];
    const reads = [];

    files.forEach(file => {
        const content = fs.readFileSync(file, 'utf-8');
        const relPath = path.relative('.', file);

        // Find the class
        const classMatch = content.match(new RegExp(`^class\\s+${className}[^:]*:`, 'm'));
        if (classMatch) {
            classFile = relPath;
            classContent = content;

            const lines = content.split('\n');
            let inClass = false;
            let classIndent = 0;
            let currentMethod = null;

            lines.forEach((line, idx) => {
                // Check if we're entering the class
                if (line.match(new RegExp(`^class\\s+${className}`))) {
                    inClass = true;
                    classIndent = 0;
                    return;
                }

                if (!inClass) return;

                // Check if we've exited the class
                const indent = line.match(/^(\s*)/)[1].length;
                if (line.trim() && indent === 0 && !line.startsWith('#')) {
                    inClass = false;
                    return;
                }

                // Track current method
                const methodMatch = line.match(/^\s+def\s+(\w+)/);
                if (methodMatch) {
                    currentMethod = methodMatch[1];
                }

                // Find self.x = assignments (mutations)
                const mutationMatch = line.match(/self\.(\w+)\s*=(?!=)/);
                if (mutationMatch) {
                    mutations.push({
                        attr: mutationMatch[1],
                        method: currentMethod,
                        line: idx + 1,
                        isInit: currentMethod === '__init__',
                    });
                }

                // Find self.x reads (without assignment)
                const readMatches = line.matchAll(/self\.(\w+)(?!\s*=)/g);
                for (const match of readMatches) {
                    reads.push({
                        attr: match[1],
                        method: currentMethod,
                        line: idx + 1,
                    });
                }
            });
        }
    });

    if (!classFile) {
        console.log(colorize(`\n  ⚠️  Class not found: ${className}`, 'yellow'));
        return;
    }

    console.log(`\n  ${colorize('📍', 'green')} ${classFile}`);

    // Analyze attributes
    const initAttrs = [...new Set(mutations.filter(m => m.isInit).map(m => m.attr))];
    const laterAttrs = [...new Set(mutations.filter(m => !m.isInit).map(m => m.attr))];

    printSection(`Attributes Initialized in __init__ (${initAttrs.length})`);
    initAttrs.forEach(attr => {
        console.log(`  ${colorize('•', 'green')} self.${attr}`);
    });

    printSection(`Attributes Modified Elsewhere (${laterAttrs.length})`);
    if (laterAttrs.length === 0) {
        console.log(colorize('  (none - good encapsulation!)', 'gray'));
    } else {
        laterAttrs.forEach(attr => {
            const methods = [...new Set(mutations.filter(m => m.attr === attr && !m.isInit).map(m => m.method))];
            console.log(`  ${colorize('⚠️', 'yellow')} self.${attr} ${colorize(`(in: ${methods.join(', ')})`, 'gray')}`);
        });
    }

    // Find attributes that are written but never read
    const allWritten = [...new Set(mutations.map(m => m.attr))];
    const allRead = [...new Set(reads.map(r => r.attr))];
    const writeOnly = allWritten.filter(a => !allRead.includes(a));

    if (writeOnly.length > 0) {
        printSection(`Write-Only Attributes (potential dead code)`);
        writeOnly.forEach(attr => {
            console.log(`  ${colorize('🗑️', 'red')} self.${attr}`);
        });
    }
}

// COMMAND: endpoints - Map API endpoints to internal function calls
function mapEndpoints() {
    printHeader('Endpoint → Implementation Map');

    const files = collectPythonFiles(scanPath);
    const endpoints = [];

    files.forEach(file => {
        const content = fs.readFileSync(file, 'utf-8');
        const relPath = path.relative('.', file);
        const lines = content.split('\n');

        // Find FastAPI/Flask route decorators
        lines.forEach((line, idx) => {
            const routeMatch = line.match(/@(?:app|router)\.(get|post|put|delete|patch)\s*\(\s*["']([^"']+)["']/i);
            if (routeMatch) {
                const method = routeMatch[1].toUpperCase();
                const path = routeMatch[2];

                // Find the function on the next non-decorator line
                for (let i = idx + 1; i < lines.length; i++) {
                    const funcMatch = lines[i].match(/^(?:async\s+)?def\s+(\w+)/);
                    if (funcMatch) {
                        endpoints.push({
                            method,
                            path,
                            handler: funcMatch[1],
                            file: relPath,
                            line: i + 1,
                        });
                        break;
                    }
                    // Skip other decorators
                    if (!lines[i].trim().startsWith('@') && lines[i].trim()) break;
                }
            }
        });
    });

    if (endpoints.length === 0) {
        console.log(colorize('\n  No HTTP endpoints found', 'gray'));
        return;
    }

    // Group by file
    const byFile = {};
    endpoints.forEach(ep => {
        if (!byFile[ep.file]) byFile[ep.file] = [];
        byFile[ep.file].push(ep);
    });

    Object.entries(byFile).forEach(([file, eps]) => {
        printSection(file);
        eps.forEach(ep => {
            const methodColor = {
                'GET': 'green',
                'POST': 'blue',
                'PUT': 'yellow',
                'DELETE': 'red',
                'PATCH': 'magenta',
            }[ep.method] || 'gray';

            console.log(`  ${colorize(ep.method.padEnd(6), methodColor)} ${ep.path}`);
            console.log(`         ${colorize('→', 'gray')} ${ep.handler}() ${colorize(`:${ep.line}`, 'gray')}`);
        });
    });
}

// Help
function showHelp() {
    console.log(`
${colorize('flow.js', 'bright')} - Data flow analyzer

${colorize('Usage:', 'yellow')}
  node flow.js <command> [target] [--path=dir]

${colorize('Commands:', 'yellow')}
  trace <function>     Show calls to and from a function
  chain <function>     Build call chain tree from function
  params <name>        Track parameter through codebase
  state <class>        Analyze state mutations in class
  endpoints            Map HTTP endpoints to handlers

${colorize('Examples:', 'cyan')}
  node flow.js trace initialize --path=rvc
  node flow.js chain run_rvc --path=rvc
  node flow.js params pitch_shift --path=rvc
  node flow.js state TTSRVCPipeline --path=rvc
  node flow.js endpoints --path=rvc
`);
}

// Main
switch (command) {
    case 'trace':
        if (!target) {
            console.log(colorize('Error: function name required', 'red'));
            showHelp();
        } else {
            traceFunction(target);
        }
        break;
    case 'chain':
        if (!target) {
            console.log(colorize('Error: function name required', 'red'));
            showHelp();
        } else {
            buildCallChain(target);
        }
        break;
    case 'params':
        if (!target) {
            console.log(colorize('Error: parameter name required', 'red'));
            showHelp();
        } else {
            trackParam(target);
        }
        break;
    case 'state':
        if (!target) {
            console.log(colorize('Error: class name required', 'red'));
            showHelp();
        } else {
            analyzeState(target);
        }
        break;
    case 'endpoints':
        mapEndpoints();
        break;
    default:
        showHelp();
}
