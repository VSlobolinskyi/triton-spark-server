/**
 * Shared utilities for organisms
 */

const { execSync } = require('child_process');
const path = require('path');

const moleculesPath = path.join(__dirname, '..', 'molecules', 'index.js');
const atomsPath = path.join(__dirname, '..', 'atoms', 'index.js');

/**
 * Run a molecule and capture its output
 */
function runMolecule(molecule, scanPath = '.', target = null) {
    try {
        const targetArg = target ? ` ${target}` : '';
        const cmd = `node "${moleculesPath}" ${molecule}${targetArg} --path=${scanPath}`;
        return execSync(cmd, { encoding: 'utf-8', maxBuffer: 10 * 1024 * 1024 });
    } catch (e) {
        return e.stdout || '';
    }
}

/**
 * Run an atom and return parsed predicates
 */
function runAtom(atom, scanPath = '.') {
    try {
        const cmd = `node "${atomsPath}" ${atom} --path=${scanPath}`;
        const output = execSync(cmd, { encoding: 'utf-8', maxBuffer: 10 * 1024 * 1024 });
        return output.trim().split('\n').filter(l => l);
    } catch (e) {
        return [];
    }
}

/**
 * Parse predicate output lines into structured objects
 */
function parsePredicates(lines) {
    return lines.map(line => {
        const match = line.match(/^(\w+)\((.+)\)$/);
        if (!match) return null;
        const predicate = match[1];
        const argsStr = match[2];
        const args = argsStr.split(', ').map(a => a.trim());
        return { predicate, args };
    }).filter(p => p);
}

/**
 * Print a styled header
 */
function printHeader(text) {
    console.log('\x1b[36m' + '═'.repeat(70) + '\x1b[0m');
    console.log('\x1b[1;36m' + text + '\x1b[0m');
    console.log('\x1b[36m' + '═'.repeat(70) + '\x1b[0m');
}

/**
 * Print a styled section header
 */
function printSection(text) {
    console.log('\n\x1b[1;33m▸ ' + text + '\x1b[0m');
    console.log('\x1b[90m' + '─'.repeat(50) + '\x1b[0m');
}

/**
 * Print a subsection
 */
function printSubsection(text) {
    console.log(`\n  \x1b[1m${text}\x1b[0m`);
}

/**
 * Parse command line arguments for organisms
 */
function parseArgs(args) {
    const organism = args[0];
    const target = args[1]?.startsWith('--') ? null : args[1];
    let scanPath = '.';
    let outputFile = null;

    args.forEach(arg => {
        if (arg.startsWith('--path=')) scanPath = arg.split('=')[1];
        if (arg.startsWith('--output=')) outputFile = arg.split('=')[1];
    });

    return { organism, target, scanPath, outputFile };
}

module.exports = {
    runMolecule,
    runAtom,
    parsePredicates,
    printHeader,
    printSection,
    printSubsection,
    parseArgs
};
