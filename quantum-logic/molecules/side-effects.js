/**
 * Molecule: SIDE-EFFECTS
 * Find functions that mutate state outside their __init__
 */

const { runAtom, parsePredicates, printHeader, printSection } = require('./utils');

function sideEffects(scanPath) {
    printHeader('Side Effect Analysis');

    const mutates = parsePredicates(runAtom('mutates', scanPath));

    // Group mutations by function
    const byFunction = new Map();
    mutates.forEach(m => {
        const func = m.args[1];
        const attr = m.args[2];
        const file = m.args[0];
        const line = m.args[3];

        if (!byFunction.has(func)) byFunction.set(func, []);
        byFunction.get(func).push({ attr, file, line });
    });

    // Categorize
    printSection('Global State Mutations');
    let globalCount = 0;
    byFunction.forEach((mutations, func) => {
        const globals = mutations.filter(m => m.attr.startsWith('global.'));
        if (globals.length > 0) {
            console.log(`  \x1b[31m⚠\x1b[0m ${func}`);
            globals.forEach(g => {
                console.log(`    \x1b[90m${g.attr.replace('global.', '')} (${g.file}:${g.line})\x1b[0m`);
            });
            globalCount += globals.length;
        }
    });
    if (globalCount === 0) console.log('  \x1b[32m✓ No global mutations\x1b[0m');

    printSection('Instance Mutations Outside __init__');
    let instanceCount = 0;
    byFunction.forEach((mutations, func) => {
        if (func.includes('__init__')) return;

        const instance = mutations.filter(m => m.attr.startsWith('self.'));
        if (instance.length > 0) {
            console.log(`  \x1b[33m◐\x1b[0m ${func}`);
            instance.forEach(i => {
                console.log(`    \x1b[90m${i.attr} (${i.file}:${i.line})\x1b[0m`);
            });
            instanceCount += instance.length;
        }
    });
    if (instanceCount === 0) console.log('  \x1b[32m✓ No mutations outside __init__\x1b[0m');

    console.log(`\n\x1b[33mTotal: ${globalCount} global, ${instanceCount} instance mutations\x1b[0m`);
}

module.exports = sideEffects;
