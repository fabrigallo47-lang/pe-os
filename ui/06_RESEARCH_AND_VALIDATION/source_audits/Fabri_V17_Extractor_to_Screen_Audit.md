# Extractor to Screen — scansione della superficie V17

**PANTA V17 · 27 agosto 2026 · base commit `ca9ec8d`**
Store al momento della scansione: 34 claim · 1.449 binding · 29.476 celle · 5 record.

L'estrattore funziona e i suoi risultati arrivano a schermo. Quello che c'è fra i
due è un guscio di presentazione consegnato come demo, e si vede: **zero campi di
input**, sei lenti che non fanno niente, e metà della logica già scritta nel
backend senza una rotta che la raggiunga.

| Critici | Maggiori | Minori | Input file | Rotte POST | Schermate vive |
|--------:|---------:|-------:|-----------:|-----------:|---------------:|
| 11 | 21 | 12 | 0 | 4 | 5 / 19 |

**Perimetro.** Questa scansione riguarda struttura, logica backend mancante o
interrotta, input e output, forzature e staticità. La qualità di ciò che
l'estrattore produce — se un valore è giusto, se un'etichetta è corretta, se due
esecuzioni concordano — è fuori perimetro e non compare qui.

**Severità.** *Critico* = un invariante dichiarato del progetto non è soddisfatto,
o una capacità che il prodotto dichiara di avere non esiste. *Maggiore* = una
capacità intera è assente. *Minore* = attrito o rifinitura.

---

## Se leggi solo cinque righe

| ID | | |
|:--|:--|:--|
| **[A1](#a1)** | Non c'è un campo di input in tutta la UI | L'unico modo di ingerire qualcosa è `curl`. Zero `<input type="file">`. |
| **[A3](#a3)** | Lo schermo non si aggiorna mai dopo un ingest | `loadCase()` è chiamata una volta sola, all'avvio. |
| **[B7](#b7)** | Il selettore di lente ha sei opzioni e nessun comportamento | Scrive una classe CSS che nessuna regola intercetta. |
| **[E1](#e1)** | `bears_on` è vuoto su tutti e 34 i claim | L'invariante 2 — l'evidenza si attacca alle domande, mai ai deal — non è soddisfatto. Il binder esiste e non è collegato. |
| **[E8](#e8)** | Niente di ciò che l'umano fa viene scritto | Nessuna rotta scrive nel vault. Ogni sessione riparte da zero. |

---

# A · Input: non c'è modo di mettere dentro niente

*6 punti — 3 critici, 3 maggiori*

L'intera superficie di input della UI è: un `select` per la lente, una checkbox
per i change set, una `textarea` per i commenti, un `select` per le menzioni, e la
barra di ricerca ⌘K. Cinque controlli, nessuno dei quali immette dati nel sistema.

### A1 — Nessun input per file, percorso o URL {#a1}
**Critico.**
`grep -c 'type="file"' render.js` → 0. Niente drag-and-drop, niente selettore,
niente campo per incollare un percorso. L'ingest esiste solo come rotta HTTP che
va colpita da terminale. Un prodotto la cui unica azione è ingerire documenti non
ha un modo di ingerire documenti.

*Dove:* `ui/app/src/render.js` — nessuna vista ha un form. La rotta
`POST /api/v1/ingest` è già pronta e accetta un percorso.

### A2 — La drop-zone del vault è invisibile alla UI
**Maggiore.**
`vault/inbox/` è la cartella di consegna prevista dall'architettura, e
`tools/watcher.py` esiste già. Nessuna rotta la elenca, nessuna vista la mostra:
un file lasciato lì non succede niente.

### A3 — Nessun aggiornamento dopo un ingest {#a3}
**Critico.**
`loadCase()` viene invocata una sola volta dentro `init()`. Non c'è polling, non
c'è SSE, non c'è un pulsante di refresh. Un'estrazione lanciata mentre la pagina
è aperta non compare finché non si ricarica a mano — e non c'è niente sullo
schermo che lo dica.

*Dove:* `ui/app/src/engine.js · init()`

### A4 — Un solo deal, cablato in tre posti
**Maggiore.**
`openDeal()` rifiuta esplicitamente qualsiasi cosa non sia `PROJECT-KEYSTONE`; lo
store è per-deal ma la UI non ha un selettore; il `case_id` è una costante nella
projection. Il prodotto è definito sul *tenere insieme tutti i workstream* — a
livello fondo non c'è nemmeno un secondo deal da tenere.

### A5 — Nessun giudizio umano raggiunge il vault
**Critico.**
I commenti finiscono in `localStorage` e basta —
`storage.set('panta-v17-comments', …)`. Si perdono con la cache del browser e non
arrivano mai al backend. Non c'è modo di correggere un campo, rifiutare un claim,
accettare un rilievo del gate, o annotare un oggetto. Il gate instrada 36 rilievi
alla revisione umana e la revisione umana non ha dove scrivere.

### A6 — I due input strutturati del prodotto non esistono a schermo
**Maggiore.**
L'invariante 1 dice: esattamente un input strutturato, la decomposizione della
tesi all'apertura (`/open-deal`), più il rituale decisionale (`/ic-record`).
Entrambi sono skill da riga di comando. La UI non ha né l'uno né l'altro.

---

# B · Output: vedi tutto o niente

*10 punti — 2 critici, 5 maggiori, 3 minori*

Nessun filtro, nessun ordinamento, nessuna ricerca dentro una stanza, nessuna
paginazione, nessun controllo temporale. Quello che decide cosa vedi è codice
Python nella projection, non l'utente.

### B1 — Zero filtri, su dati che ne chiedono almeno sei
**Maggiore.**
Ogni claim porta `epistemic`, `topic`, `period`, `perimeter`, `source_doc`,
`direction`, `author`. Nessuno di questi è filtrabile. Non si può nemmeno dire
«mostrami solo i bloccanti» sui 36 rilievi del gate.

### B2 — L'ordinamento è deciso in Python
**Minore.**
Foundations ordina per rango epistemico e poi per numero di claim, dentro
`live_projection._evidence_rooms()`. È un ordine ragionevole e non è quello di chi
guarda: non c'è modo di ordinare per valore, per periodo, o per quanto una metrica
è contesa.

### B3 — La paginazione manca e il troncamento è silenzioso
**Maggiore.**
Gli unknowns sono tagliati a 200 elementi in `live_projection` — `items[:200]` —
senza che la pagina dica di aver tagliato. Con 34 claim non si nota. Con un data
room vero è una perdita muta, cioè il tipo di difetto che questo sistema esiste
per non avere.

### B4 — Nessun controllo bitemporale, benché il backend ce l'abbia
**Maggiore.**
Il filtro `as_of` è implementato e verificato (F5). I claim portano `as_of` e
`period`. La UI non espone né l'uno né l'altro: non si può chiedere «cosa sapevamo
al 10 marzo».

### B5 — Da un aggregato non si scende alle sue prove
**Maggiore.**
Foundations elenca gli id dei claim come testo. Non sono cliccabili, non aprono
nulla, non portano al passaggio del PDF. Il numero c'è, la catena che lo regge no.

### B6 — La palette ⌘K cerca solo etichette e si ferma a 5
**Minore.**
`command()` filtra per sottostringa su label e tipo, poi `.slice(0,5)`. Non cerca
dentro gli statement, i locator, i valori o i perimetri — cioè dentro tutto ciò
che è stato estratto.

### B7 — Sei lenti, nessun comportamento {#b7}
**Critico.**
Il selettore offre `command · evidence · economics · work · relationships · time`.
`setLens()` mette il valore nello stato, il render scrive
`class="lens-${state.lens}"` su `<main>`, e nel CSS non esiste una sola regola
`.lens-*`. Sei promesse di riproiettare lo stesso stato, zero mantenute: è un
controllo che finge.

*Verificato:* `grep -c "lens-" style.css` → 1, ed è `.lens-select`, lo stile del
menu a tendina.

### B8 — Niente esce dallo schermo
**Minore.**
Nessun export, nessuna copia, nessun link permanente a un claim o a una cella. Il
locator `OWNERSHIP_RETURNS!K4` è stampato come testo: non si può cliccare,
copiare con un gesto, né mandare a qualcuno.

### B9 — La stanza delle fondamenta non sa rappresentare il disaccordo {#b9}
**Critico.**
Un foundation set ha un solo campo per il valore. Sette claim EBITDA che portano
sette coppie valore/perimetro diverse devono entrare in una riga, quindi la
projection ne elegge uno e gli altri sei scompaiono — non perché siano scartati,
ma perché non c'è uno slot dove metterli. La forza mostrata accanto è invece
calcolata sul gruppo intero, quindi le due metà della riga non descrivono lo
stesso claim.

Una stanza che si chiama *«su cosa poggia il deal»* e che può mostrare un solo
valore per metrica non può fare il suo lavoro: metriche contese e metriche
pacifiche hanno esattamente lo stesso aspetto. Serve una forma d'uscita che
regga N valori con i loro perimetri, non un rappresentante.

*Dove:* `tools/live_projection.py · _evidence_rooms()` — il campo `economic`
prende `valued[0]`. Introdotto in `539fb5d`, cioè da questa sessione.

### B10 — Una stanza mostra un registro col nome di un altro
**Maggiore.**
«Unknowns» è alimentata dai 36 rilievi del grounding gate. Un claim che il gate
non ha saputo verificare non è una cosa che non sappiamo del deal: è una cosa che
non sappiamo della nostra estrazione. Sono due registri distinti — incertezza di
dominio e incertezza di pipeline — e la projection li fonde in una stanza sola,
badge di navigazione compreso, perché non esiste una seconda destinazione dove
mandare i secondi.

---

# C · Statico: la pagina non ha stati

*6 punti — 1 critico, 3 maggiori, 2 minori*

Il guscio è stato scritto per una demo scriptata, dove niente tarda e niente
fallisce. Un ingest vero tarda quattordici secondi e a volte fallisce.

### C1 — Ogni cambio di stato ridisegna tutta la pagina
**Maggiore.**
`app.innerHTML = …` a ogni `patch()`, poi `bind()` riattacca ogni handler con
`document.querySelectorAll`. Si perdono posizione di scroll, focus e selezione del
testo. Su una lista di 36 righe non si vede; su un data room sì.

### C2 — Gli errori non hanno dove comparire
**Critico.**
L'unico stato d'errore è `patch({mode:'error'})` al bootstrap. Un ingest fallito
non produce niente a schermo: il campo `fix` della risposta — quello che spiega
cosa fare — non viene letto da nessuna vista. Se la chiave API manca, la UI resta
identica a come sarebbe se il documento non contenesse nulla.

### C3 — Nessuna attesa, nessun avanzamento
**Maggiore.**
C'è un unico flag `loading` globale, usato solo al primo caricamento. Il workbook
a freddo impiega 47 secondi (L1→L3 più il calcolo di 10.700 formule), il PDF 14.
Per tutto quel tempo la pagina è ferma e non dice niente.

### C4 — Lo stato della vista non sta nell'URL
**Maggiore.**
Nessun routing. Ricaricare riporta a Fund Command. Non si può mandare a un collega
«guarda questo unknown», né tornare indietro col tasto del browser, né mettere una
stanza nei preferiti.

### C5 — Nessuna gestione del focus, nessun annuncio
**Minore.**
Il drawer si apre senza spostare il focus e senza trappola; il cambio vista non è
annunciato ad alcuna `aria-live`; la navigazione è fatta di `<button>`, quindi non
c'è nulla da aprire in una scheda nuova.

### C6 — Tempi di animazione cablati
**Minore.**
`420ms`, o `30ms` in modalità moto ridotto, dentro `animateTransition()`. Il ritmo
della rivelazione delle conseguenze è una costante, non una funzione di quante ce
ne sono.

---

# D · Artefatti: un pilastro intero assente

*5 punti — 2 critici, 2 maggiori, 1 minore*

L'invariante 6 dice che gli artefatti non vengono mai copiati nel vault: i claim
ci puntano dentro. Se puntare dentro non porta da nessuna parte, l'invariante
regge la forma e perde lo scopo.

### D1 — La schermata artefatti è una tabella HTML scritta a mano
**Critico.**
`artifactsView()` contiene un `<table>` con dentro, letterali nel markup: «Firm
EBITDA $11.4m Inputs!B11», «Base MOIC 2.00x Ownership_Returns!K4», «Offer ceiling
$108.0m — Stale». Non è una vista di un workbook: è il disegno di un workbook, e i
suoi numeri non cambiano qualunque cosa si ingerisca.

### D2 — I file ingeriti non diventano artefatti
**Maggiore.**
Il manifest dello store registra nome, digest, dimensione e ora di ogni sorgente.
Nulla di questo diventa un artefatto apribile: le due sorgenti compaiono come due
righe nel Registry e finisce lì.

### D3 — 29.476 celle catturate, nessun modo di guardarne una
**Critico.**
L1 tiene ogni cella con formula e precedenti: 10.700 formule, 24.651 archi. A
schermo si legge MOIC 1.996 con accanto `OWNERSHIP_RETURNS!K4`, e non c'è modo di
aprire quella cella, vedere la formula, o risalire la catena. È il pezzo di lavoro
più costoso del compilatore ed è quello meno visibile.

### D4 — Nessun visualizzatore di pagina PDF
**Maggiore.**
Il locator `p5:w0-250` identifica pagina e intervallo di parole con precisione, e
resta una stringa. Verificare un claim contro la sua fonte richiede di aprire il
PDF a mano e contare.

### D5 — Nessuna storia delle versioni
**Minore.**
La fixture del pacchetto modellava versioni di artefatto con causa e stato. Lo
store sostituisce una sorgente reingerita con lo stesso percorso e non tiene la
precedente: non si può vedere che il workbook è cambiato, né cosa è cambiato.

---

# E · Backend: logica già scritta senza una rotta

*11 punti — 3 critici, 5 maggiori, 3 minori*

Questa è la sezione con più valore per unità di lavoro. Non manca il codice: manca
l'ultimo tratto fra un modulo funzionante e la schermata che lo aspetta.

### E1 — Invariante 2 non soddisfatto: l'evidenza non si attacca a niente {#e1}
**Critico.**
`bears_on` è `[]` su tutti e 34 i claim. «L'evidenza si attacca alle domande, mai
ai deal» è il secondo invariante non negoziabile del progetto, e il recupero per
domanda è quindi impossibile. Foundations raggruppa per metrica non perché sia
giusto, ma perché non c'è altro.

`tools/bind_questions_e3.py` fa esattamente questo, in due strati di regole
deterministiche, senza LLM. Non è collegato all'ingest.

*Costo:* una chiamata dentro `ingest_document`, dopo il gate.

### E2 — Dodici domande nel vault, zero sullo schermo
**Critico.**
`vault/deals/keystone/questions/` contiene dodici domande tipizzate, con stato,
criticità, workstream, tipo di domanda e prove già legate come `context` /
`contradicts` / `supports`. La projection live emette `question_spine: []`, quindi
Deal Command risulta permanentemente «assente» mentre il dato esiste già su disco.

### E3 — L'agente contraddizioni non gira mai sull'estrazione live
**Maggiore.**
L'estrattore emette `direction` su ogni claim — 14 contradicts, 6 supports, 14
context — cioè metà arco: la relazione senza il bersaglio. L'agente
`contradictions` esiste come skill e non ha una rotta. Shadow IC resta vuota
mentre il materiale per riempirla è già stato prodotto.

### E4 — `/admit` restituisce uno stub
**Maggiore.**
In modalità live la rotta risponde `NOT_ADMITTED` con una spiegazione. È corretto
— il motore di transizione è del runtime — ma vuol dire che S14–S18 sono
irraggiungibili, e `tools/transition_engine.py` esiste da questa parte.

### E5 — `/replay` risponde 501
**Minore.**
Dichiarato di proprietà del runtime, coerentemente. Ma `bootstrap` annuncia
`capabilities: [… "replay"]`: il server dice di saper fare una cosa che rifiuta di
fare.

### E6 — Quattro moduli maturi senza rotta
**Maggiore.**
`coverage_report.py` (copertura dichiarata), `identity_resolver.py`,
`position_model_binder.py` (F1 100%, 62/62 binding, zero LLM),
`case_compiler_alpha.py`. Tutti verificati, nessuno raggiungibile dalla UI.

### E7 — Quattro rotte POST in tutto
**Maggiore.**
`/ingest`, `/reset`, `/settle` (che registra e basta), `/admit` (stub). Non esiste
una rotta per: elencare le sorgenti, rimuoverne una, rilanciare uno stadio,
leggere un singolo claim, leggere una cella, leggere una domanda. Tutto passa
dalla projection intera, ricostruita da capo a ogni richiesta.

### E8 — Niente di ciò che l'umano fa viene scritto {#e8}
**Critico.**
`/settle` risponde `RECORDED_NOT_SETTLED` e non scrive nulla. Non c'è persistenza
per decisioni, ammissioni, rifiuti o annotazioni. Il vault è canonico e la UI non
ha modo di scriverci — quindi ogni sessione parte da zero, qualunque cosa sia
stata guardata prima.

### E9 — L'ingest blocca il thread HTTP
**Maggiore.**
Sincrono: 14s per il PDF, 47s per il workbook a freddo. Nessuna coda, nessun job
id, nessun avanzamento. Due ingest paralleli si contendono lo stesso store senza
lock, e `add_document` fa read-modify-write sui file JSON.

### E10 — `reset` è distruttivo, senza conferma né ritorno
**Minore.**
Azzera l'intero store. Nessuna conferma, nessun annullamento, nessuno snapshot. La
cache dei valori di cella, indicizzata per digest, non viene invece mai svuotata.

### E11 — Store monoutente, senza storia
**Minore.**
Un solo deal alla volta, nessuna nozione di chi ha ingerito cosa, nessun
append-only. Reingerire sostituisce in silenzio.

---

# F · Forzature: valori cablati dove dovrebbero esserci dati

*6 punti — 3 maggiori, 3 minori*

Non è la fixture rimasta accesa — quella è stata rimossa e verificata. Sono
costanti nel codice del guscio, in posti che sembrano alimentati dai dati.

### F1 — Il grafico della traiettoria è decorativo
**Maggiore.**
Nello Scenario Lab, sotto un asse etichettato «Economics» e sopra le tacche
«Entry · Operations · Cash · Debt · Exit», ci sono cinque punti a posizioni fisse:
`--p:8%`, `31%`, `52%`, `73%`, `94%`. Sono identici per tutti e cinque gli scenari
e non derivano da nessun numero estratto. Ha la forma di un grafico dei ritorni e
non è collegato a niente.

### F2 — La navigazione ignora il contratto che il backend le manda
**Maggiore.**
`/bootstrap` restituisce `capabilities` e `case_ids`. `grep -c capabilities` sui
sette file del frontend → 0, e lo stesso per `case_ids`. L'handshake scarica un
contratto e lo butta. La barra laterale elenca sempre le stesse 19 schermate,
qualunque cosa il server dichiari di saper servire.

### F3 — Due soli elementi rivedibili, perché due chiavi sono cablate
**Maggiore.**
`render.js` ha due pulsanti di revisione con chiavi fisse, `"earnings"` e
`"concentration"`. La projection deve infilarci i primi due rilievi bloccanti per
farli comparire. Se domani ce ne fossero quindici, se ne vedrebbero due.

### F4 — Le selezioni iniziali sono id che in modalità live non esistono
**Minore.**
`selectedScenarioId:'base'`, `selectedQuestionId:'UQ-EARNINGS'`,
`selectedArtifactId:'ART-MODEL'`, `selectedSituationId:'SIT-KEYSTONE'`,
`selectedReplayId:'firm-initial'`. Gli scenari estratti si chiamano
`standalone-base`, `combined-risk` e così via: nessuna di queste cinque selezioni
combacia mai, e ogni vista cade sul fallback `|| lista[0]`. Funziona per caso, non
per costruzione.

### F5 — Cliccare un unknown apre un cassetto senza contenuto
**Minore.**
`data-question` porta un `claim_id`; `drawerContent()` lo cerca fra domande,
artefatti, persone e foundation set, non lo trova, e mostra l'id grezzo come
titolo con corpo vuoto. Non c'è un ramo per «l'oggetto è un claim».

### F6 — Il Registry mescola due registri
**Minore.**
Le righe di ingest vengono dalla projection; le righe di navigazione («Deal World
opened») le scrive il frontend in `localStorage`. Nello stesso elenco
«append-only» convivono fatti del compilatore e cronologia del browser,
distinguibili solo dall'attore.

---

# In che ordine

Il criterio non è la severità in astratto: è quanto ogni intervento sblocca. Le
prime tre voci accendono schermate che aspettano dati già presenti su disco, o
rendono usabile l'unica azione del prodotto. Costano poco perché il lavoro è quasi
tutto fatto.

1. **Collegare `bind_questions_e3` (E1) e servire le dodici domande (E2).**
   Soddisfa l'invariante 2 e accende Deal Command con dati che esistono già.
2. **Un campo di ingest e un refresh (A1, A3).** Un form con un percorso, la
   risposta a schermo, la projection ricaricata. È l'unica azione del prodotto e
   oggi passa da `curl`.
3. **Dare a Foundations una forma che regga N valori (B9).** Finché una metrica
   contesa e una pacifica hanno lo stesso aspetto, la stanza non fa il suo lavoro.
4. **Far girare l'agente contraddizioni (E3).** I `direction` sono già emessi;
   manca il bersaglio, che arriva col punto 1.
5. **Rendere navigabili celle e pagine (D3, D4).** Il lavoro più costoso del
   compilatore è quello che oggi non si vede.
6. **Una via di scrittura verso il vault (A5, E8).** Senza, il rituale decisionale
   non ha dove esistere e ogni sessione riparte da zero.

Quello che **non** è nell'elenco: riscrivere il guscio V17. C1 e C4 dicono che è
scritto per una demo, ed è vero, ma regge quello che gli si chiede finché le liste
restano corte. Diventa il problema quando i punti 1–6 sono fatti, non prima.

---

*44 punti · 11 critici · 21 maggiori · 12 minori*
