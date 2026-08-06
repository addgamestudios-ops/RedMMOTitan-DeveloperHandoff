$ErrorActionPreference = 'Stop'

$projectRoot = 'D:\RedMMOTitanWindowsData\Projects\RedMMO'
$projectFile = Join-Path $projectRoot 'RedMMO.uproject'
$homeMapFile = Join-Path $projectRoot 'Content\RedMMO\Maps\RedMMO_PPG_HomeWorld.umap'
$editor = 'D:\UE_5.8\Engine\Binaries\Win64\UnrealEditor.exe'
$diag = 'D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_PPG_ContinentBiome_R15_20260802_211912'
$log = Join-Path $diag 'r15_epic_mcp_editor.log'
$statePath = Join-Path $diag 'r15_epic_mcp_editor_start.json'
$expectedHome = 'C9BE88085575E75E1790CB9306D564EB100F5ED2E75E012C1FD09EA110FDDFE0'

function Get-FreeRamGiB {
    $os = Get-CimInstance Win32_OperatingSystem
    return [math]::Round(($os.FreePhysicalMemory * 1KB) / 1GB, 3)
}

foreach ($path in @($projectFile, $homeMapFile, $editor)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Missing required path: $path" }
}
foreach ($path in @($log, $statePath)) {
    if (Test-Path -LiteralPath $path) { throw "No-clobber output exists: $path" }
}
if ((Get-FileHash -LiteralPath $homeMapFile -Algorithm SHA256).Hash -ne $expectedHome) { throw 'Home map hash drift before MCP editor launch.' }
$unreal = @(Get-CimInstance Win32_Process | Where-Object {
    $_.Name -match '^(UnrealEditor|UnrealEditor-Cmd|ShaderCompileWorker|UnrealBuildTool|UnrealHeaderTool|AutomationTool|CrashReportClient)'
})
if ($unreal.Count -ne 0) { throw 'Another Unreal/build process is active.' }
if (@(Get-NetTCPConnection -State Listen -LocalPort 5353,8000,8765 -ErrorAction SilentlyContinue).Count -ne 0) {
    throw 'An AI/provider listener is already active.'
}
$free = Get-FreeRamGiB
if ($free -lt 12) { throw "RAM gate failed: $free GiB" }

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
    '-EnablePlugins=ModelContextProtocol,ToolsetRegistry,EditorToolset',
    '-ModelContextProtocolStartServer',
    '-DisablePlugins=Nwiro,NwiroIntegrationKit,UnrealAIIntegrationPlatform,VibeUE,MCPClientToolset',
    "-abslog=$($log.Replace('\','/'))"
)
$proc = Start-Process -FilePath $editor -ArgumentList $args -PassThru -WindowStyle Hidden
$deadline = [DateTime]::UtcNow.AddMinutes(8)
$minimumFree = $free
try {
    while ([DateTime]::UtcNow -lt $deadline) {
        Start-Sleep -Milliseconds 500
        $proc.Refresh()
        if ($proc.HasExited) { throw "Editor exited during startup: $($proc.ExitCode)" }
        $current = Get-FreeRamGiB
        if ($current -lt $minimumFree) { $minimumFree = $current }
        if ($current -lt 8) { throw "RAM abort floor crossed: $current GiB" }
        $listener = @(Get-NetTCPConnection -State Listen -LocalPort 8000 -ErrorAction SilentlyContinue | Where-Object { $_.OwningProcess -eq $proc.Id })
        if ($listener.Count -eq 1) { break }
    }
    $listener = @(Get-NetTCPConnection -State Listen -LocalPort 8000 -ErrorAction SilentlyContinue | Where-Object { $_.OwningProcess -eq $proc.Id })
    if ($listener.Count -ne 1) { throw 'Epic MCP listener did not bind to launched editor.' }
    $state = [ordered]@{
        schema = 'redmmo.r15.epic_mcp_editor_session.v1'
        status = 'READY'
        created_utc = [DateTime]::UtcNow.ToString('o')
        editor_pid = $proc.Id
        project = $projectFile
        map = '/Game/RedMMO/Maps/RedMMO_PPG_HomeWorld'
        endpoint = 'http://127.0.0.1:8000/mcp'
        free_ram_gib_at_launch = $free
        minimum_free_ram_gib_during_start = $minimumFree
        enabled_direct_integration = 'ModelContextProtocol 1.0'
        disabled_integrations = @('Nwiro','NwiroIntegrationKit','UnrealAIIntegrationPlatform','VibeUE','MCPClientToolset')
    }
    $bytes = [Text.UTF8Encoding]::new($false).GetBytes(($state | ConvertTo-Json -Depth 7) + "`n")
    $stream = [IO.File]::Open($statePath, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
    try { $stream.Write($bytes, 0, $bytes.Length); $stream.Flush($true) } finally { $stream.Dispose() }
    $state | ConvertTo-Json -Depth 7
}
catch {
    if (-not $proc.HasExited) { Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue }
    throw
}
