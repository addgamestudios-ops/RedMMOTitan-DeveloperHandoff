$ErrorActionPreference = 'Stop'

$projectRoot = 'D:\RedMMOTitanWindowsData\Projects\RedMMO'
$diagnosticsRoot = 'D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_PPG_HomePresentation_R10N_20260802_181848'
$rollbackRoot = 'D:\RedMMOTitanWindowsData\Rollback\RedMMO_PPG_HomePresentation_R10N_20260802_181848_A01'
$manifestPath = Join-Path $rollbackRoot 'pre_r10n_manifest.json'
$homeMap = Join-Path $projectRoot 'Content\RedMMO\Maps\RedMMO_PPG_HomeWorld.umap'
$sourceRoot = Join-Path $projectRoot 'Content\RedMMO\World\PPG\HomeWorld\StylizedBinding\R10M'
$sourceProfile = Join-Path $projectRoot 'Config\RedMMO\PPGStylizedFoliageProfiles\HomeWorld_Presentation_R10M.json'
$generationMaterial = Join-Path $projectRoot 'Content\RedMMO\World\PPG\HomeWorld\StylizedPilot\R05\Materials\M_PPG_Generation_CapFoliage_R05.uasset'

$expected = [ordered]@{
    $homeMap = 'B19019D31369D0325896BA871EB083036DE64516EF51314CF89A74B30366DB10'
    $generationMaterial = 'F48D4CEE2078401FD31C1EEA989EE70CF9BB4444575C2B8A62091C7DACFA5594'
    $sourceProfile = 'B18FE973B297E65522E3E6A17A97C13CC7D5201ABAFDC0DCCF6E70F1E918AC54'
}

$protected = [ordered]@{
    'D:\RedMMOTitan\Content\RedMMO\Maps\RedPlanetGen_50km_Test.umap' = 'DA5987012EEB8F550254F5FCF0F47F42B8F5E03428CF4881C83D8687537F6E7D'
    'D:\RedMMOTitan\Content\RedMMO\Maps\RedPlanetGen_50km_FusedPrototype.umap' = '4C84D7752C87854C70987ED9988C64C124C577FBE1DE3DEF3CC826F81B0B6284'
    'D:\RedMMOTitan\Content\RedMMO\Maps\Tests\RedPlanetGen_50km_FusedPrototype_Night_T03.umap' = '211429783F757F3CD8DE4A37B1E37B4A117125BF26EBFCBACF97CCFA9EFBE8D7'
    'D:\RedMMOTitanWindowsData\Rollback\BeforeCoastDatum_20260714\RedPlanetGen_50km_FusedPrototype.umap' = 'A9C42C0D1B0429DD1018F00F0D2AB8A18F66C07291611964EFF5F9710F3B0C6A'
}

if (Test-Path -LiteralPath $manifestPath) {
    throw "R10N checkpoint manifest already exists: $manifestPath"
}
if (-not (Test-Path -LiteralPath $sourceRoot -PathType Container)) {
    throw "Missing R10M source root: $sourceRoot"
}

$unreal = Get-CimInstance Win32_Process | Where-Object {
    $_.Name -match '^(UnrealEditor|UnrealEditor-Cmd|ShaderCompileWorker|UnrealBuildTool|AutomationTool)(\.exe)?$'
}
if ($unreal) {
    throw "Unreal/build process is active; refusing checkpoint copy: $($unreal.ProcessId -join ',')"
}

foreach ($pair in $expected.GetEnumerator()) {
    if (-not (Test-Path -LiteralPath $pair.Key -PathType Leaf)) {
        throw "Missing expected source: $($pair.Key)"
    }
    $actual = (Get-FileHash -Algorithm SHA256 -LiteralPath $pair.Key).Hash
    if ($actual -ne $pair.Value) {
        throw "Source hash drift: $($pair.Key) expected $($pair.Value) actual $actual"
    }
}
foreach ($pair in $protected.GetEnumerator()) {
    if (-not (Test-Path -LiteralPath $pair.Key -PathType Leaf)) {
        throw "Missing protected checkpoint: $($pair.Key)"
    }
    $actual = (Get-FileHash -Algorithm SHA256 -LiteralPath $pair.Key).Hash
    if ($actual -ne $pair.Value) {
        throw "Protected checkpoint drift: $($pair.Key) expected $($pair.Value) actual $actual"
    }
}

$backupHome = Join-Path $rollbackRoot 'RedMMO_PPG_HomeWorld.pre_r10n.umap'
$backupSource = Join-Path $rollbackRoot 'R10M_source'
$backupProfile = Join-Path $rollbackRoot 'HomeWorld_Presentation_R10M.pre_r10n.json'
Copy-Item -LiteralPath $homeMap -Destination $backupHome -ErrorAction Stop
Copy-Item -LiteralPath $sourceRoot -Destination $backupSource -Recurse -ErrorAction Stop
Copy-Item -LiteralPath $sourceProfile -Destination $backupProfile -ErrorAction Stop

$sourceFiles = Get-ChildItem -LiteralPath $sourceRoot -Recurse -File | Sort-Object FullName | ForEach-Object {
    [ordered]@{
        path = $_.FullName
        bytes = $_.Length
        sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $_.FullName).Hash
    }
}

$manifest = [ordered]@{
    schema = 'redmmo.ppg_home_presentation.r10n.rollback.v1'
    created_utc = [DateTime]::UtcNow.ToString('o')
    source_revision = 'R10M'
    source_home_map = $homeMap
    source_home_sha256 = $expected[$homeMap]
    source_generation_material = $generationMaterial
    source_generation_sha256 = $expected[$generationMaterial]
    source_profile = $sourceProfile
    source_profile_sha256 = $expected[$sourceProfile]
    source_files = $sourceFiles
    protected_hashes = $protected
    rollback_home_map = $backupHome
    rollback_source_root = $backupSource
    rollback_profile = $backupProfile
    planned_created_content_root = '/Game/RedMMO/World/PPG/HomeWorld/StylizedBinding/R10N'
    planned_created_profile = (Join-Path $projectRoot 'Config\RedMMO\PPGStylizedFoliageProfiles\HomeWorld_Presentation_R10N.json')
    rollback_method = 'Close Unreal, restore rollback_home_map over source_home_map, remove only the exact R10N content root and R10N profile listed above.'
}

$json = $manifest | ConvertTo-Json -Depth 8
$bytes = [Text.UTF8Encoding]::new($false).GetBytes($json + "`n")
$stream = [IO.File]::Open($manifestPath, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
try {
    $stream.Write($bytes, 0, $bytes.Length)
    $stream.Flush($true)
}
finally {
    $stream.Dispose()
}

$result = [ordered]@{
    status = 'PASS'
    manifest = $manifestPath
    home_backup = $backupHome
    source_backup = $backupSource
    profile_backup = $backupProfile
    home_sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $homeMap).Hash
    protected_hashes_verified = $protected.Count
    source_asset_files_backed_up = $sourceFiles.Count
}
$result | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $diagnosticsRoot 'prepare_r10n_checkpoint_result.json') -Encoding utf8
$result | ConvertTo-Json -Depth 5
