$ErrorActionPreference = 'Stop'

$projectRoot = 'D:\RedMMOTitanWindowsData\Projects\RedMMO'
$diagnosticsRoot = 'D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_PPG_ContinentBiome_R15_20260802_211912'
$rollbackRoot = 'D:\RedMMOTitanWindowsData\Rollback\RedMMO_PPG_ContinentBiome_R15_20260802_211912_A01'
$manifestPath = Join-Path $rollbackRoot 'pre_r15_manifest.json'
$homeMapFile = Join-Path $projectRoot 'Content\RedMMO\Maps\RedMMO_PPG_HomeWorld.umap'
$r10oRoot = Join-Path $projectRoot 'Content\RedMMO\World\PPG\HomeWorld\StylizedBinding\R10O'
$r10nGeneration = Join-Path $projectRoot 'Content\RedMMO\World\PPG\HomeWorld\StylizedBinding\R10N\Materials\M_PPG_Generation_SmoothSpawnGrass_R10N.uasset'
$r10lSurfaceParent = Join-Path $projectRoot 'Content\RedMMO\World\PPG\HomeWorld\StylizedBinding\R10L\Materials\M_PPG_Home_PaintedLeafGround_R10L.uasset'
$r10nSurfaceInstance = Join-Path $projectRoot 'Content\RedMMO\World\PPG\HomeWorld\StylizedBinding\R10N\Materials\MI_PPG_Home_PaintedLeafGround_Scaled_R10N.uasset'
$r10oProfile = Join-Path $projectRoot 'Config\RedMMO\PPGStylizedFoliageProfiles\HomeWorld_Presentation_R10O.json'
$projectFile = Join-Path $projectRoot 'RedMMO.uproject'
$defaultEngine = Join-Path $projectRoot 'Config\DefaultEngine.ini'
$defaultGame = Join-Path $projectRoot 'Config\DefaultGame.ini'
$vendorMask = 'D:\UE_5.8\Engine\Plugins\Marketplace\Procedur890d9e860517V2\Content\Example\Assets\M_PPG_ExampleBiomeMask.uasset'
$r15ContentRoot = Join-Path $projectRoot 'Content\RedMMO\World\PPG\HomeWorld\ContinentBiome\R15'
$r15Profile = Join-Path $projectRoot 'Config\RedMMO\PPGContinentBiomeProfiles\HomeWorld_ContinentBiome_R15.json'

$expected = [ordered]@{
    $homeMapFile = 'C9BE88085575E75E1790CB9306D564EB100F5ED2E75E012C1FD09EA110FDDFE0'
    (Join-Path $r10oRoot 'DA_PPG_HomeWorld_StylizedBinding_R10O.uasset') = '7C6835CA50EBB06B4C94AA6D1E8B0419B1E0ACF09A44D5CEA5B670FBD5865C5A'
    (Join-Path $r10oRoot 'Profiles\DA_PPG_HomeWorld_StylizedForest_R10O.uasset') = '4D7B577684CF74CBF56BCB6AF8A6867DAD130C8BACF022CF461D86A53833E18F'
    $r10nGeneration = '43EA98C552B42A28C90C588A588E6B30C9C63ABE02E1E99D744D02E6D65A1FD0'
    $r10lSurfaceParent = 'D199781D994392066DBE91F94201A9E9989A73CE7DFCB92D66640FF39FD97AA1'
    $r10nSurfaceInstance = 'A6ED14A2C495A1F7527F9AA79CA3C317E7E0101E155C4926015CCCE5927E95DB'
    $r10oProfile = 'EAFBCE63E1FBE5AE96A52DB9A3AC993D87E3BA8C47927F35B8A630D7A8AABB9D'
    $projectFile = '1B97948F52999D5C81C808A9AECEFB55C32128BCA2460AF78691082E1793AE87'
    $defaultEngine = 'A736AF02C9C056B9FC84DA8158A9B867D7F999D9150C4051AA00A90A65471B0A'
    $defaultGame = 'C83A14298F5DC3B9AC17EBA6FB89E49E2D5CAA13F2DEB2968CBC13B88BE68A98'
    $vendorMask = '6F624C548D68EE00468099CAA41414FE90764D5A8F43B35537CCB4270F615AE3'
}

$protected = [ordered]@{
    'D:\RedMMOTitan\Content\RedMMO\Maps\RedPlanetGen_50km_Test.umap' = 'DA5987012EEB8F550254F5FCF0F47F42B8F5E03428CF4881C83D8687537F6E7D'
    'D:\RedMMOTitan\Content\RedMMO\Maps\RedPlanetGen_50km_FusedPrototype.umap' = '4C84D7752C87854C70987ED9988C64C124C577FBE1DE3DEF3CC826F81B0B6284'
    'D:\RedMMOTitan\Content\RedMMO\Maps\Tests\RedPlanetGen_50km_FusedPrototype_Night_T03.umap' = '211429783F757F3CD8DE4A37B1E37B4A117125BF26EBFCBACF97CCFA9EFBE8D7'
    'D:\RedMMOTitanWindowsData\Rollback\BeforeCoastDatum_20260714\RedPlanetGen_50km_FusedPrototype.umap' = 'A9C42C0D1B0429DD1018F00F0D2AB8A18F66C07291611964EFF5F9710F3B0C6A'
}

if (Test-Path -LiteralPath $rollbackRoot) { throw "R15 rollback path already exists: $rollbackRoot" }
if (Test-Path -LiteralPath $diagnosticsRoot) { throw "R15 diagnostics path already exists: $diagnosticsRoot" }
if (Test-Path -LiteralPath $r15ContentRoot) { throw "R15 content root already exists: $r15ContentRoot" }
if (Test-Path -LiteralPath $r15Profile) { throw "R15 profile already exists: $r15Profile" }

$unreal = Get-CimInstance Win32_Process | Where-Object {
    $_.Name -match '^(UnrealEditor|UnrealEditor-Cmd|ShaderCompileWorker|UnrealBuildTool|AutomationTool)(\.exe)?$'
}
if ($unreal) { throw "Unreal/build process active; refusing checkpoint: $($unreal.ProcessId -join ',')" }

foreach ($pair in $expected.GetEnumerator()) {
    if (-not (Test-Path -LiteralPath $pair.Key -PathType Leaf)) { throw "Missing expected source: $($pair.Key)" }
    $actual = (Get-FileHash -Algorithm SHA256 -LiteralPath $pair.Key).Hash
    if ($actual -ne $pair.Value) { throw "Source hash drift: $($pair.Key) expected $($pair.Value) actual $actual" }
}
foreach ($pair in $protected.GetEnumerator()) {
    if (-not (Test-Path -LiteralPath $pair.Key -PathType Leaf)) { throw "Missing protected checkpoint: $($pair.Key)" }
    $actual = (Get-FileHash -Algorithm SHA256 -LiteralPath $pair.Key).Hash
    if ($actual -ne $pair.Value) { throw "Protected hash drift: $($pair.Key) expected $($pair.Value) actual $actual" }
}

[void](New-Item -ItemType Directory -Path $diagnosticsRoot)
[void](New-Item -ItemType Directory -Path $rollbackRoot)
$backupHome = Join-Path $rollbackRoot 'RedMMO_PPG_HomeWorld.pre_r15.umap'
$backupSources = Join-Path $rollbackRoot 'source_preimages'
[void](New-Item -ItemType Directory -Path $backupSources)
Copy-Item -LiteralPath $homeMapFile -Destination $backupHome -ErrorAction Stop

$copies = @(
    @{ Source = $r10oRoot; Target = (Join-Path $backupSources 'R10O'); Recurse = $true },
    @{ Source = $r10nGeneration; Target = (Join-Path $backupSources 'M_PPG_Generation_SmoothSpawnGrass_R10N.uasset'); Recurse = $false },
    @{ Source = $r10lSurfaceParent; Target = (Join-Path $backupSources 'M_PPG_Home_PaintedLeafGround_R10L.uasset'); Recurse = $false },
    @{ Source = $r10nSurfaceInstance; Target = (Join-Path $backupSources 'MI_PPG_Home_PaintedLeafGround_Scaled_R10N.uasset'); Recurse = $false },
    @{ Source = $r10oProfile; Target = (Join-Path $backupSources 'HomeWorld_Presentation_R10O.json'); Recurse = $false },
    @{ Source = $projectFile; Target = (Join-Path $backupSources 'RedMMO.uproject'); Recurse = $false },
    @{ Source = $defaultEngine; Target = (Join-Path $backupSources 'DefaultEngine.ini'); Recurse = $false },
    @{ Source = $defaultGame; Target = (Join-Path $backupSources 'DefaultGame.ini'); Recurse = $false }
)
foreach ($copy in $copies) {
    if ($copy.Recurse) { Copy-Item -LiteralPath $copy.Source -Destination $copy.Target -Recurse -ErrorAction Stop }
    else { Copy-Item -LiteralPath $copy.Source -Destination $copy.Target -ErrorAction Stop }
}

$manifest = [ordered]@{
    schema = 'redmmo.ppg_continent_biome.r15.rollback.v1'
    created_utc = [DateTime]::UtcNow.ToString('o')
    project = $projectFile
    source_home_map = $homeMapFile
    source_home_sha256 = $expected[$homeMapFile]
    source_hashes = $expected
    protected_hashes = $protected
    rollback_home_map = $backupHome
    rollback_source_preimages = $backupSources
    planned_created_content_root = '/Game/RedMMO/World/PPG/HomeWorld/ContinentBiome/R15'
    planned_created_profile = $r15Profile
    planned_mutation = 'Bind project-owned R15 continent/biome PlanetData to the real clean RedMMO PPG home map; remove only the rejected R06 rectangular water actor reference.'
    preserved = @('seed 1337','planet radius','noise height','recursion/streaming','R10O foliage slot ordering and weights','native PPG spherical ocean material','vendor assets','production RedMMOTitan maps')
    rollback_method = 'Close Unreal. Restore rollback_home_map over source_home_map. Remove only planned_created_content_root and planned_created_profile. Source preimages are retained for verification; no source asset is intentionally edited.'
}

$json = $manifest | ConvertTo-Json -Depth 9
$bytes = [Text.UTF8Encoding]::new($false).GetBytes($json + "`n")
$stream = [IO.File]::Open($manifestPath, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
try { $stream.Write($bytes, 0, $bytes.Length); $stream.Flush($true) } finally { $stream.Dispose() }

$result = [ordered]@{
    status = 'PASS'
    manifest = $manifestPath
    rollback_root = $rollbackRoot
    home_backup = $backupHome
    source_preimages = $backupSources
    home_sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $homeMapFile).Hash
    protected_hashes_verified = $protected.Count
    source_hashes_verified = $expected.Count
}
$resultPath = Join-Path $diagnosticsRoot 'prepare_r15_checkpoint_result.json'
$resultBytes = [Text.UTF8Encoding]::new($false).GetBytes(($result | ConvertTo-Json -Depth 6) + "`n")
$resultStream = [IO.File]::Open($resultPath, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
try { $resultStream.Write($resultBytes, 0, $resultBytes.Length); $resultStream.Flush($true) } finally { $resultStream.Dispose() }
$result | ConvertTo-Json -Depth 6
