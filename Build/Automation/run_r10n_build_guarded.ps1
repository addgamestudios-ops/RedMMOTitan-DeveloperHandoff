$ErrorActionPreference = 'Stop'

$projectRoot = 'D:\RedMMOTitanWindowsData\Projects\RedMMO'
$projectFile = Join-Path $projectRoot 'RedMMO.uproject'
$editor = 'D:\UE_5.8\Engine\Binaries\Win64\UnrealEditor.exe'
$driver = 'D:\RedMMOTitan\Build\Automation\build_r10n_spawn_grass_ground_smoothing.py'
$diag = 'D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_PPG_HomePresentation_R10N_20260802_181848'
$result = Join-Path $diag 'build_r10n_spawn_grass_ground_smoothing_result.json'
$log = Join-Path $diag 'build_r10n_spawn_grass_ground_smoothing.log'
$guard = Join-Path $diag 'run_r10n_build_guard_result.json'
$homeMapFile = Join-Path $projectRoot 'Content\RedMMO\Maps\RedMMO_PPG_HomeWorld.umap'
$targetRoot = Join-Path $projectRoot 'Content\RedMMO\World\PPG\HomeWorld\StylizedBinding\R10N'
$profile = Join-Path $projectRoot 'Config\RedMMO\PPGStylizedFoliageProfiles\HomeWorld_Presentation_R10N.json'
$rollback = 'D:\RedMMOTitanWindowsData\Rollback\RedMMO_PPG_HomePresentation_R10N_20260802_181848_A01'
$rollbackHome = Join-Path $rollback 'RedMMO_PPG_HomeWorld.pre_r10n.umap'
$manifest = Join-Path $rollback 'pre_r10n_manifest.json'

$expectedHome = 'B19019D31369D0325896BA871EB083036DE64516EF51314CF89A74B30366DB10'
$expectedDriver = 'AC89B598952C76E18D8A0B2A9B2DEA84FB3F34A89D181EBC8F5817F6F057CB73'
$expectedManifest = 'D789FF35226937FDEEC13FE5459ADFB4B63864242EA8EA00865BB6E0E17D6389'
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

function Assert-R10MSourceHashes {
    $payload = Get-Content -LiteralPath $manifest -Raw | ConvertFrom-Json
    foreach ($source in $payload.source_files) {
        if (-not (Test-Path -LiteralPath $source.path -PathType Leaf)) {
            throw "R10M source missing: $($source.path)"
        }
        if ((Get-FileHash -LiteralPath $source.path -Algorithm SHA256).Hash -ne $source.sha256) {
            throw "R10M source drift: $($source.path)"
        }
    }
}

function Restore-R10M {
    if ((Get-UnrealProcesses).Count -ne 0) {
        throw 'Cannot restore while Unreal is active.'
    }
    if ((Get-FileHash -LiteralPath $rollbackHome -Algorithm SHA256).Hash -ne $expectedHome) {
        throw 'Rollback home hash drift.'
    }
    Copy-Item -LiteralPath $rollbackHome -Destination $homeMapFile -Force
    if ((Get-FileHash -LiteralPath $homeMapFile -Algorithm SHA256).Hash -ne $expectedHome) {
        throw 'Home rollback failed.'
    }
    if (Test-Path -LiteralPath $targetRoot) {
        $content = [IO.Path]::GetFullPath((Join-Path $projectRoot 'Content')).TrimEnd('\')
        $target = [IO.Path]::GetFullPath($targetRoot)
        if (-not $target.StartsWith($content + '\', [StringComparison]::OrdinalIgnoreCase)) {
            throw 'R10N cleanup escaped Content.'
        }
        if (-not $target.EndsWith('RedMMO\World\PPG\HomeWorld\StylizedBinding\R10N', [StringComparison]::OrdinalIgnoreCase)) {
            throw 'R10N cleanup target drift.'
        }
        Remove-Item -LiteralPath $target -Recurse -Force
    }
    if (Test-Path -LiteralPath $profile -PathType Leaf) {
        Remove-Item -LiteralPath $profile -Force
    }
}

$mutex = New-Object Threading.Mutex($false, 'RedMMO_UnrealMutation_Exclusive')
$held = $mutex.WaitOne(0)
if (-not $held) {
    $mutex.Dispose()
    throw 'Another guarded Unreal mutation is active.'
}

$state = [ordered]@{
    schema = 'redmmo.ppg_home_presentation.r10n.outer_guard.v1'
    status = 'RUNNING'
    started_utc = [DateTime]::UtcNow.ToString('o')
}
$proc = $null

try {
    foreach ($path in @($projectFile, $editor, $driver, $homeMapFile, $manifest, $rollbackHome)) {
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
            throw "Required path missing: $path"
        }
    }
    foreach ($path in @($result, $log, $guard)) {
        if (Test-Path -LiteralPath $path) {
            throw "No-clobber output exists: $path"
        }
    }
    if ((Get-FileHash -LiteralPath $driver -Algorithm SHA256).Hash -ne $expectedDriver) {
        throw 'Driver hash drift.'
    }
    if ((Get-FileHash -LiteralPath $manifest -Algorithm SHA256).Hash -ne $expectedManifest) {
        throw 'Manifest hash drift.'
    }
    if ((Get-FileHash -LiteralPath $homeMapFile -Algorithm SHA256).Hash -ne $expectedHome) {
        throw 'Home map drift.'
    }
    if (Test-Path -LiteralPath $targetRoot) {
        throw 'R10N content root already exists.'
    }
    if (Test-Path -LiteralPath $profile) {
        throw 'R10N profile already exists.'
    }
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
    if (((Get-PSDrive D).Free / 1GB) -lt 100) {
        throw 'Disk gate failed.'
    }
    Assert-ProtectedHashes
    Assert-R10MSourceHashes

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
    $proc = Start-Process -FilePath $editor -ArgumentList $args -PassThru -WindowStyle Hidden
    $state.editor_pid = $proc.Id
    $state.free_ram_gib_at_launch = $free
    $minimumFree = $free
    $deadline = [DateTime]::UtcNow.AddMinutes(18)
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
            $abortReason = 'R10N build timeout.'
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
        throw 'R10N build result is missing.'
    }
    $payload = Get-Content -LiteralPath $result -Raw | ConvertFrom-Json
    if ($payload.status -ne 'PASS_STATIC_SERIALIZATION_PENDING_FRESH_RELOAD_MAPCHECK_AND_REAL_PIE') {
        throw "R10N build failed: $($payload.status) $($payload.error)"
    }
    if ((Get-FileHash -LiteralPath $homeMapFile -Algorithm SHA256).Hash -ne $payload.home_map_sha256_after) {
        throw 'R10N home hash drift after build.'
    }
    Start-Sleep -Seconds 3
    if ((Get-UnrealProcesses).Count -ne 0) {
        throw 'An Unreal/build process remains after R10N build.'
    }
    Assert-ProtectedHashes
    Assert-R10MSourceHashes

    $state.status = $payload.status
    $state.home_map_sha256_after = $payload.home_map_sha256_after
    $state.result_sha256 = (Get-FileHash -LiteralPath $result -Algorithm SHA256).Hash
    $state.created_asset_count = @($payload.created_assets).Count
    $state.providers_disabled = $true
}
catch {
    $state.error = $_.Exception.Message
    try {
        if ($null -ne $proc -and -not $proc.HasExited) {
            $state.stopped_exact_process_ids = @(Stop-ExactProcessTree $proc.Id)
            $proc.WaitForExit()
        }
        Start-Sleep -Seconds 2
        Restore-R10M
        Assert-ProtectedHashes
        Assert-R10MSourceHashes
        $state.status = 'FAIL_ROLLED_BACK_TO_R10M'
    }
    catch {
        $state.status = 'FAIL_ROLLBACK_INCOMPLETE'
        $state.rollback_error = $_.Exception.Message
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
