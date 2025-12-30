/**
 * Molecule: ENTRY-POINTS
 * Find all external entry points
 */

const { runAtom, parsePredicates, printHeader, printSection } = require('./utils');

function entryPoints(scanPath) {
    printHeader('Entry Points');

    const defines = parsePredicates(runAtom('defines', scanPath));
    const decorates = parsePredicates(runAtom('decorates', scanPath));

    // Main functions
    printSection('Main Functions');
    const mains = defines.filter(d => d.args[1] === 'main');
    if (mains.length === 0) {
        console.log('  \x1b[90m(none found)\x1b[0m');
    } else {
        mains.forEach(m => {
            console.log(`  \x1b[32m▶\x1b[0m ${m.args[0]}:${m.args[3]}`);
        });
    }

    // HTTP endpoints
    printSection('HTTP Endpoints');
    const routes = decorates.filter(d =>
        d.args[1].match(/^(app|router)\.(get|post|put|delete|patch)$/)
    );
    if (routes.length === 0) {
        console.log('  \x1b[90m(none found)\x1b[0m');
    } else {
        routes.forEach(r => {
            const method = r.args[1].split('.')[1].toUpperCase();
            console.log(`  \x1b[34m${method}\x1b[0m ${r.args[2]} \x1b[90m(${r.args[0]})\x1b[0m`);
        });
    }

    // CLI entry points (argparse)
    printSection('CLI Scripts (with argparse)');
    const argparseUsers = new Set();
    parsePredicates(runAtom('calls', scanPath)).forEach(c => {
        if (c.args[2].includes('ArgumentParser') || c.args[2].includes('argparse')) {
            argparseUsers.add(c.args[0]);
        }
    });
    if (argparseUsers.size === 0) {
        console.log('  \x1b[90m(none found)\x1b[0m');
    } else {
        argparseUsers.forEach(f => console.log(`  \x1b[35m⌘\x1b[0m ${f}`));
    }

    // gRPC servicers
    printSection('gRPC Servicers');
    const inherits = parsePredicates(runAtom('inherits', scanPath));
    const servicers = inherits.filter(i => i.args[2].includes('Servicer'));
    if (servicers.length === 0) {
        console.log('  \x1b[90m(none found)\x1b[0m');
    } else {
        servicers.forEach(s => {
            console.log(`  \x1b[36m◉\x1b[0m ${s.args[1]} \x1b[90m(${s.args[0]})\x1b[0m`);
        });
    }
}

module.exports = entryPoints;
