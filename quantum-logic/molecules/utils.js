/**
 * Shared utilities for molecules
 */

const { execSync } = require('child_process');
const path = require('path');

const atomsPath = path.join(__dirname, '..', 'atoms', 'index.js');

/**
 * Run an atom and return its output lines
 */
function runAtom(atom, scanPath = '.') {
    try {
        const cmd = `node "${atomsPath}" ${atom} --path=${scanPath}`;
        return execSync(cmd, { encoding: 'utf-8', maxBuffer: 10 * 1024 * 1024 }).trim().split('\n').filter(l => l);
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
        // Simple CSV parse (doesn't handle commas in strings, but our data is clean)
        const args = argsStr.split(', ').map(a => a.trim());
        return { predicate, args };
    }).filter(p => p);
}

/**
 * Print a styled header
 */
function printHeader(text) {
    console.log('\x1b[36m' + '═'.repeat(60) + '\x1b[0m');
    console.log('\x1b[1m' + text + '\x1b[0m');
    console.log('\x1b[36m' + '═'.repeat(60) + '\x1b[0m');
}

/**
 * Print a styled section header
 */
function printSection(text) {
    console.log('\n\x1b[33m' + text + '\x1b[0m');
    console.log('\x1b[90m' + '─'.repeat(40) + '\x1b[0m');
}

/**
 * Parse command line arguments for molecules
 */
function parseArgs(args) {
    const molecule = args[0];
    const target = args[1]?.startsWith('--') ? null : args[1];
    let scanPath = '.';

    args.forEach(arg => {
        if (arg.startsWith('--path=')) scanPath = arg.split('=')[1];
    });

    return { molecule, target, scanPath };
}

module.exports = {
    runAtom,
    parsePredicates,
    printHeader,
    printSection,
    parseArgs
};
