# CI workflow

`github-actions-ci.yml` is the GitHub Actions workflow (API lint and tests, web build, compose
validation, image builds). It could not be written into `.github/workflows/` from outside your
computer, so move it there once:

```powershell
New-Item -ItemType Directory -Force .github\workflows | Out-Null
Move-Item ci\github-actions-ci.yml .github\workflows\ci.yml
```

The zip download already has it in `.github/workflows/ci.yml`.

## The test bench (D579 to D582)

The **Test bench** job runs `python -m testbench` against EA Explorer started on the runner: the API and UI suites on
every change; nightly (02:17) a clean install with the deploy wizard (`testbench-answers.json`), every browser, a short
load test with k6 and an upgrade from the previous tag. Its reports (HTML, JSON, JUnit) are kept as the
`testbench-reports` artifact. See [docs/testbench.md](../docs/testbench.md).
