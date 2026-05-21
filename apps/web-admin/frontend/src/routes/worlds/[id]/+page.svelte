<script lang="ts">
  import { page } from '$app/state';
  import { getWorld, putWorld, reindexWorld, waitForJob, type Job } from '$lib/api';
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
    <!-- Core scalar fields -->
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
        <label><span>Wartesound (Datei)</span><input bind:value={world.wait_sound} /></label>
      </div>
      <label><span>Beschreibung</span><textarea bind:value={world.description} rows="3"></textarea></label>
      <label><span>Ausgangssituation</span><textarea bind:value={world.starting_situation} rows="2"></textarea></label>
      <label><span>Erzählstil</span><input bind:value={world.narration_style} /></label>
      <label><span>Stil-Anker (voice_sample)</span><textarea bind:value={world.voice_sample} rows="2"></textarea></label>
      <div class="grid">
        <label><span>Stimmung</span><input bind:value={world.mood} /></label>
        <label><span>Ambiente</span><input bind:value={world.ambience} /></label>
      </div>
      <label><span>Physik/Magie</span><textarea bind:value={world.magic_physics} rows="2"></textarea></label>
      <label><span>Story-Patterns (komma)</span>
        <input value={patternsStr()} oninput={(e) => setPatterns((e.target as HTMLInputElement).value)} />
      </label>
    </section>

    <!-- Tone -->
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

    <!-- Blueprint -->
    <section>
      <h3>Spannungsbogen (Blueprint)</h3>
      <label><span>Prämisse</span><textarea bind:value={world.blueprint.premise} rows="2"></textarea></label>
      <label><span>Eskalationsregel</span><textarea bind:value={world.blueprint.escalation_rule} rows="2"></textarea></label>
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

    <!-- Content lists -->
    {#each CONTENT_KINDS as spec (spec.prop)}
      <ContentList {spec} bind:items={world[spec.prop]} worldId={page.params.id} />
    {/each}

    <!-- Random tables -->
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
</style>
