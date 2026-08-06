$ErrorActionPreference = 'Stop'

$diag = 'D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_PPG_ContinentBiome_R15_20260802_211912'
$editorState = Join-Path $diag 'r15_epic_mcp_editor_start.json'
$resultPath = Join-Path $diag 'describe_redmmo_epic_mcp_toolsets_r15_result.json'
$endpoint = 'http://127.0.0.1:8000/mcp'

function Get-McpJson([string]$Content) {
    $line = ($Content -split "`r?`n" | Where-Object { $_ -like 'data: *' } | Select-Object -First 1)
    if ($line) { return ($line.Substring(6) | ConvertFrom-Json) }
    $trimmed = $Content.Trim()
    if ($trimmed.StartsWith('{')) { return ($trimmed | ConvertFrom-Json) }
    throw 'MCP response is neither SSE JSON nor application/json.'
}

function Invoke-Post([string]$Body, [hashtable]$Headers) {
    return Invoke-WebRequest -Uri $endpoint -Method Post -UseBasicParsing -ContentType 'application/json' -Headers $Headers -Body $Body -TimeoutSec 90
}

if (Test-Path -LiteralPath $resultPath) { throw "No-clobber result exists: $resultPath" }
$state = Get-Content -LiteralPath $editorState -Raw | ConvertFrom-Json
$pidValue = [int]$state.editor_pid
$process = Get-Process -Id $pidValue -ErrorAction Stop
$listener = @(Get-NetTCPConnection -State Listen -LocalPort 8000 -ErrorAction SilentlyContinue | Where-Object { $_.OwningProcess -eq $pidValue })
if ($listener.Count -ne 1) { throw 'Expected Epic MCP listener is not owned by the recorded editor.' }

$baseHeaders = @{ Accept = 'application/json, text/event-stream' }
$initBody = @{ jsonrpc='2.0'; id=1; method='initialize'; params=@{ protocolVersion='2025-11-25'; capabilities=@{}; clientInfo=@{ name='redmmo-r15-toolset-describe'; version='1.0.0' } } } | ConvertTo-Json -Depth 8 -Compress
$initResponse = Invoke-Post $initBody $baseHeaders
$initJson = Get-McpJson $initResponse.Content
$sessionId = [string]$initResponse.Headers['Mcp-Session-Id']
if (-not $sessionId) { throw 'No MCP session ID.' }
$headers = @{ Accept='application/json, text/event-stream'; 'Mcp-Session-Id'=$sessionId; 'MCP-Protocol-Version'=[string]$initJson.result.protocolVersion }
$ready = Invoke-Post ((@{jsonrpc='2.0';method='notifications/initialized'} | ConvertTo-Json -Compress)) $headers
if ($ready.StatusCode -notin 200,202) { throw 'MCP initialized notification failed.' }

$listResponse = Invoke-Post ((@{jsonrpc='2.0';id=2;method='tools/list';params=@{}} | ConvertTo-Json -Depth 4 -Compress)) $headers
$listJson = Get-McpJson $listResponse.Content
$describeSchema = @($listJson.result.tools | Where-Object { $_.name -eq 'describe_toolset' })[0].inputSchema
if (-not $describeSchema) { throw 'describe_toolset schema missing.' }

$targets = @(
    'EditorToolset.EditorAppToolset',
    'editor_toolset.toolsets.asset.AssetTools',
    'editor_toolset.toolsets.material.MaterialTools',
    'editor_toolset.toolsets.material_instance.MaterialInstanceTools',
    'editor_toolset.toolsets.object.ObjectTools',
    'editor_toolset.toolsets.data_asset.DataAssetTools',
    'editor_toolset.toolsets.scene.SceneTools',
    'editor_toolset.toolsets.programmatic.ProgrammaticToolset'
)
$descriptions = [ordered]@{}
$requestId = 10
foreach ($target in $targets) {
    $body = @{ jsonrpc='2.0'; id=$requestId; method='tools/call'; params=@{ name='describe_toolset'; arguments=@{ toolset_name=$target } } } | ConvertTo-Json -Depth 8 -Compress
    $response = Invoke-Post $body $headers
    $json = Get-McpJson $response.Content
    $text = @($json.result.content | Where-Object { $_.type -eq 'text' } | ForEach-Object { [string]$_.text }) -join "`n"
    $descriptions[$target] = [ordered]@{
        http_status = [int]$response.StatusCode
        is_error = [bool]$json.result.isError
        text = $text
    }
    $requestId++
}
$delete = Invoke-WebRequest -Uri $endpoint -Method Delete -UseBasicParsing -Headers $headers -TimeoutSec 30

$payload = [ordered]@{
    schema = 'redmmo.r15.epic_mcp.toolset_descriptions.v1'
    status = 'PASS'
    captured_utc = [DateTime]::UtcNow.ToString('o')
    editor_pid = $pidValue
    tools_list_http_status = [int]$listResponse.StatusCode
    describe_toolset_input_schema = $describeSchema
    descriptions = $descriptions
    session_close_http_status = [int]$delete.StatusCode
    mutation_count = 0
}
$bytes = [Text.UTF8Encoding]::new($false).GetBytes(($payload | ConvertTo-Json -Depth 20) + "`n")
$stream = [IO.File]::Open($resultPath, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
try { $stream.Write($bytes,0,$bytes.Length); $stream.Flush($true) } finally { $stream.Dispose() }
$payload | ConvertTo-Json -Depth 6
