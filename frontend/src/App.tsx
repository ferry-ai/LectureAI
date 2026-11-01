import { useRef, useState } from "react";
import { ExpandableKeywords } from "./components/ExpandableKeywords";
import { KeywordGraph } from "./components/KeywordGraph";
import { QuestionsPanel } from "./components/QuestionsPanel";
import { SlideConnections } from "./components/SlideConnections";
import { TranscriptBar } from "./components/TranscriptBar";
import { VideoStage } from "./components/VideoStage";
import { useLectureSession } from "./hooks/useLectureSession";
import { useVideoFile } from "./hooks/useVideoFile";

export function App() {
  const fileRef = useRef<HTMLInputElement>(null);
  const session = useLectureSession();
  const video = useVideoFile();
  const [mode, setMode] = useState<"live" | "video">("live");
  const active = session.catalog?.providers.find((item) => item.id === session.provider);
  const models = active?.models ?? [];

  return (
    <div className="flex h-full min-h-0 flex-col">
      <header className="shrink-0 border-b border-rule bg-paper/90 px-4 py-3 backdrop-blur">
        <div className="flex flex-wrap items-end gap-3">
          <div className="mr-2">
            <p className="font-display text-2xl leading-none text-ink">
              Lecture<span className="italic text-copper">AI</span>
            </p>
            <p className="mt-1 text-xs text-ink/60">Note Cornell, in diretta</p>
            <div className="mt-2 inline-flex rounded-full border border-rule bg-white p-0.5 text-xs">
              <button
                type="button"
                className={`rounded-full px-3 py-1 ${mode === "live" ? "bg-ink text-mist" : "text-ink/70"}`}
                onClick={() => setMode("live")}
              >
                Dal vivo
              </button>
              <button
                type="button"
                className={`rounded-full px-3 py-1 ${mode === "video" ? "bg-ink text-mist" : "text-ink/70"}`}
                onClick={() => setMode("video")}
              >
                Video
              </button>
            </div>
          </div>

          <label className="text-xs text-ink/70">
            Provider
            <select
              className="mt-1 block rounded-xl border border-rule bg-white px-2 py-1.5 text-sm text-ink"
              value={session.provider}
              onChange={(event) => session.selectProvider(event.target.value)}
            >
              {(session.catalog?.providers ?? [{ id: "xai", label: "xAI (Grok)" }]).map((item) => (
                <option key={item.id} value={item.id}>
                  {item.label}
                </option>
              ))}
            </select>
          </label>

          <label className="text-xs text-ink/70">
            Modello
            <input
              list="lecture-models"
              className="mt-1 block w-48 rounded-xl border border-rule bg-white px-2 py-1.5 text-sm text-ink"
              value={session.model}
              onChange={(event) => session.setModel(event.target.value)}
            />
            <datalist id="lecture-models">
              {models.map((item) => (
                <option key={item} value={item} />
              ))}
            </datalist>
          </label>

          <label className="text-xs text-ink/70">
            Lingua appunti
            <select
              className="mt-1 block rounded-xl border border-rule bg-white px-2 py-1.5 text-sm text-ink"
              value={session.language}
              onChange={(event) => session.setLanguage(event.target.value)}
            >
              <option value="it">Italiano</option>
              <option value="en">English</option>
            </select>
          </label>

          <label className="text-xs text-ink/70">
            Voce
            <select
              className="mt-1 block rounded-xl border border-rule bg-white px-2 py-1.5 text-sm text-ink"
              value={session.sttMode}
              onChange={(event) => session.setSttMode(event.target.value as "browser" | "deepgram")}
            >
              <option value="browser">Browser</option>
              <option value="deepgram">Deepgram</option>
            </select>
          </label>

          <div className="ml-auto flex flex-wrap items-center gap-2">
            <span className={`h-2.5 w-2.5 rounded-full ${session.connected ? "bg-pine" : "bg-copper"}`} title={session.connected ? "connesso" : "non connesso"} />
            <button
              type="button"
              className="rounded-full bg-white px-3 py-1.5 text-sm text-ink shadow-card"
              onClick={() => fileRef.current?.click()}
            >
              Slide PDF
            </button>
            <input
              ref={fileRef}
              type="file"
              accept="application/pdf"
              className="hidden"
              onChange={(event) => {
                const file = event.target.files?.[0];
                if (file) void session.uploadSlides(file);
                event.target.value = "";
              }}
            />
            <button
              type="button"
              className="rounded-full bg-white px-3 py-1.5 text-sm text-ink shadow-card"
              onClick={session.demoPlaying ? session.stopDemo : session.playDemo}
            >
              {session.demoPlaying ? "Stop demo" : "Lezione demo"}
            </button>
            <button
              type="button"
              className="rounded-full bg-white px-3 py-1.5 text-sm text-ink shadow-card"
              onClick={session.analyzeNow}
            >
              Analizza ora
            </button>
            <button
              type="button"
              className={`rounded-full px-4 py-1.5 text-sm font-semibold text-mist ${session.recording ? "animate-pulse bg-copper" : "bg-pine"}`}
              onClick={session.recording ? session.stopRecording : () => void session.startRecording()}
            >
              {session.recording ? "Stop" : "Registra"}
            </button>
          </div>
        </div>
        {active && !active.configured && active.via === "cli" && (
          <p className="mt-2 text-xs text-ink/70">{active.hint}</p>
        )}
        {active && !active.configured && active.via !== "cli" && active.id !== "demo" && (
          <p className="mt-2 text-xs text-ink/70">
            Manca {active.hint}. Fino a quando non la aggiungi nel file .env, l'analisi usa il demo locale.
          </p>
        )}
        {session.sttMode === "deepgram" && session.catalog && !session.catalog.stt.deepgram && (
          <p className="mt-1 text-xs text-ink/70">Deepgram chiede DEEPGRAM_API_KEY. In alternativa resta la voce del browser.</p>
        )}
        {session.notice && <p className="mt-2 text-sm text-copper">{session.notice}</p>}
        {session.error && (
          <p className="mt-2 flex items-center gap-3 text-sm text-copper">
            {session.error}
            <button type="button" className="underline" onClick={session.clearError}>
              chiudi
            </button>
          </p>
        )}
      </header>

      <div className="grid min-h-0 flex-1 lg:grid-cols-[minmax(0,1fr)_22rem]">
        <section className="relative min-h-0 border-rule">
          <p className="pointer-events-none absolute left-5 top-3 z-10 text-[11px] font-semibold uppercase tracking-[0.18em] text-ink/40">
            {mode === "video" ? "Video" : "Note"}
          </p>
          {mode === "video" ? (
            <VideoStage
              url={video.url}
              name={video.name}
              resumeAt={video.resumeAt.current}
              recording={session.recording}
              onFiles={(files) => void video.load(files)}
              onTime={video.rememberTime}
              deliverTranscript={session.deliverTranscript}
              ensureFileStt={session.ensureFileStt}
              releaseFileStt={session.releaseFileStt}
              yieldFileStt={session.yieldFileStt}
              pushPcm={session.pushPcm}
            />
          ) : (
            <KeywordGraph
              nodes={session.graph.nodes}
              edges={session.graph.edges}
              freshIds={session.freshIds}
              selectedId={session.selectedId}
              onSelect={session.setSelectedId}
            />
          )}
          <TranscriptBar
            transcript={session.transcript}
            interim={session.interim}
            analyzing={session.analyzing}
            source={session.source}
            placeholder={
              mode === "video"
                ? "Il testo del video compare qui mentre lo guardi. L'audio non viene salvato."
                : undefined
            }
          />
        </section>
        <QuestionsPanel questions={session.questions} />
      </div>

      <section className="grid max-h-72 shrink-0 overflow-hidden border-t border-rule md:grid-cols-2">
        <ExpandableKeywords
          expansions={session.expansions}
          nodes={session.graph.nodes}
          selectedId={session.selectedId}
          onSelect={session.setSelectedId}
        />
        <SlideConnections
          matches={session.slideMatches}
          slideCount={session.slideCount}
          warning={session.slideWarning}
        />
      </section>
    </div>
  );
}
