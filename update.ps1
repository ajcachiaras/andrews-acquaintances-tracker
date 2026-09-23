<#
    Weekly driver for the Guillotine Watch tracker.

    Runs update_tracker.py, and if the season data actually moved, commits and
    pushes so the GitHub Pages copy picks it up. Logs every run to logs\.

    Run it now:
        powershell -ExecutionPolicy Bypass -File .\update.ps1

    Switches:
        -NoPush    commit locally, don't push
        -DryRun    show what the pull would change; touches nothing, never commits
#>
param(
    [switch]$NoPush,
    [switch]$DryRun
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $MyInvocation.MyCommand.Definition

$logDir = Join-Path $repo 'logs'
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir | Out-Null }
$log = Join-Path $logDir ("update-{0}.log" -f (Get-Date -Format 'yyyy-MM-dd'))

function Write-Log {
    param([string]$Message)
    $line = "[{0}] {1}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $Message
    Write-Output $line
    Add-Content -Path $log -Value $line -Encoding utf8
}

Write-Log "=== update starting (repo: $repo) ==="

# Prefer the 3.12 install; fall back to whatever python is on PATH.
$python = 'C:\Python312\python.exe'
if (-not (Test-Path $python)) {
    $cmd = Get-Command python -ErrorAction SilentlyContinue
    if ($null -eq $cmd) { Write-Log 'FAILED: no python found.'; exit 1 }
    $python = $cmd.Source
}

# Python goes through cmd /c on purpose: Windows PowerShell turns a native
# command's stderr into error records, so an ordinary warning would otherwise
# make a good run look like a failure.
$env:PYTHONIOENCODING = 'utf-8'
$flags = ''
if ($DryRun) { $flags = '--dry-run' }
$out = cmd /c "`"$python`" `"$repo\update_tracker.py`" $flags 2>&1"
$pyExit = $LASTEXITCODE
foreach ($line in $out) { Write-Log "  $line" }

if ($pyExit -ne 0) {
    Write-Log "FAILED: update_tracker.py exited $pyExit. Nothing committed."
    exit $pyExit
}

if ($DryRun) { Write-Log 'Dry run complete.'; exit 0 }

# Only the generated files are ever committed by the automation.
$tracked = @('data.js', 'lineups.js', 'README.md')
$status = cmd /c "git -C `"$repo`" status --porcelain -- $($tracked -join ' ') 2>&1"
if ([string]::IsNullOrWhiteSpace($status)) {
    Write-Log 'No change to commit -- already current.'
    exit 0
}

# Name the week in the commit so the history reads as a season log.
$week = 'update'
$m = [regex]::Match((Get-Content (Join-Path $repo 'data.js') -Raw), 'weeks:\s*\[([^\]]*)\]')
if ($m.Success) {
    $nums = [regex]::Matches($m.Groups[1].Value, '\d+')
    if ($nums.Count -gt 0) { $week = "week $($nums[$nums.Count - 1].Value)" }
}

$msg = "Add $week scores from Sleeper"
cmd /c "git -C `"$repo`" add $($tracked -join ' ') 2>&1" | ForEach-Object { Write-Log "  $_" }
cmd /c "git -C `"$repo`" commit -m `"$msg`" 2>&1" | ForEach-Object { Write-Log "  $_" }
if ($LASTEXITCODE -ne 0) { Write-Log 'FAILED: commit failed.'; exit 1 }
Write-Log "Committed: $msg"

if ($NoPush) {
    Write-Log 'Skipping push (-NoPush).'
} else {
    cmd /c "git -C `"$repo`" push 2>&1" | ForEach-Object { Write-Log "  $_" }
    if ($LASTEXITCODE -ne 0) {
        Write-Log 'FAILED: push failed -- the commit is local, rerun or push by hand.'
        exit 1
    }
    Write-Log 'Pushed to origin.'
}

# Keep the last 20 daily logs.
Get-ChildItem $logDir -Filter 'update-*.log' |
    Sort-Object Name -Descending |
    Select-Object -Skip 20 |
    Remove-Item -Force -ErrorAction SilentlyContinue

Write-Log '=== update finished ==='
exit 0
