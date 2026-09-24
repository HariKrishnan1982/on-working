/**
 * Browser microphone recording helpers for voice enrollment.
 *
 * Backend contract (gateway/ops_api.py POST /api/v1/users):
 *   multipart fields: name, emp_id, email, role, dept (+ optional consented_by)
 *   + repeated `samples` file fields (1..3 audio files).
 *   settings.allowed_content_types =
 *     audio/wav, audio/x-wav, audio/wave, audio/mpeg, audio/ogg,
 *     audio/flac, application/octet-stream
 *   NOTE: audio/webm is NOT accepted, so Chrome's native MediaRecorder
 *   output must be decoded + re-encoded to 16-bit PCM WAV before upload.
 */

export const ENROLL_TARGET_SAMPLE_RATE = 16000;

/** Minimum accepted recording length (seconds). UX guard only — the backend
 *  fail-closed VAD path remains authoritative for short/silent audio. */
export const MIN_RECORDING_S = 0.5;

const MIME_CANDIDATES = [
  'audio/webm;codecs=opus',
  'audio/webm',
  'audio/ogg;codecs=opus',
  'audio/ogg',
];

/** True when the browser can record audio at all. */
export function isRecordingSupported(): boolean {
  return (
    typeof window !== 'undefined' &&
    typeof MediaRecorder !== 'undefined' &&
    !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia)
  );
}

/**
 * Pick the first MediaRecorder MIME type the browser actually supports.
 * Returns null when MediaRecorder cannot report support (caller should then
 * construct MediaRecorder without a mimeType and convert the result to WAV).
 */
export function pickRecordingMimeType(): string | null {
  try {
    if (typeof MediaRecorder === 'undefined' || !MediaRecorder.isTypeSupported) return null;
    for (const candidate of MIME_CANDIDATES) {
      try {
        if (MediaRecorder.isTypeSupported(candidate)) return candidate;
      } catch {
        /* try next candidate */
      }
    }
    return null;
  } catch {
    return null;
  }
}

/** User-facing message for getUserMedia / recording failures. Never leaks raw exceptions. */
export function friendlyMicError(err: unknown): string {
  const name = err instanceof DOMException ? err.name : err instanceof Error ? err.name : '';
  switch (name) {
    case 'NotAllowedError':
      return 'Microphone permission was denied. Allow microphone access in your browser settings and try again.';
    case 'NotFoundError':
    case 'OverconstrainedError':
      return 'No microphone was detected. Connect a microphone and try again, or use file upload instead.';
    case 'NotReadableError':
    case 'AbortError':
      return 'The microphone is already in use by another application. Close it and try again.';
    case 'SecurityError':
      return 'Microphone access was blocked for security reasons. Use a secure context (HTTPS or localhost) and try again.';
    default:
      if (typeof window !== 'undefined' && window.isSecureContext === false) {
        return 'Microphone access requires a secure context (HTTPS or localhost). Use file upload instead.';
      }
      return 'Voice recording is not supported by this browser. Use file upload instead.';
  }
}

/** Encode mono float samples as a 16-bit PCM WAV blob. */
export function encodeWavPcm16(mono: Float32Array, sampleRate: number): Blob {
  const numChannels = 1;
  const bytesPerSample = 2;
  const blockAlign = numChannels * bytesPerSample;
  const dataSize = mono.length * bytesPerSample;
  const buffer = new ArrayBuffer(44 + dataSize);
  const view = new DataView(buffer);

  const writeAscii = (offset: number, text: string) => {
    for (let i = 0; i < text.length; i++) view.setUint8(offset + i, text.charCodeAt(i));
  };

  writeAscii(0, 'RIFF');
  view.setUint32(4, 36 + dataSize, true);
  writeAscii(8, 'WAVE');
  writeAscii(12, 'fmt ');
  view.setUint32(16, 16, true); // PCM chunk size
  view.setUint16(20, 1, true); // audio format = PCM
  view.setUint16(22, numChannels, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * blockAlign, true); // byte rate
  view.setUint16(32, blockAlign, true);
  view.setUint16(34, 16, true); // bits per sample
  writeAscii(36, 'data');
  view.setUint32(40, dataSize, true);

  let offset = 44;
  for (let i = 0; i < mono.length; i++) {
    const clamped = Math.max(-1, Math.min(1, mono[i]));
    view.setInt16(offset, clamped < 0 ? clamped * 0x8000 : clamped * 0x7fff, true);
    offset += 2;
  }
  return new Blob([buffer], { type: 'audio/wav' });
}

/**
 * Decode any browser-recorded blob via Web Audio, downmix to mono, resample
 * to 16 kHz (what the ECAPA enrollment path expects), and wrap as a WAV File
 * whose MIME (audio/wav) the backend accepts.
 */
export async function recordingToWavFile(
  recorded: Blob,
  outName: string,
): Promise<{ file: File; durationS: number }> {
  if (recorded.size === 0) {
    throw new Error('Recording produced no audio data — please try again.');
  }
  const rawBytes = await recorded.arrayBuffer();
  const decodeCtx = new AudioContext();
  try {
    // Copy bytes: decodeAudioData may detach the source buffer.
    const audioBuffer = await decodeCtx.decodeAudioData(rawBytes.slice(0));
    const durationS = audioBuffer.duration;
    if (!Number.isFinite(durationS) || durationS < MIN_RECORDING_S) {
      throw new Error(
        `Recording too short (${durationS.toFixed(1)}s) — please speak for at least ~1 second.`,
      );
    }

    // Resample + downmix to mono 16 kHz offline (no playback side effects).
    const targetLen = Math.max(1, Math.ceil(durationS * ENROLL_TARGET_SAMPLE_RATE));
    const offline = new OfflineAudioContext(1, targetLen, ENROLL_TARGET_SAMPLE_RATE);
    const source = offline.createBufferSource();
    source.buffer = audioBuffer;
    source.connect(offline.destination);
    source.start(0);
    const rendered = await offline.startRendering();
    const mono = rendered.getChannelData(0);
    const wavBlob = encodeWavPcm16(mono, ENROLL_TARGET_SAMPLE_RATE);
    return {
      file: new File([wavBlob], outName, { type: 'audio/wav' }),
      durationS,
    };
  } finally {
    void decodeCtx.close().catch(() => {});
  }
}

/** Best-effort duration probe for user-uploaded files (never rejects). */
export function probeFileDurationS(file: File): Promise<number | null> {
  return new Promise(resolve => {
    try {
      const url = URL.createObjectURL(file);
      const el = new Audio();
      el.preload = 'metadata';
      const done = (value: number | null) => {
        URL.revokeObjectURL(url);
        resolve(value);
      };
      el.onloadedmetadata = () => done(Number.isFinite(el.duration) ? el.duration : null);
      el.onerror = () => done(null);
      el.src = url;
      // Safety net: never hang enrollment on a duration probe.
      setTimeout(() => done(null), 5000);
    } catch {
      resolve(null);
    }
  });
}
