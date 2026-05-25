<script lang="ts">
  import '../app.css';
  import '$lib/ui.css';
  import { onMount } from 'svelte';

  let { children } = $props();
  let storyteller_available = $state(true);

  async function refreshHealth() {
    try {
      const r = await fetch('/api/health');
      if (r.ok) {
        const j = await r.json();
        if (typeof j.storyteller_available === 'boolean') {
          storyteller_available = j.storyteller_available;
        }
      }
    } catch { /* ignore */ }
  }

  onMount(() => {
    refreshHealth();
    const id = setInterval(refreshHealth, 30000);
    return () => clearInterval(id);
  });
</script>

{#if !storyteller_available}
  <div class="storyteller-unavailable" role="status">
    Der Erzähler ist gerade nicht verfügbar — bitte einen Erwachsenen
    Bescheid sagen.
  </div>
{/if}

{@render children()}

<style>
  .storyteller-unavailable {
    padding: 0.6rem 1rem; font-size: 0.95rem;
    background: rgba(220, 50, 50, 0.22); color: #6b1111;
    border-bottom: 1px solid #c25450; text-align: center;
  }
</style>
