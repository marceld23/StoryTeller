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
  let status: 'idle' | 'connected' | 'reconnecting' | 'closed' = $state('idle');
  let error: string = $state('');
  let capPaused: boolean = $state(false);  // daily cost cap reached
  let noteInput: string = $state('');
  let showNote: boolean = $state(false);
  let ws: WebSocket | null = null;
  let closing = false;          // user navigated away -> don't reconnect
  let attempts = 0;             // reconnect backoff counter

  // A previously-started session for the chosen world (resume offer).
  let resumable = $derived(chosenWorld ? savedThread(chosenWorld) : null);

  function savedThread(world: string): string | null {
    try { return localStorage.getItem('st-thread-' + world); } catch { return null; }
  }
  function rememberThread(world: string, thread: string) {
    try { localStorage.setItem('st-thread-' + world, thread); } catch { /* ignore */ }
  }

  onMount(async () => {
    try {
      worlds = await listWorlds();
      // Auto-select: a freshly-generated world (set in /create) wins,
      // otherwise pre-select if there's only one world to pick from.
      let last: string | null = null;
      try { last = localStorage.getItem('st-last-world'); } catch { /* ignore */ }
      if (last && worlds.some((w) => w.id === last)) {
        chosenWorld = last;
        try { localStorage.removeItem('st-last-world'); } catch { /* ignore */ }
      } else if (worlds.length === 1) {
        chosenWorld = worlds[0].id;
      }
    } catch (e) {
      error = String(e);
    }
  });

  onDestroy(() => {
    closing = true;
    ws?.close();
  });

  function connect() {
    ws = openPlaySocket(threadId, chosenWorld);
    ws.onopen = () => { connected = true; status = 'connected'; attempts = 0; };
    ws.onerror = () => { /* close handler drives reconnect */ };
    ws.onclose = () => {
      connected = false;
      if (closing) return;
      if (attempts >= 6) { status = 'closed'; return; }
      status = 'reconnecting';
      const delay = Math.min(1000 * 2 ** attempts, 8000);
      attempts += 1;
      setTimeout(() => { if (!closing) connect(); }, delay);
    };
    ws.onmessage = (ev) => {
      try {
        const msg = JSON.parse(ev.data);
        if (msg.type === 'thinking') {
          thinking = true;
        } else if (msg.type === 'narration') {
          thinking = false;
          // Skip the narration echoed on (re)connect if we already have it.
          const last = lines[lines.length - 1];
          if (!(last && last.who === 'narrator' && last.text === msg.text)) {
            lines.push({ who: 'narrator', text: msg.text });
          }
        } else if (msg.type === 'daily_cap_exceeded') {
          thinking = false;
          capPaused = true;
          lines.push({ who: 'system', text: msg.message });
        } else if (msg.type === 'note_saved') {
          lines.push({
            who: 'system',
            text: `Vermerk gespeichert: ${msg.name} (${msg.kind})`
          });
        } else if (msg.type === 'story_ended') {
          // Server confirmed story end — drop back to the world picker.
          closing = true;
          ws?.close();
          ws = null;
          threadId = '';
          lines = [];
        } else if (msg.type === 'error') {
          thinking = false;
          error = msg.message;
          lines.push({ who: 'system', text: `Fehler: ${msg.message}` });
        }
      } catch {
        console.error('bad ws message', ev.data);
      }
    };
  }

  function sendNote() {
    const text = noteInput.trim();
    if (!text || !ws || ws.readyState !== WebSocket.OPEN) return;
    ws.send(JSON.stringify({ type: 'note', text }));
    noteInput = '';
    showNote = false;
  }

  function endStory() {
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      // Connection already down — just drop client state.
      closing = true;
      threadId = '';
      lines = [];
      return;
    }
    ws.send(JSON.stringify({ type: 'end_story' }));
    // The server replies with {type: 'story_ended'} which the handler
    // above picks up; if that never comes, give it ~1 s and bail out.
    setTimeout(() => {
      if (threadId) {
        closing = true; ws?.close(); ws = null; threadId = ''; lines = [];
      }
    }, 1500);
  }

  function reconnectNow() {
    attempts = 0; closing = false; status = 'reconnecting'; connect();
  }

  async function startSession(resume: boolean) {
    if (!chosenWorld) return;
    error = ''; lines = []; thinking = false; closing = false; attempts = 0;
    capPaused = false;
    try {
      if (resume && savedThread(chosenWorld)) {
        // Resume: reuse the thread; the server replays the last narration.
        threadId = savedThread(chosenWorld) as string;
      } else {
        const sess = await createSession(chosenWorld);
        threadId = sess.thread_id;
        lines.push({ who: 'narrator', text: sess.opening });
      }
      rememberThread(chosenWorld, threadId);
      connect();
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
        {#if resumable}
          <button onclick={() => startSession(true)}>Fortsetzen</button>
          <button class="ghost" onclick={() => startSession(false)}>Neu beginnen</button>
        {:else}
          <button onclick={() => startSession(false)} disabled={!chosenWorld}>
            Geschichte beginnen
          </button>
        {/if}
      {/if}
      <p class="hint">
        Du willst eine neue Welt aus deinem eigenen Brief generieren?
        <a class="link" href="/create">Neue Welt erstellen</a>.
      </p>
    </section>
  {:else}
    {#if status === 'reconnecting'}
      <p class="banner">Verbindung verloren – verbinde neu…</p>
    {:else if status === 'closed'}
      <p class="banner">Verbindung getrennt.
        <button class="link" onclick={reconnectNow}>Neu verbinden</button>
      </p>
    {/if}
    {#if capPaused}
      <p class="banner cap">
        ⛔ Tagesbudget erreicht. Spielstand ist gespeichert.
        <button class="link" onclick={endStory}>Zurück zur Welt-Auswahl</button>
      </p>
    {/if}
    <section class="chat">
      {#each lines as line, i (i)}
        <div class={'line ' + line.who}>{line.text}</div>
      {/each}
      {#if thinking}
        <div class="line system">…erzählt nach…</div>
      {/if}
    </section>

    {#if showNote}
      <section class="note-box">
        <label>
          <span class="lbl">Vermerken (wird zur Welt hinzugefügt):</span>
          <textarea bind:value={noteInput} rows="2"
                    placeholder="z. B. Otkar ist ein blinder Bibliothekar."></textarea>
        </label>
        <div class="row">
          <button onclick={sendNote} disabled={!noteInput.trim() || capPaused}>
            Notiz speichern
          </button>
          <button class="ghost" onclick={() => { showNote = false; noteInput = ''; }}>
            Abbrechen
          </button>
        </div>
      </section>
    {/if}

    <footer>
      <textarea
        bind:value={input}
        onkeydown={onKey}
        placeholder="Was tust du?"
        disabled={!connected || thinking || capPaused}
        rows="2"
      ></textarea>
      <button onclick={send} disabled={!connected || thinking || !input.trim() || capPaused}>
        Senden
      </button>
    </footer>
    <div class="side-actions">
      <button class="ghost" onclick={() => { showNote = !showNote; }}>
        {showNote ? 'Notiz schließen' : '+ Notiz'}
      </button>
      <button class="ghost" onclick={endStory}>Geschichte beenden</button>
    </div>
  {/if}
</main>

<style>
  main {
    max-width: 760px;
    margin: 0 auto;
    padding: 1rem;
    display: flex;
    flex-direction: column;
    min-height: 100vh;
  }
  .banner {
    background: var(--surface-2); color: var(--fg);
    border-left: 3px solid #e0a85a; padding: 0.4rem 0.7rem; border-radius: 4px;
  }
  .banner.cap { border-left-color: #c25450; }
  .hint { color: var(--muted); font-size: 0.9rem; }
  .note-box {
    background: var(--surface); border: 1px solid var(--border);
    border-radius: 4px; padding: 0.6rem; margin-top: 0.6rem;
  }
  .note-box .lbl { display: block; font-size: 0.85rem;
                    color: var(--muted); margin-bottom: 0.2rem; }
  .note-box textarea {
    width: 100%; box-sizing: border-box; padding: 0.4rem;
    background: var(--input-bg); color: var(--fg);
    border: 1px solid var(--border); border-radius: 3px;
    font-family: inherit; font-size: 0.95rem; resize: vertical;
  }
  .note-box .row { display: flex; gap: 0.4rem; margin-top: 0.4rem; }
  .side-actions { display: flex; gap: 0.5rem; margin-top: 0.4rem;
                   justify-content: flex-end; }
  .side-actions .ghost {
    padding: 0.3rem 0.8rem; font-size: 0.85rem;
  }
  .ghost { background: transparent; border: 1px solid var(--border); color: var(--fg); }
  .link { background: none; border: none; color: var(--link); cursor: pointer; padding: 0; text-decoration: underline; }
  header {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    border-bottom: 1px solid var(--border);
    padding-bottom: 0.5rem;
  }
  h1 { margin: 0; font-size: 1.4rem; color: #6fc3df; }
  small { color: var(--muted); }
  .picker { padding: 2rem 0; }
  .picker select { padding: 0.4rem; margin-right: 0.5rem; }
  .picker button {
    padding: 0.4rem 1rem; background: #6fc3df; color: #10131a;
    border: none; border-radius: 3px; cursor: pointer;
  }
  .chat {
    flex: 1; overflow-y: auto; padding: 1rem 0;
    display: flex; flex-direction: column; gap: 0.75rem;
  }
  .line { padding: 0.6rem 0.9rem; border-radius: 6px; max-width: 90%; white-space: pre-wrap; }
  .line.narrator { background: var(--surface); align-self: flex-start; border-left: 3px solid #6fc3df; }
  .line.player { background: var(--surface-2); align-self: flex-end; border-right: 3px solid #b4d273; }
  .line.system { background: transparent; align-self: center; color: var(--muted); font-style: italic; font-size: 0.85rem; }
  footer { display: flex; gap: 0.5rem; padding-top: 0.5rem; border-top: 1px solid var(--border); }
  footer textarea {
    flex: 1; padding: 0.5rem; background: var(--input-bg); color: var(--fg);
    border: 1px solid var(--border); border-radius: 3px; resize: vertical;
    font-family: inherit; font-size: 1rem;
  }
  footer button {
    padding: 0 1.2rem; background: #b4d273; color: #10131a;
    border: none; border-radius: 3px; cursor: pointer; font-weight: 600;
  }
  footer button:disabled { background: var(--border); color: var(--muted); cursor: not-allowed; }
  .error { color: #e07a7a; }
</style>
