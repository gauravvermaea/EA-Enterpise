"""The standard reports and their Superset dashboards (no imports, so the setup service can read it).

The thirty standard reports of the requirements workbook (sheet Standard reports, SR-01 to SR-30), plus
the model overview (MOD-010) and the pick-list heatmaps (RPT-006): code, group, title, what it shows,
the report view it reads, the dashboard slug in Superset, and for matrices the standard roles of the
rows (a) and columns (b) (D137, D140).
"""

from __future__ import annotations


def _r(code, group, title, view, about, **extra):
    slug = "eax-" + code.lower().replace("-", "")
    return {"code": code, "group": group, "title": title, "view": f"rpt.{view}", "slug": slug, "about": about, **extra}


REPORTS: list[dict[str, str]] = [
    {"code": "MO", "group": "Overview", "title": "Model overview", "view": "rpt.mo_type_counts", "slug": "eax-model-overview",
     "about": "How many entities of each type, the models and recent changes (MOD-010)."},
    _r("SR-01", "Inventory", "Application portfolio inventory", "sr01_application_inventory",
       "Every application with owner, lifecycle, criticality, cost, vendor, hosting and TIME."),
    _r("SR-02", "Inventory", "Business capability catalogue", "sr02_capability_catalogue",
       "The capability hierarchy with levels, owners, maturity and how many applications support each."),
    _r("SR-03", "Inventory", "Technology component inventory", "sr03_technology_inventory",
       "Technology components with version, vendor, lifecycle and end of life."),
    _r("SR-04", "Inventory", "Data entity catalogue", "sr04_data_catalogue",
       "Business objects and data objects with owners and classification."),
    _r("SR-05", "Inventory", "Business process catalogue", "sr05_process_catalogue",
       "Processes and functions by level with owners and the roles that perform them."),
    _r("SR-06", "Inventory", "Interface and integration catalogue", "sr06_interfaces",
       "Flows and other links between applications and interfaces, source to target."),
    _r("SR-07", "Inventory", "Stakeholder and actor catalogue", "sr07_actors",
       "Actors, roles, collaborations and stakeholders."),
    _r("SR-08", "Inventory", "Motivation catalogue", "sr08_motivation",
       "Drivers, goals, outcomes, principles, requirements, constraints and assessments."),
    _r("SR-09", "Matrix", "Application against capability", "sr_matrix",
       "Which applications support which capabilities.", a="application", b="capability"),
    _r("SR-10", "Matrix", "Application against process", "sr_matrix",
       "Which applications serve which processes.", a="application", b="process"),
    _r("SR-11", "Matrix", "Application against data entity (CRUD)", "sr_matrix",
       "Which applications create, read, update or delete which data (the access type in each cell).", a="application", b="data"),
    _r("SR-12", "Matrix", "Application against technology", "sr_matrix",
       "Which technology each application runs on.", a="application", b="technology"),
    _r("SR-13", "Matrix", "Process against role", "sr_matrix",
       "Which actors and roles perform or own which processes.", a="process", b="actor"),
    _r("SR-14", "Matrix", "Capability against value stream", "sr_matrix",
       "Which capabilities enable which value stream stages.", a="capability", b="value_stream"),
    _r("SR-15", "Matrix", "Application interaction matrix", "sr_matrix",
       "Application-to-application flows.", a="application", b="application"),
    _r("SR-16", "Heatmap", "Capability heatmap", "sr02_capability_catalogue",
       "Capabilities coloured by the number of applications supporting them, by maturity and by criticality."),
    _r("SR-17", "Heatmap", "Technology lifecycle and end of life", "sr17_technology_lifecycle",
       "Technology by lifecycle phase and end-of-life year, and what is past or near its end of life."),
    _r("SR-18", "Portfolio", "Application TIME quadrant", "sr18_application_fit",
       "Applications by functional and technical fit (Tolerate, Invest, Migrate, Eliminate), with the TIME set on each."),
    _r("SR-19", "Portfolio", "Criticality against technical health", "sr18_application_fit",
       "Business criticality against technical fit for every application."),
    _r("SR-20", "Portfolio", "Cost by capability", "sr20_cost_by_capability",
       "Application and technology annual cost rolled up to the capabilities they support."),
    _r("SR-21", "Portfolio", "Vendor concentration", "sr21_vendors",
       "Applications and technology per vendor, with their cost."),
    _r("SR-22", "Risk and impact", "Impact analysis", "sr22_impact",
       "Everything that depends on a chosen entity, up to four steps away, with the path."),
    _r("SR-23", "Risk and impact", "Obsolescence risk", "sr23_obsolescence",
       "Applications and capabilities at risk from technology past, near or phasing out of its end of life."),
    _r("SR-24", "Risk and impact", "Single points of failure", "sr24_single_points",
       "Applications and technology ranked by dependants, and how many of them have no alternative."),
    _r("SR-25", "Risk and impact", "Rationalisation candidates", "sr25_rationalisation",
       "Capabilities served by more than one application, and the applications that overlap."),
    _r("SR-26", "Data quality", "Completeness by type and owner", "sr26_completeness",
       "How complete each type and owner is, and the entities missing required values."),
    _r("SR-27", "Data quality", "Orphans and missing relationships", "sr27_orphans",
       "Entities with no relationships, no parent and no children."),
    _r("SR-28", "Data quality", "Duplicate candidates", "sr28_duplicates",
       "Entities of the same type with the same or similar names, with a similarity score."),
    _r("SR-29", "Governance", "Change activity", "sr29_change_activity",
       "Changes by week, model, person and kind over the last two years."),
    _r("SR-30", "Governance", "Comparison with the source model", "sr30_source_comparison",
       "Each model against the model it was created from: kept, changed, new and removed entities (gap analysis)."),
    {"code": "HM", "group": "Heatmap", "title": "Pick-list heatmaps", "view": "rpt.mo_pick_list_counts", "slug": "eax-heatmaps",
     "about": "How the values of every pick list are spread over entities (RPT-006)."},
]
