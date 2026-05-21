<script lang="ts">
  import { page } from '$app/state';
  let { children } = $props();
</script>

<nav>
  <a href="/" class:active={page.url.pathname === '/'}>Welten</a>
  <a href="/generate" class:active={page.url.pathname.startsWith('/generate')}>Generieren</a>
  <a href="/transcripts" class:active={page.url.pathname.startsWith('/transcript')}>Verläufe</a>
  <a href="/settings" class:active={page.url.pathname.startsWith('/settings')}>Einstellungen</a>
  <span class="grow"></span>
  <small>storyteller-admin</small>
</nav>

<main>{@render children()}</main>

<style>
  :global(html, body) {
    margin: 0;
    background: #f7f7f8;
    color: #111;
    font-family: system-ui, -apple-system, sans-serif;
  }
  nav {
    display: flex; gap: 1rem; padding: 0.6rem 1rem;
    background: #222; color: #ddd; align-items: center;
  }
  nav a { color: #aaa; text-decoration: none; padding: 0.3rem 0.5rem; border-radius: 3px; }
  nav a.active { color: #fff; background: #444; }
  nav .grow { flex: 1; }
  nav small { color: #888; }
  main { max-width: 1100px; margin: 0 auto; padding: 1.5rem; }
  :global(button) {
    background: #4a90e2; color: #fff; border: none;
    padding: 0.4rem 0.9rem; border-radius: 3px; cursor: pointer;
    font-size: 0.95rem;
  }
  :global(button.danger) { background: #c25450; }
  :global(button:disabled) { background: #aaa; cursor: not-allowed; }
  :global(input, select, textarea) {
    padding: 0.4rem; border: 1px solid #ccc; border-radius: 3px;
    font-family: inherit; font-size: 0.95rem;
  }
  :global(textarea) { font-family: ui-monospace, Consolas, monospace; }
</style>
