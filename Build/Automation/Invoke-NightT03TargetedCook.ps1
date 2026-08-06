[CmdletBinding()]
param(
    [switch]$PreflightOnly,
    [double]$MinimumFreeCommitGB = 12.0,
    [double]$MinimumFreePhysicalGB = 8.0,
    [double]$AbortFreeCommitGB = 8.0,
    [double]$AbortFreePhysicalGB = 6.0,
    [int]$PollSeconds = 5,
    [string]$SandboxRoot = ""
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 2.0

$ProjectRoot = 'D:\RedMMOTitan'
$ProjectFile = Join-Path $ProjectRoot 'Titan.uproject'
$EditorCmd = 'D:\UE_5.8\Engine\Binaries\Win64\UnrealEditor-Cmd.exe'
$DiagnosticsRoot = 'D:\RedMMOTitanWindowsData\Diagnostics'
$CookRoot = 'D:\RedMMOTitanWindowsData\CookSandboxes'
$ProtectedCheckpoint = 'D:\RedMMOTitanWindowsData\PackagedBuilds\Development_50KM_FOUNDATION_20260716_064703'
$MapPackage = '/Game/RedMMO/Maps/Tests/RedPlanetGen_50km_FusedPrototype_Night_T03'
$DiagnosticMaterialPackage = '/Game/RedMMO/Environment/Tests/M_RedStar_T03Diagnostic'
$MilkyWayMaterialPackage = '/Game/RedMMO/Environment/Tests/M_RedStar_T03MilkyWayWorldDir'
$MilkyWayTexturePackage = '/Game/SpaceColony/Textures/T_milky_way'
$EngineBasicSpherePackage = '/Engine/BasicShapes/Sphere'
$EngineSkySpherePackage = '/Engine/EngineSky/SM_SkySphere'
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
        FreeCommitGB = [math]::Round($freeCommitGB, 2)
        FreePhysicalGB = [math]::Round($os.FreePhysicalMemory / 1MB, 2)
        CommitLimitGB = [math]::Round($commitLimitGB, 2)
        CommittedGB = [math]::Round(($commitLimitGB - $freeCommitGB), 2)
    }
}

function Get-RedBlockingProcesses {
    $processes = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
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

function Write-RedPreflightSummary {
    param(
        [Parameter(Mandatory = $true)]$Memory,
        [Parameter(Mandatory = $true)][AllowEmptyCollection()][object[]]$Processes
    )

    Write-Host ("Night_T03 cook preflight: freeCommit={0:N2} GB committed={1:N2} GB commitLimit={2:N2} GB freePhysical={3:N2} GB blockers={4}" -f
        $Memory.FreeCommitGB, $Memory.CommittedGB, $Memory.CommitLimitGB, $Memory.FreePhysicalGB, $Processes.Count)
    foreach ($process in $Processes) {
        Write-Host ("  PID {0} {1} workingSet={2:N2} GB private={3:N2} GB" -f
            $process.Id,
            $process.ProcessName,
            ($process.WorkingSet64 / 1GB),
            ($process.PrivateMemorySize64 / 1GB))
    }
}

foreach ($requiredPath in @($ProjectFile, $EditorCmd, $ProtectedCheckpoint)) {
    if (-not (Test-Path -LiteralPath $requiredPath)) {
        throw "Required path is missing: $requiredPath"
    }
}

$preflightMemory = Get-RedMemorySnapshot
$preflightProcesses = @(Get-RedBlockingProcesses)
Write-RedPreflightSummary -Memory $preflightMemory -Processes $preflightProcesses

$preflightPassed = ($preflightMemory.FreeCommitGB -ge $MinimumFreeCommitGB) -and
    ($preflightMemory.FreePhysicalGB -ge $MinimumFreePhysicalGB) -and
    ($preflightProcesses.Count -eq 0)

if (-not $preflightPassed) {
    Write-Warning ("Cook not started. Required: free commit >= {0:N1} GB, free physical >= {1:N1} GB, and no Unreal/Titan/UAT/shader/crash-reporter process." -f
        $MinimumFreeCommitGB, $MinimumFreePhysicalGB)
    exit 20
}

if ($PreflightOnly) {
    Write-Host 'Preflight passed; no cook was requested.'
    exit 0
}

if ([string]::IsNullOrWhiteSpace($SandboxRoot)) {
    $stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
    $SandboxRoot = Join-Path $CookRoot "Night_T03_$stamp\Windows"
}

if (Test-Path -LiteralPath $SandboxRoot) {
    throw "Refusing to reuse or clean an existing cook sandbox: $SandboxRoot"
}

$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$stdoutLog = Join-Path $DiagnosticsRoot "night_t03_targeted_cook_${stamp}.stdout.log"
$stderrLog = Join-Path $DiagnosticsRoot "night_t03_targeted_cook_${stamp}.stderr.log"
$absoluteLog = Join-Path $DiagnosticsRoot "night_t03_targeted_cook_${stamp}.log"

New-Item -ItemType Directory -Force -Path $DiagnosticsRoot, $CookRoot, $SandboxRoot | Out-Null

$packageList = @(
    $MapPackage,
    $DiagnosticMaterialPackage,
    $MilkyWayMaterialPackage,
    $MilkyWayTexturePackage,
    $EngineBasicSpherePackage,
    $EngineSkySpherePackage
) -join '+'
$arguments = @(
    ('"{0}"' -f $ProjectFile),
    '-run=Cook',
    '-TargetPlatform=Windows',
    ('-PACKAGE={0}' -f $packageList),
    ('-OutputDir="{0}"' -f $SandboxRoot),
    '-NoGameAlwaysCook',
    '-NoDefaultMaps',
    '-stdout',
    '-unattended',
    '-NoLogTimes',
    '-UTF8Output',
    ('-AbsLog="{0}"' -f $absoluteLog)
)

Write-Host "Starting isolated targeted cook in $SandboxRoot"
$process = Start-Process -FilePath $EditorCmd -ArgumentList ($arguments -join ' ') -PassThru -NoNewWindow `
    -RedirectStandardOutput $stdoutLog -RedirectStandardError $stderrLog

$abortReason = $null
while (-not $process.HasExited) {
    Start-Sleep -Seconds $PollSeconds
    $process.Refresh()
    $memory = Get-RedMemorySnapshot
    Write-Host ("Cook PID {0}: freeCommit={1:N2} GB freePhysical={2:N2} GB" -f
        $process.Id, $memory.FreeCommitGB, $memory.FreePhysicalGB)

    if ($memory.FreeCommitGB -lt $AbortFreeCommitGB) {
        $abortReason = "free commit fell below the $AbortFreeCommitGB GB abort threshold"
    }
    if (-not $abortReason -and $memory.FreePhysicalGB -lt $AbortFreePhysicalGB) {
        $abortReason = "free physical memory fell below the $AbortFreePhysicalGB GB abort threshold"
    }

    if (-not $abortReason) {
        $tail = @()
        foreach ($cookLog in @($stdoutLog, $stderrLog, $absoluteLog)) {
            if (Test-Path -LiteralPath $cookLog) {
                $tail += @(Get-Content -LiteralPath $cookLog -Tail 160 -ErrorAction SilentlyContinue)
            }
        }
        # UE 5.8 labels a fresh loose cook as "FULL COOK" even when the
        # command line is explicitly request-scoped with -PACKAGE. That line
        # means all dependencies discovered by this request, not CookAll.
        # Memory floors still guard the size of the discovered dependency set.
        $fatalLine = $tail | Select-String -Pattern 'NNERuntimeORT.*bad allocation|VirtualAlloc.*failed|paging file is too small|out of memory' | Select-Object -First 1
        if ($fatalLine) {
            $abortReason = "unsafe cooker signature: $($fatalLine.Line.Trim())"
        }
    }

    if ($abortReason) {
        Write-Warning "Aborting targeted cook: $abortReason"
        & "$env:SystemRoot\System32\taskkill.exe" /PID $process.Id /T /F | Out-Host
        break
    }
}

$process.WaitForExit()
if ($abortReason) {
    Write-Error "Targeted cook aborted safely: $abortReason"
    exit 21
}
$process.Refresh()
$exitCode = $process.ExitCode
if ($null -eq $exitCode) {
    # Start-Process can lose the native exit-code value after a long redirected
    # commandlet run even though WaitForExit completed. Fail closed unless the
    # unique logs from this invocation contain both Unreal's success marker and
    # clean shutdown marker, with no crash/error signature.
    $cookLines = @()
    foreach ($cookLog in @($stdoutLog, $stderrLog, $absoluteLog)) {
        if (Test-Path -LiteralPath $cookLog) {
            $cookLines += @(Get-Content -LiteralPath $cookLog -ErrorAction SilentlyContinue)
        }
    }
    $hasSuccessMarker = [bool]($cookLines | Select-String -SimpleMatch 'Success - 0 error(s)' | Select-Object -First 1)
    $hasCleanExitMarker = [bool]($cookLines | Select-String -SimpleMatch 'LogExit: Exiting.' | Select-Object -First 1)
    $hasFailureMarker = [bool]($cookLines | Select-String -Pattern 'Fatal error|Assertion failed|Unhandled Exception|Cook failed|GPU device removed|NNERuntimeORT.*bad allocation|VirtualAlloc.*failed|paging file is too small|out of memory' | Select-Object -First 1)
    if ($hasSuccessMarker -and $hasCleanExitMarker -and -not $hasFailureMarker) {
        Write-Warning 'Cook process exit code was unavailable; accepting Unreal success plus clean-exit log markers.'
        $exitCode = 0
    }
}
if (($null -eq $exitCode) -or ($exitCode -ne 0)) {
    $displayExitCode = if ($null -eq $exitCode) { '<unavailable>' } else { [string]$exitCode }
    Write-Error "Targeted cook failed with exit code $displayExitCode. Logs: $stdoutLog ; $stderrLog ; $absoluteLog"
    exit 22
}

$mapFile = Join-Path $SandboxRoot 'Titan\Content\RedMMO\Maps\Tests\RedPlanetGen_50km_FusedPrototype_Night_T03.umap'
$materialFile = Join-Path $SandboxRoot 'Titan\Content\RedMMO\Environment\Tests\M_RedStar_T03Diagnostic.uasset'
$milkyWayMaterialFile = Join-Path $SandboxRoot 'Titan\Content\RedMMO\Environment\Tests\M_RedStar_T03MilkyWayWorldDir.uasset'
$milkyWayTextureFile = Join-Path $SandboxRoot 'Titan\Content\SpaceColony\Textures\T_milky_way.uasset'
$engineBasicSphereFile = Join-Path $SandboxRoot 'Engine\Content\BasicShapes\Sphere.uasset'
$engineSkySphereFile = Join-Path $SandboxRoot 'Engine\Content\EngineSky\SM_SkySphere.uasset'
$globalShaders = @(Get-ChildItem -LiteralPath $SandboxRoot -Filter 'GlobalShaderCache-*.bin' -Recurse -File -ErrorAction SilentlyContinue)

$missing = @()
if (-not (Test-Path -LiteralPath $mapFile)) { $missing += $mapFile }
if (-not (Test-Path -LiteralPath $materialFile)) { $missing += $materialFile }
if (-not (Test-Path -LiteralPath $milkyWayMaterialFile)) { $missing += $milkyWayMaterialFile }
if (-not (Test-Path -LiteralPath $milkyWayTextureFile)) { $missing += $milkyWayTextureFile }
if (-not (Test-Path -LiteralPath $engineBasicSphereFile)) { $missing += $engineBasicSphereFile }
if (-not (Test-Path -LiteralPath $engineSkySphereFile)) { $missing += $engineSkySphereFile }
if ($globalShaders.Count -eq 0) { $missing += 'GlobalShaderCache-*.bin' }
if ($missing.Count -gt 0) {
    Write-Error ("Cook exited successfully but the isolated sandbox is incomplete: {0}" -f ($missing -join '; '))
    exit 23
}

Write-Host 'Targeted cook passed artifact validation.'
Write-Host "Sandbox: $SandboxRoot"
Write-Host "Runtime: D:\RedMMOTitan\Binaries\Win64\Titan.exe $MapPackage -Sandbox=$SandboxRoot -game -windowed -ResX=960 -ResY=540 -NoSplash -NoSound -NoAutoMatch -RedNativeDiagnosticPawn -log"
exit 0
