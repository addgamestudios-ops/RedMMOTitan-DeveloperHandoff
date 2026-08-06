$ErrorActionPreference = 'Stop'

$projectRoot='D:\RedMMOTitanWindowsData\Projects\RedMMO'
$diag='D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_PPG_ContinentBiome_R15_20260802_211912'
$editorState=Join-Path $diag 'r15_epic_mcp_editor_start.json'
$resultPath=Join-Path $diag 'stage_r15_continent_biome_assets_via_epic_mcp_result.json'
$checkpoint='D:\RedMMOTitanWindowsData\Rollback\RedMMO_PPG_ContinentBiome_R15_20260802_211912_A01\pre_r15_manifest.json'
$homeMapFile=Join-Path $projectRoot 'Content\RedMMO\Maps\RedMMO_PPG_HomeWorld.umap'
$projectFile=Join-Path $projectRoot 'RedMMO.uproject'
$endpoint='http://127.0.0.1:8000/mcp'
$expectedHome='C9BE88085575E75E1790CB9306D564EB100F5ED2E75E012C1FD09EA110FDDFE0'
$expectedProject='344BDA6BF5A99CC9C0902CB8C069A0EE2E67C3F15B80B2CDEA1D4B0B007AD105'
$expectedCheckpoint='6CB41CE2DA4E78CAE1A83028CDA98E6DA6E09B461271F06FD3B2CA3A6CEADE20'

$protected=[ordered]@{
 'D:\RedMMOTitan\Content\RedMMO\Maps\RedPlanetGen_50km_Test.umap'='DA5987012EEB8F550254F5FCF0F47F42B8F5E03428CF4881C83D8687537F6E7D'
 'D:\RedMMOTitan\Content\RedMMO\Maps\RedPlanetGen_50km_FusedPrototype.umap'='4C84D7752C87854C70987ED9988C64C124C577FBE1DE3DEF3CC826F81B0B6284'
 'D:\RedMMOTitan\Content\RedMMO\Maps\Tests\RedPlanetGen_50km_FusedPrototype_Night_T03.umap'='211429783F757F3CD8DE4A37B1E37B4A117125BF26EBFCBACF97CCFA9EFBE8D7'
 'D:\RedMMOTitanWindowsData\Rollback\BeforeCoastDatum_20260714\RedPlanetGen_50km_FusedPrototype.umap'='A9C42C0D1B0429DD1018F00F0D2AB8A18F66C07291611964EFF5F9710F3B0C6A'
}

function Parse([string]$c){$l=($c -split "`r?`n"|Where-Object{$_ -like 'data: *'}|Select-Object -First 1);if($l){$l.Substring(6)|ConvertFrom-Json}else{$c.Trim()|ConvertFrom-Json}}
function Post([string]$b,[hashtable]$h){Invoke-WebRequest -Uri $endpoint -Method Post -UseBasicParsing -ContentType 'application/json' -Headers $h -Body $b -TimeoutSec 240}
function Assert-Protected{foreach($e in $protected.GetEnumerator()){if(-not(Test-Path -LiteralPath $e.Key -PathType Leaf)){throw "Protected file missing: $($e.Key)"};if((Get-FileHash -LiteralPath $e.Key -Algorithm SHA256).Hash -ne $e.Value){throw "Protected hash drift: $($e.Key)"}}}

if(Test-Path -LiteralPath $resultPath){throw "No-clobber result exists: $resultPath"}
if((Get-FileHash -LiteralPath $homeMapFile -Algorithm SHA256).Hash -ne $expectedHome){throw 'Home map hash drift before MCP stage.'}
if((Get-FileHash -LiteralPath $projectFile -Algorithm SHA256).Hash -ne $expectedProject){throw 'Project descriptor drift before MCP stage.'}
if((Get-FileHash -LiteralPath $checkpoint -Algorithm SHA256).Hash -ne $expectedCheckpoint){throw 'R15 checkpoint manifest drift.'}
Assert-Protected
$state=Get-Content -LiteralPath $editorState -Raw|ConvertFrom-Json;$pidValue=[int]$state.editor_pid
if(-not(Get-Process -Id $pidValue -ErrorAction SilentlyContinue)){throw 'Recorded editor is not running.'}
if(@(Get-NetTCPConnection -State Listen -LocalPort 8000 -ErrorAction SilentlyContinue|Where-Object{$_.OwningProcess -eq $pidValue}).Count -ne 1){throw 'Recorded editor does not own MCP listener.'}
if(@(Get-NetTCPConnection -State Listen -LocalPort 5353,8765 -ErrorAction SilentlyContinue).Count -ne 0){throw 'NWIRO or UAIP listener active.'}

$init=Post ((@{jsonrpc='2.0';id=1;method='initialize';params=@{protocolVersion='2025-11-25';capabilities=@{};clientInfo=@{name='redmmo-r15-mcp-stage';version='1.0.0'}}}|ConvertTo-Json -Depth 8 -Compress)) @{Accept='application/json, text/event-stream'}
$ij=Parse $init.Content;$sid=[string]$init.Headers['Mcp-Session-Id'];$h=@{Accept='application/json, text/event-stream';'Mcp-Session-Id'=$sid;'MCP-Protocol-Version'=[string]$ij.result.protocolVersion}
[void](Post ((@{jsonrpc='2.0';method='notifications/initialized'}|ConvertTo-Json -Compress)) $h)

$program=@'
import json

SOURCE_PLANET = "/Game/RedMMO/World/PPG/HomeWorld/StylizedBinding/R10O/DA_PPG_HomeWorld_StylizedBinding_R10O"
SOURCE_GENERATION = "/Game/RedMMO/World/PPG/HomeWorld/StylizedBinding/R10N/Materials/M_PPG_Generation_SmoothSpawnGrass_R10N"
SOURCE_MASK = "/PPG/Example/Assets/M_PPG_ExampleBiomeMask"
SOURCE_SURFACE_PARENT = "/Game/RedMMO/World/PPG/HomeWorld/StylizedBinding/R10L/Materials/M_PPG_Home_PaintedLeafGround_R10L"
SOURCE_SURFACE_MI = "/Game/RedMMO/World/PPG/HomeWorld/StylizedBinding/R10N/Materials/MI_PPG_Home_PaintedLeafGround_Scaled_R10N"

ROOT = "/Game/RedMMO/World/PPG/HomeWorld/ContinentBiome/R15"
TARGET_PLANET = ROOT + "/DA_PPG_HomeWorld_ContinentBiome_R15"
TARGET_GENERATION = ROOT + "/Materials/M_PPG_Generation_Continents_R15"
TARGET_MASK = ROOT + "/Materials/M_PPG_BiomeMask_Continents_R15"
TARGET_SURFACE_PARENT = ROOT + "/Materials/M_PPG_Home_BiomeSurface_R15"
TARGET_SURFACE_MI = ROOT + "/Materials/MI_PPG_Home_BiomeSurface_R15"

TARGETS = [TARGET_PLANET, TARGET_GENERATION, TARGET_MASK, TARGET_SURFACE_PARENT, TARGET_SURFACE_MI]

def tool(name, args):
    return execute_tool(name, json.dumps(args))

def exists(path):
    return bool(tool("editor_toolset.toolsets.asset.AssetTools.exists", {"path": path})["returnValue"])

def duplicate(path, new_path):
    if not tool("editor_toolset.toolsets.asset.AssetTools.duplicate", {"path": path, "new_path": new_path})["returnValue"]:
        raise RuntimeError("Duplicate failed: " + path + " -> " + new_path)

def delete(path):
    return tool("editor_toolset.toolsets.asset.AssetTools.delete", {"path": path})["returnValue"]

def load(path):
    return tool("editor_toolset.toolsets.asset.AssetTools.load_asset", {"asset_path": path})["returnValue"]

def expressions(asset):
    return tool("editor_toolset.toolsets.material.MaterialTools.get_expressions", {"material_or_function": asset})["returnValue"]

def node_map(asset):
    return {item["refPath"].rsplit(":", 1)[-1]: item for item in expressions(asset)}

def get_props(obj, names):
    text = tool("editor_toolset.toolsets.object.ObjectTools.get_properties", {"instance": obj, "properties": names})["returnValue"]
    return json.loads(text)

def set_props(obj, values):
    if not tool("editor_toolset.toolsets.object.ObjectTools.set_properties", {"instance": obj, "values": json.dumps(values)})["returnValue"]:
        raise RuntimeError("set_properties failed for " + obj["refPath"])

def recompile(asset):
    tool("editor_toolset.toolsets.material.MaterialTools.recompile", {"material_or_function": asset})

def save(paths):
    if not tool("editor_toolset.toolsets.asset.AssetTools.save_assets", {"asset_paths": paths})["returnValue"]:
        raise RuntimeError("save_assets failed")

def same_number(actual, expected, name):
    if abs(float(actual) - float(expected)) > 0.0001:
        raise RuntimeError(name + " drift: " + str(actual))

def run():
    for path in [SOURCE_PLANET, SOURCE_GENERATION, SOURCE_MASK, SOURCE_SURFACE_PARENT, SOURCE_SURFACE_MI,
                 "/Game/SoStylized/Environment/Landscape/Textures/T_DesertSand_BC",
                 "/Game/SoStylized/Environment/Landscape/Textures/T_DesertSand_N",
                 "/Game/StylizedRocksPack_01/DetailTextures/T_Rock_Painterly_01_BC",
                 "/Game/StylizedRocksPack_01/DetailTextures/T_Rock_SurfaceDirectional_N"]:
        if not exists(path):
            raise RuntimeError("Required source missing: " + path)
    for path in TARGETS:
        if exists(path):
            raise RuntimeError("No-clobber target exists: " + path)

    source_planet = load(SOURCE_PLANET)
    planet_before = get_props(source_planet, ["generationSeed", "planetRadius", "noiseHeight", "generationMaterial", "biomeMaskMaterial", "planetMaterial", "bGenerateWater", "waterMaterial"])
    if int(planet_before["generationSeed"]) != 1337:
        raise RuntimeError("Seed drift")
    same_number(planet_before["planetRadius"], 300000000.0, "planetRadius")
    same_number(planet_before["noiseHeight"], 600000.0, "noiseHeight")
    if not planet_before["bGenerateWater"]:
        raise RuntimeError("Native spherical water disabled")

    created = []
    try:
        for source, target in [
            (SOURCE_GENERATION, TARGET_GENERATION),
            (SOURCE_MASK, TARGET_MASK),
            (SOURCE_SURFACE_PARENT, TARGET_SURFACE_PARENT),
            (SOURCE_SURFACE_MI, TARGET_SURFACE_MI),
            (SOURCE_PLANET, TARGET_PLANET),
        ]:
            duplicate(source, target)
            created.append(target)

        generation = load(TARGET_GENERATION)
        mask = load(TARGET_MASK)
        surface_parent = load(TARGET_SURFACE_PARENT)
        surface_mi = load(TARGET_SURFACE_MI)
        planet = load(TARGET_PLANET)

        gen_nodes = node_map(generation)
        expected_scalars = {
            "MaterialExpressionScalarParameter_6": ("MountainDetails", 100.0, 180.0),
            "MaterialExpressionScalarParameter_12": ("MountainsHeight", 1.35, 0.85),
            "MaterialExpressionScalarParameter_2": ("HillsDetails", 200.0, 320.0),
            "MaterialExpressionScalarParameter_5": ("HIllsHeight", 5.0, 2.25),
        }
        scalar_changes = {}
        for node_name, (parameter, before_expected, after) in expected_scalars.items():
            if node_name not in gen_nodes:
                raise RuntimeError("Missing generation node " + node_name)
            before = get_props(gen_nodes[node_name], ["parameterName", "defaultValue"])
            if before["parameterName"] != parameter:
                raise RuntimeError("Parameter identity drift: " + node_name)
            same_number(before["defaultValue"], before_expected, parameter)
            set_props(gen_nodes[node_name], {"defaultValue": after})
            scalar_changes[parameter] = {"before": before_expected, "after": after}
        elevation = gen_nodes.get("MaterialExpressionPlanetElevationOutput_0")
        if not elevation:
            raise RuntimeError("Missing elevation output")
        warp_before = get_props(elevation, ["biomeVoronoiWarpStrength", "biomeVoronoiWarpScale"])
        same_number(warp_before["biomeVoronoiWarpStrength"], 1.5, "biomeVoronoiWarpStrength")
        same_number(warp_before["biomeVoronoiWarpScale"], 30.0, "biomeVoronoiWarpScale")
        set_props(elevation, {"biomeVoronoiWarpStrength": 0.55, "biomeVoronoiWarpScale": 18.0})

        mask_nodes = node_map(mask)
        mask_output = mask_nodes.get("MaterialExpressionPlanetBiomeMaskOutput_0")
        if not mask_output:
            raise RuntimeError("Biome mask signature drift")
        broad_noise_candidates = []
        for node_name, node in mask_nodes.items():
            if not node_name.startswith("MaterialExpressionPlanetNoise_"):
                continue
            values = get_props(node, ["noiseType", "baseFrequency", "octaves", "materialExpressionEditorX", "materialExpressionEditorY", "desc"])
            if (values["noiseType"] == "FbmE" and
                    abs(float(values["baseFrequency"]) - 1.5) <= 0.0001 and
                    int(values["octaves"]) == 6 and
                    int(values["materialExpressionEditorX"]) == -1344 and
                    int(values["materialExpressionEditorY"]) == 1440):
                broad_noise_candidates.append((node_name, node, values))
        if len(broad_noise_candidates) != 1:
            raise RuntimeError("Expected one exact broad-continent noise node, found " + str(len(broad_noise_candidates)))
        broad_noise_name, broad_noise, noise_before = broad_noise_candidates[0]
        mask_before = get_props(mask_output, ["biomeCellResolution", "biomeCellSeed"])
        if int(mask_before["biomeCellResolution"]) != 96 or int(mask_before["biomeCellSeed"]) != 1234:
            raise RuntimeError("Biome-cell source drift")
        set_props(mask_output, {"biomeCellResolution": 32})
        set_props(broad_noise, {"baseFrequency": 0.75, "octaves": 3})

        surface_nodes = node_map(surface_parent)
        replacements = {
            "MaterialExpressionTextureSample_3": ("/PPG/Example/Assets/Biomes/Desert/sandstone_cracks_diff_2k.sandstone_cracks_diff_2k", "/Game/SoStylized/Environment/Landscape/Textures/T_DesertSand_BC"),
            "MaterialExpressionTextureSample_4": ("/PPG/Example/Assets/Biomes/Desert/sandstone_cracks_nor_dx_2k.sandstone_cracks_nor_dx_2k", "/Game/SoStylized/Environment/Landscape/Textures/T_DesertSand_N"),
            "MaterialExpressionTextureObject_0": ("/PPG/Example/Assets/Biomes/Forest/rock_face_03_diff_2k.rock_face_03_diff_2k", "/Game/StylizedRocksPack_01/DetailTextures/T_Rock_Painterly_01_BC"),
            "MaterialExpressionTextureObject_3": ("/PPG/Example/Assets/Biomes/Forest/rock_face_03_nor_dx_2k.rock_face_03_nor_dx_2k", "/Game/StylizedRocksPack_01/DetailTextures/T_Rock_SurfaceDirectional_N"),
            "MaterialExpressionTextureSample_10": ("/PPG/Example/Assets/Biomes/Forest/rocky_trail_diff_2k.rocky_trail_diff_2k", "/Game/StylizedRocksPack_01/DetailTextures/T_Rock_Painterly_01_BC"),
            "MaterialExpressionTextureSample_11": ("/PPG/Example/Assets/Biomes/Forest/rocky_trail_nor_dx_2k.rocky_trail_nor_dx_2k", "/Game/StylizedRocksPack_01/DetailTextures/T_Rock_SurfaceDirectional_N"),
        }
        texture_changes = {}
        for node_name, (before_path, target_texture_path) in replacements.items():
            node = surface_nodes.get(node_name)
            if not node:
                raise RuntimeError("Missing surface node " + node_name)
            before = get_props(node, ["texture"])["texture"]["refPath"]
            if before != before_path:
                raise RuntimeError("Surface texture drift on " + node_name + ": " + before)
            texture = load(target_texture_path)
            set_props(node, {"texture": texture})
            texture_changes[node_name] = {"before": before_path, "after": texture["refPath"]}

        tool("editor_toolset.toolsets.material_instance.MaterialInstanceTools.set_parent", {"instance": surface_mi, "parent": surface_parent})
        set_props(planet, {"generationMaterial": generation, "biomeMaskMaterial": mask, "planetMaterial": surface_mi})

        recompile(generation)
        recompile(mask)
        recompile(surface_parent)
        save(TARGETS)

        planet_after = get_props(planet, ["generationSeed", "planetRadius", "noiseHeight", "generationMaterial", "biomeMaskMaterial", "planetMaterial", "bGenerateWater", "waterMaterial"])
        if int(planet_after["generationSeed"]) != 1337:
            raise RuntimeError("Seed changed")
        same_number(planet_after["planetRadius"], 300000000.0, "planetRadius after")
        same_number(planet_after["noiseHeight"], 600000.0, "noiseHeight after")
        return {
            "created_assets": created,
            "generation_scalar_changes": scalar_changes,
            "warp": {"before": warp_before, "after": {"biomeVoronoiWarpStrength": 0.55, "biomeVoronoiWarpScale": 18.0}},
            "biome_cells": {"before": mask_before, "after": {"biomeCellResolution": 32, "biomeCellSeed": 1234}},
            "broad_continent_noise": {"node": broad_noise_name, "before": noise_before, "after": {"noiseType": "FbmE", "baseFrequency": 0.75, "octaves": 3}},
            "surface_texture_changes": texture_changes,
            "planet_before": planet_before,
            "planet_after": planet_after,
            "oasis_water_promoted": False,
            "water_reason": "Oasis full spherical closure is not proven; native PPG spherical ocean remains bound.",
        }
    except Exception:
        for path in reversed(created):
            try:
                delete(path)
            except Exception:
                pass
        raise
'@

$body=@{jsonrpc='2.0';id=2;method='tools/call';params=@{name='call_tool';arguments=@{toolset_name='editor_toolset.toolsets.programmatic.ProgrammaticToolset';tool_name='execute_tool_script';arguments=@{script=$program}}}}|ConvertTo-Json -Depth 15 -Compress
$response=Post $body $h;$json=Parse $response.Content;$text=@($json.result.content|Where-Object{$_.type -eq 'text'}|ForEach-Object{[string]$_.text}) -join "`n"
if($json.result.isError -or -not $text){throw "Epic MCP R15 asset stage failed: $text"}
$direct=($text|ConvertFrom-Json).returnValue|ConvertFrom-Json
$delete=Invoke-WebRequest -Uri $endpoint -Method Delete -UseBasicParsing -Headers $h -TimeoutSec 30

if((Get-FileHash -LiteralPath $homeMapFile -Algorithm SHA256).Hash -ne $expectedHome){throw 'Home map changed during asset-only MCP stage.'}
Assert-Protected
$payload=[ordered]@{schema='redmmo.ppg_continent_biome.r15.epic_mcp_asset_stage.v1';status='PASS_DIRECT_MCP_ASSET_STAGE';captured_utc=[DateTime]::UtcNow.ToString('o');editor_pid=$pidValue;endpoint=$endpoint;protocol=[string]$ij.result.protocolVersion;http_status=[int]$response.StatusCode;direct_tool='editor_toolset.toolsets.programmatic.ProgrammaticToolset.execute_tool_script';result=$direct;home_map_sha256_unchanged=$expectedHome;session_close_http_status=[int]$delete.StatusCode;protected_hashes_verified=$protected.Count}
$bytes=[Text.UTF8Encoding]::new($false).GetBytes(($payload|ConvertTo-Json -Depth 30)+"`n");$stream=[IO.File]::Open($resultPath,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None);try{$stream.Write($bytes,0,$bytes.Length);$stream.Flush($true)}finally{$stream.Dispose()}
$payload|ConvertTo-Json -Depth 9
