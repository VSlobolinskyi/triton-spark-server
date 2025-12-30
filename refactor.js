#!/usr/bin/env node
/**
 * refactor.js - Safe refactoring helper
 *
 * Helps plan and validate refactoring operations:
 *   - Find all usages of a symbol (function, class, variable)
 *   - Check what would break if something is renamed/moved
 *   - Detect redundant/duplicate code
 *   - Suggest extraction opportunities
 *
 * Usage:
 *   node refactor.js usages <symbol>              # Find all usages
 *   node refactor.js rename <old> <new> --dry-run # Preview rename
 *   node refactor.js duplicates                   # Find duplicate code
 *   node refactor.js extract <file:line>          # Suggest extractions
 *   node refactor.js move <symbol> <to_module>    # Check move safety
 *   node refactor.js unused                       # Find unused code
 */

const fs = require('fs');
const path = require('path');

const args = process.argv.slice(2);
const command = args.find(a => !a.startsWith('--')) || 'help';
const commandArgs = args.filter(a => !a.startsWith('--')).slice(1);
const getArg = (name, def) => {
    const arg = args.find(a => a.startsWith(`--${name}=`));
    return arg ? arg.split('=')[1] : def;
};
const hasFlag = (name) => args.includes(`--${name}`);

const targetPath = getArg('path', '.');
const dryRun = hasFlag('dry-run');

function collectPythonFiles(dir, maxDepth = 10, depth = 0) {
    if (depth > maxDepth) return [];
    const files = [];
    try {
        const entries = fs.readdirSync(dir, { withFileTypes: true });
        for (const entry of entries) {
            const fullPath = path.join(dir, entry.name);
            if (entry.name.startsWith('.') || entry.name === '__pycache__' ||
                entry.name === 'node_modules' || entry.name === 'venv') continue;
            if (entry.isDirectory()) {
                files.push(...collectPythonFiles(fullPath, maxDepth, depth + 1));
            } else if (entry.name.endsWith('.py')) {
                files.push(fullPath);
            }
        }
    } catch (e) { }
    return files;
}

// Find all usages of a symbol
function findUsages(symbol) {
    const files = collectPythonFiles(targetPath);
    const usages = [];

    // Patterns for different usage types
    const patterns = {
        definition: new RegExp(`^\\s*(?:class|def|async\\s+def)\\s+${symbol}\\b`),
        import: new RegExp(`(?:from\\s+\\S+\\s+import\\s+.*\\b${symbol}\\b|import\\s+.*\\b${symbol}\\b)`),
        call: new RegExp(`\\b${symbol}\\s*\\(`),
        reference: new RegExp(`\\b${symbol}\\b`),
        assignment: new RegExp(`\\b${symbol}\\s*=`),
        attribute: new RegExp(`\\.${symbol}\\b`),
        type_hint: new RegExp(`:\\s*${symbol}\\b|->\\s*${symbol}\\b`),
    };

    for (const file of files) {
        const content = fs.readFileSync(file, 'utf-8');
        const lines = content.split('\n');
        const relPath = path.relative(process.cwd(), file);

        for (let i = 0; i < lines.length; i++) {
            const line = lines[i];

            for (const [type, pattern] of Object.entries(patterns)) {
                if (pattern.test(line)) {
                    usages.push({
                        file: relPath,
                        line: i + 1,
                        type: type,
                        text: line.trim(),
                    });
                    break;  // Only record one type per line
                }
            }
        }
    }

    return usages;
}

// Find duplicate/similar code blocks
function findDuplicates() {
    const files = collectPythonFiles(targetPath);
    const blocks = new Map();  // normalized code -> [locations]

    for (const file of files) {
        const content = fs.readFileSync(file, 'utf-8');
        const lines = content.split('\n');
        const relPath = path.relative(process.cwd(), file);

        // Extract function bodies
        let inFunction = false;
        let funcStart = 0;
        let funcName = '';
        let funcBody = [];
        let funcIndent = 0;

        for (let i = 0; i < lines.length; i++) {
            const line = lines[i];
            const match = line.match(/^(\s*)(?:async\s+)?def\s+(\w+)/);

            if (match) {
                // Save previous function if any
                if (inFunction && funcBody.length >= 5) {
                    const normalized = normalizeCode(funcBody);
                    if (!blocks.has(normalized)) {
                        blocks.set(normalized, []);
                    }
                    blocks.get(normalized).push({
                        file: relPath,
                        line: funcStart,
                        name: funcName,
                        length: funcBody.length,
                    });
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
                        if (!blocks.has(normalized)) {
                            blocks.set(normalized, []);
                        }
                        blocks.get(normalized).push({
                            file: relPath,
                            line: funcStart,
                            name: funcName,
                            length: funcBody.length,
                        });
                    }
                    inFunction = false;
                } else {
                    funcBody.push(line);
                }
            }
        }
    }

    // Find duplicates (blocks that appear more than once)
    const duplicates = [];
    for (const [code, locations] of blocks) {
        if (locations.length > 1) {
            duplicates.push({
                code: code.substring(0, 200),
                locations: locations,
                similarity: 1.0,
            });
        }
    }

    return duplicates;
}

// Normalize code for comparison (remove variable names, whitespace)
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

// Find unused definitions
function findUnused() {
    const files = collectPythonFiles(targetPath);
    const definitions = new Map();  // symbol -> { file, line, type }
    const usages = new Map();       // symbol -> count

    // First pass: find all definitions
    for (const file of files) {
        const content = fs.readFileSync(file, 'utf-8');
        const lines = content.split('\n');
        const relPath = path.relative(process.cwd(), file);

        for (let i = 0; i < lines.length; i++) {
            const line = lines[i];

            // Class definition
            const classMatch = line.match(/^class\s+(\w+)/);
            if (classMatch) {
                definitions.set(classMatch[1], { file: relPath, line: i + 1, type: 'class' });
            }

            // Function definition (top-level only for now)
            const funcMatch = line.match(/^(?:async\s+)?def\s+(\w+)/);
            if (funcMatch && !funcMatch[1].startsWith('_')) {
                definitions.set(funcMatch[1], { file: relPath, line: i + 1, type: 'function' });
            }

            // Top-level constants
            const constMatch = line.match(/^([A-Z][A-Z0-9_]*)\s*=/);
            if (constMatch) {
                definitions.set(constMatch[1], { file: relPath, line: i + 1, type: 'constant' });
            }
        }
    }

    // Second pass: count usages
    for (const file of files) {
        const content = fs.readFileSync(file, 'utf-8');
        const lines = content.split('\n');

        for (let i = 0; i < lines.length; i++) {
            const line = lines[i];

            for (const symbol of definitions.keys()) {
                // Skip the definition line itself
                const def = definitions.get(symbol);
                if (def.file === path.relative(process.cwd(), file) && def.line === i + 1) {
                    continue;
                }

                const regex = new RegExp(`\\b${symbol}\\b`, 'g');
                const matches = line.match(regex);
                if (matches) {
                    usages.set(symbol, (usages.get(symbol) || 0) + matches.length);
                }
            }
        }
    }

    // Find unused (0 usages)
    const unused = [];
    for (const [symbol, def] of definitions) {
        const count = usages.get(symbol) || 0;
        if (count === 0) {
            unused.push({ symbol, ...def });
        }
    }

    return unused;
}

// Check safety of moving a symbol to another module
function checkMoveSafety(symbol, targetModule) {
    const usages = findUsages(symbol);

    // Group by import type
    const imports = usages.filter(u => u.type === 'import');
    const references = usages.filter(u => u.type !== 'import' && u.type !== 'definition');
    const definition = usages.find(u => u.type === 'definition');

    return {
        symbol,
        targetModule,
        definition,
        importCount: imports.length,
        referenceCount: references.length,
        affectedFiles: [...new Set(usages.map(u => u.file))],
        imports,
        safe: references.every(r => imports.some(i => i.file === r.file)),
    };
}

// Preview rename operation
function previewRename(oldName, newName) {
    const usages = findUsages(oldName);
    const changes = [];

    for (const usage of usages) {
        const filePath = path.join(process.cwd(), usage.file);
        const content = fs.readFileSync(filePath, 'utf-8');
        const lines = content.split('\n');
        const oldLine = lines[usage.line - 1];
        const newLine = oldLine.replace(new RegExp(`\\b${oldName}\\b`, 'g'), newName);

        if (oldLine !== newLine) {
            changes.push({
                file: usage.file,
                line: usage.line,
                type: usage.type,
                before: oldLine.trim(),
                after: newLine.trim(),
            });
        }
    }

    return changes;
}

// Main command handlers
function main() {
    console.log('Refactoring Helper');
    console.log('═'.repeat(60));

    switch (command) {
        case 'usages':
            const symbol = commandArgs[0];
            if (!symbol) {
                console.log('Usage: node refactor.js usages <symbol>');
                return;
            }

            console.log(`🔍 USAGES OF: ${symbol}\n`);
            const usages = findUsages(symbol);

            if (usages.length === 0) {
                console.log('No usages found.');
                return;
            }

            // Group by type
            const byType = {};
            for (const u of usages) {
                if (!byType[u.type]) byType[u.type] = [];
                byType[u.type].push(u);
            }

            for (const [type, items] of Object.entries(byType)) {
                const icon = {
                    definition: '📝',
                    import: '📦',
                    call: '📞',
                    reference: '👁️',
                    assignment: '✏️',
                    attribute: '🔗',
                    type_hint: '🏷️',
                }[type] || '•';

                console.log(`\n${icon} ${type.toUpperCase()} (${items.length})`);
                for (const item of items.slice(0, 10)) {
                    console.log(`   ${item.file}:${item.line}`);
                    console.log(`      ${item.text.substring(0, 70)}`);
                }
                if (items.length > 10) {
                    console.log(`   ... and ${items.length - 10} more`);
                }
            }

            console.log(`\n📊 Total: ${usages.length} usages in ${new Set(usages.map(u => u.file)).size} files`);
            break;

        case 'rename':
            const oldName = commandArgs[0];
            const newName = commandArgs[1];
            if (!oldName || !newName) {
                console.log('Usage: node refactor.js rename <old> <new> [--dry-run]');
                return;
            }

            console.log(`🔄 RENAME: ${oldName} → ${newName}\n`);
            const changes = previewRename(oldName, newName);

            if (changes.length === 0) {
                console.log('No changes needed.');
                return;
            }

            for (const change of changes) {
                console.log(`📄 ${change.file}:${change.line} (${change.type})`);
                console.log(`   - ${change.before}`);
                console.log(`   + ${change.after}`);
                console.log();
            }

            console.log(`📊 ${changes.length} changes in ${new Set(changes.map(c => c.file)).size} files`);

            if (dryRun) {
                console.log('\n⚠️  DRY RUN - no files modified');
            } else {
                console.log('\n💡 Use --dry-run to preview without changes');
                console.log('   Actual file modification not implemented (use replace.js)');
            }
            break;

        case 'duplicates':
            console.log('🔍 FINDING DUPLICATE CODE...\n');
            const duplicates = findDuplicates();

            if (duplicates.length === 0) {
                console.log('✅ No significant duplicates found.');
                return;
            }

            console.log(`Found ${duplicates.length} duplicate patterns:\n`);

            for (const dup of duplicates.slice(0, 10)) {
                console.log('─'.repeat(50));
                console.log(`📋 Found in ${dup.locations.length} places:`);
                for (const loc of dup.locations) {
                    console.log(`   ${loc.file}:${loc.line} → ${loc.name}() [${loc.length} lines]`);
                }
                console.log(`\n   Preview: ${dup.code.substring(0, 100)}...`);
                console.log();
            }

            console.log('\n💡 Consider extracting to shared function');
            break;

        case 'unused':
            console.log('🔍 FINDING UNUSED CODE...\n');
            const unused = findUnused();

            if (unused.length === 0) {
                console.log('✅ No unused public definitions found.');
                return;
            }

            // Group by type
            const byTypeUnused = {};
            for (const u of unused) {
                if (!byTypeUnused[u.type]) byTypeUnused[u.type] = [];
                byTypeUnused[u.type].push(u);
            }

            for (const [type, items] of Object.entries(byTypeUnused)) {
                console.log(`\n🗑️  Unused ${type}s (${items.length}):`);
                for (const item of items) {
                    console.log(`   ${item.file}:${item.line} → ${item.symbol}`);
                }
            }

            console.log(`\n📊 Total: ${unused.length} potentially unused definitions`);
            console.log('⚠️  Note: May be used via dynamic imports or external code');
            break;

        case 'move':
            const moveSymbol = commandArgs[0];
            const toModule = commandArgs[1];
            if (!moveSymbol || !toModule) {
                console.log('Usage: node refactor.js move <symbol> <to_module>');
                return;
            }

            console.log(`📦 MOVE ANALYSIS: ${moveSymbol} → ${toModule}\n`);
            const moveInfo = checkMoveSafety(moveSymbol, toModule);

            if (moveInfo.definition) {
                console.log(`Current location: ${moveInfo.definition.file}:${moveInfo.definition.line}`);
            } else {
                console.log('⚠️  Definition not found!');
            }

            console.log(`\nImpact:`);
            console.log(`  • ${moveInfo.importCount} import statements to update`);
            console.log(`  • ${moveInfo.referenceCount} references`);
            console.log(`  • ${moveInfo.affectedFiles.length} files affected`);

            console.log(`\nAffected files:`);
            for (const file of moveInfo.affectedFiles) {
                console.log(`   ${file}`);
            }

            if (moveInfo.safe) {
                console.log('\n✅ Move appears safe (all references have imports)');
            } else {
                console.log('\n⚠️  Some files use symbol without proper import');
            }
            break;

        case 'help':
        default:
            console.log(`
Commands:
  usages <symbol>              Find all usages of a symbol
  rename <old> <new> --dry-run Preview rename operation
  duplicates                   Find duplicate code blocks
  unused                       Find unused definitions
  move <symbol> <module>       Check safety of moving symbol

Options:
  --path=<dir>                 Target directory (default: .)
  --dry-run                    Preview only, don't modify files
`);
    }
}

main();
