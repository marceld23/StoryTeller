<script lang="ts">
  import { onMount } from 'svelte';

  type EndpointStatus = {
    role: string; ok: boolean; consecutive_failures: number;
    last_err_kind: string | null; last_err_http: number | null;
    last_err_detail: string; base_url: string; model: string | null;
    last_ok_ts: string | null; last_err_ts: string | null;
    paid_cloud: boolean;
    probe?: { ok: boolean; kind: string | null; http_status: number | null;
              detail: string; base_url: string; skipped?: boolean };
  };
  type Health = {
    checked_at: string; any_problems: boolean;
    endpoints: Record<string, EndpointStatus>;
  };

  let health = $state<Health | null>(null);
  let loading = $state(false);
  let probing = $state(false);
  let err = $state('');

  async function load(probe = false) {
    err = '';
    if (probe) probing = true; else loading = true;
    try {
      const r = await fetch(`/api/health/endpoints${probe ? '?probe=1' : ''}`);
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      health = await r.json();
    } catch (e: unknown) {
      err = e instanceof Error ? e.message : String(e);
    } finally {
      loading = false; probing = false;
    }
  }

  function fmtTs(ts: string | null): string {
    if (!ts) return '—';
    try { return new Date(ts).toLocaleString(); } catch { return ts; }
  }

  function rowClass(e: EndpointStatus): string {
    if (e.ok) return 'ok';
    if (e.last_err_kind && ['auth', 'bad_request'].includes(e.last_err_kind)) return 'err';
    return 'warn';
  }

  function kindLabel(k: string | null): string {
    if (!k) return '';
    return ({
      unreachable: 'nicht erreichbar', timeout: 'Timeout',
      auth: 'Auth (Key prüfen)', rate_limit: 'Rate-Limit',
      server: 'Server-Fehler', bad_request: 'Bad Request (Modell?)',
      unknown: 'unbekannt',
    } as Record<string, string>)[k] ?? k;
  }

  onMount(() => {
    load();
    const id = setInterval(() => load(), 30000);
    return () => clearInterval(id);
  });
</script>

<h2>Endpoint-Status</h2>

<p class="muted">
  Passiver Status aus <code>data/health.json</code> — wird vom Voice-Loop
  nach jedem echten Call aktualisiert. „Jetzt testen" pingt jeden Endpoint
  aktiv (kann ein paar Sekunden dauern).
</p>

<div class="controls">
  <button onclick={() => load()} disabled={loading || probing}>
    {loading ? 'lade…' : 'Aktualisieren'}
  </button>
  <button onclick={() => load(true)} disabled={loading || probing}>
    {probing ? 'prüfe…' : 'Jetzt testen'}
  </button>
  {#if health}
    <span class="muted">geprüft: {fmtTs(health.checked_at)}</span>
  {/if}
</div>

{#if err}<p class="err">Fehler: {err}</p>{/if}

{#if health}
  <table>
    <thead>
      <tr>
        <th>Rolle</th><th>Status</th><th>Modell</th><th>Endpoint</th>
        <th>Letzter Fehler</th><th>Letzter Erfolg</th>
        <th>Fehler in Folge</th>
      </tr>
    </thead>
    <tbody>
      {#each Object.entries(health.endpoints) as [role, e] (role)}
        <tr class={rowClass(e)}>
          <td><strong>{role}</strong></td>
          <td>
            {#if e.ok}
              ✓ OK
            {:else}
              ✗ {kindLabel(e.last_err_kind)}{#if e.last_err_http}{' ('}{e.last_err_http}{')'}{/if}
            {/if}
          </td>
          <td>{e.model ?? '—'}</td>
          <td class="ep">
            {e.base_url || '(OpenAI default)'}
            <span class="badge" class:paid={e.paid_cloud} class:local={!e.paid_cloud}>
              {e.paid_cloud ? 'Cloud' : 'Lokal'}
            </span>
          </td>
          <td>
            {fmtTs(e.last_err_ts)}
            {#if e.last_err_detail}<div class="detail">{e.last_err_detail}</div>{/if}
            {#if e.probe}
              <div class="detail probe">
                Probe:
                {#if e.probe.skipped}
                  übersprungen ({e.probe.detail})
                {:else if e.probe.ok}
                  ✓ {e.probe.http_status ?? ''}
                {:else}
                  ✗ {kindLabel(e.probe.kind)} {e.probe.detail}
                {/if}
              </div>
            {/if}
          </td>
          <td>{fmtTs(e.last_ok_ts)}</td>
          <td>{e.consecutive_failures}</td>
        </tr>
      {/each}
    </tbody>
  </table>

  <h3>Erklärung der Status-Arten</h3>
  <ul class="muted">
    <li><strong>auth</strong> / <strong>bad_request</strong> — Admin-Aktion nötig (API-Key falsch, Modell-ID unbekannt).</li>
    <li><strong>unreachable</strong> — Endpoint antwortet nicht (Internet weg bei Cloud-Endpoint, oder lokaler Server aus).</li>
    <li><strong>rate_limit</strong> / <strong>server</strong> / <strong>timeout</strong> — transient, regelt sich meist selbst.</li>
  </ul>
{:else if loading}
  <p>lade…</p>
{/if}

<style>
  .controls { display: flex; gap: 0.8rem; align-items: center; margin: 0.6rem 0 1rem; }
  table { width: 100%; border-collapse: collapse; margin-top: 0.6rem; }
  th, td { padding: 0.45rem 0.5rem; text-align: left; border-bottom: 1px solid var(--border); vertical-align: top; }
  th { background: var(--card-alt, transparent); font-weight: 600; font-size: 0.9rem; }
  tr.ok td:nth-child(2)  { color: #2c7a2c; }
  tr.warn td:nth-child(2) { color: #b8860b; }
  tr.err  td:nth-child(2) { color: #c25450; font-weight: 600; }
  .ep { font-family: ui-monospace, Consolas, monospace; font-size: 0.85rem; }
  .badge { display: inline-block; margin-left: 0.4rem; padding: 0.05rem 0.4rem;
            border-radius: 999px; font-size: 0.72rem; font-family: inherit; }
  .badge.paid  { background: rgba(74, 144, 226, 0.18); color: #4a90e2; }
  .badge.local { background: rgba(44, 122, 44, 0.18); color: #2c7a2c; }
  .detail { color: var(--muted); font-size: 0.82rem; margin-top: 0.2rem;
            font-family: ui-monospace, Consolas, monospace; word-break: break-word; }
  .detail.probe { color: #4a90e2; }
  .err { color: #c25450; }
  .muted { color: var(--muted); }
</style>
