param(
    [ValidatePattern('^[A-Za-z0-9][A-Za-z0-9._-]{0,95}$')]
    [string]$CaptureId = 'R15_RealGPU_Orbit_EpicMCP_R01'
)

$ErrorActionPreference = 'Stop'

$projectRoot = 'D:\RedMMOTitanWindowsData\Projects\RedMMO'
$projectFile = Join-Path $projectRoot 'RedMMO.uproject'
$homeMapPackage = '/Game/RedMMO/Maps/RedMMO_PPG_HomeWorld'
$homeMapPath = Join-Path $projectRoot 'Content\RedMMO\Maps\RedMMO_PPG_HomeWorld.umap'
$editorPath = 'D:\UE_5.8\Engine\Binaries\Win64\UnrealEditor.exe'
$pluginDescriptor = 'D:\UE_5.8\Engine\Plugins\Experimental\ModelContextProtocol\ModelContextProtocol.uplugin'
$r15DiagnosticRoot = 'D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_PPG_ContinentBiome_R15_20260802_211912'
$finalizerResultPath = Join-Path $r15DiagnosticRoot 'finalize_r15_continent_biome_r05_result.json'
$freshVerifyPath = Join-Path $r15DiagnosticRoot 'verify_r15_fresh_reload_r02_result.json'
$freshVerifyGuardPath = Join-Path $r15DiagnosticRoot 'run_r15_verify_guard_r02_result.json'
$captureRoot = Join-Path $r15DiagnosticRoot $CaptureId
$logPath = Join-Path $captureRoot 'r15_real_gpu_epic_mcp_editor.log'
$pngPath = Join-Path $captureRoot 'RedMMO_R15_macro_continent_desert_ocean_orbit_1920x1080.png'
$resultPath = Join-Path $captureRoot 'r15_real_gpu_epic_mcp_capture_result.json'
$endpoint = 'http://127.0.0.1:8000/mcp'

$expectedHomeMapHash = '7BA68701F4B1A96777407FC8C349D90878037917CD3212878164B9A28BB37059'
$expectedProjectHash = '344BDA6BF5A99CC9C0902CB8C069A0EE2E67C3F15B80B2CDEA1D4B0B007AD105'
$expectedPluginVersion = '1.0'

$protected = [ordered]@{
    'D:\RedMMOTitan\Content\RedMMO\Maps\RedPlanetGen_50km_Test.umap' = 'DA5987012EEB8F550254F5FCF0F47F42B8F5E03428CF4881C83D8687537F6E7D'
    'D:\RedMMOTitan\Content\RedMMO\Maps\RedPlanetGen_50km_FusedPrototype.umap' = '4C84D7752C87854C70987ED9988C64C124C577FBE1DE3DEF3CC826F81B0B6284'
    'D:\RedMMOTitan\Content\RedMMO\Maps\Tests\RedPlanetGen_50km_FusedPrototype_Night_T03.umap' = '211429783F757F3CD8DE4A37B1E37B4A117125BF26EBFCBACF97CCFA9EFBE8D7'
    'D:\RedMMOTitanWindowsData\Rollback\BeforeCoastDatum_20260714\RedPlanetGen_50km_FusedPrototype.umap' = 'A9C42C0D1B0429DD1018F00F0D2AB8A18F66C07291611964EFF5F9710F3B0C6A'
}

# The planet center is (0, 0, -300000000) cm and the radius is 300000000 cm.
# This 2.4-radius, diagonal hemisphere view is an R15 review candidate; the
# continent/desert/ocean separation still requires human review of the PNG.
$cameraTransform = [ordered]@{
    location = [ordered]@{ x = 523800000.0; y = 349200000.0; z = 49200000.0 }
    rotation = [ordered]@{ pitch = -29.017; yaw = -146.310; roll = 0.0 }
    scale = [ordered]@{ x = 1.0; y = 1.0; z = 1.0 }
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
    if ($actual -ne $Expected) { throw "$Label hash drift: $actual" }
}

function Assert-ProtectedHashes {
    foreach ($entry in $protected.GetEnumerator()) {
        Assert-Hash $entry.Key $entry.Value 'Protected file'
    }
}

function Get-McpJson([string]$Content) {
    $line = ($Content -split "`r?`n" | Where-Object { $_ -like 'data: *' } | Select-Object -First 1)
    if ($line) { return ($line.Substring(6) | ConvertFrom-Json) }
    $trimmed = $Content.Trim()
    if ($trimmed.StartsWith('{')) { return ($trimmed | ConvertFrom-Json) }
    throw 'MCP response is neither SSE JSON nor application/json.'
}

function Invoke-McpPost([string]$Body, [hashtable]$Headers, [int]$TimeoutSec = 120) {
    return Invoke-WebRequest -Uri $endpoint -Method Post -UseBasicParsing -ContentType 'application/json' -Headers $Headers -Body $Body -TimeoutSec $TimeoutSec
}

function Invoke-EpicTool([int]$Id, [hashtable]$Headers, [string]$ToolName, [hashtable]$Arguments) {
    $body = @{
        jsonrpc = '2.0'
        id = $Id
        method = 'tools/call'
        params = @{
            name = 'call_tool'
            arguments = @{
                toolset_name = 'EditorToolset.EditorAppToolset'
                tool_name = $ToolName
                arguments = $Arguments
            }
        }
    } | ConvertTo-Json -Depth 14 -Compress
    $response = Invoke-McpPost $body $Headers 180
    $json = Get-McpJson $response.Content
    if ($response.StatusCode -ne 200 -or $null -ne $json.error -or [bool]$json.result.isError) {
        $detail = $json | ConvertTo-Json -Depth 20 -Compress
        throw "Epic MCP tool failed: $ToolName; HTTP=$($response.StatusCode); response=$detail"
    }
    $text = @($json.result.content | Where-Object { $_.type -eq 'text' } | ForEach-Object { [string]$_.text }) -join "`n"
    if (-not $text) { return [pscustomobject]@{} }
    return ($text | ConvertFrom-Json)
}

function Get-PngDimensions([byte[]]$Bytes) {
    $signature = [byte[]](137, 80, 78, 71, 13, 10, 26, 10)
    if ($Bytes.Length -lt 24) { throw 'Capture is too short to be a PNG.' }
    for ($index = 0; $index -lt $signature.Length; $index++) {
        if ($Bytes[$index] -ne $signature[$index]) { throw 'Capture does not have a PNG signature.' }
    }
    if ([Text.Encoding]::ASCII.GetString($Bytes, 12, 4) -ne 'IHDR') { throw 'Capture PNG has no IHDR header.' }
    $width = [uint32]($Bytes[16] * 16777216 + $Bytes[17] * 65536 + $Bytes[18] * 256 + $Bytes[19])
    $height = [uint32]($Bytes[20] * 16777216 + $Bytes[21] * 65536 + $Bytes[22] * 256 + $Bytes[23])
    return @([int]$width, [int]$height)
}

foreach ($requiredPath in @($projectFile, $homeMapPath, $editorPath, $pluginDescriptor, $finalizerResultPath, $freshVerifyPath, $freshVerifyGuardPath)) {
    if (-not (Test-Path -LiteralPath $requiredPath -PathType Leaf)) { throw "Required path missing: $requiredPath" }
}
if (Test-Path -LiteralPath $captureRoot) { throw "No-clobber capture directory exists: $captureRoot" }
Assert-Hash $homeMapPath $expectedHomeMapHash 'Post-R15 home map'
Assert-Hash $projectFile $expectedProjectHash 'Clean RedMMO project descriptor'
Assert-ProtectedHashes

$finalizer = Get-Content -Raw -LiteralPath $finalizerResultPath | ConvertFrom-Json
if ($finalizer.status -ne 'PASS_SERIALIZED_PENDING_FRESH_RELOAD_MAPCHECK_AND_REAL_GPU' -or $finalizer.home_map_sha256_after -ne $expectedHomeMapHash) {
    throw 'R15 finalizer gate is not the expected serialized pending-visual checkpoint.'
}
$freshVerify = Get-Content -Raw -LiteralPath $freshVerifyPath | ConvertFrom-Json
$freshVerifyGuard = Get-Content -Raw -LiteralPath $freshVerifyGuardPath | ConvertFrom-Json
if ($freshVerify.status -ne 'PASS_FRESH_RELOAD_MAPCHECK_ZERO_DIRTY_PENDING_REAL_GPU' -or
    $freshVerify.home_map_sha256 -ne $expectedHomeMapHash -or
    $freshVerify.map_check.errors -ne 0 -or $freshVerify.map_check.warnings -ne 0 -or
    $freshVerifyGuard.status -ne 'PASS_FRESH_RELOAD_MAPCHECK_ZERO_DIRTY_PENDING_REAL_GPU' -or
    $freshVerifyGuard.result_sha256 -ne (Get-FileHash -LiteralPath $freshVerifyPath -Algorithm SHA256).Hash) {
    throw 'Frozen R15 fresh-reload/MapCheck evidence gate failed.'
}
$plugin = Get-Content -Raw -LiteralPath $pluginDescriptor | ConvertFrom-Json
if ($plugin.VersionName -ne $expectedPluginVersion) { throw "Epic MCP version drift: $($plugin.VersionName)" }
$project = Get-Content -Raw -LiteralPath $projectFile | ConvertFrom-Json
$mcpEntry = @($project.Plugins | Where-Object { $_.Name -eq 'ModelContextProtocol' })
if ($mcpEntry.Count -ne 1 -or -not $mcpEntry[0].Enabled) { throw 'Official ModelContextProtocol is not enabled in clean RedMMO.' }

$unrealProcesses = @(Get-UnrealProcesses)
if ($unrealProcesses.Count -ne 0) { throw 'Another Unreal/build process is active.' }
if (@(Get-NetTCPConnection -State Listen -LocalPort 5353,8000,8765 -ErrorAction SilentlyContinue).Count -ne 0) {
    throw 'An AI/provider listener is already active.'
}
$freeRamAtLaunch = Get-FreeRamGiB
if ($freeRamAtLaunch -lt 12) { throw "RAM gate failed: $freeRamAtLaunch GiB" }

[void][IO.Directory]::CreateDirectory($captureRoot)
$report = [ordered]@{
    schema = 'redmmo.r15.real_gpu.epic_mcp_orbit_capture.v1'
    status = 'RUNNING'
    started_utc = [DateTime]::UtcNow.ToString('o')
    evidence_class = 'real_gpu_visual_pending_execution_and_human_review'
    project = $projectFile
    map = $homeMapPackage
    post_r15_home_map_sha256 = $expectedHomeMapHash
    endpoint = $endpoint
    requested_dimensions = @(1920, 1080)
    requested_camera_transform = $cameraTransform
    free_ram_gib_at_launch = $freeRamAtLaunch
    enabled_plugins = @('ModelContextProtocol', 'ToolsetRegistry', 'EditorToolset')
    disabled_plugins = @('Nwiro', 'NwiroIntegrationKit', 'UnrealAIIntegrationPlatform', 'VibeUE', 'MCPClientToolset')
    no_ui_automation = $true
    map_or_asset_save_requested = $false
}

$editorProcess = $null
$sessionHeaders = $null
$failure = $null
try {
    $arguments = @(
        $projectFile,
        $homeMapPackage,
        '-NoSplash',
        '-NoLiveCoding',
        '-NoSound',
        '-NoSourceControl',
        '-unattended',
        '-d3d12',
        '-RenderOffscreen',
        '-Windowed',
        '-ForceRes',
        '-ResX=1920',
        '-ResY=1080',
        '-EnablePlugins=ModelContextProtocol,ToolsetRegistry,EditorToolset',
        '-ModelContextProtocolStartServer',
        '-DisablePlugins=Nwiro,NwiroIntegrationKit,UnrealAIIntegrationPlatform,VibeUE,MCPClientToolset',
        "-abslog=$($logPath.Replace('\','/'))"
    )
    $editorProcess = Start-Process -FilePath $editorPath -ArgumentList $arguments -PassThru -WindowStyle Hidden
    $report.editor_pid = $editorProcess.Id

    $deadline = [DateTime]::UtcNow.AddMinutes(8)
    $minimumFreeRam = $freeRamAtLaunch
    $generationMatch = $null
    while ([DateTime]::UtcNow -lt $deadline) {
        Start-Sleep -Milliseconds 500
        $editorProcess.Refresh()
        if ($editorProcess.HasExited) { throw "Editor exited during startup: $($editorProcess.ExitCode)" }
        $currentFreeRam = Get-FreeRamGiB
        if ($currentFreeRam -lt $minimumFreeRam) { $minimumFreeRam = $currentFreeRam }
        if ($currentFreeRam -lt 8) { throw "RAM abort floor crossed: $currentFreeRam GiB" }
        $listener = @(Get-NetTCPConnection -State Listen -LocalPort 8000 -ErrorAction SilentlyContinue | Where-Object { $_.OwningProcess -eq $editorProcess.Id })
        if ($listener.Count -eq 1 -and (Test-Path -LiteralPath $logPath -PathType Leaf)) {
            $logText = Get-Content -Raw -LiteralPath $logPath
            $generationMatches = [regex]::Matches($logText, 'LogPPG: Planet generation completed in ([0-9.]+) ms with ([0-9]+) chunks\.')
            if ($generationMatches.Count -gt 0) {
                $generationMatch = $generationMatches[$generationMatches.Count - 1]
                break
            }
        }
    }
    if ($null -eq $generationMatch) { throw 'Fresh-process PPG generation and port 8000 did not both become ready.' }
    $logText = Get-Content -Raw -LiteralPath $logPath
    if ($logText -notmatch 'Map check complete: 0 Error\(s\), 0 Warning\(s\)') { throw 'Fresh-process MapCheck 0/0 marker missing.' }
    if ($logText -match 'PPG foliage output overflowed') { throw 'Fresh-process PPG foliage overflow detected.' }
    $report.minimum_free_ram_gib_during_start = $minimumFreeRam
    $report.generation = [ordered]@{
        time_ms = [double]$generationMatch.Groups[1].Value
        chunks = [int]$generationMatch.Groups[2].Value
        foliage_overflow_count = 0
    }

    $baseHeaders = @{ Accept = 'application/json, text/event-stream' }
    $initializeBody = @{
        jsonrpc = '2.0'
        id = 1
        method = 'initialize'
        params = @{
            protocolVersion = '2025-11-25'
            capabilities = @{}
            clientInfo = @{ name = 'redmmo-r15-real-gpu-capture'; version = '1.0.0' }
        }
    } | ConvertTo-Json -Depth 8 -Compress
    $initializeResponse = Invoke-McpPost $initializeBody $baseHeaders 60
    $initializeJson = Get-McpJson $initializeResponse.Content
    $sessionId = [string]$initializeResponse.Headers['Mcp-Session-Id']
    if ($initializeResponse.StatusCode -ne 200 -or -not $sessionId) { throw 'Epic MCP initialize failed.' }
    $sessionHeaders = @{
        Accept = 'application/json, text/event-stream'
        'Mcp-Session-Id' = $sessionId
        'MCP-Protocol-Version' = [string]$initializeJson.result.protocolVersion
    }
    $readyResponse = Invoke-McpPost ((@{ jsonrpc = '2.0'; method = 'notifications/initialized' } | ConvertTo-Json -Compress)) $sessionHeaders 60
    if ($readyResponse.StatusCode -notin 200,202) { throw 'Epic MCP initialized notification failed.' }

    $listResponse = Invoke-McpPost ((@{ jsonrpc = '2.0'; id = 2; method = 'tools/list'; params = @{} } | ConvertTo-Json -Depth 4 -Compress)) $sessionHeaders 60
    $listJson = Get-McpJson $listResponse.Content
    $toolNames = @($listJson.result.tools | ForEach-Object { [string]$_.name })
    if ($listResponse.StatusCode -ne 200 -or $toolNames -notcontains 'call_tool') { throw 'Epic MCP call_tool meta-tool is unavailable.' }
    $report.mcp = [ordered]@{
        negotiated_protocol = [string]$initializeJson.result.protocolVersion
        server_name = [string]$initializeJson.result.serverInfo.name
        server_version = [string]$initializeJson.result.serverInfo.version
        tools = $toolNames
    }

    Start-Sleep -Seconds 5
    $preCameraGenerationCount = ([regex]::Matches((Get-Content -Raw -LiteralPath $logPath), 'LogPPG: Planet generation completed in ([0-9.]+) ms with ([0-9]+) chunks\.')).Count
    [void](Invoke-EpicTool 10 $sessionHeaders 'SetCameraTransform' @{ transform = $cameraTransform })
    $postCameraGenerationDetected = $false
    $cameraSettleDeadline = [DateTime]::UtcNow.AddSeconds(12)
    while ([DateTime]::UtcNow -lt $cameraSettleDeadline) {
        Start-Sleep -Milliseconds 500
        $cameraLogText = Get-Content -Raw -LiteralPath $logPath
        $cameraGenerationCount = ([regex]::Matches($cameraLogText, 'LogPPG: Planet generation completed in ([0-9.]+) ms with ([0-9]+) chunks\.')).Count
        if ($cameraGenerationCount -gt $preCameraGenerationCount) {
            $postCameraGenerationDetected = $true
            break
        }
    }
    $actualCamera = Invoke-EpicTool 11 $sessionHeaders 'GetCameraTransform' @{}
    $capture = Invoke-EpicTool 12 $sessionHeaders 'CaptureViewport' @{ captureTransform = $cameraTransform; annotations = $null; bShowUI = $false }
    $captureValue = $capture.returnValue
    if ($null -eq $captureValue -or $captureValue.image.mimeType -ne 'image/png' -or -not $captureValue.image.data) {
        throw 'Epic MCP CaptureViewport returned no PNG.'
    }
    $base64 = [string]$captureValue.image.data
    if ($base64.StartsWith('data:image/png;base64,')) { $base64 = $base64.Substring(22) }
    $pngBytes = [Convert]::FromBase64String($base64)
    $stream = [IO.File]::Open($pngPath, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
    try { $stream.Write($pngBytes, 0, $pngBytes.Length); $stream.Flush($true) } finally { $stream.Dispose() }
    $dimensions = @(Get-PngDimensions $pngBytes)
    if ($dimensions[0] -ne 1920 -or $dimensions[1] -ne 1080) {
        throw "CaptureViewport returned $($dimensions[0])x$($dimensions[1]), expected 1920x1080."
    }

    Assert-Hash $homeMapPath $expectedHomeMapHash 'Post-capture home map'
    Assert-ProtectedHashes
    if (@(Get-NetTCPConnection -State Listen -LocalPort 5353,8765 -ErrorAction SilentlyContinue).Count -ne 0) {
        throw 'A disabled provider listener appeared during capture.'
    }
    $report.capture = [ordered]@{
        path = $pngPath
        sha256 = (Get-FileHash -LiteralPath $pngPath -Algorithm SHA256).Hash
        bytes = (Get-Item -LiteralPath $pngPath).Length
        dimensions = $dimensions
        camera_from_get = $actualCamera.returnValue
        camera_from_capture = [ordered]@{
            location = $captureValue.cameraLocation
            rotation = $captureValue.cameraRotation
            fov = $captureValue.cameraFOV
        }
        official_tools = @('EditorToolset.EditorAppToolset.SetCameraTransform', 'EditorToolset.EditorAppToolset.GetCameraTransform', 'EditorToolset.EditorAppToolset.CaptureViewport')
        post_camera_generation_detected = $postCameraGenerationDetected
        b_show_ui = $false
    }
    $report.status = 'PASS_REAL_GPU_CAPTURE_PENDING_HUMAN_VISUAL_REVIEW'
}
catch {
    $failure = $_
    $report.status = 'FAIL'
    $report.error = $_.Exception.Message
}
finally {
    if ($null -ne $sessionHeaders) {
        try {
            $deleteResponse = Invoke-WebRequest -Uri $endpoint -Method Delete -UseBasicParsing -Headers $sessionHeaders -TimeoutSec 30
            $report.mcp_session_close_http_status = [int]$deleteResponse.StatusCode
        }
        catch {
            $report.mcp_session_close_error = $_.Exception.Message
        }
    }
    if ($null -ne $editorProcess) {
        try {
            $editorProcess.Refresh()
            if (-not $editorProcess.HasExited) {
                $report.stopped_exact_process_ids = @(Stop-ExactProcessTree $editorProcess.Id)
                if (-not $editorProcess.WaitForExit(30000)) { throw 'Exact launched editor process tree did not exit within 30 seconds.' }
                $report.stopped_exact_editor_pid = $editorProcess.Id
            }
        }
        catch {
            $report.exact_pid_stop_error = $_.Exception.Message
        }
    }
    Start-Sleep -Seconds 2
    $processSettleDeadline = [DateTime]::UtcNow.AddSeconds(10)
    while ([DateTime]::UtcNow -lt $processSettleDeadline -and @(Get-UnrealProcesses).Count -ne 0) {
        Start-Sleep -Milliseconds 500
    }
    $report.provider_ports_after = @(5353,8000,8765 | ForEach-Object {
        [ordered]@{ port = $_; listening = [bool](Get-NetTCPConnection -State Listen -LocalPort $_ -ErrorAction SilentlyContinue) }
    })
    $report.home_map_sha256_after = (Get-FileHash -LiteralPath $homeMapPath -Algorithm SHA256).Hash
    $report.unreal_process_count_after = @(Get-UnrealProcesses).Count
    if ($report.status -like 'PASS*' -and ($report.exact_pid_stop_error -or $report.unreal_process_count_after -ne 0 -or @($report.provider_ports_after | Where-Object { $_.listening }).Count -ne 0 -or $report.home_map_sha256_after -ne $expectedHomeMapHash)) {
        $report.status = 'FAIL_POST_CAPTURE_CLEANUP_OR_HASH_GATE'
        if ($null -eq $failure) { $failure = [InvalidOperationException]::new('Post-capture exact-PID cleanup, provider-port, or home-hash gate failed.') }
    }
    $report.completed_utc = [DateTime]::UtcNow.ToString('o')
    $resultBytes = [Text.UTF8Encoding]::new($false).GetBytes(($report | ConvertTo-Json -Depth 20) + "`n")
    $resultStream = [IO.File]::Open($resultPath, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
    try { $resultStream.Write($resultBytes, 0, $resultBytes.Length); $resultStream.Flush($true) } finally { $resultStream.Dispose() }
}

$report | ConvertTo-Json -Depth 12
if ($null -ne $failure) { throw $failure }
