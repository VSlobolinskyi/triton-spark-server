/**
 * Molecule: API-SURFACE
 * Analyze the complexity of exported/public API
 *
 * Shows what's exposed in __all__ and its complexity
 */

const { runAtom, parsePredicates, printHeader, printSection } = require('./utils');

function apiSurface(scanPath) {
    printHeader('API Surface Analysis');
    console.log('\x1b[90mComplexity of exported symbols (__all__)\x1b[0m\n');

    const exports = parsePredicates(runAtom('exports', scanPath));
    const complexity = parsePredicates(runAtom('complexity', scanPath));
    const defines = parsePredicates(runAtom('defines', scanPath));

    // Map complexity by function name
    const complexityMap = new Map();
    for (const c of complexity) {
        complexityMap.set(c.args[1], {
            cyc: parseInt(c.args[2]),
            cog: parseInt(c.args[3]),
            lines: parseInt(c.args[4]),
        });
    }

    // Group defines by what they belong to
    const symbolMethods = new Map(); // symbol -> [methods]
    for (const d of defines) {
        const type = d.args[2];
        if (type === 'method' || type === 'async_method') {
            const parts = d.args[1].split('.');
            if (parts.length === 2) {
                const [cls, method] = parts;
                if (!symbolMethods.has(cls)) {
                    symbolMethods.set(cls, []);
                }
                symbolMethods.get(cls).push(method);
            }
        }
    }

    // Analyze each export
    const results = [];
    for (const exp of exports) {
        const symbol = exp.args[1];
        const file = exp.args[0];

        // Get direct complexity or sum of methods
        const methods = symbolMethods.get(symbol) || [];
        let maxCyc = 0;
        let totalLines = 0;
        let methodCount = 0;

        if (methods.length > 0) {
            // It's a class
            for (const m of methods) {
                const key = `${symbol}.${m}`;
                const c = complexityMap.get(key);
                if (c) {
                    maxCyc = Math.max(maxCyc, c.cyc);
                    totalLines += c.lines;
                    methodCount++;
                }
            }
        } else {
            // It's a function
            const c = complexityMap.get(symbol);
            if (c) {
                maxCyc = c.cyc;
                totalLines = c.lines;
                methodCount = 1;
            }
        }

        if (methodCount > 0) {
            results.push({
                symbol,
                file,
                maxCyc,
                totalLines,
                methodCount,
                isClass: methods.length > 0,
            });
        }
    }

    // Sort by complexity
    results.sort((a, b) => b.maxCyc - a.maxCyc);

    // Print by risk level
    const critical = results.filter(r => r.maxCyc > 15);
    const warning = results.filter(r => r.maxCyc > 10 && r.maxCyc <= 15);
    const good = results.filter(r => r.maxCyc <= 10);

    if (critical.length > 0) {
        printSection(`Critical Complexity (>${15})`);
        for (const r of critical) {
            console.log(`  🔴 \x1b[1m${r.symbol}\x1b[0m`);
            console.log(`     \x1b[90m${r.file}\x1b[0m`);
            console.log(`     Max cyclomatic: ${r.maxCyc}, Lines: ${r.totalLines}`);
            if (r.isClass) console.log(`     ${r.methodCount} methods`);
        }
    }

    if (warning.length > 0) {
        printSection(`Elevated Complexity (>${10})`);
        for (const r of warning) {
            console.log(`  🟠 \x1b[1m${r.symbol}\x1b[0m`);
            console.log(`     Max cyclomatic: ${r.maxCyc}, Lines: ${r.totalLines}`);
        }
    }

    printSection(`Good Complexity (≤${10})`);
    console.log(`  🟢 ${good.length} symbols with acceptable complexity`);
    for (const r of good.slice(0, 5)) {
        console.log(`     ${r.symbol} (cyc:${r.maxCyc})`);
    }
    if (good.length > 5) {
        console.log(`     \x1b[90m... and ${good.length - 5} more\x1b[0m`);
    }

    // Summary
    console.log(`\n\x1b[33mAPI Surface: ${results.length} exported symbols\x1b[0m`);
    console.log(`  🔴 ${critical.length} critical  🟠 ${warning.length} elevated  🟢 ${good.length} good`);
}

module.exports = apiSurface;
