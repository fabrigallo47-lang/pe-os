import React, { useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { PantaApp } from '../src/app/PantaApp';
import { SyntheticAdapter } from '../tests/synthetic-adapter.mjs';
import '../src/design/global.css';
import './product-lab.css';

function SourceTrackingLab() {
  const [adapter, setAdapter] = useState();
  const [error, setError] = useState('');
  useEffect(() => {
    let active = true;
    async function load() {
      try {
        const response = await fetch('/api/source-tracking-lab');
        if (!response.ok) throw new Error('Start .venv/bin/python tools/source_tracking_lab.py to open the synthetic original files.');
        const { citations } = await response.json();
        const next = new SyntheticAdapter();
        for (const citation of citations) {
          let source = next.current.sources.find(item => item.id === citation.sourceId);
          if (!source) {
            source = { id: citation.sourceId, type: 'document', title: citation.filename };
            next.current.sources.push(source);
          }
          source.currentVersionId = citation.sourceVersionId;
          next.current.sourceVersions.push({ id: citation.sourceVersionId, sourceId: source.id, contentHash: citation.sourceVersionId, knownAt: '2026-01-10', permissionScope: 'CASE' });
          let claim = next.current.claims.find(item => item.id === citation.claimId);
          if (!claim) {
            claim = { id: citation.claimId, label: citation.filename, normalizedStatement: 'Synthetic native document', type: 'document' };
            next.current.claims.push(claim);
          }
          Object.assign(claim, { sourceId: source.id, sourceVersionId: citation.sourceVersionId, locator: citation.locator, verbatimOrLosslessSpan: citation.verbatimOrLosslessSpan });
        }
        // Demonstrate a calculated number and its existing source-reference path.
        Object.assign(next.current.quantities[0], { sourceObjectIds: ['CL-8'], formula: "'Financing Plan'!B2", perimeter: { period: '2026', scope: 'Current round', scenario: 'Base' } });
        next.searchCase = async (_caseId, query) => [
          ...next.current.quantities.map(item => ({ objectId: item.id, label: item.label, kind: 'quantity' })),
          ...next.current.claims.map(item => ({ objectId: item.id, label: item.label, kind: 'claim' })),
          ...next.current.sources.map(item => ({ objectId: item.id, label: item.title, kind: 'source' })),
        ].filter(item => query.trim() && item.label.toLowerCase().includes(query.trim().toLowerCase()));
        if (active) setAdapter(next);
      } catch (cause) { if (active) setError(cause.message); }
    }
    void load();
    return () => { active = false; };
  }, []);
  return <div className="p-product-lab"><aside className="p-lab-mode-bar"><div className="p-lab-identity"><span>LAB</span><strong>Source tracking</strong></div><p>Synthetic case · original files in an isolated temporary vault</p><a href="/">Product Lab</a></aside>{error ? <p role="alert">{error}</p> : adapter ? <PantaApp adapter={adapter} initialCaseId="CASE-1" /> : <p role="status">Loading source fixtures…</p>}</div>;
}

createRoot(document.getElementById('root')).render(<React.StrictMode><SourceTrackingLab /></React.StrictMode>);
