# The draw.io plugin's tests (test only: not in the image)

`tests.cjs` (Playwright) drives `test-host.html`, a page that stands in for EA Explorer's drawn-view screen, and checks
every message of the plugin (`../eax-plugin.js`; the protocol is in `docs/phase-28.md`, "As built: the plugin
protocol"): the stencil, placing and binding, lines (refused, asked, chosen from the stencil), Add a relationship, the
layout-only lock, box or shape, junctions, nesting, decoration palettes and lines (D414), a placeholder's type changed,
deleting a line (asked: hide, restore, removed; D413), hide and show, resync, the heat map, icons, placeholders, dropping
from the search panel, PNG and SVG export, File › Export as › .drawio file (D585; screenshot `export-as-menu.png`),
keepLook and plainLabels for pictures opened in draw.io, the saved file and read only. Run it again when draw.io is upgraded.

These files are kept out of the image (`../.dockerignore`). To run them:

1. Take draw.io's web app at the image's version: the `src/main/webapp` folder of the draw.io repository at the same
   tag as `DRAWIO_IMAGE` in `../Dockerfile` (e.g. `git clone --depth 1 --branch v32.6.10 https://github.com/jgraph/drawio`).
2. Put `../eax-plugin.js` there as `plugins/eax.js`, add the `<script src="plugins/eax.js"></script>` line before
   `</body>` in `index.html` (as the Dockerfile does), and copy `test-host.html` beside `index.html`.
3. Serve the folder (e.g. `python3 -m http.server 8771`) and run `node tests.cjs http://localhost:8771 <screenshot folder>`.
   It prints each check and ends with "N passed, 0 failed" (exit code 1 on any failure).

The owner tests drawn views in EA Explorer itself (a model's Views tab); there is no hand-test page in the image.
