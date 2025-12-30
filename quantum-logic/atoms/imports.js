/**
 * Atom: IMPORTS
 * IMPORTS(file, module, symbol, alias, line)
 */

const fs = require('fs');
const { collectPythonFiles, createEmitter } = require('./utils');

function atomImports(scanPath, format) {
    const emit = createEmitter(format);
    const files = collectPythonFiles(scanPath);

    files.forEach(file => {
        const content = fs.readFileSync(file, 'utf-8');
        const lines = content.split('\n');

        lines.forEach((line, idx) => {
            // import X, import X as Y
            const importMatch = line.match(/^import\s+([\w.]+)(?:\s+as\s+(\w+))?/);
            if (importMatch) {
                emit('IMPORTS', [file, importMatch[1], '*', importMatch[2] || importMatch[1], idx + 1]);
            }

            // from X import Y, Z, from X import Y as Z
            const fromMatch = line.match(/^from\s+([\w.]+)\s+import\s+(.+)/);
            if (fromMatch) {
                const module = fromMatch[1];
                const imports = fromMatch[2];

                // Parse individual imports
                const importList = imports.split(',').map(s => s.trim());
                importList.forEach(imp => {
                    const asMatch = imp.match(/(\w+)\s+as\s+(\w+)/);
                    if (asMatch) {
                        emit('IMPORTS', [file, module, asMatch[1], asMatch[2], idx + 1]);
                    } else {
                        const name = imp.trim();
                        if (name && !name.startsWith('#')) {
                            emit('IMPORTS', [file, module, name, name, idx + 1]);
                        }
                    }
                });
            }
        });
    });
}

module.exports = atomImports;
