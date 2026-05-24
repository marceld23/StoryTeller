<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import { listWorlds, createSession, openVoiceSocket, type WorldSummary } from '$lib/api';

  type Line = { who: 'narrator' | 'player' | 'system'; text: string };

  let worlds: WorldSummary[] = $state([]);
  let chosenWorld = $state('');
  let threadId = $state('');
  let lines: Line[] = $state([]);
  let connected = $state(false);
  let thinking = $state(false);
  let recording = $state(false);
  let playing = $state(false);
  let error = $state('');

  let capPaused = $state(false);
  let noteInput = $state('');
  let showNote = $state(false);
  // Loading-state surface for the start sequence: createSession's
  // engine.opening() can block ~25–60 s on a fresh world, and even on
  // resume the TTS synthesis of the last narration takes another
  // 5–10 s before audio arrives. Without an explicit indicator the
  // voice page looks frozen after the player hits "Beginnen".
  let starting = $state(false);
  let startStatus = $state('');
  let startElapsed = $state(0);
  let startTick: number | undefined = undefined;
  let openingHeard = $state(false);
  let log = $state('');                       // debug / autoplay-fallback note
  let pendingAudio: HTMLAudioElement | null = $state(null);

  function playPending() {
    if (!pendingAudio) return;
    pendingAudio.play().then(
      () => { log = ''; pendingAudio = null; },
      (e) => { log = `Konnte nicht abspielen: ${e?.message || e}`; });
  }

  let ws: WebSocket | null = null;
  let mediaRecorder: MediaRecorder | null = null;
  let chunks: BlobPart[] = [];
  let stream: MediaStream | null = null;
  let audio: HTMLAudioElement | null = null;
  let waitAudio: HTMLAudioElement | null = null;

  onDestroy(() => cleanup());

  function cleanup() {
    ws?.close();
    mediaRecorder?.stop();
    stream?.getTracks().forEach((t) => t.stop());
  }

  // Browsers expose `navigator.mediaDevices.getUserMedia` ONLY in secure
  // contexts (HTTPS) or when the page is served from localhost. Plain
  // http://<lan-ip>:8090 is intentionally blocked by the browser. We
  // detect that up front and show an actionable error message instead
  // of the cryptic "Cannot read properties of undefined" TypeError.
  let micAvailable = $state(true);
  let secureContextHint = $state('');

  function _checkMicAvailable(): boolean {
    const ok =
      typeof navigator !== 'undefined' &&
      !!navigator.mediaDevices &&
      typeof navigator.mediaDevices.getUserMedia === 'function';
    if (!ok) {
      micAvailable = false;
      const host = typeof window !== 'undefined' ? window.location.hostname : '';
      secureContextHint =
        host && host !== 'localhost' && host !== '127.0.0.1'
          ? `Der Browser blockiert das Mikrofon, weil die Seite über http://${host} (nicht sicher) geladen ist. ` +
            'Sprachmodus funktioniert nur über HTTPS oder über http://localhost. ' +
            'Lösung: Öffne die Seite direkt auf dem Pi (http://localhost:8090/voice) oder richte einen HTTPS-Reverse-Proxy ein.'
          : 'Dieser Browser bietet keinen Mikrofonzugriff. Bitte einen aktuellen Chrome / Firefox / Safari verwenden.';
    }
    return ok;
  }

  onMount(async () => {
    try {
      worlds = await listWorlds();
      if (worlds.length === 1) chosenWorld = worlds[0].id;
    } catch (e) {
      error = String(e);
    }
    _checkMicAvailable();
  });

  function _setStartStatus(label: string) {
    // Same loading session — only update the label; the counter keeps
    // ticking across phases so the player sees one continuous timer
    // instead of three confusing restarts.
    starting = true;
    startStatus = label;
    if (startTick === undefined) {
      startElapsed = 0;
      startTick = window.setInterval(() => (startElapsed += 1), 1000);
    }
  }
  function _stopCounter() {
    starting = false;
    startStatus = '';
    if (startTick !== undefined) {
      window.clearInterval(startTick);
      startTick = undefined;
    }
  }

  async function start() {
    if (!chosenWorld || starting) return;
    error = '';
    lines = [];
    openingHeard = false;
    if (!_checkMicAvailable()) {
      error = secureContextHint;
      return;
    }
    try {
      _setStartStatus('Mikrofon-Zugriff…');
      // mic permission up front
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });

      _setStartStatus('Eröffnung wird vorbereitet (kann ~30 s dauern)…');
      const sess = await createSession(chosenWorld);
      threadId = sess.thread_id;

      _setStartStatus('Verbindung wird hergestellt…');
      ws = openVoiceSocket(threadId, chosenWorld);
      ws.onopen = () => {
        connected = true;
        _setStartStatus('Erzähler liest die Eröffnung vor…');
      };
      ws.onclose = () => {
        connected = false;
        if (!openingHeard) _stopCounter();
      };
      ws.onerror = () => {
        error = 'WebSocket-Fehler';
        _stopCounter();
      };
      ws.onmessage = (ev) => handleMessage(ev);
    } catch (e) {
      error = `Mikrofon/Verbindung: ${e}`;
      _stopCounter();
    }
  }

  function startWaitSound() {
    // Phase-4 cosmetic: browser-side wait-sound under the "thinking"
    // window so the voice player has audible feedback even when no GPIO
    // ambient is connected. We use the same generic_waiting.wav that
    // the Pi plays during world generation; it's small (~290 KB).
    try {
      if (!waitAudio) {
        waitAudio = new Audio('/api/wait_sound');
        waitAudio.loop = true;
        waitAudio.volume = 0.35;
      }
      waitAudio.currentTime = 0;
      waitAudio.play().catch(() => {});
    } catch { /* ignore */ }
  }

  function stopWaitSound() {
    try {
      waitAudio?.pause();
    } catch { /* ignore */ }
  }

  function handleMessage(ev: MessageEvent) {
    if (typeof ev.data === 'string') {
      try {
        const msg = JSON.parse(ev.data);
        if (msg.type === 'thinking') { thinking = true; startWaitSound(); }
        else if (msg.type === 'stt') lines.push({ who: 'player', text: msg.text });
        else if (msg.type === 'narration') {
          thinking = false; stopWaitSound();
          lines.push({ who: 'narrator', text: msg.text });
          // First narration after start = opening arrived → loading
          // indicator can step down. Subsequent narrations don't
          // touch the loading flag.
          if (!openingHeard) { openingHeard = true; _stopCounter(); }
        } else if (msg.type === 'audio_done') { thinking = false; stopWaitSound(); }
        else if (msg.type === 'daily_cap_exceeded') {
          thinking = false; stopWaitSound();
          capPaused = true;
          lines.push({ who: 'system', text: msg.message });
        } else if (msg.type === 'note_saved') {
          lines.push({
            who: 'system',
            text: `Vermerk gespeichert: ${msg.name} (${msg.kind})`
          });
        } else if (msg.type === 'story_ended') {
          ws?.close(); ws = null;
          threadId = ''; lines = [];
        } else if (msg.type === 'error') {
          thinking = false; stopWaitSound();
          error = msg.message;
          lines.push({ who: 'system', text: `Fehler: ${msg.message}` });
        }
      } catch {
        /* ignore */
      }
    } else {
      // binary = WAV audio of the narration
      const blob = new Blob([ev.data], { type: 'audio/wav' });
      const url = URL.createObjectURL(blob);
      audio?.pause();
      audio = new Audio(url);
      audio.onended = () => {
        URL.revokeObjectURL(url);
        playing = false;
      };
      audio.onpause = () => (playing = false);
      audio.onplay = () => (playing = true);
      // Surface autoplay-blocked errors so the player can see why
      // there's no sound — browsers gate autoplay after long async
      // delays (~30 s opening = lost gesture context). Show a one-tap
      // "Audio abspielen" prompt as a fallback.
      audio.play().catch((e) => {
        log = `Audio blockiert (Browser-Autoplay): ${e?.message || e}. `
            + 'Tippe auf "Eröffnung abspielen".';
        pendingAudio = audio;
      });
    }
  }

  // Barge-in: stop the narration playback (the player can then record again).
  function stopPlayback() {
    audio?.pause();
    playing = false;
    // Best-effort: tell the backend (ignored if mid-generation).
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: 'interrupt' }));
    }
  }

  function startRec() {
    if (!stream || recording || thinking) return;
    chunks = [];
    mediaRecorder = new MediaRecorder(stream);
    mediaRecorder.ondataavailable = (e) => {
      if (e.data.size) chunks.push(e.data);
    };
    mediaRecorder.onstop = () => {
      const blob = new Blob(chunks, { type: mediaRecorder?.mimeType || 'audio/webm' });
      if (ws && ws.readyState === WebSocket.OPEN && blob.size > 0) {
        blob.arrayBuffer().then((buf) => ws!.send(buf));
        thinking = true;
      }
    };
    mediaRecorder.start();
    recording = true;
  }

  function stopRec() {
    if (!recording) return;
    mediaRecorder?.stop();
    recording = false;
  }

  function sendNote() {
    const text = noteInput.trim();
    if (!text || !ws || ws.readyState !== WebSocket.OPEN) return;
    ws.send(JSON.stringify({ type: 'note', text }));
    noteInput = '';
    showNote = false;
  }

  function endStory() {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: 'end_story' }));
      setTimeout(() => {
        if (threadId) {
          ws?.close(); ws = null; threadId = ''; lines = [];
        }
      }, 1500);
    } else {
      threadId = ''; lines = [];
    }
  }
</script>

<main>
  <header>
    <a class="brand" href="/" title="StoryTeller">
      <img src="/favicon.png" alt="" />
      <h1>StoryTeller · Sprache</h1>
    </a>
    <a class="mode-link" href="/">Textmodus</a>
  </header>

  {#if error}<p class="error">{error}</p>{/if}

  {#if !micAvailable}
    <div class="mic-warn">
      <strong>Mikrofon-Zugriff blockiert.</strong>
      <p>{secureContextHint}</p>
    </div>
  {/if}

  {#if !threadId}
    <section class="picker">
      <h2>Welt wählen</h2>
      {#if worlds.length === 0}
        <p>Lade Welten…</p>
      {:else}
        <select bind:value={chosenWorld} disabled={starting}>
          <option value="">– bitte wählen –</option>
          {#each worlds as w (w.id)}
            <option value={w.id}>{w.name} ({w.genre})</option>
          {/each}
        </select>
        <button onclick={start} disabled={!chosenWorld || !micAvailable || starting}>
          {starting ? `…lädt (${startElapsed}s)` : 'Beginnen (Mikrofon)'}
        </button>
        {#if starting}
          <div class="loading">
            <span class="spinner"></span>
            <span>{startStatus} <strong>{startElapsed}s</strong></span>
          </div>
        {/if}
      {/if}
    </section>
  {:else}
    {#if starting}
      <div class="loading inline">
        <span class="spinner"></span>
        <span>{startStatus} <strong>{startElapsed}s</strong></span>
      </div>
    {/if}
    {#if log}
      <div class="autoplay-fallback">
        <span>{log}</span>
        {#if pendingAudio}
          <button onclick={playPending}>▶ Eröffnung abspielen</button>
        {/if}
      </div>
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
      {#if thinking}<div class="line system">…</div>{/if}
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
      <button
        class="ptt"
        class:rec={recording}
        onmousedown={startRec}
        onmouseup={stopRec}
        onmouseleave={stopRec}
        ontouchstart={startRec}
        ontouchend={stopRec}
        disabled={!connected || thinking || capPaused}
      >
        {recording ? '● Aufnahme – loslassen zum Senden' : '🎤 Halten zum Sprechen'}
      </button>
      {#if playing}
        <button class="stop" onclick={stopPlayback}>⏹ Stopp</button>
      {/if}
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
  main { max-width: 760px; margin: 0 auto; padding: 1rem;
         display: flex; flex-direction: column;
         min-height: 100vh; min-height: 100dvh;
         box-sizing: border-box; }
  header { display: flex; justify-content: space-between;
           align-items: center; border-bottom: 1px solid var(--border);
           padding-bottom: 0.5rem; gap: 0.6rem; }
  h1 { margin: 0; font-size: 1.4rem; color: #6fc3df; }
  .brand { display: flex; align-items: center; gap: 0.5rem;
           color: inherit; text-decoration: none; }
  .brand img { width: 32px; height: 32px; border-radius: 4px; display: block; }
  .mode-link { color: var(--muted); text-decoration: none; font-size: 0.95rem; }
  header a { color: var(--muted); }
  @media (max-width: 600px) {
    main { padding: 0.7rem; }
    h1 { font-size: 1.15rem; }
    .brand img { width: 28px; height: 28px; }
    .ptt { font-size: 1rem; padding: 0.9rem; }
    .line { max-width: 95%; padding: 0.5rem 0.7rem; font-size: 0.96rem; }
    .picker select { width: 100%; margin-right: 0; }
    .picker button { width: 100%; margin-top: 0.4rem; }
    .side-actions { justify-content: stretch; }
    .side-actions .ghost { flex: 1; }
  }
  .picker { padding: 2rem 0; }
  .picker select { padding: 0.4rem; margin-right: 0.5rem; }
  .picker button { padding: 0.4rem 1rem; background: #6fc3df; color: #10131a; border: none; border-radius: 3px; cursor: pointer; }
  .chat { flex: 1; overflow-y: auto; padding: 1rem 0; display: flex; flex-direction: column; gap: 0.75rem; }
  .line { padding: 0.6rem 0.9rem; border-radius: 6px; max-width: 90%; white-space: pre-wrap; }
  .line.narrator { background: var(--surface); align-self: flex-start; border-left: 3px solid #6fc3df; }
  .line.player { background: var(--surface-2); align-self: flex-end; border-right: 3px solid #b4d273; }
  .line.system { background: transparent; align-self: center; color: var(--muted); font-style: italic; }
  footer { padding-top: 0.5rem; border-top: 1px solid var(--border); }
  .ptt {
    width: 100%; padding: 1rem; font-size: 1.1rem; font-weight: 600;
    background: #b4d273; color: #10131a; border: none; border-radius: 6px; cursor: pointer;
    user-select: none;
  }
  .ptt.rec { background: #e07a7a; color: #fff; }
  .ptt:disabled { background: var(--border); color: var(--muted); cursor: not-allowed; }
  .stop {
    width: 100%; margin-top: 0.5rem; padding: 0.6rem; font-size: 1rem; font-weight: 600;
    background: #e07a7a; color: #fff; border: none; border-radius: 6px; cursor: pointer;
  }
  .error { color: #e07a7a; }
  .mic-warn {
    background: rgba(220, 50, 50, 0.10);
    border-left: 3px solid #c25450;
    padding: 0.6rem 0.8rem; border-radius: 4px;
    margin: 0.6rem 0; color: var(--fg);
  }
  .mic-warn p { margin: 0.3rem 0 0; font-size: 0.9rem; line-height: 1.45; }
  .loading {
    display: flex; align-items: center; gap: 0.55rem;
    background: var(--surface);
    border-left: 3px solid #6fc3df;
    padding: 0.55rem 0.8rem; border-radius: 4px;
    margin: 0.7rem 0; color: var(--fg);
  }
  .loading.inline { font-size: 0.92rem; }
  .loading strong { color: #6fc3df; }
  .spinner {
    display: inline-block; width: 14px; height: 14px;
    border: 2px solid rgba(255,255,255,0.18);
    border-top-color: #6fc3df; border-radius: 50%;
    animation: spin 0.9s linear infinite; flex: 0 0 auto;
  }
  @keyframes spin { to { transform: rotate(360deg); } }
  .autoplay-fallback {
    display: flex; align-items: center; gap: 0.6rem; flex-wrap: wrap;
    background: rgba(255, 200, 0, 0.10);
    border-left: 3px solid #d4a200;
    padding: 0.55rem 0.8rem; border-radius: 4px;
    margin: 0.5rem 0; color: var(--fg); font-size: 0.92rem;
  }
  .autoplay-fallback button {
    background: #6fc3df; color: #10131a; border: none;
    padding: 0.35rem 0.85rem; border-radius: 4px;
    cursor: pointer; font-weight: 600;
  }
  .banner {
    background: var(--surface-2); color: var(--fg);
    border-left: 3px solid #e0a85a; padding: 0.4rem 0.7rem;
    border-radius: 4px; margin: 0.5rem 0;
  }
  .banner.cap { border-left-color: #c25450; }
  .link { background: none; border: none; color: var(--link, #6fc3df);
          cursor: pointer; padding: 0; text-decoration: underline; }
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
  .note-box button {
    padding: 0.35rem 0.8rem; font-size: 0.9rem;
    background: #b4d273; color: #10131a; border: none; border-radius: 3px;
    cursor: pointer;
  }
  .note-box button:disabled { background: var(--border); color: var(--muted); cursor: not-allowed; }
  .note-box .ghost { background: transparent; border: 1px solid var(--border); color: var(--fg); }
  .side-actions { display: flex; gap: 0.5rem; margin-top: 0.4rem;
                   justify-content: flex-end; }
  .side-actions .ghost {
    padding: 0.3rem 0.8rem; font-size: 0.85rem;
    background: transparent; border: 1px solid var(--border);
    color: var(--fg); border-radius: 3px; cursor: pointer;
  }
</style>
