/**
 * Molecule: CIRCULAR
 * Find circular dependencies in the codebase
 */

const { runAtom, parsePredicates, printHeader, printSection } = require('./utils');

function circular(scanPath) {
    printHeader('Circular Dependency Analysis');

    const imports = parsePredicates(runAtom('imports', scanPath));

    // Build module graph
    // file -> Set of modules it imports (only internal ones)
    const graph = new Map();
    const allModules = new Set();

    // First pass: collect all modules
    imports.forEach(i => {
        const file = i.args[0];
        // Convert file path to module name
        const moduleName = file
            .replace(/\\/g, '/')
            .replace(/\.py$/, '')
            .replace(/\/__init__$/, '')
            .replace(/\//g, '.');

        allModules.add(moduleName);
    });

    // Second pass: build import graph
    imports.forEach(i => {
        const file = i.args[0];
        const importedModule = i.args[1];

        const moduleName = file
            .replace(/\\/g, '/')
            .replace(/\.py$/, '')
            .replace(/\/__init__$/, '')
            .replace(/\//g, '.');

        if (!graph.has(moduleName)) {
            graph.set(moduleName, new Set());
        }

        // Check if this is an internal import
        const isInternal = [...allModules].some(m =>
            importedModule === m ||
            importedModule.startsWith(m + '.') ||
            m.startsWith(importedModule + '.') ||
            m.endsWith('.' + importedModule)
        );

        if (isInternal) {
            // Find the actual module name
            const matchedModule = [...allModules].find(m =>
                importedModule === m ||
                m.endsWith('.' + importedModule) ||
                importedModule.endsWith('.' + m.split('.').pop())
            );

            if (matchedModule && matchedModule !== moduleName) {
                graph.get(moduleName).add(matchedModule);
            }
        }
    });

    // Find cycles using DFS
    const visited = new Set();
    const recStack = new Set();
    const cycles = [];

    function dfs(node, path) {
        visited.add(node);
        recStack.add(node);

        const neighbors = graph.get(node) || new Set();
        for (const neighbor of neighbors) {
            if (!visited.has(neighbor)) {
                dfs(neighbor, [...path, neighbor]);
            } else if (recStack.has(neighbor)) {
                // Found a cycle
                const cycleStart = path.indexOf(neighbor);
                if (cycleStart !== -1) {
                    cycles.push([...path.slice(cycleStart), neighbor]);
                } else {
                    cycles.push([...path, neighbor]);
                }
            }
        }

        recStack.delete(node);
    }

    for (const [node] of graph) {
        if (!visited.has(node)) {
            dfs(node, [node]);
        }
    }

    // Remove duplicate cycles (same cycle starting from different points)
    const uniqueCycles = [];
    const seen = new Set();

    for (const cycle of cycles) {
        // Normalize: start from smallest element
        const minIdx = cycle.indexOf(cycle.reduce((a, b) => a < b ? a : b));
        const normalized = [...cycle.slice(minIdx), ...cycle.slice(0, minIdx)];
        const key = normalized.join(' -> ');

        if (!seen.has(key)) {
            seen.add(key);
            uniqueCycles.push(cycle);
        }
    }

    // Print results
    printSection(`Circular Dependencies (${uniqueCycles.length})`);

    if (uniqueCycles.length === 0) {
        console.log('  \x1b[32m✓ No circular dependencies found\x1b[0m');
    } else {
        for (const cycle of uniqueCycles) {
            console.log(`\n  \x1b[31m↺\x1b[0m Cycle of length ${cycle.length - 1}:`);
            for (let i = 0; i < cycle.length; i++) {
                const arrow = i < cycle.length - 1 ? ' →' : ' ↺';
                console.log(`    ${cycle[i]}${arrow}`);
            }
        }

        console.log(`\n\x1b[33m⚠ ${uniqueCycles.length} circular dependency chain(s) detected\x1b[0m`);
        console.log('\x1b[90mTip: Consider extracting shared code to break cycles\x1b[0m');
    }

    // Show bidirectional imports (A imports B and B imports A)
    printSection('Direct Bidirectional Imports');

    const bidirectional = [];
    for (const [modA, importsA] of graph) {
        for (const modB of importsA) {
            const importsB = graph.get(modB);
            if (importsB && importsB.has(modA) && modA < modB) {
                bidirectional.push([modA, modB]);
            }
        }
    }

    if (bidirectional.length === 0) {
        console.log('  \x1b[32m✓ No direct bidirectional imports\x1b[0m');
    } else {
        for (const [a, b] of bidirectional) {
            console.log(`  \x1b[33m↔\x1b[0m ${a}`);
            console.log(`    ↔ ${b}`);
        }
    }
}

module.exports = circular;
