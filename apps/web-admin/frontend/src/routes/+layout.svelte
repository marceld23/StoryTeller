<script lang="ts">
  import '../app.css';
  import { page } from '$app/state';
  import { onMount } from 'svelte';

  let theme = $state('dark');
  let { children } = $props();
  let cost = $state<{ today_usd: number; cap_daily_usd: number; pct: number; over_cap: boolean; approaching: boolean } | null>(null);

  async function refreshCost() {
    try {
      const r = await fetch('/api/cost/summary?days=1');
      if (r.ok) cost = await r.json();
    } catch { /* ignore */ }
  }

  onMount(() => {
    theme = document.documentElement.dataset.theme || 'dark';
    refreshCost();
    const id = setInterval(refreshCost, 30000);
    return () => clearInterval(id);
  });

  function toggle() {
    theme = theme === 'light' ? 'dark' : 'light';
    document.documentElement.dataset.theme = theme;
    try { localStorage.setItem('st-theme', theme); } catch { /* ignore */ }
  }
</script>

<nav>
  <a href="/" class="brand" title="StoryTeller Admin">
    <img src="/favicon.png" alt="" />
    <span class="brand-label">storyteller-admin</span>
  </a>
  <a href="/" class:active={page.url.pathname === '/'}>Welten</a>
  <a href="/generate" class:active={page.url.pathname.startsWith('/generate')}>Generieren</a>
  <a href="/transcripts" class:active={page.url.pathname.startsWith('/transcript')}>Verläufe</a>
  <a href="/saves" class:active={page.url.pathname.startsWith('/saves')}>Spielstände</a>
  <a href="/cost" class:active={page.url.pathname.startsWith('/cost')}>Kosten</a>
  <a href="/settings" class:active={page.url.pathname.startsWith('/settings')}>Einstellungen</a>
  <span class="grow"></span>
  {#if cost && cost.cap_daily_usd > 0}
    <a class="cost-pill" class:over={cost.over_cap} class:warn={cost.approaching && !cost.over_cap} href="/cost" title="Tagesbudget">
      {cost.today_usd.toFixed(2)} / {cost.cap_daily_usd.toFixed(2)} USD
    </a>
  {/if}
  <button class="nav-theme" onclick={toggle} title="Hell/Dunkel umschalten" aria-label="Theme">
    {theme === 'light' ? '🌙' : '☀️'}
  </button>
</nav>

<main>{@render children()}</main>

<style>
  nav {
    display: flex; flex-wrap: wrap; gap: 0.5rem 1rem;
    padding: 0.5rem 0.8rem;
    background: var(--nav-bg); color: var(--nav-fg); align-items: center;
  }
  nav a { color: var(--nav-muted); text-decoration: none;
          padding: 0.3rem 0.5rem; border-radius: 3px;
          white-space: nowrap; }
  nav a.active { color: #fff; background: rgba(255, 255, 255, 0.15); }
  nav .grow { flex: 1; min-width: 0; }
  nav .brand {
    display: flex; align-items: center; gap: 0.45rem;
    color: var(--nav-fg); padding: 0.2rem 0.4rem 0.2rem 0.2rem;
    margin-right: 0.2rem;
  }
  nav .brand img { width: 28px; height: 28px; border-radius: 4px;
                    display: block; }
  nav .brand-label { font-size: 0.85rem; color: var(--nav-muted); }
  nav .nav-theme {
    background: transparent; color: var(--nav-fg); border: 1px solid var(--nav-muted);
    padding: 0.1rem 0.4rem; font-size: 1rem; border-radius: 4px; cursor: pointer;
  }
  nav .cost-pill {
    color: var(--nav-fg); background: rgba(255,255,255,0.10);
    border: 1px solid var(--nav-muted); border-radius: 999px;
    padding: 0.15rem 0.6rem; font-size: 0.85rem; text-decoration: none;
    margin-right: 0.5rem; white-space: nowrap;
  }
  nav .cost-pill.warn { background: rgba(255, 200, 0, 0.20); border-color: #d4a200; }
  nav .cost-pill.over { background: rgba(220, 50, 50, 0.25); border-color: #c25450; color: #fff; }
  main { max-width: 1100px; margin: 0 auto; padding: 1.2rem 1rem; }
  @media (max-width: 600px) {
    nav { gap: 0.35rem 0.6rem; padding: 0.4rem 0.6rem; }
    nav a { padding: 0.25rem 0.4rem; font-size: 0.92rem; }
    nav .brand-label { display: none; }
    nav .grow { display: none; }
    nav .cost-pill { font-size: 0.78rem; padding: 0.1rem 0.45rem; }
    main { padding: 0.8rem 0.7rem; }
  }
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
