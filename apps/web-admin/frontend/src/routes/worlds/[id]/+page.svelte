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
  type TabId = 'grundlagen' | 'ton' | 'regionen' | 'orte' | 'fraktionen'
    | 'personen' | 'items' | 'kreaturen' | 'lore' | 'zufall' | 'notizen';
  const TAB_IDS: TabId[] = ['grundlagen', 'ton', 'regionen', 'orte',
    'fraktionen', 'personen', 'items', 'kreaturen', 'lore', 'zufall',
    'notizen'];
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
    w.regions ??= [];
    w.places ??= [];
    w.factions ??= [];
    w.persons ??= [];
    w.items ??= [];
    w.creatures ??= [];
    w.glossary ??= [];
    w.history ??= [];
    w.fragments ??= [];
    w.random_tables ??= [];
    w.tone ??= { darkness: 2, humor: 1, romance: 1, action: 3, horror: 1, pacing: 'medium', notes: '' };
    w.blueprint ??= { premise: '', beats: [], escalation_rule: '' };
    w.blueprint.beats ??= [];
    // Multi-variant blueprints. When the world only has the legacy
    // single `blueprint`, we virtually hoist it as variants[0] so the
    // editor always presents the new shape (single-variant editing
    // still works exactly like before). Save writes both back —
    // backend persists both fields; the engine prefers `blueprints`
    // when non-empty (active_blueprint helper).
    w.blueprints ??= [];
    if (w.blueprints.length === 0 && w.blueprint && w.blueprint.beats) {
      w.blueprints = [{
        name: 'Hauptbogen',
        description: '',
        length: 'medium',
        structure: 'linear',
        twist_kind: '',
        trigger_hints: [],
        blueprint: w.blueprint
      }];
    }
    for (const v of w.blueprints) {
      v.trigger_hints ??= [];
      v.blueprint ??= { premise: '', beats: [], escalation_rule: '' };
      v.blueprint.beats ??= [];
    }
    // tech_magic is allowed to stay null (no system at all); we just
    // normalise the inner shape lazily when the editor needs it (see
    // ensureTechMagic). Existing worlds without the field load fine.
    // Also normalise the new per-entry fields on places/persons/
    // creatures so binding doesn't trip on undefined when the world
    // was generated with the old pipeline.
    for (const p of w.places) {
      p.region ??= ''; p.contains ??= []; p.adjacent ??= [];
    }
    for (const p of w.persons) {
      p.faction ??= ''; p.faction_role ??= '';
    }
    for (const c of w.creatures) {
      c.habitat ??= ''; c.threat_level ??= 'medium';
    }
    return w;
  }

  function ensureTechMagic() {
    world.tech_magic ??= {
      kind: 'neither', description: '', rules: [], cost_or_risk: ''
    };
    world.tech_magic.rules ??= [];
  }
  function addRule() {
    ensureTechMagic();
    world.tech_magic.rules = [...world.tech_magic.rules, ''];
  }
  function rmRule(i: number) {
    if (!world.tech_magic) return;
    world.tech_magic.rules = world.tech_magic.rules.filter(
      (_: any, idx: number) => idx !== i);
  }
  function clearTechMagic() {
    if (!confirm('Tech/Magie-System komplett entfernen?')) return;
    world.tech_magic = null;
  }

  // --- Blueprint-Variants editing (Ton & Bogen tab) ---
  let activeVariantIdx = $state(0);
  const LENGTH_OPTIONS = ['short', 'medium', 'long', 'epic'];
  const STRUCTURE_OPTIONS = ['linear', 'parallel', 'spiral', 'frame', 'mosaic'];
  const TWIST_OPTIONS = [
    { value: '', label: '— kein expliziter Twist —' },
    { value: 'betrayal', label: 'betrayal — Verbündeter wird Gegner' },
    { value: 'revelation', label: 'revelation — Wahrheit kippt Wahrnehmung' },
    { value: 'sacrifice', label: 'sacrifice — Kosten höher als gedacht' },
    { value: 'hidden_enemy', label: 'hidden_enemy — eigentlicher Antagonist enthüllt' },
    { value: 'red_herring', label: 'red_herring — falscher Antagonist' },
    { value: 'role_reversal', label: 'role_reversal — Opfer/Täter tauschen' },
    { value: 'circular', label: 'circular — Anfang = Ende, anders' }
  ];

  function addVariant() {
    world.blueprints = [...world.blueprints, {
      name: `Variante ${world.blueprints.length + 1}`,
      description: '',
      length: 'medium',
      structure: 'linear',
      twist_kind: '',
      trigger_hints: [],
      blueprint: {
        premise: '',
        beats: [],
        escalation_rule: ''
      }
    }];
    activeVariantIdx = world.blueprints.length - 1;
  }

  function rmVariant(i: number) {
    if (world.blueprints.length <= 1) {
      alert('Mindestens eine Variante muss erhalten bleiben.');
      return;
    }
    const v = world.blueprints[i];
    if (!confirm(`Variante "${v.name}" wirklich löschen?`)) return;
    world.blueprints = world.blueprints.filter((_: any, idx: number) => idx !== i);
    activeVariantIdx = Math.max(0, Math.min(activeVariantIdx, world.blueprints.length - 1));
  }

  function addVariantBeat(v: any) {
    v.blueprint.beats = [...v.blueprint.beats, { name: '', goal: '', tension: 5 }];
  }

  function rmVariantBeat(v: any, i: number) {
    v.blueprint.beats = v.blueprint.beats.filter((_: any, idx: number) => idx !== i);
  }

  function variantTriggersStr(v: any): string {
    return (v.trigger_hints ?? []).join(', ');
  }

  function setVariantTriggers(v: any, s: string) {
    v.trigger_hints = s.split(',').map((t) => t.trim()).filter(Boolean);
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
  // Legacy single-blueprint addBeat / rmBeat were replaced by the
  // variant-aware addVariantBeat / rmVariantBeat — single-blueprint
  // worlds are still editable because normalize() hoists the legacy
  // `world.blueprint` into `world.blueprints[0]` for the editor.

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
        <span class="count">{world.blueprints.length || 1}</span></button>
      <button class:active={tab === 'regionen'} onclick={() => setTab('regionen')}>Regionen
        <span class="count">{world.regions.length}</span></button>
      <button class:active={tab === 'orte'} onclick={() => setTab('orte')}>Orte
        <span class="count">{world.places.length}</span></button>
      <button class:active={tab === 'fraktionen'} onclick={() => setTab('fraktionen')}>Fraktionen
        <span class="count">{world.factions.length}</span></button>
      <button class:active={tab === 'personen'} onclick={() => setTab('personen')}>Personen
        <span class="count">{world.persons.length}</span></button>
      <button class:active={tab === 'items'} onclick={() => setTab('items')}>Gegenstände
        <span class="count">{world.items.length}</span></button>
      <button class:active={tab === 'kreaturen'} onclick={() => setTab('kreaturen')}>Kreaturen
        <span class="count">{world.creatures.length}</span></button>
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
        <label><span>Physik/Magie (Kurz-Zusammenfassung, freitext — gilt
          immer; die strukturierte Spec unten ergänzt sie)</span>
          <textarea bind:value={world.magic_physics} rows="5"></textarea>
        </label>
        <label><span>Story-Patterns (komma)</span>
          <input value={patternsStr()} oninput={(e) => setPatterns((e.target as HTMLInputElement).value)} />
        </label>
      </section>

      <section>
        <h3>Tech / Magie-System (strukturiert)</h3>
        <p class="hint">
          Strukturierte Spec, die der Erzähler bei Fragen nach Regeln /
          Möglichkeiten konsultiert. Jede Regel ist ein kurzer Satz
          (z. B. „Teleportation braucht einen bekannten Anker-Punkt.").
          Lass das Feld leer (auf „—") wenn die Welt keine besonderen
          Tech/Magie-Regeln hat.
        </p>
        {#if !world.tech_magic}
          <div class="row">
            <button onclick={ensureTechMagic}>+ Tech/Magie-System anlegen</button>
            <span class="hint">— aktuell: keine strukturierte Spec.</span>
          </div>
        {:else}
          <div class="grid">
            <label><span>Art</span>
              <select bind:value={world.tech_magic.kind}>
                <option value="neither">— keine (alltägliche Welt)</option>
                <option value="technology">technology</option>
                <option value="magic">magic</option>
                <option value="both">both (Science-Fantasy)</option>
              </select>
            </label>
            <label><span>Kosten / Risiken</span>
              <input bind:value={world.tech_magic.cost_or_risk}
                placeholder="z. B. kostet einen Atemzug Erinnerung" />
            </label>
          </div>
          <label><span>Beschreibung (2–4 Sätze, wie fühlt sich das System an)</span>
            <textarea bind:value={world.tech_magic.description} rows="4"></textarea>
          </label>
          <h4>Regeln <button onclick={addRule}>+ Regel</button></h4>
          {#if world.tech_magic.rules.length === 0}
            <p class="hint">Noch keine Regeln. „+ Regel" für je einen kurzen Satz.</p>
          {/if}
          {#each world.tech_magic.rules as r, i (i)}
            <div class="row">
              <input placeholder="kurze Regel (1 Satz)"
                bind:value={world.tech_magic.rules[i]} />
              <button class="danger" onclick={() => rmRule(i)}>×</button>
            </div>
          {/each}
          <div class="row" style="margin-top: 0.7rem">
            <button class="danger" onclick={clearTechMagic}>
              System komplett entfernen
            </button>
          </div>
        {/if}
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
        <h3>Spannungsbögen (Blueprint-Varianten)</h3>
        <p class="hint">
          Mehrere Story-Bögen pro Welt → der Story-Planer wählt zu
          Beginn jeder neuen Substory einen aus, der zum
          Spielverlauf passt. Mische bewusst Längen, Strukturen und
          Twist-Arten — sonst fühlen sich alle Spielsessions strukturell
          gleich an. Bei nur einer Variante verhält sich das System
          wie früher.
        </p>

        <nav class="vtabs">
          {#each world.blueprints as v, i (i)}
            <button
              class:active={activeVariantIdx === i}
              onclick={() => (activeVariantIdx = i)}
              title={v.description || v.blueprint.premise}
            >
              {v.name || `Variante ${i + 1}`}
              <span class="vbadge">{v.length}/{v.structure}</span>
            </button>
          {/each}
          <button class="ghost" onclick={addVariant}>+ Variante</button>
        </nav>

        {#each world.blueprints as v, i (i)}
          {#if activeVariantIdx === i}
            <div class="variant-body">
              <div class="grid">
                <label><span>Name</span>
                  <input bind:value={v.name} placeholder="Schmuggler-Run" />
                </label>
                <label><span>Länge</span>
                  <select bind:value={v.length}>
                    {#each LENGTH_OPTIONS as l (l)}
                      <option value={l}>{l}</option>
                    {/each}
                  </select>
                </label>
                <label><span>Struktur</span>
                  <select bind:value={v.structure}>
                    {#each STRUCTURE_OPTIONS as s (s)}
                      <option value={s}>{s}</option>
                    {/each}
                  </select>
                </label>
                <label><span>Twist-Art</span>
                  <select bind:value={v.twist_kind}>
                    {#each TWIST_OPTIONS as t (t.value)}
                      <option value={t.value}>{t.label}</option>
                    {/each}
                  </select>
                </label>
              </div>
              <label><span>Beschreibung (wann passt dieser Bogen)</span>
                <textarea bind:value={v.description} rows="2"></textarea>
              </label>
              <label><span>Trigger-Hinweise (komma — wann picken)</span>
                <input
                  value={variantTriggersStr(v)}
                  oninput={(e) => setVariantTriggers(v, (e.target as HTMLInputElement).value)}
                  placeholder="z.B. erstes mal, kennt fraktionen, intimer ton"
                />
              </label>
              <label><span>Prämisse (Premise)</span>
                <textarea bind:value={v.blueprint.premise} rows="3"></textarea>
              </label>
              <label><span>Eskalationsregel</span>
                <textarea bind:value={v.blueprint.escalation_rule} rows="2"></textarea>
              </label>
              <h4>Beats <button onclick={() => addVariantBeat(v)}>+ Beat</button></h4>
              {#each v.blueprint.beats as b, bi (bi)}
                <div class="row">
                  <input placeholder="Name" bind:value={b.name} />
                  <input placeholder="Ziel" bind:value={b.goal} />
                  <input type="number" min="0" max="10" bind:value={b.tension}
                          title="Spannung 0-10" style="width: 70px" />
                  <button class="danger" onclick={() => rmVariantBeat(v, bi)}>×</button>
                </div>
              {/each}

              <div class="row" style="margin-top: 0.9rem; justify-content: flex-end">
                <button class="danger" onclick={() => rmVariant(i)}>
                  Variante löschen
                </button>
              </div>
            </div>
          {/if}
        {/each}
      </section>
    {/if}

    {#if tab === 'regionen'}
      <ContentList spec={spec('regions')} bind:items={world.regions} worldId={page.params.id} />
    {/if}

    {#if tab === 'orte'}
      <ContentList spec={spec('places')} bind:items={world.places} worldId={page.params.id} />
    {/if}

    {#if tab === 'fraktionen'}
      <ContentList spec={spec('factions')} bind:items={world.factions} worldId={page.params.id} />
    {/if}

    {#if tab === 'personen'}
      <ContentList spec={spec('persons')} bind:items={world.persons} worldId={page.params.id} />
    {/if}

    {#if tab === 'items'}
      <ContentList spec={spec('items')} bind:items={world.items} worldId={page.params.id} />
    {/if}

    {#if tab === 'kreaturen'}
      <ContentList spec={spec('creatures')} bind:items={world.creatures} worldId={page.params.id} />
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

  /* Blueprint-variants sub-tabs */
  .vtabs { display: flex; flex-wrap: wrap; gap: 0.3rem;
            margin: 0.5rem 0 0.8rem;
            border-bottom: 1px solid var(--border);
            padding-bottom: 0.4rem; }
  .vtabs button { background: transparent; color: var(--muted);
                   border: 1px solid var(--border);
                   border-radius: 4px; padding: 0.3rem 0.7rem;
                   font-size: 0.9rem; cursor: pointer; }
  .vtabs button:hover { color: inherit; }
  .vtabs button.active { background: var(--surface);
                          color: inherit; border-color: #6fc3df; }
  .vtabs button.ghost { color: var(--muted); border-style: dashed; }
  .vbadge { color: var(--muted); margin-left: 0.4rem;
            font-size: 0.75rem; font-family: monospace; }
  .vtabs button.active .vbadge { color: inherit; }
  .variant-body { padding-top: 0.4rem; }
</style>
