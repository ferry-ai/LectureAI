import { AnimatePresence, motion } from "framer-motion";
import type { Question } from "../types";

interface Props {
  questions: Question[];
}

export function QuestionsPanel({ questions }: Props) {
  const ordered = [...questions].reverse();
  return (
    <aside className="cue-column flex min-h-[20rem] flex-col border-t border-rule lg:min-h-0 lg:border-l lg:border-t-0">
      <header className="px-5 pb-2 pt-4">
        <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-copper">Cues</p>
        <h2 className="font-display text-xl text-ink">Domande</h2>
      </header>
      <div className="flex-1 space-y-3 overflow-y-auto px-4 pb-4">
        {ordered.length === 0 && (
          <p className="px-1 text-sm leading-relaxed text-ink/70">
            Le domande di comprensione compariranno qui, come la colonna dei cues del metodo Cornell.
          </p>
        )}
        <AnimatePresence initial={false}>
          {ordered.map((question) => (
            <motion.article
              key={question.id}
              layout
              initial={{ opacity: 0, y: 12, scale: 0.98 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0 }}
              transition={{ type: "spring", stiffness: 420, damping: 30 }}
              className="rounded-2xl bg-mist px-4 py-3 shadow-card"
            >
              <p className="text-sm leading-relaxed text-ink">{question.text}</p>
            </motion.article>
          ))}
        </AnimatePresence>
      </div>
    </aside>
  );
}
