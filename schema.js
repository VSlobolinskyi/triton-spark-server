#!/usr/bin/env node
/**
 * schema.js - Generate logical projections of Python codebase
 *
 * Creates condensed "skeleton" views showing structure without implementation details.
 * Useful for understanding large codebases without reading every line.
 *
 * Usage:
 *   node schema.js [--path=dir] [--depth=2] [--output=file]
 *
 * Output modes:
 *   --mode=signatures  - Show class/function signatures only (default)
 *   --mode=structure   - Show file/class/method hierarchy
 *   --mode=api         - Show public API (__all__ exports + their signatures)
 *   --mode=types       - Show type hints and dataclasses
 */

const fs = require('fs');
const path = require('path');

// Parse arguments
const args = process.argv.slice(2);
const getArg = (name, def) => {
    const arg = args.find(a => a.startsWith(`--${name}=`));
    return arg ? arg.split('=')[1] : def;
};

const targetPath = getArg('path', '.');
const mode = getArg('mode', 'signatures');
const outputFile = getArg('output', null);
const maxDepth = parseInt(getArg('depth', '10'));

// Patterns for Python parsing
const PATTERNS = {
    class: /^(\s*)class\s+(\w+)(?:\s*\((.*?)\))?:/,
    function: /^(\s*)(?:async\s+)?def\s+(\w+)\s*\((.*?)\)(?:\s*->\s*(.+?))?:/,
    decorator: /^(\s*)@(\w+(?:\.\w+)*(?:\(.*?\))?)/,
    dataclass: /@dataclass/,
    assignment: /^(\s*)(\w+)\s*(?::\s*(.+?))?\s*=\s*(.+)/,
    import: /^(?:from\s+(\S+)\s+)?import\s+(.+)/,
    typeAlias: /^(\w+)\s*=\s*(Union|Optional|List|Dict|Tuple|Callable|Type)\[/,
    allExport: /^__all__\s*=\s*\[/,
    docstring: /^\s*(?:"""|\'\'\')(.*?)(?:"""|\'\'\')/s,
};

// Collect all Python files
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
    } catch (e) { /* ignore permission errors */ }
    return files;
}

// Parse a Python file for structure
function parseFile(filePath) {
    const content = fs.readFileSync(filePath, 'utf-8');
    const lines = content.split('\n');

    const result = {
        path: filePath,
        imports: [],
        exports: [],  // __all__
        classes: [],
        functions: [],
        constants: [],
        typeAliases: [],
    };

    let currentClass = null;
    let currentDecorators = [];
    let inAllBlock = false;
    let allContent = '';

    for (let i = 0; i < lines.length; i++) {
        const line = lines[i];
        const trimmed = line.trim();

        // Track __all__ exports (can be multiline)
        if (inAllBlock) {
            allContent += line;
            if (line.includes(']')) {
                inAllBlock = false;
                const matches = allContent.match(/["'](\w+)["']/g);
                if (matches) {
                    result.exports = matches.map(m => m.replace(/["']/g, ''));
                }
            }
            continue;
        }

        if (PATTERNS.allExport.test(trimmed)) {
            inAllBlock = true;
            allContent = line;
            if (line.includes(']')) {
                inAllBlock = false;
                const matches = allContent.match(/["'](\w+)["']/g);
                if (matches) {
                    result.exports = matches.map(m => m.replace(/["']/g, ''));
                }
            }
            continue;
        }

        // Imports
        const importMatch = trimmed.match(PATTERNS.import);
        if (importMatch) {
            result.imports.push({
                from: importMatch[1] || null,
                import: importMatch[2],
            });
            continue;
        }

        // Decorators
        const decoratorMatch = line.match(PATTERNS.decorator);
        if (decoratorMatch) {
            currentDecorators.push(decoratorMatch[2]);
            continue;
        }

        // Class definition
        const classMatch = line.match(PATTERNS.class);
        if (classMatch) {
            const indent = classMatch[1].length;
            if (indent === 0) {
                currentClass = {
                    name: classMatch[2],
                    bases: classMatch[3] ? classMatch[3].split(',').map(b => b.trim()) : [],
                    decorators: [...currentDecorators],
                    methods: [],
                    attributes: [],
                    isDataclass: currentDecorators.some(d => d.includes('dataclass')),
                    line: i + 1,
                };
                result.classes.push(currentClass);
            }
            currentDecorators = [];
            continue;
        }

        // Function/method definition
        const funcMatch = line.match(PATTERNS.function);
        if (funcMatch) {
            const indent = funcMatch[1].length;
            const funcInfo = {
                name: funcMatch[2],
                params: funcMatch[3] || '',
                returnType: funcMatch[4] || null,
                decorators: [...currentDecorators],
                isAsync: line.includes('async def'),
                isPrivate: funcMatch[2].startsWith('_') && !funcMatch[2].startsWith('__'),
                isMagic: funcMatch[2].startsWith('__') && funcMatch[2].endsWith('__'),
                line: i + 1,
            };

            if (indent > 0 && currentClass) {
                currentClass.methods.push(funcInfo);
            } else if (indent === 0) {
                result.functions.push(funcInfo);
                currentClass = null;
            }
            currentDecorators = [];
            continue;
        }

        // Type aliases at module level
        const typeMatch = trimmed.match(PATTERNS.typeAlias);
        if (typeMatch && !line.startsWith(' ')) {
            result.typeAliases.push({
                name: typeMatch[1],
                type: trimmed.split('=')[1].trim(),
            });
            continue;
        }

        // Constants (ALL_CAPS at module level)
        if (!line.startsWith(' ') && !line.startsWith('\t')) {
            const assignMatch = trimmed.match(/^([A-Z][A-Z0-9_]*)\s*(?::\s*(.+?))?\s*=\s*(.+)/);
            if (assignMatch) {
                result.constants.push({
                    name: assignMatch[1],
                    type: assignMatch[2] || null,
                    value: assignMatch[3].substring(0, 50),
                });
            }
        }

        // Class attributes (in dataclasses or typed attributes)
        if (currentClass && currentClass.isDataclass) {
            const attrMatch = trimmed.match(/^(\w+)\s*:\s*(.+?)(?:\s*=\s*(.+))?$/);
            if (attrMatch && !trimmed.startsWith('def ') && !trimmed.startsWith('#')) {
                currentClass.attributes.push({
                    name: attrMatch[1],
                    type: attrMatch[2],
                    default: attrMatch[3] || null,
                });
            }
        }

        // Reset decorators if we hit an empty line or non-decorator/non-class/non-func
        if (trimmed === '' || (!decoratorMatch && !classMatch && !funcMatch)) {
            if (!line.match(/^\s*#/) && trimmed !== '') {
                currentDecorators = [];
            }
        }
    }

    return result;
}

// Format signatures mode output
function formatSignatures(parsed) {
    const lines = [];
    const relPath = path.relative(process.cwd(), parsed.path);

    lines.push(`\n${'═'.repeat(60)}`);
    lines.push(`📄 ${relPath}`);
    lines.push('═'.repeat(60));

    // Exports
    if (parsed.exports.length > 0) {
        lines.push(`\n__all__ = [${parsed.exports.map(e => `"${e}"`).join(', ')}]`);
    }

    // Constants
    if (parsed.constants.length > 0) {
        lines.push('\n# Constants');
        for (const c of parsed.constants) {
            const typeHint = c.type ? `: ${c.type}` : '';
            lines.push(`${c.name}${typeHint} = ${c.value}`);
        }
    }

    // Type aliases
    if (parsed.typeAliases.length > 0) {
        lines.push('\n# Type Aliases');
        for (const t of parsed.typeAliases) {
            lines.push(`${t.name} = ${t.type}`);
        }
    }

    // Module-level functions
    if (parsed.functions.length > 0) {
        lines.push('\n# Functions');
        for (const f of parsed.functions) {
            const decorators = f.decorators.map(d => `@${d}`).join(' ');
            const prefix = decorators ? decorators + ' ' : '';
            const asyncPrefix = f.isAsync ? 'async ' : '';
            const returnType = f.returnType ? ` -> ${f.returnType}` : '';
            lines.push(`${prefix}${asyncPrefix}def ${f.name}(${formatParams(f.params)})${returnType}: ...`);
        }
    }

    // Classes
    for (const cls of parsed.classes) {
        lines.push('');
        const decorators = cls.decorators.map(d => `@${d}`).join('\n');
        if (decorators) lines.push(decorators);

        const bases = cls.bases.length > 0 ? `(${cls.bases.join(', ')})` : '';
        lines.push(`class ${cls.name}${bases}:`);

        // Dataclass attributes
        if (cls.attributes.length > 0) {
            for (const attr of cls.attributes) {
                const defaultVal = attr.default ? ` = ${attr.default}` : '';
                lines.push(`    ${attr.name}: ${attr.type}${defaultVal}`);
            }
        }

        // Methods (grouped)
        const publicMethods = cls.methods.filter(m => !m.isPrivate && !m.isMagic);
        const privateMethods = cls.methods.filter(m => m.isPrivate);
        const magicMethods = cls.methods.filter(m => m.isMagic);

        // Show magic methods (important for understanding class behavior)
        if (magicMethods.length > 0) {
            for (const m of magicMethods) {
                const asyncPrefix = m.isAsync ? 'async ' : '';
                const returnType = m.returnType ? ` -> ${m.returnType}` : '';
                lines.push(`    ${asyncPrefix}def ${m.name}(${formatParams(m.params)})${returnType}: ...`);
            }
        }

        // Show public methods
        for (const m of publicMethods) {
            const decorators = m.decorators.filter(d =>
                d === 'property' || d === 'classmethod' || d === 'staticmethod'
            ).map(d => `@${d}`).join(' ');
            const prefix = decorators ? decorators + ' ' : '';
            const asyncPrefix = m.isAsync ? 'async ' : '';
            const returnType = m.returnType ? ` -> ${m.returnType}` : '';
            lines.push(`    ${prefix}${asyncPrefix}def ${m.name}(${formatParams(m.params)})${returnType}: ...`);
        }

        // Summarize private methods
        if (privateMethods.length > 0) {
            lines.push(`    # ... ${privateMethods.length} private method(s): ${privateMethods.map(m => m.name).join(', ')}`);
        }

        if (cls.methods.length === 0 && cls.attributes.length === 0) {
            lines.push('    pass');
        }
    }

    return lines.join('\n');
}

// Format params for display (truncate long ones)
function formatParams(params) {
    if (params.length > 80) {
        // Count params and show abbreviated
        const count = (params.match(/,/g) || []).length + 1;
        const firstParams = params.split(',').slice(0, 3).join(', ');
        return `${firstParams}, ... (${count} params)`;
    }
    return params;
}

// Format structure mode output (hierarchy only)
function formatStructure(files) {
    const tree = {};

    for (const parsed of files) {
        const relPath = path.relative(process.cwd(), parsed.path);
        const parts = relPath.split(path.sep);

        let current = tree;
        for (let i = 0; i < parts.length - 1; i++) {
            if (!current[parts[i]]) current[parts[i]] = {};
            current = current[parts[i]];
        }

        const fileName = parts[parts.length - 1];
        current[fileName] = {
            _exports: parsed.exports,
            _classes: parsed.classes.map(c => c.name),
            _functions: parsed.functions.map(f => f.name),
        };
    }

    function printTree(node, indent = '') {
        const lines = [];
        const entries = Object.entries(node).sort((a, b) => {
            // Directories first, then files
            const aIsDir = !a[0].endsWith('.py');
            const bIsDir = !b[0].endsWith('.py');
            if (aIsDir !== bIsDir) return bIsDir - aIsDir;
            return a[0].localeCompare(b[0]);
        });

        for (const [key, value] of entries) {
            if (key.startsWith('_')) continue;

            if (key.endsWith('.py')) {
                // File with its contents
                const exports = value._exports?.length > 0 ? ` [${value._exports.join(', ')}]` : '';
                lines.push(`${indent}📄 ${key}${exports}`);

                if (value._classes?.length > 0) {
                    lines.push(`${indent}   classes: ${value._classes.join(', ')}`);
                }
                if (value._functions?.length > 0) {
                    const funcs = value._functions.filter(f => !f.startsWith('_'));
                    if (funcs.length > 0) {
                        lines.push(`${indent}   functions: ${funcs.join(', ')}`);
                    }
                }
            } else {
                // Directory
                lines.push(`${indent}📁 ${key}/`);
                lines.push(printTree(value, indent + '   '));
            }
        }
        return lines.join('\n');
    }

    return printTree(tree);
}

// Format API mode output (only __all__ exports with signatures)
function formatAPI(files) {
    const lines = [];

    for (const parsed of files) {
        if (parsed.exports.length === 0) continue;

        const relPath = path.relative(process.cwd(), parsed.path);
        lines.push(`\n${'─'.repeat(50)}`);
        lines.push(`📦 ${relPath}`);
        lines.push('─'.repeat(50));

        for (const exportName of parsed.exports) {
            // Find the exported item
            const cls = parsed.classes.find(c => c.name === exportName);
            const func = parsed.functions.find(f => f.name === exportName);
            const constant = parsed.constants.find(c => c.name === exportName);

            if (cls) {
                const bases = cls.bases.length > 0 ? `(${cls.bases.join(', ')})` : '';
                lines.push(`\nclass ${cls.name}${bases}:`);

                // Show __init__ params (key for understanding instantiation)
                const init = cls.methods.find(m => m.name === '__init__');
                if (init) {
                    lines.push(`    def __init__(${formatParams(init.params)})`);
                }

                // Show public methods
                const publicMethods = cls.methods.filter(m => !m.isPrivate && !m.isMagic);
                for (const m of publicMethods) {
                    const returnType = m.returnType ? ` -> ${m.returnType}` : '';
                    lines.push(`    def ${m.name}(${formatParams(m.params)})${returnType}`);
                }
            } else if (func) {
                const asyncPrefix = func.isAsync ? 'async ' : '';
                const returnType = func.returnType ? ` -> ${func.returnType}` : '';
                lines.push(`${asyncPrefix}def ${func.name}(${formatParams(func.params)})${returnType}`);
            } else if (constant) {
                lines.push(`${constant.name} = ${constant.value}`);
            } else {
                lines.push(`${exportName}  # (imported or dynamic)`);
            }
        }
    }

    return lines.join('\n');
}

// Main execution
function main() {
    console.log(`Schema Generator - Mode: ${mode}`);
    console.log(`Scanning: ${path.resolve(targetPath)}`);
    console.log('═'.repeat(60));

    const pythonFiles = collectPythonFiles(targetPath);
    console.log(`Found ${pythonFiles.length} Python files\n`);

    if (pythonFiles.length === 0) {
        console.log('No Python files found.');
        return;
    }

    const parsed = pythonFiles.map(f => parseFile(f));

    let output;
    switch (mode) {
        case 'signatures':
            output = parsed.map(p => formatSignatures(p)).join('\n');
            break;
        case 'structure':
            output = formatStructure(parsed);
            break;
        case 'api':
            output = formatAPI(parsed);
            break;
        case 'types':
            // Show dataclasses and type definitions
            output = parsed
                .filter(p => p.typeAliases.length > 0 || p.classes.some(c => c.isDataclass))
                .map(p => formatSignatures(p))
                .join('\n');
            break;
        default:
            console.log(`Unknown mode: ${mode}`);
            console.log('Available modes: signatures, structure, api, types');
            return;
    }

    if (outputFile) {
        fs.writeFileSync(outputFile, output);
        console.log(`Output written to: ${outputFile}`);
    } else {
        console.log(output);
    }
}

main();
