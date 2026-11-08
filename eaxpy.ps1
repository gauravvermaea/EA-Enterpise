<#
EA Explorer launcher, the Python version (phase 13.9, D331). Windows; Linux and macOS: eaxpy.sh.
It fetches uv (one small program) into work\tools the first time, and uv fetches the Python it needs into
work\tools\python; then it runs eaxpy.py. Nothing is installed elsewhere on the computer. cleanup keeps work\tools.
Another uv (an offline server, say): set EAX_UV to its full path. Another uv version: set EAX_UV_VERSION.
#>
$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot
$Tools = Join-Path $Root "work\tools"
$Version = if ($env:EAX_UV_VERSION) { $env:EAX_UV_VERSION } else { "0.9.5" }
$Uv = if ($env:EAX_UV) { $env:EAX_UV } else { Join-Path $Tools "uv.exe" }
if (-not (Test-Path $Uv)) {
    $arch = if ($env:PROCESSOR_ARCHITECTURE -eq "ARM64") { "aarch64" } else { "x86_64" }
    $url = "https://github.com/astral-sh/uv/releases/download/$Version/uv-$arch-pc-windows-msvc.zip"
    Write-Host "First run: fetching uv $Version into work\tools (once; it then fetches Python 3.12 there too)..." -ForegroundColor Cyan
    New-Item -ItemType Directory -Force -Path $Tools | Out-Null
    $zip = Join-Path $Tools "uv.zip"
    try {
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        $ProgressPreference = "SilentlyContinue"
        Invoke-WebRequest -Uri $url -OutFile $zip -UseBasicParsing
        $unpacked = Join-Path $Tools "uv-unpacked"
        Expand-Archive -Path $zip -DestinationPath $unpacked -Force
        Get-ChildItem -Path $unpacked -Recurse -Include "uv.exe", "uvx.exe" | Copy-Item -Destination $Tools -Force
        Remove-Item -Recurse -Force $unpacked, $zip
    } catch {
        Write-Host "ERROR: could not fetch uv from $url ($($_.Exception.Message))." -ForegroundColor Red
        Write-Host "Without internet: download that file elsewhere, put uv.exe into work\tools, or set EAX_UV to a uv.exe." -ForegroundColor Yellow
        exit 1
    }
}
# uv keeps its Python and its cache in work\tools, not in the user's profile
$env:UV_PYTHON_INSTALL_DIR = Join-Path $Tools "python"
$env:UV_CACHE_DIR = Join-Path $Tools "cache"
$env:UV_PYTHON_PREFERENCE = "only-managed"
& $Uv run --no-project --quiet --python 3.12 (Join-Path $Root "eaxpy.py") @args
exit $LASTEXITCODE
