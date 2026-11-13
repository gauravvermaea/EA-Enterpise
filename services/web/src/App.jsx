import { useEffect, useState } from "react";
import { apiFetch, can, isBreakGlass, keycloak, keycloakReachable, myInfo, partOn, roles, signedIn as isSignedIn } from "./auth";
import BreakGlass from "./BreakGlass";
import { config } from "./config";
import StartPage, { EverythingElse } from "./StartPage";
import { ArchitectureWork } from "./Areas";
import ArchitectureRepositoryPage from "./ArchitectureRepository";
import ReferenceLibraryPage from "./ReferenceLibrary";
import EnterpriseLibraryPage from "./Libraries";
import MyProfile from "./Skills";
import ModelAdmin from "./ModelAdmin";
import Metamodel from "./Metamodel";
import { DrawnViewFullScreen } from "./DrawnView";
import { ScratchDrawioFullScreen } from "./ScratchDrawio";
import Mcp from "./Mcp";
import Library from "./Library";
import CompareScreen from "./Versions";
import ChangeLog from "./ChangeLog";
import { TaskDrawer } from "./TaskDrawer";
import NotificationsPage, { Bell, ChangeDocumentPage } from "./Notifications";
import SurveysPage from "./Surveys";
import Admin from "./Admin";
import { fmtDateTime, setAppSettings } from "./fmt";
import { refreshAll } from "./ModelViews";
import ModelSwitcher, { ProjectSwitcher } from "./ModelSwitcher";
import { SearchPage, TopSearch } from "./GridPages";
import { RestoreLock, useRestoreLock } from "./Restores";
import StartupStatus from "./StartupStatus";
import Projects, { ProjectAdmin, ProjectLibraryPage } from "./Projects";
import { PrinciplesPage } from "./Principles";
import MergeRequestsPage from "./MergeBack";
import ArchivePage from "./Archive";
import TopMenu, { MenuBar } from "./TopMenu";
import FarmPage from "./Farm";
import QuickJump from "./QuickJump";
import EntityMenu from "./EntityMenu";
import { UpdateNotice } from "./Updates";
import { AdminBanner } from "./AdminBanner";
import { ContainerAlertBanner } from "./Hosts";
import HelpPanel from "./help/HelpPanel";
import DocumentationPage from "./Documentation";

function useHashRoute() {
  const [route, setRoute] = useState(window.location.hash || "#/");
  useEffect(() => {
    const onChange = () => setRoute(window.location.hash || "#/");
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);
  return route;
}

export default function App() {
  const route = useHashRoute();
  const signedIn = isSignedIn();
  const [version, setVersion] = useState(null);  // the product version, from the API (version.toml)
  const [build, setBuild] = useState(null);      // its build: commit or CI number, when, channel (R2.47)
  const [, setFormatsReady] = useState(0);        // re-render once the installation's formats are in
  const [maintenance, setMaintenance] = useState(null);   // a restore is running: read only (D216)
  // a self-test in progress (R2.51, D609): who signs in meanwhile waits (testAtSignIn); those already in see a banner
  const [testRun, setTestRun] = useState(null);
  const [testAtSignIn, setTestAtSignIn] = useState(null);   // null: not known yet; true: it was running when they came
  useEffect(() => {
    if (!signedIn) return undefined;
    const beat = () => apiFetch("/api/v1/heartbeat").then((b) => {
      setVersion(b.version); setBuild({ build: b.build, built_at: b.built_at, commit: b.commit, channel: b.channel }); setMaintenance(b.maintenance || null); setTestRun(b.test_in_progress || null);
      setTestAtSignIn((was) => (was === null ? !!b.test_in_progress : was && !!b.test_in_progress));
    }).catch(() => {});
    beat();
    const t = setInterval(beat, 20000);
    return () => clearInterval(t);
  }, [signedIn]);
  useEffect(() => {
    // the installation's formats and time zone, for every screen (phase 10, D182)
    if (signedIn) apiFetch("/api/v1/settings").then((s) => { setAppSettings(s); setFormatsReady((n) => n + 1); }).catch(() => {});
    // the sign-in check (D215): IT and Super Admins, once per sign-in, in the background; a notification follows if
    // anything needs attention, so the bell is read again shortly after
    if (signedIn && can("system.operate")) {
      let done = false;
      try { done = window.sessionStorage.getItem("eax.signInCheck") === "1"; } catch { /* no storage: check anyway */ }
      if (!done) {
        try { window.sessionStorage.setItem("eax.signInCheck", "1"); } catch { /* no storage */ }
        apiFetch("/api/v1/admin/sign-in-check", { method: "POST" })
          .then(() => { setTimeout(refreshAll, 20000); setTimeout(refreshAll, 60000); }).catch(() => {});
      }
    }
  }, [signedIn]);

  // While an infrastructure restore runs, every screen shows the lock page (D227)
  const lock = useRestoreLock();
  if (lock) return <RestoreLock lock={lock} />;

  // Nothing of the application shows until the user has signed in.
  if (!signedIn) {
    if (route.startsWith("#/break-glass")) return <BreakGlass />;
    return (
      <div className="signin">
        <div className="signin-card">
          <h1>EA Explorer</h1>
          {keycloakReachable ? <p className="quiet">Sign in to continue.</p>
            : <p className="status bad">Sign-in (Keycloak) is not reachable at the moment.</p>}
          <button className="primary" onClick={() => keycloak.login()}>Sign in</button>
          <p className="small-note"><a href="#/break-glass">Keycloak is down? Break-glass sign-in</a></p>
        </div>
      </div>
    );
  }
  const info = myInfo();
  const testExempt = testLockExempt(info);
  // the test's own accounts (its browser journeys and page sweep) see EA Explorer as it is
  const testRunShown = ((info || {}).username || "").startsWith("svc-self-test-") ? null : testRun;
  if (signedIn && testRunShown && testAtSignIn && !testExempt) return <TestInProgress run={testRunShown} />;
  // a drawn view opens in a tab of its own, full screen: none of EA Explorer's header or menus (D411)
  const drawn = /^#\/metamodel\/([^/]+)\/drawn-views\/([^/?]+)/.exec(route);
  if (drawn) return <DrawnViewFullScreen key={route} model={drawn[1]} view={decodeURIComponent(drawn[2])} route={route} />;
  // a picture opened in draw.io (D585): a scratch view in a tab of its own, full screen too
  const scratch = /^#\/drawio\/open\/([A-Za-z0-9]+)/.exec(route);
  if (scratch) return <ScratchDrawioFullScreen key={route} scratchKey={scratch[1]} />;

  return (
    <div className="shell menu-style">
      {/* the menu bar only: the Classic screens are gone (owner, 12 Nov 2026, R2.25, D606) */}
      <header className="topbar with-menu">
        <MenuBar route={route} place="left" label="Sites" />
        <a href="#/" className="brand">EA Explorer</a>
        {version && <VersionTag version={version} build={build} />}
        <span className="tm-break" aria-hidden="true" /><TopMenu route={route} />
        <TopSearch find />
        <div className="switchers">
          <ModelSwitcher route={route} />
          <ProjectSwitcher route={route} />
        </div>
        <div className="user">
          <div className="user-row">
          {signedIn ? (
            /* the menu style (D591): ? and the person's own menu (their name: User and Profile, Sign out) in one place;
               the bell beside them, so everything about the person is together (owner, 12 Nov 2026, R2.34) */
            <><Bell route={route} /><MenuBar route={route} place="right" label="Help and my menu" /></>
          ) : (
            <button className="primary" onClick={() => keycloak.login()}>Sign in</button>
          )}
          </div>
          {/* what is still starting: at the far right of the tools row (owner, 10 Nov 2026), never pushing the menu about */}
          <StartupStatus />
        </div>
      </header>
      {isBreakGlass() && <div className="break-glass-banner">Break-glass session: everything you do is audited and the IT and Super Admins are alerted. Change the break-glass password afterwards.</div>}
      {signedIn && !isBreakGlass() && !roles().length && !(info?.models || []).length && (
        <div className="lock-banner">You have no role yet: you see nothing until a model's Model Admin gives you a role
          on a model, or a Keycloak Admin gives you a global role.</div>
      )}
      {testRunShown && <div className="break-glass-banner test-lock-banner">An environment test is in progress (self-test {testRunShown.id},
        started {String(testRunShown.since || "").slice(11, 16)} by {testRunShown.by}{testRunShown.step ? `: ${testRunShown.step}` : ""}; {testRunShown.done} checks so far).
        {testExempt ? " Meanwhile only the Self-test page is open, so the test is not disturbed." : " You can keep reading; changes wait until it ends."}</div>}
      {maintenance && <div className="break-glass-banner">EA Explorer is read only: {maintenance.what || "a restore is running"} (started by {maintenance.by}).
        Nothing can be changed until it is done; you will be asked to sign in again.</div>}
      {signedIn && !isBreakGlass() && <UpdateNotice />}
      {signedIn && <AdminBanner />}
      {signedIn && <ContainerAlertBanner />}
      {signedIn && <TaskDrawer />}
      <main>
        {testRunShown && testExempt && !route.startsWith("#/admin/self-test") ? <TestOnlyPage />
          : partOff(route) ? <PartOff part={partOff(route)} />
          : route.startsWith("#/search") ? <SearchPage key={route} route={route} />
          : route.startsWith("#/work") ? <ArchitectureWork />
          : route.startsWith("#/repository") ? <ArchitectureRepositoryPage />
          : route.startsWith("#/reference-library") ? <ReferenceLibraryPage route={route} />
          : route.startsWith("#/enterprise-library") ? <EnterpriseLibraryPage route={route} />
          : route.startsWith("#/my-profile") ? <MyProfile />
          : route.startsWith("#/documentation") ? <DocumentationPage route={route} />
          : route.startsWith("#/more") ? <EverythingElse />
          : route.startsWith("#/farm") ? <FarmPage route={route} />
          : route.startsWith("#/model-admin") ? <ModelAdmin route={route} />
          : route.startsWith("#/merge-requests") ? <MergeRequestsPage route={route} />
          : route.startsWith("#/archive") ? <ArchivePage />
          : route.startsWith("#/project-admin") ? <ProjectAdmin route={route} />
          : route.startsWith("#/project-library") ? <ProjectLibraryPage />
          : route.startsWith("#/principles") ? <PrinciplesPage />
          : route.startsWith("#/metamodel") ? <Metamodel route={route} />
          : route.startsWith("#/projects") ? <Projects route={route} />
          : route.startsWith("#/mcp") ? <Mcp />
          : route.startsWith("#/library") ? <Library route={route} />
          : route.startsWith("#/compare") ? <CompareScreen route={route} />
          : route.startsWith("#/change-log") ? <ChangeLog />
          : route.startsWith("#/notifications") ? <NotificationsPage route={route} />
          : route.startsWith("#/surveys") || route.startsWith("#/maturity") ? <SurveysPage route={route} />
          : route.startsWith("#/change-documents") ? <ChangeDocumentPage route={route} />
          : route.startsWith("#/admin") ? <Admin route={route} />
          : <StartPage />}
      </main>
      <QuickJump />
      <EntityMenu />
      <HelpPanel />
      <footer>
        Version {version || "?"} · build {(build && build.build) || "dev"} · {config.deployment} deployment · open source (AGPL-3.0)
      </footer>
    </div>
  );
}

// a part switched off in System settings (D329): its pages say so instead of loading
function partOff(route) {
  if (/^#\/(projects|project-admin)/.test(route) && !partOn("projects")) return "projects";
  if (route.startsWith("#/repository") && !partOn("repository")) return "repository";
  if (route.startsWith("#/reference-library") && !partOn("references")) return "references";
  if (route.startsWith("#/enterprise-library") && !partOn("projects")) return "projects";
  return "";
}

function PartOff({ part }) {
  const name = { projects: "Projects", repository: "The Repository", references: "References" }[part];
  return (
    <div className="page">
      <h1>{name} {part === "projects" ? "are" : "is"} switched off</h1>
      <p>This installation does not use {part === "repository" ? "the Architecture Repository" : part}. A Super Admin switches it on in{" "}
        <a href="#/admin/system">System admin › System settings</a>; everything it held is kept and comes back.</p>
      <p><a href="#/">Start page</a></p>
    </div>
  );
}

// R2.51 (D609): who is not held back by a test in progress: Super Admins and IT Admins (who see only the Self-test page
// meanwhile) and the test's own accounts (svc-self-test-*)
function testLockExempt(info) {
  const u = (info || {}).username || "";
  return u.startsWith("svc-self-test-") || roles().some((r) => r === "super-admin" || r === "it-admin");
}

// a normal person who signs in while a self-test runs waits here, and is let in when it ends (the heartbeat, every 20 s)
function TestInProgress({ run }) {
  return (
    <div className="page test-lock-page">
      <h1>Environment test in progress</h1>
      <p>EA Explorer is being tested (self-test {run.id}, started {String(run.since || "").slice(0, 16).replace("T", " ")} by {run.by}).
        You can sign in as soon as it ends: this page opens EA Explorer by itself then.</p>
      <p className="quiet small">{run.step || "Running"} · {run.done} checks so far</p>
    </div>
  );
}

// an admin while a self-test runs: only the Self-test page, so the test's data and timings are not disturbed
function TestOnlyPage() {
  return (
    <div className="page">
      <h1>Environment test in progress</h1>
      <p>While the self-test runs, only its page is open. <a href="#/admin/self-test">Open the Self-test page</a> to follow it
        and see its results; everything else comes back when it ends.</p>
    </div>
  );
}

// the release and its build at the top left (owner, 12 Nov 2026: "display version of application on top left - Release +
// build number", R2.47): "1.0.0 · build 4f2a9c1"; the tooltip has the full commit, when it was built and the channel
export function VersionTag({ version, build }) {
  const b = build || {};
  const tip = [`EA Explorer ${version}`, `build ${b.build || "dev"}`, b.commit && `commit ${b.commit}`,
    b.built_at && `built ${fmtDateTime(b.built_at)}`, b.channel && `channel ${b.channel}`].filter(Boolean).join("\n");
  return <span className="version-tag" title={tip} aria-label={tip}>{version} · build {b.build || "dev"}</span>;
}
