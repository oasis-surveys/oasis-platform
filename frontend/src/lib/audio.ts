/**
 * OASIS — Browser audio capture & playback helpers.
 *
 * Captures mic input as 16-bit PCM at 16 kHz and plays back raw PCM16
 * received from the pipeline.
 */

const TARGET_SAMPLE_RATE = 16000;

// ── Mic Capture ─────────────────────────────────────────────────

export class MicCapture {
  private stream: MediaStream | null = null;
  private audioContext: AudioContext | null = null;
  private workletNode: ScriptProcessorNode | null = null;
  private onChunk: ((pcm16: Uint8Array) => void) | null = null;
  private onLevel: ((level: number) => void) | null = null;

  /**
   * Start capturing microphone audio.
   * @param onChunk — called with PCM16 LE byte chunks (~20 ms each)
   * @param onLevel — called with RMS audio level [0, 1] for visualisation
   */
  async start(
    onChunk: (pcm16: Uint8Array) => void,
    onLevel?: (level: number) => void
  ) {
    this.onChunk = onChunk;
    this.onLevel = onLevel ?? null;

    this.stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        sampleRate: TARGET_SAMPLE_RATE,
        channelCount: 1,
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
      },
    });

    this.audioContext = new AudioContext({ sampleRate: TARGET_SAMPLE_RATE });
    if (this.audioContext.state === "suspended") {
      await this.audioContext.resume();
    }
    const source = this.audioContext.createMediaStreamSource(this.stream);

    // ScriptProcessorNode (deprecated but universally supported)
    // Buffer size = 512 samples ≈ 32 ms at 16 kHz
    this.workletNode = this.audioContext.createScriptProcessor(512, 1, 1);
    this.workletNode.onaudioprocess = (e) => {
      const float32 = e.inputBuffer.getChannelData(0);

      // Compute RMS level for visualisation
      if (this.onLevel) {
        let sum = 0;
        for (let i = 0; i < float32.length; i++) {
          sum += float32[i] * float32[i];
        }
        const rms = Math.sqrt(sum / float32.length);
        // Normalise to 0-1 range with some headroom
        this.onLevel(Math.min(1, rms * 5));
      }

      const pcm16 = float32ToPcm16(float32);
      this.onChunk?.(pcm16);
    };

    source.connect(this.workletNode);
    this.workletNode.connect(this.audioContext.destination); // required for processing
  }

  stop() {
    this.workletNode?.disconnect();
    this.stream?.getTracks().forEach((t) => t.stop());
    this.audioContext?.close();
    this.stream = null;
    this.audioContext = null;
    this.workletNode = null;
    this.onChunk = null;
    this.onLevel = null;
  }
}

// ── Audio Playback ──────────────────────────────────────────────

export class AudioPlayer {
  private audioContext: AudioContext | null = null;
  private nextStartTime = 0;

  constructor() {
    // Use the browser's default sample rate (usually 44100/48000) so that
    // playback buffers at any sample rate (16 kHz, 24 kHz, etc.) are
    // resampled transparently by the browser's AudioContext.
    this.audioContext = new AudioContext();
    // Browsers may start the AudioContext in a suspended state.
    // Resume immediately (must be called from a user-gesture call chain).
    if (this.audioContext.state === "suspended") {
      this.audioContext.resume();
    }
  }

  /**
   * Enqueue a chunk of PCM16 LE audio for gapless playback.
   */
  play(pcm16: Uint8Array, sampleRate: number = TARGET_SAMPLE_RATE) {
    if (!this.audioContext) return;

    // Ensure context is running (some browsers re-suspend it)
    if (this.audioContext.state === "suspended") {
      this.audioContext.resume();
    }

    const float32 = pcm16ToFloat32(pcm16);
    if (float32.length === 0) return;

    const buffer = this.audioContext.createBuffer(1, float32.length, sampleRate);
    // Use getChannelData to avoid SharedArrayBuffer TS issues
    const channelData = buffer.getChannelData(0);
    channelData.set(float32);

    const src = this.audioContext.createBufferSource();
    src.buffer = buffer;
    src.connect(this.audioContext.destination);

    const now = this.audioContext.currentTime;
    const start = Math.max(now + 0.01, this.nextStartTime);
    src.start(start);
    this.nextStartTime = start + buffer.duration;
  }

  /** Stop playback and clear queue. */
  stop() {
    this.nextStartTime = 0;
  }

  destroy() {
    this.audioContext?.close();
    this.audioContext = null;
  }
}

// ── Conversion helpers ──────────────────────────────────────────

/** Float32 [-1, 1] → Int16 LE bytes */
function float32ToPcm16(float32: Float32Array): Uint8Array {
  const buf = new ArrayBuffer(float32.length * 2);
  const view = new DataView(buf);
  for (let i = 0; i < float32.length; i++) {
    const s = Math.max(-1, Math.min(1, float32[i]));
    view.setInt16(i * 2, s < 0 ? s * 0x8000 : s * 0x7fff, true);
  }
  return new Uint8Array(buf);
}

/** Int16 LE bytes → Float32 [-1, 1] */
function pcm16ToFloat32(pcm16: Uint8Array): Float32Array {
  const view = new DataView(pcm16.buffer, pcm16.byteOffset, pcm16.byteLength);
  const numSamples = pcm16.byteLength / 2;
  const float32 = new Float32Array(numSamples);
  for (let i = 0; i < numSamples; i++) {
    const s = view.getInt16(i * 2, true);
    float32[i] = s / (s < 0 ? 0x8000 : 0x7fff);
  }
  return float32;
}
