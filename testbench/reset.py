"""The reset-survival test from outside (D561, D581): `--reset-survival --confirm <installation name>`.

The bench does not reset anything itself: it asks the platform to run its own test, through the Command centre's run
API (POST /api/v1/admin/commands/run, argv `test --reset-survival --confirm <name>`, with the strong confirm: the name
typed and "I understand"; Super Admins only). The platform writes its markers, runs the real `eax clean-restart`
(every database and the work folder deleted), waits to come back and checks its persist/ files byte for byte.

From here the bench then sees the platform go and come back (its public API description), and reads the platform's
own result (GET /api/v1/admin/commands/reset-survival). The reset deletes every account in the database, so the token
used before may be refused afterwards: give --token-after (or a Keycloak user, whose account Keycloak re-creates only
if it is the installation's first admin) to read the result; without one the bench says so and the result is on
System admin > Command centre."""

from __future__ import annotations

import time

from .target import Client, message


def run(run, client: Client, name: str, typed: str, token_after: str = "", wait_s: int = 1800, poll_s: int = 10,
        sleep=time.sleep, clock=time.time, client_of=Client) -> None:
    rec = run.recorder("reset-survival")
    if typed != name:
        rec("the strong confirm", "failed", f"--confirm must be the installation's name, {name!r}; nothing was reset", 0)
        return
    t0 = clock()
    s, a = client.post("/api/v1/admin/commands/run", {"argv": ["test", "--reset-survival", "--confirm", name],
                                                      "confirm": {"typed": typed, "understood": True}})
    if s not in (200, 202):
        rec("the platform's reset-survival test started", "failed", f"{s}: {message(a)}", 0)
        return
    rec("the platform's reset-survival test started", "passed", f"command run {a.get('id', '')}", 0)
    run.log("reset-survival: the platform is resetting itself (every database and the work folder); waiting")
    went, back = False, False
    while clock() - t0 < wait_s:
        s, _ = client_of(client.target).get("/api/openapi.json", timeout=15)
        if s != 200:
            went = True
        elif went:
            back = True
            break
        sleep(poll_s)
    rec("EA Explorer went down for the reset", "passed" if went else "warning",
        "" if went else "it never stopped answering while the bench watched (polled every few seconds)", 0)
    rec("EA Explorer answers again after the reset", "passed" if back else "failed",
        f"after {int(clock() - t0)} s" if back else f"not within {wait_s // 60} minutes", int((clock() - t0) * 1000))
    if not back and went:
        return
    after = client_of(client.target, token_after or client.token)
    for _ in range(60):                                   # the platform finishes its own checks after it is back
        s, a = after.get("/api/v1/admin/commands/reset-survival")
        if s in (401, 403):
            rec("the platform's result", "skipped", "the reset deleted the account behind the token; give --token-after "
                "<a token made after the reset>, or read it on System admin > Command centre", 0)
            return
        runs = (a.get("runs") or []) if isinstance(a, dict) else []
        latest = runs[0] if runs else {}
        if s == 200 and latest.get("state") in ("passed", "failed"):
            for c in latest.get("checks") or []:
                rec(c.get("name", ""), c.get("result", "failed"), c.get("note", ""), 0)
            rec("the platform's reset-survival test", latest["state"], f"run {latest.get('id', '')}", 0)
            return
        sleep(poll_s)
    rec("the platform's result", "failed", "the platform did not finish its checks within ten minutes of coming back", 0)
