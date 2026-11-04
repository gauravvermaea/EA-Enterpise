// Break-glass sign-in (D80): a Super Admin session when Keycloak is down. Audited and alerted.
import { useEffect, useState } from "react";
import { breakGlassSignIn } from "./auth";

export default function BreakGlass() {
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState(null);
  useEffect(() => {
    fetch("/api/v1/break-glass/status").then((r) => r.json()).then(setStatus).catch(() => setStatus({ enabled: null }));
  }, []);
  async function submit(e) {
    e.preventDefault();
    setBusy(true); setError("");
    try { await breakGlassSignIn(password); } catch (err) { setError(err.message); setBusy(false); }
  }
  return (
    <div className="signin">
      <form className="signin-card break-glass-card" onSubmit={submit}>
        <h1>Break-glass sign-in</h1>
        <p>For when Keycloak or single sign-on is down. You get Super Admin rights until you sign out (or the break-glass password is changed).</p>
        <p className="quiet">Every sign-in, failed attempt and action is audited, the IT and Super Admins see an alert on the
          heartbeat, and the password must be changed afterwards. Five wrong passwords lock it for 15 minutes.</p>
        {status?.enabled === false ? <p className="status bad">Break-glass sign-in is not set up on this installation.</p> : (
          <>
            <label className="ed-field">
              <span>Break-glass password</span>
              <input type="password" autoFocus autoComplete="off" value={password} onChange={(e) => setPassword(e.target.value)} />
            </label>
            {error && <p className="status bad">{error}</p>}
            <button className="danger" disabled={busy || !password}>Sign in with break-glass</button>
          </>
        )}
        <p className="small-note"><a href="#/">Back to normal sign-in</a></p>
      </form>
    </div>
  );
}
