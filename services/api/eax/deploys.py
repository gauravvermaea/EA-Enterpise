"""Deploying EA Explorer elsewhere from System admin > Deploy (phase 36, D555 to D557): the history of deployment
targets, copied into operations.deployments from the operations helper's runs (services/ops/deploys.py). Secrets never
reach the API: the SSH key and cloud credentials go straight through to the helper, which keeps them only for the run
(or, when asked, in its own store, never shown again)."""

from __future__ import annotations

from sqlalchemy import text

from . import databases

STATUSES = ("running", "failed", "done", "planned", "quit", "back")
SECRET_FIELDS = ("aws_access_key_id", "aws_secret_access_key", "do_token", "spaces_key", "spaces_secret",
                 "az_client_id", "az_client_secret", "az_tenant", "ssh_key")


def _row(r: dict) -> dict:
    res = r.get("result") or {}
    return {"run_id": str(r.get("id") or ""), "target": str(r.get("target") or "")[:200], "kind": r.get("kind") or "server",
            "plan": bool(r.get("plan")), "version": str(r.get("version") or ""),
            "status": r.get("status") if r.get("status") in STATUSES else "running",
            "started_by": str(r.get("by") or ""), "started_at": r.get("started"), "finished_at": r.get("finished"),
            "address": str(res.get("public_ip") or res.get("ssh_target") or ""),
            "failed_step": str((r.get("failed") or {}).get("step") or ""), "kept": bool(r.get("keep"))}


def sync(conn, runs: list[dict]) -> int:
    n = 0
    for r in runs:
        row = _row(r)
        if not row["run_id"] or row["kind"] not in ("server", "aws", "azure", "digitalocean"):
            continue
        databases.on("operations", conn).execute(text("""
            INSERT INTO operations.deployments (run_id, target, kind, plan, version, status, started_by, started_at, finished_at,
                                          address, failed_step, kept_credentials)
            VALUES (:run_id, :target, :kind, :plan, :version, :status, :started_by, COALESCE(CAST(:started_at AS timestamptz), now()),
                    CAST(:finished_at AS timestamptz), :address, :failed_step, :kept)
            ON CONFLICT (run_id) DO UPDATE SET status = EXCLUDED.status, finished_at = EXCLUDED.finished_at,
                address = EXCLUDED.address, failed_step = EXCLUDED.failed_step, recorded_at = now()
            WHERE (operations.deployments.status, operations.deployments.finished_at, operations.deployments.address)
                  IS DISTINCT FROM (EXCLUDED.status, EXCLUDED.finished_at, EXCLUDED.address)"""), row)
        n += 1
    if n:
        try:                                     # a finished deployment's site goes into the sites list (R2.1, D646)
            from . import sites
            sites.from_deployments(conn, history(conn))
        except Exception:  # noqa: BLE001 - the sites job adds it within 5 minutes anyway
            pass
    return n


def history(conn, limit: int = 200) -> list[dict]:
    rows = databases.on("operations", conn).execute(text("""SELECT run_id, target, kind, plan, version, status, started_by, started_at, finished_at, address,
                                       failed_step, kept_credentials FROM operations.deployments
                                 ORDER BY started_at DESC LIMIT :n"""), {"n": limit}).mappings().all()
    return [dict(r) for r in rows]


def targets(rows: list[dict]) -> list[dict]:
    """Every target deployed to (not plans): its latest deployment, how many there were."""
    out: dict[str, dict] = {}
    for r in rows:
        if r.get("plan"):
            continue
        t = out.setdefault(r["target"], {**r, "deployments": 0})
        t["deployments"] += 1
    return list(out.values())


def clean_body(data: dict, user: str) -> dict:
    """What the page sends, as the helper takes it: answers without secrets, secrets apart, who started it."""
    answers = {k: str(v) for k, v in (data.get("answers") or {}).items() if k not in SECRET_FIELDS and v is not None}
    secrets = {k: str(v) for k, v in (data.get("secrets") or {}).items() if k in SECRET_FIELDS and v}
    for k in SECRET_FIELDS:                      # a secret typed among the answers moves to the secrets
        v = (data.get("answers") or {}).get(k)
        if v and k != "ssh_key":
            secrets.setdefault(k, str(v))
    return {"answers": answers, "secrets": secrets, "ssh_key": str(data.get("ssh_key") or ""),
            "keep": bool(data.get("keep")), "plan": bool(data.get("plan")), "use_kept": str(data.get("use_kept") or ""),
            "by": user}
