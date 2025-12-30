/**
 * Molecule: ORPHANS
 * Find files not imported by anything else
 */

const { runAtom, parsePredicates, printHeader, printSection } = require('./utils');

function orphans(scanPath) {
    printHeader('Orphan Files');

    const imports = parsePredicates(runAtom('imports', scanPath));

    // Get all files
    const allFiles = new Set();
    const importedModules = new Set();

    imports.forEach(i => {
        allFiles.add(i.args[0]);
        importedModules.add(i.args[1]);
    });

    // Check which files are never imported
    printSection('Files not imported by other modules');
    let count = 0;

    allFiles.forEach(file => {
        // Convert file path to module path
        const modulePath = file.replace(/\\/g, '/').replace(/\.py$/, '').replace(/\//g, '.');
        const parts = modulePath.split('.');

        // Check if any part matches an import
        let isImported = false;
        for (let i = parts.length; i > 0; i--) {
            const partial = parts.slice(-i).join('.');
            if ([...importedModules].some(m => m === partial || m.endsWith('.' + partial) || m.startsWith(partial + '.'))) {
                isImported = true;
                break;
            }
        }

        // Exclude __init__.py and test files
        const isInit = file.endsWith('__init__.py');
        const isTest = file.includes('test');

        if (!isImported && !isInit && !isTest) {
            console.log(`  \x1b[33m?\x1b[0m ${file}`);
            count++;
        }
    });

    if (count === 0) {
        console.log('  \x1b[32m✓ All files are imported somewhere\x1b[0m');
    } else {
        console.log(`\n  \x1b[33mTotal: ${count} orphan files (may be entry points or unused)\x1b[0m`);
    }
}

module.exports = orphans;
