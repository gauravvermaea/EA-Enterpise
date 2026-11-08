// What kind of model a model is, from where it came (owner, 7 Nov 2026): shown wherever models are listed or picked.
//   root metamodel · library model · new (from a metamodel) · copy of a model (now, or at a tag) · copy of a library
//   model · child of a project model (it can merge back)
export const ORIGINS = {
  root: "Root metamodel",
  library: "Library model",
  new: "New (from a metamodel)",
  copy: "Copy of a model",
  tag: "Copy of a model at a tag",
  "from-library": "From a library model",
  child: "Child (merges back)",
};

export function modelOrigin(m) {
  if (!m) return { key: "", label: "", text: "" };
  if (m.kind === "template") return { key: "root", label: ORIGINS.root, text: "a root metamodel" };
  if (m.kind === "reference") return { key: "library", label: ORIGINS.library, text: m.source_model_name ? `a library model built on ${m.source_model_name}` : "a library model" };
  if (m.parent_model_id) return { key: "child", label: ORIGINS.child, text: `child of ${m.parent_model_name || "its parent"}: it can merge back` };
  if (m.source_tag_name) return { key: "tag", label: ORIGINS.tag, text: `separate copy of ${m.source_model_name} as it was at the tag ${m.source_tag_name}` };
  if (m.source_model_kind === "project") return { key: "copy", label: ORIGINS.copy, text: `separate copy of ${m.source_model_name}` };
  if (m.source_model_kind === "reference") return { key: "from-library", label: ORIGINS["from-library"], text: `copied from the library model ${m.source_model_name}` };
  return { key: "new", label: ORIGINS.new, text: `new, from ${m.source_model_name || m.metamodel_name || "a metamodel"}` };
}
