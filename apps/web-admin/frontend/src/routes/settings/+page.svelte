<script lang="ts">
  import { onMount } from 'svelte';
  import {
    getSettings,
    putSettings,
    type ModelsSettings,
    type AudioSettings,
    type ModerationSettings,
    type StorySettings,
    type GeneralSettings
  } from '$lib/api';

  let defaults: Record<string, unknown> = $state({});
  let audio: AudioSettings | null = $state(null);
  let audioBackend: string = $state('auto');
  let audioPwSink: string = $state('');
  let moderation: ModerationSettings | null = $state(null);
  let modEnabled: boolean = $state(true);
  let moderationRaw: string = $state('');
  let story: StorySettings | null = $state(null);
  // Narrative / memory editable fields. Numbers stay as strings in
  // state so empty fields cleanly fall back to the config.toml
  // default (the backend drops empty values before writing
  // data/story.json).
  type StoryNumKey =
    | 'short_term_memory_turns'
    | 'rag_top_k'
    | 'synopsis_max_chars'
    | 'synopsis_batch'
    | 'beat_nudge_after'
    | 'known_facts_cap'
    | 'narration_gate_max_reveals';
  const STORY_NUMS: { key: StoryNumKey; label: string; hint: string }[] = [
    { key: 'short_term_memory_turns', label: 'Memory turns',
      hint: 'How many turns (= 2× messages) the narrator sees inline. Cloud: 24–48. Local 32k: 12–16. Tiny 8k: 6–8.' },
    { key: 'rag_top_k', label: 'RAG top-k',
      hint: 'Retrieved world facts per turn.' },
    { key: 'synopsis_max_chars', label: 'Synopsis max chars',
      hint: 'Rolling long-term memory length cap.' },
    { key: 'synopsis_batch', label: 'Synopsis batch',
      hint: 'How many old messages get folded per pass.' },
    { key: 'beat_nudge_after', label: 'Beat nudge after',
      hint: 'Turns on the same sub-beat before reminding the narrator (0 = off).' },
    { key: 'known_facts_cap', label: 'Known-facts cap',
      hint: 'Max KnownFacts entries before the oldest noteless one is evicted.' },
    { key: 'narration_gate_max_reveals', label: 'Gate max reveals/turn',
      hint: 'Cap on authored reveals the curator may permit per turn.' },
  ];
  let storyNums: Record<StoryNumKey, string> = $state(
    Object.fromEntries(STORY_NUMS.map((n) => [n.key, ''])) as Record<StoryNumKey, string>
  );
  let storyLongTermMemory: boolean = $state(true);
  let storyGateEnabled: boolean = $state(true);
  // Storymodus pin — soft plot-pressure controller (auto/planner/frei).
  // Stored in data/settings.json alongside intro_enabled.
  let general: GeneralSettings | null = $state(null);
  let storyMode: 'auto' | 'planner' | 'frei' = $state('auto');
  let error: string = $state('');
  let status: string = $state('');

  // Preset definitions. Selecting one in the UI populates the editable
  // fields below (model names + endpoints + reasoning) so the operator
  // doesn't have to fill seven endpoint slots by hand for a common
  // setup. `api_key` fields are deliberately left empty — keys live in
  // .env (OPENAI_API_KEY / OPENROUTER_API_KEY) and are resolved by the
  // backend per endpoint based on base_url. "Custom" is a no-op (just
  // edit the fields directly).
  type Preset = {
    label: string;
    names?: Record<string, string>;
    nums?: Record<string, number>;
    efforts?: Record<string, string>;
    eps?: Record<string, { base_url: string; api_key: string }>;
  };
  const PRESETS: Record<string, Preset> = {
    openai: {
      label: 'OpenAI default (Cloud)',
      names: {
        story_llm: 'gpt-5.4-mini', planner_llm: '', gen_llm: 'gpt-5.4-mini',
        stt: 'gpt-4o-mini-transcribe', tts: 'gpt-4o-mini-tts',
        tts_voice: 'ballad', embedding: 'text-embedding-3-small',
      },
      efforts: {
        story_reasoning_effort: 'low', planner_reasoning_effort: 'medium',
        gen_reasoning_effort: 'medium', gate_reasoning_effort: '',
      },
      eps: {
        story: { base_url: '', api_key: '' },
        planner: { base_url: '', api_key: '' },
        gen: { base_url: '', api_key: '' },
        stt: { base_url: '', api_key: '' },
        tts: { base_url: '', api_key: '' },
        embedding: { base_url: '', api_key: '' },
      },
    },
    openrouter_hybrid: {
      label: 'Hybrid: OpenRouter (DeepSeek) chat + OpenAI audio',
      names: {
        story_llm: 'deepseek/deepseek-v4-pro',
        planner_llm: 'deepseek/deepseek-v4-flash',
        gen_llm: 'deepseek/deepseek-v4-pro',
        stt: 'gpt-4o-mini-transcribe', tts: 'gpt-4o-mini-tts',
        tts_voice: 'ballad', embedding: 'text-embedding-3-small',
      },
      efforts: {
        story_reasoning_effort: 'low', planner_reasoning_effort: 'medium',
        gen_reasoning_effort: 'medium', gate_reasoning_effort: '',
      },
      eps: {
        story: { base_url: 'https://openrouter.ai/api/v1', api_key: '' },
        planner: { base_url: 'https://openrouter.ai/api/v1', api_key: '' },
        gen: { base_url: 'https://openrouter.ai/api/v1', api_key: '' },
        stt: { base_url: '', api_key: '' },
        tts: { base_url: '', api_key: '' },
        embedding: { base_url: '', api_key: '' },
      },
    },
    openrouter_full: {
      label: 'OpenRouter (everything: chat + audio + embeddings)',
      names: {
        story_llm: 'deepseek/deepseek-v4-pro',
        planner_llm: 'deepseek/deepseek-v4-flash',
        gen_llm: 'deepseek/deepseek-v4-pro',
        stt: 'openai/whisper-large-v3-turbo',
        tts: 'openai/gpt-4o-mini-tts',
        tts_voice: 'ballad',
        embedding: 'text-embedding-3-small',
      },
      efforts: {
        story_reasoning_effort: 'low', planner_reasoning_effort: 'medium',
        gen_reasoning_effort: 'medium', gate_reasoning_effort: '',
      },
      eps: {
        story: { base_url: 'https://openrouter.ai/api/v1', api_key: '' },
        planner: { base_url: 'https://openrouter.ai/api/v1', api_key: '' },
        gen: { base_url: 'https://openrouter.ai/api/v1', api_key: '' },
        stt: { base_url: 'https://openrouter.ai/api/v1', api_key: '' },
        tts: { base_url: 'https://openrouter.ai/api/v1', api_key: '' },
        embedding: { base_url: 'https://openrouter.ai/api/v1', api_key: '' },
      },
    },
    local: {
      label: 'Local AI Server (qwen3 / faster-whisper / xtts)',
      names: {
        story_llm: 'qwen3-30b-32k', planner_llm: 'qwen3-30b-32k',
        gen_llm: 'qwen3-30b-32k',
        stt: 'deepdml/faster-whisper-large-v3-turbo-ct2',
        tts: 'marcel', tts_voice: 'marcel', embedding: 'bge-m3',
      },
      efforts: {
        story_reasoning_effort: 'none', planner_reasoning_effort: 'none',
        gen_reasoning_effort: 'none', gate_reasoning_effort: 'none',
      },
      eps: {
        story: { base_url: 'http://192.168.178.95:11434/v1', api_key: '' },
        planner: { base_url: 'http://192.168.178.95:11434/v1', api_key: '' },
        gen: { base_url: 'http://192.168.178.95:11434/v1', api_key: '' },
        stt: { base_url: 'http://192.168.178.95:8001/v1', api_key: '' },
        tts: { base_url: 'xtts://192.168.178.95:8002', api_key: '' },
        embedding: { base_url: 'http://192.168.178.95:11434/v1', api_key: '' },
      },
    },
  };
  let presetSel = $state('');   // '' = Custom (no auto-apply on load)

  // structured model fields
  const NAMES = ['story_llm', 'planner_llm', 'gen_llm', 'stt', 'tts', 'tts_voice', 'embedding'];
  const NUMS = ['llm_temperature', 'planner_temperature', 'gen_temperature',
                'frequency_penalty', 'presence_penalty'];
  // Per-role reasoning effort dropdowns. Empty string = inherit (planner/gate)
  // or model-default (story/gen). "none" explicitly disables reasoning even
  // on models where it would otherwise be on (e.g. gpt-5.5+).
  const EFFORTS = ['story_reasoning_effort', 'planner_reasoning_effort',
                   'gen_reasoning_effort', 'gate_reasoning_effort'];
  const EFFORT_VALUES = ['', 'none', 'low', 'medium', 'high', 'xhigh'];
  const PURPOSES = ['story', 'planner', 'gen', 'stt', 'tts', 'embedding'];
  // Initialised up-front so the template can render before onMount seeds them.
  let names: Record<string, string> = $state(Object.fromEntries(NAMES.map((k) => [k, ''])));
  let nums: Record<string, string> = $state(Object.fromEntries(NUMS.map((k) => [k, ''])));
  let efforts: Record<string, string> = $state(Object.fromEntries(EFFORTS.map((k) => [k, ''])));
  let eps: Record<string, { base_url: string; api_key: string }> = $state(
    Object.fromEntries(PURPOSES.map((p) => [p, { base_url: '', api_key: '' }]))
  );
  let rawMode = $state(false);
  let modelsRaw = $state('');

  function seed(ov: Record<string, unknown>) {
    for (const k of NAMES) names[k] = String(ov[k] ?? '');
    for (const k of NUMS) nums[k] = String(ov[k] ?? (defaults[k] ?? ''));
    for (const k of EFFORTS) efforts[k] = String(ov[k] ?? (defaults[k] ?? ''));
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
    // Effort keys are always written (incl. empty/"none") so the overlay can
    // *override* a baked-in default — otherwise the user couldn't dial back
    // from "medium" to "none" without resetting the whole file.
    for (const k of EFFORTS) o[k] = efforts[k];
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
      const mov = (moderation.overrides ?? {}) as Record<string, unknown>;
      modEnabled = (mov.enabled as boolean | undefined) ?? moderation.enabled_default;
      const { enabled: _omit, ...rest } = mov;
      moderationRaw = JSON.stringify(rest, null, 2);

      story = await getSettings<StorySettings>('story');
      const sov = (story.overrides ?? {}) as Record<string, unknown>;
      for (const { key } of STORY_NUMS) {
        const v = sov[key];
        storyNums[key] = v === undefined || v === null ? '' : String(v);
      }
      storyLongTermMemory = (sov.long_term_memory as boolean | undefined)
        ?? (story.defaults.long_term_memory as boolean | undefined) ?? true;
      storyGateEnabled = (sov.narration_gate_enabled as boolean | undefined)
        ?? (story.defaults.narration_gate_enabled as boolean | undefined) ?? true;
      // General settings (data/settings.json) — Storymodus etc.
      general = await getSettings<GeneralSettings>('general');
      storyMode = general.story_mode ?? 'auto';
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
    try {
      const thresholds = moderationRaw.trim() ? JSON.parse(moderationRaw) : {};
      delete (thresholds as Record<string, unknown>).enabled;
      await putSettings('moderation', { enabled: modEnabled, ...thresholds });
      status = modEnabled ? 'Moderation gespeichert (aktiv).'
                          : 'Moderation gespeichert — DEAKTIVIERT.';
    } catch (e) { error = `Moderation: ${e}`; }
  }

  async function saveStoryMode() {
    error = ''; status = '';
    try {
      await putSettings('general', { story_mode: storyMode });
      status = `Storymodus gespeichert: ${storyMode}. (Greift sofort beim nächsten Spielzug.)`;
    } catch (e) { error = `Storymodus: ${e}`; }
  }

  async function saveStory() {
    error = ''; status = '';
    const payload: Record<string, unknown> = {};
    for (const { key } of STORY_NUMS) {
      const v = storyNums[key].trim();
      if (v !== '') payload[key] = Number(v);   // backend coerces to int
    }
    payload.long_term_memory = storyLongTermMemory;
    payload.narration_gate_enabled = storyGateEnabled;
    try {
      await putSettings('story', payload);
      status = 'Erzählung / Memory gespeichert (greift bei neuen Turns).';
    } catch (e) { error = `Erzählung: ${e}`; }
  }

  function storyDef(k: string): string {
    const v = (story?.defaults ?? {})[k];
    return v === undefined || v === null ? '' : String(v);
  }

  function def(k: string): string { return String(defaults[k] ?? ''); }

  function applyPreset(id: string) {
    const p = PRESETS[id];
    if (!p) return;
    if (p.names) {
      for (const [k, v] of Object.entries(p.names)) names[k] = v;
    }
    if (p.nums) {
      for (const [k, v] of Object.entries(p.nums)) nums[k] = String(v);
    }
    if (p.efforts) {
      for (const [k, v] of Object.entries(p.efforts)) efforts[k] = v;
    }
    if (p.eps) {
      for (const [k, v] of Object.entries(p.eps)) eps[k] = { ...v };
    }
    // Trigger a Svelte 5 store flush by reassigning the state vars.
    names = { ...names };
    nums = { ...nums };
    efforts = { ...efforts };
    eps = { ...eps };
    status = `Preset "${p.label}" geladen. Speichern nicht vergessen.`;
  }
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

  <div class="preset-row">
    <label class="preset">
      <span>Preset laden</span>
      <select bind:value={presetSel} onchange={() => { if (presetSel) applyPreset(presetSel); presetSel = ''; }}>
        <option value="">— Custom (Felder einzeln bearbeiten) —</option>
        {#each Object.entries(PRESETS) as [id, p] (id)}
          <option value={id}>{p.label}</option>
        {/each}
      </select>
    </label>
    <p class="hint small">
      Preset überschreibt Modellnamen, Endpoints und Reasoning-Werte.
      <strong>API-Keys liegen in <code>.env</code></strong>
      (<code>OPENAI_API_KEY</code> und/oder <code>OPENROUTER_API_KEY</code>) —
      endpoints mit base_url <code>openrouter.ai/api/v1</code> nutzen
      automatisch den OpenRouter-Key, alle anderen den OpenAI-Key. Speichern
      nicht vergessen.
    </p>
  </div>

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

    <h4>Reasoning-Effort <small>(gpt-5.x — leer = config-default, "none" = aus)</small></h4>
    <p class="hint">
      Steuert „Thinking" pro Rolle. <code>none</code> = kein
      Chain-of-Thought (schnell, billig). <code>low/medium/high/xhigh</code>
      lassen das Modell vorher überlegen — bessere Long-Context-Treue (Canon,
      JSON-Schema) gegen Output-Tokens und Latenz. <code>gate</code> leer ⇒
      erbt vom Planner. Lokale OpenAI-kompatible Server (Ollama/vLLM)
      ignorieren das Feld stillschweigend.
    </p>
    <div class="grid">
      {#each EFFORTS as k (k)}
        <label>{k}
          <select bind:value={efforts[k]}>
            {#each EFFORT_VALUES as v (v)}
              <option value={v}>{v === '' ? '(default)' : v}</option>
            {/each}
          </select>
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
  <h2>Storymodus</h2>
  <p class="hint">
    Steuert den <strong>Plot-Druck</strong> des Erzählers — wie stark er auf
    einem geplanten Bogen besteht. <code>Auto</code> lässt eine kleine
    Heuristik pro Spielzug entscheiden (siehe Verlauf-Marker <code>[pressure]</code>);
    <code>Plan</code> nagelt vollen Plot-Druck fest, <code>Frei</code>
    schaltet die Plot-Maschinerie komplett aus und macht den Erzähler
    reaktiv. Auf dem Pi via Sysmenu „Storymodus" überschreibbar.
  </p>
  <label>Modus:
    <select bind:value={storyMode}>
      <option value="auto">Auto — Heuristik entscheidet</option>
      <option value="planner">Plan — voller Plot-Druck</option>
      <option value="frei">Frei — kein Plot-Druck</option>
    </select>
  </label>
  <div class="actions"><button onclick={saveStoryMode}>Speichern</button></div>
</section>

<section>
  <h2>Erzählung &amp; Memory</h2>
  {#if story}
    <p class="hint">
      Leere Felder = Default aus <code>config.toml</code>. Gespeichert
      wird in <code>data/story.json</code>. Greift bei neuen Turns
      (kein Restart nötig).
    </p>
    <div class="grid">
      {#each STORY_NUMS as n (n.key)}
        <label>
          {n.label}
          <input
            type="number"
            bind:value={storyNums[n.key]}
            placeholder={storyDef(n.key)}
            title={n.hint}
            min="0"
          />
        </label>
      {/each}
    </div>
    <p class="hint">
      <strong>{STORY_NUMS[0].label}</strong> ist der wichtigste Knopf
      hier: {STORY_NUMS[0].hint}
    </p>
    <label class="onoff">
      <input type="checkbox" bind:checked={storyLongTermMemory} />
      <strong>Langzeit-Memory aktiv</strong>
      <span class="hint small">— wenn aus, wachsen Sessions ohne
        Synopsis-Folding (nur bei tiny-context lokalen Modellen).</span>
    </label>
    <label class="onoff">
      <input type="checkbox" bind:checked={storyGateEnabled} />
      <strong>Narration-Gate (Curator) aktiv</strong>
      <span class="hint small">— wenn aus, läuft der per-Turn-Spoiler-
        Schutz nur algorithmisch (kein gate_llm Call).</span>
    </label>
    <div class="actions"><button onclick={saveStory}>Speichern</button></div>
  {/if}
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
    <label class="onoff">
      <input type="checkbox" bind:checked={modEnabled} />
      Moderation aktiviert
      {#if !modEnabled}<span class="warn"> — Eingaben werden NICHT geprüft</span>{/if}
    </label>
    <p class="hint">Default: enabled={String(moderation.enabled_default)},
      threshold={moderation.default_threshold}. Schwellen pro Kategorie als JSON
      (z. B. <code>{'{'}"default":0.5,"categories":{'{'}"violence":0.7{'}'}{'}'}</code>):</p>
    <textarea bind:value={moderationRaw} rows="6"></textarea>
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
  .hint.small { font-size: 0.8rem; }
  .preset-row { background: var(--surface-2, transparent); padding: 0.6rem 0.7rem;
                border-radius: 4px; margin-bottom: 1rem;
                border: 1px dashed var(--border); }
  .preset-row .preset { display: grid;
                        grid-template-columns: max-content 1fr; gap: 0.5rem;
                        align-items: center; margin: 0; max-width: 720px; }
  .preset-row .preset > span { font-size: 0.85rem; color: var(--muted);
                                white-space: nowrap; }
  .preset-row .preset select { width: 100%; box-sizing: border-box; }
  .onoff { display: flex; align-items: center; gap: 0.4rem; font-size: 0.95rem; color: var(--fg); }
  .onoff input { width: auto; }
  .warn { color: #c25450; }
  .error { color: #c25450; }
  .ok { color: #4a9e4f; }
  .actions { margin-top: 0.6rem; }
  code { background: var(--code-bg); padding: 0 4px; border-radius: 2px; }
</style>
