<script lang="ts">
  import { onMount } from 'svelte';

  type Summary = {
    today_usd: number;
    cap_daily_usd: number;
    warn_threshold_pct: number;
    pct: number;
    over_cap: boolean;
    approaching: boolean;
    warned_today: boolean;
    enforce: boolean;
    days: { date: string; usd: number }[];
  };
  type Session = { thread_id: string; world_id: string | null; usd: number; last_ts: string | null };
  type CostConfig = {
    enforce: boolean;
    daily_cap_usd: number;
    warn_threshold_pct: number;
    usd_per_1m_input: number;
    usd_per_1m_output: number;
    usd_per_1m_embedding: number;
    usd_per_1m_tts_chars: number;
    usd_per_minute_stt: number;
    overrides: Record<string, unknown>;
  };

  let summary = $state<Summary | null>(null);
  let sessions = $state<Session[]>([]);
  let cfg = $state<CostConfig | null>(null);
  let busy = $state(false);
  let msg = $state('');

  async function load() {
    const [s, sess, c] = await Promise.all([
      fetch('/api/cost/summary?days=7').then(r => r.json()),
      fetch('/api/cost/sessions').then(r => r.json()),
      fetch('/api/cost/config').then(r => r.json()),
    ]);
    summary = s;
    sessions = sess.sessions ?? [];
    cfg = c;
  }

  onMount(load);

  async function resetDaily() {
    if (!confirm('Tages-Counter wirklich zurücksetzen? Eine pausierte Geschichte kann danach weiterlaufen.')) return;
    busy = true; msg = '';
    try {
      const r = await fetch('/api/cost/reset/daily', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: '{}' });
      const j = await r.json();
      msg = j.ok ? `Tag ${j.date} zurückgesetzt.` : 'Fehler.';
      await load();
    } finally { busy = false; }
  }

  async function resetSession(thread_id: string) {
    if (!confirm(`Counter für Session ${thread_id} zurücksetzen?`)) return;
    busy = true; msg = '';
    try {
      const r = await fetch(`/api/cost/reset/session/${encodeURIComponent(thread_id)}`, { method: 'POST' });
      const j = await r.json();
      msg = j.ok ? `Session ${thread_id} zurückgesetzt.` : 'Fehler.';
      await load();
    } finally { busy = false; }
  }

  async function saveConfig() {
    if (!cfg) return;
    busy = true; msg = '';
    try {
      const payload = {
        enforce: cfg.enforce,
        daily_cap_usd: Number(cfg.daily_cap_usd),
        warn_threshold_pct: Number(cfg.warn_threshold_pct),
        usd_per_1m_input: Number(cfg.usd_per_1m_input),
        usd_per_1m_output: Number(cfg.usd_per_1m_output),
        usd_per_1m_embedding: Number(cfg.usd_per_1m_embedding),
        usd_per_1m_tts_chars: Number(cfg.usd_per_1m_tts_chars),
        usd_per_minute_stt: Number(cfg.usd_per_minute_stt),
      };
      const r = await fetch('/api/cost/config', { method: 'PUT', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload) });
      const j = await r.json();
      msg = j.ok ? 'Konfiguration gespeichert. Geänderte Werte gelten ab dem nächsten Idle-Tick.' : 'Fehler.';
      await load();
    } finally { busy = false; }
  }
</script>

<h2>Kosten & Tageslimit</h2>
{#if msg}<p class="msg">{msg}</p>{/if}

{#if summary}
  <section class="hero" class:over={summary.over_cap} class:warn={summary.approaching && !summary.over_cap}>
    <div class="big">{summary.today_usd.toFixed(4)} <span class="unit">USD</span></div>
    <div class="meta">
      heute &nbsp;·&nbsp;
      Limit {summary.cap_daily_usd.toFixed(2)} USD &nbsp;·&nbsp;
      {summary.pct.toFixed(1)} % &nbsp;·&nbsp;
      {summary.enforce ? 'enforcement ON' : 'enforcement OFF'}
    </div>
    <div class="bar">
      <div class="fill" style="width: {Math.min(100, summary.pct).toFixed(1)}%"></div>
    </div>
    <div class="actions">
      <button class="danger" onclick={resetDaily} disabled={busy}>Tag zurücksetzen</button>
      {#if summary.over_cap}<span class="badge over">Pause aktiv</span>{/if}
      {#if summary.approaching && !summary.over_cap}<span class="badge warn">{summary.warn_threshold_pct}% Schwelle erreicht</span>{/if}
      {#if summary.warned_today}<span class="badge">Warnung heute schon ausgespielt</span>{/if}
    </div>
  </section>

  <section>
    <h3>Letzte 7 Tage</h3>
    <table class="days">
      <tbody>
        {#each summary.days as d (d.date)}
          <tr>
            <td class="date">{d.date}</td>
            <td class="usd">{d.usd.toFixed(4)} USD</td>
            <td class="trend"><div class="trend-bar" style="width: {summary.cap_daily_usd > 0 ? Math.min(100, d.usd / summary.cap_daily_usd * 100).toFixed(0) : 0}%"></div></td>
          </tr>
        {/each}
      </tbody>
    </table>
  </section>
{/if}

<section>
  <h3>Sessions heute</h3>
  {#if sessions.length === 0}
    <p class="muted">Noch keine Sessions heute.</p>
  {:else}
    <table class="sessions">
      <thead><tr><th>Thread</th><th>Welt</th><th>USD</th><th>letzte Aktivität</th><th></th></tr></thead>
      <tbody>
        {#each sessions as s (s.thread_id)}
          <tr>
            <td><code>{s.thread_id}</code></td>
            <td>{s.world_id ?? '—'}</td>
            <td>{s.usd.toFixed(4)}</td>
            <td><small>{s.last_ts ?? ''}</small></td>
            <td><button class="danger" onclick={() => resetSession(s.thread_id)} disabled={busy}>Reset</button></td>
          </tr>
        {/each}
      </tbody>
    </table>
  {/if}
</section>

{#if cfg}
  <section>
    <h3>Konfiguration</h3>
    <p class="muted">Lokale Endpunkte (Ollama, XTTS, faster-whisper) werden NICHT mitgezählt — nur Aufrufe an OpenAI-Default.</p>
    <div class="grid">
      <label><span>Enforcement</span>
        <select bind:value={cfg.enforce}><option value={true}>aktiv</option><option value={false}>aus</option></select>
      </label>
      <label><span>Tageslimit (USD)</span><input type="number" step="0.1" min="0" bind:value={cfg.daily_cap_usd} /></label>
      <label><span>Warnschwelle (%)</span><input type="number" step="1" min="0" max="100" bind:value={cfg.warn_threshold_pct} /></label>
      <label><span>USD / 1M Input-Token</span><input type="number" step="0.01" bind:value={cfg.usd_per_1m_input} /></label>
      <label><span>USD / 1M Output-Token</span><input type="number" step="0.01" bind:value={cfg.usd_per_1m_output} /></label>
      <label><span>USD / 1M Embedding-Token</span><input type="number" step="0.001" bind:value={cfg.usd_per_1m_embedding} /></label>
      <label><span>USD / 1M TTS-Zeichen</span><input type="number" step="0.5" bind:value={cfg.usd_per_1m_tts_chars} /></label>
      <label><span>USD / Minute STT</span><input type="number" step="0.001" bind:value={cfg.usd_per_minute_stt} /></label>
    </div>
    <div class="toolbar"><button onclick={saveConfig} disabled={busy}>Speichern</button></div>
  </section>
{/if}

<style>
  h2 { margin: 0 0 1rem; }
  section { margin: 1.5rem 0; }
  section h3 { margin: 0 0 0.7rem; }
  .msg { background: #1f4d2b; color: #cbe7d3; padding: 0.4rem 0.7rem; border-radius: 4px; }
  .hero { padding: 1rem; border: 1px solid var(--border); border-radius: 6px; background: var(--card-bg, transparent); }
  .hero.warn { border-color: #d4a200; }
  .hero.over { border-color: #c25450; }
  .hero .big { font-size: 2.4rem; font-weight: 600; }
  .hero .unit { font-size: 1rem; color: var(--muted); }
  .hero .meta { color: var(--muted); margin: 0.3rem 0 0.7rem; }
  .hero .bar { height: 8px; background: rgba(127,127,127,0.2); border-radius: 4px; overflow: hidden; }
  .hero .bar .fill { height: 100%; background: #4a90e2; transition: width 0.3s; }
  .hero.warn .bar .fill { background: #d4a200; }
  .hero.over .bar .fill { background: #c25450; }
  .hero .actions { display: flex; gap: 0.7rem; align-items: center; margin-top: 0.8rem; }
  .badge { background: rgba(127,127,127,0.2); color: var(--muted); padding: 0.15rem 0.6rem; border-radius: 999px; font-size: 0.85rem; }
  .badge.warn { background: rgba(212,162,0,0.25); color: #d4a200; }
  .badge.over { background: rgba(194,84,80,0.30); color: #c25450; }
  table { width: 100%; border-collapse: collapse; }
  th, td { padding: 0.35rem 0.5rem; text-align: left; border-bottom: 1px solid var(--border); vertical-align: middle; }
  .days .date { width: 8rem; font-family: ui-monospace, Consolas, monospace; }
  .days .usd { width: 8rem; text-align: right; }
  .days .trend { padding-left: 1rem; }
  .days .trend-bar { height: 6px; background: #4a90e2; border-radius: 3px; min-width: 2px; }
  .sessions code { font-size: 0.85rem; }
  .muted { color: var(--muted); }
  .grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 0.6rem 1rem; }
  .grid label { display: flex; flex-direction: column; gap: 0.2rem; font-size: 0.9rem; color: var(--muted); }
  .grid label span { font-size: 0.85rem; }
  .toolbar { display: flex; gap: 0.5rem; margin-top: 0.8rem; }
</style>
