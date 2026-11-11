// The self-test watched in the admin's own browser (D575, D576): the page sweep and the journeys, run in a same-origin
// frame of System admin › Self-test. The same rules as the headless runner (services/api/eax/testing/ui_pages.py and
// ui_flows.py): each page renders (no script error, no API answer of 500 or more, not "no route"), shows a heading and
// opens help on F1; each journey's steps (open, click, choose, fill, select, press, expect, expect_not, expect_sel,
// upload) are done the way a person would. test_selftest_coverage.py checks both sides know the same step kinds.

export const STEP_KINDS = ["open", "click", "choose", "fill", "select", "press", "expect", "expect_not", "expect_sel", "upload"];
const UUID = /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/gi;
const LEAVE = /^#\/(break-glass|heartbeat|sql)\b|logout|sign-?out/i;
const CLICKABLE = "button, a, [role=tab], [role=button], summary, label";
const TABS = '[role=tablist] a[href^="#/"], .tabs a[href^="#/"], .nav-groups a[href^="#/"], .nav-menu a[href^="#/"], '
  + 'nav.subnav a[href^="#/"], .subtabs a[href^="#/"], .seg a[href^="#/"]';
export const MAX_PAGES = 400;

const pause = (ms) => new Promise((ok) => setTimeout(ok, ms));
const esc = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

export function norm(route) {
  const r = route.trim().replace(/\/+(\?|$)/, "$1");
  return r || "#/";
}

export function inScope(route, scope) {
  if (!route.startsWith("#/") || LEAVE.test(route)) return false;
  const own = new Set(scope.map((s) => s.toLowerCase()));
  return (route.match(UUID) || []).every((u) => own.has(u.toLowerCase()));
}

export function judge(found, errors, help) {
  const bad = [];
  if (errors.length) bad.push(errors.slice(0, 5).join("; "));
  if (found.notFound) bad.push("shows not found");
  if (!found.head) bad.push("no heading");
  if (help !== "ok") bad.push(help === "closed" ? "F1 opened no help" : "F1: no help for this screen");
  if (!bad.length) return ["passed", "renders, has a heading, F1 help"];
  return [errors.length || found.notFound ? "failed" : "warning", bad.join("; ")];
}

// ---------------------------------------------------------------- the frame
export function makeFrame(frame, ticket, onError) {
  let role = null;
  const doc = () => frame.contentDocument;
  const text = () => (doc()?.querySelector("main") || doc()?.body)?.innerText || "";
  const waitFor = async (test, ms) => {
    const end = Date.now() + ms;
    while (Date.now() < end) {
      try { if (test()) return true; } catch { /* loading */ }
      await pause(250);
    }
    return false;
  };
  const watch = () => {
    try {
      const w = frame.contentWindow;
      if (w.__eaxSelfTestWatched) return;
      w.__eaxSelfTestWatched = true;
      w.addEventListener("error", (e) => onError(`script error: ${String(e.message || e).slice(0, 200)}`));
      const f = w.fetch.bind(w);
      w.fetch = async (...a) => {
        const r = await f(...a);
        const url = String(a[0]?.url || a[0]);
        if (url.includes("/api/") && r.status >= 500) onError(`${(a[1]?.method || "GET").toUpperCase()} ${url.split("?")[0]}: ${r.status}`);
        return r;
      };
    } catch { /* not ours */ }
  };
  const open = async (route, as, fresh) => {
    if (fresh || as !== role || !frame.contentWindow?.location?.href?.includes("eaxselftest")) {
      role = as;
      await new Promise((ok) => { frame.onload = ok; frame.src = `/?eaxselftest=${encodeURIComponent(ticket)}&eaxrole=${encodeURIComponent(as)}${route}`; setTimeout(ok, 15000); });
    } else {
      frame.contentWindow.location.hash = route.slice(1);
    }
    watch();
    const ok = await waitFor(() => doc().body.innerText.includes("EA Explorer"), 60000);
    if (!ok) throw new Error(`EA Explorer did not open ${route} within 60 s`);
    await pause(1200);
  };
  return { doc, text, waitFor, open, win: () => frame.contentWindow };
}

function visible(el) {
  return !!el && !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
}

function clickable(doc, label, exact) {
  const pat = new RegExp(exact ? `^\\s*${esc(label)}\\s*$` : `^\\s*${esc(label)}`, "i");
  return [...doc.querySelectorAll(CLICKABLE)].find((el) => visible(el) && pat.test(el.innerText || el.getAttribute("aria-label") || ""));
}

function field(doc, label) {
  const low = label.toLowerCase();
  for (const l of doc.querySelectorAll("label")) {
    if (!(l.innerText || "").trim().toLowerCase().startsWith(low)) continue;
    const el = l.htmlFor ? doc.getElementById(l.htmlFor) : l.querySelector("input, select, textarea");
    if (visible(el)) return el;
  }
  return [...doc.querySelectorAll("input, select, textarea")].find((el) => visible(el)
    && ((el.getAttribute("aria-label") || "").toLowerCase().startsWith(low) || (el.placeholder || "").toLowerCase().startsWith(low)));
}

function setValue(el, value) {
  // the way React sees a person typing: the element's own value setter, then input and change
  const proto = Object.getPrototypeOf(el);
  Object.getOwnPropertyDescriptor(proto, "value")?.set?.call(el, value);
  el.dispatchEvent(new Event("input", { bubbles: true }));
  el.dispatchEvent(new Event("change", { bubbles: true }));
}

function press(f, key) {
  const d = f.doc();
  const target = d.activeElement || d.body;
  for (const type of ["keydown", "keyup"]) target.dispatchEvent(new f.win().KeyboardEvent(type, { key, code: key, bubbles: true }));
}

// one step; "" when done, else why not (an optional step is then skipped)
export async function step(f, s, role) {
  const d = f.doc();
  if ("open" in s) {
    await f.open(s.open, role);
    if (s.expect && !(await f.waitFor(() => f.doc().body.innerText.includes(s.expect), 20000))) return `"${s.expect}" did not show`;
  } else if ("click" in s) {
    const el = clickable(d, s.click, s.exact) || (s.optional_alt && clickable(d, s.optional_alt));
    if (!el) return `no button or link "${s.click}"`;
    if (el.disabled || el.getAttribute("aria-disabled") === "true") return `"${s.click}" is disabled`;
    el.click();
  } else if ("choose" in s) {
    const l = [...d.querySelectorAll("label")].find((x) => visible(x) && (x.innerText || "").includes(s.choose));
    if (!l) return `no choice "${s.choose}"`;
    l.click();
  } else if ("fill" in s) {
    const el = field(d, s.fill);
    if (!el) return `no field "${s.fill}"`;
    el.focus();
    setValue(el, s.value);
  } else if ("select" in s) {
    const el = field(d, s.select);
    if (!el) return `no drop-down "${s.select}"`;
    const o = [...el.options].find((x) => x.text.trim().toLowerCase().startsWith(s.option.toLowerCase()));
    if (!o) return `"${s.select}" has no option "${s.option}"`;
    setValue(el, o.value);
  } else if ("press" in s) {
    press(f, s.press);
  } else if ("expect" in s) {
    if (!(await f.waitFor(() => f.doc().body.innerText.includes(s.expect), 20000))) return `"${s.expect}" did not show`;
  } else if ("expect_not" in s) {
    await pause(500);
    if (f.doc().body.innerText.includes(s.expect_not)) return `"${s.expect_not}" still shows`;
  } else if ("expect_sel" in s) {
    if (!(await f.waitFor(() => f.doc().querySelector(s.expect_sel), 20000))) return `nothing matches ${s.expect_sel}`;
  } else if ("upload" in s) {
    const el = d.querySelector(s.upload);
    if (!el) return `no file input ${s.upload}`;
    const dt = new (f.win().DataTransfer)();
    dt.items.add(new (f.win().File)([s.text], s.name, { type: "application/octet-stream" }));
    el.files = dt.files;
    el.dispatchEvent(new Event("change", { bubbles: true }));
  }
  await pause(s.wait || 400);
  return "";
}

async function refusal(f, r, role) {
  await f.open(r.open, role);
  await pause(1500);
  const d = f.doc();
  if (r.select) {
    const el = field(d, r.select[0]);
    const o = el && [...el.options].find((x) => x.text.trim().toLowerCase().startsWith(r.select[1].toLowerCase()));
    if (o) { setValue(el, o.value); await pause(1200); }
  }
  if (r.click_first) {
    const el = clickable(f.doc(), r.click_first);
    if (el && !el.disabled) { el.click(); await pause(1500); }
  }
  const el = clickable(f.doc(), r.disabled_or_absent);
  if (!el) return ["passed", `"${r.disabled_or_absent}" not offered to ${role}`];
  if (el.disabled) return ["passed", `"${r.disabled_or_absent}" disabled for ${role}`];
  return ["failed", `"${r.disabled_or_absent}" is offered to ${role}, who may not do it`];
}

export async function journey(f, j) {
  if (j.refusal) return refusal(f, j.refusal, j.role);
  let done = 0;
  const skipped = [];
  for (const s of j.steps) {
    let why;
    try { why = await step(f, s, j.role); } catch (e) { why = String(e.message || e).slice(0, 200); }
    if (why) {
      if (s.optional) { skipped.push(why); continue; }
      const k = Object.keys(s)[0];
      return ["failed", `step ${done + skipped.length + 1} (${k} ${s[k]}): ${why}`];
    }
    done += 1;
  }
  return ["passed", `${done} steps as ${j.role}${skipped.length ? `; ${skipped.length} optional skipped` : ""}`];
}

// ---------------------------------------------------------------- the page sweep
const pageFound = (f) => {
  const d = f.doc();
  const main = d.querySelector("main") || d.body;
  const head = [...d.querySelectorAll("main h1, main h2, main h3, main .nav-crumbs [aria-current]")]
    .some((h) => (h.innerText || "").trim().length > 1 && h.offsetParent !== null);
  const links = new Set();
  const nav = f.win().__eaxNav;
  if (nav?.groups) for (const g of nav.groups) for (const t of g.tabs) if (t.href) links.add(t.href);
  for (const a of d.querySelectorAll(TABS)) links.add(a.getAttribute("href"));
  return { head, notFound: /\bno route\b|^\s*Not found\s*$/im.test(main.innerText || ""), links: [...links] };
};

const helpState = (f) => {
  const p = f.doc().querySelector(".help-panel");
  if (!p) return "closed";
  return /No help for this screen yet/.test(p.innerText) ? "empty" : "ok";
};

// opens every page from browser.pages through their tabs, in scope; report(name, outcome, detail, ms, shot) per page
export async function sweep(f, browser, errors, report, onPage) {
  for (const [route, why] of Object.entries(browser.pages_skip || {})) await report(`page: ${route}`, "skipped", why, 0);
  const queue = (browser.pages || []).map(norm);
  const seen = new Set(queue);
  let n = 0;
  while (queue.length && n < MAX_PAGES) {
    const route = queue.shift();
    onPage?.(route, n, n + queue.length + 1);
    const t0 = Date.now();
    errors.length = 0;
    let outcome, detail;
    try {
      await f.open(route, "super-admin", n % 25 === 0);
      const found = pageFound(f);
      press(f, "F1");
      await pause(300);
      const help = helpState(f);
      press(f, "Escape");
      [outcome, detail] = judge(found, errors, help);
      for (const l of found.links) {
        const r = norm(l);
        if (!seen.has(r) && inScope(r, browser.scope || [])) { seen.add(r); queue.push(r); }
      }
    } catch (e) { outcome = "failed"; detail = String(e.message || e).slice(0, 300); }
    n += 1;
    await report(`page: ${route}`, outcome, `${detail} (as super-admin)`, Date.now() - t0, outcome === "failed");
  }
  if (queue.length) await report("page sweep", "warning", `stopped at ${MAX_PAGES} pages; ${queue.length} more not opened`, 0);
  return n;
}

// ---------------------------------------------------------------- the same run from the command line (D578)
// The forms of the eax command (D331). commandLine mirrors store.command_line (services/api/eax/testing/store.py);
// test_selftest_coverage.py runs both on the same runs and compares them.
export const CLI_FORMS = [[".\\eax", "Windows"], ["./eax.sh", "Linux or Mac"], [".\\eaxpy", "eaxpy, Windows"], ["./eaxpy.sh", "eaxpy, Linux or Mac"]];
export const ALL_SUITES = ["api", "ui", "db", "security"];

export function commandLine(run, eax = ".\\eax") {
  const bits = [eax, "test"];
  const suites = run.suites || [];
  const journeys = run.journeys || [];
  if (run.pages_only) bits.push("--pages-only");
  else if (journeys.length) for (const j of journeys) bits.push(j.includes(" ") ? `--journey "${j}"` : `--journey ${j}`);
  else if (run.level === "detailed") {
    bits.push("--detailed");
    const all = suites.length === ALL_SUITES.length && ALL_SUITES.every((s) => suites.includes(s));
    if (suites.length && !all) for (const s of suites) bits.push(`--suite ${s}`);
  } else bits.push("--smoke");
  if (run.role) bits.push(`--role ${run.role}`);
  if (run.area) bits.push(`--area ${run.area}`);
  return bits.join(" ") + (run.watch ? "   (journeys watched in a browser: from the Self-test page only)" : "");
}
