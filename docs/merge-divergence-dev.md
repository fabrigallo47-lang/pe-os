# dev branch divergence — what needs a decision

Local `dev` and `origin/dev` diverged from a common ancestor `b58f976`.
Origin has 11 commits not in the local history (Anto's); local has 26
(this session's GPU-deployment and extraction work). This documents every
real conflict found by attempting the merge, with reproducible evidence,
so the two implementation choices below can be decided rather than
guessed at.

Merge attempted on branch `_merge_probe` (not applied to `dev`). A
second branch, `xlsx-anto-compare`, points at `origin/dev` unmodified so
Anto's XLSX code can be run directly for the comparison below.

## Files that merge cleanly

Everything except the three below merges with no conflict — including
all of `evaluation/`, since that was already taken verbatim from
`origin/dev` earlier in this branch's history.

## 1. `requirements.txt` — trivial, no decision needed

Two unrelated additive dependencies:

```
<<<<<<< HEAD
python-docx          # test fixture builder for test_pan103_docx_tables.py
=======
mail-parser-reply==1.36
>>>>>>> origin/dev
```

Resolution: keep both. Neither conflicts with the other.

## 2. Email quote-stripping — built independently on both sides, needs a decision

Both branches fixed the same bug (a reply chain re-surfacing every
earlier message's full text as a new chunk) with different libraries.

**Local (`email_reply_parser`)** — `tools/extract_v2_physical.py`, function
`_strip_quoted_reply_history`. Has explicit handling, backed by tests
(`tools/test_pan104_email_quote_stripping.py`), for the case where a pure
forward with no new commentary would otherwise strip down to nothing.

**origin/dev (`mail-parser-reply`)** — function `_email_reply_body`, a
single call into the library's own `.replies[0].body`. Not evaluated for
the same edge cases here — would need to be checked against the same test
scenarios before trusting it in production.

**Not yet empirically tested against each other** the way the XLSX code
below was. If this matters, the same kind of side-by-side run (extract
each version's module directly, feed it the same `.eml`/`.mbox` fixtures,
diff the output) would settle it the same way.

## 3. XLSX semantics — built independently on both sides, WITH a found bug

Both branches carry their own pre-session PAN-102 work (local: `4cd9464`;
origin/dev: `1b69851`), fully duplicated: `_xlsx_merged_ranges` (different
signatures), `_xlsx_cell_role` vs `_xlsx_cell_semantic_role` (same idea,
different name), and two entirely different `test_pan102_xlsx_semantic_context.py`
files under the same filename testing each one's own implementation.

**This one was empirically tested** — both versions run directly against
the same real fixture, `evaluation/fixtures/documents/panta_financial_model.xlsx`
(confirmed byte-identical on both branches).

### Local output

```
A1=PANTA Financial Model Fixture | B1=PANTA Financial Model Fixture
A3=Metric | B3=Value
A4=Revenue (EUR m) [Metric] | B4=125 [Revenue (EUR m); Value]
A6=EBITDA (EUR m) [Metric] | B6=FORMULA(=B4-B5); cached=45 [EBITDA (EUR m); Value]
A7=Risk | B7=LOW
A8=Decision owner | B8=Maria Rossi
A9=Decision date | B9=2026-08-15 00:00:00
A12=Quarter | B12=Revenue (EUR m)
A13=Q1 [Quarter] | B13=10 [Q1; Revenue (EUR m)]
```

### origin/dev (Anto's) output, same fixture

```
A1=PANTA Financial Model Fixture [role=unclassified] | B1=PANTA Financial Model Fixture [role=unclassified]
A4=Revenue (EUR m) [role=unclassified] | B4=125 [header_path=PANTA Financial Model Fixture > Value > Revenue (EUR m); role=unclassified]
A6=EBITDA (EUR m) [role=unclassified] | B6=FORMULA(=B4-B5); cached=45 [header_path=PANTA Financial Model Fixture > Value > EBITDA (EUR m); role=formula]
A9=Decision date [role=unclassified] | B9=2026-08-15 00:00:00 [role=unclassified]
A12=Quarter [role=unclassified] | B12=Revenue (EUR m) [role=unclassified]
A13=Q1 [role=unclassified] | B13=10 [header_path=Maria Rossi > 2026-08-15 00:00:00 > Revenue (EUR m) > Q1; role=unclassified]
```

### The bug

Row 13 (`Q1`, in the **second**, unrelated table starting at row 12) gets
`header_path=Maria Rossi > 2026-08-15 00:00:00 > Revenue (EUR m) > Q1`.
"Maria Rossi" and the date are cell values from rows 8-9 of the **first**
table (`Decision owner`, `Decision date`) — a completely different block,
separated from the Quarter/Revenue table by two blank rows (confirmed
directly from the raw workbook, independent of either parser):

```
A7: 'Risk'            B7: 'LOW'
A8: 'Decision owner'  B8: 'Maria Rossi'
A9: 'Decision date'   B9: datetime(2026, 8, 15)
                                          <- blank rows 10-11
A12: 'Quarter'         B12: 'Revenue (EUR m)'
A13: 'Q1'              B13: 10
```

Anto's header-path recovery is carrying the last-seen values across the
blank-row table boundary instead of resetting at it. A claim about Q1
revenue would carry a header path implying it relates to a decision owner
and a decision date, which is wrong. The local implementation correctly
scopes to `[Q1; Revenue (EUR m)]` only.

Also noteworthy, lower severity: Anto's version tags every cell with
`[role=unclassified]` even when nothing was classified, which adds noise
without adding information; the local version only annotates a cell when
there's a real header path or a real formula/cross-sheet role to report.

## What needs a decision

1. **XLSX**: recommend keeping the local implementation given the found
   bug, unless Anto's version has since been fixed upstream of what
   `origin/dev` currently has, or has other advantages not visible from
   this specific fixture.
2. **Email quote-stripping**: not yet empirically compared the same way;
   recommend the same test-both-directly approach before deciding.
3. Whichever XLSX implementation is kept, the losing side's
   `test_pan102_xlsx_semantic_context.py` should be retired (it tests
   implementation details of the version not kept).

## How to reproduce this comparison yourself

```bash
git branch xlsx-anto-compare origin/dev   # Anto's code, unmodified
git show origin/dev:tools/extract_v2.py > /tmp/anto_extract_v2.py
python3 -c "
import sys; sys.path.insert(0, '/tmp')
import anto_extract_v2 as anto
from pathlib import Path
for c in anto.parse_xlsx(Path('evaluation/fixtures/documents/panta_financial_model.xlsx')):
    print(c.body)
"
```

Compare against the local implementation the same way, or just read
`tools/extract_v2_physical.py`'s `parse_xlsx` directly.
