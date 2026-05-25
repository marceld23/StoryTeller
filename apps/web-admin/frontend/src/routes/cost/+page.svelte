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
  type WorldSpend = {
    world_id: string;
    usd: number;
    calls: number;
    chat_in: number;
    chat_out: number;
    last_ts: string;
  };
  type ModelPrice = { input: number; output: number };
  type CostConfig = {
    enforce: boolean;
    daily_cap_usd: number;
    warn_threshold_pct: number;
    usd_per_1m_input: number;
    usd_per_1m_output: number;
    usd_per_1m_embedding: number;
    usd_per_1m_tts_chars: number;
    usd_per_minute_stt: number;
    usd_per_1m_moderation_chars: number;
    model_prices: Record<string, ModelPrice>;
    overrides: Record<string, unknown>;
  };

  let summary = $state<Summary | null>(null);
  let sessions = $state<Session[]>([]);
  let worlds = $state<WorldSpend[]>([]);
  let cfg = $state<CostConfig | null>(null);
  let busy = $state(false);
  let msg = $state('');

  // Locally edited per-model prices as an ordered array of
  // {model, input, output} rows — easier to render + add/remove than
  // a dict in Svelte. Synced back to a dict on save.
  type PriceRow = { model: string; input: number; output: number };
  let priceRows = $state<PriceRow[]>([]);

  async function load() {
    const [s, sess, w, c] = await Promise.all([
      fetch('/api/cost/summary?days=7').then(r => r.json()),
      fetch('/api/cost/sessions').then(r => r.json()),
      fetch('/api/cost/worlds?days=30').then(r => r.json()),
      fetch('/api/cost/config').then(r => r.json()),
    ]);
    summary = s;
    sessions = sess.sessions ?? [];
    worlds = w.worlds ?? [];
    cfg = c;
    priceRows = Object.entries(cfg!.model_prices ?? {})
      .map(([model, p]) => ({ model, input: p.input, output: p.output }))
      .sort((a, b) => a.model.localeCompare(b.model));
  }

  function addPriceRow() {
    priceRows = [...priceRows, { model: '', input: 0, output: 0 }];
  }
  function rmPriceRow(i: number) {
    priceRows = priceRows.filter((_, idx) => idx !== i);
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
      const mp: Record<string, ModelPrice> = {};
      for (const r of priceRows) {
        const m = r.model.trim();
        if (!m) continue;
        mp[m] = { input: Number(r.input) || 0, output: Number(r.output) || 0 };
      }
      const payload = {
        enforce: cfg.enforce,
        daily_cap_usd: Number(cfg.daily_cap_usd),
        warn_threshold_pct: Number(cfg.warn_threshold_pct),
        usd_per_1m_input: Number(cfg.usd_per_1m_input),
        usd_per_1m_output: Number(cfg.usd_per_1m_output),
        usd_per_1m_embedding: Number(cfg.usd_per_1m_embedding),
        usd_per_1m_tts_chars: Number(cfg.usd_per_1m_tts_chars),
        usd_per_minute_stt: Number(cfg.usd_per_minute_stt),
        usd_per_1m_moderation_chars: Number(cfg.usd_per_1m_moderation_chars),
        model_prices: mp,
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

<section>
  <h3>Kosten pro Welt (letzte 30 Tage)</h3>
  {#if worlds.length === 0}
    <p class="muted">Noch keine Kosten verbucht.</p>
  {:else}
    <table class="worlds">
      <thead><tr><th>Welt</th><th>USD</th><th>Calls</th><th>Tokens in/out</th><th>letzte Aktivität</th></tr></thead>
      <tbody>
        {#each worlds as w (w.world_id)}
          <tr>
            <td><code>{w.world_id}</code></td>
            <td>{w.usd.toFixed(4)}</td>
            <td>{w.calls}</td>
            <td><small>{w.chat_in.toLocaleString('de-DE')} / {w.chat_out.toLocaleString('de-DE')}</small></td>
            <td><small>{w.last_ts}</small></td>
          </tr>
        {/each}
      </tbody>
    </table>
  {/if}
</section>

{#if cfg}
  <section>
    <h3>Konfiguration</h3>
    <p class="muted">
      Kosten-Tracking gilt für <strong>OpenAI default</strong> + <strong>OpenRouter</strong>
      Endpoints. Lokale Server (Ollama, XTTS, faster-whisper auf einer
      anderen base_url) werden als kostenlos behandelt und tauchen
      nicht im Ledger auf.
    </p>
    <div class="grid">
      <label><span>Enforcement</span>
        <select bind:value={cfg.enforce}><option value={true}>aktiv</option><option value={false}>aus</option></select>
      </label>
      <label><span>Tageslimit (USD)</span><input type="number" step="0.1" min="0" bind:value={cfg.daily_cap_usd} /></label>
      <label><span>Warnschwelle (%)</span><input type="number" step="1" min="0" max="100" bind:value={cfg.warn_threshold_pct} /></label>
      <label><span>USD / 1M Input-Token (Default)</span><input type="number" step="0.01" bind:value={cfg.usd_per_1m_input} /></label>
      <label><span>USD / 1M Output-Token (Default)</span><input type="number" step="0.01" bind:value={cfg.usd_per_1m_output} /></label>
      <label><span>USD / 1M Embedding-Token</span><input type="number" step="0.001" bind:value={cfg.usd_per_1m_embedding} /></label>
      <label><span>USD / 1M TTS-Zeichen</span><input type="number" step="0.5" bind:value={cfg.usd_per_1m_tts_chars} /></label>
      <label><span>USD / Minute STT</span><input type="number" step="0.001" bind:value={cfg.usd_per_minute_stt} /></label>
      <label><span>USD / 1M Moderation-Zeichen</span><input type="number" step="0.001" bind:value={cfg.usd_per_1m_moderation_chars} /></label>
    </div>

    <h4>Modell-spezifische Preise <button class="small" onclick={addPriceRow}>+ Modell</button></h4>
    <p class="muted">
      Überschreibt die globalen Input/Output-Preise für bestimmte
      Modelle. Wichtig bei Hybrid-Stacks: gpt-5.4-mini ist ~4× billiger
      als gpt-5.4, DeepSeek V4 nochmal halber Preis. Modellname wie in
      <code>chat.completions.create(model=…)</code> (z. B.
      <code>gpt-5.4-mini</code>, <code>deepseek/deepseek-v4-pro</code>).
    </p>
    {#if priceRows.length === 0}
      <p class="muted">Keine modell-spezifischen Preise — globaler Default wird benutzt.</p>
    {:else}
      <table class="prices">
        <thead><tr><th>Modell</th><th>USD / 1M in</th><th>USD / 1M out</th><th></th></tr></thead>
        <tbody>
          {#each priceRows as r, i (i)}
            <tr>
              <td><input type="text" bind:value={r.model} placeholder="z. B. gpt-5.4-mini" /></td>
              <td><input type="number" step="0.001" bind:value={r.input} /></td>
              <td><input type="number" step="0.001" bind:value={r.output} /></td>
              <td><button class="danger small" onclick={() => rmPriceRow(i)}>×</button></td>
            </tr>
          {/each}
        </tbody>
      </table>
    {/if}

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
