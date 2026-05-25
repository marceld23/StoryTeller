<script lang="ts">
  import { goto } from '$app/navigation';
  import { onMount } from 'svelte';
  import { generatePlayerWorld } from '$lib/api';
  import { theme } from '$lib/theme';

  let prompt = $state('');
  let busy = $state(false);
  let error = $state('');
  let elapsed = $state(0);
  let tick: number | undefined = undefined;
  // Server-side cap (web.max_prompt_chars). Loaded once at mount so the
  // counter matches whatever the operator configured. Falls back to the
  // shipped default if /api/health is unreachable.
  let maxChars = $state(300000);

  const tooLong = $derived(prompt.length > maxChars);

  // Starter templates — three vibes the writer can dump into the textarea
  // and adapt. Picked from common asks: dark fantasy, light sci-fi,
  // detective. Keeps the cold-start moment from being a blank page.
  const TEMPLATES: { label: string; prompt: string }[] = [
    {
      label: '🌲 Fantasy',
      prompt:
        'Eine düstere Waldwelt, in der Bäume Erinnerungen speichern und nur '
        + 'wenige sie noch lesen können. Spielerrolle: ein junger Förster-Lehrling, '
        + 'der gerade gelernt hat, dass der Wald spricht. Zentrale Spannung: ein '
        + 'altes Versprechen, das gebrochen wurde — und der Wald beginnt sich daran '
        + 'zu erinnern. Tonalität: mythisch, mit subtilem Horror. Erste Szene: '
        + 'Morgennebel, eine Eiche flüstert deinen Namen.',
    },
    {
      label: '🚀 Sci-Fi',
      prompt:
        'Eine Generationen-Raumstation, deren ursprüngliches Ziel niemand mehr '
        + 'kennt. Spielerrolle: Wartungstechniker der Nachtschicht, der gerade '
        + 'einen Wartungsschacht gefunden hat, der auf KEINEM Plan steht. Zentrale '
        + 'Spannung: die Station verändert sich seit ein paar Wochen — nicht '
        + 'kaputt, sondern bewusst. Tonalität: melancholisch, ruhig, mit einem '
        + 'Hauch Unheimlichkeit. Erste Szene: du stehst vor einer Tür, die du '
        + 'gestern noch nicht gesehen hast.',
    },
    {
      label: '🕵 Krimi',
      prompt:
        'Eine kleine Hafenstadt in den 1950ern, in der seit drei Tagen Briefe '
        + 'verschwinden — nicht zugestellt, nicht zurückgeschickt, einfach weg. '
        + 'Spielerrolle: junger Polizist, frisch aus der Provinz versetzt. '
        + 'Zentrale Spannung: die verschwundenen Briefe haben ein Muster, das '
        + 'niemand außer dir sieht. Tonalität: nüchtern, regnerisch, mit langen '
        + 'Schweige-Momenten. Erste Szene: ein Anwohner steht vor deinem Schreibtisch '
        + 'und legt einen sehr alten Brief vor dich hin.',
    },
  ];
  function useTemplate(t: { prompt: string }) {
    if (busy) return;
    prompt = t.prompt;
  }

  onMount(async () => {
    try {
      const r = await fetch('/api/health');
      if (r.ok) {
        const j = await r.json();
        const lim = j?.limits?.max_prompt_chars;
        if (typeof lim === 'number' && lim > 0) maxChars = lim;
      }
    } catch { /* keep fallback */ }
  });

  async function submit() {
    const text = prompt.trim();
    if (!text || busy) return;
    if (tooLong) {
      error = `Prompt zu lang (${prompt.length.toLocaleString('de-DE')} / ${maxChars.toLocaleString('de-DE')} Zeichen).`;
      return;
    }
    busy = true; error = ''; elapsed = 0;
    tick = window.setInterval(() => (elapsed += 1), 1000);
    try {
      const w = await generatePlayerWorld(text);
      window.clearInterval(tick);
      // Pre-select the new world in the picker and go home.
      try { localStorage.setItem('st-last-world', w.id); } catch { /* ignore */ }
      await goto('/');
    } catch (e) {
      error = String(e);
    } finally {
      busy = false;
      if (tick !== undefined) window.clearInterval(tick);
    }
  }
</script>

<main>
  <header>
    <a class="brand" href="/" title="StoryTeller">
      <img src="/favicon.png" alt="" />
      <h1>Neue Welt erstellen</h1>
    </a>
    <div class="header-side">
      <a class="back" href="/">← zurück</a>
      <button class="icon-btn" onclick={() => theme.toggle()}
              title="Hell/Dunkel umschalten" aria-label="Theme">
        {theme.value === 'light' ? '🌙' : '☀️'}
      </button>
    </div>
  </header>

  <p class="hint">
    Beschreibe deine Wunsch-Welt: Setting, Stimmung, Spieler-Rolle, eine
    zentrale Spannung, der Ausgangsmoment der ersten Szene. Je dichter
    der Brief, desto näher trifft die Generierung. Mehrere Absätze sind
    OK — das große Modell macht daraus eine vollständige Welt
    (Orte, Personen, Items, Glossar, Blueprint, Zufallslisten). Limit
    <strong>{maxChars.toLocaleString('de-DE')}</strong> Zeichen.
    <br><strong>Dauert ein bis drei Minuten</strong> und kostet ein paar Cent
    (oder ist kostenlos, wenn das System auf lokale Modelle umgestellt ist).
  </p>

  {#if error}
    <p class="error">{error}</p>
  {/if}

  <div class="templates">
    <span class="tpl-label">Vorlage:</span>
    {#each TEMPLATES as t (t.label)}
      <button class="tpl" onclick={() => useTemplate(t)} disabled={busy}>
        {t.label}
      </button>
    {/each}
  </div>

  <textarea bind:value={prompt} rows="14"
            placeholder="z. B. 'Eine düstere Unterwasserstadt, in der Erinnerungen als Währung gehandelt werden. Spielerrolle: ein versinkender Bibliothekar. Tonalität: melancholisch mit subtilem Horror …'"
            disabled={busy}></textarea>

  <div class="meta">
    <span class:over={tooLong}>
      {prompt.length.toLocaleString('de-DE')} / {maxChars.toLocaleString('de-DE')} Zeichen
    </span>
  </div>

  <div class="actions">
    {#if busy}
      <button disabled>
        <span class="spinner-inline"></span>
        Generiere… ({elapsed}s)
      </button>
      <span class="hint small">
        Welt wird in mehreren Schritten zusammengebaut — bitte Tab
        nicht schließen.
      </span>
    {:else}
      <button onclick={submit} disabled={!prompt.trim() || tooLong}>
        Welt generieren
      </button>
    {/if}
  </div>
</main>

<style>
  main { max-width: 760px; margin: 0 auto; padding: 1rem;
         display: flex; flex-direction: column;
         min-height: 100vh; min-height: 100dvh;
         box-sizing: border-box; }
  header { display: flex; justify-content: space-between;
           align-items: center; border-bottom: 1px solid var(--border);
           padding-bottom: 0.5rem; gap: 0.6rem; }
  header h1 { margin: 0; font-size: 1.4rem; color: #6fc3df; }
  .brand { display: flex; align-items: center; gap: 0.5rem;
           color: inherit; text-decoration: none; }
  .brand img { width: 32px; height: 32px; border-radius: 4px; display: block; }
  .back { color: var(--muted, #888); text-decoration: none; font-size: 0.95rem; }
  .header-side { display: flex; gap: 0.5rem; align-items: center; }
  .icon-btn {
    background: transparent; color: var(--fg); border: 1px solid var(--border);
    padding: 0.25rem 0.55rem; border-radius: 4px; cursor: pointer;
    font-size: 0.95rem; line-height: 1;
  }
  .templates {
    display: flex; gap: 0.4rem; flex-wrap: wrap; align-items: center;
    margin: 0.4rem 0;
  }
  .tpl-label { color: var(--muted); font-size: 0.85rem; }
  .tpl {
    background: var(--surface); color: var(--fg);
    border: 1px solid var(--border); border-radius: 999px;
    padding: 0.25rem 0.7rem; cursor: pointer; font-size: 0.85rem;
  }
  .tpl:hover { border-color: #6fc3df; color: #6fc3df; }
  .tpl:disabled { opacity: 0.4; cursor: not-allowed; }
  @media (max-width: 600px) {
    main { padding: 0.7rem; }
    header h1 { font-size: 1.05rem; }
    .brand img { width: 28px; height: 28px; }
    textarea { min-height: 18em; font-size: 1rem; }
    .actions { flex-direction: column; align-items: stretch; }
    .actions button { width: 100%; }
  }
  .hint { color: var(--muted, #888); font-size: 0.9rem; }
  .hint.small { font-size: 0.85rem; }
  textarea {
    width: 100%; box-sizing: border-box; padding: 0.6rem; margin: 0.6rem 0;
    background: var(--input-bg); color: var(--fg);
    border: 1px solid var(--border); border-radius: 4px;
    font-family: inherit; font-size: 1rem; resize: vertical;
    min-height: 14em; line-height: 1.5;
  }
  .actions { display: flex; gap: 0.7rem; align-items: center;
             margin-top: 0.6rem; }
  button {
    padding: 0.5rem 1.2rem; background: #6fc3df; color: #10131a;
    border: none; border-radius: 3px; cursor: pointer; font-weight: 600;
  }
  button:disabled { background: var(--border); color: var(--muted); cursor: not-allowed; }
  .error { color: #e07a7a; }
  .meta { text-align: right; color: var(--muted); font-size: 0.85rem;
           margin: -0.4rem 0 0.4rem; }
  .meta .over { color: #c25450; font-weight: 600; }
  .spinner-inline {
    display: inline-block; width: 12px; height: 12px;
    border: 2px solid rgba(255,255,255,0.18);
    border-top-color: #fff; border-radius: 50%;
    animation: spin 0.9s linear infinite; vertical-align: middle;
    margin-right: 0.35rem;
  }
  @keyframes spin { to { transform: rotate(360deg); } }
</style>
