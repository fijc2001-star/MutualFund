import { useEffect, useRef, useState } from "react";
import {
  createChart,
  type IChartApi,
  type ISeriesApi,
  type SeriesMarker,
  type Time,
  type UTCTimestamp,
} from "lightweight-charts";
import { useAuth } from "./auth";

interface SubscriptionInfo {
  id: string;
  listing_id: string;
  symbol: string;
  strategy_id: string;
  started_at: string;
  created_at: string;
}
interface Candle {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
}
interface SignalPoint {
  time: number;
  side: string;
  price: number;
  reason: string;
}

export function MySubscriptions() {
  const { api } = useAuth();
  const [subs, setSubs] = useState<SubscriptionInfo[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [count, setCount] = useState<number | null>(null);

  const chartContainer = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);

  async function refresh() {
    const r = await api("/subscriptions");
    if (r.ok) setSubs((await r.json()) as SubscriptionInfo[]);
  }

  useEffect(() => {
    void refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!chartContainer.current) return;
    const chart = createChart(chartContainer.current, {
      autoSize: true,
      layout: { background: { color: "#0e1117" }, textColor: "#d1d4dc" },
      grid: { vertLines: { color: "#1c2230" }, horzLines: { color: "#1c2230" } },
      timeScale: { timeVisible: true, secondsVisible: false },
    });
    seriesRef.current = chart.addCandlestickSeries();
    chartRef.current = chart;
    return () => {
      chart.remove();
      chartRef.current = null;
      seriesRef.current = null;
    };
  }, []);

  async function openReplay(sub: SubscriptionInfo) {
    setSelected(sub.id);
    setCount(null);
    const r = await api(`/subscriptions/${sub.id}/replay`);
    if (!r.ok) return;
    const data = (await r.json()) as { candles: Candle[]; signals: SignalPoint[] };
    const series = seriesRef.current;
    if (!series) return;
    series.setData(
      data.candles.map((c) => ({
        time: c.time as UTCTimestamp,
        open: c.open,
        high: c.high,
        low: c.low,
        close: c.close,
      })),
    );
    const markers: SeriesMarker<Time>[] = data.signals.map((s) => ({
      time: s.time as UTCTimestamp,
      position: s.side === "buy" ? "belowBar" : "aboveBar",
      color: s.side === "buy" ? "#26a69a" : "#ef5350",
      shape: s.side === "buy" ? "arrowUp" : "arrowDown",
      text: s.side.toUpperCase(),
    }));
    series.setMarkers(markers);
    chartRef.current?.timeScale().fitContent();
    setCount(data.signals.length);
  }

  async function unsubscribe(id: string) {
    const r = await api(`/subscriptions/${id}`, { method: "DELETE" });
    if (r.ok) {
      if (selected === id) {
        setSelected(null);
        seriesRef.current?.setData([]);
        seriesRef.current?.setMarkers([]);
      }
      await refresh();
    }
  }

  return (
    <div className="subs">
      <section className="subs-list">
        <h2>My subscriptions</h2>
        {subs.length === 0 && (
          <p className="muted">None yet — subscribe to a bot in the Marketplace.</p>
        )}
        {subs.length > 0 && (
          <table className="bots-table">
            <thead>
              <tr>
                <th>Symbol</th>
                <th>Strategy</th>
                <th />
                <th />
              </tr>
            </thead>
            <tbody>
              {subs.map((s) => (
                <tr key={s.id} className={selected === s.id ? "row-active" : ""}>
                  <td>{s.symbol}</td>
                  <td>{s.strategy_id}</td>
                  <td>
                    <button onClick={() => void openReplay(s)}>Replay</button>
                  </td>
                  <td>
                    <button className="danger" onClick={() => void unsubscribe(s.id)}>
                      Unsubscribe
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
      <section className="subs-replay">
        <div className="pane-label">
          Signal replay{count != null ? ` · ${count} signals` : ""}
        </div>
        <div ref={chartContainer} className="subs-chart" />
      </section>
    </div>
  );
}
