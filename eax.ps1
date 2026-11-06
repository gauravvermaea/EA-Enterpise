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
if ($Command -eq "run") { $Command = "up" }   # run: the everyday start, the same as up
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

# ------------------------------------------------------------------ optional services (D191)
# name: setting, compose services in start order (mcp and change_log run inside the api container)
$Services = [ordered]@{
    "reports"    = @("EAX_SERVICE_REPORTS", @("reports-init", "reports"))
    "documents"  = @("EAX_SERVICE_DOCUMENTS", @("dms-broker", "dms"))
    "drawio"     = @("EAX_SERVICE_DRAWIO", @("drawio"))
    "mcp"        = @("EAX_SERVICE_MCP", @("api"))
    "change_log" = @("EAX_SERVICE_CHANGE_LOG", @("api"))
    "backups"    = @("EAX_SERVICE_BACKUPS", @("backup"))
}
function Test-ServiceOn([string]$Name) {
    $default = if ($Name -eq "mcp") { Get-Setting "EAX_MCP_ENABLED" "on" } else { "on" }
    $v = (Get-Setting $Services[$Name][0] $default).ToLower()
    return -not ($v -in @("off", "false", "0", "no", "disabled"))
}
# work\services.env: the switches only (no secrets), read by the api container
function Write-ServicesFile {
    $lines = @("# Written by EA Explorer from eaexplorer.env: the service switches only (D191). Do not edit; change eaexplorer.env.")
    foreach ($n in $Services.Keys) { $lines += "$($Services[$n][0])=$(if (Test-ServiceOn $n) { 'on' } else { 'off' })" }
    [System.IO.File]::WriteAllText((Join-Path $WorkDir "services.env"), (($lines -join "`n") + "`n"), $Utf8)
}
# compose services of the switched-off optional services (not the api, which stays on)
function Get-OffContainers {
    $off = @()
    foreach ($n in $Services.Keys) { if (-not (Test-ServiceOn $n) -and $Services[$n][1][0] -ne "api") { $off += $Services[$n][1] } }
    return $off
}
# up (all services): starts everything but the switched-off services; those are created, not started, so the
# console can switch them on later
function Invoke-Up([string[]]$Names, [switch]$NoThrow) {
    Write-ServicesFile
    if ($Names.Count -gt 0) { return (Invoke-Compose (@("up", "-d", "--build") + $Names) -NoThrow:$NoThrow) }
    $off = @(Get-OffContainers)
    if ($off.Count -eq 0) { return (Invoke-Compose @("up", "-d", "--build") -NoThrow:$NoThrow) }
    $old = $ErrorActionPreference; $ErrorActionPreference = "Continue"
    $all = @(& docker @(Get-ComposeArgs @("config", "--services")) 2>$null | Where-Object { $_ })
    $ErrorActionPreference = $old
    $on = @($all | Where-Object { $_ -notin $off })
    Write-Log "Switched off (D191): $($off -join ', '): created, not started."
    $code = Invoke-Compose (@("up", "-d", "--build") + $on) -NoThrow:$NoThrow
    Invoke-Compose (@("create", "--build") + $off) -NoThrow | Out-Null
    Invoke-Compose (@("stop") + $off) -NoThrow -Quiet | Out-Null
    return $code
}
function Show-Services {
    foreach ($n in $Services.Keys) {
        $state = if (Test-ServiceOn $n) { "on " } else { "off" }
        Write-Log ("{0,-11} {1}   {2} = {3}   containers: {4}" -f $n, $state, $Services[$n][0], (Get-Setting $Services[$n][0] "on"), ($Services[$n][1] -join ", "))
    }
    Invoke-Compose @("ps", "-a") | Out-Null
}
function Set-Service([string]$Name, [string]$Value) {
    if (-not $Services.Contains($Name)) { throw "Unknown service '$Name'. One of: $($Services.Keys -join ', ')" }
    if ($Value -notin @("on", "off")) { throw "Say on or off: .\eax service $Name on" }
    $history = Join-Path $WorkDir "config-history"
    New-Item -ItemType Directory -Force -Path $history | Out-Null
    $copy = "eaexplorer.env.$((Get-Date).ToUniversalTime().ToString('yyyyMMdd-HHmmss')).$($env:USERNAME -replace '[^A-Za-z0-9_.-]', '-').$Name-$Value"
    Copy-Item $EnvFile (Join-Path $history $copy)
    $setting = $Services[$Name][0]
    $lines = @(Get-Content $EnvFile | Where-Object { -not ($Name -eq "mcp" -and $_ -match "^\s*EAX_MCP_ENABLED\s*=") })
    if ($lines | Where-Object { $_ -match "^\s*$setting\s*=" }) {
        $lines = @($lines | ForEach-Object { if ($_ -match "^\s*$setting\s*=") { "$setting=$Value" } else { $_ } })
    } else { $lines += @("", "$setting=$Value") }
    [System.IO.File]::WriteAllText((Join-Path $PSScriptRoot $EnvFile), (($lines -join "`n") + "`n"), $Utf8)
    Write-ServicesFile
    Write-Log "$setting=$Value written (the config file before is kept as work\config-history\$copy)."
    $names = $Services[$Name][1]
    if ($names[0] -eq "api") { Invoke-Compose @("restart", "api") | Out-Null }
    elseif ($Value -eq "on") { Invoke-Compose (@("up", "-d") + $names) | Out-Null }
    else { Invoke-Compose (@("stop") + $names) | Out-Null }
}

# ------------------------------------------------------------------ output helpers
function Show-Urls {
    $h = Get-Setting "EAX_HOSTNAME" "localhost"; $p = Get-Setting "EAX_HTTPS_PORT" "443"
    $s = if ($p -eq "443") { "" } else { ":$p" }
    Write-Log "Start page:  https://$h$s/"
    Write-Log "Swagger:     https://$h$s/api/docs"
    if (Test-ServiceOn "reports") { Write-Log "Reports:     https://reports.$h$s/" }
    if (Test-ServiceOn "documents") { Write-Log "Documents:   https://docs.$h$s/" }
    Write-Log "Keycloak:    https://$h$s/auth/admin/"
    if (Test-ServiceOn "mcp") { Write-Log "MCP server:  https://$h$s/mcp" }
    if ((Get-Setting "EAX_HTTP_API_MCP" "false") -eq "true") {
        $hp = Get-Setting "EAX_HTTP_PORT" "80"; $hs = if ($hp -eq "80") { "" } else { ":$hp" }
        Write-Log "Also on plain http (this computer only): http://localhost$hs/api/docs and http://localhost$hs/mcp"
    }
    Show-TrustHint
}

# ------------------------------------------------------------------ the local certificate (D107)
# The setup service makes a local certificate authority (ca.crt) and signs the site certificate with it.
# "trust" adds ca.crt to this Windows user's trusted root certificates (Windows asks you to confirm),
# after removing earlier EA Explorer ones, so Edge, Chrome and Windows tools trust https://localhost.
function Get-CaPath {
    $d = Get-Setting "EAX_TLS_DIR" "./work/data/tls"
    if ($d -notmatch '[\\/]') { throw "EAX_TLS_DIR is the Docker volume '$d', not a folder: copy ca.crt out with docker compose cp setup:/tls/ca.crt ." }
    return Join-Path (Join-Path $PSScriptRoot $d) "ca.crt"
}
function Get-OurCas { Get-ChildItem Cert:\CurrentUser\Root | Where-Object { $_.Subject -like "*O=EA Explorer (self-signed)*" } }
function Show-TrustHint {
    try { $ca = Get-CaPath } catch { return }
    if (-not (Test-Path $ca)) { return }
    $want = (New-Object System.Security.Cryptography.X509Certificates.X509Certificate2 $ca).Thumbprint
    if (-not (Get-OurCas | Where-Object { $_.Thumbprint -eq $want })) {
        Write-Log "Optional: run  .\eax trust  once so the browser stops warning about the certificate (it survives clean-run)." "Yellow"
        Write-Log "Without it, accept the warning once for localhost, reports.localhost and docs.localhost, as before." "Yellow"
    }
}
function Invoke-Trust([string[]]$Options) {
    $ca = Get-CaPath
    if ($Options -contains "--remove") {
        $old = @(Get-OurCas); $old | Remove-Item
        Write-Log "Removed $($old.Count) EA Explorer certificate(s) from your trusted root certificates."
        return
    }
    if (-not (Test-Path $ca)) { throw "No $ca yet: run .\eax up first (the setup service makes it)." }
    $new = New-Object System.Security.Cryptography.X509Certificates.X509Certificate2 $ca
    Get-OurCas | Where-Object { $_.Thumbprint -ne $new.Thumbprint } | Remove-Item
    if (Get-OurCas | Where-Object { $_.Thumbprint -eq $new.Thumbprint }) { Write-Log "Already trusted: $($new.Subject)" }
    else {
        Write-Log "Adding $($new.Subject) to your trusted root certificates. Windows asks you to confirm: choose Yes." "Yellow"
        Import-Certificate -FilePath $ca -CertStoreLocation Cert:\CurrentUser\Root | Out-Null
        Write-Log "Trusted. Restart the browser. It may vouch only for this installation's names (localhost and EAX_HOSTNAME)."
    }
    Write-Log "Firefox: set security.enterprise_roots.enabled to true in about:config, or import $ca there."
    Write-Log "MCP clients that run on Node (Claude Code, mcp-remote): setx NODE_EXTRA_CA_CERTS `"$ca`"  and open a new window."
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
        @("MCP server (development token)",   "(bearer)",                                     (Get-Setting "EAX_MCP_DEV_TOKEN"),           "https://localhost/mcp or http://localhost/mcp"),
        @("Keycloak client secrets",          "superset/mayan",                               (Get-Setting "EAX_SUPERSET_OIDC_SECRET"),    "OIDC clients"),
        @("Keycloak API client (eax-admin)",  "eax-admin",                                    (Get-Setting "EAX_KC_SERVICE_SECRET"),       "reads people and roles"),
        @("Break-glass account",              "break-glass",                                  (Get-Setting "EAX_BREAK_GLASS_PASSWORD"),    "when Keycloak is down: start page")
    )
    # Test users (phase 3.1): their global Keycloak role and the model roles the seed gives them
    $testPw = Get-Setting "EAX_TEST_USER_PASSWORD" ""
    if (-not $testPw) { $testPw = Get-Setting "EAX_FIRST_ADMIN_PASSWORD" }
    $tests = @(
        @("user_super_admin", "eax-super-admin", "everything, every model"),
        @("user_it_admin", "eax-it-admin", "runs the installation; no models"),
        @("user_keycloak_admin", "eax-keycloak-admin", "Keycloak console of the realm"),
        @("user_user_admin", "eax-user-admin", "Users page, role mapping; reads no model"),
        @("user_library_admin", "eax-library-admin", "curates the model library: create, publish, promote, upload, withdraw"),
        @("user_model_creator", "eax-model-creator", "creates models; Model Admin: Karoo Re, Lean EA metamodel, Karoo Digital"),
        @("user_model_admin", "eax-user", "Model Admin: Fynbos group, Fynbos Life, Protea demo; Architect: Sample"),
        @("user_architect", "eax-user", "Architect: Sample, Fynbos Life, Protea demo; Model Sub Admin + Report Viewer: Fynbos Commercial"),
        @("user_model_sub_admin", "eax-user", "Model Sub Admin: Sample, Fynbos Life, Fynbos Commercial, Karoo Re"),
        @("user_committer", "eax-user", "Committer: Protea demo, Sample (commits what others ask to commit)"),
        @("user_history_viewer", "eax-user", "History Viewer and Report Viewer: Protea demo (sees everyone's commits)"),
        @("user_report_viewer", "eax-user", "Report Viewer: Fynbos group, Sample, Protea demo"),
        @("user_global_architect", "eax-user", "Architect on every model")
    )
    foreach ($t in $tests) { $rows += ,@("Test user ($($t[1]))", $t[0], $testPw, $t[2]) }
    Write-Log ""
    Write-Log "================ DEVELOPMENT LOGINS (laptop only - never use these on a server) ================" "Yellow"
    Write-Log ("{0,-38} {1,-22} {2,-16} {3}" -f "Account", "User", "Password", "Notes")
    foreach ($r in $rows) { Write-Log ("{0,-38} {1,-22} {2,-16} {3}" -f $r[0], $r[1], $r[2], $r[3]) }
    Write-Log "=================================================================================================" "Yellow"
}

# After starting only some services: where to reach them directly (laptop)
function Show-PartUrls([string[]]$Services) {
    Write-Log ""
    Write-Log "Started: $($Services -join ', ') (and what they depend on). The rest stays stopped."
    if ($Services -contains "api") {
        Write-Log "The API goes through nginx: start it too with  .\eax up api proxy  (no Keycloak needed for public endpoints):"
        Write-Log "  Swagger:    https://localhost/api/docs   (laptop also http://localhost/api/docs)"
        Write-Log "  Heartbeat:  https://localhost/api/v1/heartbeat"
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
  run                   The everyday start, after the first clean-run: the same as up. Keeps the
                        databases, documents and settings from last time.
  up [service...]       Builds our images, pulls the others, and starts every container in the
                        background. Then prints the addresses and (laptop) the logins.
                        Name services to start only those and what they depend on, for example
                        "up api proxy" starts the API, PostgreSQL and nginx only (about 1 GB);
                        the API is then at https://localhost/api/docs (laptop also http://).

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
  trust [--remove]      Adds EA Explorer's local certificate (work\data\tls\ca.crt) to your Windows
                        trusted root certificates, so the browser stops warning about https://localhost.
                        Run it once after the first start: clean-run keeps the certificate. --remove
                        takes EA Explorer's certificates out again.
  logins                Prints every user name and password (laptop only).
  down                  Stops and removes the containers. Data in Docker volumes and in work\ is kept.
  backup [tag]          Takes an infrastructure backup now (every database, the document files, the
                        certificate, the config file, the release and image versions) into
                        work\backups\infrastructure, tagged (D216, D226).
  backups [words]       Lists every backup: infrastructure (numbered, to restore) and application;
                        with words, only those whose tag, name or maker has them (search by tag).
  restore [name|tag|latest] [--what full|app|app+data|db|files] [--yes]
                        Restores an infrastructure backup: by name, by tag (the newest with it) or
                        latest (the newest good one). Without one it lists them to choose
                        from, then asks what to restore and for RESTORE to confirm. full = everything;
                        app = the config file; app+data = the config file, the repository and
                        document databases and the document files; db = every database; files =
                        the document files and the certificate. A backup of the current state is
                        taken first; nothing live changes until all is restored cleanly; it can be
                        run again. Works when the console is down (starts db, backup and ops).
  restores              Lists every restore (infrastructure and model) with its status.
  restore-log <id>      Shows a restore's whole log (also in work\backups\restores\<id>).
  delete-backup <name>  Deletes an infrastructure backup (unpin it first if it is pinned).
  delete-restore <id>   Forgets a finished restore and its log.
  stop-backup           Stops the backups running (infrastructure: at once; application: after the
                        model it is on); the partial backup is deleted. A restore cannot be stopped.
  restore-app [run|tag|latest] [--yes]
                        Restores every model of an application backup, each over itself (each backed
                        up first); models no longer there are made again; newer models stay as they
                        are. Needs the api container running.
  maintenance on|off    Shows (or stops showing) the maintenance page to everyone, served by the
                        proxy. Restores and up (an upgrade) switch it on and off themselves.
  app-backup [tag]      Backs up every model now (an application backup), into work\backups\application.
  restore-model         Lists the application backups and the models in them to choose from, then
                        restores one as a new model or over itself (needs the api container running).
  services              Lists the optional services (reports, documents, drawio, mcp, change_log,
                        backups), whether each is on in the config file and its containers' state.
  service <name> on|off Switches one optional service on or off: keeps a dated copy of the config file
                        in work\config-history, writes the switch, then starts or stops its containers.
                        Everything is on unless switched off (D191). Also in Administration > System
                        settings > Services.

Starting again
  cleanup [--all] [--yes] [--certificate]
                        Stops the containers and deletes everything in the work folder: the config
                        file, logs and laptop data folders (including backups). With --all it also
                        deletes the Docker volumes, so the databases and documents start empty.
                        The local certificate (work\data\tls) is kept, so you need not trust it
                        again; --certificate deletes it too. Asks you to type yes unless --yes is given.
  clean-run [laptop|server]
                        Starts again from scratch in one step: cleanup --all --yes, then init
                        (laptop if not given), then up. Deletes the databases and everything in
                        the work folder without asking.
  clean-debug [laptop|server]
                        The same, but ends with debug instead of up (keeps recording the
                        containers' output until Ctrl+C).
  clean-restart [laptop|server]
                        For testing a new version: down (stops and removes the running containers),
                        then clean-run (cleanup --all --yes, init, up). Rebuilds our images and
                        starts with empty databases; the trusted certificate is kept.

  help [command]        This text, or the part about one command.

Logs: every command except help and cleanup writes its full output to
work\logs\eax-<date-time>-<command>.log. When a Docker step fails, a diagnostics report is added to
that log automatically, so the log file is all you need to send when something goes wrong.
'@

# Backups and restores from the command line (D227): they talk to the operations helper and the backup container, so
# those (and the database) are started first if they are not running; the console is not needed.
function Start-BackupHelpers {
    Invoke-Compose @("up", "-d", "db", "backup", "ops") -Quiet | Out-Null
}
function Get-Version {
    return (Select-String -Path "services\api\version.toml" -Pattern '^version = "(.*)"').Matches[0].Groups[1].Value
}
# Runs a command in a container with this console attached, so it can ask (choose a backup, type RESTORE) and show
# progress as it comes; the restore keeps its own log in work\backups\restores
function Invoke-Interactive([string[]]$Target, [string[]]$Arguments) {
    Write-Log "> docker compose exec $($Target -join ' ') $($Arguments -join ' ')  (interactive: output in this window, not in this log)"
    $old = $ErrorActionPreference; $ErrorActionPreference = "Continue"
    $rest = @($Arguments | Where-Object { $null -ne $_ -and $_ -ne "" })
    & docker @(Get-ComposeArgs (@("exec") + $Target + $rest))
    $code = $LASTEXITCODE
    $ErrorActionPreference = $old
    if ($code -ne 0) { throw "$($Target[0]) $($Target[2..($Target.Count - 1)] -join ' ') ended with exit $code" }
}

# Shows the maintenance page while up rebuilds a running installation (D230); only when the proxy runs already and the
# page is not on for another reason. Returns whether it switched it on.
function Set-UpgradePage([bool]$All) {
    if (-not $All -or (Test-Path "work/proxy/maintenance")) { return $false }
    $old = $ErrorActionPreference; $ErrorActionPreference = "Continue"
    $running = @(& docker @(Get-ComposeArgs @("ps", "--status", "running", "-q", "proxy")) 2>$null | Where-Object { $_ })
    $ErrorActionPreference = $old
    if ($running.Count -eq 0) { return $false }
    New-Item -ItemType Directory -Force -Path "work/proxy" | Out-Null
    [System.IO.File]::WriteAllText((Join-Path $PSScriptRoot "work/proxy/maintenance"), "upgrade`n", $Utf8)
    Write-Log "Everyone sees the maintenance page until this has finished."
    return $true
}

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
    $all = $false; $yes = $false; $cert = $false
    foreach ($o in $Options) {
        switch ($o) { "--all" { $all = $true } "--yes" { $yes = $true } "-y" { $yes = $true } "--certificate" { $cert = $true } default { throw "Unknown option $o" } }
    }
    Write-Host "This deletes everything in ${WorkDir}: the config file, all logs, the laptop data folders, and every backup and restore log (work\backups)." -ForegroundColor Yellow
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
    if (Test-Path $WorkDir) {
        if ($cert) { Get-ChildItem -Path $WorkDir -Force | Remove-Item -Recurse -Force }
        else {
            # keep work\data\tls: the local certificate you trusted with .\eax trust (D107)
            Get-ChildItem -Path $WorkDir -Force | Where-Object { $_.Name -ne "data" } | Remove-Item -Recurse -Force
            $data = Join-Path $WorkDir "data"
            if (Test-Path $data) { Get-ChildItem -Path $data -Force | Where-Object { $_.Name -ne "tls" } | Remove-Item -Recurse -Force }
        }
    }
    foreach ($b in @((Join-Path $WorkDir "backups"), (Join-Path $WorkDir "data\backups"))) {
        if (Test-Path $b) { Remove-Item -Recurse -Force $b -ErrorAction SilentlyContinue }
    }
    if (Test-Path (Join-Path $WorkDir "backups")) { Write-Host "WARNING: work\backups could not be deleted completely (a file is in use?): delete it by hand." -ForegroundColor Yellow }
    else { Write-Host "Every backup and restore log is deleted." }
    if ($cert) { Write-Host "The work folder is empty. Run .\eax init laptop to start again." }
    else { Write-Host "The work folder is empty apart from the local certificate (work\data\tls). Run .\eax init laptop to start again." }
}

# ------------------------------------------------------------------ commands
if ($Command -in @("help", "-h", "--help", "/?")) { Show-Help $(if ($RestArgs.Count -gt 0) { $RestArgs[0] } else { "" }); exit 0 }
# clean-run and clean-debug: cleanup --all --yes, init, then up or debug, each as its own run of
# this script (so each step writes its own log, like typing the three commands)
# clean-restart: down first (when there is a config file to find the containers by), then the same
if ($Command -in @("clean-run", "clean-debug", "clean-restart")) {
    $kind = if ($RestArgs.Count -gt 0) { $RestArgs[0] } else { "laptop" }
    $last = if ($Command -eq "clean-debug") { "debug" } else { "up" }
    $steps = @(@("cleanup", "--all", "--yes"), @("init", $kind), @($last))
    if ($Command -eq "clean-restart") {
        if (Test-Path $EnvFile) { $steps = @(, @("down")) + $steps }
        else { Write-Host "No $EnvFile yet: nothing running to bring down; going straight to clean-run." -ForegroundColor Yellow }
    }
    foreach ($step in $steps) {
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
    if ($Command -in @("check", "up", "debug", "status", "logs", "down", "backup", "backups", "restore", "restores", "restore-log",
                       "delete-backup", "delete-restore", "app-backup", "restore-model", "restore-app", "stop-backup", "services", "service")) { Assert-Docker }
    switch ($Command) {
        "init" {
            $kind = if ($RestArgs.Count -gt 0) { $RestArgs[0] } else { "laptop" }
            $template = "deploy/templates/eaexplorer.$kind.env"
            if (Test-Path $EnvFile) { throw "$EnvFile already exists; not overwriting. Use .\eax cleanup to start again." }
            if (-not (Test-Path $template)) { throw "Unknown deployment kind: $kind" }
            # Plain copy, UTF-8 without BOM and LF endings (Docker Compose reads it cleanly). No passwords are generated.
            foreach ($d in "work/logs", "work/backups", "work/proxy", "work/data/imports", "work/data/exports", "work/data/tls") { New-Item -ItemType Directory -Force -Path $d | Out-Null }
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
            # an upgrade (D230): while the containers are rebuilt and restarted, the proxy shows the maintenance page
            $page = Set-UpgradePage ($RestArgs.Count -eq 0)
            try { Invoke-Up $RestArgs | Out-Null } finally { if ($page) { Remove-Item -Force "work/proxy/maintenance" -ErrorAction SilentlyContinue } }
            if ($RestArgs.Count -gt 0) { Show-PartUrls $RestArgs } else { Show-Urls; Show-Logins }
        }
        "debug" {
            $code = Invoke-Up $RestArgs -NoThrow
            if ($code -ne 0) { Write-Log "docker compose up failed (exit $code); recording what is running anyway." "Red" }
            Save-Diagnostics
            if ($RestArgs.Count -gt 0) { Show-PartUrls $RestArgs } else { Show-Urls; Show-Logins }
            Watch-Containers $RestArgs
        }
        "diag"    { Save-Diagnostics }
        "status"  { Invoke-Compose @("ps", "-a") | Out-Null }
        "logs"    { Invoke-Compose (@("logs", "-f", "--tail=100") + $RestArgs) -NoThrow | Out-Null }
        "down"    { Invoke-Compose @("down") | Out-Null }
        "backup"  { if (-not (Test-ServiceOn "backups")) { throw "Backups are switched off: .\eax service backups on" }
                    Start-BackupHelpers
                    Invoke-Interactive @("ops", "python3", "/app/ops.py", "backup") $RestArgs }
        "backups" { Start-BackupHelpers; Invoke-Interactive @("ops", "python3", "/app/ops.py", "list") $RestArgs }
        "stop-backup" { Start-BackupHelpers; Invoke-Interactive @("ops", "python3", "/app/ops.py", "stop-backup") @() }
        "restore-app" { Invoke-Interactive @("api", "python", "-m", "eax.backups_cli", "restore-all") $RestArgs }
        "maintenance" {
            $flag = "work/proxy/maintenance"
            if ($RestArgs.Count -lt 1 -or $RestArgs[0] -notin @("on", "off")) { throw "Usage: .\eax maintenance on|off" }
            if ($RestArgs[0] -eq "on") {
                New-Item -ItemType Directory -Force -Path "work/proxy" | Out-Null
                [System.IO.File]::WriteAllText((Join-Path $PSScriptRoot $flag), "maintenance`n", $Utf8)
                Write-Log "The maintenance page is shown to everyone until: .\eax maintenance off"
            } else {
                if (Test-Path $flag) { Remove-Item -Force $flag }
                Write-Log "The maintenance page is off."
            }
        }
        "restore" { if (-not (Test-ServiceOn "backups")) { throw "Backups are switched off: .\eax service backups on" }
                    Start-BackupHelpers
                    Invoke-Interactive @("ops", "python3", "/app/ops.py", "restore") ($RestArgs + @("--version", (Get-Version))) }
        "restores" { Start-BackupHelpers; Invoke-Interactive @("ops", "python3", "/app/ops.py", "restores") @() }
        "restore-log" { Start-BackupHelpers; Invoke-Interactive @("ops", "python3", "/app/ops.py", "restore-log") $RestArgs }
        "delete-backup" { Start-BackupHelpers; Invoke-Interactive @("ops", "python3", "/app/ops.py", "delete-backup") $RestArgs }
        "delete-restore" { Start-BackupHelpers; Invoke-Interactive @("ops", "python3", "/app/ops.py", "delete-restore") $RestArgs }
        "app-backup" { Invoke-Interactive @("api", "python", "-m", "eax.backups_cli", "backup") $RestArgs }
        "restore-model" { Invoke-Interactive @("api", "python", "-m", "eax.backups_cli", "restore") $RestArgs }
        "services" { Show-Services }
        "service" {
            if ($RestArgs.Count -lt 2) { throw "Usage: .\eax service <name> on|off   (names: $($Services.Keys -join ', '))" }
            Set-Service $RestArgs[0] $RestArgs[1].ToLower()
        }
        "url"     { Show-Urls; Show-Logins }
        "logins"  { if (-not (Test-Path $EnvFile)) { throw "No $EnvFile yet: run .\eax init first." }; Show-Logins }
        "trust"   { if (-not (Test-Path $EnvFile)) { throw "No $EnvFile yet: run .\eax init first." }; Invoke-Trust $RestArgs }
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
