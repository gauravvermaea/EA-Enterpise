// The current model, top right on every screen, with a drop-down to change model (UI-027).
// On a model's pages the model comes from the address; elsewhere it is the last model opened (kept in
// this browser only). Changing model keeps the view (entity types, relationship types, graph, metamodel,
// ER diagram) and opens it in the other model; from an entity it goes to the other model's entity types.
// From the roles phase (3.1) the list holds only the models the user may open.
import { useEffect, useState } from "react";
import { apiFetch } from "./auth";
import { KINDS, marksText } from "./ModelMarks";

const KEY = "eax.lastModel";
const remember = (id) => { try { localStorage.setItem(KEY, id); } catch { /* storage may be blocked */ } };
const recall = () => { try { return localStorage.getItem(KEY); } catch { return null; } };
const KIND_ORDER = ["template", "reference", "project"];
const KIND_LABEL = { template: "Root metamodels", reference: "Reference models", project: "Project models" };

export default function ModelSwitcher({ route }) {
  const [models, setModels] = useState(null);
  const parts = route.replace(/^#/, "").split("/");
  const inModel = parts[1] === "metamodel" && parts[2] && parts[2] !== "hierarchy" ? parts[2] : null;
  const current = inModel || recall();

  useEffect(() => { if (inModel) remember(inModel); }, [inModel]);
  useEffect(() => {
    let live = true;
    apiFetch("/api/v1/models?archived=false").then((m) => live && setModels(m)).catch(() => live && setModels([]));
    return () => { live = false; };
  }, []);

  if (!models) return null;
  const m = models.find((x) => x.id === current);

  function choose(id) {
    if (!id) return;
    remember(id);
    const view = inModel ? parts[3] : "";
    const keep = ["types", "rels", "graph", "metamodel", "diagram"].includes(view) ? `/${view}` : "";
    window.location.hash = `/metamodel/${id}${keep}`;
  }

  return (
    <div className={`model-switch${inModel ? " here" : ""}`} title={inModel ? "The model you are in" : "The last model you opened"}>
      <span className="model-switch-label">{inModel ? "Model" : "Last model"}</span>
      <select value={m ? m.id : ""} onChange={(e) => choose(e.target.value)} aria-label="Change model">
        {!m && <option value="">Choose a model...</option>}
        {KIND_ORDER.map((k) => {
          const list = models.filter((x) => x.kind === k);
          return list.length ? (
            <optgroup key={k} label={KIND_LABEL[k]}>
              {list.map((x) => <option key={x.id} value={x.id}>{KINDS[x.kind]?.glyph} {x.name}{x.version_label ? ` ${x.version_label}` : ""}{marksText(x) ? `  ${marksText(x)}` : ""}</option>)}
            </optgroup>
          ) : null;
        })}
      </select>
    </div>
  );
}
