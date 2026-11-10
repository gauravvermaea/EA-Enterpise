<#
EA Explorer installer for Windows (phase 36, D502). Needs nothing but this file: it asks for the repository link and
the version, downloads EA Explorer from there (the release archive, no git needed; a shallow clone when git is
here), checks it, and then runs its deployment wizard (.\eax deploy).

  powershell -NoProfile -ExecutionPolicy Bypass -Command "iwr <repository's raw address>/eax-deploy.ps1 -OutFile eax-deploy.ps1; .\eax-deploy.ps1"

Options (each is asked when not given):
  -Repo URL        the repository link (the public git URL EA Explorer comes from)
  -Channel C       prod (release tags vX.Y.Z), rc (vX.Y.Z-rc.N) or latest (the main branch)
  -Version REF     a tag, branch or commit (instead of choosing from the channel)
  -Folder DIR      where to put it (default: eaexplorer in your user folder)
  -NoDeploy        download and check only; run .\eax deploy yourself later
  -WizardArgs ...  passed to the wizard, e.g. -WizardArgs "--web"
#>
param(
    [string]$Repo = $env:EAX_REPO,
    [string]$Channel = "",
    [string]$Version = "",
    [string]$Folder = $(if ($env:EAX_FOLDER) { $env:EAX_FOLDER } else { Join-Path $HOME "eaexplorer" }),
    [switch]$NoDeploy,
    [string[]]$WizardArgs = @()
)
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

function Ask([string]$Question, [string]$Default = "") {
    $a = Read-Host ($(if ($Default) { "$Question [$Default]" } else { $Question }))
    if ($a) { return $a.Trim() } else { return $Default }
}

Write-Host "EA Explorer installer: downloads EA Explorer and starts its deployment wizard." -ForegroundColor Cyan
if (-not $Repo) { $Repo = Ask "Repository link" "https://github.com/gauravvermaea/EA-Enterpise" }
if (-not $Repo) { Write-Host "A repository link is needed." -ForegroundColor Red; exit 2 }
$Repo = $Repo.TrimEnd("/")
if ($Repo.EndsWith(".git")) { $Repo = $Repo.Substring(0, $Repo.Length - 4) }
$git = if ($env:EAX_NO_GIT) { $null } else { Get-Command git -ErrorAction SilentlyContinue }

if (-not $Version) {
    if (-not $Channel) {
        Write-Host "Which channel?"
        Write-Host "  1  Prod     released versions (tags vX.Y.Z)   [default]"
        Write-Host "  2  RC       release candidates (vX.Y.Z-rc.N), for testing before a release"
        Write-Host "  3  Latest   the newest commit of main, for trying what is being built (not for production)"
        $Channel = switch (Ask "Choose" "1") { { $_ -in "2", "rc" } { "rc" } { $_ -in "3", "latest" } { "latest" } default { "prod" } }
    }
    if ($Channel -eq "latest") { $Version = "main" }
    else {
        $tags = @()
        try {
            if ($git) {
                $tags = @(& git ls-remote --tags --refs $Repo 2>$null | ForEach-Object { ($_ -split "refs/tags/")[-1] })
            } elseif ($Repo -match "github\.com[/:]([^/]+)/([^/]+)$") {
                $tags = @((Invoke-RestMethod "https://api.github.com/repos/$($Matches[1])/$($Matches[2])/tags?per_page=100") | ForEach-Object { $_.name })
            }
        } catch { $tags = @() }
        $pattern = if ($Channel -eq "rc") { '^v\d+\.\d+\.\d+-rc\.\d+$' } else { '^v\d+\.\d+\.\d+$' }
        $list = @($tags | Where-Object { $_ -match $pattern } |
            Sort-Object @{ Expression = { [version](($_ -replace '^v', '') -replace '-rc\.\d+$', '') } },
                        @{ Expression = { if ($_ -match 'rc\.(\d+)$') { [int]$Matches[1] } else { 0 } } } -Descending |
            Select-Object -First 10)
        if ($list.Count -gt 0) {
            Write-Host "Versions on $Channel (newest first):"
            for ($i = 0; $i -lt $list.Count; $i++) { Write-Host ("  {0}  {1}" -f ($i + 1), $list[$i]) }
            $pick = Ask "Choose (or type a tag)" "1"
            $Version = if ($pick -match '^\d+$' -and [int]$pick -ge 1 -and [int]$pick -le $list.Count) { $list[[int]$pick - 1] } else { $pick }
        } else {
            Write-Host "No $Channel versions could be listed (no git here, or not GitHub)." -ForegroundColor Yellow
            $Version = Ask "Type the version (a tag such as v0.19.0, or a branch)" $(if ($Channel -eq "rc") { "rc" } else { "release" })
        }
    }
}
if (-not $Version) { Write-Host "A version is needed." -ForegroundColor Red; exit 2 }
if (-not $Channel) { $Channel = if ($Version -match '-rc\.') { "rc" } elseif ($Version -match '^v\d') { "prod" } else { "latest" } }

if ((Test-Path $Folder) -and (Get-ChildItem -Force $Folder | Select-Object -First 1)) {
    if (Test-Path (Join-Path $Folder "eax.ps1")) {
        Write-Host "$Folder holds EA Explorer already. To move it to a newer version use its updates (.\eax update);" -ForegroundColor Yellow
        Write-Host "to deploy it again: cd $Folder; .\eax deploy" -ForegroundColor Yellow
    } else { Write-Host "$Folder is not empty: choose another folder with -Folder." -ForegroundColor Red }
    exit 1
}
New-Item -ItemType Directory -Force -Path $Folder | Out-Null

function Get-ArchiveUrl {
    if ($env:EAX_ARCHIVE_URL) { return $env:EAX_ARCHIVE_URL.Replace("{repo}", $Repo).Replace("{ref}", $Version) }
    if ($Repo -match '^(https?://|git@)github\.com[/:]([^/]+)/([^/]+)$') {
        $o = $Matches[2]; $n = $Matches[3]
        if ($Version -match '^[0-9a-f]{7,40}$') { return "https://github.com/$o/$n/archive/$Version.tar.gz" }
        if ($Version -match '^v\d') { return "https://github.com/$o/$n/archive/refs/tags/$Version.tar.gz" }
        return "https://github.com/$o/$n/archive/refs/heads/$Version.tar.gz"
    }
    if ($Repo -match '^(https?://|git@)gitlab\.com[/:]([^/]+)/([^/]+)$') {
        return "https://gitlab.com/$($Matches[2])/$($Matches[3])/-/archive/$Version/$($Matches[3])-$Version.tar.gz"
    }
    return ""
}

Write-Host "Downloading EA Explorer $Version from $Repo into $Folder ..."
if ($git -and -not $env:EAX_ARCHIVE_URL) {
    $method = "git clone --depth 1"
    & git clone --quiet --depth 1 --branch $Version $Repo $Folder 2>$null
    if ($LASTEXITCODE -ne 0) {
        & git -C $Folder init -q; & git -C $Folder remote add origin $Repo
        & git -C $Folder fetch -q --depth 1 origin $Version; & git -C $Folder checkout -q FETCH_HEAD
        if ($LASTEXITCODE -ne 0) { Write-Host "Could not get $Version from $Repo." -ForegroundColor Red; exit 1 }
    }
} else {
    $url = Get-ArchiveUrl
    if (-not $url) { Write-Host "Without git only GitHub and GitLab addresses can be downloaded (or set EAX_ARCHIVE_URL)." -ForegroundColor Red; exit 1 }
    $method = "archive $url"
    $tmp = Join-Path ([IO.Path]::GetTempPath()) "eaexplorer-$([guid]::NewGuid()).tar.gz"
    try {
        if ($url -like "file://*") { Copy-Item ([uri]$url).LocalPath $tmp } else { Invoke-WebRequest -Uri $url -OutFile $tmp -UseBasicParsing }
    } catch { Write-Host "Could not download $url ($($_.Exception.Message))" -ForegroundColor Red; exit 1 }
    # tar.exe is part of Windows 10 (1803) and later
    & tar -xzf $tmp -C $Folder --strip-components=1
    $code = $LASTEXITCODE
    Remove-Item $tmp -Force
    if ($code -ne 0) { Write-Host "Could not unpack the archive (tar exit $code)." -ForegroundColor Red; exit 1 }
}

foreach ($f in @("eax.ps1", "eax.cmd", "eaxpy.ps1", "docker-compose.yml", "eaxcli\deploy.py", "services\api\version.toml", "deploy\templates\eaexplorer.server.env")) {
    if (-not (Test-Path (Join-Path $Folder $f))) {
        Write-Host "The download does not look like EA Explorer ($f is missing): check the link and the version." -ForegroundColor Red; exit 1
    }
}
$ver = ((Get-Content (Join-Path $Folder "services\api\version.toml")) | Where-Object { $_ -match '^version = "(.*)"' } | Select-Object -First 1) -replace '^version = "(.*)"', '$1'
New-Item -ItemType Directory -Force -Path (Join-Path $Folder "work") | Out-Null
$info = [ordered]@{ repo = $Repo; channel = $Channel; ref = $Version; version = $ver; method = $method; installed_at = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ") }
[IO.File]::WriteAllText((Join-Path $Folder "work\install.json"), ($info | ConvertTo-Json -Compress), (New-Object Text.UTF8Encoding($false)))
Write-Host "EA Explorer $ver ($Version) is in $Folder." -ForegroundColor Green
if (-not $NoDeploy) {
    Set-Location $Folder
    & (Join-Path $Folder "eax.ps1") deploy @WizardArgs
    exit $LASTEXITCODE
}
Write-Host "Next: cd $Folder; .\eax deploy"
