param(
    [string]$Model = "deepseek-v4-flash:cloud",
    [string]$ApiUrl = "https://ollama.com/api/chat",
    [double]$Rate = 10,
    [double]$TokenRate = 1000000,
    [int]$MaxConcurrent = 2
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

$Python = Join-Path $Root "venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    $Python = "python"
}

$LogRoot = Join-Path $Root "results\run_logs"
New-Item -ItemType Directory -Force -Path $LogRoot | Out-Null
$StatusFile = Join-Path $LogRoot "full_deepseek_status.jsonl"

function Write-RunStatus {
    param([hashtable]$Status)
    $Status.timestamp = (Get-Date).ToString("o")
    $Status | ConvertTo-Json -Compress | Add-Content -Path $StatusFile -Encoding UTF8
}

function Invoke-Experiment {
    param(
        [string]$Name,
        [string[]]$Arguments
    )

    $LogPath = Join-Path $LogRoot "$Name.log"
    Write-RunStatus @{ event = "start"; job = $Name; log = $LogPath; args = $Arguments }
    $PreviousErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    & $Python @Arguments 2>&1 | Tee-Object -FilePath $LogPath -Append
    $ExitCode = $LASTEXITCODE
    $ErrorActionPreference = $PreviousErrorActionPreference
    Write-RunStatus @{ event = "end"; job = $Name; exit_code = $ExitCode; log = $LogPath }
    if ($ExitCode -ne 0) {
        throw "Experiment failed: $Name (exit $ExitCode). See $LogPath"
    }
}

$CommonRun = @(
    "--api_url", $ApiUrl,
    "--model", $Model,
    "--max_requests_per_minute", "$Rate",
    "--max_tokens_per_minute", "$TokenRate",
    "--max_attempts", "10",
    "--max_concurrent_requests", "$MaxConcurrent",
    "--save_every", "500"
)

$CommonSelf = @(
    "--api_url", $ApiUrl,
    "--model", $Model,
    "--max_requests_per_minute", "$Rate",
    "--max_tokens_per_minute", "$TokenRate",
    "--max_attempts", "10",
    "--max_concurrent_requests", "$MaxConcurrent"
)

$LabelRun = $CommonRun + @("--response_max_token", "64")
$TitleRun = $CommonRun + @("--response_max_token", "32")
$RepairRun = $CommonRun + @("--response_max_token", "1024")

Write-RunStatus @{ event = "runner_start"; model = $Model; api_url = $ApiUrl; rate = $Rate; token_rate = $TokenRate; max_concurrent = $MaxConcurrent }

# Small-first order makes most paper tasks finish before the largest title/Chromium/stable jobs.
Invoke-Experiment "task4_vulfix_extractfix_expertise" (@("run.py", "--task", "vulfix", "--dataset", "vulfix_extractfix", "--method", "expertise", "--TEST", "test", "--testNum", "0") + $RepairRun)

Invoke-Experiment "task5_APCA_invalidator_self_heuristic" (@("run_self_heuristic.py", "--task", "APCA", "--dataset", "APCA_invalidator", "--testNum", "0", "--result_file_name", "APCA_APCA_invalidator_self-heuristic_test") + $CommonSelf)
Invoke-Experiment "task5_APCA_panther_self_heuristic" (@("run_self_heuristic.py", "--task", "APCA", "--dataset", "APCA_panther", "--testNum", "0", "--result_file_name", "APCA_APCA_panther_self-heuristic_test") + $CommonSelf)

Invoke-Experiment "task3_cvss_UI_self_heuristic" (@("run_self_heuristic.py", "--task", "cvss", "--dataset", "UI", "--testNum", "0", "--result_file_name", "cvss_UI_self-heuristic_test") + $CommonSelf)
Invoke-Experiment "task3_cvss_AC_self_heuristic" (@("run_self_heuristic.py", "--task", "cvss", "--dataset", "AC", "--testNum", "0", "--result_file_name", "cvss_AC_self-heuristic_test") + $CommonSelf)
Invoke-Experiment "task3_cvss_PR_self_heuristic" (@("run_self_heuristic.py", "--task", "cvss", "--dataset", "PR", "--testNum", "0", "--result_file_name", "cvss_PR_self-heuristic_test") + $CommonSelf)
Invoke-Experiment "task3_cvss_AV_self_heuristic" (@("run_self_heuristic.py", "--task", "cvss", "--dataset", "AV", "--testNum", "0", "--result_file_name", "cvss_AV_self-heuristic_test") + $CommonSelf)

Invoke-Experiment "task2_SBRP_Ambari_expertise" (@("run.py", "--task", "SBRP", "--dataset", "Ambari", "--method", "expertise", "--TEST", "test", "--testNum", "0") + $LabelRun)
Invoke-Experiment "task2_SBRP_Camel_expertise" (@("run.py", "--task", "SBRP", "--dataset", "Camel", "--method", "expertise", "--TEST", "test", "--testNum", "0") + $LabelRun)
Invoke-Experiment "task2_SBRP_Derby_expertise" (@("run.py", "--task", "SBRP", "--dataset", "Derby", "--method", "expertise", "--TEST", "test", "--testNum", "0") + $LabelRun)
Invoke-Experiment "task2_SBRP_Wicket_expertise" (@("run.py", "--task", "SBRP", "--dataset", "Wicket", "--method", "expertise", "--TEST", "test", "--testNum", "0") + $LabelRun)

Invoke-Experiment "task5_APCA_quatrain_code_only" (@("run.py", "--task", "APCA", "--dataset", "APCA_quatrain", "--method", "code-only", "--TEST", "test", "--testNum", "0") + $LabelRun)
Invoke-Experiment "task6_stable_patchnet_expertise" (@("run.py", "--task", "stable", "--dataset", "stable_patchnet", "--method", "expertise", "--TEST", "test", "--testNum", "0") + $LabelRun)
Invoke-Experiment "task2_SBRP_Chromium_expertise" (@("run.py", "--task", "SBRP", "--dataset", "Chromium", "--method", "expertise", "--TEST", "test", "--testNum", "0") + $LabelRun)
Invoke-Experiment "task1_title_itape_few_shot" (@("run.py", "--task", "title", "--dataset", "title_itape", "--method", "few-shot", "--TEST", "test", "--testNum", "0") + $TitleRun)

Write-RunStatus @{ event = "runner_end"; model = $Model; api_url = $ApiUrl; rate = $Rate; token_rate = $TokenRate }
