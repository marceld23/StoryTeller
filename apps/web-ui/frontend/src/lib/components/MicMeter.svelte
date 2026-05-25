<script lang="ts">
  // Live mic level + optional VAD (voice activity detection) for the
  // voice-mode push-to-talk button. Built on AnalyserNode — the same
  // stream that goes to MediaRecorder. `silentCallback` is invoked
  // ONCE after `silentMs` of below-threshold audio, so the parent can
  // auto-stop the recording (browser equivalent of the Pi's VAD).
  import { onMount, onDestroy } from 'svelte';

  let {
    stream,
    active = false,
    silentMs = 1500,
    silenceRms = 0.012,
    minSpeechMs = 350,
    onSilence = null,
  }: {
    stream: MediaStream | null;
    active?: boolean;
    silentMs?: number;
    silenceRms?: number;
    minSpeechMs?: number;
    onSilence?: (() => void) | null;
  } = $props();

  let ctx: AudioContext | null = null;
  let src: MediaStreamAudioSourceNode | null = null;
  let analyser: AnalyserNode | null = null;
  let buf = new Float32Array(1024);
  let raf: number | null = null;
  let level = $state(0);                  // 0..1, smoothed RMS

  // VAD state
  let silentSince: number | null = null;
  let speechStartedAt: number | null = null;
  let firedThisRound = false;

  function attach() {
    if (!stream) return;
    detach();
    try {
      const Ctx = (window.AudioContext || (window as any).webkitAudioContext);
      ctx = new Ctx();
      src = ctx.createMediaStreamSource(stream);
      analyser = ctx.createAnalyser();
      analyser.fftSize = 2048;
      buf = new Float32Array(analyser.fftSize);
      src.connect(analyser);
      loop();
    } catch {
      /* AudioContext / mic permission blocked — meter stays at 0 */
    }
  }

  function detach() {
    if (raf !== null) cancelAnimationFrame(raf);
    raf = null;
    try { src?.disconnect(); } catch { /* ignore */ }
    try { ctx?.close(); } catch { /* ignore */ }
    src = null; analyser = null; ctx = null;
    level = 0;
    silentSince = null; speechStartedAt = null; firedThisRound = false;
  }

  function loop() {
    if (!analyser) return;
    analyser.getFloatTimeDomainData(buf);
    let sum = 0;
    for (let i = 0; i < buf.length; i++) sum += buf[i] * buf[i];
    const rms = Math.sqrt(sum / buf.length);
    // Smooth + scale: most speech sits at 0.05–0.2 RMS. Cap at 1.0.
    level = Math.min(1, level * 0.6 + Math.min(rms * 4, 1) * 0.4);

    if (active) {
      const now = performance.now();
      const speaking = rms > silenceRms;
      if (speaking) {
        if (speechStartedAt === null) speechStartedAt = now;
        silentSince = null;
      } else if (speechStartedAt !== null
                  && (now - speechStartedAt) >= minSpeechMs) {
        // Only start measuring silence AFTER the player actually
        // produced ≥minSpeechMs of audio — otherwise the auto-stop
        // would fire 1.5 s after the player merely tapped the button.
        if (silentSince === null) silentSince = now;
        else if (!firedThisRound && (now - silentSince) >= silentMs) {
          firedThisRound = true;
          onSilence?.();
        }
      }
    }
    raf = requestAnimationFrame(loop);
  }

  // Re-attach when stream changes (e.g. after _checkMicAvailable).
  $effect(() => {
    if (stream) attach(); else detach();
  });
  // Reset VAD state on each active cycle.
  $effect(() => {
    if (active) {
      silentSince = null; speechStartedAt = null; firedThisRound = false;
    }
  });

  onMount(() => attach());
  onDestroy(() => detach());

  // Five bars, lit progressively. Cheap to draw, robust on every browser.
  const BARS = 5;
</script>

<div class="meter" aria-hidden="true">
  {#each Array(BARS) as _, i (i)}
    <span class="bar" class:on={level > (i + 1) / (BARS + 1)}></span>
  {/each}
</div>

<style>
  .meter {
    display: inline-flex; gap: 3px; align-items: flex-end;
    height: 18px; margin-right: 0.55rem; flex: 0 0 auto;
  }
  .bar {
    display: inline-block; width: 4px; background: rgba(255,255,255,0.25);
    border-radius: 1px; transition: background 0.08s, height 0.08s;
  }
  .bar:nth-child(1) { height: 30%; }
  .bar:nth-child(2) { height: 50%; }
  .bar:nth-child(3) { height: 70%; }
  .bar:nth-child(4) { height: 85%; }
  .bar:nth-child(5) { height: 100%; }
  .bar.on { background: #fff; }
</style>
