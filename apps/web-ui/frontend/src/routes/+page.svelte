<script lang="ts">
  import { onMount, onDestroy, tick } from 'svelte';
  import {
    listWorlds, createSession, openPlaySocket, fetchReplayUrl,
    type WorldSummary,
  } from '$lib/api';
  import { theme } from '$lib/theme.svelte';
  import WorldCard from '$lib/components/WorldCard.svelte';
  import ChatLine from '$lib/components/ChatLine.svelte';

  type ChatItem = {
    who: 'narrator' | 'player' | 'system';
    text: string;
    audioUrl?: string;        // cached replay-WAV blob URL
    replaying?: boolean;
  };

  let worlds: WorldSummary[] = $state([]);
  let chosenWorld: string = $state('');
  let threadId: string = $state('');
  let lines: ChatItem[] = $state([]);
  let input: string = $state('');
  let thinking: boolean = $state(false);
  let connected: boolean = $state(false);
  let status: 'idle' | 'connected' | 'reconnecting' | 'closed' = $state('idle');
  let error: string = $state('');
  let starting: boolean = $state(false);
  let startingElapsed: number = $state(0);
  let startingTick: number | undefined = undefined;
  let capPaused: boolean = $state(false);
  let capInfo: { usd_today?: number; cap_usd?: number } = $state({});
  let noteInput: string = $state('');
  let showNote: boolean = $state(false);
  let confirmEnd: boolean = $state(false);
  let ws: WebSocket | null = null;
  let closing = false;
  let attempts = 0;

  // Server-side char limit; fetched from /api/health so the counter
  // matches whatever the operator set (web.max_turn_chars).
  let maxTurnChars = $state(2000);

  // Autoscroll bookkeeping — only autoscroll when the player is already
  // near the bottom. Otherwise show a "neue Nachricht ↓"-Pill.
  let chatEl: HTMLElement | undefined = $state();
  let stickToBottom = $state(true);
  let hasUnread = $state(false);

  let chosenWorldObj = $derived(worlds.find((w) => w.id === chosenWorld));
  let lastPlayedId = $state<string>('');

  function savedThread(world: string): string | null {
    try { return localStorage.getItem('st-thread-' + world); } catch { return null; }
  }
  function rememberThread(world: string, thread: string) {
    try {
      localStorage.setItem('st-thread-' + world, thread);
      localStorage.setItem('st-last-played', world);
    } catch { /* ignore */ }
  }
  let resumable = $derived(chosenWorld ? savedThread(chosenWorld) : null);

  onMount(async () => {
    try {
      worlds = await listWorlds();
      let last: string | null = null;
      try { last = localStorage.getItem('st-last-world'); } catch { /* ignore */ }
      let lp: string | null = null;
      try { lp = localStorage.getItem('st-last-played'); } catch { /* ignore */ }
      lastPlayedId = lp || '';
      if (last && worlds.some((w) => w.id === last)) {
        chosenWorld = last;
        try { localStorage.removeItem('st-last-world'); } catch { /* ignore */ }
      } else if (lp && worlds.some((w) => w.id === lp)) {
        chosenWorld = lp;
      } else if (worlds.length === 1) {
        chosenWorld = worlds[0].id;
      }
    } catch (e) {
      error = friendlyError(e);
    }
    try {
      const r = await fetch('/api/health');
      if (r.ok) {
        const j = await r.json();
        if (typeof j?.limits?.max_turn_chars === 'number')
          maxTurnChars = j.limits.max_turn_chars;
      }
    } catch { /* keep fallback */ }
  });

  onDestroy(() => {
    closing = true;
    ws?.close();
    for (const l of lines) if (l.audioUrl) URL.revokeObjectURL(l.audioUrl);
  });

  // --- error formatting ---------------------------------------------------
  // The backend may forward Python exception reprs ("OpenAIError(...)",
  // "ConnectionRefused 502"). The player has no use for those — strip
  // anything that looks like a stack/repr and show a one-liner instead.
  function friendlyError(e: unknown): string {
    const raw = e instanceof Error ? e.message : String(e);
    if (/(401|403|auth)/i.test(raw)) return 'Zugriff verweigert.';
    if (/(429|rate.?limit)/i.test(raw))
      return 'Der Erzähler ist gerade überlastet. Bitte gleich nochmal versuchen.';
    if (/(timeout|timed out)/i.test(raw))
      return 'Der Erzähler antwortet gerade nicht. Bitte erneut versuchen.';
    if (/connect/i.test(raw))
      return 'Verbindung zum Erzähler verloren.';
    // Hide raw Python reprs from the player.
    if (raw.includes('Error(') || raw.length > 140)
      return 'Es gab eine Störung. Bitte erneut versuchen.';
    return raw;
  }

  // --- WS -----------------------------------------------------------------
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
          const last = lines[lines.length - 1];
          if (!(last && last.who === 'narrator' && last.text === msg.text)) {
            pushLine({ who: 'narrator', text: msg.text });
          }
        } else if (msg.type === 'daily_cap_exceeded') {
          thinking = false;
          capPaused = true;
          capInfo = { usd_today: msg.usd_today, cap_usd: msg.cap_usd };
          pushLine({ who: 'system', text: msg.message });
        } else if (msg.type === 'note_saved') {
          pushLine({
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
          error = friendlyError(msg.message);
          // No second copy in the chat — one error indicator is enough.
        }
      } catch {
        console.error('bad ws message', ev.data);
      }
    };
  }

  function pushLine(l: ChatItem) {
    lines.push(l);
    queueScroll();
  }

  function queueScroll() {
    // After Svelte renders the new line, either scroll to bottom (player
    // was at bottom = engaged), or set the "new message" flag.
    tick().then(() => {
      if (!chatEl) return;
      if (stickToBottom) {
        chatEl.scrollTop = chatEl.scrollHeight;
        hasUnread = false;
      } else {
        hasUnread = true;
      }
    });
  }

  function onChatScroll() {
    if (!chatEl) return;
    const dist = chatEl.scrollHeight - chatEl.scrollTop - chatEl.clientHeight;
    stickToBottom = dist < 80;
    if (stickToBottom) hasUnread = false;
  }

  function scrollToBottom() {
    if (!chatEl) return;
    chatEl.scrollTop = chatEl.scrollHeight;
    stickToBottom = true;
    hasUnread = false;
  }

  function sendNote() {
    const text = noteInput.trim();
    if (!text || !ws || ws.readyState !== WebSocket.OPEN) return;
    ws.send(JSON.stringify({ type: 'note', text }));
    noteInput = '';
    showNote = false;
  }

  function endStoryRequested() { confirmEnd = true; }
  function endStoryCancel()    { confirmEnd = false; }
  function endStoryConfirm() {
    confirmEnd = false;
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      closing = true;
      threadId = '';
      lines = [];
      return;
    }
    ws.send(JSON.stringify({ type: 'end_story' }));
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
    if (!chosenWorld || starting) return;
    error = ''; lines = []; thinking = false; closing = false; attempts = 0;
    capPaused = false; capInfo = {};
    starting = true;
    startingElapsed = 0;
    startingTick = window.setInterval(() => (startingElapsed += 1), 1000);
    try {
      if (resume && savedThread(chosenWorld)) {
        threadId = savedThread(chosenWorld) as string;
      } else {
        const sess = await createSession(chosenWorld);
        threadId = sess.thread_id;
        pushLine({ who: 'narrator', text: sess.opening });
      }
      rememberThread(chosenWorld, threadId);
      stickToBottom = true;
      connect();
    } catch (e) {
      error = friendlyError(e);
    } finally {
      starting = false;
      if (startingTick !== undefined) {
        window.clearInterval(startingTick);
        startingTick = undefined;
      }
    }
  }

  // Player input: Enter sends (Shift+Enter = newline). Eingabe bleibt
  // während `thinking` aktiv — der Spieler kann seinen nächsten Schritt
  // schon tippen während die aktuelle Antwort generiert wird; nur der
  // Senden-Knopf bleibt gated.
  let inputOverflow = $derived(input.length > maxTurnChars);
  function send() {
    const text = input.trim();
    if (!text || thinking || inputOverflow || !ws
        || ws.readyState !== WebSocket.OPEN) return;
    pushLine({ who: 'player', text });
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

  // ---- on-demand TTS for a single narrator line ("🔊 anhören") ---------
  let activeAudio: HTMLAudioElement | null = null;
  async function playLine(idx: number) {
    const line = lines[idx];
    if (!line || line.who !== 'narrator') return;
    // Stop anything currently playing — at most one line plays at a time.
    if (activeAudio) {
      try { activeAudio.pause(); } catch { /* ignore */ }
      activeAudio = null;
    }
    // Mark this line as loading. Subsequent clicks reuse the cached URL.
    if (!line.audioUrl) {
      line.replaying = true;
      try {
        line.audioUrl = await fetchReplayUrl(threadId, chosenWorld);
      } catch (e) {
        error = friendlyError(e);
        line.replaying = false;
        return;
      }
    }
    activeAudio = new Audio(line.audioUrl);
    activeAudio.onended = () => { if (line) line.replaying = false; };
    activeAudio.onpause  = () => { if (line) line.replaying = false; };
    line.replaying = true;
    activeAudio.play().catch(() => { line.replaying = false; });
  }
</script>

<main class="app-main">
  <header class="app-header">
    <a class="brand" href="/" title="StoryTeller">
      <img src="/favicon.png" alt="" />
      <h1>StoryTeller</h1>
    </a>
    <div class="header-actions">
      {#if threadId && chosenWorldObj}
        <span class="session-label">
          <strong>{chosenWorldObj.name}</strong>
          <span class="hint small">· {chosenWorldObj.genre}</span>
        </span>
      {:else}
        <a class="mode-link" href="/voice">🎤 Sprachmodus</a>
      {/if}
      <button class="icon-btn" onclick={() => theme.toggle()}
              title="Hell/Dunkel umschalten" aria-label="Theme">
        {theme.value === 'light' ? '🌙' : '☀️'}
      </button>
    </div>
  </header>

  {#if error}
    <p class="banner warn"><span>⚠ {error}</span>
      <button class="link" onclick={() => (error = '')}>schließen</button>
    </p>
  {/if}

  {#if !threadId}
    <section class="picker">
      <h2>Welt wählen</h2>
      {#if worlds.length === 0}
        <p>Lade Welten…</p>
      {:else}
        <div class="cards">
          {#each worlds as w (w.id)}
            <WorldCard world={w}
                       selected={chosenWorld === w.id}
                       highlighted={lastPlayedId === w.id}
                       onSelect={(id) => (chosenWorld = id)} />
          {/each}
        </div>
        <div class="pick-actions">
          {#if resumable}
            <button class="primary" onclick={() => startSession(true)}
                    disabled={!chosenWorld || starting}>
              {starting ? `…lade… (${startingElapsed}s)` : '▶ Fortsetzen'}
            </button>
            <button class="ghost" onclick={() => startSession(false)}
                    disabled={!chosenWorld || starting}>
              Neu beginnen
            </button>
          {:else}
            <button class="primary" onclick={() => startSession(false)}
                    disabled={!chosenWorld || starting}>
              {starting ? `…lade Geschichte… (${startingElapsed}s)` : 'Geschichte beginnen'}
            </button>
          {/if}
        </div>
        {#if starting}
          <div class="loading">
            <span class="spinner"></span>
            <span>Der Erzähler bereitet die Eröffnung vor… <strong>{startingElapsed}s</strong></span>
          </div>
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
        <span>⛔ Tagesbudget erreicht
          {#if capInfo.usd_today != null && capInfo.cap_usd != null}
            ({capInfo.usd_today.toFixed(2)} / {capInfo.cap_usd.toFixed(2)} USD)
          {/if}. Spielstand ist gespeichert; der Tag setzt sich um Mitternacht
          (UTC) zurück, ein Erwachsener kann es auch früher freischalten.
        </span>
        <button class="link" onclick={endStoryRequested}>Zur Welt-Auswahl</button>
      </p>
    {/if}
    <section class="chat" bind:this={chatEl} onscroll={onChatScroll}>
      {#each lines as line, i (i)}
        <ChatLine who={line.who} text={line.text}
                  onReplay={line.who === 'narrator' && i === lines.length - 1
                            ? () => playLine(i) : null}
                  replaying={!!line.replaying} />
      {/each}
      {#if thinking}
        <div class="line system thinking">
          <span class="spinner spinner-inline"></span>
          <span>der Erzähler überlegt…</span>
        </div>
      {/if}
    </section>

    {#if hasUnread}
      <button class="new-pill" onclick={scrollToBottom}>
        neue Antwort ↓
      </button>
    {/if}

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

    {#if confirmEnd}
      <section class="confirm-box">
        <span>Geschichte beenden? Spielstand bleibt erhalten — du kannst
              jederzeit fortsetzen.</span>
        <div class="row">
          <button class="danger" onclick={endStoryConfirm}>Ja, beenden</button>
          <button class="ghost" onclick={endStoryCancel}>Abbrechen</button>
        </div>
      </section>
    {/if}

    <footer class="composer">
      <textarea
        bind:value={input}
        onkeydown={onKey}
        placeholder="Was tust du? (Enter zum Senden, Shift+Enter für neue Zeile)"
        disabled={!connected || capPaused}
        rows="2"
      ></textarea>
      <div class="composer-side">
        <div class="char-counter" class:over={inputOverflow}
             title="Zeichen-Limit pro Zug">
          {input.length}/{maxTurnChars}
        </div>
        <button class="primary send" onclick={send}
                disabled={!connected || thinking || !input.trim()
                          || inputOverflow || capPaused}>
          {thinking ? '…' : 'Senden'}
        </button>
      </div>
    </footer>
    <div class="side-actions">
      <button class="ghost" onclick={() => { showNote = !showNote; }}>
        {showNote ? 'Notiz schließen' : '+ Notiz'}
      </button>
      <button class="ghost" onclick={endStoryRequested}>Geschichte beenden</button>
    </div>
  {/if}
</main>

<style>
  .picker { padding: 1.4rem 0; }
  .picker h2 { margin: 0 0 0.7rem; font-size: 1.2rem; }
  .cards {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
    gap: 0.7rem;
    margin-bottom: 1rem;
  }
  .pick-actions {
    display: flex; gap: 0.5rem; flex-wrap: wrap; margin-bottom: 0.5rem;
  }
  .pick-actions .primary {
    padding: 0.55rem 1.1rem; background: #6fc3df; color: #10131a;
    border: none; border-radius: 4px; cursor: pointer; font-weight: 600;
  }
  .pick-actions .primary:disabled {
    background: var(--border); color: var(--muted); cursor: not-allowed;
  }
  .pick-actions .ghost {
    padding: 0.55rem 1rem; background: transparent;
    border: 1px solid var(--border); color: var(--fg); border-radius: 4px;
    cursor: pointer;
  }
  .chat {
    flex: 1; overflow-y: auto; padding: 1rem 0;
    display: flex; flex-direction: column; gap: 0.65rem;
    scroll-behavior: smooth;
  }
  .line.system.thinking {
    display: inline-flex; align-items: center; gap: 0.35rem;
    background: transparent; align-self: center;
    color: var(--muted); font-style: italic; font-size: 0.9rem;
  }
  .new-pill {
    position: sticky; bottom: 4.5rem; align-self: center;
    background: #6fc3df; color: #10131a; border: none;
    border-radius: 999px; padding: 0.3rem 0.85rem; cursor: pointer;
    font-weight: 600; font-size: 0.85rem;
    box-shadow: 0 2px 8px rgba(0,0,0,0.25);
  }
  .composer {
    display: flex; gap: 0.5rem; padding-top: 0.5rem;
    border-top: 1px solid var(--border);
    align-items: flex-end;
  }
  .composer textarea {
    flex: 1; padding: 0.5rem; background: var(--input-bg); color: var(--fg);
    border: 1px solid var(--border); border-radius: 4px; resize: vertical;
    font-family: inherit; font-size: 1rem; min-height: 2.6em;
  }
  .composer-side {
    display: flex; flex-direction: column; align-items: flex-end;
    gap: 0.25rem; min-width: 5.5rem;
  }
  .char-counter {
    font-size: 0.74rem; color: var(--muted);
    font-variant-numeric: tabular-nums;
  }
  .char-counter.over { color: #c25450; font-weight: 600; }
  .send {
    padding: 0.45rem 1rem; background: #b4d273; color: #10131a;
    border: none; border-radius: 4px; cursor: pointer; font-weight: 600;
  }
  .send:disabled { background: var(--border); color: var(--muted); cursor: not-allowed; }
  .confirm-box {
    background: rgba(220, 50, 50, 0.10);
    border-left: 3px solid #c25450;
    padding: 0.55rem 0.8rem; border-radius: 4px;
    margin-top: 0.5rem; display: flex; flex-direction: column; gap: 0.4rem;
    font-size: 0.92rem;
  }
  .confirm-box .row { display: flex; gap: 0.4rem; }
  .confirm-box .danger {
    background: #c25450; color: #fff; border: none;
    padding: 0.35rem 0.85rem; border-radius: 3px; cursor: pointer;
  }
  .confirm-box .ghost {
    background: transparent; border: 1px solid var(--border);
    color: var(--fg); padding: 0.35rem 0.85rem; border-radius: 3px;
    cursor: pointer;
  }
  @media (max-width: 600px) {
    .cards { grid-template-columns: 1fr; }
    .composer { flex-direction: column; align-items: stretch; }
    .composer textarea { width: 100%; box-sizing: border-box; font-size: 1rem; }
    .composer-side { flex-direction: row; justify-content: space-between;
                      align-items: center; min-width: 0; }
    .composer-side .send { flex: 1; padding: 0.7rem; }
    .pick-actions { flex-direction: column; }
    .pick-actions .primary, .pick-actions .ghost { width: 100%; }
  }
</style>
