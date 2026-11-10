# Release notes

One file per release: `<version>.md` (e.g. `0.19.0.md`), and `<version>-rc.<n>.md` for a release candidate that needs
its own (otherwise an RC shows its release's file). Written with `python tools/release.py notes <version>` and edited
by hand before the release is tagged (docs/release-process.md). Installations read the file at the tag when they offer
the version on System admin > Updates and `eax update`, and show it to everyone afterwards as What's new (D510).
