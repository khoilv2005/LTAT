param(
    [string]$ApiUrl = "https://ollama.com/api/chat",
    [string]$Model = "gemini-3-flash-preview:cloud",
    [int]$MaxConcurrentRequests = 1,
    [int]$ResponseMaxToken = 512
)

$ErrorActionPreference = "Continue"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Python = Join-Path $Root "venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    $Python = "python"
}

$ResultRoot = Join-Path $Root "results\gemini3"
$BaselineRoot = Join-Path $ResultRoot "baseline"
$RagRoot = Join-Path $ResultRoot "rag"
$MetricRoot = Join-Path $Root "results\metrics\gemini3"
$LogDir = Join-Path $ResultRoot "logs"
New-Item -ItemType Directory -Force -Path $BaselineRoot, $RagRoot, $MetricRoot, $LogDir | Out-Null

$BaselineJobs = @(
    @{Name="gemini3_baseline_sbrp_ambari"; Task="SBRP"; Dataset="Ambari"; Method="expertise"; N=0; Expected=500; Extra=@()},
    @{Name="gemini3_baseline_sbrp_camel"; Task="SBRP"; Dataset="Camel"; Method="expertise"; N=0; Expected=500; Extra=@()},
    @{Name="gemini3_baseline_sbrp_derby"; Task="SBRP"; Dataset="Derby"; Method="expertise"; N=0; Expected=500; Extra=@()},
    @{Name="gemini3_baseline_sbrp_wicket"; Task="SBRP"; Dataset="Wicket"; Method="expertise"; N=0; Expected=500; Extra=@()},

    @{Name="gemini3_baseline_cvss_av"; Task="cvss"; Dataset="AV"; Method="self-heuristic"; N=0; Expected=487; Extra=@("--heuristics_file","results\heuristics\cvss_AV_heuristics.json","--task_type","CVSS")},
    @{Name="gemini3_baseline_cvss_ac"; Task="cvss"; Dataset="AC"; Method="self-heuristic"; N=0; Expected=373; Extra=@("--heuristics_file","results\heuristics\cvss_AC_heuristics.json","--task_type","CVSS")},
    @{Name="gemini3_baseline_cvss_pr"; Task="cvss"; Dataset="PR"; Method="self-heuristic"; N=0; Expected=414; Extra=@("--heuristics_file","results\heuristics\cvss_PR_heuristics.json","--task_type","CVSS")},
    @{Name="gemini3_baseline_cvss_ui"; Task="cvss"; Dataset="UI"; Method="self-heuristic"; N=0; Expected=359; Extra=@("--heuristics_file","results\heuristics\cvss_UI_heuristics.json","--task_type","CVSS")},

    @{Name="gemini3_baseline_apca_invalidator"; Task="APCA"; Dataset="APCA_invalidator"; Method="self-heuristic"; N=0; Expected=139; Extra=@("--heuristics_file","results\heuristics\APCA_APCA_invalidator_heuristics.json","--task_type","APCA")},
    @{Name="gemini3_baseline_apca_panther"; Task="APCA"; Dataset="APCA_panther"; Method="self-heuristic"; N=0; Expected=208; Extra=@("--heuristics_file","results\heuristics\APCA_APCA_panther_heuristics.json","--task_type","APCA")},
    @{Name="gemini3_baseline_apca_quatrain"; Task="APCA"; Dataset="APCA_quatrain"; Method="code-only"; N=0; Expected=995; Extra=@()},

    @{Name="gemini3_baseline_stable"; Task="stable"; Dataset="stable_patchnet"; Method="expertise"; N=0; Expected=10895; Extra=@()},
    @{Name="gemini3_baseline_sbrp_chromium"; Task="SBRP"; Dataset="Chromium"; Method="expertise"; N=0; Expected=20970; Extra=@()},
    @{Name="gemini3_baseline_title_title_itape"; Task="title"; Dataset="title_itape"; Method="few-shot"; N=0; Expected=33438; Extra=@()}
)

$RagJobs = @(
    @{Name="gemini3_rag_sbrp_ambari"; Task="SBRP"; Dataset="Ambari"; N=0; Expected=500; Extra=@()},
    @{Name="gemini3_rag_sbrp_camel"; Task="SBRP"; Dataset="Camel"; N=0; Expected=500; Extra=@()},
    @{Name="gemini3_rag_sbrp_derby"; Task="SBRP"; Dataset="Derby"; N=0; Expected=500; Extra=@()},
    @{Name="gemini3_rag_sbrp_wicket"; Task="SBRP"; Dataset="Wicket"; N=0; Expected=500; Extra=@()},

    @{Name="gemini3_rag_cvss_av"; Task="cvss"; Dataset="AV"; N=0; Expected=487; Extra=@()},
    @{Name="gemini3_rag_cvss_ac"; Task="cvss"; Dataset="AC"; N=0; Expected=373; Extra=@()},
    @{Name="gemini3_rag_cvss_pr"; Task="cvss"; Dataset="PR"; N=0; Expected=414; Extra=@()},
    @{Name="gemini3_rag_cvss_ui"; Task="cvss"; Dataset="UI"; N=0; Expected=359; Extra=@()},

    @{Name="gemini3_rag_apca_invalidator"; Task="APCA"; Dataset="APCA_invalidator"; N=0; Expected=139; Extra=@()},
    @{Name="gemini3_rag_apca_panther"; Task="APCA"; Dataset="APCA_panther"; N=0; Expected=208; Extra=@()},
    @{Name="gemini3_rag_apca_quatrain"; Task="APCA"; Dataset="APCA_quatrain"; N=0; Expected=995; Extra=@()},

    @{Name="gemini3_rag_stable"; Task="stable"; Dataset="stable_patchnet"; N=0; Expected=10895; Extra=@()},
    @{Name="gemini3_rag_sbrp_chromium"; Task="SBRP"; Dataset="Chromium"; N=0; Expected=20970; Extra=@()},
    @{Name="gemini3_rag_title_title_itape"; Task="title"; Dataset="title_itape"; N=0; Expected=33438; Extra=@()}
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

function Invoke-Step {
    param([array]$CmdArgs, [string]$Stdout, [string]$Stderr)
    $cleanArgs = @($CmdArgs | Where-Object { $null -ne $_ -and [string]$_ -ne "" })
    Write-Host "RUN $Python $($cleanArgs -join ' ')"
    $p = Start-Process -FilePath $Python -ArgumentList $cleanArgs -WorkingDirectory $Root -RedirectStandardOutput $Stdout -RedirectStandardError $Stderr -Wait -PassThru -WindowStyle Hidden
    if ($p.ExitCode -ne 0) {
        Write-Host "FAILED exit=$($p.ExitCode) stderr=$Stderr"
    }
    return $p.ExitCode
}

function Invoke-Eval {
    param([hashtable]$Job, [string]$ResultPath)
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
    Invoke-Step -CmdArgs $evalArgs -Stdout $metricOut -Stderr $metricErr | Out-Null
}

foreach ($job in $BaselineJobs) {
    $resultName = Get-BaselineResultName -Job $job
    $resultPath = Join-Path $BaselineRoot "$resultName.json"
    $metricPath = Join-Path $MetricRoot "$($job.Name).json"
    $count = Get-JsonCount $resultPath
    if ($count -ge $job.Expected -and (Test-Path $metricPath)) {
        Write-Host "SKIP completed $($job.Name) $count/$($job.Expected)"
        continue
    }

    $out = Join-Path $LogDir "$($job.Name).out.log"
    $err = Join-Path $LogDir "$($job.Name).err.log"
    $args = @(
        "-u", "run.py",
        "--task", $job.Task,
        "--dataset", $job.Dataset,
        "--method", $job.Method,
        "--TEST", "test",
        "--testNum", [string]$job.N,
        "--api_url", $ApiUrl,
        "--model", $Model,
        "--result_root", "results\gemini3\baseline",
        "--max_requests_per_minute", "30",
        "--max_tokens_per_minute", "1000000",
        "--max_concurrent_requests", [string]$MaxConcurrentRequests,
        "--save_every", "25",
        "--response_max_token", [string]$ResponseMaxToken
    ) + $job.Extra

    $code = Invoke-Step -CmdArgs $args -Stdout $out -Stderr $err
    if ($code -eq 0) {
        Invoke-Eval -Job $job -ResultPath $resultPath
    }
}

foreach ($job in $RagJobs) {
    $resultPath = Join-Path $RagRoot "$($job.Name).json"
    $metricPath = Join-Path $MetricRoot "$($job.Name).json"
    $count = Get-JsonCount $resultPath
    if ($count -ge $job.Expected -and (Test-Path $metricPath)) {
        Write-Host "SKIP completed $($job.Name) $count/$($job.Expected)"
        continue
    }

    $out = Join-Path $LogDir "$($job.Name).out.log"
    $err = Join-Path $LogDir "$($job.Name).err.log"
    $args = @(
        "-u", "run_rag.py",
        "--task", $job.Task,
        "--dataset", $job.Dataset,
        "--TEST", "test",
        "--testNum", [string]$job.N,
        "--api_url", $ApiUrl,
        "--model", $Model,
        "--result_root", "results\gemini3\rag",
        "--result_file_name", $job.Name,
        "--max_requests_per_minute", "30",
        "--max_tokens_per_minute", "1000000",
        "--max_concurrent_requests", [string]$MaxConcurrentRequests,
        "--save_every", "25",
        "--response_max_token", [string]$ResponseMaxToken
    ) + $job.Extra

    $code = Invoke-Step -CmdArgs $args -Stdout $out -Stderr $err
    if ($code -eq 0) {
        Invoke-Eval -Job $job -ResultPath $resultPath
    }
}

Write-Host "Gemini baseline/RAG queue finished."
