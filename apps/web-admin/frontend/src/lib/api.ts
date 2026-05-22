// Admin backend address. Override via VITE_BACKEND env var. When unset and
// running in the browser, default to the page's own origin — so the SPA
// served by the FastAPI backend talks back to that same host:port.
const _browser = typeof window !== 'undefined';
export const BACKEND =
  (import.meta.env.VITE_BACKEND as string | undefined) ??
  (_browser ? window.location.origin : 'http://localhost:8080');

export type WorldSummary = {
  id: string;
  name: string;
  genre: string;
  player_role: string;
};

export type ModelsSettings = {
  defaults: Record<string, unknown>;
  overrides: Record<string, unknown>;
};

export type AudioSettings = {
  default_backend: string;
  overrides: Record<string, unknown>;
  allowed_backends: string[];
};

export type ModerationSettings = {
  enabled_default: boolean;
  default_threshold: number;
  overrides: Record<string, unknown>;
};

function authToken(): string {
  try { return localStorage.getItem('st-token') || ''; } catch { return ''; }
}

/** fetch wrapper: attaches the optional bearer token; on 401 asks for it. */
async function afetch(url: string, init: RequestInit = {}): Promise<Response> {
  const t = authToken();
  const headers = new Headers(init.headers || {});
  if (t) headers.set('Authorization', `Bearer ${t}`);
  const r = await fetch(url, { ...init, headers });
  if (r.status === 401) {
    const entered = typeof window !== 'undefined'
      ? window.prompt('Admin-Passwort (STORYTELLER_ADMIN_TOKEN):') : null;
    if (entered) {
      try { localStorage.setItem('st-token', entered); } catch { /* ignore */ }
      location.reload();
    }
    throw new Error('unauthorized');
  }
  return r;
}

async function _json<T>(r: Response): Promise<T> {
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
  return r.json() as Promise<T>;
}

export async function listWorlds(): Promise<WorldSummary[]> {
  return _json(await afetch(`${BACKEND}/api/worlds`));
}

export async function getWorld(id: string): Promise<Record<string, unknown>> {
  return _json(await afetch(`${BACKEND}/api/worlds/${encodeURIComponent(id)}`));
}

export async function putWorld(id: string, data: unknown): Promise<unknown> {
  return _json(
    await afetch(`${BACKEND}/api/worlds/${encodeURIComponent(id)}`, {
      method: 'PUT',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(data)
    })
  );
}

export async function deleteWorld(id: string): Promise<unknown> {
  return _json(
    await afetch(`${BACKEND}/api/worlds/${encodeURIComponent(id)}`, {
      method: 'DELETE'
    })
  );
}

export type Job = {
  id: string;
  kind: string;
  title: string;
  status: 'running' | 'done' | 'error';
  elapsed: number;
  result_url: string | null;
  error: string | null;
  detail: string;
};

export type TranscriptSummary = {
  name: string;
  stem: string;
  events: number;
  modified: string;
};

export type TranscriptEvent = Record<string, unknown> & { type?: string };

export async function generateWorld(prompt: string): Promise<{ job_id: string }> {
  return _json(
    await afetch(`${BACKEND}/api/worlds/generate`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ prompt })
    })
  );
}

export async function suggestPiece(
  worldId: string,
  kind: string,
  prompt = ''
): Promise<{ kind: string; piece: Record<string, unknown> }> {
  return _json(
    await afetch(`${BACKEND}/api/worlds/${encodeURIComponent(worldId)}/suggest`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ kind, prompt })
    })
  );
}

export async function reindexWorld(id: string): Promise<{ job_id: string }> {
  return _json(
    await afetch(`${BACKEND}/api/worlds/${encodeURIComponent(id)}/reindex`, {
      method: 'POST'
    })
  );
}

export async function getJob(id: string): Promise<Job> {
  return _json(await afetch(`${BACKEND}/api/jobs/${encodeURIComponent(id)}`));
}

/** Poll a job until it leaves the "running" state. */
export async function waitForJob(
  id: string,
  onProgress?: (j: Job) => void,
  intervalMs = 2000
): Promise<Job> {
  for (;;) {
    const j = await getJob(id);
    onProgress?.(j);
    if (j.status !== 'running') return j;
    await new Promise((r) => setTimeout(r, intervalMs));
  }
}

export async function listTranscripts(): Promise<TranscriptSummary[]> {
  return _json(await afetch(`${BACKEND}/api/transcripts`));
}

export async function getTranscript(
  name: string
): Promise<{ name: string; stem: string; events: TranscriptEvent[] }> {
  return _json(await afetch(`${BACKEND}/api/transcripts/${encodeURIComponent(name)}`));
}

export type SaveGame = {
  thread_id: string;
  checkpoints: number;
  last_narration: string;
  world_id: string | null;
  world_name: string;
  source: string;
};

export async function listSaves(): Promise<SaveGame[]> {
  return _json(await afetch(`${BACKEND}/api/saves`));
}

export async function resetSave(threadId: string): Promise<unknown> {
  return _json(
    await afetch(`${BACKEND}/api/saves/${encodeURIComponent(threadId)}`, {
      method: 'DELETE'
    })
  );
}

export async function getSettings<T>(kind: 'models' | 'audio' | 'moderation'): Promise<T> {
  return _json(await afetch(`${BACKEND}/api/settings/${kind}`));
}

export async function putSettings(
  kind: 'models' | 'audio' | 'moderation',
  data: unknown
): Promise<unknown> {
  return _json(
    await afetch(`${BACKEND}/api/settings/${kind}`, {
      method: 'PUT',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(data)
    })
  );
}
