// A terminal in the browser over the operations helper's WebSocket (D214), opened with a one-time address the API gives:
// a container's shell (Containers) or an SSH session to a remote instance's host (R2.2, D634). `ticket` asks the API for
// the address with the screen's size; it ends with exit, End session or leaving the page, or after the idle time.
import { useEffect, useRef, useState } from "react";

export default function WebTerminal({ ticket, openLabel = "▶ Open a terminal", what = "the terminal", note = null, disabled = false }) {
  const box = useRef(null);
  const sess = useRef(null);
  const [state, setState] = useState("idle");   // idle, opening, open, ended
  const [err, setErr] = useState("");
  const [why, setWhy] = useState("");
  const [idle, setIdle] = useState(null);
  useEffect(() => () => end(true), []);   // eslint-disable-line react-hooks/exhaustive-deps

  function end(leaving = false) {
    const s = sess.current;
    if (!s) return;
    try { s.send({ t: "end" }); s.ws.close(1000); } catch { /* already closed */ }
    s.ro.disconnect();
    if (leaving) s.term.dispose();
  }

  async function open() {
    setErr(""); setWhy(""); setState("opening");
    try {
      if (sess.current) { end(); sess.current.term.dispose(); sess.current = null; }
      const [{ Terminal: XTerm }, { FitAddon }] = await Promise.all([import("@xterm/xterm"), import("@xterm/addon-fit")]);
      await import("@xterm/xterm/css/xterm.css");
      const term = new XTerm({ cursorBlink: true, scrollback: 5000, fontSize: 13,
        fontFamily: "ui-monospace, SFMono-Regular, Consolas, monospace", theme: { background: "#0d1117", foreground: "#e6edf3" } });
      const fit = new FitAddon();
      term.loadAddon(fit);
      term.open(box.current);
      fit.fit();
      const t = await ticket({ cols: term.cols, rows: term.rows });
      setIdle(t.idle_minutes);
      const ws = new window.WebSocket(`${window.location.protocol === "https:" ? "wss" : "ws"}://${window.location.host}${t.url}`);
      ws.binaryType = "arraybuffer";
      const send = (m) => { if (ws.readyState === 1) ws.send(JSON.stringify(m)); };
      ws.onopen = () => { setState("open"); send({ t: "r", cols: term.cols, rows: term.rows }); term.focus(); };
      ws.onmessage = (e) => {
        if (typeof e.data !== "string") { term.write(new Uint8Array(e.data)); return; }
        try { const m = JSON.parse(e.data); if (m.t === "exit") setWhy(m.reason || "ended"); } catch { /* not ours */ }
      };
      ws.onerror = () => setErr("The terminal could not connect: check that the operations helper runs (Administration > Services).");
      ws.onclose = () => setState("ended");
      term.onData((d) => send({ t: "i", d }));
      term.onResize(({ cols, rows }) => send({ t: "r", cols, rows }));
      const ro = new ResizeObserver(() => { try { fit.fit(); } catch { /* hidden */ } });
      ro.observe(box.current);
      sess.current = { ws, term, ro, send };
    } catch (e) { setErr(e.message); setState("idle"); }
  }

  return (
    <div>
      <div className="row-gap filters">
        {state === "open"
          ? <button className="danger" onClick={() => end()}>■ End session</button>
          : <button className="primary" onClick={open} disabled={disabled || state === "opening"}>
            {state === "opening" ? "Opening..." : state === "ended" ? "▶ Open a new session" : openLabel}</button>}
        <span className="quiet small">
          {state === "open" ? <>Connected to {what}. Ends with <code>exit</code>, End session or leaving this page{idle ? `, or after ${idle} minutes without typing` : ""}.</>
            : state === "ended" ? <>The session has ended{why ? `: ${why}` : ""}.</> : note}
        </span>
      </div>
      {err && <p className="status bad">{err}</p>}
      <div className={`ct-xterm${state === "idle" ? " empty" : ""}`} ref={box} />
    </div>
  );
}
