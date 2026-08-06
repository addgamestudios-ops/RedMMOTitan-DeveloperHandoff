[CmdletBinding()]
param(
    [string]$EditorPath = 'D:\UE_5.8\Engine\Binaries\Win64\UnrealEditor.exe',
    [string]$ProjectPath = 'D:\RedMMOTitan\Titan.uproject',
    [double]$MinimumFreePhysicalGiB = 16.0,
    [double]$MinimumFreeCommitGiB = 16.0,
    [double]$AbortFreePhysicalGiB = 8.0,
    [int]$PreflightSamples = 6,
    [int]$PreflightIntervalSeconds = 2,
    [int]$StartupTimeoutSeconds = 600,
    [switch]$NullRHI,
    [switch]$PreflightOnly
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

if ($AbortFreePhysicalGiB -ge $MinimumFreePhysicalGiB) {
    throw 'AbortFreePhysicalGiB must remain lower than MinimumFreePhysicalGiB.'
}
if ($PreflightSamples -lt 1) {
    throw 'PreflightSamples must be at least 1.'
}
if (-not (Test-Path -LiteralPath $EditorPath -PathType Leaf)) {
    throw "Unreal editor executable not found: $EditorPath"
}
if (-not (Test-Path -LiteralPath $ProjectPath -PathType Leaf)) {
    throw "Unreal project not found: $ProjectPath"
}

function Get-MemorySnapshot {
    $operatingSystem = Get-CimInstance Win32_OperatingSystem
    $performance = Get-Counter '\Memory\Committed Bytes', '\Memory\Commit Limit'
    $values = @{}
    foreach ($sample in $performance.CounterSamples) {
        $values[$sample.Path.Split('\')[-1]] = $sample.CookedValue
    }

    [pscustomobject]@{
        Timestamp       = Get-Date
        FreePhysicalGiB = [math]::Round($operatingSystem.FreePhysicalMemory / 1MB, 2)
        FreeCommitGiB   = [math]::Round(
            ($values['commit limit'] - $values['committed bytes']) / 1GB,
            2
        )
    }
}

function Get-UnrealEditorProcesses {
    @(Get-Process -Name 'UnrealEditor', 'UnrealEditor-Cmd' -ErrorAction SilentlyContinue)
}

function Test-LocalListener {
    param([Parameter(Mandatory)][int]$Port)
    $listener = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue
    return $null -ne $listener
}

$existingEditors = @(Get-UnrealEditorProcesses)
if ($existingEditors.Count -gt 0) {
    $ids = ($existingEditors.Id | Sort-Object) -join ', '
    throw "Refusing to launch a second Unreal editor. Existing PID(s): $ids"
}

$preflight = @()
for ($index = 0; $index -lt $PreflightSamples; $index++) {
    $snapshot = Get-MemorySnapshot
    $preflight += $snapshot
    Write-Host (
        'Preflight {0}/{1}: freePhysical={2:N2} GiB freeCommit={3:N2} GiB' -f
        ($index + 1),
        $PreflightSamples,
        $snapshot.FreePhysicalGiB,
        $snapshot.FreeCommitGiB
    )
    if ($index -lt ($PreflightSamples - 1) -and $PreflightIntervalSeconds -gt 0) {
        Start-Sleep -Seconds $PreflightIntervalSeconds
    }
}

$minimumPhysical = ($preflight | Measure-Object FreePhysicalGiB -Minimum).Minimum
$minimumCommit = ($preflight | Measure-Object FreeCommitGiB -Minimum).Minimum
$preflightPassed = (
    $minimumPhysical -ge $MinimumFreePhysicalGiB -and
    $minimumCommit -ge $MinimumFreeCommitGiB
)

if (-not $preflightPassed) {
    throw ((
        'Editor not started. Sustained preflight requires free physical >= {0:N1} GiB ' +
        'and free commit >= {1:N1} GiB; observed minima were {2:N2} GiB and {3:N2} GiB.'
    ) -f $MinimumFreePhysicalGiB, $MinimumFreeCommitGiB, $minimumPhysical, $minimumCommit)
}

if ($PreflightOnly) {
    Write-Host 'Preflight passed; PreflightOnly was specified, so no editor was started.'
    return
}

$arguments = @(
    $ProjectPath
    '-NoSplash'
    '-uaip-mcp-enable'
    '-uaip-http-port=8765'
    '-ModelContextProtocolStartServer'
)
if ($NullRHI) {
    $arguments += '-NullRHI'
}

$diagnosticsRoot = 'D:\RedMMOTitanWindowsData\Diagnostics\UnrealAIGuardedLaunch'
$null = New-Item -ItemType Directory -Path $diagnosticsRoot -Force
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$stdoutPath = Join-Path $diagnosticsRoot "$stamp-stdout.log"
$stderrPath = Join-Path $diagnosticsRoot "$stamp-stderr.log"

$editor = Start-Process `
    -FilePath $EditorPath `
    -ArgumentList $arguments `
    -PassThru `
    -RedirectStandardOutput $stdoutPath `
    -RedirectStandardError $stderrPath

Write-Host "Started guarded Unreal editor PID $($editor.Id)."
$deadline = (Get-Date).AddSeconds($StartupTimeoutSeconds)

while ((Get-Date) -lt $deadline) {
    $editor.Refresh()
    if ($editor.HasExited) {
        throw "Unreal editor PID $($editor.Id) exited with code $($editor.ExitCode)."
    }

    $snapshot = Get-MemorySnapshot
    if ($snapshot.FreePhysicalGiB -lt $AbortFreePhysicalGiB) {
        Stop-Process -Id $editor.Id -ErrorAction SilentlyContinue
        Wait-Process -Id $editor.Id -Timeout 30 -ErrorAction SilentlyContinue
        throw ((
            'Stopped only the guarded Unreal editor PID {0}: free physical RAM fell to ' +
            '{1:N2} GiB, below the preserved {2:N1} GiB abort floor.'
        ) -f $editor.Id, $snapshot.FreePhysicalGiB, $AbortFreePhysicalGiB)
    }

    $officialMcpReady = Test-LocalListener -Port 8000
    $uaipReady = Test-LocalListener -Port 8765
    Write-Host (
        'Startup: PID={0} freePhysical={1:N2} GiB freeCommit={2:N2} GiB ' +
        'officialMCP={3} UAIP={4}' -f
        $editor.Id,
        $snapshot.FreePhysicalGiB,
        $snapshot.FreeCommitGiB,
        $officialMcpReady,
        $uaipReady
    )

    if ($officialMcpReady -and $uaipReady) {
        Write-Host (
            'Both listeners are live. Runtime acceptance still requires MCP initialize ' +
            'and explicit UAIP/Nwiro module verification.'
        )
        return
    }
    Start-Sleep -Seconds 2
}

throw ((
    'Unreal editor PID {0} is still running, but ports 8000 and 8765 did not both ' +
    'listen within {1} seconds. Inspect {2} and the Unreal project log.'
) -f $editor.Id, $StartupTimeoutSeconds, $diagnosticsRoot)
