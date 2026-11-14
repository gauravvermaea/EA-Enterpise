// The choices and steps of the Import and export wizards (D676; ImportWizards.jsx): plain data, tested with node.

// Bring data in: where is the data? [key, label, hint]
export const BRING_IN = [
  ["file", "A file I have (Excel or CSV)", "Upload a workbook made here, a CSV set, or a sheet from another system; download a workbook to fill in first if you need one."],
  ["folder", "Files another system drops in a folder", "A system delivers workbooks or CSV sets to a folder of its own; each file becomes a delivery to review."],
  ["odata", "A feed EA Explorer reads (OData)", "A configuration database, a cloud inventory or any OData feed: read on demand, daily or weekly, only what changed."],
  ["push", "A system or script sends it (Push)", "Another system, or a short Python script (the kit has one, with samples), sends records to an address of this model."],
  ["ai", "Documents read by AI", "Text, Word documents or a web page: the AI engine names the elements and relationships in them."],
];

// Take data out: what is it for? [key, label, hint]
export const TAKE_OUT = [
  ["edit", "Edit it in Excel and load it back", "A workbook of the types you choose, with what is there now; change it and upload it again."],
  ["file", "A file for another system", "The published formats: a CSV set or an Excel workbook, or an empty template for a system to fill."],
  ["live", "Read it live in Power BI or Excel", "The model's OData feed: every entity type as a table, signed in as you, always current."],
  ["package", "A copy of the whole model", "A model package (Excel or zip), without data, with the data, or with its full history, for another EA Explorer."],
  ["api", "Use it from a program", "The REST API, with a personal token or a service account's API key."],
];

const IN_STEPS = {
  file: ["Where is your data?", "Template and upload", "Review the preview"],
  folder: ["Where is your data?", "The folder source", "Review the deliveries"],
  odata: ["Where is your data?", "The feed", "Check the mapping and run", "Review the delivery"],
  push: ["Where is your data?", "The source", "Send it (Python kit)", "Review the delivery"],
  ai: ["Where is your data?", "The documents", "Run it", "Review the delivery"],
};

const OUT_STEPS = {
  edit: ["What is it for?", "Download the workbook", "Upload it back"],
  file: ["What is it for?", "Download the file", "Done"],
  live: ["What is it for?", "The OData feed", "Done"],
  package: ["What is it for?", "The model package", "Done"],
  api: ["What is it for?", "The REST API", "Done"],
};

export function bringInSteps(kind) {
  return IN_STEPS[kind] || IN_STEPS.file;
}

export function takeOutSteps(what) {
  return OUT_STEPS[what] || OUT_STEPS.edit;
}
