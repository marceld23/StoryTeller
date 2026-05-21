<script lang="ts">
  import { page } from '$app/state';
  import { getWorld, putWorld, reindexWorld, waitForJob, type Job } from '$lib/api';

  let raw: string = $state('');
  let error: string = $state('');
  let status: string = $state('');
  let loading: boolean = $state(true);
  let reindexJob: Job | null = $state(null);
  let reindexing: boolean = $state(false);

  $effect(() => {
    const id = page.params.id;
    if (!id) return;
    loading = true;
    getWorld(id)
      .then((data) => {
        raw = JSON.stringify(data, null, 2);
        loading = false;
      })
      .catch((e) => {
        error = String(e);
        loading = false;
      });
  });

  async function onSave() {
    error = '';
    status = '';
    let parsed: unknown;
    try {
      parsed = JSON.parse(raw);
    } catch (e) {
      error = `JSON-Fehler: ${e}`;
      return;
    }
    try {
      await putWorld(page.params.id, parsed);
      status = 'gespeichert.';
    } catch (e) {
      error = String(e);
    }
  }

  async function onReindex() {
    error = '';
    status = '';
    reindexing = true;
    reindexJob = null;
    try {
      const { job_id } = await reindexWorld(page.params.id);
      const finished = await waitForJob(job_id, (j) => (reindexJob = j));
      if (finished.status === 'error') {
        error = finished.error ?? 'Reindex fehlgeschlagen';
      } else {
        status = finished.detail || 'Reindex fertig.';
      }
    } catch (e) {
      error = String(e);
    } finally {
      reindexing = false;
    }
  }
</script>

<a href="/">← zurück</a>
<h1>Welt: <code>{page.params.id}</code></h1>

{#if error}<p class="error">{error}</p>{/if}
{#if status}<p class="ok">{status}</p>{/if}

{#if loading}
  <p>Lade…</p>
{:else}
  <p class="hint">
    Minimaler JSON-Editor. Validierung erfolgt durch das Backend
    (Pydantic-Schema, <code>World</code>).
  </p>
  <textarea bind:value={raw} rows="40"></textarea>
  <div class="actions">
    <button onclick={onSave}>Speichern</button>
    <button onclick={onReindex} disabled={reindexing}>
      {reindexing ? 'Reindexiere…' : 'RAG neu indexieren'}
    </button>
  </div>
  {#if reindexJob}
    <p class="hint">Reindex: {reindexJob.status} · {reindexJob.detail}</p>
  {/if}
{/if}

<style>
  textarea { width: 100%; box-sizing: border-box; }
  .error { color: #c25450; }
  .ok { color: #4a9e4f; }
  .hint { color: #666; font-size: 0.9rem; }
  .actions { margin-top: 0.8rem; }
  code { background: #eef; padding: 0 4px; border-radius: 2px; }
  a { color: #2a6dbd; text-decoration: none; }
</style>
