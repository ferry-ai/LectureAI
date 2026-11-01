import type { SlideMatch } from "../types";

interface Props {
  matches: SlideMatch[];
  slideCount: number;
  warning: string | null;
}

export function SlideConnections({ matches, slideCount, warning }: Props) {
  return (
    <section className="flex min-h-0 flex-col">
      <header className="px-5 pb-2 pt-4">
        <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-copper">Slide</p>
        <h2 className="font-display text-xl text-ink">
          Collegamenti {slideCount > 0 ? <span className="text-base text-ink/50">· {slideCount} pagine</span> : null}
        </h2>
      </header>
      <div className="space-y-2 overflow-y-auto px-5 pb-4">
        {warning && <p className="text-sm text-copper">{warning}</p>}
        {slideCount === 0 && !warning && (
          <p className="text-sm leading-relaxed text-ink/70">
            Carica il PDF delle slide. I concetti del grafo si agganciano alla pagina che ne parla.
          </p>
        )}
        {slideCount > 0 && matches.length === 0 && !warning && (
          <p className="text-sm text-ink/70">Nessun collegamento ancora. Arriva con i prossimi concetti.</p>
        )}
        {matches.map((match) => (
          <article key={`${match.concept}-${match.slide_number}`} className="rounded-2xl bg-white px-4 py-3 shadow-card">
            <p className="text-[11px] font-semibold uppercase tracking-wider text-pine">
              Slide {match.slide_number} · {match.concept}
            </p>
            <h3 className="mt-1 text-sm font-semibold text-ink">{match.title}</h3>
            {match.excerpt && <p className="mt-1 line-clamp-3 text-sm text-ink/70">{match.excerpt}</p>}
          </article>
        ))}
      </div>
    </section>
  );
}
