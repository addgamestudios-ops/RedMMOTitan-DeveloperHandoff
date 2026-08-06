[CmdletBinding()]
param(
    [switch]$PreflightOnly,

    [ValidateRange(1.0, 128.0)]
    [double]$MinimumFreeCommitGB = 18.0,

    [ValidateRange(1.0, 128.0)]
    [double]$MinimumFreePhysicalGB = 14.0,

    [ValidateRange(256, 65536)]
    [int]$MinimumFreeVramMB = 6500,

    [ValidateRange(1.0, 128.0)]
    [double]$AbortFreeCommitGB = 12.0,

    [ValidateRange(1.0, 128.0)]
    [double]$AbortFreePhysicalGB = 9.0,

    [ValidateRange(256, 65536)]
    [int]$AbortFreeVramMB = 4500,

    [ValidateRange(3, 60)]
    [int]$SustainedSampleCount = 12,

    [ValidateRange(1, 10)]
    [int]$SampleIntervalSeconds = 1,

    [ValidateRange(1, 30)]
    [int]$PollSeconds = 2,

    [ValidateRange(1, 60)]
    [int]$MaximumRuntimeMinutes = 10
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 2.0

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$ProjectFile = Join-Path $ProjectRoot 'Titan.uproject'
$ProbeScript = Join-Path $ProjectRoot 'Build\Automation\prepare_red_sand_sparkle_mask_probe.py'
$EditorCmd = 'D:\UE_5.8\Engine\Binaries\Win64\UnrealEditor-Cmd.exe'
$DiagnosticsRoot = 'D:\RedMMOTitanWindowsData\Diagnostics\SandSparkleMaskProbe'
$ProtectedMap = Join-Path $ProjectRoot 'Content\RedMMO\Maps\RedPlanetGen_50km_Test.umap'
$ProtectedReadyMarker = 'D:\RedMMOTitanWindowsData\PackagedBuilds\Development_50KM_FOUNDATION_20260716_064703\REDMMO_PACKAGE_READY.txt'
$ExpectedProtectedMapHash = 'DA5987012EEB8F550254F5FCF0F47F42B8F5E03428CF4881C83D8687537F6E7D'
$ExpectedProtectedReadyMarkerHash = '26B00A20C4B18717CEC36B5CA289CC9001AE1E65DA649404ACC8721F14EF26E8'
$TargetAssetFile = Join-Path $ProjectRoot 'Content\RedMMO\Materials\DesertSparkleTest\MI_PlanetBiome_DesertSparkle_T02.uasset'
$TargetAssetPath = '/Game/RedMMO/Materials/DesertSparkleTest/MI_PlanetBiome_DesertSparkle_T02'
$WriteFlag = '-RedSandSparkleMaskProbeWrite'
$BlockingExecutableNames = @(
    'UnrealEditor',
    'UnrealEditor-Cmd',
    'Titan',
    'AutomationTool',
    'UnrealBuildTool',
    'MSBuild',
    'ShaderCompileWorker',
    'CrashReportClient',
    'CrashReportClientEditor'
)
$DotNetHostedBuildPattern = '(?i)(AutomationTool|UnrealBuildTool|RunUAT|BuildCookRun|Titan(?:Editor)?\.Target)'

function Get-RedMemorySnapshot {
    $os = Get-CimInstance Win32_OperatingSystem
    $freeCommitGB = $os.FreeVirtualMemory / 1MB
    $commitLimitGB = $os.TotalVirtualMemorySize / 1MB
    [pscustomobject]@{
        FreeCommitGB = [math]::Round($freeCommitGB, 3)
        FreePhysicalGB = [math]::Round($os.FreePhysicalMemory / 1MB, 3)
        CommitLimitGB = [math]::Round($commitLimitGB, 3)
        CommittedGB = [math]::Round(($commitLimitGB - $freeCommitGB), 3)
    }
}

function Get-RedGpuSnapshot {
    $nvidiaSmi = Get-Command 'nvidia-smi.exe' -ErrorAction SilentlyContinue
    if (-not $nvidiaSmi) {
        throw 'nvidia-smi.exe is required for the probe VRAM safety gate.'
    }
    $line = @(& $nvidiaSmi.Source --query-gpu=memory.total,memory.used,memory.free --format=csv,noheader,nounits 2>&1) | Select-Object -First 1
    if ($LASTEXITCODE -ne 0 -or -not $line) {
        throw "Unable to query GPU memory through nvidia-smi.exe: $line"
    }
    $parts = @([string]$line -split ',' | ForEach-Object { $_.Trim() })
    if ($parts.Count -ne 3) {
        throw "Unexpected nvidia-smi.exe output: $line"
    }
    [pscustomobject]@{
        TotalMB = [int]$parts[0]
        UsedMB = [int]$parts[1]
        FreeMB = [int]$parts[2]
    }
}

function Get-RedBlockingProcesses {
    try {
        $allProcesses = @(Get-CimInstance Win32_Process -ErrorAction Stop)
    } catch {
        throw "Unable to enumerate blocking processes; refusing to continue: $($_.Exception.Message)"
    }
    if ($null -eq $allProcesses) {
        throw 'Blocking-process enumeration returned no result; refusing to continue.'
    }

    $processes = @($allProcesses | Where-Object {
        $baseName = [System.IO.Path]::GetFileNameWithoutExtension($_.Name)
        ($BlockingExecutableNames -contains $baseName) -or
            (($baseName -eq 'dotnet') -and ($_.CommandLine -match $DotNetHostedBuildPattern))
    })

    @($processes | ForEach-Object {
        [pscustomobject]@{
            Id = $_.ProcessId
            ProcessName = [System.IO.Path]::GetFileNameWithoutExtension($_.Name)
            WorkingSet64 = [uint64]$_.WorkingSetSize
            PrivateMemorySize64 = [uint64]$_.PrivatePageCount
            CommandLine = $_.CommandLine
        }
    })
}

function Assert-RedProtectedCheckpoints {
    $mapHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $ProtectedMap).Hash
    if ($mapHash -ne $ExpectedProtectedMapHash) {
        throw "Protected 50 km map hash changed: $mapHash"
    }
    $markerHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $ProtectedReadyMarker).Hash
    if ($markerHash -ne $ExpectedProtectedReadyMarkerHash) {
        throw "Protected foundation marker hash changed: $markerHash"
    }
}

function Get-RedRollbackBackupPath {
    param(
        [Parameter(Mandatory = $true)][string]$TargetPath,
        [Parameter(Mandatory = $true)][string]$TargetHash,
        [string]$BackupRoot = (Join-Path $DiagnosticsRoot 'AssetBackups')
    )
    Join-Path $BackupRoot ("{0}_{1}{2}" -f
        [System.IO.Path]::GetFileNameWithoutExtension($TargetPath),
        $TargetHash.ToUpperInvariant(),
        [System.IO.Path]::GetExtension($TargetPath))
}

function Restore-RedTargetFromBackupIfNeeded {
    param(
        [Parameter(Mandatory = $true)][string]$TargetPath,
        [Parameter(Mandatory = $true)][string]$ExpectedHash,
        [Parameter(Mandatory = $true)][string]$BackupPath
    )

    $normalizedExpectedHash = $ExpectedHash.ToUpperInvariant()
    $currentHash = $null
    if (Test-Path -LiteralPath $TargetPath) {
        $currentHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $TargetPath).Hash.ToUpperInvariant()
    }
    if ($currentHash -eq $normalizedExpectedHash) {
        return $false
    }
    if (-not (Test-Path -LiteralPath $BackupPath)) {
        throw "Target differs from its pre-run hash and rollback backup is missing: $BackupPath"
    }
    $backupHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $BackupPath).Hash.ToUpperInvariant()
    if ($backupHash -ne $normalizedExpectedHash) {
        throw "Rollback backup hash mismatch: expected=$normalizedExpectedHash actual=$backupHash path=$BackupPath"
    }
    Copy-Item -LiteralPath $BackupPath -Destination $TargetPath -Force
    $restoredHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $TargetPath).Hash.ToUpperInvariant()
    if ($restoredHash -ne $normalizedExpectedHash) {
        throw "Rollback restore hash mismatch: expected=$normalizedExpectedHash actual=$restoredHash"
    }
    return $true
}

function Stop-RedExactProcessTree {
    param([Parameter(Mandatory = $true)]$Process)

    try {
        $Process.Refresh()
        if ($Process.HasExited) {
            return
        }
    } catch {
        throw "Unable to inspect probe PID $($Process.Id) before cleanup: $($_.Exception.Message)"
    }

    & "$env:SystemRoot\System32\taskkill.exe" /PID $Process.Id /T /F | Out-Host
    if ($LASTEXITCODE -ne 0) {
        throw "taskkill failed for probe PID $($Process.Id) with exit code $LASTEXITCODE"
    }
    if (-not $Process.WaitForExit(30000)) {
        throw "Probe PID $($Process.Id) did not exit within 30 seconds after taskkill."
    }
}

function Initialize-RedProcessExitTracking {
    param([Parameter(Mandatory = $true)]$Process)

    try {
        # PowerShell's Start-Process can return a Process object whose native
        # handle is never materialized. If that process exits first, ExitCode
        # remains unavailable even after WaitForExit. Cache the exact started
        # process handle immediately so a zero exit code remains authoritative.
        $null = $Process.Handle
    } catch {
        throw "Unable to initialize exit-code tracking for probe PID $($Process.Id): $($_.Exception.Message)"
    }
    return $Process
}

function Wait-RedBlockingProcessesToDrain {
    param(
        [ValidateRange(1, 60)][int]$TimeoutSeconds = 15,
        [ValidateRange(25, 5000)][int]$PollMilliseconds = 250
    )

    $deadline = [datetime]::UtcNow.AddSeconds($TimeoutSeconds)
    do {
        $remaining = @(Get-RedBlockingProcesses)
        if ($remaining.Count -eq 0) {
            return @()
        }
        if ([datetime]::UtcNow -ge $deadline) {
            return $remaining
        }
        Start-Sleep -Milliseconds $PollMilliseconds
    } while ($true)
}

function Test-RedRuntimeDeadlineExceeded {
    param(
        [Parameter(Mandatory = $true)][datetime]$StartedUtc,
        [Parameter(Mandatory = $true)][int]$MaximumMinutes,
        [datetime]$NowUtc = [datetime]::UtcNow
    )
    return $NowUtc -ge $StartedUtc.AddMinutes($MaximumMinutes)
}

function Assert-RedProbeMarkerSchema {
    param(
        [Parameter(Mandatory = $true)]$Result,
        [int]$ExpectedProtectedHashCount = 6
    )

    $requiredProperties = @(
        'target',
        'target_hash_before',
        'target_hash_after',
        'rollback_backup',
        'desired_switches',
        'changed',
        'protected_hash_count'
    )
    $propertyNames = @($Result.PSObject.Properties.Name)
    foreach ($propertyName in $requiredProperties) {
        if ($propertyNames -notcontains $propertyName) {
            throw "Probe success marker is missing required property: $propertyName"
        }
    }
    if (-not ($Result.changed -is [bool])) {
        throw 'Probe success marker property changed must be a JSON boolean.'
    }
    foreach ($hashName in @('target_hash_before', 'target_hash_after')) {
        $hashValue = [string]$Result.$hashName
        if ($hashValue -notmatch '^[A-Fa-f0-9]{64}$') {
            throw "Probe success marker property $hashName is not a SHA-256 hash."
        }
    }
    if (($Result.protected_hash_count -isnot [int]) -and
        ($Result.protected_hash_count -isnot [long])) {
        throw 'Probe success marker property protected_hash_count must be an integer.'
    }
    if ([int64]$Result.protected_hash_count -ne $ExpectedProtectedHashCount) {
        throw "Probe success marker has wrong protected_hash_count: $($Result.protected_hash_count)"
    }
    if ($null -eq $Result.desired_switches) {
        throw 'Probe success marker is missing desired_switches data.'
    }
    $switchNames = @($Result.desired_switches.PSObject.Properties.Name)
    foreach ($switchName in @('SimpleSparkle?', 'SparklShrinkNear?')) {
        if ($switchNames -notcontains $switchName -or
            -not ($Result.desired_switches.$switchName -is [bool])) {
            throw "Probe success marker switch $switchName must be a JSON boolean."
        }
    }
    if ($Result.changed) {
        if (-not ($Result.rollback_backup -is [string]) -or
            [string]::IsNullOrWhiteSpace([string]$Result.rollback_backup)) {
            throw 'A changed probe result must name a rollback backup.'
        }
    } elseif ($null -ne $Result.rollback_backup) {
        throw 'An idempotent probe result must have a null rollback_backup.'
    }
}

function Assert-RedProbeResultPostconditions {
    param(
        [Parameter(Mandatory = $true)]$Result,
        [Parameter(Mandatory = $true)][string]$ExpectedTarget,
        [Parameter(Mandatory = $true)][string]$TargetHashBefore,
        [Parameter(Mandatory = $true)][string]$TargetHashAfter
    )

    Assert-RedProbeMarkerSchema -Result $Result
    if ($Result.target -ne $ExpectedTarget) {
        throw "Probe success marker names the wrong target: $($Result.target)"
    }
    if (($Result.desired_switches.'SimpleSparkle?' -ne $true) -or
        ($Result.desired_switches.'SparklShrinkNear?' -ne $false)) {
        throw 'Probe success marker does not contain the exact desired switch pair.'
    }
    if ($Result.target_hash_before.ToUpperInvariant() -ne $TargetHashBefore.ToUpperInvariant() -or
        $Result.target_hash_after.ToUpperInvariant() -ne $TargetHashAfter.ToUpperInvariant()) {
        throw 'Probe success-marker hashes do not match the actual target file.'
    }
    if ($Result.changed) {
        if ($TargetHashAfter -eq $TargetHashBefore) {
            throw 'Probe reported a write but the target hash did not change.'
        }
        if (-not (Test-Path -LiteralPath $Result.rollback_backup)) {
            throw 'Probe changed the target without a durable rollback backup.'
        }
        $backupHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $Result.rollback_backup).Hash
        if ($backupHash -ne $TargetHashBefore) {
            throw 'Probe rollback backup does not match the exact pre-write target hash.'
        }
    } elseif ($TargetHashAfter -ne $TargetHashBefore) {
        throw 'Idempotent probe changed the target file unexpectedly.'
    }
}

function Write-RedSample {
    param(
        [Parameter(Mandatory = $true)]$Memory,
        [Parameter(Mandatory = $true)]$Gpu,
        [Parameter(Mandatory = $true)][int]$Index
    )
    Write-Host ("Probe preflight sample {0}/{1}: freeCommit={2:N3} GB freePhysical={3:N3} GB freeVRAM={4} MB" -f
        $Index, $SustainedSampleCount, $Memory.FreeCommitGB, $Memory.FreePhysicalGB, $Gpu.FreeMB)
}

function Invoke-RedSandSparkleMaskProbeMain {
foreach ($requiredPath in @(
    $ProjectFile,
    $ProbeScript,
    $EditorCmd,
    $ProtectedMap,
    $ProtectedReadyMarker,
    $TargetAssetFile
)) {
    if (-not (Test-Path -LiteralPath $requiredPath)) {
        throw "Required path is missing: $requiredPath"
    }
}

if ($AbortFreeCommitGB -ge $MinimumFreeCommitGB) {
    throw 'AbortFreeCommitGB must be lower than MinimumFreeCommitGB.'
}
if ($AbortFreePhysicalGB -ge $MinimumFreePhysicalGB) {
    throw 'AbortFreePhysicalGB must be lower than MinimumFreePhysicalGB.'
}
if ($AbortFreeVramMB -ge $MinimumFreeVramMB) {
    throw 'AbortFreeVramMB must be lower than MinimumFreeVramMB.'
}

Assert-RedProtectedCheckpoints
$targetHashBefore = (Get-FileHash -Algorithm SHA256 -LiteralPath $TargetAssetFile).Hash
$preflightProcesses = @(Get-RedBlockingProcesses)
if ($preflightProcesses.Count -gt 0) {
    foreach ($process in $preflightProcesses) {
        Write-Host ("Blocking PID {0} {1} workingSet={2:N2} GB private={3:N2} GB" -f
            $process.Id,
            $process.ProcessName,
            ($process.WorkingSet64 / 1GB),
            ($process.PrivateMemorySize64 / 1GB))
    }
    Write-Warning 'Probe not started because an Unreal, Titan, build, shader, or crash-reporter process is active.'
    exit 20
}

$samples = @()
for ($sampleIndex = 1; $sampleIndex -le $SustainedSampleCount; $sampleIndex++) {
    $memory = Get-RedMemorySnapshot
    $gpu = Get-RedGpuSnapshot
    Write-RedSample -Memory $memory -Gpu $gpu -Index $sampleIndex
    $samples += [pscustomobject]@{
        FreeCommitGB = $memory.FreeCommitGB
        FreePhysicalGB = $memory.FreePhysicalGB
        FreeVramMB = $gpu.FreeMB
    }
    if ($sampleIndex -lt $SustainedSampleCount) {
        Start-Sleep -Seconds $SampleIntervalSeconds
    }
}

$preflightProcesses = @(Get-RedBlockingProcesses)
$minimumObservedCommitGB = ($samples | Measure-Object -Property FreeCommitGB -Minimum).Minimum
$minimumObservedPhysicalGB = ($samples | Measure-Object -Property FreePhysicalGB -Minimum).Minimum
$minimumObservedVramMB = ($samples | Measure-Object -Property FreeVramMB -Minimum).Minimum
$preflightPassed = ($minimumObservedCommitGB -ge $MinimumFreeCommitGB) -and
    ($minimumObservedPhysicalGB -ge $MinimumFreePhysicalGB) -and
    ($minimumObservedVramMB -ge $MinimumFreeVramMB) -and
    ($preflightProcesses.Count -eq 0)

if (-not $preflightPassed) {
    Write-Warning ("Probe not started. Sustained minima: commit={0:N3} GB physical={1:N3} GB VRAM={2} MB blockers={3}. Required: commit >= {4:N1} GB, physical >= {5:N1} GB, VRAM >= {6} MB, blockers=0." -f
        $minimumObservedCommitGB,
        $minimumObservedPhysicalGB,
        $minimumObservedVramMB,
        $preflightProcesses.Count,
        $MinimumFreeCommitGB,
        $MinimumFreePhysicalGB,
        $MinimumFreeVramMB)
    exit 20
}

if ($PreflightOnly) {
    Write-Host 'Sustained probe preflight passed; no Unreal process or asset write was requested.'
    exit 0
}

$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$runRoot = Join-Path $DiagnosticsRoot "Runtime_$stamp"
if (Test-Path -LiteralPath $runRoot) {
    throw "Refusing to reuse an existing diagnostic directory: $runRoot"
}
New-Item -ItemType Directory -Path $runRoot | Out-Null
$stdoutLog = Join-Path $runRoot 'stdout.log'
$stderrLog = Join-Path $runRoot 'stderr.log'
$unrealLog = Join-Path $runRoot 'unreal.log'
$guardLog = Join-Path $runRoot 'resource_guard.log'

$arguments = @(
    ('"{0}"' -f $ProjectFile),
    '-run=pythonscript',
    ('-script="{0}"' -f $ProbeScript),
    $WriteFlag,
    '-NullRHI',
    '-unattended',
    '-nop4',
    '-nosplash',
    '-NoSound',
    '-stdout',
    '-UTF8Output',
    '-NoLogTimes',
    ('-AbsLog="{0}"' -f $unrealLog)
)

Write-Host "Starting isolated sand mask probe in $runRoot"
$process = $null
$failureExitCode = 32
$targetHashAfter = $null
$deterministicBackupPath = Get-RedRollbackBackupPath -TargetPath $TargetAssetFile -TargetHash $targetHashBefore
try {
    $process = Start-Process -FilePath $EditorCmd -ArgumentList ($arguments -join ' ') -PassThru -NoNewWindow `
        -RedirectStandardOutput $stdoutLog -RedirectStandardError $stderrLog
    $process = Initialize-RedProcessExitTracking -Process $process
    $startedUtc = [datetime]::UtcNow
    $abortReason = $null
    while (-not $process.HasExited) {
        Start-Sleep -Seconds $PollSeconds
        $process.Refresh()
        if (Test-RedRuntimeDeadlineExceeded -StartedUtc $startedUtc -MaximumMinutes $MaximumRuntimeMinutes) {
            $abortReason = "runtime exceeded the $MaximumRuntimeMinutes minute safety limit"
        }

        $memory = Get-RedMemorySnapshot
        $gpu = Get-RedGpuSnapshot
        $guardLine = "$(Get-Date -Format o) pid=$($process.Id) freeCommitGB=$($memory.FreeCommitGB) freePhysicalGB=$($memory.FreePhysicalGB) freeVramMB=$($gpu.FreeMB)"
        Add-Content -LiteralPath $guardLog -Value $guardLine
        Write-Host $guardLine

        if (-not $abortReason -and $memory.FreeCommitGB -lt $AbortFreeCommitGB) {
            $abortReason = "free commit fell below $AbortFreeCommitGB GB"
        }
        if (-not $abortReason -and $memory.FreePhysicalGB -lt $AbortFreePhysicalGB) {
            $abortReason = "free physical memory fell below $AbortFreePhysicalGB GB"
        }
        if (-not $abortReason -and $gpu.FreeMB -lt $AbortFreeVramMB) {
            $abortReason = "free VRAM fell below $AbortFreeVramMB MB"
        }

        if (-not $abortReason) {
            $tail = @()
            foreach ($path in @($stdoutLog, $stderrLog, $unrealLog)) {
                if (Test-Path -LiteralPath $path) {
                    $tail += @(Get-Content -LiteralPath $path -Tail 180 -ErrorAction Stop)
                }
            }
            $unsafe = $tail | Select-String -Pattern 'Fatal error|Assertion failed|Unhandled Exception|GPU device removed|Out of video memory|NNERuntimeORT.*bad allocation|VirtualAlloc.*failed|paging file is too small|out of memory' | Select-Object -First 1
            if ($unsafe) {
                $abortReason = "unsafe Unreal signature: $($unsafe.Line.Trim())"
            }
        }

        if ($abortReason) {
            $failureExitCode = 21
            throw "Sand mask probe aborted safely: $abortReason"
        }
    }

    $process.WaitForExit()
    $process.Refresh()
    if ($null -eq $process.ExitCode -or $process.ExitCode -ne 0) {
        $displayExitCode = if ($null -eq $process.ExitCode) { '<unavailable>' } else { [string]$process.ExitCode }
        $failureExitCode = 22
        throw "Sand mask probe failed with exit code $displayExitCode. Logs: $runRoot"
    }
    # UE starts CrashReportClientEditor as a normal session helper even when no
    # crash occurs. Give commandlet descendants a bounded shutdown grace period;
    # anything still present then remains a hard failure.
    $postRunProcesses = @(Wait-RedBlockingProcessesToDrain)
    if ($postRunProcesses.Count -gt 0) {
        $failureExitCode = 22
        throw "A blocking Unreal/build process remained after the probe commandlet exited: $($postRunProcesses.ProcessName -join ', ')"
    }

    $allLogLines = @()
    foreach ($path in @($stdoutLog, $stderrLog, $unrealLog)) {
        if (Test-Path -LiteralPath $path) {
            $allLogLines += @(Get-Content -LiteralPath $path -ErrorAction Stop)
        }
    }
    $failureMarker = $allLogLines | Select-String -Pattern 'Fatal error|Assertion failed|Unhandled Exception|GPU device removed|Out of video memory|Failed to compile Material|\[SM6\].*error|Mask-probe preparation failed' | Select-Object -First 1
    if ($failureMarker) {
        $failureExitCode = 23
        throw "Probe log contains a failure marker: $($failureMarker.Line.Trim())"
    }
    $successLine = $allLogLines | Select-String -Pattern 'RED_SAND_MASK_PROBE_PREPARED\s+\{' | Select-Object -Last 1
    if (-not $successLine) {
        $failureExitCode = 24
        throw "Probe exited without the required success marker. Logs: $runRoot"
    }
    $jsonText = $successLine.Line.Substring($successLine.Line.IndexOf('{'))
    try {
        $result = $jsonText | ConvertFrom-Json -ErrorAction Stop
    } catch {
        $failureExitCode = 24
        throw "Probe emitted malformed success-marker JSON: $($_.Exception.Message)"
    }

    Assert-RedProtectedCheckpoints
    $targetHashAfter = (Get-FileHash -Algorithm SHA256 -LiteralPath $TargetAssetFile).Hash
    $failureExitCode = 25
    Assert-RedProbeResultPostconditions `
        -Result $result `
        -ExpectedTarget $TargetAssetPath `
        -TargetHashBefore $targetHashBefore `
        -TargetHashAfter $targetHashAfter
} catch {
    $primaryFailure = $_.Exception.Message
    $recoveryErrors = @()
    if ($null -ne $process) {
        try {
            Stop-RedExactProcessTree -Process $process
        } catch {
            $recoveryErrors += "process cleanup failed: $($_.Exception.Message)"
        }
    }
    try {
        $restored = Restore-RedTargetFromBackupIfNeeded `
            -TargetPath $TargetAssetFile `
            -ExpectedHash $targetHashBefore `
            -BackupPath $deterministicBackupPath
        if ($restored) {
            Add-Content -LiteralPath $guardLog -Value "$(Get-Date -Format o) restoredTarget=$TargetAssetFile backup=$deterministicBackupPath"
        }
    } catch {
        $recoveryErrors += "target rollback failed: $($_.Exception.Message)"
    }
    try {
        Assert-RedProtectedCheckpoints
    } catch {
        $recoveryErrors += "protected checkpoint verification failed: $($_.Exception.Message)"
    }

    if ($recoveryErrors.Count -gt 0) {
        $failureExitCode = 33
        $primaryFailure = "$primaryFailure Recovery errors: $($recoveryErrors -join ' | ')"
    }
    [Console]::Error.WriteLine($primaryFailure)
    exit $failureExitCode
}

Write-Host 'Sand mask probe preparation passed its guarded runtime and hash gates.'
Write-Host "Result logs: $runRoot"
Write-Host "Target hash: $targetHashAfter"
Write-Host 'Visual sparkle acceptance is still pending a capped real-GPU capture.'
exit 0
}

if ($MyInvocation.InvocationName -ne '.') {
    Invoke-RedSandSparkleMaskProbeMain
}
