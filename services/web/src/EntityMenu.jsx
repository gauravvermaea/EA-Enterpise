// The right-click menu on entities (D480): on any row, card or link that leads to an entity (#/metamodel/<model>/entity/<id>),
// a menu of what can be done with it; each item only when the person may. Shift + right-click keeps the browser's own menu.
import { useEffect, useState } from "react";
import { apiFetch, canOn } from "./auth";
import { MenuList } from "./ActionsMenu";
import { Modal } from "./ModelOps";
import { refreshAll } from "./ModelViews";

const ENTITY = /#\/metamodel\/([^/?#]+)\/entity\/([^/?#]+)/;

function entityUnder(target) {
  const a = target.closest?.("a[href]");
  let m = a && ENTITY.exec(a.getAttribute("href") || "");
  if (m) return m;
  const holder = target.closest?.("tr, li, .card, .entity-card, [data-entity-href]");
  if (!holder) return null;
  const href = holder.getAttribute("data-entity-href") || "";
  m = ENTITY.exec(href);
  if (m) return m;
  const links = [...holder.querySelectorAll("a[href]")].map((x) => ENTITY.exec(x.getAttribute("href") || "")).filter(Boolean);
  const ids = new Set(links.map((x) => x[2]));
  return ids.size === 1 ? links[0] : null;     // a row about one entity only (not a relationship row naming two)
}

export default function EntityMenu() {
  const [menu, setMenu] = useState(null);       // { x, y, model, id }
  const [del, setDel] = useState(null);
  const [msg, setMsg] = useState("");
  useEffect(() => {
    const on = (e) => {
      if (e.shiftKey) return;
      if (e.target.closest?.("input, textarea, select, [contenteditable=true], iframe, .nav-pop")) return;
      const hit = entityUnder(e.target);
      if (!hit) return;
      e.preventDefault();
      setMenu({ x: Math.min(e.clientX, window.innerWidth - 260), y: Math.min(e.clientY, window.innerHeight - 330), model: decodeURIComponent(hit[1]), id: decodeURIComponent(hit[2]) });
    };
    const close = (e) => { if (!e.target.closest?.(".entity-menu")) setMenu(null); };
    document.addEventListener("contextmenu", on);
    document.addEventListener("mousedown", close);
    const gone = () => setMenu(null);
    window.addEventListener("hashchange", gone);
    return () => { document.removeEventListener("contextmenu", on); document.removeEventListener("mousedown", close); window.removeEventListener("hashchange", gone); };
  }, []);
  if (!menu && !del) return null;
  const base = menu ? `#/metamodel/${menu.model}/entity/${menu.id}` : "";
  const mayEdit = menu && canOn(menu.model, "model.content");
  const items = menu ? [
    { label: "Open", href: base },
    { label: "Edit…", href: base, ok: mayEdit, title: "Opens the entity; use ✎ Edit there" },
    { label: "Show in a graph", href: `${base}/graph` },
    { label: "History", href: `${base}/history` },
    { label: "Related entities", href: `${base}/relations` },
    { label: "Where it sits (tree)", href: `${base}/tree` },
    { label: "Add to a view…", href: `#/metamodel/${menu.model}/views/custom`, title: "Open the model's drawn views and add it there" },
    { label: "Compare with earlier versions", href: `${base}/history` },
    "-",
    { label: "Delete…", danger: true, ok: mayEdit, run: () => setDel({ model: menu.model, id: menu.id }) },
  ].filter((a) => a === "-" || a.ok !== false) : [];
  if (items[items.length - 1] === "-") items.pop();
  return (
    <>
      {menu && (
        <div className="entity-menu" style={{ position: "fixed", left: menu.x, top: menu.y, zIndex: 60 }}>
          <MenuList label="Entity" items={items} onDone={() => setMenu(null)} />
        </div>
      )}
      {del && (
        <Modal title="Delete this entity?" onClose={() => { setDel(null); setMsg(""); }}
          actions={<button className="danger" onClick={async () => {
            try {
              await apiFetch(`/api/v1/models/${del.model}/content/entities/${del.id}`, { method: "DELETE" });
              setDel(null); setMsg(""); refreshAll();
              if (window.location.hash.includes(`/entity/${del.id}`)) window.location.hash = `/metamodel/${del.model}/types`;
            } catch (err) { setMsg(err.message); }
          }}>Delete</button>}>
          <p>It and its relationships are removed from the model. Its history is kept. Retire it instead if it is only no longer in use.</p>
          {msg && <p className="status bad">{msg}</p>}
        </Modal>
      )}
    </>
  );
}
