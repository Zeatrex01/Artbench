// HTTP API client. Every call resolves to JSON or throws an Error with the server's message (ARCHITECTURE.md, HTTP API).
async function parse(response) {
  const json = await response.json().catch(() => ({ error: response.statusText }));
  if (!response.ok || json.error) {
    const err = json.error;                  // /api/* sends a string, /api/v1 an object {code, message}
    throw new Error((err && typeof err === 'object' ? err.message : err) || response.statusText);
  }
  return json;
}

export const api = {
  get(path, params = {}) {
    const query = new URLSearchParams(params).toString();
    return fetch(path + (query ? '?' + query : '')).then(parse);
  },
  /** Like get(), but returns { status, data } and does not throw on 202 (work still pending). */
  async getWithStatus(path, params = {}) {
    const query = new URLSearchParams(params).toString();
    const r = await fetch(path + (query ? '?' + query : ''));
    const data = await r.json().catch(() => ({ error: r.statusText }));
    if (!r.ok && r.status !== 202) throw new Error(data.error || r.statusText);
    return { status: r.status, data };
  },
  post(path, body) {
    return fetch(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }).then(parse);
  },
  thumbURL(project, path) {
    return `/api/thumb?project=${encodeURIComponent(project)}&path=${encodeURIComponent(path)}`;
  },
};
