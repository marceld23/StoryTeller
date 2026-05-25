<script lang="ts">
  import { onMount, onDestroy, tick } from 'svelte';
  import {
    listWorlds, createSession, openVoiceSocket, fetchReplayUrl,
    type WorldSummary,
  } from '$lib/api';
  import { theme } from '$lib/theme';
  import WorldCard from '$lib/components/WorldCard.svelte';
  import ChatLine from '$lib/components/ChatLine.svelte';
  import MicMeter from '$lib/components/MicMeter.svelte';

  type Line = { who: 'narrator' | 'player' | 'system'; text: string };

  let worlds: WorldSummary[] = $state([]);
  let chosenWorld = $state('');
  let threadId = $state('');
  let lines: Line[] = $state([]);
  let connected = $state(false);
  let thinking = $state(false);
  let recording = $state(false);
  let playing = $state(false);
  let paused = $state(false);
  let error = $state('');
  let lastPlayedId = $state('');

  let capPaused = $state(false);
  let capInfo: { usd_today?: number; cap_usd?: number } = $state({});
  let noteInput = $state('');
  let showNote = $state(false);
  let confirmEnd = $state(false);

  let starting = $state(false);
  let startStatus = $state('');
  let startElapsed = $state(0);
  let startTick: number | undefined = undefined;
  let openingHeard = $state(false);
  let log = $state('');
  let pendingAudio: HTMLAudioElement | null = $state(null);

  // Recording timer (in seconds) — shown inside the PTT button so
  // the player has feedback on how long they've been holding the floor.
  let recElapsed = $state(0);
  let recTick: number | undefined = undefined;

  // Wait-sound preference, persisted.
  let waitSoundEnabled = $state(true);
  try {
    const v = localStorage.getItem('st-wait-sound');
    if (v === 'off') waitSoundEnabled = false;
  } catch { /* ignore */ }
  function toggleWaitSound() {
    waitSoundEnabled = !waitSoundEnabled;
    try { localStorage.setItem('st-wait-sound',
                               waitSoundEnabled ? 'on' : 'off'); } catch { /* */ }
    if (!waitSoundEnabled) stopWaitSound();
  }

  function playPending() {
    if (!pendingAudio) return;
    pendingAudio.play().then(
      () => { log = ''; pendingAudio = null; },
      (e) => { log = `Konnte nicht abspielen: ${e?.message || e}`; });
  }

  // --- WS / audio refs ---------------------------------------------------
  let ws: WebSocket | null = null;
  let mediaRecorder: MediaRecorder | null = null;
  let chunks: BlobPart[] = [];
  let stream: MediaStream | null = $state(null);
  let audio: HTMLAudioElement | null = null;
  let lastAudioUrl: string | null = null;
  let waitAudio: HTMLAudioElement | null = null;

  // Autoscroll + new-message pill — same UX as the text route.
  let chatEl: HTMLElement | undefined = $state();
  let stickToBottom = $state(true);
  let hasUnread = $state(false);

  let chosenWorldObj = $derived(worlds.find((w) => w.id === chosenWorld));

  onDestroy(() => cleanup());

  function cleanup() {
    ws?.close();
    mediaRecorder?.stop();
    stream?.getTracks().forEach((t) => t.stop());
    if (lastAudioUrl) {
      URL.revokeObjectURL(lastAudioUrl);
      lastAudioUrl = null;
    }
  }

  function friendlyError(e: unknown): string {
    const raw = e instanceof Error ? e.message : String(e);
    if (/(401|403|auth)/i.test(raw)) return 'Zugriff verweigert.';
    if (/(429|rate.?limit)/i.test(raw))
      return 'Der Erzähler ist gerade überlastet. Bitte gleich nochmal versuchen.';
    if (/(timeout|timed out)/i.test(raw))
      return 'Der Erzähler antwortet gerade nicht.';
    if (/connect/i.test(raw))
      return 'Verbindung zum Erzähler verloren.';
    if (raw.includes('Error(') || raw.length > 140)
      return 'Es gab eine Störung. Bitte erneut versuchen.';
    return raw;
  }

  // Mic permission gate — secure-context only on non-localhost.
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
          ? `Der Browser blockiert das Mikrofon, weil die Seite über http://${host} (nicht sicher) geladen ist. `
            + 'Sprachmodus funktioniert nur über HTTPS oder über http://localhost. '
            + 'Lösung: Öffne die Seite direkt auf dem Pi (http://localhost:8090/voice) oder richte einen HTTPS-Reverse-Proxy ein.'
          : 'Dieser Browser bietet keinen Mikrofonzugriff. Bitte einen aktuellen Chrome / Firefox / Safari verwenden.';
    }
    return ok;
  }

  onMount(async () => {
    try {
      worlds = await listWorlds();
      let lp: string | null = null;
      try { lp = localStorage.getItem('st-last-played'); } catch { /* ignore */ }
      lastPlayedId = lp || '';
      if (lp && worlds.some((w) => w.id === lp)) chosenWorld = lp;
      else if (worlds.length === 1) chosenWorld = worlds[0].id;
    } catch (e) {
      error = friendlyError(e);
    }
    _checkMicAvailable();
  });

  function _setStartStatus(label: string) {
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
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      _setStartStatus('Eröffnung wird vorbereitet (kann ~30 s dauern)…');
      const sess = await createSession(chosenWorld);
      threadId = sess.thread_id;
      try { localStorage.setItem('st-last-played', chosenWorld); } catch { /* ignore */ }
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
      error = `Mikrofon/Verbindung: ${friendlyError(e)}`;
      _stopCounter();
    }
  }

  function pushLine(l: Line) {
    lines.push(l);
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

  function startWaitSound() {
    if (!waitSoundEnabled) return;
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
    try { waitAudio?.pause(); } catch { /* ignore */ }
  }

  function handleMessage(ev: MessageEvent) {
    if (typeof ev.data === 'string') {
      try {
        const msg = JSON.parse(ev.data);
        if (msg.type === 'thinking') { thinking = true; startWaitSound(); }
        else if (msg.type === 'stt') pushLine({ who: 'player', text: msg.text });
        else if (msg.type === 'narration') {
          thinking = false; stopWaitSound();
          pushLine({ who: 'narrator', text: msg.text });
          if (!openingHeard) { openingHeard = true; _stopCounter(); }
        } else if (msg.type === 'audio_done') { thinking = false; stopWaitSound(); }
        else if (msg.type === 'daily_cap_exceeded') {
          thinking = false; stopWaitSound();
          capPaused = true;
          capInfo = { usd_today: msg.usd_today, cap_usd: msg.cap_usd };
          pushLine({ who: 'system', text: msg.message });
        } else if (msg.type === 'note_saved') {
          pushLine({
            who: 'system',
            text: `Vermerk gespeichert: ${msg.name} (${msg.kind})`
          });
        } else if (msg.type === 'story_ended') {
          ws?.close(); ws = null;
          threadId = ''; lines = [];
        } else if (msg.type === 'error') {
          thinking = false; stopWaitSound();
          error = friendlyError(msg.message);
        }
      } catch {
        /* ignore */
      }
      return;
    }
    // Binary frames = WAV audio of the narration. Be defensive: only
    // accept ArrayBuffer / Blob, never a string slipping through.
    let blob: Blob | null = null;
    if (ev.data instanceof ArrayBuffer) {
      blob = new Blob([ev.data], { type: 'audio/wav' });
    } else if (ev.data instanceof Blob) {
      blob = ev.data;
    } else {
      console.warn('voice WS: unexpected binary payload', typeof ev.data);
      return;
    }
    const url = URL.createObjectURL(blob);
    if (audio) { try { audio.pause(); } catch { /* */ } }
    if (lastAudioUrl) URL.revokeObjectURL(lastAudioUrl);
    lastAudioUrl = url;
    audio = new Audio(url);
    audio.onended = () => { playing = false; paused = false; };
    audio.onpause = () => { if (audio && !audio.ended) paused = true; playing = false; };
    audio.onplay  = () => { playing = true; paused = false; };
    audio.play().catch((e) => {
      log = `Audio blockiert (Browser-Autoplay): ${e?.message || e}. `
          + 'Tippe auf "Erzähler anhören".';
      pendingAudio = audio;
    });
  }

  // Two distinct controls:
  //   ⏸ Pause Audio — purely local; lets the player skim or finish reading
  //   ✋ unterbrechen — local pause AND a server `interrupt` signal
  function pauseAudio() {
    audio?.pause();
  }
  function resumeAudio() {
    audio?.play().catch(() => { /* autoplay-blocked etc. */ });
  }
  function interrupt() {
    audio?.pause();
    playing = false; paused = false;
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: 'interrupt' }));
    }
  }

  // --- recording ----------------------------------------------------------
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
    recElapsed = 0;
    recTick = window.setInterval(() => (recElapsed += 1), 1000);
  }
  function stopRec() {
    if (!recording) return;
    mediaRecorder?.stop();
    recording = false;
    if (recTick !== undefined) { window.clearInterval(recTick); recTick = undefined; }
  }
  function toggleRec() {
    if (!connected || thinking || capPaused) return;
    if (recording) stopRec(); else startRec();
  }
  // VAD auto-stop — invoked by MicMeter after `silentMs` of below-
  // threshold audio FOLLOWING a real speech segment. We just stop the
  // recording so onstop sends the blob like a normal tap-to-stop.
  function onVadSilence() {
    if (recording) stopRec();
  }
  function fmtMS(secs: number): string {
    const m = Math.floor(secs / 60);
    const s = secs % 60;
    return `${m}:${s.toString().padStart(2, '0')}`;
  }

  function onKeydown(e: KeyboardEvent) {
    if (e.code !== 'Space') return;
    const t = e.target as HTMLElement | null;
    const tag = t?.tagName;
    if (tag === 'INPUT' || tag === 'TEXTAREA' || t?.isContentEditable) return;
    if (!threadId) return;
    e.preventDefault();
    toggleRec();
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

  // Replay last narration via server TTS — single button below the chat.
  let replayLoading = $state(false);
  async function replayLast() {
    if (replayLoading) return;
    replayLoading = true;
    try {
      const url = await fetchReplayUrl(threadId, chosenWorld);
      if (audio) { try { audio.pause(); } catch { /* */ } }
      if (lastAudioUrl) URL.revokeObjectURL(lastAudioUrl);
      lastAudioUrl = url;
      audio = new Audio(url);
      audio.onended = () => { playing = false; paused = false; };
      audio.onpause = () => { if (audio && !audio.ended) paused = true; playing = false; };
      audio.onplay  = () => { playing = true; paused = false; };
      await audio.play();
    } catch (e) {
      error = friendlyError(e);
    } finally {
      replayLoading = false;
    }
  }
</script>

<svelte:window onkeydown={onKeydown} />

<main class="app-main">
  <header class="app-header">
    <a class="brand" href="/" title="StoryTeller">
      <img src="/favicon.png" alt="" />
      <h1>StoryTeller · Sprache</h1>
    </a>
    <div class="header-actions">
      {#if threadId && chosenWorldObj}
        <span class="session-label">
          <strong>{chosenWorldObj.name}</strong>
          <span class="hint small">· {chosenWorldObj.genre}</span>
        </span>
      {:else}
        <a class="mode-link" href="/">Textmodus</a>
      {/if}
      <button class="icon-btn" onclick={toggleWaitSound}
              title={waitSoundEnabled
                       ? 'Hintergrundklang aus'
                       : 'Hintergrundklang an'}
              aria-label="Hintergrundklang umschalten">
        {waitSoundEnabled ? '🔊' : '🔇'}
      </button>
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
        <div class="cards">
          {#each worlds as w (w.id)}
            <WorldCard world={w}
                       selected={chosenWorld === w.id}
                       highlighted={lastPlayedId === w.id}
                       onSelect={(id) => (chosenWorld = id)} />
          {/each}
        </div>
        <div class="pick-actions">
          <button class="primary" onclick={start}
                  disabled={!chosenWorld || !micAvailable || starting}>
            {starting ? `…lädt (${startElapsed}s)` : '🎤 Beginnen'}
          </button>
        </div>
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
      <div class="banner warn">
        <span>{log}</span>
        {#if pendingAudio}
          <button class="link" onclick={playPending}>▶ Erzähler anhören</button>
        {/if}
      </div>
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
        <ChatLine who={line.who} text={line.text} />
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

    <footer class="ptt-footer">
      <button
        class="ptt"
        class:rec={recording}
        onclick={toggleRec}
        disabled={!connected || thinking || capPaused}
        title="Leertaste startet/stoppt die Aufnahme"
      >
        {#if recording}
          <MicMeter stream={stream} active={recording} onSilence={onVadSilence} />
          <span>● Stopp & senden · {fmtMS(recElapsed)}</span>
        {:else}
          <span>🎤 Aufnahme starten</span>
        {/if}
      </button>
      <div class="ptt-hint">
        Tipp: Leertaste startet/stoppt · Stille beendet automatisch
      </div>
      {#if playing || paused}
        <div class="playback-controls">
          {#if paused}
            <button class="pause" onclick={resumeAudio}>▶ Weiter</button>
          {:else}
            <button class="pause" onclick={pauseAudio}>⏸ Pause</button>
          {/if}
          <button class="interrupt" onclick={interrupt}>✋ Unterbrechen</button>
        </div>
      {:else if lines.some((l) => l.who === 'narrator')}
        <div class="playback-controls">
          <button class="pause" onclick={replayLast} disabled={replayLoading}>
            {replayLoading ? '…' : '🔁 Sag das nochmal'}
          </button>
        </div>
      {/if}
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
    position: sticky; bottom: 5rem; align-self: center;
    background: #6fc3df; color: #10131a; border: none;
    border-radius: 999px; padding: 0.3rem 0.85rem; cursor: pointer;
    font-weight: 600; font-size: 0.85rem;
    box-shadow: 0 2px 8px rgba(0,0,0,0.25);
  }
  .ptt-footer { padding-top: 0.5rem; border-top: 1px solid var(--border); }
  .ptt {
    width: 100%; padding: 1rem; font-size: 1.1rem; font-weight: 600;
    background: #b4d273; color: #10131a; border: none; border-radius: 6px;
    cursor: pointer; user-select: none;
    display: flex; align-items: center; justify-content: center;
    gap: 0.4rem;
  }
  .ptt.rec { background: #e07a7a; color: #fff; }
  .ptt:disabled { background: var(--border); color: var(--muted); cursor: not-allowed; }
  .ptt-hint {
    text-align: center; color: var(--muted); font-size: 0.78rem;
    margin: 0.35rem 0 0;
  }
  .playback-controls {
    display: flex; gap: 0.5rem; margin-top: 0.5rem;
  }
  .playback-controls button {
    flex: 1; padding: 0.55rem; font-size: 0.95rem; font-weight: 600;
    background: var(--surface); color: var(--fg);
    border: 1px solid var(--border); border-radius: 6px; cursor: pointer;
  }
  .playback-controls .interrupt {
    background: rgba(220, 50, 50, 0.18); border-color: #c25450; color: #fff;
  }
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
  .mic-warn {
    background: rgba(220, 50, 50, 0.10);
    border-left: 3px solid #c25450;
    padding: 0.6rem 0.8rem; border-radius: 4px;
    margin: 0.6rem 0; color: var(--fg);
  }
  .mic-warn p { margin: 0.3rem 0 0; font-size: 0.9rem; line-height: 1.45; }

  @media (max-width: 600px) {
    .cards { grid-template-columns: 1fr; }
    .ptt { font-size: 1rem; padding: 0.9rem; }
    .pick-actions .primary { width: 100%; padding: 0.7rem; }
  }
</style>
