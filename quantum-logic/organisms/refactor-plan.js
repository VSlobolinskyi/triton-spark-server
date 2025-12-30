/**
 * Organism: REFACTOR-PLAN
 * Generate a refactoring plan for a symbol
 *
 * Analyzes:
 * - Where the symbol is defined
 * - All usages (calls, imports, references)
 * - Dependencies (what it needs)
 * - Dependents (what needs it)
 * - Safe refactoring steps
 */

const { runAtom, parsePredicates, printHeader, printSection, printSubsection } = require('./utils');

function refactorPlan(target, scanPath) {
    if (!target) {
        console.log('Usage: organisms refactor-plan <symbol> [--path=dir]');
        console.log('Example: organisms refactor-plan TTSRVCPipeline --path=rvc');
        return;
    }

    printHeader(`REFACTOR PLAN: ${target}`);
    console.log(`\x1b[90mPath: ${scanPath}\x1b[0m\n`);

    // Gather data
    const defines = parsePredicates(runAtom('defines', scanPath));
    const calls = parsePredicates(runAtom('calls', scanPath));
    const imports = parsePredicates(runAtom('imports', scanPath));
    const inherits = parsePredicates(runAtom('inherits', scanPath));
    const mutates = parsePredicates(runAtom('mutates', scanPath));

    // ═══════════════════════════════════════════════════════════════
    // FIND DEFINITION
    // ═══════════════════════════════════════════════════════════════
    printSection('DEFINITION');

    const definition = defines.find(d =>
        d.args[1] === target || d.args[1].endsWith('.' + target)
    );

    if (!definition) {
        console.log(`  ❌ Symbol "${target}" not found in codebase`);
        console.log('\n  Did you mean one of these?');
        const similar = defines
            .filter(d => d.args[1].toLowerCase().includes(target.toLowerCase()))
            .slice(0, 5);
        similar.forEach(d => console.log(`    • ${d.args[1]} (${d.args[2]})`));
        return;
    }

    console.log(`  📍 ${definition.args[0]}:${definition.args[3]}`);
    console.log(`  Type: ${definition.args[2]}`);

    // Check inheritance
    const parents = inherits.filter(i => i.args[1] === target);
    const children = inherits.filter(i => i.args[2] === target);

    if (parents.length > 0) {
        console.log(`  Extends: ${parents.map(p => p.args[2]).join(', ')}`);
    }
    if (children.length > 0) {
        console.log(`  Extended by: ${children.map(c => c.args[1]).join(', ')}`);
    }

    // ═══════════════════════════════════════════════════════════════
    // USAGE ANALYSIS
    // ═══════════════════════════════════════════════════════════════
    printSection('USAGE ANALYSIS');

    // Find all calls to this symbol
    const directCalls = calls.filter(c =>
        c.args[2] === target || c.args[2].endsWith('.' + target)
    );

    // Find imports of this symbol
    const directImports = imports.filter(i =>
        i.args[2] === target || i.args[1].endsWith(target)
    );

    // Group by file
    const usageByFile = new Map();
    directCalls.forEach(c => {
        const file = c.args[0];
        if (!usageByFile.has(file)) usageByFile.set(file, { calls: [], imports: [] });
        usageByFile.get(file).calls.push({ caller: c.args[1], line: c.args[3] });
    });
    directImports.forEach(i => {
        const file = i.args[0];
        if (!usageByFile.has(file)) usageByFile.set(file, { calls: [], imports: [] });
        usageByFile.get(file).imports.push({ from: i.args[1], line: i.args[4] });
    });

    console.log(`  📊 ${usageByFile.size} files use this symbol`);
    console.log(`  📞 ${directCalls.length} call sites`);
    console.log(`  📦 ${directImports.length} imports`);

    printSubsection('Files affected');
    for (const [file, usage] of usageByFile) {
        const callCount = usage.calls.length;
        const importCount = usage.imports.length;
        console.log(`    ${file}`);
        console.log(`      └─ ${callCount} calls, ${importCount} imports`);
    }

    // ═══════════════════════════════════════════════════════════════
    // DEPENDENCIES (what this symbol needs)
    // ═══════════════════════════════════════════════════════════════
    printSection('DEPENDENCIES');

    // Find what this symbol calls
    const symbolCalls = calls.filter(c =>
        c.args[1] === target ||
        c.args[1].startsWith(target + '.') ||
        c.args[1].endsWith('.' + target.split('.').pop())
    );

    const calledSymbols = [...new Set(symbolCalls.map(c => c.args[2]))];

    if (calledSymbols.length > 0) {
        console.log(`  This symbol calls ${calledSymbols.length} other symbols:`);
        calledSymbols.slice(0, 10).forEach(s => {
            console.log(`    → ${s}`);
        });
        if (calledSymbols.length > 10) {
            console.log(`    ... and ${calledSymbols.length - 10} more`);
        }
    } else {
        console.log('  No internal dependencies detected');
    }

    // ═══════════════════════════════════════════════════════════════
    // STATE MUTATIONS
    // ═══════════════════════════════════════════════════════════════
    const symbolMutations = mutates.filter(m =>
        m.args[1].startsWith(target + '.') || m.args[1] === target
    );

    if (symbolMutations.length > 0) {
        printSection('STATE MUTATIONS');
        const attrs = [...new Set(symbolMutations.map(m => m.args[2]))];
        console.log(`  Modifies ${attrs.length} attributes:`);
        attrs.forEach(a => console.log(`    • ${a}`));
    }

    // ═══════════════════════════════════════════════════════════════
    // REFACTORING STEPS
    // ═══════════════════════════════════════════════════════════════
    printSection('REFACTORING STEPS');

    console.log('  \x1b[1mTo rename this symbol:\x1b[0m');
    console.log('');
    console.log(`  1. Update definition in ${definition.args[0]}:${definition.args[3]}`);

    if (directImports.length > 0) {
        console.log(`  2. Update ${directImports.length} import statement(s):`);
        const importFiles = [...new Set(directImports.map(i => i.args[0]))];
        importFiles.slice(0, 5).forEach(f => console.log(`     • ${f}`));
        if (importFiles.length > 5) console.log(`     ... and ${importFiles.length - 5} more`);
    }

    if (directCalls.length > 0) {
        console.log(`  3. Update ${directCalls.length} call site(s):`);
        const callFiles = [...new Set(directCalls.map(c => c.args[0]))];
        callFiles.slice(0, 5).forEach(f => console.log(`     • ${f}`));
        if (callFiles.length > 5) console.log(`     ... and ${callFiles.length - 5} more`);
    }

    if (children.length > 0) {
        console.log(`  4. Update ${children.length} child class(es):`);
        children.forEach(c => console.log(`     • ${c.args[1]} in ${c.args[0]}`));
    }

    console.log('  5. Run tests to verify');

    // ═══════════════════════════════════════════════════════════════
    // RISK ASSESSMENT
    // ═══════════════════════════════════════════════════════════════
    printSection('RISK ASSESSMENT');

    let riskScore = 0;
    const risks = [];

    if (usageByFile.size > 10) {
        riskScore += 3;
        risks.push('High usage (>10 files)');
    }
    if (children.length > 0) {
        riskScore += 2;
        risks.push('Has child classes');
    }
    if (symbolMutations.length > 5) {
        riskScore += 2;
        risks.push('Many state mutations');
    }
    if (definition.args[2] === 'class') {
        riskScore += 1;
        risks.push('Is a class (larger scope)');
    }

    let riskLevel, riskColor;
    if (riskScore <= 2) { riskLevel = 'LOW'; riskColor = '\x1b[32m'; }
    else if (riskScore <= 5) { riskLevel = 'MEDIUM'; riskColor = '\x1b[33m'; }
    else { riskLevel = 'HIGH'; riskColor = '\x1b[31m'; }

    console.log(`  Risk Level: ${riskColor}${riskLevel}\x1b[0m`);

    if (risks.length > 0) {
        console.log('  Risk factors:');
        risks.forEach(r => console.log(`    ⚠️  ${r}`));
    }

    console.log('\n' + '\x1b[36m' + '═'.repeat(70) + '\x1b[0m');
    console.log(`\x1b[90mTip: Use 'node replace.js "${target}" "NewName" --dry-run' to preview changes\x1b[0m`);
    console.log('\x1b[36m' + '═'.repeat(70) + '\x1b[0m');
}

module.exports = refactorPlan;
