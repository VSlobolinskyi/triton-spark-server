/**
 * Atom: EXPORTS
 * EXPORTS(file, symbol, line)
 * Extracts __all__ exports from Python modules
 */

const fs = require('fs');
const { collectPythonFiles, createEmitter } = require('./utils');

function atomExports(scanPath, format) {
    const emit = createEmitter(format);
    const files = collectPythonFiles(scanPath);

    files.forEach(file => {
        const content = fs.readFileSync(file, 'utf-8');
        const lines = content.split('\n');

        let inAllBlock = false;
        let allContent = '';
        let startLine = 0;

        for (let i = 0; i < lines.length; i++) {
            const line = lines[i];

            // Start of __all__ block
            if (line.match(/^__all__\s*=\s*\[/)) {
                inAllBlock = true;
                allContent = line;
                startLine = i + 1;

                // Single line __all__
                if (line.includes(']')) {
                    inAllBlock = false;
                    extractExports(file, allContent, startLine, emit);
                }
                continue;
            }

            // Continuation of multiline __all__
            if (inAllBlock) {
                allContent += line;
                if (line.includes(']')) {
                    inAllBlock = false;
                    extractExports(file, allContent, startLine, emit);
                }
            }
        }
    });
}

function extractExports(file, content, line, emit) {
    const matches = content.match(/["'](\w+)["']/g);
    if (matches) {
        for (const match of matches) {
            const symbol = match.replace(/["']/g, '');
            emit('EXPORTS', [file, symbol, line]);
        }
    }
}

module.exports = atomExports;
