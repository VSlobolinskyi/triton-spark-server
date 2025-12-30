#!/usr/bin/env node
/**
 * Python Codebase Analyzer v2 - Built on QuantumLogic
 *
 * This is an example of a project-specific macro that consumes QuantumLogic.
 * It provides the same functionality as analyze.js but uses the framework.
 *
 * Usage:
 *   node analyze-v2.js imports [--path=dir]     Show import dependency graph
 *   node analyze-v2.js classes [--path=dir]     Show class hierarchy and methods
 *   node analyze-v2.js calls <function>         Show call graph for a function
 *   node analyze-v2.js exports [--path=dir]     Show module public API (__all__)
 *   node analyze-v2.js dataflow <class>         Show data flow through a class
 */

const ql = require('../quantum-logic');

// Parse arguments
const args = process.argv.slice(2);
let command = null;
let target = null;
let searchPath = '.';

for (const arg of args) {
    if (arg.startsWith('--path=')) {
        searchPath = arg.slice(7);
    } else if (command === null) {
        command = arg;
    } else if (target === null) {
        target = arg;
    }
}

// Commands - now using QuantumLogic

function cmdImports() {
    console.log(`\nImport Dependency Graph (${searchPath})`);
    console.log('═'.repeat(60));

    // Use QuantumLogic atom
    const imports = ql.atom('imports', searchPath);

    // Group by file
    const byFile = ql.groupBy(imports, 'file');

    // Filter to local imports and display
    for (const [file, fileImports] of Object.entries(byFile).sort()) {
        const localImports = fileImports
            .filter(i => {
                const mod = i.args[1];
                return mod.startsWith('rvc') || mod.startsWith('sparktts') || mod.startsWith('.');
            })
            .map(i => i.args[1]);

        if (localImports.length > 0) {
            const uniqueImports = [...new Set(localImports)];
            console.log(`\n${file}`);
            for (const dep of uniqueImports) {
                console.log(`  └── ${dep}`);
            }
        }
    }

    console.log(`\n${'─'.repeat(60)}`);
    console.log(`Files analyzed: ${Object.keys(byFile).length}`);
}

function cmdClasses() {
    console.log(`\nClass Hierarchy (${searchPath})`);
    console.log('═'.repeat(60));

    // Get defines and inherits from QuantumLogic
    const defines = ql.atom('defines', searchPath);
    const inherits = ql.atom('inherits', searchPath);

    // Find all classes
    const classes = defines.filter(d => d.args[2] === 'class');
    const methods = defines.filter(d => d.args[2] === 'method' || d.args[2] === 'async_method');

    // Build inheritance map
    const parentMap = {};
    for (const inh of inherits) {
        parentMap[inh.args[1]] = inh.args[2];
    }

    // Display each class
    for (const cls of classes.sort((a, b) => a.args[1].localeCompare(b.args[1]))) {
        const name = cls.args[1];
        const file = cls.args[0];
        const parent = parentMap[name];

        const parentStr = parent ? ` (${parent})` : '';
        console.log(`\n${name}${parentStr}`);
        console.log(`  File: ${file}`);

        // Find methods for this class
        const clsMethods = methods
            .filter(m => m.args[1].startsWith(name + '.'))
            .map(m => m.args[1].split('.')[1]);

        if (clsMethods.length > 0) {
            console.log(`  Methods:`);
            const publicMethods = clsMethods.filter(m => !m.startsWith('_'));
            const privateMethods = clsMethods.filter(m => m.startsWith('_') && !m.startsWith('__'));
            const magicMethods = clsMethods.filter(m => m.startsWith('__'));

            if (publicMethods.length > 0) {
                console.log(`    Public: ${publicMethods.join(', ')}`);
            }
            if (privateMethods.length > 0) {
                console.log(`    Private: ${privateMethods.join(', ')}`);
            }
            if (magicMethods.length > 0) {
                console.log(`    Magic: ${magicMethods.join(', ')}`);
            }
        }
    }

    console.log(`\n${'─'.repeat(60)}`);
    console.log(`Classes found: ${classes.length}`);
}

function cmdExports() {
    console.log(`\nModule Exports / Public API (${searchPath})`);
    console.log('═'.repeat(60));

    // Use QuantumLogic exports atom
    const exports = ql.atom('exports', searchPath);

    // Group by file
    const byFile = ql.groupBy(exports, 'file');

    for (const [file, fileExports] of Object.entries(byFile).sort()) {
        console.log(`\n${file}`);
        console.log(`  __all__ = [`);
        for (const exp of fileExports) {
            console.log(`    "${exp.args[1]}",`);
        }
        console.log(`  ]`);
    }
}

function cmdCalls() {
    if (!target) {
        console.error('Usage: node analyze-v2.js calls <function_name>');
        process.exit(1);
    }

    console.log(`\nCall Sites for: ${target}`);
    console.log('═'.repeat(60));

    // Use QuantumLogic calls atom
    const calls = ql.atom('calls', searchPath);

    // Filter to calls of our target
    const targetCalls = calls.filter(c => c.args[2] === target || c.args[2].endsWith('.' + target));

    // Group by file
    const byFile = ql.groupBy(targetCalls, 'file');

    let totalCalls = 0;
    for (const [file, fileCalls] of Object.entries(byFile).sort()) {
        console.log(`\n${file}`);
        for (const call of fileCalls) {
            console.log(`  L${call.args[3]}: called from ${call.args[1]}`);
        }
        totalCalls += fileCalls.length;
    }

    console.log(`\n${'─'.repeat(60)}`);
    console.log(`Total call sites: ${totalCalls}`);
}

function cmdDataflow() {
    if (!target) {
        console.error('Usage: node analyze-v2.js dataflow <ClassName>');
        process.exit(1);
    }

    console.log(`\nData Flow Analysis: ${target}`);
    console.log('═'.repeat(60));

    // Use QuantumLogic atoms
    const defines = ql.atom('defines', searchPath);
    const mutates = ql.atom('mutates', searchPath);
    const calls = ql.atom('calls', searchPath);

    // Find class definition
    const classDef = defines.find(d => d.args[1] === target && d.args[2] === 'class');

    if (classDef) {
        console.log(`\nDefined in: ${classDef.args[0]}:${classDef.args[3]}`);

        // Find all mutations in this class
        const classMutations = mutates.filter(m => m.args[1].startsWith(target + '.'));

        // Group by method
        const byMethod = {};
        for (const mut of classMutations) {
            const method = mut.args[1];
            if (!byMethod[method]) byMethod[method] = [];
            byMethod[method].push(mut.args[2]);
        }

        // Show __init__ attributes
        const initAttrs = byMethod[`${target}.__init__`];
        if (initAttrs) {
            console.log(`\nInstance Attributes (from __init__):`);
            for (const attr of [...new Set(initAttrs)]) {
                console.log(`  • ${attr}`);
            }
        }

        // Show other mutations
        const otherMethods = Object.keys(byMethod).filter(m => m !== `${target}.__init__`);
        if (otherMethods.length > 0) {
            console.log(`\nState Mutations:`);
            for (const method of otherMethods) {
                const shortMethod = method.split('.')[1];
                const attrs = [...new Set(byMethod[method])];
                console.log(`  ${shortMethod}() modifies: ${attrs.join(', ')}`);
            }
        }
    }

    // Find instantiations
    const instantiations = calls.filter(c => c.args[2] === target);
    if (instantiations.length > 0) {
        console.log(`\nInstantiated:`);
        for (const inst of instantiations) {
            console.log(`  ${inst.args[0]}:${inst.args[3]} in ${inst.args[1]}`);
        }
    }
}

// Enhanced commands using molecules

function cmdHotspots() {
    console.log(`\nCodebase Hotspots (${searchPath})`);
    console.log('═'.repeat(60));

    // Use QuantumLogic molecule directly
    const output = ql.molecule('hotspots', searchPath);
    console.log(output);
}

function cmdRisk() {
    console.log(`\nRisk Analysis (${searchPath})`);
    console.log('═'.repeat(60));

    const output = ql.molecule('risk-score', searchPath);
    console.log(output);
}

function cmdHealth() {
    console.log(`\nCodebase Health (${searchPath})`);
    console.log('═'.repeat(60));

    const output = ql.organism('health', searchPath);
    console.log(output);
}

// Main
function showHelp() {
    console.log(`
Python Codebase Analyzer v2 - Built on QuantumLogic

Usage:
  node analyze-v2.js <command> [options]

Basic Commands (original):
  imports [--path=dir]     Show import dependency graph
  classes [--path=dir]     Show class hierarchy and methods
  calls <function>         Show call sites for a function
  exports [--path=dir]     Show module public API (__all__)
  dataflow <class>         Show data flow through a class

Enhanced Commands (via QuantumLogic):
  hotspots [--path=dir]    Find codebase hotspots
  risk [--path=dir]        Risk score analysis
  health [--path=dir]      Full health check

Options:
  --path=dir               Directory to analyze (default: current)

Examples:
  node analyze-v2.js imports --path=rvc
  node analyze-v2.js classes --path=rvc/processing
  node analyze-v2.js calls process --path=rvc
  node analyze-v2.js dataflow TTSRVCPipeline
  node analyze-v2.js hotspots --path=rvc
`);
}

if (!command) {
    showHelp();
    process.exit(0);
}

switch (command) {
    case 'imports':
        cmdImports();
        break;
    case 'classes':
        cmdClasses();
        break;
    case 'calls':
        cmdCalls();
        break;
    case 'exports':
        cmdExports();
        break;
    case 'dataflow':
        cmdDataflow();
        break;
    case 'hotspots':
        cmdHotspots();
        break;
    case 'risk':
        cmdRisk();
        break;
    case 'health':
        cmdHealth();
        break;
    default:
        console.error(`Unknown command: ${command}`);
        showHelp();
        process.exit(1);
}
