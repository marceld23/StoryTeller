<script lang="ts">
  import '../app.css';
  import { page } from '$app/state';
  import { onMount } from 'svelte';

  type EndpointStatus = {
    role: string; ok: boolean; consecutive_failures: number;
    last_err_kind: string | null; last_err_http: number | null;
    last_err_detail: string; base_url: string; model: string | null;
    last_ok_ts: string | null; last_err_ts: string | null;
    paid_cloud: boolean;
  };
  type Health = {
    checked_at: string; any_problems: boolean;
    endpoints: Record<string, EndpointStatus>;
  };

  let theme = $state('dark');
  let { children } = $props();
  let cost = $state<{ today_usd: number; cap_daily_usd: number; pct: number; over_cap: boolean; approaching: boolean } | null>(null);
  let health = $state<Health | null>(null);

  async function refreshCost() {
    try {
      const r = await fetch('/api/cost/summary?days=1');
      if (r.ok) cost = await r.json();
    } catch { /* ignore */ }
  }

  async function refreshHealth() {
    try {
      const r = await fetch('/api/health/endpoints');
      if (r.ok) health = await r.json();
    } catch { /* ignore */ }
  }

  // Action-required = admin must fix (auth, bad_request). Everything else
  // (rate_limit, server, unreachable, timeout) is transient — show as a
  // warning, not an error.
  const ACTION_REQUIRED = new Set(['auth', 'bad_request']);

  function problemRoles(h: Health | null) {
    if (!h) return [];
    return Object.values(h.endpoints).filter(e => !e.ok);
  }
  function severity(rs: EndpointStatus[]): 'error' | 'warn' | null {
    if (rs.length === 0) return null;
    return rs.some(r => r.last_err_kind && ACTION_REQUIRED.has(r.last_err_kind))
      ? 'error' : 'warn';
  }

  let problems = $derived(problemRoles(health));
  let sev = $derived(severity(problems));

  onMount(() => {
    theme = document.documentElement.dataset.theme || 'dark';
    refreshCost();
    refreshHealth();
    const id = setInterval(() => { refreshCost(); refreshHealth(); }, 30000);
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
  <a href="/health" class:active={page.url.pathname.startsWith('/health')}
     class:health-warn={sev === 'warn'} class:health-err={sev === 'error'}>
    Status{#if sev}{' ⚠'}{/if}
  </a>
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

{#if sev && problems.length > 0}
  <div class="health-banner" class:err={sev === 'error'} class:warn={sev === 'warn'}>
    <strong>
      {sev === 'error' ? 'Endpoint-Problem — Aktion nötig:' : 'Endpoint nicht erreichbar:'}
    </strong>
    {#each problems as p (p.role)}
      <span class="role">
        {p.role}{#if p.model}{' ('}{p.model}{')'}{/if}:
        {p.last_err_kind}{#if p.last_err_http}{' '}{p.last_err_http}{/if}
        {#if p.consecutive_failures > 1}{` ×${p.consecutive_failures}`}{/if}
      </span>
    {/each}
    <a href="/health">Details →</a>
  </div>
{/if}

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
  nav a.health-warn { color: #ffd166; }
  nav a.health-err  { color: #ff7a7a; }
  .health-banner {
    padding: 0.6rem 1rem; font-size: 0.92rem;
    display: flex; flex-wrap: wrap; gap: 0.4rem 0.9rem; align-items: center;
  }
  .health-banner.warn { background: rgba(255, 200, 0, 0.18); color: #6b4d00;
                        border-bottom: 1px solid #d4a200; }
  .health-banner.err  { background: rgba(220, 50, 50, 0.22); color: #6b1111;
                        border-bottom: 1px solid #c25450; }
  .health-banner a { color: inherit; text-decoration: underline; }
  .health-banner .role { font-family: ui-monospace, Consolas, monospace; }
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
