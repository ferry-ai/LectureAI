/** A short lecture used when the microphone is off. Sentences are long enough to trigger analysis. */
export const DEMO_LECTURE = [
  "Oggi vediamo come una rete neurale impara dai dati attraverso la discesa del gradiente.",
  "La funzione di perdita misura la distanza tra la previsione del modello e l'etichetta corretta.",
  "Il gradiente di quella funzione indica la direzione in cui la perdita cresce più in fretta.",
  "Per migliorare il modello aggiorniamo i pesi nel verso opposto al gradiente, con un passo deciso dal tasso di apprendimento.",
  "Se il tasso di apprendimento è troppo alto la discesa del gradiente oscilla e non converge verso un minimo.",
  "La retropropagazione applica la regola della catena per calcolare il gradiente strato per strato, dall'output verso l'input.",
  "La regolarizzazione, per esempio il weight decay, penalizza pesi troppo grandi e riduce l'overfitting.",
  "Il set di validazione serve a controllare se il modello generalizza su esempi che non ha usato in addestramento.",
  "Quando la perdita di validazione sale mentre quella di training scende, il modello sta memorizzando il training set.",
  "Conviene allora fermare l'addestramento, rivedere il tasso di apprendimento oppure rafforzare la regolarizzazione.",
].join(" ");
