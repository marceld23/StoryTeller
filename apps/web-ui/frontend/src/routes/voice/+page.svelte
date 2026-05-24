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

  let ws: WebSocket | null = null;
  let mediaRecorder: MediaRecorder | null = null;
  let chunks: BlobPart[] = [];
  let stream: MediaStream | null = null;
  let audio: HTMLAudioElement | null = null;
  let waitAudio: HTMLAudioElement | null = null;

  onMount(async () => {
    try {
      worlds = await listWorlds();
      if (worlds.length === 1) chosenWorld = worlds[0].id;
    } catch (e) {
      error = String(e);
    }
  });

  onDestroy(() => cleanup());

  function cleanup() {
    ws?.close();
    mediaRecorder?.stop();
    stream?.getTracks().forEach((t) => t.stop());
  }

  async function start() {
    if (!chosenWorld) return;
    error = '';
    lines = [];
    try {
      // mic permission up front
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });

      const sess = await createSession(chosenWorld);
      threadId = sess.thread_id;

      ws = openVoiceSocket(threadId, chosenWorld);
      ws.onopen = () => (connected = true);
      ws.onclose = () => (connected = false);
      ws.onerror = () => (error = 'WebSocket-Fehler');
      ws.onmessage = (ev) => handleMessage(ev);
    } catch (e) {
      error = `Mikrofon/Verbindung: ${e}`;
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
      audio.play().catch(() => {});
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
    <h1>StoryTeller · Sprache</h1>
    <a href="/">Textmodus</a>
  </header>

  {#if error}<p class="error">{error}</p>{/if}

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
        <button onclick={start} disabled={!chosenWorld}>Beginnen (Mikrofon)</button>
      {/if}
    </section>
  {:else}
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
  main { max-width: 760px; margin: 0 auto; padding: 1rem; display: flex; flex-direction: column; min-height: 100vh; }
  header { display: flex; justify-content: space-between; align-items: baseline; border-bottom: 1px solid var(--border); padding-bottom: 0.5rem; }
  h1 { margin: 0; font-size: 1.4rem; color: #6fc3df; }
  header a { color: var(--muted); }
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
