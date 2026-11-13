// System Admin › Estate (R2.33; owner, 12 Nov 2026: "Logical and physical diagram with softwares, components physical
// network etc of estate"): the logical diagram (components and who calls whom) and the physical one of this
// installation as it runs (containers, images, networks, published ports, volumes and folders). Read only; a download
// as draw.io or SVG. The repository keeps the same, from docker-compose.yml, in docs/estate.md.
import { useState } from "react";
import { downloadDrawio, downloadPictureSvg, pictureSvg } from "./exporting";
import { useApi } from "./ModelViews";

export default function EstatePage() {
  const { data, error } = useApi("/api/v1/admin/estate");
  const [which, setWhich] = useState("logical");
  if (error) return <p className="status bad">{error}</p>;
  if (!data) return <p>Loading...</p>;
  const d = data[which];
  const svg = pictureSvg(d.nodes, d.edges);
  const title = `EA Explorer ${which}`;
  return (
    <div>
      <div className="row-gap">
        <div className="tabs small-tabs" role="tablist">
          {[["logical", "Logical"], ["physical", "Physical"]].map(([k, l]) => (
            <button key={k} role="tab" aria-selected={which === k} className={which === k ? "tab on" : "tab"} onClick={() => setWhich(k)}>{l}</button>))}
        </div>
        <button onClick={() => downloadDrawio(title, d.nodes, d.edges)}>Download draw.io</button>
        <button onClick={() => downloadPictureSvg(title, d.nodes, d.edges)}>Download SVG</button>
      </div>
      <p className="quiet small">{which === "logical" ? "The components and who calls whom." :
        `This installation as it runs: ${data.containers.length} containers, the Docker networks they are on, what is published on the host, and the volumes and folders they use.`}</p>
      <div className="estate-picture"><img alt={`${title} diagram`} src={`data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg.text)}`} /></div>
    </div>
  );
}
