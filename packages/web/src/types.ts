// Wire types mirroring the backend /ws/sandbox protocol (mutualfund.realtime.sandbox_session).

export interface DemoBar {
  time: number; // unix seconds (UTC)
  open: number;
  high: number;
  low: number;
  close: number;
}

// Why a signal fired — streamed with each fill so a trade can always be explained (M9).
export interface Rationale {
  thesis: string;
  indicators: string[];
  invalidation: string | null;
}

export interface DemoSignal {
  time: number;
  side: "buy" | "sell";
  price: number;
  reason: string;
  rationale?: Rationale | null;
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

export type OrderAction = "buy" | "sell" | "close";

// An order rejected before execution by the risk model or a hard guardrail (M6).
export interface BlockedOrder {
  time: number;
  kind: "risk" | "guardrail";
  reason: string | null;
  action: OrderAction;
}

export interface QualificationResult {
  policy: string;
  policy_version: number;
  passed: boolean;
  failures: string[];
}

// The bot's lifecycle state, streamed at evaluation start and after qualification (M4).
export interface LifecycleState {
  bot_id: string;
  version: number;
  state: string; // draft | evaluation | listed | suspended | delisted | ...
  qualification?: QualificationResult;
}

export type DemoMessage =
  | { type: "snapshot"; symbol: string; bars: DemoBar[] }
  | { type: "bar"; bar: DemoBar }
  | { type: "signal"; signal: DemoSignal }
  | { type: "perf"; perf: SandboxPerf }
  | { type: "blocked"; blocked: BlockedOrder }
  | { type: "lifecycle"; lifecycle: LifecycleState };
