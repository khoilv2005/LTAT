param(
    [string]$Model = "deepseek-v4-flash:cloud",
    [string]$ApiUrl = "https://ollama.com/api/chat",
    [int]$MonitorMinutes = 30,
    [int]$Expected = 33438
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$envVars = [Environment]::GetEnvironmentVariables()
if ($envVars.Contains("Path") -and $envVars.Contains("PATH")) {
    [Environment]::SetEnvironmentVariable("PATH", $null, "Process")
}

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

$Python = Join-Path $Root "venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    $Python = "python"
}

$LogRoot = Join-Path $Root "results\run_logs"
New-Item -ItemType Directory -Force -Path $LogRoot | Out-Null
$StatusFile = Join-Path $LogRoot "task1_title_adaptive_status.jsonl"
$StdoutFile = Join-Path $LogRoot "task1_title_adaptive_stdout.log"
$StderrFile = Join-Path $LogRoot "task1_title_adaptive_stderr.log"
$ResultFile = Join-Path $Root "results\title_title_itape_few-shot_test.json"

$Configs = @(
    @{ rate = 30; concurrent = 4; saveEvery = 20 },
    @{ rate = 20; concurrent = 3; saveEvery = 20 },
    @{ rate = 10; concurrent = 2; saveEvery = 20 }
)

function Get-ResultStats {
    if (-not (Test-Path $ResultFile)) {
        return @{ count = 0; unique = 0; errors = 0; remaining = $Expected }
    }
    $script = @"
import json
from pathlib import Path
p=Path(r'$ResultFile')
data=json.loads(p.read_text(encoding='utf-8'))
ids=[str(x.get('id')) for x in data if isinstance(x,dict)]
errs=sum(1 for x in data if isinstance(x,dict) and isinstance(x.get('response'),dict) and 'error' in x.get('response',{}))
print(len(data), len(set(ids)), errs)
"@
    $raw = & $Python -c $script
    $parts = "$raw".Trim().Split(" ")
    $unique = [int]$parts[1]
    return @{
        count = [int]$parts[0]
        unique = $unique
        errors = [int]$parts[2]
        remaining = [Math]::Max(0, $Expected - $unique)
    }
}

function Write-Status {
    param([hashtable]$Status)
    $Status.timestamp = (Get-Date).ToString("o")
    $Status | ConvertTo-Json -Compress | Add-Content -Path $StatusFile -Encoding UTF8
}

function Start-Task1Process {
    param([hashtable]$Config)
    $args = @(
        "run.py",
        "--task", "title",
        "--dataset", "title_itape",
        "--method", "few-shot",
        "--TEST", "test",
        "--testNum", "0",
        "--api_url", $ApiUrl,
        "--model", $Model,
        "--max_requests_per_minute", "$($Config.rate)",
        "--max_tokens_per_minute", "1000000",
        "--max_attempts", "10",
        "--max_concurrent_requests", "$($Config.concurrent)",
        "--save_every", "$($Config.saveEvery)",
        "--response_max_token", "32"
    )
    return Start-Process -FilePath $Python -ArgumentList $args -WorkingDirectory $Root -RedirectStandardOutput $StdoutFile -RedirectStandardError $StderrFile -WindowStyle Hidden -PassThru
}

$configIndex = 0
while ($true) {
    $stats = Get-ResultStats
    if ($stats.unique -ge $Expected) {
        Write-Status @{ event = "complete"; stats = $stats }
        break
    }

    if ($configIndex -ge $Configs.Count) {
        $configIndex = $Configs.Count - 1
    }
    $config = $Configs[$configIndex]
    Write-Status @{ event = "start"; config = $config; stats = $stats }
    $proc = Start-Task1Process -Config $config

    while ($true) {
        Start-Sleep -Seconds ($MonitorMinutes * 60)
        $newStats = Get-ResultStats
        $delta = $newStats.unique - $stats.unique
        $alive = $null -ne (Get-Process -Id $proc.Id -ErrorAction SilentlyContinue)
        Write-Status @{ event = "monitor"; pid = $proc.Id; config = $config; stats = $newStats; delta = $delta; alive = $alive }

        if ($newStats.unique -ge $Expected) {
            if ($alive) { Stop-Process -Id $proc.Id -Force }
            Write-Status @{ event = "complete"; stats = $newStats }
            exit 0
        }

        if (-not $alive) {
            Write-Status @{ event = "process_exited"; pid = $proc.Id; config = $config; stats = $newStats }
            $stats = $newStats
            break
        }

        # If high-rate config makes poor progress over one monitor window, lower it.
        if ((($delta -lt 50) -or ($newStats.errors -gt $stats.errors)) -and $configIndex -lt ($Configs.Count - 1)) {
            Stop-Process -Id $proc.Id -Force
            Write-Status @{ event = "downgrade"; pid = $proc.Id; from = $config; stats = $newStats; delta = $delta }
            $configIndex += 1
            $stats = $newStats
            break
        }

        $stats = $newStats
    }
}
