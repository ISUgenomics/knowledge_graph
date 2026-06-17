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
 *   timeline:settings {anchorType, orderField, profile} — store in-session timeline overrides
 *   db:changed        {}         — reload graph data
 *
 * Outgoing events:
 *   graph:loaded      {nodeCount, edgeCount}
 *   graph:projection  {entityTypes, visibleNodesByType, relTypeCounts, graphMode}
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

const FIXED_TYPE_COLORS = {
    gene: '#4e9af1',
    transcript: '#f1a34e',
    protein: '#4ef17a',
    orthogroup: '#f14e4e',
    bcn_gene: '#ff7a7a',
    comparative_hit: '#ffb347',
    annotation_term: '#c34ef1',
    localization_call: '#4ef1e8',
    prediction_call: '#f1e24e',
    expression_measure: '#ff8fc7',
    contrast_definition: '#6fd3a0',
    tag: '#9aa4b2',
};

const REL_COLORS = {
    default: '#555566',
};

const LIVE_NODE_RESOLUTION = 8;
const EXPORT_NODE_RESOLUTION = 96;
const EXPORT_RENDER_PIXEL_RATIO = 3;
const DEFAULT_TIMELINE_X_STEP = 140;
const DEFAULT_TIMELINE_Y_STEP = 90;
const DEFAULT_TIMELINE_ANCHOR_Z = 0;
const DEFAULT_TIMELINE_ANCHOR_LABEL_Z = -25;
const DEFAULT_HIERARCHY_LEVEL_SPACING = 180;
const DEFAULT_HIERARCHY_TYPE_SEPARATION = 140;
const DEFAULT_HIERARCHY_STRUCTURE_PULL = 100;
const DEFAULT_HIERARCHY_RELATION_CLASSES = {
    hierarchy: ['BROADER', 'PARENT_OF', 'NARROWER', 'CHILD_OF'],
    structural: ['AUTHORED', 'CREATED', 'WROTE', 'PUBLISHED', 'PRODUCED', 'PRESENTED', 'ISSUED', 'FILED', 'FUNDED', 'GRANTED', 'WON'],
    affiliation: ['MEMBER_OF', 'AFFILIATED_WITH', 'BELONGS_TO', 'WORKS_AT', 'PART_OF'],
    annotation: ['TAGGED', 'HAS_TAG', 'ABOUT', 'TOPIC', 'KEYWORD', 'MENTIONS'],
    associative: ['COAUTHOR', 'COLLABORATOR', 'RELATED', 'SIMILAR', 'CITES', 'CITED'],
};
const TIMELINE_PERSON_Z = 140;
const TIMELINE_ORGANIZATION_Z = 260;
const TIMELINE_Z_BAND_STEP = 190;
const TIMELINE_Z_MICRO_JITTER = 24; // Must stay <= 0.5 * TIMELINE_Z_BAND_STEP
const TIMELINE_TAG_TOPIC_Z = TIMELINE_ORGANIZATION_Z + (TIMELINE_Z_BAND_STEP * 1);
const TIMELINE_TAG_FIELD_Z = TIMELINE_ORGANIZATION_Z + (TIMELINE_Z_BAND_STEP * 2);
const TIMELINE_TAG_DOMAIN_Z = TIMELINE_ORGANIZATION_Z + (TIMELINE_Z_BAND_STEP * 3);
const TIMELINE_TAG_TOP_Z = TIMELINE_ORGANIZATION_Z + (TIMELINE_Z_BAND_STEP * 4);
const TIMELINE_TAG_CORE_Z = TIMELINE_ORGANIZATION_Z + (TIMELINE_Z_BAND_STEP * 5);
const AXIS_GIZMO_SIZE = 96;
const AXIS_GIZMO_CENTER = AXIS_GIZMO_SIZE / 2;
const AXIS_GIZMO_RADIUS = 28;
const AXIS_GIZMO_AXES = [
    { key: 'x', vector: { x: 1, y: 0, z: 0 }, color: '#f1784e', label: 'X' },
    { key: 'y', vector: { x: 0, y: 1, z: 0 }, color: '#4ef17a', label: 'Y' },
    { key: 'z', vector: { x: 0, y: 0, z: 1 }, color: '#4e9af1', label: 'Z' },
];

export function initGraph(container, eventBus, apiClient) {
    let graphInstance = null;
    let allNodes = [];
    let allEdges = [];
    let hiddenNodeIds = new Set();
    const DEFAULT_HIDDEN_NODE_TYPES = new Set(['dataset']);
    let hiddenNodeTypes = new Set(DEFAULT_HIDDEN_NODE_TYPES);
    let hiddenNodeGroups = new Map();
    let hiddenRelTypes = new Set();
    let presetDefaultHiddenRelTypes = new Set();
    let highlightedIds = new Set();
    let selectedNodeId = null;
    // SQL filter sets: filter_id → Set<node_id>
    let filterSets = new Map();
    // Nodes force-shown via "Expand neighbors" — overrides all filters
    let forceShownIds = new Set();
    let typeColorMap = {};
    let colorIndex = 0;
    let communityMode = false;  // toggle: type colors vs community colors
    let communityColorMap = {}; // node_id -> color
    let communityResolution = 1.0; // <1 = fewer/larger communities, >1 = more/smaller
    let graphMode = 'explore';  // keep current alex default behavior
    let graphPreset = '';
    let currentLayout = 'force';
    let pinLabelsOn = false;
    let exportDbBaseName = null;
    let projectionMeta = { mode: graphMode };
    let timelineSettings = {
        anchorType: '',
        orderField: '',
        profile: null,
        showAnchorLabels: true,
        anchorLabelZ: DEFAULT_TIMELINE_ANCHOR_LABEL_Z,
        anchorLabelRotate: 0,
        anchorLabelZRotate: 0,
    };
    let hierarchySettings = {
        levelSpacing: DEFAULT_HIERARCHY_LEVEL_SPACING,
        typeSeparation: DEFAULT_HIERARCHY_TYPE_SEPARATION,
        shapeBlend: 0,
        coreOffset: 0,
        structureMode: 'linear',
        reverseTags: false,
        strictBands: false,
        profile: null,
    };
    let timelineAnchorTargets = new Map();
    let timelineAnchorLabelTargets = new Map();
    let hierarchyEdgesCache = null;
    let hierarchyOptionsCache = null;
    const labelLayer = document.createElement('div');
    labelLayer.className = 'graph-label-layer';
    const pinnedLabelEls = new Map();
    const timelineAnchorLabelEls = new Map();
    const selectedMarkerEl = document.createElement('div');
    selectedMarkerEl.className = 'graph-selected-marker';
    selectedMarkerEl.style.display = 'none';
    let lastAxisSnapKey = '';
    let lastAxisSnapSign = 1;
    let activeAxisLockKey = '';
    let activeAxisLockDrag = null;
    const axisGizmoEl = document.createElement('div');
    axisGizmoEl.className = 'graph-axis-gizmo';
    axisGizmoEl.innerHTML = `
        <svg viewBox="0 0 ${AXIS_GIZMO_SIZE} ${AXIS_GIZMO_SIZE}" aria-hidden="true">
            <circle class="graph-axis-gizmo-ring" cx="${AXIS_GIZMO_CENTER}" cy="${AXIS_GIZMO_CENTER}" r="${AXIS_GIZMO_RADIUS + 12}"></circle>
            ${AXIS_GIZMO_AXES.map(axis => `
                <g class="graph-axis-gizmo-axis" data-axis="${axis.key}">
                    <line data-part="hit-line" x1="${AXIS_GIZMO_CENTER}" y1="${AXIS_GIZMO_CENTER}" x2="${AXIS_GIZMO_CENTER}" y2="${AXIS_GIZMO_CENTER}" stroke="transparent" stroke-width="14"></line>
                    <line data-part="line" x1="${AXIS_GIZMO_CENTER}" y1="${AXIS_GIZMO_CENTER}" x2="${AXIS_GIZMO_CENTER}" y2="${AXIS_GIZMO_CENTER}" stroke="${axis.color}"></line>
                    <circle data-part="hit-dot" cx="${AXIS_GIZMO_CENTER}" cy="${AXIS_GIZMO_CENTER}" r="14" fill="transparent"></circle>
                    <circle data-part="dot" cx="${AXIS_GIZMO_CENTER}" cy="${AXIS_GIZMO_CENTER}" r="8" fill="${axis.color}"></circle>
                    <text data-part="label" x="${AXIS_GIZMO_CENTER}" y="${AXIS_GIZMO_CENTER}">${axis.label}</text>
                </g>
            `).join('')}
        </svg>
    `;
    const axisGizmoParts = new Map();

    function isNodeVisibleInCurrentLayout(node) {
        return !!node && !node.__hidden && !node.__timelineHidden;
    }

    function isEdgeVisibleInCurrentLayout(edge) {
        return !!edge && !edge.__hidden && !edge.__timelineHidden;
    }

    // Community detection color palette (distinct from type palette)
const COMMUNITY_COLORS = [
        '#e6194b', '#3cb44b', '#ffe119', '#4363d8', '#f58231',
        '#911eb4', '#42d4f4', '#f032e6', '#bfef45', '#fabed4',
        '#469990', '#dcbeff', '#9A6324', '#fffac8', '#800000',
        '#aaffc3', '#808000', '#ffd8b1', '#000075', '#a9a9a9',
    ];

    const TYPE_SIZE_MULTIPLIERS = {
        organism: 1.1,
        chromosome: 0.9,
        gene: 1.45,
        transcript: 1.15,
        protein: 1.2,
        orthogroup: 1.05,
        bcn_gene: 0.95,
        comparative_hit: 0.9,
        annotation_term: 0.85,
        localization_call: 0.88,
        prediction_call: 0.9,
        expression_measure: 0.98,
        contrast_definition: 0.98,
        tag: 0.78,
    };

    const PRESET_TYPE_SIZE_MULTIPLIERS = {
        comparative: {
            organism: 1.18,
            chromosome: 0.82,
            gene: 1.35,
            orthogroup: 1.55,
            bcn_gene: 0.82,
            comparative_hit: 0.8,
        },
    };

    function getTypeColor(type) {
        if (FIXED_TYPE_COLORS[type]) {
            typeColorMap[type] = FIXED_TYPE_COLORS[type];
            return FIXED_TYPE_COLORS[type];
        }
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

    // Compute filtered degree — only counts visible edges
    function recomputeFilteredDegrees() {
        for (const n of allNodes) n._filteredDegree = 0;
        const nodeMap = {};
        for (const n of allNodes) nodeMap[n.id] = n;
        for (const e of allEdges) {
            if (e.__hidden) continue;
            const src = typeof e.source === 'object' ? e.source.id : e.source;
            const tgt = typeof e.target === 'object' ? e.target.id : e.target;
            if (nodeMap[src]) nodeMap[src]._filteredDegree++;
            if (nodeMap[tgt]) nodeMap[tgt]._filteredDegree++;
        }
    }

    function seededRng(seed) {
        let state = seed | 0;
        return () => {
            state = (state * 1664525 + 1013904223) & 0x7fffffff;
            return state / 0x7fffffff;
        };
    }

    // Label propagation community detection on visible subgraph
    function detectCommunities() {
        const rng = seededRng(42);
        const resolution = communityResolution;

        // Build weighted adjacency from visible edges
        const adj = {};
        const edgeWeight = {};
        for (const n of allNodes) {
            if (!n.__hidden) adj[n.id] = [];
        }
        for (const e of allEdges) {
            if (e.__hidden) continue;
            const src = typeof e.source === 'object' ? e.source.id : e.source;
            const tgt = typeof e.target === 'object' ? e.target.id : e.target;
            if (adj[src] && adj[tgt]) {
                adj[src].push(tgt);
                adj[tgt].push(src);
                const weight = e.weight || 1;
                edgeWeight[`${src}|${tgt}`] = weight;
                edgeWeight[`${tgt}|${src}`] = weight;
            }
        }

        // Initialize: each node is its own community
        const label = {};
        const ids = Object.keys(adj);
        for (const id of ids) label[id] = id;

        // Iterate label propagation with deterministic order and resolution-aware scoring.
        for (let iter = 0; iter < 30; iter++) {
            let changed = false;
            const shuffled = [...ids].sort(() => rng() - 0.5);
            for (const id of shuffled) {
                const neighbors = adj[id];
                if (neighbors.length === 0) continue;
                // Count neighbor labels weighted by edge weight.
                const counts = {};
                for (const nb of neighbors) {
                    const l = label[nb];
                    const weight = edgeWeight[`${id}|${nb}`] || 1;
                    counts[l] = (counts[l] || 0) + weight;
                }
                if (resolution !== 1.0) {
                    const labelSizes = {};
                    for (const existingLabel of Object.values(label)) {
                        labelSizes[existingLabel] = (labelSizes[existingLabel] || 0) + 1;
                    }
                    for (const communityLabel of Object.keys(counts)) {
                        counts[communityLabel] =
                            counts[communityLabel] / Math.pow(labelSizes[communityLabel] || 1, resolution - 1);
                    }
                }
                // Pick most frequent with deterministic tie-breaking.
                let maxCount = 0;
                let candidates = [];
                for (const [l, c] of Object.entries(counts)) {
                    if (c > maxCount) { maxCount = c; candidates = [l]; }
                    else if (c === maxCount) candidates.push(l);
                }
                candidates.sort();
                const pick = candidates[0];
                if (pick !== label[id]) { label[id] = pick; changed = true; }
            }
            if (!changed) break;
        }

        // Assign colors to communities
        const uniqueLabels = [...new Set(Object.values(label))];
        // Sort by community size (largest first) for best color assignment
        const labelCounts = {};
        for (const l of Object.values(label)) labelCounts[l] = (labelCounts[l] || 0) + 1;
        uniqueLabels.sort((a, b) => (labelCounts[b] || 0) - (labelCounts[a] || 0));
        const labelColorMap = {};
        uniqueLabels.forEach((l, i) => {
            labelColorMap[l] = COMMUNITY_COLORS[i % COMMUNITY_COLORS.length];
        });

        communityColorMap = {};
        for (const [id, l] of Object.entries(label)) {
            communityColorMap[id] = labelColorMap[l];
        }
    }

    function getNodeColor(n) {
        if (highlightedIds.size > 0) {
            return highlightedIds.has(n.id) ? '#ffffff' : (communityMode ? communityColorMap[n.id] || n._color : n._color) + '44';
        }
        return communityMode ? (communityColorMap[n.id] || n._color) : n._color;
    }

    function getNodeSize(n) {
        const degree = Math.max(1, Math.sqrt(n._filteredDegree || n._degree || 1)) * 2;
        const presetScale = PRESET_TYPE_SIZE_MULTIPLIERS[graphPreset]?.[n.type];
        return degree * (presetScale || TYPE_SIZE_MULTIPLIERS[n.type] || 1);
    }

    function getNodeLabel(n) {
        const base = `${getNodeDisplayName(n)} (${n._group || n.type})`;
        const meta = n?.metadata || {};
        if (graphPreset === 'comparative' && n.type === 'orthogroup') {
            const extras = [
                meta.local_gene_count != null ? `local genes: ${meta.local_gene_count}` : '',
                meta.schachtii_gene_count != null ? `H. schachtii: ${meta.schachtii_gene_count}` : '',
            ].filter(Boolean).join(' • ');
            return extras ? `${base}\n${extras}` : base;
        }
        if (graphPreset === 'comparative' && n.type === 'bcn_gene') {
            const extras = [
                meta.organism,
                Array.isArray(meta.relationship_types) ? meta.relationship_types.join(', ') : '',
            ].filter(Boolean).join(' • ');
            return extras ? `${base}\n${extras}` : base;
        }
        if (graphPreset === 'comparative' && n.type === 'comparative_hit') {
            const extras = [
                meta.organism,
                Array.isArray(meta.scope_tag_ids) ? meta.scope_tag_ids.join(', ') : '',
                Array.isArray(meta.relationship_types) ? meta.relationship_types.join(', ') : '',
            ].filter(Boolean).join(' • ');
            return extras ? `${base}\n${extras}` : base;
        }
        if (n.type === 'annotation_term') {
            const extras = [meta.namespace, meta.category].filter(Boolean).join(' • ');
            return extras ? `${base}\n${extras}` : base;
        }
        if (n.type === 'prediction_call') {
            const extras = [meta.category, meta.source_column].filter(Boolean).join(' • ');
            return extras ? `${base}\n${extras}` : base;
        }
        if (n.type === 'localization_call') {
            const extras = [meta.category, meta.source_column].filter(Boolean).join(' • ');
            return extras ? `${base}\n${extras}` : base;
        }
        if (n.type === 'expression_measure') {
            const extras = [meta.category, meta.source_column].filter(Boolean).join(' • ');
            return extras ? `${base}\n${extras}` : base;
        }
        if (n.type === 'contrast_definition') {
            const extras = [meta.category, meta.source_column].filter(Boolean).join(' • ');
            return extras ? `${base}\n${extras}` : base;
        }
        return base;
    }

    function applyPresetForceTuning() {
        if (!graphInstance) return;
        const linkForce = graphInstance.d3Force('link');
        const chargeForce = graphInstance.d3Force('charge');
        const centerForce = graphInstance.d3Force('center');
        graphInstance.d3Force('comparativeBands', null);
        if (linkForce) {
            linkForce.distance(30);
            linkForce.strength(0.1);
        }
        if (chargeForce) {
            chargeForce.strength(-120);
        }
        if (centerForce) {
            centerForce.strength(0.1);
        }
        graphInstance.d3AlphaDecay(0.0228);
    }

    function refreshNodeAppearance() {
        if (!graphInstance) return;
        graphInstance
            .nodeColor(n => getNodeColor(n))
            .nodeVal(n => getNodeSize(n))
            .nodeLabel(n => getNodeLabel(n));
    }

    function getPinnedLabelIds() {
        if (!pinLabelsOn) return [];
        if (highlightedIds.size > 0) {
            return [...highlightedIds].filter(id => {
                const node = allNodes.find(n => n.id === id);
                return node && !node.__hidden;
            });
        }
        if (!selectedNodeId) return [];
        const selected = allNodes.find(n => n.id === selectedNodeId);
        return selected && !selected.__hidden ? [selectedNodeId] : [];
    }

    function syncPinnedLabelElements() {
        const activeIds = new Set(getPinnedLabelIds());
        for (const [id, el] of pinnedLabelEls.entries()) {
            if (!activeIds.has(id)) {
                el.remove();
                pinnedLabelEls.delete(id);
            }
        }
        for (const id of activeIds) {
            if (pinnedLabelEls.has(id)) continue;
            const node = allNodes.find(n => n.id === id);
            if (!node) continue;
            const el = document.createElement('div');
            el.className = 'graph-node-label';
            el.textContent = getNodeDisplayName(node);
            labelLayer.appendChild(el);
            pinnedLabelEls.set(id, el);
        }
    }

    function syncTimelineAnchorLabelElements() {
        const activeEntries = (timelineSettings.showAnchorLabels !== false && timelineAnchorLabelTargets.size > 0)
            ? timelineAnchorLabelTargets
            : new Map();
        const activeKeys = new Set(activeEntries.keys());
        for (const [key, el] of timelineAnchorLabelEls.entries()) {
            if (!activeKeys.has(key)) {
                el.remove();
                timelineAnchorLabelEls.delete(key);
            }
        }
        for (const [key, entry] of activeEntries.entries()) {
            if (timelineAnchorLabelEls.has(key)) continue;
            const el = document.createElement('div');
            el.className = 'graph-node-label';
            el.style.fontSize = '10px';
            el.style.opacity = '0.82';
            el.style.pointerEvents = 'none';
            el.textContent = entry.text;
            labelLayer.appendChild(el);
            timelineAnchorLabelEls.set(key, el);
        }
    }

    function updatePinnedLabelPositions() {
        if (!graphInstance) return;
        syncTimelineAnchorLabelElements();
        for (const [key, el] of timelineAnchorLabelEls.entries()) {
            const entry = timelineAnchorLabelTargets.get(key);
            if (!entry || timelineSettings.showAnchorLabels === false) {
                el.style.display = 'none';
                continue;
            }
            let coords = null;
            const anchorTargets = (entry.anchorIds || [])
                .map(id => timelineAnchorTargets.get(id))
                .filter(target => target && Number.isFinite(target.x) && Number.isFinite(target.y));
            if (anchorTargets.length > 0) {
                const avgX = anchorTargets.reduce((sum, target) => sum + target.x, 0) / anchorTargets.length;
                const avgY = anchorTargets.reduce((sum, target) => sum + target.y, 0) / anchorTargets.length;
                coords = graphInstance.graph2ScreenCoords(avgX, avgY, entry.z);
            }
            if (!coords || !Number.isFinite(coords.x) || !Number.isFinite(coords.y)) {
                coords = graphInstance.graph2ScreenCoords(entry.x, entry.y, entry.z);
            }
            if (!coords || !Number.isFinite(coords.x) || !Number.isFinite(coords.y)) {
                el.style.display = 'none';
                continue;
            }
            el.style.display = '';
            el.style.left = `${coords.x}px`;
            el.style.top = `${coords.y + 16}px`;
            el.style.transform = `translate(-50%, -100%) perspective(600px) rotateY(${timelineSettings.anchorLabelZRotate || 0}deg) rotateZ(${timelineSettings.anchorLabelRotate || 0}deg)`;
        }
        syncPinnedLabelElements();
        for (const [id, el] of pinnedLabelEls.entries()) {
            const node = allNodes.find(n => n.id === id);
            if (!node || node.__hidden || !Number.isFinite(node.x) || !Number.isFinite(node.y) || !Number.isFinite(node.z)) {
                el.style.display = 'none';
                continue;
            }
            const coords = graphInstance.graph2ScreenCoords(node.x, node.y, node.z);
            if (!coords || !Number.isFinite(coords.x) || !Number.isFinite(coords.y)) {
                el.style.display = 'none';
                continue;
            }
            el.style.display = '';
            el.style.left = `${coords.x}px`;
            el.style.top = `${coords.y - 10}px`;
        }

        const selected = selectedNodeId ? allNodes.find(n => n.id === selectedNodeId) : null;
        if (!selected || selected.__hidden || !Number.isFinite(selected.x) || !Number.isFinite(selected.y) || !Number.isFinite(selected.z)) {
            selectedMarkerEl.style.display = 'none';
            return;
        }
        const selectedCoords = graphInstance.graph2ScreenCoords(selected.x, selected.y, selected.z);
        if (!selectedCoords || !Number.isFinite(selectedCoords.x) || !Number.isFinite(selectedCoords.y)) {
            selectedMarkerEl.style.display = 'none';
            return;
        }
        selectedMarkerEl.style.display = '';
        selectedMarkerEl.style.left = `${selectedCoords.x}px`;
        selectedMarkerEl.style.top = `${selectedCoords.y}px`;
    }

    function startPinnedLabelLoop() {
        const tick = () => {
            updatePinnedLabelPositions();
            updateAxisGizmo();
            requestAnimationFrame(tick);
        };
        requestAnimationFrame(tick);
    }

    function drawRoundedRect(ctx, x, y, width, height, radius) {
        const r = Math.min(radius, width / 2, height / 2);
        ctx.beginPath();
        ctx.moveTo(x + r, y);
        ctx.arcTo(x + width, y, x + width, y + height, r);
        ctx.arcTo(x + width, y + height, x, y + height, r);
        ctx.arcTo(x, y + height, x, y, r);
        ctx.arcTo(x, y, x + width, y, r);
        ctx.closePath();
    }

    function rotateVectorByQuaternionInverse(vec, quat) {
        const qx = -(quat?.x || 0);
        const qy = -(quat?.y || 0);
        const qz = -(quat?.z || 0);
        const qw = quat?.w ?? 1;

        const ix = (qw * vec.x) + (qy * vec.z) - (qz * vec.y);
        const iy = (qw * vec.y) + (qz * vec.x) - (qx * vec.z);
        const iz = (qw * vec.z) + (qx * vec.y) - (qy * vec.x);
        const iw = -(qx * vec.x) - (qy * vec.y) - (qz * vec.z);

        return {
            x: (ix * qw) + (iw * -qx) + (iy * -qz) - (iz * -qy),
            y: (iy * qw) + (iw * -qy) + (iz * -qx) - (ix * -qz),
            z: (iz * qw) + (iw * -qz) + (ix * -qy) - (iy * -qx),
        };
    }

    function normalizeVector(vec) {
        const length = Math.hypot(vec.x || 0, vec.y || 0, vec.z || 0) || 1;
        return {
            x: (vec.x || 0) / length,
            y: (vec.y || 0) / length,
            z: (vec.z || 0) / length,
        };
    }

    function rotateVectorAroundAxis(vec, axis, angle) {
        const unitAxis = normalizeVector(axis);
        const cos = Math.cos(angle);
        const sin = Math.sin(angle);
        const dot = (vec.x * unitAxis.x) + (vec.y * unitAxis.y) + (vec.z * unitAxis.z);
        return {
            x: (vec.x * cos) + ((unitAxis.y * vec.z) - (unitAxis.z * vec.y)) * sin + (unitAxis.x * dot * (1 - cos)),
            y: (vec.y * cos) + ((unitAxis.z * vec.x) - (unitAxis.x * vec.z)) * sin + (unitAxis.y * dot * (1 - cos)),
            z: (vec.z * cos) + ((unitAxis.x * vec.y) - (unitAxis.y * vec.x)) * sin + (unitAxis.z * dot * (1 - cos)),
        };
    }

    function initAxisGizmo() {
        axisGizmoEl.querySelectorAll('.graph-axis-gizmo-axis').forEach(group => {
            const key = group.dataset.axis;
            axisGizmoParts.set(key, {
                group,
                hitLine: group.querySelector('[data-part="hit-line"]'),
                line: group.querySelector('[data-part="line"]'),
                hitDot: group.querySelector('[data-part="hit-dot"]'),
                dot: group.querySelector('[data-part="dot"]'),
                label: group.querySelector('[data-part="label"]'),
            });
            const handlePointer = event => {
                event.stopPropagation();
                event.preventDefault();
                snapCameraToAxis(key);
            };
            group.addEventListener('pointerdown', handlePointer);
            group.addEventListener('click', handlePointer);
        });
    }

    function getCameraTarget() {
        const controls = graphInstance?.controls?.();
        if (controls?.target) {
            return {
                x: controls.target.x || 0,
                y: controls.target.y || 0,
                z: controls.target.z || 0,
            };
        }
        return { x: 0, y: 0, z: 0 };
    }

    function getAxisVector(axisKey) {
        return AXIS_GIZMO_AXES.find(item => item.key === axisKey)?.vector || { x: 0, y: 0, z: 1 };
    }

    function snapCameraToAxis(axisKey) {
        if (!graphInstance) return;
        const camera = graphInstance.camera?.();
        if (!camera?.position) return;
        const target = getCameraTarget();
        const axis = AXIS_GIZMO_AXES.find(item => item.key === axisKey);
        if (!axis) return;

        const dx = (camera.position.x || 0) - target.x;
        const dy = (camera.position.y || 0) - target.y;
        const dz = (camera.position.z || 0) - target.z;
        const distance = Math.max(Math.hypot(dx, dy, dz), 1);
        const signBasis = axisKey === 'x' ? dx : axisKey === 'y' ? dy : dz;
        const defaultSign = signBasis >= 0 ? 1 : -1;
        const sign = lastAxisSnapKey === axisKey ? -lastAxisSnapSign : defaultSign;
        const upVector = (() => {
            if (axisKey === 'z') {
                return { x: 0, y: sign > 0 ? 1 : -1, z: 0 };
            }
            return { x: 0, y: 0, z: sign > 0 ? 1 : -1 };
        })();
        const nextPosition = {
            x: target.x + (axis.vector.x * sign * distance),
            y: target.y + (axis.vector.y * sign * distance),
            z: target.z + (axis.vector.z * sign * distance),
        };

        const controls = graphInstance.controls?.();
        if (controls?.target?.set) {
            controls.target.set(target.x, target.y, target.z);
        }
        if (camera.position?.set) {
            camera.position.set(nextPosition.x, nextPosition.y, nextPosition.z);
        } else {
            camera.position.x = nextPosition.x;
            camera.position.y = nextPosition.y;
            camera.position.z = nextPosition.z;
        }
        if (camera.up?.set) {
            camera.up.set(upVector.x, upVector.y, upVector.z);
        } else if (camera.up) {
            camera.up.x = upVector.x;
            camera.up.y = upVector.y;
            camera.up.z = upVector.z;
        }
        if (camera.lookAt) {
            camera.lookAt(target.x, target.y, target.z);
        }
        controls?.update?.();
        graphInstance.refresh?.();
        lastAxisSnapKey = axisKey;
        lastAxisSnapSign = sign;
    }

    function updateAxisGizmo() {
        if (!graphInstance) return;
        const camera = graphInstance.camera?.();
        if (!camera?.quaternion) return;

        const projected = AXIS_GIZMO_AXES.map(axis => {
            const view = rotateVectorByQuaternionInverse(axis.vector, camera.quaternion);
            return {
                ...axis,
                view,
                x2: AXIS_GIZMO_CENTER + (view.x * AXIS_GIZMO_RADIUS),
                y2: AXIS_GIZMO_CENTER - (view.y * AXIS_GIZMO_RADIUS),
            };
        }).sort((a, b) => a.view.z - b.view.z);

        projected.forEach(axis => {
            const parts = axisGizmoParts.get(axis.key);
            if (!parts) return;
            parts.group.parentNode.appendChild(parts.group);
            const opacity = 0.45 + ((axis.view.z + 1) * 0.25);
            parts.hitLine.setAttribute('x1', String(AXIS_GIZMO_CENTER));
            parts.hitLine.setAttribute('y1', String(AXIS_GIZMO_CENTER));
            parts.hitLine.setAttribute('x2', String(axis.x2));
            parts.hitLine.setAttribute('y2', String(axis.y2));
            parts.line.setAttribute('x1', String(AXIS_GIZMO_CENTER));
            parts.line.setAttribute('y1', String(AXIS_GIZMO_CENTER));
            parts.line.setAttribute('x2', String(axis.x2));
            parts.line.setAttribute('y2', String(axis.y2));
            parts.line.setAttribute('opacity', String(opacity));
            parts.hitDot.setAttribute('cx', String(axis.x2));
            parts.hitDot.setAttribute('cy', String(axis.y2));
            parts.dot.setAttribute('cx', String(axis.x2));
            parts.dot.setAttribute('cy', String(axis.y2));
            parts.dot.setAttribute('opacity', String(opacity));
            parts.label.setAttribute('x', String(axis.x2));
            parts.label.setAttribute('y', String(axis.y2));
            parts.label.setAttribute('opacity', String(Math.min(1, opacity + 0.1)));
        });
    }

    function isEditableTarget(target) {
        const tag = target?.tagName?.toLowerCase?.() || '';
        return tag === 'input' || tag === 'textarea' || tag === 'select' || target?.isContentEditable;
    }

    function setActiveAxisLockKey(nextKey) {
        activeAxisLockKey = nextKey;
        if (container) {
            container.style.cursor = activeAxisLockDrag
                ? 'grabbing'
                : (activeAxisLockKey ? 'crosshair' : '');
        }
    }

    function endAxisLockDrag() {
        if (!activeAxisLockDrag) {
            setActiveAxisLockKey(activeAxisLockKey);
            return;
        }
        const controls = graphInstance?.controls?.();
        if (controls) controls.enabled = true;
        activeAxisLockDrag = null;
        setActiveAxisLockKey(activeAxisLockKey);
    }

    function startAxisLockInteraction() {
        window.addEventListener('keydown', event => {
            if (event.repeat || isEditableTarget(event.target)) return;
            const key = String(event.key || '').toLowerCase();
            if (key === 'x' || key === 'y' || key === 'z') {
                setActiveAxisLockKey(key);
            }
        });
        window.addEventListener('keyup', event => {
            const key = String(event.key || '').toLowerCase();
            if (key === activeAxisLockKey) {
                setActiveAxisLockKey('');
            }
        });
        window.addEventListener('blur', () => {
            setActiveAxisLockKey('');
            endAxisLockDrag();
        });

        container.addEventListener('pointerdown', event => {
            if (event.button !== 0 || !activeAxisLockKey || !graphInstance) return;
            if (axisGizmoEl.contains(event.target)) return;
            const camera = graphInstance.camera?.();
            const controls = graphInstance.controls?.();
            if (!camera?.position || !controls) return;
            const target = getCameraTarget();
            activeAxisLockDrag = {
                pointerId: event.pointerId,
                axisKey: activeAxisLockKey,
                lastClientX: event.clientX,
                lastClientY: event.clientY,
                target,
            };
            controls.enabled = false;
            setActiveAxisLockKey(activeAxisLockKey);
            container.setPointerCapture?.(event.pointerId);
            event.preventDefault();
            event.stopPropagation();
        });

        container.addEventListener('pointermove', event => {
            if (!activeAxisLockDrag || event.pointerId !== activeAxisLockDrag.pointerId || !graphInstance) return;
            const camera = graphInstance.camera?.();
            const controls = graphInstance.controls?.();
            if (!camera?.position) return;
            const dx = event.clientX - activeAxisLockDrag.lastClientX;
            const dy = event.clientY - activeAxisLockDrag.lastClientY;
            if (!dx && !dy) return;
            activeAxisLockDrag.lastClientX = event.clientX;
            activeAxisLockDrag.lastClientY = event.clientY;

            const axis = getAxisVector(activeAxisLockDrag.axisKey);
            const angle = ((dx * 0.8) - (dy * 0.8)) * 0.01;
            const offset = {
                x: (camera.position.x || 0) - activeAxisLockDrag.target.x,
                y: (camera.position.y || 0) - activeAxisLockDrag.target.y,
                z: (camera.position.z || 0) - activeAxisLockDrag.target.z,
            };
            const rotatedOffset = rotateVectorAroundAxis(offset, axis, angle);
            const rotatedUp = rotateVectorAroundAxis(camera.up || { x: 0, y: 1, z: 0 }, axis, angle);

            if (camera.position?.set) {
                camera.position.set(
                    activeAxisLockDrag.target.x + rotatedOffset.x,
                    activeAxisLockDrag.target.y + rotatedOffset.y,
                    activeAxisLockDrag.target.z + rotatedOffset.z
                );
            } else {
                camera.position.x = activeAxisLockDrag.target.x + rotatedOffset.x;
                camera.position.y = activeAxisLockDrag.target.y + rotatedOffset.y;
                camera.position.z = activeAxisLockDrag.target.z + rotatedOffset.z;
            }
            if (camera.up?.set) {
                camera.up.set(rotatedUp.x, rotatedUp.y, rotatedUp.z);
            } else if (camera.up) {
                camera.up.x = rotatedUp.x;
                camera.up.y = rotatedUp.y;
                camera.up.z = rotatedUp.z;
            }
            controls.target?.set?.(
                activeAxisLockDrag.target.x,
                activeAxisLockDrag.target.y,
                activeAxisLockDrag.target.z
            );
            camera.lookAt?.(
                activeAxisLockDrag.target.x,
                activeAxisLockDrag.target.y,
                activeAxisLockDrag.target.z
            );
            controls.update?.();
            graphInstance.refresh?.();
            event.preventDefault();
            event.stopPropagation();
        });

        const finishPointer = event => {
            if (!activeAxisLockDrag) return;
            if (event.pointerId != null && event.pointerId !== activeAxisLockDrag.pointerId) return;
            container.releasePointerCapture?.(activeAxisLockDrag.pointerId);
            endAxisLockDrag();
        };
        container.addEventListener('pointerup', finishPointer);
        container.addEventListener('pointercancel', finishPointer);
    }

    function nextFrame() {
        return new Promise(resolve => requestAnimationFrame(() => resolve()));
    }

    async function nextFrames(count = 1) {
        for (let i = 0; i < count; i++) {
            await nextFrame();
        }
    }

    async function getExportDbBaseName() {
        if (exportDbBaseName) return exportDbBaseName;
        try {
            const cfg = await apiClient.get('/api/config');
            const rawPath = String(cfg?.db_path || '').trim();
            const fileName = rawPath.split(/[\\/]/).pop() || '';
            const stem = fileName.replace(/\.[^.]+$/, '') || 'kgx';
            exportDbBaseName = stem.replace(/[^A-Za-z0-9._-]+/g, '_');
        } catch (_) {
            exportDbBaseName = 'kgx';
        }
        return exportDbBaseName;
    }

    function parseTimelineOrderValue(value) {
        if (typeof value === 'number' && Number.isFinite(value)) return value;
        if (typeof value !== 'string') return null;
        const text = value.trim();
        if (!text) return null;
        if (/^-?\d+(\.\d+)?$/.test(text)) return Number(text);
        const parsedDate = Date.parse(text);
        return Number.isFinite(parsedDate) ? parsedDate : null;
    }

    function sanitizeTimelineFieldName(field) {
        return /^[A-Za-z0-9_]+$/.test(field || '') ? field : '';
    }

    function getTimelineProfileFieldCandidates(profile) {
        return profile?.order?.field_candidates || [];
    }

    function normalizeTimelineToken(value) {
        return String(value || '')
            .trim()
            .toLowerCase()
            .replace(/\s+/g, '_');
    }

    function getTimelineFieldAliases(fieldToken) {
        const normalized = normalizeTimelineToken(fieldToken);
        const aliases = new Set([normalized]);
        if (normalized === 'award_year') aliases.add('year');
        if (normalized === 'publication_year') aliases.add('year');
        if (normalized === 'event_year') aliases.add('year');
        if (normalized === 'award_date') aliases.add('date');
        return aliases;
    }

    function stableHash(text) {
        const value = String(text || '');
        let hash = 0;
        for (let i = 0; i < value.length; i++) {
            hash = ((hash << 5) - hash + value.charCodeAt(i)) | 0;
        }
        return Math.abs(hash);
    }

    function humanizeSlugName(value) {
        return String(value || '')
            .split(/[-_]+/)
            .filter(Boolean)
            .map(part => {
                if (/^[a-z]$/i.test(part)) return part.toUpperCase();
                if (/^[a-z]\.$/i.test(part)) return part.toUpperCase();
                return part.charAt(0).toUpperCase() + part.slice(1);
            })
            .join(' ');
    }

    function getNodeDisplayName(node) {
        const rawName = String(node?.name || '').trim();
        const rawId = String(node?.id || '').trim();
        if (!rawName) return rawId ? humanizeSlugName(rawId) : '';
        if (!rawId) return rawName;
        const normalizedName = rawName.toLowerCase().replace(/\s+/g, '-');
        if (normalizedName === rawId.toLowerCase() && /^[a-z0-9._-]+$/i.test(rawId) && /[-_]/.test(rawId)) {
            return humanizeSlugName(rawId);
        }
        return rawName;
    }

    function getTimelineTagCategory(node) {
        const category = node?.metadata?.category;
        return typeof category === 'string' ? category.toLowerCase() : '';
    }

    function getTimelineNodeName(node) {
        return String(node?.name || node?.id || '').trim().toLowerCase();
    }

    function getTimelineFeaturedTopIds(profile) {
        return new Set(
            (profile?.featured_top_ids || [])
                .map(value => String(value || '').trim().toLowerCase())
                .filter(Boolean)
        );
    }

    function getTimelineBandStep(profile) {
        const bandStep = Number(profile?.band_step);
        return Number.isFinite(bandStep) && bandStep > 0 ? bandStep : TIMELINE_Z_BAND_STEP;
    }

    function getTimelineClusteringValue(profile, key, fallback = 100) {
        const value = Number(profile?.clustering?.[key]);
        if (!Number.isFinite(value)) return fallback;
        return Math.max(40, Math.min(220, value));
    }

    function timelineBandBounds(centerZ, profile, jitter = TIMELINE_Z_MICRO_JITTER) {
        const bandStep = getTimelineBandStep(profile);
        const bounded = Math.min(Math.abs(jitter), bandStep * 0.5);
        return {
            center: centerZ,
            min: centerZ - bounded,
            max: centerZ + bounded,
        };
    }

    function getTimelineLayerZ(node, profile, anchorType) {
        const typeName = String(node.type || '').toLowerCase();
        if (node.type === anchorType) return profile?.anchors?.z ?? DEFAULT_TIMELINE_ANCHOR_Z;
        const profileLayer = profile?.layers?.[node.type] || profile?.layers?.[typeName];
        const bandStep = getTimelineBandStep(profile);
        if (profileLayer && Number.isFinite(profileLayer.z)) {
            const layerZ = Number(profileLayer.z);
            const scaleWithBandStep = profileLayer.scale_with_band_step !== false;
            return scaleWithBandStep ? layerZ * (bandStep / TIMELINE_Z_BAND_STEP) : layerZ;
        }
        const family = getHierarchyTypeFamily(node, getTimelineTagCategory(node));
        if (family === 'person') return TIMELINE_PERSON_Z;
        if (family === 'organization') return TIMELINE_ORGANIZATION_Z;
        if (family === 'publication') return 180;
        if (family === 'artifact' || family === 'other') return 220;
        if (/(tag|topic|keyword|category)/.test(typeName)) {
            const category = getTimelineTagCategory(node);
            if (category === 'core') return TIMELINE_ORGANIZATION_Z + (bandStep * 4);
            if (category === 'domain') return TIMELINE_ORGANIZATION_Z + (bandStep * 3);
            if (category === 'field') return TIMELINE_ORGANIZATION_Z + (bandStep * 2);
            return TIMELINE_ORGANIZATION_Z + (bandStep * 1);
        }
        return 180;
    }

    function getTimelineTagBandCenter(profile, band) {
        const bandStep = getTimelineBandStep(profile);
        if (band === 'core') return TIMELINE_ORGANIZATION_Z + (bandStep * 5);
        if (band === 'top') return TIMELINE_ORGANIZATION_Z + (bandStep * 4);
        if (band === 'domain') return TIMELINE_ORGANIZATION_Z + (bandStep * 3);
        if (band === 'field') return TIMELINE_ORGANIZATION_Z + (bandStep * 2);
        return TIMELINE_ORGANIZATION_Z + (bandStep * 1);
    }

    function isTimelineTagLike(nodeType) {
        const typeName = String(nodeType || '').toLowerCase();
        return /(tag|topic|keyword|category)/.test(typeName);
    }

    function isHierarchyCoreTag(node, tagCategory = '') {
        return isTimelineTagLike(node?.type) && String(tagCategory || '').toLowerCase() === 'core';
    }

    function getHierarchyTypeFamily(node, tagCategory = '') {
        const typeName = String(node?.type || '').toLowerCase();
        const explicitAliases = hierarchySettings.profile?.type_aliases || {};
        const aliasTypeName = String(
            explicitAliases[node?.type]
            || explicitAliases[typeName]
            || typeName
        ).toLowerCase();
        const explicitFamilies = hierarchySettings.profile?.type_families || {};
        const explicitFamily = explicitFamilies[node?.type] || explicitFamilies[typeName] || explicitFamilies[aliasTypeName];
        if (explicitFamily) return String(explicitFamily).toLowerCase();
        if (isTimelineTagLike(aliasTypeName)) {
            if (tagCategory === 'domain') return 'tag-domain';
            if (tagCategory === 'field') return 'tag-field';
            if (tagCategory === 'core') return 'tag-domain';
            return 'tag-topic';
        }
        if (/(organization|institution|center|department|lab|laboratory|company|group)/.test(aliasTypeName)) return 'organization';
        if (/(person|author|researcher|scientist|scholar|inventor)/.test(aliasTypeName)) return 'person';
        if (/(publication|paper|article|book|journal|report)/.test(aliasTypeName)) return 'publication';
        if (/(award|prize|event|grant|patent|project|dataset|tool|software|acknowledg|credit)/.test(aliasTypeName)) return 'artifact';
        return 'other';
    }

    function getHierarchyBandIndex(node, tagCategory = '') {
        const family = getHierarchyTypeFamily(node, tagCategory);
        if (family === 'organization') return 0;
        if (family === 'provenance') return 0;
        if (family === 'person') return 1;
        if (family === 'backbone' || family === 'core') return 1;
        if (family === 'publication' || family === 'artifact' || family === 'other') return 2;
        if (family === 'comparative') return 2;
        if (family === 'measurement') return 3;
        if (family === 'tag-domain') return 3;
        if (family === 'ontology') return 4;
        if (family === 'tag-field') return 4;
        return 5;
    }

    function getHierarchyFamilySortKey(family) {
        if (family === 'organization') return 0;
        if (family === 'provenance') return 0;
        if (family === 'person') return 1;
        if (family === 'backbone' || family === 'core') return 1;
        if (family === 'publication') return 2;
        if (family === 'artifact') return 3;
        if (family === 'comparative') return 4;
        if (family === 'measurement') return 5;
        if (family === 'ontology') return 6;
        if (family === 'other') return 7;
        if (family === 'tag-domain') return 8;
        if (family === 'tag-field') return 9;
        if (family === 'tag-topic') return 10;
        return 11;
    }

    function buildHierarchyRelationClassSets(profile = hierarchySettings.profile) {
        const relationClasses = profile?.relation_classes || DEFAULT_HIERARCHY_RELATION_CLASSES;
        return {
            hierarchy: new Set((relationClasses.hierarchy || []).map(item => String(item || '').toUpperCase())),
            structural: new Set((relationClasses.structural || []).map(item => String(item || '').toUpperCase())),
            affiliation: new Set((relationClasses.affiliation || []).map(item => String(item || '').toUpperCase())),
            annotation: new Set((relationClasses.annotation || []).map(item => String(item || '').toUpperCase())),
            associative: new Set((relationClasses.associative || []).map(item => String(item || '').toUpperCase())),
        };
    }

    function resolveHierarchyProfile(profile = null, contract = null) {
        const merged = {
            ...(contract || {}),
            ...(profile || {}),
            relation_classes: {
                ...((contract || {}).relation_classes || {}),
                ...((profile || {}).relation_classes || {}),
            },
            type_families: {
                ...((contract || {}).type_families || {}),
                ...((profile || {}).type_families || {}),
            },
            type_aliases: {
                ...((contract || {}).type_aliases || {}),
                ...((profile || {}).type_aliases || {}),
            },
            type_levels: {
                ...((contract || {}).type_levels || {}),
                ...((profile || {}).type_levels || {}),
            },
            driver_direction_overrides: {
                ...((contract || {}).driver_direction_overrides || {}),
                ...((profile || {}).driver_direction_overrides || {}),
            },
            bands: {
                ...((contract || {}).bands || {}),
                ...((profile || {}).bands || {}),
            },
        };
        if (merged.annotation_driver_default === undefined) {
            merged.annotation_driver_default = (contract || {}).annotation_driver_default;
        }
        if (merged.strict_bands_default === undefined) {
            merged.strict_bands_default = (contract || {}).strict_bands_default;
        }
        return merged;
    }

    function classifyHierarchyRelation(relType, relationSets = null) {
        const rel = String(relType || '').toUpperCase();
        const sets = relationSets || buildHierarchyRelationClassSets();
        if (sets.hierarchy.has(rel)) {
            return { kind: 'hierarchy', weight: 1.9 };
        }
        if (sets.structural.has(rel)) {
            return { kind: 'structural', weight: 1.45 };
        }
        if (sets.annotation.has(rel)) {
            return { kind: 'annotation', weight: 1.15 };
        }
        if (sets.affiliation.has(rel)) {
            return { kind: 'affiliation', weight: 0.95 };
        }
        if (sets.associative.has(rel)) {
            return { kind: 'weak', weight: graphMode === 'explore' ? 0.18 : 0.32 };
        }
        return { kind: 'generic', weight: graphMode === 'explore' ? 0.35 : 0.5 };
    }

    function isStubLikeNode(node) {
        return /\(stub\)\s*$/i.test(String(node?._group || ''));
    }

    function summarizeAnchorTargets(anchorIds, targetById, xStep) {
        const targets = anchorIds
            .map(anchorId => targetById.get(anchorId))
            .filter(Boolean);
        if (targets.length === 0) return null;
        const xs = targets.map(target => target.x);
        return {
            x: xs.reduce((sum, value) => sum + value, 0) / xs.length,
            minX: Math.min(...xs),
            maxX: Math.max(...xs),
            span: Math.max(...xs) - Math.min(...xs),
            count: targets.length,
            global: targets.length >= 4 || (Math.max(...xs) - Math.min(...xs)) >= xStep * 2,
        };
    }

    function getTimelineBucketOffsets(bucket, options) {
        const { anchorTarget, layerZ, ids } = bucket;
        const {
            xStep,
            localXStep,
            yStep,
            targetById,
            visibleNeighborIds,
            nodeById,
            profile,
        } = options;
        const count = ids.length;
        if (count <= 0) return [];

        const offsets = [];
        const lineThreshold = 2;
        const bandStep = getTimelineBandStep(profile);
        const innerDensity = getTimelineClusteringValue(profile, 'inner_density', 100);
        const outerDensity = getTimelineClusteringValue(profile, 'outer_density', 100);
        const innerSpreadScale = Math.max(0.45, Math.min(1.8, 100 / innerDensity));
        const outerSpreadScale = Math.max(0.45, Math.min(1.8, 100 / outerDensity));
        const clusterSpacingScale = Math.max(0.55, Math.min(1.5, (innerSpreadScale + outerSpreadScale) * 0.5));
        const bandHeightFromAnchor = Math.max(0, layerZ - (anchorTarget.z || 0));
        const isFirstSecondaryBand = bandHeightFromAnchor <= (bandStep * 1.05);
        const useAnchorCore = bucket.bucketRole === 'direct' && isFirstSecondaryBand;
        const zSpan = bandStep * 0.5;
        const zMin = layerZ - (zSpan * 0.5);
        const zMax = layerZ + (zSpan * 0.5);
        const xRadius = Math.max(Math.min(localXStep * 0.14, 22), 10);
        const yRadiusBase = Math.max(yStep * (0.75 + Math.min(count, 12) * 0.06), yStep * 0.85);
        const yRadius = isFirstSecondaryBand ? (yRadiusBase * 0.72) : yRadiusBase;

        const bucketSet = new Set(ids);
        const positions = new Map();
        const siblingMinDistance = Math.max(Math.min(yStep * 0.52, 44), 24) * clusterSpacingScale;
        const siblingMinDistanceSq = siblingMinDistance * siblingMinDistance;
        const coreMinDistanceY = Math.max(Math.min(yStep * 0.52, 48), 28);
        const coreMinDistanceZ = Math.max(Math.min(bandStep * 0.16, 26), 14);
        const outerZSpan = bandStep * 0.4;
        const maxOuterX = Math.max(Math.min(localXStep * 0.26, 34), 16);
        const innerShellRadius = (bandStep * 0.25) * innerSpreadScale;
        const outerShellMinRadius = (bandStep * 0.025) * outerSpreadScale;
        const outerShellMaxRadius = (bandStep * 0.04) * outerSpreadScale;
        const outerShellMaxYFromInner = outerShellMaxRadius * 0.5;

        const getNeighborTarget = (neighborId) => {
            if (bucketSet.has(neighborId)) return positions.get(neighborId) || null;
            if (targetById.has(neighborId)) return targetById.get(neighborId);
            const neighborNode = nodeById.get(neighborId);
            if (neighborNode && !neighborNode.__hidden) {
                return {
                    x: Number.isFinite(neighborNode.x) ? neighborNode.x : anchorTarget.x,
                    y: Number.isFinite(neighborNode.y) ? neighborNode.y : anchorTarget.y,
                    z: Number.isFinite(neighborNode.z) ? neighborNode.z : layerZ,
                };
            }
            return null;
        };

        const visibleNeighborIdsByNode = new Map(ids.map(id => [
            id,
            visibleNeighborIds.get(id) || [],
        ]));
        const externalNeighborIdsByNode = new Map(ids.map(id => [
            id,
            visibleNeighborIdsByNode.get(id).filter(neighborId => !bucketSet.has(neighborId)),
        ]));
        const hasExternalNeighbors = [...externalNeighborIdsByNode.values()].some(neighborIds => neighborIds.length > 0);
        if (bucket.bucketRole === 'direct' && hasExternalNeighbors) {
            const directOffsets = ids.map((id, index) => {
                const neighborTargets = (externalNeighborIdsByNode.get(id) || [])
                    .map(neighborId => getNeighborTarget(neighborId))
                    .filter(Boolean);
                if (neighborTargets.length === 0) {
                    return {
                        x: 0,
                        y: (index - (ids.length - 1) / 2) * (yStep * 0.75),
                        z: 0,
                    };
                }
                const avgX = neighborTargets.reduce((sum, target) => sum + target.x, 0) / neighborTargets.length;
                const avgY = neighborTargets.reduce((sum, target) => sum + target.y, 0) / neighborTargets.length;
                return {
                    x: avgX - anchorTarget.x,
                    y: (avgY - anchorTarget.y) + ((index - (ids.length - 1) / 2) * Math.min(yStep * 0.35, 18)),
                    z: 0,
                };
            });
            return directOffsets;
        }
        if (count === 1 && hasExternalNeighbors) {
            const id = ids[0];
            const neighborTargets = (externalNeighborIdsByNode.get(id) || [])
                .map(neighborId => getNeighborTarget(neighborId))
                .filter(Boolean);
            if (neighborTargets.length > 0) {
                const avgX = neighborTargets.reduce((sum, target) => sum + target.x, 0) / neighborTargets.length;
                const avgY = neighborTargets.reduce((sum, target) => sum + target.y, 0) / neighborTargets.length;
                offsets.push({
                    x: avgX - anchorTarget.x,
                    y: avgY - anchorTarget.y,
                    z: 0,
                });
                return offsets;
            }
        }
        if (count <= lineThreshold && !hasExternalNeighbors) {
            for (let index = 0; index < count; index++) {
                const centeredIndex = index - (count - 1) / 2;
                offsets.push({
                    x: count === 1 ? 0 : (centeredIndex * Math.min(xRadius * 0.85, 16)),
                    y: centeredIndex * (yStep * 0.85),
                    z: 0,
                });
            }
            return offsets;
        }
        const directExternalNeighborCounts = new Map();
        ids.forEach((id) => {
            for (const neighborId of externalNeighborIdsByNode.get(id) || []) {
                const target = getNeighborTarget(neighborId);
                if (!target) continue;
                directExternalNeighborCounts.set(neighborId, (directExternalNeighborCounts.get(neighborId) || 0) + 1);
            }
        });
        const directExternalCenters = [...directExternalNeighborCounts.entries()]
            .map(([neighborId, neighborCount]) => ({ id: neighborId, count: neighborCount, target: getNeighborTarget(neighborId), node: nodeById.get(neighborId) }))
            .filter(item => item.target && item.node && !item.node.__hidden)
            .sort((a, b) => {
                const tagBiasA = isTimelineTagLike(a.node?.type) ? 1 : 0;
                const tagBiasB = isTimelineTagLike(b.node?.type) ? 1 : 0;
                if (tagBiasA !== tagBiasB) return tagBiasA - tagBiasB;
                const layerDeltaA = Math.abs((a.target?.z ?? layerZ) - layerZ);
                const layerDeltaB = Math.abs((b.target?.z ?? layerZ) - layerZ);
                if (layerDeltaA !== layerDeltaB) return layerDeltaA - layerDeltaB;
                if (b.count !== a.count) return b.count - a.count;
                return String(a.id).localeCompare(String(b.id));
            });
        const directExternalCenterById = new Map(directExternalCenters.map(item => [item.id, item]));
        const useExternalCenters = directExternalCenters.length > 0;

        const externalNeighborFrequency = new Map();
        ids.forEach((id) => {
            for (const neighborId of externalNeighborIdsByNode.get(id) || []) {
                const target = getNeighborTarget(neighborId);
                if (!target) continue;
                externalNeighborFrequency.set(neighborId, (externalNeighborFrequency.get(neighborId) || 0) + 1);
            }
        });

        let coreTarget = { x: anchorTarget.x, y: anchorTarget.y, z: layerZ };
        let dominantCoreTargets = [];
        if (externalNeighborFrequency.size > 0) {
            if (count === 1) {
                dominantCoreTargets = [...externalNeighborFrequency.entries()]
                    .map(([neighborId, countValue]) => ({ id: neighborId, count: countValue, target: getNeighborTarget(neighborId) }))
                    .filter(item => item.target);
                if (dominantCoreTargets.length > 0) {
                    coreTarget = {
                        x: dominantCoreTargets.reduce((sum, item) => sum + item.target.x, 0) / dominantCoreTargets.length,
                        y: dominantCoreTargets.reduce((sum, item) => sum + item.target.y, 0) / dominantCoreTargets.length,
                        z: dominantCoreTargets.reduce((sum, item) => sum + item.target.z, 0) / dominantCoreTargets.length,
                    };
                }
            } else {
            const maxCount = Math.max(...externalNeighborFrequency.values());
            const dominantThreshold = Math.max(2, Math.ceil(maxCount * 0.6));
            dominantCoreTargets = [...externalNeighborFrequency.entries()]
                .filter(([, countValue]) => countValue >= dominantThreshold)
                .map(([neighborId, countValue]) => ({ id: neighborId, count: countValue, target: getNeighborTarget(neighborId) }))
                .filter(item => item.target);
            if (dominantCoreTargets.length > 0) {
                coreTarget = {
                    x: dominantCoreTargets.reduce((sum, item) => sum + item.target.x, 0) / dominantCoreTargets.length,
                    y: dominantCoreTargets.reduce((sum, item) => sum + item.target.y, 0) / dominantCoreTargets.length,
                    z: dominantCoreTargets.reduce((sum, item) => sum + item.target.z, 0) / dominantCoreTargets.length,
                };
            }
            }
        }
        const externalCenterYDamping = (isFirstSecondaryBand && !useExternalCenters) ? 0.24 : 1;
        coreTarget = {
            x: Math.max(anchorTarget.x - maxOuterX * 0.4, Math.min(anchorTarget.x + maxOuterX * 0.4, coreTarget.x)),
            y: anchorTarget.y + ((coreTarget.y - anchorTarget.y) * externalCenterYDamping),
            z: Math.max(zMin + coreMinDistanceZ, Math.min(zMax - coreMinDistanceZ, coreTarget.z)),
        };
        dominantCoreTargets = dominantCoreTargets.map(item => ({
            ...item,
            target: {
                x: Math.max(anchorTarget.x - maxOuterX * 0.4, Math.min(anchorTarget.x + maxOuterX * 0.4, item.target.x)),
                y: anchorTarget.y + ((item.target.y - anchorTarget.y) * externalCenterYDamping),
                z: Math.max(zMin + coreMinDistanceZ, Math.min(zMax - coreMinDistanceZ, item.target.z)),
            },
        }));
        if (dominantCoreTargets.length === 0) {
            dominantCoreTargets = [{ id: bucket.anchorId, count: count, target: coreTarget }];
        }
        const dominantCoreTargetById = new Map(dominantCoreTargets.map(item => [item.id, item]));

        const typeBuckets = new Map();
        ids.forEach((id) => {
            const typeName = String(nodeById.get(id)?.type || 'other').toLowerCase();
            if (!typeBuckets.has(typeName)) typeBuckets.set(typeName, []);
            typeBuckets.get(typeName).push(id);
        });
        const orderedTypeGroups = [...typeBuckets.entries()].sort((a, b) => {
            if (a[1].length !== b[1].length) return a[1].length - b[1].length;
            return a[0].localeCompare(b[0]);
        });
        const singleTypeBucket = orderedTypeGroups.length === 1;
        const singleTypeExternalShell = false;
        const innerIds = singleTypeBucket
            ? [...ids]
            : (singleTypeExternalShell
                ? [...ids]
                : [...orderedTypeGroups[0][1]]);
        const innerIdSet = new Set(innerIds);
        const outerIds = ids.filter(id => !innerIdSet.has(id));
        const innerRingRadius = (bandStep * 0.15) * innerSpreadScale;
        const externalShellMinRadius = (bandStep * 0.12) * outerSpreadScale;
        const externalShellMaxRadius = (bandStep * 0.18) * outerSpreadScale;
        const innerRadiusY = (singleTypeBucket && isFirstSecondaryBand)
            ? Math.min(innerRingRadius * 0.08, yStep * 0.025)
            : (singleTypeBucket
                ? Math.min(innerRingRadius * 0.22, yStep * 0.08)
                : innerRingRadius);
        const innerRadiusZ = singleTypeBucket
            ? Math.max(coreMinDistanceZ + 6, Math.min(innerRingRadius * 1.28, bandStep * 0.22))
            : Math.max(coreMinDistanceZ + 4, Math.min(innerRingRadius * 1.02, bandStep * 0.18));
        const outerRadiusYMin = Math.max(innerRingRadius * 1.35, outerShellMinRadius * 0.92);
        const outerRadiusYMax = Math.min(yStep * 1.1, outerShellMaxRadius * 0.9);
        const outerRadiusZMin = Math.max(innerRadiusZ * 1.35, outerShellMinRadius * 0.56);
        const outerRadiusZMax = Math.min(outerZSpan * 0.5, outerShellMaxRadius * 0.6);
        const externalShellMaxYFromCore = Math.min(externalShellMaxRadius * 0.32, yStep * 0.12);

        const getPreferredExternalCenter = (id) => {
            if (useExternalCenters) {
                const nodeTypeName = String(nodeById.get(id)?.type || '').toLowerCase();
                const rankedNeighbors = [];
                for (const neighborId of (externalNeighborIdsByNode.get(id) || [])) {
                    const externalCenter = directExternalCenterById.get(neighborId);
                    if (externalCenter) {
                        const neighborTypeName = String(externalCenter.node?.type || '').toLowerCase();
                        rankedNeighbors.push({
                            id: neighborId,
                            externalCenter,
                            differentType: neighborTypeName !== nodeTypeName,
                            tagLike: isTimelineTagLike(neighborTypeName),
                        });
                    }
                }
                if (rankedNeighbors.length > 0) {
                    const differentTypeNonTag = rankedNeighbors.filter(item => item.differentType && !item.tagLike);
                    const differentTypeAny = rankedNeighbors.filter(item => item.differentType);
                    const preferredPool = differentTypeNonTag.length > 0
                        ? differentTypeNonTag
                        : (differentTypeAny.length > 0 ? differentTypeAny : rankedNeighbors);
                    preferredPool.sort((a, b) => {
                        if (a.externalCenter.count !== b.externalCenter.count) return b.externalCenter.count - a.externalCenter.count;
                        const layerDeltaA = Math.abs((a.externalCenter.target?.z ?? layerZ) - layerZ);
                        const layerDeltaB = Math.abs((b.externalCenter.target?.z ?? layerZ) - layerZ);
                        if (layerDeltaA !== layerDeltaB) return layerDeltaA - layerDeltaB;
                        return String(a.id).localeCompare(String(b.id));
                    });
                    if (preferredPool[0]?.externalCenter) {
                        return preferredPool[0].externalCenter;
                    }
                }
                return directExternalCenters[stableHash(`${bucket.anchorId}:${id}:external-core`) % directExternalCenters.length];
            }
            return null;
        };

        const getPreferredCore = (id) => {
            if (useAnchorCore) {
                return {
                    id: bucket.anchorId,
                    count,
                    target: {
                        x: anchorTarget.x,
                        y: anchorTarget.y,
                        z: layerZ,
                    },
                };
            }
            if (count === 1 && dominantCoreTargets.length > 0) {
                return {
                    id: '__bucket_center__',
                    count: dominantCoreTargets.length,
                    target: coreTarget,
                };
            }
            if (useExternalCenters) {
                const preferredExternalCenter = getPreferredExternalCenter(id);
                if (preferredExternalCenter) {
                    return preferredExternalCenter;
                }
            }
            const neighborCounts = new Map();
            for (const neighborId of (visibleNeighborIdsByNode.get(id) || [])) {
                const dominant = dominantCoreTargetById.get(neighborId);
                if (dominant) {
                    neighborCounts.set(neighborId, (neighborCounts.get(neighborId) || 0) + 1);
                }
            }
            if (neighborCounts.size > 0) {
                const bestNeighborId = [...neighborCounts.entries()]
                    .sort((a, b) => b[1] - a[1] || String(a[0]).localeCompare(String(b[0])))[0][0];
                return dominantCoreTargetById.get(bestNeighborId) || dominantCoreTargets[0];
            }
            return dominantCoreTargets[stableHash(`${bucket.anchorId}:${id}:core`) % dominantCoreTargets.length];
        };

        const preferredCoreById = new Map(ids.map(id => [id, getPreferredCore(id)]));
        const centerCompetitionPool = useExternalCenters ? directExternalCenters : dominantCoreTargets;
        const otherCoreTargetsById = new Map(ids.map(id => [
            id,
            centerCompetitionPool
                .filter(item => item.id !== preferredCoreById.get(id)?.id)
                .map(item => item.target),
        ]));
        const innerIdsByCoreId = new Map();
        innerIds.forEach((id) => {
            const coreId = preferredCoreById.get(id)?.id || '__default__';
            if (!innerIdsByCoreId.has(coreId)) innerIdsByCoreId.set(coreId, []);
            innerIdsByCoreId.get(coreId).push(id);
        });

        const keepNearestToOwnCore = (candidate, ownCoreTarget, otherCoreTargets) => {
            if (!ownCoreTarget || !otherCoreTargets || otherCoreTargets.length === 0) return candidate;
            const ownDistanceSq =
                ((candidate.x - ownCoreTarget.x) ** 2) * 1.35 +
                ((candidate.y - ownCoreTarget.y) ** 2) +
                ((candidate.z - ownCoreTarget.z) ** 2) * 0.95;
            let nearestOther = null;
            let nearestOtherDistanceSq = Infinity;
            for (const otherCoreTarget of otherCoreTargets) {
                const otherDistanceSq =
                    ((candidate.x - otherCoreTarget.x) ** 2) * 1.35 +
                    ((candidate.y - otherCoreTarget.y) ** 2) +
                    ((candidate.z - otherCoreTarget.z) ** 2) * 0.95;
                if (otherDistanceSq < nearestOtherDistanceSq) {
                    nearestOtherDistanceSq = otherDistanceSq;
                    nearestOther = otherCoreTarget;
                }
            }
            if (!nearestOther || ownDistanceSq <= nearestOtherDistanceSq * 0.92) return candidate;
            return {
                x: candidate.x + ((ownCoreTarget.x - nearestOther.x) * 0.16) + ((ownCoreTarget.x - candidate.x) * 0.22),
                y: candidate.y + ((ownCoreTarget.y - nearestOther.y) * 0.12) + ((ownCoreTarget.y - candidate.y) * 0.18),
                z: candidate.z + ((ownCoreTarget.z - nearestOther.z) * 0.12) + ((ownCoreTarget.z - candidate.z) * 0.18),
            };
        };

        const keepWithinShellRange = (candidate, centerTarget, minRadius, maxRadius) => {
            if (!centerTarget) return candidate;
            let dx = (candidate.x - centerTarget.x) * 1.2;
            let dy = candidate.y - centerTarget.y;
            let dz = (candidate.z - centerTarget.z) * 1.05;
            let distance = Math.sqrt((dx * dx) + (dy * dy) + (dz * dz));
            if (distance < 1e-4) {
                dx = minRadius;
                dy = 0;
                dz = 0;
                distance = Math.abs(minRadius);
            }
            const targetRadius = Math.max(minRadius, Math.min(maxRadius, distance));
            const scale = targetRadius / distance;
            return {
                x: centerTarget.x + ((dx * scale) / 1.2),
                y: centerTarget.y + (dy * scale),
                z: centerTarget.z + ((dz * scale) / 1.05),
            };
        };

        const keepYBoundToCenter = (candidate, centerTarget, maxYDelta) => {
            if (!centerTarget || !Number.isFinite(maxYDelta)) return candidate;
            return {
                x: candidate.x,
                y: Math.max(centerTarget.y - maxYDelta, Math.min(centerTarget.y + maxYDelta, candidate.y)),
                z: candidate.z,
            };
        };

        const keepOuterYBoundToInner = (candidate, innerTarget, maxYDelta = outerShellMaxYFromInner) => {
            return keepYBoundToCenter(candidate, innerTarget, maxYDelta);
        };

        const keepOutsideCoreRadius = (candidate, coreCenter, minRadius) => {
            if (!coreCenter) return candidate;
            let dx = (candidate.x - coreCenter.x) * 1.2;
            let dy = candidate.y - coreCenter.y;
            let dz = (candidate.z - coreCenter.z) * 1.05;
            let distance = Math.sqrt((dx * dx) + (dy * dy) + (dz * dz));
            if (distance >= minRadius) return candidate;
            if (distance < 1e-4) {
                dx = minRadius;
                dy = 0;
                dz = 0;
                distance = minRadius;
            }
            const scale = minRadius / distance;
            return {
                x: coreCenter.x + ((dx * scale) / 1.2),
                y: coreCenter.y + (dy * scale),
                z: coreCenter.z + ((dz * scale) / 1.05),
            };
        };

        const keepInnerAnchorBias = (candidate, innerCenter, strength = 0.22) => {
            if (!innerCenter) return candidate;
            return {
                x: candidate.x + ((innerCenter.x - candidate.x) * strength),
                y: candidate.y + ((innerCenter.y - candidate.y) * strength),
                z: candidate.z + ((innerCenter.z - candidate.z) * strength),
            };
        };

        const keepNearestToAssignedInner = (candidate, assignedInnerTarget, otherInnerTargets) => {
            if (!assignedInnerTarget || !otherInnerTargets || otherInnerTargets.length === 0) return candidate;
            const ownDistanceSq =
                ((candidate.x - assignedInnerTarget.x) ** 2) * 1.2 +
                ((candidate.y - assignedInnerTarget.y) ** 2) +
                ((candidate.z - assignedInnerTarget.z) ** 2) * 1.05;
            let nearestOther = null;
            let nearestOtherDistanceSq = Infinity;
            for (const otherInnerTarget of otherInnerTargets) {
                const otherDistanceSq =
                    ((candidate.x - otherInnerTarget.x) ** 2) * 1.2 +
                    ((candidate.y - otherInnerTarget.y) ** 2) +
                    ((candidate.z - otherInnerTarget.z) ** 2) * 1.05;
                if (otherDistanceSq < nearestOtherDistanceSq) {
                    nearestOtherDistanceSq = otherDistanceSq;
                    nearestOther = otherInnerTarget;
                }
            }
            if (!nearestOther || ownDistanceSq <= nearestOtherDistanceSq * 0.82) return candidate;
            return {
                x: candidate.x + ((assignedInnerTarget.x - nearestOther.x) * 0.22) + ((assignedInnerTarget.x - candidate.x) * 0.32),
                y: candidate.y + ((assignedInnerTarget.y - nearestOther.y) * 0.22) + ((assignedInnerTarget.y - candidate.y) * 0.3),
                z: candidate.z + ((assignedInnerTarget.z - nearestOther.z) * 0.2) + ((assignedInnerTarget.z - candidate.z) * 0.28),
            };
        };

        const keepSameSideOfCore = (candidate, coreCenter, innerCenter) => {
            if (!candidate || !coreCenter || !innerCenter) return candidate;
            const adjusted = { ...candidate };
            const axes = ['x', 'y', 'z'];
            for (const axis of axes) {
                const dir = innerCenter[axis] - coreCenter[axis];
                if (Math.abs(dir) < 1e-3) continue;
                const offset = adjusted[axis] - coreCenter[axis];
                if ((offset * dir) < 0) {
                    adjusted[axis] = coreCenter[axis] + (Math.abs(offset) * Math.sign(dir));
                }
            }
            const dirX = innerCenter.x - coreCenter.x;
            const dirY = innerCenter.y - coreCenter.y;
            const dirZ = innerCenter.z - coreCenter.z;
            const candidateDot =
                ((adjusted.x - coreCenter.x) * dirX) +
                ((adjusted.y - coreCenter.y) * dirY) +
                ((adjusted.z - coreCenter.z) * dirZ);
            if (candidateDot <= 0) {
                adjusted.x += dirX * 0.25;
                adjusted.y += dirY * 0.25;
                adjusted.z += dirZ * 0.25;
            }
            return adjusted;
        };

        const keepForwardOfInner = (candidate, coreCenter, innerCenter, minForwardDistance) => {
            if (!candidate || !coreCenter || !innerCenter) return candidate;
            const direction = normalizeVector({
                x: innerCenter.x - coreCenter.x,
                y: innerCenter.y - coreCenter.y,
                z: innerCenter.z - coreCenter.z,
            });
            const relative = {
                x: candidate.x - innerCenter.x,
                y: candidate.y - innerCenter.y,
                z: candidate.z - innerCenter.z,
            };
            const forward =
                (relative.x * direction.x) +
                (relative.y * direction.y) +
                (relative.z * direction.z);
            if (forward >= minForwardDistance) return candidate;
            const delta = minForwardDistance - forward;
            return {
                x: candidate.x + (direction.x * delta),
                y: candidate.y + (direction.y * delta),
                z: candidate.z + (direction.z * delta),
            };
        };

        const normalizeVector = (vector) => {
            const magnitude = Math.sqrt((vector.x ** 2) + (vector.y ** 2) + (vector.z ** 2));
            if (magnitude < 1e-6) return { x: 0, y: 1, z: 0 };
            return {
                x: vector.x / magnitude,
                y: vector.y / magnitude,
                z: vector.z / magnitude,
            };
        };

        const crossProduct = (a, b) => ({
            x: (a.y * b.z) - (a.z * b.y),
            y: (a.z * b.x) - (a.x * b.z),
            z: (a.x * b.y) - (a.y * b.x),
        });

        const getPrimaryInnerId = (id) => {
            const preferredCore = preferredCoreById.get(id);
            const sameCoreInnerIds = innerIdsByCoreId.get(preferredCore?.id || '__default__') || innerIds;
            const directInnerNeighbors = (visibleNeighborIdsByNode.get(id) || []).filter(neighborId => innerIdSet.has(neighborId));
            const innerNeighborPool = directInnerNeighbors.length > 0 ? directInnerNeighbors : sameCoreInnerIds;
            if (innerNeighborPool.length === 0) return null;
            return innerNeighborPool[stableHash(`${bucket.anchorId}:${id}:inner-primary`) % innerNeighborPool.length];
        };

        const getLiveInnerTarget = (innerId) => {
            if (!innerId) return null;
            return positions.get(innerId) || innerTargetById?.get(innerId) || null;
        };

        const getConnectedInnerIds = (id) => {
            const directInnerNeighbors = (visibleNeighborIdsByNode.get(id) || []).filter(neighborId => innerIdSet.has(neighborId));
            if (directInnerNeighbors.length > 0) return directInnerNeighbors;
            const primaryInnerId = assignedInnerIdByOuterId.get(id);
            return primaryInnerId ? [primaryInnerId] : [];
        };

        const getLiveInnerGroupTargets = (id) => getConnectedInnerIds(id)
            .map(innerId => getLiveInnerTarget(innerId))
            .filter(Boolean);

        const getLiveInnerGroupCenter = (id) => {
            const targets = getLiveInnerGroupTargets(id);
            if (targets.length === 0) {
                return getLiveInnerTarget(assignedInnerIdByOuterId.get(id)) || coreTarget;
            }
            return {
                x: targets.reduce((sum, target) => sum + target.x, 0) / targets.length,
                y: targets.reduce((sum, target) => sum + target.y, 0) / targets.length,
                z: targets.reduce((sum, target) => sum + target.z, 0) / targets.length,
            };
        };

        const placeInnerId = (id, index, total) => {
            const seed = stableHash(`${bucket.anchorId}:${layerZ}:inner:${id}:${index}`);
            const ownCore = preferredCoreById.get(id)?.target || coreTarget;
            if (singleTypeExternalShell) {
                const u = ((seed % 10000) / 10000);
                const v = ((Math.floor(seed / 10000) % 10000) / 10000);
                const radiusMix = ((Math.floor(seed / 100000000) % 10000) / 10000);
                const theta = u * 2 * Math.PI;
                const phi = Math.acos((2 * v) - 1);
                const radius = externalShellMinRadius + ((externalShellMaxRadius - externalShellMinRadius) * radiusMix);
                const candidate = {
                    x: Math.max(anchorTarget.x - maxOuterX, Math.min(anchorTarget.x + maxOuterX, ownCore.x + (Math.cos(theta) * Math.sin(phi) * radius * 0.72))),
                    y: ownCore.y + (Math.sin(theta) * Math.sin(phi) * radius * 0.28),
                    z: Math.max(zMin, Math.min(zMax, ownCore.z + (Math.cos(phi) * radius))),
                };
                return keepYBoundToCenter(keepWithinShellRange(
                    keepNearestToOwnCore(candidate, ownCore, otherCoreTargetsById.get(id)),
                    ownCore,
                    externalShellMinRadius,
                    externalShellMaxRadius
                ), ownCore, externalShellMaxYFromCore);
            }
            const baseAngle = (((index + 0.5) / Math.max(total, 1)) * 2 * Math.PI);
            const angle = baseAngle + (((seed % 42) - 21) * (Math.PI / 180));
            const xJitter = ((((Math.floor(seed / 97) % 1000) / 1000) * 2) - 1) * Math.max(Math.min(maxOuterX * 0.18, 5), 1.5);
            return keepWithinShellRange(keepNearestToOwnCore({
                x: ownCore.x + xJitter,
                y: ownCore.y + (Math.cos(angle) * innerRadiusY),
                z: Math.max(zMin, Math.min(zMax, ownCore.z + (Math.sin(angle) * innerRadiusZ))),
            }, ownCore, otherCoreTargetsById.get(id)), ownCore, innerRingRadius * 0.94, innerRingRadius * 1.04);
        };

        let innerTargetById = null;
        const assignedInnerIdByOuterId = new Map(outerIds.map(id => [id, getPrimaryInnerId(id)]));
        const outerIndexById = new Map(outerIds.map((id, index) => [id, index]));
        const buildDirectionalOuterTarget = (id, index, total) => {
            const seed = stableHash(`${bucket.anchorId}:${layerZ}:outer:${id}:${index}`);
            const assignedInnerId = assignedInnerIdByOuterId.get(id);
            const primaryInnerTarget = innerTargetById ? (getLiveInnerGroupCenter(id) || getLiveInnerTarget(assignedInnerId) || coreTarget) : coreTarget;
            const u = ((seed % 10000) / 10000);
            const v = ((Math.floor(seed / 10000) % 10000) / 10000);
            const radiusMix = ((Math.floor(seed / 100000000) % 10000) / 10000);
            const theta = u * 2 * Math.PI;
            const phi = Math.acos((2 * v) - 1);
            const radius = outerShellMinRadius + ((outerShellMaxRadius - outerShellMinRadius) * radiusMix);
            const offsetX = Math.cos(theta) * Math.sin(phi) * radius * 0.9;
            const offsetY = Math.sin(theta) * Math.sin(phi) * radius * 0.5;
            const offsetZ = Math.cos(phi) * radius;
            const seeded = {
                x: Math.max(anchorTarget.x - maxOuterX, Math.min(anchorTarget.x + maxOuterX, primaryInnerTarget.x + offsetX)),
                y: primaryInnerTarget.y + offsetY,
                z: Math.max(
                    layerZ - (outerZSpan * 0.5),
                    Math.min(layerZ + (outerZSpan * 0.5), primaryInnerTarget.z + offsetZ)
                ),
            };
            const shellPlaced = keepOuterYBoundToInner(
                keepWithinShellRange(seeded, primaryInnerTarget, outerShellMinRadius, outerShellMaxRadius),
                primaryInnerTarget
            );
            return keepNearestToAssignedInner(
                shellPlaced,
                primaryInnerTarget,
                innerIds
                    .filter(innerId => !getConnectedInnerIds(id).includes(innerId))
                    .map(innerId => getLiveInnerTarget(innerId))
                    .filter(Boolean)
            );
        };

        innerIds.forEach((id, index) => positions.set(id, placeInnerId(id, index, innerIds.length)));
        outerIds.forEach((id, index) => positions.set(id, buildDirectionalOuterTarget(id, index, outerIds.length)));
        innerTargetById = new Map(innerIds.map((id, index) => [id, placeInnerId(id, index, innerIds.length)]));

        const enforceCoreSpacing = (candidate, ownCoreTarget = coreTarget) => {
            let adjusted = { ...candidate };
            let dy = adjusted.y - ownCoreTarget.y;
            let dz = adjusted.z - ownCoreTarget.z;
            const normalizedDistance = Math.sqrt(
                (dy * dy) / Math.max(coreMinDistanceY * coreMinDistanceY, 1) +
                (dz * dz) / Math.max(coreMinDistanceZ * coreMinDistanceZ, 1)
            );
            if (normalizedDistance < 1) {
                if (normalizedDistance < 1e-4) {
                    dy = coreMinDistanceY;
                    dz = 0;
                }
                const scale = 1 / Math.max(normalizedDistance, 1e-4);
                adjusted.y = ownCoreTarget.y + (dy * scale);
                adjusted.z = ownCoreTarget.z + (dz * scale);
            }
            return adjusted;
        };

        for (let iteration = 0; iteration < 12; iteration++) {
            const nextPositions = new Map();
            ids.forEach((id) => {
                const current = positions.get(id);
                let nextX = current.x;
                let nextY = current.y;
                let nextZ = current.z;

                let repelX = 0;
                let repelY = 0;
                let repelZ = 0;
                ids.forEach((otherId) => {
                    if (otherId === id) return;
                    const other = positions.get(otherId);
                    const dx = current.x - other.x;
                    const dy = current.y - other.y;
                    const dz = current.z - other.z;
                    const idIsOuter = !innerIdSet.has(id);
                    const otherIsOuter = !innerIdSet.has(otherId);
                    const sameAssignedInner = idIsOuter
                        && otherIsOuter
                        && assignedInnerIdByOuterId.get(id)
                        && assignedInnerIdByOuterId.get(id) === assignedInnerIdByOuterId.get(otherId);
                    const samePreferredExternalCore = singleTypeExternalShell
                        && innerIdSet.has(id)
                        && innerIdSet.has(otherId)
                        && preferredCoreById.get(id)?.id
                        && preferredCoreById.get(id)?.id === preferredCoreById.get(otherId)?.id;
                    const desiredMinDistance = sameAssignedInner
                        ? (siblingMinDistance * 0.62)
                        : (singleTypeExternalShell && innerIdSet.has(id) && innerIdSet.has(otherId)
                            ? (samePreferredExternalCore ? siblingMinDistance * 0.58 : siblingMinDistance * 0.12)
                            : (idIsOuter && otherIsOuter ? siblingMinDistance * 1.18 : siblingMinDistance));
                    const desiredMinDistanceSq = desiredMinDistance * desiredMinDistance;
                    const distanceSq = (dx * dx * 1.5) + (dy * dy) + (dz * dz * 0.9);
                    if (distanceSq <= 0 || distanceSq >= desiredMinDistanceSq) return;
                    const distance = Math.sqrt(distanceSq);
                    const force = (desiredMinDistance - distance) / desiredMinDistance;
                    const repelScale = sameAssignedInner
                        ? 0.82
                        : (singleTypeExternalShell && innerIdSet.has(id) && innerIdSet.has(otherId)
                            ? (samePreferredExternalCore ? 0.72 : 0.04)
                            : (idIsOuter && otherIsOuter ? 1.26 : 1));
                    repelX += ((dx || 0.1) / Math.max(distance, 1)) * force * 8 * repelScale;
                    repelY += ((dy || 0.1) / Math.max(distance, 1)) * force * 14 * repelScale;
                    repelZ += ((dz || 0.1) / Math.max(distance, 1)) * force * 12 * repelScale;
                });

                if (innerIdSet.has(id)) {
                    const ringTarget = innerTargetById.get(id) || current;
                    const ownCore = preferredCoreById.get(id)?.target || coreTarget;
                    if (singleTypeExternalShell) {
                        nextX = current.x + repelX;
                        nextY = current.y + repelY;
                        nextZ = current.z + repelZ;
                        nextX += (ringTarget.x - nextX) * 0.38;
                        nextY += (ringTarget.y - nextY) * 0.42;
                        nextZ += (ringTarget.z - nextZ) * 0.34;
                    } else {
                        nextX = ringTarget.x + repelX * 0.35;
                        nextY = ringTarget.y + repelY;
                        nextZ = ringTarget.z + repelZ;
                    }
                    const boundedCandidate = {
                        x: Math.max(anchorTarget.x - maxOuterX, Math.min(anchorTarget.x + maxOuterX, nextX)),
                        y: Math.max(anchorTarget.y - yRadius * 1.15, Math.min(anchorTarget.y + yRadius * 1.15, nextY)),
                        z: Math.max(zMin, Math.min(zMax, nextZ)),
                    };
                    const bounded = singleTypeExternalShell
                        ? keepYBoundToCenter(keepWithinShellRange(
                            keepNearestToOwnCore(boundedCandidate, ownCore, otherCoreTargetsById.get(id)),
                            ownCore,
                            externalShellMinRadius,
                            externalShellMaxRadius
                        ), ownCore, externalShellMaxYFromCore)
                        : enforceCoreSpacing(keepNearestToOwnCore(boundedCandidate, ownCore, otherCoreTargetsById.get(id)), ownCore);
                    nextPositions.set(id, {
                        x: bounded.x,
                        y: bounded.y,
                        z: bounded.z,
                    });
                    return;
                }

                nextX += repelX;
                nextY += repelY;
                nextZ += repelZ;

                const shellTarget = buildDirectionalOuterTarget(id, outerIndexById.get(id) || 0, outerIds.length);
                nextX += (shellTarget.x - nextX) * 0.34;
                nextY += (shellTarget.y - nextY) * 0.3;
                nextZ += (shellTarget.z - nextZ) * 0.3;
                const assignedInnerTarget = getLiveInnerGroupCenter(id) || getLiveInnerTarget(assignedInnerIdByOuterId.get(id)) || shellTarget;
                const otherInnerTargets = innerIds
                    .filter(innerId => !getConnectedInnerIds(id).includes(innerId))
                    .map(innerId => getLiveInnerTarget(innerId))
                    .filter(Boolean);

                const bounded = {
                    x: Math.max(anchorTarget.x - maxOuterX, Math.min(anchorTarget.x + maxOuterX, nextX)),
                    y: Math.max(anchorTarget.y - yRadius * 1.15, Math.min(anchorTarget.y + yRadius * 1.15, nextY)),
                    z: Math.max(layerZ - (outerZSpan * 0.5), Math.min(layerZ + (outerZSpan * 0.5), nextZ)),
                };
                const shellBound = keepOuterYBoundToInner(
                    keepWithinShellRange(bounded, assignedInnerTarget, outerShellMinRadius, outerShellMaxRadius),
                    assignedInnerTarget
                );
                const spaced = keepNearestToAssignedInner(shellBound, assignedInnerTarget, otherInnerTargets);
                nextPositions.set(id, keepNearestToAssignedInner(
                    keepOuterYBoundToInner(
                        keepInnerAnchorBias(spaced, assignedInnerTarget, 0.2),
                        assignedInnerTarget
                    ),
                    assignedInnerTarget,
                    otherInnerTargets
                ));
            });
            ids.forEach(id => positions.set(id, nextPositions.get(id)));
        }

        ids.forEach((id) => {
            const position = positions.get(id);
            offsets.push({
                x: position.x - anchorTarget.x,
                y: position.y - anchorTarget.y,
                z: position.z - layerZ,
            });
        });
        return offsets;
    }

    function getTimelineHierarchyMapping(relType, sourceId, targetId) {
        const rel = String(relType || '').toUpperCase();
        if (rel === 'BROADER' || rel === 'PARENT_OF') {
            return { childId: sourceId, parentId: targetId };
        }
        if (rel === 'NARROWER' || rel === 'CHILD_OF') {
            return { childId: targetId, parentId: sourceId };
        }
        return null;
    }

    function formatTimelineOrderLabel(value) {
        if (value == null) return '';
        if (typeof value === 'number' && Number.isFinite(value)) return String(value);
        const text = String(value).trim();
        if (!text) return '';
        if (/^\d{4}$/.test(text)) return text;
        const isoDateMatch = text.match(/^(\d{4}-\d{2}-\d{2})/);
        if (isoDateMatch) return isoDateMatch[1];
        const isoYearMatch = text.match(/^(\d{4})-\d{2}-\d{2}/);
        if (isoYearMatch) return isoYearMatch[1];
        return text;
    }

    function formatTimelineAnchorLabel(values, fallbackValue) {
        const uniqueLabels = [...new Set(
            (Array.isArray(values) ? values : [values])
                .map(value => String(value || '').trim())
                .filter(Boolean)
        )];
        if (uniqueLabels.length === 1) return uniqueLabels[0];
        if (uniqueLabels.length > 1) return uniqueLabels.join(' / ');
        return formatTimelineOrderLabel(fallbackValue);
    }

    function chooseAnchorId(anchorIds, anchorInfoById, rule = 'strongest_then_earliest') {
        const entries = [...anchorIds.entries()];
        if (entries.length === 0) return null;
        const preferLatest = rule.includes('latest');
        entries.sort((a, b) => {
            if (b[1] !== a[1]) return b[1] - a[1];
            const aOrder = anchorInfoById.get(a[0])?.orderValue ?? 0;
            const bOrder = anchorInfoById.get(b[0])?.orderValue ?? 0;
            if (aOrder !== bOrder) return preferLatest ? bOrder - aOrder : aOrder - bOrder;
            return String(a[0]).localeCompare(String(b[0]));
        });
        return entries[0][0];
    }

    async function resolveTimelineSpec() {
        let options = { profile: null, candidates: [] };
        try {
            options = await apiClient.get('/api/layout/timeline/options');
        } catch (err) {
            console.warn('Timeline options fetch failed:', err.message);
        }

        const profile = timelineSettings.profile || options.profile || null;
        const candidates = options.candidates || [];
        let anchorType = timelineSettings.anchorType || profile?.anchor_type || '';
        let candidate = candidates.find(item => item.type === anchorType) || null;
        if (!candidate && candidates.length > 0) {
            candidate = candidates[0];
            anchorType = candidate.type;
        }

        const profileFieldCandidates = getTimelineProfileFieldCandidates(profile);
        let orderField = timelineSettings.orderField || profileFieldCandidates[0] || '';
        const candidateOrderFields = candidate?.order_fields || [];
        if (orderField && candidateOrderFields.length > 0) {
            const aliases = getTimelineFieldAliases(orderField);
            const matchedField = candidateOrderFields.find(item =>
                aliases.has(normalizeTimelineToken(item.field))
            );
            if (matchedField) {
                orderField = matchedField.field;
            }
        }
        if (!orderField && candidateOrderFields.length) {
            orderField = candidateOrderFields[0].field;
        }
        const orderFieldMeta = candidateOrderFields.find(item => item.field === orderField)
            || candidateOrderFields[0]
            || null;

        return { profile, anchorType, orderField, orderFieldMeta, candidates };
    }

    async function fetchTimelineAnchorValues(anchorType, orderField) {
        const safeField = sanitizeTimelineFieldName(orderField);
        if (!anchorType || !safeField) return [];
        const isColumnField = safeField === 'created_at' || safeField === 'updated_at';
        const valueExpr = isColumnField
            ? safeField
            : `json_extract(metadata, '$.${safeField}')`;
        const data = await apiClient.post('/api/query', {
            sql: `SELECT id, name, ${valueExpr} AS order_value
                  FROM entities
                  WHERE type = ? AND ${valueExpr} IS NOT NULL`,
            params: [anchorType],
        });
        return data.results || [];
    }

    function buildLinearFallbackAnchorContext(visibleNodes) {
        const sortedVisibleNodes = [...visibleNodes].sort((a, b) => {
            const aName = String(getTimelineNodeName(a) || '').toLowerCase();
            const bName = String(getTimelineNodeName(b) || '').toLowerCase();
            if (aName !== bName) return aName.localeCompare(bName);
            return String(a.id).localeCompare(String(b.id));
        });
        const personNodes = sortedVisibleNodes.filter(node =>
            getHierarchyTypeFamily(node, getTimelineTagCategory(node)) === 'person'
        );
        const orgNodes = sortedVisibleNodes.filter(node =>
            getHierarchyTypeFamily(node, getTimelineTagCategory(node)) === 'organization'
        );
        const nonTagNodes = sortedVisibleNodes.filter(node => !isTimelineTagLike(node.type));
        const anchorNodes = personNodes.length
            ? personNodes
            : orgNodes.length
                ? orgNodes
                : nonTagNodes.length
                    ? nonTagNodes
                    : sortedVisibleNodes;
        if (!anchorNodes.length) return null;

        const anchorInfoById = new Map();
        const assignedAnchorById = new Map();
        for (const [index, node] of anchorNodes.entries()) {
            anchorInfoById.set(node.id, {
                rawValue: getTimelineNodeName(node) || node.id,
                orderValue: index,
            });
            assignedAnchorById.set(node.id, node.id);
        }
        return {
            anchorInfoById,
            assignedAnchorById,
            directAnchorNeighbors: new Map(),
            isLinearFallback: true,
        };
    }

    async function fetchHierarchyEdges() {
        if (hierarchyEdgesCache) return hierarchyEdgesCache;
        try {
            const data = await apiClient.post('/api/query', {
                sql: `SELECT r.source_id,
                             r.target_id,
                             r.rel_type,
                             source.type AS source_type,
                             target.type AS target_type,
                             json_extract(source.metadata, '$.category') AS source_category,
                             json_extract(target.metadata, '$.category') AS target_category
                      FROM relationships r
                      JOIN entities source ON source.id = r.source_id
                      JOIN entities target ON target.id = r.target_id
                      WHERE r.rel_type IN ('BROADER', 'PARENT_OF', 'NARROWER', 'CHILD_OF')`,
                params: [],
            });
            hierarchyEdgesCache = data.results || [];
        } catch (err) {
            console.warn('Hierarchy edge query failed:', err.message);
            hierarchyEdgesCache = [];
        }
        return hierarchyEdgesCache;
    }

    async function ensureHierarchyOptions() {
        if (hierarchyOptionsCache) return hierarchyOptionsCache;
        try {
            hierarchyOptionsCache = await apiClient.get('/api/layout/hierarchy/options');
        } catch (err) {
            console.warn('Hierarchy options fetch failed:', err.message);
            hierarchyOptionsCache = { profile: null, contract: null };
        }
        return hierarchyOptionsCache;
    }

    async function applyTimelineLayout() {
        for (const node of allNodes) delete node.__timelineHidden;
        for (const edge of allEdges) delete edge.__timelineHidden;
        const spec = await resolveTimelineSpec();
        const profile = spec.profile || {};

        let anchorRows = [];
        let hierarchyRows = [];
        try {
            const hierarchyOptions = await ensureHierarchyOptions();
            if (!hierarchySettings.profile && (hierarchyOptions?.profile || hierarchyOptions?.contract)) {
                hierarchySettings.profile = resolveHierarchyProfile(
                    hierarchyOptions.profile || null,
                    hierarchyOptions.contract || null,
                );
            }
            hierarchyRows = await fetchHierarchyEdges();
            if (spec.anchorType && spec.orderField) {
                anchorRows = await fetchTimelineAnchorValues(spec.anchorType, spec.orderField);
            }
        } catch (err) {
            console.warn('Timeline anchor query failed:', err.message);
            graphInstance.d3ReheatSimulation();
            return;
        }

        const visibleNodeIds = new Set(allNodes.filter(n => !n.__hidden).map(n => n.id));
        let anchorInfoById = new Map();
        for (const row of anchorRows) {
            if (!visibleNodeIds.has(row.id)) continue;
            const parsedValue = parseTimelineOrderValue(row.order_value);
            if (!Number.isFinite(parsedValue)) continue;
            anchorInfoById.set(row.id, {
                label: String(row.name || row.id || '').trim(),
                rawValue: row.order_value,
                orderValue: parsedValue,
            });
        }
        let fallbackAnchorContext = null;
        if (anchorInfoById.size === 0) {
            fallbackAnchorContext = buildLinearFallbackAnchorContext(
                allNodes.filter(node => !node.__hidden)
            );
            if (fallbackAnchorContext?.anchorInfoById?.size) {
                anchorInfoById = fallbackAnchorContext.anchorInfoById;
            }
        }

        if (anchorInfoById.size === 0) {
            console.warn('Timeline: no usable anchor values or visible linear fallback nodes found');
            graphInstance.d3ReheatSimulation();
            return;
        }

        const hideUnanchored = (profile?.unanchored?.mode || 'hide_or_dim') === 'hide_or_dim';
        const direction = profile?.order?.direction === 'desc' ? 'desc' : 'asc';
        const anchorZ = Number.isFinite(profile?.anchors?.z) ? profile.anchors.z : DEFAULT_TIMELINE_ANCHOR_Z;
        const xStep = Number.isFinite(profile?.anchors?.x_step) ? profile.anchors.x_step : DEFAULT_TIMELINE_X_STEP;
        const localXStep = Math.max(60, Math.min(getTimelineBandStep(profile) * 0.55, 110));
        const yStep = Number.isFinite(profile?.anchors?.same_value_y_step)
            ? profile.anchors.same_value_y_step
            : DEFAULT_TIMELINE_Y_STEP;
        const sameValueStep = Number.isFinite(profile?.anchors?.same_value_x_step)
            ? profile.anchors.same_value_x_step
            : yStep;
        const anchorGroups = new Map();
        for (const [id, info] of anchorInfoById.entries()) {
            const key = String(info.orderValue);
            if (!anchorGroups.has(key)) {
                anchorGroups.set(key, { orderValue: info.orderValue, rawValue: info.rawValue, ids: [], labels: [] });
            }
            anchorGroups.get(key).ids.push(id);
            if (info.label) anchorGroups.get(key).labels.push(info.label);
        }

        const orderedGroups = [...anchorGroups.values()].sort((a, b) =>
            direction === 'desc' ? b.orderValue - a.orderValue : a.orderValue - b.orderValue
        );
        const minOrder = Math.min(...orderedGroups.map(group => group.orderValue));
        const maxOrder = Math.max(...orderedGroups.map(group => group.orderValue));
        const orderRange = maxOrder - minOrder || 1;
        const axisSpread = xStep * Math.max(orderedGroups.length - 1, 1);
        const targetById = new Map();
        timelineAnchorTargets = new Map();
        timelineAnchorLabelTargets = new Map();

        for (const [groupIndex, group] of orderedGroups.entries()) {
            const normalized = ((group.orderValue - minOrder) / orderRange) * axisSpread - axisSpread / 2;
            group.ids.sort();
            group.ids.forEach((id, index) => {
                const xOffset = (index - (group.ids.length - 1) / 2) * sameValueStep;
                targetById.set(id, { x: normalized + xOffset, y: 0, z: anchorZ, strength: 0.95, pinX: true, pinY: true, pinZ: true });
                timelineAnchorTargets.set(id, { x: normalized + xOffset, y: 0, z: anchorZ });
                anchorInfoById.get(id).target = { x: normalized + xOffset, y: 0, z: anchorZ };
            });
            const labelText = fallbackAnchorContext?.isLinearFallback
                ? String(group.rawValue || '').trim()
                : formatTimelineAnchorLabel(group.labels, group.rawValue ?? group.orderValue);
            if (labelText) {
                timelineAnchorLabelTargets.set(`${group.orderValue}:${groupIndex}`, {
                    x: normalized,
                    y: 0,
                    z: Number.isFinite(timelineSettings.anchorLabelZ) ? timelineSettings.anchorLabelZ : DEFAULT_TIMELINE_ANCHOR_LABEL_Z,
                    anchorIds: [...group.ids],
                    text: labelText,
                });
            }
        }

        const visibleEdges = allEdges.filter(e => !e.__hidden).map(e => ({
            source: typeof e.source === 'object' ? e.source.id : e.source,
            target: typeof e.target === 'object' ? e.target.id : e.target,
            rel_type: e.rel_type,
        }));
        const nodeById = new Map(allNodes.map(node => [node.id, node]));
        const visibleNeighborIds = new Map();
        for (const edge of visibleEdges) {
            if (!visibleNeighborIds.has(edge.source)) visibleNeighborIds.set(edge.source, []);
            if (!visibleNeighborIds.has(edge.target)) visibleNeighborIds.set(edge.target, []);
            visibleNeighborIds.get(edge.source).push(edge.target);
            visibleNeighborIds.get(edge.target).push(edge.source);
        }
        const anchorIds = new Set(anchorInfoById.keys());
        const assignedAnchorById = new Map(fallbackAnchorContext?.assignedAnchorById || []);
        if (!fallbackAnchorContext?.isLinearFallback) {
            for (const anchorId of anchorIds) assignedAnchorById.set(anchorId, anchorId);
        }

        const neighborBuckets = new Map();
        const directAnchorNeighbors = new Map();
        for (const [nodeId, anchorSet] of (fallbackAnchorContext?.directAnchorNeighbors || new Map()).entries()) {
            directAnchorNeighbors.set(nodeId, new Set(anchorSet));
        }
        const tagChildren = new Map();
        const tagParents = new Map();
        const hierarchyTagCategoryById = new Map();
        for (const edge of visibleEdges) {
            for (const [from, to] of [[edge.source, edge.target], [edge.target, edge.source]]) {
                if (!neighborBuckets.has(from)) neighborBuckets.set(from, []);
                neighborBuckets.get(from).push(to);
                if (anchorIds.has(to)) {
                    if (!directAnchorNeighbors.has(from)) directAnchorNeighbors.set(from, new Set());
                    directAnchorNeighbors.get(from).add(to);
                }
            }
        }
        for (const edge of hierarchyRows) {
            const hierarchy = getTimelineHierarchyMapping(edge.rel_type, edge.source_id, edge.target_id);
            const childType = edge.rel_type === 'NARROWER' || edge.rel_type === 'CHILD_OF'
                ? edge.target_type
                : edge.source_type;
            const parentType = edge.rel_type === 'NARROWER' || edge.rel_type === 'CHILD_OF'
                ? edge.source_type
                : edge.target_type;
            const childCategory = edge.rel_type === 'NARROWER' || edge.rel_type === 'CHILD_OF'
                ? edge.target_category
                : edge.source_category;
            const parentCategory = edge.rel_type === 'NARROWER' || edge.rel_type === 'CHILD_OF'
                ? edge.source_category
                : edge.target_category;
            if (hierarchy && isTimelineTagLike(childType) && isTimelineTagLike(parentType)) {
                if (!tagChildren.has(hierarchy.parentId)) tagChildren.set(hierarchy.parentId, new Set());
                tagChildren.get(hierarchy.parentId).add(hierarchy.childId);
                if (!tagParents.has(hierarchy.childId)) tagParents.set(hierarchy.childId, new Set());
                tagParents.get(hierarchy.childId).add(hierarchy.parentId);
                if (typeof childCategory === 'string' && childCategory) {
                    hierarchyTagCategoryById.set(hierarchy.childId, childCategory.toLowerCase());
                }
                if (typeof parentCategory === 'string' && parentCategory) {
                    hierarchyTagCategoryById.set(hierarchy.parentId, parentCategory.toLowerCase());
                }
            }
        }

        const primaryRule = profile?.assignment?.primary_anchor_rule || 'strongest_then_earliest';
        const visibleNonAnchorIds = allNodes
            .filter(node => !node.__hidden && !anchorIds.has(node.id) && !isTimelineTagLike(node.type))
            .map(node => node.id);

        for (let pass = 0; pass < 3; pass++) {
            let changed = false;
            for (const nodeId of visibleNonAnchorIds) {
                if (assignedAnchorById.has(nodeId)) continue;
                const counts = new Map();
                const neighbors = neighborBuckets.get(nodeId) || [];
                for (const neighborId of neighbors) {
                    const anchorId = assignedAnchorById.get(neighborId);
                    if (!anchorId) continue;
                    counts.set(anchorId, (counts.get(anchorId) || 0) + 1);
                }
                const chosenAnchorId = chooseAnchorId(counts, anchorInfoById, primaryRule);
                if (chosenAnchorId) {
                    assignedAnchorById.set(nodeId, chosenAnchorId);
                    changed = true;
                }
            }
            if (!changed) break;
        }

        const secondaryBuckets = new Map();
        const unanchoredBuckets = new Map();
        const floatingTagBuckets = new Map();
        const timelineHiddenNodeIds = new Set();
        const baseTagAnchorIds = new Map();
        const visibleTagNodes = allNodes.filter(node => !node.__hidden && !anchorIds.has(node.id) && isTimelineTagLike(node.type));
        for (const node of visibleTagNodes) {
            const tagAnchorIds = new Set(directAnchorNeighbors.get(node.id) || []);
            const neighbors = neighborBuckets.get(node.id) || [];
            for (const neighborId of neighbors) {
                const anchorId = assignedAnchorById.get(neighborId);
                if (anchorId) tagAnchorIds.add(anchorId);
            }
            baseTagAnchorIds.set(node.id, tagAnchorIds);
        }

        const tagAnchorMemo = new Map();
        const collectTagAnchorIds = (tagId, visiting = new Set()) => {
            if (tagAnchorMemo.has(tagId)) return tagAnchorMemo.get(tagId);
            if (visiting.has(tagId)) return new Set(baseTagAnchorIds.get(tagId) || []);
            visiting.add(tagId);
            const combined = new Set(baseTagAnchorIds.get(tagId) || []);
            for (const childId of (tagChildren.get(tagId) || [])) {
                for (const anchorId of collectTagAnchorIds(childId, visiting)) {
                    combined.add(anchorId);
                }
            }
            visiting.delete(tagId);
            tagAnchorMemo.set(tagId, combined);
            return combined;
        };
        const tagAnchorSummaryById = new Map();

        const featuredTopIds = getTimelineFeaturedTopIds(profile);
        for (const node of visibleTagNodes) {
            const anchorSummary = summarizeAnchorTargets([...collectTagAnchorIds(node.id)], targetById, xStep);
            if (!anchorSummary) {
                if (hideUnanchored) timelineHiddenNodeIds.add(node.id);
                continue;
            }
            tagAnchorSummaryById.set(node.id, anchorSummary);
            const baseLayerZ = getTimelineLayerZ(node, profile, spec.anchorType);
            const parentCount = (tagParents.get(node.id) || new Set()).size;
            const tagCategory = hierarchyTagCategoryById.get(node.id) || getTimelineTagCategory(node);
            const tagName = getTimelineNodeName(node);
            const parentIds = [...(tagParents.get(node.id) || [])];
            const parentNodes = parentIds.map(parentId => nodeById.get(parentId)).filter(Boolean);
            const parentNames = new Set(parentNodes.map(parent => String(parent.name || '').toLowerCase()));
            const parentCategories = new Set(
                parentIds
                    .map(parentId => hierarchyTagCategoryById.get(parentId) || getTimelineTagCategory(nodeById.get(parentId)))
                    .filter(Boolean)
            );
            let structuralBaseZ = baseLayerZ;
            let minLayerZ = baseLayerZ - TIMELINE_Z_MICRO_JITTER;
            let maxLayerZ = baseLayerZ + TIMELINE_Z_MICRO_JITTER;
            if (tagCategory === 'core') {
                const band = timelineBandBounds(getTimelineTagBandCenter(profile, 'core'), profile);
                structuralBaseZ = band.center;
                minLayerZ = band.min;
                maxLayerZ = band.max;
            } else if (featuredTopIds.has(tagName)) {
                const band = timelineBandBounds(getTimelineTagBandCenter(profile, 'top'), profile);
                structuralBaseZ = band.center;
                minLayerZ = band.min;
                maxLayerZ = band.max;
            } else if (tagCategory === 'domain' || parentCount === 0) {
                const band = timelineBandBounds(getTimelineTagBandCenter(profile, 'domain'), profile);
                structuralBaseZ = band.center;
                minLayerZ = band.min;
                maxLayerZ = band.max;
            } else if (tagCategory === 'field') {
                const band = timelineBandBounds(getTimelineTagBandCenter(profile, 'field'), profile);
                structuralBaseZ = band.center;
                minLayerZ = band.min;
                maxLayerZ = band.max;
            } else if (tagCategory === 'topic' || parentCategories.has('field') || parentCategories.has('domain')) {
                const band = timelineBandBounds(getTimelineTagBandCenter(profile, 'topic'), profile);
                structuralBaseZ = band.center;
                minLayerZ = band.min;
                maxLayerZ = band.max;
            } else {
                const band = timelineBandBounds(getTimelineTagBandCenter(profile, 'topic'), profile);
                structuralBaseZ = band.center;
                minLayerZ = band.min;
                maxLayerZ = band.max;
            }
            const layerZ = Math.max(minLayerZ, Math.min(maxLayerZ, structuralBaseZ));
            const bucketKey = `${Math.round(anchorSummary.x / Math.max(xStep, 1))}:${layerZ}`;
            if (!floatingTagBuckets.has(bucketKey)) {
                floatingTagBuckets.set(bucketKey, { x: anchorSummary.x, layerZ, minLayerZ, maxLayerZ, ids: [] });
            }
            floatingTagBuckets.get(bucketKey).ids.push(node.id);
        }

        for (const node of allNodes) {
            if (node.__hidden || anchorIds.has(node.id) || isTimelineTagLike(node.type)) continue;
            let assignedAnchorId = assignedAnchorById.get(node.id);
            if (!assignedAnchorId) {
                const tagNeighborCounts = new Map();
                const neighbors = neighborBuckets.get(node.id) || [];
                for (const neighborId of neighbors) {
                    if (!tagAnchorSummaryById.has(neighborId)) continue;
                    for (const anchorId of collectTagAnchorIds(neighborId)) {
                        tagNeighborCounts.set(anchorId, (tagNeighborCounts.get(anchorId) || 0) + 1);
                    }
                }
                const inheritedAnchorId = chooseAnchorId(tagNeighborCounts, anchorInfoById, primaryRule);
                if (inheritedAnchorId) {
                    assignedAnchorId = inheritedAnchorId;
                    assignedAnchorById.set(node.id, inheritedAnchorId);
                }
            }
            if (!assignedAnchorId) {
                const bucketKey = `${node.type || 'other'}:unanchored`;
                if (!unanchoredBuckets.has(bucketKey)) unanchoredBuckets.set(bucketKey, []);
                unanchoredBuckets.get(bucketKey).push(node.id);
                if (hideUnanchored) timelineHiddenNodeIds.add(node.id);
                continue;
            }
            const layerZ = getTimelineLayerZ(node, profile, spec.anchorType);
            const isDirectAnchorNeighbor = (directAnchorNeighbors.get(node.id) || new Set()).has(assignedAnchorId);
            const bucketRole = isDirectAnchorNeighbor ? 'direct' : 'indirect';
            const bucketKey = `${assignedAnchorId}:${layerZ}:${bucketRole}`;
            if (!secondaryBuckets.has(bucketKey)) {
                secondaryBuckets.set(bucketKey, { anchorId: assignedAnchorId, layerZ, bucketRole, ids: [] });
            }
            secondaryBuckets.get(bucketKey).ids.push(node.id);
        }

        const secondaryBucketsByAnchor = new Map();
        for (const bucket of secondaryBuckets.values()) {
            if (!secondaryBucketsByAnchor.has(bucket.anchorId)) secondaryBucketsByAnchor.set(bucket.anchorId, []);
            secondaryBucketsByAnchor.get(bucket.anchorId).push(bucket);
        }
        for (const [anchorId, buckets] of secondaryBucketsByAnchor.entries()) {
            const baseAnchorTarget = targetById.get(anchorId);
            if (!baseAnchorTarget) continue;
            const bandStep = getTimelineBandStep(profile);
            buckets.sort((a, b) => a.layerZ - b.layerZ);
            const centerIndex = (buckets.length - 1) / 2;
            buckets.forEach((bucket, index) => {
                const phase = (stableHash(`${anchorId}:${bucket.layerZ}`) % 360) * (Math.PI / 180);
                const isFirstSecondaryBand = (bucket.layerZ - baseAnchorTarget.z) <= (bandStep * 1.05);
                if (isFirstSecondaryBand && bucket.bucketRole === 'direct') {
                    bucket.anchorTarget = {
                        x: baseAnchorTarget.x,
                        y: baseAnchorTarget.y,
                        z: baseAnchorTarget.z,
                    };
                    return;
                }
                const yOffset = isFirstSecondaryBand
                    ? 0
                    : Math.sin(phase) * Math.min(yStep * 0.2, 16);
                bucket.anchorTarget = {
                    x: baseAnchorTarget.x,
                    y: baseAnchorTarget.y + yOffset,
                    z: baseAnchorTarget.z,
                };
            });
        }

        for (const bucket of secondaryBuckets.values()) {
            const anchorTarget = bucket.anchorTarget || targetById.get(bucket.anchorId);
            if (!anchorTarget) continue;
            bucket.ids.sort((a, b) => String(a).localeCompare(String(b)));
            bucket.ids.forEach((id, index) => {
                targetById.set(id, {
                    x: anchorTarget.x + (((index % 3) - 1) * 10),
                    y: anchorTarget.y + ((index - (bucket.ids.length - 1) / 2) * (yStep * 0.75)),
                    z: bucket.layerZ,
                    strength: 0.5,
                    pinX: true,
                    pinY: true,
                    pinZ: true,
                });
            });
        }

        const orderedSecondaryBuckets = [...secondaryBuckets.values()].sort((a, b) => {
            if (a.layerZ !== b.layerZ) return a.layerZ - b.layerZ;
            if (a.bucketRole !== b.bucketRole) return a.bucketRole === 'direct' ? -1 : 1;
            return String(a.anchorId).localeCompare(String(b.anchorId));
        });

        for (let pass = 0; pass < 3; pass++) {
            for (const bucket of orderedSecondaryBuckets) {
                const anchorTarget = bucket.anchorTarget || targetById.get(bucket.anchorId);
                if (!anchorTarget) continue;
                const offsets = getTimelineBucketOffsets(bucket, {
                    xStep,
                    localXStep,
                    yStep,
                    targetById,
                    visibleNeighborIds,
                    nodeById,
                    profile,
                });
                bucket.ids.forEach((id, index) => {
                    const offset = offsets[index] || { x: 0, y: 0, z: 0 };
                    targetById.set(id, {
                        x: anchorTarget.x + offset.x,
                        y: anchorTarget.y + offset.y,
                        z: bucket.layerZ + offset.z,
                        strength: 0.5,
                        pinX: true,
                        pinY: true,
                        pinZ: true,
                    });
                });
            }
        }

        for (const bucket of floatingTagBuckets.values()) {
            bucket.ids.sort((a, b) => String(a).localeCompare(String(b)));
            bucket.ids.forEach((id, index) => {
                const hash = stableHash(id);
                const xJitter = ((hash % 17) - 8) * 18;
                const yJitter = (((Math.floor(hash / 17)) % 15) - 7) * 15;
                const zJitter = (((Math.floor(hash / 289)) % 5) - 2) * (TIMELINE_Z_MICRO_JITTER / 4);
                const spreadY = (index - (bucket.ids.length - 1) / 2) * (yStep * 0.5);
                const z = Math.max(bucket.minLayerZ, Math.min(bucket.maxLayerZ, bucket.layerZ + zJitter));
                targetById.set(id, {
                    x: bucket.x + xJitter,
                    y: spreadY + yJitter,
                    z,
                    strength: 0.28,
                    pinX: true,
                    pinY: true,
                    pinZ: true,
                });
            });
        }

        if (!hideUnanchored) {
            for (const [bucketKey, ids] of unanchoredBuckets.entries()) {
                const [typeName] = bucketKey.split(':');
                const layerZ = getTimelineLayerZ({ type: typeName }, profile, spec.anchorType);
                ids.sort((a, b) => String(a).localeCompare(String(b)));
                ids.forEach((id, index) => {
                    targetById.set(id, {
                        x: 0,
                        y: (index - (ids.length - 1) / 2) * yStep,
                        z: layerZ,
                        strength: 0.28,
                        pinX: true,
                        pinY: true,
                        pinZ: true,
                    });
                });
            }
        }

        if (hideUnanchored && timelineHiddenNodeIds.size > 0) {
            for (const node of allNodes) {
                if (timelineHiddenNodeIds.has(node.id)) node.__timelineHidden = true;
            }
            for (const edge of allEdges) {
                const src = typeof edge.source === 'object' ? edge.source.id : edge.source;
                const tgt = typeof edge.target === 'object' ? edge.target.id : edge.target;
                edge.__timelineHidden = timelineHiddenNodeIds.has(src) || timelineHiddenNodeIds.has(tgt);
            }
        }

        refreshVisibility();
        emitProjectionSnapshot();

        // Snap visible nodes to their deterministic timeline targets before
        // enabling the force so switching from another layout doesn't bias
        // the initial timeline geometry.
        for (const node of allNodes) {
            if (!isNodeVisibleInCurrentLayout(node)) continue;
            const target = targetById.get(node.id);
            if (!target) continue;
            node.x = target.x;
            node.y = target.y;
            node.z = target.z;
            node.vx = 0;
            node.vy = 0;
            node.vz = 0;
            if (target.pinX) node.fx = target.x; else delete node.fx;
            if (target.pinY) node.fy = target.y; else delete node.fy;
            if (target.pinZ) node.fz = target.z; else delete node.fz;
        }

        graphInstance.d3Force('timeline', alpha => {
            for (const node of allNodes) {
                if (!isNodeVisibleInCurrentLayout(node)) continue;
                const target = targetById.get(node.id);
                if (!target) {
                    delete node.fx;
                    delete node.fy;
                    delete node.fz;
                    continue;
                }
                if (target.pinX) node.fx = target.x; else delete node.fx;
                if (target.pinY) node.fy = target.y; else delete node.fy;
                if (target.pinZ) node.fz = target.z; else delete node.fz;
                const strength = target.strength || 0.4;
                if (!target.pinX) {
                    node.vx = (node.vx || 0) + (target.x - (node.x || 0)) * strength * alpha;
                }
                if (!target.pinY) {
                    node.vy = (node.vy || 0) + (target.y - (node.y || 0)) * strength * alpha;
                }
                if (!target.pinZ) {
                    node.vz = (node.vz || 0) + (target.z - (node.z || 0)) * Math.min(strength, 0.45) * alpha;
                }
            }
        });
        graphInstance.d3ReheatSimulation();
        await nextFrames(2);
        updatePinnedLabelPositions();
    }

    async function applyHierarchicalLayout() {
        const hierarchyOptions = await ensureHierarchyOptions();
        const hierarchyProfile = resolveHierarchyProfile(
            hierarchySettings.profile || hierarchyOptions.profile || null,
            hierarchyOptions.contract || null,
        );
        if (hierarchyProfile) {
            hierarchySettings.profile = hierarchyProfile;
            if (hierarchySettings.strictBands !== true && hierarchySettings.strictBands !== false) {
                hierarchySettings.strictBands = hierarchyProfile.strict_bands_default === true;
            }
        }
        const hierarchyRows = await fetchHierarchyEdges();
        const visibleNodes = allNodes.filter(node => !node.__hidden);
        const visibleNodeIds = new Set(visibleNodes.map(node => node.id));
        const tagCategoryById = new Map();
        const tagParentsById = new Map();
        const tagChildrenById = new Map();
        const nodeById = new Map(allNodes.map(node => [node.id, node]));

        for (const row of hierarchyRows) {
            const hierarchy = getTimelineHierarchyMapping(row.rel_type, row.source_id, row.target_id);
            if (!hierarchy) continue;
            if (!visibleNodeIds.has(hierarchy.childId) && !visibleNodeIds.has(hierarchy.parentId)) continue;
            const childNode = nodeById.get(hierarchy.childId);
            const parentNode = nodeById.get(hierarchy.parentId);
            if (isTimelineTagLike(childNode?.type) && isTimelineTagLike(parentNode?.type)) {
                if (!tagParentsById.has(hierarchy.childId)) tagParentsById.set(hierarchy.childId, new Set());
                tagParentsById.get(hierarchy.childId).add(hierarchy.parentId);
                if (!tagChildrenById.has(hierarchy.parentId)) tagChildrenById.set(hierarchy.parentId, new Set());
                tagChildrenById.get(hierarchy.parentId).add(hierarchy.childId);
            }
            const childCategory = row.rel_type === 'NARROWER' || row.rel_type === 'CHILD_OF'
                ? row.target_category
                : row.source_category;
            const parentCategory = row.rel_type === 'NARROWER' || row.rel_type === 'CHILD_OF'
                ? row.source_category
                : row.target_category;
            if (typeof childCategory === 'string' && childCategory) {
                tagCategoryById.set(hierarchy.childId, childCategory.toLowerCase());
            }
            if (typeof parentCategory === 'string' && parentCategory) {
                tagCategoryById.set(hierarchy.parentId, parentCategory.toLowerCase());
            }
        }

        const levelSpacing = Number.isFinite(hierarchySettings.levelSpacing) ? hierarchySettings.levelSpacing : DEFAULT_HIERARCHY_LEVEL_SPACING;
        const clusterSeparation = Number.isFinite(hierarchySettings.typeSeparation) ? hierarchySettings.typeSeparation : DEFAULT_HIERARCHY_TYPE_SEPARATION;
        const shapeBlend = Math.max(0, Math.min(100, Number.isFinite(hierarchySettings.shapeBlend) ? hierarchySettings.shapeBlend : 0)) / 100;
        const coreOffset = Number.isFinite(hierarchySettings.coreOffset) ? hierarchySettings.coreOffset : 0;
        const structureMode = hierarchySettings.structureMode === 'linearized' ? 'linearized' : 'linear';
        const tagBandStep = Math.max(18, Math.min(levelSpacing * 0.22, 42));
        const tagMicroSpread = 4;
        const baseEntityZ = 0;
        const bandCfg = hierarchySettings.profile?.bands || {};
        const relationSets = buildHierarchyRelationClassSets(hierarchyProfile);
        const driverDirectionOverrides = hierarchySettings.profile?.driver_direction_overrides || {};

        const visibleEdges = allEdges
            .filter(edge => !edge.__hidden)
            .map(edge => {
                const sourceId = typeof edge.source === 'object' ? edge.source.id : edge.source;
                const targetId = typeof edge.target === 'object' ? edge.target.id : edge.target;
                return { edge, sourceId, targetId };
            })
            .filter(({ sourceId, targetId }) => visibleNodeIds.has(sourceId) && visibleNodeIds.has(targetId));

        function getHierarchyDriverEndpoints(edge, sourceId, targetId) {
            if (structureMode !== 'linearized') {
                return { source: sourceId, target: targetId };
            }
            const relType = String(edge?.rel_type || '').toUpperCase();
            const override = String(
                driverDirectionOverrides[edge?.rel_type]
                ?? driverDirectionOverrides[String(edge?.rel_type || '').toLowerCase()]
                ?? driverDirectionOverrides[relType]
                ?? ''
            ).toLowerCase();
            if (override === 'reverse') {
                return { source: targetId, target: sourceId };
            }
            return { source: sourceId, target: targetId };
        }

        const hierarchyDriverEdges = visibleEdges.filter(({ edge, sourceId, targetId }) => {
            const relation = classifyHierarchyRelation(edge.rel_type, relationSets);
            if (relation.kind === 'hierarchy' || relation.kind === 'structural' || relation.kind === 'affiliation') return true;
            if (relation.kind === 'annotation') {
                const sourceNode = nodeById.get(sourceId);
                const targetNode = nodeById.get(targetId);
                return isTimelineTagLike(sourceNode?.type) || isTimelineTagLike(targetNode?.type);
            }
            return false;
        }).map(({ edge, sourceId, targetId }) => {
            const endpoints = getHierarchyDriverEndpoints(edge, sourceId, targetId);
            return {
            source: endpoints.source,
            target: endpoints.target,
            rel_type: edge.rel_type,
            weight: edge.weight || 1,
            __hidden: false,
        }});
        const sparseDriverEdges = visibleEdges.filter(({ edge, sourceId, targetId }) => {
            const relation = classifyHierarchyRelation(edge.rel_type, relationSets);
            if (relation.kind !== 'weak') return true;
            const sourceNode = nodeById.get(sourceId);
            const targetNode = nodeById.get(targetId);
            if (!sourceNode || !targetNode) return true;
            if (isStubLikeNode(sourceNode) || isStubLikeNode(targetNode)) return true;
            return String(sourceNode.type || '') !== String(targetNode.type || '');
        }).map(({ edge, sourceId, targetId }) => {
            const endpoints = getHierarchyDriverEndpoints(edge, sourceId, targetId);
            return {
            source: endpoints.source,
            target: endpoints.target,
            rel_type: edge.rel_type,
            weight: edge.weight || 1,
            __hidden: false,
        }});
    function getHierarchyTargetYForFamily(family) {
            if (family === 'organization') return levelSpacing * Number(bandCfg.organization_y ?? 0.6);
            if (family === 'provenance') return levelSpacing * Number(bandCfg.organization_y ?? 0.6);
            if (family === 'person') return levelSpacing * Number(bandCfg.person_y ?? 0.0);
            if (family === 'backbone' || family === 'core') return levelSpacing * Number(bandCfg.person_y ?? 0.0);
            if (family === 'publication' || family === 'artifact' || family === 'other') {
                return levelSpacing * Number(bandCfg.publication_y ?? -0.65);
            }
            if (family === 'comparative') {
                return levelSpacing * Number(bandCfg.publication_y ?? -0.65);
            }
            if (family === 'measurement') return levelSpacing * Number(bandCfg.tag_field_y ?? -1.95);
            if (family === 'ontology') return levelSpacing * Number(bandCfg.tag_domain_y ?? -2.6);
            if (family === 'tag-domain') return levelSpacing * Number(bandCfg.tag_domain_y ?? -2.6);
            if (family === 'tag-field') return levelSpacing * Number(bandCfg.tag_field_y ?? -1.95);
            if (family === 'tag-topic') return levelSpacing * Number(bandCfg.tag_topic_y ?? -1.3);
            return 0;
        }

        function getHierarchyExplicitTypeLevel(node) {
            const typeAliases = hierarchySettings.profile?.type_aliases || {};
            const typeLevels = hierarchySettings.profile?.type_levels || {};
            const typeName = String(node?.type || '');
            const normalizedTypeName = typeName.toLowerCase();
            const aliasTypeName = String(
                typeAliases[typeName]
                ?? typeAliases[normalizedTypeName]
                ?? normalizedTypeName
            ).toLowerCase();
            const explicitLevel = typeLevels[typeName] ?? typeLevels[normalizedTypeName] ?? typeLevels[aliasTypeName];
            if (!Number.isFinite(Number(explicitLevel))) return null;
            return levelSpacing * Number(explicitLevel);
        }

        function isPromotedHierarchyRootTag(node, tagCategory = '') {
            const childIds = [...(tagChildrenById.get(node.id) || [])];
            const hasDomainChild = childIds.some(childId => {
                const childNode = nodeById.get(childId);
                const childCategory = tagCategoryById.get(childId) || getTimelineTagCategory(childNode);
                return String(childCategory || '').toLowerCase() === 'domain';
            });
            return (
                isHierarchyCoreTag(node, tagCategory)
                || (
                    isTimelineTagLike(node?.type)
                    && (tagParentsById.get(node.id)?.size || 0) === 0
                    && hasDomainChild
                )
            );
        }

        function getHierarchyTargetY(node, family, tagCategory = '') {
            const explicitTypeLevel = getHierarchyExplicitTypeLevel(node);
            if (explicitTypeLevel != null) return explicitTypeLevel;
            if (isPromotedHierarchyRootTag(node, tagCategory)) {
                const domainBand = Number(bandCfg.tag_domain_y ?? -2.6);
                const fieldBand = Number(bandCfg.tag_field_y ?? -1.95);
                const domainStep = domainBand - fieldBand;
                return levelSpacing * (domainBand + domainStep);
            }
            return getHierarchyTargetYForFamily(family);
        }

        function getHierarchyReversedTagTargetY(node, family, tagCategory = '') {
            const domainBand = Number(bandCfg.tag_domain_y ?? -2.6);
            const fieldBand = Number(bandCfg.tag_field_y ?? -1.95);
            const topicBand = Number(bandCfg.tag_topic_y ?? -1.3);
            const domainStep = domainBand - fieldBand;
            const promotedRootBand = domainBand + domainStep;
            const mirroredInnerBand = topicBand - domainStep;
            if (isPromotedHierarchyRootTag(node, tagCategory)) {
                return levelSpacing * mirroredInnerBand;
            }
            if (family === 'tag-domain') return levelSpacing * topicBand;
            if (family === 'tag-topic') return levelSpacing * domainBand;
            if (family === 'tag-field') return levelSpacing * fieldBand;
            return levelSpacing * promotedRootBand;
        }

        function getHierarchyTargetZForFamily(node, family) {
            const localSeed = stableHash(node.id);
            if (isTimelineTagLike(node.type)) {
                return (((localSeed % 11) - 5) * tagMicroSpread);
            }
            if (structureMode === 'linear') {
                return 0;
            }
            const familyBase = (
                family === 'organization' ? DEFAULT_HIERARCHY_TYPE_SEPARATION * 0.8
                : family === 'provenance' ? DEFAULT_HIERARCHY_TYPE_SEPARATION * 0.8
                : family === 'person' ? 0
                : (family === 'backbone' || family === 'core') ? 0
                : (family === 'publication' || family === 'artifact' || family === 'other') ? -DEFAULT_HIERARCHY_TYPE_SEPARATION * 0.8
                : family === 'comparative' ? -DEFAULT_HIERARCHY_TYPE_SEPARATION * 0.6
                : family === 'measurement' ? -DEFAULT_HIERARCHY_TYPE_SEPARATION * 0.25
                : family === 'ontology' ? DEFAULT_HIERARCHY_TYPE_SEPARATION * 0.35
                : 0
            );
            const localSpread = Math.max(4, Math.min(DEFAULT_HIERARCHY_TYPE_SEPARATION * 0.08, 18));
            return familyBase + (((localSeed % 13) - 6) * localSpread * 0.35);
        }

        refreshVisibility();
        emitProjectionSnapshot();

        // Cold-start Hierarchical from deterministic seeds so its shape does not
        // inherit coordinates or momentum from Force, Timeline, or a prior mode.
        for (const node of visibleNodes) {
            const seed = stableHash(node.id);
            const tagCategory = tagCategoryById.get(node.id) || getTimelineTagCategory(node);
            const family = getHierarchyTypeFamily(node, tagCategory);
            const yJitter = ((seed % 7) - 3) * 3;
            const zJitter = (((Math.floor(seed / 7)) % 7) - 3) * 2;
            delete node.fx;
            delete node.fy;
            delete node.fz;
            node.x = 0;
            node.y = getHierarchyTargetY(node, family, tagCategory) + yJitter;
            node.z = getHierarchyTargetZForFamily(node, family) + zJitter;
            node.vx = 0;
            node.vy = 0;
            node.vz = 0;
        }

        if (typeof graphInstance.dagLevelDistance === 'function') {
            graphInstance.dagLevelDistance(Math.max(80, levelSpacing));
        }

        if (structureMode === 'linear') {
            graphInstance.d3Force('hierarchy', null);
            graphInstance.d3Force('hierarchyPeers', null);
            graphInstance.d3Force('hierarchySparseHold', null);
            graphInstance.graphData({
                nodes: allNodes,
                links: visibleEdges.map(({ edge, sourceId, targetId }) => ({
                    source: sourceId,
                    target: targetId,
                    rel_type: edge.rel_type,
                    weight: edge.weight || 1,
                    __hidden: false,
                })),
            });
            graphInstance.dagMode('td');
            graphInstance.d3ReheatSimulation();
            return;
        }

        graphInstance.d3Force('hierarchyPeers', null);
        graphInstance.d3Force('hierarchySparseHold', null);
        graphInstance.graphData({
            nodes: allNodes,
            links: sparseDriverEdges.length ? sparseDriverEdges : allEdges,
        });
        graphInstance.dagMode('td');
        graphInstance.d3ReheatSimulation();
        await nextFrames(4);

        const dagBaselineXById = new Map();
        const dagBaselineZById = new Map();
        for (const node of visibleNodes) {
            dagBaselineXById.set(node.id, Number.isFinite(node.x) ? node.x : 0);
            dagBaselineZById.set(node.id, Number.isFinite(node.z) ? node.z : 0);
        }
        const baselineXValues = Array.from(dagBaselineXById.values());
        const minBaselineX = baselineXValues.length ? Math.min(...baselineXValues) : 0;
        const maxBaselineX = baselineXValues.length ? Math.max(...baselineXValues) : 0;
        const baselineCenterX = (minBaselineX + maxBaselineX) / 2;
        const baselineHalfSpan = Math.max(1, (maxBaselineX - minBaselineX) / 2);
        graphInstance.dagMode(null);
        graphInstance.graphData({ nodes: allNodes, links: allEdges });
        refreshVisibility();
        emitProjectionSnapshot();

        graphInstance.d3Force('hierarchy', alpha => {
            for (const node of visibleNodes) {
                const tagCategory = tagCategoryById.get(node.id) || getTimelineTagCategory(node);
                const family = getHierarchyTypeFamily(node, tagCategory);
                const explicitTypeLevel = getHierarchyExplicitTypeLevel(node);
                const baselineX = dagBaselineXById.get(node.id) ?? 0;
                const baselineZ = dagBaselineZById.get(node.id) ?? 0;
                let targetY = explicitTypeLevel != null ? explicitTypeLevel : getHierarchyTargetY(node, family, tagCategory);
                let targetZ = baselineZ;
                const yStrength = graphMode === 'display' ? 0.85 : 0.72;
                const zStrength = isTimelineTagLike(node.type)
                    ? (graphMode === 'display' ? 0.18 : 0.16)
                    : (graphMode === 'display' ? 0.22 : 0.18);
                const reverseTags = hierarchySettings.reverseTags === true;
                const strictBands = hierarchySettings.strictBands === true;
                const xStrength = graphMode === 'display' ? 0.22 : 0.18;
                const isCoreEntity = (family === 'person' || family === 'backbone' || family === 'core') && !isStubLikeNode(node);
                if (isCoreEntity) {
                    targetY += coreOffset;
                }
                if (reverseTags && isTimelineTagLike(node.type)) {
                    targetY = getHierarchyReversedTagTargetY(node, family, tagCategory);
                }

                if (structureMode === 'linearized') {
                    const linearZ = baseEntityZ + getHierarchyTargetZForFamily(node, family);
                    // Experimental Cluster Separation XZ-plane spreading is disabled for now.
                    // clusterSeparation is intentionally unused in the active Linear shape path.
                    if (shapeBlend > 0) {
                        const compactX = baselineCenterX + ((baselineX - baselineCenterX) * 0.78);
                        const compactStrength = xStrength * shapeBlend;
                        node.vx = (node.vx || 0) + (compactX - (node.x || 0)) * compactStrength * alpha;
                    }
                    targetZ = linearZ;
                    node.vz = (node.vz || 0) + (targetZ - (node.z || 0)) * zStrength * alpha;
                }
                const forceSemanticLevel = structureMode === 'linearized' && explicitTypeLevel != null;
                if (family === 'person' || forceSemanticLevel) {
                    node.fy = targetY;
                    node.y = targetY;
                    node.vy = 0;
                } else if (isTimelineTagLike(node.type)) {
                    node.fy = targetY;
                    node.y = targetY;
                    node.vy = 0;
                } else if (strictBands && (family === 'organization' || family === 'provenance' || family === 'publication' || family === 'artifact' || family === 'comparative' || family === 'measurement' || family === 'ontology' || family === 'other')) {
                    node.fy = targetY;
                    node.y = targetY;
                    node.vy = 0;
                } else {
                    delete node.fy;
                    node.vy = (node.vy || 0) + (targetY - (node.y || 0)) * yStrength * alpha;
                }
                if (family !== 'person' && family !== 'backbone' && family !== 'core' && !isTimelineTagLike(node.type) && !(strictBands && (family === 'organization' || family === 'provenance' || family === 'publication' || family === 'artifact' || family === 'comparative' || family === 'measurement' || family === 'ontology' || family === 'other'))) {
                    node.y = (node.y || 0) + (targetY - (node.y || 0)) * 0.2;
                }
            }
        });

        graphInstance.d3ReheatSimulation();
    }

    async function refreshTimelineIfActive() {
        if (currentLayout === 'timeline' && graphInstance) {
            await applyTimelineLayout();
        }
    }

    async function applyPostFilterUpdate() {
        if (currentLayout === 'timeline' && graphInstance) {
            await applyTimelineLayout();
            return;
        }
        if (currentLayout === 'td' && graphInstance) {
            await applyHierarchicalLayout();
            return;
        }
        refreshVisibility();
        emitProjectionSnapshot();
    }

    async function downloadCurrentViewPng() {
        if (!graphInstance) return;
        const liveWidth = container.clientWidth;
        const liveHeight = container.clientHeight;
        const renderer = graphInstance.renderer?.();
        const livePixelRatio = renderer?.getPixelRatio ? renderer.getPixelRatio() : 1;
        const exportPixelRatio = Math.max(livePixelRatio, EXPORT_RENDER_PIXEL_RATIO);

        try {
            graphInstance.nodeResolution(EXPORT_NODE_RESOLUTION);
            graphInstance.refresh();
            if (renderer?.setPixelRatio) renderer.setPixelRatio(exportPixelRatio);
            graphInstance.width(liveWidth).height(liveHeight);
            await nextFrames(2);
            updatePinnedLabelPositions();

            const sourceCanvas = renderer?.domElement;
            if (!sourceCanvas) return;

            renderer.render(graphInstance.scene(), graphInstance.camera());

            const exportCanvas = document.createElement('canvas');
            exportCanvas.width = liveWidth;
            exportCanvas.height = liveHeight;
            const ctx = exportCanvas.getContext('2d');
            if (!ctx) return;

            ctx.drawImage(sourceCanvas, 0, 0, liveWidth, liveHeight);

            const scaleX = 1;
            const scaleY = 1;
            const scale = 1;

            if (selectedMarkerEl.style.display !== 'none') {
                const markerX = parseFloat(selectedMarkerEl.style.left);
                const markerY = parseFloat(selectedMarkerEl.style.top);
                if (Number.isFinite(markerX) && Number.isFinite(markerY)) {
                    ctx.save();
                    ctx.strokeStyle = 'rgba(255,255,255,0.95)';
                    ctx.lineWidth = 2 * scale;
                    ctx.shadowColor = 'rgba(255,255,255,0.35)';
                    ctx.shadowBlur = 10 * scale;
                    ctx.beginPath();
                    ctx.arc(markerX * scaleX, markerY * scaleY, 11 * scale, 0, Math.PI * 2);
                    ctx.stroke();
                    ctx.restore();
                }
            }

            ctx.textBaseline = 'middle';
            ctx.textAlign = 'left';

            for (const el of pinnedLabelEls.values()) {
                if (el.style.display === 'none') continue;
                const left = parseFloat(el.style.left);
                const top = parseFloat(el.style.top);
                if (!Number.isFinite(left) || !Number.isFinite(top)) continue;

                const text = el.textContent || '';
                const fontSize = 11 * scale;
                const paddingX = 6 * scale;
                const paddingY = 2 * scale;
                const rectHeight = fontSize + paddingY * 2;
                ctx.font = `${fontSize}px sans-serif`;
                const textWidth = ctx.measureText(text).width;
                const rectWidth = textWidth + paddingX * 2;
                const rectX = (left * scaleX) - rectWidth / 2;
                const rectY = (top * scaleY) - rectHeight;

                ctx.save();
                ctx.shadowColor = 'rgba(0,0,0,0.2)';
                ctx.shadowBlur = 12 * scale;
                ctx.fillStyle = 'rgba(15, 15, 26, 0.82)';
                ctx.strokeStyle = 'rgba(255,255,255,0.12)';
                ctx.lineWidth = Math.max(1, scale);
                drawRoundedRect(ctx, rectX, rectY, rectWidth, rectHeight, rectHeight / 2);
                ctx.fill();
                ctx.stroke();
                ctx.restore();

                ctx.fillStyle = '#f4f6fb';
                ctx.font = `${fontSize}px sans-serif`;
                ctx.fillText(text, rectX + paddingX, rectY + rectHeight / 2 + 0.5 * scale);
            }

            const baseName = await getExportDbBaseName();
            const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
            const link = document.createElement('a');
            link.download = `${baseName}_graph_${timestamp}.png`;
            link.href = exportCanvas.toDataURL('image/png');
            link.click();
        } finally {
            graphInstance.nodeResolution(LIVE_NODE_RESOLUTION);
            graphInstance.refresh();
            if (renderer?.setPixelRatio) renderer.setPixelRatio(livePixelRatio);
            graphInstance.width(liveWidth).height(liveHeight);
            await nextFrames(2);
            updatePinnedLabelPositions();
        }
    }

    function clearHighlight() {
        if (highlightedIds.size === 0) return;
        highlightedIds.clear();
        if (graphInstance) {
            graphInstance.nodeColor(n => getNodeColor(n));
        }
        updatePinnedLabelPositions();
        eventBus.emit('node:highlight-cleared', {});
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
            .nodeVisibility(n => isNodeVisibleInCurrentLayout(n))
            .linkVisibility(l => isEdgeVisibleInCurrentLayout(l));
        // Recompute filtered degrees so node sizes reflect visible edges
        recomputeFilteredDegrees();
        if (communityMode) detectCommunities();
        refreshNodeAppearance();
        updatePinnedLabelPositions();
    }

    function visibleCounts() {
        return {
            visibleNodeCount: allNodes.filter(n => isNodeVisibleInCurrentLayout(n)).length,
            visibleEdgeCount: allEdges.filter(e => isEdgeVisibleInCurrentLayout(e)).length,
        };
    }

    function visibleNodesByType() {
        return allNodes
            .filter(node => isNodeVisibleInCurrentLayout(node))
            .reduce((acc, node) => {
                if (!acc[node.type]) acc[node.type] = [];
                acc[node.type].push({ id: node.id, name: node.name });
                return acc;
            }, {});
    }

    function availableNodesByType() {
        return allNodes
            .filter(node => !node.__baseHidden)
            .reduce((acc, node) => {
                if (!acc[node.type]) acc[node.type] = [];
                acc[node.type].push({ id: node.id, name: node.name });
                return acc;
            }, {});
    }

    function projectedEntityTypes() {
        return Object.entries(visibleNodesByType())
            .map(([type, nodes]) => ({ type, count: nodes.length }))
            .sort((a, b) => String(a.type).localeCompare(String(b.type)));
    }

    function availableEntityTypes() {
        return Object.entries(availableNodesByType())
            .map(([type, nodes]) => ({ type, count: nodes.length }))
            .sort((a, b) => String(a.type).localeCompare(String(b.type)));
    }

    function projectedRelTypeCounts() {
        return Object.fromEntries(
            allEdges.reduce((acc, edge) => {
                if (edge.__baseHidden) return acc;
                acc.set(edge.rel_type, (acc.get(edge.rel_type) || 0) + 1);
                return acc;
            }, new Map())
        );
    }

    function emitProjectionSnapshot(extra = {}) {
        const nodesByType = visibleNodesByType();
        for (const nodes of Object.values(nodesByType)) {
            nodes.sort((a, b) => String(a.name).localeCompare(String(b.name)));
        }
        eventBus.emit('graph:projection', {
            graphMode,
            projectionMode: projectionMeta?.mode || graphMode,
            projectionMeta: { ...projectionMeta },
            typeColors: { ...typeColorMap },
            entityTypes: projectedEntityTypes(),
            availableEntityTypes: availableEntityTypes(),
            relTypeCounts: projectedRelTypeCounts(),
            visibleNodesByType: nodesByType,
            ...extra,
        });
    }

    function isStubAuthoredContextEdge(edge, nodeById) {
        if (edge.rel_type !== 'AUTHORED') return false;
        const src = typeof edge.source === 'object' ? edge.source.id : edge.source;
        const tgt = typeof edge.target === 'object' ? edge.target.id : edge.target;
        const srcNode = nodeById[src];
        const tgtNode = nodeById[tgt];
        return srcNode?._group === 'person (stub)' || tgtNode?._group === 'person (stub)';
    }

    function recomputeHiddenFlags() {
        const nodeById = Object.fromEntries(allNodes.map(n => [n.id, n]));
        const relationSets = buildHierarchyRelationClassSets(hierarchySettings.profile);
        const annotationRelTypes = relationSets.annotation;
        const hierarchyRelTypes = relationSets.hierarchy;
        const structuralRelTypes = relationSets.structural;
        const annotationHiddenActive = [...annotationRelTypes].some(rt => hiddenRelTypes.has(rt));

        // Build: nodeId → set of rel_types it participates in
        const nodeRelTypes = {};
        for (const e of allEdges) {
            if (e.__baseHidden) continue;
            const src = typeof e.source === 'object' ? e.source.id : e.source;
            const tgt = typeof e.target === 'object' ? e.target.id : e.target;
            const srcNode = nodeById[src];
            const tgtNode = nodeById[tgt];
            if (srcNode?.__baseHidden || tgtNode?.__baseHidden) continue;
            if (hiddenRelTypes.has('COAUTHOR') && isStubAuthoredContextEdge(e, nodeById)) continue;
            (nodeRelTypes[src] = nodeRelTypes[src] || new Set()).add(e.rel_type);
            (nodeRelTypes[tgt] = nodeRelTypes[tgt] || new Set()).add(e.rel_type);
        }

        // Merge all filter sets into one lookup
        const filteredIds = filterSets.size > 0
            ? new Set([...filterSets.values()].flatMap(s => [...s]))
            : null;
        const hiddenGroupedIds = hiddenNodeGroups.size > 0
            ? new Set([...hiddenNodeGroups.values()].flatMap(s => [...s]))
            : null;

        // Mark nodes
        for (const n of allNodes) {
            if (n.__baseHidden) {
                n.__hidden = true;
                continue;
            }
            if (hiddenNodeTypes.has(n.type)) {
                n.__hidden = true;
                continue;
            }
            // Force-shown nodes (from Expand neighbors) override all filters except type filters
            if (forceShownIds.has(n.id)) {
                n.__hidden = false;
                continue;
            }
            if (hiddenNodeIds.has(n.id) || (filteredIds && filteredIds.has(n.id)) || (hiddenGroupedIds && hiddenGroupedIds.has(n.id))) {
                n.__hidden = true;
                continue;
            }
            // If the node has edges and ALL of them are of hidden rel types → hide it
            const rels = nodeRelTypes[n.id];
            if (rels && rels.size > 0 && hiddenRelTypes.size > 0) {
                n.__hidden = [...rels].every(rt => hiddenRelTypes.has(rt));
            } else if ((!rels || rels.size === 0) && hiddenRelTypes.size > 0) {
                n.__hidden = true;
            } else {
                n.__hidden = false;
            }
            if (!n.__hidden && rels && rels.size > 0) {
                const family = getHierarchyTypeFamily(n, getTimelineTagCategory(n));
                const mediatorLike = family === 'publication' || family === 'artifact' || family === 'other';
                const tagLike = family === 'tag-core' || family === 'tag-domain' || family === 'tag-field' || family === 'tag-topic';
                const visibleRels = [...rels].filter(rt => !hiddenRelTypes.has(rt));
                const hadStructuralHidden = [...rels].some(rt => structuralRelTypes.has(rt) && hiddenRelTypes.has(rt));
                const hadAnnotationHidden = [...rels].some(rt => annotationRelTypes.has(rt) && hiddenRelTypes.has(rt));
                const onlyAnnotationVisible = visibleRels.length > 0 && visibleRels.every(rt => annotationRelTypes.has(rt));
                const onlyHierarchyVisible = visibleRels.length > 0 && visibleRels.every(rt => hierarchyRelTypes.has(rt));
                if (mediatorLike && hadStructuralHidden && onlyAnnotationVisible) {
                    n.__hidden = true;
                } else if (tagLike && annotationHiddenActive && onlyHierarchyVisible) {
                    n.__hidden = true;
                }
            }
        }

        // Build node hidden lookup for link visibility
        const nodeHidden = {};
        for (const n of allNodes) nodeHidden[n.id] = n.__hidden;

        // Mark links — force-show links where both endpoints are visible
        for (const e of allEdges) {
            const src = typeof e.source === 'object' ? e.source.id : e.source;
            const tgt = typeof e.target === 'object' ? e.target.id : e.target;
            if (e.__baseHidden) {
                e.__hidden = true;
            } else if (hiddenRelTypes.has('COAUTHOR') && isStubAuthoredContextEdge(e, nodeById)) {
                e.__hidden = true;
            } else if (forceShownIds.has(src) || forceShownIds.has(tgt)) {
                // Show link only if neither endpoint ended up hidden
                e.__hidden = !!nodeHidden[src] || !!nodeHidden[tgt];
            } else {
                e.__hidden = hiddenRelTypes.has(e.rel_type)
                    || !!nodeHidden[src]
                    || !!nodeHidden[tgt]
                    || hiddenNodeIds.has(src)
                    || hiddenNodeIds.has(tgt)
                    || (filteredIds && (filteredIds.has(src) || filteredIds.has(tgt)));
            }
        }
    }

    // ---------- Data loading ----------

    async function loadGraph() {
        try {
            hierarchyEdgesCache = null;
            const presetParam = graphPreset ? `&preset=${encodeURIComponent(graphPreset)}` : '';
            const data = await apiClient.get(`/api/graph?mode=${graphMode}${presetParam}`);
            projectionMeta = data.projection || { mode: graphMode };
            const rawEdges = data.edges.map(e => ({
                source: e.source,
                target: e.target,
                rel_type: e.rel_type,
                weight: e.weight || 1,
            }));
            const deg = computeDegrees(data.nodes, rawEdges);
            allNodes = data.nodes.map(n => ({
                ...n,
                _group: n.group || n.type,
                _color: getTypeColor(n.group || n.type),
                _degree: deg[n.id] || 0,
                _filteredDegree: deg[n.id] || 0,
                __baseHidden: !!n.hidden,
                __hidden: !!n.hidden,
            }));
            allEdges = data.edges.map(e => ({
                source: e.source,
                target: e.target,
                rel_type: e.rel_type,
                weight: e.weight || 1,
                __baseHidden: !!e.hidden,
                __hidden: !!e.hidden,
            }));

            const nextPresetDefaultHiddenRelTypes = new Set(
                Array.isArray(projectionMeta?.default_hidden_rel_types)
                    ? projectionMeta.default_hidden_rel_types.map(item => String(item))
                    : []
            );
            for (const relType of presetDefaultHiddenRelTypes) {
                hiddenRelTypes.delete(relType);
            }
            for (const relType of nextPresetDefaultHiddenRelTypes) {
                hiddenRelTypes.add(relType);
            }
            presetDefaultHiddenRelTypes = nextPresetDefaultHiddenRelTypes;
            applyPresetForceTuning();

            // Do NOT clear user-hidden rel types here — preserve the user's filter state.
            // Recompute hidden flags so existing filters plus preset defaults apply to the new data.
            recomputeHiddenFlags();
            refreshVisibility();

            graphInstance.graphData({ nodes: allNodes, links: allEdges });

            // Count edge types from the actual graph data
            const relTypeCounts = projectedRelTypeCounts();

            const autoHiddenRelTypes = [];
            if (graphMode === 'display') {
                for (const [relType, count] of Object.entries(relTypeCounts)) {
                    if (relType === 'AUTHORED') continue;
                    if (count > 3000) {
                        hiddenRelTypes.add(relType);
                        autoHiddenRelTypes.push(relType);
                    }
                }
                if (autoHiddenRelTypes.length) {
                    recomputeHiddenFlags();
                    refreshVisibility();
                }
            }

            eventBus.emit('graph:loaded', {
                nodeCount: allNodes.length,
                edgeCount: allEdges.length,
                ...visibleCounts(),
                graphMode,
                projectionMode: projectionMeta?.mode || graphMode,
                projectionMeta: { ...projectionMeta },
                typeColors: { ...typeColorMap },
                relTypeCounts,
                autoHiddenRelTypes,
                visibleNodesByType: allNodes
                    .filter(n => !n.__hidden)
                    .reduce((acc, n) => {
                        if (!acc[n.type]) acc[n.type] = [];
                        acc[n.type].push({ id: n.id, name: n.name });
                        return acc;
                    }, {}),
            });
            emitProjectionSnapshot({ autoHiddenRelTypes });
            if (currentLayout === 'timeline') {
                applyTimelineLayout();
            } else if (currentLayout === 'td') {
                applyHierarchicalLayout();
            } else if (currentLayout === 'cluster') {
                applyClusterLayout();
            }
        } catch (err) {
            console.error('Failed to load graph:', err);
            container.innerHTML = `<div class="graph-error">Failed to load graph: ${err.message}</div>`;
        }
    }

    // ---------- Text labels ----------
    // Hover labels always use the built-in nodeLabel tooltip.
    // Pinned labels for selected/highlighted nodes are rendered in a lightweight HTML overlay.

    // ---------- Force graph init ----------

    function initForceGraph() {
        graphInstance = ForceGraph3D({
            rendererConfig: {
                antialias: true,
                preserveDrawingBuffer: true,
            },
        })(container)
            .width(container.clientWidth)
            .height(container.clientHeight)
            .backgroundColor('#0f0f1a')
            .onDagError(() => {}) // graph has cycles — suppress error, best-effort layout
            .nodeId('id')
            .nodeLabel(n => getNodeLabel(n))
            .nodeColor(n => getNodeColor(n))
            .nodeOpacity(0.9)
            .nodeVal(n => getNodeSize(n))
            .nodeRelSize(4)
            .nodeResolution(LIVE_NODE_RESOLUTION)
            // Visibility — initial callbacks; refreshVisibility() re-sets them to trigger updates
            .nodeVisibility(n => !n.__hidden)
            .linkVisibility(l => !l.__hidden)
            .linkColor(l => REL_COLORS[l.rel_type] || REL_COLORS.default)
            .linkOpacity(0.4)
            .linkWidth(l => l.weight > 1 ? Math.min(l.weight, 8) : 0.5)
            .linkDirectionalParticles(1)
            .linkDirectionalParticleWidth(l => highlightedIds.size > 0 ? 0 : 1)
            .onNodeClick(node => {
                eventBus.emit('node:selected', { id: node.id, type: node.type, name: getNodeDisplayName(node) });
            })
            .onNodeRightClick((node, event) => {
                event.preventDefault();
                eventBus.emit('node:right-clicked', {
                    id: node.id, type: node.type, name: getNodeDisplayName(node),
                    x: event.clientX, y: event.clientY,
                });
            })
            .onBackgroundClick(() => {
                clearHighlight();
            });

        container.appendChild(labelLayer);
        container.appendChild(axisGizmoEl);
        labelLayer.appendChild(selectedMarkerEl);
        initAxisGizmo();
        startAxisLockInteraction();
        startPinnedLabelLoop();

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
                controls.noRotate = false;
                controls.noZoom = false;
                controls.noPan = false;
                if (controls.mouseButtons) {
                    const mouse = globalThis.THREE?.MOUSE;
                    if (mouse) {
                        controls.mouseButtons.LEFT = mouse.ROTATE;
                        controls.mouseButtons.MIDDLE = mouse.DOLLY;
                        controls.mouseButtons.RIGHT = mouse.PAN;
                    }
                }
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

    // Toggle community coloring on/off
    eventBus.on('community:toggle', ({ enabled }) => {
        communityMode = enabled;
        if (communityMode) {
            detectCommunities();
        }
        refreshNodeAppearance();
        eventBus.emit('graph:loaded', {
            nodeCount: allNodes.length,
            edgeCount: allEdges.length,
            ...visibleCounts(),
            graphMode,
            projectionMode: projectionMeta?.mode || graphMode,
            typeColors: { ...typeColorMap },
            relTypeCounts: projectedRelTypeCounts(),
            autoHiddenRelTypes: [],
        });
        emitProjectionSnapshot();
    });

    eventBus.on('community:resolution', ({ value }) => {
        communityResolution = value;
        if (communityMode) {
            detectCommunities();
            refreshNodeAppearance();
        }
    });

    eventBus.on('graph:mode', ({ mode }) => {
        graphMode = mode;
        hiddenRelTypes.clear();
        eventBus.emit('edge:reset', {});
        loadGraph();
    });

    eventBus.on('graph:preset', ({ preset }) => {
        graphPreset = preset || '';
        if (graphMode !== 'explore') return;
        hiddenRelTypes.clear();
        eventBus.emit('edge:reset', {});
        loadGraph();
    });

    eventBus.on('timeline:settings', (settings) => {
        timelineSettings = {
            anchorType: settings.anchorType || '',
            orderField: settings.orderField || '',
            profile: settings.profile || null,
            showAnchorLabels: settings.showAnchorLabels !== false,
            anchorLabelZ: Number.isFinite(settings.anchorLabelZ) ? settings.anchorLabelZ : DEFAULT_TIMELINE_ANCHOR_LABEL_Z,
            anchorLabelRotate: Number.isFinite(settings.anchorLabelRotate) ? settings.anchorLabelRotate : 0,
            anchorLabelZRotate: Number.isFinite(settings.anchorLabelZRotate) ? settings.anchorLabelZRotate : 0,
        };
        if (currentLayout === 'timeline' && graphInstance) {
            applyTimelineLayout();
        }
    });

    eventBus.on('hierarchy:settings', (settings) => {
        hierarchySettings = {
            levelSpacing: Number.isFinite(settings.levelSpacing) ? settings.levelSpacing : DEFAULT_HIERARCHY_LEVEL_SPACING,
            typeSeparation: Number.isFinite(settings.typeSeparation) ? settings.typeSeparation : DEFAULT_HIERARCHY_TYPE_SEPARATION,
            shapeBlend: Number.isFinite(settings.shapeBlend) ? settings.shapeBlend : 0,
            coreOffset: Number.isFinite(settings.coreOffset) ? settings.coreOffset : 0,
            structureMode: settings.structureMode === 'linearized'
                ? 'linearized'
                : 'linear',
            reverseTags: settings.reverseTags === true,
            strictBands: settings.strictBands === true,
        };
        if (currentLayout === 'td' && graphInstance) {
            applyHierarchicalLayout();
        }
    });

    // Toggle pinned labels for the selected detail node or active highlighted set.
    eventBus.on('labels:toggle', ({ visible }) => {
        pinLabelsOn = visible;
        updatePinnedLabelPositions();
    });

    // ---- Event listeners ----

    eventBus.on('graph:refresh', () => loadGraph());
    eventBus.on('graph:export-png', () => {
        downloadCurrentViewPng();
    });
    eventBus.on('db:changed', () => loadGraph());

    eventBus.on('node:hide', async ({ id }) => {
        hiddenNodeIds.add(id);
        recomputeHiddenFlags();
        await applyPostFilterUpdate();
    });

    eventBus.on('node:show-all', async () => {
        hiddenNodeIds.clear();
        hiddenNodeTypes = new Set(DEFAULT_HIDDEN_NODE_TYPES);
        hiddenNodeGroups.clear();
        hiddenRelTypes.clear();
        for (const relType of presetDefaultHiddenRelTypes) {
            hiddenRelTypes.add(relType);
        }
        filterSets.clear();
        forceShownIds.clear();
        recomputeHiddenFlags();
        // Also tell sidebar to re-check all edge filters
        eventBus.emit('edge:reset', {});
        eventBus.emit('node:type-filter-reset', {});
        eventBus.emit('node:group-filter-reset', {});
        await applyPostFilterUpdate();
    });

    eventBus.on('node:type-filter', async ({ node_type, visible }) => {
        if (!node_type) return;
        if (visible) {
            hiddenNodeTypes.delete(node_type);
        } else {
            hiddenNodeTypes.add(node_type);
        }
        recomputeHiddenFlags();
        await applyPostFilterUpdate();
    });

    eventBus.on('node:group-filter', async ({ group_id, node_ids, visible }) => {
        if (!group_id) return;
        if (visible) {
            hiddenNodeGroups.delete(group_id);
        } else {
            hiddenNodeGroups.set(group_id, new Set((node_ids || []).map(String)));
        }
        recomputeHiddenFlags();
        await applyPostFilterUpdate();
    });

    // SQL filter: {filter_id, ids, active}
    // When active=true, ids is the list of node IDs to hide.
    // When active=false, remove the filter set.
    eventBus.on('node:sql-filter', async ({ filter_id, ids, active }) => {
        if (active && ids && ids.length > 0) {
            filterSets.set(filter_id, new Set(ids));
        } else {
            filterSets.delete(filter_id);
        }
        recomputeHiddenFlags();
        await applyPostFilterUpdate();
    });

    eventBus.on('node:highlight', ({ ids }) => {
        highlightedIds = new Set(ids);
        if (graphInstance) {
            graphInstance.nodeColor(n => getNodeColor(n));
        }
        updatePinnedLabelPositions();
    });

    eventBus.on('node:highlight-clear', () => {
        clearHighlight();
    });

    eventBus.on('node:highlight-neighbors', ({ id }) => {
        // Find neighbors from current graph edges and highlight them + the node itself
        const ids = new Set([id]);
        const directTagIds = new Set();
        for (const e of allEdges) {
            const src = typeof e.source === 'object' ? e.source.id : e.source;
            const tgt = typeof e.target === 'object' ? e.target.id : e.target;
            if (src === id) {
                ids.add(tgt);
                if (isTimelineTagLike(allNodes.find(n => n.id === tgt)?.type)) directTagIds.add(tgt);
            }
            if (tgt === id) {
                ids.add(src);
                if (isTimelineTagLike(allNodes.find(n => n.id === src)?.type)) directTagIds.add(src);
            }
        }
        (async () => {
            const hierarchyRows = await fetchHierarchyEdges();
            for (const edge of hierarchyRows) {
                const hierarchy = getTimelineHierarchyMapping(edge.rel_type, edge.source_id, edge.target_id);
                if (hierarchy && directTagIds.has(hierarchy.childId)) ids.add(hierarchy.parentId);
            }
            eventBus.emit('node:highlight', { ids: [...ids] });
        })();
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

    eventBus.on('node:selected', ({ id }) => {
        selectedNodeId = id || null;
        updatePinnedLabelPositions();
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
        // Find neighbors from the current graph edges (not raw DB)
        forceShownIds.add(id);
        hiddenNodeIds.delete(id);
        for (const e of allEdges) {
            const src = typeof e.source === 'object' ? e.source.id : e.source;
            const tgt = typeof e.target === 'object' ? e.target.id : e.target;
            if (src === id) { forceShownIds.add(tgt); hiddenNodeIds.delete(tgt); }
            if (tgt === id) { forceShownIds.add(src); hiddenNodeIds.delete(src); }
        }
        recomputeHiddenFlags();
        await applyPostFilterUpdate();
    });

    eventBus.on('edge:filter', async ({ rel_type, visible }) => {
        if (visible) {
            hiddenRelTypes.delete(rel_type);
        } else {
            hiddenRelTypes.add(rel_type);
        }
        recomputeHiddenFlags();
        await applyPostFilterUpdate();
    });

    // Clear any custom forces and unpin UMAP positions from a previous layout
    function clearCustomForces() {
        graphInstance.d3Force('cluster', null);
        graphInstance.d3Force('hierarchy', null);
        graphInstance.d3Force('hierarchyPeers', null);
        graphInstance.d3Force('hierarchySparseHold', null);
        graphInstance.d3Force('timeline', null);
        graphInstance.d3Force('umap', null);
        timelineAnchorTargets = new Map();
        timelineAnchorLabelTargets = new Map();
        for (const n of allNodes) {
            delete n.__timelineHidden;
            delete n.fx; delete n.fy; delete n.fz;
            n.vx = 0; n.vy = 0; n.vz = 0;
        }
        for (const e of allEdges) delete e.__timelineHidden;
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
            <button id="umap-compute-btn" title="Generate embeddings if needed and compute UMAP positions for this graph" style="
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

    function applyClusterLayout() {
        const types = [...new Set(allNodes.map(n => n._group))];
        const radius = 600;
        const typeCentroids = {};
        types.forEach((t, i) => {
            const angle = (i / Math.max(types.length, 1)) * 2 * Math.PI;
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
    }

    eventBus.on('layout:change', async ({ layout }) => {
        if (!graphInstance) return;
        currentLayout = layout;

        // Always clear custom forces and dag mode first
        clearCustomForces();
        graphInstance.dagMode(null);
        refreshVisibility();
        emitProjectionSnapshot();

        if (layout === 'force') {
            graphInstance.d3ReheatSimulation();

        } else if (layout === 'cluster') {
            applyClusterLayout();

        } else if (layout === 'timeline') {
            await applyTimelineLayout();

        } else if (layout === 'td') {
            await applyHierarchicalLayout();

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

    // ---- Shared graph settings ----
    eventBus.on('graph:settings:update', (settings) => {
        if (!graphInstance) return;

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

        graphInstance.refresh();
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
