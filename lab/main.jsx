import React from 'react';
import { createRoot } from 'react-dom/client';
import { PantaApp } from '../src/app/PantaApp';
import { SyntheticAdapter } from '../tests/synthetic-adapter.mjs';
import '../src/design/global.css';

const adapter = new SyntheticAdapter();

createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <PantaApp adapter={adapter} initialCaseId="CASE-1" />
  </React.StrictMode>,
);
