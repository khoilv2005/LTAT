param(
    [string]$ApiUrl = "https://ollama.com/api/chat",
    [string]$Model = "gemini-3-flash-preview:cloud",
    [int]$MaxParallelJobs = 3,
    [int]$ResponseMaxToken = 512,
    [string]$ResultNamespace = "gemini3",
    [int]$MaxRequestsPerMinute = 30,
    [int]$MaxTokensPerMinute = 1000000
)

$ErrorActionPreference = "Continue"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Python = Join-Path $Root "venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    $Python = "python"
}

$ResultRoot = Join-Path $Root "results\$ResultNamespace"
$BaselineRoot = Join-Path $ResultRoot "baseline"
$RagRoot = Join-Path $ResultRoot "rag"
$MetricRoot = Join-Path $Root "results\metrics\$ResultNamespace"
$LogDir = Join-Path $ResultRoot "parallel_logs"
New-Item -ItemType Directory -Force -Path $BaselineRoot, $RagRoot, $MetricRoot, $LogDir | Out-Null

$Jobs = @(
    @{Name="gemini3_baseline_sbrp_ambari"; Kind="baseline"; Task="SBRP"; Dataset="Ambari"; Method="expertise"; N=0; Expected=500; Extra=@()},
    @{Name="gemini3_baseline_sbrp_camel"; Kind="baseline"; Task="SBRP"; Dataset="Camel"; Method="expertise"; N=0; Expected=500; Extra=@()},
    @{Name="gemini3_baseline_sbrp_derby"; Kind="baseline"; Task="SBRP"; Dataset="Derby"; Method="expertise"; N=0; Expected=500; Extra=@()},
    @{Name="gemini3_baseline_sbrp_wicket"; Kind="baseline"; Task="SBRP"; Dataset="Wicket"; Method="expertise"; N=0; Expected=500; Extra=@()},

    @{Name="gemini3_baseline_cvss_av"; Kind="baseline"; Task="cvss"; Dataset="AV"; Method="self-heuristic"; N=0; Expected=487; Extra=@("--heuristics_file","results\heuristics\cvss_AV_heuristics.json","--task_type","CVSS")},
    @{Name="gemini3_baseline_cvss_ac"; Kind="baseline"; Task="cvss"; Dataset="AC"; Method="self-heuristic"; N=0; Expected=373; Extra=@("--heuristics_file","results\heuristics\cvss_AC_heuristics.json","--task_type","CVSS")},
    @{Name="gemini3_baseline_cvss_pr"; Kind="baseline"; Task="cvss"; Dataset="PR"; Method="self-heuristic"; N=0; Expected=414; Extra=@("--heuristics_file","results\heuristics\cvss_PR_heuristics.json","--task_type","CVSS")},
    @{Name="gemini3_baseline_cvss_ui"; Kind="baseline"; Task="cvss"; Dataset="UI"; Method="self-heuristic"; N=0; Expected=359; Extra=@("--heuristics_file","results\heuristics\cvss_UI_heuristics.json","--task_type","CVSS")},

    @{Name="gemini3_baseline_stable"; Kind="baseline"; Task="stable"; Dataset="stable_patchnet"; Method="expertise"; N=0; Expected=10895; Extra=@()},
    @{Name="gemini3_baseline_sbrp_chromium"; Kind="baseline"; Task="SBRP"; Dataset="Chromium"; Method="expertise"; N=0; Expected=20970; Extra=@()},
    @{Name="gemini3_baseline_title_title_itape"; Kind="baseline"; Task="title"; Dataset="title_itape"; Method="few-shot"; N=0; Expected=33438; Extra=@()},

    @{Name="gemini3_rag_sbrp_ambari"; Kind="rag"; Task="SBRP"; Dataset="Ambari"; N=0; Expected=500; Extra=@()},
    @{Name="gemini3_rag_sbrp_camel"; Kind="rag"; Task="SBRP"; Dataset="Camel"; N=0; Expected=500; Extra=@()},
    @{Name="gemini3_rag_sbrp_derby"; Kind="rag"; Task="SBRP"; Dataset="Derby"; N=0; Expected=500; Extra=@()},
    @{Name="gemini3_rag_sbrp_wicket"; Kind="rag"; Task="SBRP"; Dataset="Wicket"; N=0; Expected=500; Extra=@()},

    @{Name="gemini3_rag_cvss_av"; Kind="rag"; Task="cvss"; Dataset="AV"; N=0; Expected=487; Extra=@()},
    @{Name="gemini3_rag_cvss_ac"; Kind="rag"; Task="cvss"; Dataset="AC"; N=0; Expected=373; Extra=@()},
    @{Name="gemini3_rag_cvss_pr"; Kind="rag"; Task="cvss"; Dataset="PR"; N=0; Expected=414; Extra=@()},
    @{Name="gemini3_rag_cvss_ui"; Kind="rag"; Task="cvss"; Dataset="UI"; N=0; Expected=359; Extra=@()},

    @{Name="gemini3_rag_apca_invalidator"; Kind="rag"; Task="APCA"; Dataset="APCA_invalidator"; N=0; Expected=139; Extra=@()},
    @{Name="gemini3_rag_apca_panther"; Kind="rag"; Task="APCA"; Dataset="APCA_panther"; N=0; Expected=208; Extra=@()},
    @{Name="gemini3_rag_apca_quatrain"; Kind="rag"; Task="APCA"; Dataset="APCA_quatrain"; N=0; Expected=995; Extra=@()},

    @{Name="gemini3_rag_stable"; Kind="rag"; Task="stable"; Dataset="stable_patchnet"; N=0; Expected=10895; Extra=@()},
    @{Name="gemini3_rag_sbrp_chromium"; Kind="rag"; Task="SBRP"; Dataset="Chromium"; N=0; Expected=20970; Extra=@()},
    @{Name="gemini3_rag_title_title_itape"; Kind="rag"; Task="title"; Dataset="title_itape"; N=0; Expected=33438; Extra=@()}
)

function Get-JsonCount {
    param([string]$Path)
    if (-not (Test-Path $Path)) { return 0 }
    try {
        $json = Get-Content -Raw -Encoding UTF8 $Path | ConvertFrom-Json
        return @($json).Count
    } catch {
        return 0
    }
}

function Get-BaselineResultName {
    param([hashtable]$Job)
    return "$($Job.Task)_$($Job.Dataset)_$($Job.Method)_test"
}

function Get-ResultPath {
    param([hashtable]$Job)
    if ($Job.Kind -eq "baseline") {
        return Join-Path $BaselineRoot "$((Get-BaselineResultName -Job $Job)).json"
    }
    return Join-Path $RagRoot "$($Job.Name).json"
}

function Get-RunArgs {
    param([hashtable]$Job)
    if ($Job.Kind -eq "baseline") {
        return @(
            "-u", "run.py",
            "--task", $Job.Task,
            "--dataset", $Job.Dataset,
            "--method", $Job.Method,
            "--TEST", "test",
            "--testNum", [string]$Job.N,
            "--api_url", $ApiUrl,
            "--model", $Model,
            "--result_root", $BaselineRoot,
            "--max_requests_per_minute", [string]$MaxRequestsPerMinute,
            "--max_tokens_per_minute", [string]$MaxTokensPerMinute,
            "--max_concurrent_requests", "1",
            "--save_every", "25",
            "--response_max_token", [string]$ResponseMaxToken
        ) + $Job.Extra
    }

    return @(
        "-u", "run_rag.py",
        "--task", $Job.Task,
        "--dataset", $Job.Dataset,
        "--TEST", "test",
        "--testNum", [string]$Job.N,
        "--api_url", $ApiUrl,
        "--model", $Model,
        "--result_root", $RagRoot,
        "--result_file_name", $Job.Name,
        "--max_requests_per_minute", [string]$MaxRequestsPerMinute,
        "--max_tokens_per_minute", [string]$MaxTokensPerMinute,
        "--max_concurrent_requests", "1",
        "--save_every", "25",
        "--response_max_token", [string]$ResponseMaxToken
    ) + $Job.Extra
}

function Invoke-Eval {
    param([hashtable]$Job, [string]$ResultPath)
    if (-not (Test-Path $ResultPath)) {
        Write-Host "SKIP eval missing result $($Job.Name)"
        return
    }
    $metricPath = Join-Path $MetricRoot "$($Job.Name).json"
    $metricOut = Join-Path $LogDir "$($Job.Name).metrics.out.log"
    $metricErr = Join-Path $LogDir "$($Job.Name).metrics.err.log"
    $evalArgs = @(
        "tools/evaluate_rag_metrics.py",
        $ResultPath,
        "--task", $Job.Task,
        "--dataset", $Job.Dataset,
        "--name", $Job.Name,
        "--output", $metricPath
    )
    $cleanArgs = @($evalArgs | Where-Object { $null -ne $_ -and [string]$_ -ne "" })
    $p = Start-Process -FilePath $Python -ArgumentList $cleanArgs -WorkingDirectory $Root -RedirectStandardOutput $metricOut -RedirectStandardError $metricErr -Wait -PassThru -WindowStyle Hidden
    if ($p.ExitCode -ne 0) {
        Write-Host "FAILED eval $($Job.Name) exit=$($p.ExitCode)"
    } else {
        Write-Host "EVAL done $($Job.Name)"
    }
}

$Pending = New-Object System.Collections.Queue
foreach ($job in $Jobs) {
    $resultPath = Get-ResultPath -Job $job
    $metricPath = Join-Path $MetricRoot "$($job.Name).json"
    $count = Get-JsonCount $resultPath
    if ($count -ge $job.Expected -and (Test-Path $metricPath)) {
        Write-Host "SKIP completed $($job.Name) $count/$($job.Expected)"
        continue
    }
    $Pending.Enqueue($job)
}

$Running = @()

function Stop-AllRunning {
    param([string]$Reason)
    Write-Host "FATAL: $Reason"
    foreach ($entry in $Running) {
        try {
            $entry.Process.Refresh()
            if (-not $entry.Process.HasExited) {
                Stop-Process -Id $entry.Process.Id -Force -ErrorAction SilentlyContinue
            }
        } catch {}
    }
    exit 1
}

while ($Pending.Count -gt 0 -or $Running.Count -gt 0) {
    while ($Pending.Count -gt 0 -and $Running.Count -lt $MaxParallelJobs) {
        $job = $Pending.Dequeue()
        $out = Join-Path $LogDir "$($job.Name).out.log"
        $err = Join-Path $LogDir "$($job.Name).err.log"
        $args = Get-RunArgs -Job $job
        $cleanArgs = @($args | Where-Object { $null -ne $_ -and [string]$_ -ne "" })
        Write-Host "START $($job.Name)"
        Write-Host "RUN $Python $($cleanArgs -join ' ')"
        $proc = Start-Process -FilePath $Python -ArgumentList $cleanArgs -WorkingDirectory $Root -RedirectStandardOutput $out -RedirectStandardError $err -PassThru -WindowStyle Hidden
        $Running += [pscustomobject]@{ Job=$job; Process=$proc; Out=$out; Err=$err; ResultPath=(Get-ResultPath -Job $job) }
    }

    Start-Sleep -Seconds 10

    $StillRunning = @()
    foreach ($entry in $Running) {
        $proc = $entry.Process
        $proc.Refresh()
        if ($proc.HasExited) {
            Write-Host "DONE $($entry.Job.Name) exit=$($proc.ExitCode)"
            if ($proc.ExitCode -eq 0) {
                Invoke-Eval -Job $entry.Job -ResultPath $entry.ResultPath
            } else {
                Write-Host "FAILED run $($entry.Job.Name) stderr=$($entry.Err)"
                Stop-AllRunning "a job failed; stopping all remaining Gemini jobs"
            }
        } else {
            $StillRunning += $entry
        }
    }
    $Running = $StillRunning
}

Write-Host "Gemini parallel baseline/RAG queue finished."
