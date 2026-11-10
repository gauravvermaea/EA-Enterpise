// A page's tabs in the person's chosen style (D478): Grouped (groups, then tabs, then the tab's own sub-tabs), Menu (a
// menu down the left, folding to icons) or Classic (every tab in one row, as before). The same #/... links in every
// style, so old links and bookmarks keep working. Each group remembers its last tab; counts roll up onto the group.
import { useEffect, useRef, useState } from "react";
import ActionsMenu from "./ActionsMenu";
import {
  clearCurrentNav, NAV_STYLES, navStyleChosen, readFolded, readLastTabs, readNavStyle, saveFolded, saveLastTab, saveNavStyle, setCurrentNav,
} from "./navActions";

export function useNavStyle() {
  const [style, setStyle] = useState(readNavStyle);
  useEffect(() => {
    const on = () => setStyle(readNavStyle());
    window.addEventListener("eax-nav-style", on);
    return () => window.removeEventListener("eax-nav-style", on);
  }, []);
  return [style, saveNavStyle];
}

// the chooser, in the top bar beside the person's name (and on My profile)
export function NavStylePicker({ compact = false }) {
  const [style, setStyle] = useNavStyle();
  return (
    <label className={compact ? "nav-style-pick compact" : "nav-style-pick"} title="How the tabs of model and project pages are shown">
      {compact ? <span aria-hidden="true">▦</span> : "Page tabs "}
      <select aria-label="Page tabs style" value={style} onChange={(e) => setStyle(e.target.value)}>
        {NAV_STYLES.map(([k, l, d]) => <option key={k} value={k} title={d}>{l}</option>)}
      </select>
    </label>
  );
}

// tabs: [[key, label, count?]] in today's order (Classic); groups: [[key, label, icon, [tab keys]]].
// href(k): the tab's link; active: the tab shown; crumbs: [{ label, href }] before the group; subLabel: the sub-tab shown.
export default function PageNav({ page, tabs, groups, active, href, crumbs = [], subLabel = "", ctx = {}, children }) {
  const [style] = useNavStyle();
  const [folded, setFolded] = useState(readFolded);
  const byKey = Object.fromEntries(tabs.map((t) => [t[0], t]));
  const placed = new Set();
  const live = groups.map(([gk, gl, icon, keys]) => {
    const list = keys.filter((k) => byKey[k] && !placed.has(k)).map((k) => { placed.add(k); return byKey[k]; });
    return { k: gk, label: gl, icon, tabs: list, count: list.reduce((n, t) => n + (Number(t[2]) || 0), 0) };
  });
  const rest = tabs.filter((t) => !placed.has(t[0]));      // a tab no group names (added later): never lost
  if (rest.length) live.push({ k: "other", label: "Other", icon: "•", tabs: rest, count: rest.reduce((n, t) => n + (Number(t[2]) || 0), 0) });
  const shown = live.filter((g) => g.tabs.length);
  const group = shown.find((g) => g.tabs.some((t) => t[0] === active)) || shown[0];
  const tab = byKey[active] || group?.tabs[0];
  useEffect(() => { if (group && tab) saveLastTab(page, group.k, tab[0]); }, [page, group?.k, tab?.[0]]);   // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    const nav = { page, groups: shown.map((g) => ({ label: g.label, tabs: g.tabs.map((t) => ({ k: t[0], label: t[1], href: href(t[0]) })) })), ctx, active };
    setCurrentNav(nav);
    return () => clearCurrentNav(nav);
  });
  const last = readLastTabs(page);
  const groupHref = (g) => href(g.tabs.some((t) => t[0] === last[g.k]) ? last[g.k] : g.tabs[0][0]);
  const label = (t) => <>{t[1]}{Number(t[2]) ? <span className="nav-count"> ({t[2]})</span> : null}</>;
  const tabLink = (t) => (
    <a key={t[0]} role="tab" aria-selected={tab && tab[0] === t[0]} href={href(t[0])}
      className={tab && tab[0] === t[0] ? "tab on" : "tab"}>{label(t)}</a>
  );
  const actions = <ActionsMenu page={page} tab={tab ? tab[0] : ""} ctx={ctx} />;
  const trail = (
    <nav className="nav-crumbs small" aria-label="Breadcrumb">
      {crumbs.map((c, i) => <span key={i}>{c.href ? <a href={c.href}>{c.label}</a> : c.label} › </span>)}
      {group && <span>{group.label} › </span>}
      {tab && (subLabel ? <><a href={href(tab[0])}>{tab[1]}</a> › <span aria-current="page">{subLabel}</span></> : <span aria-current="page">{tab[1]}</span>)}
    </nav>
  );

  if (style === "classic") {
    return (
      <>
        <div className="tabs nav-classic" role="tablist">
          {tabs.map(tabLink)}
          <span className="nav-spacer" />{actions}
        </div>
        {children}
      </>
    );
  }

  if (style === "menu") {
    return (
      <div className={folded ? "nav-menu-layout folded" : "nav-menu-layout"}>
        <aside className="nav-menu" aria-label="Page menu">
          <button className="linkish nav-fold" aria-expanded={!folded} title={folded ? "Open the menu" : "Fold the menu to icons"}
            onClick={() => { saveFolded(!folded); setFolded(!folded); }}>{folded ? "»" : "«"}</button>
          <ul>
            {shown.map((g) => (
              <li key={g.k} className={g === group ? "on" : ""}>
                <a className="nav-menu-group" href={groupHref(g)} title={g.label} aria-current={g === group ? "true" : undefined}>
                  <span className="nav-icon" aria-hidden="true">{g.icon}</span>
                  {!folded && <span className="nav-menu-label">{g.label}</span>}
                  {g.count ? <span className="nav-badge">{g.count}</span> : null}
                </a>
                {!folded && (
                  <ul>
                    {g.tabs.map((t) => (
                      <li key={t[0]}><a href={href(t[0])} className={tab && tab[0] === t[0] ? "on" : ""}
                        aria-current={tab && tab[0] === t[0] ? "page" : undefined}>{label(t)}</a></li>
                    ))}
                  </ul>
                )}
              </li>
            ))}
          </ul>
        </aside>
        <div className="nav-menu-main">
          <div className="nav-menu-top">{trail}<span className="nav-spacer" />{actions}</div>
          {children}
        </div>
      </div>
    );
  }

  // Grouped (the default)
  return (
    <>
      {trail}
      <div className="tabs nav-groups" role="tablist" aria-label="Groups">
        {shown.map((g) => (
          <a key={g.k} role="tab" aria-selected={g === group} href={groupHref(g)} className={g === group ? "tab on" : "tab"}>
            <span className="nav-icon" aria-hidden="true">{g.icon}</span> {g.label}{g.count ? <span className="nav-badge">{g.count}</span> : null}
          </a>
        ))}
      </div>
      {group && (
        <div className="tabs sub nav-tabs" role="tablist" aria-label={group.label}>
          {group.tabs.map(tabLink)}
          <span className="nav-spacer" />{actions}
        </div>
      )}
      {children}
    </>
  );
}

// ---------------------------------------------------------------- first sign-in: choose a style (owner, 10 Nov 2026, D478)
// Shown once, before the page, to a person who has not chosen yet. Esc or Skip keeps Grouped and does not ask again.
// Not shown to automated browsers (navigator.webdriver, i.e. Playwright and tests) unless the address has ?welcome=1.
function Sketch({ kind }) {
  const bar = (x, y, w, h, on) => <rect x={x} y={y} width={w} height={h} rx="2" className={on === "pane" ? "sk-pane" : on ? "sk-on" : "sk"} />;
  return (
    <svg viewBox="0 0 120 80" className="nav-sketch" aria-hidden="true">
      <rect x="1" y="1" width="118" height="78" rx="5" className="sk-frame" />
      {kind === "grouped" && <>{[0, 1, 2, 3, 4].map((i) => bar(8 + i * 21, 8, 18, 8, i === 0))}{[0, 1, 2].map((i) => bar(8 + i * 18, 20, 15, 6, i === 1))}{bar(8, 30, 104, 42, "pane")}</>}
      {kind === "menu" && <>{bar(8, 8, 28, 64, "pane")}{[0, 1, 2, 3, 4, 5].map((i) => bar(11, 12 + i * 9, i % 3 === 0 ? 22 : 18, 5, i === 1))}{bar(42, 8, 70, 64, "pane")}</>}
      {kind === "classic" && <>{[0, 1, 2, 3, 4, 5, 6, 7].map((i) => bar(8 + i * 13, 8, 11, 7, i === 2))}{[0, 1, 2, 3, 4, 5, 6, 7].map((i) => bar(8 + i * 13, 17, 11, 7, false))}{bar(8, 28, 104, 44, "pane")}</>}
    </svg>
  );
}

export function NavWelcome() {
  const force = /[?&]welcome=1\b/.test(window.location.search);
  const [open, setOpen] = useState(() => force || (!navStyleChosen() && !navigator.webdriver));
  const first = useRef(null);
  useEffect(() => { if (open) first.current?.focus(); }, [open]);
  if (!open) return null;
  const choose = (k) => { saveNavStyle(k); setOpen(false); };
  return (
    <div className="ed-backdrop nav-welcome-back" onKeyDown={(e) => { if (e.key === "Escape") { e.preventDefault(); choose("grouped"); } }}>
      <div className="ed-dialog nav-welcome" role="dialog" aria-modal="true" aria-labelledby="nav-welcome-title">
        <h2 id="nav-welcome-title">Welcome: how should pages show their tabs?</h2>
        <p className="quiet">Model and project pages have many tabs. Choose the layout you like.</p>
        <div className="nav-welcome-choices" role="group" aria-label="Layouts">
          {NAV_STYLES.map(([k, l, d], i) => (
            <button key={k} ref={i === 0 ? first : undefined} className={k === "grouped" ? "nav-welcome-choice rec" : "nav-welcome-choice"} onClick={() => choose(k)}>
              <Sketch kind={k} />
              <strong>{l}{k === "grouped" && <span className="chip on">Recommended</span>}</strong>
              <span className="small quiet">{d}</span>
            </button>
          ))}
        </div>
        <p className="small quiet">You can change this any time from ▦ beside your name.</p>
        <div className="ed-actions"><button className="linkish" onClick={() => choose("grouped")}>Skip (keep Grouped)</button></div>
      </div>
    </div>
  );
}
