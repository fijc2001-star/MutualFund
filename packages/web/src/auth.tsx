import { createContext, useContext, useEffect, useState, type ReactNode } from "react";

const API_BASE = "http://localhost:8000";
const ACCESS = "mf_access";
const REFRESH = "mf_refresh";

export interface Principal {
  user_id: string;
  tenant_id: string;
  email: string;
  role: string;
}

interface AuthContextValue {
  principal: Principal | null;
  ready: boolean;
  devLogin: (email: string, role: string) => Promise<void>;
  googleLogin: () => void;
  logout: () => Promise<void>;
  api: (path: string, init?: RequestInit) => Promise<Response>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within <AuthProvider>");
  return ctx;
}

function setTokens(access: string, refresh: string): void {
  localStorage.setItem(ACCESS, access);
  localStorage.setItem(REFRESH, refresh);
}

function clearTokens(): void {
  localStorage.removeItem(ACCESS);
  localStorage.removeItem(REFRESH);
}

async function tryRefresh(): Promise<boolean> {
  const refresh = localStorage.getItem(REFRESH);
  if (!refresh) return false;
  const res = await fetch(`${API_BASE}/auth/refresh`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ refresh_token: refresh }),
  });
  if (!res.ok) return false;
  const t = await res.json();
  setTokens(t.access_token, t.refresh_token);
  return true;
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [principal, setPrincipal] = useState<Principal | null>(null);
  const [ready, setReady] = useState(false);

  // Authenticated fetch: attaches the access token and retries once after a refresh on 401.
  async function api(path: string, init: RequestInit = {}): Promise<Response> {
    const headers: Record<string, string> = { ...(init.headers as Record<string, string>) };
    const access = localStorage.getItem(ACCESS);
    if (access) headers.Authorization = `Bearer ${access}`;
    let res = await fetch(`${API_BASE}${path}`, { ...init, headers });
    if (res.status === 401 && (await tryRefresh())) {
      const a2 = localStorage.getItem(ACCESS);
      if (a2) headers.Authorization = `Bearer ${a2}`;
      res = await fetch(`${API_BASE}${path}`, { ...init, headers });
    }
    return res;
  }

  async function loadMe(): Promise<void> {
    const res = await api("/auth/me");
    if (res.ok) {
      setPrincipal((await res.json()) as Principal);
    } else {
      clearTokens();
      setPrincipal(null);
    }
  }

  useEffect(() => {
    (async () => {
      if (localStorage.getItem(ACCESS)) await loadMe();
      setReady(true);
    })();
    // run once on mount
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function devLogin(email: string, role: string): Promise<void> {
    const res = await fetch(`${API_BASE}/auth/dev-login`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ email, role }),
    });
    if (!res.ok) throw new Error(`Sign-in failed (${res.status})`);
    const t = await res.json();
    setTokens(t.access_token, t.refresh_token);
    await loadMe();
  }

  function googleLogin(): void {
    window.location.href = `${API_BASE}/auth/google/login`;
  }

  async function logout(): Promise<void> {
    const refresh = localStorage.getItem(REFRESH);
    if (refresh) {
      try {
        await fetch(`${API_BASE}/auth/logout`, {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ refresh_token: refresh }),
        });
      } catch {
        /* best-effort */
      }
    }
    clearTokens();
    setPrincipal(null);
  }

  return (
    <AuthContext.Provider value={{ principal, ready, devLogin, googleLogin, logout, api }}>
      {children}
    </AuthContext.Provider>
  );
}
