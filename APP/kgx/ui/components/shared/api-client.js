/**
 * ApiClient — single fetch wrapper for all API calls.
 * All components use this instead of raw fetch().
 */
export class ApiClient {
    constructor(baseUrl = '') {
        this.baseUrl = baseUrl;
    }

    async get(path) {
        const resp = await fetch(this.baseUrl + path);
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: resp.statusText }));
            throw new Error(err.detail || `GET ${path} failed: ${resp.status}`);
        }
        return resp.json();
    }

    async post(path, body = {}) {
        const resp = await fetch(this.baseUrl + path, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: resp.statusText }));
            throw new Error(err.detail || `POST ${path} failed: ${resp.status}`);
        }
        return resp.json();
    }

    async delete(path) {
        const resp = await fetch(this.baseUrl + path, { method: 'DELETE' });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: resp.statusText }));
            throw new Error(err.detail || `DELETE ${path} failed: ${resp.status}`);
        }
        return resp.json();
    }

    /** Open a WebSocket. Returns the WebSocket instance. */
    ws(path) {
        const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
        return new WebSocket(`${protocol}//${location.host}${path}`);
    }
}
