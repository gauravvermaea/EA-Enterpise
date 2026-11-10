"""ArchiMate 4 starter metamodel and sample data, taken from the EA Repository Workbench 1.1 seed.

Used by eax.seed.build to fill the template model and the sample model. Element list follows the
42 ArchiMate 4 elements. Domains (not layers), their colours and the allowed relationships follow the owner's
ArchiMate 4 guide, *Modelling the Enterprise with ArchiMate 4* (owner, 9 Nov 2026, D392 to D394): the direct
relationships it describes, plus the derived ones it says are drawn directly (each marked "derived" in its note).
Composition is allowed exactly where aggregation is. Junctions wait for drawn views (phase 28).
"""

# ---------------------------------------------------------------- domains
# the ArchiMate 4 notation's colours, as in the guide's notation figures (D392): warm grey Common, yellow Business,
# blue Application, green Technology, orange Strategy, purple Motivation, pink Implementation and Migration
DOMAIN_COLOURS = {
    "Common": "E4DED2",
    "Business": "ECD678",
    "Application": "B0D0D9",
    "Technology": "BBD8AD",
    "Strategy": "EFBD5D",
    "Motivation": "D1BADC",
    "Implementation & Migration": "F1BBB7",
}
# the colours before 0.15.1, so an upgrade recolours only what nobody changed
OLD_DOMAIN_COLOURS = {"Common": "EEEEEE", "Business": "FFFFB5", "Application": "B5FFFF", "Technology": "C9E7B7",
                      "Strategy": "F5DEAA", "Motivation": "CCCCFF", "Implementation & Migration": "FFE0E0"}

# (TypeCode, Name, Domain, Aspect, IDPrefix)
ENTITY_TYPES = [
    ("Role", "Role", "Common", "Internal Active Structure", "ROL"),
    ("Collaboration", "Collaboration", "Common", "Internal Active Structure", "COL"),
    ("Path", "Path", "Common", "Active Structure", "PTH"),
    ("Service", "Service", "Common", "External Behaviour", "SRV"),
    ("Process", "Process", "Common", "Internal Behaviour", "PRC"),
    ("Function", "Function", "Common", "Internal Behaviour", "FUN"),
    ("Event", "Event", "Common", "Event", "EVT"),
    ("Grouping", "Grouping", "Common", "Composite", "GRP"),
    ("Location", "Location", "Common", "Composite", "LOC"),
    ("BusinessActor", "Business Actor", "Business", "Internal Active Structure", "BAC"),
    ("BusinessInterface", "Business Interface", "Business", "External Active Structure", "BIF"),
    ("BusinessObject", "Business Object", "Business", "Passive Structure", "BOB"),
    ("Product", "Product", "Business", "Composite", "PRD"),
    ("ApplicationComponent", "Application Component", "Application", "Internal Active Structure", "APP"),
    ("ApplicationInterface", "Application Interface", "Application", "External Active Structure", "AIF"),
    ("DataObject", "Data Object", "Application", "Passive Structure", "DOB"),
    ("Node", "Node", "Technology", "Internal Active Structure", "NOD"),
    ("Device", "Device", "Technology", "Internal Active Structure", "DEV"),
    ("SystemSoftware", "System Software", "Technology", "Internal Active Structure", "SSW"),
    ("TechnologyInterface", "Technology Interface", "Technology", "External Active Structure", "TIF"),
    ("CommunicationNetwork", "Communication Network", "Technology", "Active Structure", "CNW"),
    ("DistributionNetwork", "Distribution Network", "Technology", "Active Structure", "DNW"),
    ("Equipment", "Equipment", "Technology", "Internal Active Structure", "EQP"),
    ("Facility", "Facility", "Technology", "Internal Active Structure", "FAC"),
    ("Artifact", "Artifact", "Technology", "Passive Structure", "ART"),
    ("Material", "Material", "Technology", "Passive Structure", "MAT"),
    ("Resource", "Resource", "Strategy", "Structure", "RES"),
    ("Capability", "Capability", "Strategy", "Behaviour", "CAP"),
    ("ValueStream", "Value Stream", "Strategy", "Behaviour", "VST"),
    ("CourseOfAction", "Course of Action", "Strategy", "Behaviour", "COA"),
    ("Stakeholder", "Stakeholder", "Motivation", "Motivation", "STK"),
    ("Driver", "Driver", "Motivation", "Motivation", "DRV"),
    ("Assessment", "Assessment", "Motivation", "Motivation", "ASM"),
    ("Goal", "Goal", "Motivation", "Motivation", "GOL"),
    ("Outcome", "Outcome", "Motivation", "Motivation", "OUT"),
    ("Principle", "Principle", "Motivation", "Motivation", "PRI"),
    ("Requirement", "Requirement", "Motivation", "Motivation", "REQ"),
    ("Meaning", "Meaning", "Motivation", "Motivation", "MNG"),
    ("Value", "Value", "Motivation", "Motivation", "VAL"),
    ("WorkPackage", "Work Package", "Implementation & Migration", "Behaviour", "WPK"),
    ("Deliverable", "Deliverable", "Implementation & Migration", "Passive Structure", "DLV"),
    ("Plateau", "Plateau", "Implementation & Migration", "Composite", "PLT"),
]
assert len(ENTITY_TYPES) == 42
SPEC_TYPES = [t[0] for t in ENTITY_TYPES]   # the 42 elements of the ArchiMate 4 Specification

# EA Explorer extensions (owner, 9 Nov 2026, D345): the TOGAF business architecture artifacts ArchiMate has no element
# for. Marked as extensions (their description says so); an ArchiMate exchange leaves them out. (code, name, domain,
# aspect, ID prefix, what it is)
EXTENSIONS = [
    ("ValueStreamStage", "Value Stream Stage", "Strategy", "Behaviour", "VSS",
     "A stage of a value stream: its order, entry and exit criteria and the value it adds; part of a value stream, enabled by capabilities"),
    ("ProductLifecycleStage", "Product Lifecycle Stage", "Business", "Behaviour", "PLS",
     "A stage in a product's life, from launch to withdrawal, in order, with its entry and exit criteria"),
    ("BusinessScenario", "Business Scenario", "Motivation", "Motivation", "BSC",
     "A business problem in its setting: the problem, the environment, the actors and the outcome wanted"),
    ("Control", "Control", "Business", "Passive Structure", "CTL", "A check in a process that keeps it within its rules"),
    ("Contract", "Contract", "Business", "Passive Structure", "CTR", "An agreement on a service between parties: its terms and dates"),
    ("Measure", "Measure", "Motivation", "Motivation", "MEA", "An indicator, with its target, that tells whether an outcome is met"),
]
EXTENSION_NOTE = "EA Explorer extension (not an element of the ArchiMate 4 Specification): "
ENTITY_TYPES = ENTITY_TYPES + [t[:5] for t in EXTENSIONS]
EXTENSION_DESCRIPTIONS = {t[0]: EXTENSION_NOTE + t[5] for t in EXTENSIONS}

# Connectors (owner, 10 Nov 2026, D397, D402): the And and Or junction. Not an element: a repository object that joins
# relationships of one type; each source and target through it must be allowed as if they were related directly
# (eax.junctions). It is left out of catalogues and counts (core.entity_types.is_connector).
CONNECTORS = [("Junction", "Junction", "Common", "Connector", "JNC")]
CONNECTOR_TYPES = [t[0] for t in CONNECTORS]
EXTENSION_DESCRIPTIONS["Junction"] = ("A junction (And or Or) joining relationships of one type; each source and target "
                                      "through it must be allowed as if related directly")
ENTITY_TYPES = ENTITY_TYPES + CONNECTORS

# (RelCode, Name, Category, Directed, Description)
REL_TYPES = [
    ("Composition", "composed of", "Structural", "Y", "Whole consists of parts that cannot exist without it (specialization of Aggregation)"),
    ("Aggregation", "aggregates", "Structural", "Y", "Whole groups parts that may exist independently"),
    ("Assignment", "assigned to", "Structural", "Y", "Allocation of responsibility, performance of behaviour, or execution"),
    ("Realization", "realizes", "Structural", "Y", "Source plays a critical role in creating or achieving the target"),
    ("Serving", "serves", "Dependency", "Y", "Source provides its functionality to the target"),
    ("Access", "accesses", "Dependency", "Y", "Behaviour or active structure observes or acts on passive structure"),
    ("Influence", "influences", "Dependency", "Y", "Source affects the implementation or achievement of a motivation element"),
    ("Association", "associated with", "Dependency", "N", "Unspecified relationship"),
    ("Triggering", "triggers", "Dynamic", "Y", "Temporal or causal precedence"),
    ("Flow", "flows to", "Dynamic", "Y", "Transfer from one element to another"),
    ("Specialization", "specializes", "Other", "Y", "Target is a more general form of the source"),
]

# ---------------------------------------------------------------- type groups
G = {
    "INT_ACTIVE": ["Role", "Collaboration", "BusinessActor", "ApplicationComponent", "Node", "Device",
                   "SystemSoftware", "Equipment", "Facility"],
    "EXT_ACTIVE": ["BusinessInterface", "ApplicationInterface", "TechnologyInterface"],
    "NETWORK": ["Path", "CommunicationNetwork", "DistributionNetwork"],
    "BEHAVIOUR": ["Service", "Process", "Function", "Event"],
    "INT_BEHAVIOUR": ["Process", "Function"],
    "PASSIVE": ["BusinessObject", "DataObject", "Artifact", "Material"],
    "STRATEGY": ["Resource", "Capability", "ValueStream", "CourseOfAction"],
    "MOTIVATION": ["Stakeholder", "Driver", "Assessment", "Goal", "Outcome", "Principle", "Requirement",
                   "Meaning", "Value"],
    "IMPLEMENTATION": ["WorkPackage", "Deliverable", "Plateau"],
    "EXTENSIONS": [t[0] for t in EXTENSIONS],
    "TECH_NODE": ["Node", "Device", "SystemSoftware", "Equipment", "Facility"],
}
G["IT_ACTIVE"] = ["ApplicationComponent", "Node", "Device", "SystemSoftware", "Equipment", "Facility"]
G["PEOPLE"] = ["BusinessActor", "Role", "Collaboration"]
G["ACTIVE"] = G["INT_ACTIVE"] + G["EXT_ACTIVE"] + G["NETWORK"]
G["CORE"] = G["ACTIVE"] + G["BEHAVIOUR"] + G["PASSIVE"] + ["Product"]
G["DYNAMIC"] = ["Service", "Process", "Function", "Event"]

# ---------------------------------------------------------------- allowed relationships
# Tokens: TypeCode | '*' (any) | 'SAME' (target same type as source) | 'G:<group>'
R = []
def allow(src, rel, tgt, note=""):
    R.append((src, rel, tgt, note))

# structural: aggregation and composition (composition wherever aggregation is; mirrored at the end)
for rel in ("Aggregation", "Specialization"):
    allow("*", rel, "SAME", "Element to element of the same type")
allow("Process", "Aggregation", "Function", "Process and function aggregate each other, either way")
allow("Function", "Aggregation", "Process", "Process and function aggregate each other, either way")
allow("Grouping", "Aggregation", "*", "Grouping aggregates any concept")
allow("Location", "Aggregation", "*", "Location aggregates whatever is situated there")
allow("Plateau", "Aggregation", "G:CORE", "Plateau aggregates what is in force during that state")
allow("Plateau", "Aggregation", "G:STRATEGY", "Plateau aggregates what is in force during that state")
allow("Plateau", "Aggregation", "G:MOTIVATION", "Motivation elements attach to plateaus by aggregation")
allow("Product", "Aggregation", "Service", "Product: services, objects, artifacts and material offered as a whole")
allow("Product", "Aggregation", "G:PASSIVE", "Product: services, objects, artifacts and material offered as a whole")
allow("Product", "Aggregation", "G:INT_ACTIVE", "Product aggregates the active structure it offers")
allow("Product", "Aggregation", "G:EXT_ACTIVE", "Product aggregates the active structure it offers")
allow("Product", "Aggregation", "G:INT_BEHAVIOUR", "Product aggregates the behaviour it offers")
allow("Collaboration", "Aggregation", "G:INT_ACTIVE", "Collaboration aggregates internal active structure")
allow("BusinessActor", "Aggregation", "BusinessInterface", "A business interface is aggregated by its actor")
allow("ApplicationComponent", "Aggregation", "ApplicationInterface", "An application interface is aggregated by its component")
allow("G:TECH_NODE", "Aggregation", "TechnologyInterface", "Nodes, devices, system software, equipment and facilities offer interfaces")
allow("Node", "Aggregation", "G:TECH_NODE", "A node consists of devices, system software, equipment and facilities")
allow("G:NETWORK", "Aggregation", "G:NETWORK", "Networks aggregate paths and networks")
allow("CommunicationNetwork", "Aggregation", "G:TECH_NODE", "A network aggregates the infrastructure it is made of")
allow("DistributionNetwork", "Aggregation", "G:TECH_NODE", "A network aggregates the infrastructure it is made of")
allow("DistributionNetwork", "Aggregation", "BusinessActor", "A distribution network is partly made of people")
allow("BusinessObject", "Aggregation", "BusinessObject", "")

# assignment: who performs, hosts or answers for what
allow("G:INT_ACTIVE", "Assignment", "G:INT_BEHAVIOUR", "Active structure performs behaviour")
allow("G:INT_ACTIVE", "Assignment", "Event", "Active structure raises events")
allow("G:INT_ACTIVE", "Assignment", "Role", "An internal active structure element is assigned to a role")
allow("Role", "Assignment", "G:INT_BEHAVIOUR", "The role is assigned to the process or function")
allow("G:EXT_ACTIVE", "Assignment", "Service", "An interface is assigned to the services it exposes")
allow("BusinessActor", "Assignment", "BusinessObject", "An actor answers for a business object")
allow("ApplicationComponent", "Assignment", "DataObject", "A component is the golden source of a data object")
allow("BusinessActor", "Assignment", "Stakeholder", "A business actor holds a stakeholder's perspective")
allow("Facility", "Assignment", "BusinessActor", "People work in buildings (crosses Technology to Business)")
allow("Facility", "Assignment", "Equipment", "Equipment is installed and used in a facility")
allow("Facility", "Assignment", "Material", "Material is stored in a facility")
for s_ in ("Node", "Device", "SystemSoftware"):
    allow(s_, "Assignment", "Artifact", "Deployment: the artifact runs on it")
allow("Resource", "Assignment", "Capability", "Resources are assigned to the capabilities that draw on them")
allow("Resource", "Assignment", "ValueStream", "Resources are assigned to the value streams that draw on them")
allow("G:INT_ACTIVE", "Assignment", "WorkPackage", "A role (or actor) answers for a work package")

# realization: the concrete makes the abstract real
allow("G:INT_BEHAVIOUR", "Realization", "Service", "A service is the external face of internal behaviour")
allow("CommunicationNetwork", "Realization", "Path", "A network realizes the path")
allow("DistributionNetwork", "Realization", "Path", "A network realizes the path")
allow("DataObject", "Realization", "BusinessObject", "Data object realizes business object (crosses domains)")
allow("Material", "Realization", "BusinessObject", "Material realizes business object (crosses domains)")
for t_ in ("ApplicationComponent", "DataObject", "SystemSoftware", "Device"):
    allow("Artifact", "Realization", t_, "Implementation: the artifact makes it real")
allow("G:BEHAVIOUR", "Realization", "Capability", "Only behaviour realizes a capability")
allow("Grouping", "Realization", "Capability", "Core elements together, grouped, realize a capability")
allow("G:BEHAVIOUR", "Realization", "ValueStream", "Behaviour realizes value streams")
allow("G:ACTIVE", "Realization", "Resource", "Structure realizes a resource")
allow("G:PASSIVE", "Realization", "Resource", "Structure realizes a resource")
allow("Capability", "Realization", "CourseOfAction", "Capabilities realize a course of action")
allow("Resource", "Realization", "CourseOfAction", "")
allow("Capability", "Realization", "Outcome", "A capability realizes an outcome, never a goal directly")
allow("ValueStream", "Realization", "Outcome", "A stage realizes an outcome")
allow("CourseOfAction", "Realization", "Outcome", "A course of action realizes an outcome, and so reaches a goal")
allow("G:CORE", "Realization", "Requirement", "A structure or behaviour element realizes a requirement")
allow("G:STRATEGY", "Realization", "Requirement", "Strategy elements realize a requirement")
for t_ in ("Principle", "Outcome", "Goal"):
    allow("G:CORE", "Realization", t_, "derived: through the requirement it realizes")
allow("Requirement", "Realization", "Principle", "The requirement realizes the principle")
allow("Principle", "Realization", "Outcome", "")
allow("Outcome", "Realization", "Goal", "What you get realizes what you want")
allow("Requirement", "Realization", "Outcome", "derived")
allow("Requirement", "Realization", "Goal", "derived")
allow("Principle", "Realization", "Goal", "derived")
allow("WorkPackage", "Realization", "Deliverable", "Work package produces deliverable")
allow("Deliverable", "Realization", "G:CORE", "A deliverable may realize any core element")
allow("Deliverable", "Realization", "G:STRATEGY", "A deliverable may realize any strategy element")
allow("Deliverable", "Realization", "Plateau", "Plateaus are realized by deliverables")
allow("Deliverable", "Realization", "Requirement", "Permitted shortcut for the indirect chain")

# serving: the provider is used by the consumer
allow("Service", "Serving", "G:BEHAVIOUR", "Service serves behaviour")
allow("Service", "Serving", "G:INT_ACTIVE", "Service serves active structure")
allow("Service", "Serving", "Capability", "")
allow("Service", "Serving", "ValueStream", "")
allow("G:EXT_ACTIVE", "Serving", "G:INT_ACTIVE", "derived: an interface serves the actor or role that uses it")
allow("G:INT_BEHAVIOUR", "Serving", "G:BEHAVIOUR", "Behaviour serves behaviour")
# derived: walking a service's serving back along realization and assignment, software and technology serve what uses
# them; people serve people. Never a person or role straight to software (the guide calls that out as wrong).
allow("G:IT_ACTIVE", "Serving", "G:INT_ACTIVE", "derived: through the service it realizes")
allow("G:PEOPLE", "Serving", "G:PEOPLE", "derived: through the service it realizes")
allow("Capability", "Serving", "Capability", "Capabilities serve one another")
allow("Capability", "Serving", "ValueStream", "The capability serves the stream, never the reverse")

# access: behaviour reads, writes or creates passive structure
allow("G:BEHAVIOUR", "Access", "G:PASSIVE", "Behaviour accesses passive structure")
allow("G:INT_ACTIVE", "Access", "G:PASSIVE", "derived: through the behaviour it performs")
allow("G:EXT_ACTIVE", "Access", "G:PASSIVE", "derived: through the service it exposes")
allow("WorkPackage", "Access", "Deliverable", "")

# influence always ends at a motivation element
allow("G:MOTIVATION", "Influence", "G:MOTIVATION", "Motivation influences motivation")
allow("G:CORE", "Influence", "G:MOTIVATION", "Weaker than realization: helps or hinders")
allow("G:STRATEGY", "Influence", "G:MOTIVATION", "Weaker than realization: helps or hinders")
allow("G:IMPLEMENTATION", "Influence", "G:MOTIVATION", "Weaker than realization: helps or hinders")

# dynamic: between behaviour (all Common)
allow("G:DYNAMIC", "Triggering", "G:DYNAMIC", "Behaviour triggers behaviour")
allow("WorkPackage", "Triggering", "WorkPackage", "")
allow("WorkPackage", "Triggering", "Event", "")
allow("Event", "Triggering", "WorkPackage", "")
allow("Plateau", "Triggering", "Plateau", "Plateaus are sequenced by triggering")
allow("G:DYNAMIC", "Flow", "G:DYNAMIC", "Behaviour flows to behaviour")
allow("ValueStream", "Flow", "ValueStream", "Stages are joined by flow")
allow("Capability", "Flow", "Capability", "")
allow("G:INT_ACTIVE", "Flow", "G:INT_ACTIVE", "derived: shorthand that hides which behaviours were involved")

# the EA Explorer extensions (D345): stages make up a value stream or a product's life and follow one another;
# capabilities serve stages; a scenario, control, contract or measure links to anything by association
allow("ValueStream", "Aggregation", "ValueStreamStage", "EA Explorer extension")
allow("ValueStreamStage", "Triggering", "ValueStreamStage", "EA Explorer extension")
allow("ValueStreamStage", "Flow", "ValueStreamStage", "EA Explorer extension")
allow("Capability", "Serving", "ValueStreamStage", "EA Explorer extension")
allow("Resource", "Assignment", "ValueStreamStage", "EA Explorer extension")
allow("ValueStreamStage", "Realization", "Outcome", "EA Explorer extension")
allow("ValueStreamStage", "Realization", "Value", "EA Explorer extension")
allow("Product", "Aggregation", "ProductLifecycleStage", "EA Explorer extension")
allow("ProductLifecycleStage", "Triggering", "ProductLifecycleStage", "EA Explorer extension")
allow("Control", "Influence", "Process", "EA Explorer extension")
allow("Contract", "Realization", "Service", "EA Explorer extension")
allow("Measure", "Influence", "Outcome", "EA Explorer extension")
allow("BusinessScenario", "Influence", "G:MOTIVATION", "EA Explorer extension")

# a junction joins relationships of any one type (D397): the metamodel lets every type reach it and leave it; the rule
# that each source and target through it is allowed as if direct is checked in Python (eax.junctions)
for _rel in [r[0] for r in REL_TYPES]:
    if _rel not in ("Aggregation", "Composition", "Specialization"):
        allow("*", _rel, "Junction", "Through a junction (checked as if direct)")
        allow("Junction", _rel, "*", "Through a junction (checked as if direct)")
allow("*", "Aggregation", "Junction", "Through a junction (checked as if direct)")    # composition follows below
allow("Junction", "Aggregation", "*", "Through a junction (checked as if direct)")

# composition is allowed exactly where aggregation is
R += [(s_, "Composition", t_, n_) for (s_, r_, t_, n_) in list(R) if r_ == "Aggregation"]
allow("*", "Association", "*", "Association is always allowed")

# ---------------------------------------------------------------- lists
LISTS = {
    "Status": ["Active", "Retired"],
    "Lifecycle": ["Plan", "Phase In", "Production", "Phase Out", "Retiring", "Retired"],
    "LandscapeLevel": ["Strategic", "Segment", "Capability"],
    "ArchitectureState": ["Baseline", "Transition", "Target"],
    "Hosting": ["On-premises", "SaaS", "IaaS", "PaaS", "Hybrid"],
    "TimeClassification": ["Tolerate", "Invest", "Migrate", "Eliminate"],
    "DataClassification": ["Public", "Internal", "Confidential", "Restricted"],
    "Priority": ["Must", "Should", "Could", "Won't"],
    "Maturity": ["1 - Initial", "2 - Managed", "3 - Defined", "4 - Measured", "5 - Optimised"],
    "Importance": ["High", "Medium", "Low"],
    "Investment": ["Invest", "Sustain", "Reduce"],
    "DomainList": ["Business", "Application", "Technology"],
    "YesNo": ["Y", "N"],
    "DataType": ["Text", "LongText", "Integer", "Decimal", "Currency", "Percent", "Date", "Boolean",
                 "List", "URL", "Email", "EntityRef"],
    "RuleType": ["Mandatory", "List", "MinValue", "MaxValue", "Range", "MinLength", "MaxLength", "Regex",
                 "DateRange", "DateOrder", "Unique", "EntityRef", "RequiredIf"],
    "Severity": ["Error", "Warning"],
    "RelCategory": ["Structural", "Dependency", "Dynamic", "Other"],
    "Domain": list(DOMAIN_COLOURS.keys()),
    "JunctionKind": ["And", "Or"],
}

# ---------------------------------------------------------------- attributes
# System attributes (columns on every entity, not mapped per type)
SYSTEM_ATTRS = [
    # code, name, datatype, list
    ("EntityID", "Entity ID", "Text", ""),
    ("TypeCode", "Type", "List", ""),
    ("DisplayID", "Display ID", "Text", ""),
    ("Name", "Name", "Text", ""),
    ("Description", "Description", "LongText", ""),
    ("Status", "Status", "List", "Status"),
    ("Created", "Created", "Text", ""),
    ("CreatedBy", "Created By", "Text", ""),
    ("Modified", "Modified", "Text", ""),
    ("ModifiedBy", "Modified By", "Text", ""),
    ("RowHash", "Row Hash", "Text", ""),
]
SYSTEM_EDITABLE = {"Name", "Description", "Status"}   # the Repository Area is on the entity type now (D318)

# Business attributes: code, name, datatype, list, unit, description
ATTRS = [
    ("Owner", "Owner", "Text", "", "", "Accountable person or team"),
    ("Lifecycle", "Lifecycle", "List", "Lifecycle", "", "Lifecycle stage"),
    ("LandscapeLevel", "Landscape Level", "List", "LandscapeLevel", "", "TOGAF landscape level"),
    ("ArchitectureState", "Architecture State", "List", "ArchitectureState", "", "Baseline, transition or target"),
    ("Domain", "Domain", "List", "DomainList", "", "Domain of a Common Domain element"),
    ("Criticality", "Criticality", "Integer", "", "", "Business criticality, 1 low to 5 high"),
    ("Vendor", "Vendor", "Text", "", "", "Supplier or vendor"),
    ("Version", "Version", "Text", "", "", "Version number, e.g. 4.2.1"),
    ("Hosting", "Hosting", "List", "Hosting", "", "Hosting model"),
    ("GoLiveDate", "Go-live Date", "Date", "", "", "Date put into production"),
    ("RetirementDate", "Retirement Date", "Date", "", "", "Planned or actual retirement"),
    ("AnnualCost", "Annual Cost", "Currency", "", "USD", "Annual run cost"),
    ("TimeClassification", "TIME", "List", "TimeClassification", "", "Portfolio decision: Tolerate, Invest, Migrate or Eliminate"),
    ("FunctionalFit", "Functional Fit", "Integer", "", "", "How well it meets business needs, 1 poor to 5 excellent"),
    ("TechnicalFit", "Technical Fit", "Integer", "", "", "Technical health, 1 poor to 5 excellent"),
    ("DataClassification", "Data Classification", "List", "DataClassification", "", "Information classification"),
    ("ProcessLevel", "Process Level", "Integer", "", "", "Process hierarchy level, 0 to 5"),
    ("Maturity", "Maturity", "List", "Maturity", "", "Capability maturity"),
    ("CapabilityLevel", "Capability Level", "Integer", "", "", "Capability map level, 1 to 4"),
    ("Priority", "Priority", "List", "Priority", "", "MoSCoW priority"),
    ("StartDate", "Start Date", "Date", "", "", "Start date"),
    ("EndDate", "End Date", "Date", "", "", "End date"),
    ("Measure", "Measure", "Text", "", "", "How achievement is measured"),
    ("Url", "Documents", "URL", "", "", "Links to more detailed documents: one or more, each with a note (D418)"),
    # the business architecture artifacts (D345)
    ("Importance", "Importance", "List", "Importance", "", "How much the capability matters to the strategy"),
    ("Investment", "Investment", "List", "Investment", "", "Where the capability's investment goes: invest, sustain or reduce"),
    ("StageOrder", "Stage Order", "Integer", "", "", "The stage's place in its value stream or lifecycle: 1, 2, 3..."),
    ("EntryCriteria", "Entry Criteria", "LongText", "", "", "What must be true to start the stage"),
    ("ExitCriteria", "Exit Criteria", "LongText", "", "", "What must be true to finish the stage"),
    ("ValueItem", "Value Item", "Text", "", "", "The value the stage adds for the stakeholder"),
    ("Problem", "Problem", "LongText", "", "", "The business problem the scenario describes"),
    ("Environment", "Environment", "LongText", "", "", "The setting: the business and technical environment"),
    ("DesiredOutcome", "Desired Outcome", "LongText", "", "", "What the scenario should achieve"),
    ("Target", "Target", "Text", "", "", "The value the measure should reach, and by when"),
    ("JunctionKind", "Junction Kind", "List", "JunctionKind", "", "And: all of them; Or: one or more of them (D397)"),
]

ALL_TYPES = [t[0] for t in ENTITY_TYPES]
MAP = {}  # TypeCode -> list of (AttrCode, Mandatory, Section)
for t in ALL_TYPES:
    MAP[t] = [("Owner", "N", "General"), ("LandscapeLevel", "N", "Landscape"),
              ("ArchitectureState", "N", "Landscape")]
for t in G["CORE"] + G["STRATEGY"] + ["Product"]:
    MAP[t].append(("Lifecycle", "N", "General"))
for t in ["Role", "Collaboration", "Path", "Service", "Process", "Function", "Event"]:
    MAP[t].append(("Domain", "N", "General"))
for t in ["ApplicationComponent", "Node", "Device", "SystemSoftware", "Service", "Equipment", "Facility"]:
    MAP[t] += [("Criticality", "N", "Assessment"), ("Vendor", "N", "Sourcing"), ("Version", "N", "Sourcing")]
for t in ["ApplicationComponent", "Node", "SystemSoftware"]:
    MAP[t] += [("Hosting", "N", "Sourcing"), ("GoLiveDate", "N", "Lifecycle"),
               ("RetirementDate", "N", "Lifecycle"), ("AnnualCost", "N", "Financial")]
MAP["ApplicationComponent"] += [("TimeClassification", "N", "Assessment"), ("FunctionalFit", "N", "Assessment"),
                                ("TechnicalFit", "N", "Assessment")]
MAP["ApplicationComponent"] = [(a, "Y" if a in ("Owner", "Lifecycle") else m, s)
                               for a, m, s in MAP["ApplicationComponent"]]
for t in G["PASSIVE"]:
    MAP[t].append(("DataClassification", "N", "Information"))
MAP["Process"].append(("ProcessLevel", "N", "Structure"))
MAP["Capability"] += [("CapabilityLevel", "N", "Structure"), ("Maturity", "N", "Assessment"),
                      ("Criticality", "N", "Assessment")]
for t in ["Requirement", "Goal", "WorkPackage", "Principle"]:
    MAP[t].append(("Priority", "N", "General"))
for t in ["WorkPackage", "Plateau", "Deliverable"]:
    MAP[t] += [("StartDate", "N", "Schedule"), ("EndDate", "N", "Schedule")]
for t in ["Goal", "Outcome"]:
    MAP[t].append(("Measure", "N", "General"))
for t in ["ApplicationComponent", "SystemSoftware", "Product", "Service", "Requirement", "Principle",
          "Deliverable", "WorkPackage"]:
    MAP[t].append(("Url", "N", "Links"))   # a Link (D418): one or more, each with a note
# the business architecture artifacts (D345)
MAP["Capability"] += [("Importance", "N", "Assessment"), ("Investment", "N", "Assessment")]
for t in ["ValueStreamStage", "ProductLifecycleStage"]:
    MAP[t] += [("StageOrder", "N", "Stage"), ("EntryCriteria", "N", "Stage"), ("ExitCriteria", "N", "Stage")]
MAP["ValueStreamStage"].append(("ValueItem", "N", "Stage"))
MAP["BusinessScenario"] += [("Problem", "N", "Scenario"), ("Environment", "N", "Scenario"), ("DesiredOutcome", "N", "Scenario")]
MAP["Control"] += [("Priority", "N", "General"), ("Url", "N", "Links")]
MAP["Contract"] += [("Vendor", "N", "Sourcing"), ("StartDate", "N", "Schedule"), ("EndDate", "N", "Schedule"),
                    ("AnnualCost", "N", "Financial"), ("Url", "N", "Links")]
MAP["Measure"] += [("Measure", "N", "General"), ("Target", "N", "General")]
MAP["Junction"] = [("JunctionKind", "Y", "General")]     # a connector carries nothing else (D397)

# ---------------------------------------------------------------- rules
# AttrCode, TypeCode('' = all), RuleType, Param1, Param2, Severity, Message
RULES = [
    ("Name", "", "Mandatory", "", "", "Error", "Name is required"),
    ("Name", "", "MaxLength", "120", "", "Error", "Name must be 120 characters or fewer"),
    ("Name", "", "Unique", "Type", "", "Warning", "Another entity of this type has the same name"),
    ("Status", "", "List", "Status", "", "Error", "Status must be Active or Retired"),
    ("Criticality", "", "Range", "1", "5", "Error", "Criticality must be a whole number from 1 to 5"),
    ("Version", "", "Regex", r"^\d+(\.\d+){0,3}$", "", "Warning", "Version should look like 4.2 or 4.2.1"),
    ("RetirementDate", "", "DateOrder", "GoLiveDate", "", "Error", "Retirement date must be after the go-live date"),
    ("RetirementDate", "", "RequiredIf", "Lifecycle", "Retiring", "Warning", "Set a retirement date for a retiring element"),
    ("EndDate", "", "DateOrder", "StartDate", "", "Error", "End date must be after the start date"),
    ("AnnualCost", "", "MinValue", "0", "", "Error", "Annual cost cannot be negative"),
    ("FunctionalFit", "", "Range", "1", "5", "Error", "Functional fit must be a whole number from 1 to 5"),
    ("TechnicalFit", "", "Range", "1", "5", "Error", "Technical fit must be a whole number from 1 to 5"),
    ("ProcessLevel", "", "Range", "0", "5", "Error", "Process level must be from 0 to 5"),
    ("CapabilityLevel", "", "Range", "1", "4", "Error", "Capability level must be from 1 to 4"),
    ("GoLiveDate", "", "DateRange", "1990-01-01", "2100-12-31", "Warning", "Go-live date looks out of range"),
]

# ---------------------------------------------------------------- sample data (insurance flavour)
SAMPLE_ENTITIES = [
    # TypeCode, Name, Description, {attrs}
    ("ApplicationComponent", "Policy Administration System", "Core policy lifecycle system",
     {"Owner": "Head of Policy IT", "Lifecycle": "Production", "Criticality": 5, "Vendor": "Sapiens",
      "Version": "10.2", "Hosting": "IaaS", "GoLiveDate": "2017-03-01", "AnnualCost": 4200000,
      "ArchitectureState": "Baseline", "TimeClassification": "Migrate", "FunctionalFit": 3, "TechnicalFit": 2}),
    ("ApplicationComponent", "Claims Platform", "Claims registration and settlement",
     {"Owner": "Head of Claims IT", "Lifecycle": "Production", "Criticality": 5, "Vendor": "Guidewire",
      "Version": "9.0", "Hosting": "SaaS", "GoLiveDate": "2020-07-15", "AnnualCost": 3100000,
      "ArchitectureState": "Baseline", "TimeClassification": "Invest", "FunctionalFit": 4, "TechnicalFit": 4}),
    ("ApplicationComponent", "Customer Portal", "Self-service web portal",
     {"Owner": "Digital Channels", "Lifecycle": "Phase In", "Criticality": 4, "Hosting": "PaaS",
      "ArchitectureState": "Target", "TimeClassification": "Invest", "FunctionalFit": 4, "TechnicalFit": 5}),
    ("DataObject", "Policy Record", "Policy master data",
     {"Owner": "Data Office", "DataClassification": "Confidential"}),
    ("DataObject", "Claim Record", "Claim case data",
     {"Owner": "Data Office", "DataClassification": "Confidential"}),
    ("Capability", "Claims Management", "Ability to register, assess and settle claims",
     {"Owner": "COO", "CapabilityLevel": 1, "Maturity": "3 - Defined", "Criticality": 5}),
    ("Capability", "Policy Management", "Ability to issue and service policies",
     {"Owner": "COO", "CapabilityLevel": 1, "Maturity": "2 - Managed", "Criticality": 5}),
    ("Process", "Register Claim", "First notification of loss",
     {"Owner": "Claims Operations", "ProcessLevel": 2, "Domain": "Business", "Lifecycle": "Production"}),
    ("Service", "Claims Service", "Claims handling exposed to customers and brokers",
     {"Owner": "Claims Operations", "Domain": "Business", "Lifecycle": "Production"}),
    ("BusinessActor", "Claims Department", "Claims operations team", {"Owner": "COO"}),
    ("Node", "Production Database Cluster", "Shared Oracle cluster",
     {"Owner": "Infrastructure", "Lifecycle": "Production", "Criticality": 5, "Vendor": "Oracle",
      "Version": "19.3", "Hosting": "On-premises", "RetirementDate": "2027-04-30"}),
    ("Goal", "Settle claims faster", "Reduce average settlement time",
     {"Owner": "COO", "Priority": "Must", "Measure": "Average settlement under 10 days"}),
    ("Requirement", "Digital first notification of loss", "Customers can log claims online",
     {"Owner": "Digital Channels", "Priority": "Must"}),
    ("WorkPackage", "Claims Digitisation Programme", "Programme delivering online claims",
     {"Owner": "Programme Office", "Priority": "Must", "StartDate": "2026-01-15", "EndDate": "2027-06-30"}),
]
SAMPLE_RELS = [
    # source name, RelCode, target name
    ("Claims Platform", "Assignment", "Register Claim"),
    ("Register Claim", "Realization", "Claims Management"),
    ("Claims Platform", "Access", "Claim Record"),
    ("Policy Administration System", "Access", "Policy Record"),
    ("Claims Department", "Assignment", "Register Claim"),
    ("Register Claim", "Realization", "Claims Service"),
    ("Claims Platform", "Serving", "Claims Department"),
    ("Production Database Cluster", "Serving", "Policy Administration System"),
    ("Customer Portal", "Serving", "Claims Platform"),
    ("Claims Platform", "Realization", "Digital first notification of loss"),
    ("Digital first notification of loss", "Realization", "Settle claims faster"),
    ("Claims Digitisation Programme", "Association", "Customer Portal"),
]
