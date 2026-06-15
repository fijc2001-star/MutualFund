import { type FormEvent, useState } from "react";
import { useAuth } from "./auth";

const ROLES = ["user", "designer", "admin", "root_admin"];

export function Login() {
  const { devLogin, googleLogin } = useAuth();
  const [email, setEmail] = useState("demo@example.com");
  const [role, setRole] = useState("designer");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setErr(null);
    try {
      await devLogin(email, role);
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : String(ex));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login">
      <div className="login-card">
        <h1>MutualFund</h1>
        <p className="muted">Sign in to continue</p>

        <button className="google" onClick={googleLogin}>
          Continue with Google
        </button>

        <div className="login-sep">dev login</div>

        <form onSubmit={submit}>
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="email"
            required
          />
          <select value={role} onChange={(e) => setRole(e.target.value)}>
            {ROLES.map((r) => (
              <option key={r} value={r}>
                {r}
              </option>
            ))}
          </select>
          <button type="submit" disabled={busy}>
            {busy ? "…" : "Sign in"}
          </button>
        </form>

        {err && <p className="login-err">{err}</p>}
        <p className="muted login-note">
          Google needs OAuth credentials configured; dev login works now.
        </p>
      </div>
    </div>
  );
}
