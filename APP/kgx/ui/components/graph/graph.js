/**
 * Graph component — 3D force-directed knowledge graph.
 *
 * Self-contained: receives eventBus and apiClient, emits/listens on the bus.
 * Never imports other UI components.
 *
 * Incoming events:
 *   graph:refresh     — re-fetch all data from API
 *   node:hide         {id}       — hide node from current view
 *   node:show-all     {}         — restore all hidden nodes
 *   node:highlight    {ids}      — pulse/color highlight a set of nodes
 *   node:focus        {id}       — pan camera to node
 *   edge:filter       {rel_type, visible} — show/hide edge type
 *   layout:change     {layout}   — switch layout engine
 *   db:changed        {}         — reload graph data
 *
 * Outgoing events:
 *   graph:loaded      {nodeCount, edgeCount}
 *   node:selected     {id, type, name}
 *   node:right-clicked {id, type, name, x, y}
 */

// Color palette for entity types (auto-assigned for unknown types)
const TYPE_COLORS = [
    '#4e9af1', // blue
    '#f1a34e', // orange
    '#4ef17a', // green
    '#f14e4e', // red
    '#c34ef1', // purple
    '#f1e24e', // yellow
    '#4ef1e8', // cyan
    '#f14eb5', // pink
];

const REL_COLORS = {
    default: '#555566',
};

export function initGraph(container, eventBus, apiClient) {
    let graphInstance = null;
    let allNodes = [];
    let allEdges = [];
    let hiddenNodeIds = new Set();
    let hiddenRelTypes = new Set();
    let highlightedIds = new Set();
    // SQL filter sets: filter_id → Set<node_id>
    let filterSets = new Map();
    // Nodes force-shown via "Expand neighbors" — overrides all filters
    let forceShownIds = new Set();
    let typeColorMap = {};
    let colorIndex = 0;

    function getTypeColor(type) {
        if (!typeColorMap[type]) {
            typeColorMap[type] = TYPE_COLORS[colorIndex % TYPE_COLORS.length];
            colorIndex++;
        }
        return typeColorMap[type];
    }

    function computeDegrees(nodes, edges) {
        const deg = {};
        for (const n of nodes) deg[n.id] = 0;
        for (const e of edges) {
            if (e.source in deg) deg[e.source]++;
            if (e.target in deg) deg[e.target]++;
        }
        return deg;
    }

    // ---------- Visibility ----------
    // We toggle __hidden flags on node/link objects, then pass a NEW function
    // reference to nodeVisibility/linkVisibility to force the library to
    // re-evaluate.  This only triggers a render refresh — NOT a simulation
    // restart — so positions stay stable.

    function refreshVisibility() {
        if (!graphInstance) return;
        // New arrow functions = new references → library detects the change
        graphInstance
            .nodeVisibility(n => !n.__hidden)
            .linkVisibility(l => !l.__hidden);
    }

    function recomputeHiddenFlags() {
        // Build: nodeId → set of rel_types it participates in
        const nodeRelTypes = {};
        for (const e of allEdges) {
            const src = typeof e.source === 'object' ? e.source.id : e.source;
            const tgt = typeof e.target === 'object' ? e.target.id : e.target;
            (nodeRelTypes[src] = nodeRelTypes[src] || new Set()).add(e.rel_type);
            (nodeRelTypes[tgt] = nodeRelTypes[tgt] || new Set()).add(e.rel_type);
        }

        // Merge all filter sets into one lookup
        const filteredIds = filterSets.size > 0
            ? new Set([...filterSets.values()].flatMap(s => [...s]))
            : null;

        // Mark nodes
        for (const n of allNodes) {
            // Force-shown nodes (from Expand neighbors) override all filters
            if (forceShownIds.has(n.id)) {
                n.__hidden = false;
                continue;
            }
            if (hiddenNodeIds.has(n.id) || (filteredIds && filteredIds.has(n.id))) {
                n.__hidden = true;
                continue;
            }
            // If the node has edges and ALL of them are of hidden rel types → hide it
            const rels = nodeRelTypes[n.id];
            if (rels && rels.size > 0 && hiddenRelTypes.size > 0) {
                n.__hidden = [...rels].every(rt => hiddenRelTypes.has(rt));
            } else {
                n.__hidden = false;
            }
        }

        // Build node hidden lookup for link visibility
        const nodeHidden = {};
        for (const n of allNodes) nodeHidden[n.id] = n.__hidden;

        // Mark links — force-show links where both endpoints are visible
        for (const e of allEdges) {
            const src = typeof e.source === 'object' ? e.source.id : e.source;
            const tgt = typeof e.target === 'object' ? e.target.id : e.target;
            if (forceShownIds.has(src) || forceShownIds.has(tgt)) {
                // Show link only if neither endpoint ended up hidden
                e.__hidden = !!nodeHidden[src] || !!nodeHidden[tgt];
            } else {
                e.__hidden = hiddenRelTypes.has(e.rel_type)
                    || hiddenNodeIds.has(src)
                    || hiddenNodeIds.has(tgt)
                    || (filteredIds && (filteredIds.has(src) || filteredIds.has(tgt)));
            }
        }
    }

    // ---------- Data loading ----------

    async function loadGraph() {
        try {
            const data = await apiClient.get('/api/graph');
            const rawEdges = data.edges.map(e => ({
                source: e.source,
                target: e.target,
                rel_type: e.rel_type,
            }));
            const deg = computeDegrees(data.nodes, rawEdges);
            allNodes = data.nodes.map(n => ({
                ...n,
                _group: n.group || n.type,  // 'person (stub)' vs 'person' vs 'signal' etc.
                _color: getTypeColor(n.group || n.type),
                _degree: deg[n.id] || 0,
                __hidden: false,
            }));
            allEdges = rawEdges.map(e => ({ ...e, __hidden: false }));

            // Do NOT clear hiddenRelTypes here — preserve the user's filter state.
            // Recompute hidden flags so existing filters apply to the new data.
            recomputeHiddenFlags();
        refreshVisibility();

            graphInstance.graphData({ nodes: allNodes, links: allEdges });
            eventBus.emit('graph:loaded', {
                nodeCount: allNodes.length,
                edgeCount: allEdges.length,
                typeColors: { ...typeColorMap },
            });
        } catch (err) {
            console.error('Failed to load graph:', err);
            container.innerHTML = `<div class="graph-error">Failed to load graph: ${err.message}</div>`;
        }
    }

    // ---------- Text labels ----------
    // THREE is bundled inside 3d-force-graph but not exported as a global.
    // We skip custom sprite labels entirely — use the built-in nodeLabel tooltip
    // and nodeVal for sizing. Labels via THREE sprites require the THREE global.
    let showLabels = true;

    // ---------- Force graph init ----------

    function initForceGraph() {
        graphInstance = ForceGraph3D()(container)
            .width(container.clientWidth)
            .height(container.clientHeight)
            .backgroundColor('#0f0f1a')
            .onDagError(() => {}) // graph has cycles — suppress error, best-effort layout
            .nodeId('id')
            .nodeLabel(n => `${n.name} (${n._group || n.type})`)
            .nodeColor(n => highlightedIds.size > 0
                ? (highlightedIds.has(n.id) ? '#ffffff' : n._color + '44')
                : n._color
            )
            .nodeOpacity(0.9)
            .nodeVal(n => Math.max(1, Math.sqrt(n._degree || 1)) * 2)
            .nodeRelSize(4)
            // Visibility — initial callbacks; refreshVisibility() re-sets them to trigger updates
            .nodeVisibility(n => !n.__hidden)
            .linkVisibility(l => !l.__hidden)
            .linkColor(l => REL_COLORS[l.rel_type] || REL_COLORS.default)
            .linkOpacity(0.4)
            .linkWidth(0.5)
            .linkDirectionalParticles(1)
            .linkDirectionalParticleWidth(l => highlightedIds.size > 0 ? 0 : 1)
            .onNodeClick(node => {
                eventBus.emit('node:selected', { id: node.id, type: node.type, name: node.name });
            })
            .onNodeRightClick((node, event) => {
                event.preventDefault();
                eventBus.emit('node:right-clicked', {
                    id: node.id, type: node.type, name: node.name,
                    x: event.clientX, y: event.clientY,
                });
            })
            .onBackgroundClick(() => {
                if (highlightedIds.size > 0) {
                    highlightedIds.clear();
                    graphInstance.nodeColor(n => n._color);
                    eventBus.emit('node:highlight-cleared', {});
                }
            });

        // Disable damping/inertia so mouse release stops immediately.
        // 3d-force-graph uses TrackballControls (staticMoving) not OrbitControls (enableDamping).
        setTimeout(() => {
            const controls = graphInstance.controls();
            if (controls) {
                // TrackballControls: staticMoving=true means no inertia
                controls.staticMoving = true;
                controls.dynamicDampingFactor = 1.0; // instant stop if staticMoving ignored
                // OrbitControls fallback (in case lib version differs)
                controls.enableDamping = false;
                controls.dampingFactor = 0;
            }
        }, 100);
    }

    // Keep renderer dimensions in sync with the container (grid layout can resize it)
    const _resizeObserver = new ResizeObserver(() => {
        if (graphInstance) {
            graphInstance
                .width(container.clientWidth)
                .height(container.clientHeight);
        }
    });
    _resizeObserver.observe(container);

    // Toggle labels on/off — controls the built-in nodeLabel tooltip visibility
    eventBus.on('labels:toggle', ({ visible }) => {
        showLabels = visible;
        if (graphInstance) {
            graphInstance.nodeLabel(showLabels ? (n => `${n.name} (${n._group || n.type})`) : (() => ''));
        }
    });

    // ---- Event listeners ----

    eventBus.on('graph:refresh', () => loadGraph());
    eventBus.on('db:changed', () => loadGraph());

    eventBus.on('node:hide', ({ id }) => {
        hiddenNodeIds.add(id);
        recomputeHiddenFlags();
        refreshVisibility();
    });

    eventBus.on('node:show-all', () => {
        hiddenNodeIds.clear();
        hiddenRelTypes.clear();
        filterSets.clear();
        forceShownIds.clear();
        recomputeHiddenFlags();
        refreshVisibility();
        // Also tell sidebar to re-check all edge filters
        eventBus.emit('edge:reset', {});
    });

    // SQL filter: {filter_id, ids, active}
    // When active=true, ids is the list of node IDs to hide.
    // When active=false, remove the filter set.
    eventBus.on('node:sql-filter', ({ filter_id, ids, active }) => {
        if (active && ids && ids.length > 0) {
            filterSets.set(filter_id, new Set(ids));
        } else {
            filterSets.delete(filter_id);
        }
        recomputeHiddenFlags();
        refreshVisibility();
    });

    eventBus.on('node:highlight', ({ ids }) => {
        highlightedIds = new Set(ids);
        if (graphInstance) {
            graphInstance.nodeColor(n => highlightedIds.size > 0
                ? (highlightedIds.has(n.id) ? '#ffffff' : n._color + '55')
                : n._color
            );
        }
    });

    eventBus.on('node:focus', ({ id }) => {
        if (!graphInstance) return;
        const node = allNodes.find(n => n.id === id);
        if (!node) return;
        const distance = 120;
        const dist = Math.hypot(node.x || 0, node.y || 0, node.z || 0);
        const distRatio = dist > 0 ? 1 + distance / dist : 1.5;
        graphInstance.cameraPosition(
            { x: (node.x || 0) * distRatio, y: (node.y || 0) * distRatio, z: (node.z || 0) * distRatio },
            node,
            1000
        );
    });

    eventBus.on('node:orbit', ({ id }) => {
        if (!graphInstance) return;
        const node = allNodes.find(n => n.id === id);
        if (!node) return;
        const controls = graphInstance.controls();
        if (controls && controls.target) {
            controls.target.set(node.x || 0, node.y || 0, node.z || 0);
            controls.update();
        }
    });

    eventBus.on('node:expand', async ({ id }) => {
        forceShownIds.add(id);
        hiddenNodeIds.delete(id);
        try {
            const data = await apiClient.get(`/api/entity/${encodeURIComponent(id)}/neighbors`);
            for (const n of (data.neighbors || [])) {
                forceShownIds.add(n.id);
                hiddenNodeIds.delete(n.id);
            }
        } catch (_) { /* best-effort */ }
        recomputeHiddenFlags();
        refreshVisibility();
    });

    eventBus.on('edge:filter', ({ rel_type, visible }) => {
        if (visible) {
            hiddenRelTypes.delete(rel_type);
        } else {
            hiddenRelTypes.add(rel_type);
        }
        recomputeHiddenFlags();
        refreshVisibility();
    });

    // Clear any custom forces and unpin UMAP positions from a previous layout
    function clearCustomForces() {
        graphInstance.d3Force('cluster', null);
        graphInstance.d3Force('timeline', null);
        graphInstance.d3Force('umap', null);
        for (const n of allNodes) {
            delete n.fx; delete n.fy; delete n.fz;
        }
    }

    // ---- UMAP overlay ----
    function showUmapOverlay(status) {
        removeUmapOverlay();
        const overlay = document.createElement('div');
        overlay.id = 'umap-overlay';
        overlay.style.cssText = `
            position:absolute;inset:0;display:flex;flex-direction:column;
            align-items:center;justify-content:center;
            background:rgba(10,10,20,0.82);z-index:50;gap:12px;
            font-family:monospace;color:#ccc;font-size:13px;
        `;
        overlay.innerHTML = `
            <div style="font-size:15px;font-weight:600;color:#4e9af1">UMAP Semantic Layout</div>
            <div id="umap-status-line">
                ${status.embedding_count} embeddings &nbsp;·&nbsp;
                ${status.position_count} positions &nbsp;·&nbsp;
                ${status.total_entities} total entities
            </div>
            <div id="umap-log" style="max-height:120px;overflow-y:auto;width:360px;
                background:#111;border:1px solid #333;border-radius:4px;
                padding:8px;font-size:11px;color:#888;"></div>
            <button id="umap-compute-btn" style="
                background:#4e9af1;border:none;border-radius:4px;
                color:#fff;padding:8px 20px;font-size:13px;cursor:pointer;">
                ${status.embedding_count === 0 ? 'Generate Embeddings + Compute UMAP' : 'Recompute UMAP'}
            </button>
            <div style="font-size:11px;color:#555;max-width:340px;text-align:center;">
                Requires <code>ollama pull nomic-embed-text</code>
            </div>
        `;
        container.style.position = 'relative';
        container.appendChild(overlay);

        document.getElementById('umap-compute-btn').addEventListener('click', () => {
            runUmapCompute();
        });
    }

    function removeUmapOverlay() {
        const el = document.getElementById('umap-overlay');
        if (el) el.remove();
    }

    function logUmap(msg) {
        const log = document.getElementById('umap-log');
        if (!log) return;
        const line = document.createElement('div');
        line.textContent = msg;
        log.appendChild(line);
        log.scrollTop = log.scrollHeight;
    }

    async function runUmapCompute() {
        const btn = document.getElementById('umap-compute-btn');
        if (btn) btn.disabled = true;

        const es = new EventSource('/api/layout/umap/compute');
        // POST not supported by EventSource — use fetch SSE approach
        es.close();

        // Use fetch with streaming for POST
        logUmap('Starting…');
        try {
            const resp = await fetch('/api/layout/umap/compute', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({}),
            });
            const reader = resp.body.getReader();
            const decoder = new TextDecoder();
            let buf = '';
            while (true) {
                const { done, value } = await reader.read();
                if (done) break;
                buf += decoder.decode(value, { stream: true });
                const lines = buf.split('\n');
                buf = lines.pop();
                for (const line of lines) {
                    if (line.startsWith('data: ')) logUmap(line.slice(6));
                    if (line.startsWith('event: done')) {
                        // positions are ready — apply them
                        removeUmapOverlay();
                        await applyUmapPositions();
                    }
                    if (line.startsWith('event: error')) {
                        if (btn) btn.disabled = false;
                    }
                }
            }
        } catch (err) {
            logUmap(`Error: ${err.message}`);
            if (btn) btn.disabled = false;
        }
    }

    async function applyUmapPositions() {
        try {
            const data = await apiClient.get('/api/layout/umap/positions');
            const positions = data.positions || {};
            clearCustomForces();
            graphInstance.dagMode(null);
            for (const n of allNodes) {
                const pos = positions[n.id];
                if (pos) {
                    n.fx = pos.x;
                    n.fy = pos.y;
                    n.fz = pos.z;
                }
            }
            graphInstance.d3ReheatSimulation();
        } catch (err) {
            console.error('UMAP positions fetch failed:', err.message);
        }
    }

    eventBus.on('layout:change', async ({ layout }) => {
        if (!graphInstance) return;

        // Always clear custom forces and dag mode first
        clearCustomForces();
        graphInstance.dagMode(null);

        if (layout === 'force') {
            graphInstance.d3ReheatSimulation();

        } else if (layout === 'cluster') {
            // Pull each node toward its type's centroid arranged in a circle
            const types = [...new Set(allNodes.map(n => n._group))];
            const radius = 600;
            const typeCentroids = {};
            types.forEach((t, i) => {
                const angle = (i / types.length) * 2 * Math.PI;
                typeCentroids[t] = {
                    x: Math.cos(angle) * radius,
                    y: Math.sin(angle) * radius,
                    z: 0,
                };
            });
            graphInstance.d3Force('cluster', alpha => {
                for (const n of allNodes) {
                    if (n.__hidden) continue;
                    const c = typeCentroids[n._group];
                    if (!c) continue;
                    n.vx = (n.vx || 0) + (c.x - (n.x || 0)) * 0.3 * alpha;
                    n.vy = (n.vy || 0) + (c.y - (n.y || 0)) * 0.3 * alpha;
                    n.vz = (n.vz || 0) + (c.z - (n.z || 0)) * 0.3 * alpha;
                }
            });
            graphInstance.d3ReheatSimulation();

        } else if (layout === 'timeline') {
            // Fetch year data from metadata, lock X axis to year
            let yearMap = {};
            try {
                const data = await apiClient.post('/api/query', {
                    sql: `SELECT id,
                          CAST(COALESCE(
                            json_extract(metadata,'$.year'),
                            substr(json_extract(metadata,'$.date'),1,4),
                            substr(created_at,1,4)
                          ) AS INTEGER) as year
                          FROM entities
                          WHERE year IS NOT NULL AND year > 1900 AND year < 2100`
                });
                for (const r of (data.results || [])) {
                    if (r.year) yearMap[r.id] = r.year;
                }
            } catch (_) {}

            const years = Object.values(yearMap);
            if (years.length === 0) {
                console.warn('Timeline: no date metadata found');
                graphInstance.d3ReheatSimulation();
                return;
            }
            const minYear = Math.min(...years);
            const maxYear = Math.max(...years);
            const spread = 1200;
            const range = maxYear - minYear || 1;

            graphInstance.d3Force('timeline', alpha => {
                for (const n of allNodes) {
                    if (n.__hidden) continue;
                    const year = yearMap[n.id];
                    if (!year) continue;
                    const targetX = ((year - minYear) / range) * spread - spread / 2;
                    n.vx = (n.vx || 0) + (targetX - (n.x || 0)) * 0.9 * alpha;
                }
            });
            graphInstance.d3ReheatSimulation();

        } else if (layout === 'umap') {
            try {
                const status = await apiClient.get('/api/layout/umap/status');
                if (status.ready) {
                    await applyUmapPositions();
                } else {
                    showUmapOverlay(status);
                }
            } catch (err) {
                console.error('UMAP status check failed:', err.message);
                showUmapOverlay({ embedding_count: 0, position_count: 0, total_entities: 0 });
            }

        } else {
            // DAG modes: td, bu, lr, rl, radialout, radialin
            graphInstance.dagMode(layout);
        }
    });

    eventBus.on('sidebar:select', ({ id }) => {
        eventBus.emit('node:focus', { id });
        eventBus.emit('node:selected', { id });
    });

    // ---- Force settings ----
    eventBus.on('force:get-types', ({ callback }) => {
        const types = [...new Set(allNodes.map(n => n._group))].sort();
        callback(types);
    });

    eventBus.on('force:update', (settings) => {
        if (!graphInstance) return;

        const linkForce = graphInstance.d3Force('link');
        if (linkForce) {
            linkForce.distance(settings.linkDist);
            linkForce.strength(settings.linkStr / 100);
        }

        const chargeForce = graphInstance.d3Force('charge');
        if (chargeForce) {
            if (settings.typeCharges && Object.keys(settings.typeCharges).length > 0) {
                chargeForce.strength(node => {
                    return settings.typeCharges[node._group] ?? settings.charge;
                });
            } else {
                chargeForce.strength(settings.charge);
            }
        }

        const centerForce = graphInstance.d3Force('center');
        if (centerForce) {
            centerForce.strength(settings.center / 100);
        }

        // Collision force — only works if d3 is available globally
        try {
            if (settings.collision > 0 && typeof d3 !== 'undefined' && d3.forceCollide) {
                graphInstance.d3Force('collision', d3.forceCollide(settings.collision));
            } else {
                graphInstance.d3Force('collision', null);
            }
        } catch (_) { /* d3 not available as global — collision slider is a no-op */ }

        // Alpha decay
        graphInstance.d3AlphaDecay(settings.decay / 1000);

        // Edge visual properties
        if (settings.edgeWidth !== undefined) {
            graphInstance.linkWidth(settings.edgeWidth / 10);
        }
        if (settings.edgeOpacity !== undefined) {
            graphInstance.linkOpacity(settings.edgeOpacity / 100);
        }
        if (settings.edgeColor !== undefined) {
            graphInstance.linkColor(() => settings.edgeColor);
        }
        if (settings.particles !== undefined) {
            graphInstance.linkDirectionalParticles(settings.particles);
        }

        graphInstance.d3ReheatSimulation();
    });

    eventBus.on('force:reheat', () => {
        if (graphInstance) graphInstance.d3ReheatSimulation();
    });

    // ---- Init ----
    initForceGraph();
    loadGraph();

    return {
        reload: loadGraph,
        getTypeColorMap: () => ({ ...typeColorMap }),
        getInstance: () => graphInstance,
    };
}
