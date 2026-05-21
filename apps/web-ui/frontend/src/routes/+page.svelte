<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import { listWorlds, createSession, openPlaySocket, type WorldSummary } from '$lib/api';

  type ChatLine = { who: 'narrator' | 'player' | 'system'; text: string };

  let worlds: WorldSummary[] = $state([]);
  let chosenWorld: string = $state('');
  let threadId: string = $state('');
  let lines: ChatLine[] = $state([]);
  let input: string = $state('');
  let thinking: boolean = $state(false);
  let connected: boolean = $state(false);
  let error: string = $state('');
  let ws: WebSocket | null = null;

  onMount(async () => {
    try {
      worlds = await listWorlds();
      if (worlds.length === 1) chosenWorld = worlds[0].id;
    } catch (e) {
      error = String(e);
    }
  });

  onDestroy(() => {
    if (ws) ws.close();
  });

  async function startSession() {
    if (!chosenWorld) return;
    error = '';
    lines = [];
    thinking = false;
    try {
      const sess = await createSession(chosenWorld);
      threadId = sess.thread_id;
      lines.push({ who: 'narrator', text: sess.opening });

      ws = openPlaySocket(threadId, chosenWorld);
      ws.onopen = () => { connected = true; };
      ws.onclose = () => { connected = false; };
      ws.onerror = (ev) => { error = `ws error`; };
      ws.onmessage = (ev) => {
        try {
          const msg = JSON.parse(ev.data);
          if (msg.type === 'thinking') {
            thinking = true;
          } else if (msg.type === 'narration') {
            thinking = false;
            // The first narration after connect is the opening repeated by
            // the WS handshake; skip if identical to the last narration we
            // already have.
            const last = lines[lines.length - 1];
            if (!(last && last.who === 'narrator' && last.text === msg.text)) {
              lines.push({ who: 'narrator', text: msg.text });
            }
          } else if (msg.type === 'error') {
            thinking = false;
            error = msg.message;
            lines.push({ who: 'system', text: `Fehler: ${msg.message}` });
          }
        } catch (e) {
          console.error('bad ws message', ev.data);
        }
      };
    } catch (e) {
      error = String(e);
    }
  }

  function send() {
    const text = input.trim();
    if (!text || !ws || ws.readyState !== WebSocket.OPEN) return;
    lines.push({ who: 'player', text });
    input = '';
    ws.send(JSON.stringify({ type: 'turn', text }));
    thinking = true;
  }

  function onKey(e: KeyboardEvent) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  }
</script>

<main>
  <header>
    <h1>StoryTeller</h1>
    {#if threadId}
      <small>session: <code>{threadId}</code></small>
    {:else}
      <a href="/voice">🎤 Sprachmodus</a>
    {/if}
  </header>

  {#if error}
    <p class="error">{error}</p>
  {/if}

  {#if !threadId}
    <section class="picker">
      <h2>Welt wählen</h2>
      {#if worlds.length === 0}
        <p>Lade Welten…</p>
      {:else}
        <select bind:value={chosenWorld}>
          <option value="">– bitte wählen –</option>
          {#each worlds as w (w.id)}
            <option value={w.id}>{w.name} ({w.genre})</option>
          {/each}
        </select>
        <button onclick={startSession} disabled={!chosenWorld}>
          Geschichte beginnen
        </button>
      {/if}
    </section>
  {:else}
    <section class="chat">
      {#each lines as line, i (i)}
        <div class={'line ' + line.who}>{line.text}</div>
      {/each}
      {#if thinking}
        <div class="line system">…erzählt nach…</div>
      {/if}
    </section>

    <footer>
      <textarea
        bind:value={input}
        onkeydown={onKey}
        placeholder="Was tust du?"
        disabled={!connected || thinking}
        rows="2"
      ></textarea>
      <button onclick={send} disabled={!connected || thinking || !input.trim()}>
        Senden
      </button>
    </footer>
  {/if}
</main>

<style>
  :global(html, body) {
    margin: 0;
    padding: 0;
    background: #1a1a1d;
    color: #f1f1f1;
    font-family: system-ui, -apple-system, sans-serif;
    min-height: 100vh;
  }
  main {
    max-width: 760px;
    margin: 0 auto;
    padding: 1rem;
    display: flex;
    flex-direction: column;
    min-height: 100vh;
  }
  header {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    border-bottom: 1px solid #333;
    padding-bottom: 0.5rem;
  }
  h1 { margin: 0; font-size: 1.4rem; color: #6fc3df; }
  small { color: #888; }
  .picker { padding: 2rem 0; }
  .picker select { padding: 0.4rem; margin-right: 0.5rem; }
  .picker button {
    padding: 0.4rem 1rem; background: #6fc3df; color: #111;
    border: none; border-radius: 3px; cursor: pointer;
  }
  .chat {
    flex: 1; overflow-y: auto; padding: 1rem 0;
    display: flex; flex-direction: column; gap: 0.75rem;
  }
  .line { padding: 0.6rem 0.9rem; border-radius: 6px; max-width: 90%; white-space: pre-wrap; }
  .line.narrator { background: #232527; align-self: flex-start; border-left: 3px solid #6fc3df; }
  .line.player { background: #2a3038; align-self: flex-end; border-right: 3px solid #b4d273; }
  .line.system { background: transparent; align-self: center; color: #888; font-style: italic; font-size: 0.85rem; }
  footer { display: flex; gap: 0.5rem; padding-top: 0.5rem; border-top: 1px solid #333; }
  footer textarea {
    flex: 1; padding: 0.5rem; background: #222; color: #eee;
    border: 1px solid #333; border-radius: 3px; resize: vertical;
    font-family: inherit; font-size: 1rem;
  }
  footer button {
    padding: 0 1.2rem; background: #b4d273; color: #111;
    border: none; border-radius: 3px; cursor: pointer; font-weight: 600;
  }
  footer button:disabled { background: #444; color: #888; cursor: not-allowed; }
  .error { color: #e87a7a; }
</style>
