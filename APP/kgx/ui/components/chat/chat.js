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

    // ---- Render shell ----

    container.innerHTML = `
        <div class="chat-messages" id="chat-messages"></div>
        <div class="chat-input-row">
            <div class="chat-status" id="chat-status"></div>
            <input id="chat-input" class="chat-input" placeholder="Ask about the graph… (Ollama required)" autocomplete="off">
            <button id="chat-send" class="chat-send-btn" title="Send">&#9654;</button>
            <button id="chat-clear" class="chat-clear-btn" title="Clear history">&#8635;</button>
        </div>
    `;

    const messagesEl = container.querySelector('#chat-messages');
    const inputEl    = container.querySelector('#chat-input');
    const sendBtn    = container.querySelector('#chat-send');
    const clearBtn   = container.querySelector('#chat-clear');
    const statusEl   = container.querySelector('#chat-status');

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
    });
    sendBtn.addEventListener('click', sendMessage);
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

    // ---- Send ----

    async function sendMessage() {
        const text = inputEl.value.trim();
        if (!text) return;

        // Inject node context if available
        let message = text;
        if (contextNode && !text.toLowerCase().includes(contextNode.name?.toLowerCase() || '___')) {
            message = `(Context: selected node is "${contextNode.name}" [${contextNode.type}, id: ${contextNode.id}])\n${text}`;
        }

        inputEl.value = '';
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

            if (data.intent === 'query') {
                appendQueryResult(data);
            } else if (data.intent === 'mutation') {
                appendMutationPreview(data);
            } else {
                appendMessage('assistant', data.content || data.error || '(no response)');
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

    function appendQueryResult(data) {
        const div = document.createElement('div');
        div.className = 'chat-msg chat-msg-result';

        const header = document.createElement('div');
        header.className = 'chat-result-header';
        header.textContent = `${data.count ?? 0} row${data.count !== 1 ? 's' : ''}`;
        if (data.sql) {
            const sqlSpan = document.createElement('code');
            sqlSpan.className = 'chat-sql-inline';
            sqlSpan.textContent = data.sql.length > 80 ? data.sql.slice(0, 80) + '…' : data.sql;
            header.appendChild(sqlSpan);
        }
        div.appendChild(header);

        if (data.error) {
            const err = document.createElement('div');
            err.className = 'chat-result-error';
            err.textContent = data.error;
            div.appendChild(err);
        } else if (data.results && data.results.length > 0) {
            div.appendChild(buildTable(data.results.slice(0, 50)));
            if (data.count > 50) {
                const more = document.createElement('div');
                more.className = 'chat-result-more';
                more.textContent = `…and ${data.count - 50} more rows`;
                div.appendChild(more);
            }
        } else {
            const empty = document.createElement('div');
            empty.className = 'chat-result-empty';
            empty.textContent = 'No results';
            div.appendChild(empty);
        }

        messagesEl.appendChild(div);
        messagesEl.scrollTop = messagesEl.scrollHeight;
    }

    function appendMutationPreview(data) {
        const div = document.createElement('div');
        div.className = 'chat-msg chat-msg-mutation';

        div.innerHTML = `
            <div class="chat-mutation-label">Mutation detected</div>
            <code class="chat-mutation-sql">${escHtml(data.sql || '')}</code>
            <button class="chat-mutation-btn">Review &amp; Confirm</button>
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
        const keys = Object.keys(rows[0]);
        const table = document.createElement('table');
        table.className = 'chat-result-table';

        const thead = document.createElement('thead');
        thead.innerHTML = `<tr>${keys.map(k => `<th>${escHtml(k)}</th>`).join('')}</tr>`;
        table.appendChild(thead);

        const tbody = document.createElement('tbody');
        for (const row of rows) {
            const tr = document.createElement('tr');
            tr.innerHTML = keys.map(k => {
                const val = row[k] == null ? '' : String(row[k]);
                const display = val.length > 60 ? val.slice(0, 60) + '…' : val;
                return `<td>${escHtml(display)}</td>`;
            }).join('');
            tbody.appendChild(tr);
        }
        table.appendChild(tbody);
        return table;
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

    function escHtml(str) {
        return String(str ?? '')
            .replace(/&/g, '&amp;').replace(/</g, '&lt;')
            .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }
}
