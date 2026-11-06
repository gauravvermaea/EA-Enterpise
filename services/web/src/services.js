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
      { name: "Create and copy models", text: "New root metamodels and models from Root or any model, with or without content and history; move to another framework; archive and delete", href: "#/metamodel", live: true },
      { name: "Metamodels with AI", text: "Your own language model drafts a metamodel through MCP; you review, trim and apply the draft", href: "#/metamodel/drafts", live: true },
      { name: "Library models and packages", text: "Library models, publish, withdraw and promote; download any model as zip or Excel and upload it through a placement wizard", href: "#/library", live: true },
      { name: "Library model packs", text: "Guidance, workbooks and any other files carried with a library model and its package, kept in Mayan", phase: "13" },
      { name: "Data entry", text: "Forms from the metamodel, a data entry page by entity type, relationships as you go, tags, retire, delete and roll back", href: "#/metamodel", live: true },
      { name: "Grids, search and saved views", text: "Spreadsheet grids for entities, relationships and the metamodel, paste from Excel; search every model; saved views", href: "#/search", live: true },
      { name: "Commits and publishing", text: "Stage changes, review and commit them, publish change sets", phase: "8" },
      { name: "Notifications and requests", text: "What happened on your models, requests between people like tickets, metamodel changes pushed down the hierarchy", href: "#/notifications", live: true },
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
      { name: "Roadmaps and transition architectures", text: "Baseline, transition and target plateaus, gaps and work packages; a timeline roadmap; effective dates to see the architecture on any future date; scenarios and options compared", phase: "later" },
      { name: "Document generation", text: "Word, PDF and PowerPoint deliverables from templates filled with live model data", phase: "later" },
      { name: "Cost and investment", text: "Cost per application rolled up to capabilities, value streams and organisations; run and change spend; business cases", phase: "later" },
      { name: "Risk, controls and compliance", text: "Regulatory obligations, controls mapped to the architecture, risk ratings, compliance gaps, technology radar and end-of-life alerts", phase: "later" },
      { name: "Process modelling", text: "BPMN 2.0 processes linked to the model, with versions, approval and maturity assessments", phase: "later" },
      { name: "Initiatives and delivery", text: "Gantt, status reports, work breakdown, task board, capex and opex budgets, risks and benefits tracking", phase: "later" },
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
      { name: "Published portal", text: "Browse and search an approved model without a role in the tool", phase: "later" },
      { name: "Computed attributes", text: "Formulas, inherited values and roll-ups such as capability health from its applications", phase: "later" },
      { name: "Entity approval and stakeholders", text: "Approval state per entity, stakeholders with your own roles, tag groups, form layouts and no-code automations", phase: "later" },
    ],
  },
  {
    title: "Diagrams, views and reports",
    items: [
      { name: "Diagrams (draw.io)", service: "drawio", text: "The draw.io editor, self-hosted", href: "/drawio/", live: true, integration: "28" },
      { name: "Reports (Superset)", service: "reports", text: "Dashboards: the model overview, the thirty standard reports and pick-list heatmaps, for the models you have", href: `${config.reportsUrl}/login/keycloak?next=/superset/dashboard/eax-model-overview/`, live: true },
      { name: "Documents (Mayan EDMS)", service: "documents", text: "Documents linked to entities", href: `${config.docsUrl}/`, live: true },
      { name: "Report views and catalogue", text: "A view per entity type with a column per attribute, kept in step with every metamodel; each model's Reports tab lists them", href: "#/metamodel", live: true },
      { name: "Standard reports", service: "reports", text: "All thirty: inventories, matrices, heatmaps, portfolio, risk and impact, data quality and governance, on one or several of your models", href: `${config.reportsUrl}/login/keycloak?next=/dashboard/list/`, live: true },
      { name: "Document management", text: "Mayan cabinets per model and version, linked to entities and library packs", phase: "13" },
      { name: "draw.io with the repository", text: "Draw with the model's own entities; diagrams feed the repository (also the desktop app)", phase: "28" },
      { name: "Standard views", text: "Pick a model (or several) and a view; get a draw.io file", phase: "30" },
      { name: "Slides (PowerPoint)", text: "Download views, diagrams, reports and dashboards as slides, gather several into one deck, on your own template", phase: "31" },
      { name: "Model tags and gap analysis", text: "Tag a whole model with its data, roll back to a tag; compare tags, models and parents at tags, without the noise; gap analysis and a gap report", phase: "8.3" },
      { name: "Viewpoints, maps and richer reports", text: "Any model through the ArchiMate 4 viewpoints VP-01 to VP-25 and your own, as diagram, catalog, heat map or matrix; value stream map and roadmap; TOGAF catalogues and matrices, dependency reports and a dashboard per audience (CEO, CFO, architects...)", href: "#/metamodel", live: true },
      { name: "What-if analysis", text: "Explore changes before making them, perhaps with a language model", phase: "later" },
      { name: "Drafts, approvals and publishing", text: "One consistent design for draft models, metamodel drafts, review rounds and publishing approval", phase: "8" },
      { name: "Test automation", text: "Run every unit, integration and UI test from the Health dashboard on a separate test database; tests work on copies of test models only", phase: "36.1" },
      { name: "Documentation, guidebooks and inline help", text: "A full documentation site, step-by-step guides per role and task, and help on every screen and field, searchable from the top bar", phase: "later" },
    ],
  },
  {
    title: "Data exchange and integration",
    items: [
      { name: "Import and export sheets", text: "Template download and CSV or Excel upload per entity type, one sheet for relations, collection sets loaded into staging", phase: "10.1" },
      { name: "ArchiMate exchange", text: "Import and export ArchiMate exchange files", phase: "33" },
      { name: "Integrations and reference data", text: "Connect to the rest of the estate", phase: "34" },
      { name: "Integration and ETL", text: "Drag-and-drop ETL with Apache Hop and its standard connectors: other APIs, our API, file dumps, into staging", phase: "34.1" },
      { name: "Architecture as code", text: "Models as YAML in Git, lint in pipelines, a command-line tool, scripts, import preview and an offline HTML export", phase: "later" },
      { name: "More connectors", text: "ServiceNow CMDB sync, end-of-life data, AWS, Azure, Confluence, Jira and Slack", phase: "later" },
    ],
  },
  {
    title: "Language models",
    items: [
      { name: "MCP server", service: "mcp", text: "Connect your own language model (Claude, ChatGPT, local models) to the repository", href: "#/mcp", live: true },
      { name: "MCP proposals", text: "Language models propose changes into staging, never make them", phase: "27" },
      { name: "AI assistant in the tool", text: "Ask the model questions; suggestions for relationships, descriptions, classifications, duplicates and fixes; draft artefacts", phase: "later" },
    ],
  },
  {
    title: "Platform",
    items: [
      { name: "Heartbeat", text: "API, database and job queue status", href: "#/heartbeat", live: true },
      { name: "API documentation (Swagger)", text: "Every API call, runnable in the browser", href: "/api/docs", live: true },
      { name: "SQL", text: "Run queries on the database with a database login and see the results", href: "#/sql", live: true, perm: "system.operate", roles: ["it-admin", "super-admin"] },
      { name: "My account (Keycloak)", text: "Password, sessions and sign-in settings", href: `${config.keycloakUrl}/realms/${config.realm}/account/`, live: true },
      // The Keycloak administration console of the master realm, opened on our realm. Sign in there with the
      // Keycloak administrator (EAX_KC_ADMIN, listed by "eax logins"), not with an EA Explorer user.
      // Roles are given here, in Keycloak (D92). Keycloak Admins and Super Admins hold realm-admin on our realm,
      // so they sign in to its console with their own EA Explorer login.
      { name: "Keycloak administration", text: "Give people roles, manage users, groups and identity providers. Sign in with your own login", href: `${config.keycloakUrl}/admin/${config.realm}/console/`, live: true, perm: "keycloak.console", roles: ["keycloak-admin", "super-admin"], badge: "Keycloak Admins" },
      { name: "Users and roles", text: "People, the EA Explorer roles their Keycloak roles give, their models, and the Keycloak role mapping", href: "#/users", live: true, perm: "users.read", roles: ["user-admin", "super-admin"] },
      { name: "Home dashboard and administration", text: "Live counts and the administration screens", phase: "10" },
      { name: "Backup and restore", text: "Back up now, scheduled backups, restore from the web or from a backup file you choose", phase: "8.4" },
      { name: "Enterprise readiness, part 1", text: "Release process and continuous integration, more automated tests, Superset tested end to end, monitoring and alerts", phase: "8.5" },
      { name: "Enterprise readiness, part 2", text: "Penetration test, encryption, scale test, high availability, disaster recovery, Active Directory, usability and accessibility", phase: "36.2" },
      { name: "Security hardening", text: "Enterprise identity and fine-grained rights", phase: "25" },
      { name: "Operations insight", text: "Health, usage, jobs and housekeeping", phase: "35" },
      { name: "Production deployment", text: "Upgrades that keep your data (a backup first, then the version's upgrade scripts; no clean restart in production), scale-out, Active Directory sign-in, another identity platform, auth and paths in the config, a key vault for passwords", phase: "36" },
      { name: "Industry models and documentation", text: "More industries with their packs, and the product's guides", phase: "39" },
      { name: "API tokens, privacy and archiving", text: "Service accounts and scoped tokens; personal data and POPIA; archive and purge models", phase: "later" },
      { name: "Several organisations", text: "Separate organisations in one installation, each with its own admins, users, branding and data", phase: "later" },
      { name: "Scale test and extensions", text: "A large-model performance test; custom pages, widgets and report types", phase: "later" },
    ],
  },
];
