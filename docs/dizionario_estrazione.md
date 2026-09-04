# Dizionario di estrazione — termini, concetti, formule

File di lavoro, da espandere insieme. Ogni voce distingue **cosa esiste già
nello schema di produzione** da **cosa è stato osservato mancante su
documenti reali** — le due liste non vanno confuse: la prima è codice
vivo (`tools/extract_v2_physical.py`), la seconda è materiale grezzo per
decidere cosa promuovere.

---

## 1. Schema di produzione — enum vigenti oggi

### 1.1 METRIC_ENUM (65 voci + `Other`)

Fonte: `tools/extract_v2_physical.py:278`. Raggruppate qui per famiglia solo
per leggibilità — nel codice è una lista piatta.

**Conto economico**
Revenue · Recurring Revenue · Revenue Growth · Gross Profit · Gross Margin ·
EBITDA · EBITDA Margin · EBITDA Add-back · EBITDA Adjustment · EBIT ·
Net Income

**Cassa e capitale circolante**
Free Cash Flow · Operating Cash Flow · Capex · Working Capital · DSO · DPO ·
Inventory Days · Net Working Capital · Net Working Capital Target ·
Net Working Capital Adjustment

**Qualità dell'utile / QoE**
Earnings Quality Risk · Revenue Quality · Adjustment Supportability

**Cliente / commerciale**
Customer Concentration · Customer Count · Active Billing Accounts ·
Customer Retention · Contract Terms · Customer Contract Terms ·
Market Position · Market Size

**Valutazione**
Enterprise Value · Equity Value · Entry Multiple · Exit Multiple · Exit EV

**Debito e leva**
Net Debt · Gross Debt · Leverage · Interest Coverage · First-Lien Debt ·
Revolver Capacity · DDTL Availability · Covenant EBITDA ·
Covenant Threshold · Covenant Headroom

**Struttura del capitale**
Sponsor Equity · Seller Rollover

**Ritorni**
MOIC · IRR · Exit Horizon · Supported Price

**Persone / operazioni**
Headcount · Team Tenure · Acquisition Count

**Rischio**
Systems Integration Risk · Integration Risk · Operational Risk ·
Key Person Risk · Regulatory Risk · Competition Risk

**Governance / IC**
IC Conditions · IC Vote · Decision Coherence

**Valvola di sfogo (PAN-117)**
`Other` — richiede `metric_label` col nome vero del concetto. Mai messo in
`METRIC_VOCABULARY` di `tools/object_identity.py` di proposito: un claim
`Other` resta *unresolvable*, mai confrontato silenziosamente con un altro.

### 1.2 TOPIC_ENUM (9 + OTHER)

Fonte: `tools/extract_v2_physical.py:355`, derivato da `ARCHETYPE_PACK`
(non hardcoded qui — cambia se cambia l'archetipo).

COMMERCIAL_AND_MARKET · FINANCIAL_QOE · FINANCING_AND_LIQUIDITY ·
LEGAL_REGULATORY · MANAGEMENT_SPONSOR_AND_GOVERNANCE ·
MODEL_VALUATION_AND_RETURNS · OPERATIONS_TECHNOLOGY_AND_EXECUTION ·
TAX_AND_STRUCTURING · VALUE_CREATION_AND_OWNERSHIP_READINESS · OTHER

### 1.3 Le altre dimensioni di identità

| Enum | Valori | Cosa distingue |
|---|---|---|
| `EPISTEMIC_CLASS_ENUM` | asserted, observed, derived, attested | chi lo dice e con che autorità |
| `BASIS_ENUM` | SellerView, QoEView, FirmView, CovenantView, ReportedView, unspecified | sotto le rettifiche di quale parte |
| `SCOPE_ENUM` | consolidated, standalone, customer, segment, unspecified | confine economico |
| `SCENARIO_ENUM` | base, management, seller, upside, downside, unspecified | quale caso |
| `CLAIM_KIND_ENUM` | QUANTITATIVE, DEFINITION, CONDITION, ATTRIBUTION, NEGATIVE, CHARACTERISATION | tipo di asserzione |
| `BOUND_ENUM` | EXACT, AT_LEAST, AT_MOST, APPROXIMATE, RANGE, NONE | come leggere il numero |
| `DIRECTION_ENUM` | supports, contradicts, context | verso la tesi |
| `measurement` | testo libero, non enum | **quale fetta** della metrica — vedi §3, è la causa delle collisioni trovate oggi |

`UNIT_ENUM` (parziale, valuta+ratio+tempo): `$m £m €m` · `$m/year $m/quarter`
· `%` · `x` (multiplo) · `bps` · `days` · `headcount` · `turns` · valute
bare `$ £ €`.

---

## 2. Concetti mancanti — osservati su documenti reali, non ipotetici

Ogni riga qui è un'etichetta **`metric_label`** vista davvero in un run
reale di questa sessione (mai inventata per questo file). Formato:
etichetta osservata · valore/unità di esempio · documento sorgente.

### 2.1 Dominio LBO (Keystone) — buchi *dentro* il dominio per cui l'enum è stato scritto

Da `keystone_qoe_report.md` (schedule debt-like):

| Etichetta osservata | Esempio | Nota |
|---|---|---|
| Accrued interest | $0.10m | riga di debt-like schedule |
| Finance-lease obligations | $0.55m | |
| Deferred acquisition consideration | $1.10m | |
| Transaction bonuses and payroll taxes | $0.85m | |
| Unpaid seller transaction expenses | $0.90m | |
| Pre-closing income and payroll taxes | $0.55m | |
| Insurance and legal-tail liabilities | $0.25m | |
| Debt-like subtotal | $3.65m | totale della sezione — derivato |
| Acquired unrestricted cash | $4.20m | |
| Working capital normalization drivers | (nessun valore, CONDITION) | assunzione verificabile senza numero |

Da `keystone_firm_model_summary.md`:

| Etichetta osservata | Esempio | Nota |
|---|---|---|
| Model coverage period | "FY2023A-FY2025A historical, April-December 2026 stub..." | testo, non numero |
| Model case structure | (nessun valore) | descrittivo |
| Opening cash | $3.0m | manca da METRIC_ENUM come voce propria |
| Acquisition assumption | (nessun valore) | |
| Acquisition funding structure | (nessun valore) | |
| Cash funding for acquisition | $3.5m | |
| Sentinel acquisition close date | (data, no numero) | |

### 2.2 Dominio Venture/Growth (Silexara) — l'enum non copre proprio questo mondo

Da `SRC-06_GTM_and_Terms_Call` (round di finanziamento, pipeline commerciale):

| Etichetta osservata | Esempio | Nota |
|---|---|---|
| Funding round size | €6.0m | il "round" — non è Sponsor Equity |
| Pre-money valuation | €24.0m | non è Enterprise Value |
| Runway months / Runway target | 18–24 mesi | due run diversi, formulazione leggermente diversa — normalizzare |
| Northforge ownership stake (full draw scenario) | 30% | scenario esplicito nell'etichetta |
| Northforge ownership stake (lower case scenario) | 4% | idem |
| Pilot contract value | €8.000 | |
| Phase 2 contract value | €30.000 | |
| Steady-state annual price | €65.000 | |
| TerraLink partnership scope | (testo) | |
| Partnership and pilot status | (testo) | |
| Early conversations | 3 | conteggio, non valuta |
| Technical readiness horizon | 16 mesi | |
| Funding round status | (testo) | |
| Product development stage | (testo) | |
| Product scope and capabilities | (testo) | |
| Customer acquisition timeline for civil operators | 9 / 4 mesi | due valori, stesso concetto |
| Customer acquisition timeline for institutional buyers | 20 / 30 mesi | |
| Paid sites required (for 2027 revenue target) | 8 / 12 | conteggio siti, non revenue — collideva con `Revenue` prima di PAN-117 |
| Revenue composition assumption | (nessun valore, CONDITION) | |

Da `SRC-19_INDEPENDENT_CONTROLLED_VALIDATION_REPORT` (tecnico/prodotto):

| Etichetta osservata | Esempio | Nota |
|---|---|---|
| Instrumented [and independently validated] area | 18 ha | area di test misurata |
| Planning envelope area | 70 ha | area pianificata — stesso ordine di grandezza, concetto diverso |
| Heavy service vehicle range | 650 m | portata di rilevamento |
| Coverage uniformity across [test zones] | (nessun valore) | |

Da `SRC-21_MODEL_NODES.csv` (nodi di modello dichiarati dall'analista, non
dall'estrattore — vedi PAN-122): `detection_recall` (due perimetri diversi,
0.94 e 0.41), `customer_alert_delivery`, `production_revenue`,
`raw_data_retention_right`, `prime_led_cycle` (non ammesso).

### 2.3 Candidati alla promozione (ricorrono, non sono rumore)

Etichette che sono apparse **più di una volta** in run diversi — segnale che
non sono un caso isolato:
- **Pre-money valuation / Post-money valuation** (round venture — post-money
  non compare mai perché non viene mai derivato, vedi §3)
- **Runway** (mesi di liquidità residua — concetto ricorrente in ogni deal
  early-stage, oggi confuso una volta con `Exit Horizon`)
- **Opening cash / Cash funding for [event]** — pattern ricorrente anche
  dentro Keystone, non solo Silexara

### 2.4 Raccolto parziale — resto del corpus Silexara (16 fonti aggiuntive)

Girata l'estrazione reale su 16 delle fonti Silexara non ancora processate
(mancano solo i 2 PDF, che servono il pod GPU spento). Da `SRC-02_Founder_Call_1`:

| Etichetta osservata | Esempio | Nota |
|---|---|---|
| Paid permanent site deployment timeline | "May" | testo, non numero |
| Development partnership status | (nessun valore, ×2) | |
| Installed systems count | 70 | |
| Model accuracy in lab | 99% | |
| Production line stoppages per week | 2 | |
| Years of AI implementation experience on physical equipment | 4 | |

**Nota onesta**: per le altre 15 fonti ho pulito le directory di output
prima di salvare il dettaglio etichetta-per-etichetta (errore mio di
sequenza, non un limite del metodo). Restano solo i conteggi grezzi di
claim `Other` per fonte, veri ma senza dettaglio:

SRC-03: 18 · SRC-05: 13 · SRC-12: 18 · SRC-15: 14 · SRC-16: 5 · SRC-18: 11 ·
SRC-22: 2 — più altre fonti con conteggio non isolato pulitamente dal log.
**Totale grezzo: 90+ claim `Other` aggiuntivi nel solo resto del corpus
Silexara**, segno che il dominio venture ha molto più materiale da
promuovere di quanto §2.2 mostri finora. Da rifare con il dettaglio salvato
prima di ripulire, quando si vuole espandere davvero questa sezione.

---

## 3. Pattern di formula osservati

### 3.1 Cosa il valutatore sa eseguire oggi

`tools/model_evaluator.py` — whitelist AST: `+ - * / ** %` e parentesi, su
operandi già noti. Niente di più, per design (le espressioni arrivano da
fogli compilati, non è un confine di fiducia).

`tools/derivation_verifier.py` — stesso motore, applicato al campo
`derivation` in prosa dei claim. Estrae la catena numerica pura,
esegue, confronta contro il risultato dichiarato nel testo E contro il
valore salvato sul claim (possono discordare indipendentemente).

### 3.2 Forme di derivazione trovate realmente (non ipotizzate)

| Forma | Esempio reale | Verificabile oggi? |
|---|---|---|
| Somma/bridge | `10.2 + 0.35 + 0.25 + ... = 11.9` (bridge EBITDA) | ✅ |
| Sottrazione | `$8.4m − $7.7m = $0.7m` (scarto NWC) | ✅ |
| Media | `(21 + 50) / 2 = 35.5` (età media fatture) | ✅ |
| Catena a più hop | subtotale debito + subtotale debt-like = lordo; lordo − cassa = netto | ✅ (ogni hop singolarmente) |
| Rapporto/margine | EBITDA / Revenue (margine) | ✅ se i due numeri sono nel testo |
| Riferimento simbolico a cella | `C91 (Covenant net debt) / MAX(0.001, C97 (LTM covenant EBITDA))` | ❌ — nessun numero letterale, solo nomi di cella; il verificatore si astiene onestamente |
| Formula con funzione di foglio | `IF(balance>0, MIN(0.015, balance), 0)` | ❌ — `MAX`/`MIN`/`IF` fuori whitelist per design |
| XIRR / solver | flussi di cassa + date → tasso | ❌ — `evaluation_type` dichiarato non eseguibile, mai finto |
| Test di covenant | rapporto confrontato con soglia → Breach/Compliant | ⚠️ è una CONDITION, non un'equazione — non ancora coperto da nessun verificatore |

**Split reale misurato** su un campione di 86 claim derivati (run
`b575a2a7`): 37 con almeno un `=` ma comunque simbolici (nessun numero
letterale), 49 senza nemmeno un `=`. **Zero su 86 verificabili** col
verificatore attuale — un pattern completamente diverso da quello (con
numeri letterali in prosa) su cui il verificatore È stato validato (9
claim, 3 errori trovati). Sono due stili di derivazione che coesistono
nella pipeline senza che il prompt li distingua.

### 3.3 Cosa NON viene mai derivato, anche quando potrebbe

- **Post-money da pre-money + round** (Silexara: 24+6=30, mai nello stesso
  claim nonostante entrambi i numeri siano nello stesso chunk)
- **Crescita % da due valori assoluti** in prosa discorsiva (2027→2028,
  mai calcolata)

Pattern: la derivazione scatta quando il documento **stesso** sta facendo
il conto (una tabella con un bridge), non quando richiederebbe applicare
una regola di mestiere a numeri sparsi in una frase parlata. Vedi
`tools/experiments/README.md` per la misura completa — non è (ancora)
chiaro se sia un bug da correggere o un confine giusto tra estrazione e
modellazione.

---

## 4. Da espandere — sezioni aperte

*(vuote di proposito — riempiamole insieme)*

### 4.1 Altri tipi di deal da coprire
- [ ] Infrastruttura / project finance
- [ ] Immobiliare
- [ ] Credito diretto / private debt
- [ ] ...

### 4.2 Metriche venture da aggiungere formalmente
- [ ] Pre-money valuation / Post-money valuation
- [ ] Runway (mesi)
- [ ] Burn rate
- [ ] ARR / MRR
- [ ] Ownership / dilution per round
- [ ] ...

### 4.3 Formule da rendere verificabili
- [ ] Sintassi per riferimenti a cella con valore noto (oggi persi)
- [ ] `MAX`/`MIN`/`IF` — vale la pena estendere la whitelist, con cautela?
- [ ] Test di covenant come tipo di derivazione a sé (confronto + soglia → esito)

### 4.4 measurement — granularità mancanti trovate da PAN-124
- [ ] Livello di aggregazione cliente (billing-account vs ultimate-parent) — oggi indistinguibile
- [ ] Riga WIP-ledger per cliente nominato — oggi schiacciata sulla service line
- [ ] ...
