import { useEffect, useRef, useState } from "react";
import { startElementPcmCapture } from "../audio/pcmCapture";
import { cuesAtPlayhead, type Cue } from "../video/cues";

interface Props {
  url: string | null;
  name: string | null;
  resumeAt: number;
  recording: boolean;
  onFiles: (files: File[]) => void;
  onTime: (time: number) => void;
  deliverTranscript: (text: string, final: boolean) => void;
  ensureFileStt: () => void;
  releaseFileStt: () => void;
  yieldFileStt: () => void;
  pushPcm: (pcm: ArrayBuffer) => void;
}

export function VideoStage({
  url,
  name,
  resumeAt,
  recording,
  onFiles,
  onTime,
  deliverTranscript,
  ensureFileStt,
  releaseFileStt,
  yieldFileStt,
  pushPcm,
}: Props) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const sentRef = useRef(new Set<string>());
  const stopPcmRef = useRef<(() => void) | null>(null);
  const [over, setOver] = useState(false);
  const [playbackError, setPlaybackError] = useState<string | null>(null);
  const [playing, setPlaying] = useState(false);
  const [embedded, setEmbedded] = useState<Cue[]>([]);
  const followCues = embedded.length > 0;

  useEffect(() => {
    sentRef.current = new Set();
    setEmbedded([]);
  }, [url]);

  useEffect(() => {
    const video = videoRef.current;
    if (!video || !url) return;
    const pull = () => {
      const found: Cue[] = [];
      for (const track of Array.from(video.textTracks)) {
        track.mode = "hidden";
        for (const cue of Array.from(track.cues ?? [])) {
          const text = "text" in cue ? String(cue.text).replace(/\s+/g, " ").trim() : "";
          if (!text) continue;
          found.push({ start: cue.startTime, end: cue.endTime, text });
        }
      }
      found.sort((left, right) => left.start - right.start);
      if (!found.length) return;
      setEmbedded((current) => {
        if (
          current.length === found.length &&
          current.every((cue, index) => cue.start === found[index]?.start && cue.text === found[index]?.text)
        ) {
          return current;
        }
        return found;
      });
    };
    pull();
    video.textTracks.addEventListener("addtrack", pull);
    const timer = window.setInterval(pull, 400);
    const stop = window.setTimeout(() => window.clearInterval(timer), 8000);
    return () => {
      window.clearInterval(timer);
      window.clearTimeout(stop);
      video.textTracks.removeEventListener("addtrack", pull);
    };
  }, [url]);

  useEffect(() => {
    const video = videoRef.current;
    if (!video || !url) return;
    const restore = () => {
      if (resumeAt > 0 && Math.abs(video.currentTime - resumeAt) > 0.4) {
        video.currentTime = resumeAt;
      }
    };
    video.addEventListener("loadedmetadata", restore);
    return () => video.removeEventListener("loadedmetadata", restore);
  }, [url, resumeAt]);

  useEffect(() => {
    if (!playing || !followCues) return;
    const video = videoRef.current;
    if (!video) return;
    const emit = () => {
      for (const cue of cuesAtPlayhead(embedded, video.currentTime, sentRef.current)) {
        deliverTranscript(cue.text, true);
      }
      onTime(video.currentTime);
    };
    emit();
    const timer = window.setInterval(emit, 200);
    return () => window.clearInterval(timer);
  }, [playing, followCues, embedded, deliverTranscript, onTime]);

  useEffect(() => {
    if (followCues || !playing || recording || !url) {
      stopPcmRef.current?.();
      stopPcmRef.current = null;
      if (recording) yieldFileStt();
      if (followCues) releaseFileStt();
      return;
    }
    const video = videoRef.current;
    if (!video) return;
    let cancelled = false;
    ensureFileStt();
    void startElementPcmCapture(video, pushPcm)
      .then((stop) => {
        if (cancelled) stop();
        else stopPcmRef.current = stop;
      })
      .catch(() => {
        if (cancelled) return;
        releaseFileStt();
        setPlaybackError("Questo video non ha un audio che il browser può leggere.");
      });
    return () => {
      cancelled = true;
      stopPcmRef.current?.();
      stopPcmRef.current = null;
    };
  }, [followCues, playing, recording, url, ensureFileStt, releaseFileStt, pushPcm, yieldFileStt]);

  useEffect(() => {
    return () => {
      stopPcmRef.current?.();
      releaseFileStt();
    };
  }, [releaseFileStt]);

  const take = (list: FileList | null | undefined) => {
    if (!list?.length) return;
    setPlaybackError(null);
    onFiles(Array.from(list));
  };

  return (
    <div
      className={`relative h-full min-h-[28rem] ${over ? "ring-2 ring-inset ring-copper" : ""}`}
      onDragOver={(event) => {
        event.preventDefault();
        setOver(true);
      }}
      onDragLeave={() => setOver(false)}
      onDrop={(event) => {
        event.preventDefault();
        setOver(false);
        take(event.dataTransfer.files);
      }}
    >
      {url ? (
        <div className="h-full pb-28">
        <video
          ref={videoRef}
          key={url}
          src={url}
          controls
          className="h-full w-full bg-ink object-contain"
          onPlay={() => setPlaying(true)}
          onPause={() => {
            setPlaying(false);
            if (videoRef.current) onTime(videoRef.current.currentTime);
          }}
          onError={() => setPlaybackError("Questo browser non riproduce il file. Prova mp4 o webm.")}
        />
        </div>
      ) : (
        <button
          type="button"
          className="flex h-full w-full flex-col items-center justify-center gap-3 px-8 text-center"
          onClick={() => fileRef.current?.click()}
        >
          <p className="font-display text-3xl text-ink">Trascina un video</p>
          <p className="max-w-md text-sm leading-relaxed text-ink/70">
            mp4, webm o mov. Parte solo il video: l'audio viene trascritto su questo PC mentre lo guardi, anche in
            cuffia, e gli appunti si aggiornano come dal vivo.
          </p>
        </button>
      )}
      <input
        ref={fileRef}
        type="file"
        accept="video/*,.mp4,.webm,.mov,.mkv"
        className="hidden"
        onChange={(event) => {
          take(event.target.files);
          event.target.value = "";
        }}
      />
      {url && (
        <div className="pointer-events-none absolute left-5 top-9 z-10 max-w-lg rounded-xl bg-ink/75 px-3 py-2 text-xs text-mist">
          <p>{name}</p>
          <p className="mt-1 text-mist/80">
            {followCues
              ? "Il video ha sottotitoli dentro il file. Il testo entra negli appunti mentre guardi."
              : "Trascrivo l'audio nella lingua parlata nel video. Il testo compare a tratti."}
          </p>
          {playbackError && <p className="mt-1 text-copper">{playbackError}</p>}
        </div>
      )}
    </div>
  );
}
