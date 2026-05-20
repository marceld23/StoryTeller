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
