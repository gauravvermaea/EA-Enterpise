import { groups } from "./services";
import { config } from "./config";
import { keycloak, roles } from "./auth";

function Tile({ item }) {
  const allowed = !item.role || roles().includes(item.role);
  if (item.devOnly && config.deployment !== "laptop") return null;
  if (!allowed) return null;
  if (item.live) {
    const external = item.href.startsWith("http");
    return (
      <a className="tile live" href={item.href} target={external ? "_blank" : undefined} rel="noreferrer">
        <h3>{item.name}</h3>
        <p>{item.text}</p>
        {item.badge && <span className="badge">{item.badge}</span>}
        {item.integration && <span className="badge">{item.name === "Metamodel" ? `read only; editing in phase ${item.integration}` : `running; repository link in phase ${item.integration}`}</span>}
      </a>
    );
  }
  return (
    <div className="tile placeholder" aria-disabled="true">
      <h3>{item.name}</h3>
      <p>{item.text}</p>
      <span className="badge">arrives in build phase {item.phase}</span>
    </div>
  );
}

export default function StartPage() {
  return (
    <>
      <section className="intro">
        <h1>Start</h1>
        <p>
          Every part of EA Explorer is linked from here. Tiles in colour work now; the others show
          the build phase that delivers them.
          {!keycloak.authenticated && " Sign in once and every product opens without another login."}
        </p>
      </section>
      {groups.map((g) => (
        <section key={g.title}>
          <h2>{g.title}</h2>
          <div className="grid">
            {g.items.map((item) => <Tile key={item.name} item={item} />)}
          </div>
        </section>
      ))}
    </>
  );
}
