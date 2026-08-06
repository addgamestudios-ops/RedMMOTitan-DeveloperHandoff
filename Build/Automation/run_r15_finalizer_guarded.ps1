$ErrorActionPreference = 'Stop'

$projectRoot = 'D:\RedMMOTitanWindowsData\Projects\RedMMO'
$projectFile = Join-Path $projectRoot 'RedMMO.uproject'
$editor = 'D:\UE_5.8\Engine\Binaries\Win64\UnrealEditor.exe'
$driver = 'D:\RedMMOTitan\Build\Automation\finalize_r15_continent_biome.py'
$diag = 'D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_PPG_ContinentBiome_R15_20260802_211912'
$result = Join-Path $diag 'finalize_r15_continent_biome_r05_result.json'
$log = Join-Path $diag 'finalize_r15_continent_biome_r05.log'
$guard = Join-Path $diag 'run_r15_finalizer_guard_r05_result.json'
$stageResult = Join-Path $diag 'stage_r15_continent_biome_assets_via_epic_mcp_result.json'
$homeMapFile = Join-Path $projectRoot 'Content\RedMMO\Maps\RedMMO_PPG_HomeWorld.umap'
$targetRoot = Join-Path $projectRoot 'Content\RedMMO\World\PPG\HomeWorld\ContinentBiome\R15'
$profile = Join-Path $projectRoot 'Config\RedMMO\PPGContinentBiomeProfiles\HomeWorld_ContinentBiome_R15.json'
$rollbackRoot = 'D:\RedMMOTitanWindowsData\Rollback\RedMMO_PPG_ContinentBiome_R15_20260802_211912_A01'
$rollbackHome = Join-Path $rollbackRoot 'RedMMO_PPG_HomeWorld.pre_r15.umap'
$manifest = Join-Path $rollbackRoot 'pre_r15_manifest.json'

$expectedHome = 'C9BE88085575E75E1790CB9306D564EB100F5ED2E75E012C1FD09EA110FDDFE0'
$expectedProject = '344BDA6BF5A99CC9C0902CB8C069A0EE2E67C3F15B80B2CDEA1D4B0B007AD105'
$expectedDriver = '137EA9B070F41364B0117250B09D0C13546FE96B02CA911AEA5191B065E9D686'
$expectedStageResult = '2C225D177A19F82F5DB7B7B04243F3C7CD49CD50AFC6732E8D457E8D3FD79804'
$expectedManifest = '6CB41CE2DA4E78CAE1A83028CDA98E6DA6E09B461271F06FD3B2CA3A6CEADE20'

$expectedStageFiles = [ordered]@{
    (Join-Path $targetRoot 'DA_PPG_HomeWorld_ContinentBiome_R15.uasset') = 'B54D5551DF34DB3F07F6A87F1A1DFE3EEF6321E33CA121FA7BC09736B880C850'
    (Join-Path $targetRoot 'Materials\M_PPG_Generation_Continents_R15.uasset') = 'ABA8639EA06F30CCAFB35244E96A375F9433D0FB60014B2766195CD4C8B25048'
    (Join-Path $targetRoot 'Materials\M_PPG_BiomeMask_Continents_R15.uasset') = '262688D1F71CC00025124923A0368C9906AB3A766C7E8757389BF835FD6DE1B9'
    (Join-Path $targetRoot 'Materials\M_PPG_Home_BiomeSurface_R15.uasset') = 'D2B6DBE3BF6ABBD4DE0C9BA277C682BED2813DDBBB0A48D2308340D25524D653'
    (Join-Path $targetRoot 'Materials\MI_PPG_Home_BiomeSurface_R15.uasset') = '656D2CA24C5736D6EC27A5B8A8F8240AD6401F64A79931306D944A164B679A8A'
}

$protected = [ordered]@{
    'D:\RedMMOTitan\Content\RedMMO\Maps\RedPlanetGen_50km_Test.umap' = 'DA5987012EEB8F550254F5FCF0F47F42B8F5E03428CF4881C83D8687537F6E7D'
    'D:\RedMMOTitan\Content\RedMMO\Maps\RedPlanetGen_50km_FusedPrototype.umap' = '4C84D7752C87854C70987ED9988C64C124C577FBE1DE3DEF3CC826F81B0B6284'
    'D:\RedMMOTitan\Content\RedMMO\Maps\Tests\RedPlanetGen_50km_FusedPrototype_Night_T03.umap' = '211429783F757F3CD8DE4A37B1E37B4A117125BF26EBFCBACF97CCFA9EFBE8D7'
    'D:\RedMMOTitanWindowsData\Rollback\BeforeCoastDatum_20260714\RedPlanetGen_50km_FusedPrototype.umap' = 'A9C42C0D1B0429DD1018F00F0D2AB8A18F66C07291611964EFF5F9710F3B0C6A'
}

function Get-FreeRamGiB {
    $os = Get-CimInstance Win32_OperatingSystem
    return [math]::Round(($os.FreePhysicalMemory * 1KB) / 1GB, 3)
}

function Get-UnrealProcesses {
    return @(Get-CimInstance Win32_Process | Where-Object {
        $_.Name -match '^(UnrealEditor|UnrealEditor-Cmd|ShaderCompileWorker|UnrealBuildTool|UnrealHeaderTool|AutomationTool|CrashReportClient)'
    })
}

function Get-ProcessTree([int]$RootPid) {
    $all = @(Get-CimInstance Win32_Process)
    $known = [Collections.Generic.HashSet[int]]::new()
    [void]$known.Add($RootPid)
    $changed = $true
    while ($changed) {
        $changed = $false
        foreach ($item in $all) {
            if ($known.Contains([int]$item.ParentProcessId) -and -not $known.Contains([int]$item.ProcessId)) {
                [void]$known.Add([int]$item.ProcessId)
                $changed = $true
            }
        }
    }
    return @($known)
}

function Stop-ExactProcessTree([int]$RootPid) {
    $ids = @(Get-ProcessTree $RootPid | Sort-Object -Descending)
    foreach ($id in $ids) {
        if (Get-Process -Id $id -ErrorAction SilentlyContinue) {
            Stop-Process -Id $id -Force -ErrorAction SilentlyContinue
        }
    }
    return $ids
}

function Assert-Hash([string]$Path, [string]$Expected, [string]$Label) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "$Label missing: $Path"
    }
    $actual = (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash
    if ($actual -ne $Expected) {
        throw "$Label hash drift: $Path actual=$actual expected=$Expected"
    }
}

function Assert-ProtectedHashes {
    foreach ($entry in $protected.GetEnumerator()) {
        Assert-Hash $entry.Key $entry.Value 'Protected file'
    }
}

function Restore-HomeOnly {
    Assert-Hash $rollbackHome $expectedHome 'Rollback home map'
    Copy-Item -LiteralPath $rollbackHome -Destination $homeMapFile -Force
    Assert-Hash $homeMapFile $expectedHome 'Restored home map'
    if (Test-Path -LiteralPath $profile -PathType Leaf) {
        Remove-Item -LiteralPath $profile -Force
    }
}

$mutex = New-Object Threading.Mutex($false, 'RedMMO_UnrealMutation_Exclusive')
$held = $mutex.WaitOne(0)
if (-not $held) {
    $mutex.Dispose()
    throw 'Another guarded Unreal operation is active.'
}

$state = [ordered]@{
    schema = 'redmmo.ppg_continent_biome.r15.finalizer_guard.v1'
    status = 'RUNNING'
    started_utc = [DateTime]::UtcNow.ToString('o')
}
$proc = $null
$mutationMayHaveStarted = $false

try {
    foreach ($path in @($projectFile, $editor, $driver, $homeMapFile, $manifest, $rollbackHome, $stageResult)) {
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
            throw "Required path missing: $path"
        }
    }
    foreach ($path in @($result, $log, $guard, $profile)) {
        if (Test-Path -LiteralPath $path) {
            throw "No-clobber output exists: $path"
        }
    }
    Assert-Hash $projectFile $expectedProject 'Project descriptor'
    Assert-Hash $driver $expectedDriver 'R15 finalizer driver'
    Assert-Hash $stageResult $expectedStageResult 'Direct MCP stage result'
    Assert-Hash $manifest $expectedManifest 'R15 checkpoint manifest'
    Assert-Hash $homeMapFile $expectedHome 'R15 source home map'
    Assert-Hash $rollbackHome $expectedHome 'R15 rollback home map'
    foreach ($entry in $expectedStageFiles.GetEnumerator()) {
        Assert-Hash $entry.Key $entry.Value 'R15 staged asset'
    }
    Assert-ProtectedHashes
    if ((Get-UnrealProcesses).Count -ne 0) {
        throw 'Another Unreal/build process is active.'
    }
    $listeners = @(Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | Where-Object {
        $_.LocalPort -in 5353, 8000, 8765
    })
    if ($listeners.Count -ne 0) {
        throw 'An AI/provider listener is active.'
    }
    $free = Get-FreeRamGiB
    if ($free -lt 12) {
        throw "RAM gate failed: $free GiB"
    }

    $args = @(
        $projectFile,
        '/Game/RedMMO/Maps/RedMMO_PPG_HomeWorld',
        '-NoSplash',
        '-NoLiveCoding',
        '-NoSound',
        '-NoSourceControl',
        '-unattended',
        '-d3d12',
        '-RenderOffscreen',
        '-DisablePlugins=ModelContextProtocol,ToolsetRegistry,EditorToolset,Nwiro,NwiroIntegrationKit,UnrealAIIntegrationPlatform,VibeUE,MCPClientToolset',
        "-ExecCmds=`"py $($driver.Replace('\','/'))`"",
        "-abslog=$($log.Replace('\','/'))"
    )
    $mutationMayHaveStarted = $true
    $proc = Start-Process -FilePath $editor -ArgumentList $args -PassThru -WindowStyle Hidden
    $state.editor_pid = $proc.Id
    $state.free_ram_gib_at_launch = $free
    $minimumFree = $free
    $deadline = [DateTime]::UtcNow.AddMinutes(20)
    $abortReason = $null
    while (-not $proc.HasExited) {
        Start-Sleep -Milliseconds 750
        $proc.Refresh()
        $current = Get-FreeRamGiB
        if ($current -lt $minimumFree) {
            $minimumFree = $current
        }
        if ($current -lt 8) {
            $abortReason = "RAM abort floor crossed: $current GiB"
            break
        }
        if ([DateTime]::UtcNow -gt $deadline) {
            $abortReason = 'R15 finalizer timeout.'
            break
        }
    }
    $state.minimum_free_ram_gib = $minimumFree
    if ($abortReason) {
        $state.stopped_exact_process_ids = @(Stop-ExactProcessTree $proc.Id)
        $proc.WaitForExit()
        throw $abortReason
    }
    $state.editor_exit_code = $proc.ExitCode
    if ($proc.ExitCode -ne 0) {
        throw "Editor exit code $($proc.ExitCode)"
    }
    if (-not (Test-Path -LiteralPath $result -PathType Leaf)) {
        throw 'R15 finalizer result is missing.'
    }
    $payload = Get-Content -LiteralPath $result -Raw | ConvertFrom-Json
    if ($payload.status -ne 'PASS_SERIALIZED_PENDING_FRESH_RELOAD_MAPCHECK_AND_REAL_GPU') {
        throw "R15 finalizer failed: $($payload.status) $($payload.error)"
    }
    $state.home_map_sha256_after = $payload.home_map_sha256_after
    $state.project_owned_hashes = $payload.project_owned_hashes
    $state.result_sha256 = (Get-FileHash -LiteralPath $result -Algorithm SHA256).Hash
    Assert-ProtectedHashes
    $state.status = 'PASS_SERIALIZED_PENDING_FRESH_RELOAD_MAPCHECK_AND_REAL_GPU'
}
catch {
    $state.status = 'FAIL'
    $state.error = $_.Exception.Message
    if ($null -ne $proc -and -not $proc.HasExited) {
        $state.stopped_exact_process_ids = @(Stop-ExactProcessTree $proc.Id)
        $proc.WaitForExit()
    }
    if ($mutationMayHaveStarted) {
        try {
            Restore-HomeOnly
            Assert-ProtectedHashes
            $state.rollback = 'HOME_RESTORED_R13_R15_ASSETS_RETAINED_FOR_DIAGNOSIS'
        }
        catch {
            $state.rollback = 'FAILED'
            $state.rollback_error = $_.Exception.Message
        }
    }
    throw
}
finally {
    $state.completed_utc = [DateTime]::UtcNow.ToString('o')
    $bytes = [Text.UTF8Encoding]::new($false).GetBytes(($state | ConvertTo-Json -Depth 12))
    $stream = [IO.File]::Open($guard, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
    try {
        $stream.Write($bytes, 0, $bytes.Length)
        $stream.Flush($true)
    }
    finally {
        $stream.Dispose()
    }
    if ($held) {
        $mutex.ReleaseMutex()
    }
    $mutex.Dispose()
}
