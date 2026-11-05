import { groups } from "./services";
import { config } from "./config";
import { can, needsRole, roleName, signedIn } from "./auth";
import { serviceOn } from "./fmt";

function Tile({ item }) {
  const allowed = !item.perm || can(item.perm);
  if (item.devOnly && config.deployment !== "laptop") return null;
  if (item.live && item.service && !serviceOn(item.service)) {
    return (
      <div className="tile off" aria-disabled="true" title="Switched off: Administration > System settings > Services">
        <h3>{item.name}</h3>
        <p>{item.text}</p>
        <span className="badge">switched off</span>
      </div>
    );
  }
  if (item.live && !allowed) {
    return (
      <div className="tile off" aria-disabled="true" title={needsRole(item.roles || [])}>
        <h3>{item.name}</h3>
        <p>{item.text}</p>
        <span className="badge">needs {(item.roles || []).map(roleName).join(" or ")}</span>
      </div>
    );
  }
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
      <span className="badge">{item.phase === "later" ? "agreed; phase to be set" : `coming in build phase ${item.phase}`}</span>
    </div>
  );
}

export default function StartPage() {
  return (
    <>
      <section className="intro">
        <h1>Start</h1>
        <p>
          Every part of EA Explorer is linked from here. Tiles in colour work now; the grey ones show what is
          coming and the build phase that delivers it.
          {!signedIn() && " Sign in once and every product opens without another login."}
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
