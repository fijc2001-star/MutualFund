import { useEffect, useRef, useState } from "react";
import {
  createChart,
  CrosshairMode,
  type CandlestickData,
  type IChartApi,
  type ISeriesApi,
  type SeriesMarker,
  type Time,
  type UTCTimestamp,
} from "lightweight-charts";
import type { DemoMessage, DemoSignal } from "./types";

const WS_URL = "ws://localhost:8000/ws/demo";

type Status = "connecting" | "live" | "closed";

export function SignalChart({ symbol = "AAPL" }: { symbol?: string }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const markersRef = useRef<SeriesMarker<Time>[]>([]);

  const [status, setStatus] = useState<Status>("connecting");
  const [signals, setSignals] = useState<DemoSignal[]>([]);

  // Build the chart once.
  useEffect(() => {
    if (!containerRef.current) return;
    const chart = createChart(containerRef.current, {
      autoSize: true,
      layout: { background: { color: "#0e1117" }, textColor: "#d1d4dc" },
      grid: {
        vertLines: { color: "#1c2230" },
        horzLines: { color: "#1c2230" },
      },
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
    chartRef.current = chart;
    seriesRef.current = series;
    return () => {
      chart.remove();
      chartRef.current = null;
      seriesRef.current = null;
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
        series.setData(data);
        chartRef.current?.timeScale().fitContent();
      } else if (msg.type === "bar") {
        series.update({
          time: msg.bar.time as UTCTimestamp,
          open: msg.bar.open,
          high: msg.bar.high,
          low: msg.bar.low,
          close: msg.bar.close,
        });
      } else if (msg.type === "signal") {
        const s = msg.signal;
        const marker: SeriesMarker<Time> = {
          time: s.time as UTCTimestamp,
          position: s.side === "buy" ? "belowBar" : "aboveBar",
          color: s.side === "buy" ? "#26a69a" : "#ef5350",
          shape: s.side === "buy" ? "arrowUp" : "arrowDown",
          text: s.side.toUpperCase(),
        };
        markersRef.current = [...markersRef.current, marker].slice(-50);
        series.setMarkers(markersRef.current);
        setSignals((prev) => [s, ...prev].slice(0, 12));
      }
    };

    return () => ws.close();
  }, [symbol]);

  return (
    <div className="chart-layout">
      <div className="chart-main">
        <div className="chart-header">
          <span className="symbol">{symbol}</span>
          <span className={`status status-${status}`}>● {status}</span>
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
