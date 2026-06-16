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
    let previousRelTypes = new Set();

    // Receive the active graph projection and mirror it exactly in the sidebar.
    eventBus.on('graph:projection', ({ typeColors, entityTypes, relTypeCounts, autoHiddenRelTypes, visibleNodesByType }) => {
        if (typeColors) {
            typeColorMap = { ...typeColors };
        }
        if (entityTypes) {
            typeData = [...entityTypes];
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

    // Fallback color palette (matches graph.js)
    const PALETTE = [
        '#4e9af1','#f1a34e','#4ef17a','#f14e4e',
        '#c34ef1','#f1e24e','#4ef1e8','#f14eb5',
    ];
    let paletteIdx = 0;
    function typeColor(type) {
        if (!typeColorMap[type]) {
            typeColorMap[type] = PALETTE[paletteIdx % PALETTE.length];
            paletteIdx++;
        }
        return typeColorMap[type];
    }

    async function loadSidebarConfig() {
        try {
            try {
                const cfg = await apiClient.get('/api/config');
                const vis = cfg?.ui?.edge_filters_default_visible;
                if (Array.isArray(vis) && vis.length) {
                    defaultVisibleRelTypes = new Set(vis.map(x => String(x)));
                }
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

    function filteredList(type) {
        const list = entityList(type);
        if (!searchQuery) return list;
        const q = searchQuery.toLowerCase();
        return list.filter(e => e.name.toLowerCase().includes(q));
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

    function renderSections(sectionsEl) {
        if (!sectionsEl) return;
        sectionsEl.innerHTML = '';
        for (const t of typeData) {
            const section = document.createElement('div');
            section.className = 'sidebar-section';
            const isExpanded = expandedTypes.has(t.type);
            const color = typeColor(t.type);
            const displayCount = graphVisibleNodesByType[t.type]?.length ?? t.count;

            section.innerHTML = `
                <div class="sidebar-section-header" data-type="${t.type}">
                    <span class="sidebar-dot" style="background:${color}"></span>
                    <span class="sidebar-section-title">${t.type}</span>
                    <span class="sidebar-count">${displayCount}</span>
                    <span class="sidebar-chevron">${isExpanded ? '▾' : '▸'}</span>
                </div>
                <div class="sidebar-entity-list ${isExpanded ? 'expanded' : ''}" data-list-type="${t.type}"></div>
            `;

            const header = section.querySelector('.sidebar-section-header');
            header.setAttribute('role', 'button');
            header.setAttribute('tabindex', '0');
            const openSection = () => toggleSection(t.type, section);
            header.addEventListener('click', (ev) => { ev.preventDefault(); openSection(); });
            header.addEventListener('keydown', (ev) => {
                if (ev.key === 'Enter' || ev.key === ' ') {
                    ev.preventDefault(); openSection();
                }
            });

            sectionsEl.appendChild(section);

            if (isExpanded) {
                renderEntityList(section.querySelector(`[data-list-type="${t.type}"]`), t.type);
            }
        }
    }

    function toggleSection(type, sectionEl) {
        const listEl = sectionEl.querySelector(`[data-list-type="${type}"]`);
        const chevron = sectionEl.querySelector('.sidebar-chevron');

        if (expandedTypes.has(type)) {
            expandedTypes.delete(type);
            listEl.classList.remove('expanded');
            if (chevron) chevron.textContent = '▸';
        } else {
            expandedTypes.add(type);
            listEl.classList.add('expanded');
            if (chevron) chevron.textContent = '▾';
            renderEntityList(listEl, type);
        }
    }

    function renderEntityList(listEl, type) {
        if (!listEl) return;
        const items = filteredList(type);
        if (items.length === 0) {
            listEl.innerHTML = `<div class="sidebar-empty">${searchQuery ? 'No matches' : 'Empty'}</div>`;
            return;
        }
        listEl.innerHTML = items.slice(0, 500).map(e => `
            <div class="sidebar-entity-item" data-id="${e.id}" data-type="${type}" data-name="${escHtml(e.name)}">
                <span class="sidebar-entity-name truncate">${escHtml(e.name)}</span>
            </div>
        `).join('');

        if (items.length > 500) {
            listEl.innerHTML += `<div class="sidebar-empty">…and ${items.length - 500} more. Use search to filter.</div>`;
        }

        listEl.querySelectorAll('.sidebar-entity-item').forEach(el => {
            el.addEventListener('click', () => {
                const id   = el.dataset.id;
                const name = el.dataset.name;
                const t    = el.dataset.type;
                // Deselect previous
                container.querySelectorAll('.sidebar-entity-item.active')
                    .forEach(x => x.classList.remove('active'));
                el.classList.add('active');
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
            <label class="edge-filter-row">
                <input type="checkbox" class="edge-filter-cb" data-rel="${r.rel_type}" ${isChecked ? 'checked' : ''}>
                <span class="edge-filter-name">${r.rel_type}</span>
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
