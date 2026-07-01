/**
 * Chat panel — Phase 5.
 *
 * Natural language → SQL via Ollama. Results shown inline.
 * Mutations go through the existing confirm dialog via chat:mutation event.
 *
 * Incoming events:
 *   node:selected  {id, name, type} — pre-fills context for "ask about this node"
 *
 * Outgoing events:
 *   chat:mutation  {sql, token}     — triggers mutation confirm dialog
 *   db:changed     {}               — emitted after successful mutation confirm
 */
export function initChat(container, eventBus, apiClient) {
    let history = [];        // [{role, content}] for multi-turn context
    let contextNode = null;  // currently selected node (for context injection)
    let ollamaAvailable = null;
    let inputHistory = [];   // past user inputs (most recent last)
    let inputHistIdx = -1;   // -1 = not browsing history

    // ---- Render shell ----

    container.innerHTML = `
        <div class="chat-messages" id="chat-messages"></div>
        <div class="chat-input-row">
            <div class="chat-status" id="chat-status"></div>
            <input id="chat-input" class="chat-input" title="Ask a question about the graph, or type help for examples" placeholder="Ask about the graph… (type help for guide)" autocomplete="off">
            <button id="chat-send" class="chat-send-btn" title="Send">&#9654;</button>
            <button id="chat-tools" class="chat-clear-btn" title="Run tools">Tools</button>
            <button id="chat-help" class="chat-clear-btn" title="Help">?</button>
            <button id="chat-clear" class="chat-clear-btn" title="Clear history">&#8635;</button>
        </div>
    `;

    const messagesEl = container.querySelector('#chat-messages');
    const inputEl    = container.querySelector('#chat-input');
    const sendBtn    = container.querySelector('#chat-send');
    const toolsBtn   = container.querySelector('#chat-tools');
    const helpBtn    = container.querySelector('#chat-help');
    const clearBtn   = container.querySelector('#chat-clear');
    const statusEl   = container.querySelector('#chat-status');

    async function showHelp() {
        let typeNames = [];
        try {
            const typesData = await apiClient.get('/api/types');
            typeNames = (typesData.entity_types || []).map(t => t.type);
        } catch (_) {}

        const exType1 = typeNames[0] || 'nodes';
        const exType2 = typeNames[1] || 'nodes';
        const queryExamples = [
            `show all ${exType1} with > 10 edges`,
            `who has the most connections?`,
            typeNames.length > 1 ? `list ${exType2} ordered by degree` : 'nodes ordered by degree',
        ].map(e => `<code>${e}</code>`).join('<br>');

        const filterExamples = [
            `give me IDs of nodes with fewer than 5 edges`,
            typeNames.length > 0 ? `select IDs of ${exType1} not tagged with any topic` : `select IDs of nodes not tagged`,
        ].map(e => `<code>${e}</code>`).join('<br>');

        const timelineExamples = [
            `<code>timeline</code>`,
            `<code>timeline reset</code>`,
        ].join('<br>');

        const div = document.createElement('div');
        div.className = 'chat-msg chat-msg-help';
        div.innerHTML = `
            <div style="font-size:12px;font-weight:600;color:var(--text-primary);margin-bottom:8px;">Chat Help</div>
            <div style="font-size:11px;color:var(--text-secondary);line-height:1.7;">
                <div style="font-weight:600;color:var(--text-muted);margin-top:6px;">Query examples (sent to LLM):</div>
                <div style="padding-left:8px;">
                    ${queryExamples}
                </div>
                <div style="font-weight:600;color:var(--text-muted);margin-top:8px;">Filter examples (returns IDs &rarr; apply to graph):</div>
                <div style="padding-left:8px;">
                    ${filterExamples}<br>
                    When results include an <b>id</b> column, buttons appear to<br>
                    <b>Hide</b> those nodes or <b>Save as sidebar filter</b>
                </div>
                <div style="font-weight:600;color:var(--text-muted);margin-top:8px;">Instant answers (no LLM needed):</div>
                <div style="padding-left:8px;">
                    <code>what types are there?</code> &mdash; list entity & relationship types<br>
                    <code>what can I order by?</code> &mdash; sortable fields & metadata keys<br>
                    <code>what topics exist?</code> &mdash; all topics with counts<br>
                    <code>help</code> &mdash; this guide
                </div>
                <div style="font-weight:600;color:var(--text-muted);margin-top:8px;">Local timeline commands (no LLM needed):</div>
                <div style="padding-left:8px;">
                    ${timelineExamples}<br>
                    These switch the graph to <b>Timeline</b> using the current module defaults.
                </div>
                <div style="font-weight:600;color:var(--text-muted);margin-top:8px;">Keyboard:</div>
                <div style="padding-left:8px;">
                    <code>&uarr; &darr;</code> &mdash; browse input history<br>
                    <code>Enter</code> &mdash; send query
                </div>
                <div style="font-weight:600;color:var(--text-muted);margin-top:8px;">Tips:</div>
                <div style="padding-left:8px;">
                    &bull; SQL appears in the <b>Last SQL</b> panel (bottom-right) &mdash; click Copy<br>
                    &bull; Click a node first to add it as context for your question<br>
                    &bull; Results are capped at 50 rows in chat
                </div>
            </div>
        `;
        messagesEl.appendChild(div);
        messagesEl.scrollTop = messagesEl.scrollHeight;
    }

    // Show help on first load
    showHelp();

    // ---- Status check ----

    async function checkStatus() {
        try {
            const s = await apiClient.get('/api/chat/status');
            ollamaAvailable = s.available;
            statusEl.textContent = s.available
                ? `${s.model}`
                : 'Ollama offline';
            statusEl.className = 'chat-status ' + (s.available ? 'status-ok' : 'status-err');
        } catch (_) {
            ollamaAvailable = false;
            statusEl.textContent = 'Chat unavailable';
            statusEl.className = 'chat-status status-err';
        }
    }

    checkStatus();

    // ---- Events ----

    inputEl.addEventListener('keydown', e => {
        if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); }
        if (e.key === 'ArrowUp' && inputHistory.length > 0) {
            e.preventDefault();
            if (inputHistIdx === -1) inputHistIdx = inputHistory.length;
            if (inputHistIdx > 0) {
                inputHistIdx--;
                inputEl.value = inputHistory[inputHistIdx];
            }
        }
        if (e.key === 'ArrowDown' && inputHistIdx >= 0) {
            e.preventDefault();
            inputHistIdx++;
            if (inputHistIdx >= inputHistory.length) {
                inputHistIdx = -1;
                inputEl.value = '';
            } else {
                inputEl.value = inputHistory[inputHistIdx];
            }
        }
    });
    sendBtn.addEventListener('click', sendMessage);
    toolsBtn.addEventListener('click', () => {
        window.dispatchEvent(new CustomEvent('kgx:open-tools'));
    });
    helpBtn.addEventListener('click', showHelp);
    clearBtn.addEventListener('click', () => {
        history = [];
        messagesEl.innerHTML = '';
    });

    eventBus.on('node:selected', ({ id, name, type }) => {
        contextNode = { id, name, type };
    });

    eventBus.on('skill:started', ({ job_id, skill, entity_name }) => {
        const div = appendMessage('assistant',
            `Running skill "${skill}" for ${entity_name || job_id}…`);
        div.dataset.jobId = job_id;
        streamJobOutput(job_id, div);
    });

    async function runTimelineCommand(command) {
        return new Promise(resolve => {
            eventBus.emit('timeline:command', {
                ...command,
                callback: resolve,
            });
        });
    }

    function parseLocalTimelineCommand(text) {
        const raw = String(text || '').trim();
        if (!raw) return null;
        const normalized = raw.replace(/\s+/g, ' ').trim();
        const lower = normalized.toLowerCase();
        if (lower === 'timeline' || lower === 'layout timeline') {
            return { anchorType: '', orderField: '', reset: false };
        }
        if (lower === 'timeline reset') {
            return { reset: true };
        }
        return null;
    }

    // ---- Send ----

    async function sendMessage() {
        const text = inputEl.value.trim();
        if (!text) return;

        const localTimelineCommand = parseLocalTimelineCommand(text);
        if (localTimelineCommand) {
            inputEl.value = '';
            inputHistory.push(text);
            inputHistIdx = -1;
            appendMessage('user', text);
            inputEl.disabled = true;
            sendBtn.disabled = true;
            try {
                const result = await runTimelineCommand(localTimelineCommand);
                appendMessage('assistant', result?.message || 'Timeline updated.');
            } catch (err) {
                appendError(err.message);
            } finally {
                inputEl.disabled = false;
                sendBtn.disabled = false;
                inputEl.focus();
            }
            return;
        }

        // Inject node context if available
        let message = text;
        if (contextNode && !text.toLowerCase().includes(contextNode.name?.toLowerCase() || '___')) {
            message = `(Context: selected node is "${contextNode.name}" [${contextNode.type}, id: ${contextNode.id}])\n${text}`;
        }

        inputEl.value = '';
        inputHistory.push(text);
        inputHistIdx = -1;
        appendMessage('user', text);
        const thinkingEl = appendThinking();
        inputEl.disabled = true;
        sendBtn.disabled = true;

        try {
            const data = await apiClient.post('/api/chat', {
                message,
                history: history.slice(-10), // last 10 turns
            });

            thinkingEl.remove();

            // Emit SQL to the display panel — use data.sql or extract from content
            const sql = data.sql || extractSQL(data.content);
            if (sql) {
                eventBus.emit('chat:sql-executed', { sql });
            }

            if (data.intent === 'query') {
                appendQueryResult(data);
            } else if (data.intent === 'mutation') {
                appendMutationPreview(data);
            } else {
                appendAnswerResult(data);
            }

            // Maintain history with the raw user message (not context-injected)
            history.push({ role: 'user', content: text });
            history.push({ role: 'assistant', content: data.content || '' });

        } catch (err) {
            thinkingEl.remove();
            appendError(err.message);
        } finally {
            inputEl.disabled = false;
            sendBtn.disabled = false;
            inputEl.focus();
        }
    }

    // ---- Render helpers ----

    function appendMessage(role, text) {
        const div = document.createElement('div');
        div.className = `chat-msg chat-msg-${role}`;
        div.textContent = text;
        messagesEl.appendChild(div);
        messagesEl.scrollTop = messagesEl.scrollHeight;
        return div;
    }

    function appendThinking() {
        const div = document.createElement('div');
        div.className = 'chat-msg chat-msg-thinking';
        div.innerHTML = '<span class="chat-dots"><span>.</span><span>.</span><span>.</span></span>';
        messagesEl.appendChild(div);
        messagesEl.scrollTop = messagesEl.scrollHeight;
        return div;
    }

    function appendError(msg) {
        const div = document.createElement('div');
        div.className = 'chat-msg chat-msg-error';
        div.textContent = `Error: ${msg}`;
        messagesEl.appendChild(div);
        messagesEl.scrollTop = messagesEl.scrollHeight;
    }

    function normalizedPresentation(data) {
        const source = (data && typeof data.presentation === 'object' && data.presentation) ? data.presentation : {};
        const availableViews = Array.isArray(source.available_views) && source.available_views.length
            ? source.available_views
            : inferAvailableViews(data);
        const primaryView = typeof source.primary_view === 'string' && source.primary_view
            ? source.primary_view
            : availableViews[0] || 'message';
        return {
            ...source,
            available_views: availableViews,
            primary_view: primaryView,
            prefer_summary: Boolean(source.prefer_summary),
            prefer_table: Boolean(source.prefer_table),
        };
    }

    function inferAvailableViews(data) {
        if (data?.intent === 'query') return ['table'];
        if (data?.intent === 'mutation') return ['message', 'sql'];
        if (data?.results && data.results.length > 0) return ['summary', 'table'];
        return ['message'];
    }

    function appendAnswerResult(data) {
        const presentation = normalizedPresentation(data);
        const div = document.createElement('div');
        div.className = 'chat-msg chat-msg-result chat-msg-answer';

        const header = buildPresentationHeader(data, presentation);
        if (header) {
            div.appendChild(header);
        }

        if (data.error) {
            const err = document.createElement('div');
            err.className = 'chat-result-error';
            err.textContent = data.error;
            div.appendChild(err);
        }

        if (presentation.primary_view === 'summary' || presentation.available_views.includes('summary')) {
            const summaryEl = document.createElement('div');
            summaryEl.className = 'chat-answer-summary';
            summaryEl.textContent = data.content || data.error || '(no response)';
            div.appendChild(summaryEl);
        } else if (data.content) {
            const msg = document.createElement('div');
            msg.className = 'chat-answer-message';
            msg.textContent = data.content;
            div.appendChild(msg);
        }

        if (presentation.available_views.includes('table')) {
            appendTableSection(div, data, { secondary: presentation.primary_view !== 'table' });
        } else if (!data.content && (!data.results || data.results.length === 0) && !data.error) {
            const empty = document.createElement('div');
            empty.className = 'chat-result-empty';
            empty.textContent = 'No results';
            div.appendChild(empty);
        }

        if (data.artifact && typeof data.artifact === 'object') {
            div.appendChild(buildArtifactInspector(data.artifact));
        }

        messagesEl.appendChild(div);
        messagesEl.scrollTop = messagesEl.scrollHeight;
    }

    function appendQueryResult(data) {
        const div = document.createElement('div');
        div.className = 'chat-msg chat-msg-result';

        const header = buildPresentationHeader(data, normalizedPresentation(data));
        if (header) {
            div.appendChild(header);
        }

        if (data.error) {
            const err = document.createElement('div');
            err.className = 'chat-result-error';
            err.textContent = data.error;
            div.appendChild(err);
        } else if (data.results && data.results.length > 0) {
            appendTableSection(div, data, { secondary: false });
        } else {
            const empty = document.createElement('div');
            empty.className = 'chat-result-empty';
            empty.textContent = 'No results';
            div.appendChild(empty);
        }

        messagesEl.appendChild(div);
        messagesEl.scrollTop = messagesEl.scrollHeight;
    }

    function buildPresentationHeader(data, presentation) {
        const header = document.createElement('div');
        header.className = 'chat-result-header';
        const count = Number.isFinite(data.count) ? data.count : (Array.isArray(data.results) ? data.results.length : 0);
        const meta = [];
        if (presentation.primary_view === 'summary') {
            meta.push('Summary');
        } else if (presentation.primary_view === 'table') {
            meta.push(`${count} row${count !== 1 ? 's' : ''}`);
        } else {
            meta.push('Message');
        }
        if (presentation.artifact_kind) {
            meta.push(presentation.artifact_kind.replace(/_/g, ' '));
        }
        if (presentation.summary_style) {
            meta.push(presentation.summary_style);
        }
        header.textContent = meta.join(' · ');
        if (data.sql) {
            const sqlSpan = document.createElement('code');
            sqlSpan.className = 'chat-sql-inline';
            sqlSpan.textContent = data.sql.length > 80 ? data.sql.slice(0, 80) + '…' : data.sql;
            header.appendChild(sqlSpan);
        }
        return header;
    }

    function appendTableSection(container, data, { secondary = false } = {}) {
        const rows = Array.isArray(data.results) ? data.results : [];
        if (!rows.length) {
            const empty = document.createElement('div');
            empty.className = 'chat-result-empty';
            empty.textContent = 'No results';
            container.appendChild(empty);
            return;
        }
        const section = document.createElement('div');
        section.className = secondary ? 'chat-result-section chat-result-section-secondary' : 'chat-result-section';
        if (secondary) {
            const label = document.createElement('div');
            label.className = 'chat-result-section-label';
            label.textContent = 'Supporting rows';
            section.appendChild(label);
        }
        section.appendChild(buildTable(rows.slice(0, 50)));
        if ((data.count ?? rows.length) > 50) {
            const more = document.createElement('div');
            more.className = 'chat-result-more';
            more.textContent = `…and ${(data.count ?? rows.length) - 50} more rows`;
            section.appendChild(more);
        }
        appendRowActions(section, data, rows);
        container.appendChild(section);
    }

    function appendRowActions(container, data, rows) {
        const ids = rows.map(r => r.id).filter(Boolean);
        if (ids.length === 0 || !data.sql) return;
        const actions = document.createElement('div');
        actions.className = 'chat-filter-actions';
        actions.innerHTML = `
            <button class="chat-filter-btn" data-action="highlight" title="Highlight these result nodes in the graph">Highlight ${ids.length}</button>
            <button class="chat-filter-btn" data-action="apply" title="Hide these result nodes in the graph">Hide ${ids.length}</button>
            <button class="chat-filter-btn" data-action="save" title="Save this result query as a reusable SQL filter">Save filter</button>
        `;
        const hlBtn = actions.querySelector('[data-action="highlight"]');
        hlBtn.addEventListener('click', () => {
            eventBus.emit('node:highlight', { ids });
            hlBtn.textContent = `Highlighted (${ids.length})`;
        });
        eventBus.on('node:highlight-cleared', () => {
            hlBtn.textContent = `Highlight ${ids.length}`;
        });
        actions.querySelector('[data-action="apply"]').addEventListener('click', () => {
            const filterId = 'chat-' + Date.now();
            eventBus.emit('node:sql-filter', { filter_id: filterId, ids, active: true });
            const btn = actions.querySelector('[data-action="apply"]');
            btn.textContent = `Hidden (${ids.length})`;
            btn.disabled = true;
        });
        actions.querySelector('[data-action="save"]').addEventListener('click', () => {
            const name = prompt('Filter name:', 'Chat filter');
            if (!name) return;
            eventBus.emit('chat:save-filter', { name, sql: data.sql });
            const btn = actions.querySelector('[data-action="save"]');
            btn.textContent = 'Saved!';
            btn.disabled = true;
        });
        container.appendChild(actions);
    }

    function buildArtifactInspector(artifact) {
        const details = document.createElement('details');
        details.className = 'chat-artifact-details';
        const summary = document.createElement('summary');
        summary.className = 'chat-artifact-summary';
        const kind = String(artifact.artifact_kind || 'artifact').replace(/_/g, ' ');
        const rows = Array.isArray(artifact.rows) ? artifact.rows.length : 0;
        summary.textContent = `Inspect artifact · ${kind} · ${rows} row${rows !== 1 ? 's' : ''}`;
        details.appendChild(summary);

        const pre = document.createElement('pre');
        pre.className = 'chat-artifact-json';
        pre.textContent = JSON.stringify(artifact, null, 2);
        details.appendChild(pre);
        return details;
    }

    function appendMutationPreview(data) {
        const div = document.createElement('div');
        div.className = 'chat-msg chat-msg-mutation';

        div.innerHTML = `
            <div class="chat-mutation-label">Mutation detected</div>
            <code class="chat-mutation-sql">${escHtml(data.sql || '')}</code>
            <button class="chat-mutation-btn" title="Open the mutation review dialog before executing this change">Review &amp; Confirm</button>
        `;

        div.querySelector('.chat-mutation-btn').addEventListener('click', () => {
            eventBus.emit('chat:mutation', {
                sql: data.sql,
                token: data.token,
                preview: null,
            });
        });

        messagesEl.appendChild(div);
        messagesEl.scrollTop = messagesEl.scrollHeight;
    }

    function buildTable(rows) {
        if (!rows.length) return document.createTextNode('');
        const preferredPrefix = ['id', 'name', 'type'];
        const discoveredKeys = [];
        const seenKeys = new Set();
        for (const key of preferredPrefix) {
            if (rows.some(row => Object.prototype.hasOwnProperty.call(row, key))) {
                discoveredKeys.push(key);
                seenKeys.add(key);
            }
        }
        for (const row of rows) {
            for (const key of Object.keys(row)) {
                if (seenKeys.has(key)) continue;
                discoveredKeys.push(key);
                seenKeys.add(key);
            }
        }
        const keys = discoveredKeys;
        const hasId = keys.includes('id');
        const wrapper = document.createElement('div');
        wrapper.className = 'chat-result-table-wrap';
        const table = document.createElement('table');
        table.className = 'chat-result-table';

        const thead = document.createElement('thead');
        thead.innerHTML = `<tr>${keys.map(k => `<th>${escHtml(k)}</th>`).join('')}</tr>`;
        table.appendChild(thead);

        const tbody = document.createElement('tbody');
        for (const row of rows) {
            const tr = document.createElement('tr');
            if (hasId && row.id) {
                tr.className = 'clickable-row';
                tr.title = 'Click to select & orbit';
                tr.addEventListener('click', () => {
                    eventBus.emit('node:selected', { id: row.id, type: row.type, name: row.name });
                    eventBus.emit('node:orbit', { id: row.id });
                });
            }
            tr.innerHTML = keys.map(k => {
                const val = row[k] == null ? '' : String(row[k]);
                const display = val.length > 60 ? val.slice(0, 60) + '…' : val;
                return `<td>${escHtml(display)}</td>`;
            }).join('');
            tbody.appendChild(tr);
        }
        table.appendChild(tbody);
        wrapper.appendChild(table);
        return wrapper;
    }

    function streamJobOutput(job_id, msgEl) {
        const output = document.createElement('pre');
        output.className = 'chat-skill-output';
        msgEl.appendChild(output);

        const evtSource = new EventSource(`/api/skill/stream/${job_id}`);

        evtSource.addEventListener('message', e => {
            const line = JSON.parse(e.data);
            output.textContent += line + '\n';
            messagesEl.scrollTop = messagesEl.scrollHeight;
        });

        evtSource.addEventListener('status', e => {
            const status = JSON.parse(e.data);
            msgEl.querySelector('.chat-skill-status')?.remove();
            const badge = document.createElement('span');
            badge.className = 'chat-skill-status';
            badge.textContent = ` [${status}]`;
            badge.style.color = status === 'completed' ? 'var(--success)' : 'var(--danger)';
            msgEl.appendChild(badge);
            if (status !== 'running') {
                evtSource.close();
                if (status === 'completed') {
                    eventBus.emit('db:changed', {});
                }
            }
        });

        evtSource.addEventListener('done', () => evtSource.close());
        evtSource.addEventListener('error', () => evtSource.close());
    }

    function extractSQL(text) {
        if (!text) return null;
        // Try ```sql ... ``` first
        let m = text.match(/```sql\s*([\s\S]*?)\s*```/i);
        if (m) return m[1].trim();
        // Try plain ``` ... ```
        m = text.match(/```\s*((?:SELECT|INSERT|UPDATE|DELETE|WITH)\b[\s\S]*?)\s*```/i);
        if (m) return m[1].trim();
        // Bare SQL (possibly with trailing ```)
        m = text.match(/((?:SELECT|INSERT|UPDATE|DELETE|WITH)\b[\s\S]*?)(?:\s*```\s*)?$/i);
        if (m) return m[1].trim();
        return null;
    }

    function escHtml(str) {
        return String(str ?? '')
            .replace(/&/g, '&amp;').replace(/</g, '&lt;')
            .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }
}
