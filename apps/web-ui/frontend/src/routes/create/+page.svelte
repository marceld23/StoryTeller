<script lang="ts">
  import { goto } from '$app/navigation';
  import { generatePlayerWorld } from '$lib/api';

  let prompt = $state('');
  let busy = $state(false);
  let error = $state('');
  let elapsed = $state(0);
  let tick: number | undefined = undefined;

  async function submit() {
    const text = prompt.trim();
    if (!text || busy) return;
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
    <h1>Neue Welt erstellen</h1>
    <a href="/">← zurück</a>
  </header>

  <p class="hint">
    Beschreibe deine Wunsch-Welt: Setting, Stimmung, Spieler-Rolle, eine
    zentrale Spannung, der Ausgangsmoment der ersten Szene. Je dichter
    der Brief, desto näher trifft die Generierung. Mehrere Absätze sind
    OK — das große Modell macht daraus eine vollständige Welt
    (Orte, Personen, Items, Glossar, Blueprint, Zufallslisten).
    <br><strong>Dauert ein bis drei Minuten</strong> und kostet ein paar Cent
    (oder ist kostenlos, wenn das System auf lokale Modelle umgestellt ist).
  </p>

  {#if error}
    <p class="error">{error}</p>
  {/if}

  <textarea bind:value={prompt} rows="14"
            placeholder="z. B. 'Eine düstere Unterwasserstadt, in der Erinnerungen als Währung gehandelt werden. Spielerrolle: ein versinkender Bibliothekar. Tonalität: melancholisch mit subtilem Horror …'"
            disabled={busy}></textarea>

  <div class="actions">
    {#if busy}
      <button disabled>Generiere… ({elapsed}s)</button>
      <span class="hint small">
        Welt wird in mehreren Schritten zusammengebaut — bitte Tab
        nicht schließen.
      </span>
    {:else}
      <button onclick={submit} disabled={!prompt.trim()}>
        Welt generieren
      </button>
    {/if}
  </div>
</main>

<style>
  main { max-width: 760px; margin: 0 auto; padding: 1rem;
         display: flex; flex-direction: column; min-height: 100vh; }
  header { display: flex; justify-content: space-between; align-items: baseline;
           border-bottom: 1px solid var(--border); padding-bottom: 0.5rem; }
  header h1 { margin: 0; font-size: 1.4rem; color: #6fc3df; }
  header a { color: var(--muted, #888); text-decoration: none; }
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
</style>
