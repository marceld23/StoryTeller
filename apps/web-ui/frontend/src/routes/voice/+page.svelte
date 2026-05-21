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
  let error = $state('');

  let ws: WebSocket | null = null;
  let mediaRecorder: MediaRecorder | null = null;
  let chunks: BlobPart[] = [];
  let stream: MediaStream | null = null;
  let audio: HTMLAudioElement | null = null;

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

  function handleMessage(ev: MessageEvent) {
    if (typeof ev.data === 'string') {
      try {
        const msg = JSON.parse(ev.data);
        if (msg.type === 'thinking') thinking = true;
        else if (msg.type === 'stt') lines.push({ who: 'player', text: msg.text });
        else if (msg.type === 'narration') {
          thinking = false;
          lines.push({ who: 'narrator', text: msg.text });
        } else if (msg.type === 'audio_done') thinking = false;
        else if (msg.type === 'error') {
          thinking = false;
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
      audio.onended = () => URL.revokeObjectURL(url);
      audio.play().catch(() => {});
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
    <section class="chat">
      {#each lines as line, i (i)}
        <div class={'line ' + line.who}>{line.text}</div>
      {/each}
      {#if thinking}<div class="line system">…</div>{/if}
    </section>

    <footer>
      <button
        class="ptt"
        class:rec={recording}
        onmousedown={startRec}
        onmouseup={stopRec}
        onmouseleave={stopRec}
        ontouchstart={startRec}
        ontouchend={stopRec}
        disabled={!connected || thinking}
      >
        {recording ? '● Aufnahme – loslassen zum Senden' : '🎤 Halten zum Sprechen'}
      </button>
    </footer>
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
  .error { color: #e07a7a; }
</style>
