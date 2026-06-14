import { useEffect, useRef, useState } from "react";
import {
  createChart,
  CrosshairMode,
  type CandlestickData,
  type IChartApi,
  type ISeriesApi,
  type LineData,
  type SeriesMarker,
  type Time,
  type UTCTimestamp,
} from "lightweight-charts";
import type { DemoMessage, DemoSignal } from "./types";

const WS_URL = "ws://localhost:8000/ws/demo";

type Status = "connecting" | "live" | "closed";
type Side = "buy" | "sell";

function sortByTime(markers: SeriesMarker<Time>[]): SeriesMarker<Time>[] {
  return [...markers].sort((a, b) => Number(a.time) - Number(b.time));
}

function makeMarker(time: Time, side: Side, manual: boolean): SeriesMarker<Time> {
  return {
    time,
    position: side === "buy" ? "belowBar" : "aboveBar",
    color: side === "buy" ? "#26a69a" : "#ef5350",
    shape: side === "buy" ? "arrowUp" : "arrowDown",
    text: manual ? `${side.toUpperCase()} (manual)` : side.toUpperCase(),
  };
}

// Simple moving average computed from candle closes — an "indicator" in our own code.
function sma(bars: CandlestickData[], period: number): LineData[] {
  const out: LineData[] = [];
  let sum = 0;
  for (let i = 0; i < bars.length; i++) {
    sum += bars[i].close;
    if (i >= period) sum -= bars[i - period].close;
    if (i >= period - 1) {
      out.push({ time: bars[i].time, value: +(sum / period).toFixed(2) });
    }
  }
  return out;
}

export function SignalChart({ symbol = "AAPL" }: { symbol?: string }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const sma9Ref = useRef<ISeriesApi<"Line"> | null>(null);
  const sma21Ref = useRef<ISeriesApi<"Line"> | null>(null);
  const barsRef = useRef<CandlestickData[]>([]);
  const markersRef = useRef<SeriesMarker<Time>[]>([]);
  const sideRef = useRef<Side>("buy");

  const [status, setStatus] = useState<Status>("connecting");
  const [signals, setSignals] = useState<DemoSignal[]>([]);
  const [side, setSide] = useState<Side>("buy");
  const [manualCount, setManualCount] = useState(0);
  const [showSma9, setShowSma9] = useState(true);
  const [showSma21, setShowSma21] = useState(true);

  useEffect(() => {
    sideRef.current = side;
  }, [side]);

  useEffect(() => {
    sma9Ref.current?.applyOptions({ visible: showSma9 });
  }, [showSma9]);
  useEffect(() => {
    sma21Ref.current?.applyOptions({ visible: showSma21 });
  }, [showSma21]);

  function applyMarkers() {
    seriesRef.current?.setMarkers(sortByTime(markersRef.current));
  }

  function recomputeIndicators() {
    const bars = barsRef.current;
    sma9Ref.current?.setData(sma(bars, 9));
    sma21Ref.current?.setData(sma(bars, 21));
  }

  // Build the chart once.
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
    const sma9 = chart.addLineSeries({
      color: "#f0b429",
      lineWidth: 2,
      priceLineVisible: false,
      lastValueVisible: false,
      title: "SMA 9",
    });
    const sma21 = chart.addLineSeries({
      color: "#2962ff",
      lineWidth: 2,
      priceLineVisible: false,
      lastValueVisible: false,
      title: "SMA 21",
    });
    chartRef.current = chart;
    seriesRef.current = series;
    sma9Ref.current = sma9;
    sma21Ref.current = sma21;

    chart.subscribeClick((param) => {
      if (param.time === undefined) return;
      markersRef.current = [
        ...markersRef.current,
        makeMarker(param.time, sideRef.current, true),
      ];
      applyMarkers();
      setManualCount((n) => n + 1);
    });

    return () => {
      chart.remove();
      chartRef.current = null;
      seriesRef.current = null;
      sma9Ref.current = null;
      sma21Ref.current = null;
    };
  }, []);

  // Connect the WebSocket and feed the chart.
  useEffect(() => {
    const ws = new WebSocket(`${WS_URL}?symbol=${encodeURIComponent(symbol)}`);
    setStatus("connecting");
    ws.onopen = () => setStatus("live");
    ws.onclose = () => setStatus("closed");
    ws.onerror = () => setStatus("closed");

    ws.onmessage = (event) => {
      const msg: DemoMessage = JSON.parse(event.data);
      const series = seriesRef.current;
      if (!series) return;

      if (msg.type === "snapshot") {
        const data: CandlestickData[] = msg.bars.map((b) => ({
          time: b.time as UTCTimestamp,
          open: b.open,
          high: b.high,
          low: b.low,
          close: b.close,
        }));
        barsRef.current = data;
        series.setData(data);
        recomputeIndicators();
        chartRef.current?.timeScale().fitContent();
      } else if (msg.type === "bar") {
        const bar: CandlestickData = {
          time: msg.bar.time as UTCTimestamp,
          open: msg.bar.open,
          high: msg.bar.high,
          low: msg.bar.low,
          close: msg.bar.close,
        };
        series.update(bar);
        const bars = barsRef.current;
        if (bars.length && bars[bars.length - 1].time === bar.time) {
          bars[bars.length - 1] = bar;
        } else {
          bars.push(bar);
        }
        recomputeIndicators();
      } else if (msg.type === "signal") {
        const s = msg.signal;
        markersRef.current = [
          ...markersRef.current,
          makeMarker(s.time as UTCTimestamp, s.side, false),
        ].slice(-100);
        applyMarkers();
        setSignals((prev) => [s, ...prev].slice(0, 12));
      }
    };

    return () => ws.close();
  }, [symbol]);

  function clearMarkers() {
    markersRef.current = [];
    applyMarkers();
    setManualCount(0);
  }

  return (
    <div className="chart-layout">
      <div className="chart-main">
        <div className="chart-header">
          <span className="symbol">{symbol}</span>
          <span className={`status status-${status}`}>● {status}</span>
        </div>

        <div className="marker-toolbar">
          <span className="muted">Markers — click chart to drop:</span>
          <button
            className={side === "buy" ? "active buy" : "buy"}
            onClick={() => setSide("buy")}
          >
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

          <span className="divider" />

          <span className="muted">Indicators:</span>
          <button
            className={showSma9 ? "active sma9" : "sma9"}
            onClick={() => setShowSma9((v) => !v)}
          >
            SMA 9
          </button>
          <button
            className={showSma21 ? "active sma21" : "sma21"}
            onClick={() => setShowSma21((v) => !v)}
          >
            SMA 21
          </button>
        </div>

        <div ref={containerRef} className="chart-canvas" />
      </div>

      <aside className="signal-feed">
        <h3>Signals</h3>
        {signals.length === 0 && <p className="muted">Waiting for signals…</p>}
        <ul>
          {signals.map((s, i) => (
            <li key={`${s.time}-${i}`} className={`sig sig-${s.side}`}>
              <span className="sig-side">{s.side.toUpperCase()}</span>
              <span className="sig-price">${s.price.toFixed(2)}</span>
              <span className="sig-reason">{s.reason}</span>
            </li>
          ))}
        </ul>
      </aside>
    </div>
  );
}
