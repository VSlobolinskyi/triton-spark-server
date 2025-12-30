#!/usr/bin/env node
/**
 * Atoms - Composable code analysis primitives
 *
 * Each atom extracts one type of relationship and outputs it as a predicate.
 * Predicates are simple, parseable, and chainable.
 *
 * Usage:
 *   node framework/atoms/index.js <atom> [--path=dir] [--format=predicate|json|tsv]
 *
 * Atoms:
 *   defines   - What symbols are defined (functions, classes, methods)
 *   calls     - What calls what
 *   imports   - What imports what
 *   mutates   - What modifies what attributes
 *   params    - Function parameters
 *   returns   - Return statements
 *   decorates - Decorator relationships
 *   inherits  - Class inheritance
 *
 * Output formats:
 *   predicate (default) - PREDICATE(arg1, arg2, ...)
 *   json                - {"predicate": "...", "args": [...]}
 *   tsv                 - tab-separated values
 *
 * Examples:
 *   node framework/atoms/index.js defines --path=rvc
 *   node framework/atoms/index.js calls --path=rvc | grep run_rvc
 *   node framework/atoms/index.js imports --path=rvc --format=json
 */

const { parseArgs } = require('./utils');

// Import individual atoms
const atomDefines = require('./defines');
const atomCalls = require('./calls');
const atomImports = require('./imports');
const atomMutates = require('./mutates');
const atomParams = require('./params');
const atomReturns = require('./returns');
const atomDecorates = require('./decorates');
const atomInherits = require('./inherits');
const atomFiles = require('./files');
const atomExports = require('./exports');
const atomComplexity = require('./complexity');

// Parse arguments
const args = process.argv.slice(2);
const atom = args[0];
const { scanPath, format } = parseArgs(args);

// Help
function showHelp() {
    console.log(`
Atoms - Composable code analysis primitives

Usage:
  node framework/atoms/index.js <atom> [--path=dir] [--format=predicate|json|tsv]

Atoms:
  defines    DEFINES(file, name, type, line)
  calls      CALLS(file, caller, callee, line)
  imports    IMPORTS(file, module, symbol, alias, line)
  mutates    MUTATES(file, function, attribute, line)
  params     PARAMS(file, function, name, has_type, has_default, line)
  returns    RETURNS(file, function, has_value, line)
  decorates  DECORATES(file, decorator, target, line)
  inherits   INHERITS(file, child, parent, line)
  files      FILES(path, name, type, depth)
  exports    EXPORTS(file, symbol, line)
  complexity COMPLEXITY(file, func, cyclomatic, cognitive, lines, nesting, params)

Examples:
  node framework/atoms/index.js defines --path=rvc
  node framework/atoms/index.js calls --path=rvc | grep run_rvc
  node framework/atoms/index.js imports --format=tsv | sort | uniq -c
`);
}

// Dispatch
switch (atom) {
    case 'defines': atomDefines(scanPath, format); break;
    case 'calls': atomCalls(scanPath, format); break;
    case 'imports': atomImports(scanPath, format); break;
    case 'mutates': atomMutates(scanPath, format); break;
    case 'params': atomParams(scanPath, format); break;
    case 'returns': atomReturns(scanPath, format); break;
    case 'decorates': atomDecorates(scanPath, format); break;
    case 'inherits': atomInherits(scanPath, format); break;
    case 'files': atomFiles(scanPath, format); break;
    case 'exports': atomExports(scanPath, format); break;
    case 'complexity': atomComplexity(scanPath, format); break;
    default: showHelp();
}
