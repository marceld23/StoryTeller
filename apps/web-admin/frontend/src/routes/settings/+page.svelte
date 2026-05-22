<script lang="ts">
  import { onMount } from 'svelte';
  import {
    getSettings,
    putSettings,
    type ModelsSettings,
    type AudioSettings,
    type ModerationSettings
  } from '$lib/api';

  let defaults: Record<string, unknown> = $state({});
  let audio: AudioSettings | null = $state(null);
  let audioBackend: string = $state('auto');
  let audioPwSink: string = $state('');
  let moderation: ModerationSettings | null = $state(null);
  let moderationRaw: string = $state('');
  let error: string = $state('');
  let status: string = $state('');

  // structured model fields
  const NAMES = ['story_llm', 'planner_llm', 'gen_llm', 'stt', 'tts', 'tts_voice', 'embedding'];
  const NUMS = ['llm_temperature', 'planner_temperature', 'gen_temperature',
                'frequency_penalty', 'presence_penalty'];
  const PURPOSES = ['story', 'planner', 'gen', 'stt', 'tts', 'embedding'];
  let names: Record<string, string> = $state({});
  let nums: Record<string, string> = $state({});
  let eps: Record<string, { base_url: string; api_key: string }> = $state({});
  let rawMode = $state(false);
  let modelsRaw = $state('');

  function seed(ov: Record<string, unknown>) {
    for (const k of NAMES) names[k] = String(ov[k] ?? '');
    for (const k of NUMS) nums[k] = String(ov[k] ?? (defaults[k] ?? ''));
    for (const p of PURPOSES) {
      const e = (ov[`${p}_endpoint`] ?? {}) as { base_url?: string; api_key?: string };
      eps[p] = { base_url: String(e.base_url ?? ''), api_key: String(e.api_key ?? '') };
    }
  }

  function buildModels(): Record<string, unknown> {
    const o: Record<string, unknown> = {};
    for (const k of NAMES) if (names[k].trim()) o[k] = names[k].trim();
    for (const k of NUMS) {
      const n = parseFloat(nums[k]);
      if (Number.isFinite(n)) o[k] = n;
    }
    for (const p of PURPOSES) {
      const e = eps[p];
      if (e.base_url.trim()) {
        o[`${p}_endpoint`] = { base_url: e.base_url.trim(), api_key: e.api_key.trim() };
      }
    }
    return o;
  }

  onMount(async () => {
    try {
      const models = await getSettings<ModelsSettings>('models');
      defaults = models.defaults ?? {};
      seed((models.overrides ?? {}) as Record<string, unknown>);
      modelsRaw = JSON.stringify(buildModels(), null, 2);
      audio = await getSettings<AudioSettings>('audio');
      audioBackend = String((audio.overrides as { backend?: string })?.backend ?? audio.default_backend ?? 'auto');
      audioPwSink = String((audio.overrides as { pw_sink?: string })?.pw_sink ?? '');
      moderation = await getSettings<ModerationSettings>('moderation');
      moderationRaw = JSON.stringify(moderation.overrides ?? {}, null, 2);
    } catch (e) {
      error = String(e);
    }
  });

  function toggleRaw() {
    if (!rawMode) modelsRaw = JSON.stringify(buildModels(), null, 2);
    rawMode = !rawMode;
  }

  async function saveModels() {
    error = ''; status = '';
    try {
      const data = rawMode ? JSON.parse(modelsRaw) : buildModels();
      await putSettings('models', data);
      status = 'Modelle gespeichert. (Greift bei neuen Sessions / nach Neustart von storyteller + storyteller-web-ui.)';
    } catch (e) { error = `Modelle: ${e}`; }
  }

  async function saveAudio() {
    error = ''; status = '';
    const data: Record<string, string> = { backend: audioBackend };
    if (audioPwSink.trim()) data.pw_sink = audioPwSink.trim();
    try { await putSettings('audio', data); status = 'Audio gespeichert.'; }
    catch (e) { error = `Audio: ${e}`; }
  }

  async function saveModeration() {
    error = ''; status = '';
    try { await putSettings('moderation', JSON.parse(moderationRaw)); status = 'Moderation gespeichert.'; }
    catch (e) { error = `Moderation: ${e}`; }
  }

  function def(k: string): string { return String(defaults[k] ?? ''); }
</script>

<h1>Einstellungen</h1>
{#if error}<p class="error">{error}</p>{/if}
{#if status}<p class="ok">{status}</p>{/if}

<section>
  <div class="head">
    <h2>Modelle</h2>
    <label class="rawtoggle"><input type="checkbox" checked={rawMode} onchange={toggleRaw} /> Roh-JSON</label>
  </div>
  <p class="hint">Leere Felder = Standard aus <code>config.toml</code>. <code>planner_llm</code>/<code>gen_llm</code> leer ⇒ wie <code>story_llm</code>. Gespeichert wird in <code>data/models.json</code>.</p>

  {#if rawMode}
    <textarea bind:value={modelsRaw} rows="16"></textarea>
  {:else}
    <h4>Modellnamen</h4>
    <div class="grid">
      {#each NAMES as k (k)}
        <label>{k}
          <input bind:value={names[k]} placeholder={def(k) || '(leer)'} />
        </label>
      {/each}
    </div>

    <h4>Parameter</h4>
    <div class="grid">
      {#each NUMS as k (k)}
        <label>{k}
          <input type="number" step="0.05" bind:value={nums[k]} placeholder={def(k)} />
        </label>
      {/each}
    </div>

    <h4>Eigene OpenAI-kompatible Endpoints <small>(leer = OpenAI)</small></h4>
    <p class="hint">base_url inkl. Port und <code>/v1</code>, z. B. <code>http://192.168.1.50:8000/v1</code>.
      Server muss Tool-Calls + JSON-Mode können (vLLM o. ä.). Moderation bleibt immer OpenAI.</p>
    {#each PURPOSES as p (p)}
      <div class="ep">
        <span class="eplabel">{p}</span>
        <input bind:value={eps[p].base_url} placeholder="base_url (leer = OpenAI)" />
        <input bind:value={eps[p].api_key} placeholder="api_key (optional)" />
      </div>
    {/each}
  {/if}
  <div class="actions"><button onclick={saveModels}>Speichern</button></div>
</section>

<section>
  <h2>Audio</h2>
  {#if audio}
    <p class="hint">Default: <code>{audio.default_backend}</code></p>
    <label>Backend:
      <select bind:value={audioBackend}>
        {#each audio.allowed_backends as b (b)}<option value={b}>{b}</option>{/each}
      </select>
    </label>
    <label>PipeWire-Sink: <input bind:value={audioPwSink} placeholder="(leer = default)" /></label>
    <div class="actions"><button onclick={saveAudio}>Speichern</button></div>
  {/if}
</section>

<section>
  <h2>Moderation</h2>
  {#if moderation}
    <p class="hint">Default: enabled={String(moderation.enabled_default)}, threshold={moderation.default_threshold}</p>
    <textarea bind:value={moderationRaw} rows="8"></textarea>
    <div class="actions"><button onclick={saveModeration}>Speichern</button></div>
  {/if}
</section>

<style>
  section { margin-bottom: 2rem; padding: 1rem; background: var(--surface); border-radius: 4px; }
  section h2 { margin-top: 0; font-size: 1.1rem; }
  .head { display: flex; justify-content: space-between; align-items: center; }
  .rawtoggle { font-size: 0.85rem; color: var(--muted); }
  h4 { margin: 0.9rem 0 0.3rem; font-size: 0.95rem; }
  .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 0.5rem; }
  label { display: block; margin: 0.3rem 0; font-size: 0.85rem; color: var(--muted); }
  label input, label select, textarea { width: 100%; box-sizing: border-box; }
  .ep { display: grid; grid-template-columns: 6rem 2fr 1fr; gap: 0.4rem; align-items: center; margin: 0.3rem 0; }
  .eplabel { font-size: 0.85rem; color: var(--muted); }
  textarea { width: 100%; box-sizing: border-box; }
  .hint { color: var(--muted); font-size: 0.9rem; margin: 0.3rem 0; }
  .error { color: #c25450; }
  .ok { color: #4a9e4f; }
  .actions { margin-top: 0.6rem; }
  code { background: var(--code-bg); padding: 0 4px; border-radius: 2px; }
</style>
