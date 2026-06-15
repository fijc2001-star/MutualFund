import { type FormEvent, useEffect, useState } from "react";
import { useAuth } from "./auth";

interface SchemaProp {
  type?: string;
  default?: unknown;
}
interface Strategy {
  id: string;
  params_schema: { properties?: Record<string, SchemaProp> };
}
interface BotSummary {
  id: string;
  name: string;
  state: string;
  current_version: number;
  created_at: string;
}

export function DesignerStudio() {
  const { api } = useAuth();
  const [strategies, setStrategies] = useState<Strategy[]>([]);
  const [bots, setBots] = useState<BotSummary[]>([]);
  const [name, setName] = useState("");
  const [strategyId, setStrategyId] = useState("");
  const [params, setParams] = useState<Record<string, string>>({});
  const [universe, setUniverse] = useState("AAPL");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function refresh() {
    const r = await api("/bots");
    if (r.ok) setBots((await r.json()) as BotSummary[]);
  }

  function selectStrategy(s: Strategy) {
    setStrategyId(s.id);
    const props = s.params_schema.properties ?? {};
    const defaults: Record<string, string> = {};
    for (const [k, v] of Object.entries(props)) {
      defaults[k] = v.default != null ? String(v.default) : "";
    }
    setParams(defaults);
  }

  useEffect(() => {
    (async () => {
      const s = await api("/strategies");
      if (s.ok) {
        const list = (await s.json()) as Strategy[];
        setStrategies(list);
        if (list[0]) selectStrategy(list[0]);
      }
      await refresh();
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const schemaProps: Record<string, SchemaProp> =
    strategies.find((s) => s.id === strategyId)?.params_schema.properties ?? {};

  async function create(e: FormEvent) {
    e.preventDefault();
    setErr(null);
    setBusy(true);
    try {
      const coerced: Record<string, unknown> = {};
      for (const [k, v] of Object.entries(schemaProps)) {
        const raw = params[k] ?? "";
        coerced[k] = v.type === "integer" || v.type === "number" ? Number(raw) : raw;
      }
      const body = {
        name,
        strategy_id: strategyId,
        params: coerced,
        universe: universe.split(",").map((s) => s.trim()).filter(Boolean),
      };
      const r = await api("/bots", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!r.ok) {
        const d = await r.json().catch(() => ({}));
        throw new Error(typeof d.detail === "string" ? d.detail : JSON.stringify(d.detail));
      }
      setName("");
      await refresh();
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : String(ex));
    } finally {
      setBusy(false);
    }
  }

  async function submitForEval(id: string) {
    setErr(null);
    const r = await api(`/bots/${id}/transition`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ to: "evaluation", reason: "submitted" }),
    });
    if (r.ok) await refresh();
    else {
      const d = await r.json().catch(() => ({}));
      setErr(typeof d.detail === "string" ? d.detail : "Transition failed");
    }
  }

  return (
    <div className="studio">
      <section className="studio-create">
        <h2>New bot</h2>
        <form onSubmit={create}>
          <label>
            Name
            <input value={name} onChange={(e) => setName(e.target.value)} required />
          </label>
          <label>
            Strategy
            <select
              value={strategyId}
              onChange={(e) => {
                const s = strategies.find((x) => x.id === e.target.value);
                if (s) selectStrategy(s);
              }}
            >
              {strategies.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.id}
                </option>
              ))}
            </select>
          </label>
          {Object.entries(schemaProps).map(([k, v]) => (
            <label key={k}>
              {k}
              <input
                type={v.type === "integer" || v.type === "number" ? "number" : "text"}
                value={params[k] ?? ""}
                onChange={(e) => setParams((p) => ({ ...p, [k]: e.target.value }))}
              />
            </label>
          ))}
          <label>
            Universe (symbols, comma-separated)
            <input value={universe} onChange={(e) => setUniverse(e.target.value)} />
          </label>
          <button type="submit" disabled={busy}>
            {busy ? "…" : "Create & publish v1"}
          </button>
        </form>
        {err && <p className="login-err">{err}</p>}
      </section>

      <section className="studio-list">
        <h2>My bots</h2>
        {bots.length === 0 && <p className="muted">No bots yet — create one.</p>}
        {bots.length > 0 && (
          <table className="bots-table">
            <thead>
              <tr>
                <th>Name</th>
                <th>State</th>
                <th>Version</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {bots.map((b) => (
                <tr key={b.id}>
                  <td>{b.name}</td>
                  <td>
                    <span className={`lc-state lifecycle-${b.state}`}>{b.state}</span>
                  </td>
                  <td>v{b.current_version}</td>
                  <td>
                    {b.state === "draft" && (
                      <button onClick={() => void submitForEval(b.id)}>Submit for evaluation</button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  );
}
