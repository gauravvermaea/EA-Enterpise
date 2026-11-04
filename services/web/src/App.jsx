import { useEffect, useState } from "react";
import { apiFetch, can, currentUser, isBreakGlass, keycloak, keycloakReachable, myInfo, roleName, roles, signedIn as isSignedIn, signOut, needsRole } from "./auth";
import BreakGlass from "./BreakGlass";
import Users from "./Users";
import { config } from "./config";
import StartPage from "./StartPage";
import Heartbeat from "./Heartbeat";
import Metamodel from "./Metamodel";
import Mcp from "./Mcp";
import Sql from "./Sql";
import Library from "./Library";
import ModelSwitcher from "./ModelSwitcher";
import { SearchPage, TopSearch } from "./GridPages";

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
  useEffect(() => {
    if (signedIn) apiFetch("/api/v1/heartbeat").then((b) => setVersion(b.version)).catch(() => {});
  }, [signedIn]);

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
          <a href="#/">Start</a>
          <a href="#/metamodel">Models</a>
          <a href="#/library">Library</a>
          <a href="#/mcp">MCP</a>
          <a href="#/heartbeat">Heartbeat</a>
          {can("system.operate") ? <a href="#/sql">SQL</a>
            : <span className="nav-off" title={needsRole(["it-admin", "super-admin"])}>SQL</span>}
          {can("users.read") ? <a href="#/users">Users</a>
            : <span className="nav-off" title={needsRole(["user-admin", "super-admin"])}>Users</span>}
          <a href="/api/docs">API</a>
        </nav>
        <TopSearch />
        <ModelSwitcher route={route} />
        <div className="user">
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
      </header>
      {isBreakGlass() && <div className="break-glass-banner">Break-glass session: everything you do is audited and the IT and Super Admins are alerted. Change the break-glass password afterwards.</div>}
      {signedIn && !isBreakGlass() && !roles().length && !(info?.models || []).length && (
        <div className="lock-banner">You have no role yet: you see nothing until a model's Model Admin gives you a role
          on a model, or a Keycloak Admin gives you a global role.</div>
      )}
      <main>
        {route.startsWith("#/search") ? <SearchPage key={route} route={route} />
          : route.startsWith("#/heartbeat") ? <Heartbeat />
          : route.startsWith("#/metamodel") ? <Metamodel route={route} />
          : route.startsWith("#/mcp") ? <Mcp />
          : route.startsWith("#/sql") ? <Sql />
          : route.startsWith("#/library") ? <Library route={route} />
          : route.startsWith("#/users") ? <Users route={route} />
          : <StartPage />}
      </main>
      <footer>
        Version {version || "?"} · {config.deployment} deployment · open source (AGPL-3.0)
      </footer>
    </div>
  );
}
