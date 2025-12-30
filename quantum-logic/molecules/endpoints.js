/**
 * Molecule: ENDPOINTS
 * Map HTTP routes to handlers with their call graphs
 */

const { runAtom, parsePredicates, printHeader } = require('./utils');

function endpoints(scanPath) {
    printHeader('HTTP Endpoints');

    const decorates = parsePredicates(runAtom('decorates', scanPath));
    const calls = parsePredicates(runAtom('calls', scanPath));

    // Find route decorators
    const routes = decorates.filter(d =>
        d.args[1].match(/^(app|router)\.(get|post|put|delete|patch)$/)
    );

    if (routes.length === 0) {
        console.log('  \x1b[90m(no HTTP endpoints found)\x1b[0m');
        return;
    }

    // Build call graph for each handler
    routes.forEach(route => {
        const method = route.args[1].split('.')[1].toUpperCase();
        const handler = route.args[2];
        const file = route.args[0];
        const line = route.args[3];

        const methodColor = {
            'GET': '\x1b[32m',
            'POST': '\x1b[34m',
            'PUT': '\x1b[33m',
            'DELETE': '\x1b[31m',
            'PATCH': '\x1b[35m'
        }[method] || '\x1b[0m';

        console.log(`\n${methodColor}${method.padEnd(6)}\x1b[0m \x1b[1m${handler}\x1b[0m`);
        console.log(`       \x1b[90m${file}:${line}\x1b[0m`);

        // Find what the handler calls
        const handlerCalls = calls.filter(c =>
            c.args[1] === handler || c.args[1].endsWith('.' + handler)
        ).map(c => c.args[2]);

        const uniqueCalls = [...new Set(handlerCalls)].filter(c =>
            !c.startsWith('self.') && !c.includes('.')
        ).slice(0, 5);

        if (uniqueCalls.length > 0) {
            console.log(`       → ${uniqueCalls.join(', ')}`);
        }
    });

    console.log(`\n\x1b[33mTotal: ${routes.length} endpoints\x1b[0m`);
}

module.exports = endpoints;
