// Wire types mirroring the backend /ws/demo protocol (mutualfund.realtime.router).

export interface DemoBar {
  time: number; // unix seconds (UTC)
  open: number;
  high: number;
  low: number;
  close: number;
}

export interface DemoSignal {
  time: number;
  side: "buy" | "sell";
  price: number;
  reason: string;
}

export interface SandboxPerf {
  equity: number;
  cash: number;
  position: number;
  net_pnl: number;
  return_pct: number;
  max_drawdown_pct: number;
  num_trades: number;
}

export type DemoMessage =
  | { type: "snapshot"; symbol: string; bars: DemoBar[] }
  | { type: "bar"; bar: DemoBar }
  | { type: "signal"; signal: DemoSignal }
  | { type: "perf"; perf: SandboxPerf };
