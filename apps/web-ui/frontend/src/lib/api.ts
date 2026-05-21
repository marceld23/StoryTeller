// Backend address. Override via VITE_BACKEND env var (e.g. http://pi.local:8090).
// When unset and running in the browser, default to the page's own origin —
// so the SPA served by the FastAPI backend (HTTP + WebSocket) talks back to
// that same host:port without hard-coding an IP.
const _browser = typeof window !== 'undefined';
export const BACKEND =
  (import.meta.env.VITE_BACKEND as string | undefined) ??
  (_browser ? window.location.origin : 'http://localhost:8090');

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
