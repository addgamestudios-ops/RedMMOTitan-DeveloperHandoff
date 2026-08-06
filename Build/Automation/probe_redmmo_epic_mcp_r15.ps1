$ErrorActionPreference = 'Stop'

$projectRoot = 'D:\RedMMOTitanWindowsData\Projects\RedMMO'
$projectFile = Join-Path $projectRoot 'RedMMO.uproject'
$homeMap = '/Game/RedMMO/Maps/RedMMO_PPG_HomeWorld'
$homeMapFile = Join-Path $projectRoot 'Content\RedMMO\Maps\RedMMO_PPG_HomeWorld.umap'
$editor = 'D:\UE_5.8\Engine\Binaries\Win64\UnrealEditor.exe'
$pluginDescriptor = 'D:\UE_5.8\Engine\Plugins\Experimental\ModelContextProtocol\ModelContextProtocol.uplugin'
$diag = 'D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_PPG_ContinentBiome_R15_20260802_211912'
$log = Join-Path $diag 'probe_redmmo_epic_mcp_r15_r02.log'
$resultPath = Join-Path $diag 'probe_redmmo_epic_mcp_r15_r02_result.json'
$endpoint = 'http://127.0.0.1:8000/mcp'
$expectedHome = 'C9BE88085575E75E1790CB9306D564EB100F5ED2E75E012C1FD09EA110FDDFE0'
$expectedPlugin = '1.0'

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
        if (-not (Test-Path -LiteralPath $entry.Key -PathType Leaf)) { throw "Protected file missing: $($entry.Key)" }
        if ((Get-FileHash -LiteralPath $entry.Key -Algorithm SHA256).Hash -ne $entry.Value) {
            throw "Protected hash drift: $($entry.Key)"
        }
    }
}

function Get-SseJson([string]$Content) {
    $line = ($Content -split "`r?`n" | Where-Object { $_ -like 'data: *' } | Select-Object -First 1)
    if ($line) { return ($line.Substring(6) | ConvertFrom-Json) }
    $trimmed = $Content.Trim()
    if ($trimmed.StartsWith('{')) { return ($trimmed | ConvertFrom-Json) }
    throw 'MCP response is neither SSE JSON nor application/json.'
}

function Invoke-McpPost([string]$Body, [hashtable]$Headers) {
    return Invoke-WebRequest -Uri $endpoint -Method Post -UseBasicParsing -ContentType 'application/json' -Headers $Headers -Body $Body -TimeoutSec 60
}

if (Test-Path -LiteralPath $resultPath) { throw "No-clobber result exists: $resultPath" }
if (Test-Path -LiteralPath $log) { throw "No-clobber log exists: $log" }
foreach ($path in @($projectFile, $homeMapFile, $editor, $pluginDescriptor)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Required path missing: $path" }
}
if ((Get-FileHash -LiteralPath $homeMapFile -Algorithm SHA256).Hash -ne $expectedHome) { throw 'Home map hash drift.' }
Assert-ProtectedHashes
$plugin = Get-Content -LiteralPath $pluginDescriptor -Raw | ConvertFrom-Json
if ($plugin.VersionName -ne $expectedPlugin) { throw "Epic MCP version drift: $($plugin.VersionName)" }
$project = Get-Content -LiteralPath $projectFile -Raw | ConvertFrom-Json
$entry = @($project.Plugins | Where-Object { $_.Name -eq 'ModelContextProtocol' })
if ($entry.Count -ne 1 -or -not $entry[0].Enabled) { throw 'ModelContextProtocol is not enabled in clean RedMMO.' }
if ((Get-UnrealProcesses).Count -ne 0) { throw 'Another Unreal/build process is active.' }
if (@(Get-NetTCPConnection -State Listen -LocalPort 5353,8000,8765 -ErrorAction SilentlyContinue).Count -ne 0) {
    throw 'An AI/provider listener is already active.'
}
$free = Get-FreeRamGiB
if ($free -lt 12) { throw "RAM gate failed: $free GiB" }

$state = [ordered]@{
    schema = 'redmmo.epic_mcp.r15.readonly_probe.v1'
    status = 'RUNNING'
    started_utc = [DateTime]::UtcNow.ToString('o')
    project = $projectFile
    map = $homeMap
    plugin = [ordered]@{
        descriptor = $pluginDescriptor
        friendly_name = $plugin.FriendlyName
        version = $plugin.VersionName
        valid_binaries = (Test-Path -LiteralPath (Join-Path (Split-Path $pluginDescriptor) 'Binaries\Win64\UnrealEditor-ModelContextProtocol.dll'))
    }
    free_ram_gib_at_launch = $free
    no_map_or_asset_mutation = $true
}
$proc = $null

try {
    $args = @(
        $projectFile,
        $homeMap,
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
    $state.editor_pid = $proc.Id
    $deadline = [DateTime]::UtcNow.AddMinutes(8)
    $minimumFree = $free
    while ([DateTime]::UtcNow -lt $deadline) {
        Start-Sleep -Milliseconds 500
        $proc.Refresh()
        if ($proc.HasExited) { throw "Editor exited before MCP probe: $($proc.ExitCode)" }
        $current = Get-FreeRamGiB
        if ($current -lt $minimumFree) { $minimumFree = $current }
        if ($current -lt 8) { throw "RAM abort floor crossed: $current GiB" }
        $listener = Get-NetTCPConnection -State Listen -LocalPort 8000 -ErrorAction SilentlyContinue | Where-Object { $_.OwningProcess -eq $proc.Id }
        if ($listener) { break }
    }
    $state.minimum_free_ram_gib = $minimumFree
    $listener = @(Get-NetTCPConnection -State Listen -LocalPort 8000 -ErrorAction SilentlyContinue | Where-Object { $_.OwningProcess -eq $proc.Id })
    if ($listener.Count -ne 1) { throw 'Epic MCP port 8000 did not bind to the launched editor.' }
    $state.listener = [ordered]@{ port = 8000; pid = $proc.Id; loopback = $true }

    $baseHeaders = @{ Accept = 'application/json, text/event-stream' }
    $initBody = @{ jsonrpc='2.0'; id=1; method='initialize'; params=@{ protocolVersion='2025-11-25'; capabilities=@{}; clientInfo=@{ name='redmmo-r15-guarded-probe'; version='1.0.0' } } } | ConvertTo-Json -Depth 8 -Compress
    $initResponse = Invoke-McpPost $initBody $baseHeaders
    $initJson = Get-SseJson $initResponse.Content
    $sessionId = [string]$initResponse.Headers['Mcp-Session-Id']
    if (-not $sessionId) { throw 'Epic MCP initialize returned no session ID.' }
    if ($initResponse.StatusCode -ne 200) { throw "Epic MCP initialize status $($initResponse.StatusCode)" }
    $state.initialize = [ordered]@{
        http_status = [int]$initResponse.StatusCode
        requested_protocol = '2025-11-25'
        negotiated_protocol = [string]$initJson.result.protocolVersion
        server_name = [string]$initJson.result.serverInfo.name
        server_version = [string]$initJson.result.serverInfo.version
        session_header_present = $true
    }

    $sessionHeaders = @{ Accept='application/json, text/event-stream'; 'Mcp-Session-Id'=$sessionId; 'MCP-Protocol-Version'=[string]$initJson.result.protocolVersion }
    $readyBody = @{ jsonrpc='2.0'; method='notifications/initialized' } | ConvertTo-Json -Compress
    $readyResponse = Invoke-McpPost $readyBody $sessionHeaders
    if ($readyResponse.StatusCode -notin 200,202) { throw "Initialized notification status $($readyResponse.StatusCode)" }
    $state.initialized_notification_http_status = [int]$readyResponse.StatusCode

    $listBody = @{ jsonrpc='2.0'; id=2; method='tools/list'; params=@{} } | ConvertTo-Json -Depth 4 -Compress
    $listResponse = Invoke-McpPost $listBody $sessionHeaders
    $listJson = Get-SseJson $listResponse.Content
    $toolNames = @($listJson.result.tools | ForEach-Object { [string]$_.name } | Sort-Object)
    if ($listResponse.StatusCode -ne 200 -or $toolNames.Count -eq 0) { throw 'Epic MCP tools/list failed.' }
    $state.tools_list = [ordered]@{ http_status=[int]$listResponse.StatusCode; tool_count=$toolNames.Count; tools=$toolNames }
    if ($toolNames -notcontains 'list_toolsets') { throw 'Epic MCP read-only list_toolsets tool missing.' }

    $callBody = @{ jsonrpc='2.0'; id=3; method='tools/call'; params=@{ name='list_toolsets'; arguments=@{} } } | ConvertTo-Json -Depth 7 -Compress
    $callResponse = Invoke-McpPost $callBody $sessionHeaders
    $callJson = Get-SseJson $callResponse.Content
    if ($callResponse.StatusCode -ne 200 -or $null -eq $callJson.result) { throw 'Epic MCP list_toolsets call failed.' }
    $contentText = @($callJson.result.content | Where-Object { $_.type -eq 'text' } | ForEach-Object { [string]$_.text }) -join "`n"
    $state.readonly_proof = [ordered]@{
        tool = 'list_toolsets'
        http_status = [int]$callResponse.StatusCode
        result_received = [bool]$callJson.result
        result_text_bytes = [Text.Encoding]::UTF8.GetByteCount($contentText)
        result_text_sha256 = ([BitConverter]::ToString(([Security.Cryptography.SHA256]::Create()).ComputeHash([Text.Encoding]::UTF8.GetBytes($contentText)))).Replace('-','')
        result_text = $contentText
    }

    $deleteResponse = Invoke-WebRequest -Uri $endpoint -Method Delete -UseBasicParsing -Headers $sessionHeaders -TimeoutSec 30
    $state.session_close_http_status = [int]$deleteResponse.StatusCode
    $state.home_map_sha256_after = (Get-FileHash -LiteralPath $homeMapFile -Algorithm SHA256).Hash
    if ($state.home_map_sha256_after -ne $expectedHome) { throw 'Home map changed during read-only MCP probe.' }
    Assert-ProtectedHashes
    $state.status = 'PASS_LIVE_EPIC_MCP_READONLY'
}
catch {
    $state.status = 'FAIL'
    $state.error = $_.Exception.Message
    throw
}
finally {
    if ($null -ne $proc -and -not $proc.HasExited) {
        $state.stopped_exact_process_ids = @(Stop-ExactProcessTree $proc.Id)
        $proc.WaitForExit()
    }
    Start-Sleep -Seconds 2
    $state.provider_ports_after = @(5353,8000,8765 | ForEach-Object {
        [ordered]@{ port=$_; listening=[bool](Get-NetTCPConnection -State Listen -LocalPort $_ -ErrorAction SilentlyContinue) }
    })
    $state.completed_utc = [DateTime]::UtcNow.ToString('o')
    $bytes = [Text.UTF8Encoding]::new($false).GetBytes(($state | ConvertTo-Json -Depth 12) + "`n")
    $stream = [IO.File]::Open($resultPath, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
    try { $stream.Write($bytes, 0, $bytes.Length); $stream.Flush($true) } finally { $stream.Dispose() }
}
