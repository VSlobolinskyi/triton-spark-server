/**
 * Molecule: HIERARCHY
 * Display file/class/method hierarchy in tree format
 */

const { runAtom, parsePredicates, printHeader, printSection } = require('./utils');

function hierarchy(scanPath) {
    printHeader('Code Hierarchy');

    const defines = parsePredicates(runAtom('defines', scanPath));
    const inherits = parsePredicates(runAtom('inherits', scanPath));

    // Build hierarchy tree
    const tree = {};

    // Group by file
    defines.forEach(d => {
        const file = d.args[0];
        const name = d.args[1];
        const type = d.args[2];
        const line = d.args[3];

        if (!tree[file]) {
            tree[file] = { classes: {}, functions: [] };
        }

        if (type === 'class') {
            tree[file].classes[name] = { methods: [], line };
        } else if (type === 'method' || type === 'async_method') {
            // name is "ClassName.methodName"
            const [className, methodName] = name.split('.');
            if (tree[file].classes[className]) {
                tree[file].classes[className].methods.push({ name: methodName, type, line });
            }
        } else if (type === 'function' || type === 'async_function') {
            tree[file].functions.push({ name, type, line });
        }
    });

    // Build inheritance map
    const parentMap = {};
    inherits.forEach(i => {
        const child = i.args[1];
        const parent = i.args[2];
        if (!parentMap[child]) parentMap[child] = [];
        parentMap[child].push(parent);
    });

    // Print tree
    const files = Object.keys(tree).sort();

    for (const file of files) {
        const data = tree[file];
        const hasContent = Object.keys(data.classes).length > 0 || data.functions.length > 0;
        if (!hasContent) continue;

        console.log(`\n\x1b[36m📄 ${file}\x1b[0m`);

        // Print classes
        const classes = Object.entries(data.classes).sort((a, b) => a[1].line - b[1].line);
        for (const [className, classData] of classes) {
            const parents = parentMap[className];
            const inheritance = parents ? `\x1b[90m(${parents.join(', ')})\x1b[0m` : '';
            console.log(`   \x1b[33m◆ ${className}\x1b[0m ${inheritance}`);

            // Group methods
            const publicMethods = classData.methods.filter(m => !m.name.startsWith('_'));
            const privateMethods = classData.methods.filter(m => m.name.startsWith('_') && !m.name.startsWith('__'));
            const magicMethods = classData.methods.filter(m => m.name.startsWith('__'));

            if (magicMethods.length > 0) {
                const names = magicMethods.map(m => m.name).join(', ');
                console.log(`      \x1b[90m├─ magic: ${names}\x1b[0m`);
            }
            if (publicMethods.length > 0) {
                for (const m of publicMethods) {
                    const asyncMark = m.type.includes('async') ? '\x1b[35masync \x1b[0m' : '';
                    console.log(`      ├─ ${asyncMark}${m.name}()`);
                }
            }
            if (privateMethods.length > 0) {
                const names = privateMethods.map(m => m.name).join(', ');
                console.log(`      \x1b[90m└─ private: ${names}\x1b[0m`);
            }
        }

        // Print module-level functions
        if (data.functions.length > 0) {
            const funcs = data.functions.sort((a, b) => a.line - b.line);
            for (const f of funcs) {
                const asyncMark = f.type.includes('async') ? '\x1b[35masync \x1b[0m' : '';
                console.log(`   \x1b[32m○ ${asyncMark}${f.name}()\x1b[0m`);
            }
        }
    }

    // Summary
    const totalClasses = defines.filter(d => d.args[2] === 'class').length;
    const totalFunctions = defines.filter(d => d.args[2].includes('function')).length;
    const totalMethods = defines.filter(d => d.args[2].includes('method')).length;

    console.log(`\n\x1b[90m${'─'.repeat(40)}\x1b[0m`);
    console.log(`\x1b[33mTotal: ${files.length} files, ${totalClasses} classes, ${totalFunctions} functions, ${totalMethods} methods\x1b[0m`);
}

module.exports = hierarchy;
