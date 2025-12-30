#!/usr/bin/env node
/**
 * Project-scoped find and replace (like Ctrl+Shift+H)
 *
 * Usage:
 *   node replace.js "pattern" "replacement" [--path=dir] [--ext=py,js] [--dry-run]
 *
 * Examples:
 *   node replace.js "from infer\." "from rvc.infer." --ext=py
 *   node replace.js "oldFunc" "newFunc" --path=src --dry-run
 *   node replace.js "console\.log\((.*)\)" "logger.info($1)" --ext=js,ts
 */

const fs = require('fs');
const path = require('path');

// Parse arguments
const args = process.argv.slice(2);
let pattern = null;
let replacement = null;
let searchPath = '.';
let extensions = null;
let dryRun = false;

for (const arg of args) {
    if (arg.startsWith('--path=')) {
        searchPath = arg.slice(7);
    } else if (arg.startsWith('--ext=')) {
        extensions = arg.slice(6).split(',').map(e => e.startsWith('.') ? e : '.' + e);
    } else if (arg === '--dry-run') {
        dryRun = true;
    } else if (pattern === null) {
        pattern = arg;
    } else if (replacement === null) {
        replacement = arg;
    }
}

if (!pattern || replacement === null) {
    console.log(`
Project-scoped find and replace

Usage:
  node replace.js "pattern" "replacement" [options]

Options:
  --path=dir     Directory to search (default: current directory, must be within project)
  --ext=py,js    File extensions to include (default: all)
  --dry-run      Show what would change without modifying files

Examples:
  node replace.js "from infer\\." "from rvc.infer." --ext=py
  node replace.js "oldFunc" "newFunc" --path=src --dry-run
`);
    process.exit(1);
}

// Security: Ensure we only operate within the project directory
const scriptDir = path.dirname(path.dirname(path.resolve(__filename))); // Go up from macros/
const resolvedSearchPath = path.resolve(searchPath);

if (!resolvedSearchPath.startsWith(scriptDir)) {
    console.error(`Error: Search path must be within project directory.`);
    console.error(`  Project root: ${scriptDir}`);
    console.error(`  Requested path: ${resolvedSearchPath}`);
    process.exit(1);
}

searchPath = resolvedSearchPath;

const regex = new RegExp(pattern, 'g');

// Directories to skip
const skipDirs = new Set([
    'node_modules', '.git', '__pycache__', '.venv', 'venv',
    'dist', 'build', '.eggs', '*.egg-info', 'pretrained_models',
    'assets', 'logs', 'TEMP'
]);

// Get all files recursively
function getFiles(dir) {
    const files = [];

    try {
        const entries = fs.readdirSync(dir, { withFileTypes: true });

        for (const entry of entries) {
            const fullPath = path.join(dir, entry.name);

            if (entry.isDirectory()) {
                if (!skipDirs.has(entry.name) && !entry.name.startsWith('.')) {
                    files.push(...getFiles(fullPath));
                }
            } else if (entry.isFile()) {
                if (extensions === null || extensions.some(ext => entry.name.endsWith(ext))) {
                    files.push(fullPath);
                }
            }
        }
    } catch (err) {
        // Skip directories we can't read
    }

    return files;
}

// Process files
const files = getFiles(searchPath);
let totalMatches = 0;
let filesChanged = 0;

console.log(`\nSearching for: ${pattern}`);
console.log(`Replacing with: ${replacement}`);
console.log(`Path: ${searchPath}`);
console.log(`Extensions: ${extensions ? extensions.join(', ') : 'all'}`);
console.log(`Dry run: ${dryRun}\n`);
console.log('─'.repeat(60));

for (const file of files) {
    try {
        const content = fs.readFileSync(file, 'utf8');
        const matches = content.match(regex);

        if (matches && matches.length > 0) {
            const newContent = content.replace(regex, replacement);
            const matchCount = matches.length;
            totalMatches += matchCount;
            filesChanged++;

            console.log(`\n${file}`);
            console.log(`  ${matchCount} match${matchCount > 1 ? 'es' : ''}`);

            // Show context for each match
            const lines = content.split('\n');
            lines.forEach((line, i) => {
                if (regex.test(line)) {
                    // Reset regex lastIndex after test
                    regex.lastIndex = 0;
                    console.log(`  L${i + 1}: ${line.trim().substring(0, 80)}`);
                }
            });

            if (!dryRun) {
                fs.writeFileSync(file, newContent, 'utf8');
                console.log(`  ✓ Updated`);
            }
        }
    } catch (err) {
        // Skip files we can't read (binary, etc.)
    }
}

console.log('\n' + '─'.repeat(60));
console.log(`\nSummary:`);
console.log(`  Files scanned: ${files.length}`);
console.log(`  Files ${dryRun ? 'would be ' : ''}changed: ${filesChanged}`);
console.log(`  Total matches: ${totalMatches}`);

if (dryRun && filesChanged > 0) {
    console.log(`\nRun without --dry-run to apply changes.`);
}
