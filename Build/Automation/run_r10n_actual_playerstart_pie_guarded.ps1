$ErrorActionPreference = 'Stop'

$projectRoot = 'D:\RedMMOTitanWindowsData\Projects\RedMMO'
$projectFile = Join-Path $projectRoot 'RedMMO.uproject'
$editor = 'D:\UE_5.8\Engine\Binaries\Win64\UnrealEditor.exe'
$driver = 'D:\RedMMOTitan\Build\Automation\start_r10n_actual_playerstart_pie.py'
$diag = 'D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_PPG_HomePresentation_R10N_20260802_181848'
$result = Join-Path $diag 'start_r10n_actual_playerstart_pie_result.json'
$png = Join-Path $diag 'RedMMO_Home_R10N_actual_PlayerStart_PIE_1920x1080.png'
$log = Join-Path $diag 'start_r10n_actual_playerstart_pie.log'
$guard = Join-Path $diag 'run_r10n_actual_playerstart_pie_guard_result.json'
$verify = Join-Path $diag 'verify_r10n_fresh_reload_result.json'
$homeMapFile = Join-Path $projectRoot 'Content\RedMMO\Maps\RedMMO_PPG_HomeWorld.umap'
$expectedHome = 'A0F4FECBAAB38CCC40D5B667706D72E8402C2312EB523AAB28CD4C1F1A26C665'
$expectedDriver = 'F84F2F8E6FF96B3A834547372C1946D583334BF5728EC17FA940ADD9ECD04C59'
$expectedVerify = 'B9C3FE2EE1287B7F83A644CDDC2922CFC442BA8AEC5B5316CE6548BD87F72E05'

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

Add-Type @'
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Text;
public static class RedMMOWindowFocus {
    public delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lParam);
    [DllImport("user32.dll")] public static extern bool EnumWindows(EnumWindowsProc callback, IntPtr extraData);
    [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint processId);
    [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr hWnd);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] public static extern int GetWindowText(IntPtr hWnd, StringBuilder text, int count);
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int command);
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
    public static string[] FocusBest(uint pid) {
        var windows = new List<Tuple<IntPtr,string>>();
        EnumWindows(delegate(IntPtr hWnd, IntPtr lParam) {
            uint owner;
            GetWindowThreadProcessId(hWnd, out owner);
            if (owner == pid && IsWindowVisible(hWnd)) {
                var title = new StringBuilder(1024);
                GetWindowText(hWnd, title, title.Capacity);
                if (title.Length > 0) windows.Add(Tuple.Create(hWnd, title.ToString()));
            }
            return true;
        }, IntPtr.Zero);
        Tuple<IntPtr,string> best = null;
        foreach (var item in windows) {
            if (item.Item2.IndexOf("Preview", StringComparison.OrdinalIgnoreCase) >= 0 ||
                item.Item2.IndexOf("Standalone", StringComparison.OrdinalIgnoreCase) >= 0) {
                best = item;
                break;
            }
        }
        if (best == null && windows.Count > 0) best = windows[0];
        if (best != null) {
            ShowWindow(best.Item1, 9);
            SetForegroundWindow(best.Item1);
        }
        var titles = new List<string>();
        foreach (var item in windows) titles.Add(item.Item2);
        return titles.ToArray();
    }
}
'@

$mutex = New-Object Threading.Mutex($false, 'RedMMO_UnrealMutation_Exclusive')
$held = $mutex.WaitOne(0)
if (-not $held) {
    $mutex.Dispose()
    throw 'Another guarded Unreal operation is active.'
}

$state = [ordered]@{
    schema = 'redmmo.ppg_home_presentation.r10n.visible_pie_guard.v1'
    status = 'RUNNING'
    started_utc = [DateTime]::UtcNow.ToString('o')
}
$proc = $null
$success = $false

try {
    foreach ($path in @($projectFile, $editor, $driver, $homeMapFile, $verify)) {
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
            throw "Required path missing: $path"
        }
    }
    foreach ($path in @($result, $png, $log, $guard)) {
        if (Test-Path -LiteralPath $path) {
            throw "No-clobber output exists: $path"
        }
    }
    if ((Get-FileHash -LiteralPath $driver -Algorithm SHA256).Hash -ne $expectedDriver) {
        throw 'PIE driver hash drift.'
    }
    if ((Get-FileHash -LiteralPath $verify -Algorithm SHA256).Hash -ne $expectedVerify) {
        throw 'Fresh-reload evidence hash drift.'
    }
    if ((Get-FileHash -LiteralPath $homeMapFile -Algorithm SHA256).Hash -ne $expectedHome) {
        throw 'R10N home hash drift.'
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

    $args = @(
        $projectFile,
        '/Game/RedMMO/Maps/RedMMO_PPG_HomeWorld',
        '-NoSplash',
        '-NoLiveCoding',
        '-NoSourceControl',
        '-d3d12',
        '-DisablePlugins=ModelContextProtocol,Nwiro,UnrealAIIntegrationPlatform',
        "-ExecCmds=`"py $($driver.Replace('\','/'))`"",
        "-abslog=$($log.Replace('\','/'))"
    )
    $proc = Start-Process -FilePath $editor -ArgumentList $args -PassThru
    $state.editor_pid = $proc.Id
    $state.free_ram_gib_at_launch = $free
    $minimumFree = $free
    $deadline = [DateTime]::UtcNow.AddMinutes(10)
    while (-not (Test-Path -LiteralPath $result -PathType Leaf)) {
        Start-Sleep -Milliseconds 750
        $proc.Refresh()
        if ($proc.HasExited) {
            throw "Editor exited before PIE readiness with code $($proc.ExitCode)"
        }
        $current = Get-FreeRamGiB
        if ($current -lt $minimumFree) {
            $minimumFree = $current
        }
        if ($current -lt 8) {
            throw "RAM abort floor crossed: $current GiB"
        }
        if ([DateTime]::UtcNow -gt $deadline) {
            throw 'R10N actual-PlayerStart PIE readiness timeout.'
        }
    }
    Start-Sleep -Seconds 2
    $payload = Get-Content -LiteralPath $result -Raw | ConvertFrom-Json
    $allowed = @(
        'PASS_REAL_GPU_ACTUAL_PLAYERSTART_PIE_READY_PENDING_HUMAN_REVIEW',
        'REAL_GPU_ACTUAL_PLAYERSTART_PIE_READY_WITH_PER_CHUNK_FOLIAGE_CAP_BLOCKER'
    )
    if ($payload.status -notin $allowed) {
        throw "R10N actual-PlayerStart PIE failed: $($payload.status) $($payload.error)"
    }
    if (-not (Test-Path -LiteralPath $png -PathType Leaf)) {
        throw 'R10N actual-PlayerStart screenshot missing.'
    }
    $proc.Refresh()
    if ($proc.HasExited) {
        throw 'Editor closed after PIE readiness instead of remaining open.'
    }
    $identity = Get-CimInstance Win32_Process -Filter "ProcessId=$($proc.Id)"
    if ($null -eq $identity -or $identity.CommandLine -notlike "*$projectFile*" -or $identity.CommandLine -notlike "*$driver*") {
        throw 'Retained editor identity drift.'
    }
    if ((Get-FileHash -LiteralPath $homeMapFile -Algorithm SHA256).Hash -ne $expectedHome) {
        throw 'PIE changed the R10N home map.'
    }
    $windowTitles = [RedMMOWindowFocus]::FocusBest([uint32]$proc.Id)
    $state.minimum_free_ram_gib = $minimumFree
    $state.pie_status = $payload.status
    $state.pie_generation = $payload.generation
    $state.pawn_class = $payload.pie_playerstart_contract.pawn_class
    $state.pawn_distance_from_player_start_cm = $payload.pie_playerstart_contract.pawn_distance_from_player_start_cm
    $state.screenshot = $payload.screenshot
    $state.window_titles = @($windowTitles)
    $state.editor_and_pie_left_open = $true
    $state.status = 'PASS_VISIBLE_EDITOR_ACTUAL_PLAYERSTART_PIE_LEFT_OPEN_FOR_USER'
    $success = $true
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
