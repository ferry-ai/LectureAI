export interface GraphNode {
  id: string;
  term: string;
  importance: number;
  explanation?: string | null;
}

export interface GraphEdge {
  id: string;
  source: string;
  target: string;
}

export interface GraphState {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export interface Question {
  id: string;
  text: string;
  created_at: number;
}

export interface Expansion {
  term: string;
  explanation: string;
}

export interface SlideMatch {
  concept: string;
  slide_number: number;
  title: string;
  excerpt: string;
  score: number;
}

export interface ProviderInfo {
  id: string;
  label: string;
  models: string[];
  configured: boolean;
  hint: string;
  via?: "cli" | "env";
}

export interface Catalog {
  default_provider: string;
  default_model: string;
  providers: ProviderInfo[];
  stt: { deepgram: boolean; browser: boolean; local?: boolean };
  analysis: { min_interval_s: number; min_chars: number };
}

export interface LectureDelta {
  keywords: GraphNode[];
  edges: GraphEdge[];
  questions: Question[];
  expansions: Expansion[];
  slide_matches: SlideMatch[];
}
