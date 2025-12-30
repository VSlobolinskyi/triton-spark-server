#!/usr/bin/env node
/**
 * Molecules - Composed analysis patterns from atoms
 *
 * Molecules combine multiple atoms to answer higher-level questions.
 * They consume atom output and produce actionable insights.
 *
 * Usage:
 *   node framework/molecules/index.js <molecule> [--path=dir] [options]
 *
 * Molecules:
 *   dead-code      - Find defined symbols never called
 *   impact         - What depends on a given symbol
 *   endpoints      - Map HTTP routes to handlers with their dependencies
 *   side-effects   - Functions that mutate state outside __init__
 *   coupling       - Measure module interdependencies
 *   entry-points   - Find all external entry points (main, endpoints, CLI)
 *   orphans        - Files with no imports from rest of codebase
 *
 * Examples:
 *   node framework/molecules/index.js dead-code --path=rvc
 *   node framework/molecules/index.js impact run_rvc --path=rvc
 *   node framework/molecules/index.js endpoints --path=rvc
 */

const { parseArgs } = require('./utils');

// Import individual molecules
const deadCode = require('./dead-code');
const impact = require('./impact');
const endpoints = require('./endpoints');
const sideEffects = require('./side-effects');
const coupling = require('./coupling');
const entryPoints = require('./entry-points');
const orphans = require('./orphans');
const hierarchy = require('./hierarchy');
const circular = require('./circular');
const duplicates = require('./duplicates');
const patterns = require('./patterns');
const riskScore = require('./risk-score');
const apiSurface = require('./api-surface');
const hotspots = require('./hotspots');

// Parse arguments
const args = process.argv.slice(2);
const { molecule, target, scanPath } = parseArgs(args);

// Help
function showHelp() {
    console.log(`
Molecules - Composed analysis patterns

Usage:
  node framework/molecules/index.js <molecule> [target] [--path=dir]

Molecules:
  dead-code      Find defined symbols never called
  impact <sym>   What depends on a given symbol
  endpoints      Map HTTP routes to handlers
  side-effects   Functions that mutate state
  coupling       Measure module interdependencies
  entry-points   Find external entry points
  orphans        Files not imported anywhere
  hierarchy      File/class/method tree view
  circular       Find circular dependencies
  duplicates     Find duplicate code blocks
  patterns       Detect architectural patterns
  risk-score     Complexity × mutations risk ranking
  api-surface    Exported API complexity analysis
  hotspots       Multi-signal codebase hotspots

Examples:
  node framework/molecules/index.js dead-code --path=rvc
  node framework/molecules/index.js impact run_rvc --path=rvc
  node framework/molecules/index.js endpoints --path=rvc
  node framework/molecules/index.js side-effects --path=rvc
`);
}

// Dispatch
switch (molecule) {
    case 'dead-code': deadCode(scanPath); break;
    case 'impact': impact(target, scanPath); break;
    case 'endpoints': endpoints(scanPath); break;
    case 'side-effects': sideEffects(scanPath); break;
    case 'coupling': coupling(scanPath); break;
    case 'entry-points': entryPoints(scanPath); break;
    case 'orphans': orphans(scanPath); break;
    case 'hierarchy': hierarchy(scanPath); break;
    case 'circular': circular(scanPath); break;
    case 'duplicates': duplicates(scanPath); break;
    case 'patterns': patterns(scanPath); break;
    case 'risk-score': riskScore(scanPath); break;
    case 'api-surface': apiSurface(scanPath); break;
    case 'hotspots': hotspots(scanPath); break;
    default: showHelp();
}
