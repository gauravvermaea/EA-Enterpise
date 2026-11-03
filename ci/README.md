# CI workflow

`github-actions-ci.yml` is the GitHub Actions workflow (API lint and tests, web build, compose
validation, image builds). It could not be written into `.github/workflows/` from outside your
computer, so move it there once:

```powershell
New-Item -ItemType Directory -Force .github\workflows | Out-Null
Move-Item ci\github-actions-ci.yml .github\workflows\ci.yml
```

The zip download already has it in `.github/workflows/ci.yml`.
