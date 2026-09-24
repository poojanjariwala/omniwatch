import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { ApiError, apiErrorText, login } from "../lib/api";
import { DEMO_PERSONAS } from "../lib/demo";

export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const navigate = useNavigate();

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      const user = await login(email, password);
      routeUser(user.role);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : apiErrorText(err));
    } finally {
      setBusy(false);
    }
  }

  async function quick(p: (typeof DEMO_PERSONAS)[number]) {
    setError("");
    setBusy(true);
    try {
      const user = await login(p.email, p.password);
      routeUser(user.role);
    } catch (err) {
      setError(`Quick login failed (${p.label}): ${apiErrorText(err)}`);
    } finally {
      setBusy(false);
    }
  }

  function routeUser(role: string) {
    if (role === "dosje" || role === "state") navigate("/gov/dashboard");
    else if (role === "pmu") navigate("/inspector/tasks");
    else if (role === "ngo") navigate("/ngo/terminal");
    else navigate("/verify");
  }

  return (
    <div className="login-page">
      <div className="panel login-card">
        <div style={{ padding: 28 }}>
          <h1 style={{ marginBottom: 2 }}>OMNIWATCH</h1>
          <div className="tagline" style={{ color: "var(--ink-faint)", fontSize: 11, letterSpacing: 0.08 }}>
            FROM SELF-REPORTED MONITORING TO EVIDENCE-BACKED VERIFICATION
          </div>
          <div className="ok-box" style={{ margin: "14px 0 4px" }}>
            DEMO build — sample credentials below
          </div>

          <form onSubmit={submit} className="stack" style={{ marginTop: 14 }}>
            <label className="flabel">
              Email
              <input className="field" type="email" value={email} required
                onChange={(e) => setEmail(e.target.value)} autoComplete="username" />
            </label>
            <label className="flabel">
              Password
              <input className="field" type="password" value={password} required
                onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" />
            </label>
            {error && <div className="error-box">{error}</div>}
            <button className="btn primary" type="submit" disabled={busy}>
              {busy ? "Signing in…" : "Sign in"}
            </button>
          </form>

          <div style={{ marginTop: 22 }}>
            <div className="caption" style={{ marginBottom: 8 }}>Quick demo logins (roles)</div>
            <div className="grid cols-2">
              {DEMO_PERSONAS.map((p) => (
                <button key={p.email} className="btn small" disabled={busy} onClick={() => quick(p)}>
                  {p.label}
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
