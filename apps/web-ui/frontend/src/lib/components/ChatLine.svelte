<script lang="ts">
  // One chat bubble. `who` controls alignment + color; `text` is the
  // content. `onReplay` (optional) shows a little 🔊 button on narrator
  // lines so text-mode players can opt-in to hear the line spoken.
  // Voice mode reuses the same component, just without the button.
  type Who = 'narrator' | 'player' | 'system';
  let {
    who,
    text,
    onReplay = null,
    replaying = false,
  }: {
    who: Who;
    text: string;
    onReplay?: (() => void) | null;
    replaying?: boolean;
  } = $props();
</script>

<div class="line {who}">
  <div class="text">{text}</div>
  {#if who === 'narrator' && onReplay}
    <button class="replay" onclick={onReplay} disabled={replaying}
            title="Erzähler vorlesen lassen" aria-label="Vorlesen">
      {replaying ? '⏳' : '🔊'}
    </button>
  {/if}
</div>

<style>
  .line {
    padding: 0.7rem 0.95rem; border-radius: 8px; max-width: 90%;
    white-space: pre-wrap; position: relative;
    line-height: 1.5;
  }
  .line .text { word-break: break-word; }
  .line.narrator {
    background: var(--surface);
    align-self: flex-start;
    border-left: 3px solid #6fc3df;
    font-size: 1.05rem;
  }
  .line.player {
    background: var(--surface-2);
    align-self: flex-end;
    border-right: 3px solid #b4d273;
    font-size: 0.95rem;
    color: var(--muted);
  }
  .line.system {
    background: transparent;
    align-self: center;
    color: var(--muted);
    font-style: italic;
    font-size: 0.85rem;
    text-align: center;
    padding: 0.3rem 0.6rem;
  }
  .replay {
    position: absolute; bottom: 0.25rem; right: 0.35rem;
    background: transparent; border: none; color: var(--muted);
    cursor: pointer; padding: 0.15rem 0.35rem; border-radius: 4px;
    font-size: 0.95rem; opacity: 0.55; transition: opacity 0.15s;
  }
  .line.narrator:hover .replay { opacity: 1; }
  .replay:hover { background: var(--surface-2); color: var(--fg); }
  .replay:disabled { cursor: wait; opacity: 0.4; }
  @media (max-width: 600px) {
    .line { max-width: 95%; padding: 0.55rem 0.75rem; }
    .line.narrator { font-size: 0.98rem; }
    .replay { opacity: 0.85; }   /* mobile has no hover; show it */
  }
</style>
