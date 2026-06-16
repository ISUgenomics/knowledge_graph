/**
 * EventBus — the ONLY way UI components communicate with each other.
 * Components never import each other directly.
 *
 * Event catalog:
 *   graph:loaded         {nodeCount, edgeCount}
 *   graph:refresh        {}  — re-fetch from API
 *   node:selected        {id, type, name}
 *   node:right-clicked   {id, type, name, x, y}
 *   node:hide            {id}
 *   node:show-all        {}
 *   node:expand          {id}
 *   node:highlight       {ids: [...]}
 *   node:focus           {id}  — pan/zoom camera to node
 *   edge:filter          {rel_type, visible}
 *   detail:loaded        {entity, relationships, neighbors}
 *   chat:result          {results, sql, entity_ids}
 *   chat:mutation        {sql, token, preview}
 *   skill:started        {job_id, skill_name}
 *   skill:output         {job_id, line}
 *   skill:completed      {job_id, exit_code}
 *   db:changed           {}  — DB was modified, trigger refresh
 *   layout:change        {layout}  — "force"|"hierarchical"|"clustered"
 *   sidebar:select       {id, type}
 */
export class EventBus {
    constructor() {
        this._listeners = {};
    }

    on(event, callback) {
        if (!this._listeners[event]) this._listeners[event] = [];
        this._listeners[event].push(callback);
        // Return unsubscribe function
        return () => this.off(event, callback);
    }

    off(event, callback) {
        if (!this._listeners[event]) return;
        this._listeners[event] = this._listeners[event].filter(cb => cb !== callback);
    }

    emit(event, data = {}) {
        if (!this._listeners[event]) return;
        for (const cb of this._listeners[event]) {
            try {
                cb(data);
            } catch (err) {
                console.error(`EventBus error in handler for "${event}":`, err);
            }
        }
    }
}
