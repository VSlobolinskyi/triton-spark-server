/**
 * Atom: DECORATES
 * DECORATES(file, decorator, target, line)
 */

const fs = require('fs');
const { collectPythonFiles, createEmitter } = require('./utils');

function atomDecorates(scanPath, format) {
    const emit = createEmitter(format);
    const files = collectPythonFiles(scanPath);

    files.forEach(file => {
        const content = fs.readFileSync(file, 'utf-8');
        const lines = content.split('\n');

        let pendingDecorators = [];
        let currentClass = null;
        let classIndent = 0;

        lines.forEach((line, idx) => {
            // Track class
            const classMatch = line.match(/^(\s*)class\s+(\w+)/);
            if (classMatch) {
                classIndent = classMatch[1].length;
                currentClass = classMatch[2];

                // Apply pending decorators to class
                pendingDecorators.forEach(dec => {
                    emit('DECORATES', [file, dec.name, classMatch[2], dec.line]);
                });
                pendingDecorators = [];
            }

            // Decorator
            const decMatch = line.match(/^(\s*)@([\w.]+(?:\([^)]*\))?)/);
            if (decMatch) {
                const decName = decMatch[2].split('(')[0]; // Remove args
                pendingDecorators.push({ name: decName, line: idx + 1 });
            }

            // Function/method (applies pending decorators)
            const funcMatch = line.match(/^(\s*)(?:async\s+)?def\s+(\w+)/);
            if (funcMatch && pendingDecorators.length > 0) {
                const indent = funcMatch[1].length;
                const name = funcMatch[2];
                const fullName = (currentClass && indent > classIndent) ? `${currentClass}.${name}` : name;

                pendingDecorators.forEach(dec => {
                    emit('DECORATES', [file, dec.name, fullName, dec.line]);
                });
                pendingDecorators = [];
            }

            // Clear decorators if we hit a non-decorator, non-def line
            if (!line.trim().startsWith('@') && !line.match(/^\s*(?:async\s+)?def\s/) && !line.match(/^\s*class\s/) && line.trim() && !line.trim().startsWith('#')) {
                pendingDecorators = [];
            }
        });
    });
}

module.exports = atomDecorates;
