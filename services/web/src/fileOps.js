// What the file explorer does, without the screen (R3.5): paths, choosing several items, cut, copy and paste, drag and
// drop, the keys, and the views. FileExplorer.jsx draws it; tests run these with node.

export const VIEWS = [["details", "Details"], ["list", "List"], ["icons", "Large icons"]];

export const parentOf = (p) => p.split("/").slice(0, -1).join("/") || "/";
export const joinPath = (folder, name) => `${folder.replace(/\/$/, "")}/${name}`;
export const baseName = (p) => p.replace(/\/$/, "").split("/").pop() || "/";

// The folders above a path, root first: "/usr/lib" -> ["/", "/usr", "/usr/lib"].
export function crumbs(p) {
  const parts = p.split("/").filter(Boolean);
  return ["/", ...parts.map((_, i) => `/${parts.slice(0, i + 1).join("/")}`)];
}

// A click on an item: alone it chooses that item; with Ctrl (or Cmd) it adds or takes it away; with Shift it chooses
// everything from the last item clicked to this one. Returns {chosen: [paths], anchor}.
export function choose(list, chosen, anchor, path, { ctrl = false, shift = false } = {}) {
  const paths = list.map((e) => e.path);
  if (shift && anchor && paths.includes(anchor)) {
    const [a, b] = [paths.indexOf(anchor), paths.indexOf(path)].sort((x, y) => x - y);
    const range = paths.slice(a, b + 1);
    return { chosen: ctrl ? [...new Set([...chosen, ...range])] : range, anchor };
  }
  if (ctrl) {
    return { chosen: chosen.includes(path) ? chosen.filter((p) => p !== path) : [...chosen, path], anchor: path };
  }
  return { chosen: [path], anchor: path };
}

// Paste: each item cut or copied goes into the folder under its own name. Nothing is pasted into itself or where it
// already is. Returns the changes to send ({op, path, to}) and what is left out and why.
export function pasteOps(clip, folder) {
  const ops = [], skipped = [];
  for (const p of clip?.paths || []) {
    const to = joinPath(folder, baseName(p));
    if (to === p) { skipped.push(`${baseName(p)}: already here`); continue; }
    if (folder === p || folder.startsWith(`${p.replace(/\/$/, "")}/`)) { skipped.push(`${baseName(p)}: not into itself`); continue; }
    ops.push({ op: clip.mode === "cut" ? "move" : "copy", path: p, to });
  }
  return { ops, skipped };
}

// A drop on a folder: files from the computer are uploaded into it; items dragged from this explorer are moved there
// (copied with Ctrl, or Alt on a Mac).
export function dropPlan({ files = [], dragged = [], copy = false }, folder) {
  if (files.length) return { upload: { path: folder, count: files.length } };
  if (!dragged.length) return null;
  return pasteOps({ mode: copy ? "copy" : "cut", paths: dragged }, folder);
}

// The keys: Enter opens, F2 renames, Delete deletes, Ctrl+C / Ctrl+X / Ctrl+V / Ctrl+A, Backspace and Alt+Up go up,
// Alt+Left and Alt+Right go back and forward, F5 refreshes. Returns the action's name or null.
export function keyAction(e) {
  const k = String(e.key || "");
  const ctrl = !!(e.ctrlKey || e.metaKey);
  if (ctrl && !e.altKey) {
    const c = k.toLowerCase();
    return { c: "copy", x: "cut", v: "paste", a: "all" }[c] || null;
  }
  if (e.altKey) return { ArrowLeft: "back", ArrowRight: "forward", ArrowUp: "up" }[k] || null;
  return { Enter: "open", F2: "rename", Delete: "delete", Backspace: "up", F5: "refresh", Escape: "none" }[k] || null;
}

// What deleting the chosen items asks to be typed: one item its full path (as before); several the word DELETE.
export function deleteAsk(paths) {
  if (!paths.length) return null;
  if (paths.length === 1) return { prompt: `Delete ${paths[0]} for good? Type its full path to confirm:`, expect: paths[0] };
  return { prompt: `Delete these ${paths.length} items for good?\n${paths.slice(0, 12).join("\n")}${paths.length > 12 ? "\n..." : ""}\n\nType DELETE to confirm:`, expect: "DELETE" };
}

// What a text preview may show: text files up to a size; anything else shows its properties only.
export const PREVIEW_LIMIT = 512 * 1024;
export const previewable = (e) => !!e && !e.dir && (e.bytes || 0) <= PREVIEW_LIMIT;

export const iconOf = (e) => (e.dir ? "📁" : /\.(png|jpe?g|gif|svg|webp)$/i.test(e.name) ? "🖼" : /\.(zip|gz|tgz|tar|7z)$/i.test(e.name) ? "🗜"
  : /\.(log|txt|md|ya?ml|json|toml|conf|ini|env|sql|py|js|sh|css|html|xml)$/i.test(e.name) ? "📝" : "📄");
