/**
 * Molecule: DEAD-CODE
 * Find symbols that are defined but never called
 */

const { runAtom, parsePredicates, printHeader, printSection } = require('./utils');

function deadCode(scanPath) {
    printHeader('Dead Code Analysis');

    const defines = parsePredicates(runAtom('defines', scanPath));
    const calls = parsePredicates(runAtom('calls', scanPath));
    const decorates = parsePredicates(runAtom('decorates', scanPath));

    // Get all defined functions/methods
    const defined = new Map();
    defines.forEach(d => {
        if (['function', 'async_function', 'method', 'async_method'].includes(d.args[2])) {
            const name = d.args[1].split('.').pop(); // Get just function name
            if (!defined.has(name)) defined.set(name, []);
            defined.get(name).push({ file: d.args[0], fullName: d.args[1], line: d.args[3] });
        }
    });

    // Get all called names
    const called = new Set();
    calls.forEach(c => {
        const callee = c.args[2];
        called.add(callee.split('.').pop()); // Add base name
    });

    // Get decorated functions (they're called by framework)
    const decorated = new Set();
    decorates.forEach(d => {
        decorated.add(d.args[2].split('.').pop());
    });

    // Find uncalled (excluding decorated, __init__, __enter__, etc.)
    const builtins = new Set(['__init__', '__enter__', '__exit__', '__str__', '__repr__', '__len__',
        '__iter__', '__next__', '__call__', '__getitem__', '__setitem__', '__contains__',
        '__eq__', '__hash__', '__lt__', '__gt__', '__le__', '__ge__', '__add__', '__sub__',
        '__mul__', '__div__', '__bool__', '__del__', 'forward', 'main']);

    printSection('Potentially Dead Functions');
    let count = 0;

    defined.forEach((locations, name) => {
        if (!called.has(name) && !decorated.has(name) && !builtins.has(name)) {
            locations.forEach(loc => {
                console.log(`  \x1b[31m✗\x1b[0m ${loc.fullName}`);
                console.log(`    \x1b[90m${loc.file}:${loc.line}\x1b[0m`);
                count++;
            });
        }
    });

    if (count === 0) {
        console.log('  \x1b[32m✓ No dead code found\x1b[0m');
    } else {
        console.log(`\n  \x1b[33mTotal: ${count} potentially unused functions\x1b[0m`);
    }
}

module.exports = deadCode;
