/**
 * Molecule: RISK-SCORE
 * Combine complexity and mutations to find risky functions
 *
 * Risk = Cyclomatic Complexity × State Mutations
 * High risk functions are both complex AND mutate state
 */

const { runAtom, parsePredicates, printHeader, printSection } = require('./utils');

function riskScore(scanPath) {
    printHeader('Risk Score Analysis');
    console.log('\x1b[90mRisk = Cyclomatic Complexity × State Mutations\x1b[0m\n');

    const complexity = parsePredicates(runAtom('complexity', scanPath));
    const mutates = parsePredicates(runAtom('mutates', scanPath));

    // Filter to high complexity functions
    const highComplexity = complexity
        .filter(c => parseInt(c.args[2]) > 10)
        .map(c => ({
            file: c.args[0],
            func: c.args[1],
            cyc: parseInt(c.args[2]),
            cog: parseInt(c.args[3]),
            lines: parseInt(c.args[4]),
        }));

    // Find mutations for each
    const results = [];
    for (const c of highComplexity) {
        const funcMutations = mutates.filter(m => m.args[1] === c.func);
        if (funcMutations.length > 0) {
            const risk = c.cyc * funcMutations.length;
            results.push({
                ...c,
                mutations: funcMutations.length,
                mutatedAttrs: funcMutations.map(m => m.args[2]),
                risk,
            });
        }
    }

    results.sort((a, b) => b.risk - a.risk);

    // Print results
    printSection(`High-Risk Functions (${results.length})`);

    if (results.length === 0) {
        console.log('  \x1b[32m✓ No high-risk functions found\x1b[0m');
        return;
    }

    for (const r of results.slice(0, 15)) {
        const maxBar = 20;
        const barLen = Math.min(maxBar, Math.floor(r.risk / 10));
        const bar = '█'.repeat(barLen) + '░'.repeat(maxBar - barLen);

        const level = r.risk > 100 ? '\x1b[31m' : r.risk > 50 ? '\x1b[33m' : '\x1b[32m';
        console.log(`\n  ${level}${bar} ${r.risk}\x1b[0m`);
        console.log(`    \x1b[1m${r.func}\x1b[0m`);
        console.log(`    \x1b[90m${r.file}\x1b[0m`);
        console.log(`    Cyclomatic: ${r.cyc} × Mutations: ${r.mutations}`);

        // Show what's mutated
        const uniqueAttrs = [...new Set(r.mutatedAttrs)];
        console.log(`    Mutates: ${uniqueAttrs.slice(0, 4).join(', ')}${uniqueAttrs.length > 4 ? '...' : ''}`);
    }

    // Summary
    const critical = results.filter(r => r.risk > 100).length;
    const warning = results.filter(r => r.risk > 50 && r.risk <= 100).length;

    console.log(`\n\x1b[33mSummary: ${critical} critical, ${warning} warnings\x1b[0m`);
    if (critical > 0) {
        console.log('\x1b[90mTip: Refactor by extracting pure functions from state mutations\x1b[0m');
    }
}

module.exports = riskScore;
