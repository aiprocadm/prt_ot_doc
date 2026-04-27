param(
    [switch]$PreflightOnly,
    [switch]$AutoKillPorts
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RootDir = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $RootDir

$ArgsList = @(".\scripts\dev_lite.py")
if ($PreflightOnly) {
    $ArgsList += "--preflight-only"
}
if ($AutoKillPorts) {
    $ArgsList += "--auto-kill-ports"
}

if (Get-Command py -ErrorAction SilentlyContinue) {
    py -3 @ArgsList
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    python @ArgsList
} else {
    throw "Python not found. Install Python 3.12+."
}
