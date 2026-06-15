import { useState } from "react";
import { AuthProvider, useAuth } from "./auth";
import { DesignerStudio } from "./DesignerStudio";
import { Login } from "./Login";
import { SignalChart } from "./SignalChart";

const SYMBOLS = ["AAPL", "MSFT", "NVDA", "TSLA"];
const DESIGNER_ROLES = ["designer", "admin", "root_admin"];

function Dashboard() {
  const [symbol, setSymbol] = useState("AAPL");
  return (
    <>
      <div className="symbol-picker dash-symbols">
        {SYMBOLS.map((s) => (
          <button key={s} className={s === symbol ? "active" : ""} onClick={() => setSymbol(s)}>
            {s}
          </button>
        ))}
      </div>
      {/* key forces a clean remount (new WS + fresh chart) on symbol change */}
      <SignalChart key={symbol} symbol={symbol} />
    </>
  );
}

function AuthedApp() {
  const { principal, logout } = useAuth();
  const [view, setView] = useState<"dashboard" | "designer">("dashboard");
  const isDesigner = !!principal && DESIGNER_ROLES.includes(principal.role);

  return (
    <div className="app">
      <header className="app-header">
        <h1>MutualFund</h1>
        <nav className="nav">
          <button
            className={view === "dashboard" ? "active" : ""}
            onClick={() => setView("dashboard")}
          >
            Dashboard
          </button>
          {isDesigner && (
            <button
              className={view === "designer" ? "active" : ""}
              onClick={() => setView("designer")}
            >
              Designer Studio
            </button>
          )}
        </nav>
        <div className="user-box">
          <span className="muted">
            {principal?.email} · {principal?.role}
          </span>
          <button onClick={() => void logout()}>Logout</button>
        </div>
      </header>
      {view === "designer" && isDesigner ? <DesignerStudio /> : <Dashboard />}
    </div>
  );
}

function Shell() {
  const { ready, principal } = useAuth();
  if (!ready) {
    return (
      <div className="app">
        <p className="muted">Loading…</p>
      </div>
    );
  }
  return principal ? <AuthedApp /> : <Login />;
}

export function App() {
  return (
    <AuthProvider>
      <Shell />
    </AuthProvider>
  );
}
