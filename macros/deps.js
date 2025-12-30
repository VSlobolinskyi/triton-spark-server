#!/usr/bin/env node
/**
 * deps.js - Dependency graph analysis with impact assessment
 *
 * Analyzes module dependencies to help with:
 *   - Understanding coupling between modules
 *   - Predicting impact of changes
 *   - Finding circular dependencies
 *   - Identifying highly-coupled "god" modules
 *
 * Usage:
 *   node deps.js [--path=dir]                    # Show full dependency graph
 *   node deps.js impact <module>                 # What depends on this module?
 *   node deps.js depends <module>                # What does this module depend on?
 *   node deps.js circular                        # Find circular dependencies
 *   node deps.js coupling                        # Show coupling metrics
 *   node deps.js layers                          # Suggest layer structure
 */

const fs = require('fs');
const path = require('path');

const args = process.argv.slice(2);
const command = args.find(a => !a.startsWith('--')) || 'graph';
const target = args.find((a, i) => i > 0 && !a.startsWith('--')) || null;
const getArg = (name, def) => {
    const arg = args.find(a => a.startsWith(`--${name}=`));
    return arg ? arg.split('=')[1] : def;
};

const targetPath = getArg('path', '.');

// Build module name from file path
function getModuleName(filePath, basePath) {
    const rel = path.relative(basePath, filePath);
    return rel
        .replace(/\.py$/, '')
        .replace(/[\\\/]/g, '.')
        .replace(/__init__$/, '')
        .replace(/\.$/, '');
}

// Parse imports from a file
function parseImports(filePath, basePath) {
    const content = fs.readFileSync(filePath, 'utf-8');
    const lines = content.split('\n');
    const imports = [];
    const moduleName = getModuleName(filePath, basePath);

    for (const line of lines) {
        // from X import Y
        const fromMatch = line.match(/^from\s+(\S+)\s+import\s+(.+)/);
        if (fromMatch) {
            let module = fromMatch[1];
            // Handle relative imports
            if (module.startsWith('.')) {
                const dots = module.match(/^\.+/)[0].length;
                const parts = moduleName.split('.');
                const base = parts.slice(0, parts.length - dots + 1).join('.');
                const rest = module.replace(/^\.+/, '');
                module = base + (rest ? '.' + rest : '');
            }
            imports.push({
                type: 'from',
                module: module,
                names: fromMatch[2].split(',').map(n => n.trim().split(' as ')[0].trim()),
            });
        }

        // import X
        const importMatch = line.match(/^import\s+(\S+)/);
        if (importMatch && !line.includes('from')) {
            imports.push({
                type: 'import',
                module: importMatch[1].split(' as ')[0],
                names: [importMatch[1].split(' as ')[0].split('.').pop()],
            });
        }
    }

    return imports;
}

// Collect all Python files
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

// Build dependency graph
function buildGraph(basePath) {
    const files = collectPythonFiles(basePath);
    const modules = new Map();  // module -> { file, imports, exports }
    const graph = new Map();     // module -> Set of modules it imports
    const reverseGraph = new Map();  // module -> Set of modules that import it

    // First pass: collect all modules
    for (const file of files) {
        const moduleName = getModuleName(file, basePath);
        if (moduleName) {
            modules.set(moduleName, { file, imports: [], dependsOn: new Set(), dependedBy: new Set() });
        }
    }

    // Second pass: parse imports
    for (const file of files) {
        const moduleName = getModuleName(file, basePath);
        if (!moduleName) continue;

        const imports = parseImports(file, basePath);
        const moduleData = modules.get(moduleName);
        moduleData.imports = imports;

        for (const imp of imports) {
            // Check if this is an internal module
            const importedModule = imp.module;

            // Try to find matching internal module
            for (const [name, _] of modules) {
                if (name === importedModule || importedModule.startsWith(name + '.') || name.startsWith(importedModule)) {
                    moduleData.dependsOn.add(name);

                    if (!reverseGraph.has(name)) {
                        reverseGraph.set(name, new Set());
                    }
                    reverseGraph.get(name).add(moduleName);
                }
            }
        }
    }

    // Update dependedBy
    for (const [mod, dependents] of reverseGraph) {
        if (modules.has(mod)) {
            modules.get(mod).dependedBy = dependents;
        }
    }

    return modules;
}

// Find circular dependencies
function findCircular(modules) {
    const visited = new Set();
    const recStack = new Set();
    const cycles = [];

    function dfs(module, path) {
        visited.add(module);
        recStack.add(module);

        const data = modules.get(module);
        if (data) {
            for (const dep of data.dependsOn) {
                if (!visited.has(dep)) {
                    const result = dfs(dep, [...path, dep]);
                    if (result) return result;
                } else if (recStack.has(dep)) {
                    // Found cycle
                    const cycleStart = path.indexOf(dep);
                    if (cycleStart !== -1) {
                        cycles.push(path.slice(cycleStart).concat([dep]));
                    } else {
                        cycles.push([...path, dep]);
                    }
                }
            }
        }

        recStack.delete(module);
        return null;
    }

    for (const [module, _] of modules) {
        if (!visited.has(module)) {
            dfs(module, [module]);
        }
    }

    return cycles;
}

// Calculate coupling metrics
function calculateCoupling(modules) {
    const metrics = [];

    for (const [name, data] of modules) {
        const afferent = data.dependedBy.size;   // Incoming (who depends on me)
        const efferent = data.dependsOn.size;    // Outgoing (who do I depend on)
        const instability = efferent / (afferent + efferent) || 0;

        metrics.push({
            module: name,
            afferent,
            efferent,
            instability: instability.toFixed(2),
            total: afferent + efferent,
        });
    }

    return metrics.sort((a, b) => b.total - a.total);
}

// Suggest layer structure
function suggestLayers(modules) {
    const layers = {
        core: [],      // No internal dependencies
        domain: [],    // Depends only on core
        services: [],  // Depends on domain/core
        interface: [], // Depends on everything, nothing depends on it
    };

    for (const [name, data] of modules) {
        const hasInternalDeps = data.dependsOn.size > 0;
        const hasDependents = data.dependedBy.size > 0;

        if (!hasInternalDeps && hasDependents) {
            layers.core.push(name);
        } else if (!hasDependents && hasInternalDeps) {
            layers.interface.push(name);
        } else if (hasInternalDeps && hasDependents) {
            // Check depth of dependencies
            let isService = false;
            for (const dep of data.dependsOn) {
                const depData = modules.get(dep);
                if (depData && depData.dependsOn.size > 0) {
                    isService = true;
                    break;
                }
            }
            if (isService) {
                layers.services.push(name);
            } else {
                layers.domain.push(name);
            }
        }
    }

    return layers;
}

// Print dependency tree
function printTree(modules, root, depth = 0, visited = new Set()) {
    if (depth > 5 || visited.has(root)) {
        if (visited.has(root)) console.log('  '.repeat(depth) + `↺ ${root} (circular)`);
        return;
    }
    visited.add(root);

    const data = modules.get(root);
    if (!data) return;

    const prefix = '  '.repeat(depth);
    const icon = depth === 0 ? '📦' : '├─';
    console.log(`${prefix}${icon} ${root}`);

    for (const dep of data.dependsOn) {
        printTree(modules, dep, depth + 1, new Set(visited));
    }
}

// Main command handlers
function main() {
    console.log('Dependency Analyzer');
    console.log('═'.repeat(60));

    const modules = buildGraph(targetPath);
    console.log(`Found ${modules.size} modules\n`);

    switch (command) {
        case 'graph':
            console.log('📊 DEPENDENCY GRAPH\n');
            for (const [name, data] of modules) {
                if (data.dependsOn.size > 0 || data.dependedBy.size > 0) {
                    const deps = [...data.dependsOn].join(', ') || '(none)';
                    console.log(`${name}`);
                    console.log(`  → imports: ${deps}`);
                    console.log(`  ← used by: ${[...data.dependedBy].join(', ') || '(none)'}`);
                    console.log();
                }
            }
            break;

        case 'impact':
            if (!target) {
                console.log('Usage: node deps.js impact <module>');
                return;
            }
            console.log(`🎯 IMPACT ANALYSIS: ${target}\n`);
            console.log('Modules that would be affected by changes:\n');

            // Find all modules that depend on target (transitively)
            const affected = new Set();
            function findAffected(mod) {
                const data = modules.get(mod);
                if (data) {
                    for (const dep of data.dependedBy) {
                        if (!affected.has(dep)) {
                            affected.add(dep);
                            findAffected(dep);
                        }
                    }
                }
            }

            // Find target module (partial match)
            for (const [name, _] of modules) {
                if (name.includes(target)) {
                    console.log(`📦 ${name}`);
                    findAffected(name);
                }
            }

            if (affected.size > 0) {
                console.log(`\nDirect + Transitive dependents (${affected.size}):`);
                for (const mod of affected) {
                    console.log(`  ⚠️  ${mod}`);
                }
            } else {
                console.log('\n✅ No internal modules depend on this.');
            }
            break;

        case 'depends':
            if (!target) {
                console.log('Usage: node deps.js depends <module>');
                return;
            }
            console.log(`📥 DEPENDENCIES OF: ${target}\n`);

            for (const [name, data] of modules) {
                if (name.includes(target)) {
                    console.log(`📦 ${name}`);
                    printTree(modules, name);
                    console.log();
                }
            }
            break;

        case 'circular':
            console.log('🔄 CIRCULAR DEPENDENCIES\n');
            const cycles = findCircular(modules);

            if (cycles.length === 0) {
                console.log('✅ No circular dependencies found!');
            } else {
                console.log(`Found ${cycles.length} cycle(s):\n`);
                for (const cycle of cycles) {
                    console.log(`  ↺ ${cycle.join(' → ')}`);
                }
            }
            break;

        case 'coupling':
            console.log('🔗 COUPLING METRICS\n');
            console.log('Module                                    In  Out  Inst  Total');
            console.log('─'.repeat(65));

            const metrics = calculateCoupling(modules);
            for (const m of metrics.slice(0, 20)) {
                const name = m.module.substring(0, 40).padEnd(40);
                const instBar = m.instability > 0.7 ? '🔴' : m.instability > 0.3 ? '🟡' : '🟢';
                console.log(`${name} ${String(m.afferent).padStart(3)}  ${String(m.efferent).padStart(3)}  ${instBar}${m.instability}   ${m.total}`);
            }

            console.log('\nInstability: 0=stable (many depend on it), 1=unstable (depends on many)');
            break;

        case 'layers':
            console.log('📐 SUGGESTED LAYER STRUCTURE\n');
            const layers = suggestLayers(modules);

            console.log('🔵 CORE (no internal dependencies, others depend on it):');
            for (const mod of layers.core) console.log(`   ${mod}`);

            console.log('\n🟢 DOMAIN (depends on core only):');
            for (const mod of layers.domain) console.log(`   ${mod}`);

            console.log('\n🟡 SERVICES (depends on domain/core):');
            for (const mod of layers.services) console.log(`   ${mod}`);

            console.log('\n🔴 INTERFACE (entry points, nothing depends on them):');
            for (const mod of layers.interface) console.log(`   ${mod}`);
            break;

        default:
            console.log(`Unknown command: ${command}`);
            console.log('Commands: graph, impact, depends, circular, coupling, layers');
    }
}

main();
