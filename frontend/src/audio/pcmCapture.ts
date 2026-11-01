/** Capture mic audio and emit 16 kHz mono PCM. Nothing is written to disk. */

const WORKLET = `
class PCMProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.buf = [];
  }
  process(inputs) {
    const channel = inputs[0] && inputs[0][0];
    if (!channel) return true;
    for (let i = 0; i < channel.length; i += 1) this.buf.push(channel[i]);
    if (this.buf.length >= 2048) {
      const copy = new Float32Array(this.buf);
      this.buf = [];
      this.port.postMessage(copy, [copy.buffer]);
    }
    return true;
  }
}
registerProcessor("pcm-processor", PCMProcessor);
`;

export async function startPcmCapture(onChunk: (pcm: ArrayBuffer) => void): Promise<() => void> {
  if (!navigator.mediaDevices?.getUserMedia) {
    throw new Error("Questo browser non espone il microfono.");
  }
  const stream = await navigator.mediaDevices.getUserMedia({
    audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true },
    video: false,
  });
  const stop = await captureStreamPcm(stream, onChunk);
  return () => {
    stop();
    stream.getTracks().forEach((track) => track.stop());
  };
}

export async function startElementPcmCapture(
  video: HTMLVideoElement,
  onChunk: (pcm: ArrayBuffer) => void,
): Promise<() => void> {
  const capture = captureFromElement(video);
  const audio = capture.getAudioTracks();
  if (!audio.length) {
    throw new Error("Questo video non ha una traccia audio leggibile dal browser.");
  }
  return captureStreamPcm(new MediaStream(audio), onChunk);
}

function captureFromElement(video: HTMLVideoElement): MediaStream {
  const element = video as HTMLVideoElement & {
    captureStream?: () => MediaStream;
    mozCaptureStream?: () => MediaStream;
  };
  const capture = element.captureStream?.() ?? element.mozCaptureStream?.();
  if (!capture) {
    throw new Error("Questo browser non può leggere l'audio del video.");
  }
  return capture;
}

async function captureStreamPcm(stream: MediaStream, onChunk: (pcm: ArrayBuffer) => void): Promise<() => void> {
  const context = new AudioContext();
  await context.resume();
  const blob = new Blob([WORKLET], { type: "application/javascript" });
  const url = URL.createObjectURL(blob);
  await context.audioWorklet.addModule(url);
  URL.revokeObjectURL(url);

  const source = context.createMediaStreamSource(stream);
  const node = new AudioWorkletNode(context, "pcm-processor");
  node.port.onmessage = (event: MessageEvent<Float32Array>) => {
    const pcm = downsample(event.data, context.sampleRate, 16000);
    onChunk(pcm.buffer as ArrayBuffer);
  };
  source.connect(node);

  return () => {
    node.port.onmessage = null;
    source.disconnect();
    node.disconnect();
    void context.close();
  };
}

function downsample(buffer: Float32Array, inRate: number, outRate: number): Int16Array {
  if (outRate >= inRate) return floatTo16(buffer);
  const ratio = inRate / outRate;
  const length = Math.max(1, Math.round(buffer.length / ratio));
  const result = new Int16Array(length);
  let offset = 0;
  for (let index = 0; index < length; index += 1) {
    const next = Math.min(buffer.length, Math.round((index + 1) * ratio));
    let sum = 0;
    let count = 0;
    for (let cursor = offset; cursor < next; cursor += 1) {
      sum += buffer[cursor] ?? 0;
      count += 1;
    }
    offset = next;
    const sample = count ? sum / count : 0;
    const clamped = Math.max(-1, Math.min(1, sample));
    result[index] = clamped < 0 ? clamped * 0x8000 : clamped * 0x7fff;
  }
  return result;
}

function floatTo16(buffer: Float32Array): Int16Array {
  const result = new Int16Array(buffer.length);
  for (let index = 0; index < buffer.length; index += 1) {
    const sample = Math.max(-1, Math.min(1, buffer[index] ?? 0));
    result[index] = sample < 0 ? sample * 0x8000 : sample * 0x7fff;
  }
  return result;
}
