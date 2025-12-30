/**
 * Shared utilities for atoms
 */

const fs = require('fs');
const path = require('path');

/**
 * Collect all Python files recursively from a directory
 */
function collectPythonFiles(dir, files = []) {
    try {
        const entries = fs.readdirSync(dir, { withFileTypes: true });
        for (const entry of entries) {
            const fullPath = path.join(dir, entry.name);
            if (entry.isDirectory()) {
                if (!['__pycache__', '.git', 'node_modules', '.venv', 'venv', 'assets', 'pretrained_models', 'framework'].includes(entry.name)) {
                    collectPythonFiles(fullPath, files);
                }
            } else if (entry.name.endsWith('.py')) {
                files.push(fullPath);
            }
        }
    } catch (e) {}
    return files;
}

/**
 * Emit a predicate in the specified format
 */
function createEmitter(format) {
    return function emit(predicate, args) {
        const relArgs = args.map(a => typeof a === 'string' && a.includes(path.sep) ? path.relative('.', a).replace(/\\/g, '/') : a);

        switch (format) {
            case 'json':
                console.log(JSON.stringify({ predicate, args: relArgs }));
                break;
            case 'tsv':
                console.log([predicate, ...relArgs].join('\t'));
                break;
            default: // predicate
                console.log(`${predicate}(${relArgs.join(', ')})`);
        }
    };
}

/**
 * Parse command line arguments for atoms
 */
function parseArgs(args) {
    let scanPath = '.';
    let format = 'predicate';

    args.forEach(arg => {
        if (arg.startsWith('--path=')) scanPath = arg.split('=')[1];
        if (arg.startsWith('--format=')) format = arg.split('=')[1];
    });

    return { scanPath, format };
}

module.exports = {
    collectPythonFiles,
    createEmitter,
    parseArgs
};
