$ErrorActionPreference = 'Stop'

$projectRoot = 'D:\RedMMOTitanWindowsData\Projects\RedMMO'
$projectFile = Join-Path $projectRoot 'RedMMO.uproject'
$editor = 'D:\UE_5.8\Engine\Binaries\Win64\UnrealEditor.exe'
$driver = 'D:\RedMMOTitan\Build\Automation\verify_r15_fresh_reload.py'
$diag = 'D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_PPG_ContinentBiome_R15_20260802_211912'
$finalizerResult = Join-Path $diag 'finalize_r15_continent_biome_r05_result.json'
$finalizerGuard = Join-Path $diag 'run_r15_finalizer_guard_r05_result.json'
$result = Join-Path $diag 'verify_r15_fresh_reload_r02_result.json'
$log = Join-Path $diag 'verify_r15_fresh_reload_r02.log'
$guard = Join-Path $diag 'run_r15_verify_guard_r02_result.json'
$homeMapFile = Join-Path $projectRoot 'Content\RedMMO\Maps\RedMMO_PPG_HomeWorld.umap'
$profile = Join-Path $projectRoot 'Config\RedMMO\PPGContinentBiomeProfiles\HomeWorld_ContinentBiome_R15.json'
$expectedDriver = 'A3E575D2CAC7AB08225E1B57DB7D4C9089661F9BF1FB39807095F26728CA4EF8'
$expectedHomePost = '7BA68701F4B1A96777407FC8C349D90878037917CD3212878164B9A28BB37059'
$expectedFinalizerResult = 'DEF1A4D5F56DA6F0FB6296B553882EB68D0DF8AA04D81A83256A4241B0F1EE95'
$expectedProfile = 'FAAD649D96227DC03589E0E604762A533D3232DAC65B42EBEB895B49D03DF3CD'

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

function Convert-AssetPathToFile([string]$AssetPath) {
    if (-not $AssetPath.StartsWith('/Game/')) {
        throw "Unexpected project asset path: $AssetPath"
    }
    $relative = $AssetPath.Substring('/Game'.Length).Replace('/', '\') + '.uasset'
    return Join-Path (Join-Path $projectRoot 'Content') $relative.TrimStart('\')
}

function Get-TrackedHashes($Finalizer) {
    $expectedHome = ([string]$Finalizer.home_map_sha256_after).ToUpperInvariant()
    if ($expectedHome -notmatch '^[0-9A-F]{64}$') {
        throw 'Finalizer post-R15 home hash is invalid.'
    }
    if ($expectedHome -ne $expectedHomePost) {
        throw 'Serialized post-R15 home hash drift.'
    }
    $values = [ordered]@{
        home_map = @{ Path = $homeMapFile; Expected = $expectedHome }
        profile = @{ Path = $profile; Expected = ([string]$Finalizer.profile_sha256).ToUpperInvariant() }
    }
    $assetProperties = @($Finalizer.project_owned_hashes.PSObject.Properties)
    if ($assetProperties.Count -ne 6) {
        throw "Expected six R15 project-owned assets, found $($assetProperties.Count)."
    }
    foreach ($property in $assetProperties) {
        $values["target:$($property.Name)"] = @{
            Path = Convert-AssetPathToFile $property.Name
            Expected = ([string]$property.Value).ToUpperInvariant()
        }
    }
    foreach ($entry in $protected.GetEnumerator()) {
        $values["protected:$($entry.Key)"] = @{ Path = $entry.Key; Expected = $entry.Value }
    }
    return $values
}

function Assert-TrackedHashes($Tracked) {
    $snapshot = [ordered]@{}
    foreach ($entry in $Tracked.GetEnumerator()) {
        Assert-Hash $entry.Value.Path $entry.Value.Expected $entry.Key
        $snapshot[$entry.Key] = $entry.Value.Expected
    }
    return $snapshot
}

$mutex = New-Object Threading.Mutex($false, 'RedMMO_UnrealMutation_Exclusive')
$held = $mutex.WaitOne(0)
if (-not $held) {
    $mutex.Dispose()
    throw 'Another guarded Unreal operation is active.'
}

$state = [ordered]@{
    schema = 'redmmo.ppg_home_continent_biome.r15.fresh_reload_guard.v1'
    status = 'RUNNING'
    started_utc = [DateTime]::UtcNow.ToString('o')
}
$proc = $null

try {
    foreach ($path in @($projectFile, $editor, $driver, $finalizerResult, $finalizerGuard, $homeMapFile, $profile)) {
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
            throw "Required path missing: $path"
        }
    }
    foreach ($path in @($result, $log, $guard)) {
        if (Test-Path -LiteralPath $path) {
            throw "No-clobber output exists: $path"
        }
    }
    Assert-Hash $driver $expectedDriver 'R15 fresh-reload verifier'
    $finalizer = Get-Content -LiteralPath $finalizerResult -Raw | ConvertFrom-Json
    $finalizerGate = Get-Content -LiteralPath $finalizerGuard -Raw | ConvertFrom-Json
    if ($finalizer.status -ne 'PASS_SERIALIZED_PENDING_FRESH_RELOAD_MAPCHECK_AND_REAL_GPU') {
        throw "R15 finalizer did not pass: $($finalizer.status)"
    }
    if ($finalizerGate.status -ne 'PASS_SERIALIZED_PENDING_FRESH_RELOAD_MAPCHECK_AND_REAL_GPU') {
        throw "R15 finalizer guard did not pass: $($finalizerGate.status)"
    }
    $finalizerHash = (Get-FileHash -LiteralPath $finalizerResult -Algorithm SHA256).Hash
    if ($finalizerHash -ne $expectedFinalizerResult) {
        throw 'R15 finalizer result hash drift.'
    }
    if ($finalizerGate.result_sha256 -ne $finalizerHash) {
        throw 'R15 finalizer result is not anchored by its guard.'
    }
    if (([string]$finalizer.profile_sha256).ToUpperInvariant() -ne $expectedProfile) {
        throw 'R15 profile evidence hash drift.'
    }
    $tracked = Get-TrackedHashes $finalizer
    $state.hashes_before = Assert-TrackedHashes $tracked
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
            $abortReason = 'R15 fresh-reload timeout.'
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
        throw 'R15 fresh-reload result is missing.'
    }
    $payload = Get-Content -LiteralPath $result -Raw | ConvertFrom-Json
    if ($payload.status -ne 'PASS_FRESH_RELOAD_MAPCHECK_ZERO_DIRTY_PENDING_REAL_GPU') {
        throw "R15 fresh reload failed: $($payload.status) $($payload.error)"
    }
    if ($payload.saved_project_state -ne $false) {
        throw 'R15 verifier reported a save operation.'
    }
    if ($payload.actor_count -ne 12 -or $payload.map_check.errors -ne 0 -or $payload.map_check.warnings -ne 0) {
        throw 'R15 actor or MapCheck acceptance drift.'
    }
    $state.hashes_after = Assert-TrackedHashes $tracked
    $beforeJson = $state.hashes_before | ConvertTo-Json -Compress
    $afterJson = $state.hashes_after | ConvertTo-Json -Compress
    if ($beforeJson -ne $afterJson) {
        throw 'Tracked files changed during fresh no-save verification.'
    }
    Start-Sleep -Seconds 2
    if ((Get-UnrealProcesses).Count -ne 0) {
        throw 'An Unreal/build process remains after R15 fresh reload.'
    }
    $logText = Get-Content -LiteralPath $log -Raw
    if ($logText -notmatch 'R15_FRESH_MAPCHECK_BEGIN_') {
        throw 'Fresh MapCheck marker is absent from the log.'
    }
    $state.status = 'PASS_FRESH_RELOAD_MAPCHECK_ZERO_DIRTY_PENDING_REAL_GPU'
    $state.result_sha256 = (Get-FileHash -LiteralPath $result -Algorithm SHA256).Hash
    $state.finalizer_result_sha256 = $finalizerHash
    $state.home_map_sha256 = ([string]$finalizer.home_map_sha256_after).ToUpperInvariant()
    $state.map_check = $payload.map_check
    $state.actor_count = $payload.actor_count
}
catch {
    $state.status = 'FAIL'
    $state.error = $_.Exception.Message
    if ($null -ne $proc -and -not $proc.HasExited) {
        $state.stopped_exact_process_ids = @(Stop-ExactProcessTree $proc.Id)
        $proc.WaitForExit()
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
