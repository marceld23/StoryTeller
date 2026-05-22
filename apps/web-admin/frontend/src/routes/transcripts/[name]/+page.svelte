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
    return typeof v === 'string' ? v : JSON.stringify(v, null, 2);
  }
  function asArr(v: unknown): Record<string, unknown>[] {
    return Array.isArray(v) ? (v as Record<string, unknown>[]) : [];
  }
  function body(m: Record<string, unknown>): string {
    if (typeof m.content === 'string' && m.content) return m.content;
    if (m.tool_calls) return str(m.tool_calls);
    return '';
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
      {:else if e.type === 'prompt'}
        <details class="card prompt">
          <summary>📤 Prompt an LLM — {str(e.model)} ·
            {asArr(e.messages).length} Nachrichten{e.tools ? ' · +tools' : ''}</summary>
          {#each asArr(e.messages) as m, j (j)}
            <div class="msg">
              <b>{str(m.role)}{m.tool_calls ? ' (tool_calls)' : ''}</b>
              <pre>{body(m)}</pre>
            </div>
          {/each}
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
  .card { padding: 0.6rem 0.9rem; border-radius: 5px; background: var(--surface); }
  .card.user { border-left: 3px solid #b4d273; }
  .card.narrator { border-left: 3px solid #4a90e2; }
  .card.tool { border-left: 3px solid #d0a040; }
  .card.mod { border-left: 3px solid #7aa37a; }
  .card.mod.bad { border-left-color: #c25450; }
  .card.prompt { border-left: 3px solid #9a7ad0; }
  .msg { margin: 0.4rem 0; border-top: 1px solid var(--border); padding-top: 0.3rem; }
  .msg b { font-size: 0.8rem; color: var(--muted); text-transform: uppercase; }
  .note { color: var(--muted); }
  pre { white-space: pre-wrap; margin: 0.4rem 0 0; font-size: 0.85rem; }
  .error { color: #c25450; }
  code { background: var(--code-bg); padding: 0 4px; border-radius: 2px; }
  a { color: var(--link); text-decoration: none; }
</style>
