$ErrorActionPreference = 'Stop'
$diag='D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_PPG_ContinentBiome_R15_20260802_211912'
$editorState=Join-Path $diag 'r15_epic_mcp_editor_start.json'
$resultPath=Join-Path $diag 'inspect_r15_ppg_properties_via_epic_mcp_r03_result.json'
$endpoint='http://127.0.0.1:8000/mcp'

function Parse([string]$c){$l=($c -split "`r?`n"|Where-Object{$_ -like 'data: *'}|Select-Object -First 1);if($l){$l.Substring(6)|ConvertFrom-Json}else{$c.Trim()|ConvertFrom-Json}}
function Post([string]$b,[hashtable]$h){Invoke-WebRequest -Uri $endpoint -Method Post -UseBasicParsing -ContentType 'application/json' -Headers $h -Body $b -TimeoutSec 120}
if(Test-Path -LiteralPath $resultPath){throw "No-clobber result exists: $resultPath"}
$state=Get-Content -LiteralPath $editorState -Raw|ConvertFrom-Json;$pidValue=[int]$state.editor_pid
if(-not(Get-Process -Id $pidValue -ErrorAction SilentlyContinue)){throw 'Recorded editor is not running.'}
if(@(Get-NetTCPConnection -State Listen -LocalPort 8000 -ErrorAction SilentlyContinue|Where-Object{$_.OwningProcess -eq $pidValue}).Count -ne 1){throw 'Recorded editor does not own MCP listener.'}

$init=Post ((@{jsonrpc='2.0';id=1;method='initialize';params=@{protocolVersion='2025-11-25';capabilities=@{};clientInfo=@{name='redmmo-r15-property-inspect';version='1.0.0'}}}|ConvertTo-Json -Depth 8 -Compress)) @{Accept='application/json, text/event-stream'}
$ij=Parse $init.Content;$sid=[string]$init.Headers['Mcp-Session-Id'];$h=@{Accept='application/json, text/event-stream';'Mcp-Session-Id'=$sid;'MCP-Protocol-Version'=[string]$ij.result.protocolVersion}
[void](Post ((@{jsonrpc='2.0';method='notifications/initialized'}|ConvertTo-Json -Compress)) $h)

$program=@'
import json

def load(path):
    return execute_tool("editor_toolset.toolsets.asset.AssetTools.load_asset", json.dumps({"asset_path": path}))["returnValue"]

def expressions(asset):
    return execute_tool("editor_toolset.toolsets.material.MaterialTools.get_expressions", json.dumps({"material_or_function": asset}))["returnValue"]

def props(obj, names):
    value = execute_tool("editor_toolset.toolsets.object.ObjectTools.get_properties", json.dumps({"instance": obj, "properties": names}))["returnValue"]
    return json.loads(value)

def list_props(obj):
    value = execute_tool("editor_toolset.toolsets.object.ObjectTools.list_properties", json.dumps({"instance": obj}))["returnValue"]
    return json.loads(value)

def inspect_nodes(path, sample_names, collect_textures=False, collect_noises=False):
    asset = load(path)
    nodes = expressions(asset)
    by_name = {item["refPath"].rsplit(":", 1)[-1]: item for item in nodes}
    result = {"asset": asset, "expression_count": len(nodes), "property_lists": {}}
    for name in sample_names:
        if name not in by_name:
            raise RuntimeError("Missing expression " + name + " in " + path)
        result["property_lists"][name] = list_props(by_name[name])
    if collect_textures:
        texture_nodes = []
        for item in nodes:
            names = list_props(item)
            texture_names = [name for name in names if name.lower() == "texture"]
            if not texture_names:
                continue
            value = props(item, texture_names)
            texture_nodes.append({"refPath": item["refPath"], "properties": names, "texture_values": value})
        result["texture_nodes"] = texture_nodes
    if collect_noises:
        noise_nodes = []
        for item in nodes:
            names = list_props(item)
            if "baseFrequency" not in names:
                continue
            values = props(item, ["noiseType", "baseFrequency", "octaves", "desc", "materialExpressionEditorX", "materialExpressionEditorY"])
            noise_nodes.append({"refPath": item["refPath"], "values": values})
        result["noise_nodes"] = noise_nodes
    return result

def run():
    generation = inspect_nodes(
        "/Game/RedMMO/World/PPG/HomeWorld/StylizedBinding/R10N/Materials/M_PPG_Generation_SmoothSpawnGrass_R10N",
        ["MaterialExpressionScalarParameter_6", "MaterialExpressionScalarParameter_12", "MaterialExpressionPlanetElevationOutput_0"],
    )
    mask = inspect_nodes(
        "/PPG/Example/Assets/M_PPG_ExampleBiomeMask",
        ["MaterialExpressionPlanetBiomeMaskOutput_0", "MaterialExpressionPlanetNoise_4"],
        False,
        True,
    )
    surface = inspect_nodes(
        "/Game/RedMMO/World/PPG/HomeWorld/StylizedBinding/R10L/Materials/M_PPG_Home_PaintedLeafGround_R10L",
        [],
        False,
    )
    return {"generation": generation, "mask": mask, "surface": surface}
'@
$body=@{jsonrpc='2.0';id=2;method='tools/call';params=@{name='call_tool';arguments=@{toolset_name='editor_toolset.toolsets.programmatic.ProgrammaticToolset';tool_name='execute_tool_script';arguments=@{script=$program}}}}|ConvertTo-Json -Depth 12 -Compress
$response=Post $body $h;$json=Parse $response.Content;$text=@($json.result.content|Where-Object{$_.type -eq 'text'}|ForEach-Object{[string]$_.text}) -join "`n"
if($json.result.isError -or -not $text){throw "MCP property inspection failed: $text"}
$delete=Invoke-WebRequest -Uri $endpoint -Method Delete -UseBasicParsing -Headers $h -TimeoutSec 30
$payload=[ordered]@{schema='redmmo.r15.epic_mcp.ppg_property_inspection.v1';status='PASS';captured_utc=[DateTime]::UtcNow.ToString('o');editor_pid=$pidValue;http_status=[int]$response.StatusCode;inspection=($text|ConvertFrom-Json);session_close_http_status=[int]$delete.StatusCode;mutation_count=0}
$bytes=[Text.UTF8Encoding]::new($false).GetBytes(($payload|ConvertTo-Json -Depth 30)+"`n");$stream=[IO.File]::Open($resultPath,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None);try{$stream.Write($bytes,0,$bytes.Length);$stream.Flush($true)}finally{$stream.Dispose()}
$payload|ConvertTo-Json -Depth 8
