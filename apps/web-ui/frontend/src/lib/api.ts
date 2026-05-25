// Backend address. Override via VITE_BACKEND env var (e.g. http://pi.local:8090).
// When unset and running in the browser, default to the page's own origin —
// so the SPA served by the FastAPI backend (HTTP + WebSocket) talks back to
// that same host:port without hard-coding an IP.
const _browser = typeof window !== 'undefined';
export const BACKEND =
  (import.meta.env.VITE_BACKEND as string | undefined) ??
  (_browser ? window.location.origin : 'http://localhost:8090');

// Sibling admin UI URL. The player web-ui (this app) runs on :8090 directly
// or behind Caddy at :443; the admin web-ui runs on :8080 directly or :8443
// behind Caddy. We derive the admin URL from the current `window.location`
// so the same SPA build works on `localhost:8090`, `story.local`, etc.
//
// Returns "" during SSR (no window) — callers gate the link on that.
export function adminUrl(): string {
  if (!_browser) return '';
  const { protocol, hostname, port } = window.location;
  // HTTPS via Caddy (default 443, or any non-8090 port assumed proxy).
  if (protocol === 'https:') return `https://${hostname}:8443/`;
  // Direct HTTP — the player-direct port is 8090; admin-direct is 8080.
  // Falls back to :8080 for any other plain-HTTP port too.
  void port;
  return `http://${hostname}:8080/`;
}

export type WorldSummary = {
  id: string;
  name: string;
  genre: string;
  player_role: string;
  description: string;
};

export type CreatedSession = {
  thread_id: string;
  world_id: string;
  opening: string;
};

function authToken(): string {
  try { return localStorage.getItem('st-token') || ''; } catch { return ''; }
}

function authHeaders(): Record<string, string> {
  const t = authToken();
  return t ? { Authorization: `Bearer ${t}` } : {};
}

function on401(r: Response): void {
  if (r.status === 401 && typeof window !== 'undefined') {
    const t = window.prompt('Zugriffstoken (STORYTELLER_WEB_TOKEN):');
    if (t) {
      try { localStorage.setItem('st-token', t); } catch { /* ignore */ }
      location.reload();
    }
  }
}

/** Append the auth token to a WS URL (browsers can't set WS headers). */
function wsToken(): string {
  const t = authToken();
  return t ? `&token=${encodeURIComponent(t)}` : '';
}

export async function listWorlds(): Promise<WorldSummary[]> {
  const r = await fetch(`${BACKEND}/api/worlds`, { headers: authHeaders() });
  if (!r.ok) { on401(r); throw new Error(`worlds: ${r.status}`); }
  return r.json();
}

export async function createSession(
  world_id: string,
  thread_id?: string
): Promise<CreatedSession> {
  const r = await fetch(`${BACKEND}/api/sessions`, {
    method: 'POST',
    headers: { 'content-type': 'application/json', ...authHeaders() },
    body: JSON.stringify({ world_id, thread_id })
  });
  if (!r.ok) { on401(r); throw new Error(`createSession: ${r.status}`); }
  return r.json();
}

/** Check whether a thread still has saved content on the server.
 *
 * Used to decide whether the "Fortsetzen" button is real or a stale
 * localStorage leftover — if the player or an admin deleted the save
 * elsewhere, the browser's `st-thread-<world>` entry would still point
 * at a now-empty thread.
 *
 * Three-state result so the caller can tell "couldn't reach the
 * server / 401 / 5xx" apart from "definitely empty":
 *   - true   → thread has content (memory_len > 0)
 *   - false  → thread is empty or missing (200 OK with memory_len=0)
 *   - null   → couldn't verify (network error, 401, 5xx — caller
 *              should leave localStorage alone)
 */
export async function threadHasContent(
  thread_id: string, world_id: string
): Promise<boolean | null> {
  try {
    const r = await fetch(
      `${BACKEND}/api/sessions/${encodeURIComponent(thread_id)}/state?world_id=${encodeURIComponent(world_id)}`,
      { headers: authHeaders() }
    );
    if (!r.ok) return null;
    const s = await r.json();
    if (typeof s.memory_len !== 'number') return null;
    return s.memory_len > 0;
  } catch {
    return null;
  }
}

/** Open a text-play WebSocket. */
export function openPlaySocket(thread_id: string, world_id: string): WebSocket {
  const wsBase = BACKEND.replace(/^http/, 'ws');
  const url = `${wsBase}/ws/play/${encodeURIComponent(thread_id)}?world_id=${encodeURIComponent(world_id)}${wsToken()}`;
  return new WebSocket(url);
}

/** Open a voice-play WebSocket (binary frames = audio). */
export function openVoiceSocket(thread_id: string, world_id: string): WebSocket {
  const wsBase = BACKEND.replace(/^http/, 'ws');
  const url = `${wsBase}/ws/voice/${encodeURIComponent(thread_id)}?world_id=${encodeURIComponent(world_id)}${wsToken()}`;
  const ws = new WebSocket(url);
  ws.binaryType = 'arraybuffer';
  return ws;
}

export type GeneratedWorld = { id: string; name: string; genre: string };

/** Player-facing world generation. Blocks 1–3 minutes while the
 * multi-step pipeline runs server-side; callers should show a spinner. */
export async function generatePlayerWorld(
  prompt: string
): Promise<GeneratedWorld> {
  const r = await fetch(`${BACKEND}/api/worlds/generate`, {
    method: 'POST',
    headers: { 'content-type': 'application/json', ...authHeaders() },
    body: JSON.stringify({ prompt })
  });
  if (!r.ok) {
    on401(r);
    const detail = await r.json().catch(() => ({ detail: r.statusText }));
    throw new Error(detail.detail || `generate: ${r.status}`);
  }
  return r.json();
}

/** Fetch the last narration's TTS audio for replay. Returns a Blob URL
 * the caller can hand to a `new Audio(url)` or a `<audio>` element.
 * The browser will cache nothing (server sends Cache-Control:no-store),
 * so each click costs one TTS call — that's intentional for the text-
 * mode 🔊 button: silent reading should stay free. */
export async function fetchReplayUrl(
  thread_id: string, world_id: string
): Promise<string> {
  const r = await fetch(
    `${BACKEND}/api/sessions/${encodeURIComponent(thread_id)}/replay?world_id=${encodeURIComponent(world_id)}`,
    { headers: authHeaders() }
  );
  if (!r.ok) { on401(r); throw new Error(`replay: ${r.status}`); }
  const blob = await r.blob();
  return URL.createObjectURL(blob);
}

/** Send a player-introduced world fact ("Vermerken: …") via REST.
 * The text gets classified + indexed in the per-world JSONL + RAG. */
export async function sessionNote(
  thread_id: string, world_id: string, text: string
): Promise<{ id: string; name: string; kind: string }> {
  const r = await fetch(
    `${BACKEND}/api/sessions/${encodeURIComponent(thread_id)}/note?world_id=${encodeURIComponent(world_id)}`,
    {
      method: 'POST',
      headers: { 'content-type': 'application/json', ...authHeaders() },
      body: JSON.stringify({ text })
    }
  );
  if (!r.ok) {
    on401(r);
    const detail = await r.json().catch(() => ({ detail: r.statusText }));
    throw new Error(detail.detail || `note: ${r.status}`);
  }
  return r.json();
}
