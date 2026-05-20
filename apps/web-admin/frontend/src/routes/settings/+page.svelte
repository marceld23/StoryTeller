<script lang="ts">
  import { onMount } from 'svelte';
  import {
    getSettings,
    putSettings,
    type ModelsSettings,
    type AudioSettings,
    type ModerationSettings
  } from '$lib/api';

  let models: ModelsSettings | null = $state(null);
  let modelsRaw: string = $state('');
  let audio: AudioSettings | null = $state(null);
  let audioBackend: string = $state('auto');
  let audioPwSink: string = $state('');
  let moderation: ModerationSettings | null = $state(null);
  let moderationRaw: string = $state('');
  let error: string = $state('');
  let status: string = $state('');

  onMount(async () => {
    try {
      models = await getSettings<ModelsSettings>('models');
      modelsRaw = JSON.stringify(models.overrides ?? {}, null, 2);
      audio = await getSettings<AudioSettings>('audio');
      audioBackend = String((audio.overrides as { backend?: string })?.backend ?? audio.default_backend ?? 'auto');
      audioPwSink = String((audio.overrides as { pw_sink?: string })?.pw_sink ?? '');
      moderation = await getSettings<ModerationSettings>('moderation');
      moderationRaw = JSON.stringify(moderation.overrides ?? {}, null, 2);
    } catch (e) {
      error = String(e);
    }
  });

  async function saveModels() {
    error = ''; status = '';
    try {
      const data = JSON.parse(modelsRaw);
      await putSettings('models', data);
      status = 'Modelle gespeichert.';
    } catch (e) { error = `Modelle: ${e}`; }
  }

  async function saveAudio() {
    error = ''; status = '';
    const data: Record<string, string> = { backend: audioBackend };
    if (audioPwSink.trim()) data.pw_sink = audioPwSink.trim();
    try {
      await putSettings('audio', data);
      status = 'Audio gespeichert.';
    } catch (e) { error = `Audio: ${e}`; }
  }

  async function saveModeration() {
    error = ''; status = '';
    try {
      const data = JSON.parse(moderationRaw);
      await putSettings('moderation', data);
      status = 'Moderation gespeichert.';
    } catch (e) { error = `Moderation: ${e}`; }
  }
</script>

<h1>Einstellungen</h1>
{#if error}<p class="error">{error}</p>{/if}
{#if status}<p class="ok">{status}</p>{/if}

<section>
  <h2>Modelle (Overrides)</h2>
  {#if models}
    <p class="hint">Defaults: <code>story_llm = {String(models.defaults['story_llm'])}</code></p>
    <textarea bind:value={modelsRaw} rows="10"></textarea>
    <div class="actions"><button onclick={saveModels}>Speichern</button></div>
  {/if}
</section>

<section>
  <h2>Audio</h2>
  {#if audio}
    <p class="hint">Default: <code>{audio.default_backend}</code></p>
    <label>Backend:
      <select bind:value={audioBackend}>
        {#each audio.allowed_backends as b (b)}
          <option value={b}>{b}</option>
        {/each}
      </select>
    </label>
    <label>PipeWire-Sink:
      <input bind:value={audioPwSink} placeholder="(leer = default)" />
    </label>
    <div class="actions"><button onclick={saveAudio}>Speichern</button></div>
  {/if}
</section>

<section>
  <h2>Moderation</h2>
  {#if moderation}
    <p class="hint">
      Default: enabled={String(moderation.enabled_default)},
      threshold={moderation.default_threshold}
    </p>
    <textarea bind:value={moderationRaw} rows="10"></textarea>
    <div class="actions"><button onclick={saveModeration}>Speichern</button></div>
  {/if}
</section>

<style>
  section { margin-bottom: 2rem; padding: 1rem; background: white; border-radius: 4px; }
  section h2 { margin-top: 0; font-size: 1.1rem; }
  textarea { width: 100%; box-sizing: border-box; }
  .hint { color: #666; font-size: 0.9rem; margin: 0.3rem 0; }
  .error { color: #c25450; }
  .ok { color: #4a9e4f; }
  .actions { margin-top: 0.6rem; }
  label { display: block; margin: 0.4rem 0; }
  code { background: #eef; padding: 0 4px; border-radius: 2px; }
</style>
