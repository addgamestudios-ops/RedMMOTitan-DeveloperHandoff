param(
    [string]$SourceProject = "D:\RedMMOTitan",
    [string]$OutputRoot = "D:\RedMMOTitanWindowsData\ArtistHandoff",
    [string]$PackageName = "RED_Mars_PlanetArtist_UE58_20260720_SAFE2"
)

$ErrorActionPreference = "Stop"
$stage = Join-Path $OutputRoot $PackageName
$zip = Join-Path $OutputRoot ($PackageName + ".zip")
$protectedMarker = "D:\RedMMOTitanWindowsData\PackagedBuilds\Development_50KM_FOUNDATION_20260716_064703\REDMMO_PACKAGE_READY.txt"
$protectedExpected = "26B00A20C4B18717CEC36B5CA289CC9001AE1E65DA649404ACC8721F14EF26E8"

if ((Get-FileHash -LiteralPath $protectedMarker -Algorithm SHA256).Hash -ne $protectedExpected) {
    throw "Protected 50 km checkpoint marker changed; refusing to package."
}

$resolvedOutput = [IO.Path]::GetFullPath($OutputRoot).TrimEnd('\')
$resolvedStage = [IO.Path]::GetFullPath($stage)
if (-not $resolvedStage.StartsWith($resolvedOutput + '\', [StringComparison]::OrdinalIgnoreCase)) {
    throw "Unsafe staging path: $resolvedStage"
}
if (Test-Path -LiteralPath $stage) { Remove-Item -LiteralPath $stage -Recurse -Force }
if (Test-Path -LiteralPath $zip) { Remove-Item -LiteralPath $zip -Force }

$dirs = @(
    $stage,
    (Join-Path $stage "Content"),
    (Join-Path $stage "Plugins"),
    (Join-Path $stage "Binaries\Win64"),
    (Join-Path $stage "Documents"),
    (Join-Path $stage "Build\Verification")
)
foreach ($dir in $dirs) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }

$artistConfigDir = Join-Path $stage "Config"
New-Item -ItemType Directory -Path $artistConfigDir -Force | Out-Null
Get-ChildItem -LiteralPath (Join-Path $SourceProject "Config") -Filter '*.ini' -File |
    Copy-Item -Destination $artistConfigDir
$artistSourceArtDir = Join-Path $stage "SourceArt"
New-Item -ItemType Directory -Path $artistSourceArtDir -Force | Out-Null
Copy-Item -LiteralPath (Join-Path $SourceProject "SourceArt\Planet50Km") -Destination $artistSourceArtDir -Recurse
$revisionBackupDirs = @(Get-ChildItem -LiteralPath (Join-Path $stage "SourceArt\Planet50Km") -Directory -Recurse -Filter 'RevisionBackups')
foreach ($revisionBackupDir in $revisionBackupDirs) {
    $resolvedRevisionBackup = [IO.Path]::GetFullPath($revisionBackupDir.FullName)
    if (-not $resolvedRevisionBackup.StartsWith($resolvedStage + '\', [StringComparison]::OrdinalIgnoreCase)) {
        throw "Unsafe revision-backup path: $resolvedRevisionBackup"
    }
    Remove-Item -LiteralPath $resolvedRevisionBackup -Recurse -Force
}
Copy-Item -LiteralPath (Join-Path $SourceProject "Tools") -Destination $stage -Recurse
Copy-Item -LiteralPath (Join-Path $SourceProject "Plugins\PlanetGenPinned_1_4_0_RedMMO") -Destination (Join-Path $stage "Plugins") -Recurse
$stagedPlanetGenPlugin = Join-Path $stage "Plugins\PlanetGenPinned_1_4_0_RedMMO"
foreach ($generatedPluginDirName in @('Intermediate', 'Saved')) {
    $generatedPluginDir = Join-Path $stagedPlanetGenPlugin $generatedPluginDirName
    if (Test-Path -LiteralPath $generatedPluginDir) {
        $resolvedGeneratedPluginDir = [IO.Path]::GetFullPath($generatedPluginDir)
        if (-not $resolvedGeneratedPluginDir.StartsWith($resolvedStage + '\', [StringComparison]::OrdinalIgnoreCase)) {
            throw "Unsafe generated plugin path: $resolvedGeneratedPluginDir"
        }
        Remove-Item -LiteralPath $resolvedGeneratedPluginDir -Recurse -Force
    }
}

Copy-Item -LiteralPath (Join-Path $PSScriptRoot "Titan_Artist.uproject") -Destination (Join-Path $stage "Titan.uproject")
Copy-Item -LiteralPath (Join-Path $PSScriptRoot "PlanetArtist_README_UA.md") -Destination (Join-Path $stage "README_UA.md")
Copy-Item -LiteralPath (Join-Path $PSScriptRoot "verify_planet_artist_project.py") -Destination (Join-Path $stage "Build\Verification\verify_planet_artist_project.py")
Copy-Item -LiteralPath (Join-Path $PSScriptRoot "OPEN_PLANET_EDITOR_SAFE.cmd") -Destination (Join-Path $stage "OPEN_PLANET_EDITOR_SAFE.cmd")

# The source project's startup map is the full gameplay world.  Loading it in an
# environment-art handoff eagerly pulls ships, characters, UI, VFX and hundreds
# of textures into the editor.  Keep the handoff pointed at the fused 27-patch
# canvas and use a neutral engine game mode/instance so pressing Play does not
# materialize the production gameplay stack.
$artistDefaultEnginePath = Join-Path $stage "Config\DefaultEngine.ini"
$artistDefaultEngine = Get-Content -LiteralPath $artistDefaultEnginePath -Raw

function Remove-IniSection {
    param(
        [Parameter(Mandatory = $true)][string]$Text,
        [Parameter(Mandatory = $true)][string]$Section
    )

    $pattern = '(?ms)^\[' + [Regex]::Escape($Section) + '\]\s*\r?\n.*?(?=^\[|\z)'
    return [Regex]::Replace($Text, $pattern, '')
}

$artistConfigReplacements = [ordered]@{
    'EditorStartupMap'      = '/Game/RedMMO/Maps/RedPlanetGen_50km_ArtistCanvas.RedPlanetGen_50km_ArtistCanvas'
    'GameDefaultMap'        = '/Game/RedMMO/Maps/RedPlanetGen_50km_ArtistCanvas.RedPlanetGen_50km_ArtistCanvas'
    'ServerDefaultMap'      = '/Game/RedMMO/Maps/RedPlanetGen_50km_ArtistCanvas.RedPlanetGen_50km_ArtistCanvas'
    'GameInstanceClass'     = '/Script/Engine.GameInstance'
    'GlobalDefaultGameMode' = '/Script/Engine.GameModeBase'
    'DefaultGraphicsRHI'    = 'DefaultGraphicsRHI_DX11'
}
foreach ($key in $artistConfigReplacements.Keys) {
    $pattern = '(?m)^' + [Regex]::Escape($key) + '=.*$'
    if (-not [Regex]::IsMatch($artistDefaultEngine, $pattern)) {
        throw "Artist config key missing from source DefaultEngine.ini: $key"
    }
    $artistDefaultEngine = [Regex]::Replace(
        $artistDefaultEngine,
        $pattern,
        ($key + '=' + $artistConfigReplacements[$key]),
        1
    )
}

# The handoff is a content-only environment project.  Remove production-only
# online/UI configuration so disabled plugins cannot be referenced during
# editor startup.  In particular, a stale GameFeatureData asset-manager entry
# caused an AssetManagerTypes.cpp handled ensure in the first SAFE extract.
$viewportPattern = '(?m)^GameViewportClientClassName=.*$'
if ([Regex]::IsMatch($artistDefaultEngine, $viewportPattern)) {
    $artistDefaultEngine = [Regex]::Replace(
        $artistDefaultEngine,
        $viewportPattern,
        'GameViewportClientClassName=/Script/Engine.GameViewportClient',
        1
    )
}
foreach ($section in @(
    'OnlineSubsystem',
    'OnlineSubsystemSteam',
    '/Script/Engine.GameEngine',
    '/Script/SteamSockets.SteamSocketsNetDriver'
)) {
    $artistDefaultEngine = Remove-IniSection -Text $artistDefaultEngine -Section $section
}
$artistDefaultEngine = [Regex]::Replace(
    $artistDefaultEngine,
    '(?m)^;.*(?:OnlineSubsystemSteam|SteamSockets).*(?:\r?\n|$)',
    ''
)
Set-Content -LiteralPath $artistDefaultEnginePath -Value $artistDefaultEngine -Encoding UTF8

$artistDefaultGamePath = Join-Path $stage "Config\DefaultGame.ini"
$artistDefaultGame = Get-Content -LiteralPath $artistDefaultGamePath -Raw
$artistDefaultGame = [Regex]::Replace(
    $artistDefaultGame,
    '(?m)^\+PrimaryAssetTypesToScan=.*PrimaryAssetType="GameFeatureData".*\r?\n?',
    ''
)
$artistDefaultGame = $artistDefaultGame.Replace('PrimaryAssetType="World"', 'PrimaryAssetType="Map"')
Set-Content -LiteralPath $artistDefaultGamePath -Value $artistDefaultGame -Encoding UTF8

foreach ($configName in @('DefaultEditor.ini', 'DefaultInput.ini')) {
    $configPath = Join-Path $stage ("Config\" + $configName)
    if (Test-Path -LiteralPath $configPath) {
        $configText = Get-Content -LiteralPath $configPath -Raw
        $commonUiSections = [Regex]::Matches($configText, '(?m)^\[([^\]]*CommonUI[^\]]*)\]') |
            ForEach-Object { $_.Groups[1].Value } |
            Select-Object -Unique
        foreach ($section in $commonUiSections) {
            $configText = Remove-IniSection -Text $configText -Section $section
        }
        Set-Content -LiteralPath $configPath -Value $configText -Encoding UTF8
    }
}
Copy-Item -LiteralPath (Join-Path $PSScriptRoot "PlanetArtist_ConsoleVariables.ini") -Destination (Join-Path $stage "Config\ConsoleVariables.ini")

$artistLauncherPath = Join-Path $stage "OPEN_PLANET_EDITOR_SAFE.cmd"
$artistLauncher = Get-Content -LiteralPath $artistLauncherPath -Raw
foreach ($requiredLaunchToken in @(
    '/Game/RedMMO/Maps/RedPlanetGen_50km_ArtistCanvas',
    '-dx11',
    '-cvarsini=%~dp0Config\ConsoleVariables.ini'
)) {
    if ($artistLauncher.IndexOf($requiredLaunchToken, [StringComparison]::OrdinalIgnoreCase) -lt 0) {
        throw "Artist safe launcher is missing required token: $requiredLaunchToken"
    }
}

$dependencyFile = Join-Path $OutputRoot "planet_asset_dependencies.json"
$dependency = Get-Content -LiteralPath $dependencyFile -Raw | ConvertFrom-Json
$requiredArtistPackages = @(
    "/Game/RedMMO/Maps/RedPlanetGen_50km_ArtistCanvas",
    "/Game/RedMMO/Environment/DA_RED_Planet50Km_FusedHeightfield"
)
$missingDependencyPackages = @($requiredArtistPackages | Where-Object { $dependency.project_packages -notcontains $_ })
if ($missingDependencyPackages.Count -gt 0) {
    throw "Dependency export is stale; missing required artist packages: $($missingDependencyPackages -join ', ')"
}
$forbiddenMarkers = @('/Ships/', '/UI/', '/Characters/', '/Weapons/', '/SpaceShip/', '/Action_', '/Jet_Packs', '/Projectiles', '/Vefects/', '/StylizedFX_2/')
$forbiddenDependencies = @($dependency.project_packages | Where-Object {
    $candidate = $_
    @($forbiddenMarkers | Where-Object { $candidate.IndexOf($_, [StringComparison]::OrdinalIgnoreCase) -ge 0 }).Count -gt 0
})
if ($forbiddenDependencies.Count -gt 0) {
    throw "Artist dependency export contains gameplay-only packages: $($forbiddenDependencies -join ', ')"
}
$packageExtensions = @(".uasset", ".umap", ".uexp", ".ubulk", ".uptnl")
$copiedPackages = 0
foreach ($package in $dependency.project_packages) {
    $relativeBase = $package.Substring(6).Replace('/', '\')
    $foundPrimary = $false
    foreach ($ext in $packageExtensions) {
        $src = Join-Path (Join-Path $SourceProject "Content") ($relativeBase + $ext)
        if (Test-Path -LiteralPath $src) {
            $dst = Join-Path (Join-Path $stage "Content") ($relativeBase + $ext)
            New-Item -ItemType Directory -Path (Split-Path -Parent $dst) -Force | Out-Null
            Copy-Item -LiteralPath $src -Destination $dst
            if ($ext -eq ".uasset" -or $ext -eq ".umap") { $foundPrimary = $true }
        }
    }
    if ($foundPrimary) { $copiedPackages++ }
}

Copy-Item -LiteralPath (Join-Path $OutputRoot "RED_Mars_27_Patches_Artist_Guide_UA.docx") -Destination (Join-Path $stage "Documents")
Copy-Item -LiteralPath (Join-Path $OutputRoot "RED_Mars_27_Patches_Artist_Guide_UA.pdf") -Destination (Join-Path $stage "Documents")
Copy-Item -LiteralPath $dependencyFile -Destination (Join-Path $stage "Documents")

$patchPngCount = (Get-ChildItem -LiteralPath (Join-Path $stage "SourceArt\Planet50Km\AuthoringPatches") -Filter "RED_Patch_*_Height_16.png" -File).Count
if ($patchPngCount -ne 27) { throw "Expected 27 authoring height PNGs, found $patchPngCount" }
if (-not (Test-Path -LiteralPath (Join-Path $stage "Content\RedMMO\Maps\RedPlanetGen_50km_ArtistCanvas.umap"))) { throw "Artist canvas map missing" }
if (-not (Test-Path -LiteralPath (Join-Path $stage "Content\RedMMO\Environment\DA_RED_Planet50Km_FusedHeightfield.uasset"))) { throw "Fused data asset missing" }
$stagedDefaultEngine = Get-Content -LiteralPath (Join-Path $stage "Config\DefaultEngine.ini") -Raw
if ($stagedDefaultEngine -notmatch 'EditorStartupMap=/Game/RedMMO/Maps/RedPlanetGen_50km_ArtistCanvas') { throw "Artist startup map override missing" }
if ($stagedDefaultEngine -notmatch 'DefaultGraphicsRHI=DefaultGraphicsRHI_DX11') { throw "Artist safe RHI override missing" }
$stagedConfigCorpus = Get-ChildItem -LiteralPath (Join-Path $stage "Config") -Filter '*.ini' -File |
    ForEach-Object { Get-Content -LiteralPath $_.FullName -Raw }
$forbiddenConfigReferences = @(
    'GameFeatureData',
    'PrimaryAssetType="World"',
    '/Script/CommonUI.',
    'DefaultPlatformService=Steam',
    '/Script/SteamSockets.',
    'OnlineSubsystemSteam'
)
foreach ($forbiddenReference in $forbiddenConfigReferences) {
    if (($stagedConfigCorpus -join "`n").IndexOf($forbiddenReference, [StringComparison]::OrdinalIgnoreCase) -ge 0) {
        throw "Artist configuration retains production-only reference: $forbiddenReference"
    }
}

$manifestLines = Get-ChildItem -LiteralPath $stage -Recurse -File | Sort-Object FullName | ForEach-Object {
    $relative = $_.FullName.Substring($stage.Length + 1)
    $hash = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash
    "$hash  $relative"
}
$manifestLines | Set-Content -LiteralPath (Join-Path $stage "MANIFEST_SHA256.txt") -Encoding UTF8

$summary = @(
    "RED MMO Mars Planet Artist Handoff",
    "Generated: $([DateTime]::UtcNow.ToString('u')) UTC",
    "Project packages copied: $copiedPackages",
    "Authoring height patches: $patchPngCount",
    "Map: /Game/RedMMO/Maps/RedPlanetGen_50km_ArtistCanvas",
    "Protected foundation marker hash: $protectedExpected"
)
$summary | Set-Content -LiteralPath (Join-Path $stage "PACKAGE_CONTENTS.txt") -Encoding UTF8

& tar.exe -a -c -f $zip -C $OutputRoot $PackageName
if ($LASTEXITCODE -ne 0) { throw "tar zip creation failed: $LASTEXITCODE" }

$entries = & tar.exe -tf $zip
$required = @(
    "$PackageName/Titan.uproject",
    "$PackageName/OPEN_PLANET_EDITOR_SAFE.cmd",
    "$PackageName/Config/ConsoleVariables.ini",
    "$PackageName/README_UA.md",
    "$PackageName/Documents/RED_Mars_27_Patches_Artist_Guide_UA.pdf",
    "$PackageName/Content/RedMMO/Maps/RedPlanetGen_50km_ArtistCanvas.umap",
    "$PackageName/SourceArt/Planet50Km/AuthoringPatches/RED_Patch_00_Height_16.png"
)
foreach ($entry in $required) {
    if ($entries -notcontains $entry) { throw "ZIP validation missing: $entry" }
}

[pscustomobject]@{
    Stage = $stage
    Zip = $zip
    ZipBytes = (Get-Item -LiteralPath $zip).Length
    ProjectPackages = $copiedPackages
    PatchCount = $patchPngCount
    ZipEntries = $entries.Count
} | ConvertTo-Json
