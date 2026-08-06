$ErrorActionPreference = 'Stop'
$diag = 'D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_PPG_ContinentBiome_R15_20260802_211912'
$editorState = Join-Path $diag 'r15_epic_mcp_editor_start.json'
$resultPath = Join-Path $diag 'get_redmmo_epic_mcp_programmatic_environment_r15_r02_result.json'
$endpoint = 'http://127.0.0.1:8000/mcp'

function Get-McpJson([string]$Content) {
    $line = ($Content -split "`r?`n" | Where-Object { $_ -like 'data: *' } | Select-Object -First 1)
    if ($line) { return ($line.Substring(6) | ConvertFrom-Json) }
    return ($Content.Trim() | ConvertFrom-Json)
}
function Post([string]$Body,[hashtable]$Headers) {
    Invoke-WebRequest -Uri $endpoint -Method Post -UseBasicParsing -ContentType 'application/json' -Headers $Headers -Body $Body -TimeoutSec 90
}
if (Test-Path -LiteralPath $resultPath) { throw "No-clobber result exists: $resultPath" }
$state = Get-Content -LiteralPath $editorState -Raw | ConvertFrom-Json
$pidValue = [int]$state.editor_pid
if (-not (Get-Process -Id $pidValue -ErrorAction SilentlyContinue)) { throw 'Recorded editor is not running.' }
if (@(Get-NetTCPConnection -State Listen -LocalPort 8000 -ErrorAction SilentlyContinue | Where-Object {$_.OwningProcess -eq $pidValue}).Count -ne 1) { throw 'Recorded editor does not own MCP listener.' }
$init = Post ((@{jsonrpc='2.0';id=1;method='initialize';params=@{protocolVersion='2025-11-25';capabilities=@{};clientInfo=@{name='redmmo-r15-programmatic-env';version='1.0.0'}}}|ConvertTo-Json -Depth 8 -Compress)) @{Accept='application/json, text/event-stream'}
$initJson=Get-McpJson $init.Content
$sid=[string]$init.Headers['Mcp-Session-Id']
$headers=@{Accept='application/json, text/event-stream';'Mcp-Session-Id'=$sid;'MCP-Protocol-Version'=[string]$initJson.result.protocolVersion}
[void](Post ((@{jsonrpc='2.0';method='notifications/initialized'}|ConvertTo-Json -Compress)) $headers)
$call=Post ((@{jsonrpc='2.0';id=2;method='tools/call';params=@{name='call_tool';arguments=@{toolset_name='editor_toolset.toolsets.programmatic.ProgrammaticToolset';tool_name='get_execution_environment';arguments=@{}}}}|ConvertTo-Json -Depth 10 -Compress)) $headers
$callJson=Get-McpJson $call.Content
$text=@($callJson.result.content|Where-Object{$_.type -eq 'text'}|ForEach-Object{[string]$_.text}) -join "`n"
if (-not $text -or $callJson.result.isError) { throw 'Programmatic environment call failed.' }
$delete=Invoke-WebRequest -Uri $endpoint -Method Delete -UseBasicParsing -Headers $headers -TimeoutSec 30
$payload=[ordered]@{schema='redmmo.r15.epic_mcp.programmatic_environment.v1';status='PASS';captured_utc=[DateTime]::UtcNow.ToString('o');editor_pid=$pidValue;http_status=[int]$call.StatusCode;result=$text;session_close_http_status=[int]$delete.StatusCode;mutation_count=0}
$bytes=[Text.UTF8Encoding]::new($false).GetBytes(($payload|ConvertTo-Json -Depth 12)+"`n")
$stream=[IO.File]::Open($resultPath,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
try{$stream.Write($bytes,0,$bytes.Length);$stream.Flush($true)}finally{$stream.Dispose()}
$payload|ConvertTo-Json -Depth 5
