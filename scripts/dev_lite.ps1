Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Invoke-Checked {
    param(
        [Parameter(Mandatory = $true)]
        [string]$FilePath,
        [Parameter(Mandatory = $false)]
        [string[]]$Arguments = @()
    )

    & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed ($LASTEXITCODE): $FilePath $($Arguments -join ' ')"
    }
}

$RootDir = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $RootDir

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
}

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    py -3 -m venv .venv
}

$Python = ".\.venv\Scripts\python.exe"
$Pip = ".\.venv\Scripts\pip.exe"

# Configure dockerless defaults in .env (same behavior as configure_dockerless_env.sh).
$envUpdates = [ordered]@{
    APP_RUN_MODE = "dockerless"
    DATABASE_URL = "sqlite+aiosqlite:///./dev.db"
    STORAGE_BACKEND = "local"
    S3_BACKEND = "local"
    STORAGE_ROOT = "./.local_storage"
    CELERY_EAGER = "true"
    REDIS_URL = "memory://"
    REDIS_RESULT_URL = "memory://"
    RATE_LIMIT_STORAGE_URI = "memory://"
    ENABLE_METRICS = "false"
    LIBREOFFICE_BIN = "python"
    DEMO_BOOTSTRAP = "0"
}

$lines = Get-Content ".env"
$seen = @{}
$newLines = New-Object System.Collections.Generic.List[string]
foreach ($line in $lines) {
    if ([string]::IsNullOrWhiteSpace($line) -or $line.TrimStart().StartsWith("#") -or (-not $line.Contains("="))) {
        $newLines.Add($line)
        continue
    }
    $parts = $line.Split("=", 2)
    $key = $parts[0]
    if ($envUpdates.Contains($key)) {
        $newLines.Add("$key=$($envUpdates[$key])")
        $seen[$key] = $true
    } else {
        $newLines.Add($line)
    }
}
foreach ($key in $envUpdates.Keys) {
    if (-not $seen.ContainsKey($key)) {
        $newLines.Add("$key=$($envUpdates[$key])")
    }
}
Set-Content -Path ".env" -Value $newLines -Encoding UTF8

$ReqStamp = ".venv\.requirements.stamp"
if ((-not (Test-Path $ReqStamp)) -or ((Get-Item "requirements.txt").LastWriteTimeUtc -gt (Get-Item $ReqStamp).LastWriteTimeUtc) -or ((Get-Item "requirements-dev.txt").LastWriteTimeUtc -gt (Get-Item $ReqStamp).LastWriteTimeUtc)) {
    Invoke-Checked -FilePath $Python -Arguments @("-m", "pip", "install", "--upgrade", "pip")
    Invoke-Checked -FilePath $Python -Arguments @("-m", "pip", "install", "-r", "requirements.txt", "-r", "requirements-dev.txt")
    New-Item -Path $ReqStamp -ItemType File -Force | Out-Null
} else {
    Write-Host "Python dependencies are up to date (.venv)."
}

$FrontendStamp = "frontend\.npm-ci.stamp"
$ViteCmd = "frontend\node_modules\.bin\vite.cmd"
if ((-not (Test-Path "frontend\node_modules")) -or (-not (Test-Path $FrontendStamp)) -or (-not (Test-Path $ViteCmd)) -or ((Get-Item "frontend\package-lock.json").LastWriteTimeUtc -gt (Get-Item $FrontendStamp).LastWriteTimeUtc)) {
    Push-Location "frontend"
    try {
        Invoke-Checked -FilePath "npm" -Arguments @("ci")
    } catch {
        Write-Warning "npm ci failed; cleaning node_modules and retrying once."
        if (Test-Path "node_modules") {
            Remove-Item "node_modules" -Recurse -Force
        }
        Invoke-Checked -FilePath "npm" -Arguments @("ci")
    }
    Pop-Location
    New-Item -Path $FrontendStamp -ItemType File -Force | Out-Null
} else {
    Write-Host "Frontend dependencies are up to date (frontend/node_modules)."
}

$env:APP_RUN_MODE = "dockerless"
$env:DATABASE_URL = "sqlite+aiosqlite:///./dev.db"
$env:STORAGE_BACKEND = "local"
$env:S3_BACKEND = "local"
$env:STORAGE_ROOT = "./.local_storage"
$env:CELERY_EAGER = "true"
$env:REDIS_URL = "memory://"
$env:REDIS_RESULT_URL = "memory://"
$env:RATE_LIMIT_STORAGE_URI = "memory://"
$env:ENABLE_METRICS = "false"
$env:LIBREOFFICE_BIN = $Python
$env:DEMO_BOOTSTRAP = "0"

if (($env:KEEP_DB -ne "1") -and (Test-Path "dev.db")) {
    Remove-Item "dev.db" -Force
}

Write-Host ""
Write-Host "Dockerless mode enabled"
Write-Host "- Database: $($env:DATABASE_URL)"
Write-Host "- Storage: $($env:STORAGE_BACKEND) ($($env:STORAGE_ROOT))"
Write-Host "- Celery eager: $($env:CELERY_EAGER)"
Write-Host "- Redis: disabled"
Write-Host ""
Write-Host "Backend:  http://localhost:8000"
Write-Host "Frontend: http://localhost:5173"
Write-Host ""

if (Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue) {
    throw "Backend port 8000 is already in use. Stop existing process and retry."
}
if (Get-NetTCPConnection -LocalPort 5173 -State Listen -ErrorAction SilentlyContinue) {
    throw "Frontend port 5173 is already in use. Stop existing process and retry."
}

$backend = Start-Process -FilePath $Python -ArgumentList ".\scripts\run_backend_lite.py" -PassThru -NoNewWindow

$backendReady = $false
for ($i = 0; $i -lt 60; $i++) {
    try {
        $resp = Invoke-WebRequest -Uri "http://127.0.0.1:8000/health" -UseBasicParsing -TimeoutSec 2
        if ($resp.StatusCode -eq 200) {
            $backendReady = $true
            break
        }
    } catch {
        Start-Sleep -Seconds 1
    }
}

if ($backendReady) {
    Write-Host "Backend ready: http://127.0.0.1:8000/health"
} else {
    Write-Warning "Backend health check timed out (continuing; inspect backend logs)."
}

Push-Location "frontend"
try {
    Invoke-Checked -FilePath "npm" -Arguments @("run", "dev", "--", "--host", "0.0.0.0", "--port", "5173")
} finally {
    Pop-Location
    if (-not $backend.HasExited) {
        Stop-Process -Id $backend.Id -Force
    }
}
