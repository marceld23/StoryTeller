<script lang="ts">
  import { suggestPiece } from '$lib/api';
  import { emptyPiece, type KindSpec } from '$lib/worldFields';

  let {
    spec,
    items = $bindable(),
    worldId
  }: {
    spec: KindSpec;
    items: Record<string, unknown>[];
    worldId: string;
  } = $props();

  let suggesting = $state(false);
  let suggestPrompt = $state('');
  let error = $state('');

  function add() {
    items = [...items, emptyPiece(spec)];
  }

  function remove(i: number) {
    items = items.filter((_, idx) => idx !== i);
  }

  async function suggest() {
    error = '';
    suggesting = true;
    try {
      const { piece } = await suggestPiece(worldId, spec.suggestKind, suggestPrompt);
      // ensure all fields exist
      const full = { ...emptyPiece(spec), ...piece };
      items = [...items, full];
      suggestPrompt = '';
    } catch (e) {
      error = String(e);
    } finally {
      suggesting = false;
    }
  }

  // tags <-> comma string
  function tagsToStr(v: unknown): string {
    return Array.isArray(v) ? v.join(', ') : String(v ?? '');
  }
  function strToTags(s: string): string[] {
    return s.split(',').map((t) => t.trim()).filter(Boolean);
  }
</script>

<section>
  <header>
    <h3>{spec.label} <span class="count">({items.length})</span></h3>
    <div class="suggest">
      <input
        bind:value={suggestPrompt}
        placeholder="Vorschlag-Hinweis (optional)"
        disabled={suggesting}
      />
      <button onclick={suggest} disabled={suggesting}>
        {suggesting ? '✨…' : '✨ Vorschlag'}
      </button>
      <button onclick={add}>+ leer</button>
    </div>
  </header>

  {#if error}<p class="error">{error}</p>{/if}

  {#each items as item, i (i)}
    <div class="card">
      <div class="card-head">
        <strong>{(item[spec.titleKey] as string) || '(neu)'}</strong>
        <button class="danger" onclick={() => remove(i)}>entfernen</button>
      </div>
      {#each spec.fields as f (f.key)}
        <label>
          <span>{f.label}</span>
          {#if f.type === 'textarea'}
            <textarea bind:value={item[f.key]} rows="5"></textarea>
          {:else if f.type === 'tags'}
            <input
              value={tagsToStr(item[f.key])}
              oninput={(e) => (item[f.key] = strToTags((e.target as HTMLInputElement).value))}
              placeholder="komma, getrennt"
            />
          {:else if f.type === 'select'}
            <select bind:value={item[f.key]}>
              {#each (f.options ?? []) as opt (opt.value)}
                <option value={opt.value}>{opt.label}</option>
              {/each}
            </select>
          {:else}
            <input bind:value={item[f.key]} />
          {/if}
        </label>
      {/each}
    </div>
  {/each}
</section>

<style>
  section { background: var(--surface); border-radius: 5px; padding: 1rem; margin-bottom: 1.2rem; }
  header { display: flex; justify-content: space-between; align-items: center; gap: 1rem; flex-wrap: wrap; }
  h3 { margin: 0; font-size: 1.05rem; }
  .count { color: var(--muted); font-weight: normal; }
  .suggest { display: flex; gap: 0.4rem; align-items: center; }
  .suggest input { width: 220px; }
  .card { border: 1px solid var(--border); border-radius: 4px; padding: 0.7rem; margin-top: 0.7rem; }
  .card-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.4rem; }
  label { display: block; margin: 0.4rem 0; }
  label span { display: block; font-size: 0.8rem; color: var(--muted); margin-bottom: 0.15rem; }
  label input, label textarea { width: 100%; box-sizing: border-box; }
  label textarea { min-height: 5em; line-height: 1.5; resize: vertical;
                   font-family: inherit; }
  .error { color: #c25450; }
</style>
