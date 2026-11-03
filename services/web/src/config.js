// Installation settings, served by the web container as /config.js (from eaexplorer.env).
const raw = window.EAX_CONFIG || {};
const host = raw.hostname || window.location.hostname;
const port = raw.httpsPort || "443";
const withPort = (h) => (port === "443" ? `https://${h}` : `https://${h}:${port}`);

export const config = {
  version: raw.version || "dev",
  deployment: raw.deployment || "laptop",
  realm: raw.realm || "eaexplorer",
  clientId: raw.clientId || "eax-web",
  publicUrl: window.location.origin,
  keycloakUrl: `${window.location.origin}/auth`,
  reportsUrl: withPort(`reports.${host}`),
  docsUrl: withPort(`docs.${host}`),
};
