param(
    [ValidatePattern('^[A-Za-z0-9][A-Za-z0-9._-]{0,95}$')]
    [string]$SessionId = 'R15_UserPlay_R01'
)

$ErrorActionPreference = 'Stop'

$projectRoot = 'D:\RedMMOTitanWindowsData\Projects\RedMMO'
$projectFile = Join-Path $projectRoot 'RedMMO.uproject'
$homeMap = '/Game/RedMMO/Maps/RedMMO_PPG_HomeWorld'
$homeFile = Join-Path $projectRoot 'Content\RedMMO\Maps\RedMMO_PPG_HomeWorld.umap'
$editor = 'D:\UE_5.8\Engine\Binaries\Win64\UnrealEditor.exe'
$diagRoot = 'D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_PPG_ContinentBiome_R15_20260802_211912'
$freshVerify = Join-Path $diagRoot 'verify_r15_fresh_reload_r02_result.json'
$freshGuard = Join-Path $diagRoot 'run_r15_verify_guard_r02_result.json'
$sessionRoot = Join-Path $diagRoot $SessionId
$log = Join-Path $sessionRoot 'r15_user_play_editor.log'
$result = Join-Path $sessionRoot 'r15_user_play_ready.json'
$endpoint = 'http://127.0.0.1:8000/mcp'
$expectedHome = '7BA68701F4B1A96777407FC8C349D90878037917CD3212878164B9A28BB37059'

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
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { throw "$Label missing: $Path" }
    $actual = (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash
    if ($actual -ne $Expected) { throw "$Label hash drift: actual=$actual expected=$Expected" }
}

function Assert-Protected {
    foreach ($entry in $protected.GetEnumerator()) { Assert-Hash $entry.Key $entry.Value 'Protected file' }
}

function Get-McpJson([string]$Content) {
    $line = ($Content -split "`r?`n" | Where-Object { $_ -like 'data: *' } | Select-Object -First 1)
    if ($line) { return ($line.Substring(6) | ConvertFrom-Json) }
    $trimmed = $Content.Trim()
    if ($trimmed.StartsWith('{')) { return ($trimmed | ConvertFrom-Json) }
    throw 'MCP response is neither SSE JSON nor application/json.'
}

function Invoke-McpPost([string]$Body, [hashtable]$Headers, [int]$TimeoutSec = 180) {
    return Invoke-WebRequest -Uri $endpoint -Method Post -UseBasicParsing -ContentType 'application/json' -Headers $Headers -Body $Body -TimeoutSec $TimeoutSec
}

function Invoke-EditorTool([int]$Id, [hashtable]$Headers, [string]$Tool, [hashtable]$Arguments) {
    $body = @{
        jsonrpc = '2.0'; id = $Id; method = 'tools/call'
        params = @{
            name = 'call_tool'
            arguments = @{ toolset_name = 'EditorToolset.EditorAppToolset'; tool_name = $Tool; arguments = $Arguments }
        }
    } | ConvertTo-Json -Depth 14 -Compress
    $response = Invoke-McpPost $body $Headers 240
    $json = Get-McpJson $response.Content
    if ($response.StatusCode -ne 200 -or $null -ne $json.error -or [bool]$json.result.isError) {
        throw "Epic MCP tool failed: $Tool; response=$(($json | ConvertTo-Json -Depth 20 -Compress))"
    }
    $text = @($json.result.content | Where-Object { $_.type -eq 'text' } | ForEach-Object { [string]$_.text }) -join "`n"
    return $(if ($text) { $text | ConvertFrom-Json } else { [pscustomobject]@{} })
}

foreach ($path in @($projectFile, $homeFile, $editor, $freshVerify, $freshGuard)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Required path missing: $path" }
}
if (Test-Path -LiteralPath $sessionRoot) { throw "No-clobber play session exists: $sessionRoot" }
Assert-Hash $homeFile $expectedHome 'R15 home map'
Assert-Protected
$verify = Get-Content -LiteralPath $freshVerify -Raw | ConvertFrom-Json
$guard = Get-Content -LiteralPath $freshGuard -Raw | ConvertFrom-Json
if ($verify.status -ne 'PASS_FRESH_RELOAD_MAPCHECK_ZERO_DIRTY_PENDING_REAL_GPU' -or
    $verify.home_map_sha256 -ne $expectedHome -or
    $verify.map_check.errors -ne 0 -or $verify.map_check.warnings -ne 0 -or
    $guard.status -ne 'PASS_FRESH_RELOAD_MAPCHECK_ZERO_DIRTY_PENDING_REAL_GPU' -or
    $guard.result_sha256 -ne (Get-FileHash -LiteralPath $freshVerify -Algorithm SHA256).Hash) {
    throw 'Frozen R15 fresh-reload evidence gate failed.'
}
if (@(Get-UnrealProcesses).Count -ne 0) { throw 'Another Unreal/build process is active.' }
if (@(Get-NetTCPConnection -State Listen -LocalPort 5353,8000,8765 -ErrorAction SilentlyContinue).Count -ne 0) { throw 'An AI/provider listener is already active.' }
$freeRam = Get-FreeRamGiB
if ($freeRam -lt 12) { throw "RAM gate failed: $freeRam GiB" }

[void][IO.Directory]::CreateDirectory($sessionRoot)
$state = [ordered]@{
    schema = 'redmmo.r15.user_play.epic_mcp.v1'
    status = 'STARTING'
    started_utc = [DateTime]::UtcNow.ToString('o')
    project = $projectFile
    map = $homeMap
    home_map_sha256 = $expectedHome
    free_ram_gib_at_launch = $freeRam
    direct_interface = 'official Epic ModelContextProtocol 1.0'
    direct_action = 'EditorToolset.EditorAppToolset.StartPIE'
    disabled_integrations = @('Nwiro','NwiroIntegrationKit','UnrealAIIntegrationPlatform','VibeUE','MCPClientToolset')
    save_requested = $false
}
$proc = $null
$sessionHeaders = $null
$failure = $null
try {
    $args = @(
        $projectFile, $homeMap, '-NoSplash', '-NoLiveCoding', '-NoSourceControl', '-d3d12', '-Windowed',
        '-EnablePlugins=ModelContextProtocol,ToolsetRegistry,EditorToolset', '-ModelContextProtocolStartServer',
        '-DisablePlugins=Nwiro,NwiroIntegrationKit,UnrealAIIntegrationPlatform,VibeUE,MCPClientToolset',
        "-abslog=$($log.Replace('\','/'))"
    )
    $proc = Start-Process -FilePath $editor -ArgumentList $args -PassThru -WindowStyle Normal
    $state.editor_pid = $proc.Id
    $minimumFree = $freeRam
    $deadline = [DateTime]::UtcNow.AddMinutes(10)
    $generation = $null
    while ([DateTime]::UtcNow -lt $deadline) {
        Start-Sleep -Milliseconds 500
        $proc.Refresh()
        if ($proc.HasExited) { throw "Editor exited before PIE: $($proc.ExitCode)" }
        $currentFree = Get-FreeRamGiB
        if ($currentFree -lt $minimumFree) { $minimumFree = $currentFree }
        if ($currentFree -lt 8) { throw "RAM abort floor crossed: $currentFree GiB" }
        $listener = @(Get-NetTCPConnection -State Listen -LocalPort 8000 -ErrorAction SilentlyContinue | Where-Object { $_.OwningProcess -eq $proc.Id })
        if ($listener.Count -eq 1 -and (Test-Path -LiteralPath $log -PathType Leaf)) {
            $text = Get-Content -LiteralPath $log -Raw
            $matches = [regex]::Matches($text, 'LogPPG: Planet generation completed in ([0-9.]+) ms with ([0-9]+) chunks\.')
            if ($matches.Count) { $generation = $matches[$matches.Count - 1]; break }
        }
    }
    if ($null -eq $generation) { throw 'Editor/MCP/PPG did not become ready.' }
    $state.minimum_free_ram_gib_during_start = $minimumFree
    $state.editor_generation = @{ time_ms = [double]$generation.Groups[1].Value; chunks = [int]$generation.Groups[2].Value }

    $baseHeaders = @{ Accept = 'application/json, text/event-stream' }
    $initBody = @{ jsonrpc='2.0'; id=1; method='initialize'; params=@{ protocolVersion='2025-11-25'; capabilities=@{}; clientInfo=@{name='redmmo-r15-user-play';version='1.0.0'} } } | ConvertTo-Json -Depth 8 -Compress
    $initResponse = Invoke-McpPost $initBody $baseHeaders 60
    $initJson = Get-McpJson $initResponse.Content
    $mcpSessionId = [string]$initResponse.Headers['Mcp-Session-Id']
    if ($initResponse.StatusCode -ne 200 -or -not $mcpSessionId) { throw 'Epic MCP initialize failed.' }
    $sessionHeaders = @{ Accept='application/json, text/event-stream'; 'Mcp-Session-Id'=$mcpSessionId; 'MCP-Protocol-Version'=[string]$initJson.result.protocolVersion }
    $ready = Invoke-McpPost ((@{jsonrpc='2.0';method='notifications/initialized'}|ConvertTo-Json -Compress)) $sessionHeaders 60
    if ($ready.StatusCode -notin 200,202) { throw 'Epic MCP initialized notification failed.' }
    [void](Invoke-EditorTool 10 $sessionHeaders 'StartPIE' @{
        options = @{ bSimulate = $false; playMode = 'PlayMode_InEditorFloating'; startTransform = $null; warmupSeconds = 6.0 }
    })
    $pie = Invoke-EditorTool 11 $sessionHeaders 'IsPIERunning' @{}
    if (-not [bool]$pie.returnValue) { throw 'Epic MCP reports PIE is not running.' }
    Assert-Hash $homeFile $expectedHome 'R15 home map after PIE start'
    Assert-Protected
    $state.status = 'PASS_PIE_RUNNING_READY_FOR_USER'
    $state.pie_running = $true
    $state.play_mode = 'PlayMode_InEditorFloating'
    $state.provider_ports = @(
        @{ port = 8000; purpose = 'official Epic MCP'; listening = [bool](Get-NetTCPConnection -State Listen -LocalPort 8000 -ErrorAction SilentlyContinue) },
        @{ port = 5353; purpose = 'NWIRO'; listening = [bool](Get-NetTCPConnection -State Listen -LocalPort 5353 -ErrorAction SilentlyContinue) },
        @{ port = 8765; purpose = 'UAIP'; listening = [bool](Get-NetTCPConnection -State Listen -LocalPort 8765 -ErrorAction SilentlyContinue) }
    )
    $state.completed_utc = [DateTime]::UtcNow.ToString('o')
}
catch {
    $failure = $_
    $state.status = 'FAIL'
    $state.error = $_.Exception.Message
    if ($null -ne $proc -and -not $proc.HasExited) { $state.stopped_exact_process_ids = @(Stop-ExactProcessTree $proc.Id) }
}
finally {
    if ($null -ne $sessionHeaders) {
        try {
            $deleted = Invoke-WebRequest -Uri $endpoint -Method Delete -UseBasicParsing -Headers $sessionHeaders -TimeoutSec 30
            $state.mcp_session_close_http_status = [int]$deleted.StatusCode
        } catch { $state.mcp_session_close_error = $_.Exception.Message }
    }
    if (-not $state.completed_utc) { $state.completed_utc = [DateTime]::UtcNow.ToString('o') }
    $bytes = [Text.UTF8Encoding]::new($false).GetBytes(($state | ConvertTo-Json -Depth 16) + "`n")
    $stream = [IO.File]::Open($result,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
    try { $stream.Write($bytes,0,$bytes.Length); $stream.Flush($true) } finally { $stream.Dispose() }
}

$state | ConvertTo-Json -Depth 12
if ($null -ne $failure) { throw $failure }
