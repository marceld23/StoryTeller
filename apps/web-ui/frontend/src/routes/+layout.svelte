<script lang="ts">
  import '../app.css';
  import { onMount } from 'svelte';

  let theme = $state('dark');
  let { children } = $props();

  onMount(() => {
    theme = document.documentElement.dataset.theme || 'dark';
  });

  function toggle() {
    theme = theme === 'light' ? 'dark' : 'light';
    document.documentElement.dataset.theme = theme;
    try { localStorage.setItem('st-theme', theme); } catch { /* ignore */ }
  }
</script>

{@render children()}

<button class="theme-toggle" onclick={toggle}
        title="Hell/Dunkel umschalten" aria-label="Theme umschalten">
  {theme === 'light' ? '🌙' : '☀️'}
</button>
