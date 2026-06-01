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

    function escHtml(str) {
        return String(str ?? '')
            .replace(/&/g, '&amp;').replace(/</g, '&lt;')
            .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }

    function renderMeta(meta) {
        if (!meta || typeof meta !== 'object' || Object.keys(meta).length === 0) return '';
        const rows = Object.entries(meta)
            .filter(([k, v]) => v !== null && v !== '' && v !== 'N/A')
            .map(([k, v]) => {
                const display = typeof v === 'object' ? JSON.stringify(v) : String(v);
                // Make URLs clickable
                const val = display.startsWith('http')
                    ? `<a href="${escHtml(display)}" target="_blank" class="detail-link-ext">${escHtml(display)}</a>`
                    : escHtml(display);
                return `<tr><td class="detail-key">${escHtml(k)}</td><td class="detail-val">${val}</td></tr>`;
            }).join('');
        if (!rows) return '';
        return `
            <section class="detail-section">
                <h3 class="detail-section-title">Properties</h3>
                <table class="detail-table"><tbody>${rows}</tbody></table>
            </section>`;
    }

    function renderRelationships(rels, entityId) {
        if (!rels || rels.length === 0) return '';

        // Group by rel_type
        const groups = {};
        for (const r of rels) {
            const rt = r.rel_type;
            if (!groups[rt]) groups[rt] = [];
            const other = r.source_id === entityId ? r.target_id : r.source_id;
            groups[rt].push({ id: other, meta: r.metadata });
        }

        const sections = Object.entries(groups).sort(([a],[b]) => a.localeCompare(b)).map(([rt, items]) => {
            const links = items.map(item => `
                <span class="detail-rel-link" data-entity-id="${escHtml(item.id)}">${escHtml(item.id)}</span>
            `).join('');
            return `
                <div class="detail-rel-group">
                    <span class="detail-rel-type">${escHtml(rt)}</span>
                    <div class="detail-rel-links">${links}</div>
                </div>`;
        }).join('');

        return `
            <section class="detail-section">
                <h3 class="detail-section-title">Relationships <span class="detail-count">${rels.length}</span></h3>
                ${sections}
            </section>`;
    }

    async function loadEntity(id) {
        currentId = id;
        container.innerHTML = `<div class="detail-loading">Loading…</div>`;

        try {
            const data = await apiClient.get(`/api/entity/${encodeURIComponent(id)}`);
            const { entity, relationships, neighbors, degree } = data;
            const color = typeColor(entity.type);

            container.innerHTML = `
                <div class="detail-header">
                    <div class="detail-type-badge" style="background:${color}22;color:${color};border-color:${color}44">
                        ${escHtml(entity.type)}
                    </div>
                    <h2 class="detail-name">${escHtml(entity.name)}</h2>
                    <div class="detail-id truncate">${escHtml(entity.id)}</div>
                    <div class="detail-degree">
                        <span class="degree-label">degree</span>
                        <span class="degree-value">${degree}</span>
                    </div>
                </div>

                <div class="detail-actions">
                    <button class="detail-btn" id="btn-highlight-neighbors">Highlight neighbors</button>
                    <button class="detail-btn" id="btn-export-md">Export markdown</button>
                </div>

                <div id="detail-body">
                    ${renderMeta(entity.metadata)}
                    ${renderRelationships(relationships, entity.id)}
                </div>
            `;

            // Highlight neighbors in graph
            container.querySelector('#btn-highlight-neighbors')?.addEventListener('click', () => {
                const ids = neighbors.map(n => n.id);
                ids.push(entity.id);
                eventBus.emit('node:highlight', { ids });
            });

            // Export markdown
            container.querySelector('#btn-export-md')?.addEventListener('click', () => {
                window.open(`/api/export/markdown/${encodeURIComponent(entity.id)}`, '_blank');
            });

            // Click related entity links → navigate
            container.querySelectorAll('.detail-rel-link').forEach(el => {
                el.addEventListener('click', () => {
                    const linkId = el.dataset.entityId;
                    eventBus.emit('node:selected', { id: linkId, name: linkId, type: '' });
                    eventBus.emit('node:focus', { id: linkId });
                });
            });

        } catch (err) {
            container.innerHTML = `<div class="detail-error">Failed to load: ${escHtml(err.message)}</div>`;
        }
    }

    eventBus.on('node:selected', ({ id, type, name }) => {
        if (id) loadEntity(id);
    });

    // Refresh if DB changes and detail panel is open
    eventBus.on('db:changed', () => {
        if (currentId) loadEntity(currentId);
    });
}
