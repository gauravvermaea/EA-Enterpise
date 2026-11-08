// The content framework's fixed areas (D299), the same list as eax/content_framework.py AREAS (a test checks they match).
// [code, label, section, group]; "Outcomes" where TOGAF says objectives (house style).
export const CF_AREAS = [
  ["prelim.principles", "Architecture Principles", "Principles, vision and requirements", "Preliminary"],
  ["req.requirements", "Requirements", "Principles, vision and requirements", "Architecture Requirements"],
  ["req.constraints", "Constraints", "Principles, vision and requirements", "Architecture Requirements"],
  ["req.assumptions", "Assumptions", "Principles, vision and requirements", "Architecture Requirements"],
  ["req.gaps", "Gaps", "Principles, vision and requirements", "Architecture Requirements"],
  ["req.locations", "Locations", "Principles, vision and requirements", "Architecture Requirements"],
  ["vision.business_strategy", "Business Strategy", "Principles, vision and requirements", "Architecture Vision"],
  ["vision.technology_strategy", "Technology Strategy", "Principles, vision and requirements", "Architecture Vision"],
  ["vision.principles_drivers", "Business Principles, Outcomes and Drivers", "Principles, vision and requirements", "Architecture Vision"],
  ["vision.architecture_vision", "Architecture Vision", "Principles, vision and requirements", "Architecture Vision"],
  ["vision.stakeholders", "Stakeholders", "Principles, vision and requirements", "Architecture Vision"],
  ["motivation.drivers", "Drivers", "Architecture definition", "Motivation"],
  ["motivation.goals", "Goals", "Architecture definition", "Motivation"],
  ["motivation.outcomes", "Outcomes", "Architecture definition", "Motivation"],
  ["motivation.measures", "Measures", "Architecture definition", "Motivation"],
  ["business.value_streams", "Value Streams", "Architecture definition", "Business: strategy"],
  ["business.capabilities", "Business Capabilities", "Architecture definition", "Business: strategy"],
  ["business.courses_of_action", "Courses of Action", "Architecture definition", "Business: strategy"],
  ["business.services_contracts", "Business Services, Contracts", "Architecture definition", "Business: operational"],
  ["business.processes_events", "Processes, Events", "Architecture definition", "Business: operational"],
  ["business.functions_org_units", "Functions, Organisation Units", "Architecture definition", "Business: operational"],
  ["business.roles_actors", "Roles, Actors", "Architecture definition", "Business: operational"],
  ["data.entities", "Data Entities", "Architecture definition", "Data"],
  ["data.logical_components", "Logical Data Components", "Architecture definition", "Data"],
  ["data.physical_components", "Physical Data Components", "Architecture definition", "Data"],
  ["app.services", "Application Services", "Architecture definition", "Application"],
  ["app.logical_components", "Logical Application Components", "Architecture definition", "Application"],
  ["app.physical_components", "Physical Application Components", "Architecture definition", "Application"],
  ["tech.services", "Technology Services", "Architecture definition", "Technology"],
  ["tech.logical_components", "Logical Technology Components", "Architecture definition", "Technology"],
  ["tech.physical_components", "Physical Technology Components", "Architecture definition", "Technology"],
  ["real.capabilities", "Capabilities", "Architecture realisation", "Opportunities, solutions and migration planning"],
  ["real.work_packages", "Work Packages", "Architecture realisation", "Opportunities, solutions and migration planning"],
  ["real.contracts", "Architecture Contracts", "Architecture realisation", "Opportunities, solutions and migration planning"],
  ["gov.standards", "Standards", "Architecture realisation", "Implementation governance"],
  ["gov.guidelines", "Guidelines", "Architecture realisation", "Implementation governance"],
  ["gov.specifications", "Specifications", "Architecture realisation", "Implementation governance"],
];
export const CF_LABEL = Object.fromEntries(CF_AREAS.map(([c, l]) => [c, l]));
// for a select: [code, "group: label"]
export const CF_OPTIONS = CF_AREAS.map(([c, l, , g]) => [c, `${g}: ${l}`]);
// the parts of the TOGAF Architecture Repository a document class or an entity type is filed in (D318)
export const REPO_AREAS = ["Architecture Metamodel", "Architecture Capability", "Architecture Landscape", "Standards Information Base",
  "Reference Library", "Governance Log", "Architecture Requirements Repository", "Solutions Landscape"];
