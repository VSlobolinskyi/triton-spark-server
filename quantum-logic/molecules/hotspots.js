/**
 * Molecule: HOTSPOTS
 * Find the most "hot" parts of the codebase using multiple signals
 *
 * Combines: complexity, coupling, mutations, decorator usage
 */

const { runAtom, parsePredicates, printHeader, printSection } = require('./utils');

function hotspots(scanPath) {
    printHeader('Codebase Hotspots');
    console.log('\x1b[90mFiles/classes with multiple concerning signals\x1b[0m\n');

    const complexity = parsePredicates(runAtom('complexity', scanPath));
    const mutates = parsePredicates(runAtom('mutates', scanPath));
    const imports = parsePredicates(runAtom('imports', scanPath));
    const defines = parsePredicates(runAtom('defines', scanPath));

    // Score each file
    const fileScores = new Map();

    function addScore(file, points, reason) {
        if (!fileScores.has(file)) {
            fileScores.set(file, { score: 0, reasons: [] });
        }
        fileScores.get(file).score += points;
        fileScores.get(file).reasons.push(reason);
    }

    // High complexity functions
    for (const c of complexity) {
        const cyc = parseInt(c.args[2]);
        if (cyc > 15) {
            addScore(c.args[0], 30, `High complexity: ${c.args[1]} (${cyc})`);
        } else if (cyc > 10) {
            addScore(c.args[0], 15, `Elevated complexity: ${c.args[1]} (${cyc})`);
        }
    }

    // Many mutations
    const fileMutations = new Map();
    for (const m of mutates) {
        const file = m.args[0];
        fileMutations.set(file, (fileMutations.get(file) || 0) + 1);
    }
    for (const [file, count] of fileMutations) {
        if (count > 20) {
            addScore(file, 25, `Many mutations (${count})`);
        } else if (count > 10) {
            addScore(file, 10, `Moderate mutations (${count})`);
        }
    }

    // High import count (coupling)
    const fileImports = new Map();
    for (const i of imports) {
        const file = i.args[0];
        fileImports.set(file, (fileImports.get(file) || 0) + 1);
    }
    for (const [file, count] of fileImports) {
        if (count > 20) {
            addScore(file, 20, `High coupling (${count} imports)`);
        } else if (count > 15) {
            addScore(file, 10, `Moderate coupling (${count} imports)`);
        }
    }

    // Many definitions (large file)
    const fileDefs = new Map();
    for (const d of defines) {
        const file = d.args[0];
        fileDefs.set(file, (fileDefs.get(file) || 0) + 1);
    }
    for (const [file, count] of fileDefs) {
        if (count > 30) {
            addScore(file, 15, `Large file (${count} definitions)`);
        }
    }

    // Sort and display
    const sorted = [...fileScores.entries()]
        .sort((a, b) => b[1].score - a[1].score);

    printSection(`Hotspots (${sorted.length} files analyzed)`);

    if (sorted.length === 0 || sorted[0][1].score === 0) {
        console.log('  \x1b[32m✓ No significant hotspots found\x1b[0m');
        return;
    }

    for (const [file, data] of sorted.slice(0, 10)) {
        if (data.score === 0) continue;

        const maxBar = 20;
        const barLen = Math.min(maxBar, Math.floor(data.score / 5));
        const bar = '█'.repeat(barLen) + '░'.repeat(maxBar - barLen);

        const level = data.score > 50 ? '\x1b[31m🔥' : data.score > 25 ? '\x1b[33m⚠️' : '\x1b[90m·';
        console.log(`\n  ${level} ${bar} ${data.score}\x1b[0m`);
        console.log(`    \x1b[36m${file}\x1b[0m`);

        for (const reason of data.reasons.slice(0, 3)) {
            console.log(`    └─ ${reason}`);
        }
        if (data.reasons.length > 3) {
            console.log(`    └─ \x1b[90m... and ${data.reasons.length - 3} more\x1b[0m`);
        }
    }

    // Summary
    const critical = sorted.filter(([_, d]) => d.score > 50).length;
    const warning = sorted.filter(([_, d]) => d.score > 25 && d.score <= 50).length;

    console.log(`\n\x1b[33mSummary: ${critical} critical hotspots, ${warning} warnings\x1b[0m`);
}

module.exports = hotspots;
