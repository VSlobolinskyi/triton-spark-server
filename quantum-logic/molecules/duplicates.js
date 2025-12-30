/**
 * Molecule: DUPLICATES
 * Find duplicate/similar code blocks
 */

const fs = require('fs');
const path = require('path');
const { runAtom, parsePredicates, printHeader, printSection } = require('./utils');

function duplicates(scanPath) {
    printHeader('Duplicate Code Analysis');

    const defines = parsePredicates(runAtom('defines', scanPath));

    // Get unique files
    const files = [...new Set(defines.map(d => d.args[0]))];

    // Extract function bodies and normalize them
    const blocks = new Map(); // normalized code -> [locations]

    for (const file of files) {
        try {
            const fullPath = path.resolve(file);
            const content = fs.readFileSync(fullPath, 'utf-8');
            const lines = content.split('\n');

            let inFunction = false;
            let funcStart = 0;
            let funcName = '';
            let funcBody = [];
            let funcIndent = 0;

            for (let i = 0; i < lines.length; i++) {
                const line = lines[i];
                const match = line.match(/^(\s*)(?:async\s+)?def\s+(\w+)/);

                if (match) {
                    // Save previous function if substantial
                    if (inFunction && funcBody.length >= 5) {
                        const normalized = normalizeCode(funcBody);
                        if (normalized.length > 50) { // Skip trivial functions
                            if (!blocks.has(normalized)) {
                                blocks.set(normalized, []);
                            }
                            blocks.get(normalized).push({
                                file: file,
                                line: funcStart,
                                name: funcName,
                                length: funcBody.length,
                            });
                        }
                    }

                    inFunction = true;
                    funcStart = i + 1;
                    funcName = match[2];
                    funcIndent = match[1].length;
                    funcBody = [];
                } else if (inFunction) {
                    const lineIndent = line.match(/^(\s*)/)[1].length;
                    if (line.trim() !== '' && lineIndent <= funcIndent) {
                        // Function ended
                        if (funcBody.length >= 5) {
                            const normalized = normalizeCode(funcBody);
                            if (normalized.length > 50) {
                                if (!blocks.has(normalized)) {
                                    blocks.set(normalized, []);
                                }
                                blocks.get(normalized).push({
                                    file: file,
                                    line: funcStart,
                                    name: funcName,
                                    length: funcBody.length,
                                });
                            }
                        }
                        inFunction = false;
                    } else {
                        funcBody.push(line);
                    }
                }
            }

            // Handle last function
            if (inFunction && funcBody.length >= 5) {
                const normalized = normalizeCode(funcBody);
                if (normalized.length > 50) {
                    if (!blocks.has(normalized)) {
                        blocks.set(normalized, []);
                    }
                    blocks.get(normalized).push({
                        file: file,
                        line: funcStart,
                        name: funcName,
                        length: funcBody.length,
                    });
                }
            }
        } catch (e) {
            // Skip files we can't read
        }
    }

    // Find exact duplicates
    printSection('Exact Duplicates');

    const exactDups = [...blocks.entries()].filter(([_, locs]) => locs.length > 1);

    if (exactDups.length === 0) {
        console.log('  \x1b[32m✓ No exact duplicate functions found\x1b[0m');
    } else {
        for (const [code, locations] of exactDups.slice(0, 10)) {
            console.log(`\n  \x1b[31m◆ Duplicate pattern (${locations.length} occurrences)\x1b[0m`);
            for (const loc of locations) {
                console.log(`    \x1b[90m${loc.file}:${loc.line}\x1b[0m → ${loc.name}() [${loc.length} lines]`);
            }
            // Show snippet
            const preview = code.split('\n').slice(0, 3).join(' ').substring(0, 80);
            console.log(`    \x1b[90mPreview: ${preview}...\x1b[0m`);
        }

        if (exactDups.length > 10) {
            console.log(`\n  \x1b[90m... and ${exactDups.length - 10} more duplicate patterns\x1b[0m`);
        }
    }

    // Find similar method signatures (classes with same methods)
    printSection('Similar Class Structures');

    const classSignatures = new Map(); // method signature -> [class locations]

    // Group defines by class
    const classMethods = new Map();
    defines.forEach(d => {
        const type = d.args[2];
        if (type === 'method' || type === 'async_method') {
            const [className, methodName] = d.args[1].split('.');
            const key = `${d.args[0]}:${className}`;
            if (!classMethods.has(key)) {
                classMethods.set(key, { file: d.args[0], class: className, methods: [] });
            }
            classMethods.get(key).methods.push(methodName);
        }
    });

    // Find classes with identical method sets
    for (const [key, data] of classMethods) {
        const sig = data.methods.filter(m => !m.startsWith('_')).sort().join(',');
        if (sig && sig.split(',').length >= 3) { // At least 3 public methods
            if (!classSignatures.has(sig)) {
                classSignatures.set(sig, []);
            }
            classSignatures.get(sig).push(data);
        }
    }

    const similarClasses = [...classSignatures.entries()].filter(([_, locs]) => locs.length > 1);

    if (similarClasses.length === 0) {
        console.log('  \x1b[32m✓ No classes with identical method signatures\x1b[0m');
    } else {
        for (const [sig, classes] of similarClasses.slice(0, 5)) {
            const methods = sig.split(',');
            console.log(`\n  \x1b[33m◆ Classes with methods: [${methods.slice(0, 5).join(', ')}${methods.length > 5 ? '...' : ''}]\x1b[0m`);
            for (const cls of classes) {
                console.log(`    \x1b[90m${cls.file}\x1b[0m → ${cls.class}`);
            }
        }
    }

    // Summary
    const totalDups = exactDups.reduce((sum, [_, locs]) => sum + locs.length - 1, 0);
    console.log(`\n\x1b[33mTotal: ${exactDups.length} duplicate patterns affecting ${totalDups} extra copies\x1b[0m`);

    if (totalDups > 0) {
        console.log('\x1b[90mTip: Extract duplicates to shared utilities\x1b[0m');
    }
}

function normalizeCode(lines) {
    return lines
        .map(line => line.trim())
        .filter(line => line !== '' && !line.startsWith('#'))
        .join('\n')
        // Normalize variable names
        .replace(/\b[a-z_][a-z0-9_]*\b/gi, 'VAR')
        // Normalize strings
        .replace(/"[^"]*"/g, '"STR"')
        .replace(/'[^']*'/g, "'STR'")
        // Normalize numbers
        .replace(/\b\d+\.?\d*\b/g, 'NUM');
}

module.exports = duplicates;
