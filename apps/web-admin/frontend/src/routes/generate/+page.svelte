<script lang="ts">
  import { goto } from '$app/navigation';
  import { generateWorld, waitForJob, type Job } from '$lib/api';

  let prompt: string = $state('');
  let job: Job | null = $state(null);
  let error: string = $state('');
  let busy: boolean = $state(false);

  async function run() {
    const p = prompt.trim();
    if (!p) return;
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
  anschließend für RAG. Dauert je nach Modell 1–3 Minuten und kostet Tokens.
</p>

<textarea
  bind:value={prompt}
  rows="5"
  placeholder="z. B. 'Eine düstere Unterwasserstadt, in der Erinnerungen als Währung gehandelt werden.'"
  disabled={busy}
></textarea>

<div class="actions">
  <button onclick={run} disabled={busy || !prompt.trim()}>
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
  .hint { color: #666; font-size: 0.9rem; }
  .actions { margin: 0.8rem 0; }
  .status { background: #fff; padding: 0.7rem 1rem; border-radius: 4px; border-left: 3px solid #4a90e2; }
  .detail { margin-top: 0.4rem; color: #555; }
  .error { color: #c25450; }
  code { background: #eef; padding: 0 4px; border-radius: 2px; }
</style>
