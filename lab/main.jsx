import React, { useEffect, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { PantaApp } from '../src/app/PantaApp';
import { buildRouteHash, parseRouteLocation } from '../src/app/routes';
import { emptyAdapter } from '../src/providers/emptyAdapter';
import { SyntheticAdapter } from '../tests/synthetic-adapter.mjs';
import { EMPTY_CASE_ID, EmptyCaseAdapter } from './empty-case-adapter.mjs';
import '../src/design/global.css';
import './product-lab.css';

const SYNTHETIC_CASE_ID = 'CASE-1';
const syntheticAdapter = new SyntheticAdapter();
const emptyCaseAdapter = new EmptyCaseAdapter();

function readInitialMode() {
  const mode = new URLSearchParams(window.location.search).get('labCase');
  return mode === 'none' || mode === 'empty' || mode === 'synthetic' ? mode : 'synthetic';
}

function canonicalLocation(mode, requested = parseRouteLocation(window.location.hash)) {
  if (mode === 'none') return { route: 'deal', context: {} };
  if (mode === 'empty') return { route: 'formation', context: { caseId: EMPTY_CASE_ID } };
  return { route: requested.route, context: { ...requested.context, caseId: SYNTHETIC_CASE_ID } };
}

function replaceLabLocation(mode, location) {
  const url = new URL(window.location.href);
  url.searchParams.set('labCase', mode);
  url.hash = buildRouteHash(location.route, location.context);
  if (url.href !== window.location.href) window.history.replaceState(null, '', url);
}

const initialMode = readInitialMode();
replaceLabLocation(initialMode, canonicalLocation(initialMode));

function ProductLab() {
  const [mode, setMode] = useState(initialMode);
  const syntheticLocation = useRef(initialMode === 'synthetic'
    ? parseRouteLocation(window.location.hash)
    : { route: 'deal', context: {} });
  const adapter = mode === 'synthetic' ? syntheticAdapter : mode === 'empty' ? emptyCaseAdapter : emptyAdapter;

  useEffect(() => {
    const syncMode = () => {
      const nextMode = readInitialMode();
      const location = canonicalLocation(nextMode);
      if (nextMode === 'synthetic') syntheticLocation.current = location;
      replaceLabLocation(nextMode, location);
      setMode(nextMode);
    };
    window.addEventListener('popstate', syncMode);
    return () => window.removeEventListener('popstate', syncMode);
  }, []);

  const switchMode = (nextMode, requestedSyntheticRoute) => {
    if (nextMode === mode) return;
    const location = parseRouteLocation(window.location.hash);
    if (mode === 'synthetic') syntheticLocation.current = location;
    const requested = nextMode === 'synthetic'
      ? requestedSyntheticRoute
        ? { route: requestedSyntheticRoute, context: {} }
        : syntheticLocation.current
      : location;
    replaceLabLocation(nextMode, canonicalLocation(nextMode, requested));
    setMode(nextMode);
  };

  return <div className={`p-product-lab is-${mode}`}>
    <aside className="p-lab-mode-bar" aria-label="Product Lab case mode">
      <div className="p-lab-identity"><span>LAB</span><strong>Product Lab</strong></div>
      <div className="p-lab-mode-switch" role="group" aria-label="Choose development case mode">
        <button type="button" aria-pressed={mode === 'none'} onClick={() => switchMode('none')}>No case</button>
        <button type="button" aria-pressed={mode === 'empty'} onClick={() => switchMode('empty')}>Empty case</button>
        <button type="button" aria-pressed={mode === 'synthetic'} onClick={() => switchMode('synthetic')}>Synthetic case</button>
      </div>
      <p aria-live="polite">{mode === 'synthetic' ? 'Viewing synthetic fixture data' : mode === 'empty' ? 'Viewing a new case before material' : 'No case is selected'}</p>
    </aside>
    <PantaApp
      key={mode}
      adapter={adapter}
      initialCaseId={mode === 'synthetic' ? SYNTHETIC_CASE_ID : mode === 'empty' ? EMPTY_CASE_ID : undefined}
      onStartNewCase={() => switchMode('empty')}
      onOpenExistingCase={() => switchMode('synthetic', 'deal')}
    />
  </div>;
}

createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <ProductLab />
  </React.StrictMode>,
);
