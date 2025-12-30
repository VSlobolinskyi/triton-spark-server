/**
 * Atom: RETURNS
 * RETURNS(file, function, has_value, line)
 */

const fs = require('fs');
const { collectPythonFiles, createEmitter } = require('./utils');

function atomReturns(scanPath, format) {
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
                }
            }

            if (!currentFunc) return;

            // Return statements
            const returnMatch = line.match(/^\s*return\b(.*)$/);
            if (returnMatch) {
                const hasValue = returnMatch[1].trim().length > 0;
                emit('RETURNS', [file, currentFunc, hasValue, idx + 1]);
            }
        });
    });
}

module.exports = atomReturns;
