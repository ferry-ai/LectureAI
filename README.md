# LectureAI

Appunti in diretta durante una lezione. Il parlato diventa un grafo di parole chiave al centro, domande di comprensione a destra (la colonna cues del metodo Cornell) e approfondimenti in basso. Se carichi le slide in PDF, i concetti si agganciano alla pagina che ne parla.

L'audio non viene salvato. Restano solo il transcript, il grafo e il testo delle slide, in memoria, finché il backend è acceso.

## Scelte

- Il provider LLM restituisce solo JSON. L'orchestratore decide cosa entra nel grafo. Un canale rotto (timeout, 429) si ritenta una volta; una risposta di forma sbagliata riceve un solo sollecito, non la stessa chiamata alla cieca.
- Le chiavi restano sul server. Il browser vede soltanto se un provider è configurato.
- Senza chiavi, l'estrattore demo locale fa funzionare il flusso. I test non chiamano nessun modello.
- Niente automazione di chat web a pagamento: solo API ufficiali (xAI, OpenAI, Anthropic, OpenRouter) o un server locale compatibile.

## Setup (Windows)

Due terminali, dalla cartella del progetto.

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
copy ..\.env.example ..\.env
.\.venv\Scripts\python -m uvicorn app.main:app --reload --port 8000
```

```powershell
cd frontend
npm install
npm run dev
```

Apri http://localhost:5173

Senza chiavi: scegli **Demo locale**, oppure lascia xAI e premi **Lezione demo**. Il grafo si muove lo stesso. Con `XAI_API_KEY` nel `.env` il default è Grok `grok-4.7` su `https://api.x.ai/v1`.

## Variabili

| Variabile | Ruolo |
| --- | --- |
| `XAI_API_KEY` | Grok. Modello di default `grok-4.7`. |
| `OPENAI_API_KEY` | OpenAI. |
| `ANTHROPIC_API_KEY` | Anthropic. |
| `OPENROUTER_API_KEY` | OpenRouter. |
| `LOCAL_LLM_BASE_URL` | Server locale tipo Ollama, es. `http://127.0.0.1:11434/v1`. |
| `DEEPGRAM_API_KEY` | Trascrizione server. Senza, si usa il riconoscimento del browser (Chrome). |
| `ANALYSIS_MIN_CHARS` | Caratteri nuovi prima di chiamare il modello. Default 80. |
| `ANALYSIS_MIN_INTERVAL` | Secondi minimi tra un'analisi e la successiva. Default 20. Il primo passaggio parte subito. |

Il nome del modello nell'interfaccia è libero: i preset sono solo suggerimenti.

## Come si usa

1. Avvia backend e frontend.
2. Opzionale: carica il PDF delle slide. I PDF scansiti non hanno testo e vengono segnalati.
3. **Registra** (microfono) oppure **Lezione demo**.
4. Ogni fine frase, se c'è abbastanza testo nuovo e sono passati almeno 20 secondi, il backend manda chunk + grafo al modello.
5. Il modello risponde con keyword, relazioni, domande, approfondimenti e un indizio di slide.
6. Un click su un nodo apre l'approfondimento.

**Analizza ora** forza un passaggio anche prima dell'intervallo.

## Layout del codice

```
backend/app/
  main.py
  routers/session.py
  services/llm_orchestrator.py
  services/graph_manager.py
  services/stt.py
  services/providers/   base, xai, openai, anthropic, openrouter, local, demo
frontend/src/
  components/KeywordGraph.tsx
  components/QuestionsPanel.tsx
  components/ExpandableKeywords.tsx
  components/SlideConnections.tsx
  hooks/useLectureSession.ts
```

WebSocket: `/ws/sessions/{id}`. Messaggi in ingresso: `config`, `transcript`, `analyze`, `start`, `stop`, oppure PCM 16 kHz a 16 bit se la voce è Deepgram. In uscita: `snapshot`, `transcript`, `update`, `slides`, `status`, `error`.

## Test

Dalla cartella `backend`, con il venv attivo:

```powershell
.\.venv\Scripts\python -m unittest discover -s tests -v
```

## Limiti

- Una sessione vive solo nel processo del backend.
- Deepgram va provato con una chiave vera: i test non aprono il socket audio.
- La latenza del modello dipende dal provider. Il demo locale è immediato; un modello reasoning può superare i 2–6 secondi.
