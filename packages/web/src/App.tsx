import { useState } from "react";
import { AuthProvider, useAuth } from "./auth";
import { Login } from "./Login";
import { SignalChart } from "./SignalChart";

const SYMBOLS = ["AAPL", "MSFT", "NVDA", "TSLA"];

function Dashboard() {
  const { principal, logout } = useAuth();
  const [symbol, setSymbol] = useState("AAPL");

  return (
    <div className="app">
      <header className="app-header">
        <h1>MutualFund — Live Signal Prototype</h1>
        <div className="symbol-picker">
          {SYMBOLS.map((s) => (
            <button
              key={s}
              className={s === symbol ? "active" : ""}
              onClick={() => setSymbol(s)}
            >
              {s}
            </button>
          ))}
        </div>
        <div className="user-box">
          <span className="muted">
            {principal?.email} · {principal?.role}
          </span>
          <button onClick={() => void logout()}>Logout</button>
        </div>
      </header>
      <p className="subtitle">
        A live SMA-crossover <strong>bot</strong> (M3/M9) trading in the{" "}
        <strong>real sandbox</strong> (M5): each signal is risk-checked and guardrailed (M6)
        before it fills, every fill is recorded on the hash-chained ledger (M10), and the bot is
        qualified into a lifecycle state (M4) — all streamed over WebSocket onto Lightweight
        Charts.
      </p>
      {/* key forces a clean remount (new WS + fresh chart) on symbol change */}
      <SignalChart key={symbol} symbol={symbol} />
    </div>
  );
}

function Shell() {
  const { ready, principal } = useAuth();
  if (!ready) {
    return (
      <div className="app">
        <p className="muted">Loading…</p>
      </div>
    );
  }
  return principal ? <Dashboard /> : <Login />;
}

export function App() {
  return (
    <AuthProvider>
      <Shell />
    </AuthProvider>
  );
}
