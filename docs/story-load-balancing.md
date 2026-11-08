# Infrastructure story — Load balancing and scaling up and down (requested, for later)

Status: **an infrastructure story for production deployment (phase 36)** (owner, 8 Nov 2026; was phase 13.6, moved out of phase 13, D334). Not designed or built yet; discuss before building.

## The ask
Put the services behind a load balancer so that, **based on load, servers go up and down**: more copies of a service
when it is busy, fewer when it is quiet.

## Questions to settle when it is built
- Where it runs: the laptop install stays one copy of each; scaling is for a server install (Docker Swarm, Kubernetes,
  or a cloud's own container service). Which one(s) EA Explorer supports.
- What scales: the API (stateless: sessions are tokens) and the background job runner first; the web front end is static
  files. Keycloak, Mayan (Documents) and Superset each have their own rules for running several copies.
- The load balancer: the reverse proxy EA Explorer already has, or the platform's; health checks (the heartbeat).
- When to scale: CPU, memory, requests per second, the length of the background task queue; least and most copies;
  how fast to go up and down.
- What must be one at a time: database migrations and the start-up seed run once; periodic jobs (repository builds,
  backups) run on one runner only (queueing locks already do this).
- Files kept on local disk today (uploads waiting, task files, the TOGAF folder) move to shared storage.
- Fits with 13.7 (the database itself is mirrored, not scaled this way).
