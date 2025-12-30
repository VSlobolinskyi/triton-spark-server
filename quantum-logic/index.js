/**
 * QuantumLogic - Main entry point for macro consumption
 *
 * Usage in macros:
 *   const ql = require('./quantum-logic');
 *   const defines = ql.atom('defines', 'src');
 *   const hotspots = ql.molecule('hotspots', 'src');
 *   const health = ql.organism('health', 'src');
 */

const { execSync } = require('child_process');
const path = require('path');

const QUANTUM_LOGIC_PATH = __dirname;

/**
 * Run an atom and return parsed predicates
 * @param {string} atom - Atom name (defines, calls, imports, etc.)
 * @param {string} scanPath - Path to scan
 * @param {object} options - Optional settings
 * @returns {Array} Array of {predicate, args} objects
 */
function atom(atomName, scanPath = '.', options = {}) {
    const atomsPath = path.join(QUANTUM_LOGIC_PATH, 'atoms', 'index.js');
    const format = options.format || 'predicate';

    try {
        const output = execSync(
            `node "${atomsPath}" ${atomName} --path=${scanPath} --format=${format}`,
            { encoding: 'utf8', maxBuffer: 50 * 1024 * 1024 }
        );

        if (format === 'json') {
            return JSON.parse(output);
        }

        // Parse predicate format
        return output
            .split('\n')
            .filter(line => line.startsWith(atomName.toUpperCase()))
            .map(line => {
                const match = line.match(/^(\w+)\((.*)\)$/);
                if (!match) return null;
                const args = match[2].split(',').map(s => s.trim());
                return { predicate: match[1], args };
            })
            .filter(Boolean);
    } catch (e) {
        console.error(`QuantumLogic atom error: ${e.message}`);
        return [];
    }
}

/**
 * Run a molecule and return output
 * @param {string} moleculeName - Molecule name
 * @param {string} scanPath - Path to scan
 * @param {string} target - Optional target symbol
 * @returns {string} Molecule output
 */
function molecule(moleculeName, scanPath = '.', target = null) {
    const moleculesPath = path.join(QUANTUM_LOGIC_PATH, 'molecules', 'index.js');
    const targetArg = target ? ` ${target}` : '';

    try {
        return execSync(
            `node "${moleculesPath}" ${moleculeName}${targetArg} --path=${scanPath}`,
            { encoding: 'utf8', maxBuffer: 50 * 1024 * 1024 }
        );
    } catch (e) {
        console.error(`QuantumLogic molecule error: ${e.message}`);
        return '';
    }
}

/**
 * Run an organism and return output
 * @param {string} organismName - Organism name
 * @param {string} scanPath - Path to scan
 * @param {string} target - Optional target symbol
 * @returns {string} Organism output
 */
function organism(organismName, scanPath = '.', target = null) {
    const organismsPath = path.join(QUANTUM_LOGIC_PATH, 'organisms', 'index.js');
    const targetArg = target ? ` ${target}` : '';

    try {
        return execSync(
            `node "${organismsPath}" ${organismName}${targetArg} --path=${scanPath}`,
            { encoding: 'utf8', maxBuffer: 50 * 1024 * 1024 }
        );
    } catch (e) {
        console.error(`QuantumLogic organism error: ${e.message}`);
        return '';
    }
}

/**
 * Parse predicate lines into structured data
 * @param {string} output - Raw predicate output
 * @returns {Array} Parsed predicates
 */
function parsePredicates(output) {
    return output
        .split('\n')
        .filter(line => line.match(/^\w+\(/))
        .map(line => {
            const match = line.match(/^(\w+)\((.*)\)$/);
            if (!match) return null;
            const args = match[2].split(',').map(s => s.trim());
            return { predicate: match[1], args };
        })
        .filter(Boolean);
}

/**
 * Chain multiple atoms and combine results
 * @param {Array} atomSpecs - Array of {atom, scanPath} objects
 * @returns {object} Map of atom name to results
 */
function chain(...atomSpecs) {
    const results = {};
    for (const spec of atomSpecs) {
        const { name, scanPath = '.', options = {} } = typeof spec === 'string'
            ? { name: spec }
            : spec;
        results[name] = atom(name, scanPath, options);
    }
    return results;
}

/**
 * Find predicates matching a filter
 * @param {Array} predicates - Parsed predicates
 * @param {object} filter - Filter criteria
 * @returns {Array} Matching predicates
 */
function filter(predicates, criteria) {
    return predicates.filter(p => {
        for (const [key, value] of Object.entries(criteria)) {
            if (key === 'predicate' && p.predicate !== value) return false;
            if (typeof key === 'number' && p.args[key] !== value) return false;
            if (key === 'file' && p.args[0] !== value) return false;
            if (key === 'name' && !p.args[1]?.includes(value)) return false;
            if (key === 'contains' && !p.args.some(a => a.includes(value))) return false;
        }
        return true;
    });
}

/**
 * Group predicates by a field
 * @param {Array} predicates - Parsed predicates
 * @param {number|string} field - Field index or 'file'
 * @returns {object} Grouped predicates
 */
function groupBy(predicates, field) {
    const idx = field === 'file' ? 0 : field;
    const groups = {};
    for (const p of predicates) {
        const key = p.args[idx];
        if (!groups[key]) groups[key] = [];
        groups[key].push(p);
    }
    return groups;
}

// Export all functions
module.exports = {
    atom,
    molecule,
    organism,
    parsePredicates,
    chain,
    filter,
    groupBy,
    QUANTUM_LOGIC_PATH,
};
