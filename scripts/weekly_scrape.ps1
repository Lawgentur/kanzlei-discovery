param(
    [string]$RepoRoot = (Split-Path -Parent $PSScriptRoot)
)

$ErrorActionPreference = "Stop"
Set-Location $RepoRoot

$stamp = Get-Date -Format "yyyy-MM-dd_HHmmss"
$today = Get-Date -Format "yyyy-MM-dd"
$logDir = Join-Path $RepoRoot "logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$logFile = Join-Path $logDir "weekly_scrape_$stamp.log"
$pytestTmp = Join-Path $RepoRoot ".tmp"
New-Item -ItemType Directory -Force -Path $pytestTmp | Out-Null
$env:TMP = $pytestTmp
$env:TEMP = $pytestTmp

function Invoke-Native {
    param(
        [Parameter(Mandatory = $true)]
        [string]$FilePath,
        [Parameter(ValueFromRemainingArguments = $true)]
        [string[]]$Arguments
    )
    & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$FilePath failed with exit code $LASTEXITCODE"
    }
}

Start-Transcript -Path $logFile -Append | Out-Null
try {
    Write-Host "WEEKLY_SCRAPE_START $stamp"

    if (Test-Path ".env") {
        Get-Content ".env" | ForEach-Object {
            if ($_ -match '^\s*([^#=]+)=(.*)$') {
                [Environment]::SetEnvironmentVariable($matches[1].Trim(), $matches[2].Trim().Trim('"'), "Process")
            }
        }
    }

    Invoke-Native git add jobs_master.csv media/jobs_master_public.csv target_firms_full.csv reports state/imported_board_files.json
    $prePullChanges = git status --porcelain
    if ($prePullChanges) {
        Invoke-Native git commit -m "Preserve generated job data before weekly scrape $today"
    }

    Invoke-Native git pull --rebase origin main

    Invoke-Native python -m kanzlei_discovery.cli `
        --no-drive `
        --scrape `
        --llm-fallback `
        --days-until-deletion 3650 `
        --checkpoint-interval 50 `
        --strategy-file state/site_strategies.csv `
        --no-job-report "reports/kanzleien_ohne_jobs_diagnose_$today.csv"

    Invoke-Native python scripts/import_job_boards.py `
        --date $today `
        --report-file "reports/import_report_$today.csv" `
        --no-job-report "reports/kanzleien_ohne_jobs_diagnose_$today.csv"

    Invoke-Native python scripts/import_xml_feeds.py `
        --date $today `
        --report-file "reports/xml_feed_import_report_$today.csv" `
        --no-job-report "reports/kanzleien_ohne_jobs_diagnose_$today.csv"

    Invoke-Native python -m pytest tests -q --basetemp .tmp/pytest-weekly

    Invoke-Native git add jobs_master.csv media/jobs_master_public.csv target_firms_full.csv reports state/imported_board_files.json
    $changes = git status --porcelain
    if ($changes) {
        Invoke-Native git commit -m "Weekly jobs scrape $today"
        Invoke-Native git push origin main
        Write-Host "WEEKLY_SCRAPE_COMMITTED $today"
    } else {
        Write-Host "WEEKLY_SCRAPE_NO_CHANGES $today"
    }
}
finally {
    Stop-Transcript | Out-Null
}
