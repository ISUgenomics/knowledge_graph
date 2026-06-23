/**
 * Sidebar component — dynamic entity browser.
 *
 * Auto-populates from the active graph projection — no hardcoded entity types.
 * Sections expand to show entity lists on click.
 * Search filters across all types.
 *
 * Incoming events:
 *   db:changed        {} — refresh counts
 *   graph:projection  {} — update lists and counts from graph data
 *
 * Outgoing events:
 *   sidebar:select  {id, type, name}
 *   edge:filter     {rel_type, visible}
 *   node:selected   {id, type, name}
 */
export function initSidebar(container, eventBus, apiClient) {
    const sqlPanel = document.getElementById('sidebar-sql-panel');
    let typeData = [];
    let relData = [];
    let expandedTypes = new Set();
    let searchQuery = '';
    let typeColorMap = {};
    let loadError = '';
    let defaultVisibleRelTypes = null;  // null = all visible by default
    let edgeDefaultsApplied = false;
    let graphVisibleNodesByType = {};
    let graphAvailableTypes = [];
    let previousRelTypes = new Set();
    let uncheckedNodeTypes = new Set();
    let uncheckedNodeGroups = new Set();
    let hierarchyTypeFamilies = {};
    let currentProjectionMeta = {};

    const GENOMICS_PRIMARY_TYPES = new Set(['gene', 'transcript', 'protein', 'orthogroup', 'bcn_gene']);
    const GENOMICS_SECONDARY_TYPES = new Set(['annotation_term', 'localization_call', 'prediction_call', 'expression_measure', 'contrast_definition', 'tag']);
    const SIDEBAR_HIDDEN_TYPES = new Set(['dataset']);
    const AGGREGATED_ENTITY_TYPES = new Set(['localization_call', 'prediction_call']);
    const GENOMICS_TYPE_ORDER = new Map([
        ['organism', 0],
        ['chromosome', 1],
        ['gene', 2],
        ['transcript', 3],
        ['protein', 4],
        ['orthogroup', 10],
        ['bcn_gene', 11],
        ['comparative_hit', 12],
        ['hgt_donor', 13],
        ['expression_measure', 20],
        ['contrast_definition', 21],
        ['localization_call', 22],
        ['prediction_call', 23],
        ['annotation_term', 30],
        ['tag', 31],
        ['dataset', 40],
    ]);
    const PRIMARY_TYPE_COLORS = [
        '#4e9af1', '#f14e63', '#4ecf68', '#d4b13f', '#a45cff',
        '#23b7d6', '#f19a3e', '#f05ba6', '#6d6cff', '#91c94a',
        '#cc6c46', '#35b59c', '#d85fd7', '#5e7fe0', '#b78833',
        '#db6546', '#4ba6c9', '#b3a63a', '#6c8f4c', '#9f6dcb',
    ];
    const PRIMARY_TYPE_COLOR_HINTS = {
        organism: 0,
        chromosome: 1,
        gene: 2,
        transcript: 3,
        protein: 4,
        orthogroup: 5,
        person: 6,
        organization: 7,
        publication: 8,
        artifact: 9,
        event: 10,
        award: 11,
        signal: 12,
        center: 13,
        dataset: 14,
    };
    const DERIVED_TYPE_COLOR_RULES = {
        bcn_gene: { from: 'gene', accent: '#f19a3e', accentMix: 0.24, whiteMix: 0.22 },
        comparative_hit: { from: 'protein', accent: '#f14e63', accentMix: 0.26, whiteMix: 0.2 },
        hgt_donor: { from: 'protein', accent: '#f19a3e', accentMix: 0.3, whiteMix: 0.18 },
        annotation_term: { from: 'protein', accent: '#a45cff', accentMix: 0.38, whiteMix: 0.28 },
        localization_call: { from: 'protein', accent: '#23b7d6', accentMix: 0.32, whiteMix: 0.14 },
        prediction_call: { from: 'protein', accent: '#d4b13f', accentMix: 0.36, whiteMix: 0.16 },
        expression_measure: { from: 'transcript', accent: '#f05ba6', accentMix: 0.32, whiteMix: 0.16 },
        contrast_definition: { from: 'transcript', accent: '#4ecf68', accentMix: 0.34, whiteMix: 0.22 },
        dataset: { from: 'organism', whiteMix: 0.62 },
    };
    const TAG_CATEGORY_COLORS = {
        broad: '#9aa4b2',
        core: '#9aa4b2',
        domain: '#b2bac5',
        field: '#c8cfd7',
        topic: '#dde2e8',
    };
    const TYPE_LABELS = {
        gene: 'gene',
        transcript: 'transcript',
        protein: 'protein',
        orthogroup: 'orthogroup',
        bcn_gene: 'ortholog gene',
        comparative_hit: 'homology hit',
        hgt_donor: 'hgt donor',
        annotation_term: 'annotation',
        localization_call: 'localization',
        prediction_call: 'prediction',
        expression_measure: 'expression',
        contrast_definition: 'dge contrast',
        tag: 'tag',
    };
    const TYPE_TOOLTIPS = {
        organism: 'Biological root organism for the current genomics graph.',
        dataset: 'Dataset provenance container for imported gene records.',
        chromosome: 'Chromosome or scaffold grouping genes by physical genomic locus.',
        gene: 'Gene records with genomic identity and locus-level attributes.',
        transcript: 'Transcript records with RNA sequence and transcript-level measurements.',
        protein: 'Protein records with annotation, localization, structure, and composition features.',
        orthogroup: 'Comparative gene-family groupings shared across related genes.',
        bcn_gene: 'External ortholog genes from H. schachtii, the beet cyst nematode (BCN), used for family-level comparison.',
        comparative_hit: 'Specific homology-hit records that capture matched proteins used as comparative evidence.',
        hgt_donor: 'Putative horizontal gene transfer donor accessions linked from proteins when donor-hit evidence is present.',
        annotation_term: 'Promoted annotation terms such as GO, InterPro, Pfam, SMART, FunFam, and PANTHER.',
        localization_call: 'Promoted deterministic localization values derived from localization columns and tools.',
        prediction_call: 'Promoted score- or binary-style prediction features derived from sequence-based tools.',
        expression_measure: 'Shared expression-stage or condition concepts linked directly to transcripts with per-edge values.',
        contrast_definition: 'Shared differential-expression contrast concepts linked directly to transcripts with per-edge values.',
        tag: 'Broad ontology and category tags used for grouping and hierarchy.',
    };
    const EDGE_LABELS = {
        HAS_TRANSCRIPT: 'transcribed',
        TRANSLATED_TO: 'translated',
        BELONGS_TO_ORTHOGROUP: 'orthogroup',
        HAS_BCN_MEMBER: 'ortholog member',
        HAS_BCN_HIT: 'BCN hit',
        HAS_NEMATODE_HIT: 'nematode hit',
        HAS_BROAD_HOMOLOGY_HIT: 'broad hit',
        HAS_HGT_DONOR: 'hgt donor',
        PROTEIN_ORTHOGROUP: 'protein orthogroup',
        HAS_ANNOTATION: 'annotated',
        HAS_LOCALIZATION: 'localized',
        HAS_PREDICTION: 'predicted',
        HAS_EXPRESSION_SUMMARY: 'expressed',
        HAS_EXPRESSION_CONTRAST: 'dge contrast',
        CONTRAST_SOURCE: 'contrast from',
        CONTRAST_TARGET: 'contrast to',
        MEASURED_AS: 'measure',
        CONTRAST_TYPE: 'contrast',
        IN_DATASET: 'in dataset',
        BROADER: 'broader',
        TAGGED: 'tagged',
    };
    const EDGE_TOOLTIPS = {
        HAS_TRANSCRIPT: 'Links a gene to its transcript records.',
        TRANSLATED_TO: 'Links a transcript to its translated protein record.',
        BELONGS_TO_ORTHOGROUP: 'Links a gene to a comparative orthogroup.',
        HAS_BCN_MEMBER: 'Links an orthogroup to an external ortholog gene from H. schachtii.',
        HAS_BCN_HIT: 'Links a protein to a specific H. schachtii homology hit.',
        HAS_NEMATODE_HIT: 'Links a protein to a broader nematode homology hit.',
        HAS_BROAD_HOMOLOGY_HIT: 'Links a protein to broader parasite or database homology evidence.',
        HAS_HGT_DONOR: 'Links a protein to a putative horizontal gene transfer donor accession when donor-hit evidence is present.',
        PROTEIN_ORTHOGROUP: 'Derived shortcut linking a protein to its gene orthogroup context through transcript and gene ownership.',
        HAS_ANNOTATION: 'Links a biological record to a promoted annotation concept.',
        HAS_LOCALIZATION: 'Links a biological record to a promoted deterministic localization concept.',
        HAS_PREDICTION: 'Links a biological record to a promoted score- or binary-style prediction concept.',
        HAS_EXPRESSION_SUMMARY: 'Links a transcript directly to a shared expression concept; the edge stores the transcript-specific value.',
        HAS_EXPRESSION_CONTRAST: 'Links a transcript directly to a shared differential-expression contrast; the edge stores the transcript-specific value.',
        CONTRAST_SOURCE: 'Links a contrast definition to the source-side expression summary in canonical left-to-right order.',
        CONTRAST_TARGET: 'Links a contrast definition to the target-side expression summary in canonical left-to-right order.',
        MEASURED_AS: 'Internal relation reserved for legacy or transitional expression modeling.',
        CONTRAST_TYPE: 'Internal relation reserved for legacy or transitional contrast modeling.',
        IN_DATASET: 'Links a record to the dataset it belongs to.',
        BROADER: 'Ontology hierarchy link from a narrower concept to a broader one.',
        TAGGED: 'Grouping link to a broad ontology or category tag.',
    };

    // Receive the active graph projection and mirror it exactly in the sidebar.
    eventBus.on('graph:projection', ({ typeColors, entityTypes, availableEntityTypes, relTypeCounts, autoHiddenRelTypes, visibleNodesByType, projectionMeta }) => {
        if (typeColors) {
            typeColorMap = { ...typeColors };
        }
        currentProjectionMeta = { ...(projectionMeta || {}) };
        if (entityTypes) {
            typeData = [...entityTypes];
        }
        if (availableEntityTypes) {
            graphAvailableTypes = [...availableEntityTypes];
        } else if (entityTypes) {
            graphAvailableTypes = [...entityTypes];
        }
        if (visibleNodesByType) {
            graphVisibleNodesByType = { ...visibleNodesByType };
        }
        if (relTypeCounts) {
            // Use edge types from the graph projection, not raw DB
            relData = Object.entries(relTypeCounts)
                .map(([rel_type, count]) => ({ rel_type, count }))
                .sort((a, b) => a.rel_type.localeCompare(b.rel_type));
            const currentRelTypes = new Set(relData.map(item => item.rel_type));
            for (const relType of currentRelTypes) {
                const defaultVisible = !defaultVisibleRelTypes || defaultVisibleRelTypes.has(relType);
                const newlyAppeared = !previousRelTypes.has(relType);
                if (newlyAppeared && defaultVisible) {
                    uncheckedRelTypes.delete(relType);
                }
            }
            previousRelTypes = currentRelTypes;
            edgeDefaultsApplied = false;
        }
        if (autoHiddenRelTypes && autoHiddenRelTypes.length) {
            for (const relType of autoHiddenRelTypes) {
                uncheckedRelTypes.add(relType);
            }
        }
        loadError = '';
        render();
    });

    let paletteIdx = 0;
    function normalizeColorTypeKey(type) {
        return String(type || '')
            .trim()
            .toLowerCase()
            .replace(/\s*\(.*?\)\s*$/g, '')
            .replace(/\s+/g, '_');
    }
    function hexToRgb(hex) {
        const normalized = String(hex || '').replace('#', '').trim();
        const value = normalized.length === 3
            ? normalized.split('').map(ch => ch + ch).join('')
            : normalized.padStart(6, '0').slice(0, 6);
        return {
            r: parseInt(value.slice(0, 2), 16),
            g: parseInt(value.slice(2, 4), 16),
            b: parseInt(value.slice(4, 6), 16),
        };
    }
    function rgbToHex({ r, g, b }) {
        return `#${[r, g, b].map(value => Math.max(0, Math.min(255, Math.round(value))).toString(16).padStart(2, '0')).join('')}`;
    }
    function mixHex(colorA, colorB, ratio = 0.5) {
        const a = hexToRgb(colorA);
        const b = hexToRgb(colorB);
        const mix = Math.max(0, Math.min(1, Number(ratio)));
        return rgbToHex({
            r: a.r + ((b.r - a.r) * mix),
            g: a.g + ((b.g - a.g) * mix),
            b: a.b + ((b.b - a.b) * mix),
        });
    }
    function lightenHex(color, ratio) {
        return mixHex(color, '#ffffff', ratio);
    }
    function deriveTypeColor(rule) {
        let color = getPrimaryColorForKey(rule.from);
        if (rule.accent) {
            color = mixHex(color, rule.accent, rule.accentMix ?? 0.3);
        }
        if (rule.whiteMix) {
            color = lightenHex(color, rule.whiteMix);
        }
        return color;
    }
    function getPrimaryColorForKey(key) {
        const normalizedKey = normalizeColorTypeKey(key);
        if (typeColorMap[normalizedKey]) return typeColorMap[normalizedKey];
        const hintedIndex = PRIMARY_TYPE_COLOR_HINTS[normalizedKey];
        if (Number.isInteger(hintedIndex)) {
            typeColorMap[normalizedKey] = PRIMARY_TYPE_COLORS[hintedIndex % PRIMARY_TYPE_COLORS.length];
            return typeColorMap[normalizedKey];
        }
        typeColorMap[normalizedKey] = PRIMARY_TYPE_COLORS[paletteIdx % PRIMARY_TYPE_COLORS.length];
        paletteIdx++;
        return typeColorMap[normalizedKey];
    }
    function resolveLegendTypeColor(type) {
        const normalizedType = normalizeColorTypeKey(type);
        if (normalizedType === 'tag') return TAG_CATEGORY_COLORS.broad;
        const derivedRule = DERIVED_TYPE_COLOR_RULES[normalizedType];
        if (derivedRule) return deriveTypeColor(derivedRule);
        const family = hierarchyTypeFamilies[normalizedType];
        if (family === 'ontology') return TAG_CATEGORY_COLORS.core;
        if (family === 'tag-domain') return TAG_CATEGORY_COLORS.domain;
        if (family === 'tag-field') return TAG_CATEGORY_COLORS.field;
        if (family === 'tag-topic') return TAG_CATEGORY_COLORS.topic;
        return getPrimaryColorForKey(normalizedType);
    }
    function typeColor(type) {
        const normalizedType = normalizeColorTypeKey(type);
        if (!typeColorMap[normalizedType]) {
            typeColorMap[normalizedType] = resolveLegendTypeColor(normalizedType);
        }
        return typeColorMap[normalizedType];
    }

    async function loadSidebarConfig() {
        try {
            try {
                const cfg = await apiClient.get('/api/config');
                const vis = cfg?.ui?.edge_filters_default_visible;
                if (Array.isArray(vis) && vis.length) {
                    defaultVisibleRelTypes = new Set(vis.map(x => String(x)));
                }
                hierarchyTypeFamilies = Object.fromEntries(
                    Object.entries(cfg?.ui?.layouts?.hierarchical?.type_families || {})
                        .map(([key, value]) => [String(key).toLowerCase(), String(value).toLowerCase()])
                );
            } catch (_) { /* optional */ }
            loadError = '';
            edgeDefaultsApplied = false;
            render();
        } catch (err) {
            loadError = err.message;
            container.innerHTML = `<div class="sidebar-error">Failed to load sidebar configuration: ${escHtml(err.message)}</div>`;
            console.error('Sidebar loadSidebarConfig failed', err);
        }
    }

    function entityList(type) {
        return graphVisibleNodesByType[type] || [];
    }

    function shouldAggregateEntityType(type) {
        return AGGREGATED_ENTITY_TYPES.has(type);
    }

    function filteredList(type) {
        const list = entityList(type);
        if (!searchQuery) return list;
        const q = searchQuery.toLowerCase();
        return list.filter(e => e.name.toLowerCase().includes(q));
    }

    function groupedEntityList(type) {
        const items = filteredList(type);
        if (!shouldAggregateEntityType(type)) {
            return items.map(item => ({ kind: 'single', ...item }));
        }
        const grouped = new Map();
        for (const item of items) {
            const key = String(item.name || '').trim();
            if (!grouped.has(key)) {
                grouped.set(key, { kind: 'group', name: key, ids: [], count: 0 });
            }
            const group = grouped.get(key);
            group.ids.push(item.id);
            group.count += 1;
        }
        return [...grouped.values()].sort((a, b) => String(a.name).localeCompare(String(b.name)));
    }

    function render() {
        const q = searchQuery;
        container.innerHTML = `
            ${loadError ? `<div class="sidebar-error">${escHtml(loadError)}</div>` : ''}
            <div class="sidebar-header">
                <div class="sidebar-panel-title" title="Browse entity lists, filter the graph, and focus a selected node">Browse and Focus</div>
                <div class="sidebar-toolbar">
                    <button class="sidebar-toolbar-btn" id="btn-sidebar-show-all"
                        title="Reset hidden nodes, filters, and temporary graph visibility changes">Reset</button>
                </div>
            </div>
            <div class="sidebar-search-wrap">
                <input id="sidebar-search" class="sidebar-search" title="Filter the loaded sidebar lists by name" placeholder="Filter sidebar lists…" value="${escHtml(q)}">
            </div>
            <div id="sidebar-sections"></div>
            <div class="sidebar-section" id="edge-filters-section">
                <div class="sidebar-section-header edge-filters-header">
                    <span class="sidebar-section-title">Edge Types</span>
                </div>
                <div id="edge-filters" class="edge-filters-list"></div>
            </div>
        `;

        if (sqlPanel) {
            sqlPanel.innerHTML = `
                <div class="sidebar-section" id="sql-filters-section">
                    <div class="sidebar-section-header sql-filters-header">
                        <span class="sidebar-section-title" title="Store reusable SQL queries, including ones saved from chat, and toggle them to hide matching nodes in the current graph view">SQL Filters</span>
                        <button class="sf-add-btn" id="sf-add-btn" title="Create a saved SQL filter that hides matching nodes from the graph">+</button>
                    </div>
                    <div id="sf-form" class="sf-form" style="display:none">
                        <input id="sf-name" class="sf-input" title="Name this saved SQL filter" placeholder="Filter name…">
                        <textarea id="sf-sql" class="sf-textarea" title="Enter a SQL query that returns entity IDs to hide" placeholder="SELECT id FROM entities WHERE type = 'tag'"></textarea>
                        <div class="sf-form-actions">
                            <button class="sf-btn-save" id="sf-save" title="Save this SQL filter to the sidebar">Save</button>
                            <button class="sf-btn-cancel" id="sf-cancel" title="Cancel creating this SQL filter">Cancel</button>
                        </div>
                    </div>
                    <div id="sf-list" class="sf-list"></div>
                </div>
            `;
        }

        // Search input
        const searchEl = container.querySelector('#sidebar-search');
        searchEl.addEventListener('input', e => {
            searchQuery = e.target.value;
            const sections = container.querySelector('#sidebar-sections');
            if (sections) renderSections(sections);
        });
        container.querySelector('#btn-sidebar-show-all')?.addEventListener('click', () => {
            eventBus.emit('node:show-all', {});
        });

        renderSections(container.querySelector('#sidebar-sections'));
        renderEdgeFilters(container.querySelector('#edge-filters'));
        renderSqlFilters();
        bindSqlFilterForm();
    }

    function getVisibleCountForType(type) {
        return (graphVisibleNodesByType[type] || []).length;
    }

    function displayTypeName(type) {
        return TYPE_LABELS[type] || type;
    }

    function typeTooltip(type) {
        return TYPE_TOOLTIPS[type] || `Toggle and browse the ${displayTypeName(type)} node layer.`;
    }

    function displayEdgeName(relType) {
        return EDGE_LABELS[relType] || String(relType).toLowerCase();
    }

    function edgeTooltip(relType) {
        return EDGE_TOOLTIPS[relType] || `Toggle visibility of ${displayEdgeName(relType)} relationships.`;
    }

    function isGenomicsLikeProjection() {
        const types = new Set(graphAvailableTypes.map(t => t.type));
        return ['gene', 'transcript', 'protein'].every(type => types.has(type));
    }

    function configuredTypeFamily(type) {
        return hierarchyTypeFamilies[String(type || '').toLowerCase()] || '';
    }

    function visibleTagGroups() {
        return Array.isArray(currentProjectionMeta?.visible_tag_groups)
            ? currentProjectionMeta.visible_tag_groups
            : [];
    }

    function tagGroupItems(tagIds) {
        const tagNodes = graphVisibleNodesByType.tag || [];
        const tagById = new Map(tagNodes.map(item => [String(item.id), item]));
        return (tagIds || [])
            .map(id => tagById.get(String(id)))
            .filter(Boolean);
    }

    function displayGroupName(group) {
        return String(group?.label || group?.id || 'tag group');
    }

    function groupTooltip(group) {
        return `Toggle and browse the ${displayGroupName(group)} ontology branch.`;
    }

    function compareTypesForSidebar(a, b) {
        const left = String(a?.type || '');
        const right = String(b?.type || '');
        const leftRank = GENOMICS_TYPE_ORDER.has(left) ? GENOMICS_TYPE_ORDER.get(left) : 999;
        const rightRank = GENOMICS_TYPE_ORDER.has(right) ? GENOMICS_TYPE_ORDER.get(right) : 999;
        if (leftRank !== rightRank) return leftRank - rightRank;
        return left.localeCompare(right);
    }

    function renderSections(sectionsEl) {
        if (!sectionsEl) return;
        sectionsEl.innerHTML = '';
        const available = graphAvailableTypes.filter(item => {
            if (SIDEBAR_HIDDEN_TYPES.has(item.type)) return false;
            if (configuredTypeFamily(item.type) === 'provenance') return false;
            return true;
        });
        if (!available.length) return;

        const genomicsFamiliesPresent = available.some(item =>
            ['backbone', 'comparative', 'measurement', 'ontology', 'provenance'].includes(configuredTypeFamily(item.type))
        );
        const ontologyTagGroups = visibleTagGroups().filter(group => Array.isArray(group.node_ids) && group.node_ids.length > 0);
        const groupedTagIds = new Set(ontologyTagGroups.flatMap(group => group.node_ids.map(String)));
        const ontologyTypeItems = available
            .filter(item => configuredTypeFamily(item.type) === 'ontology')
            .filter(item => item.type !== 'tag');
        const leftoverTagItem = available.find(item => item.type === 'tag');
        const leftoverTagCount = tagGroupItems((graphVisibleNodesByType.tag || []).map(item => item.id).filter(id => !groupedTagIds.has(String(id)))).length;
        const ontologyItems = [
            ...ontologyTypeItems.sort(compareTypesForSidebar).map(item => ({ kind: 'type', ...item })),
            ...ontologyTagGroups.map(group => ({
                kind: 'tag_group',
                id: String(group.id),
                label: displayGroupName(group),
                count: tagGroupItems(group.node_ids).length,
                node_ids: [...group.node_ids],
            })),
        ];
        if (leftoverTagItem && leftoverTagCount > 0) {
            ontologyItems.push({ kind: 'type', ...leftoverTagItem, count: leftoverTagCount });
        }
        const groups = genomicsFamiliesPresent
            ? [
                { title: 'Structure', items: available.filter(item => configuredTypeFamily(item.type) === 'backbone').sort(compareTypesForSidebar).map(item => ({ kind: 'type', ...item })) },
                { title: 'Comparative', items: available.filter(item => configuredTypeFamily(item.type) === 'comparative').sort(compareTypesForSidebar).map(item => ({ kind: 'type', ...item })) },
                { title: 'Measurements', items: available.filter(item => configuredTypeFamily(item.type) === 'measurement').sort(compareTypesForSidebar).map(item => ({ kind: 'type', ...item })) },
                { title: 'Ontology', items: ontologyItems },
                { title: 'Other Types', items: available.filter(item => !configuredTypeFamily(item.type) || configuredTypeFamily(item.type) === 'other').sort(compareTypesForSidebar).map(item => ({ kind: 'type', ...item })) },
            ]
            : isGenomicsLikeProjection()
                ? [
                    { title: 'Node Types', items: available.filter(item => GENOMICS_PRIMARY_TYPES.has(item.type)).sort(compareTypesForSidebar).map(item => ({ kind: 'type', ...item })) },
                    { title: 'Scientific Layers', items: available.filter(item => GENOMICS_SECONDARY_TYPES.has(item.type)).sort(compareTypesForSidebar).map(item => ({ kind: 'type', ...item })) },
                    { title: 'Other Types', items: available.filter(item => !GENOMICS_PRIMARY_TYPES.has(item.type) && !GENOMICS_SECONDARY_TYPES.has(item.type)).sort(compareTypesForSidebar).map(item => ({ kind: 'type', ...item })) },
                ]
                : [
                    { title: 'Node Types', items: available.map(item => ({ kind: 'type', ...item })) },
                ];

        for (const group of groups) {
            if (!group.items.length) continue;
            const groupWrap = document.createElement('div');
            groupWrap.className = 'sidebar-section';
            groupWrap.innerHTML = `
                <div class="sidebar-section-header edge-filters-header">
                    <span class="sidebar-section-title">${escHtml(group.title)}</span>
                </div>
                <div class="sidebar-type-group"></div>
            `;
            const groupEl = groupWrap.querySelector('.sidebar-type-group');

            for (const t of group.items) {
                const section = document.createElement('div');
                section.className = 'sidebar-subsection';
                const itemKey = t.kind === 'tag_group' ? `tag-root:${t.id}` : t.type;
                const isExpanded = expandedTypes.has(itemKey);
                const color = t.kind === 'tag_group' ? typeColor('tag') : typeColor(t.type);
                const visibleCount = t.kind === 'tag_group' ? tagGroupItems(t.node_ids).length : getVisibleCountForType(t.type);
                const availableCount = t.count || 0;
                const countLabel = visibleCount === availableCount ? `${visibleCount}` : `${visibleCount}/${availableCount}`;
                const isChecked = t.kind === 'tag_group'
                    ? !uncheckedNodeGroups.has(t.id)
                    : !uncheckedNodeTypes.has(t.type);
                const title = t.kind === 'tag_group' ? groupTooltip(t) : typeTooltip(t.type);
                const displayName = t.kind === 'tag_group' ? displayGroupName(t) : displayTypeName(t.type);

                section.innerHTML = `
                    <div class="sidebar-section-header sidebar-type-header" data-type="${escHtml(itemKey)}" title="${escHtml(title)}">
                        <span class="sidebar-checkbox-control" title="${escHtml(title)}">
                            <input type="checkbox" class="sidebar-row-toggle-input sidebar-type-toggle" data-type="${escHtml(itemKey)}" ${isChecked ? 'checked' : ''} aria-label="Toggle ${escHtml(displayName)} visibility" title="${escHtml(title)}">
                            <span class="sidebar-checkbox-box" aria-hidden="true"></span>
                        </span>
                        <span class="sidebar-dot" style="background:${color}"></span>
                        <span class="sidebar-section-title">${escHtml(displayName)}</span>
                        <span class="sidebar-count">${escHtml(countLabel)}</span>
                    </div>
                    <div class="sidebar-entity-list ${isExpanded ? 'expanded' : ''}" data-list-type="${escHtml(itemKey)}"></div>
                `;

                const header = section.querySelector('.sidebar-type-header');
                const checkbox = section.querySelector('.sidebar-type-toggle');
                const checkboxControl = section.querySelector('.sidebar-checkbox-control');
                header.setAttribute('role', 'button');
                header.setAttribute('tabindex', '0');
                const openSection = () => toggleSection(itemKey, section, t);
                header.addEventListener('click', (ev) => {
                    if (ev.target === checkbox || ev.target.closest('.sidebar-checkbox-control')) return;
                    ev.preventDefault();
                    openSection();
                });
                header.addEventListener('keydown', (ev) => {
                    if (ev.target === checkbox || ev.target.closest('.sidebar-checkbox-control')) return;
                    if (ev.key === 'Enter' || ev.key === ' ') {
                        ev.preventDefault();
                        openSection();
                    }
                });
                checkboxControl?.addEventListener('click', ev => ev.stopPropagation());
                checkbox.addEventListener('click', ev => ev.stopPropagation());
                checkbox.addEventListener('change', () => {
                    if (t.kind === 'tag_group') {
                        if (checkbox.checked) {
                            uncheckedNodeGroups.delete(t.id);
                        } else {
                            uncheckedNodeGroups.add(t.id);
                        }
                        eventBus.emit('node:group-filter', {
                            group_id: t.id,
                            node_ids: t.node_ids,
                            visible: checkbox.checked,
                        });
                    } else {
                        if (checkbox.checked) {
                            uncheckedNodeTypes.delete(t.type);
                        } else {
                            uncheckedNodeTypes.add(t.type);
                        }
                        eventBus.emit('node:type-filter', {
                            node_type: t.type,
                            visible: checkbox.checked,
                        });
                    }
                });

                groupEl.appendChild(section);
                if (isExpanded) {
                    renderEntityList(section.querySelector(`[data-list-type="${CSS.escape(itemKey)}"]`), t);
                }
            }

            sectionsEl.appendChild(groupWrap);
        }
    }

    function toggleSection(typeKey, sectionEl, item) {
        const listEl = sectionEl.querySelector(`[data-list-type="${CSS.escape(typeKey)}"]`);
        const chevron = sectionEl.querySelector('.sidebar-chevron');

        if (expandedTypes.has(typeKey)) {
            expandedTypes.delete(typeKey);
            listEl.classList.remove('expanded');
            if (chevron) chevron.textContent = '▸';
        } else {
            expandedTypes.add(typeKey);
            listEl.classList.add('expanded');
            if (chevron) chevron.textContent = '▾';
            renderEntityList(listEl, item);
        }
    }

    function renderEntityList(listEl, item) {
        if (!listEl) return;
        const type = item.kind === 'tag_group' ? 'tag' : item.type;
        const items = item.kind === 'tag_group'
            ? tagGroupItems(item.node_ids).map(node => ({ kind: 'single', ...node }))
            : groupedEntityList(type);
        if (items.length === 0) {
            listEl.innerHTML = `<div class="sidebar-empty">${searchQuery ? 'No matches' : 'Empty'}</div>`;
            return;
        }
        listEl.innerHTML = items.slice(0, 500).map(e => {
            if (e.kind === 'group') {
                const ids = e.ids.join(',');
                const countBadge = e.count > 1 ? `<span class="sidebar-entity-count">${e.count}</span>` : '';
                const title = `Highlight ${e.count} ${displayTypeName(type)} node${e.count === 1 ? '' : 's'} named "${e.name}" and focus the first match.`;
                return `
                    <div class="sidebar-entity-item sidebar-entity-item-grouped" data-ids="${escHtml(ids)}" data-id="${escHtml(e.ids[0])}" data-type="${type}" data-name="${escHtml(e.name)}" title="${escHtml(title)}">
                        <span class="sidebar-entity-name truncate">${escHtml(e.name)}</span>
                        ${countBadge}
                    </div>
                `;
            }
            return `
                <div class="sidebar-entity-item" data-id="${e.id}" data-type="${type}" data-name="${escHtml(e.name)}" title="${escHtml(e.name)}">
                    <span class="sidebar-entity-name truncate">${escHtml(e.name)}</span>
                </div>
            `;
        }).join('');

        if (items.length > 500) {
            listEl.innerHTML += `<div class="sidebar-empty">…and ${items.length - 500} more. Use search to filter.</div>`;
        }

        listEl.querySelectorAll('.sidebar-entity-item').forEach(el => {
            el.addEventListener('click', () => {
                const id   = el.dataset.id;
                const name = el.dataset.name;
                const t    = el.dataset.type;
                const ids  = (el.dataset.ids || '').split(',').filter(Boolean);
                // Deselect previous
                container.querySelectorAll('.sidebar-entity-item.active')
                    .forEach(x => x.classList.remove('active'));
                el.classList.add('active');
                if (ids.length > 1) {
                    eventBus.emit('node:highlight', { ids });
                } else {
                    eventBus.emit('node:highlight-clear', {});
                }
                eventBus.emit('sidebar:select', { id, type: t, name });
                eventBus.emit('node:selected', { id, type: t, name });
            });
        });
    }

    // Track which rel_types the user has unchecked so we can restore state on re-render
    let uncheckedRelTypes = new Set();

    function renderEdgeFilters(filtersEl) {
        if (!filtersEl) return;
        filtersEl.innerHTML = relData.map(r => {
            const isChecked = (!defaultVisibleRelTypes || defaultVisibleRelTypes.has(r.rel_type)) && !uncheckedRelTypes.has(r.rel_type);
            return `
            <label class="edge-filter-row" title="${escHtml(edgeTooltip(r.rel_type))}">
                <span class="sidebar-checkbox-control">
                    <input type="checkbox" class="sidebar-row-toggle-input edge-filter-cb" data-rel="${r.rel_type}" ${isChecked ? 'checked' : ''} aria-label="Toggle ${escHtml(displayEdgeName(r.rel_type))} relationships" title="${escHtml(edgeTooltip(r.rel_type))}">
                    <span class="sidebar-checkbox-box" aria-hidden="true"></span>
                </span>
                <span class="edge-filter-name">${escHtml(displayEdgeName(r.rel_type))}</span>
                <span class="sidebar-count">${r.count}</span>
            </label>`;
        }).join('');

        filtersEl.querySelectorAll('.edge-filter-cb').forEach(cb => {
            cb.addEventListener('change', () => {
                if (cb.checked) {
                    uncheckedRelTypes.delete(cb.dataset.rel);
                } else {
                    uncheckedRelTypes.add(cb.dataset.rel);
                }
                eventBus.emit('edge:filter', {
                    rel_type: cb.dataset.rel,
                    visible: cb.checked,
                });
            });
        });
        if (!edgeDefaultsApplied) {
            edgeDefaultsApplied = true;
            for (const r of relData) {
                const visible = !defaultVisibleRelTypes || defaultVisibleRelTypes.has(r.rel_type);
                if (!visible) {
                    uncheckedRelTypes.add(r.rel_type);
                    eventBus.emit('edge:filter', { rel_type: r.rel_type, visible: false });
                }
            }
        }
    }

    // "Show All" resets edge filters too
    eventBus.on('edge:reset', () => {
        uncheckedRelTypes.clear();
        const filtersEl = container.querySelector('#edge-filters');
        if (filtersEl) renderEdgeFilters(filtersEl);
    });

    eventBus.on('node:type-filter-reset', () => {
        uncheckedNodeTypes.clear();
        const sectionsEl = container.querySelector('#sidebar-sections');
        if (sectionsEl) renderSections(sectionsEl);
    });

    eventBus.on('node:group-filter-reset', () => {
        uncheckedNodeGroups.clear();
        const sectionsEl = container.querySelector('#sidebar-sections');
        if (sectionsEl) renderSections(sectionsEl);
    });

    // Timeline and Hierarchical depend on AUTHORED as structural context.
    // Do not carry a stale unchecked AUTHORED state into those layouts by default.
    eventBus.on('layout:change', ({ layout }) => {
        if (layout !== 'timeline' && layout !== 'td') return;
        if (!uncheckedRelTypes.has('AUTHORED')) return;
        uncheckedRelTypes.delete('AUTHORED');
        eventBus.emit('edge:filter', { rel_type: 'AUTHORED', visible: true });
        const filtersEl = container.querySelector('#edge-filters');
        if (filtersEl) renderEdgeFilters(filtersEl);
    });

    // Re-render on db change
    eventBus.on('db:changed', () => {
        loadSidebarConfig();
    });

    // Highlight active node in sidebar
    eventBus.on('node:selected', ({ id }) => {
        container.querySelectorAll('.sidebar-entity-item.active')
            .forEach(x => x.classList.remove('active'));
        const el = container.querySelector(`.sidebar-entity-item[data-id="${id}"]`);
        if (el) {
            el.classList.add('active');
            el.scrollIntoView({ block: 'nearest' });
        }
    });

    // ---- SQL Filters ----
    // Persisted in localStorage as [{id, name, sql, active}]
    const SF_KEY = 'kgx:sql-filters';

    function sfLoad() {
        try { return JSON.parse(localStorage.getItem(SF_KEY) || '[]'); }
        catch (_) { return []; }
    }
    function sfSave(filters) {
        localStorage.setItem(SF_KEY, JSON.stringify(filters));
    }

    async function sfApply(filter) {
        try {
            const data = await apiClient.post('/api/query', { sql: filter.sql });
            const ids = (data.results || []).map(r => r.id).filter(Boolean);
            eventBus.emit('node:sql-filter', { filter_id: filter.id, ids, active: true });
            return ids.length;
        } catch (err) {
            return null; // error — leave filter as-is
        }
    }

    function sfDeactivate(filter) {
        eventBus.emit('node:sql-filter', { filter_id: filter.id, ids: [], active: false });
    }

    // Allow chat to save a filter directly into the sidebar
    eventBus.on('chat:save-filter', ({ name, sql }) => {
        const filters = sfLoad();
        const id = 'sf-' + Date.now();
        filters.push({ id, name, sql, active: false });
        sfSave(filters);
        console.log('chat:save-filter saved', { id, name, sql }, 'total:', filters.length);
        renderSqlFilters();
        // Scroll sidebar to show the SQL filters section
        const section = sqlPanel?.querySelector('#sql-filters-section');
        if (section) section.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    });

    function renderSqlFilters() {
        const listEl = sqlPanel?.querySelector('#sf-list');
        if (!listEl) return;
        const filters = sfLoad();
        if (filters.length === 0) {
            listEl.innerHTML = `<div class="sf-empty">No filters. Click + to add one.</div>`;
            return;
        }
        listEl.innerHTML = filters.map(f => `
            <div class="sf-row" data-id="${escHtml(f.id)}">
                <label class="sf-toggle" title="${escHtml(f.sql)}">
                    <input type="checkbox" class="sf-cb" ${f.active ? 'checked' : ''}>
                    <span class="sf-name">${escHtml(f.name)}</span>
                </label>
                <button class="sf-edit" data-id="${escHtml(f.id)}" title="Edit">✎</button>
                <button class="sf-del" data-id="${escHtml(f.id)}" title="Delete">×</button>
            </div>
        `).join('');

        listEl.querySelectorAll('.sf-cb').forEach(cb => {
            cb.addEventListener('change', async () => {
                const filterId = cb.closest('.sf-row').dataset.id;
                const filters = sfLoad();
                const f = filters.find(x => x.id === filterId);
                if (!f) return;
                f.active = cb.checked;
                sfSave(filters);
                if (f.active) {
                    const count = await sfApply(f);
                    // show count badge
                    const nameEl = cb.closest('.sf-row').querySelector('.sf-name');
                    if (count !== null && nameEl) nameEl.dataset.count = count;
                } else {
                    sfDeactivate(f);
                }
            });
        });

        listEl.querySelectorAll('.sf-edit').forEach(btn => {
            btn.addEventListener('click', () => {
                const filterId = btn.dataset.id;
                const f = sfLoad().find(x => x.id === filterId);
                if (!f) return;
                const form = sqlPanel?.querySelector('#sf-form');
                sqlPanel.querySelector('#sf-name').value = f.name;
                sqlPanel.querySelector('#sf-sql').value = f.sql;
                form.dataset.editId = filterId;
                form.style.display = 'block';
                sqlPanel.querySelector('#sf-name').focus();
            });
        });

        listEl.querySelectorAll('.sf-del').forEach(btn => {
            btn.addEventListener('click', () => {
                const filterId = btn.dataset.id;
                let filters = sfLoad();
                const f = filters.find(x => x.id === filterId);
                if (f && f.active) sfDeactivate(f);
                filters = filters.filter(x => x.id !== filterId);
                sfSave(filters);
                renderSqlFilters();
            });
        });
    }

    function bindSqlFilterForm() {
        const addBtn  = sqlPanel?.querySelector('#sf-add-btn');
        const form    = sqlPanel?.querySelector('#sf-form');
        const saveBtn = sqlPanel?.querySelector('#sf-save');
        const cancelBtn = sqlPanel?.querySelector('#sf-cancel');
        if (!addBtn) return;

        addBtn.addEventListener('click', () => {
            form.style.display = form.style.display === 'none' ? 'block' : 'none';
        });

        cancelBtn.addEventListener('click', () => {
            form.style.display = 'none';
            sqlPanel.querySelector('#sf-name').value = '';
            sqlPanel.querySelector('#sf-sql').value = '';
            delete form.dataset.editId;
        });

        saveBtn.addEventListener('click', async () => {
            const name = sqlPanel.querySelector('#sf-name').value.trim();
            const sql  = sqlPanel.querySelector('#sf-sql').value.trim();
            if (!name || !sql) return;

            const filters = sfLoad();
            const editId = form.dataset.editId;

            let filter;
            if (editId) {
                // Update existing
                filter = filters.find(x => x.id === editId);
                if (filter) {
                    if (filter.active) sfDeactivate(filter); // remove old filter from graph
                    filter.name = name;
                    filter.sql = sql;
                }
                delete form.dataset.editId;
            } else {
                // Create new
                filter = { id: 'sf-' + Date.now(), name, sql, active: true };
                filters.push(filter);
            }

            sfSave(filters);
            form.style.display = 'none';
            sqlPanel.querySelector('#sf-name').value = '';
            sqlPanel.querySelector('#sf-sql').value = '';

            renderSqlFilters();
            if (filter && filter.active) await sfApply(filter);
        });
    }

    // Re-apply active filters after graph reloads
    eventBus.on('graph:loaded', async () => {
        const filters = sfLoad();
        for (const f of filters) {
            if (f.active) await sfApply(f);
        }
    });

    // "Show All" clears sql filters too
    eventBus.on('edge:reset', () => {
        // Deactivate all but keep them saved so user can re-enable
        const filters = sfLoad();
        filters.forEach(f => { f.active = false; });
        sfSave(filters);
        renderSqlFilters();
    });

    function escHtml(str) {
        return String(str)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    loadSidebarConfig();
}
