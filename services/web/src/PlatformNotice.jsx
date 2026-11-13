// On a Docker platform that runs the containers itself (Swarm or another orchestrator; EAX_PLATFORM=managed, R2.44, D635)
// there is no Docker socket: the operations helper does not run, so the Command centre and the Containers page say the
// platform manages the containers and show the commands to use there instead.
import { useEffect, useState } from "react";
import { apiFetch } from "./auth";

let cached = null;

export default function PlatformNotice() {
  const [b, setB] = useState(cached);
  useEffect(() => {
    if (cached) return;
    apiFetch("/api/v1/heartbeat").then((x) => { cached = x; setB(x); }).catch(() => {});
  }, []);
  if (!b || b.platform !== "managed") return null;
  return (
    <div className="card platform-notice">
      <h2>The platform manages the containers</h2>
      <p>EA Explorer runs on a container platform here (EAX_PLATFORM=managed): there is no Docker socket, so starting, stopping and
        scaling the containers, their logs and terminals are done with the platform's own tools. For example, on Docker Swarm:</p>
      <pre className="small">{`docker service ls                          # the services and how many of each run
docker service ps <stack>_api              # where each copy of the API runs
docker service logs -f <stack>_api         # an API's log
docker service scale <stack>_api=3         # three copies of the API
docker service update --force <stack>_api  # restart the API's copies one by one`}</pre>
      <p className="quiet small">Self-test runs go to the always-on test runner service; files go to the {b.file_store === "database" ? "file store in the database" : "work folder"} (EAX_FILE_STORE).</p>
    </div>
  );
}
