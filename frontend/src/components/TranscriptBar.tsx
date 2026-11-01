interface Props {
  transcript: string;
  interim: string;
  analyzing: boolean;
  source: "llm" | "demo" | null;
  placeholder?: string;
}

export function TranscriptBar({ transcript, interim, analyzing, source, placeholder }: Props) {
  return (
    <div className="pointer-events-none absolute inset-x-4 bottom-4">
      <div className="pointer-events-auto rounded-2xl border border-rule bg-mist/95 px-4 py-3 shadow-card backdrop-blur">
        <div className="mb-1 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.16em] text-ink/50">
          <span>Transcript</span>
          {analyzing && <span className="text-copper">Sto collegando i concetti…</span>}
          {source && <span className="text-pine">{source === "demo" ? "demo locale" : "modello"}</span>}
        </div>
        <p className="max-h-16 overflow-y-auto text-sm leading-relaxed text-ink">
          {transcript ||
            (!interim && (placeholder ?? "Il parlato compare qui. L'audio non viene salvato."))}
          {interim && <span className="text-ink/50"> {interim}</span>}
        </p>
      </div>
    </div>
  );
}
