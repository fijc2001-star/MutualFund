import { useState } from "react";
import { SignalChart } from "./SignalChart";

const SYMBOLS = ["AAPL", "MSFT", "NVDA", "TSLA"];

export function App() {
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
      </header>
      <p className="subtitle">
        Fake bot signals streamed from the backend over WebSocket, plotted on
        TradingView Lightweight Charts.
      </p>
      {/* key forces a clean remount (new WS + fresh chart) on symbol change */}
      <SignalChart key={symbol} symbol={symbol} />
    </div>
  );
}
