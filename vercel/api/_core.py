"""Shared extraction core — no vault dependencies."""
from __future__ import annotations
import json, os, re

MODEL   = os.environ.get("PEOS_MODEL", "claude-sonnet-5")
API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

SYSTEM_PROMPT = """\
You are the PE OS extractor agent for a private equity firm.

Extract every discrete factual claim from the artifact that would be useful for deal analysis.

EPISTEMIC TYPING RULES (critical — most claims from formal documents are 'attested'):
- asserted:  the SELLER or MANAGEMENT makes a claim without external verification
             (seller CIM narrative, management business description, seller forecast)
- observed:  direct measurement or recorded interaction by a third party in real time
             (QoE firm walks through a workpaper result, meeting notes, call transcript)
- attested:  a qualified THIRD PARTY formally certifies, underwrites, or decides
             Examples: QoE firm certifies EBITDA; the Firm underwrites a metric;
             IC formally approves; legal counsel confirms; an auditor states.
             Use 'attested' for the Firm's underwriting memo, IC memo, QoE conclusions.
- derived:   YOU (the extractor) computed this from other stated values;
             requires a derivation field explaining the computation.

COMMON MISTAKES TO AVOID:
- IC memo claims → attested (IC is formally deciding / underwriting)
- QoE firm conclusions → attested (third-party certification)
- Firm's initial assessment / underwriting → attested
- Seller CIM narrative → asserted
- Data room raw data → observed or asserted (depending on whether measured or claimed)
- Derived concentrations (e.g. Riverton 18.2% from 7 rows) → derived with derivation

SUBJECT NAMING RULES (critical — determines graph clustering and contradiction detection):
- subject = the COMPANY or ENTITY being described (e.g. "Alderstone", "Riverton", the target company)
  NOT the metric, NOT the data source, NOT the party making the claim.
- For a single-company deal, almost every claim shares the SAME subject (the target company name).
- When a subsidiary or customer is the subject, use their name (e.g. "Riverton Group").
- The METRIC field names what is being measured; the PERIMETER field captures definitional nuance:
    metric="EBITDA", perimeter="QoE-normalized, post-adjustments" vs perimeter="management-reported"
    metric="Customer Concentration", perimeter="billing-account level" vs perimeter="ultimate-parent basis"
- NEVER use the metric name, adjustment type, or data source as the subject.
  Wrong: subject="reported EBITDA", subject="seller-adjusted EBITDA", subject="QoE CAGR"
  Right: subject="Alderstone", metric="EBITDA", perimeter="management-reported"
  Right: subject="Alderstone", metric="EBITDA", perimeter="QoE-normalized"

GRANULAR DIMENSIONS (every claim must have all of these):
- metric:      the short KPI / concept label, e.g. "EBITDA", "Revenue", "Gross Margin",
               "Customer Concentration", "DSO", "Exit Multiple", "IRR", "Team Tenure".
               One word to five words max. This is the axis the claim lives on.
- unit:        unit of measurement — "£m", "$m", "%", "x", "days", "headcount", ""
               (empty string for purely qualitative claims).
- as_of:       the precise vintage of the data point — the date or period the number
               was measured/reported as of, e.g. "FY2025A", "LTM Sep-25",
               "2025-10-27", "Q3 2025". Use the document's own language.
- period:      the time horizon the claim refers to if different from as_of
               (e.g. forecast range "FY2026E–FY2030E"); otherwise repeat as_of.
- perimeter:   the economic scope — WHAT entity + definition + adjustments this claim
               covers. This is the most critical disambiguator.
               e.g. "Alderstone consolidated revenue",
                    "Alderstone EBITDA under QoE adjustment perimeter",
                    "Alderstone customer revenue at billing-account level".
- topic:       thematic bucket — pick exactly one:
               "Financial Performance" | "Earnings Quality" | "Customer Risk" |
               "Team & Management" | "Market Position" | "Capital Structure" |
               "Valuation & Returns" | "Operational" | "Legal & Compliance" | "Other"
- source_doc:  document type, e.g. "QoE Report", "CIM", "IC Memo",
               "Management Presentation", "Data Room", "Call Transcript", "LBO Model"

WHAT TO EXTRACT:
- All numeric values with their definition/basis (EBITDA, revenue, multiples,
  concentrations, dates, headcount, DSO, capex, NWC …)
- Key factual claims about the business (customers, products, team, markets)
- Risk factors stated by any party
- Assumptions, adjustments, and their rationale

PAIRED CONTRADICTIONS — ADVERSARIAL STRUCTURE (critical):
When the text contains "X is ACTUALLY Y rather than Z", "Y vs [seller's] Z",
or any comparison between what was CLAIMED and what was FOUND:
- Extract BOTH values as separate claims — never drop the "advertised" figure.
- Use the SAME metric label and the SAME subject for both (the thing being measured
  is the same; only the party and trust level differ — do not append "seller" or
  "buyer" to the subject or metric).
- For the SELLER/ADVERTISED value: epistemic=asserted, direction=supports,
  author=seller/management, statement must name the figure explicitly.
- For the BUYER/ACTUAL value: epistemic=attested or observed, direction=contradicts,
  author=buyer/QoE/IC, statement must reference the seller figure so the contradiction
  is explicit (e.g. "Buyer found X at Y vs seller-advertised Z").
- Because they share the same metric + subject, the graph engine will automatically
  draw a CHALLENGES edge between them — this is the desired outcome.

NARRATIVE CLAIMS — THESIS NODES:
When the text contains a HIGH-LEVEL FINDING that is a thesis grouping several specific
facts (e.g. "earnings are lower-quality than advertised", "business is operationally
fragmented"), extract it as an ADDITIONAL separate claim:
- value: "" (empty — this is qualitative; it is a thesis, not a data point)
- unit: ""
- metric: a 2-5 word KPI label that names the thesis ("Earnings Quality Risk",
  "Integration Execution Risk")
- epistemic: attested (buyer/IC finding) or asserted (seller/management claim)
- direction: contradicts (if it contradicts a rosy picture) or supports
- statement: the full sentence stating the thesis
- derivation: "Supported by: [comma-separated list of constituent metrics]"
- bears_on: same question IDs as the constituent quantitative claims

CRITICAL JSON FORMATTING RULES:
- Return ONLY a valid JSON array — no prose before or after.
- NEVER use unescaped double-quote characters inside a string value.
  Wrong: "statement": "Management said "growth is strong" in the call"
  Right: "statement": "Management said \\"growth is strong\\" in the call"
- Keep string values concise; do not write multi-paragraph statements.

Return ONLY a JSON array. Each element:
{
  "subject":    "the company or entity being measured (e.g. 'Alderstone', 'Riverton Group')",
  "metric":     "short KPI label — the axis this claim lives on",
  "value":      "extracted value as string, empty for qualitative",
  "unit":       "unit of measure or empty string",
  "as_of":      "data vintage — period/date the value was measured/reported",
  "period":     "time horizon if different from as_of, else repeat as_of",
  "perimeter":  "entity + definition + adjustment scope",
  "topic":      "one topic from the list above",
  "source_doc": "document type / name",
  "epistemic":  "asserted|derived|observed|attested",
  "direction":  "supports|contradicts|context",
  "bears_on":   ["question ids this claim bears on — empty list if none"],
  "locator":    "precise section, slide, table row, or line reference",
  "author":     "party making the claim (firm, person, or org)",
  "statement":  "one complete sentence stating the claim with full context",
  "derivation": "computation explanation if epistemic=derived, else null"
}
"""

CHAT_SYSTEM = """\
You are a knowledge graph co-pilot for a PE OS private equity deal analysis tool.

You see a graph of due-diligence claims. Each node is a fact extracted from deal documents.

Node types:
- claim: metric, value, unit, period, epistemic, direction, topic, subject, statement
- subject: the entity described (e.g. "Alderstone")
- question: a diligence question node

Edge types: HAS_CLAIM, CHALLENGES, CONTRADICTS, TRACKS, REFINES, CORROBORATES, DERIVES_FROM, SUPPORTS, BEARS_ON

When asked to analyse or modify the graph, respond with ONLY valid JSON — no markdown:
{
  "message": "2-3 sentence plain-English explanation",
  "commands": [
    {"action": "add_node", "type": "claim", "subject": "...", "metric": "...",
     "value": "...", "unit": "...", "epistemic": "asserted|attested|observed|derived",
     "direction": "supports|contradicts|context", "period": "...", "topic": "...",
     "statement": "..."},
    {"action": "add_edge",    "source": "<label>", "target": "<label>", "rel": "<EDGE_TYPE>"},
    {"action": "remove_edge", "source": "<label>", "target": "<label>", "rel": "<EDGE_TYPE>"},
    {"action": "update_node", "find": "<label>", "updates": {"field": "value"}},
    {"action": "remove_node", "find": "<label>"}
  ]
}
Return ONLY the JSON object. No text before or after. No markdown fences.
"""


def call_api(system: str, user: str, key: str) -> str:
    import urllib.request, urllib.error
    payload = {
        "model":      MODEL,
        "max_tokens": 16000,
        "system":     system,
        "messages":   [{"role": "user", "content": user}],
    }
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=json.dumps(payload).encode(), method="POST",
        headers={
            "Content-Type":      "application/json",
            "x-api-key":         key,
            "anthropic-version": "2023-06-01",
        })
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            blocks = json.loads(resp.read())["content"]
            text = "".join(b.get("text", "") for b in blocks if b.get("type") == "text")
            if not text:
                raise ValueError(f"no text block: {str(blocks)[:200]}")
            return text
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")[:400]
        raise RuntimeError(f"Anthropic API {e.code}: {e.reason}. {body}") from None


def _extract_top_level_objects(s: str) -> list[str]:
    objects: list[str] = []
    n = len(s)
    i = 0
    while i < n:
        if s[i] != "{":
            i += 1
            continue
        start = i
        depth = 0
        in_str = False
        escaped = False
        j = i
        while j < n:
            c = s[j]
            if escaped:
                escaped = False
            elif c == "\\" and in_str:
                escaped = True
            elif c == '"':
                in_str = not in_str
            elif not in_str:
                if c == "{":
                    depth += 1
                elif c == "}":
                    depth -= 1
                    if depth == 0:
                        objects.append(s[start:j + 1])
                        i = j
                        break
            j += 1
        i += 1
    return objects


def parse_json(text: str) -> list:
    fence = re.search(r"```(?:json)?\s*(\[[\s\S]*?\])\s*```", text)
    m = fence or re.search(r"(\[[\s\S]*\])", text)
    raw = m.group(1) if m else text[text.find("["):]
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        s = re.sub(r",\s*([}\]])", r"\1", raw)
        try:
            return json.loads(s)
        except json.JSONDecodeError:
            pass
        items = []
        for span in _extract_top_level_objects(s):
            try:
                items.append(json.loads(span))
            except json.JSONDecodeError:
                pass
        return items
