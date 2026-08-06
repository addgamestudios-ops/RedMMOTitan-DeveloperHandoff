$ErrorActionPreference = 'Stop'

$projectRoot = 'D:\RedMMOTitanWindowsData\Projects\RedMMO'
$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$rollbackRoot = "D:\RedMMOTitanWindowsData\Rollback\RedMMO_R15_Playability_$stamp"
$expectedMapHash = '7BA68701F4B1A96777407FC8C349D90878037917CD3212878164B9A28BB37059'

$relativeFiles = @(
    'RedMMO.uproject',
    'Config\DefaultEngine.ini',
    'Config\DefaultGame.ini',
    'Config\DefaultInput.ini',
    'Content\RedMMO\Maps\RedMMO_PPG_HomeWorld.umap',
    'Content\RedMMO\Gameplay\Player\BP_RedPlanetCharacter_R11.uasset',
    'Content\RedMMO\Gameplay\Player\GM_RedPlanet_R11.uasset',
    'Content\RedMMO\Gameplay\Input\IMC_RedPlanet_R11.uasset',
    'Content\RedMMO\World\PPG\HomeWorld\ContinentBiome\R15\DA_PPG_HomeWorld_ContinentBiome_R15.uasset'
)

$protected = [ordered]@{
    'D:\RedMMOTitan\Content\RedMMO\Maps\RedPlanetGen_50km_Test.umap' = 'DA5987012EEB8F550254F5FCF0F47F42B8F5E03428CF4881C83D8687537F6E7D'
    'D:\RedMMOTitan\Content\RedMMO\Maps\RedPlanetGen_50km_FusedPrototype.umap' = '4C84D7752C87854C70987ED9988C64C124C577FBE1DE3DEF3CC826F81B0B6284'
    'D:\RedMMOTitan\Content\RedMMO\Maps\Tests\RedPlanetGen_50km_FusedPrototype_Night_T03.umap' = '211429783F757F3CD8DE4A37B1E37B4A117125BF26EBFCBACF97CCFA9EFBE8D7'
    'D:\RedMMOTitanWindowsData\Rollback\BeforeCoastDatum_20260714\RedPlanetGen_50km_FusedPrototype.umap' = 'A9C42C0D1B0429DD1018F00F0D2AB8A18F66C07291611964EFF5F9710F3B0C6A'
}

if (Test-Path -LiteralPath $rollbackRoot) {
    throw "No-clobber rollback already exists: $rollbackRoot"
}

$mapPath = Join-Path $projectRoot 'Content\RedMMO\Maps\RedMMO_PPG_HomeWorld.umap'
$mapHash = (Get-FileHash -LiteralPath $mapPath -Algorithm SHA256).Hash
if ($mapHash -ne $expectedMapHash) {
    throw "R15 map hash drift: actual=$mapHash expected=$expectedMapHash"
}

foreach ($entry in $protected.GetEnumerator()) {
    $actual = (Get-FileHash -LiteralPath $entry.Key -Algorithm SHA256).Hash
    if ($actual -ne $entry.Value) {
        throw "Protected hash drift: $($entry.Key) actual=$actual expected=$($entry.Value)"
    }
}

New-Item -ItemType Directory -Path $rollbackRoot | Out-Null
$records = @()
foreach ($relative in $relativeFiles) {
    $source = Join-Path $projectRoot $relative
    if (-not (Test-Path -LiteralPath $source -PathType Leaf)) {
        throw "Required checkpoint source missing: $source"
    }
    $destination = Join-Path $rollbackRoot $relative
    $destinationParent = Split-Path -Parent $destination
    New-Item -ItemType Directory -Path $destinationParent -Force | Out-Null
    Copy-Item -LiteralPath $source -Destination $destination
    $sourceHash = (Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash
    $destinationHash = (Get-FileHash -LiteralPath $destination -Algorithm SHA256).Hash
    if ($sourceHash -ne $destinationHash) {
        throw "Checkpoint copy hash mismatch: $relative"
    }
    $records += [ordered]@{
        relative_path = $relative.Replace('\', '/')
        source_path = $source
        source_sha256 = $sourceHash
        rollback_path = $destination
        rollback_sha256 = $destinationHash
        bytes = (Get-Item -LiteralPath $source).Length
    }
}

$manifest = [ordered]@{
    schema = 'redmmo.r15.playability_checkpoint.v1'
    status = 'PASS'
    created_utc = (Get-Date).ToUniversalTime().ToString('o')
    project_root = $projectRoot
    rollback_root = $rollbackRoot
    home_map_sha256 = $mapHash
    files = $records
    protected_hashes = $protected
    scope = @(
        'R15 home map lighting and PlayerStart',
        'project-owned R11 pawn, GameMode, and input context',
        'R15 PlanetData identity only; seed and topology must remain unchanged'
    )
}
$manifestPath = Join-Path $rollbackRoot 'manifest.json'
$manifest | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $manifestPath -Encoding UTF8

[ordered]@{
    status = 'PASS'
    rollback_root = $rollbackRoot
    manifest = $manifestPath
    manifest_sha256 = (Get-FileHash -LiteralPath $manifestPath -Algorithm SHA256).Hash
    file_count = $records.Count
    home_map_sha256 = $mapHash
} | ConvertTo-Json -Depth 4
