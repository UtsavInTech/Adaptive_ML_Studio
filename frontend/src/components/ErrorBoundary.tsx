/** A view that fails must say so — the run itself keeps going on the server and its data is saved. */

import { Component, type ErrorInfo, type ReactNode } from "react";

type Props = { children: ReactNode };
type State = { error: Error | null };

export default class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("UI error:", error, info.componentStack);
  }

  render() {
    const { error } = this.state;
    if (!error) return this.props.children;
    return (
      <div className="page">
        <div className="banner error">
          <div>
            <strong>This view failed to render.</strong> The run itself is unaffected — its measurements are stored on
            the server and can be opened from the Experiments tab.
            <div className="small mono">{error.message}</div>
          </div>
          <div className="spacer" />
          <button type="button" className="btn" onClick={() => this.setState({ error: null })}>Try again</button>
          <button type="button" className="btn" onClick={() => window.location.reload()}>Reload</button>
        </div>
      </div>
    );
  }
}
