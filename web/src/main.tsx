import React from 'react';
import {createRoot} from 'react-dom/client';
import App from './App';

createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);

if ('serviceWorker' in navigator && location.port !== '5173') {
  void navigator.serviceWorker.register('/sw.js');
}
