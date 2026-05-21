<script lang="ts">
  import { onMount } from 'svelte';
  import { listTranscripts, type TranscriptSummary } from '$lib/api';

  let items: TranscriptSummary[] = $state([]);
  let error: string = $state('');
  let loading: boolean = $state(true);

  onMount(async () => {
    try {
      items = await listTranscripts();
    } catch (e) {
      error = String(e);
    } finally {
      loading = false;
    }
  });
</script>

<h1>Verläufe</h1>
{#if error}<p class="error">{error}</p>{/if}
{#if loading}
  <p>Lade…</p>
{:else if items.length === 0}
  <p>Noch keine Verläufe aufgezeichnet.</p>
{:else}
  <table>
    <thead><tr><th>Sitzung</th><th>Ereignisse</th><th>Geändert</th></tr></thead>
    <tbody>
      {#each items as t (t.name)}
        <tr>
          <td><a href={`/transcripts/${encodeURIComponent(t.name)}`}>{t.stem}</a></td>
          <td>{t.events}</td>
          <td>{t.modified}</td>
        </tr>
      {/each}
    </tbody>
  </table>
{/if}

<style>
  table { width: 100%; border-collapse: collapse; background: white; }
  th, td { padding: 0.5rem 0.7rem; text-align: left; border-bottom: 1px solid #eee; }
  th { background: #fafafa; }
  .error { color: #c25450; }
  a { color: #2a6dbd; text-decoration: none; }
  a:hover { text-decoration: underline; }
</style>
