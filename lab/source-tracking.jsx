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
        const { citations, typedClaims } = await response.json();
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
        // Explicit fictional full chain. These declarations are test records, never real judgments.
        next.current.claims.push(...typedClaims);
        const raise = typedClaims.find(item => item.locator.endsWith('## Euro raise'));
        next.current.sources.push({ id: 'SRC-TYPED', title: 'Synthetic financing statements', type: 'document', currentVersionId: raise.sourceVersionId });
        next.current.sourceVersions.push({ id: raise.sourceVersionId, sourceId: 'SRC-TYPED', contentHash: raise.sourceVersionId, knownAt: '2026-01-10T09:00:00Z', permissionScope: 'CASE' });
        next.current.quantities.push({ id: 'TEST-FORMULA', label: 'Twice the proposed primary raise', value: 10, unit: 'mm', currency: 'EUR', sourceObjectIds: [raise.id], formula: '2 × primary raise', perimeter: { period: 'FY2026', scope: 'primary round', basis: 'cash proceeds', scenario: 'Base' }, assumptionObjectIds: [], downstreamObjectIds: [], editable: false, institutionalState: 'CURRENT', freshnessStatus: 'CURRENT' });
        next.current.actors.push({ id: 'TEST-ANALYST', displayName: 'Test analyst', actorType: 'HUMAN' });
        next.current.humanPositions.push({ id: 'TEST-VIEW', text: 'Simulated view: verify the financing basis before approval.', authorActorId: 'TEST-ANALYST', recordedAt: '2026-01-10T10:00:00Z', scopeObjectId: 'Q-F', institutionalState: 'CURRENT' });
        next.current.relations.push({ id: 'TEST-SUPPORT', caseId: 'CASE-1', sourceObjectId: 'TEST-FORMULA', sourceObjectType: 'modelNode', targetObjectId: 'TEST-VIEW', targetObjectType: 'humanPosition', type: 'SUPPORTS', institutionalState: 'CURRENT', contractVersion: '0.1.0' });
        next.current.decisions.push({ id: 'TEST-DECISION', pathId: 'PATH-1', actorOrBodyId: 'TEST-ANALYST', rationale: 'Simulated decision: defer until the financing basis is verified.', recordedAt: '2026-01-10T11:00:00Z', basisObjectIds: ['TEST-VIEW'], caseVersion: next.current.caseVersion });
        // No inherited synthetic analysis for these records: the app reads only their declared references.
        const inheritedInspection = next.inspectObject.bind(next);
        next.inspectObject = async (caseId, objectId, options) => objectId.startsWith('TEST-') || objectId === 'SRC-TYPED' || objectId === raise.sourceVersionId || typedClaims.some(item => item.id === objectId)
          ? null : inheritedInspection(caseId, objectId, options);
        next.searchCase = async (_caseId, query) => [
          ...next.current.quantities.map(item => ({ objectId: item.id, label: item.label, kind: 'quantity' })),
          ...next.current.claims.map(item => ({ objectId: item.id, label: item.label, kind: 'claim' })),
          ...next.current.sources.map(item => ({ objectId: item.id, label: item.title, kind: 'source' })),
          ...next.current.humanPositions.map(item => ({ objectId: item.id, label: item.text, kind: 'humanPosition' })),
          ...next.current.decisions.map(item => ({ objectId: item.id, label: item.rationale, kind: 'decision' })),
        ].filter(item => query.trim() && item.label.toLowerCase().includes(query.trim().toLowerCase()));
        if (active) setAdapter(next);
      } catch (cause) { if (active) setError(cause.message); }
    }
    void load();
    return () => { active = false; };
  }, []);
  return <div className="p-product-lab"><aside className="p-lab-mode-bar"><div className="p-lab-identity"><span>LAB</span><strong>Source tracking</strong></div><p>Simulated extraction, analyst and decision · isolated test vault</p><a href="/">Product Lab</a></aside>{error ? <p role="alert">{error}</p> : adapter ? <PantaApp adapter={adapter} initialCaseId="CASE-1" /> : <p role="status">Loading source fixtures…</p>}</div>;
}

createRoot(document.getElementById('root')).render(<React.StrictMode><SourceTrackingLab /></React.StrictMode>);
