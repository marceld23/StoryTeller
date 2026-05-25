<script lang="ts">
  import { goto } from '$app/navigation';
  import { onMount } from 'svelte';
  import { generateWorld, waitForJob, type Job } from '$lib/api';

  let prompt: string = $state('');
  let job: Job | null = $state(null);
  let error: string = $state('');
  let busy: boolean = $state(false);

  // Hard cap surfaced by the backend (web.max_prompt_chars). Loaded once at
  // mount so the textarea can show a live counter + early "too long" warning
  // before the user hits Generieren and gets a 413.
  let maxChars: number = $state(300000);

  onMount(async () => {
    try {
      const r = await fetch('/api/health');
      if (r.ok) {
        const j = await r.json();
        const lim = j?.limits?.max_prompt_chars;
        if (typeof lim === 'number' && lim > 0) maxChars = lim;
      }
    } catch { /* keep fallback */ }
  });

  const tooLong = $derived(prompt.length > maxChars);

  async function run() {
    const p = prompt.trim();
    if (!p) return;
    if (tooLong) {
      error = `Prompt zu lang (${prompt.length} / ${maxChars} Zeichen).`;
      return;
    }
    error = '';
    busy = true;
    job = null;
    try {
      const { job_id } = await generateWorld(p);
      const finished = await waitForJob(job_id, (j) => (job = j));
      if (finished.status === 'error') {
        error = finished.error ?? 'unbekannter Fehler';
      } else if (finished.result_url) {
        // result_url is the new world id
        await goto(`/worlds/${finished.result_url}`);
      }
    } catch (e) {
      error = String(e);
    } finally {
      busy = false;
    }
  }
</script>

<h1>Welt aus Prompt generieren</h1>
<p class="hint">
  Das große Modell (<code>gen_llm</code>) entwirft eine vollständige Welt
  (Orte, Personen, Items, Glossar, Blueprint, Zufallslisten) und indexiert sie
  anschließend für RAG. Dauert je nach Modell 5–15 Minuten und kostet viele Tokens.
  Du kannst hier auch mehrseitige Briefings einfügen — Limit
  <strong>{maxChars.toLocaleString('de-DE')}</strong> Zeichen.
</p>

<textarea
  class="big"
  bind:value={prompt}
  rows="20"
  placeholder="z. B. 'Eine düstere Unterwasserstadt, in der Erinnerungen als Währung gehandelt werden.'

Du kannst hier auch mehrere Absätze mit Lore, Ton, Spielerrolle, gewünschten Personen und Orten reinpacken — je dichter der Brief, desto näher trifft die Generierung."
  disabled={busy}
></textarea>

<div class="meta">
  <span class:over={tooLong}>
    {prompt.length.toLocaleString('de-DE')} / {maxChars.toLocaleString('de-DE')} Zeichen
  </span>
</div>

<div class="actions">
  <button onclick={run} disabled={busy || !prompt.trim() || tooLong}>
    {busy ? 'Generiere…' : 'Generieren'}
  </button>
</div>

{#if job}
  <div class="status">
    <strong>{job.status}</strong> · {Math.round(job.elapsed)} s
    {#if job.detail}<div class="detail"><code>{job.detail}</code></div>{/if}
  </div>
{/if}

{#if error}<p class="error">{error}</p>{/if}

<style>
  textarea { width: 100%; box-sizing: border-box; }
  textarea.big { min-height: 22em; line-height: 1.5; resize: vertical; }
  .hint { color: var(--muted); font-size: 0.9rem; }
  .meta { text-align: right; color: var(--muted); font-size: 0.85rem; margin: 0.2rem 0 0.6rem; }
  .meta .over { color: #c25450; font-weight: 600; }
  .actions { margin: 0.8rem 0; }
  .status { background: var(--surface); padding: 0.7rem 1rem; border-radius: 4px; border-left: 3px solid #4a90e2; }
  .detail { margin-top: 0.4rem; color: var(--muted); }
  .error { color: #c25450; }
  code { background: var(--code-bg); padding: 0 4px; border-radius: 2px; }
</style>
