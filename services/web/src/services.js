// Every service the start page links to, and everything agreed and still to come (D109). "phase" is the
// build phase that delivers it (EA_Explorer_Build_Plan.xlsx); until then the tile shows as a placeholder.
// "later" means agreed but not yet given a phase. Keep this list in step with the build plan.
import { config } from "./config";

export const groups = [
  {
    title: "Models and the library",
    items: [
      { name: "Models", text: "Every model you may open, as a list or a hierarchy tree; its entities, relationships and metamodel (Model Admins change it)", href: "#/metamodel", live: true },
      { name: "Model library", text: "Root metamodels (ArchiMate 4, your own) and reference models (insurance now, more industries later), with a browser", href: "#/library", live: true },
      { name: "Create and copy models", text: "Build root metamodels from the Root model or a copy; create models from them; deep copy; move to a new framework version (ArchiMate 5)", phase: "4" },
      { name: "Library models and packages", text: "Create a model as a library model with its pack and any other files, promote a model, download and upload packages through a placement wizard", phase: "4" },
      { name: "Data entry", text: "Forms per entity type, a data entry page with relations as you go, and grids", phase: "6" },
      { name: "Grids, search and saved views", text: "Work with many records at once and find anything", phase: "7" },
      { name: "Commits and publishing", text: "Stage changes, review and commit them, publish change sets", phase: "8" },
      { name: "Notifications and workflows", text: "Metamodel changes pushed down to child models (forced or accepted), change documents, notifications kept until resolved with a description", phase: "8.1" },
      { name: "History and change log", text: "Field-level history, restore a record, the model's change log", phase: "9" },
      { name: "Validation and data quality", text: "Rules, scores and failing checks across models", phase: "12" },
    ],
  },
  {
    title: "Architecture projects and repository",
    items: [
      { name: "Architecture projects and the ADM", text: "Projects that say which ADM phase they are in, with gates, iterations and a dashboard; several projects on one model, or on a copy merged back", phase: "15" },
      { name: "Principles, standards and reference library", text: "Organisation-wide: principles kept as versions (projects told when one changes), standards, glossary, EA capability, landscapes", phase: "15.1" },
      { name: "Decision and governance logs", text: "Per project: decisions, compliance reviews, dispensations, requirements, risks and change requests, rolled up across projects", phase: "16" },
      { name: "Project setup wizard", text: "Set up an architecture project in one pass: its models, people, repository and starter material", phase: "16.1" },
      { name: "Artefacts and deliverables", text: "Produce each deliverable from a library template, review and approve it, store it read-only by ADM phase", phase: "16.2" },
    ],
  },
  {
    title: "Working together",
    items: [
      { name: "Work copies and merge", text: "Split a model, work in parallel, merge back", phase: "19" },
      { name: "Dedupe", text: "Find and combine duplicate entities in a model", phase: "21" },
      { name: "Ownership and collaboration", text: "Owners, comments, tasks and approval rules by type", phase: "22" },
      { name: "Portfolio, lifecycle and impact", text: "Application portfolio management and impact analysis", phase: "23" },
      { name: "Surveys", text: "Ask people for information through dynamic survey sheets and use the answers", phase: "38.1" },
    ],
  },
  {
    title: "Diagrams, views and reports",
    items: [
      { name: "Diagrams (draw.io)", text: "The draw.io editor, self-hosted", href: "/drawio/", live: true, integration: "28" },
      { name: "Reports (Superset)", text: "Dashboards and the standard reports", href: `${config.reportsUrl}/login/keycloak?next=/superset/dashboard/eax-phase0-sample/`, live: true },
      { name: "Documents (Mayan EDMS)", text: "Documents linked to entities", href: `${config.docsUrl}/`, live: true },
      { name: "Report views", text: "Typed views of every published metamodel for Superset and SQL", phase: "5" },
      { name: "Standard reports", text: "Thirty standard reports, including reports across every model you may read", phase: "11" },
      { name: "Document management", text: "Mayan cabinets per model and version, linked to entities and library packs", phase: "13" },
      { name: "draw.io with the repository", text: "Draw with the model's own entities; diagrams feed the repository (also the desktop app)", phase: "28" },
      { name: "Standard views", text: "Pick a model (or several) and a view; get a draw.io file", phase: "30" },
      { name: "Model versions and gap analysis", text: "Version a model and roll it back; compare it with its own versions or another model, without the noise; gap analysis and a gap report", phase: "24.1" },
      { name: "What-if analysis", text: "Explore changes before making them, perhaps with a language model", phase: "later" },
    ],
  },
  {
    title: "Data exchange and integration",
    items: [
      { name: "Import and export sheets", text: "Dynamic sheets per entity type (Excel and CSV), one for relations, collection sets loaded into staging", phase: "32" },
      { name: "ArchiMate exchange", text: "Import and export ArchiMate exchange files", phase: "33" },
      { name: "Integrations and reference data", text: "Connect to the rest of the estate", phase: "34" },
      { name: "Integration and ETL", text: "Drag-and-drop ETL with standard connectors: other APIs, our API, file dumps", phase: "34.1" },
    ],
  },
  {
    title: "Language models",
    items: [
      { name: "MCP server", text: "Connect your own language model (Claude, ChatGPT, local models) to the repository", href: "#/mcp", live: true },
      { name: "MCP proposals", text: "Language models propose changes into staging, never make them", phase: "27" },
    ],
  },
  {
    title: "Platform",
    items: [
      { name: "Heartbeat", text: "API, database and job queue status", href: "#/heartbeat", live: true },
      { name: "API documentation (Swagger)", text: "Every API call, runnable in the browser", href: "/api/docs", live: true },
      { name: "SQL", text: "Run queries on the database with a database login and see the results", href: "#/sql", live: true, perm: "system.operate" },
      { name: "My account (Keycloak)", text: "Password, sessions and sign-in settings", href: `${config.keycloakUrl}/realms/${config.realm}/account/`, live: true },
      // The Keycloak administration console of the master realm, opened on our realm. Sign in there with the
      // Keycloak administrator (EAX_KC_ADMIN, listed by "eax logins"), not with an EA Explorer user.
      // Roles are given here, in Keycloak (D92). Keycloak Admins and Super Admins hold realm-admin on our realm,
      // so they sign in to its console with their own EA Explorer login.
      { name: "Keycloak administration", text: "Give people roles, manage users, groups and identity providers. Sign in with your own login", href: `${config.keycloakUrl}/admin/${config.realm}/console/`, live: true, perm: "keycloak.console", badge: "Keycloak Admins" },
      { name: "Users and roles", text: "People, the EA Explorer roles their Keycloak roles give, their models, and the Keycloak role mapping", href: "#/users", live: true, perm: "users.read" },
      { name: "Home dashboard and administration", text: "Live counts and the administration screens", phase: "10" },
      { name: "Backup and restore", text: "Complete backups and restores, also from the web", phase: "14" },
      { name: "Security hardening", text: "Enterprise identity and fine-grained rights", phase: "25" },
      { name: "Operations insight", text: "Health, usage, jobs and housekeeping", phase: "35" },
      { name: "Production deployment", text: "Scale-out, Active Directory sign-in, another identity platform, auth and paths in the config, a key vault for passwords", phase: "36" },
      { name: "Industry models and documentation", text: "More industries with their packs, and the product's guides", phase: "39" },
    ],
  },
];
