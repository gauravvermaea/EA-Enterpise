// Sign-in through Keycloak (OpenID Connect, authorisation code with PKCE).
// Roles are given in Keycloak; the API maps them to EA Explorer's eight roles (phase 3.1) and
// /api/v1/me says which the signed-in person has, what they allow and which models are theirs.
// When Keycloak is down, the break-glass account signs in through the API instead (D80).
import Keycloak from "keycloak-js";
import { config } from "./config";

export const keycloak = new Keycloak({
  url: config.keycloakUrl,
  realm: config.realm,
  clientId: config.clientId,
});

const BG_KEY = "eax-break-glass";
let breakGlass = null;     // { token, until } when signed in with the break-glass account
let me = null;             // /api/v1/me: roles, permissions, models
export let keycloakReachable = true;

function loadBreakGlass() {
  try {
    const raw = localStorage.getItem(BG_KEY);
    const bg = raw ? JSON.parse(raw) : null;
    if (bg && bg.token) return bg;   // no expiry (D100): until sign-out or a password change
    localStorage.removeItem(BG_KEY);
  } catch { /* storage blocked: break-glass lasts for this page only */ }
  return null;
}

export async function initAuth() {
  breakGlass = loadBreakGlass();
  if (!breakGlass) {
    try {
      await keycloak.init({
        onLoad: "check-sso",
        pkceMethod: "S256",
        silentCheckSsoRedirectUri: `${window.location.origin}/silent-check-sso.html`,
        checkLoginIframe: false,
      });
    } catch (err) {
      keycloakReachable = false;
      console.warn("Keycloak is not reachable", err);
    }
  }
  if (signedIn()) {
    try { me = await apiFetch("/api/v1/me"); } catch (err) { console.warn("Could not read /api/v1/me", err); }
  }
  return signedIn();
}

export function signedIn() {
  return !!breakGlass || keycloak.authenticated === true;
}

export function isBreakGlass() {
  return !!breakGlass;
}

export async function breakGlassSignIn(password) {
  const r = await fetch("/api/v1/break-glass/sign-in", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ password }),
  });
  const body = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(body.message || `${r.status} ${r.statusText}`);
  breakGlass = { token: body.access_token };
  try { localStorage.setItem(BG_KEY, JSON.stringify(breakGlass)); } catch { /* page only */ }
  window.location.hash = "#/";
  window.location.reload();
}

export function signOut() {
  if (breakGlass) {
    breakGlass = null;
    try { localStorage.removeItem(BG_KEY); } catch { /* nothing kept */ }
    window.location.hash = "#/";
    window.location.reload();
    return;
  }
  keycloak.logout({ redirectUri: config.publicUrl });
}

// The signed-in person as the API sees them
export function currentUser() {
  if (breakGlass) return { name: "Break-glass account", preferred_username: "break-glass" };
  return keycloak.tokenParsed || {};
}

// EA Explorer roles (mapped from Keycloak's), e.g. ["model-admin"]
export function roles() {
  return me?.roles || [];
}

const ROLE_NAMES = { "super-admin": "Super Admin", "it-admin": "IT Admin", "user-admin": "User Admin", "keycloak-admin": "Keycloak Admin",
  "model-creator": "Model Creator", "library-admin": "Library Admin", user: "User",
  "model-admin": "Model Admin", architect: "Architect", "model-sub-admin": "Model Sub Admin", "report-viewer": "Report Viewer",
  committer: "Committer", "history-viewer": "History Viewer" };
export const MODEL_ROLES = ["model-admin", "model-sub-admin", "committer", "architect", "history-viewer", "report-viewer"];
export const roleName = (r) => ROLE_NAMES[r] || r;

// Why a greyed-out control cannot be used: the role it needs and who gives it, so people can ask for it.
// Global roles (Super Admin, Model Creator, Library Admin...) are given in Keycloak by a User Admin;
// roles on a model by that model's Model Admins on its People tab.
const GLOBAL_ROLE_CODES = ["super-admin", "it-admin", "user-admin", "keycloak-admin", "model-creator", "library-admin"];
export function needsRole(roles, modelName) {
  const list = (Array.isArray(roles) ? roles : [roles]);
  const names = list.map((r) => roleName(r));
  const text = names.length > 1 ? `${names.slice(0, -1).join(", ")} or ${names[names.length - 1]}` : names[0];
  if (list.every((r) => GLOBAL_ROLE_CODES.includes(r))) {
    return `Needs the ${text} role. Ask a User Admin to give it to you (global roles are given in Keycloak).`;
  }
  return `Needs the ${text} role on ${modelName || "this model"}. Ask a Model Admin of ${modelName || "the model"} to give it to you on its People tab.`;
}

// Whether the signed-in person's global roles give a permission (see the API's eax/permissions.py)
export function can(permission) {
  return !!me?.permissions?.[permission];
}

// Whether they may do something on one model: their roles on it (or Super Admin)
export function canOn(model, permission) {
  if (can(permission)) return true;
  return !!me?.models?.find((x) => String(x.id) === String(model))?.permissions?.includes(permission);
}

// Their roles on a model (empty when none)
export function myRolesOn(model) {
  return me?.models?.find((x) => String(x.id) === String(model))?.roles || [];
}

export function myInfo() {
  return me;
}

async function authHeaders(extra = {}) {
  const headers = { ...extra };
  if (breakGlass) {
    headers.Authorization = `Bearer ${breakGlass.token}`;
  } else if (keycloak.authenticated) {
    await keycloak.updateToken(30).catch(() => keycloak.login());
    headers.Authorization = `Bearer ${keycloak.token}`;
  }
  return headers;
}

// Upload a form (multipart, for example a package file) and read the JSON answer (phase 4)
export async function apiUpload(path, form) {
  const response = await fetch(path, { method: "POST", body: form, headers: await authHeaders() });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    const err = new Error(body.message || `${response.status} ${response.statusText}`);
    err.status = response.status;
    err.body = body;   // for example the conflicts of a commit (phase 8)
    throw err;
  }
  return body;
}

// Download a file the API makes (for example a model package) and hand it to the browser to save (phase 4);
// with a body, the request is a POST (for example a comparison's Excel workbook, phase 8.3)
export async function apiDownload(path, fallbackName = "download", body = undefined) {
  const response = await fetch(path, body === undefined ? { headers: await authHeaders() }
    : { method: "POST", body: JSON.stringify(body), headers: await authHeaders({ "Content-Type": "application/json" }) });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.message || `${response.status} ${response.statusText}`);
  }
  const disposition = response.headers.get("Content-Disposition") || "";
  const name = (/filename\*?=(?:UTF-8'')?"?([^";]+)"?/i.exec(disposition) || [])[1];
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name ? decodeURIComponent(name) : fallbackName;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}

// fetch() with the access token, refreshed when it is about to expire.
export async function apiFetch(path, options = {}) {
  const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
  if (breakGlass) {
    headers.Authorization = `Bearer ${breakGlass.token}`;
  } else if (keycloak.authenticated) {
    await keycloak.updateToken(30).catch(() => keycloak.login());
    headers.Authorization = `Bearer ${keycloak.token}`;
  }
  const response = await fetch(path, { ...options, headers });
  if (breakGlass && response.status === 401) {   // the break-glass password was changed: the session is over
    signOut();
    throw new Error("The break-glass session has ended.");
  }
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    const err = new Error(body.message || `${response.status} ${response.statusText}`);
    err.status = response.status;
    err.body = body;   // for example the conflicts of a commit (phase 8): body.errors.conflicts
    throw err;
  }
  return body;
}
