<script lang="ts">
  import { onMount } from 'svelte';
  import {
    copyWorld,
    deleteWorld,
    listWorlds,
    renameWorld,
    type WorldSummary
  } from '$lib/api';

  let worlds: WorldSummary[] = $state([]);
  let error: string = $state('');
  let status: string = $state('');
  let loading: boolean = $state(true);

  // Inline form state per row: which world is being copied / renamed and
  // the new-id / new-name values. Open form for at most ONE world at a
  // time so the table layout stays predictable.
  type FormMode = 'copy' | 'rename';
  let openFor: string = $state('');     // world id whose form is open
  let openMode: FormMode = $state('copy');
  let newId: string = $state('');
  let newName: string = $state('');
  let busy: boolean = $state(false);

  function slugify(text: string): string {
    let s = (text || '').toLowerCase().trim();
    const umlauts: Record<string, string> = { ä: 'ae', ö: 'oe', ü: 'ue', ß: 'ss' };
    s = s.replace(/[äöüß]/g, (c) => umlauts[c] ?? c);
    s = s.replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '');
    if (s && !/^[a-z]/.test(s)) s = 'w_' + s;
    return s || 'welt';
  }

  function isValidId(id: string): boolean {
    return /^[a-z][a-z0-9_]*$/.test(id);
  }

  async function reload() {
    loading = true;
    error = '';
    try {
      worlds = await listWorlds();
    } catch (e) {
      error = String(e);
    } finally {
      loading = false;
    }
  }

  function startForm(mode: FormMode, w: WorldSummary) {
    openMode = mode;
    openFor = w.id;
    // Default new_name = current name (+ Kopie for copy)
    if (mode === 'copy') {
      newName = w.name ? `${w.name} (Kopie)` : '';
      newId = slugify(newName) || `${w.id}_kopie`;
    } else {
      newName = w.name;
      newId = w.id;
    }
    status = '';
    error = '';
  }

  function closeForm() {
    openFor = '';
    newId = '';
    newName = '';
  }

  // Auto-derive id from name as the user types — but only when the
  // user hasn't manually edited the id field (heuristic: id still
  // matches the slug of the previous name value). Keeps the common
  // case ergonomic without locking out manual edits.
  let lastDerivedId: string = $state('');
  function onNameInput(value: string) {
    newName = value;
    if (newId === '' || newId === lastDerivedId) {
      newId = slugify(value);
      lastDerivedId = newId;
    }
  }

  async function submitForm() {
    error = '';
    status = '';
    if (!isValidId(newId)) {
      error = `Ungültige ID: "${newId}" (Kleinbuchstaben, beginnt mit Buchstabe, nur [a-z0-9_]).`;
      return;
    }
    if (openMode === 'rename' && newId === openFor && newName === worlds.find((w) => w.id === openFor)?.name) {
      error = 'Nichts geändert.';
      return;
    }
    busy = true;
    try {
      if (openMode === 'copy') {
        const r = await copyWorld(openFor, newId, newName);
        status = `Kopie als '${r.world_id}' angelegt.`;
      } else {
        const r = await renameWorld(openFor, newId, newName);
        status = `Umbenannt zu '${r.world_id}'.`;
      }
      closeForm();
      await reload();
    } catch (e) {
      error = String(e);
    } finally {
      busy = false;
    }
  }

  async function onDelete(w: WorldSummary) {
    if (!confirm(
      `Welt '${w.id}' (${w.name}) wirklich löschen?\n\n` +
        `Welt-Daten, RAG-Index und Pi-Spielstände gehen verloren.`
    )) return;
    error = '';
    try {
      await deleteWorld(w.id);
      status = `'${w.id}' gelöscht.`;
      await reload();
    } catch (e) {
      error = String(e);
    }
  }

  onMount(reload);
</script>

<h1>Welten</h1>
{#if error}<p class="error">{error}</p>{/if}
{#if status}<p class="ok">{status}</p>{/if}

{#if loading}
  <p>Lade…</p>
{:else if worlds.length === 0}
  <p>Keine Welten gefunden.</p>
{:else}
  <table>
    <thead><tr><th>ID</th><th>Name</th><th>Genre</th><th>Spielerrolle</th><th>Aktionen</th></tr></thead>
    <tbody>
      {#each worlds as w (w.id)}
        <tr>
          <td><a href={`/worlds/${w.id}`}><code>{w.id}</code></a></td>
          <td>{w.name}</td>
          <td>{w.genre}</td>
          <td>{w.player_role}</td>
          <td class="actions">
            <button onclick={() => startForm('copy', w)}>Kopieren</button>
            <button onclick={() => startForm('rename', w)}>Umbenennen</button>
            <button class="danger" onclick={() => onDelete(w)}>Löschen</button>
          </td>
        </tr>
        {#if openFor === w.id}
          <tr class="form-row">
            <td colspan="5">
              <form onsubmit={(e) => { e.preventDefault(); submitForm(); }}>
                <strong>{openMode === 'copy' ? 'Welt kopieren' : 'Welt umbenennen'}</strong>
                — Quelle: <code>{w.id}</code>
                <div class="form-grid">
                  <label>
                    <span>Neuer Name</span>
                    <input
                      value={newName}
                      oninput={(e) => onNameInput((e.target as HTMLInputElement).value)}
                      disabled={busy}
                      placeholder="z. B. Sternenfahrt II"
                      autofocus
                    />
                  </label>
                  <label>
                    <span>Neue ID</span>
                    <input
                      bind:value={newId}
                      disabled={busy}
                      placeholder="z. B. sternenfahrt_ii"
                      pattern="^[a-z][a-z0-9_]*$"
                    />
                  </label>
                </div>
                <p class="hint">
                  ID = Kleinbuchstaben, beginnt mit Buchstabe, nur
                  <code>a-z 0-9 _</code>. Wird automatisch aus dem
                  Namen abgeleitet — kannst du auch direkt
                  überschreiben.
                  {#if openMode === 'copy'}
                    Die Kopie startet ohne Spielstände (Saves bleiben
                    bei <code>{w.id}</code>).
                  {:else}
                    Spielstände werden mit-umbenannt
                    (<code>pi-{w.id}</code> →
                    <code>pi-{newId || '?'}</code>).
                  {/if}
                </p>
                <div class="form-actions">
                  <button type="submit" disabled={busy || !newId || !newName}>
                    {busy ? '…' : (openMode === 'copy' ? 'Kopie anlegen' : 'Umbenennen')}
                  </button>
                  <button type="button" class="ghost" onclick={closeForm} disabled={busy}>
                    Abbrechen
                  </button>
                </div>
              </form>
            </td>
          </tr>
        {/if}
      {/each}
    </tbody>
  </table>
{/if}

<style>
  table { width: 100%; border-collapse: collapse; background: var(--surface); }
  th, td { padding: 0.5rem 0.7rem; text-align: left; border-bottom: 1px solid var(--border); }
  th { background: var(--surface-2); font-weight: 600; }
  td.actions { white-space: nowrap; }
  td.actions button { margin-right: 0.3rem; padding: 0.2rem 0.6rem; font-size: 0.85rem; }
  tr.form-row td { background: var(--surface-2); padding: 0.9rem 1rem; }
  .form-grid { display: grid; grid-template-columns: 1fr 1fr;
               gap: 0.5rem; margin: 0.6rem 0 0.2rem; }
  @media (max-width: 600px) { .form-grid { grid-template-columns: 1fr; } }
  .form-grid label { display: block; }
  .form-grid label span { display: block; font-size: 0.75rem;
                          color: var(--muted); margin-bottom: 0.15rem; }
  .form-grid input { width: 100%; box-sizing: border-box;
                      padding: 0.3rem 0.5rem; font-family: inherit; }
  .form-actions { margin-top: 0.5rem; display: flex; gap: 0.4rem; }
  .form-actions button.ghost { background: transparent;
                                border: 1px solid var(--border);
                                color: var(--fg); }
  .hint { color: var(--muted); font-size: 0.8rem; margin: 0.4rem 0 0; }
  .error { color: #c25450; }
  .ok { color: #4a9e4f; }
  code { background: var(--code-bg); padding: 0 4px; border-radius: 2px; }
  a { color: var(--link); text-decoration: none; }
  a:hover { text-decoration: underline; }
</style>
