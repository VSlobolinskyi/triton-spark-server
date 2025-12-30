/**
 * Atom: FILES
 * FILES(path, name, type, depth)
 * type: file | directory
 */

const fs = require('fs');
const path = require('path');
const { createEmitter } = require('./utils');

const SKIP_DIRS = new Set([
    '__pycache__', '.git', 'node_modules', '.venv', 'venv',
    'assets', 'pretrained_models', 'logs', 'dist', 'build',
    '.eggs', 'TEMP', '.idea', '.vscode'
]);

function atomFiles(scanPath, format) {
    const emit = createEmitter(format);

    function walk(dir, depth = 0) {
        try {
            const entries = fs.readdirSync(dir, { withFileTypes: true });

            for (const entry of entries) {
                if (entry.name.startsWith('.') && entry.name !== '.') continue;
                if (SKIP_DIRS.has(entry.name)) continue;

                const fullPath = path.join(dir, entry.name);
                const type = entry.isDirectory() ? 'directory' : 'file';

                emit('FILES', [fullPath, entry.name, type, depth]);

                if (entry.isDirectory()) {
                    walk(fullPath, depth + 1);
                }
            }
        } catch (e) { /* ignore permission errors */ }
    }

    walk(scanPath);
}

module.exports = atomFiles;
