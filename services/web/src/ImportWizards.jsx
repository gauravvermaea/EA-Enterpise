// The Import and export wizards (D676; owner, 14 Nov 2026: "make the whole discovery import export a little more user
// friendly. Can these be wizard guided in a model?", both directions, built in Release 3). Each asks one question first,
// then walks through the screens that already do the work, so a wizard and its tab never differ:
//   BringInWizard   where is the data?  a file I have (template, upload, the load's preview) | files another system drops
//                   in a folder (a delivery source) | a feed EA Explorer reads (OData) | a system or script that sends
//                   it (push, with the Python kit) | documents read by AI; each ends in the review (Loads or Deliveries)
//   TakeOutWizard   what is it for?  edit it in Excel and load it back | a file for another system (a CSV set or an
//                   empty template) | read it live in Power BI or Excel (the OData feed) | a copy of the whole model (a
//                   model package) | a program (the REST API)
// The choices themselves are in importWizardLists.js, so they are tested without a browser.
import { useState } from "react";
import { apiFetch, canOn } from "./auth";
import { refreshAll, useApi } from "./ModelViews";
import { DownloadDialog, Field, Modal } from "./ModelOps";
import { Download, Upload } from "./Sheets";
import { SourceDialog } from "./Deliveries";
import { SCHEDULES, SourcePanel } from "./Discovery";
import { ODataTab } from "./ReportDesigner";
import { Steps } from "./GuidedWizards";
import { BRING_IN, TAKE_OUT, bringInSteps, takeOutSteps } from "./importWizardLists";

const go = (path) => { window.location.hash = path; };
const post = (path, body) => apiFetch(path, { method: "POST", body: JSON.stringify(body || {}) });

function Choices({ options, value, onChange, disabled = {} }) {
  return (
    <div className="ed-radio wizard-choices">
      {options.map(([k, label, hint]) => (
        <label key={k} className="lock-opt" title={disabled[k] || hint}>
          <input type="radio" name="wizard-choice" checked={value === k} disabled={!!disabled[k]} onChange={() => onChange(k)} />
          <span><b>{label}</b><br /><span className="quiet">{disabled[k] || hint}</span></span>
        </label>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------- bringing data in
export function BringInWizard({ m, onClose }) {
  const model = m.id;
  const may = canOn(model, "model.content");
  const { data: srcs } = useApi(`/api/v1/models/${model}/import-sources`);
  const [kind, setKind] = useState("file");
  const [step, setStep] = useState(0);
  const [form, setForm] = useState({ name: "", url: "", auth_ref: "", schedule: "off" });
  const [source, setSource] = useState(null);       // the discovery source made in step 2
  const [folder, setFolder] = useState(false);      // the delivery source dialog open
  const [err, setErr] = useState("");
  const names = bringInSteps(kind);
  const last = names.length - 1;
  const disabled = {};
  if (!may) for (const [k] of BRING_IN) disabled[k] = `Bringing data in needs a role that changes the content of ${m.name}.`;
  if (srcs && !srcs.may_manage) disabled.folder = disabled.folder || "Folder sources are set up by the model's Model Admins.";
  const set = (k) => (e) => setForm({ ...form, [k]: k === "auth_ref" ? e.target.value.toUpperCase() : e.target.value });
  const discovery = ["odata", "push", "ai"].includes(kind);

  async function makeSource() {
    setErr("");
    try {
      const s = await post(`/api/v1/models/${model}/discovery-sources`, { ...form, kind });
      setSource(s); refreshAll(); setStep(2);
    } catch (e) { setErr(e.message); }
  }
  const review = (where) => { onClose(); go(`/metamodel/${model}/import/${where}`); };
  const next = () => {
    if (step === 1 && discovery && !source) return makeSource();
    return setStep(step + 1);
  };
  const nextLabel = step === 0 ? "Next" : step === 1 && discovery && !source ? "Create the source" : "Next";
  const nextOff = (step === 0 && !!disabled[kind]) || (step === 1 && discovery && !source && (!form.name.trim() || (kind === "odata" && !form.url.trim())))
    || (step === 1 && kind === "file");     // the upload itself moves on, to the load's preview

  return (
    <Modal wide title={`Bring data into ${m.name}`} onClose={onClose}
      actions={<>{step > 0 && !(discovery && source && step === 2) && <button onClick={() => setStep(step - 1)}>Back</button>}
        {step < last ? <button className="primary" disabled={nextOff} onClick={next}>{nextLabel}</button>
          : <button className="primary" onClick={() => review(kind === "file" ? "loads" : "deliveries")}>
            {kind === "file" ? "Open Loads" : "Open Deliveries"}</button>}
        <button onClick={onClose}>Close</button></>}>
      <Steps names={names} at={step} />
      {step === 0 && <>
        <p>Where is the data you want to bring into {m.name}?</p>
        <Choices options={BRING_IN} value={kind} onChange={(k) => { setKind(k); setSource(null); }} disabled={disabled} />
        <p className="quiet small">Whichever way it comes, you see what is new, changed and kept before anything reaches the model.</p>
      </>}

      {step === 1 && kind === "file" && <>
        <p>Have a file in EA Explorer's format? Upload it. If not, download a workbook first: the types you choose, with what is in
          the model now, or empty to fill in. A file from another system works too: you map its columns after the upload.</p>
        <details className="wizard-more"><summary>Download a workbook to fill in first</summary><Download model={model} m={m} /></details>
        <Upload model={model} m={m} may={may} onDone={onClose} />
        <p className="quiet small">After the upload the preview opens: check it, correct rows, then add them to your uncommitted changes
          and commit them on the Changes tab.</p>
      </>}

      {step === 1 && kind === "folder" && <>
        <p>Another system drops files in the published formats (an Excel workbook or a CSV set) in a folder of its own. Each file
          becomes a delivery to review. Set the source up, then tell the other system its folder.</p>
        <div className="toolbar"><button className="primary" onClick={() => setFolder(true)}>+ Set up the folder source</button></div>
        {folder && <SourceDialog model={model} source={{}} onClose={() => { setFolder(false); setStep(2); }} />}
      </>}

      {step === 1 && discovery && !source && <div className="ed-form">
        <p>{kind === "odata" ? "EA Explorer reads an OData feed your organisation already has (a configuration database, a cloud inventory): give its address."
          : kind === "push" ? "A system or script sends records to EA Explorer. Name the source; the next step gives its address and a Python example."
            : "The AI engine reads documents (text, Word, web pages) and names the elements and relationships in them. Give a page to read, or leave the address empty and drop documents in the source's folder."}</p>
        <Field label="Name"><input value={form.name} onChange={set("name")} placeholder="Cloud inventory" autoFocus /></Field>
        {kind !== "push" && <Field label="Address" hint={kind === "odata" ? "the feed's service document or one entity set (JSON)" : "a page to read, or empty"}>
          <input value={form.url} onChange={set("url")} placeholder="https://" /></Field>}
        {kind === "odata" && <Field label="Sign-in setting" hint="optional: the name of a setting in the config file (EAX_SOURCE_...) whose value is sent as the Authorization header; never the secret itself">
          <input value={form.auth_ref} onChange={set("auth_ref")} placeholder="EAX_SOURCE_INVENTORY" /></Field>}
        {kind !== "push" && <Field label="Runs"><select value={form.schedule} onChange={set("schedule")}>
          {SCHEDULES.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select></Field>}
        {kind === "ai" && <p className="quiet small">The AI engine is chosen by a Super Admin (Discovery, below the sources); it is off until then.</p>}
      </div>}

      {step === 2 && discovery && source && <>
        <p className="status ok">{source.name} is set up.{kind === "odata" ? " Look at it to check where each set goes, save the mapping, then run it."
          : kind === "push" ? " Download the Python kit or copy the code: it sends the sample files (one for every entity type) to this source."
            : " Run it: the documents are read and what they name becomes a delivery."}</p>
        <SourcePanel id={source.id} model={model} />
      </>}

      {step === last && <>
        <p>{kind === "file" ? "Your upload is in Loads with its preview." : "What arrives becomes a delivery in Deliveries: open it, check what is new, changed and kept, then a Committer, Model Sub Admin or Model Admin accepts or declines it."}</p>
        <p className="quiet small">Nothing reaches the model before that, and an accepted delivery can be undone like any load.</p>
      </>}
      {err && <p className="status bad">{err}</p>}
    </Modal>
  );
}

// ---------------------------------------------------------------- taking data out
export function TakeOutWizard({ m, onClose }) {
  const model = m.id;
  const may = canOn(model, "model.content");
  const [what, setWhat] = useState("edit");
  const [step, setStep] = useState(0);
  const [pkg, setPkg] = useState(false);
  const names = takeOutSteps(what);
  const last = names.length - 1;
  return (
    <Modal wide title={`Take data out of ${m.name}`} onClose={onClose}
      actions={<>{step > 0 && <button onClick={() => setStep(step - 1)}>Back</button>}
        {step < last ? <button className="primary" onClick={() => setStep(step + 1)}>Next</button> : null}
        <button onClick={onClose}>{step === last ? "Done" : "Close"}</button></>}>
      <Steps names={names} at={step} />
      {step === 0 && <>
        <p>What is the data for?</p>
        <Choices options={TAKE_OUT} value={what} onChange={setWhat} />
      </>}
      {step === 1 && what === "edit" && <>
        <p>Choose the types: the workbook holds what is in the model now, one sheet per type and one of relationships. Change values,
          add rows, mark rows to delete.</p>
        <Download model={model} m={m} format="xlsx" />
      </>}
      {step === 2 && what === "edit" && <>
        <p>When you have changed it, upload it here: you see a preview before anything changes.</p>
        <Upload model={model} m={m} may={may} onDone={onClose} />
      </>}
      {step === 1 && what === "file" && <>
        <p>The published formats another system reads and writes (docs/import-formats.md): a CSV set (one file per type and one of
          relationships, with a master file) or an Excel workbook; tick <b>Empty template</b> for the columns only, for a system to fill.</p>
        <Download model={model} m={m} format="zip" />
      </>}
      {step === 1 && what === "live" && <>
        <ODataTab model={model} />
        <p className="quiet small">The feed always shows the committed content as it is now: refresh in Power BI or Excel to see the latest.
          People on single sign-on use a personal token as the password (System admin › Machine access).</p>
      </>}
      {step === 1 && what === "package" && <>
        <p>The whole model as one package (Excel or zip): without data, with the data, or deep with its full history. Upload it in
          another EA Explorer (Models › Upload a model) or keep it as a copy.</p>
        <div className="toolbar"><button className="primary" onClick={() => setPkg(true)}>⬇ Choose and download the package</button></div>
        {pkg && <DownloadDialog m={m} onClose={() => setPkg(false)} />}
      </>}
      {step === 1 && what === "api" && <>
        <p>Programs read and change the model through the REST API, with a personal token or a service account's API key
          (System admin › Machine access). Every address is described in the API documentation.</p>
        <div className="toolbar"><a className="button primary" href="/api/docs" target="_blank" rel="noreferrer">Open the API documentation ↗</a>
          <a className="button" href="#/admin/machine-access">Machine access</a></div>
        <p className="quiet small">To send data in from a program, use a Push source instead: Bring data in › A system or script sends it.</p>
      </>}
      {step === last && what !== "edit" && <p>Done. You can come back to this at any time from Import and export › Take data out.</p>}
    </Modal>
  );
}
