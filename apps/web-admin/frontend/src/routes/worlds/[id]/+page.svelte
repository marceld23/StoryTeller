<script lang="ts">
  import { page } from '$app/state';
  import { goto } from '$app/navigation';
  import { onMount } from 'svelte';
  import { getWorld, listWaitSounds, putWorld, reindexWorld, waitForJob, type Job } from '$lib/api';
  import ContentList from '$lib/ContentList.svelte';
  import { CONTENT_KINDS } from '$lib/worldFields';

  // The full world object (structured editing binds into this).
  let world: any = $state(null);
  let error = $state('');
  let status = $state('');
  let loading = $state(true);
  let showRaw = $state(false);
  let raw = $state('');
  let reindexJob: Job | null = $state(null);
  let reindexing = $state(false);
  // Files available as wait-sound (filenames in data/wait_sounds/).
  let waitSounds: string[] = $state([]);

  // ----- Tab state (URL-persistent: ?tab=orte) -----
  type TabId = 'grundlagen' | 'ton' | 'orte' | 'personen' | 'items' | 'lore' | 'zufall' | 'notizen';
  const TAB_IDS: TabId[] = ['grundlagen', 'ton', 'orte', 'personen', 'items', 'lore', 'zufall', 'notizen'];
  let tab: TabId = $state('grundlagen');

  // User notes (Phase A/B): notes the player added via "Vermerken: …"
  // voice command. The admin reviews them here and promotes the
  // valuable ones to the canonical world (places / persons / items /
  // fragments). The list is loaded lazily when the Notizen tab opens.
  type Note = {
    id: string; ts: string; world_id: string; locale: string;
    kind: string; name: string; description: string; tags: string[];
    raw_text: string; thread_id: string | null; promoted: boolean;
  };
  let notes: Note[] = $state([]);
  let notesLoading = $state(false);
  let notesError = $state('');
  let notesPromoted = $state(false); // toggle: show promoted history

  async function loadNotes() {
    notesLoading = true;
    notesError = '';
    try {
      const url = `/api/worlds/${page.params.id}/user_notes?promoted=${notesPromoted}`;
      const r = await fetch(url);
      const j = await r.json();
      notes = j.notes ?? [];
    } catch (e) {
      notesError = String(e);
    } finally {
      notesLoading = false;
    }
  }

  async function promoteNote(n: Note) {
    if (!confirm(`"${n.name}" als ${n.kind} in die Welt übernehmen?`)) return;
    notesError = '';
    try {
      const r = await fetch(
        `/api/worlds/${page.params.id}/user_notes/${n.id}/promote`,
        { method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ kind: n.kind, name: n.name,
                                  description: n.description,
                                  tags: n.tags }) });
      const j = await r.json();
      if (!j.ok) { notesError = JSON.stringify(j); return; }
      status = `Notiz "${n.name}" in die Welt übernommen (${n.kind}).`;
      // Refresh world (new entry now in places/persons/...).
      world = normalize(await getWorld(page.params.id));
      await loadNotes();
    } catch (e) { notesError = String(e); }
  }

  async function discardNote(n: Note) {
    if (!confirm(`Notiz "${n.name}" verwerfen?`)) return;
    notesError = '';
    try {
      const r = await fetch(
        `/api/worlds/${page.params.id}/user_notes/${n.id}`,
        { method: 'DELETE' });
      const j = await r.json();
      if (!j.ok) { notesError = JSON.stringify(j); return; }
      await loadNotes();
    } catch (e) { notesError = String(e); }
  }

  $effect(() => {
    if (tab === 'notizen' && !notesLoading) loadNotes();
  });

  onMount(() => {
    const q = new URLSearchParams(window.location.search);
    const t = q.get('tab');
    if (t && (TAB_IDS as string[]).includes(t)) tab = t as TabId;
  });

  function setTab(t: TabId) {
    tab = t;
    const url = new URL(window.location.href);
    url.searchParams.set('tab', t);
    goto(url.pathname + url.search, { replaceState: true, noScroll: true });
  }

  // helpers to find a content-list spec by prop name (CONTENT_KINDS order is fixed)
  function spec(prop: string) {
    return CONTENT_KINDS.find((k) => k.prop === prop)!;
  }

  $effect(() => {
    const id = page.params.id;
    if (!id) return;
    loading = true;
    getWorld(id)
      .then((data) => {
        world = normalize(data);
        loading = false;
      })
      .catch((e) => {
        error = String(e);
        loading = false;
      });
    // independent: pull the wait-sound directory listing once
    listWaitSounds().then((s) => (waitSounds = s)).catch(() => {});
  });

  // make sure optional containers exist so binding doesn't explode
  function normalize(w: any): any {
    w.story_patterns ??= [];
    w.places ??= [];
    w.persons ??= [];
    w.items ??= [];
    w.glossary ??= [];
    w.history ??= [];
    w.fragments ??= [];
    w.random_tables ??= [];
    w.tone ??= { darkness: 2, humor: 1, romance: 1, action: 3, horror: 1, pacing: 'medium', notes: '' };
    w.blueprint ??= { premise: '', beats: [], escalation_rule: '' };
    w.blueprint.beats ??= [];
    return w;
  }

  async function save() {
    error = '';
    status = '';
    try {
      await putWorld(page.params.id, world);
      status = 'gespeichert.';
    } catch (e) {
      error = String(e);
    }
  }

  function syncRaw() {
    raw = JSON.stringify(world, null, 2);
    showRaw = true;
  }
  function applyRaw() {
    try {
      world = normalize(JSON.parse(raw));
      showRaw = false;
      status = 'Roh-JSON übernommen (noch nicht gespeichert).';
    } catch (e) {
      error = `JSON: ${e}`;
    }
  }

  async function onReindex() {
    error = '';
    status = '';
    reindexing = true;
    reindexJob = null;
    try {
      const { job_id } = await reindexWorld(page.params.id);
      const finished = await waitForJob(job_id, (j) => (reindexJob = j));
      if (finished.status === 'error') error = finished.error ?? 'Reindex fehlgeschlagen';
      else status = finished.detail || 'Reindex fertig.';
    } catch (e) {
      error = String(e);
    } finally {
      reindexing = false;
    }
  }

  // beats helpers
  function addBeat() {
    world.blueprint.beats = [...world.blueprint.beats, { name: '', goal: '', tension: 5 }];
  }
  function rmBeat(i: number) {
    world.blueprint.beats = world.blueprint.beats.filter((_: any, idx: number) => idx !== i);
  }

  // random table helpers
  function addTable() {
    world.random_tables = [...world.random_tables, { name: '', description: '', entries: [] }];
  }
  function rmTable(i: number) {
    world.random_tables = world.random_tables.filter((_: any, idx: number) => idx !== i);
  }
  function addEntry(t: any) {
    t.entries = [...(t.entries ?? []), { weight: 1, text: '' }];
  }
  function rmEntry(t: any, i: number) {
    t.entries = t.entries.filter((_: any, idx: number) => idx !== i);
  }

  // story_patterns as comma string
  function patternsStr(): string {
    return (world.story_patterns ?? []).join(', ');
  }
  function setPatterns(s: string) {
    world.story_patterns = s.split(',').map((x) => x.trim()).filter(Boolean);
  }
</script>

<a href="/">← zurück</a>
<h1>Welt: <code>{page.params.id}</code></h1>

{#if error}<p class="error">{error}</p>{/if}
{#if status}<p class="ok">{status}</p>{/if}

{#if loading}
  <p>Lade…</p>
{:else if world}
  <div class="toolbar">
    <button onclick={save}>Speichern</button>
    <button onclick={onReindex} disabled={reindexing}>
      {reindexing ? 'Reindexiere…' : 'RAG neu indexieren'}
    </button>
    <button onclick={showRaw ? () => (showRaw = false) : syncRaw}>
      {showRaw ? 'Editor' : 'Roh-JSON'}
    </button>
  </div>
  {#if reindexJob}<p class="hint">Reindex: {reindexJob.status} · {reindexJob.detail}</p>{/if}

  {#if showRaw}
    <textarea class="raw" bind:value={raw} rows="40"></textarea>
    <div class="toolbar"><button onclick={applyRaw}>JSON übernehmen</button></div>
  {:else}
    <!-- Tab bar (horizontal pill nav). -->
    <nav class="tabs" aria-label="Welt-Editor Sektionen">
      <button class:active={tab === 'grundlagen'} onclick={() => setTab('grundlagen')}>Grundlagen</button>
      <button class:active={tab === 'ton'} onclick={() => setTab('ton')}>Ton &amp; Bogen
        <span class="count">{(world.blueprint.beats ?? []).length}</span></button>
      <button class:active={tab === 'orte'} onclick={() => setTab('orte')}>Orte
        <span class="count">{world.places.length}</span></button>
      <button class:active={tab === 'personen'} onclick={() => setTab('personen')}>Personen
        <span class="count">{world.persons.length}</span></button>
      <button class:active={tab === 'items'} onclick={() => setTab('items')}>Gegenstände
        <span class="count">{world.items.length}</span></button>
      <button class:active={tab === 'lore'} onclick={() => setTab('lore')}>Lore
        <span class="count">{world.glossary.length + world.history.length + world.fragments.length}</span></button>
      <button class:active={tab === 'zufall'} onclick={() => setTab('zufall')}>Zufallslisten
        <span class="count">{world.random_tables.length}</span></button>
      <button class:active={tab === 'notizen'} onclick={() => setTab('notizen')}>Notizen
        {#if notes.filter((n) => !n.promoted).length > 0}
          <span class="count">{notes.filter((n) => !n.promoted).length}</span>
        {/if}
      </button>
    </nav>

    {#if tab === 'grundlagen'}
      <section>
        <h3>Kern</h3>
        <div class="grid">
          <label><span>Name</span><input bind:value={world.name} /></label>
          <label><span>Genre</span><input bind:value={world.genre} /></label>
          <label><span>Spielerrolle</span><input bind:value={world.player_role} /></label>
          <label><span>Komplexität</span>
            <select bind:value={world.complexity}>
              <option value="simple">simple</option>
              <option value="standard">standard</option>
              <option value="rich">rich</option>
            </select>
          </label>
          <label><span>Zielgruppe</span><input bind:value={world.audience} /></label>
          <label>
            <span>Wartesound</span>
            <select bind:value={world.wait_sound}>
              <option value="">— kein —</option>
              {#each waitSounds as f (f)}
                <option value={f}>{f}</option>
              {/each}
              {#if world.wait_sound && !waitSounds.includes(world.wait_sound)}
                <option value={world.wait_sound}>{world.wait_sound} (fehlt)</option>
              {/if}
            </select>
          </label>
        </div>
        <label><span>Beschreibung (bis zu mehrere Absätze)</span>
          <textarea class="big" bind:value={world.description} rows="18"></textarea>
        </label>
        <label><span>Ausgangssituation</span>
          <textarea class="big" bind:value={world.starting_situation} rows="6"></textarea>
        </label>
        <label><span>Erzählstil</span>
          <textarea bind:value={world.narration_style} rows="3"></textarea>
        </label>
        <label><span>Stil-Anker (voice_sample) — 1–2 Beispielsätze im Welt-Ton</span>
          <textarea bind:value={world.voice_sample} rows="4"></textarea>
        </label>
        <div class="grid">
          <label><span>Stimmung</span><textarea bind:value={world.mood} rows="2"></textarea></label>
          <label><span>Ambiente</span><textarea bind:value={world.ambience} rows="2"></textarea></label>
        </div>
        <label><span>Physik/Magie</span>
          <textarea bind:value={world.magic_physics} rows="5"></textarea>
        </label>
        <label><span>Story-Patterns (komma)</span>
          <input value={patternsStr()} oninput={(e) => setPatterns((e.target as HTMLInputElement).value)} />
        </label>
      </section>
    {/if}

    {#if tab === 'ton'}
      <section>
        <h3>Ton</h3>
        <div class="grid">
          {#each ['darkness', 'humor', 'romance', 'action', 'horror'] as k (k)}
            <label><span>{k}</span>
              <input type="number" min="0" max="5" bind:value={world.tone[k]} />
            </label>
          {/each}
          <label><span>pacing</span>
            <select bind:value={world.tone.pacing}>
              <option value="slow">slow</option>
              <option value="medium">medium</option>
              <option value="fast">fast</option>
            </select>
          </label>
        </div>
        <label><span>Notizen</span><input bind:value={world.tone.notes} /></label>
      </section>

      <section>
        <h3>Spannungsbogen (Blueprint)</h3>
        <label><span>Prämisse</span>
          <textarea bind:value={world.blueprint.premise} rows="4"></textarea>
        </label>
        <label><span>Eskalationsregel</span>
          <textarea bind:value={world.blueprint.escalation_rule} rows="3"></textarea>
        </label>
        <h4>Beats <button onclick={addBeat}>+ Beat</button></h4>
        {#each world.blueprint.beats as b, i (i)}
          <div class="row">
            <input placeholder="Name" bind:value={b.name} />
            <input placeholder="Ziel" bind:value={b.goal} />
            <input type="number" min="0" max="10" bind:value={b.tension} title="Spannung 0-10" />
            <button class="danger" onclick={() => rmBeat(i)}>×</button>
          </div>
        {/each}
      </section>
    {/if}

    {#if tab === 'orte'}
      <ContentList spec={spec('places')} bind:items={world.places} worldId={page.params.id} />
    {/if}

    {#if tab === 'personen'}
      <ContentList spec={spec('persons')} bind:items={world.persons} worldId={page.params.id} />
    {/if}

    {#if tab === 'items'}
      <ContentList spec={spec('items')} bind:items={world.items} worldId={page.params.id} />
    {/if}

    {#if tab === 'lore'}
      <ContentList spec={spec('glossary')} bind:items={world.glossary} worldId={page.params.id} />
      <ContentList spec={spec('history')} bind:items={world.history} worldId={page.params.id} />
      <ContentList spec={spec('fragments')} bind:items={world.fragments} worldId={page.params.id} />
    {/if}

    {#if tab === 'notizen'}
      <section>
        <h3>Notizen aus dem Spiel
          <span class="count">{notes.filter((n) => !n.promoted).length} offen</span></h3>
        <p class="hint">
          Vermerke, die Spieler:innen mit dem Sprachbefehl
          „Vermerken: …" gesetzt haben. Sie sind im RAG-Index dieser Welt
          aktiv (also im Spiel verfügbar) — hier kannst du wertvolle
          Einträge dauerhaft in die Welt aufnehmen oder verwerfen.
        </p>
        <div class="toolbar">
          <label class="inline">
            <input type="checkbox" bind:checked={notesPromoted} onchange={loadNotes} />
            Bereits übernommene anzeigen
          </label>
          <button onclick={loadNotes} disabled={notesLoading}>
            {notesLoading ? 'Lade…' : 'Aktualisieren'}
          </button>
        </div>
        {#if notesError}<p class="error">{notesError}</p>{/if}
        {#if notes.length === 0}
          <p class="muted">{notesLoading ? 'Lade…' : 'Keine Notizen.'}</p>
        {:else}
          {#each notes as n (n.id)}
            <div class="card" class:promoted={n.promoted}>
              <div class="card-head row">
                <strong>{n.name}</strong>
                <span class="kind-pill">{n.kind}</span>
                {#if n.promoted}<span class="kind-pill ok">übernommen</span>{/if}
                <span class="grow"></span>
                <small class="muted">{n.ts}</small>
              </div>
              <div class="grid">
                <label><span>Art</span>
                  <select bind:value={n.kind}>
                    <option value="person">Person</option>
                    <option value="place">Ort</option>
                    <option value="item">Gegenstand</option>
                    <option value="fact">Welt-Fakt</option>
                  </select>
                </label>
                <label><span>Name</span><input bind:value={n.name} /></label>
              </div>
              <label><span>Beschreibung</span>
                <textarea bind:value={n.description} rows="4"></textarea>
              </label>
              <label><span>Tags (komma)</span>
                <input value={(n.tags ?? []).join(', ')}
                  oninput={(e) => (n.tags = (e.target as HTMLInputElement).value.split(',').map((s) => s.trim()).filter(Boolean))} />
              </label>
              {#if n.raw_text && n.raw_text !== n.description}
                <p class="muted small">Originaler Sprachbefehl: „{n.raw_text}"</p>
              {/if}
              <div class="row">
                {#if !n.promoted}
                  <button onclick={() => promoteNote(n)}>In Welt aufnehmen</button>
                  <button class="danger" onclick={() => discardNote(n)}>Verwerfen</button>
                {:else}
                  <button class="danger" onclick={() => discardNote(n)}>Aus RAG entfernen</button>
                {/if}
              </div>
            </div>
          {/each}
        {/if}
      </section>
    {/if}

    {#if tab === 'zufall'}
      <section>
        <h3>Zufallslisten <button onclick={addTable}>+ Liste</button></h3>
        {#each world.random_tables as t, ti (ti)}
          <div class="card">
            <div class="row">
              <input placeholder="Name" bind:value={t.name} />
              <input placeholder="Beschreibung" bind:value={t.description} />
              <button class="danger" onclick={() => rmTable(ti)}>Liste löschen</button>
            </div>
            {#each t.entries ?? [] as e, ei (ei)}
              <div class="row indent">
                <input type="number" min="1" bind:value={e.weight} title="Gewicht" style="width:70px" />
                <input placeholder="Text" bind:value={e.text} />
                <button class="danger" onclick={() => rmEntry(t, ei)}>×</button>
              </div>
            {/each}
            <button onclick={() => addEntry(t)}>+ Eintrag</button>
          </div>
        {/each}
      </section>
    {/if}

    <div class="toolbar"><button onclick={save}>Speichern</button></div>
  {/if}
{/if}

<style>
  .toolbar { display: flex; gap: 0.5rem; margin: 0.8rem 0; }
  section { background: var(--surface); border-radius: 5px; padding: 1rem; margin-bottom: 1.2rem; }
  section h3 { margin-top: 0; }
  h4 { margin: 0.8rem 0 0.4rem; }
  .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 0.5rem; }
  label { display: block; margin: 0.4rem 0; }
  label span { display: block; font-size: 0.8rem; color: var(--muted); margin-bottom: 0.15rem; }
  label input, label textarea, label select { width: 100%; box-sizing: border-box; }
  label textarea { min-height: 4.5em; line-height: 1.5; resize: vertical; }
  label textarea.big { min-height: 12em; }
  .row { display: flex; gap: 0.4rem; align-items: center; margin: 0.3rem 0; }
  .row.indent { margin-left: 1.2rem; }
  .row input { flex: 1; }
  .card { border: 1px solid var(--border); border-radius: 4px; padding: 0.7rem; margin-top: 0.7rem; }
  .raw { width: 100%; box-sizing: border-box; }
  .error { color: #c25450; }
  .ok { color: #4a9e4f; }
  .hint { color: var(--muted); font-size: 0.9rem; }
  code { background: var(--code-bg); padding: 0 4px; border-radius: 2px; }
  a { color: var(--link); text-decoration: none; }

  /* Tab nav */
  .tabs {
    display: flex; flex-wrap: wrap; gap: 0.3rem;
    border-bottom: 1px solid var(--border);
    margin: 0.5rem 0 1rem;
  }
  @media (max-width: 700px) {
    /* horizontal scroll instead of multi-row wrap so the editor body
       stays at full height on phones */
    .tabs {
      flex-wrap: nowrap; overflow-x: auto; gap: 0.2rem;
      -webkit-overflow-scrolling: touch;
      scrollbar-width: thin;
    }
    .tabs button { flex: 0 0 auto; font-size: 0.88rem;
                    padding: 0.35rem 0.6rem; }
    .grid { grid-template-columns: 1fr !important; }
    .toolbar { flex-wrap: wrap; }
  }
  .tabs button {
    background: transparent; color: var(--muted);
    border: 1px solid transparent; border-bottom: none;
    border-radius: 4px 4px 0 0; padding: 0.4rem 0.8rem;
    font-size: 0.95rem; cursor: pointer;
  }
  .tabs button:hover { color: inherit; background: var(--surface); }
  .tabs button.active {
    color: inherit; background: var(--surface);
    border-color: var(--border); position: relative; top: 1px;
  }
  .tabs .count {
    background: rgba(127,127,127,0.25); color: var(--muted);
    border-radius: 999px; padding: 0 0.45rem; font-size: 0.75rem;
    margin-left: 0.35rem;
  }
  .tabs button.active .count { color: inherit; }

  /* Notizen tab */
  .kind-pill {
    background: rgba(127,127,127,0.25); color: var(--muted);
    border-radius: 999px; padding: 0 0.5rem; font-size: 0.75rem;
    margin-left: 0.4rem;
  }
  .kind-pill.ok { background: rgba(74,158,79,0.30); color: #4a9e4f; }
  .card.promoted { opacity: 0.7; }
  .card-head { align-items: center; }
  .grow { flex: 1; }
  .muted { color: var(--muted); }
  .muted.small { font-size: 0.85rem; }
  label.inline { display: flex; align-items: center; gap: 0.4rem; }
  label.inline input[type=checkbox] { width: auto; }
</style>
