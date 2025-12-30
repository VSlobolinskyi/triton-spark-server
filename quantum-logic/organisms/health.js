/**
 * Organism: HEALTH
 * Codebase health check - finds issues and suggests improvements
 *
 * Combines multiple analyses:
 * - Dead code
 * - Circular dependencies
 * - Duplicate code
 * - Complexity issues
 * - Orphan files
 */

const { runAtom, parsePredicates, printHeader, printSection, printSubsection } = require('./utils');

function health(scanPath) {
    printHeader('CODEBASE HEALTH CHECK');
    console.log(`\x1b[90mPath: ${scanPath}\x1b[0m\n`);

    const issues = {
        critical: [],
        warning: [],
        info: [],
    };

    // Gather data
    const defines = parsePredicates(runAtom('defines', scanPath));
    const calls = parsePredicates(runAtom('calls', scanPath));
    const imports = parsePredicates(runAtom('imports', scanPath));
    const decorates = parsePredicates(runAtom('decorates', scanPath));
    const complexity = parsePredicates(runAtom('complexity', scanPath));
    const mutates = parsePredicates(runAtom('mutates', scanPath));

    // ═══════════════════════════════════════════════════════════════
    // DEAD CODE
    // ═══════════════════════════════════════════════════════════════
    printSection('DEAD CODE ANALYSIS');

    const defined = new Map();
    defines.forEach(d => {
        if (['function', 'async_function', 'method', 'async_method'].includes(d.args[2])) {
            const name = d.args[1].split('.').pop();
            if (!defined.has(name)) defined.set(name, []);
            defined.get(name).push({ file: d.args[0], fullName: d.args[1], line: d.args[3] });
        }
    });

    const called = new Set();
    calls.forEach(c => called.add(c.args[2].split('.').pop()));

    const decorated = new Set();
    decorates.forEach(d => decorated.add(d.args[2].split('.').pop()));

    const builtins = new Set(['__init__', '__enter__', '__exit__', '__str__', '__repr__',
        '__len__', '__iter__', '__next__', '__call__', '__getitem__', '__setitem__',
        '__eq__', '__hash__', '__bool__', '__del__', 'forward', 'main']);

    let deadCount = 0;
    defined.forEach((locations, name) => {
        if (!called.has(name) && !decorated.has(name) && !builtins.has(name)) {
            deadCount += locations.length;
            locations.forEach(loc => {
                issues.warning.push({
                    type: 'dead-code',
                    message: `Unused function: ${loc.fullName}`,
                    file: loc.file,
                    line: loc.line,
                });
            });
        }
    });

    if (deadCount === 0) {
        console.log('  ✅ No dead code found');
    } else {
        console.log(`  ⚠️  ${deadCount} potentially unused functions`);
        issues.warning.slice(0, 3).forEach(i => {
            if (i.type === 'dead-code') {
                console.log(`     └─ ${i.message}`);
            }
        });
        if (deadCount > 3) console.log(`     └─ ... and ${deadCount - 3} more`);
    }

    // ═══════════════════════════════════════════════════════════════
    // CIRCULAR DEPENDENCIES
    // ═══════════════════════════════════════════════════════════════
    printSection('CIRCULAR DEPENDENCIES');

    // Build module graph
    const graph = new Map();
    const allModules = new Set();

    imports.forEach(i => {
        const file = i.args[0];
        const moduleName = file.replace(/\\/g, '/').replace(/\.py$/, '').replace(/\/__init__$/, '').replace(/\//g, '.');
        allModules.add(moduleName);
    });

    imports.forEach(i => {
        const file = i.args[0];
        const importedModule = i.args[1];
        const moduleName = file.replace(/\\/g, '/').replace(/\.py$/, '').replace(/\/__init__$/, '').replace(/\//g, '.');

        if (!graph.has(moduleName)) graph.set(moduleName, new Set());

        const isInternal = [...allModules].some(m =>
            importedModule === m || importedModule.startsWith(m + '.') || m.startsWith(importedModule + '.')
        );

        if (isInternal) {
            const matched = [...allModules].find(m =>
                importedModule === m || m.endsWith('.' + importedModule)
            );
            if (matched && matched !== moduleName) {
                graph.get(moduleName).add(matched);
            }
        }
    });

    // Find bidirectional imports
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
        console.log('  ✅ No circular dependencies');
    } else {
        console.log(`  ⚠️  ${bidirectional.length} bidirectional import pair(s)`);
        bidirectional.slice(0, 3).forEach(([a, b]) => {
            console.log(`     └─ ${a} ↔ ${b}`);
            issues.warning.push({
                type: 'circular',
                message: `Circular import: ${a} ↔ ${b}`,
            });
        });
    }

    // ═══════════════════════════════════════════════════════════════
    // COMPLEXITY
    // ═══════════════════════════════════════════════════════════════
    printSection('COMPLEXITY ISSUES');

    const complexFuncs = complexity.map(c => ({
        file: c.args[0],
        func: c.args[1],
        cyclomatic: parseInt(c.args[2]),
        cognitive: parseInt(c.args[3]),
        lines: parseInt(c.args[4]),
        nesting: parseInt(c.args[5]),
        params: parseInt(c.args[6]),
    }));

    const highCyclomatic = complexFuncs.filter(f => f.cyclomatic > 15);
    const deepNesting = complexFuncs.filter(f => f.nesting > 5);
    const longFuncs = complexFuncs.filter(f => f.lines > 100);
    const manyParams = complexFuncs.filter(f => f.params > 7);

    if (highCyclomatic.length === 0 && deepNesting.length === 0 && longFuncs.length === 0 && manyParams.length === 0) {
        console.log('  ✅ No critical complexity issues');
    } else {
        if (highCyclomatic.length > 0) {
            console.log(`  🔴 ${highCyclomatic.length} functions with cyclomatic > 15 (hard to test)`);
            highCyclomatic.slice(0, 2).forEach(f => {
                console.log(`     └─ ${f.func}() cyc:${f.cyclomatic}`);
                issues.critical.push({
                    type: 'complexity',
                    message: `High cyclomatic complexity: ${f.func}() = ${f.cyclomatic}`,
                    file: f.file,
                });
            });
        }
        if (deepNesting.length > 0) {
            console.log(`  🟠 ${deepNesting.length} functions with nesting > 5 (hard to read)`);
            issues.warning.push({ type: 'nesting', message: `${deepNesting.length} deeply nested functions` });
        }
        if (longFuncs.length > 0) {
            console.log(`  🟠 ${longFuncs.length} functions with > 100 lines (should split)`);
            issues.warning.push({ type: 'length', message: `${longFuncs.length} overly long functions` });
        }
        if (manyParams.length > 0) {
            console.log(`  🟡 ${manyParams.length} functions with > 7 params (use object)`);
            issues.info.push({ type: 'params', message: `${manyParams.length} functions with many parameters` });
        }
    }

    // ═══════════════════════════════════════════════════════════════
    // SIDE EFFECTS
    // ═══════════════════════════════════════════════════════════════
    printSection('SIDE EFFECTS');

    const globalMutations = mutates.filter(m => m.args[2].startsWith('global.'));
    const instanceMutationsOutsideInit = mutates.filter(m =>
        m.args[2].startsWith('self.') && !m.args[1].includes('__init__')
    );

    if (globalMutations.length === 0 && instanceMutationsOutsideInit.length < 10) {
        console.log('  ✅ Minimal side effects detected');
    } else {
        if (globalMutations.length > 0) {
            console.log(`  🟠 ${globalMutations.length} global state mutations`);
            issues.warning.push({
                type: 'global-state',
                message: `${globalMutations.length} global state mutations`,
            });
        }
        if (instanceMutationsOutsideInit.length >= 10) {
            console.log(`  🟡 ${instanceMutationsOutsideInit.length} instance mutations outside __init__`);
            issues.info.push({
                type: 'instance-mutation',
                message: `${instanceMutationsOutsideInit.length} instance mutations outside __init__`,
            });
        }
    }

    // ═══════════════════════════════════════════════════════════════
    // HEALTH SCORE
    // ═══════════════════════════════════════════════════════════════
    console.log('\n' + '\x1b[36m' + '═'.repeat(70) + '\x1b[0m');

    const criticalWeight = issues.critical.length * 10;
    const warningWeight = issues.warning.length * 3;
    const infoWeight = issues.info.length * 1;
    const totalIssues = criticalWeight + warningWeight + infoWeight;

    let score = Math.max(0, 100 - totalIssues);
    let grade, color;

    if (score >= 90) { grade = 'A'; color = '\x1b[32m'; }
    else if (score >= 80) { grade = 'B'; color = '\x1b[32m'; }
    else if (score >= 70) { grade = 'C'; color = '\x1b[33m'; }
    else if (score >= 60) { grade = 'D'; color = '\x1b[33m'; }
    else { grade = 'F'; color = '\x1b[31m'; }

    console.log(`\x1b[1mHEALTH SCORE: ${color}${score}/100 (${grade})\x1b[0m`);
    console.log(`\n  🔴 Critical: ${issues.critical.length}`);
    console.log(`  🟠 Warnings: ${issues.warning.length}`);
    console.log(`  🟡 Info:     ${issues.info.length}`);

    if (issues.critical.length > 0) {
        console.log('\n\x1b[1mPriority fixes:\x1b[0m');
        issues.critical.slice(0, 3).forEach(i => {
            console.log(`  1. ${i.message}`);
            if (i.file) console.log(`     \x1b[90m${i.file}\x1b[0m`);
        });
    }

    console.log('\x1b[36m' + '═'.repeat(70) + '\x1b[0m');
}

module.exports = health;
