/**
 * Atom: DEFINES
 * DEFINES(file, name, type, line)
 * type: function | method | class | async_function | async_method
 */

const fs = require('fs');
const { collectPythonFiles, createEmitter } = require('./utils');

function atomDefines(scanPath, format) {
    const emit = createEmitter(format);
    const files = collectPythonFiles(scanPath);

    files.forEach(file => {
        const content = fs.readFileSync(file, 'utf-8');
        const lines = content.split('\n');

        let currentClass = null;
        let classIndent = 0;

        lines.forEach((line, idx) => {
            // Track class context
            const classMatch = line.match(/^(\s*)class\s+(\w+)/);
            if (classMatch) {
                classIndent = classMatch[1].length;
                currentClass = classMatch[2];
                emit('DEFINES', [file, classMatch[2], 'class', idx + 1]);
            }

            // Check if we've exited the class
            const currentIndent = line.match(/^(\s*)/)[1].length;
            if (currentClass && line.trim() && currentIndent <= classIndent && !classMatch) {
                currentClass = null;
            }

            // Functions/methods
            const funcMatch = line.match(/^(\s*)(async\s+)?def\s+(\w+)/);
            if (funcMatch) {
                const indent = funcMatch[1].length;
                const isAsync = !!funcMatch[2];
                const name = funcMatch[3];

                let type;
                if (currentClass && indent > classIndent) {
                    type = isAsync ? 'async_method' : 'method';
                    emit('DEFINES', [file, `${currentClass}.${name}`, type, idx + 1]);
                } else {
                    type = isAsync ? 'async_function' : 'function';
                    emit('DEFINES', [file, name, type, idx + 1]);
                }
            }
        });
    });
}

module.exports = atomDefines;
