import React from "react";

type State = { error: Error | null };

export class AppErrorBoundary extends React.Component<
  { children: React.ReactNode },
  State
> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    console.error("SynthPost Studio render failed", error, info);
  }

  render() {
    if (this.state.error) {
      return (
        <main className="empty-state" role="alert" style={{ marginTop: 80 }}>
          <div className="empty-state-title">Studio could not render this view</div>
          <p className="empty-state-desc">{this.state.error.message}</p>
          <button onClick={() => window.location.reload()}>Reload Studio</button>
        </main>
      );
    }
    return this.props.children;
  }
}
