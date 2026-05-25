<script lang="ts">
  import { onMount } from 'svelte';
  import {
    deleteTranscript,
    listTranscripts,
    type TranscriptSummary,
  } from '$lib/api';

  let items: TranscriptSummary[] = $state([]);
  let error: string = $state('');
  let loading: boolean = $state(true);
  // Two-stage confirm — click 🗑 once arms the row (button turns red,
  // label flips to "wirklich?"); a second click within ~5 s actually
  // deletes. Auto-disarms if the user clicks somewhere else.
  let armed: string = $state('');
  let armedTimer: number | undefined = undefined;

  onMount(async () => {
    try {
      items = await listTranscripts();
    } catch (e) {
      error = String(e);
    } finally {
      loading = false;
    }
  });

  function arm(name: string) {
    if (armed === name) return;
    armed = name;
    if (armedTimer !== undefined) window.clearTimeout(armedTimer);
    armedTimer = window.setTimeout(() => { armed = ''; }, 5000);
  }
  function disarm() {
    armed = '';
    if (armedTimer !== undefined) {
      window.clearTimeout(armedTimer);
      armedTimer = undefined;
    }
  }

  async function onDelete(name: string) {
    if (armed !== name) {
      arm(name);
      return;
    }
    disarm();
    try {
      await deleteTranscript(name);
      items = items.filter((t) => t.name !== name);
    } catch (e) {
      error = `Löschen fehlgeschlagen: ${e}`;
    }
  }
</script>

<h1>Verläufe</h1>
{#if error}<p class="error">{error}</p>{/if}
{#if loading}
  <p>Lade…</p>
{:else if items.length === 0}
  <p>Noch keine Verläufe aufgezeichnet.</p>
{:else}
  <p class="hint">
    Verläufe einer Welt werden außerdem automatisch gelöscht, wenn die
    Welt selbst gelöscht oder ihr Spielstand zurückgesetzt wird.
  </p>
  <table>
    <thead>
      <tr>
        <th>Sitzung</th>
        <th class="right">Ereignisse</th>
        <th>Geändert</th>
        <th class="actions"></th>
      </tr>
    </thead>
    <tbody>
      {#each items as t (t.name)}
        <tr>
          <td><a href={`/transcripts/${encodeURIComponent(t.name)}`}>{t.stem}</a></td>
          <td class="right">{t.events}</td>
          <td>{t.modified}</td>
          <td class="actions">
            <button class="trash" class:armed={armed === t.name}
                    onclick={() => onDelete(t.name)}
                    onmouseleave={armed === t.name ? undefined : disarm}
                    title={armed === t.name
                            ? 'Nochmal klicken zum endgültigen Löschen'
                            : 'Verlauf löschen'}>
              {armed === t.name ? 'wirklich? 🗑' : '🗑'}
            </button>
          </td>
        </tr>
      {/each}
    </tbody>
  </table>
{/if}

<style>
  table { width: 100%; border-collapse: collapse; background: var(--surface); }
  th, td { padding: 0.5rem 0.7rem; text-align: left; border-bottom: 1px solid var(--border); }
  th { background: var(--surface-2); }
  th.right, td.right { text-align: right; }
  th.actions, td.actions { text-align: right; width: 8rem; }
  .hint { color: var(--muted); font-size: 0.9rem; margin: 0.4rem 0 0.8rem; }
  .error { color: #c25450; }
  a { color: var(--link); text-decoration: none; }
  a:hover { text-decoration: underline; }
  .trash {
    background: transparent; color: var(--muted);
    border: 1px solid var(--border); border-radius: 4px;
    padding: 0.2rem 0.55rem; cursor: pointer; font-size: 0.9rem;
  }
  .trash:hover { color: #c25450; border-color: #c25450; }
  .trash.armed {
    background: #c25450; color: #fff; border-color: #c25450;
    font-weight: 600;
  }
</style>
