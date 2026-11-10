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
$AskedFor = $Command          # as typed, for <command> --help
if ($Command -eq "run") { $Command = "up" }   # run: the everyday start, the same as up
if ($Command -eq "stop") { $Command = "down" }   # stop: the same as down (the data is kept)
$Rest = @($args | Select-Object -Skip 1 | ForEach-Object { [string]$_ })
$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot
$WorkDir = Join-Path $PSScriptRoot "work"
$EnvFile = "work/eaexplorer.env"
$LogDir = Join-Path $WorkDir "logs"
$Stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$RestArgs = @($Rest | Where-Object { $_ })   # extra arguments, without empty entries
# --wait-all (up, run, debug and the clean-* commands): start everything and wait until all of it is up, the sample data
# loaded too; without it the core starts first and the rest in the background (D255)
$WaitAll = $RestArgs -contains "--wait-all"
$RestArgs = @($RestArgs | Where-Object { $_ -ne "--wait-all" })
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
    # scale-out extra files (phase 36.3, D521): EAX_COMPOSE_EXTRA=standby,shared-storage... (deploy/compose/scale)
    $extra = @()
    foreach ($x in ((Get-Setting "EAX_COMPOSE_EXTRA" "") -split "[,\s]+" | Where-Object { $_ })) {
        $f = "deploy/compose/scale/docker-compose.$x.yml"
        if (-not (Test-Path $f)) { throw "EAX_COMPOSE_EXTRA names $x, but there is no $f." }
        $extra += @("-f", $f)
    }
    return @("compose", "--ansi", "never", "--progress", "plain", "--env-file", $EnvFile,
             "-f", "docker-compose.yml", "-f", "deploy/compose/docker-compose.$kind.yml") + $extra + $Arguments
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
    "library"    = @("EAX_SERVICE_LIBRARY", @("library"))
    "views"      = @("EAX_SERVICE_VIEWS", @("views"))
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
# how many API and job servers (copies of the api container) run (D249): 1 to 16, 1 when not set
function Get-ApiServers {
    $n = 1
    if (-not [int]::TryParse((Get-Setting "EAX_API_SERVERS" "1"), [ref]$n)) { $n = 1 }
    return [Math]::Max(1, [Math]::Min(16, $n))
}
# The start-up in two tiers (D255): the core first (database, set-up, proxy, screens, sign-in, the API with the database
# upgrade and the built-in models), so people can sign in in a minute or two; everything else after it, in the
# background (Reports, Documents, draw.io, backups, the operations helper), while the API loads the sample data and
# measures data quality. The screens show each part red, amber or green (down, starting, up).
$CoreServices = @("db", "setup", "proxy", "web", "keycloak", "api")
function Get-Tiers {
    $off = @(Get-OffContainers)
    $old = $ErrorActionPreference; $ErrorActionPreference = "Continue"
    $all = @(& docker @(Get-ComposeArgs @("config", "--services")) 2>$null | Where-Object { $_ })
    $ErrorActionPreference = $old
    $on = @($all | Where-Object { $_ -notin $off })
    return @{ First = @($on | Where-Object { $_ -in $CoreServices }); Later = @($on | Where-Object { $_ -notin $CoreServices }); Off = $off }
}
# waits until the API (every copy) and Keycloak say healthy; shows each change; false when one stopped or it took too long
function Wait-Core([int]$Minutes = 15) {
    $until = (Get-Date).AddMinutes($Minutes)
    $last = ""
    while ((Get-Date) -lt $until) {
        $old = $ErrorActionPreference; $ErrorActionPreference = "Continue"
        $rows = @(& docker @(Get-ComposeArgs @("ps", "-a", "--format", "{{.Name}}|{{.State}}|{{.Health}}", "api", "keycloak")) 2>$null | Where-Object { $_ -match "\|" })
        $ErrorActionPreference = $old
        $now = ($rows | ForEach-Object { $p = $_ -split "\|"; "$($p[0]): $(if ($p[2]) { $p[2] } else { $p[1] })" }) -join ", "
        if ($now -and $now -ne $last) { Write-Log "  $now"; $last = $now }
        if ($rows.Count -ge 2 -and -not ($rows | Where-Object { ($_ -split "\|")[2] -ne "healthy" })) { return $true }
        if ($rows | Where-Object { ($_ -split "\|")[1] -in @("exited", "dead") }) {
            Write-Log "A core container stopped; see .\eax logs api (or keycloak)." "Red"
            return $false
        }
        Start-Sleep -Seconds 5
    }
    Write-Log "The API or sign-in was not ready after $Minutes minutes; see .\eax logs api (or keycloak)." "Yellow"
    return $false
}
# --wait-all: waits until every part is up (the API's start-up status, D255): Reports, Documents, Diagrams, the sample data
function Wait-All([int]$Minutes = 30) {
    $until = (Get-Date).AddMinutes($Minutes)
    $t0 = Get-Date
    $last = ""
    $py = "import json,urllib.request as u; d=json.load(u.urlopen('http://localhost:8000/api/startup',timeout=20)); print(d['overall']+'|'+', '.join(p['key']+': '+p['status'] for p in d['parts']))"
    Write-Log "Waiting for everything: Reports, Documents, Diagrams and the sample data (up to $Minutes minutes)..."
    while ((Get-Date) -lt $until) {
        $old = $ErrorActionPreference; $ErrorActionPreference = "Continue"
        $now = @(& docker @(Get-ComposeArgs @("exec", "-T", "api", "python", "-c", $py)) 2>$null | Where-Object { $_ -match "\|" }) | Select-Object -Last 1
        $ErrorActionPreference = $old
        if ($now -and $now -ne $last) { Write-Log "  $(($now -split '\|', 2)[1])"; $last = $now }
        if ($now -like "up|*") { Write-Log "Everything is up after $([int]((Get-Date) - $t0).TotalSeconds) s." "Green"; return }
        if ($now -like "down|*" -and $now -notmatch "starting") {
            Write-Log "Started, but not everything is up (see above): .\eax logs <service>." "Yellow"; return
        }
        Start-Sleep -Seconds 10
    }
    Write-Log "Not everything was up after $Minutes minutes (see above); EA Explorer is usable, the rest may still come." "Yellow"
}
# the second tier, in a hidden PowerShell of its own with its own log, so this window is free at once
function Start-Later {
    $p = @{ FilePath = (Get-Process -Id $PID).Path; WorkingDirectory = $PSScriptRoot
            ArgumentList = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "`"$PSCommandPath`"", "start-later") }
    if (-not ($IsLinux -or $IsMacOS)) { $p.WindowStyle = "Hidden" }   # Windows only; elsewhere it has no window anyway
    Start-Process @p | Out-Null
    Write-Log "Reports, documents, draw.io, backups and the operations helper start now in the background (log: work\logs\eax-*-start-later.log)."
}
function Invoke-Up([string[]]$Names, [switch]$NoThrow) {
    Write-ServicesFile
    $scale = @("--scale", "api=$(Get-ApiServers)")
    if ($Names.Count -gt 0) {
        if ($Names -contains "api") { return (Invoke-Compose (@("up", "-d", "--build") + $scale + $Names) -NoThrow:$NoThrow) }
        return (Invoke-Compose (@("up", "-d", "--build") + $Names) -NoThrow:$NoThrow)
    }
    $t = Get-Tiers
    if ($t.Off.Count -gt 0) { Write-Log "Switched off (D191): $($t.Off -join ', '): created, not started." }
    Write-Log "Starting the core first (D255): $($t.First -join ', ')" "Cyan"
    $code = Invoke-Compose (@("up", "-d", "--build") + $scale + $t.First) -NoThrow:$NoThrow
    if ($code -ne 0) { return $code }
    Write-Log "Waiting for the API and sign-in to be ready (the database upgrade and the built-in models come first)..."
    $started = Get-Date
    $ready = Wait-Core
    if ($WaitAll) {          # --wait-all: the rest now, in this window, and wait until everything is up
        Invoke-Later
        Wait-All
        return 0
    }
    Start-Later
    Write-Log "(To wait for everything instead: .\eax up --wait-all.)"
    if ($ready) {
        Write-Log "EA Explorer is ready after $([int]((Get-Date) - $started).TotalSeconds) s: you can sign in." "Green"
        Write-Log "Still starting in the background: Reports, Documents, Diagrams and the sample data; the screens show each in red, amber or green (down, starting, up)." "Green"
    }
    return 0
}
# start-later: the second tier (run by Start-Later): the rest without touching the core, then the switched-off ones created
function Invoke-Later {
    $t = Get-Tiers
    if ($t.Later.Count -gt 0) {
        Write-Log "Starting after the core (D255): $($t.Later -join ', ')"
        Invoke-Compose (@("up", "-d", "--build", "--no-deps") + $t.Later) -NoThrow | Out-Null
    }
    if ($t.Off.Count -gt 0) {
        Invoke-Compose (@("create", "--build") + $t.Off) -NoThrow | Out-Null
        Invoke-Compose (@("stop") + $t.Off) -NoThrow -Quiet | Out-Null
    }
    Write-Log "Everything is started."
}
# the file systems after the containers (owner, 8 Nov 2026): Docker's disk and the work and backups folders, read by
# the operations helper; and this computer's drive the project sits on, read here (so it shows with the helper down too)
function Show-FileSystems {
    Write-Log ""
    $ops = @(& docker @(Get-ComposeArgs @("ps", "--status", "running", "-q", "ops")) 2>$null | Where-Object { $_ })
    if ($ops.Count -gt 0) {
        & docker @(Get-ComposeArgs @("exec", "-T", "ops", "python3", "/app/ops.py", "filesystems")) 2>$null | ForEach-Object { Write-Log $_ }
    } else {
        Write-Log "File systems: the operations helper is not running, so Docker's disk is not read (docker system df below)." "Yellow"
        & docker system df 2>$null | ForEach-Object { Write-Log "  $_" }
    }
    try {
        $drive = Get-PSDrive -Name ((Split-Path -Qualifier $PSScriptRoot).TrimEnd(":")) -ErrorAction Stop
        $total = $drive.Used + $drive.Free
        if ($total -gt 0) {
            $pct = [math]::Round($drive.Used / $total * 100, 1)
            $color = if ($pct -ge 90) { "Red" } elseif ($pct -ge 80) { "Yellow" } else { "" }
            Write-Log ("  This computer's drive {0}: {1:N1} GB, {2:N1} GB used, {3:N1} GB free ({4}% used)" -f $drive.Name, ($total / 1e9), ($drive.Used / 1e9), ($drive.Free / 1e9), $pct) $color
        }
    } catch { }
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
    Show-TemplatesHint
}
# one-time admin task (phase 13, D262): the TOGAF template deliverables are bought or downloaded from The Open Group
# (publication I094) and kept in the library folder, never in git; shown until the folder has them
function Show-TemplatesHint {
    $dir = Get-Setting "EAX_LIBRARY_DIR" "./library"
    $togaf = Join-Path (Join-Path $dir "templates") "togaf"
    $have = @(Get-ChildItem -Path $togaf -Recurse -File -ErrorAction SilentlyContinue | Where-Object { $_.Extension -in @(".docx", ".doc", ".pptx", ".xlsx") })
    if ($have.Count -gt 0) { return }
    Write-Log ""
    Write-Log "One-time admin task: the TOGAF template deliverables (for architecture projects)" "Yellow"
    Write-Log "  1. Download 'The TOGAF Standard, 10th Edition - Template Deliverables' (The Open Group publication I094):" "Yellow"
    Write-Log "     https://publications.opengroup.org/i094" "Yellow"
    Write-Log "  2. Unzip it into $togaf, keeping its phase folders (the files stay on this computer; git ignores them)." "Yellow"
    Write-Log "     To use another folder, set EAX_LIBRARY_DIR in $EnvFile (it must hold templates\togaf) and run .\eax up." "Yellow"
    Write-Log "  3. As a Super Admin: Administration > Project library > Load templates from the folder." "Yellow"
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
        @("PostgreSQL Library",               "eax_library",                                  (Get-Setting "EAX_LIBRARY_DB_PASSWORD"),     "database eaxlibrary"),
        @("PostgreSQL Views",                 "eax_views",                                    (Get-Setting "EAX_VIEWS_DB_PASSWORD"),       "database eaxviews"),
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
        @("user_global_architect", "eax-user", "Architect on every model"),
        @("user_project_admin", "eax-user", "Project Admin of the sample architecture project (runs its setup and people)"),
        @("user_lead_architect", "eax-user", "Lead Architect of the sample architecture project"),
        @("user_stakeholder", "eax-user", "Stakeholder of the sample architecture project (reads; approves documents in 13.1)")
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
# The help is read from eaxcli\help.txt, the one source for every form of eax (D331; tests/test_eax_help.py):
# Show-Help prints the overview, one command in full (Show-Help stop) or everything (Show-Help --all).
function Get-HelpText([string]$Name, [string]$Arg = "") {
    $src = [System.IO.File]::ReadAllLines((Join-Path $PSScriptRoot "eaxcli\help.txt"), [System.Text.Encoding]::UTF8)
    $intro = New-Object 'System.Collections.Generic.List[string]'
    $footer = New-Object 'System.Collections.Generic.List[string]'
    $sections = New-Object 'System.Collections.Generic.List[object]'
    $internal = New-Object 'System.Collections.Generic.List[object]'
    $where = "intro"; $cmd = $null
    foreach ($raw in $src) {
        $line = $raw.TrimEnd()
        if ($line.StartsWith(";")) { continue }
        if ($line -match '^\[(win|unix|ps1|sh|py)\]') {
            if ($Matches[1] -notin @("ps1", "win")) { continue }
            $line = $line.Substring($Matches[0].Length); if ($line.StartsWith(" ")) { $line = $line.Substring(1) }
        }
        if ($where -eq "footer") { $footer.Add($line); continue }
        if ($line -eq "@footer") { $where = "footer"; continue }
        if ($line.StartsWith("@internal ")) {
            $r = $line.Substring(10); $p = $r.IndexOf(" ")
            $internal.Add(@{ Name = $r.Substring(0, $p); What = $r.Substring($p + 1) }); continue
        }
        if ($line.StartsWith("## ")) {
            $sections.Add(@{ Title = $line.Substring(3); Notes = (New-Object 'System.Collections.Generic.List[string]'); Cmds = (New-Object 'System.Collections.Generic.List[object]') })
            $where = "section"; $cmd = $null; continue
        }
        if ($line.StartsWith("### ")) {
            $r = $line.Substring(4); $p = $r.IndexOf(" ")
            $names = if ($p -ge 0) { $r.Substring(0, $p) } else { $r }
            $cmd = @{ Names = @($names -split '\|'); Args = $(if ($p -ge 0) { $r.Substring($p + 1) } else { "" }); Summary = "";
                      Detail = (New-Object 'System.Collections.Generic.List[string]'); Examples = (New-Object 'System.Collections.Generic.List[string]') }
            $sections[$sections.Count - 1].Cmds.Add($cmd); continue
        }
        if ($where -eq "intro") { if ($line) { $intro.Add($line) }; continue }
        if ($line.StartsWith(": ") -and $null -eq $cmd) { $sections[$sections.Count - 1].Notes.Add($line.Substring(2)); continue }
        if ($null -eq $cmd) { continue }
        if ($line.StartsWith("> ")) { $cmd.Summary = $line.Substring(2) }
        elseif ($line.StartsWith('$ ')) { $cmd.Examples.Add($line.Substring(2)) }
        elseif ($line) { $cmd.Detail.Add($line) }
    }
    while ($footer.Count -gt 0 -and -not $footer[$footer.Count - 1]) { $footer.RemoveAt($footer.Count - 1) }
    $block = {
        param($c)
        $h = "  " + ((@($c.Names[0], $c.Args) | Where-Object { $_ }) -join " ")
        if ($c.Names.Count -gt 1) { $h += "   (also: " + (($c.Names | Select-Object -Skip 1) -join ", ") + ")" }
        $b = @($h, ("    " + $c.Summary))
        foreach ($d in $c.Detail) { $b += "    " + $d }
        if ($c.Examples.Count -gt 0) { $b += "    Examples:"; foreach ($e in $c.Examples) { $b += "      " + $e } }
        , $b
    }
    $out = @(); $code = 0
    $all = @(); foreach ($s in $sections) { foreach ($c in $s.Cmds) { $all += , @($s, $c) } }
    if ($Name -eq "--groups") {
        for ($i = 0; $i -lt $sections.Count; $i++) { $out += ("{0,4}  {1}" -f ($i + 1), $sections[$i].Title) }
    } elseif ($Name -eq "--group") {
        $n = 0; if ($Arg -match '^[0-9]+$') { $n = [int]$Arg }
        if ($n -lt 1 -or $n -gt $sections.Count) { $out = @("No group $Arg."); $code = 1 }
        else {
            $s = $sections[$n - 1]; $out += $s.Title
            foreach ($x in $s.Notes) { $out += "  " + $x }
            foreach ($c in $s.Cmds) { $out += ""; $out += & $block $c }
        }
    } elseif ($Name -eq "--search") {
        $w = $Arg.ToLower(); $found = $false
        foreach ($pair in $all) {
            $c = $pair[1]
            $t = ((@($c.Names) + @($c.Args, $c.Summary) + @($c.Detail) + @($c.Examples)) -join " ").ToLower()
            if ($w -and $t.Contains($w)) { if ($found) { $out += "" }; $out += & $block $c; $found = $true }
        }
        if (-not $found) { $out = @("Nothing found for '$Arg'."); $code = 1 }
    } elseif (-not $Name -or $Name -eq "--all") {
        $out += $intro
        foreach ($s in $sections) {
            $out += ""; $out += $s.Title
            foreach ($n in $s.Notes) { $out += "  " + $n }
            foreach ($c in $s.Cmds) {
                if ($Name) { $out += ""; $out += & $block $c; continue }
                $lab = (@(($c.Names -join ", "), $c.Args) | Where-Object { $_ }) -join " "
                if ($lab.Length -le 20) { $out += "  " + $lab.PadRight(22) + $c.Summary }
                else { $out += "  " + $lab; $out += (" " * 24) + $c.Summary }
            }
        }
        if ($Name -and $internal.Count -gt 0) {
            $out += ""; $out += "Internal (run by eax itself; not for typing)"
            foreach ($i in $internal) { $out += "  " + $i.Name.PadRight(22) + $i.What }
        }
        $out += ""; $out += $footer
    } else {
        $found = $false
        foreach ($s in $sections) { foreach ($c in $s.Cmds) { if (-not $found -and $c.Names -contains $Name) { $out = & $block $c; $found = $true } } }
        if (-not $found) { foreach ($i in $internal) { if (-not $found -and $i.Name -eq $Name) { $out = @(("  " + $i.Name), ("    " + $i.What)); $found = $true } } }
        if (-not $found) { $out = @("No command '$Name'. Run {eax} help to list them."); $code = 1 }
    }
    $text = ($out -join "`n").Replace("{eax}", ".\eax")
    $text = [regex]::Replace($text, '\bwork/[^\s,;)]*', [System.Text.RegularExpressions.MatchEvaluator] { param($m) $m.Value.Replace("/", "\") })
    @{ Text = $text; Code = $code }
}

# eax document (D331): every command in full, from eaxcli\help.txt, as a web page (eaxcli\document.html with the help
# copied in; eaxpy and eax.sh make the same file) or in the console (a menu of the groups, page by page)
function Save-DocumentPage {
    $page = [System.IO.File]::ReadAllText((Join-Path $PSScriptRoot "eaxcli\document.html"), [System.Text.Encoding]::UTF8).Replace("`r`n", "`n")
    $help = [System.IO.File]::ReadAllText((Join-Path $PSScriptRoot "eaxcli\help.txt"), [System.Text.Encoding]::UTF8).Replace("`r`n", "`n")
    if ($help.EndsWith("`n")) { $help = $help.Substring(0, $help.Length - 1) }
    $html = $page.Replace("__FORM__", "ps1").Replace("__EAX__", ".\eax").Replace("__WINDOWS__", "true").Replace("__HELP__", $help)
    $dir = Join-Path $PSScriptRoot "work\docs"
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
    $out = Join-Path $dir "eax-commands.html"
    [System.IO.File]::WriteAllText($out, $html, (New-Object System.Text.UTF8Encoding $false))
    Write-Host "The commands as a web page: $out"
    if (-not $env:EAX_NO_BROWSER) { Start-Process $out }
}

function Show-Paged([string]$Text) {
    $rows = 22
    try { $rows = [Math]::Max(10, $Host.UI.RawUI.WindowSize.Height - 2) } catch { }
    $n = 0
    foreach ($line in ($Text -split "`n")) {
        Write-Host $line; $n++
        if ($n -ge $rows -and -not [Console]::IsOutputRedirected) { $n = 0; $k = Read-Host "-- Enter for more, q to stop --"; if ($k -eq "q") { break } }
    }
}

function Invoke-Document([string[]]$Options) {
    $mode = if ($Options -contains "--console") { "console" } elseif ($Options -contains "--web") { "web" } else { "" }
    if (-not $mode) {
        $a = Read-Host "Show the commands (1) here in the console or (2) as a web page in your browser? [1/2]"
        $mode = if ($a -in @("2", "w", "web")) { "web" } else { "console" }
    }
    if ($mode -eq "web") { Save-DocumentPage; return }
    while ($true) {
        Write-Host ""; Write-Host "EA Explorer commands (.\eax document)" -ForegroundColor Cyan
        Write-Host (Get-HelpText "--groups").Text
        $a = Read-Host "Number, s to search, q to quit"
        if ($null -eq $a -or $a -in @("q", "Q")) { return }
        if ($a -in @("s", "S")) { $w = Read-Host "Search for"; if ($null -eq $w) { return }; Show-Paged (Get-HelpText "--search" $w).Text }
        elseif ($a -match '^[0-9]+$') { Show-Paged (Get-HelpText "--group" $a).Text }
        elseif ($a) { Write-Host "Choose a number, s or q." }
    }
}

function Show-Help([string]$Name, [string]$Arg = "") {
    $h = Get-HelpText $Name $Arg
    Write-Host $h.Text
    return $h.Code
}

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
        # work\tools (uv and its Python, for eaxpy, D331) is kept either way
        if ($cert) { Get-ChildItem -Path $WorkDir -Force | Where-Object { $_.Name -ne "tools" } | Remove-Item -Recurse -Force }
        else {
            # keep work\data\tls: the local certificate you trusted with .\eax trust (D107)
            Get-ChildItem -Path $WorkDir -Force | Where-Object { $_.Name -notin @("data", "tools") } | Remove-Item -Recurse -Force
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
if ($Command -in @("help", "-h", "--help", "/?")) { exit (Show-Help $(if ($RestArgs.Count -gt 0) { $RestArgs[0] } else { "" }) $(if ($RestArgs.Count -gt 1) { $RestArgs[1] } else { "" })) }
if ($Rest | Where-Object { $_ -in @("--help", "-h", "/?") }) { exit (Show-Help $AskedFor) }   # <command> --help: that command's help
# restart: down, then up, each as its own run of this script (own log); the data is kept
if ($Command -eq "restart") {
    [string[]]$up = @("up")
    if ($WaitAll) { $up += "--wait-all" }
    foreach ($step in @(, @("down")) + @(, $up)) {
        Write-Host ""
        Write-Host "=== .\eax $($step -join ' ')" -ForegroundColor Cyan
        & $PSCommandPath @step
        if ($LASTEXITCODE -ne 0) {
            Write-Host "ERROR: .\eax $($step -join ' ') failed (exit $LASTEXITCODE); restart stopped there." -ForegroundColor Red
            exit $LASTEXITCODE
        }
    }
    exit 0
}
# clean-run and clean-debug: cleanup --all --yes, init, then up or debug, each as its own run of
# this script (so each step writes its own log, like typing the three commands)
# clean-restart: down first (when there is a config file to find the containers by), then the same
if ($Command -in @("clean-run", "clean-debug", "clean-restart")) {
    $kind = if ($RestArgs.Count -gt 0) { $RestArgs[0] } else { "laptop" }
    $last = if ($Command -eq "clean-debug") { "debug" } else { "up" }
    # built as an array on purpose: an if-expression would turn @("up") into the string "up", and splatting a string
    # passes its letters one by one ("u")
    [string[]]$finish = @($last)
    if ($WaitAll) { $finish += "--wait-all" }
    $steps = @(@("cleanup", "--all", "--yes"), @("init", $kind), $finish)
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
# the console (phase 13.5, D330): a numbered menu for getting a system that is down back up. It runs in the operations
# helper (services/ops/console.py); what needs this machine (start, stop, diagnostics, any eax command) it hands back here
# by its exit code. No sign-in: being on the machine is the trust. With --server: another installation, through its API.
function Invoke-Console([string[]]$Options) {
    if ($Options -contains "--server") {
        Assert-Docker
        & docker @(Get-ComposeArgs (@("run", "--rm", "--no-deps", "api", "python", "-m", "eax.console_cli", "remote") + $Options))
        return
    }
    $stopped = $false            # after Stop everything, nothing is started again until asked (1 below)
    while ($true) {
        $old = $ErrorActionPreference; $ErrorActionPreference = "Continue"
        & docker info --format "{{.ServerVersion}}" 2>&1 | Out-Null
        $dockerOk = ($LASTEXITCODE -eq 0)
        $code = 99
        if ($dockerOk -and (Test-Path $EnvFile) -and -not $stopped) {
            # built first: an ops image from before the console has no console.py (a rebuild takes seconds when nothing changed)
            Write-Host "Starting the console (the operations helper; the first time it is built, a minute)..." -ForegroundColor DarkGray
            & docker @(Get-ComposeArgs @("up", "-d", "--build", "--no-deps", "ops")) 2>&1 | Out-Null
            if ($LASTEXITCODE -eq 0) {
                & docker @(Get-ComposeArgs @("exec", "ops", "python3", "/app/console.py", "--version", (Get-Version)))
                $code = $LASTEXITCODE
                # anything but the console's own answers (it failed): the basic menu, not the same failure again
                if ($code -notin @(0, 20, 21, 23, 25)) {
                    Write-Host "The console stopped with an error (exit $code); the basic menu follows. Its log: work\logs\console-*.log" -ForegroundColor Yellow
                    $code = 99
                }
            }
        }
        $ErrorActionPreference = $old
        if ($code -eq 99) {          # the helper could not start: only what this machine can do
            Write-Host ""
            Write-Host "EA Explorer console (basic: $(if ($stopped) { 'everything is stopped' } else { 'the operations helper is not running' }))" -ForegroundColor Cyan
            if (-not $dockerOk) { Write-Host "Docker Desktop is not running: start it, wait for 'Engine running', then choose 1." -ForegroundColor Yellow }
            elseif (-not (Test-Path $EnvFile)) { Write-Host "Not set up yet: there is no $EnvFile. Run .\eax init laptop first." -ForegroundColor Yellow }
            Write-Host "  1  Start everything"; Write-Host "  2  Save a diagnostics file for support"
            Write-Host "  c  Command prompt (every eax command)"; Write-Host "  q  Quit"
            $a = Read-Host "Choose"
            $code = switch ($a) { "1" { 20 } "2" { 23 } "c" { 25 } "q" { 0 } default { 98 } }
        }
        switch ($code) {
            0 { return }
            20 { $stopped = $false; & $PSCommandPath up }
            21 { & $PSCommandPath down; $stopped = $true }
            23 { & $PSCommandPath diag }
            25 {
                Write-Host "Type an eax command (for example: logs api, services, backups). Empty or back: the menu." -ForegroundColor Cyan
                while ($true) {
                    $line = Read-Host "eax"
                    if (-not $line -or $line -in @("back", "b", "menu")) { break }
                    $words = @($line -split "\s+" | Where-Object { $_ })
                    if ($words[0] -eq "console") { Write-Host "You are in the console already."; continue }
                    & $PSCommandPath @words
                }
            }
            default { }
        }
    }
}
if ($Command -eq "console") {
    try { Invoke-Console $RestArgs; exit 0 }
    catch { Write-Host "ERROR: $($_.Exception.Message)" -ForegroundColor Red; exit 1 }
}
if ($Command -in @("deploy", "secrets")) {
    # phase 36 (D498, D504): one Python program for every form (D500); eaxpy.ps1 fetches uv and Python into work\tools
    & (Join-Path $PSScriptRoot "eaxpy.ps1") $Command @RestArgs
    exit $LASTEXITCODE
}
if ($Command -eq "document") {
    try { Invoke-Document $RestArgs; exit 0 }
    catch { Write-Host "ERROR: $($_.Exception.Message)" -ForegroundColor Red; exit 1 }
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
    if ($Command -in @("check", "up", "start-later", "debug", "status", "logs", "down", "backup", "backups", "restore", "restores", "restore-log",
                       "delete-backup", "delete-restore", "app-backup", "restore-model", "restore-app", "stop-backup", "services", "service", "import", "update", "rollback", "test", "standby")) { Assert-Docker }
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
        "start-later" { Invoke-Later }
        "debug" {
            $code = Invoke-Up $RestArgs -NoThrow
            if ($code -ne 0) { Write-Log "docker compose up failed (exit $code); recording what is running anyway." "Red" }
            Save-Diagnostics
            if ($RestArgs.Count -gt 0) { Show-PartUrls $RestArgs } else { Show-Urls; Show-Logins }
            Watch-Containers $RestArgs
        }
        "diag"    { Save-Diagnostics }
        "status"  { Invoke-Compose @("ps", "-a") | Out-Null; Show-FileSystems }
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
        "import" { Invoke-Interactive @("api", "python", "-m", "eax.deliveries_cli") $RestArgs }
        "update" { Start-BackupHelpers; Invoke-Interactive @("ops", "python3", "/app/ops.py", "update") $RestArgs }      # phase 36, D417
        "rollback" { Start-BackupHelpers; Invoke-Interactive @("ops", "python3", "/app/ops.py", "rollback") $RestArgs }
        "restore-model" { Invoke-Interactive @("api", "python", "-m", "eax.backups_cli", "restore") $RestArgs }
        "test" {     # test automation (phase 36.1, D367): builds the test runner, then the operations helper runs it
            Invoke-Compose @("--profile", "test", "build", "testrunner") | Out-Null
            Start-BackupHelpers
            Invoke-Interactive @("ops", "python3", "/app/ops.py", "test") ($RestArgs + @("--version", (Get-Version)))
        }
        "standby" {  # the database standby (phase 36.3, D527; EAX_COMPOSE_EXTRA=standby)
            $what = if ($RestArgs.Count -gt 0) { $RestArgs[0] } else { "status" }
            if ($what -eq "status") {
                Invoke-Interactive @("db", "psql", "-U", "postgres", "-c") @("SELECT client_addr, state, sync_state, replay_lag FROM pg_stat_replication")
                Invoke-Interactive @("db-standby", "psql", "-U", "postgres", "-c") @("SELECT pg_is_in_recovery() AS following_the_primary, now() - pg_last_xact_replay_timestamp() AS behind_by")
            } elseif ($what -eq "promote") {
                Write-Log "The standby becomes the primary: it stops following and accepts changes. Then set EAX_DB_HOST=db-standby (or the standby's host) and run .\eax up." "Yellow"
                if ((Read-Host "Type PROMOTE to go on") -ne "PROMOTE") { Write-Log "Nothing changed."; return }
                Invoke-Interactive @("-u", "postgres", "db-standby", "pg_ctl", "promote", "-D") @("/var/lib/postgresql/data")
            } else { throw "Usage: .\eax standby status|promote" }
        }
        "services" { Show-Services }
        "servers" {
            if ($RestArgs.Count -lt 1) {
                Write-Log "API and job servers wanted: $(Get-ApiServers) (EAX_API_SERVERS). Running:"
                Invoke-Compose @("ps", "api") | Out-Null
            } else {
                $n = 0
                if (-not [int]::TryParse($RestArgs[0], [ref]$n) -or $n -lt 1 -or $n -gt 16) { throw "Usage: .\eax servers <1 to 16>" }
                $history = Join-Path $WorkDir "config-history"
                New-Item -ItemType Directory -Force -Path $history | Out-Null
                Copy-Item $EnvFile (Join-Path $history "eaexplorer.env.$((Get-Date).ToUniversalTime().ToString('yyyyMMdd-HHmmss')).$($env:USERNAME -replace '[^A-Za-z0-9_.-]', '-').servers-$n")
                $lines = @(Get-Content $EnvFile)
                if ($lines | Where-Object { $_ -match "^\s*EAX_API_SERVERS\s*=" }) { $lines = $lines | ForEach-Object { if ($_ -match "^\s*EAX_API_SERVERS\s*=") { "EAX_API_SERVERS=$n" } else { $_ } } }
                else { $lines += @("", "# ---- API and job servers (D249)", "EAX_API_SERVERS=$n") }
                [System.IO.File]::WriteAllText((Join-Path $PSScriptRoot $EnvFile), (($lines -join "`n") + "`n"), $Utf8)
                Write-Log "Running $n API and job server(s); stopping a server lets the jobs it runs finish first."
                Invoke-Compose @("up", "-d", "--no-deps", "--no-recreate", "--scale", "api=$n", "api") | Out-Null
            }
        }
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
