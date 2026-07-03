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

    git pull --rebase origin main

    python -m kanzlei_discovery.cli `
        --no-drive `
        --scrape `
        --llm-fallback `
        --checkpoint-interval 50 `
        --strategy-file state/site_strategies.csv `
        --no-job-report "reports/kanzleien_ohne_jobs_diagnose_$today.csv"

    python scripts/import_job_boards.py `
        --date $today `
        --report-file "reports/import_report_$today.csv" `
        --no-job-report "reports/kanzleien_ohne_jobs_diagnose_$today.csv"

    python -m pytest -q

    git add jobs_master.csv media/jobs_master_public.csv target_firms_full.csv reports state/imported_board_files.json
    $changes = git status --porcelain
    if ($changes) {
        git commit -m "Weekly jobs scrape $today"
        git push origin main
        Write-Host "WEEKLY_SCRAPE_COMMITTED $today"
    } else {
        Write-Host "WEEKLY_SCRAPE_NO_CHANGES $today"
    }
}
finally {
    Stop-Transcript | Out-Null
}
