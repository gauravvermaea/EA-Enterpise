// Every service the start page links to. "phase" is the build phase that delivers it
// (EA_Explorer_Build_Plan.xlsx); until then the tile shows as a placeholder.
import { config } from "./config";

export const groups = [
  {
    title: "Repository",
    items: [
      { name: "Metamodel", text: "Browse the ArchiMate 4 metamodel, then edit and publish it", phase: "1" },
      { name: "Model library", text: "Read-only reference models and industry models; deep copy", phase: "2" },
      { name: "Models", text: "Working models, roles and copies", phase: "4" },
      { name: "Data entry", text: "Forms and grids for entities and relationships", phase: "6" },
      { name: "Repository workflow", text: "Staging, reviews and publishing of change sets", phase: "8" },
      { name: "History and versions", text: "History, baselines and comparisons", phase: "9" },
      { name: "Architecture repository", text: "TOGAF parts: landscapes, standards, governance log", phase: "15" },
      { name: "Work copies and merge", text: "Split a model, work in parallel, merge back", phase: "19" },
      { name: "Dedupe", text: "Find and combine duplicate entities", phase: "21" },
    ],
  },
  {
    title: "Diagrams, views and reports",
    items: [
      { name: "Diagrams (draw.io)", text: "The draw.io editor, self-hosted", href: "/drawio/", live: true, integration: "28" },
      { name: "Standard views", text: "Pick a model and a view; get a draw.io file", phase: "30" },
      { name: "Reports (Superset)", text: "Dashboards and the standard reports", href: `${config.reportsUrl}/login/keycloak?next=/superset/dashboard/eax-phase0-sample/`, live: true },
      { name: "Documents (Mayan EDMS)", text: "Documents linked to entities", href: `${config.docsUrl}/`, live: true },
    ],
  },
  {
    title: "Data exchange",
    items: [
      { name: "CSV loads", text: "CSV templates, loads into staging and exports", phase: "32" },
      { name: "ArchiMate exchange", text: "Import and export ArchiMate exchange files", phase: "33" },
      { name: "MCP connection", text: "Connect your own language model", phase: "26" },
    ],
  },
  {
    title: "Platform",
    items: [
      { name: "Heartbeat", text: "API, database and job queue status", href: "#/heartbeat", live: true },
      { name: "API documentation (Swagger)", text: "Every API call, runnable in the browser", href: "/api/docs", live: true },
      { name: "My account (Keycloak)", text: "Password, sessions and sign-in settings", href: `${config.keycloakUrl}/realms/${config.realm}/account/`, live: true },
      { name: "Users and sign-in (Keycloak admin)", text: "Users, roles and identity providers", href: `${config.keycloakUrl}/admin/${config.realm}/console/`, live: true, role: "system-admin" },
      { name: "Mail (development)", text: "Mailpit: every mail the installation sends", href: "/mail/", live: true, devOnly: true },
      { name: "Administration", text: "Health, usage, backups, jobs and housekeeping", phase: "35" },
    ],
  },
];
