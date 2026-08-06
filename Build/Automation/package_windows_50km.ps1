param(
    [ValidatePattern('^[A-Za-z0-9_-]+$')]
    [string]$ArchiveLabel = 'FOUNDATION',

    [switch]$FreshCook,

    [switch]$Include50KmCheckpoints,

    [switch]$PreflightOnly,

    [ValidateRange(24.0, 128.0)]
    [double]$MinimumFreeCommitGB = 26.0,

    [ValidateRange(18.0, 128.0)]
    [double]$MinimumFreePhysicalGB = 20.0,

    [ValidateRange(1.0, 128.0)]
    [double]$AbortFreeCommitGB = 16.0,

    [ValidateRange(1.0, 128.0)]
    [double]$AbortFreePhysicalGB = 12.0,

    [ValidateRange(6, 60)]
    [int]$PreflightSamples = 12,

    [ValidateRange(1, 10)]
    [int]$PreflightSampleSeconds = 1,

    [ValidateRange(1, 60)]
    [int]$PollSeconds = 2
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 2.0

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$Project = (Resolve-Path (Join-Path $ProjectRoot 'Titan.uproject')).Path
$RunUAT = 'D:\UE_5.8\Engine\Build\BatchFiles\RunUAT.bat'
$ProtectedCheckpoint = 'D:\RedMMOTitanWindowsData\PackagedBuilds\Development_50KM_FOUNDATION_20260716_064703'
$ProtectedMap = Join-Path $ProjectRoot 'Content\RedMMO\Maps\RedPlanetGen_50km_Test.umap'
$ProtectedReadyMarker = Join-Path $ProtectedCheckpoint 'REDMMO_PACKAGE_READY.txt'
$ExpectedProtectedMapHash = 'DA5987012EEB8F550254F5FCF0F47F42B8F5E03428CF4881C83D8687537F6E7D'
$ExpectedProtectedReadyMarkerHash = '26B00A20C4B18717CEC36B5CA289CC9001AE1E65DA649404ACC8721F14EF26E8'
$FusedPrototypeMap = Join-Path $ProjectRoot 'Content\RedMMO\Maps\RedPlanetGen_50km_FusedPrototype.umap'
$ExpectedFusedPrototypeHash = '4C84D7752C87854C70987ED9988C64C124C577FBE1DE3DEF3CC826F81B0B6284'
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

function Get-RedPackagePhase {
    param(
        [Parameter(Mandatory = $true)][string]$LogPath,
        [ValidateSet('automation_startup', 'build', 'cook', 'stage', 'package', 'archive', 'complete')]
        [string]$PreviousPhase = 'automation_startup'
    )

    if (-not (Test-Path -LiteralPath $LogPath)) {
        return $PreviousPhase
    }

    $tail = @(Get-Content -LiteralPath $LogPath -Tail 800 -ErrorAction SilentlyContinue)
    $candidatePhase = 'automation_startup'
    if ($tail -match 'BUILD SUCCESSFUL') {
        $candidatePhase = 'complete'
    }
    elseif ($tail -match 'ARCHIVE COMMAND STARTED') {
        $candidatePhase = 'archive'
    }
    elseif ($tail -match 'PACKAGE COMMAND STARTED') {
        $candidatePhase = 'package'
    }
    elseif ($tail -match 'STAGE COMMAND STARTED') {
        $candidatePhase = 'stage'
    }
    elseif ($tail -match 'COOK COMMAND STARTED') {
        $candidatePhase = 'cook'
    }
    elseif ($tail -match 'BUILD COMMAND STARTED') {
        $candidatePhase = 'build'
    }

    $phaseRank = @{
        automation_startup = 0
        build = 1
        cook = 2
        stage = 3
        package = 4
        archive = 5
        complete = 6
    }
    if ($phaseRank[$candidatePhase] -gt $phaseRank[$PreviousPhase]) {
        return $candidatePhase
    }
    return $PreviousPhase
}

function Write-RedPreflightSummary {
    param(
        [Parameter(Mandatory = $true)]$Memory,
        [Parameter(Mandatory = $true)][AllowEmptyCollection()][object[]]$Processes,
        [Parameter(Mandatory = $true)][int]$SampleCount,
        [Parameter(Mandatory = $true)][int]$SampleSeconds
    )

    Write-Host ("Windows package sustained preflight: samples={0} interval={1}s minFreeCommit={2:N2} GB maxCommitted={3:N2} GB commitLimit={4:N2} GB minFreePhysical={5:N2} GB blockersSeen={6}" -f
        $SampleCount, $SampleSeconds, $Memory.FreeCommitGB, $Memory.CommittedGB, $Memory.CommitLimitGB, $Memory.FreePhysicalGB, $Processes.Count)
    foreach ($process in $Processes) {
        Write-Host ("  PID {0} {1} workingSet={2:N2} GB private={3:N2} GB" -f
            $process.Id,
            $process.ProcessName,
            ($process.WorkingSet64 / 1GB),
            ($process.PrivateMemorySize64 / 1GB))
    }
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

function Get-RedFusedPrototypeSourceHash {
    if (-not (Test-Path -LiteralPath $FusedPrototypeMap)) {
        throw "Fused prototype source map is missing: $FusedPrototypeMap"
    }

    $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $FusedPrototypeMap).Hash
    if ($hash -ne $ExpectedFusedPrototypeHash) {
        throw "Fused prototype source hash changed. Expected $ExpectedFusedPrototypeHash, got $hash."
    }
    return $hash
}

foreach ($requiredPath in @($Project, $RunUAT, $ProtectedCheckpoint, $ProtectedMap, $ProtectedReadyMarker)) {
    if (-not (Test-Path -LiteralPath $requiredPath)) {
        throw "Required path is missing: $requiredPath"
    }
}
Assert-RedProtectedCheckpoints
$FusedPrototypeSourceHash = $null
if ($Include50KmCheckpoints) {
    # Capture the exact source input before UAT so the ready marker can prove
    # which fused-map bytes were eligible for this package.
    $FusedPrototypeSourceHash = Get-RedFusedPrototypeSourceHash
}

if ($AbortFreeCommitGB -ge $MinimumFreeCommitGB) {
    throw 'AbortFreeCommitGB must be lower than MinimumFreeCommitGB.'
}
if ($AbortFreePhysicalGB -ge $MinimumFreePhysicalGB) {
    throw 'AbortFreePhysicalGB must be lower than MinimumFreePhysicalGB.'
}
if ($Include50KmCheckpoints -and -not $FreshCook) {
    throw 'Include50KmCheckpoints requires FreshCook; iterative cook cannot prove fused source currency.'
}

$preflightMemorySamples = @()
$preflightProcesses = @()
for ($preflightIndex = 0; $preflightIndex -lt $PreflightSamples; $preflightIndex++) {
    $preflightMemorySamples += Get-RedMemorySnapshot
    $preflightProcesses += @(Get-RedBlockingProcesses)
    if ($preflightIndex -lt ($PreflightSamples - 1)) {
        Start-Sleep -Seconds $PreflightSampleSeconds
    }
}
$preflightProcesses = @($preflightProcesses | Sort-Object -Property Id -Unique)
$lastPreflightMemory = $preflightMemorySamples[-1]
$preflightMemory = [pscustomobject]@{
    FreeCommitGB = [math]::Round(($preflightMemorySamples | Measure-Object -Property FreeCommitGB -Minimum).Minimum, 2)
    FreePhysicalGB = [math]::Round(($preflightMemorySamples | Measure-Object -Property FreePhysicalGB -Minimum).Minimum, 2)
    CommitLimitGB = $lastPreflightMemory.CommitLimitGB
    CommittedGB = [math]::Round(($preflightMemorySamples | Measure-Object -Property CommittedGB -Maximum).Maximum, 2)
}
Write-RedPreflightSummary -Memory $preflightMemory -Processes $preflightProcesses `
    -SampleCount $PreflightSamples -SampleSeconds $PreflightSampleSeconds

$preflightPassed = ($preflightMemory.FreeCommitGB -ge $MinimumFreeCommitGB) -and
    ($preflightMemory.FreePhysicalGB -ge $MinimumFreePhysicalGB) -and
    ($preflightProcesses.Count -eq 0)

if (-not $preflightPassed) {
    Write-Warning ("Package not started. Sustained minimums across {0} samples must be: free commit >= {1:N1} GB, free physical >= {2:N1} GB, and no Unreal/Titan/UAT/shader/crash-reporter process may appear." -f
        $PreflightSamples, $MinimumFreeCommitGB, $MinimumFreePhysicalGB)
    exit 20
}

if ($PreflightOnly) {
    Write-Host 'Preflight passed; no build or cook was requested.'
    exit 0
}

$Stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$BuildTimestampUtc = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
$SourceRevision = (& git -C $ProjectRoot rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0 -or -not $SourceRevision) {
    throw 'Unable to capture the packaging-time Git revision.'
}
$DirtyLines = @(& git -C $ProjectRoot status --porcelain)
if ($LASTEXITCODE -ne 0) {
    throw 'Unable to capture the packaging-time Git dirty state.'
}
$SourceDirty = if ($DirtyLines.Count -gt 0) { 'true' } else { 'false' }
$Archive = "D:\RedMMOTitanWindowsData\PackagedBuilds\Development_50KM_${ArchiveLabel}_$Stamp"
$Log = "D:\RedMMOTitanWindowsData\BuildLogs\Package50km_$Stamp.log"
$ErrorLog = "$Log.stderr.log"
$GuardLog = "$Log.memory-guard.log"
$ExitFile = "$Log.exitcode"
$ReadyMarkerPath = Join-Path $Archive 'REDMMO_PACKAGE_READY.txt'
$ReadyMarkerTemp = "$ReadyMarkerPath.tmp"
$ReadyMarkerTempCreatedByThisRun = $false
$ReadyMarkerPublishedByThisRun = $false

New-Item -ItemType Directory -Force -Path (Split-Path $Log), (Split-Path $Archive) | Out-Null
Set-Content -LiteralPath 'D:\RedMMOTitanWindowsData\BuildLogs\LatestPackage50km.txt' -Value $Log
Set-Content -LiteralPath 'D:\RedMMOTitanWindowsData\BuildLogs\LatestPackage50kmAttemptArchive.txt' -Value $Archive

$RequiredRuntimePackageList = @(
    '/Game/Jet_Packs_Sci-Fi/Blueprints/Sci-Fi_Jetpack_Master_BP',
    '/Game/Jet_Packs_Sci-Fi/Particles/Large_Jet_Exhaust_PS',
    '/Game/Jet_Packs_Sci-Fi/Particles/Jet_Exhaust_PS',
    '/Game/Jet_Packs_Sci-Fi/Audio/Jet_Engine_Light_Loop_Cue',
    '/Game/BeamsPack/VFX/Beams/NS_BeamOnly_02',
    '/Game/RedMMO/Environment/M_RedStarSolid',
    '/Game/RedMMO/Environment/M_RedStarSpriteMasked',
    '/Game/ProjectilesVol1/Materials/M_Additive',
    '/Game/RedMMO/Environment/MI_RedClearWater',
    '/Game/RedMMO/Environment/M_RedBabyBlueSurfaceSky',
    '/Game/Cloudz_Hi5/Materials/Instances/MI_Cloudz_Hi5_002',
    '/Game/Cloudz_Hi5/Materials/Instances/MI_Cloudz_Hi5_003',
    '/Game/Cloudz_Hi5/Materials/Instances/MI_Cloudz_Hi5_004',
    '/Game/Cloudz_Hi5/Materials/Instances/MI_Cloudz_Hi5_005',
    '/Game/SoStylized/Environment/Sky/BP_StylizedSky_Lite',
    '/Game/SoStylized/Environment/Sky/Meshes/SM_StylizedSkyDome',
    '/Game/RedMMO/Materials/MI_PlanetBiome_RED',
    '/Game/RedMMO/UI/Generated/weapon_slot_epic',
    '/Game/RedMMO/UI/Generated/weapon_slot_legendary',
    '/Game/RedMMO/Materials/M_ShipPlume_Cyan',
    '/Game/SoStylized/Environment/Water/Materials/MI_WaterWaves',
    '/Game/SpaceShip/Audio/SC_RocketEngine',
    '/Game/SpaceShip/Audio/SC_RocketEngineHigh',
    '/Game/Vefects/Sand_VFX/Audio/SFX_Attenuation'
)
$RequiredRuntimePackages = '-PACKAGE=' + ($RequiredRuntimePackageList -join '+')
$CookerOptions = "$RequiredRuntimePackages -NoGameAlwaysCook -NoDefaultMaps"
$RequiredMapList = @('/Game/RedMMO/Maps/RedPlanetGen')
if ($Include50KmCheckpoints) {
    $RequiredMapList += @(
        '/Game/RedMMO/Maps/RedPlanetGen_50km_Test',
        '/Game/RedMMO/Maps/RedPlanetGen_50km_FusedPrototype'
    )
}
$RequiredMaps = $RequiredMapList -join '+'
$Arguments = @(
    'BuildCookRun',
    "-project=$Project",
    '-noP4',
    '-utf8output',
    '-platform=Win64',
    '-clientconfig=Development',
    '-serverconfig=Development',
    '-UbtArgs=-NoUBA -MaxParallelActions=1',
    '-build',
    '-cook',
    '-stage',
    '-pak',
    '-iostore',
    '-zenstore',
    '-compressed',
    '-prereqs',
    '-archive',
    "-archivedirectory=$Archive",
    "-map=$RequiredMaps",
    "-additionalcookeroptions=$CookerOptions"
)

if (-not $FreshCook) {
    $Arguments += '-iterate'
}

try {
    $quotedRunUAT = '"' + $RunUAT.Replace('"', '\"') + '"'
    $quotedArguments = @($Arguments | ForEach-Object {
        '"' + ([string]$_).Replace('"', '\"') + '"'
    })
    $uatCommand = $quotedRunUAT + ' ' + ($quotedArguments -join ' ')
    $cmdArguments = '/d /s /c "' + $uatCommand + '"'

    Set-Content -LiteralPath $GuardLog -Value @(
        "started_utc=$BuildTimestampUtc",
        "minimum_free_commit_gb=$MinimumFreeCommitGB",
        "minimum_free_physical_gb=$MinimumFreePhysicalGB",
        "abort_free_commit_gb=$AbortFreeCommitGB",
        "abort_free_physical_gb=$AbortFreePhysicalGB",
        "preflight_samples=$PreflightSamples",
        "preflight_sample_seconds=$PreflightSampleSeconds",
        "preflight_min_free_commit_gb=$($preflightMemory.FreeCommitGB)",
        "preflight_min_free_physical_gb=$($preflightMemory.FreePhysicalGB)",
        'zen_store=true',
        "fresh_cook=$($FreshCook.IsPresent.ToString().ToLowerInvariant())",
        "include_50km_checkpoints=$($Include50KmCheckpoints.IsPresent.ToString().ToLowerInvariant())"
    )

    $uatProcess = Start-Process -FilePath $env:ComSpec -ArgumentList $cmdArguments -WorkingDirectory $ProjectRoot `
        -PassThru -NoNewWindow -RedirectStandardOutput $Log -RedirectStandardError $ErrorLog

    $abortReason = $null
    $sampleCount = 0
    $packagePhase = 'automation_startup'
    while (-not $uatProcess.HasExited) {
        Start-Sleep -Seconds $PollSeconds
        $uatProcess.Refresh()
        $memory = Get-RedMemorySnapshot
        $packagePhase = Get-RedPackagePhase -LogPath $Log -PreviousPhase $packagePhase
        $sampleCount++
        $sample = "{0} pid={1} phase={2} freeCommitGB={3:N2} freePhysicalGB={4:N2}" -f `
            (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ'),
            $uatProcess.Id,
            $packagePhase,
            $memory.FreeCommitGB,
            $memory.FreePhysicalGB
        Add-Content -LiteralPath $GuardLog -Value $sample
        if (($sampleCount -eq 1) -or (($sampleCount * $PollSeconds) % 30 -eq 0)) {
            Write-Host $sample
        }

        if ($memory.FreeCommitGB -lt $AbortFreeCommitGB) {
            $abortReason = "free commit fell below the $AbortFreeCommitGB GB abort threshold"
        }
        if (-not $abortReason -and $memory.FreePhysicalGB -lt $AbortFreePhysicalGB) {
            $abortReason = "free physical memory fell below the $AbortFreePhysicalGB GB abort threshold"
        }

        if (-not $abortReason) {
            $tail = @()
            foreach ($candidateLog in @($Log, $ErrorLog)) {
                if (Test-Path -LiteralPath $candidateLog) {
                    $tail += @(Get-Content -LiteralPath $candidateLog -Tail 200 -ErrorAction SilentlyContinue)
                }
            }
            $fatalLine = $tail | Select-String -Pattern 'NNERuntimeORT.*bad allocation|VirtualAlloc.*failed|paging file is too small|out of memory|out of video memory|GPU device removed' | Select-Object -First 1
            if ($fatalLine) {
                $abortReason = "unsafe package signature: $($fatalLine.Line.Trim())"
            }
        }

        if ($abortReason) {
            Add-Content -LiteralPath $GuardLog -Value "aborted_phase=$packagePhase"
            Add-Content -LiteralPath $GuardLog -Value "aborted_reason=$abortReason"
            Write-Warning "Aborting the exact package process tree: $abortReason"
            & "$env:SystemRoot\System32\taskkill.exe" /PID $uatProcess.Id /T /F | Out-Host
            break
        }
    }

    $uatProcess.WaitForExit()
    $packagePhase = Get-RedPackagePhase -LogPath $Log -PreviousPhase $packagePhase
    Add-Content -LiteralPath $GuardLog -Value "final_phase=$packagePhase"
    if ($abortReason) {
        throw "BuildCookRun aborted safely: $abortReason"
    }
    $uatProcess.Refresh()
    $ExitCode = $uatProcess.ExitCode
    if ($ExitCode -ne 0) {
        throw "BuildCookRun failed with exit code $ExitCode."
    }

$WindowsRoot = Join-Path $Archive 'Windows'
$Executable = Join-Path $WindowsRoot 'Titan.exe'
$MainData = Join-Path $WindowsRoot 'Titan\Content\Paks\Titan-Windows.ucas'
$SteamAppId = Join-Path $ProjectRoot 'steam_appid.txt'
if (Test-Path -LiteralPath $SteamAppId) {
    Copy-Item -LiteralPath $SteamAppId -Destination (Join-Path $WindowsRoot 'steam_appid.txt') -Force
    Copy-Item -LiteralPath $SteamAppId -Destination (Join-Path $WindowsRoot 'Titan\Binaries\Win64\steam_appid.txt') -Force
}

if ($Include50KmCheckpoints) {
    Copy-Item -LiteralPath (Join-Path $ProjectRoot 'Build\Templates\Launch_50km_Test.bat') -Destination (Join-Path $WindowsRoot 'Launch_50km_Test.bat') -Force
    Copy-Item -LiteralPath (Join-Path $ProjectRoot 'Build\Templates\Launch_50km_FusedPrototype.bat') -Destination (Join-Path $WindowsRoot 'Launch_50km_FusedPrototype.bat') -Force
}

$UnrealPak = 'D:\UE_5.8\Engine\Binaries\Win64\UnrealPak.exe'
$Container = Join-Path $WindowsRoot 'Titan\Content\Paks\Titan-Windows.utoc'
$ContainerList = "$Log.iostore.list.txt"
foreach ($RequiredOutput in @($Executable, $Container, $MainData)) {
    if (-not (Test-Path -LiteralPath $RequiredOutput)) {
        throw "Packaged output is missing: $RequiredOutput"
    }
}

& $UnrealPak $Container -List 2>&1 | Set-Content -LiteralPath $ContainerList
if ($LASTEXITCODE -ne 0) {
    throw "UnrealPak failed to list the packaged IoStore container (exit $LASTEXITCODE)."
}

$RequiredContainerEntries = @(
    '../../../Titan/Content/RedMMO/Maps/RedPlanetGen.umap',
    '../../../Titan/Content/RedMMO/Environment/M_RedStarSolid.uasset',
    '../../../Titan/Content/RedMMO/Environment/M_RedStarSpriteMasked.uasset',
    '../../../Titan/Content/RedMMO/Environment/MI_RedClearWater.uasset',
    '../../../Titan/Content/RedMMO/Environment/M_RedBabyBlueSurfaceSky.uasset',
    '../../../Titan/Content/Cloudz_Hi5/Materials/Instances/MI_Cloudz_Hi5_002.uasset',
    '../../../Titan/Content/Cloudz_Hi5/Materials/Instances/MI_Cloudz_Hi5_003.uasset',
    '../../../Titan/Content/Cloudz_Hi5/Materials/Instances/MI_Cloudz_Hi5_004.uasset',
    '../../../Titan/Content/Cloudz_Hi5/Materials/Instances/MI_Cloudz_Hi5_005.uasset',
    '../../../Titan/Content/SoStylized/Environment/Sky/BP_StylizedSky_Lite.uasset',
    '../../../Titan/Content/SoStylized/Environment/Sky/Meshes/SM_StylizedSkyDome.uasset',
    '../../../Titan/Content/ProjectilesVol1/Textures/T_Point5.uasset',
    '../../../Titan/Content/BeamsPack/VFX/Beams/NS_BeamOnly_02.uasset',
    '../../../Titan/Content/RedMMO/Materials/MI_PlanetBiome_RED.uasset',
    '../../../Titan/Content/RedMMO/UI/Generated/weapon_slot_epic.uasset',
    '../../../Titan/Content/RedMMO/UI/Generated/weapon_slot_legendary.uasset',
    '../../../Titan/Content/RedMMO/Materials/M_ShipPlume_Cyan.uasset',
    '../../../Titan/Content/SoStylized/Environment/Water/Materials/MI_WaterWaves.uasset',
    '../../../Titan/Content/SpaceShip/Audio/SC_RocketEngine.uasset',
    '../../../Titan/Content/SpaceShip/Audio/SC_RocketEngineHigh.uasset',
    '../../../Titan/Content/Vefects/Sand_VFX/Audio/SFX_Attenuation.uasset',
    '../../../Titan/Content/UI/RedHUD/Textures/ExactLayoutSprites/T_REDHUD_FullComposite_Exact.uasset'
)
if ($Include50KmCheckpoints) {
    $RequiredContainerEntries += @(
        '../../../Titan/Content/RedMMO/Maps/RedPlanetGen_50km_Test.umap',
        '../../../Titan/Content/RedMMO/Maps/RedPlanetGen_50km_FusedPrototype.umap',
        '../../../Titan/Content/RedMMO/Environment/DA_RED_Planet50Km_FusedHeightfield.uasset'
    )
}
foreach ($RequiredEntry in $RequiredContainerEntries) {
    if (-not (Select-String -LiteralPath $ContainerList -SimpleMatch $RequiredEntry -Quiet)) {
        throw "Required packaged entry is missing: $RequiredEntry"
    }
}

if ($Include50KmCheckpoints) {
    $PostPackageFusedPrototypeHash = Get-RedFusedPrototypeSourceHash
    if ($PostPackageFusedPrototypeHash -ne $FusedPrototypeSourceHash) {
        throw "Fused prototype source changed during packaging: before=$FusedPrototypeSourceHash after=$PostPackageFusedPrototypeHash"
    }
}

$ReadyMarkerLines = @(
    "archive=$Archive",
    "build_log=$Log",
    "uat_exit_file=$ExitFile",
    'configuration=Development',
    "build_timestamp_utc=$BuildTimestampUtc",
    "source_revision=$SourceRevision",
    "source_dirty=$SourceDirty",
    "fresh_cook=$($FreshCook.IsPresent.ToString().ToLowerInvariant())",
    "include_50km_checkpoints=$($Include50KmCheckpoints.IsPresent.ToString().ToLowerInvariant())",
    'zen_store=true',
    "memory_guard_log=$GuardLog",
    "container_list=$ContainerList",
    'default_launch=Windows\Titan.exe',
    'verified_map=/Game/RedMMO/Maps/RedPlanetGen',
    'verified_surface_sky=/Game/RedMMO/Environment/M_RedBabyBlueSurfaceSky',
    'verified_star_material=/Game/RedMMO/Environment/M_RedStarSolid',
    'verified_hi5_cloud_instances=002,003,004,005',
    'verified_grapple=/Game/BeamsPack/VFX/Beams/NS_BeamOnly_02'
)
if ($Include50KmCheckpoints) {
    $ReadyMarkerLines += @(
        '50km_test_launch=Windows\Launch_50km_Test.bat',
        '50km_fused_launch=Windows\Launch_50km_FusedPrototype.bat',
        'verified_50km_test_map=/Game/RedMMO/Maps/RedPlanetGen_50km_Test',
        'verified_fused_map=/Game/RedMMO/Maps/RedPlanetGen_50km_FusedPrototype',
        'verified_fused_asset=/Game/RedMMO/Environment/DA_RED_Planet50Km_FusedHeightfield',
        "fused_prototype_source_sha256=$FusedPrototypeSourceHash"
    )
}

Assert-RedProtectedCheckpoints
    if ((Test-Path -LiteralPath $ReadyMarkerPath) -or (Test-Path -LiteralPath $ReadyMarkerTemp)) {
        throw "Refusing to overwrite existing package publication marker: $ReadyMarkerPath"
    }
    $ReadyMarkerTempCreatedByThisRun = $true
    Set-Content -LiteralPath $ReadyMarkerTemp -Value $ReadyMarkerLines
    Set-Content -LiteralPath $ExitFile -Value 0
    Move-Item -LiteralPath $ReadyMarkerTemp -Destination $ReadyMarkerPath
    $ReadyMarkerTempCreatedByThisRun = $false
    $ReadyMarkerPublishedByThisRun = $true
    Set-Content -LiteralPath 'D:\RedMMOTitanWindowsData\BuildLogs\LatestPackage50kmArchive.txt' -Value $Archive
    Write-Output "REDMMO_PACKAGE_READY archive=$Archive"
}
catch {
    if ($ReadyMarkerTempCreatedByThisRun -and (Test-Path -LiteralPath $ReadyMarkerTemp)) {
        Remove-Item -LiteralPath $ReadyMarkerTemp -Force -ErrorAction SilentlyContinue
    }
    if ($ReadyMarkerPublishedByThisRun -and (Test-Path -LiteralPath $ReadyMarkerPath)) {
        Remove-Item -LiteralPath $ReadyMarkerPath -Force -ErrorAction SilentlyContinue
    }
    Set-Content -LiteralPath $ExitFile -Value 1
    Write-Error $_
    exit 1
}
