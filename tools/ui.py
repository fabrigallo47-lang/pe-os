#!/usr/bin/env python3
"""Deal dashboard generator — renders a self-contained HTML projection of a deal
from the derived index. Read-only, zero external assets, zero network calls.

Usage:  python3 tools/ui.py <deal-id>     ->  docs/ui/<deal-id>.html
"""
from __future__ import annotations

import html
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from engine import load_transitions  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
import indexer  # noqa: E402
DB = indexer.DB

STATE_ORDER = [
    "S0_INTAKE", "S1_ACCESS_CLEARANCE", "S2_CASE_INGESTION", "S3_SCREENING_ASSESSMENT",
    "S4_QUESTION_PLANNING", "S5_DILIGENCE_ACTIVE", "S6_UNDERWRITING_VALUATION",
    "S7_INVESTMENT_DECISION", "S8_EXECUTION_DOCUMENTATION", "S9_CLOSING_ADMINISTRATION",
    "S10_MONITORING", "S11_REUNDERWRITING", "S12_EXIT_REALIZATION", "S13_CLOSED_ARCHIVE",
]

E = html.escape


def state_label(sid: str) -> str:
    return sid.split("_", 1)[1].replace("_", " ").title() if "_" in sid else sid


def fetch(con, deal, typ):
    rows = con.execute(
        "SELECT frontmatter, title FROM nodes WHERE type=? AND deal=? ORDER BY id", (typ, deal)
    ).fetchall()
    return [(json.loads(fm), title) for fm, title in rows]


def replay(events, transitions, crit_open):
    state, trail, held = "START", [], []
    for ev in events:
        kind = ev.get("kind")
        cands = [t for t in transitions if t["from"] in (state, "ANY") and kind in t["triggers"]]
        if not cands:
            trail.append((ev, state, None, False))
            continue
        t = cands[0]
        if t["to"] == "S7_INVESTMENT_DECISION" and crit_open:
            held.append(t)
            trail.append((ev, state, t, True))
            continue
        trail.append((ev, state, t, False))
        state = t["to"]
    return state, trail, held


def build(deal: str) -> Path:
    con = sqlite3.connect(DB)
    dl = fetch(con, deal, "deal")
    if not dl:
        sys.exit(f"deal '{deal}' not in index — run make index")
    dfm, dtitle = dl[0]

    questions = fetch(con, deal, "question")
    claims = fetch(con, deal, "claim")
    events = sorted(fetch(con, deal, "event"), key=lambda x: str(x[0].get("at", "")))
    crit_open = [q for q, _ in questions if q.get("critical") and q.get("state") in ("open", "reducing")]
    state, trail, held = replay([e for e, _ in events], load_transitions(), crit_open)

    by_subject: dict[str, list] = {}
    for fm, t in claims:
        by_subject.setdefault(fm.get("subject") or "—", []).append(fm)
    contras = {s: cs for s, cs in by_subject.items() if len({str(c.get("value")) for c in cs}) > 1}

    # ---------- fragments ----------
    def badge(txt, cls):
        return f'<span class="badge {cls}">{E(txt)}</span>'

    st_badge = {
        "open": ("open", "b-open"), "reducing": ("reducing", "b-red2"),
        "resolved": ("resolved", "b-green"), "accepted-unresolved": ("accepted unresolved", "b-gold"),
    }

    rail = []
    cur_idx = STATE_ORDER.index(state) if state in STATE_ORDER else -1
    for i, sid in enumerate(STATE_ORDER):
        cls = "done" if i < cur_idx else ("current" if i == cur_idx else "todo")
        rail.append(
            f'<li class="{cls}"><span class="dot" aria-hidden="true"></span>'
            f'<span class="snum">{E(sid.split("_")[0])}</span>'
            f'<span class="sname">{E(state_label(sid))}</span></li>'
        )

    kpis = [
        (str(sum(1 for q, _ in questions if q.get("state") in ("open", "reducing"))) + f" / {len(questions)}", "questions open"),
        (str(len(crit_open)), "critical blockers"),
        (str(len(contras)), "contradictions"),
        (str(len(claims)), "claims held"),
        (str(len(events)), "events recorded"),
    ]
    kpi_html = "".join(f'<div class="kpi"><div class="n">{E(v)}</div><div class="l">{E(l)}</div></div>' for v, l in kpis)

    guard_html = ""
    if held:
        t = held[0]
        guard_html = f"""
        <section class="guard" role="alert">
          <h2>Investment-committee gate held</h2>
          <p>Transition <strong>{E(t['id'])} → {E(state_label(t['to']))}</strong> was requested and refused:
          <strong>{len(crit_open)} critical question(s)</strong> remain open without risk acceptance.
          The deal cannot reach the decision until they are resolved — or a human explicitly accepts them, on the record.</p>
        </section>"""

    # question tree
    roots = [(q, t) for q, t in questions if not q.get("parent")]
    kids: dict[str, list] = {}
    for q, t in questions:
        p = q.get("parent")
        if p:
            pid = p.strip("[]").split("|")[0]
            kids.setdefault(pid, []).append((q, t))

    def q_card(q, title, depth=0):
        lbl, cls = st_badge.get(q.get("state"), (q.get("state", "?"), "b-open"))
        crit = badge("critical", "b-crit") if q.get("critical") else ""
        ws = f'<span class="ws">{E(q.get("target-workstream") or "")}</span>' if q.get("target-workstream") else ""
        sub = "".join(q_card(cq, ct, depth + 1) for cq, ct in kids.get(q.get("id"), []))
        return (f'<div class="qcard d{depth}"><div class="qrow"><h3>{E(title)}</h3>'
                f'<div class="qmeta">{badge(lbl, cls)}{crit}{ws}</div></div>{sub}</div>')

    qtree = "".join(q_card(q, t) for q, t in roots)

    # evidence
    ep_cls = {"asserted": "b-open", "derived": "b-red2", "observed": "b-green", "attested": "b-gold"}
    contra_html = ""
    for subject, cs in contras.items():
        cards = ""
        for c in sorted(cs, key=lambda x: x.get("epistemic", "")):
            src = c.get("source") or {}
            working = ' <span class="works">shows its working</span>' if c.get("derivation") else ""
            cards += (f'<div class="ecard"><div class="etop">{badge(c.get("epistemic","?"), ep_cls.get(c.get("epistemic"), "b-open"))}{working}</div>'
                      f'<div class="eval">{E(str(c.get("value","")))}</div>'
                      f'<div class="esrc">{E(str(src.get("locator","")))} · {E(str(src.get("author","")))} · {E(str(src.get("date","")))}</div></div>')
        contra_html += (f'<div class="contra"><div class="chead"><span class="cmark" aria-hidden="true">≠</span>'
                        f'<h3>{E(subject)}</h3><span class="cnote">these do not reconcile</span></div>'
                        f'<div class="egrid">{cards}</div></div>')

    # timeline
    tl = ""
    for ev, frm, t, blocked in trail:
        when, kind = str(ev.get("at", "")).replace("T", " · "), ev.get("kind", "?")
        if blocked:
            move = f'<span class="tmove thold">held at guard {E(t["id"])}</span>'
        elif t:
            move = f'<span class="tmove">{E(state_label(frm))} → {E(state_label(t["to"]))}</span>'
        else:
            move = '<span class="tmove tnull">recorded</span>'
        tl += (f'<li class="{"blocked" if blocked else ""}"><span class="tdot" aria-hidden="true"></span>'
               f'<div><div class="tkind">{E(kind)}</div><div class="twhen">{E(when)} · {E(str(ev.get("actor","")))}</div>{move}</div></li>')

    generated = datetime.now().strftime("%Y-%m-%d %H:%M")
    doc = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="robots" content="noindex, nofollow"><title>{E(dfm.get('id','deal'))} — Deal Intelligence</title>
<style>
:root {{
  --bg:#0b1622; --surface:#111f2e; --surface2:#17293c; --line:#22384e;
  --ink:#e9eff5; --muted:#9db0c2; --gold:#c9a24b; --green:#4fae7f; --red:#d4685f; --blue:#7fa8cf;
  --serif:"Iowan Old Style","Palatino Linotype",Palatino,Georgia,serif;
  --sans:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
  --mono:"SF Mono",Menlo,Consolas,monospace;
}}
*{{margin:0;padding:0;box-sizing:border-box}}
body{{background:var(--bg);color:var(--ink);font-family:var(--sans);font-size:16px;line-height:1.55;-webkit-font-smoothing:antialiased}}
.wrap{{max-width:1180px;margin:0 auto;padding:0 24px 80px}}
a{{color:var(--gold)}}
.topbar{{display:flex;justify-content:space-between;align-items:center;padding:18px 0;border-bottom:1px solid var(--line);font-size:12px;letter-spacing:.18em;text-transform:uppercase;color:var(--muted)}}
.topbar .wordmark{{color:var(--ink);font-family:var(--serif);font-size:17px;letter-spacing:.04em;text-transform:none}}
.topbar .wordmark b{{color:var(--gold);font-weight:600}}
header.deal{{padding:40px 0 8px}}
.crumb{{font-size:12px;letter-spacing:.16em;text-transform:uppercase;color:var(--gold);margin-bottom:14px;font-weight:600}}
h1{{font-family:var(--serif);font-weight:500;font-size:clamp(1.9rem,4vw,2.7rem);line-height:1.12;margin-bottom:10px}}
.thesis{{color:var(--muted);max-width:70ch;font-size:1.04rem}}
.statechip{{display:inline-flex;align-items:center;gap:8px;margin-top:16px;border:1px solid var(--gold);color:var(--gold);border-radius:99px;padding:7px 16px;font-size:12.5px;letter-spacing:.1em;text-transform:uppercase;font-weight:600}}
.statechip .pulse{{width:8px;height:8px;border-radius:50%;background:var(--gold)}}
@media (prefers-reduced-motion: no-preference){{.statechip .pulse{{animation:pu 2.6s ease-in-out infinite}}@keyframes pu{{0%,100%{{opacity:.45}}50%{{opacity:1}}}}}}
/* rail */
.rail{{list-style:none;display:flex;gap:0;overflow-x:auto;padding:30px 0 12px;border-bottom:1px solid var(--line)}}
.rail li{{position:relative;flex:1 0 84px;text-align:center;padding-top:18px}}
.rail li::before{{content:"";position:absolute;top:5px;left:-50%;width:100%;height:2px;background:var(--line)}}
.rail li:first-child::before{{display:none}}
.rail .dot{{position:absolute;top:0;left:50%;transform:translateX(-50%);width:12px;height:12px;border-radius:50%;background:var(--line);border:2px solid var(--line)}}
.rail li.done .dot{{background:var(--green);border-color:var(--green)}}
.rail li.done::before{{background:var(--green)}}
.rail li.current .dot{{background:var(--gold);border-color:var(--gold);box-shadow:0 0 0 5px rgba(201,162,75,.18)}}
.rail li.current::before{{background:var(--green)}}
.snum{{display:block;font-family:var(--mono);font-size:10.5px;color:var(--muted)}}
.sname{{display:block;font-size:10.5px;color:var(--muted);line-height:1.25;padding:0 4px}}
.rail li.current .sname,.rail li.current .snum{{color:var(--gold);font-weight:600}}
/* kpis */
.kpis{{display:grid;grid-template-columns:repeat(5,1fr);gap:14px;padding:26px 0}}
.kpi{{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:16px 18px}}
.kpi .n{{font-family:var(--serif);font-size:1.7rem;color:var(--ink);font-variant-numeric:tabular-nums}}
.kpi .l{{font-size:11.5px;letter-spacing:.12em;text-transform:uppercase;color:var(--muted);margin-top:2px}}
/* guard */
.guard{{border:1px solid var(--red);background:rgba(212,104,95,.07);border-radius:14px;padding:22px 26px;margin:6px 0 28px}}
.guard h2{{font-family:var(--serif);font-size:1.25rem;color:var(--red);margin-bottom:6px}}
.guard p{{color:var(--muted);max-width:80ch}} .guard strong{{color:var(--ink)}}
/* layout */
.cols{{display:grid;grid-template-columns:1.6fr 1fr;gap:28px;align-items:start}}
section h2.sec{{font-family:var(--serif);font-size:1.35rem;font-weight:500;margin:26px 0 14px}}
.badge{{display:inline-block;font-size:10.5px;letter-spacing:.09em;text-transform:uppercase;font-weight:600;border-radius:99px;padding:3px 10px;border:1px solid}}
.b-open{{color:#e0a49e;border-color:#8a5049}} .b-red2{{color:var(--blue);border-color:#3d5a77}}
.b-green{{color:var(--green);border-color:#2e6b4f}} .b-gold{{color:var(--gold);border-color:#8a7134}}
.b-crit{{color:var(--red);border-color:var(--red)}}
/* questions */
.qcard{{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:16px 18px;margin-bottom:12px}}
.qcard.d1{{margin-left:26px;background:var(--surface2)}} .qcard.d2{{margin-left:52px}}
.qrow{{display:flex;justify-content:space-between;gap:14px;align-items:baseline;flex-wrap:wrap}}
.qcard h3{{font-family:var(--serif);font-weight:500;font-size:1.06rem}}
.qmeta{{display:flex;gap:6px;align-items:center;flex-wrap:wrap}}
.ws{{font-family:var(--mono);font-size:10.5px;color:var(--muted)}}
/* evidence */
.contra{{background:var(--surface);border:1px solid var(--line);border-left:3px solid var(--red);border-radius:12px;padding:18px 20px;margin-bottom:16px}}
.chead{{display:flex;align-items:baseline;gap:10px;margin-bottom:12px;flex-wrap:wrap}}
.cmark{{color:var(--red);font-size:1.2rem;font-weight:700}}
.chead h3{{font-family:var(--serif);font-weight:500;font-size:1.1rem}}
.cnote{{font-size:11.5px;letter-spacing:.1em;text-transform:uppercase;color:var(--red)}}
.egrid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px}}
.ecard{{background:var(--surface2);border:1px solid var(--line);border-radius:10px;padding:12px 14px}}
.eval{{font-family:var(--serif);font-size:1.25rem;margin:8px 0 4px;font-variant-numeric:tabular-nums}}
.esrc{{font-size:11.5px;color:var(--muted)}}
.works{{font-size:10.5px;color:var(--green);letter-spacing:.06em;text-transform:uppercase;font-weight:600}}
/* timeline */
.tline{{list-style:none;border-left:2px solid var(--line);margin-left:6px}}
.tline li{{position:relative;padding:0 0 20px 22px}}
.tdot{{position:absolute;left:-7px;top:5px;width:12px;height:12px;border-radius:50%;background:var(--green);border:2px solid var(--bg)}}
.tline li.blocked .tdot{{background:var(--red)}}
.tkind{{font-family:var(--mono);font-size:12.5px}}
.twhen{{font-size:11.5px;color:var(--muted);margin:2px 0}}
.tmove{{font-size:11.5px;color:var(--green)}} .thold{{color:var(--red);font-weight:600}} .tnull{{color:var(--muted)}}
footer{{border-top:1px solid var(--line);margin-top:44px;padding-top:22px;display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap;font-size:12px;color:var(--muted)}}
@media (max-width: 900px){{.cols{{grid-template-columns:1fr}}.kpis{{grid-template-columns:repeat(2,1fr)}}}}
</style></head>
<body><div class="wrap">
  <div class="topbar"><span class="wordmark"><b>◆</b> Deal Intelligence</span><span>Private &amp; Confidential</span></div>
  <header class="deal">
    <p class="crumb">Live deal · {E(dfm.get('company','').strip('[]'))}</p>
    <h1>{E(dtitle)}</h1>
    <p class="thesis">{E(dfm.get('thesis',''))}</p>
    <span class="statechip"><span class="pulse"></span>{E(state_label(state))} ({E(state.split('_')[0])})</span>
  </header>
  <ul class="rail" aria-label="Deal lifecycle state machine">{''.join(rail)}</ul>
  <div class="kpis">{kpi_html}</div>
  {guard_html}
  <div class="cols">
    <div>
      <section aria-labelledby="qh"><h2 class="sec" id="qh">Question structure</h2>{qtree}</section>
      <section aria-labelledby="ch"><h2 class="sec" id="ch">Contradictions — unresolved</h2>{contra_html or '<p class="thesis">None detected.</p>'}</section>
    </div>
    <div>
      <section aria-labelledby="th"><h2 class="sec" id="th">Event record</h2><ul class="tline">{tl}</ul></section>
    </div>
  </div>
  <footer><span>Generated {E(generated)} — read-only projection of the deal graph; state derived by event replay, never set by hand.</span><span>Confidential — not for distribution</span></footer>
</div></body></html>"""

    out = ROOT / "docs" / "ui" / f"{deal}.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(doc, encoding="utf-8")
    print(f"written {out.relative_to(ROOT)}")
    return out


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("usage: ui.py <deal-id>")
    build(sys.argv[1])
