<script lang="ts">
  // A single world tile. Displays name + genre + player role + a snippet
  // of the description; the genre-color stripe gives the grid visual
  // texture. `highlighted` is set on the last-played world so resuming
  // is one obvious tap.
  import type { WorldSummary } from '$lib/api';

  let {
    world,
    highlighted = false,
    selected = false,
    onSelect,
  }: {
    world: WorldSummary;
    highlighted?: boolean;
    selected?: boolean;
    onSelect: (id: string) => void;
  } = $props();

  // Stable hue from the world name so each world feels distinct without
  // forcing the world author to pick a color. Simple djb2-ish hash.
  function hueFor(s: string): number {
    let h = 5381;
    for (let i = 0; i < s.length; i++) h = ((h << 5) + h) ^ s.charCodeAt(i);
    return Math.abs(h) % 360;
  }
  let hue = $derived(hueFor(world.name + world.genre));
  let stripeColor = $derived(`hsl(${hue}, 65%, 55%)`);
  let descSnippet = $derived(
    world.description
      ? (world.description.length > 120
          ? world.description.slice(0, 117).trimEnd() + '…'
          : world.description)
      : ''
  );
</script>

<button
  type="button"
  class="card"
  class:selected
  class:highlighted
  onclick={() => onSelect(world.id)}
  style="--stripe: {stripeColor}"
>
  <header>
    <span class="name">{world.name}</span>
    {#if highlighted}
      <span class="badge resume" title="Zuletzt gespielt">▶ Fortsetzen</span>
    {/if}
  </header>
  <div class="meta">
    <span class="genre">{world.genre}</span>
    {#if world.player_role}
      <span class="role">· du bist <strong>{world.player_role}</strong></span>
    {/if}
  </div>
  {#if descSnippet}
    <p class="desc">{descSnippet}</p>
  {/if}
</button>

<style>
  .card {
    text-align: left; cursor: pointer; font: inherit;
    background: var(--surface); color: var(--fg);
    border: 1px solid var(--border); border-radius: 8px;
    padding: 0.85rem 0.95rem 0.9rem; position: relative;
    transition: transform 0.08s ease, border-color 0.12s ease,
                background 0.12s ease;
    display: flex; flex-direction: column; gap: 0.35rem;
    overflow: hidden;
  }
  .card::before {
    content: ""; position: absolute; left: 0; top: 0; bottom: 0;
    width: 4px; background: var(--stripe);
  }
  .card:hover { border-color: var(--stripe); transform: translateY(-1px); }
  .card.selected {
    border-color: var(--stripe);
    box-shadow: 0 0 0 2px color-mix(in srgb, var(--stripe) 30%, transparent);
  }
  .card.highlighted {
    background: color-mix(in srgb, var(--stripe) 8%, var(--surface));
  }
  header {
    display: flex; justify-content: space-between; align-items: baseline;
    gap: 0.5rem;
  }
  .name { font-weight: 600; font-size: 1.05rem; color: var(--fg); }
  .badge.resume {
    background: var(--stripe); color: #10131a;
    padding: 0.1rem 0.5rem; border-radius: 999px;
    font-size: 0.72rem; font-weight: 600; white-space: nowrap;
  }
  .meta {
    color: var(--muted); font-size: 0.85rem; line-height: 1.3;
  }
  .meta .genre {
    text-transform: uppercase; letter-spacing: 0.05em;
    font-size: 0.75rem; color: var(--stripe); font-weight: 600;
  }
  .meta strong { color: var(--fg); font-weight: 600; }
  .desc {
    margin: 0.15rem 0 0; color: var(--muted); font-size: 0.9rem;
    line-height: 1.4;
  }
  @media (max-width: 600px) {
    .card { padding: 0.7rem 0.8rem; }
    .name { font-size: 1rem; }
  }
</style>
