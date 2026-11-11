// "Open in draw.io" (owner, 11 Nov 2026, D585): a generated picture, a canvas or the metamodel diagram opens in our own
// draw.io, full screen in a tab of its own (D411), as a scratch view: shown and exported there, kept nowhere, bound to
// the model only if saved as a drawn view. The picture's file reaches the new tab without going in its address:
//  1. this tab puts it in localStorage under a one-time key and opens #/drawio/open/<key>;
//  2. the new tab takes it out (the key is removed at once) and keeps it in its own sessionStorage, so a reload of that
//     tab shows it again;
//  3. a picture too big for localStorage (about 5 MB) is handed over through window.opener instead: shown, but a
//     reload cannot bring it back (the tab says so).
// Keys older than a day (a tab that never opened) are cleared whenever another picture is opened.

import { apiBlobUrl, apiDownload } from "./auth";

const PREFIX = "eax.scratch.";
const DAY = 24 * 3600 * 1000;

function sweep() {
  try {
    for (let i = window.localStorage.length - 1; i >= 0; i--) {
      const k = window.localStorage.key(i);
      if (!k || !k.startsWith(PREFIX)) continue;
      const at = Number((JSON.parse(window.localStorage.getItem(k) || "{}") || {}).at || 0);
      if (!at || Date.now() - at > DAY) window.localStorage.removeItem(k);
    }
  } catch { /* storage not available */ }
}

// picture: {model (a model id, or null for a picture of no model), title, xml (a draw.io file or mxGraphModel), plain
// (its boxes are not entities, as the metamodel diagram's types: shown as made, never opened as entities)}
export function openInDrawio({ model = null, title = "picture", xml, plain = false }) {
  if (!xml) throw new Error("Nothing on the picture to open.");
  const key = `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 10)}`;
  const pic = { model: model || null, title: String(title || "picture"), xml: String(xml), plain: !!plain, at: Date.now() };
  sweep();
  let stored = false;
  try { window.localStorage.setItem(PREFIX + key, JSON.stringify(pic)); stored = true; } catch { /* too big, or private */ }
  if (!stored) { window.eaxScratch = window.eaxScratch || {}; window.eaxScratch[key] = pic; }
  const url = new URL(`#/drawio/open/${key}`, window.location.href).href;
  const tab = window.open(url, "_blank");            // not noopener: the fallback reads window.opener
  if (!tab) {
    try { window.localStorage.removeItem(PREFIX + key); } catch { /* none */ }
    throw new Error("The browser blocked the new tab: allow pop-ups for EA Explorer and try again.");
  }
  return key;
}

// in the new tab: the picture for this key, or null. {pic, reloadable}
export function takeScratch(key) {
  const session = `${PREFIX}${key}`;
  try {
    const kept = window.sessionStorage.getItem(session);
    if (kept) return { pic: JSON.parse(kept), reloadable: true };
  } catch { /* none */ }
  let pic = null;
  try {
    const raw = window.localStorage.getItem(PREFIX + key);
    if (raw) { pic = JSON.parse(raw); window.localStorage.removeItem(PREFIX + key); }
  } catch { /* none */ }
  if (!pic) {
    try { pic = window.opener?.eaxScratch?.[key] || null; if (pic) delete window.opener.eaxScratch[key]; } catch { pic = null; }
  }
  if (!pic) return null;
  let reloadable = false;
  try { window.sessionStorage.setItem(session, JSON.stringify(pic)); reloadable = true; } catch { /* too big: this time only */ }
  return { pic, reloadable };
}

export function forgetScratch(key) {
  try { window.sessionStorage.removeItem(`${PREFIX}${key}`); } catch { /* none */ }
}

// a file the API serves (a project document, a library file): a .drawio file opens in our draw.io (a picture of no
// model: look, export); anything else downloads as before
export async function openFile(path, fileName) {
  if (!/\.drawio$/i.test(String(fileName || ""))) return apiDownload(path, fileName);
  const u = await apiBlobUrl(path);
  try { openInDrawio({ model: null, title: String(fileName).replace(/\.drawio$/i, ""), xml: await (await fetch(u)).text() }); }
  finally { URL.revokeObjectURL(u); }
  return null;
}
