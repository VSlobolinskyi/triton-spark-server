/**
 * Organism: OVERVIEW
 * Complete codebase overview combining multiple molecules
 *
 * Provides a comprehensive summary for understanding a codebase:
 * - Structure and hierarchy
 * - Entry points
 * - Key patterns
 * - Potential issues
 */

const { runAtom, parsePredicates, printHeader, printSection, printSubsection } = require('./utils');

function overview(scanPath) {
    printHeader('CODEBASE OVERVIEW');
    console.log(`\x1b[90mPath: ${scanPath}\x1b[0m\n`);

    // Gather all data
    const defines = parsePredicates(runAtom('defines', scanPath));
    const imports = parsePredicates(runAtom('imports', scanPath));
    const calls = parsePredicates(runAtom('calls', scanPath));
    const decorates = parsePredicates(runAtom('decorates', scanPath));
    const inherits = parsePredicates(runAtom('inherits', scanPath));
    const exports = parsePredicates(runAtom('exports', scanPath));
    const complexity = parsePredicates(runAtom('complexity', scanPath));

    // ═══════════════════════════════════════════════════════════════
    // STRUCTURE SUMMARY
    // ═══════════════════════════════════════════════════════════════
    printSection('STRUCTURE');

    const files = [...new Set(defines.map(d => d.args[0]))];
    const classes = defines.filter(d => d.args[2] === 'class');
    const functions = defines.filter(d => d.args[2].includes('function'));
    const methods = defines.filter(d => d.args[2].includes('method'));

    console.log(`  📁 Files:      ${files.length}`);
    console.log(`  📦 Classes:    ${classes.length}`);
    console.log(`  ⚙️  Functions:  ${functions.length}`);
    console.log(`  🔧 Methods:    ${methods.length}`);

    // Top-level modules
    const modules = [...new Set(files.map(f => f.split('/')[0].split('\\')[0]))];
    console.log(`\n  Top-level modules: ${modules.join(', ')}`);

    // ═══════════════════════════════════════════════════════════════
    // ENTRY POINTS
    // ═══════════════════════════════════════════════════════════════
    printSection('ENTRY POINTS');

    // Main functions
    const mains = defines.filter(d => d.args[1] === 'main');
    if (mains.length > 0) {
        printSubsection('CLI Entry Points (main)');
        mains.forEach(m => console.log(`    ▶ ${m.args[0]}`));
    }

    // HTTP endpoints
    const httpRoutes = decorates.filter(d =>
        d.args[1].match(/^(app|router)\.(get|post|put|delete|patch)$/)
    );
    if (httpRoutes.length > 0) {
        printSubsection(`HTTP Endpoints (${httpRoutes.length})`);
        const byMethod = {};
        httpRoutes.forEach(r => {
            const method = r.args[1].split('.')[1].toUpperCase();
            if (!byMethod[method]) byMethod[method] = [];
            byMethod[method].push(r.args[2]);
        });
        for (const [method, handlers] of Object.entries(byMethod)) {
            console.log(`    ${method}: ${handlers.join(', ')}`);
        }
    }

    // gRPC servicers
    const servicers = inherits.filter(i => i.args[2].includes('Servicer'));
    if (servicers.length > 0) {
        printSubsection('gRPC Servicers');
        servicers.forEach(s => console.log(`    ◉ ${s.args[1]} (${s.args[0]})`));
    }

    // ═══════════════════════════════════════════════════════════════
    // PUBLIC API
    // ═══════════════════════════════════════════════════════════════
    if (exports.length > 0) {
        printSection('PUBLIC API (__all__ exports)');

        const byFile = {};
        exports.forEach(e => {
            if (!byFile[e.args[0]]) byFile[e.args[0]] = [];
            byFile[e.args[0]].push(e.args[1]);
        });

        for (const [file, symbols] of Object.entries(byFile)) {
            console.log(`  📄 ${file}`);
            console.log(`     ${symbols.join(', ')}`);
        }
    }

    // ═══════════════════════════════════════════════════════════════
    // KEY CLASSES
    // ═══════════════════════════════════════════════════════════════
    printSection('KEY CLASSES');

    // Classes with most methods
    const classMethods = {};
    methods.forEach(m => {
        const className = m.args[1].split('.')[0];
        if (!classMethods[className]) classMethods[className] = 0;
        classMethods[className]++;
    });

    const sortedClasses = Object.entries(classMethods)
        .sort((a, b) => b[1] - a[1])
        .slice(0, 10);

    if (sortedClasses.length > 0) {
        console.log('  Most complex classes (by method count):');
        for (const [cls, count] of sortedClasses) {
            const parents = inherits.filter(i => i.args[1] === cls).map(i => i.args[2]);
            const parentStr = parents.length > 0 ? ` \x1b[90m(${parents.join(', ')})\x1b[0m` : '';
            console.log(`    ${count.toString().padStart(3)} methods │ ${cls}${parentStr}`);
        }
    }

    // ═══════════════════════════════════════════════════════════════
    // COMPLEXITY HOTSPOTS
    // ═══════════════════════════════════════════════════════════════
    printSection('COMPLEXITY HOTSPOTS');

    // Parse complexity: COMPLEXITY(file, func, cyclomatic, cognitive, lines, nesting, params)
    const complexFuncs = complexity
        .map(c => ({
            file: c.args[0],
            func: c.args[1],
            cyclomatic: parseInt(c.args[2]),
            cognitive: parseInt(c.args[3]),
            lines: parseInt(c.args[4]),
            nesting: parseInt(c.args[5]),
            params: parseInt(c.args[6]),
            score: parseInt(c.args[2]) + Math.floor(parseInt(c.args[3]) / 2) + Math.floor(parseInt(c.args[4]) / 20)
        }))
        .sort((a, b) => b.score - a.score)
        .slice(0, 5);

    if (complexFuncs.length > 0) {
        console.log('  Top complexity hotspots:');
        for (const f of complexFuncs) {
            const bar = '█'.repeat(Math.min(f.score, 20));
            console.log(`    ${bar} ${f.score}`);
            console.log(`      ${f.func}() - cyc:${f.cyclomatic} cog:${f.cognitive} lines:${f.lines}`);
        }
    }

    // ═══════════════════════════════════════════════════════════════
    // DEPENDENCY PATTERNS
    // ═══════════════════════════════════════════════════════════════
    printSection('DEPENDENCIES');

    // Most imported modules
    const importCounts = {};
    imports.forEach(i => {
        const mod = i.args[1].split('.')[0];
        importCounts[mod] = (importCounts[mod] || 0) + 1;
    });

    const topImports = Object.entries(importCounts)
        .sort((a, b) => b[1] - a[1])
        .slice(0, 10);

    console.log('  Most imported modules:');
    for (const [mod, count] of topImports) {
        const bar = '▪'.repeat(Math.min(count, 15));
        console.log(`    ${bar.padEnd(15)} ${count.toString().padStart(3)}x ${mod}`);
    }

    // ═══════════════════════════════════════════════════════════════
    // POTENTIAL ISSUES
    // ═══════════════════════════════════════════════════════════════
    printSection('POTENTIAL ISSUES');

    let issueCount = 0;

    // High complexity functions
    const highComplexity = complexFuncs.filter(f => f.cyclomatic > 10);
    if (highComplexity.length > 0) {
        console.log(`  ⚠️  ${highComplexity.length} functions with cyclomatic complexity > 10`);
        issueCount += highComplexity.length;
    }

    // Long functions
    const longFuncs = complexity.filter(c => parseInt(c.args[4]) > 100);
    if (longFuncs.length > 0) {
        console.log(`  ⚠️  ${longFuncs.length} functions with > 100 lines`);
        issueCount += longFuncs.length;
    }

    // Deep nesting
    const deepNesting = complexity.filter(c => parseInt(c.args[5]) > 5);
    if (deepNesting.length > 0) {
        console.log(`  ⚠️  ${deepNesting.length} functions with nesting depth > 5`);
        issueCount += deepNesting.length;
    }

    // Many parameters
    const manyParams = complexity.filter(c => parseInt(c.args[6]) > 6);
    if (manyParams.length > 0) {
        console.log(`  ⚠️  ${manyParams.length} functions with > 6 parameters`);
        issueCount += manyParams.length;
    }

    if (issueCount === 0) {
        console.log('  ✅ No significant issues detected');
    }

    // ═══════════════════════════════════════════════════════════════
    // SUMMARY
    // ═══════════════════════════════════════════════════════════════
    console.log('\n' + '\x1b[36m' + '═'.repeat(70) + '\x1b[0m');
    console.log('\x1b[1mSummary:\x1b[0m');
    console.log(`  ${files.length} files, ${classes.length} classes, ${functions.length + methods.length} functions/methods`);
    console.log(`  ${mains.length} CLI entry points, ${httpRoutes.length} HTTP endpoints, ${servicers.length} gRPC servicers`);
    if (issueCount > 0) {
        console.log(`  \x1b[33m${issueCount} potential issues to review\x1b[0m`);
    }
    console.log('\x1b[36m' + '═'.repeat(70) + '\x1b[0m');
}

module.exports = overview;
