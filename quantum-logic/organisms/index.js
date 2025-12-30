#!/usr/bin/env node
/**
 * Organisms - High-level project analysis reports
 *
 * Organisms combine multiple molecules to produce comprehensive reports.
 * They answer strategic questions about the codebase.
 *
 * Usage:
 *   node framework/organisms/index.js <organism> [target] [--path=dir]
 *
 * Organisms:
 *   overview         - Complete codebase summary (structure, entry points, patterns)
 *   health           - Codebase health check (issues, complexity, score)
 *   refactor-plan    - Safe refactoring plan for a symbol
 *
 * Examples:
 *   node framework/organisms/index.js overview --path=rvc
 *   node framework/organisms/index.js health --path=rvc
 *   node framework/organisms/index.js refactor-plan TTSRVCPipeline --path=rvc
 */

const { parseArgs } = require('./utils');

// Import individual organisms
const overview = require('./overview');
const health = require('./health');
const refactorPlan = require('./refactor-plan');

// Parse arguments
const args = process.argv.slice(2);
const { organism, target, scanPath } = parseArgs(args);

// Help
function showHelp() {
    console.log(`
Organisms - High-level project analysis reports

Usage:
  node framework/organisms/index.js <organism> [target] [--path=dir]

Organisms:
  overview         Complete codebase summary
  health           Codebase health check with score
  refactor-plan    Safe refactoring plan for a symbol

Examples:
  node framework/organisms/index.js overview --path=rvc
  node framework/organisms/index.js health --path=rvc
  node framework/organisms/index.js refactor-plan TTSRVCPipeline --path=rvc
`);
}

// Dispatch
switch (organism) {
    case 'overview': overview(scanPath); break;
    case 'health': health(scanPath); break;
    case 'refactor-plan': refactorPlan(target, scanPath); break;
    default: showHelp();
}
