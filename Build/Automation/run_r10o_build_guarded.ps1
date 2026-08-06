$ErrorActionPreference = 'Stop'

$projectRoot = 'D:\RedMMOTitanWindowsData\Projects\RedMMO'
$projectFile = Join-Path $projectRoot 'RedMMO.uproject'
$editor = 'D:\UE_5.8\Engine\Binaries\Win64\UnrealEditor.exe'
$driver = 'D:\RedMMOTitan\Build\Automation\build_r10o_cap_safe_grass_density.py'
$diag = 'D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_PPG_HomePresentation_R10O_20260802_183909'
$result = Join-Path $diag 'build_r10o_cap_safe_grass_density_result.json'
$log = Join-Path $diag 'build_r10o_cap_safe_grass_density.log'
$guard = Join-Path $diag 'run_r10o_build_guard_result.json'
$homeMapFile = Join-Path $projectRoot 'Content\RedMMO\Maps\RedMMO_PPG_HomeWorld.umap'
$targetRoot = Join-Path $projectRoot 'Content\RedMMO\World\PPG\HomeWorld\StylizedBinding\R10O'
$profile = Join-Path $projectRoot 'Config\RedMMO\PPGStylizedFoliageProfiles\HomeWorld_Presentation_R10O.json'
$rollback = 'D:\RedMMOTitanWindowsData\Rollback\RedMMO_PPG_HomePresentation_R10O_20260802_183909_A01'
$rollbackHome = Join-Path $rollback 'RedMMO_PPG_HomeWorld.pre_r10o.umap'
$manifest = Join-Path $rollback 'pre_r10o_manifest.json'

$expectedHome = 'A0F4FECBAAB38CCC40D5B667706D72E8402C2312EB523AAB28CD4C1F1A26C665'
$expectedDriver = 'C4BD092EB1A2C82D1D41DE0F8ED86F57B504A6E9A47C8AD0011035A3318035AF'
$expectedManifest = '2203BF4B19A49A49ED67A00A1BFC735296AF313825BBC34861EFCBA3ADA556A3'
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

function Assert-ProtectedHashes {
    foreach ($entry in $protected.GetEnumerator()) {
        if (-not (Test-Path -LiteralPath $entry.Key -PathType Leaf)) {
            throw "Protected file missing: $($entry.Key)"
        }
        if ((Get-FileHash -LiteralPath $entry.Key -Algorithm SHA256).Hash -ne $entry.Value) {
            throw "Protected file drift: $($entry.Key)"
        }
    }
}

function Restore-R10NState {
    if (-not (Test-Path -LiteralPath $rollbackHome -PathType Leaf)) {
        throw 'Rollback home map is missing.'
    }
    Copy-Item -LiteralPath $rollbackHome -Destination $homeMapFile -Force
    if ((Get-FileHash -LiteralPath $homeMapFile -Algorithm SHA256).Hash -ne $expectedHome) {
        throw 'Rollback home hash verification failed.'
    }

    $resolvedBindingRoot = [IO.Path]::GetFullPath((Join-Path $projectRoot 'Content\RedMMO\World\PPG\HomeWorld\StylizedBinding'))
    $resolvedTarget = [IO.Path]::GetFullPath($targetRoot)
    if (-not $resolvedTarget.StartsWith($resolvedBindingRoot + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Refusing unsafe R10O rollback target.'
    }
    if (Test-Path -LiteralPath $targetRoot) {
        Remove-Item -LiteralPath $targetRoot -Recurse -Force
    }
    if (Test-Path -LiteralPath $profile) {
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
    schema = 'redmmo.ppg_home_presentation.r10o.build_guard.v1'
    status = 'RUNNING'
    started_utc = [DateTime]::UtcNow.ToString('o')
}
$proc = $null
$mutationMayHaveStarted = $false

try {
    foreach ($path in @($projectFile, $editor, $driver, $homeMapFile, $manifest, $rollbackHome)) {
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
            throw "Required path missing: $path"
        }
    }
    foreach ($path in @($result, $log, $guard, $targetRoot, $profile)) {
        if (Test-Path -LiteralPath $path) {
            throw "No-clobber output exists: $path"
        }
    }
    if ((Get-FileHash -LiteralPath $driver -Algorithm SHA256).Hash -ne $expectedDriver) {
        throw 'R10O driver hash drift.'
    }
    if ((Get-FileHash -LiteralPath $manifest -Algorithm SHA256).Hash -ne $expectedManifest) {
        throw 'R10O rollback manifest hash drift.'
    }
    if ((Get-FileHash -LiteralPath $homeMapFile -Algorithm SHA256).Hash -ne $expectedHome) {
        throw 'R10N home hash drift before R10O.'
    }
    if ((Get-FileHash -LiteralPath $rollbackHome -Algorithm SHA256).Hash -ne $expectedHome) {
        throw 'R10O rollback home hash drift.'
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
        '-DisablePlugins=ModelContextProtocol,Nwiro,UnrealAIIntegrationPlatform',
        "-ExecCmds=`"py $($driver.Replace('\','/'))`"",
        "-abslog=$($log.Replace('\','/'))"
    )
    $mutationMayHaveStarted = $true
    $proc = Start-Process -FilePath $editor -ArgumentList $args -PassThru -WindowStyle Hidden
    $state.editor_pid = $proc.Id
    $state.free_ram_gib_at_launch = $free
    $minimumFree = $free
    $deadline = [DateTime]::UtcNow.AddMinutes(15)
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
            $abortReason = 'R10O build timeout.'
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
        throw 'R10O build result is missing.'
    }
    $payload = Get-Content -LiteralPath $result -Raw | ConvertFrom-Json
    if ($payload.status -ne 'PASS_STATIC_SERIALIZATION_PENDING_FRESH_RELOAD_MAPCHECK_AND_ACTUAL_PLAYERSTART_PIE') {
        throw "R10O build failed: $($payload.status) $($payload.error)"
    }
    $state.home_map_sha256_after = $payload.home_map_sha256_after
    $state.created_assets = @($payload.created_assets)
    $state.result_sha256 = (Get-FileHash -LiteralPath $result -Algorithm SHA256).Hash
    Assert-ProtectedHashes
    Start-Sleep -Seconds 2
    if ((Get-UnrealProcesses).Count -ne 0) {
        throw 'An Unreal/build process remains after R10O build.'
    }
    $state.status = 'PASS_STATIC_SERIALIZATION_PENDING_FRESH_RELOAD_MAPCHECK_AND_ACTUAL_PLAYERSTART_PIE'
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
            Restore-R10NState
            Assert-ProtectedHashes
            $state.rollback = 'RESTORED_R10N'
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
    $bytes = [Text.UTF8Encoding]::new($false).GetBytes(($state | ConvertTo-Json -Depth 10))
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
