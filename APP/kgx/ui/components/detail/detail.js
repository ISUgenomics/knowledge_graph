/**
 * Detail panel component — shows full entity info on node click.
 *
 * Incoming events:
 *   node:selected  {id, type, name} — load and render entity detail
 *
 * Outgoing events:
 *   node:selected  {id, type, name} — when user clicks a linked entity
 *   node:highlight {ids}            — highlight related nodes in graph
 */
export function initDetail(container, eventBus, apiClient) {

    let currentId = null;

    const PALETTE = [
        '#4e9af1','#f1a34e','#4ef17a','#f14e4e',
        '#c34ef1','#f1e24e','#4ef1e8','#f14eb5',
    ];
    const typeColors = {};
    let palIdx = 0;
    function typeColor(type) {
        if (!typeColors[type]) { typeColors[type] = PALETTE[palIdx++ % PALETTE.length]; }
        return typeColors[type];
    }

    function esc(str) {
        return String(str ?? '')
            .replace(/&/g, '&amp;').replace(/</g, '&lt;')
            .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }

    function linkVal(v) {
        const s = String(v ?? '');
        return s.startsWith('http')
            ? `<a href="${esc(s)}" target="_blank" class="detail-link-ext">${esc(s)}</a>`
            : esc(s);
    }

    // ---- Section renderers ----

    function renderTopics(topics) {
        if (!topics?.length) return '';
        const chips = topics.map(t =>
            `<span class="detail-topic-chip">${esc(t)}</span>`
        ).join('');
        return `
            <section class="detail-section">
                <h3 class="detail-section-title">Topics</h3>
                <div class="detail-topic-chips">${chips}</div>
            </section>`;
    }

    function renderContact(contact) {
        if (!contact || Object.keys(contact).length === 0) return '';
        const FIELD_ORDER = ['title', 'department', 'email', 'phone', 'orcid', 'website'];
        const sorted = [
            ...FIELD_ORDER.filter(f => contact[f]),
            ...Object.keys(contact).filter(f => !FIELD_ORDER.includes(f) && contact[f]),
        ];
        const rows = sorted.map(f =>
            `<tr><td class="detail-key">${esc(f)}</td><td class="detail-val">${linkVal(contact[f])}</td></tr>`
        ).join('');
        return `
            <section class="detail-section">
                <h3 class="detail-section-title">Contact</h3>
                <table class="detail-table"><tbody>${rows}</tbody></table>
            </section>`;
    }

    function renderInterests(interests) {
        if (!interests?.length) return '';
        const items = interests.map(i => `<li class="detail-interest">${esc(i)}</li>`).join('');
        return `
            <section class="detail-section">
                <h3 class="detail-section-title">Research Interests</h3>
                <ul class="detail-interest-list">${items}</ul>
            </section>`;
    }

    function renderMeta(meta, exclude = new Set()) {
        if (!meta || typeof meta !== 'object') return '';
        const rows = Object.entries(meta)
            .filter(([k, v]) => !exclude.has(k) && v !== null && v !== '' && v !== 'N/A')
            .map(([k, v]) => {
                const display = typeof v === 'object' ? JSON.stringify(v) : String(v);
                return `<tr><td class="detail-key">${esc(k)}</td><td class="detail-val">${linkVal(display)}</td></tr>`;
            }).join('');
        if (!rows) return '';
        return `
            <section class="detail-section">
                <h3 class="detail-section-title">Properties</h3>
                <table class="detail-table"><tbody>${rows}</tbody></table>
            </section>`;
    }

    function renderSnippets(snippets) {
        if (!snippets?.length) return '';

        // Group by ref_type
        const groups = {};
        for (const s of snippets) {
            const key = s.ref_type || 'general';
            if (!groups[key]) groups[key] = [];
            groups[key].push(s);
        }

        let html = '';
        for (const [refType, snips] of Object.entries(groups)) {
            // Sub-group by ref_id within each ref_type
            const byRef = {};
            for (const s of snips) {
                const key = s.ref_id || '_ungrouped';
                if (!byRef[key]) byRef[key] = [];
                byRef[key].push(s);
            }

            if (Object.keys(byRef).length === 1 && byRef['_ungrouped']) {
                // Flat list — no sub-grouping
                const quotes = snips.map(s =>
                    `<blockquote class="detail-snippet">${esc(s.text)}</blockquote>`
                ).join('');
                const title = refType === 'general' ? 'Snippets' : `${esc(refType)} Snippets`;
                html += `
                    <section class="detail-section">
                        <h3 class="detail-section-title">${title}</h3>
                        ${quotes}
                    </section>`;
            } else {
                const subSections = Object.entries(byRef).map(([refId, refSnips]) => {
                    const quotes = refSnips.map(s =>
                        `<blockquote class="detail-snippet">${esc(s.text)}</blockquote>`
                    ).join('');
                    return `
                        <div class="detail-person-snippets">
                            <div class="detail-person-snippet-name detail-rel-link" data-entity-id="${esc(refId)}">${esc(refId)}</div>
                            ${quotes}
                        </div>`;
                }).join('');
                const title = refType === 'general' ? 'Snippets' : `${esc(refType)} Context`;
                html += `
                    <section class="detail-section">
                        <h3 class="detail-section-title">${title}</h3>
                        ${subSections}
                    </section>`;
            }
        }

        return html;
    }

    function renderSnippetsAbout(snippetsAbout) {
        if (!snippetsAbout?.length) return '';

        // Group by source entity (entity_id)
        const bySource = {};
        for (const s of snippetsAbout) {
            const key = s.entity_id;
            if (!bySource[key]) bySource[key] = { name: s.signal_name, quotes: [] };
            bySource[key].quotes.push(s.text);
        }

        const sections = Object.entries(bySource).map(([sourceId, data]) => {
            const quotes = data.quotes.map(q =>
                `<blockquote class="detail-snippet">${esc(q)}</blockquote>`
            ).join('');
            return `
                <div class="detail-person-snippets">
                    <div class="detail-person-snippet-name detail-rel-link"
                         data-entity-id="${esc(sourceId)}">${esc(data.name)}</div>
                    ${quotes}
                </div>`;
        }).join('');

        return `
            <section class="detail-section">
                <h3 class="detail-section-title">Mentioned In <span class="detail-count">${snippetsAbout.length}</span></h3>
                ${sections}
            </section>`;
    }

    function renderSources(sources) {
        if (!sources?.length) return '';
        const rows = sources.map(s => `
            <tr>
                <td class="detail-key">${esc(s.source_name)}</td>
                <td class="detail-val">${s.url ? `<a href="${esc(s.url)}" target="_blank" class="detail-link-ext">${esc(s.url)}</a>` : '—'}</td>
                <td class="detail-val" style="color:var(--text-muted);font-size:11px">${esc(s.retrieved_at ?? '')}</td>
            </tr>`).join('');
        return `
            <section class="detail-section">
                <h3 class="detail-section-title">Sources</h3>
                <table class="detail-table"><tbody>${rows}</tbody></table>
            </section>`;
    }

    function renderRelationships(rels, entityId) {
        if (!rels?.length) return '';

        // Group by rel_type
        const groups = {};
        for (const r of rels) {
            const rt = r.rel_type;
            if (!groups[rt]) groups[rt] = [];
            const otherId = r.source_id === entityId ? r.target_id : r.source_id;
            const displayName = r.other_name && r.other_name !== otherId ? r.other_name : otherId;
            groups[rt].push({ id: otherId, name: displayName });
        }

        const sections = Object.entries(groups)
            .sort(([a], [b]) => a.localeCompare(b))
            .map(([rt, items]) => {
                const links = items.map(item => `
                    <span class="detail-rel-link" data-entity-id="${esc(item.id)}"
                          title="${esc(item.id)}">${esc(item.name)}</span>
                `).join('');
                return `
                    <div class="detail-rel-group">
                        <span class="detail-rel-type">${esc(rt)}</span>
                        <div class="detail-rel-links">${links}</div>
                    </div>`;
            }).join('');

        return `
            <section class="detail-section">
                <h3 class="detail-section-title">Relationships <span class="detail-count">${rels.length}</span></h3>
                ${sections}
            </section>`;
    }

    // ---- Data-driven section rendering ----
    // Renders all available sections based on what data exists.
    // No type-specific branches — works for any entity type.

    function renderLongText(meta) {
        // Render long text fields (abstract, description, summary) in dedicated blocks
        const longFields = ['abstract', 'description', 'summary'];
        const rendered = [];
        for (const field of longFields) {
            const val = meta[field];
            if (val && String(val).length > 200) {
                rendered.push(`
                    <section class="detail-section">
                        <h3 class="detail-section-title">${esc(field.charAt(0).toUpperCase() + field.slice(1))}</h3>
                        <p class="detail-abstract">${esc(val)}</p>
                    </section>`);
            }
        }
        return rendered.join('');
    }

    function renderBody(entity, relationships, rich) {
        const meta = entity.metadata || {};
        const r = rich || {};

        // Fields shown in dedicated sections should be excluded from the meta table
        const excludeFromMeta = new Set();
        // Exclude contact fields if contact info exists
        if (r.contact && Object.keys(r.contact).length > 0) {
            for (const f of Object.keys(r.contact)) excludeFromMeta.add(f);
        }
        // Exclude long text fields rendered separately
        for (const f of ['abstract', 'description', 'summary']) {
            if (meta[f] && String(meta[f]).length > 200) excludeFromMeta.add(f);
        }

        // Render all sections — each returns '' if no data
        return [
            renderContact(r.contact),
            renderInterests(r.research_interests),
            renderTopics(r.topics),
            renderSnippetsAbout(r.snippets_about),
            renderMeta(meta, excludeFromMeta),
            renderLongText(meta),
            renderSnippets(r.snippets),
            renderRelationships(relationships, entity.id),
            renderSources(r.sources),
        ].join('');
    }

    // ---- Load & render ----

    async function loadEntity(id) {
        currentId = id;
        container.innerHTML = `<div class="detail-loading">Loading…</div>`;

        try {
            const data = await apiClient.get(`/api/entity/${encodeURIComponent(id)}`);
            const { entity, relationships, neighbors, degree, rich } = data;
            const color = typeColor(entity.type);

            container.innerHTML = `
                <div class="detail-header">
                    <div class="detail-type-badge" style="background:${color}22;color:${color};border-color:${color}44">
                        ${esc(entity.type)}
                    </div>
                    <h2 class="detail-name">${esc(entity.name)}</h2>
                    <div class="detail-id truncate">${esc(entity.id)}</div>
                    <div class="detail-degree">
                        <span class="degree-label">degree</span>
                        <span class="degree-value">${degree}</span>
                    </div>
                </div>

                <div class="detail-actions">
                    <button class="detail-btn" id="btn-highlight-neighbors">Highlight neighbors</button>
                    <button class="detail-btn" id="btn-export-md">Export markdown</button>
                    <span class="detail-nav-hint" id="detail-nav-hint"></span>
                </div>

                <div id="detail-body">
                    ${renderBody(entity, relationships, rich)}
                </div>
            `;

            container.querySelector('#btn-highlight-neighbors')?.addEventListener('click', () => {
                const ids = neighbors.map(n => n.id);
                ids.push(entity.id);
                eventBus.emit('node:highlight', { ids });
            });

            container.querySelector('#btn-export-md')?.addEventListener('click', () => {
                window.open(`/api/export/markdown/${encodeURIComponent(entity.id)}`, '_blank');
            });

            container.querySelectorAll('.detail-rel-link').forEach(el => {
                el.addEventListener('click', () => {
                    const linkId = el.dataset.entityId;
                    eventBus.emit('node:selected', { id: linkId, name: linkId, type: '' });
                    eventBus.emit('node:focus', { id: linkId });
                });
            });

        } catch (err) {
            container.innerHTML = `<div class="detail-error">Failed to load: ${esc(err.message)}</div>`;
        }
    }

    // ---- Arrow-key navigation ----
    let navList = [];      // [{id, name}] for current type
    let navType = '';      // entity type of current list
    let navIndex = -1;

    async function ensureNavList(type) {
        if (type && type !== navType) {
            try {
                const data = await apiClient.get(`/api/entities/${encodeURIComponent(type)}`);
                navList = (data.entities || []).map(e => ({ id: e.id, name: e.name }));
                navType = type;
            } catch (_) {
                navList = [];
                navType = '';
            }
        }
    }

    function updateNavHint() {
        const el = document.getElementById('detail-nav-hint');
        if (!el) return;
        if (navList.length > 0 && navIndex >= 0) {
            el.textContent = `${navIndex + 1}/${navList.length}  ↑↓`;
        } else {
            el.textContent = '';
        }
    }

    function navTo(delta) {
        if (navList.length === 0) return;
        navIndex = Math.max(0, Math.min(navList.length - 1, navIndex + delta));
        const target = navList[navIndex];
        if (target && target.id !== currentId) {
            eventBus.emit('node:selected', { id: target.id, name: target.name, type: navType });
            eventBus.emit('node:focus', { id: target.id });
        }
        updateNavHint();
    }

    document.addEventListener('keydown', (e) => {
        if (!currentId) return;
        // Don't intercept if user is typing in an input/textarea
        const tag = document.activeElement?.tagName;
        if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return;

        if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
            e.preventDefault();
            navTo(e.key === 'ArrowDown' ? 1 : -1);
        }
    });

    eventBus.on('node:selected', async ({ id, type }) => {
        if (!id) return;
        loadEntity(id);
        // Resolve type if not provided (e.g. from relationship click)
        const entityType = type || navType;
        if (entityType) {
            await ensureNavList(entityType);
            navIndex = navList.findIndex(e => e.id === id);
            updateNavHint();
        }
    });

    eventBus.on('db:changed', () => {
        if (currentId) loadEntity(currentId);
    });
}
