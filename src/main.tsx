import React from 'react';
import { createRoot } from 'react-dom/client';
import { PantaApp } from './app/PantaApp';
import { emptyAdapter } from './providers/emptyAdapter';
import './design/global.css';

createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <PantaApp adapter={emptyAdapter} />
  </React.StrictMode>,
);
