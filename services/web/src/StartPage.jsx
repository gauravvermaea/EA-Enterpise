import { groups } from "./services";
import { config } from "./config";
import { can, needsRole, roleName, signedIn } from "./auth";
import { serviceOn } from "./fmt";
import { useApi } from "./ModelViews";
import { AreaTiles } from "./Areas";
import { FirstRunPanel } from "./GuidedWizards";

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

// Before the first architecture project: one highlighted tile to the template library setup (D264)
function ProjectSetupTile() {
  const { data } = useApi(signedIn() ? "/api/v1/projects" : null);
  if (!data || data.setup?.done) return null;
  return (
    <section>
      <h2>Get started</h2>
      <div className="grid">
        <a className="tile live setup-tile" href={data.may_manage ? "#/project-admin/library" : "#/work"}>
          <h3>Set up architecture projects</h3>
          <p>{data.may_manage
            ? "Choose the template libraries projects start from: EA Explorer's own, TOGAF 10 (upload its zip) and your own. Needed before the first project."
            : "A Super Admin chooses the template libraries first; then you can create architecture projects."}</p>
          <span className="badge">{data.may_manage ? "to do: template library setup →" : "waiting for a Super Admin"}</span>
        </a>
      </div>
    </section>
  );
}

// The start page (D285): the five areas
export default function StartPage() {
  return (
    <>
      <section className="intro">
        <h1>Start</h1>
        <p>Choose where to work. Admin work (setting up and changing models, projects and the system) is done by wizards;
          architecture work is done on the model and project pages.
          {!signedIn() && " Sign in once and every product opens without another login."}</p>
      </section>
      <FirstRunPanel />
      <ProjectSetupTile />
      <AreaTiles />
    </>
  );
}

// Everything else (#/more, D285): the screens that belong to no area, and every product and what is coming
const MORE = [
  { name: "Search", text: "Search every model you may open", href: "#/search", live: true },
  { name: "Notifications", text: "What happened on your models and projects, requests, and your background tasks", href: "#/notifications", live: true },
  { name: "Change log", text: "Every change across the models, with who and when, and its export", href: "#/change-log", live: true },
  { name: "Model library", text: "Browse the root metamodels and reference models", href: "#/library", live: true },
  { name: "MCP", service: "mcp", text: "Connect your own language model to the repository", href: "#/mcp", live: true },
  { name: "API", text: "The REST API and its documentation", href: "/api/docs", live: true },
];

export function EverythingElse() {
  return (
    <>
      <section className="intro">
        <h1>Everything else</h1>
        <p>Tiles in colour work now; the grey ones show what is coming and the build phase that delivers it.</p>
      </section>
      <section>
        <div className="grid">{MORE.map((item) => <Tile key={item.name} item={item} />)}</div>
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
