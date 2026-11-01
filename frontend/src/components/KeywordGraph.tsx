import { useEffect, useRef } from "react";
import { DataSet } from "vis-data";
import { Network } from "vis-network";
import type { GraphEdge, GraphNode } from "../types";

interface VisNode {
  id: string;
  label: string;
  title: string;
  value: number;
  font: { color: string; face: string; size: number };
  color: { background: string; border: string; highlight: { background: string; border: string } };
  borderWidth: number;
}

interface VisEdge {
  id: string;
  from: string;
  to: string;
}

interface Props {
  nodes: GraphNode[];
  edges: GraphEdge[];
  freshIds: string[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}

function syncSet<T extends { id: string }>(dataset: DataSet<T>, next: T[]) {
  const keep = new Set(next.map((item) => item.id));
  for (const id of dataset.getIds()) {
    if (!keep.has(String(id))) dataset.remove(id);
  }
  const existing = new Set(dataset.getIds().map((id) => String(id)));
  const additions = next.filter((item) => !existing.has(item.id));
  const updates = next.filter((item) => existing.has(item.id));
  if (additions.length) dataset.add(additions);
  if (updates.length) dataset.update(updates as never);
}

function paint(node: GraphNode, fresh: boolean, selected: boolean): VisNode {
  const hot = node.importance >= 4;
  const mid = node.importance === 3;
  const background = fresh ? "#e07a3d" : hot ? "#c45c26" : mid ? "#1e3a34" : "#d9d3c5";
  const font = hot || mid || fresh ? "#f7f3ec" : "#1c1915";
  return {
    id: node.id,
    label: node.term,
    title: node.explanation || node.term,
    value: 8 + node.importance * 4,
    font: { color: font, face: "Figtree", size: 14 },
    color: {
      background,
      border: selected ? "#1c1915" : "#f7f3ec",
      highlight: { background: "#e07a3d", border: "#1c1915" },
    },
    borderWidth: selected ? 3 : 2,
  };
}

export function KeywordGraph({ nodes, edges, freshIds, selectedId, onSelect }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const networkRef = useRef<Network | null>(null);
  const nodesRef = useRef<DataSet<VisNode> | null>(null);
  const edgesRef = useRef<DataSet<VisEdge> | null>(null);
  const fittedRef = useRef(false);
  const onSelectRef = useRef(onSelect);
  onSelectRef.current = onSelect;

  useEffect(() => {
    const element = containerRef.current;
    if (!element) return;
    const nodeSet = new DataSet<VisNode>([]);
    const edgeSet = new DataSet<VisEdge>([]);
    nodesRef.current = nodeSet;
    edgesRef.current = edgeSet;
    const network = new Network(
      element,
      { nodes: nodeSet, edges: edgeSet },
      {
        autoResize: true,
        physics: {
          barnesHut: { gravitationalConstant: -2200, springLength: 140, damping: 0.45 },
          stabilization: { iterations: 80 },
        },
        interaction: { hover: true, tooltipDelay: 120 },
        nodes: { shape: "dot", scaling: { min: 12, max: 36 } },
        edges: {
          color: { color: "#c4b8a5", highlight: "#c45c26" },
          smooth: { enabled: true, type: "continuous", roundness: 0.4 },
          width: 1.5,
        },
      },
    );
    network.on("click", (params) => {
      const id = params.nodes[0];
      if (id !== undefined) onSelectRef.current(String(id));
    });
    networkRef.current = network;
    return () => {
      network.destroy();
      networkRef.current = null;
      nodesRef.current = null;
      edgesRef.current = null;
    };
  }, []);

  useEffect(() => {
    const nodeSet = nodesRef.current;
    const edgeSet = edgesRef.current;
    if (!nodeSet || !edgeSet) return;
    const fresh = new Set(freshIds);
    const nextNodes = nodes.map((node) => paint(node, fresh.has(node.id), node.id === selectedId));
    const nextEdges = edges.map((edge) => ({ id: edge.id, from: edge.source, to: edge.target }));
    syncSet(nodeSet, nextNodes);
    syncSet(edgeSet, nextEdges);
    if (!fittedRef.current && nextNodes.length > 0) {
      fittedRef.current = true;
      window.setTimeout(() => networkRef.current?.fit({ animation: { duration: 400, easingFunction: "easeInOutQuad" } }), 280);
    }
  }, [nodes, edges, freshIds, selectedId]);

  return (
    <div className="relative h-full min-h-[28rem]">
      <div ref={containerRef} className="h-full w-full" />
      {nodes.length === 0 && (
        <div className="pointer-events-none absolute inset-0 flex items-center justify-center px-8 text-center">
          <p className="max-w-sm font-display text-2xl text-ink/80">
            Avvia la registrazione o la lezione demo. Le parole chiave si aggrappano qui, man mano.
          </p>
        </div>
      )}
    </div>
  );
}
