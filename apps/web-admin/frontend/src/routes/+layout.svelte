<script lang="ts">
  import '../app.css';
  import { page } from '$app/state';
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

<nav>
  <a href="/" class:active={page.url.pathname === '/'}>Welten</a>
  <a href="/generate" class:active={page.url.pathname.startsWith('/generate')}>Generieren</a>
  <a href="/transcripts" class:active={page.url.pathname.startsWith('/transcript')}>Verläufe</a>
  <a href="/settings" class:active={page.url.pathname.startsWith('/settings')}>Einstellungen</a>
  <span class="grow"></span>
  <button class="nav-theme" onclick={toggle} title="Hell/Dunkel umschalten" aria-label="Theme">
    {theme === 'light' ? '🌙' : '☀️'}
  </button>
  <small>storyteller-admin</small>
</nav>

<main>{@render children()}</main>

<style>
  nav {
    display: flex; gap: 1rem; padding: 0.6rem 1rem;
    background: var(--nav-bg); color: var(--nav-fg); align-items: center;
  }
  nav a { color: var(--nav-muted); text-decoration: none; padding: 0.3rem 0.5rem; border-radius: 3px; }
  nav a.active { color: #fff; background: rgba(255, 255, 255, 0.15); }
  nav .grow { flex: 1; }
  nav small { color: var(--nav-muted); }
  nav .nav-theme {
    background: transparent; color: var(--nav-fg); border: 1px solid var(--nav-muted);
    padding: 0.1rem 0.4rem; font-size: 1rem; border-radius: 4px; cursor: pointer;
  }
  main { max-width: 1100px; margin: 0 auto; padding: 1.5rem; }
  :global(button) {
    background: #4a90e2; color: #fff; border: none;
    padding: 0.4rem 0.9rem; border-radius: 3px; cursor: pointer;
    font-size: 0.95rem;
  }
  :global(button.danger) { background: #c25450; }
  :global(button:disabled) { background: var(--border); color: var(--muted); cursor: not-allowed; }
  :global(input, select, textarea) {
    padding: 0.4rem; font-family: inherit; font-size: 0.95rem;
  }
  :global(textarea) { font-family: ui-monospace, Consolas, monospace; }
</style>
