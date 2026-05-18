# Run all self-heuristic experiments sequentially
# Usage: .\run_all_cvss.ps1

# CVSS datasets
$cvssDatasets = @("AV", "AC", "PR", "UI")

# SBRP datasets
$sbrpDatasets = @("Ambari", "Camel", "Chromium", "Derby", "Wicket")

# Run CVSS tasks
foreach ($dataset in $cvssDatasets) {
    Write-Host "==========================================" -ForegroundColor Cyan
    Write-Host "Running: CVSS $dataset" -ForegroundColor Cyan
    Write-Host "==========================================" -ForegroundColor Cyan

    python run_self_heuristic.py --task cvss --dataset $dataset --testNum 0

    if ($LASTEXITCODE -eq 0) {
        Write-Host "SUCCESS: CVSS $dataset completed" -ForegroundColor Green
    } else {
        Write-Host "FAILED: CVSS $dataset failed" -ForegroundColor Red
    }
    Write-Host ""
}

# Run SBRP tasks
foreach ($dataset in $sbrpDatasets) {
    Write-Host "==========================================" -ForegroundColor Cyan
    Write-Host "Running: SBRP $dataset" -ForegroundColor Cyan
    Write-Host "==========================================" -ForegroundColor Cyan

    python run_self_heuristic.py --task sbrp --dataset $dataset --testNum 0

    if ($LASTEXITCODE -eq 0) {
        Write-Host "SUCCESS: SBRP $dataset completed" -ForegroundColor Green
    } else {
        Write-Host "FAILED: SBRP $dataset failed" -ForegroundColor Red
    }
    Write-Host ""
}

Write-Host "==========================================" -ForegroundColor Green
Write-Host "ALL EXPERIMENTS COMPLETED" -ForegroundColor Green
Write-Host "==========================================" -ForegroundColor Green

# Shutdown PC after completion
Write-Host "Shutting down PC in 60 seconds..." -ForegroundColor Yellow
Write-Host "Press Ctrl+C to cancel" -ForegroundColor Yellow
shutdown /s /t 60
