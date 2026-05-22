<script lang="ts">
  import { onMount } from 'svelte';
  import { listSaves, resetSave, type SaveGame } from '$lib/api';

  let items: SaveGame[] = $state([]);
  let error: string = $state('');
  let loading: boolean = $state(true);
  let busy: string = $state(''); // thread_id currently being reset

  async function load() {
    loading = true;
    error = '';
    try {
      items = await listSaves();
    } catch (e) {
      error = String(e);
    } finally {
      loading = false;
    }
  }

  async function reset(s: SaveGame) {
    const label = s.world_name || s.thread_id;
    if (
      !confirm(
        `Spielstand „${label}" (${s.checkpoints} Schritte) wirklich zurücksetzen?\n` +
          `Der gesamte Fortschritt geht verloren und die Welt startet von vorn.`
      )
    )
      return;
    busy = s.thread_id;
    error = '';
    try {
      await resetSave(s.thread_id);
      await load();
    } catch (e) {
      error = String(e);
    } finally {
      busy = '';
    }
  }

  onMount(load);
</script>

<h1>Spielstände</h1>
<p class="hint">
  Jede gespeicherte Sitzung kann zurückgesetzt werden — danach beginnt die Welt
  wieder mit der Eröffnung. <strong>Zurücksetzen kann nicht rückgängig gemacht
  werden.</strong>
</p>
{#if error}<p class="error">{error}</p>{/if}
{#if loading}
  <p>Lade…</p>
{:else if items.length === 0}
  <p>Keine gespeicherten Spielstände.</p>
{:else}
  <table>
    <thead>
      <tr><th>Welt</th><th>Quelle</th><th>Schritte</th><th>Zuletzt</th><th></th></tr>
    </thead>
    <tbody>
      {#each items as s (s.thread_id)}
        <tr>
          <td>
            <strong>{s.world_name}</strong>
            <div class="tid">{s.thread_id}</div>
          </td>
          <td><span class="src">{s.source}</span></td>
          <td>{s.checkpoints}</td>
          <td class="last">{s.last_narration || '—'}</td>
          <td>
            <button
              class="danger"
              disabled={busy === s.thread_id}
              onclick={() => reset(s)}
            >
              {busy === s.thread_id ? 'Setze zurück…' : 'Zurücksetzen'}
            </button>
          </td>
        </tr>
      {/each}
    </tbody>
  </table>
{/if}

<style>
  table { width: 100%; border-collapse: collapse; background: var(--surface); }
  th, td { padding: 0.5rem 0.7rem; text-align: left; border-bottom: 1px solid var(--border); vertical-align: top; }
  th { background: var(--surface-2); }
  .hint { color: var(--muted, #888); max-width: 60ch; }
  .error { color: #c25450; }
  .tid { font-size: 0.78rem; color: var(--muted, #888); font-family: monospace; }
  .src { font-size: 0.8rem; padding: 0.1rem 0.4rem; border-radius: 3px; background: var(--surface-2); }
  .last { max-width: 40ch; color: var(--muted, #888); font-size: 0.85rem; }
  button.danger {
    background: #c25450; color: #fff; border: none; padding: 0.35rem 0.7rem;
    border-radius: 4px; cursor: pointer; white-space: nowrap;
  }
  button.danger:disabled { opacity: 0.6; cursor: default; }
</style>
