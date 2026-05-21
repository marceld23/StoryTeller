<script lang="ts">
  import { page } from '$app/state';
  import { getTranscript, type TranscriptEvent } from '$lib/api';

  let events: TranscriptEvent[] = $state([]);
  let stem: string = $state('');
  let error: string = $state('');
  let loading: boolean = $state(true);

  $effect(() => {
    const name = page.params.name;
    if (!name) return;
    loading = true;
    getTranscript(name)
      .then((d) => {
        events = d.events;
        stem = d.stem;
        loading = false;
      })
      .catch((e) => {
        error = String(e);
        loading = false;
      });
  });

  function str(v: unknown): string {
    return typeof v === 'string' ? v : JSON.stringify(v);
  }
</script>

<a href="/transcripts">← alle Verläufe</a>
<h1>Verlauf: <code>{stem}</code></h1>
{#if error}<p class="error">{error}</p>{/if}
{#if loading}
  <p>Lade…</p>
{:else}
  <div class="feed">
    {#each events as e, i (i)}
      {#if e.type === 'user'}
        <div class="card user">🧑 <b>Spieler:</b> {str(e.text)}</div>
      {:else if e.type === 'assistant'}
        <div class="card narrator">
          📖 <small>[{str(e.state)} · ${str(e.cost ?? 0)}]</small>
          <div>{str(e.text)}</div>
        </div>
      {:else if e.type === 'tool'}
        <details class="card tool">
          <summary>🔧 {str(e.name)}</summary>
          <pre>args: {str(e.args)}
result: {str(e.result)}</pre>
        </details>
      {:else if e.type === 'moderation'}
        <div class="card mod" class:bad={!e.ok}>
          🛡 Moderation: {e.ok ? 'OK' : 'BLOCKIERT'}
          {#if e.flagged && Array.isArray(e.flagged) && e.flagged.length}
            — {str(e.flagged)}
          {/if}
        </div>
      {:else if e.type === 'note'}
        <p class="note"><i>{str(e.text)}</i></p>
      {/if}
    {/each}
  </div>
{/if}

<style>
  .feed { display: flex; flex-direction: column; gap: 0.6rem; }
  .card { padding: 0.6rem 0.9rem; border-radius: 5px; background: #fff; }
  .card.user { border-left: 3px solid #b4d273; }
  .card.narrator { border-left: 3px solid #4a90e2; }
  .card.tool { border-left: 3px solid #d0a040; }
  .card.mod { border-left: 3px solid #7aa37a; }
  .card.mod.bad { border-left-color: #c25450; }
  .note { color: #888; }
  pre { white-space: pre-wrap; margin: 0.4rem 0 0; font-size: 0.85rem; }
  .error { color: #c25450; }
  code { background: #eef; padding: 0 4px; border-radius: 2px; }
  a { color: #2a6dbd; text-decoration: none; }
</style>
