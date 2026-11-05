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


# ================================================================ phase 8.2 (D161): viewpoints, TOGAF, dependencies, audiences
# Everything below is product data: the seed brings the database tables in line with it on every start
# (eax.seed.catalog), so the reports, the Reports tab and the Viewpoints tab read one list.

# ---------------------------------------------------------------- audiences (D153): who a report interests; not roles
AUDIENCES: list[tuple[str, str, str]] = [
    # code, name, group
    ("ceo", "CEO", "Executive"), ("cfo", "CFO", "Executive"), ("cio", "CIO", "Executive"), ("cto", "CTO", "Executive"),
    ("coo", "COO", "Executive"), ("cro", "Chief Risk Officer", "Executive"),
    ("ciso", "Chief Information Security Officer", "Executive"), ("cdo", "Chief Data Officer", "Executive"),
    ("cco", "Chief Compliance Officer", "Executive"),
    ("bu_head", "Business unit head", "Business"), ("product_owner", "Product owner", "Business"),
    ("process_owner", "Process owner", "Business"), ("change_manager", "Change manager", "Business"),
    ("portfolio_manager", "Portfolio manager", "Business"),
    ("enterprise_architect", "Enterprise architect", "Architecture"), ("business_architect", "Business architect", "Architecture"),
    ("solution_architect", "Solution architect", "Architecture"), ("application_architect", "Application architect", "Architecture"),
    ("data_architect", "Data architect", "Architecture"), ("technology_architect", "Technology architect", "Architecture"),
    ("integration_architect", "Integration architect", "Architecture"), ("security_architect", "Security architect", "Architecture"),
    ("architecture_board", "Architecture board", "Architecture"),
    ("application_owner", "Application owner", "Operations and control"), ("it_operations", "IT operations", "Operations and control"),
    ("procurement", "Procurement and vendor manager", "Operations and control"),
    ("internal_audit", "Internal audit", "Operations and control"), ("model_owner", "Model owner", "Operations and control"),
    ("data_steward", "Data steward", "Operations and control"),
]

# ---------------------------------------------------------------- viewpoints (VP-01 to VP-25)
# The 25 example viewpoints of the ArchiMate 4 Specification (Appendix C), as data: the element types and
# relationship types each shows, in our own words. A model is shown through a viewpoint as a diagram, a
# catalog, a matrix or a heat map coloured by an attribute (Section 13.4). Organisations add their own
# (Library Admins); built-in ones cannot be changed.
_ALL_RELS = ["Composition", "Aggregation", "Assignment", "Realization", "Serving", "Access", "Influence", "Association",
             "Triggering", "Flow", "Specialization"]
_MOT_RELS = ["Composition", "Aggregation", "Realization", "Influence", "Association", "Specialization"]
_CORE_ACT = ["BusinessActor", "Role", "Collaboration", "BusinessInterface", "ApplicationComponent", "ApplicationInterface",
             "Node", "Device", "SystemSoftware", "TechnologyInterface", "CommunicationNetwork", "Path", "Equipment", "Facility",
             "DistributionNetwork"]
_BEH = ["Service", "Process", "Function", "Event"]
_PASS = ["BusinessObject", "DataObject", "Artifact", "Material"]
_CORE = _CORE_ACT + _BEH + _PASS + ["Product"]


def _vp(n, name, category, purpose, concerns, stakeholders, elements, rels=None, heat="Lifecycle", audiences=()):
    return {"code": f"VP-{n:02d}", "name": name, "category": category, "purpose": purpose, "concerns": concerns,
            "stakeholders": stakeholders, "element_types": list(dict.fromkeys(elements + ["Grouping"])),
            "relationship_types": rels or _ALL_RELS, "heat_attribute": heat, "audiences": list(audiences)}


VIEWPOINTS: list[dict] = [
    _vp(1, "Organization", "Basic: composition", "Designing, deciding, informing",
        "Who is in the organisation, how it is structured and where people work",
        "Enterprise, process and business architects, managers, employees",
        ["BusinessActor", "Role", "Collaboration", "BusinessInterface", "Location"], heat="Owner",
        audiences=["coo", "bu_head", "business_architect", "enterprise_architect"]),
    _vp(2, "Application Structure", "Basic: composition", "Designing",
        "How applications are built from components and interfaces, and the data they hold",
        "Application and solution architects", ["ApplicationComponent", "ApplicationInterface", "DataObject"],
        audiences=["application_architect", "solution_architect", "application_owner"]),
    _vp(3, "Information Structure", "Basic: composition", "Designing",
        "The structure of the information the enterprise uses, from business objects to data and files",
        "Data, information and business architects", ["BusinessObject", "DataObject", "Artifact", "Meaning"],
        heat="DataClassification", audiences=["cdo", "data_architect", "data_steward"]),
    _vp(4, "Technology", "Basic: composition", "Designing",
        "The technology platforms, their parts, networks and the technology services they offer",
        "Infrastructure and technology architects, operations",
        ["Node", "Device", "SystemSoftware", "TechnologyInterface", "CommunicationNetwork", "Path", "Artifact", "Location"] + _BEH,
        audiences=["cto", "technology_architect", "it_operations"]),
    _vp(5, "Layered", "Basic: composition", "Designing, informing",
        "The whole picture from business through application to technology in one view",
        "Enterprise architects, managers", _CORE + ["Location"],
        audiences=["enterprise_architect", "solution_architect", "cio"]),
    _vp(6, "Physical", "Basic: composition", "Designing",
        "Physical equipment, facilities, distribution networks and materials, and where they are",
        "Infrastructure architects, operations",
        ["Equipment", "Facility", "DistributionNetwork", "Material", "Location", "Node", "Device", "Path", "CommunicationNetwork"],
        audiences=["technology_architect", "it_operations"]),
    _vp(7, "Product", "Basic: support", "Designing, deciding",
        "What a product is made of: its services, the value it gives and who provides it",
        "Product managers, business architects, sales",
        ["Product", "Service", "BusinessActor", "Role", "Collaboration", "BusinessInterface", "Process", "Function", "Event",
         "BusinessObject", "ApplicationComponent", "ApplicationInterface", "Value"],
        audiences=["product_owner", "bu_head", "business_architect"]),
    _vp(8, "Application Usage", "Basic: support", "Designing, deciding",
        "Which applications the business uses and for what",
        "Business and application architects, application owners",
        ["ApplicationComponent", "ApplicationInterface", "Service", "Process", "Function", "Event", "BusinessActor", "Role",
         "Collaboration", "BusinessObject", "DataObject"],
        audiences=["application_owner", "process_owner", "application_architect"]),
    _vp(9, "Technology Usage", "Basic: support", "Designing, deciding",
        "Which technology the applications depend on, and how",
        "Application and technology architects, operations",
        ["Node", "Device", "SystemSoftware", "TechnologyInterface", "CommunicationNetwork", "Artifact", "Service", "Process",
         "Function", "Event", "ApplicationComponent", "DataObject"],
        audiences=["technology_architect", "application_architect", "it_operations"]),
    _vp(10, "Business Process Cooperation", "Basic: cooperation", "Designing, deciding",
        "How business processes work together, what triggers them and what they exchange",
        "Process and business architects, process owners",
        ["Process", "Function", "Event", "Service", "BusinessActor", "Role", "Collaboration", "BusinessObject",
         "ApplicationComponent", "Location"],
        audiences=["process_owner", "coo", "business_architect"]),
    _vp(11, "Application Cooperation", "Basic: cooperation", "Designing",
        "How applications work together: flows, interfaces and the services they offer each other",
        "Application, integration and solution architects",
        ["ApplicationComponent", "ApplicationInterface", "Service", "Function", "Process", "Event", "DataObject", "Location"],
        heat="Criticality", audiences=["integration_architect", "application_architect", "solution_architect"]),
    _vp(12, "Service Realization", "Basic: realization", "Designing, deciding",
        "How business services are realised by processes, people and applications",
        "Process and business architects, product managers",
        ["Service", "Process", "Function", "Event", "BusinessActor", "Role", "Collaboration", "BusinessObject", "DataObject",
         "ApplicationComponent", "Product"],
        audiences=["business_architect", "process_owner", "product_owner"]),
    _vp(13, "Implementation and Deployment", "Basic: realization", "Designing",
        "How applications are deployed on technology: artifacts, nodes, system software and networks",
        "Application and technology architects, operations",
        ["ApplicationComponent", "ApplicationInterface", "DataObject", "Artifact", "Node", "Device", "SystemSoftware",
         "TechnologyInterface", "CommunicationNetwork", "Path", "Service"],
        audiences=["technology_architect", "solution_architect", "it_operations"]),
    _vp(14, "Stakeholder", "Motivation", "Designing, deciding, informing",
        "Who the stakeholders are, what drives them, how they assess things and the goals that follow",
        "Executives, enterprise and business architects",
        ["Stakeholder", "Driver", "Assessment", "Goal", "Outcome"], rels=_MOT_RELS, heat="Owner",
        audiences=["ceo", "enterprise_architect", "architecture_board"]),
    _vp(15, "Goal Realization", "Motivation", "Designing, deciding",
        "How goals are refined into outcomes, principles and requirements",
        "Executives, enterprise architects", ["Goal", "Outcome", "Principle", "Requirement"], rels=_MOT_RELS, heat="Priority",
        audiences=["ceo", "enterprise_architect", "architecture_board"]),
    _vp(16, "Requirements Realization", "Motivation", "Designing, deciding",
        "Which parts of the architecture realise each requirement",
        "Enterprise, solution and business architects",
        ["Requirement", "Principle", "Goal", "Outcome", "ApplicationComponent", "Service", "Process", "Function",
         "BusinessActor", "Role", "Node", "SystemSoftware", "DataObject", "BusinessObject", "Product", "Capability",
         "Resource", "CourseOfAction"], heat="Priority",
        audiences=["solution_architect", "enterprise_architect", "cco"]),
    _vp(17, "Motivation", "Motivation", "Designing, deciding, informing",
        "The whole motivation of the enterprise: stakeholders, drivers, assessments, goals, outcomes, principles, "
        "requirements, meanings and values",
        "Executives, enterprise architects, architecture board",
        ["Stakeholder", "Driver", "Assessment", "Goal", "Outcome", "Principle", "Requirement", "Meaning", "Value"],
        rels=_MOT_RELS, heat="Priority", audiences=["ceo", "architecture_board", "enterprise_architect"]),
    _vp(18, "Strategy", "Strategy", "Deciding, informing",
        "The strategic direction: capabilities, resources, courses of action, value streams and outcomes",
        "Executives, enterprise and business architects",
        ["Capability", "Resource", "CourseOfAction", "ValueStream", "Outcome"], heat="Maturity",
        audiences=["ceo", "coo", "enterprise_architect", "business_architect"]),
    _vp(19, "Capability Map", "Strategy", "Deciding, informing",
        "The capabilities of the enterprise, their structure and the resources and outcomes linked to them",
        "Executives, business architects", ["Capability", "Resource", "Outcome"], heat="Maturity",
        audiences=["ceo", "coo", "cio", "business_architect", "bu_head"]),
    _vp(20, "Value Stream", "Strategy", "Deciding, informing",
        "The stages that create value for a stakeholder, and the capabilities that enable each stage",
        "Executives, business architects, product owners",
        ["ValueStream", "Capability", "Outcome", "Stakeholder", "Value"], heat="Maturity",
        audiences=["ceo", "coo", "business_architect", "product_owner"]),
    _vp(21, "Outcome Realization", "Strategy", "Deciding",
        "How capabilities, value streams and core elements produce the outcomes the business wants",
        "Executives, business and enterprise architects",
        ["Capability", "Resource", "ValueStream", "CourseOfAction", "Outcome", "Goal", "Value", "Meaning", "Product",
         "Service", "Process"], heat="Maturity", audiences=["ceo", "enterprise_architect", "portfolio_manager"]),
    _vp(22, "Resource Map", "Strategy", "Deciding",
        "The resources of the enterprise (people, applications, technology, information) and the capabilities they serve",
        "Executives, business architects, portfolio managers",
        ["Resource", "Capability", "WorkPackage", "BusinessActor", "Role", "ApplicationComponent", "Node", "BusinessObject",
         "DataObject", "Artifact", "Equipment", "Facility", "Material"], heat="Criticality",
        audiences=["coo", "cfo", "portfolio_manager", "business_architect"]),
    _vp(23, "Project", "Implementation and migration", "Deciding, informing",
        "The work packages of a change, their deliverables, events and the people and goals involved",
        "Programme and project managers, enterprise architects",
        ["WorkPackage", "Deliverable", "Event", "BusinessActor", "Role", "Goal", "Outcome", "Requirement"], heat="Priority",
        audiences=["change_manager", "portfolio_manager", "enterprise_architect"]),
    _vp(24, "Migration", "Implementation and migration", "Deciding, informing",
        "The plateaus from baseline through transitions to target, and what moves between them",
        "Enterprise architects, programme managers", ["Plateau", "Deliverable", "Event"], heat="ArchitectureState",
        audiences=["enterprise_architect", "architecture_board", "cio"]),
    _vp(25, "Implementation and Migration", "Implementation and migration", "Deciding, informing",
        "The programme of change: work packages, deliverables and plateaus, and the architecture they change",
        "Programme managers, enterprise and solution architects",
        ["WorkPackage", "Deliverable", "Plateau", "Event", "BusinessActor", "Role", "Requirement", "Goal", "Outcome",
         "ApplicationComponent", "Node", "SystemSoftware", "Capability", "Service", "Process"], heat="ArchitectureState",
        audiences=["portfolio_manager", "change_manager", "enterprise_architect", "cio"]),
]
assert len(VIEWPOINTS) == 25


def _f(code, family, group, title, view, about, audiences, **extra):
    slug = "eax-" + code.lower().replace("-", "")
    return {"code": code, "family": family, "group": group, "title": title, "view": f"rpt.{view}", "slug": slug,
            "about": about, "audiences": audiences, **extra}


for _v in VIEWPOINTS:
    REPORTS.append(_f(_v["code"], "Viewpoint", _v["category"], f"{_v['name']} viewpoint", "vp_elements",
                      f"The model through the {_v['name']} viewpoint: {_v['concerns'][0].lower()}{_v['concerns'][1:]}. "
                      "As a catalog, a matrix, a network and a heat map.", _v["audiences"], viewpoint=_v["code"]))

# TOGAF 10 catalogs and matrices the standard reports did not have
_T = "TOGAF catalogue"
_M = "TOGAF matrix"
REPORTS += [
    _f("TC-01", _T, "Preliminary and A", "Principles catalogue", "tc_principles",
       "Architecture principles with priority, owner and the goals they support.",
       ["architecture_board", "enterprise_architect", "cio"]),
    _f("TC-02", _T, "A: vision", "Stakeholder catalogue", "tc_stakeholders",
       "Stakeholders and the drivers, goals and requirements they are concerned with.",
       ["enterprise_architect", "change_manager", "architecture_board"]),
    _f("TC-03", _T, "A: vision", "Driver, goal and outcome catalogue", "tc_motivation_chain",
       "From each driver through assessments and goals to the outcomes and requirements that realise them.",
       ["ceo", "enterprise_architect", "architecture_board"]),
    _f("TC-04", _T, "Requirements management", "Requirements catalogue", "tc_requirements",
       "Requirements with priority, what they realise and what realises them.",
       ["solution_architect", "enterprise_architect", "cco", "internal_audit"]),
    _f("TC-05", _T, "B to D", "Location catalogue", "tc_locations",
       "Locations and what is there: organisation units, technology and facilities.",
       ["coo", "technology_architect", "it_operations"]),
    _f("TC-06", _T, "B: business", "Product and service catalogue", "tc_products",
       "Products, the services they bundle and the business objects they carry.",
       ["product_owner", "bu_head", "business_architect"]),
    _f("TC-07", _T, "B: business", "Contract and measure catalogue", "tc_measures",
       "Goals and outcomes with how they are measured.",
       ["ceo", "cfo", "architecture_board", "portfolio_manager"]),
    _f("TC-08", _T, "E and F", "Work package and roadmap catalogue", "tc_roadmap",
       "Work packages, deliverables and plateaus with their dates, as a roadmap.",
       ["portfolio_manager", "change_manager", "cio", "enterprise_architect"]),
    _f("TC-09", _T, "B: business", "Role catalogue", "tc_roles",
       "Roles, the actors that fill them and the processes they perform.",
       ["coo", "process_owner", "business_architect"]),
    _f("TM-01", _M, "B: business", "Business interaction matrix", "type_pairs",
       "Which organisation units and collaborations work with which.",
       ["coo", "business_architect", "bu_head"], a_types=["BusinessActor", "Collaboration"],
       b_types=["BusinessActor", "Collaboration"]),
    _f("TM-02", _M, "B: business", "Actor and role matrix", "type_pairs",
       "Which actors fill which roles.", ["coo", "process_owner", "business_architect"],
       a_types=["BusinessActor", "Collaboration"], b_types=["Role"]),
    _f("TM-03", _M, "C: application", "Role and application matrix", "type_pairs",
       "Which roles use or are served by which applications.", ["application_owner", "security_architect", "ciso"],
       a_types=["Role"], b_types=["ApplicationComponent"]),
    _f("TM-04", _M, "C: application", "Application and organisation matrix", "type_pairs",
       "Which organisation units use or are served by which applications.", ["cio", "bu_head", "application_architect"],
       a_types=["ApplicationComponent"], b_types=["BusinessActor"]),
    _f("TM-05", _M, "B to D", "Location matrix", "type_pairs",
       "What is at each location.", ["coo", "technology_architect", "it_operations"],
       a_types=["Location"], b_types=_CORE + ["Capability"]),
    _f("TM-06", _M, "C: data", "Data entity and business function matrix", "type_pairs",
       "Which processes and functions create, read, update or delete which data.", ["cdo", "data_architect", "process_owner"],
       a_types=["Process", "Function"], b_types=["BusinessObject", "DataObject"]),
    _f("TM-07", _M, "C: data", "Data security matrix", "tm_data_security",
       "Who and what accesses each item of data, with its classification: restricted and confidential data first.",
       ["ciso", "cdo", "security_architect", "internal_audit", "cco"]),
    _f("TM-08", _M, "A and B", "Strategy and capability matrix", "type_pairs",
       "Which goals, outcomes and courses of action each capability serves.", ["ceo", "coo", "business_architect"],
       a_types=["Capability"], b_types=["Goal", "Outcome", "CourseOfAction"]),
    _f("TM-09", _M, "B: business", "Capability and organisation matrix", "tm_capability_org",
       "Which organisation units each capability depends on, through the applications, processes and roles that "
       "realise it.", ["coo", "bu_head", "business_architect"]),
    _f("TM-10", _M, "A: vision", "Stakeholder and concern matrix", "type_pairs",
       "Which drivers, goals and requirements each stakeholder is concerned with.",
       ["enterprise_architect", "change_manager"], a_types=["Stakeholder"],
       b_types=["Driver", "Goal", "Requirement", "Assessment"]),
    _f("TM-11", _M, "E and F", "Plateau and architecture matrix", "type_pairs",
       "What each plateau (baseline, transition, target) holds: the migration from one to the next.",
       ["enterprise_architect", "architecture_board", "cio", "portfolio_manager"],
       a_types=["Plateau"], b_types=_CORE + ["Capability"]),
    _f("TM-12", _M, "B: business", "Service and process matrix", "type_pairs",
       "Which processes realise which services, and which services serve which processes.",
       ["process_owner", "business_architect"], a_types=["Service"], b_types=["Process", "Function"]),
]

# dependency reports (D149)
_D = "Dependency"
REPORTS += [
    _f("DR-01", _D, "Dependency", "Dependencies of an entity", "dr_dependencies",
       "Choose an entity: what it depends on (upstream) and what depends on it (downstream), up to six steps, with the path.",
       ["solution_architect", "enterprise_architect", "change_manager", "it_operations"]),
    _f("DR-02", _D, "Dependency", "Dependency matrix between two types", "entity_pairs",
       "Choose the row type and the column type: every relationship between their entities.",
       ["enterprise_architect", "solution_architect", "application_architect"]),
    _f("DR-03", _D, "Dependency", "Impact chain from technology to value stream", "dr_impact_chain",
       "Each technology, the applications it serves, the processes and capabilities they support and the value streams "
       "those enable, with end-of-life risk.", ["cto", "cro", "cio", "technology_architect", "enterprise_architect"]),
    _f("DR-04", _D, "Dependency", "Dependency counts and hot spots", "dr_fan",
       "How many entities each entity depends on and how many depend on it, banded by thresholds you choose.",
       ["cro", "cto", "solution_architect", "it_operations"]),
]

# standard report audiences (D153, the table agreed on 4 Nov 2026)
STANDARD_AUDIENCES = {
    "MO": ["model_owner", "enterprise_architect", "architecture_board"],
    "SR-01": ["cio", "application_architect", "application_owner", "portfolio_manager"],
    "SR-02": ["ceo", "coo", "business_architect", "bu_head"],
    "SR-03": ["cto", "technology_architect", "it_operations"], "SR-04": ["cdo", "data_architect"],
    "SR-05": ["coo", "process_owner", "business_architect"],
    "SR-06": ["integration_architect", "solution_architect", "it_operations"],
    "SR-07": ["enterprise_architect", "change_manager"], "SR-08": ["ceo", "architecture_board", "enterprise_architect"],
    "SR-09": ["cio", "business_architect", "application_architect"], "SR-10": ["coo", "process_owner", "application_owner"],
    "SR-11": ["cdo", "data_architect", "ciso"], "SR-12": ["cto", "technology_architect", "application_architect"],
    "SR-13": ["coo", "process_owner"], "SR-14": ["ceo", "coo", "business_architect", "product_owner"],
    "SR-15": ["integration_architect", "solution_architect"], "SR-16": ["ceo", "cio", "coo", "business_architect"],
    "SR-17": ["cto", "cro", "technology_architect", "it_operations"], "SR-18": ["cio", "cfo", "portfolio_manager"],
    "SR-19": ["cio", "cto", "portfolio_manager"], "SR-20": ["cfo", "ceo", "cio"], "SR-21": ["cfo", "procurement", "cro"],
    "SR-22": ["solution_architect", "change_manager", "enterprise_architect"],
    "SR-23": ["cro", "cto", "ciso", "internal_audit"], "SR-24": ["cro", "cto", "it_operations"],
    "SR-25": ["cio", "cfo", "portfolio_manager"], "SR-26": ["model_owner", "enterprise_architect"],
    "SR-27": ["model_owner", "data_steward"], "SR-28": ["model_owner", "data_steward"],
    "SR-29": ["architecture_board", "internal_audit", "model_owner"], "SR-30": ["enterprise_architect", "architecture_board"],
    "HM": ["model_owner", "data_steward", "enterprise_architect"],
}
for _r in REPORTS:
    _r.setdefault("family", "Standard")
    _r.setdefault("audiences", STANDARD_AUDIENCES.get(_r["code"], []))

# one dashboard per audience: the headline charts of that audience's reports (AU-<code>)
for _code, _name, _group in AUDIENCES:
    REPORTS.append({"code": f"AU-{_code}", "family": "Audience", "group": _group, "title": f"{_name} dashboard",
                    "view": "", "slug": f"eax-au-{_code.replace('_', '-')}", "audience": _code, "audiences": [_code],
                    "about": f"The headline view of every report a {_name.lower() if _group != 'Executive' else _name} "
                             "usually wants, on one page."})

_codes = [r["code"] for r in REPORTS]
assert len(_codes) == len(set(_codes))
_aud = {a for a, _n, _g in AUDIENCES}
assert all(set(r["audiences"]) <= _aud for r in REPORTS), [r["code"] for r in REPORTS if not set(r["audiences"]) <= _aud]
assert all(r["audiences"] for r in REPORTS), [r["code"] for r in REPORTS if not r["audiences"]]
