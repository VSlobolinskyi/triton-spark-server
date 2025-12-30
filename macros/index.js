#!/usr/bin/env node
/**
 * Macros - Project-specific code analysis tools
 *
 * Usage:
 *   node macros/index.js              # List available macros
 *   node macros/<macro>.js [args]     # Run a specific macro
 *
 * These macros are built on top of QuantumLogic framework.
 */

const fs = require('fs');
const path = require('path');

const macrosDir = __dirname;

// Categorize macros
const CATEGORIES = {
    'Structure': ['generate-structure', 'schema'],
    'Analysis': ['analyze', 'analyze-v2', 'complexity', 'deps', 'flow'],
    'Patterns': ['patterns', 'grpc-audit', 'api-docs', 'model-audit', 'worker-audit'],
    'Refactoring': ['replace', 'refactor'],
    'Schemas': ['schema-export', 'resource-audit'],
};

// Get all JS files
const macroFiles = fs.readdirSync(macrosDir)
    .filter(f => f.endsWith('.js') && f !== 'index.js')
    .map(f => f.replace('.js', ''));

console.log('═'.repeat(60));
console.log('Available Macros');
console.log('═'.repeat(60));

// Print by category
for (const [category, macros] of Object.entries(CATEGORIES)) {
    const available = macros.filter(m => macroFiles.includes(m));
    if (available.length > 0) {
        console.log(`\n${category}:`);
        for (const macro of available) {
            console.log(`  node macros/${macro}.js`);
        }
    }
}

// Print uncategorized
const categorized = Object.values(CATEGORIES).flat();
const uncategorized = macroFiles.filter(m => !categorized.includes(m));
if (uncategorized.length > 0) {
    console.log('\nOther:');
    for (const macro of uncategorized) {
        console.log(`  node macros/${macro}.js`);
    }
}

console.log('\n' + '─'.repeat(60));
console.log('Run any macro with --help for usage info');
console.log('═'.repeat(60));
