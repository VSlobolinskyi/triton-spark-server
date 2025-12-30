/**
 * Molecule: COUPLING
 * Measure how tightly modules are coupled
 */

const { runAtom, parsePredicates, printHeader, printSection } = require('./utils');

function coupling(scanPath) {
    printHeader('Module Coupling Analysis');

    const imports = parsePredicates(runAtom('imports', scanPath));

    // Build import graph
    const importGraph = new Map(); // file -> Set of modules imported

    imports.forEach(i => {
        const file = i.args[0];
        const module = i.args[1];

        // Normalize to top-level module
        const baseModule = module.split('.')[0];

        if (!importGraph.has(file)) importGraph.set(file, new Set());
        importGraph.get(file).add(baseModule);
    });

    // Count imports per module
    const moduleCounts = new Map();
    importGraph.forEach((imports, file) => {
        const fileModule = file.split('/')[0];
        imports.forEach(imp => {
            const key = `${fileModule} → ${imp}`;
            moduleCounts.set(key, (moduleCounts.get(key) || 0) + 1);
        });
    });

    // Sort by count
    const sorted = [...moduleCounts.entries()].sort((a, b) => b[1] - a[1]);

    printSection('Top Dependencies');
    sorted.slice(0, 15).forEach(([dep, count]) => {
        const bar = '█'.repeat(Math.min(count, 20));
        console.log(`  ${dep.padEnd(30)} ${bar} ${count}`);
    });

    // Find circular-ish dependencies (A imports B and B imports A)
    printSection('Bidirectional Dependencies');
    const pairs = new Set();
    sorted.forEach(([dep]) => {
        const [from, to] = dep.split(' → ');
        const reverse = `${to} → ${from}`;
        if (moduleCounts.has(reverse) && from !== to) {
            const key = [from, to].sort().join(' ↔ ');
            pairs.add(key);
        }
    });

    if (pairs.size === 0) {
        console.log('  \x1b[32m✓ No bidirectional dependencies\x1b[0m');
    } else {
        pairs.forEach(p => console.log(`  \x1b[33m↔\x1b[0m ${p}`));
    }
}

module.exports = coupling;
