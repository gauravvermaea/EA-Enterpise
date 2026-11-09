"""ArchiMate 4 starter metamodel and sample data, taken from the EA Repository Workbench 1.1 seed.

Used by eax.seed.build to fill the template model and the sample model. Element list follows the
42 ArchiMate 4 elements (Linked.Archi ArchiMate 4.0 taxonomy). Allowed
relationships are DERIVED from the generic metamodel and marked
Origin='ArchiMate4-derived (verify)' until checked against the spec's
relationship tables.
"""

# ---------------------------------------------------------------- domains
DOMAIN_COLOURS = {
    "Common": "EEEEEE",
    "Business": "FFFFB5",
    "Application": "B5FFFF",
    "Technology": "C9E7B7",
    "Strategy": "F5DEAA",
    "Motivation": "CCCCFF",
    "Implementation & Migration": "FFE0E0",
}

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
G["ACTIVE"] = G["INT_ACTIVE"] + G["EXT_ACTIVE"] + G["NETWORK"]
G["CORE"] = G["ACTIVE"] + G["BEHAVIOUR"] + G["PASSIVE"] + ["Product"]
G["DYNAMIC"] = ["Service", "Process", "Function", "Event"]

# ---------------------------------------------------------------- allowed relationships
# Tokens: TypeCode | '*' (any) | 'SAME' (target same type as source) | 'G:<group>'
R = []
def allow(src, rel, tgt, note=""):
    R.append((src, rel, tgt, note))

for rel in ("Composition", "Aggregation", "Specialization"):
    allow("*", rel, "SAME", "Element to element of the same type")
allow("Grouping", "Aggregation", "*", "Grouping aggregates any concept")
allow("Grouping", "Composition", "*", "Grouping composes any concept")
allow("Location", "Aggregation", "*", "Location aggregates anything located there")
allow("Plateau", "Aggregation", "G:CORE", "Plateau aggregates core elements")
allow("Plateau", "Aggregation", "G:STRATEGY", "Plateau aggregates strategy elements")
for tgt in ("G:BEHAVIOUR", "G:PASSIVE", "G:INT_ACTIVE", "G:EXT_ACTIVE"):
    allow("Product", "Aggregation", tgt, "Product aggregates services, passive and active structure")
    allow("Product", "Composition", tgt, "Product composes services, passive and active structure")
allow("Collaboration", "Aggregation", "G:INT_ACTIVE", "Collaboration aggregates internal active structure")
allow("BusinessActor", "Composition", "BusinessInterface", "Actor exposes interface")
allow("ApplicationComponent", "Composition", "ApplicationInterface", "Component exposes interface")
allow("G:TECH_NODE", "Composition", "TechnologyInterface", "Node exposes interface")
allow("Node", "Composition", "G:TECH_NODE", "Node composed of devices, system software, equipment, facilities")
allow("Node", "Aggregation", "G:TECH_NODE", "Node aggregates technology elements")
allow("G:NETWORK", "Aggregation", "G:NETWORK", "Networks aggregate paths and networks")

allow("G:INT_ACTIVE", "Assignment", "G:INT_BEHAVIOUR", "Active structure performs behaviour")
allow("G:INT_ACTIVE", "Assignment", "Event", "Active structure raises events")
allow("G:EXT_ACTIVE", "Assignment", "Service", "Interface exposes service")
allow("BusinessActor", "Assignment", "Role", "Actor fulfils role")
allow("Collaboration", "Assignment", "Role", "Collaboration fulfils role")
allow("G:INT_ACTIVE", "Assignment", "Role", "Active structure fulfils role (ArchiMate 4 generic Role)")
allow("G:TECH_NODE", "Assignment", "Artifact", "Artifact deployed on technology")
allow("Resource", "Assignment", "Capability", "Resource assigned to capability")
allow("G:INT_ACTIVE", "Assignment", "WorkPackage", "Active structure assigned to work package")

allow("G:INT_BEHAVIOUR", "Realization", "Service", "Behaviour realizes service")
allow("G:ACTIVE", "Realization", "Path", "Active structure realizes path (ArchiMate 4)")
allow("Artifact", "Realization", "ApplicationComponent", "Artifact realizes component")
allow("Artifact", "Realization", "DataObject", "Artifact realizes data object")
allow("Artifact", "Realization", "SystemSoftware", "Artifact realizes system software")
allow("DataObject", "Realization", "BusinessObject", "Data object realizes business object")
allow("G:CORE", "Realization", "Capability", "Core elements realize capability")
allow("G:CORE", "Realization", "Resource", "Core elements realize resource")
allow("G:BEHAVIOUR", "Realization", "ValueStream", "Behaviour realizes value stream")
allow("Capability", "Realization", "CourseOfAction", "Capability realizes course of action")
allow("Resource", "Realization", "CourseOfAction", "Resource realizes course of action")
allow("CourseOfAction", "Realization", "Outcome", "Course of action realizes outcome")
allow("CourseOfAction", "Realization", "Goal", "Course of action realizes goal")
for tgt in ("Requirement", "Principle", "Goal", "Outcome"):
    allow("G:CORE", "Realization", tgt, "Core elements realize motivation")
    allow("G:STRATEGY", "Realization", tgt, "Strategy elements realize motivation")
allow("Requirement", "Realization", "Goal", "")
allow("Requirement", "Realization", "Outcome", "")
allow("Requirement", "Realization", "Principle", "")
allow("Principle", "Realization", "Goal", "")
allow("Principle", "Realization", "Outcome", "")
allow("Outcome", "Realization", "Goal", "")
allow("WorkPackage", "Realization", "Deliverable", "Work package produces deliverable")
allow("Deliverable", "Realization", "G:CORE", "Deliverable realizes core element")
allow("Deliverable", "Realization", "G:STRATEGY", "Deliverable realizes strategy element")
allow("Deliverable", "Realization", "Plateau", "Deliverable realizes plateau")

allow("Service", "Serving", "G:BEHAVIOUR", "Service serves behaviour")
allow("Service", "Serving", "G:ACTIVE", "Service serves active structure")
allow("Service", "Serving", "Capability", "")
allow("Service", "Serving", "ValueStream", "")
allow("G:EXT_ACTIVE", "Serving", "G:INT_ACTIVE", "Interface serves active structure")
allow("G:INT_ACTIVE", "Serving", "G:INT_ACTIVE", "Active structure serves active structure")
allow("G:INT_BEHAVIOUR", "Serving", "G:BEHAVIOUR", "Behaviour serves behaviour")
allow("Capability", "Serving", "Capability", "")
allow("Capability", "Serving", "ValueStream", "")
allow("ValueStream", "Serving", "ValueStream", "")

allow("G:BEHAVIOUR", "Access", "G:PASSIVE", "Behaviour accesses passive structure")
allow("G:INT_ACTIVE", "Access", "G:PASSIVE", "Active structure accesses passive structure (derived)")
allow("G:EXT_ACTIVE", "Access", "G:PASSIVE", "Interface accesses passive structure (derived)")
allow("WorkPackage", "Access", "Deliverable", "")

allow("G:MOTIVATION", "Influence", "G:MOTIVATION", "Motivation influences motivation")
allow("G:CORE", "Influence", "G:MOTIVATION", "Core influences motivation")
allow("G:STRATEGY", "Influence", "G:MOTIVATION", "Strategy influences motivation")
allow("G:IMPLEMENTATION", "Influence", "G:MOTIVATION", "Implementation influences motivation")

allow("G:DYNAMIC", "Triggering", "G:DYNAMIC", "Behaviour triggers behaviour")
allow("ValueStream", "Triggering", "ValueStream", "")
allow("WorkPackage", "Triggering", "WorkPackage", "")
allow("WorkPackage", "Triggering", "Event", "")
allow("Event", "Triggering", "WorkPackage", "")
allow("Plateau", "Triggering", "Plateau", "Transition between plateaus")
allow("G:DYNAMIC", "Flow", "G:DYNAMIC", "Behaviour flows to behaviour")
allow("ValueStream", "Flow", "ValueStream", "")
allow("Capability", "Flow", "Capability", "")
allow("G:INT_ACTIVE", "Flow", "G:INT_ACTIVE", "Active structure flow (derived)")

# the EA Explorer extensions (D345): stages make up a value stream or a product's life and follow one another;
# capabilities serve stages; a scenario, control, contract or measure links to anything by association
allow("ValueStream", "Composition", "ValueStreamStage", "EA Explorer extension")
allow("ValueStreamStage", "Triggering", "ValueStreamStage", "EA Explorer extension")
allow("ValueStreamStage", "Flow", "ValueStreamStage", "EA Explorer extension")
allow("Capability", "Serving", "ValueStreamStage", "EA Explorer extension")
allow("ValueStreamStage", "Realization", "Value", "EA Explorer extension")
allow("Product", "Composition", "ProductLifecycleStage", "EA Explorer extension")
allow("ProductLifecycleStage", "Triggering", "ProductLifecycleStage", "EA Explorer extension")
allow("Control", "Influence", "Process", "EA Explorer extension")
allow("Contract", "Realization", "Service", "EA Explorer extension")
allow("Measure", "Influence", "Outcome", "EA Explorer extension")
allow("BusinessScenario", "Influence", "G:MOTIVATION", "EA Explorer extension")
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
    ("Url", "URL", "URL", "", "", "Link to documentation"),
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
          "Deliverable"]:
    MAP[t].append(("Url", "N", "Links"))
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
    ("Url", "", "Regex", r"^https?://\S+$", "", "Warning", "URL should start with http:// or https://"),
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
    ("Claims Platform", "Realization", "Claims Management"),
    ("Policy Administration System", "Realization", "Policy Management"),
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
