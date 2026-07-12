import React from 'react';
import {createRoot} from 'react-dom/client';
import App from './App';

class StudioErrorBoundary extends React.Component<
  React.PropsWithChildren,
  {failed: boolean}
> {
  state = {failed: false};

  static getDerivedStateFromError() {
    return {failed: true};
  }

  componentDidCatch(error: unknown) {
    console.error('SynthPost Studio render failed', error);
  }

  render() {
    if (!this.state.failed) return this.props.children;

    return (
      <main className="studio-crash-screen">
        <div className="studio-crash-card">
          <span className="studio-crash-kicker">Studio recovery</span>
          <h1>This screen could not be displayed</h1>
          <p>
            SynthPost hit an interface error. Reload to reconnect without
            changing any episode or render data.
          </p>
          <button type="button" onClick={() => window.location.reload()}>
            Reload Studio
          </button>
        </div>
      </main>
    );
  }
}

createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <StudioErrorBoundary>
      <App />
    </StudioErrorBoundary>
  </React.StrictMode>,
);

if ('serviceWorker' in navigator && location.port !== '5173') {
  void navigator.serviceWorker.register('/sw.js');
}
