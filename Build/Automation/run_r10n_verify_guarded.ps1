$ErrorActionPreference = 'Stop'

$projectRoot = 'D:\RedMMOTitanWindowsData\Projects\RedMMO'
$projectFile = Join-Path $projectRoot 'RedMMO.uproject'
$editor = 'D:\UE_5.8\Engine\Binaries\Win64\UnrealEditor.exe'
$driver = 'D:\RedMMOTitan\Build\Automation\verify_r10n_fresh_reload.py'
$diag = 'D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_PPG_HomePresentation_R10N_20260802_181848'
$result = Join-Path $diag 'verify_r10n_fresh_reload_result.json'
$log = Join-Path $diag 'verify_r10n_fresh_reload.log'
$guard = Join-Path $diag 'run_r10n_verify_guard_result.json'
$homeMapFile = Join-Path $projectRoot 'Content\RedMMO\Maps\RedMMO_PPG_HomeWorld.umap'
$expectedHome = 'A0F4FECBAAB38CCC40D5B667706D72E8402C2312EB523AAB28CD4C1F1A26C665'
$expectedDriver = '2F6F18FB63064E72C337271BC702084CB979F97D3B444BA214ECE005644365A0'

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

$mutex = New-Object Threading.Mutex($false, 'RedMMO_UnrealMutation_Exclusive')
$held = $mutex.WaitOne(0)
if (-not $held) {
    $mutex.Dispose()
    throw 'Another guarded Unreal operation is active.'
}

$state = [ordered]@{
    schema = 'redmmo.ppg_home_presentation.r10n.reload_guard.v1'
    status = 'RUNNING'
    started_utc = [DateTime]::UtcNow.ToString('o')
}
$proc = $null

try {
    foreach ($path in @($projectFile, $editor, $driver, $homeMapFile)) {
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
        throw 'Verifier driver hash drift.'
    }
    if ((Get-FileHash -LiteralPath $homeMapFile -Algorithm SHA256).Hash -ne $expectedHome) {
        throw 'R10N home hash drift before reload.'
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
    $deadline = [DateTime]::UtcNow.AddMinutes(12)
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
            $abortReason = 'R10N fresh-reload timeout.'
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
        throw 'R10N reload result is missing.'
    }
    $payload = Get-Content -LiteralPath $result -Raw | ConvertFrom-Json
    if ($payload.status -ne 'PASS_FRESH_RELOAD_AND_MAPCHECK_PENDING_ACTUAL_PLAYERSTART_REAL_PIE') {
        throw "R10N reload failed: $($payload.status) $($payload.error)"
    }
    if ((Get-FileHash -LiteralPath $homeMapFile -Algorithm SHA256).Hash -ne $expectedHome) {
        throw 'R10N reload changed the home map.'
    }
    Start-Sleep -Seconds 2
    if ((Get-UnrealProcesses).Count -ne 0) {
        throw 'An Unreal/build process remains after R10N reload.'
    }

    $logText = Get-Content -LiteralPath $log -Raw
    $generation = [regex]::Matches($logText, 'Planet generation completed in ([0-9.]+) ms with ([0-9]+) chunks')
    if ($generation.Count -lt 1) {
        throw 'No completed asynchronous PPG generation marker in fresh-reload log.'
    }
    $overflows = [regex]::Matches($logText, 'PPG foliage output overflowed: generated ([0-9]+) records, retained ([0-9]+)')
    $generatedCounts = @($overflows | ForEach-Object { [int]$_.Groups[1].Value })
    $retainedCounts = @($overflows | ForEach-Object { [int]$_.Groups[2].Value })
    $state.generation_completed = $true
    $state.generation_time_ms = [double]$generation[$generation.Count - 1].Groups[1].Value
    $state.generation_chunks = [int]$generation[$generation.Count - 1].Groups[2].Value
    $state.foliage_overflow_count = $overflows.Count
    $state.foliage_generated_min = if ($generatedCounts.Count) { ($generatedCounts | Measure-Object -Minimum).Minimum } else { 0 }
    $state.foliage_generated_max = if ($generatedCounts.Count) { ($generatedCounts | Measure-Object -Maximum).Maximum } else { 0 }
    $state.foliage_retained_values = @($retainedCounts | Sort-Object -Unique)
    $state.map_check = $payload.map_check
    $state.result_sha256 = (Get-FileHash -LiteralPath $result -Algorithm SHA256).Hash
    $state.status = if ($overflows.Count) {
        'PASS_FRESH_RELOAD_MAPCHECK_WITH_PER_CHUNK_FOLIAGE_CAP_PENDING_ACTUAL_PLAYERSTART_REAL_PIE'
    }
    else {
        'PASS_FRESH_RELOAD_MAPCHECK_PENDING_ACTUAL_PLAYERSTART_REAL_PIE'
    }
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
