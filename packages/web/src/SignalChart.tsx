import { useEffect, useRef, useState } from "react";
import {
  createChart,
  CrosshairMode,
  LineStyle,
  LineType,
  type IChartApi,
  type ISeriesApi,
  type LogicalRange,
  type SeriesMarker,
  type Time,
  type UTCTimestamp,
} from "lightweight-charts";
import type {
  BlockedOrder,
  DemoMessage,
  DemoSignal,
  LifecycleState,
  OrderAction,
  SandboxPerf,
} from "./types";
import {
  type Candle,
  type MaType,
  aggregate,
  anchoredVwap,
  movingAverage,
  prevPeriodLevels,
  rsi,
  vwap,
} from "./indicators";

const WS_URL = "ws://localhost:8000/ws/sandbox";
const MA_TYPES: MaType[] = ["SMA", "EMA", "WMA", "RMA", "HMA"];

const TIMEFRAMES: { label: string; minutes: number }[] = [
  { label: "1m", minutes: 1 },
  { label: "5m", minutes: 5 },
  { label: "15m", minutes: 15 },
  { label: "1h", minutes: 60 },
  { label: "1D", minutes: 1440 },
];

const RANGES: { label: string; seconds: number | "all" }[] = [
  { label: "1H", seconds: 3600 },
  { label: "1D", seconds: 86_400 },
  { label: "1W", seconds: 604_800 },
  { label: "All", seconds: "all" },
];

type Status = "connecting" | "live" | "closed";
type Side = "buy" | "sell";

// Markers are kept at their raw (1-minute) time and snapped to the active timeframe's
// bucket at render time, so a signal still lands on a candle after the timeframe changes.
type RawMarker =
  | { kind: "signal"; time: number; side: Side; price?: number; manual: boolean }
  | { kind: "blocked"; time: number; action: OrderAction };

interface MaCfg {
  on: boolean;
  type: MaType;
  len: number;
  color: string;
}

interface Settings {
  enMA: boolean;
  mas: MaCfg[];
  enVWAP: boolean;
  vwapMult: number;
  enAVWAP: boolean;
  avwapDate: string; // "YYYY-MM-DD"; empty → anchor at first bar
  enLevels: boolean;
  enRSI: boolean;
  rsiLen: number;
}

const DEFAULT_SETTINGS: Settings = {
  enMA: true,
  mas: [
    { on: true, type: "EMA", len: 9, color: "#26c6da" },
    { on: true, type: "EMA", len: 21, color: "#ffa726" },
    { on: true, type: "EMA", len: 50, color: "#ffee58" },
    { on: true, type: "SMA", len: 200, color: "#e040fb" },
  ],
  enVWAP: true,
  vwapMult: 2,
  enAVWAP: false,
  avwapDate: "",
  enLevels: true,
  enRSI: true,
  rsiLen: 14,
};

interface Overlays {
  mas: ISeriesApi<"Line">[];
  vwap: ISeriesApi<"Line">;
  vwapUp: ISeriesApi<"Line">;
  vwapLo: ISeriesApi<"Line">;
  avwap: ISeriesApi<"Line">;
  pdh: ISeriesApi<"Line">;
  pdl: ISeriesApi<"Line">;
  pwh: ISeriesApi<"Line">;
  pwl: ISeriesApi<"Line">;
}

function sortByTime(markers: SeriesMarker<Time>[]): SeriesMarker<Time>[] {
  return [...markers].sort((a, b) => Number(a.time) - Number(b.time));
}

function bucketTime(t: number, tfMinutes: number): UTCTimestamp {
  const tf = tfMinutes * 60;
  return (tfMinutes <= 1 ? t : Math.floor(t / tf) * tf) as UTCTimestamp;
}

function makeMarker(time: Time, side: Side, manual: boolean, price?: number): SeriesMarker<Time> {
  // Buy → green up-arrow below the bar; Sell → red down-arrow above the bar.
  const text = manual
    ? `${side.toUpperCase()} (manual)`
    : price !== undefined
      ? price.toFixed(2)
      : "";
  return {
    time,
    position: side === "buy" ? "belowBar" : "aboveBar",
    color: side === "buy" ? "#26a69a" : "#ef5350",
    shape: side === "buy" ? "arrowUp" : "arrowDown",
    size: manual ? 1 : 2,
    text,
  };
}

function makeBlockedMarker(time: Time, action: OrderAction): SeriesMarker<Time> {
  return {
    time,
    position: action === "buy" ? "belowBar" : "aboveBar",
    color: "#f0b429",
    shape: "circle",
    text: "BLOCKED",
  };
}

function LifecycleBadge({ lifecycle }: { lifecycle: LifecycleState }) {
  const q = lifecycle.qualification;
  const title = q
    ? q.passed
      ? `Passed ${q.policy} v${q.policy_version}`
      : `Failed ${q.policy} v${q.policy_version}: ${q.failures.join(", ")}`
    : "Evaluating…";
  return (
    <span className={`lifecycle lifecycle-${lifecycle.state}`} title={title}>
      <span className="lc-state">{lifecycle.state}</span>
      {q && (
        <span className="lc-qual">
          {q.passed ? `✓ ${q.policy} v${q.policy_version}` : `✗ ${q.failures.join(", ")}`}
        </span>
      )}
    </span>
  );
}

function anchorTs(dateStr: string, bars: Candle[]): number {
  if (dateStr) {
    const t = Date.parse(`${dateStr}T00:00:00Z`);
    if (!Number.isNaN(t)) return Math.floor(t / 1000);
  }
  return bars.length ? bars[0].time : 0;
}

export function SignalChart({ symbol = "AAPL" }: { symbol?: string }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const rsiContainerRef = useRef<HTMLDivElement>(null);

  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const overlaysRef = useRef<Overlays | null>(null);
  const rsiChartRef = useRef<IChartApi | null>(null);
  const rsiSeriesRef = useRef<ISeriesApi<"Line"> | null>(null);
  const syncingRef = useRef(false);

  const base1mRef = useRef<Candle[]>([]); // raw 1-minute bars (source of truth)
  const displayedRef = useRef<Candle[]>([]); // aggregated to the active timeframe
  const rawMarkersRef = useRef<RawMarker[]>([]);
  const sideRef = useRef<Side>("buy");
  const redrawRef = useRef<() => void>(() => {});

  const [status, setStatus] = useState<Status>("connecting");
  const [signals, setSignals] = useState<DemoSignal[]>([]);
  const [blocked, setBlocked] = useState<BlockedOrder[]>([]);
  const [lifecycle, setLifecycle] = useState<LifecycleState | null>(null);
  const [perf, setPerf] = useState<SandboxPerf | null>(null);
  const [side, setSide] = useState<Side>("buy");
  const [manualCount, setManualCount] = useState(0);
  const [tf, setTf] = useState(1);
  const tfRef = useRef(tf);
  const [settings, setSettings] = useState<Settings>(DEFAULT_SETTINGS);
  const settingsRef = useRef<Settings>(settings);

  useEffect(() => {
    sideRef.current = side;
  }, [side]);

  function applyMarkers() {
    const tfMin = tfRef.current;
    const markers = rawMarkersRef.current.map((r) =>
      r.kind === "blocked"
        ? makeBlockedMarker(bucketTime(r.time, tfMin), r.action)
        : makeMarker(bucketTime(r.time, tfMin), r.side, r.manual, r.price),
    );
    seriesRef.current?.setMarkers(sortByTime(markers));
  }

  function recomputeOverlays(bars: Candle[]) {
    const s = settingsRef.current;
    const ov = overlaysRef.current;
    if (ov) {
      ov.mas.forEach((seriesApi, i) => {
        const cfg = s.mas[i];
        const show = s.enMA && cfg.on;
        seriesApi.applyOptions({ visible: show, color: cfg.color });
        seriesApi.setData(show ? movingAverage(bars, cfg.len, cfg.type) : []);
      });

      const vw = s.enVWAP ? vwap(bars, s.vwapMult) : { vwap: [], upper: [], lower: [] };
      ov.vwap.applyOptions({ visible: s.enVWAP });
      ov.vwapUp.applyOptions({ visible: s.enVWAP });
      ov.vwapLo.applyOptions({ visible: s.enVWAP });
      ov.vwap.setData(vw.vwap);
      ov.vwapUp.setData(vw.upper);
      ov.vwapLo.setData(vw.lower);

      ov.avwap.applyOptions({ visible: s.enAVWAP });
      ov.avwap.setData(s.enAVWAP ? anchoredVwap(bars, anchorTs(s.avwapDate, bars)) : []);

      const lv = s.enLevels ? prevPeriodLevels(bars) : { pdh: [], pdl: [], pwh: [], pwl: [] };
      for (const [seriesApi, data] of [
        [ov.pdh, lv.pdh],
        [ov.pdl, lv.pdl],
        [ov.pwh, lv.pwh],
        [ov.pwl, lv.pwl],
      ] as const) {
        seriesApi.applyOptions({ visible: s.enLevels });
        seriesApi.setData(data);
      }
    }

    if (rsiSeriesRef.current) {
      rsiSeriesRef.current.setData(s.enRSI ? rsi(bars, s.rsiLen) : []);
    }
  }

  // redrawRef holds the latest closure so the (symbol-scoped) WS handler never goes stale.
  redrawRef.current = () => {
    const displayed = aggregate(base1mRef.current, tfRef.current);
    displayedRef.current = displayed;
    seriesRef.current?.setData(displayed);
    recomputeOverlays(displayed);
    applyMarkers();
  };

  function showRange(seconds: number | "all") {
    const ts = chartRef.current?.timeScale();
    const bars = displayedRef.current;
    if (!ts || bars.length === 0) return;
    if (seconds === "all") {
      ts.fitContent();
      return;
    }
    const to = bars[bars.length - 1].time as number;
    ts.setVisibleRange({ from: (to - seconds) as Time, to: to as Time });
  }

  // Build the price chart + overlay series once.
  useEffect(() => {
    if (!containerRef.current) return;
    const chart = createChart(containerRef.current, {
      autoSize: true,
      layout: { background: { color: "#0e1117" }, textColor: "#d1d4dc" },
      grid: { vertLines: { color: "#1c2230" }, horzLines: { color: "#1c2230" } },
      crosshair: { mode: CrosshairMode.Normal },
      timeScale: { timeVisible: true, secondsVisible: false },
    });
    const series = chart.addCandlestickSeries({
      upColor: "#26a69a",
      downColor: "#ef5350",
      borderVisible: false,
      wickUpColor: "#26a69a",
      wickDownColor: "#ef5350",
    });

    const line = (color: string, opts = {}) =>
      chart.addLineSeries({
        color,
        lineWidth: 2,
        priceLineVisible: false,
        lastValueVisible: false,
        ...opts,
      });
    const step = (color: string, title: string) =>
      line(color, { lineWidth: 1, lineType: LineType.WithSteps, title });

    const overlays: Overlays = {
      mas: DEFAULT_SETTINGS.mas.map((m) => line(m.color, { title: `MA ${m.len}` })),
      vwap: line("#42a5f5", { title: "VWAP" }),
      vwapUp: line("#42a5f5", { lineWidth: 1, lineStyle: LineStyle.Dotted }),
      vwapLo: line("#42a5f5", { lineWidth: 1, lineStyle: LineStyle.Dotted }),
      avwap: line("#ab47bc", { title: "AVWAP" }),
      pdh: step("#b0bec5", "PDH"),
      pdl: step("#b0bec5", "PDL"),
      pwh: step("#4dd0e1", "PWH"),
      pwl: step("#4dd0e1", "PWL"),
    };

    chartRef.current = chart;
    seriesRef.current = series;
    overlaysRef.current = overlays;

    chart.subscribeClick((param) => {
      if (param.time === undefined) return;
      rawMarkersRef.current = [
        ...rawMarkersRef.current,
        { kind: "signal" as const, time: Number(param.time), side: sideRef.current, manual: true },
      ];
      applyMarkers();
      setManualCount((n) => n + 1);
    });

    // Keep the RSI pane's time scale in lockstep with the price chart.
    chart.timeScale().subscribeVisibleLogicalRangeChange((range: LogicalRange | null) => {
      if (syncingRef.current || !range || !rsiChartRef.current) return;
      syncingRef.current = true;
      rsiChartRef.current.timeScale().setVisibleLogicalRange(range);
      syncingRef.current = false;
    });

    return () => {
      chart.remove();
      chartRef.current = null;
      seriesRef.current = null;
      overlaysRef.current = null;
    };
  }, []);

  // Create/destroy the RSI sub-pane chart when the toggle changes.
  useEffect(() => {
    if (!settings.enRSI || !rsiContainerRef.current) return;
    const chart = createChart(rsiContainerRef.current, {
      autoSize: true,
      layout: { background: { color: "#0e1117" }, textColor: "#8b93a7" },
      grid: { vertLines: { color: "#1c2230" }, horzLines: { color: "#1c2230" } },
      timeScale: { timeVisible: true, secondsVisible: false },
      rightPriceScale: { scaleMargins: { top: 0.1, bottom: 0.1 } },
    });
    const rsiSeries = chart.addLineSeries({
      color: "#ce93d8",
      lineWidth: 2,
      priceLineVisible: false,
      lastValueVisible: true,
      title: "RSI",
    });
    for (const level of [70, 30]) {
      rsiSeries.createPriceLine({
        price: level,
        color: "#5a6479",
        lineStyle: LineStyle.Dashed,
        lineWidth: 1,
        axisLabelVisible: true,
        title: String(level),
      });
    }
    rsiChartRef.current = chart;
    rsiSeriesRef.current = rsiSeries;

    chart.timeScale().subscribeVisibleLogicalRangeChange((range: LogicalRange | null) => {
      if (syncingRef.current || !range || !chartRef.current) return;
      syncingRef.current = true;
      chartRef.current.timeScale().setVisibleLogicalRange(range);
      syncingRef.current = false;
    });

    rsiSeries.setData(settings.enRSI ? rsi(displayedRef.current, settings.rsiLen) : []);
    const mainRange = chartRef.current?.timeScale().getVisibleLogicalRange();
    if (mainRange) chart.timeScale().setVisibleLogicalRange(mainRange);

    return () => {
      chart.remove();
      rsiChartRef.current = null;
      rsiSeriesRef.current = null;
    };
  }, [settings.enRSI]);

  // Mirror settings into the ref and recompute overlays when they change.
  useEffect(() => {
    settingsRef.current = settings;
    recomputeOverlays(displayedRef.current);
  }, [settings]);

  // Re-aggregate and redraw when the timeframe changes.
  useEffect(() => {
    tfRef.current = tf;
    redrawRef.current();
  }, [tf]);

  // Connect the WebSocket and feed the chart.
  useEffect(() => {
    const ws = new WebSocket(`${WS_URL}?symbol=${encodeURIComponent(symbol)}`);
    setStatus("connecting");
    setPerf(null);
    setBlocked([]);
    setLifecycle(null);
    ws.onopen = () => setStatus("live");
    ws.onclose = () => setStatus("closed");
    ws.onerror = () => setStatus("closed");

    ws.onmessage = (event) => {
      const msg: DemoMessage = JSON.parse(event.data);
      const series = seriesRef.current;
      if (!series) return;

      if (msg.type === "snapshot") {
        base1mRef.current = msg.bars.map((b) => ({
          time: b.time as UTCTimestamp,
          open: b.open,
          high: b.high,
          low: b.low,
          close: b.close,
          volume: b.volume,
        }));
        // A snapshot starts a fresh series — clear markers/feed so a reconnect doesn't
        // stack duplicate arrows from the replayed deterministic feed.
        rawMarkersRef.current = [];
        setSignals([]);
        setManualCount(0);
        redrawRef.current();
        showRange(86_400); // default to the most recent day; use the range buttons to zoom out
      } else if (msg.type === "bar") {
        const bar: Candle = {
          time: msg.bar.time as UTCTimestamp,
          open: msg.bar.open,
          high: msg.bar.high,
          low: msg.bar.low,
          close: msg.bar.close,
          volume: msg.bar.volume,
        };
        const bars = base1mRef.current;
        if (bars.length && bars[bars.length - 1].time === bar.time) {
          bars[bars.length - 1] = bar;
        } else {
          bars.push(bar);
        }
        redrawRef.current();
      } else if (msg.type === "signal") {
        const s = msg.signal;
        rawMarkersRef.current = [
          ...rawMarkersRef.current,
          { kind: "signal" as const, time: s.time, side: s.side, price: s.price, manual: false },
        ].slice(-200);
        applyMarkers();
        setSignals((prev) => [s, ...prev].slice(0, 12));
      } else if (msg.type === "blocked") {
        const b = msg.blocked;
        rawMarkersRef.current = [
          ...rawMarkersRef.current,
          { kind: "blocked" as const, time: b.time, action: b.action },
        ].slice(-200);
        applyMarkers();
        setBlocked((prev) => [b, ...prev].slice(0, 8));
      } else if (msg.type === "lifecycle") {
        setLifecycle(msg.lifecycle);
      } else if (msg.type === "perf") {
        setPerf(msg.perf);
      }
    };

    return () => ws.close();
  }, [symbol]);

  function clearMarkers() {
    rawMarkersRef.current = [];
    applyMarkers();
    setManualCount(0);
  }

  const patch = (p: Partial<Settings>) => setSettings((s) => ({ ...s, ...p }));
  const patchMa = (i: number, p: Partial<MaCfg>) =>
    setSettings((s) => ({ ...s, mas: s.mas.map((m, j) => (j === i ? { ...m, ...p } : m)) }));

  return (
    <div className="chart-layout">
      <div className="chart-main">
        <div className="chart-header">
          <span className="symbol">{symbol}</span>
          {perf && (
            <span className="perf">
              <span className={perf.net_pnl >= 0 ? "pnl up" : "pnl down"}>
                {perf.net_pnl >= 0 ? "+" : ""}
                {perf.net_pnl.toFixed(2)} ({perf.return_pct.toFixed(2)}%)
              </span>
              <span className="perf-meta">
                equity ${perf.equity.toFixed(0)} · pos {perf.position} · trades{" "}
                {perf.num_trades} · maxDD {perf.max_drawdown_pct.toFixed(1)}%
              </span>
            </span>
          )}
          {lifecycle && <LifecycleBadge lifecycle={lifecycle} />}
          <span className={`status status-${status}`}>● {status}</span>
        </div>

        <div className="chart-toolbar">
          <span className="muted">TF</span>
          {TIMEFRAMES.map((t) => (
            <button
              key={t.minutes}
              className={tf === t.minutes ? "active" : ""}
              onClick={() => setTf(t.minutes)}
            >
              {t.label}
            </button>
          ))}
          <span className="divider" />
          <span className="muted">Range</span>
          {RANGES.map((r) => (
            <button key={r.label} onClick={() => showRange(r.seconds)}>
              {r.label}
            </button>
          ))}
        </div>

        <div className="marker-toolbar">
          <span className="muted">Markers — click chart to drop:</span>
          <button className={side === "buy" ? "active buy" : "buy"} onClick={() => setSide("buy")}>
            ▲ Buy
          </button>
          <button
            className={side === "sell" ? "active sell" : "sell"}
            onClick={() => setSide("sell")}
          >
            ▼ Sell
          </button>
          <button onClick={clearMarkers}>Clear</button>
          <span className="muted">manual: {manualCount}</span>
        </div>

        <div ref={containerRef} className="chart-canvas" />
        {settings.enRSI && <div ref={rsiContainerRef} className="rsi-pane" />}
      </div>

      <aside className="side-col">
        <section className="indicators">
          <h3>Indicators</h3>

          <label className="ind-head">
            <input
              type="checkbox"
              checked={settings.enMA}
              onChange={(e) => patch({ enMA: e.target.checked })}
            />
            Moving averages
          </label>
          {settings.mas.map((m, i) => (
            <div className="ma-row" key={i}>
              <input
                type="checkbox"
                checked={m.on}
                onChange={(e) => patchMa(i, { on: e.target.checked })}
              />
              <span className="swatch" style={{ background: m.color }} />
              <select
                value={m.type}
                onChange={(e) => patchMa(i, { type: e.target.value as MaType })}
              >
                {MA_TYPES.map((t) => (
                  <option key={t} value={t}>
                    {t}
                  </option>
                ))}
              </select>
              <input
                type="number"
                min={1}
                value={m.len}
                onChange={(e) => patchMa(i, { len: Math.max(1, Number(e.target.value) || 1) })}
              />
            </div>
          ))}

          <label className="ind-head">
            <input
              type="checkbox"
              checked={settings.enVWAP}
              onChange={(e) => patch({ enVWAP: e.target.checked })}
            />
            VWAP + bands
          </label>
          <div className="ind-row">
            <span className="muted">band σ×</span>
            <input
              type="number"
              min={0}
              step={0.5}
              value={settings.vwapMult}
              onChange={(e) => patch({ vwapMult: Math.max(0, Number(e.target.value) || 0) })}
            />
          </div>

          <label className="ind-head">
            <input
              type="checkbox"
              checked={settings.enAVWAP}
              onChange={(e) => patch({ enAVWAP: e.target.checked })}
            />
            Anchored VWAP
          </label>
          <div className="ind-row">
            <span className="muted">anchor</span>
            <input
              type="date"
              value={settings.avwapDate}
              onChange={(e) => patch({ avwapDate: e.target.value })}
            />
          </div>

          <label className="ind-head">
            <input
              type="checkbox"
              checked={settings.enLevels}
              onChange={(e) => patch({ enLevels: e.target.checked })}
            />
            Key levels (PDH/PDL/PWH/PWL)
          </label>

          <label className="ind-head">
            <input
              type="checkbox"
              checked={settings.enRSI}
              onChange={(e) => patch({ enRSI: e.target.checked })}
            />
            RSI
          </label>
          <div className="ind-row">
            <span className="muted">length</span>
            <input
              type="number"
              min={2}
              value={settings.rsiLen}
              onChange={(e) => patch({ rsiLen: Math.max(2, Number(e.target.value) || 2) })}
            />
          </div>
        </section>

        <section className="signal-feed">
          <h3>Signals</h3>
          {signals.length === 0 && <p className="muted">Waiting for signals…</p>}
          <ul>
            {signals.map((s, i) => (
              <li
                key={`${s.time}-${i}`}
                className={`sig sig-${s.side}`}
                title={s.rationale?.invalidation ?? undefined}
              >
                <span className="sig-side">{s.side.toUpperCase()}</span>
                <span className="sig-price">${s.price.toFixed(2)}</span>
                <span className="sig-reason">{s.reason}</span>
                {s.rationale && s.rationale.indicators.length > 0 && (
                  <span className="sig-indicators">{s.rationale.indicators.join(" · ")}</span>
                )}
              </li>
            ))}
          </ul>

          <h3>Blocked orders</h3>
          {blocked.length === 0 && <p className="muted">None — every order passed risk.</p>}
          <ul>
            {blocked.map((b, i) => (
              <li key={`${b.time}-${i}`} className={`blk blk-${b.kind}`}>
                <span className="blk-kind">{b.kind}</span>
                <span className="blk-action">{b.action.toUpperCase()}</span>
                <span className="blk-reason">{b.reason}</span>
              </li>
            ))}
          </ul>
        </section>
      </aside>
    </div>
  );
}
