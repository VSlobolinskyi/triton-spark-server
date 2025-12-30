/**
 * Atom: PARAMS
 * PARAMS(file, function, name, has_type, has_default, line)
 */

const fs = require('fs');
const { collectPythonFiles, createEmitter } = require('./utils');

function atomParams(scanPath, format) {
    const emit = createEmitter(format);
    const files = collectPythonFiles(scanPath);

    files.forEach(file => {
        const content = fs.readFileSync(file, 'utf-8');
        const lines = content.split('\n');

        let currentClass = null;
        let classIndent = 0;

        lines.forEach((line, idx) => {
            // Track class
            const classMatch = line.match(/^(\s*)class\s+(\w+)/);
            if (classMatch) {
                classIndent = classMatch[1].length;
                currentClass = classMatch[2];
            }

            // Function definition with params
            const funcMatch = line.match(/^(\s*)(?:async\s+)?def\s+(\w+)\s*\(([^)]*)\)/);
            if (funcMatch) {
                const indent = funcMatch[1].length;
                const name = funcMatch[2];
                const paramsStr = funcMatch[3];

                const fullName = (currentClass && indent > classIndent) ? `${currentClass}.${name}` : name;

                if (paramsStr.trim()) {
                    const params = paramsStr.split(',').map(p => p.trim()).filter(p => p && p !== 'self' && p !== 'cls');

                    params.forEach(param => {
                        const hasType = param.includes(':');
                        const hasDefault = param.includes('=');
                        const paramName = param.split(':')[0].split('=')[0].trim();

                        if (paramName && !paramName.startsWith('*')) {
                            emit('PARAMS', [file, fullName, paramName, hasType, hasDefault, idx + 1]);
                        }
                    });
                }
            }
        });
    });
}

module.exports = atomParams;
