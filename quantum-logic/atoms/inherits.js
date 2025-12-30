/**
 * Atom: INHERITS
 * INHERITS(file, child, parent, line)
 */

const fs = require('fs');
const { collectPythonFiles, createEmitter } = require('./utils');

function atomInherits(scanPath, format) {
    const emit = createEmitter(format);
    const files = collectPythonFiles(scanPath);

    files.forEach(file => {
        const content = fs.readFileSync(file, 'utf-8');
        const lines = content.split('\n');

        lines.forEach((line, idx) => {
            const classMatch = line.match(/^class\s+(\w+)\s*\(([^)]+)\)/);
            if (classMatch) {
                const child = classMatch[1];
                const parents = classMatch[2].split(',').map(p => p.trim()).filter(p => p);

                parents.forEach(parent => {
                    emit('INHERITS', [file, child, parent, idx + 1]);
                });
            }
        });
    });
}

module.exports = atomInherits;
