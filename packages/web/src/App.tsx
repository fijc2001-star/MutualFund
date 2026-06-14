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
        A live SMA-crossover bot trading in the <strong>real sandbox</strong> (M5) — every
        fill is recorded on the hash-chained ledger (M10); fills and live P&amp;L stream over
        WebSocket onto TradingView Lightweight Charts.
      </p>
      {/* key forces a clean remount (new WS + fresh chart) on symbol change */}
      <SignalChart key={symbol} symbol={symbol} />
    </div>
  );
}
