"""The TOGAF 10 content metamodel (owner, 8 Nov 2026, D303): a root metamodel made from the Root model, built in for
every installation and read-only like ArchiMate 4. Its entity types follow the TOGAF content metamodel and each sits
in its area of the content framework (D299). The TOGAF 10 project base points to it (phase 13.1).

House style: "Outcome" where TOGAF says objective. Descriptions are EA Explorer's own words.
"""

from __future__ import annotations

KEY = "togaf10-content-metamodel-1.0"
NAME = "TOGAF 10 content metamodel"

LAYERS = [("Motivation", "CCCCFF"), ("Strategy", "F5DEAA"), ("Business", "FFFFB5"), ("Data", "B5FFFF"), ("Application", "B5FFFF"),
          ("Technology", "C9E7B7"), ("Implementation and Migration", "FFE0E0"), ("Governance", "E0FFE0")]

# (code, name, layer, ID prefix, content framework area, description)
TYPES = [
    ("Stakeholder", "Stakeholder", "Motivation", "STK", "vision.stakeholders", "A person or group with an interest in the architecture"),
    ("Driver", "Driver", "Motivation", "DRV", "motivation.drivers", "Something inside or outside the enterprise that prompts change"),
    ("Goal", "Goal", "Motivation", "GOL", "motivation.goals", "A high-level statement of intent or direction"),
    ("Outcome", "Outcome", "Motivation", "OUT", "motivation.outcomes", "A time-bound, measurable result that moves a goal forward"),
    ("Measure", "Measure", "Motivation", "MEA", "motivation.measures", "An indicator used to tell whether an outcome is met"),
    ("Principle", "Principle", "Motivation", "PRI", "prelim.principles", "A general rule that guides how the enterprise works and changes"),
    ("Requirement", "Requirement", "Motivation", "REQ", "req.requirements", "A need the architecture must meet"),
    ("Constraint", "Constraint", "Motivation", "CON", "req.constraints", "A restriction on how the architecture may be built"),
    ("Assumption", "Assumption", "Motivation", "ASM", "req.assumptions", "Something taken as true without proof while planning"),
    ("Gap", "Gap", "Motivation", "GAP", "req.gaps", "A difference between the baseline and the target"),
    ("Capability", "Capability", "Strategy", "CAP", "business.capabilities", "An ability the enterprise has or needs"),
    ("ValueStream", "Value Stream", "Strategy", "VST", "business.value_streams", "The end-to-end stages that create value for a stakeholder"),
    ("CourseOfAction", "Course of Action", "Strategy", "COA", "business.courses_of_action", "A chosen approach to reach a goal"),
    # EA Explorer extensions for the business architecture artifacts (owner, 9 Nov 2026, D345)
    ("ValueStreamStage", "Value Stream Stage", "Strategy", "VSS", "business.value_streams",
     "EA Explorer extension: a stage of a value stream, in order, with its entry and exit criteria"),
    ("BusinessScenario", "Business Scenario", "Motivation", "BSC", "vision.architecture_vision",
     "EA Explorer extension: a business problem in its setting, the actors and the outcome wanted"),
    ("Actor", "Actor", "Business", "ACT", "business.roles_actors", "A person, organisation or system that takes part in the business"),
    ("Role", "Role", "Business", "ROL", "business.roles_actors", "A part an actor plays, with its responsibilities"),
    ("OrganisationUnit", "Organisation Unit", "Business", "ORG", "business.functions_org_units", "A unit of the organisation with its own goals and resources"),
    ("Function", "Function", "Business", "FUN", "business.functions_org_units", "A grouping of business behaviour by skill or resource"),
    ("BusinessService", "Business Service", "Business", "BSV", "business.services_contracts", "A service the business offers, with defined boundaries"),
    ("Contract", "Contract", "Business", "CTR", "business.services_contracts", "An agreement on a service between parties"),
    ("Product", "Product", "Business", "PRD", "business.services_contracts", "What is offered to customers: services and the terms of their use"),
    ("ProductLifecycleStage", "Product Lifecycle Stage", "Business", "PLS", "business.services_contracts",
     "EA Explorer extension: a stage in a product's life, in order, with its entry and exit criteria"),
    ("Process", "Process", "Business", "PRC", "business.processes_events", "A sequence of activities that produces a result"),
    ("Event", "Event", "Business", "EVT", "business.processes_events", "Something that happens and starts or changes behaviour"),
    ("Control", "Control", "Business", "CTL", "business.processes_events", "A check in a process that keeps it within rules"),
    ("Location", "Location", "Business", "LOC", "req.locations", "A place where business is done or technology is hosted"),
    ("DataEntity", "Data Entity", "Data", "DEN", "data.entities", "A thing the business holds information about"),
    ("LogicalDataComponent", "Logical Data Component", "Data", "LDC", "data.logical_components", "A logical grouping of data entities"),
    ("PhysicalDataComponent", "Physical Data Component", "Data", "PDC", "data.physical_components", "A physical store that holds data, such as a database"),
    ("ApplicationService", "Application Service", "Application", "ASV", "app.services", "A service an application offers to the business"),
    ("LogicalApplicationComponent", "Logical Application Component", "Application", "LAC", "app.logical_components",
     "A product-independent grouping of application functionality"),
    ("PhysicalApplicationComponent", "Physical Application Component", "Application", "PAC", "app.physical_components",
     "A deployed application, package or system"),
    ("TechnologyService", "Technology Service", "Technology", "TSV", "tech.services", "A platform service offered to applications"),
    ("LogicalTechnologyComponent", "Logical Technology Component", "Technology", "LTC", "tech.logical_components",
     "A product-independent grouping of technology, such as a class of platform"),
    ("PhysicalTechnologyComponent", "Physical Technology Component", "Technology", "PTC", "tech.physical_components",
     "A specific piece of technology: hardware, software or a cloud service"),
    ("WorkPackage", "Work Package", "Implementation and Migration", "WPK", "real.work_packages", "A set of actions that delivers a change"),
    ("ArchitectureContract", "Architecture Contract", "Implementation and Migration", "ACN", "real.contracts",
     "An agreement on what a delivery will build and how it is governed"),
    ("Standard", "Standard", "Governance", "STD", "gov.standards", "A norm the architecture and its solutions follow"),
    ("Guideline", "Guideline", "Governance", "GDL", "gov.guidelines", "Advice on how to apply the architecture"),
    ("Specification", "Specification", "Governance", "SPC", "gov.specifications", "A precise statement of what a solution must do or be"),
]

# (code, verb, category, directed)
RELS = [("Association", "associated with", "Dependency", False), ("Composition", "composed of", "Structural", True),
        ("Realization", "realizes", "Structural", True), ("Serving", "serves", "Dependency", True),
        ("Assignment", "assigned to", "Structural", True), ("Access", "accesses", "Dependency", True),
        ("Influence", "influences", "Dependency", True), ("Triggering", "triggers", "Dynamic", True)]

ALLOWED = [
    ("Stakeholder", "Association", "Driver"), ("Driver", "Influence", "Goal"), ("Outcome", "Realization", "Goal"),
    ("Measure", "Association", "Outcome"), ("Principle", "Influence", "Requirement"), ("Constraint", "Association", "Requirement"),
    ("Assumption", "Association", "Requirement"), ("Gap", "Association", "WorkPackage"), ("CourseOfAction", "Realization", "Goal"),
    ("Capability", "Composition", "Capability"), ("Capability", "Serving", "ValueStream"), ("CourseOfAction", "Association", "Capability"),
    ("Process", "Realization", "Capability"), ("Actor", "Assignment", "Role"), ("OrganisationUnit", "Composition", "OrganisationUnit"),
    ("OrganisationUnit", "Composition", "Actor"), ("Role", "Assignment", "Process"), ("Function", "Composition", "Function"),
    ("Function", "Composition", "Process"), ("Process", "Composition", "Process"), ("Process", "Realization", "BusinessService"),
    ("BusinessService", "Serving", "Actor"), ("Contract", "Association", "BusinessService"), ("Product", "Composition", "BusinessService"),
    ("Event", "Triggering", "Process"), ("Control", "Association", "Process"), ("Process", "Access", "DataEntity"),
    ("OrganisationUnit", "Association", "Location"), ("LogicalDataComponent", "Composition", "DataEntity"),
    ("PhysicalDataComponent", "Realization", "LogicalDataComponent"), ("ApplicationService", "Serving", "Process"),
    ("LogicalApplicationComponent", "Realization", "ApplicationService"), ("PhysicalApplicationComponent", "Realization", "LogicalApplicationComponent"),
    ("LogicalApplicationComponent", "Access", "DataEntity"), ("PhysicalApplicationComponent", "Access", "PhysicalDataComponent"),
    ("TechnologyService", "Serving", "PhysicalApplicationComponent"), ("LogicalTechnologyComponent", "Realization", "TechnologyService"),
    ("PhysicalTechnologyComponent", "Realization", "LogicalTechnologyComponent"), ("PhysicalTechnologyComponent", "Assignment", "PhysicalApplicationComponent"),
    ("PhysicalTechnologyComponent", "Association", "Location"), ("WorkPackage", "Realization", "Capability"),
    ("WorkPackage", "Realization", "Requirement"), ("ArchitectureContract", "Association", "WorkPackage"),
    ("Standard", "Association", "LogicalTechnologyComponent"), ("Standard", "Association", "PhysicalTechnologyComponent"),
    ("Standard", "Association", "LogicalApplicationComponent"), ("Standard", "Association", "DataEntity"),
    ("Guideline", "Association", "Process"), ("Specification", "Association", "PhysicalApplicationComponent"),
    ("Requirement", "Association", "Gap"),
    # D345
    ("ValueStream", "Composition", "ValueStreamStage"), ("ValueStreamStage", "Triggering", "ValueStreamStage"),
    ("Capability", "Serving", "ValueStreamStage"), ("Product", "Composition", "ProductLifecycleStage"),
    ("ProductLifecycleStage", "Triggering", "ProductLifecycleStage"), ("BusinessScenario", "Association", "Stakeholder"),
    ("BusinessScenario", "Association", "Actor"), ("BusinessScenario", "Association", "Driver"), ("BusinessScenario", "Association", "Goal"),
    ("BusinessScenario", "Association", "Requirement"), ("BusinessScenario", "Association", "Process"),
]


def sql(gid, insert, snake, empty_id: str) -> str:
    """The model and its metamodel, as seed SQL (the helpers come from build.py)."""
    k = KEY
    m = gid("model", k)
    return "".join([
        "SELECT set_config('eax.history_label', 'TOGAF 10 content metamodel', true);\n",
        insert("model", ["id", "name", "description", "kind_code", "source_model_id", "metamodel_name", "is_locked", "owner", "version_label"], [[
            m, NAME,
            "The TOGAF 10 content metamodel as a root metamodel: its entity types from motivation and strategy to technology "
            "and governance, each placed in the content framework, and the relationships the content metamodel allows. "
            "Read-only; the TOGAF 10 project base points to it, and models start from it.",
            "template", empty_id, NAME, True, "EA Explorer", "10"]]),
        insert("layer", ["id", "model_id", "code", "name", "colour", "sort_order"],
               [[gid(k, "layer", n), m, snake(n), n, c, i * 10] for i, (n, c) in enumerate(LAYERS, 1)]),
        insert("entity_type", ["id", "model_id", "layer_id", "code", "name", "description", "id_prefix", "table_name", "content_area", "sort_order"],
               [[gid(k, "entity_type", c), m, gid(k, "layer", lay), c, n, d, pre, snake(c), area, i * 10]
                for i, (c, n, lay, pre, area, d) in enumerate(TYPES, 1)]),
        insert("relationship_type", ["id", "model_id", "code", "name", "verb", "category", "is_directed", "sort_order"],
               [[gid(k, "relationship_type", c), m, c, c, v, cat, directed, i * 10] for i, (c, v, cat, directed) in enumerate(RELS, 1)]),
        insert("allowed_relationship", ["id", "model_id", "relationship_type_id", "source_type_id", "target_type_id"],
               [[gid(k, "allowed_relationship", s, r, t), m, gid(k, "relationship_type", r), gid(k, "entity_type", s), gid(k, "entity_type", t)]
                for s, r, t in ALLOWED]),
    ])
