import { useEffect, useState } from "react";
import { useAuth } from "./auth";

interface TrackRecord {
  return_pct?: number;
  num_trades?: number;
  max_drawdown_pct?: number;
  sharpe?: number | null;
}
interface Listing {
  id: string;
  title: string;
  description: string;
  symbol: string;
  strategy_id: string;
  price_cents: number;
  billing_period: string;
  track_record: TrackRecord;
}

function price(listing: Listing): string {
  if (listing.price_cents === 0) return "Free";
  return `$${(listing.price_cents / 100).toFixed(2)}/${listing.billing_period}`;
}

export function Marketplace() {
  const { api } = useAuth();
  const [listings, setListings] = useState<Listing[]>([]);
  const [subscribed, setSubscribed] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  async function refresh() {
    const [l, s] = await Promise.all([api("/marketplace/listings"), api("/subscriptions")]);
    if (l.ok) setListings((await l.json()) as Listing[]);
    if (s.ok) {
      const subs = (await s.json()) as { listing_id: string }[];
      setSubscribed(new Set(subs.map((x) => x.listing_id)));
    }
  }

  useEffect(() => {
    void refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function subscribe(listing: Listing) {
    setBusy(listing.id);
    setMsg(null);
    try {
      const r = await api("/subscriptions", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ listing_id: listing.id }),
      });
      if (!r.ok) {
        const d = await r.json().catch(() => ({}));
        throw new Error(typeof d.detail === "string" ? d.detail : "Subscribe failed");
      }
      setMsg(
        listing.price_cents === 0
          ? `Subscribed to "${listing.title}".`
          : `Subscribed to "${listing.title}" — ${price(listing)} recorded.`,
      );
      await refresh();
    } catch (ex) {
      setMsg(ex instanceof Error ? ex.message : String(ex));
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="marketplace">
      <h2>Marketplace</h2>
      <p className="muted">Subscribe to a designer's bot to follow its signal stream.</p>
      {msg && <p className="mk-msg">{msg}</p>}
      {listings.length === 0 && <p className="muted">No listings yet.</p>}
      <div className="mk-grid">
        {listings.map((l) => {
          const tr = l.track_record;
          const isSub = subscribed.has(l.id);
          return (
            <div key={l.id} className="mk-card">
              <div className="mk-card-head">
                <h3>{l.title}</h3>
                <span className="mk-price">{price(l)}</span>
              </div>
              <div className="mk-tags">
                <span className="mk-tag">{l.symbol}</span>
                <span className="mk-tag">{l.strategy_id}</span>
              </div>
              {l.description && <p className="mk-desc">{l.description}</p>}
              <div className="mk-stats">
                <span className={(tr.return_pct ?? 0) >= 0 ? "pnl up" : "pnl down"}>
                  {tr.return_pct ?? 0}%
                </span>
                <span className="perf-meta">
                  maxDD {tr.max_drawdown_pct ?? 0}% · trades {tr.num_trades ?? 0} · Sharpe{" "}
                  {tr.sharpe ?? "—"}
                </span>
              </div>
              <button
                disabled={isSub || busy === l.id}
                onClick={() => void subscribe(l)}
                className={isSub ? "mk-subscribed" : ""}
              >
                {isSub ? "Subscribed ✓" : busy === l.id ? "…" : "Subscribe"}
              </button>
            </div>
          );
        })}
      </div>
    </div>
  );
}
