// A page's tabs (D478): groups, then tabs, then the tab's own sub-tabs (Classic's one row went with R2.25, D606). The
// same #/... links as ever, so old links and bookmarks keep working. Each group remembers its last tab; counts roll up onto the group.
import { useEffect } from "react";
import ActionsMenu from "./ActionsMenu";
import { clearCurrentNav, readLastTabs, saveLastTab, setCurrentNav } from "./navActions";

// tabs: [[key, label, count?]]; groups: [[key, label, icon, [tab keys]]].
// href(k): the tab's link; active: the tab shown; crumbs: [{ label, href }] before the group; subLabel: the sub-tab shown.
export default function PageNav({ page, tabs, groups, active, href, crumbs = [], subLabel = "", ctx = {}, children }) {
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
