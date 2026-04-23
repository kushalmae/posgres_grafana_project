# Start Postgres + Grafana, then run the CSV ingestor from the repo root.
# Usage: .\start.ps1   (from this directory in PowerShell)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host "Starting Docker Compose (Postgres + Grafana)..." -ForegroundColor Cyan
docker compose up -d

Write-Host "Waiting for Postgres to accept connections..." -ForegroundColor Cyan
$ready = $false
for ($i = 0; $i -lt 45; $i++) {
    docker compose exec -T postgres pg_isready -U grafana_user -d local_csv_db 2>$null | Out-Null
    if ($LASTEXITCODE -eq 0) {
        $ready = $true
        break
    }
    Start-Sleep -Seconds 1
}
if (-not $ready) {
    Write-Host "Postgres did not become ready in time. Check: docker compose logs postgres" -ForegroundColor Red
    exit 1
}

Write-Host "Installing Python dependencies..." -ForegroundColor Cyan
python -m pip install -q -r requirements.txt

Write-Host ""
Write-Host "Grafana: http://localhost:3000  (admin / admin)" -ForegroundColor Green
Write-Host "Ingestor running — watching data/*.csv (Ctrl+C to stop)" -ForegroundColor Green
Write-Host ""

python scripts/ingest_csv_to_postgres.py
