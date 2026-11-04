<#
EA Explorer helper for Windows (PowerShell 5.1 or 7). Linux and macOS: use eax.sh.
Run  .\eax help  for every command.

The script is not signed. Either use the launcher, which bypasses the execution policy for this run only:
    .\eax up
or call PowerShell with the bypass yourself:
    powershell -NoProfile -ExecutionPolicy Bypass -File .\eax.ps1 up

Everything local lives in the work folder, which is never committed: the config file
(work\eaexplorer.env), the logs (work\logs) and laptop data (work\data: backups, imports, exports, tls).
#>
# No param() block on purpose: options such as --all, --yes and --scratch must reach the script as
# plain text, and an advanced-script parameter block would reject them as unknown parameters.
$Command = if ($args.Count -gt 0) { [string]$args[0] } else { "help" }
$Rest = @($args | Select-Object -Skip 1 | ForEach-Object { [string]$_ })
$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot
$WorkDir = Join-Path $PSScriptRoot "work"
$EnvFile = "work/eaexplorer.env"
$LogDir = Join-Path $WorkDir "logs"
$Stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$RestArgs = @($Rest | Where-Object { $_ })   # extra arguments, without empty entries
$script:Log = $null          # StreamWriter for this run's log
$script:LogPath = $null
$Utf8 = New-Object System.Text.UTF8Encoding $false

# ------------------------------------------------------------------ logging
function Open-Writer([string]$Path) {
    $w = New-Object System.IO.StreamWriter($Path, $true, $Utf8)
    $w.AutoFlush = $true
    return $w
}

function Start-Log([string]$Name) {
    New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
    # keep two weeks of logs
    Get-ChildItem -Path $LogDir -Filter "*.log" -ErrorAction SilentlyContinue |
        Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-14) } | Remove-Item -Force -ErrorAction SilentlyContinue
    $script:LogPath = Join-Path $LogDir "eax-$Stamp-$Name.log"
    $script:Log = Open-Writer $script:LogPath
    $script:Log.WriteLine("=== eax $Name $($Rest -join ' ')   $(Get-Date -Format o)")
    $script:Log.WriteLine("=== folder $PSScriptRoot   PowerShell $($PSVersionTable.PSVersion)   $([Environment]::OSVersion.VersionString)")
    Write-Host "Log: $script:LogPath" -ForegroundColor DarkGray
}

function Stop-Log {
    if ($script:Log) { $script:Log.WriteLine("=== end $(Get-Date -Format o)"); $script:Log.Dispose(); $script:Log = $null }
}

function Write-Log([string]$Text = "", [string]$Color = "") {
    if ($Color) { Write-Host $Text -ForegroundColor $Color } else { Write-Host $Text }
    if ($script:Log) { $script:Log.WriteLine($Text) }
}

# Masks passwords, secrets and keys before config or container output reaches a log
function Hide-Secrets([string]$Line) {
    $Line = $Line -replace '((?:PASSWORD|SECRET|_KEY|URLENC)[A-Z_]*\s*[:=]\s*).*$', '$1****'
    $Line = $Line -replace '(redis://:)[^@]+@', '$1****@'
    $Line = $Line -replace '("PASSWORD"\s*:\s*")[^"]*"', '$1****"'
    return $Line
}

# Runs a program; every output line goes to the console (unless -Quiet) and to the log.
function Invoke-Logged([string]$Exe, [string[]]$Arguments, [switch]$Quiet, [switch]$Mask) {
    if ($script:Log) { $script:Log.WriteLine(""); $script:Log.WriteLine("> $Exe $($Arguments -join ' ')") }
    $old = $ErrorActionPreference; $ErrorActionPreference = "Continue"
    try {
        & $Exe @Arguments 2>&1 | ForEach-Object {
            $line = if ($_ -is [System.Management.Automation.ErrorRecord]) { $_.Exception.Message } else { "$_" }
            if ($Mask) { $line = Hide-Secrets $line }
            if (-not $Quiet) { Write-Host $line }
            if ($script:Log) { $script:Log.WriteLine($line) }
        }
        $code = $LASTEXITCODE
    } finally { $ErrorActionPreference = $old }
    if ($script:Log) { $script:Log.WriteLine("< exit $code") }
    return $code
}

# ------------------------------------------------------------------ settings and compose
function Get-Setting([string]$Name, [string]$Default = "") {
    if (-not (Test-Path $EnvFile)) { return $Default }
    $line = Get-Content $EnvFile | Where-Object { $_ -match "^$Name=" } | Select-Object -First 1
    if (-not $line) { return $Default }
    $v = ($line -split "=", 2)[1].Trim()
    # strip surrounding single or double quotes
    if ($v.Length -ge 2 -and (($v.StartsWith("'") -and $v.EndsWith("'")) -or ($v.StartsWith('"') -and $v.EndsWith('"')))) { $v = $v.Substring(1, $v.Length - 2) }
    if ($v -eq "") { return $Default } else { return $v }
}

function Get-ComposeArgs([string[]]$Arguments) {
    if (-not (Test-Path $EnvFile)) { throw "No $EnvFile yet: run .\eax init first." }
    $kind = Get-Setting "EAX_DEPLOYMENT" "laptop"
    # plain progress and no colour codes, so the log reads cleanly
    return @("compose", "--ansi", "never", "--progress", "plain", "--env-file", $EnvFile,
             "-f", "docker-compose.yml", "-f", "deploy/compose/docker-compose.$kind.yml") + $Arguments
}

function Invoke-Compose([string[]]$Arguments, [switch]$NoThrow, [switch]$Quiet) {
    $code = Invoke-Logged "docker" (Get-ComposeArgs $Arguments) -Quiet:$Quiet
    if ($code -ne 0 -and -not $NoThrow) {
        Write-Log "docker compose failed (exit $code). Collecting diagnostics..." "Red"
        Save-Diagnostics
        throw "docker compose failed (exit $code). Full log with diagnostics: $script:LogPath"
    }
    return $code
}

# Versions, containers, images, every container's recent log and the (masked) config, into the log
function Save-Diagnostics {
    Write-Log ""
    Write-Log "==================== DIAGNOSTICS $(Get-Date -Format o) ===================="
    Invoke-Logged "docker" @("version") -Quiet | Out-Null
    Invoke-Logged "docker" @("compose", "version") -Quiet | Out-Null
    Invoke-Logged "docker" @("info", "--format", "CPUs {{.NCPU}}  Memory {{.MemTotal}}  Storage {{.Driver}}  OS {{.OperatingSystem}}") -Quiet | Out-Null
    Invoke-Logged "docker" @("system", "df") -Quiet | Out-Null
    if (Test-Path $EnvFile) {
        if ($script:Log) {
            $script:Log.WriteLine(""); $script:Log.WriteLine("> settings in $EnvFile (images, site, deployment)")
            Get-Content $EnvFile | Where-Object { $_ -match "^EAX_(IMAGE_|DEPLOYMENT|HOSTNAME|HTTPS?_PORT|VERSION)|^COMPOSE_" } | ForEach-Object { $script:Log.WriteLine($_) }
        }
        Invoke-Logged "docker" (Get-ComposeArgs @("ps", "-a")) -Quiet | Out-Null
        Invoke-Logged "docker" (Get-ComposeArgs @("images")) -Quiet | Out-Null
        $old = $ErrorActionPreference; $ErrorActionPreference = "Continue"
        $services = & docker @(Get-ComposeArgs @("config", "--services")) 2>$null
        $ErrorActionPreference = $old
        foreach ($s in $services) {
            if ($s) { Invoke-Logged "docker" (Get-ComposeArgs @("logs", "--no-color", "--timestamps", "--tail", "300", $s)) -Quiet -Mask | Out-Null }
        }
        Invoke-Logged "docker" (Get-ComposeArgs @("config")) -Quiet -Mask | Out-Null
    } else {
        Write-Log "No ${EnvFile}: run .\eax init first."
    }
    Write-Log "==================== END DIAGNOSTICS ===================="
    Write-Log "Diagnostics saved in $script:LogPath" "Yellow"
}

# ------------------------------------------------------------------ output helpers
function Show-Urls {
    $h = Get-Setting "EAX_HOSTNAME" "localhost"; $p = Get-Setting "EAX_HTTPS_PORT" "443"
    $s = if ($p -eq "443") { "" } else { ":$p" }
    Write-Log "Start page:  https://$h$s/"
    Write-Log "Swagger:     https://$h$s/api/docs"
    Write-Log "Reports:     https://reports.$h$s/"
    Write-Log "Documents:   https://docs.$h$s/"
    Write-Log "Keycloak:    https://$h$s/auth/admin/"
    if ((Get-Setting "EAX_MCP_ENABLED" "false") -eq "true") { Write-Log "MCP server:  https://$h$s/mcp  (laptop: http://localhost:8001/mcp)" }
}

function Show-Logins {
    if ((Get-Setting "EAX_DEPLOYMENT" "laptop") -ne "laptop") {
        Write-Log "Logins are only printed for a laptop (development) installation. See $EnvFile."
        return
    }
    $rows = @(
        @("EA Explorer (Keycloak realm)",     (Get-Setting "EAX_FIRST_ADMIN_USER" "eaadmin"), (Get-Setting "EAX_FIRST_ADMIN_PASSWORD"),    "start page sign-in; Superset and Mayan via SSO"),
        @("Keycloak administrator",           (Get-Setting "EAX_KC_ADMIN" "kcadmin"),         (Get-Setting "EAX_KC_ADMIN_PASSWORD"),       "/auth/admin/ (master realm)"),
        @("Superset break-glass admin",       "admin",                                        (Get-Setting "EAX_SUPERSET_ADMIN_PASSWORD"), "only when EAX_SUPERSET_AUTH=db"),
        @("Mayan EDMS administrator",         (Get-Setting "EAX_MAYAN_ADMIN_USER" "admin"),   (Get-Setting "EAX_MAYAN_ADMIN_PASSWORD"),    "local Mayan account"),
        @("PostgreSQL superuser",             "postgres",                                     (Get-Setting "EAX_DB_SUPERUSER_PASSWORD"),   "docker compose exec db psql -U postgres"),
        @("PostgreSQL EA Explorer",           "eax_app",                                      (Get-Setting "EAX_DB_PASSWORD"),             "database $(Get-Setting 'EAX_DB_NAME' 'eaexplorer')"),
        @("PostgreSQL reporting (read only)", "eax_report",                                   (Get-Setting "EAX_DB_REPORT_PASSWORD"),      "schema rpt"),
        @("PostgreSQL installer",             "eax_migrator",                                 (Get-Setting "EAX_DB_MIGRATOR_PASSWORD"),    "loads reference models only"),
        @("PostgreSQL Keycloak",              "keycloak",                                     (Get-Setting "EAX_KEYCLOAK_DB_PASSWORD"),    "database keycloak"),
        @("PostgreSQL Superset",              "superset",                                     (Get-Setting "EAX_SUPERSET_DB_PASSWORD"),    "database superset"),
        @("PostgreSQL Mayan",                 "mayan",                                        (Get-Setting "EAX_MAYAN_DB_PASSWORD"),       "database mayan"),
        @("Mayan broker (Valkey)",            "(none)",                                       (Get-Setting "EAX_DMS_BROKER_PASSWORD"),     "password only"),
        @("MCP server (development token)",   "(bearer)",                                     (Get-Setting "EAX_MCP_DEV_TOKEN"),           "http://localhost:8001/mcp"),
        @("Keycloak client secrets",          "superset/mayan",                               (Get-Setting "EAX_SUPERSET_OIDC_SECRET"),    "OIDC clients")
    )
    Write-Log ""
    Write-Log "================ DEVELOPMENT LOGINS (laptop only - never use these on a server) ================" "Yellow"
    Write-Log ("{0,-34} {1,-14} {2,-16} {3}" -f "Account", "User", "Password", "Notes")
    foreach ($r in $rows) { Write-Log ("{0,-34} {1,-14} {2,-16} {3}" -f $r[0], $r[1], $r[2], $r[3]) }
    Write-Log "=================================================================================================" "Yellow"
}

# After starting only some services: where to reach them directly (laptop)
function Show-PartUrls([string[]]$Services) {
    Write-Log ""
    Write-Log "Started: $($Services -join ', ') (and what they depend on). The rest stays stopped."
    if ($Services -contains "api") {
        Write-Log "API directly (laptop, no proxy or sign-in needed for public endpoints):"
        Write-Log "  Swagger:    http://localhost:8000/api/docs"
        Write-Log "  Heartbeat:  http://localhost:8000/api/v1/heartbeat"
    }
    Write-Log "Stop everything with .\eax down"
}

# Follows every container's log into logs\containers-<stamp>.log (and the console) until Ctrl+C
function Watch-Containers([string[]]$Services = @()) {
    $path = Join-Path $LogDir "containers-$Stamp.log"
    Write-Log ""
    Write-Log "Recording every container's log to $path" "Yellow"
    Write-Log "Leave this window open while you test; press Ctrl+C to stop recording (the containers keep running)." "Yellow"
    $w = Open-Writer $path
    $old = $ErrorActionPreference; $ErrorActionPreference = "Continue"
    try {
        & docker @(Get-ComposeArgs (@("logs", "-f", "--no-color", "--timestamps", "--tail", "500") + $Services)) 2>&1 | ForEach-Object {
            $raw = if ($_ -is [System.Management.Automation.ErrorRecord]) { $_.Exception.Message } else { "$_" }
            $line = Hide-Secrets $raw
            Write-Host $line
            $w.WriteLine($line)
        }
    } finally { $ErrorActionPreference = $old; $w.Dispose() }
}

# Stops early with a plain message when the Docker engine is not reachable
function Assert-Docker {
    $old = $ErrorActionPreference; $ErrorActionPreference = "Continue"
    & docker info --format "{{.ServerVersion}}" 2>&1 | Out-Null
    $ok = ($LASTEXITCODE -eq 0)
    $ErrorActionPreference = $old
    if (-not $ok) {
        throw "Docker Desktop is not running (or still starting). Start Docker Desktop, wait until it shows 'Engine running', check with: docker version (it must show a Server section), then run this again."
    }
}

# ------------------------------------------------------------------ help
$HelpText = @'
EA Explorer helper. Usage: .\eax <command> [options]
(.\eax is the launcher; the long form is: powershell -NoProfile -ExecutionPolicy Bypass -File .\eax <command>)

Getting started
  init [laptop|server]  Creates work\eaexplorer.env from the template for the deployment kind
                        (laptop if not given) and the work folders. Nothing is generated: on a
                        laptop every password is P^55w0rd1234&; on a server, replace every change-me
                        value before starting. Refuses to overwrite an existing config file.
  check                 Checks that Docker Desktop is running and that the config file and compose
                        files are valid. Starts nothing.
  up [service...]       Builds our images, pulls the others, and starts every container in the
                        background. Then prints the addresses and (laptop) the logins.
                        Name services to start only those and what they depend on, for example
                        "up api" starts the API and PostgreSQL only (needs about 1 GB). On a laptop
                        the API is then at http://localhost:8000/api/docs.

Finding problems
  debug [service...]    Same as up, but does not stop on failure: it saves a diagnostics report and
                        then keeps recording the containers' output to
                        work\logs\containers-<date-time>.log until you press Ctrl+C.
                        The containers keep running after Ctrl+C. "debug api" starts and records
                        the API (and PostgreSQL) only.
  diag                  Saves a diagnostics report into this run's log: Docker versions, memory and
                        disk, image settings, every container's state, the last 300 log lines of
                        each container, and the compose configuration (passwords masked).
  status                Lists every container with its state and health, including stopped ones.
  logs [service]        Follows the logs of every container, or of one (for example: logs api).
                        Ctrl+C to stop.

Everyday use
  url                   Prints the addresses to open (and the logins on a laptop).
  logins                Prints every user name and password (laptop only).
  down                  Stops and removes the containers. Data in Docker volumes and in work\ is kept.
  backup                Takes a backup now into work\data\backups (laptop) or EAX_BACKUP_DIR.
  restore <folder> [--scratch]
                        Restores a backup folder: into the live databases, or with --scratch into
                        a separate scratch database to inspect first.

Starting again
  cleanup [--all] [--yes]
                        Stops the containers and deletes everything in the work folder: the config
                        file, logs and laptop data folders (including backups). With --all it also
                        deletes the Docker volumes, so the databases and documents start empty.
                        Asks you to type yes unless --yes is given. Run init afterwards.
  clean-run [laptop|server]
                        Starts again from scratch in one step: cleanup --all --yes, then init
                        (laptop if not given), then up. Deletes the databases and everything in
                        the work folder without asking.
  clean-debug [laptop|server]
                        The same, but ends with debug instead of up (keeps recording the
                        containers' output until Ctrl+C).

  help [command]        This text, or the part about one command.

Logs: every command except help and cleanup writes its full output to
work\logs\eax-<date-time>-<command>.log. When a Docker step fails, a diagnostics report is added to
that log automatically, so the log file is all you need to send when something goes wrong.
'@

function Show-Help([string]$Name) {
    if (-not $Name) { Write-Host $HelpText; return }
    $show = $false
    foreach ($line in ($HelpText -split "`r?`n")) {
        if ($line -match '^  ([a-z-]+)') { $show = ($Matches[1] -eq $Name) }
        elseif ($line -notmatch '^ {24}') { $show = $false }
        if ($show) { Write-Host $line }
    }
}

# Stops the containers and empties the work folder (no log: the logs folder is being deleted)
function Invoke-Cleanup([string[]]$Options) {
    $all = $false; $yes = $false
    foreach ($o in $Options) {
        switch ($o) { "--all" { $all = $true } "--yes" { $yes = $true } "-y" { $yes = $true } default { throw "Unknown option $o" } }
    }
    Write-Host "This deletes everything in ${WorkDir}: the config file, all logs and the laptop data folders (including backups)." -ForegroundColor Yellow
    if ($all) { Write-Host "With --all it also deletes the Docker volumes: the databases and documents start empty." -ForegroundColor Yellow }
    if (-not $yes) {
        $answer = Read-Host "Type yes to continue"
        if ($answer -ne "yes") { Write-Host "Nothing deleted."; return }
    }
    if (Test-Path $EnvFile) {
        $down = if ($all) { @("down", "-v", "--remove-orphans") } else { @("down", "--remove-orphans") }
        Invoke-Logged "docker" (Get-ComposeArgs $down) | Out-Null
    } elseif ($all) {
        Write-Host "No $EnvFile, so the Docker volumes cannot be found by name; list them with: docker volume ls"
    }
    if (Test-Path $WorkDir) { Get-ChildItem -Path $WorkDir -Force | Remove-Item -Recurse -Force }
    Write-Host "The work folder is empty. Run .\eax init laptop to start again."
}

# ------------------------------------------------------------------ commands
if ($Command -in @("help", "-h", "--help", "/?")) { Show-Help $(if ($RestArgs.Count -gt 0) { $RestArgs[0] } else { "" }); exit 0 }
# clean-run and clean-debug: cleanup --all --yes, init, then up or debug, each as its own run of
# this script (so each step writes its own log, like typing the three commands)
if ($Command -in @("clean-run", "clean-debug")) {
    $kind = if ($RestArgs.Count -gt 0) { $RestArgs[0] } else { "laptop" }
    $last = if ($Command -eq "clean-run") { "up" } else { "debug" }
    foreach ($step in @(@("cleanup", "--all", "--yes"), @("init", $kind), @($last))) {
        Write-Host ""
        Write-Host "=== .\eax $($step -join ' ')" -ForegroundColor Cyan
        & $PSCommandPath @step
        if ($LASTEXITCODE -ne 0) {
            Write-Host "ERROR: .\eax $($step -join ' ') failed (exit $LASTEXITCODE); $Command stopped there." -ForegroundColor Red
            exit $LASTEXITCODE
        }
    }
    exit 0
}
if ($Command -eq "cleanup") {
    try { Invoke-Cleanup $RestArgs; exit 0 }
    catch { Write-Host "ERROR: $($_.Exception.Message)" -ForegroundColor Red; exit 1 }
}

Start-Log $Command
if ((Test-Path "eaexplorer.env") -and -not (Test-Path $EnvFile)) {
    Write-Log "Found eaexplorer.env in the main folder: it is no longer used. The config now lives in work\eaexplorer.env." "Yellow"
    Write-Log "Delete the old file and run .\eax init laptop (or copy your changes into work\eaexplorer.env)." "Yellow"
}
$failed = $false
try {
    if ($Command -in @("check", "up", "debug", "status", "logs", "down", "backup", "restore")) { Assert-Docker }
    switch ($Command) {
        "init" {
            $kind = if ($RestArgs.Count -gt 0) { $RestArgs[0] } else { "laptop" }
            $template = "deploy/templates/eaexplorer.$kind.env"
            if (Test-Path $EnvFile) { throw "$EnvFile already exists; not overwriting. Use .\eax cleanup to start again." }
            if (-not (Test-Path $template)) { throw "Unknown deployment kind: $kind" }
            # Plain copy, UTF-8 without BOM and LF endings (Docker Compose reads it cleanly). No passwords are generated.
            foreach ($d in "work/logs", "work/data/backups", "work/data/imports", "work/data/exports", "work/data/tls") { New-Item -ItemType Directory -Force -Path $d | Out-Null }
            $lines = Get-Content $template
            [System.IO.File]::WriteAllText((Join-Path $PSScriptRoot $EnvFile), (($lines -join "`n") + "`n"), $Utf8)
            Write-Log "Created $EnvFile ($kind) from $template."
            if ($kind -eq "laptop") { Show-Logins }
            else { Write-Log "Now replace every change-me value in $EnvFile with your own passwords before .\eax up." }
        }
        "check" {
            if ((Invoke-Logged "docker" @("version", "--format", "Docker {{.Server.Version}}")) -ne 0) { throw "Docker Desktop is not running." }
            Invoke-Logged "docker" @("compose", "version") | Out-Null
            if (Test-Path $EnvFile) { Write-Log "Config: $EnvFile ($(Get-Setting 'EAX_DEPLOYMENT' 'laptop'))" } else { throw "No $EnvFile yet: run .\eax init" }
            Invoke-Compose @("config", "--quiet") | Out-Null
            Write-Log "Compose configuration is valid."
        }
        "up"      {
            Invoke-Compose (@("up", "-d", "--build") + $RestArgs) | Out-Null
            if ($RestArgs.Count -gt 0) { Show-PartUrls $RestArgs } else { Show-Urls; Show-Logins }
        }
        "debug" {
            $code = Invoke-Compose (@("up", "-d", "--build") + $RestArgs) -NoThrow
            if ($code -ne 0) { Write-Log "docker compose up failed (exit $code); recording what is running anyway." "Red" }
            Save-Diagnostics
            if ($RestArgs.Count -gt 0) { Show-PartUrls $RestArgs } else { Show-Urls; Show-Logins }
            Watch-Containers $RestArgs
        }
        "diag"    { Save-Diagnostics }
        "status"  { Invoke-Compose @("ps", "-a") | Out-Null }
        "logs"    { Invoke-Compose (@("logs", "-f", "--tail=100") + $RestArgs) -NoThrow | Out-Null }
        "down"    { Invoke-Compose @("down") | Out-Null }
        "backup"  { Invoke-Compose @("exec", "-T", "backup", "backup.sh") | Out-Null }
        "restore" { Invoke-Compose (@("exec", "-T", "backup", "restore.sh") + $RestArgs) | Out-Null }
        "url"     { Show-Urls; Show-Logins }
        "logins"  { if (-not (Test-Path $EnvFile)) { throw "No $EnvFile yet: run .\eax init first." }; Show-Logins }
        default   { throw "Unknown command '$Command'. Run .\eax help" }
    }
} catch {
    $failed = $true
    if ($script:Log) { $script:Log.WriteLine("ERROR: $($_.Exception.Message)") }
    Write-Host "ERROR: $($_.Exception.Message)" -ForegroundColor Red
} finally {
    if ($script:LogPath) { Write-Host "Log: $script:LogPath" -ForegroundColor DarkGray }
    Stop-Log
}
if ($failed) { exit 1 }
