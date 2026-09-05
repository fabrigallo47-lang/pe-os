import React from 'react';
import { createRoot } from 'react-dom/client';
import { PantaApp } from '../src/app/PantaApp';
import { createConnectedSimulationsAdapter } from '../src/providers/connectedSimulations';
import '../src/design/global.css';
import './product-lab.css';

if (!window.location.hash) window.history.replaceState(null, '', '#/simulate?caseId=SIMULATION-TEST');
const adapter = createConnectedSimulationsAdapter('SIMULATION-TEST');
createRoot(document.getElementById('root')).render(<React.StrictMode><div className="p-product-lab">
  <aside className="p-lab-mode-bar"><div className="p-lab-identity"><span>LAB</span><strong>Simulation · fictional model · real deterministic calculation</strong></div><span>No live case is changed</span></aside>
  <PantaApp adapter={adapter} initialCaseId="SIMULATION-TEST" />
</div></React.StrictMode>);
