import React from 'react';
import { createRoot } from 'react-dom/client';
import { PantaApp } from './app/PantaApp';
import { createConnectedSimulationsAdapter } from './providers/connectedSimulations';
import './design/global.css';

const initialCaseId = new URLSearchParams(window.location.hash.split('?')[1] ?? window.location.search).get('caseId') ?? undefined;
if (!window.location.hash) window.history.replaceState(null, '', '#/simulate');
const adapter = createConnectedSimulationsAdapter(initialCaseId);

createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <PantaApp adapter={adapter} initialCaseId={initialCaseId} />
  </React.StrictMode>,
);
