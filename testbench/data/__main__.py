import sys

from . import manifest
from .build import build, check

cmd = (sys.argv[1:] or ["build"])[0]
if cmd == "build":
    w = build()
    print("Written: " + ", ".join(w) if w else "Every file was already as built.")
elif cmd == "check":
    bad = check()
    print("Every file is as built." if not bad else "Not as built (run python -m testbench.data build): " + ", ".join(bad))
    sys.exit(1 if bad else 0)
elif cmd == "list":
    for name, f in manifest()["files"].items():
        print(f"{name:<32}{f['bytes']:>8} bytes  {f['what']}\n{'':<42}used by: {'; '.join(f['used_by'])}")
else:
    print("python -m testbench.data build|check|list")
    sys.exit(2)
