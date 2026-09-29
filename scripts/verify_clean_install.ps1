<#
  Proves that the README's setup instructions work from scratch.

  It clones the COMMITTED repository into a temp folder (so uncommitted files and your own .env cannot hide a problem),
  creates a fresh virtual environment, starts a SEPARATE PostgreSQL container on another port, then runs the same steps as the README:
  generate data, load, run the whole test suite. Everything is removed afterwards.

  Usage (from the project root):   powershell -ExecutionPolicy Bypass -File scripts/verify_clean_install.ps1
  Needs: Git, Python 3, Docker Desktop running. Takes about 5-8 minutes (mostly pip install).
#>
param([string]$Port = "5544")
$ErrorActionPreference = "Stop"
$source = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$work = Join-Path $env:TEMP ("retail_verify_" + [guid]::NewGuid().ToString("N").Substring(0, 8))
$project = "retail_verify"
$container = "retail_pg_verify"
$started = Get-Date

function Step($text) { Write-Host "`n=== $text" -ForegroundColor Cyan }

git clone --quiet $source $work
Set-Location $work
$ok = $false
try {
    Step "1/6 create virtual environment and install requirements"
    python -m venv .venv
    & .\.venv\Scripts\python.exe -m pip install --quiet --disable-pip-version-check -r requirements.txt

    Step "2/6 create .env (random password, port $Port)"
    $pw = -join ((48..57) + (65..90) + (97..122) | Get-Random -Count 20 | ForEach-Object { [char]$_ })
    @"
DATABASE_HOST=localhost
DATABASE_PORT=$Port
DATABASE_NAME=retail_analytics
DATABASE_USER=retail_user
DATABASE_PASSWORD=$pw
"@ | Set-Content .env -Encoding ascii

    Step "3/6 start PostgreSQL (docker compose up -d --wait)"
    $env:CONTAINER_NAME = $container
    docker compose -p $project up -d --wait

    Step "4/6 generate synthetic data"
    & .\.venv\Scripts\python.exe scripts/generate_data.py

    Step "5/6 load database (schema, COPY, views, indexes)"
    & .\.venv\Scripts\python.exe scripts/load_data.py

    Step "6/6 run the full test suite"
    & .\.venv\Scripts\python.exe -m pytest tests -q
    if ($LASTEXITCODE -ne 0) { throw "tests failed" }
    $ok = $true
}
finally {
    Step "cleanup"
    # Docker writes normal progress text ("Container ... Stopping") to stderr. Under $ErrorActionPreference = "Stop"
    # PowerShell would treat that as a failure and skip the rest of the cleanup, so relax it for this block only.
    $ErrorActionPreference = "Continue"
    $env:CONTAINER_NAME = $container
    docker compose -p $project down -v *> $null
    Remove-Item Env:\CONTAINER_NAME -ErrorAction SilentlyContinue
    Set-Location $source
    Remove-Item -Recurse -Force $work -ErrorAction SilentlyContinue
}
$minutes = [math]::Round(((Get-Date) - $started).TotalMinutes, 1)
if ($ok) { Write-Host "`nCLEAN INSTALL VERIFIED in $minutes minutes." -ForegroundColor Green; exit 0 }
else { Write-Host "`nCLEAN INSTALL FAILED after $minutes minutes." -ForegroundColor Red; exit 1 }
