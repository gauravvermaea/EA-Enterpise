import { useEffect, useState } from "react";
import { apiFetch, can, currentUser, isBreakGlass, keycloak, keycloakReachable, myInfo, roleName, roles, signedIn as isSignedIn, signOut } from "./auth";
import BreakGlass from "./BreakGlass";
import { config } from "./config";
import StartPage, { EverythingElse } from "./StartPage";
import { AreaMenu, ArchitectureWork } from "./Areas";
import ArchitectureRepositoryPage from "./ArchitectureRepository";
import ReferenceLibraryPage from "./ReferenceLibrary";
import ModelAdmin from "./ModelAdmin";
import Metamodel from "./Metamodel";
import Mcp from "./Mcp";
import Library from "./Library";
import CompareScreen from "./Versions";
import ChangeLog from "./ChangeLog";
import { TaskDrawer } from "./TaskDrawer";
import NotificationsPage, { Bell, ChangeDocumentPage } from "./Notifications";
import Admin from "./Admin";
import { serviceOn, setAppSettings } from "./fmt";
import { refreshAll } from "./ModelViews";
import ModelSwitcher, { ProjectSwitcher } from "./ModelSwitcher";
import { SearchPage, TopSearch } from "./GridPages";
import { RestoreLock, useRestoreLock } from "./Restores";
import StartupStatus from "./StartupStatus";
import Projects, { ProjectAdmin } from "./Projects";

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
  const user = currentUser();
  const [version, setVersion] = useState(null);  // the product version, from the API (version.toml)
  const [, setFormatsReady] = useState(0);        // re-render once the installation's formats are in
  const [maintenance, setMaintenance] = useState(null);   // a restore is running: read only (D216)
  useEffect(() => {
    if (signedIn) apiFetch("/api/v1/heartbeat").then((b) => { setVersion(b.version); setMaintenance(b.maintenance || null); }).catch(() => {});
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

  return (
    <div className="shell">
      <header className="topbar">
        <a href="#/" className="brand">EA Explorer</a>
        <nav>
          <AreaMenu route={route} />
        </nav>
        <TopSearch />
        <Bell route={route} />
        <div className="switchers">
          <ModelSwitcher route={route} />
          <ProjectSwitcher route={route} />
        </div>
        <div className="user">
          <div className="user-row">
          {signedIn ? (
            <>
              <span className={isBreakGlass() ? "break-glass-user" : ""}
                title={`EA Explorer roles: ${roles().join(", ") || "none"}${info?.keycloak_roles ? `\nKeycloak roles: ${info.keycloak_roles.join(", ")}` : ""}`}>
                {user?.name || user?.preferred_username}
                <small className="role-chip">{roles().length ? roles().map(roleName).join(", ") : "no role"}</small>
              </span>
              <button onClick={signOut}>Sign out</button>
            </>
          ) : (
            <button className="primary" onClick={() => keycloak.login()}>Sign in</button>
          )}
          </div>
          {/* what is still starting, under the sign-out so it never pushes the menu about */}
          <StartupStatus />
        </div>
        {/* every menu there was before the five areas, kept for those who use them (owner, 7 Nov 2026: nothing is taken away, D289) */}
        <nav className="subnav" aria-label="Menus">
          <a href="#/" className={route === "#/" || route === "#" ? "on" : ""}>Start</a>
          <a href="#/metamodel" className={route.startsWith("#/metamodel") ? "on" : ""}>Models</a>
          <a href="#/work" className={/^#\/(projects|work|project-admin)/.test(route) ? "on" : ""}>Projects</a>
          <a href="#/repository" className={route.startsWith("#/repository") ? "on" : ""}>Repository</a>
          <a href="#/library" className={route.startsWith("#/library") ? "on" : ""}>Library</a>
          <a href="#/reference-library" className={route.startsWith("#/reference-library") ? "on" : ""}>Reference library</a>
          <a href="#/compare" className={route === "#/compare" || route.startsWith("#/compare?") ? "on" : ""}>Compare</a>
          <a href="#/compare/gaps" className={route.startsWith("#/compare/gaps") ? "on" : ""}>Gap analysis</a>
          <a href="#/compare/common" className={route.startsWith("#/compare/common") ? "on" : ""}>Common analysis</a>
          <a href="#/change-log" className={route.startsWith("#/change-log") ? "on" : ""}>Change log</a>
          {serviceOn("mcp") ? <a href="#/mcp" className={route.startsWith("#/mcp") ? "on" : ""}>MCP</a>
            : <span className="nav-off" title="The MCP server is switched off (System admin > System settings > Services)">MCP</span>}
          <a href="#/admin" className={route.startsWith("#/admin") ? "on" : ""}>Administration</a>
          <a href="/api/docs">API</a>
        </nav>
      </header>
      {isBreakGlass() && <div className="break-glass-banner">Break-glass session: everything you do is audited and the IT and Super Admins are alerted. Change the break-glass password afterwards.</div>}
      {signedIn && !isBreakGlass() && !roles().length && !(info?.models || []).length && (
        <div className="lock-banner">You have no role yet: you see nothing until a model's Model Admin gives you a role
          on a model, or a Keycloak Admin gives you a global role.</div>
      )}
      {maintenance && <div className="break-glass-banner">EA Explorer is read only: {maintenance.what || "a restore is running"} (started by {maintenance.by}).
        Nothing can be changed until it is done; you will be asked to sign in again.</div>}
      {signedIn && <TaskDrawer />}
      <main>
        {route.startsWith("#/search") ? <SearchPage key={route} route={route} />
          : route.startsWith("#/work") ? <ArchitectureWork />
          : route.startsWith("#/repository") ? <ArchitectureRepositoryPage />
          : route.startsWith("#/reference-library") ? <ReferenceLibraryPage route={route} />
          : route.startsWith("#/more") ? <EverythingElse />
          : route.startsWith("#/model-admin") ? <ModelAdmin route={route} />
          : route.startsWith("#/project-admin") ? <ProjectAdmin route={route} />
          : route.startsWith("#/metamodel") ? <Metamodel route={route} />
          : route.startsWith("#/projects") ? <Projects route={route} />
          : route.startsWith("#/mcp") ? <Mcp />
          : route.startsWith("#/library") ? <Library route={route} />
          : route.startsWith("#/compare") ? <CompareScreen route={route} />
          : route.startsWith("#/change-log") ? <ChangeLog />
          : route.startsWith("#/notifications") ? <NotificationsPage route={route} />
          : route.startsWith("#/change-documents") ? <ChangeDocumentPage route={route} />
          : route.startsWith("#/admin") || route.startsWith("#/users") || route.startsWith("#/heartbeat") || route.startsWith("#/sql") ? <Admin route={route} />
          : <StartPage />}
      </main>
      <footer>
        Version {version || "?"} · {config.deployment} deployment · open source (AGPL-3.0)
      </footer>
    </div>
  );
}
