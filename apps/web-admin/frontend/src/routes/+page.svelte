<script lang="ts">
  import { onMount } from 'svelte';
  import { listWorlds, deleteWorld, type WorldSummary } from '$lib/api';

  let worlds: WorldSummary[] = $state([]);
  let error: string = $state('');
  let loading: boolean = $state(true);

  async function reload() {
    loading = true;
    error = '';
    try {
      worlds = await listWorlds();
    } catch (e) {
      error = String(e);
    } finally {
      loading = false;
    }
  }

  async function onDelete(id: string) {
    if (!confirm(`Welt '${id}' wirklich löschen?`)) return;
    try {
      await deleteWorld(id);
      await reload();
    } catch (e) {
      error = String(e);
    }
  }

  onMount(reload);
</script>

<h1>Welten</h1>
{#if error}<p class="error">{error}</p>{/if}
{#if loading}
  <p>Lade…</p>
{:else if worlds.length === 0}
  <p>Keine Welten gefunden.</p>
{:else}
  <table>
    <thead><tr><th>ID</th><th>Name</th><th>Genre</th><th>Spielerrolle</th><th></th></tr></thead>
    <tbody>
      {#each worlds as w (w.id)}
        <tr>
          <td><a href={`/worlds/${w.id}`}><code>{w.id}</code></a></td>
          <td>{w.name}</td>
          <td>{w.genre}</td>
          <td>{w.player_role}</td>
          <td>
            <button class="danger" onclick={() => onDelete(w.id)}>Löschen</button>
          </td>
        </tr>
      {/each}
    </tbody>
  </table>
{/if}

<style>
  table { width: 100%; border-collapse: collapse; background: white; }
  th, td { padding: 0.5rem 0.7rem; text-align: left; border-bottom: 1px solid #eee; }
  th { background: #fafafa; font-weight: 600; }
  .error { color: #c25450; }
  code { background: #eef; padding: 0 4px; border-radius: 2px; }
  a { color: #2a6dbd; text-decoration: none; }
  a:hover { text-decoration: underline; }
</style>
