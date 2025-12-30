/**
 * Atom: CALLS
 * CALLS(file, caller, callee, line)
 */

const fs = require('fs');
const { collectPythonFiles, createEmitter } = require('./utils');

const KEYWORDS = new Set(['if', 'for', 'while', 'with', 'except', 'print', 'len', 'str', 'int', 'float',
    'list', 'dict', 'set', 'tuple', 'range', 'enumerate', 'zip', 'map', 'filter', 'isinstance',
    'hasattr', 'getattr', 'setattr', 'type', 'super', 'open', 'class', 'def', 'return', 'yield',
    'raise', 'assert', 'True', 'False', 'None', 'and', 'or', 'not', 'in', 'is']);

function atomCalls(scanPath, format) {
    const emit = createEmitter(format);
    const files = collectPythonFiles(scanPath);

    files.forEach(file => {
        const content = fs.readFileSync(file, 'utf-8');
        const lines = content.split('\n');

        let currentFunc = null;
        let currentClass = null;
        let funcIndent = 0;
        let classIndent = 0;

        lines.forEach((line, idx) => {
            // Track class
            const classMatch = line.match(/^(\s*)class\s+(\w+)/);
            if (classMatch) {
                classIndent = classMatch[1].length;
                currentClass = classMatch[2];
            }

            // Track function
            const funcMatch = line.match(/^(\s*)(?:async\s+)?def\s+(\w+)/);
            if (funcMatch) {
                funcIndent = funcMatch[1].length;
                const name = funcMatch[2];
                if (currentClass && funcIndent > classIndent) {
                    currentFunc = `${currentClass}.${name}`;
                } else {
                    currentFunc = name;
                    currentClass = null;
                }
            }

            // Skip if not in a function or is a comment
            if (!currentFunc || line.trim().startsWith('#')) return;

            // Find calls
            const callRegex = /(\w+(?:\.\w+)*)\s*\(/g;
            let match;
            while ((match = callRegex.exec(line)) !== null) {
                const callee = match[1];
                const baseName = callee.split('.')[0];
                if (!KEYWORDS.has(baseName)) {
                    emit('CALLS', [file, currentFunc, callee, idx + 1]);
                }
            }
        });
    });
}

module.exports = atomCalls;
