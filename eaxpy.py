"""EA Explorer helper in Python (phase 13.9, D331). Run it through the launcher (eaxpy.cmd / eaxpy.ps1 on Windows,
eaxpy.sh on Linux and macOS), which fetches uv and the right Python the first time. Usage: eaxpy <command>; eaxpy help."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from eaxcli.main import main

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
