import { useEffect, useRef, useState } from "react";
import {
  createChart,
  type IChartApi,
  type ISeriesApi,
  type UTCTimestamp,
} from "lightweight-charts";
import { useAuth } from "./auth";

interface BotSummary {
  id: string;
  name: string;
  state: string;
  current_version: number;
}
interface SubscriptionInfo {
  id: string;
  listing_id: string;
  symbol: string;
  strategy_id: string;
}
interface Listing {
  id: string;
  title: string;
}
interface LegPerf {
  return_pct: number;
  net_pnl: number;
  num_trades: number;
  max_drawdown_pct: number;
}
interface Leg {
  bot_id: string;
  name: string;
  symbol: string;
  strategy_id: string;
  weight: number;
  perf: LegPerf;
}
interface PortfolioResult {
  capital: number;
  equity: { time: number; value: number }[];
  perf: {
    equity: number;
    net_pnl: number;
    return_pct: number;
    max_drawdown_pct: number;
    sharpe: number | null;
    num_trades: number;
  };
  legs: Leg[];
}

// One allocatable line: a subscribed listing, or an owned bot.
interface AllocRow {
  key: string;
  label: string;
  kind: "Subscribed" | "Owned";
  ref: { listing_id?: string; bot_id?: string };
}

export function Portfolio() {
  const { api } = useAuth();
  const [rows, setRows] = useState<AllocRow[]>([]);
  const [weights, setWeights] = useState<Record<string, string>>({}); // "" = excluded
  const [capital, setCapital] = useState("100000");
  const [result, setResult] = useState<PortfolioResult | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const chartContainer = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Line"> | null>(null);

  useEffect(() => {
    (async () => {
      const [s, b, l] = await Promise.all([
        api("/subscriptions"),
        api("/bots"),
        api("/marketplace/listings"),
      ]);
      const subs = s.ok ? ((await s.json()) as SubscriptionInfo[]) : [];
      const bots = b.ok ? ((await b.json()) as BotSummary[]) : [];
      const listings = l.ok ? ((await l.json()) as Listing[]) : [];
      const title = new Map(listings.map((x) => [x.id, x.title]));

      const subRows: AllocRow[] = subs.map((sub) => ({
        key: `listing:${sub.listing_id}`,
        label: `${title.get(sub.listing_id) ?? sub.symbol} (${sub.symbol})`,
        kind: "Subscribed",
        ref: { listing_id: sub.listing_id },
      }));
      const botRows: AllocRow[] = bots.map((bot) => ({
        key: `bot:${bot.id}`,
        label: bot.name,
        kind: "Owned",
        ref: { bot_id: bot.id },
      }));
      setRows([...subRows, ...botRows]);
    })();
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
    const series = chart.addLineSeries({
      color: "#26a69a",
      lineWidth: 2,
      priceLineVisible: false,
      lastValueVisible: true,
    });
    chartRef.current = chart;
    seriesRef.current = series;
    return () => {
      chart.remove();
      chartRef.current = null;
      seriesRef.current = null;
    };
  }, []);

  useEffect(() => {
    if (seriesRef.current && result) {
      seriesRef.current.setData(
        result.equity.map((p) => ({ time: p.time as UTCTimestamp, value: p.value })),
      );
      chartRef.current?.timeScale().fitContent();
    }
  }, [result]);

  function toggle(key: string, on: boolean) {
    setWeights((w) => ({ ...w, [key]: on ? w[key] || "1" : "" }));
  }
  function setWeight(key: string, v: string) {
    setWeights((w) => ({ ...w, [key]: v }));
  }

  async function run() {
    setErr(null);
    setBusy(true);
    try {
      const allocations = rows
        .filter((r) => (weights[r.key] ?? "") !== "" && Number(weights[r.key]) > 0)
        .map((r) => ({ ...r.ref, weight: Number(weights[r.key]) }));
      if (allocations.length === 0) {
        setErr("Select at least one bot with a weight.");
        return;
      }
      const r = await api("/portfolio/backtest", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ capital: Number(capital), allocations }),
      });
      if (!r.ok) {
        const d = await r.json().catch(() => ({}));
        throw new Error(typeof d.detail === "string" ? d.detail : "Backtest failed");
      }
      setResult((await r.json()) as PortfolioResult);
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : String(ex));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="portfolio">
      <section className="pf-controls">
        <h2>Allocate capital across bots</h2>
        <label className="pf-cap">
          Capital
          <input type="number" value={capital} onChange={(e) => setCapital(e.target.value)} />
        </label>
        {rows.length === 0 && (
          <p className="muted">
            Nothing to allocate yet — subscribe to a bot in the Marketplace (or create one in
            Designer Studio).
          </p>
        )}
        {rows.length > 0 && (
          <table className="bots-table">
            <thead>
              <tr>
                <th />
                <th>Bot</th>
                <th>Source</th>
                <th>Weight</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => {
                const included = (weights[row.key] ?? "") !== "";
                return (
                  <tr key={row.key}>
                    <td>
                      <input
                        type="checkbox"
                        checked={included}
                        onChange={(e) => toggle(row.key, e.target.checked)}
                      />
                    </td>
                    <td>{row.label}</td>
                    <td>
                      <span className="mk-tag">{row.kind}</span>
                    </td>
                    <td>
                      <input
                        type="number"
                        min={0}
                        step={0.5}
                        disabled={!included}
                        value={weights[row.key] ?? ""}
                        onChange={(e) => setWeight(row.key, e.target.value)}
                        style={{ width: 64 }}
                      />
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
        <button onClick={() => void run()} disabled={busy}>
          {busy ? "Running…" : "Run portfolio backtest"}
        </button>
        {err && <p className="login-err">{err}</p>}
      </section>

      <section className="pf-result">
        {result && (
          <div className="pf-stats">
            <span className={result.perf.net_pnl >= 0 ? "pnl up" : "pnl down"}>
              {result.perf.net_pnl >= 0 ? "+" : ""}
              {result.perf.net_pnl.toFixed(0)} ({result.perf.return_pct}%)
            </span>
            <span className="perf-meta">
              equity ${result.perf.equity.toFixed(0)} · maxDD {result.perf.max_drawdown_pct}% ·
              Sharpe {result.perf.sharpe ?? "—"} · trades {result.perf.num_trades}
            </span>
          </div>
        )}
        <div className="pane-label">Portfolio equity</div>
        <div ref={chartContainer} className="pf-chart" />
        {result && (
          <table className="bots-table">
            <thead>
              <tr>
                <th>Bot</th>
                <th>Symbol</th>
                <th>Weight</th>
                <th>Return</th>
                <th>Trades</th>
              </tr>
            </thead>
            <tbody>
              {result.legs.map((l) => (
                <tr key={l.bot_id}>
                  <td>{l.name}</td>
                  <td>{l.symbol}</td>
                  <td>{(l.weight * 100).toFixed(0)}%</td>
                  <td className={l.perf.return_pct >= 0 ? "pnl up" : "pnl down"}>
                    {l.perf.return_pct}%
                  </td>
                  <td>{l.perf.num_trades}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  );
}
