// Admin backend address. Override via VITE_BACKEND env var.
export const BACKEND =
  (import.meta.env.VITE_BACKEND as string | undefined) ?? 'http://localhost:8080';

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

async function _json<T>(r: Response): Promise<T> {
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
  return r.json() as Promise<T>;
}

export async function listWorlds(): Promise<WorldSummary[]> {
  return _json(await fetch(`${BACKEND}/api/worlds`));
}

export async function getWorld(id: string): Promise<Record<string, unknown>> {
  return _json(await fetch(`${BACKEND}/api/worlds/${encodeURIComponent(id)}`));
}

export async function putWorld(id: string, data: unknown): Promise<unknown> {
  return _json(
    await fetch(`${BACKEND}/api/worlds/${encodeURIComponent(id)}`, {
      method: 'PUT',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(data)
    })
  );
}

export async function deleteWorld(id: string): Promise<unknown> {
  return _json(
    await fetch(`${BACKEND}/api/worlds/${encodeURIComponent(id)}`, {
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
    await fetch(`${BACKEND}/api/worlds/generate`, {
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
    await fetch(`${BACKEND}/api/worlds/${encodeURIComponent(worldId)}/suggest`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ kind, prompt })
    })
  );
}

export async function reindexWorld(id: string): Promise<{ job_id: string }> {
  return _json(
    await fetch(`${BACKEND}/api/worlds/${encodeURIComponent(id)}/reindex`, {
      method: 'POST'
    })
  );
}

export async function getJob(id: string): Promise<Job> {
  return _json(await fetch(`${BACKEND}/api/jobs/${encodeURIComponent(id)}`));
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
  return _json(await fetch(`${BACKEND}/api/transcripts`));
}

export async function getTranscript(
  name: string
): Promise<{ name: string; stem: string; events: TranscriptEvent[] }> {
  return _json(await fetch(`${BACKEND}/api/transcripts/${encodeURIComponent(name)}`));
}

export async function getSettings<T>(kind: 'models' | 'audio' | 'moderation'): Promise<T> {
  return _json(await fetch(`${BACKEND}/api/settings/${kind}`));
}

export async function putSettings(
  kind: 'models' | 'audio' | 'moderation',
  data: unknown
): Promise<unknown> {
  return _json(
    await fetch(`${BACKEND}/api/settings/${kind}`, {
      method: 'PUT',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(data)
    })
  );
}
