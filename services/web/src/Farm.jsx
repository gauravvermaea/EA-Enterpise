// Farm Admin (R2.0, D586): the place for the other EA Explorer sites (installations) this one knows and connects to.
// The screens come with R2.1 (farms of installations) and R2.2 (connecting to a remote instance), designed with the
// owner first; until then this page says what is coming and what can be done today. Super Admins only.
import { roles } from "./auth";

export default function FarmPage({ route }) {
  if (!roles().includes("super-admin")) {
    return <section className="page"><h1>Farm Admin</h1><p className="status bad">Farm Admin is for Super Admins.</p></section>;
  }
  const connect = route.startsWith("#/farm/connect");
  return (
    <section className="page farm-page">
      <h1>Farm Admin{connect ? " › Connect to a site" : " › Sites"}</h1>
      <p>Farm Admin is where a Super Admin manages the other EA Explorer sites: the installations this one knows, their versions and
        health, updates and deployments pushed to them, and connecting to one to work on it.</p>
      <div className="card">
        <h2>Coming in Release 2</h2>
        <ul>
          <li><strong>Sites</strong> (R2.1): every known installation in one list, with its version, channel and health.</li>
          <li><strong>Connect to a site</strong> (R2.2): pick a site at the top left (Local by default); you are asked for its credentials
            (single sign-on, keys, a certificate, or a user name and password); its own screens open, and its command line.</li>
        </ul>
        <p className="quiet small">Both are designed with the owner before they are built (docs/build-phases.md, R2.1 and R2.2).</p>
      </div>
      <h2>Today</h2>
      <ul>
        <li>Put EA Explorer on another laptop, server or cloud: <a href="#/admin/deploy">System Admin › Updates and deploy › Deploy</a>.</li>
        <li>Open another site: its own address in a new browser tab, signing in there.</li>
      </ul>
    </section>
  );
}
