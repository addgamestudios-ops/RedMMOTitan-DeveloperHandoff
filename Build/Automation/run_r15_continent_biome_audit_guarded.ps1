$ErrorActionPreference = 'Stop'

$projectRoot = 'D:\RedMMOTitanWindowsData\Projects\RedMMO'
$projectFile = Join-Path $projectRoot 'RedMMO.uproject'
$editor = 'D:\UE_5.8\Engine\Binaries\Win64\UnrealEditor.exe'
$driver = 'D:\RedMMOTitan\Build\Automation\audit_redmmo_ppg_continent_biome_controls_r15.py'
$diag = 'D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_PPG_ContinentBiomeControls_R15_20260802'
$result = Join-Path $diag 'audit_redmmo_ppg_continent_biome_controls_r15_result.json'
$log = Join-Path $diag 'audit_redmmo_ppg_continent_biome_controls_r15.log'
$guard = Join-Path $diag 'run_r15_continent_biome_audit_guard_result.json'
$homeMapFile = Join-Path $projectRoot 'Content\RedMMO\Maps\RedMMO_PPG_HomeWorld.umap'
$expectedHome = 'C9BE88085575E75E1790CB9306D564EB100F5ED2E75E012C1FD09EA110FDDFE0'
$expectedDriver = '00C778F595AAA95FBF3BDA7E86B320EE9F4C8C2447B7DF1A4964387B23E5A23D'

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
    schema = 'redmmo.ppg_continent_biome_controls.r15.audit_guard.v1'
    status = 'RUNNING'
    started_utc = [DateTime]::UtcNow.ToString('o')
}
$proc = $null

try {
    foreach ($path in @($projectFile, $editor, $driver, $homeMapFile)) {
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Required path missing: $path" }
    }
    if (Test-Path -LiteralPath $diag) { throw "No-clobber diagnostic root exists: $diag" }
    if ((Get-FileHash -LiteralPath $driver -Algorithm SHA256).Hash -ne $expectedDriver) { throw 'Audit driver hash drift.' }
    if ((Get-FileHash -LiteralPath $homeMapFile -Algorithm SHA256).Hash -ne $expectedHome) { throw 'Home map hash drift before audit.' }
    if ((Get-UnrealProcesses).Count -ne 0) { throw 'Another Unreal/build process is active.' }
    $listeners = @(Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | Where-Object { $_.LocalPort -in 5353, 8000, 8765 })
    if ($listeners.Count -ne 0) { throw 'An AI/provider listener is active.' }
    $free = Get-FreeRamGiB
    if ($free -lt 12) { throw "RAM gate failed: $free GiB" }

    New-Item -ItemType Directory -Path $diag -ErrorAction Stop | Out-Null
    $args = @(
        $projectFile,
        '/Game/RedMMO/Maps/RedMMO_PPG_HomeWorld',
        '-NoSplash', '-NoLiveCoding', '-NoSound', '-NoSourceControl', '-unattended',
        '-d3d12', '-RenderOffscreen',
        '-DisablePlugins=ModelContextProtocol,Nwiro,NwiroIntegrationKit,UnrealAIIntegrationPlatform,VibeUE,MCPClientToolset',
        "-ExecCmds=`"py $($driver.Replace('\','/'))`"",
        "-abslog=$($log.Replace('\','/'))"
    )
    $proc = Start-Process -FilePath $editor -ArgumentList $args -PassThru -WindowStyle Hidden
    $state.editor_pid = $proc.Id
    $state.free_ram_gib_at_launch = $free
    $minimumFree = $free
    $deadline = [DateTime]::UtcNow.AddMinutes(10)
    $abortReason = $null
    while (-not $proc.HasExited) {
        Start-Sleep -Milliseconds 750
        $proc.Refresh()
        $current = Get-FreeRamGiB
        if ($current -lt $minimumFree) { $minimumFree = $current }
        if ($current -lt 8) { $abortReason = "RAM abort floor crossed: $current GiB"; break }
        if ([DateTime]::UtcNow -gt $deadline) { $abortReason = 'R15 read-only audit timeout.'; break }
    }
    $state.minimum_free_ram_gib = $minimumFree
    if ($abortReason) {
        $state.stopped_exact_process_ids = @(Stop-ExactProcessTree $proc.Id)
        $proc.WaitForExit()
        throw $abortReason
    }
    $state.editor_exit_code = $proc.ExitCode
    if ($proc.ExitCode -ne 0) { throw "Editor exit code $($proc.ExitCode)" }
    if (-not (Test-Path -LiteralPath $result -PathType Leaf)) { throw 'R15 audit result is missing.' }
    $payload = Get-Content -LiteralPath $result -Raw | ConvertFrom-Json
    if ($payload.status -ne 'PASS_READ_ONLY_CONTROL_INVENTORY') { throw "R15 audit failed: $($payload.status) $($payload.error)" }
    if ((Get-FileHash -LiteralPath $homeMapFile -Algorithm SHA256).Hash -ne $expectedHome) { throw 'R15 audit changed the home map.' }
    if ((Get-UnrealProcesses).Count -ne 0) { throw 'An Unreal/build process remains after R15 audit.' }
    $state.result_sha256 = (Get-FileHash -LiteralPath $result -Algorithm SHA256).Hash
    $state.status = 'PASS_READ_ONLY_CONTROL_INVENTORY'
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
    if (-not (Test-Path -LiteralPath $diag)) { New-Item -ItemType Directory -Path $diag -ErrorAction Stop | Out-Null }
    $bytes = [Text.UTF8Encoding]::new($false).GetBytes(($state | ConvertTo-Json -Depth 10))
    $stream = [IO.File]::Open($guard, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
    try { $stream.Write($bytes, 0, $bytes.Length); $stream.Flush($true) }
    finally { $stream.Dispose() }
    if ($held) { $mutex.ReleaseMutex() }
    $mutex.Dispose()
}
