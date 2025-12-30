/**
 * Atom: COMPLEXITY
 * COMPLEXITY(file, function, cyclomatic, cognitive, lines, nesting, params)
 * Extracts complexity metrics for each function
 */

const fs = require('fs');
const { collectPythonFiles, createEmitter } = require('./utils');

// Complexity patterns
const PATTERNS = {
    if: /^\s*(?:if|elif)\s+/,
    for: /^\s*for\s+/,
    while: /^\s*while\s+/,
    except: /^\s*except/,
    andOr: /\s+(and|or)\s+/g,
    ternary: /\sif\s+.+\s+else\s+/,
    comprehension: /\[.+\s+for\s+.+\s+in\s+/,
    lambda: /lambda\s+/g,
    function: /^(\s*)(?:async\s+)?def\s+(\w+)\s*\(([^)]*)\)/,
    class: /^(\s*)class\s+(\w+)/,
};

function analyzeFunction(lines, startLine, indent) {
    const metrics = {
        lines: 0,
        cyclomatic: 1,
        cognitive: 0,
        maxNesting: 0,
        params: 0,
    };

    let currentNesting = 0;
    let i = startLine;

    while (i < lines.length) {
        const line = lines[i];
        const lineIndent = line.match(/^(\s*)/)[1].length;

        // Exit if we've dedented past the function
        if (i > startLine && lineIndent <= indent && line.trim() !== '') {
            break;
        }

        metrics.lines++;

        // Track nesting depth
        const relativeIndent = Math.floor((lineIndent - indent) / 4);
        currentNesting = Math.max(0, relativeIndent);
        metrics.maxNesting = Math.max(metrics.maxNesting, currentNesting);

        // Cyclomatic complexity
        if (PATTERNS.if.test(line)) {
            metrics.cyclomatic++;
            metrics.cognitive += 1 + currentNesting;
        }
        if (PATTERNS.for.test(line) || PATTERNS.while.test(line)) {
            metrics.cyclomatic++;
            metrics.cognitive += 1 + currentNesting;
        }
        if (PATTERNS.except.test(line)) {
            metrics.cyclomatic++;
        }

        // Boolean operators
        const andOrMatches = line.match(PATTERNS.andOr);
        if (andOrMatches) {
            metrics.cyclomatic += andOrMatches.length;
            metrics.cognitive += andOrMatches.length;
        }

        // Ternary
        if (PATTERNS.ternary.test(line)) {
            metrics.cyclomatic++;
            metrics.cognitive += 2;
        }

        // Comprehensions
        if (PATTERNS.comprehension.test(line)) {
            metrics.cognitive += 2;
        }

        // Lambdas
        const lambdaMatches = line.match(PATTERNS.lambda);
        if (lambdaMatches) {
            metrics.cognitive += lambdaMatches.length;
        }

        i++;
    }

    return metrics;
}

function atomComplexity(scanPath, format) {
    const emit = createEmitter(format);
    const files = collectPythonFiles(scanPath);

    files.forEach(file => {
        const content = fs.readFileSync(file, 'utf-8');
        const lines = content.split('\n');

        let currentClass = null;
        let classIndent = 0;

        for (let i = 0; i < lines.length; i++) {
            const line = lines[i];

            // Track current class
            const classMatch = line.match(PATTERNS.class);
            if (classMatch && classMatch[1].length === 0) {
                currentClass = classMatch[2];
                classIndent = 0;
            }

            // Find function definitions
            const funcMatch = line.match(PATTERNS.function);
            if (funcMatch) {
                const indent = funcMatch[1].length;
                const name = funcMatch[2];
                const params = funcMatch[3];

                // Full name with class prefix
                const fullName = (indent > 0 && currentClass)
                    ? `${currentClass}.${name}`
                    : name;

                // Count parameters (excluding self, cls, and those with defaults)
                const paramCount = params.trim() === '' ? 0 :
                    params.split(',')
                        .map(p => p.trim())
                        .filter(p => p && p !== 'self' && p !== 'cls')
                        .length;

                const metrics = analyzeFunction(lines, i, indent);
                metrics.params = paramCount;

                emit('COMPLEXITY', [
                    file,
                    fullName,
                    metrics.cyclomatic,
                    metrics.cognitive,
                    metrics.lines,
                    metrics.maxNesting,
                    metrics.params
                ]);

                // Reset class if top-level function
                if (indent === 0) {
                    currentClass = null;
                }
            }
        }
    });
}

module.exports = atomComplexity;
