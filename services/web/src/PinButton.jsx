// Pin a project or a model (owner, 8 Nov 2026): a pinned one comes first on Architecture work, and "pinned only" shows
// just those. On the tiles, the lists and the project's and model's own pages.
import { apiFetch } from "./auth";
import { refreshAll, useApi } from "./ModelViews";

export function usePins() {
  const { data } = useApi("/api/v1/me/favourites");
  return new Set((data || []).filter((f) => f.kind === "project" || f.kind === "model").map((f) => `${f.kind}:${f.id}`));
}

export default function PinButton({ k, x, pins, small }) {
  const own = usePins();
  const on = (pins || own).has(`${k}:${x.id}`);
  async function flip(e) {
    e.preventDefault(); e.stopPropagation();
    try { await apiFetch("/api/v1/me/favourites", { method: "POST", body: JSON.stringify({ kind: k, id: x.id, favourite: !on, label: x.name }) }); refreshAll(); }
    catch { /* shown next time */ }
  }
  return (
    <button type="button" className={`pin-btn${on ? " on" : ""}${small ? " small" : ""}`} onClick={flip} aria-pressed={on}
      title={on ? "Pinned: comes first on Architecture work. Click to unpin" : "Pin it: it comes first on Architecture work"}
      aria-label={on ? `Unpin ${x.name}` : `Pin ${x.name}`}>{on ? "★ Pinned" : "☆ Pin"}</button>
  );
}
