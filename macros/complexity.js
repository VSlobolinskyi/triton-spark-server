#!/usr/bin/env node
/**
 * complexity.js - Identify complexity hotspots in Python codebase
 *
 * Metrics:
 *   - Cyclomatic complexity (branches, loops, conditions)
 *   - Cognitive complexity (nesting depth, breaks in flow)
 *   - Function length
 *   - Parameter count
 *   - Coupling (imports, calls to other modules)
 *
 * Usage:
 *   node complexity.js [--path=dir] [--threshold=10] [--top=20]
 *   node complexity.js --file=path/to/file.py
 *   node complexity.js --function=submit_job
 */

const fs = require('fs');
const path = require('path');

const args = process.argv.slice(2);
const getArg = (name, def) => {
    const arg = args.find(a => a.startsWith(`--${name}=`));
    return arg ? arg.split('=')[1] : def;
};

const targetPath = getArg('path', '.');
const targetFile = getArg('file', null);
const targetFunction = getArg('function', null);
const threshold = parseInt(getArg('threshold', '10'));
const topN = parseInt(getArg('top', '20'));

// Complexity patterns
const PATTERNS = {
    // Control flow (cyclomatic)
    if: /^\s*(?:if|elif)\s+/,
    else: /^\s*else\s*:/,
    for: /^\s*for\s+/,
    while: /^\s*while\s+/,
    try: /^\s*try\s*:/,
    except: /^\s*except/,
    with: /^\s*(?:async\s+)?with\s+/,

    // Boolean operators add paths
    andOr: /\s+(and|or)\s+/g,
    ternary: /\sif\s+.+\s+else\s+/,

    // Comprehensions (hidden complexity)
    comprehension: /\[.+\s+for\s+.+\s+in\s+/,

    // Cognitive complexity (nesting, jumps)
    return: /^\s*return\s+/,
    break: /^\s*break\s*$/,
    continue: /^\s*continue\s*$/,
    raise: /^\s*raise\s+/,

    // Function/class definitions
    function: /^(\s*)(?:async\s+)?def\s+(\w+)\s*\((.*?)\)(?:\s*->\s*(.+?))?:/,
    class: /^(\s*)class\s+(\w+)/,

    // Lambda (inline complexity)
    lambda: /lambda\s+/g,
};

function collectPythonFiles(dir, maxDepth = 10, depth = 0) {
    if (depth > maxDepth) return [];
    const files = [];
    try {
        const entries = fs.readdirSync(dir, { withFileTypes: true });
        for (const entry of entries) {
            const fullPath = path.join(dir, entry.name);
            if (entry.name.startsWith('.') || entry.name === '__pycache__' ||
                entry.name === 'node_modules' || entry.name === 'venv') continue;
            if (entry.isDirectory()) {
                files.push(...collectPythonFiles(fullPath, maxDepth, depth + 1));
            } else if (entry.name.endsWith('.py')) {
                files.push(fullPath);
            }
        }
    } catch (e) { }
    return files;
}

function analyzeFunction(lines, startLine, indent) {
    const metrics = {
        lines: 0,
        cyclomatic: 1,  // Base complexity
        cognitive: 0,
        maxNesting: 0,
        params: 0,
        returns: 0,
        branches: 0,
        loops: 0,
        exceptions: 0,
        lambdas: 0,
        comprehensions: 0,
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
            metrics.branches++;
            metrics.cognitive += 1 + currentNesting;  // Nesting penalty
        }
        if (PATTERNS.for.test(line) || PATTERNS.while.test(line)) {
            metrics.cyclomatic++;
            metrics.loops++;
            metrics.cognitive += 1 + currentNesting;
        }
        if (PATTERNS.except.test(line)) {
            metrics.cyclomatic++;
            metrics.exceptions++;
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
            metrics.cognitive += 2;  // Inline conditionals are harder to read
        }

        // Comprehensions
        if (PATTERNS.comprehension.test(line)) {
            metrics.comprehensions++;
            metrics.cognitive += 2;
        }

        // Jumps (break flow)
        if (PATTERNS.return.test(line)) metrics.returns++;
        if (PATTERNS.break.test(line) || PATTERNS.continue.test(line)) {
            metrics.cognitive += 2;  // Jumps break mental model
        }
        if (PATTERNS.raise.test(line)) {
            metrics.cognitive++;
        }

        // Lambdas
        const lambdaMatches = line.match(PATTERNS.lambda);
        if (lambdaMatches) {
            metrics.lambdas += lambdaMatches.length;
            metrics.cognitive += lambdaMatches.length;
        }

        i++;
    }

    return metrics;
}

function analyzeFile(filePath) {
    const content = fs.readFileSync(filePath, 'utf-8');
    const lines = content.split('\n');
    const functions = [];

    let currentClass = null;

    for (let i = 0; i < lines.length; i++) {
        const line = lines[i];

        // Track current class
        const classMatch = line.match(PATTERNS.class);
        if (classMatch && classMatch[1].length === 0) {
            currentClass = classMatch[2];
        }

        // Find function definitions
        const funcMatch = line.match(PATTERNS.function);
        if (funcMatch) {
            const indent = funcMatch[1].length;
            const name = funcMatch[2];
            const params = funcMatch[3];
            const returnType = funcMatch[4];

            // Count parameters
            const paramCount = params.trim() === '' ? 0 :
                params.split(',').filter(p => !p.includes('=')).length;

            const metrics = analyzeFunction(lines, i, indent);
            metrics.params = paramCount;

            // Calculate total complexity score
            const score = metrics.cyclomatic +
                         Math.floor(metrics.cognitive / 2) +
                         Math.floor(metrics.lines / 20) +
                         Math.max(0, metrics.params - 4) +
                         Math.max(0, metrics.maxNesting - 3) * 2;

            functions.push({
                file: filePath,
                class: indent > 0 ? currentClass : null,
                name: name,
                fullName: indent > 0 && currentClass ? `${currentClass}.${name}` : name,
                line: i + 1,
                params: paramCount,
                returnType: returnType,
                metrics: metrics,
                score: score,
            });

            // Reset class if this was a top-level function
            if (indent === 0) {
                currentClass = null;
            }
        }
    }

    return functions;
}

function formatMetrics(func) {
    const m = func.metrics;
    return [
        `cyc:${m.cyclomatic}`,
        `cog:${m.cognitive}`,
        `lines:${m.lines}`,
        `nest:${m.maxNesting}`,
        `params:${m.params}`,
    ].join(' ');
}

function printComplexityBar(score, maxScore = 50) {
    const width = 20;
    const filled = Math.min(width, Math.round((score / maxScore) * width));
    const bar = '█'.repeat(filled) + '░'.repeat(width - filled);

    let color = '';
    if (score >= 30) color = '🔴';
    else if (score >= 20) color = '🟠';
    else if (score >= 10) color = '🟡';
    else color = '🟢';

    return `${color} [${bar}] ${score}`;
}

function main() {
    console.log('Complexity Analyzer');
    console.log('═'.repeat(60));

    let files;
    if (targetFile) {
        files = [targetFile];
    } else {
        files = collectPythonFiles(targetPath);
    }

    console.log(`Analyzing ${files.length} files...\n`);

    let allFunctions = [];

    for (const file of files) {
        const functions = analyzeFile(file);
        allFunctions = allFunctions.concat(functions);
    }

    // Filter by function name if specified
    if (targetFunction) {
        allFunctions = allFunctions.filter(f =>
            f.name === targetFunction || f.fullName === targetFunction
        );
    }

    // Sort by score
    allFunctions.sort((a, b) => b.score - a.score);

    // Summary stats
    const totalFunctions = allFunctions.length;
    const complexFunctions = allFunctions.filter(f => f.score >= threshold);
    const avgScore = allFunctions.reduce((sum, f) => sum + f.score, 0) / totalFunctions || 0;

    console.log('📊 SUMMARY');
    console.log('─'.repeat(40));
    console.log(`Total functions: ${totalFunctions}`);
    console.log(`Average complexity: ${avgScore.toFixed(1)}`);
    console.log(`Above threshold (${threshold}): ${complexFunctions.length}`);

    // Hotspots
    console.log(`\n🔥 TOP ${topN} COMPLEXITY HOTSPOTS`);
    console.log('─'.repeat(60));

    const topFunctions = allFunctions.slice(0, topN);

    for (const func of topFunctions) {
        const relPath = path.relative(process.cwd(), func.file);
        console.log(`\n${printComplexityBar(func.score)}`);
        console.log(`   ${func.fullName}() at ${relPath}:${func.line}`);
        console.log(`   ${formatMetrics(func)}`);

        // Specific issues
        const issues = [];
        if (func.metrics.cyclomatic > 10) issues.push('high branching');
        if (func.metrics.maxNesting > 4) issues.push('deep nesting');
        if (func.metrics.lines > 50) issues.push('too long');
        if (func.metrics.params > 6) issues.push('too many params');
        if (func.metrics.cognitive > 15) issues.push('hard to understand');
        if (func.metrics.returns > 3) issues.push('multiple returns');

        if (issues.length > 0) {
            console.log(`   ⚠️  ${issues.join(', ')}`);
        }
    }

    // File-level summary
    console.log(`\n\n📁 COMPLEXITY BY FILE`);
    console.log('─'.repeat(60));

    const byFile = {};
    for (const func of allFunctions) {
        const relPath = path.relative(process.cwd(), func.file);
        if (!byFile[relPath]) {
            byFile[relPath] = { functions: 0, totalScore: 0, maxScore: 0 };
        }
        byFile[relPath].functions++;
        byFile[relPath].totalScore += func.score;
        byFile[relPath].maxScore = Math.max(byFile[relPath].maxScore, func.score);
    }

    const fileStats = Object.entries(byFile)
        .map(([file, stats]) => ({
            file,
            ...stats,
            avgScore: stats.totalScore / stats.functions,
        }))
        .sort((a, b) => b.avgScore - a.avgScore)
        .slice(0, 10);

    for (const stat of fileStats) {
        const bar = printComplexityBar(Math.round(stat.avgScore));
        console.log(`${bar}  ${stat.file}`);
        console.log(`        ${stat.functions} funcs, max: ${stat.maxScore}`);
    }

    // Suggestions
    if (complexFunctions.length > 0) {
        console.log(`\n\n💡 REFACTORING SUGGESTIONS`);
        console.log('─'.repeat(60));

        const worst = complexFunctions[0];
        console.log(`\nPriority target: ${worst.fullName}() (score: ${worst.score})`);
        console.log(`Location: ${path.relative(process.cwd(), worst.file)}:${worst.line}`);

        const m = worst.metrics;
        if (m.lines > 50) {
            console.log(`• Extract ${Math.ceil(m.lines / 30)} smaller functions`);
        }
        if (m.maxNesting > 4) {
            console.log(`• Use early returns to reduce nesting`);
        }
        if (m.params > 6) {
            console.log(`• Group parameters into a config object/dataclass`);
        }
        if (m.branches > 5) {
            console.log(`• Consider strategy pattern or dispatch table`);
        }
        if (m.comprehensions > 2) {
            console.log(`• Extract complex comprehensions to named functions`);
        }
    }
}

main();
