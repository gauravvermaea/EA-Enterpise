import { useEffect, useState } from "react";
import { keycloak, roles } from "./auth";
import { config } from "./config";
import StartPage from "./StartPage";
import Heartbeat from "./Heartbeat";
import Metamodel from "./Metamodel";
import Mcp from "./Mcp";
import Sql from "./Sql";

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
  const signedIn = keycloak.authenticated === true;
  const user = keycloak.tokenParsed;

  // Nothing of the application shows until the user has signed in.
  if (!signedIn) {
    return (
      <div className="signin">
        <div className="signin-card">
          <h1>EA Explorer</h1>
          <p className="quiet">Sign in to continue.</p>
          <button className="primary" onClick={() => keycloak.login()}>Sign in</button>
        </div>
      </div>
    );
  }

  return (
    <div className="shell">
      <header className="topbar">
        <a href="#/" className="brand">EA Explorer</a>
        <nav>
          <a href="#/">Start</a>
          <a href="#/metamodel">Models</a>
          <a href="#/mcp">MCP</a>
          <a href="#/heartbeat">Heartbeat</a>
          {roles().includes("system-admin") && <a href="#/sql">SQL</a>}
          <a href="/api/docs">API</a>
        </nav>
        <div className="user">
          {signedIn ? (
            <>
              <span title={roles().join(", ")}>{user?.name || user?.preferred_username}</span>
              <button onClick={() => keycloak.logout({ redirectUri: config.publicUrl })}>Sign out</button>
            </>
          ) : (
            <button className="primary" onClick={() => keycloak.login()}>Sign in</button>
          )}
        </div>
      </header>
      <main>
        {route.startsWith("#/heartbeat") ? <Heartbeat />
          : route.startsWith("#/metamodel") ? <Metamodel route={route} />
          : route.startsWith("#/mcp") ? <Mcp />
          : route.startsWith("#/sql") ? <Sql />
          : <StartPage />}
      </main>
      <footer>
        Version {config.version} · {config.deployment} deployment · open source (AGPL-3.0)
      </footer>
    </div>
  );
}
