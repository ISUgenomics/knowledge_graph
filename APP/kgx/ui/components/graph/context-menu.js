/**
 * Context menu — Phase 4.
 *
 * Incoming events:
 *   node:right-clicked  {id, type, name, x, y}
 *
 * Outgoing events:
 *   node:selected   {id, type, name}
 *   node:focus      {id}
 *   node:hide       {id}
 *   node:expand     {id}
 *   skill:dispatch  {skill, entity_id, entity_type, entity_name}
 */
export function initContextMenu(menuEl, eventBus, apiClient) {
    let currentNode = null;

    // Hide on any click outside the menu
    document.addEventListener('click', e => {
        if (!menuEl.contains(e.target)) {
            menuEl.classList.remove('visible');
        }
    });

    // Also hide on Escape
    document.addEventListener('keydown', e => {
        if (e.key === 'Escape') menuEl.classList.remove('visible');
    });

    function show(node, x, y) {
        currentNode = node;

        menuEl.innerHTML = `
            <div class="ctx-label">${escHtml(node.name)}</div>
            <div class="ctx-type">${escHtml(node.type || '')}</div>
            <div class="ctx-separator"></div>
            <div class="ctx-item" data-action="detail" title="Open the detail panel for this node">Show detail</div>
            <div class="ctx-item" data-action="focus" title="Move the camera focus to this node">Focus in graph</div>
            <div class="ctx-item" data-action="orbit" title="Make this node the camera orbit center">Orbit around this node</div>
            <div class="ctx-item" data-action="highlight" title="Highlight nodes directly connected to this one">Highlight neighbors</div>
            <div class="ctx-item" data-action="expand" title="Reveal neighbors connected in the current graph view">Expand neighbors</div>
            <div class="ctx-separator"></div>
            <div class="ctx-item" data-action="hide" title="Hide this node from the current view">Hide this node</div>
            <div class="ctx-item" data-action="relax" title="Un-pin this node so it re-joins the force layout">Relax node</div>
            <div class="ctx-separator"></div>
            <div class="ctx-item ctx-item-muted" data-action="copy" title="Copy this node's canonical ID">Copy ID</div>
        `;

        // Position — keep within viewport
        const vw = window.innerWidth;
        const vh = window.innerHeight;
        menuEl.style.left = '0px';
        menuEl.style.top  = '0px';
        menuEl.classList.add('visible');
        const rect = menuEl.getBoundingClientRect();
        menuEl.style.left = `${Math.min(x, vw - rect.width - 8)}px`;
        menuEl.style.top  = `${Math.min(y, vh - rect.height - 8)}px`;

        menuEl.querySelectorAll('[data-action]').forEach(el => {
            el.addEventListener('click', e => {
                e.stopPropagation();
                handleAction(el.dataset.action, node);
                menuEl.classList.remove('visible');
            });
        });
    }

    function handleAction(action, node) {
        switch (action) {
            case 'detail':
                eventBus.emit('node:selected', { id: node.id, type: node.type, name: node.name });
                break;
            case 'focus':
                eventBus.emit('node:focus', { id: node.id });
                break;
            case 'orbit':
                eventBus.emit('node:orbit', { id: node.id });
                break;
            case 'highlight':
                eventBus.emit('node:highlight-neighbors', { id: node.id });
                break;
            case 'expand':
                eventBus.emit('node:expand', { id: node.id });
                break;
            case 'hide':
                eventBus.emit('node:hide', { id: node.id });
                break;
            case 'relax':
                eventBus.emit('node:relax', { id: node.id });
                break;
            case 'copy':
                navigator.clipboard.writeText(node.id).catch(() => {
                    // Fallback for non-https contexts
                    const tmp = document.createElement('textarea');
                    tmp.value = node.id;
                    document.body.appendChild(tmp);
                    tmp.select();
                    document.execCommand('copy');
                    document.body.removeChild(tmp);
                });
                break;
        }
    }

    function escHtml(str) {
        return String(str ?? '')
            .replace(/&/g, '&amp;').replace(/</g, '&lt;')
            .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }

    eventBus.on('node:right-clicked', ({ id, type, name, x, y }) => {
        show({ id, type, name }, x, y);
    });
}
