/**
 * Molecule: IMPACT
 * What would break if we changed/removed a symbol
 */

const { runAtom, parsePredicates, printHeader, printSection } = require('./utils');

function impact(target, scanPath) {
    if (!target) {
        console.log('Usage: molecules impact <symbol> --path=dir');
        return;
    }

    printHeader(`Impact Analysis: ${target}`);

    const calls = parsePredicates(runAtom('calls', scanPath));
    const defines = parsePredicates(runAtom('defines', scanPath));
    const imports = parsePredicates(runAtom('imports', scanPath));

    // Find direct callers
    const directCallers = new Map();
    calls.forEach(c => {
        const callee = c.args[2];
        if (callee === target || callee.endsWith('.' + target)) {
            const caller = c.args[1];
            const file = c.args[0];
            const key = `${file}:${caller}`;
            if (!directCallers.has(key)) {
                directCallers.set(key, { file, caller, lines: [] });
            }
            directCallers.get(key).lines.push(c.args[3]);
        }
    });

    // Find files that import it
    const importers = [];
    imports.forEach(i => {
        if (i.args[2] === target || i.args[1].endsWith(target)) {
            importers.push({ file: i.args[0], module: i.args[1], line: i.args[4] });
        }
    });

    // Find definition
    const definition = defines.find(d => d.args[1] === target || d.args[1].endsWith('.' + target));

    if (definition) {
        printSection('Definition');
        console.log(`  📍 ${definition.args[0]}:${definition.args[3]}`);
        console.log(`     Type: ${definition.args[2]}`);
    }

    printSection(`Direct Callers (${directCallers.size})`);
    if (directCallers.size === 0) {
        console.log('  \x1b[90m(no direct callers found)\x1b[0m');
    } else {
        directCallers.forEach((info, key) => {
            console.log(`  \x1b[34m←\x1b[0m ${info.caller}`);
            console.log(`    \x1b[90m${info.file} (lines: ${info.lines.join(', ')})\x1b[0m`);
        });
    }

    printSection(`Importers (${importers.length})`);
    if (importers.length === 0) {
        console.log('  \x1b[90m(no direct imports found)\x1b[0m');
    } else {
        importers.forEach(i => {
            console.log(`  \x1b[35m⬇\x1b[0m ${i.file}:${i.line}`);
            console.log(`    \x1b[90mfrom ${i.module}\x1b[0m`);
        });
    }

    // Transitive impact (callers of callers)
    printSection('Transitive Impact (callers of callers)');
    const visited = new Set([target]);
    const queue = [...directCallers.values()].map(c => c.caller);
    const transitive = [];

    queue.forEach(caller => {
        if (visited.has(caller)) return;
        visited.add(caller);

        calls.forEach(c => {
            const callee = c.args[2];
            if (callee === caller || callee.endsWith('.' + caller.split('.').pop())) {
                transitive.push({
                    caller: c.args[1],
                    via: caller,
                    file: c.args[0],
                    line: c.args[3]
                });
            }
        });
    });

    if (transitive.length === 0) {
        console.log('  \x1b[90m(no transitive callers)\x1b[0m');
    } else {
        transitive.slice(0, 10).forEach(t => {
            console.log(`  \x1b[36m←←\x1b[0m ${t.caller} \x1b[90m(via ${t.via})\x1b[0m`);
        });
        if (transitive.length > 10) {
            console.log(`  \x1b[90m... and ${transitive.length - 10} more\x1b[0m`);
        }
    }
}

module.exports = impact;
