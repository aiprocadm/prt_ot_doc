param(
  [string]$EnvFile = "e2e.env"
)

$ErrorActionPreference = "Stop"

function Set-EnvFromFile {
  param([string]$Path)

  if (-not (Test-Path -Path $Path)) {
    throw "Env file not found: $Path. Create it from e2e.env.example."
  }

  Get-Content -Path $Path | ForEach-Object {
    $line = $_.Trim()
    if ([string]::IsNullOrWhiteSpace($line)) { return }
    if ($line.StartsWith("#")) { return }
    $parts = $line -split "=", 2
    if ($parts.Length -ne 2) { return }
    $key = $parts[0].Trim()
    $value = $parts[1]
    [System.Environment]::SetEnvironmentVariable($key, $value, "Process")
  }
}

Set-EnvFromFile -Path $EnvFile

if (-not $env:E2E_START_SERVER -and -not $env:E2E_BASE_URL) {
  throw "Set E2E_START_SERVER=1 or E2E_BASE_URL in $EnvFile."
}

if (-not $env:E2E_USER_EMAIL -or -not $env:E2E_USER_PASSWORD) {
  throw "Set E2E_USER_EMAIL and E2E_USER_PASSWORD in $EnvFile."
}

npm run e2e:key-scenarios
