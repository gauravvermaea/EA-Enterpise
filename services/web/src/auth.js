// Sign-in through Keycloak (OpenID Connect, authorisation code with PKCE).
import Keycloak from "keycloak-js";
import { config } from "./config";

export const keycloak = new Keycloak({
  url: config.keycloakUrl,
  realm: config.realm,
  clientId: config.clientId,
});

export async function initAuth() {
  try {
    await keycloak.init({
      onLoad: "check-sso",
      pkceMethod: "S256",
      silentCheckSsoRedirectUri: `${window.location.origin}/silent-check-sso.html`,
      checkLoginIframe: false,
    });
  } catch (err) {
    console.warn("Keycloak is not reachable yet", err);
  }
  return keycloak.authenticated === true;
}

export function roles() {
  return keycloak.tokenParsed?.realm_access?.roles || [];
}

// fetch() with the access token, refreshed when it is about to expire.
export async function apiFetch(path, options = {}) {
  const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
  if (keycloak.authenticated) {
    await keycloak.updateToken(30).catch(() => keycloak.login());
    headers.Authorization = `Bearer ${keycloak.token}`;
  }
  const response = await fetch(path, { ...options, headers });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.message || `${response.status} ${response.statusText}`);
  return body;
}
