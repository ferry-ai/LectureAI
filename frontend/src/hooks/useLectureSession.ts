import { useCallback, useEffect, useRef, useState } from "react";
import { startPcmCapture } from "../audio/pcmCapture";
import { DEMO_LECTURE } from "../demoLecture";
import type { Catalog, Expansion, GraphState, LectureDelta, Question, SlideMatch } from "../types";

const EMPTY_GRAPH: GraphState = { nodes: [], edges: [] };

interface ServerMessage {
  type: string;
  source?: "llm" | "demo";
  notice?: string | null;
  message?: string;
  scope?: string;
  graph?: GraphState;
  questions?: Question[];
  expansions?: Expansion[];
  slide_matches?: SlideMatch[];
  slide_count?: number;
  slide_warning?: string | null;
  tail?: string;
  transcript_tail?: string;
  interim?: string;
  final?: boolean;
  delta?: LectureDelta;
  analyzing?: boolean;
  provider?: string;
  model?: string;
  language?: string;
  session_id?: string;
}

function speechLang(language: string): string {
  if (language.startsWith("en")) return "en-US";
  if (language.startsWith("it")) return "it-IT";
  return language;
}

export function useLectureSession() {
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [connected, setConnected] = useState(false);
  const [provider, setProvider] = useState("xai");
  const [model, setModel] = useState("grok-4.7");
  const [language, setLanguage] = useState("it");
  const [sttMode, setSttMode] = useState<"browser" | "deepgram">("browser");
  const [graph, setGraph] = useState<GraphState>(EMPTY_GRAPH);
  const [questions, setQuestions] = useState<Question[]>([]);
  const [expansions, setExpansions] = useState<Expansion[]>([]);
  const [slideMatches, setSlideMatches] = useState<SlideMatch[]>([]);
  const [slideCount, setSlideCount] = useState(0);
  const [slideWarning, setSlideWarning] = useState<string | null>(null);
  const [transcript, setTranscript] = useState("");
  const [interim, setInterim] = useState("");
  const [recording, setRecording] = useState(false);
  const [demoPlaying, setDemoPlaying] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const [source, setSource] = useState<"llm" | "demo" | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [freshIds, setFreshIds] = useState<string[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const queueRef = useRef<string[]>([]);
  const recordingRef = useRef(false);
  const recognitionRef = useRef<SpeechRecognition | null>(null);
  const stopAudioRef = useRef<(() => void) | null>(null);
  const demoTimerRef = useRef<number | null>(null);
  const interimAtRef = useRef(0);
  const fileSttRef = useRef(false);

  const send = useCallback((message: object) => {
    const raw = JSON.stringify(message);
    const socket = wsRef.current;
    if (socket && socket.readyState === WebSocket.OPEN) socket.send(raw);
    else queueRef.current.push(raw);
  }, []);

  const apply = useCallback((message: ServerMessage) => {
    if (message.type === "snapshot" || message.type === "update") {
      if (message.graph) setGraph(message.graph);
      if (message.questions) setQuestions(message.questions);
      if (message.expansions) setExpansions(message.expansions);
      if (message.slide_matches) setSlideMatches(message.slide_matches);
      if (typeof message.slide_count === "number") setSlideCount(message.slide_count);
      if (message.slide_warning !== undefined) setSlideWarning(message.slide_warning ?? null);
      if (message.transcript_tail) setTranscript(message.transcript_tail);
      if (message.notice !== undefined) setNotice(message.notice ?? null);
      if (message.source) setSource(message.source);
      if (message.delta?.keywords?.length) {
        setFreshIds(message.delta.keywords.map((node) => node.id));
      }
    }
    if (message.type === "transcript") {
      if (message.tail !== undefined) setTranscript(message.tail);
      setInterim(message.interim ?? "");
    }
    if (message.type === "slides") {
      if (typeof message.slide_count === "number") setSlideCount(message.slide_count);
      setSlideWarning(message.slide_warning ?? null);
      if (message.slide_matches) setSlideMatches(message.slide_matches);
    }
    if (message.type === "status") {
      if (typeof message.analyzing === "boolean") setAnalyzing(message.analyzing);
    }
    if (message.type === "error" && message.message) {
      setError(message.message);
      if (message.scope === "stt") {
        recordingRef.current = false;
        setRecording(false);
      }
    }
    if (message.type === "notice") setNotice(message.message || null);
  }, []);

  useEffect(() => {
    let cancelled = false;
    let socket: WebSocket | null = null;

    const connect = (id: string) => {
      const protocol = window.location.protocol === "https:" ? "wss" : "ws";
      socket = new WebSocket(`${protocol}://${window.location.host}/ws/sessions/${id}`);
      wsRef.current = socket;
      socket.onopen = () => {
        if (cancelled) return;
        setConnected(true);
        const pending = queueRef.current.splice(0);
        for (const item of pending) socket?.send(item);
      };
      socket.onmessage = (event) => {
        try {
          apply(JSON.parse(String(event.data)) as ServerMessage);
        } catch {
          setError("Messaggio dal server non leggibile.");
        }
      };
      socket.onerror = () => {
        if (!cancelled) setError("Connessione con il backend interrotta.");
      };
      socket.onclose = () => {
        if (!cancelled) setConnected(false);
      };
    };

    void (async () => {
      try {
        const catalogResponse = await fetch("/api/providers");
        if (!catalogResponse.ok) throw new Error("Catalogo provider non disponibile.");
        const body = (await catalogResponse.json()) as Catalog;
        if (cancelled) return;
        setCatalog(body);
        setProvider(body.default_provider || "xai");
        setModel(body.default_model || "grok-4.7");
        const created = await fetch("/api/sessions", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            provider: body.default_provider || "xai",
            model: body.default_model || "grok-4.7",
            language: "it",
          }),
        });
        if (!created.ok) throw new Error("Impossibile aprire la sessione.");
        const session = (await created.json()) as { id: string };
        if (cancelled) return;
        setSessionId(session.id);
        connect(session.id);
      } catch (reason) {
        if (!cancelled) setError(reason instanceof Error ? reason.message : "Avvio non riuscito.");
      }
    })();

    return () => {
      cancelled = true;
      socket?.close();
      wsRef.current = null;
    };
  }, [apply]);

  useEffect(() => {
    if (!freshIds.length) return;
    const timer = window.setTimeout(() => setFreshIds([]), 1600);
    return () => window.clearTimeout(timer);
  }, [freshIds]);

  useEffect(() => {
    send({ type: "config", provider, model, language });
  }, [provider, model, language, send]);

  const stopCapture = useCallback(() => {
    recordingRef.current = false;
    recognitionRef.current?.stop();
    recognitionRef.current = null;
    stopAudioRef.current?.();
    stopAudioRef.current = null;
    setRecording(false);
  }, []);

  const deliverTranscript = useCallback(
    (text: string, final: boolean) => {
      send({ type: "transcript", text, final });
    },
    [send],
  );

  const ensureFileStt = useCallback(() => {
    if (fileSttRef.current) return;
    fileSttRef.current = true;
    send({ type: "start", stt: "local" });
  }, [send]);

  const releaseFileStt = useCallback(() => {
    if (!fileSttRef.current) return;
    fileSttRef.current = false;
    send({ type: "stop" });
  }, [send]);

  const yieldFileStt = useCallback(() => {
    fileSttRef.current = false;
  }, []);

  const pushPcm = useCallback((pcm: ArrayBuffer) => {
    const socket = wsRef.current;
    if (socket && socket.readyState === WebSocket.OPEN) socket.send(pcm);
  }, []);

  const startRecording = useCallback(async () => {
    setError(null);
    fileSttRef.current = false;
    if (demoTimerRef.current !== null) {
      window.clearInterval(demoTimerRef.current);
      demoTimerRef.current = null;
      setDemoPlaying(false);
    }
    recordingRef.current = true;
    setRecording(true);
    try {
      if (sttMode === "deepgram") {
        stopAudioRef.current = await startPcmCapture((pcm) => {
          const socket = wsRef.current;
          if (socket && socket.readyState === WebSocket.OPEN) socket.send(pcm);
        });
        send({ type: "start", stt: "deepgram" });
        return;
      }
      const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
      if (!Recognition) {
        throw new Error("Il browser non ha il riconoscimento vocale. Usa Chrome, oppure la lezione demo.");
      }
      const recognition = new Recognition();
      recognition.lang = speechLang(language);
      recognition.continuous = true;
      recognition.interimResults = true;
      recognition.onresult = (event) => {
        let pending = "";
        for (let index = event.resultIndex; index < event.results.length; index += 1) {
          const result = event.results[index];
          const text = result?.[0]?.transcript ?? "";
          if (!text.trim()) continue;
          if (result?.isFinal) send({ type: "transcript", text, final: true });
          else pending += text;
        }
        const now = Date.now();
        if (pending && now - interimAtRef.current > 250) {
          interimAtRef.current = now;
          send({ type: "transcript", text: pending, final: false });
        }
      };
      recognition.onerror = (event) => {
        if (event.error === "not-allowed") setError("Permesso microfono negato.");
        else if (event.error) setError(`Riconoscimento vocale: ${event.error}`);
        recordingRef.current = false;
        setRecording(false);
      };
      recognition.onend = () => {
        if (recordingRef.current) {
          try {
            recognition.start();
          } catch {
            /* already running */
          }
        }
      };
      recognitionRef.current = recognition;
      recognition.start();
      send({ type: "start", stt: "browser" });
    } catch (reason) {
      stopCapture();
      setError(reason instanceof Error ? reason.message : "Registrazione non avviata.");
    }
  }, [language, send, sttMode, stopCapture]);

  const stopRecording = useCallback(() => {
    stopCapture();
    send({ type: "stop" });
  }, [send, stopCapture]);

  const playDemo = useCallback(() => {
    if (demoPlaying) return;
    stopCapture();
    send({ type: "start", stt: "demo" });
    const sentences = DEMO_LECTURE.split(/(?<=[.!?])\s+/);
    let cursor = 0;
    setDemoPlaying(true);
    const tick = () => {
      const sentence = sentences[cursor];
      if (!sentence) {
        if (demoTimerRef.current !== null) window.clearInterval(demoTimerRef.current);
        demoTimerRef.current = null;
        setDemoPlaying(false);
        send({ type: "stop" });
        return;
      }
      send({ type: "transcript", text: sentence, final: true });
      cursor += 1;
    };
    tick();
    demoTimerRef.current = window.setInterval(tick, 3200);
  }, [demoPlaying, send, stopCapture]);

  const stopDemo = useCallback(() => {
    if (demoTimerRef.current !== null) window.clearInterval(demoTimerRef.current);
    demoTimerRef.current = null;
    setDemoPlaying(false);
    send({ type: "stop" });
  }, [send]);

  const analyzeNow = useCallback(() => send({ type: "analyze" }), [send]);

  const uploadSlides = useCallback(
    async (file: File) => {
      if (!sessionId) {
        setError("Sessione non pronta.");
        return;
      }
      setError(null);
      const body = new FormData();
      body.append("file", file);
      const response = await fetch(`/api/sessions/${sessionId}/slides`, { method: "POST", body });
      if (!response.ok) {
        const payload = (await response.json().catch(() => ({}))) as { detail?: string };
        setError(payload.detail || "Upload non riuscito.");
      }
    },
    [sessionId],
  );

  const selectProvider = useCallback(
    (next: string) => {
      setProvider(next);
      const found = catalog?.providers.find((item) => item.id === next);
      if (found?.models[0]) setModel(found.models[0]);
    },
    [catalog],
  );

  useEffect(() => {
    return () => {
      if (demoTimerRef.current !== null) window.clearInterval(demoTimerRef.current);
      recognitionRef.current?.stop();
      stopAudioRef.current?.();
    };
  }, []);

  return {
    catalog,
    connected,
    provider,
    model,
    language,
    sttMode,
    graph,
    questions,
    expansions,
    slideMatches,
    slideCount,
    slideWarning,
    transcript,
    interim,
    recording,
    demoPlaying,
    analyzing,
    source,
    notice,
    error,
    freshIds,
    selectedId,
    setModel,
    setLanguage,
    setSttMode,
    setSelectedId,
    selectProvider,
    startRecording,
    stopRecording,
    playDemo,
    stopDemo,
    analyzeNow,
    uploadSlides,
    deliverTranscript,
    ensureFileStt,
    releaseFileStt,
    yieldFileStt,
    pushPcm,
    clearError: () => setError(null),
  };
}
