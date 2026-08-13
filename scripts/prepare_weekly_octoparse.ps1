param(
    [string]$RepoRoot = (Split-Path -Parent $PSScriptRoot),
    [int]$DurationMinutes = 720
)

$ErrorActionPreference = "Stop"
$logDir = Join-Path $RepoRoot "logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$stamp = Get-Date -Format "yyyy-MM-dd_HHmmss"
$logFile = Join-Path $logDir "octoparse_prepare_$stamp.log"

$executionStateSource = @"
using System;
using System.Runtime.InteropServices;

public static class KanzleiExecutionState
{
    [DllImport("kernel32.dll", SetLastError = true)]
    public static extern uint SetThreadExecutionState(uint executionState);
}
"@

Add-Type -TypeDefinition $executionStateSource
$continuous = [Convert]::ToUInt32("80000000", 16)
$systemRequired = [uint32]0x00000001

Start-Transcript -Path $logFile -Append | Out-Null
try {
    $result = [KanzleiExecutionState]::SetThreadExecutionState($continuous -bor $systemRequired)
    if ($result -eq 0) {
        throw "Windows could not enable the keep-awake execution state."
    }

    if (-not (Get-Process -Name "Octoparse" -ErrorAction SilentlyContinue)) {
        $octoparsePath = "C:\Program Files\Octoparse\Octoparse.exe"
        if (-not (Test-Path -LiteralPath $octoparsePath)) {
            throw "Octoparse was not found at $octoparsePath"
        }
        Start-Process -FilePath $octoparsePath -WindowStyle Hidden
        Start-Sleep -Seconds 30
    }

    Write-Host "OCTOPARSE_READY $(Get-Date -Format o) duration_minutes=$DurationMinutes"
    Start-Sleep -Seconds ($DurationMinutes * 60)
}
finally {
    [void][KanzleiExecutionState]::SetThreadExecutionState($continuous)
    Stop-Transcript | Out-Null
}
