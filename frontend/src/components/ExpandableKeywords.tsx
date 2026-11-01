import { AnimatePresence, motion } from "framer-motion";
import type { Expansion, GraphNode } from "../types";

interface Props {
  expansions: Expansion[];
  nodes: GraphNode[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}

export function ExpandableKeywords({ expansions, nodes, selectedId, onSelect }: Props) {
  const selected = nodes.find((node) => node.id === selectedId) ?? null;
  const active =
    expansions.find((item) => item.term === selected?.term) ??
    (selected
      ? { term: selected.term, explanation: selected.explanation || "" }
      : expansions[0]);

  return (
    <section className="flex min-h-0 flex-col border-b border-rule md:border-b-0 md:border-r">
      <header className="px-5 pb-2 pt-4">
        <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-copper">Summary</p>
        <h2 className="font-display text-xl text-ink">Approfondimenti</h2>
      </header>
      <div className="flex gap-2 overflow-x-auto px-5 pb-3">
        {nodes.length === 0 && <p className="text-sm text-ink/60">Nessun termine ancora.</p>}
        {nodes.map((node) => {
          const on = node.id === (selected?.id ?? nodes.find((item) => item.term === active?.term)?.id);
          return (
            <button
              key={node.id}
              type="button"
              onClick={() => onSelect(node.id)}
              className={`shrink-0 rounded-full px-3 py-1 text-sm transition ${
                on ? "bg-pine text-mist" : "bg-white text-ink hover:bg-rule"
              }`}
            >
              {node.term}
            </button>
          );
        })}
      </div>
      <div className="min-h-[5.5rem] px-5 pb-4">
        <AnimatePresence mode="wait">
          {active ? (
            <motion.div
              key={active.term}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.18 }}
            >
              <h3 className="font-display text-lg text-pine">{active.term}</h3>
              <p className="mt-1 text-sm leading-relaxed text-ink/80">
                {active.explanation || "L'approfondimento arriva al prossimo passaggio della lezione."}
              </p>
            </motion.div>
          ) : (
            <p className="text-sm text-ink/60">Clicca un nodo del grafo per aprire il suo approfondimento.</p>
          )}
        </AnimatePresence>
      </div>
    </section>
  );
}
