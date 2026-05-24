<script lang="ts">
  import { onMount } from 'svelte';
  import { listSaves, resetSave, type SaveGame } from '$lib/api';

  let items: SaveGame[] = $state([]);
  let error: string = $state('');
  let loading: boolean = $state(true);
  let busy: string = $state(''); // thread_id currently being reset

  // KnownFacts modal state
  type KnownFact = { kind: string; name: string; note?: string };
  let factsOpen = $state(false);
  let factsThread = $state<SaveGame | null>(null);
  let facts: KnownFact[] = $state([]);
  let charState: Record<string, string> = $state({});
  let factsLoading = $state(false);
  let factsError = $state('');
  let promoting = $state('');     // index being promoted
  let promoteStatus = $state('');

  async function load() {
    loading = true;
    error = '';
    try {
      items = await listSaves();
    } catch (e) {
      error = String(e);
    } finally {
      loading = false;
    }
  }

  async function reset(s: SaveGame) {
    const label = s.world_name || s.thread_id;
    if (
      !confirm(
        `Spielstand „${label}" (${s.checkpoints} Schritte) wirklich zurücksetzen?\n` +
          `Der gesamte Fortschritt geht verloren und die Welt startet von vorn.`
      )
    )
      return;
    busy = s.thread_id;
    error = '';
    try {
      await resetSave(s.thread_id);
      await load();
    } catch (e) {
      error = String(e);
    } finally {
      busy = '';
    }
  }

  async function openFacts(s: SaveGame) {
    factsOpen = true;
    factsThread = s;
    facts = [];
    charState = {};
    factsError = '';
    factsLoading = true;
    promoteStatus = '';
    try {
      const r = await fetch(`/api/saves/${encodeURIComponent(s.thread_id)}/promotable`);
      const j = await r.json();
      facts = j.known_facts ?? [];
      charState = j.char_state ?? {};
    } catch (e) {
      factsError = String(e);
    } finally {
      factsLoading = false;
    }
  }

  function closeFacts() {
    factsOpen = false;
    factsThread = null;
    facts = [];
    charState = {};
  }

  // Kind heuristic from the known-fact `kind` string used at remember_fact
  // time. The narrator picks free-form labels there ("ort", "person",
  // "gegenstand", …) — map to canonical buckets.
  function canonicalKind(raw: string): 'person' | 'place' | 'item' | 'fact' {
    const k = (raw || '').toLowerCase();
    if (k.includes('person') || k.includes('npc') || k.includes('figur')) return 'person';
    if (k.includes('ort') || k.includes('place') || k.includes('locat')) return 'place';
    if (k.includes('item') || k.includes('gegenstand') || k.includes('artefakt')) return 'item';
    return 'fact';
  }

  async function promoteFact(idx: number, fact: KnownFact) {
    if (!factsThread || !factsThread.world_id) {
      factsError = 'Kein world_id für diesen Spielstand — kann nicht promovieren.';
      return;
    }
    const kind = canonicalKind(fact.kind);
    if (!confirm(`„${fact.name}" als ${kind} in die Welt aufnehmen?`)) return;
    promoting = String(idx);
    try {
      const r = await fetch(
        `/api/saves/${encodeURIComponent(factsThread.thread_id)}/promote_known_fact`,
        { method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            world_id: factsThread.world_id,
            kind, name: fact.name,
            description: fact.note || '',
            tags: [] }) });
      const j = await r.json();
      if (!j.ok) { factsError = JSON.stringify(j); return; }
      promoteStatus = `„${fact.name}" in „${factsThread.world_name}" aufgenommen (${kind}).`;
    } catch (e) {
      factsError = String(e);
    } finally {
      promoting = '';
    }
  }

  onMount(load);
</script>

<h1>Spielstände</h1>
<p class="hint">
  Jede gespeicherte Sitzung kann zurückgesetzt werden — danach beginnt die Welt
  wieder mit der Eröffnung. <strong>Zurücksetzen kann nicht rückgängig gemacht
  werden.</strong>
</p>
{#if error}<p class="error">{error}</p>{/if}
{#if loading}
  <p>Lade…</p>
{:else if items.length === 0}
  <p>Keine gespeicherten Spielstände.</p>
{:else}
  <table>
    <thead>
      <tr><th>Welt</th><th>Quelle</th><th>Schritte</th><th>Zuletzt</th><th></th></tr>
    </thead>
    <tbody>
      {#each items as s (s.thread_id)}
        <tr>
          <td>
            <strong>{s.world_name}</strong>
            <div class="tid">{s.thread_id}</div>
          </td>
          <td><span class="src">{s.source}</span></td>
          <td>{s.checkpoints}</td>
          <td class="last">{s.last_narration || '—'}</td>
          <td class="actions">
            <button onclick={() => openFacts(s)}>Bekannte Fakten</button>
            <button
              class="danger"
              disabled={busy === s.thread_id}
              onclick={() => reset(s)}
            >
              {busy === s.thread_id ? 'Setze zurück…' : 'Zurücksetzen'}
            </button>
          </td>
        </tr>
      {/each}
    </tbody>
  </table>
{/if}

{#if factsOpen && factsThread}
  <div class="modal-bg" onclick={closeFacts} role="presentation"></div>
  <div class="modal" role="dialog" aria-modal="true">
    <header>
      <h2>Bekannte Fakten — {factsThread.world_name}</h2>
      <button class="close" onclick={closeFacts} aria-label="Schließen">×</button>
    </header>
    <p class="hint">
      Per <code>remember_fact</code> während dieser Sitzung gespeicherte
      Spieler-Fakten. „In Welt aufnehmen" trägt einen Eintrag in die kanonische
      Welt ein und macht ihn für alle künftigen Spielstände dieser Welt
      verfügbar (RAG wird sofort aktualisiert).
    </p>
    {#if factsError}<p class="error">{factsError}</p>{/if}
    {#if promoteStatus}<p class="ok">{promoteStatus}</p>{/if}
    {#if factsLoading}
      <p>Lade…</p>
    {:else if facts.length === 0}
      <p class="muted">Keine remember_fact-Einträge in diesem Spielstand.</p>
    {:else}
      <table class="facts">
        <thead><tr><th>Art</th><th>Name</th><th>Notiz</th><th></th></tr></thead>
        <tbody>
          {#each facts as f, i (`${f.kind}-${f.name}-${i}`)}
            <tr>
              <td><code>{f.kind}</code></td>
              <td><strong>{f.name}</strong></td>
              <td class="note">{f.note || '—'}</td>
              <td>
                <button onclick={() => promoteFact(i, f)} disabled={promoting === String(i) || !factsThread.world_id}>
                  {promoting === String(i) ? 'Übernehme…' : 'In Welt aufnehmen'}
                </button>
              </td>
            </tr>
          {/each}
        </tbody>
      </table>
    {/if}
    {#if Object.keys(charState).length > 0}
      <h3>Charakter-Zustand</h3>
      <p class="hint small">Spielsitzungs-Zustände einzelner Personen — nicht direkt promovierbar, nur zur Info.</p>
      <table class="facts">
        <thead><tr><th>Name</th><th>Status</th></tr></thead>
        <tbody>
          {#each Object.entries(charState) as [name, state] (name)}
            <tr><td><strong>{name}</strong></td><td>{state}</td></tr>
          {/each}
        </tbody>
      </table>
    {/if}
  </div>
{/if}

<style>
  table { width: 100%; border-collapse: collapse; background: var(--surface); }
  th, td { padding: 0.5rem 0.7rem; text-align: left; border-bottom: 1px solid var(--border); vertical-align: top; }
  th { background: var(--surface-2); }
  .hint { color: var(--muted, #888); max-width: 60ch; }
  .hint.small { font-size: 0.85rem; }
  .error { color: #c25450; }
  .ok { color: #4a9e4f; }
  .tid { font-size: 0.78rem; color: var(--muted, #888); font-family: monospace; }
  .src { font-size: 0.8rem; padding: 0.1rem 0.4rem; border-radius: 3px; background: var(--surface-2); }
  .last { max-width: 40ch; color: var(--muted, #888); font-size: 0.85rem; }
  td.actions { display: flex; gap: 0.4rem; flex-wrap: wrap; justify-content: flex-end; }
  button.danger {
    background: #c25450; color: #fff; border: none; padding: 0.35rem 0.7rem;
    border-radius: 4px; cursor: pointer; white-space: nowrap;
  }
  button.danger:disabled { opacity: 0.6; cursor: default; }
  .modal-bg {
    position: fixed; inset: 0; background: rgba(0,0,0,0.55); z-index: 10;
  }
  .modal {
    position: fixed; top: 5vh; left: 50%; transform: translateX(-50%);
    width: min(900px, 92vw); max-height: 90vh; overflow: auto;
    background: var(--surface); border: 1px solid var(--border);
    border-radius: 6px; padding: 1.2rem 1.4rem; z-index: 11;
  }
  .modal header { display: flex; align-items: center; gap: 1rem; margin-bottom: 0.4rem; }
  .modal header h2 { margin: 0; flex: 1; font-size: 1.2rem; }
  .modal .close { background: transparent; color: inherit; font-size: 1.4rem;
                  border: none; cursor: pointer; padding: 0 0.5rem; }
  .modal h3 { margin: 1.2rem 0 0.4rem; font-size: 1rem; }
  .facts code { font-size: 0.85rem; color: var(--muted); }
  .facts .note { color: var(--muted); max-width: 40ch; }
  .muted { color: var(--muted, #888); }
</style>
