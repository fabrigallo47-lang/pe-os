# Schema: Artifact

A document that arrived in the vault. First-class node — claims point to it; it never gets copied. The document stays where it landed (inbox path or external URL); this record is the graph anchor.

## Frontmatter

```yaml
---
type: artifact
id: art-<deal>-<slug>          # e.g. art-keystone-qoe-2026
deal: "[[keystone]]"
title: "Quality of Earnings Report — Keystone, Jan 2026"
kind: deck | model | transcript | email | report | contract | vdr-document | data-room-index
digital-source: "vault/inbox/keystone_qoe_jan2026.md"   # local path or external URL
url: null                       # permanent external URL if available (e.g. VDR permalink)
received: 2026-01-15            # date vault received it
source-date: 2026-01-10         # date the document was produced / signed
author: "Big4 Advisory LLP"     # free-text author name
author-entity: "[[big4-advisory]]"   # wikilink to entity node (company or person)
company: "[[keystone-project]]"      # the company being described in the document
page-count: null
written-by: extractor
---
```

## Relationship to claims

Claims carry `artifact-id: "[[art-keystone-qoe-2026]]"` pointing here.  
This lets the graph answer: *which claims came from this document?* and *which documents bear on this question?*

## Body

One-line description of what the document contains and its significance.
The extractor appends a list of extracted claim IDs after ingestion.

### Claims extracted
<!-- extractor appends: - [[c-keystone-NNN]] subject: … -->
