param(
    [string]$Archive
)

$ErrorActionPreference = 'Stop'

$DataRoot = 'D:\RedMMOTitanWindowsData'
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$Stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$Log = Join-Path $DataRoot "BuildLogs\PackagedSmokeFused_$Stamp.log"
$ExitFile = "$Log.exitcode"
$UnrealPak = 'D:\UE_5.8\Engine\Binaries\Win64\UnrealPak.exe'
New-Item -ItemType Directory -Force -Path (Split-Path $Log) | Out-Null

$ExpectedHashes = [ordered]@{
    'Content\RedMMO\Maps\RedPlanetGen.umap' = '1DF9E6ED913A267875F1EF452F6ED51DAF337DBBAAE4C6EC3379EA6299346724'
    'Content\RedMMO\Maps\RedPlanetGen_50km_Test.umap' = 'DA5987012EEB8F550254F5FCF0F47F42B8F5E03428CF4881C83D8687537F6E7D'
    # July 19 ascent-safety save; provenance is pinned by the M03 static evidence record.
    'Content\RedMMO\Maps\RedPlanetGen_50km_FusedPrototype.umap' = '4C84D7752C87854C70987ED9988C64C124C577FBE1DE3DEF3CC826F81B0B6284'
    'Content\RedMMO\Environment\DA_RED_Planet50Km_FusedHeightfield.uasset' = '412E26B75DAD95CE0EF4FA63BFF21CCA0EDB755B5D08BA1A4CFA3EEFEC06E562'
}
$ExpectedFusedPrototypeHash = $ExpectedHashes['Content\RedMMO\Maps\RedPlanetGen_50km_FusedPrototype.umap']

function Assert-ProtectedHashes {
    param([string]$Phase)

    foreach ($Entry in $ExpectedHashes.GetEnumerator()) {
        $Path = Join-Path $ProjectRoot $Entry.Key
        if (-not (Test-Path -LiteralPath $Path)) {
            throw "$Phase protected artifact is missing: $Path"
        }
        $Actual = (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash
        if ($Actual -ne $Entry.Value) {
            throw "$Phase protected hash mismatch for $Path. Expected $($Entry.Value), got $Actual."
        }
    }
}

function Assert-LogContains {
    param(
        [string]$Pattern,
        [string]$Description
    )

    if (-not (Select-String -LiteralPath $Log -SimpleMatch $Pattern -Quiet)) {
        throw "Packaged fused smoke did not report $Description. Missing: $Pattern"
    }
}

function Assert-PackagedSourceCurrency {
    param([string]$ReadyMarker)

    $ExpectedMarker = "fused_prototype_source_sha256=$ExpectedFusedPrototypeHash"
    $MarkerLines = @(Get-Content -LiteralPath $ReadyMarker)
    if ($MarkerLines -notcontains $ExpectedMarker) {
        throw "Packaged fused source currency is unverified. Ready marker must contain exact line: $ExpectedMarker"
    }
}

function Assert-SpaceSceneryComposition {
    $SceneryLine = Select-String -LiteralPath $Log -Pattern 'Built scenery: stars=(\d+)/(\d+)/(\d+) decorativeAsteroids=(\d+)' |
        Select-Object -Last 1
    if (-not $SceneryLine) {
        throw 'Packaged fused smoke did not report the procedural star field and decorative asteroid belt.'
    }

    $Match = [regex]::Match($SceneryLine.Line, 'Built scenery: stars=(\d+)/(\d+)/(\d+) decorativeAsteroids=(\d+)')
    $DimStars = [int]$Match.Groups[1].Value
    $MediumStars = [int]$Match.Groups[2].Value
    $BrightStars = [int]$Match.Groups[3].Value
    $DecorativeAsteroids = [int]$Match.Groups[4].Value
    $TotalStars = $DimStars + $MediumStars + $BrightStars

    if ($TotalStars -ne 4200 -or $DimStars -le 0 -or $MediumStars -le 0 -or $BrightStars -le 0) {
        throw "Packaged fused smoke reported an invalid V3 star composition: dim=$DimStars medium=$MediumStars bright=$BrightStars total=$TotalStars."
    }
    if ($DecorativeAsteroids -ne 72) {
        throw "Packaged fused smoke reported $DecorativeAsteroids decorative asteroids; expected 72."
    }
}

try {
    if ([string]::IsNullOrWhiteSpace($Archive)) {
        $LatestArchiveFile = Join-Path $DataRoot 'BuildLogs\LatestPackage50kmArchive.txt'
        if (-not (Test-Path -LiteralPath $LatestArchiveFile)) {
            throw "Latest successful package pointer is missing: $LatestArchiveFile"
        }
        $Archive = (Get-Content -LiteralPath $LatestArchiveFile -Raw).Trim()
    }

    $Archive = (Resolve-Path -LiteralPath $Archive).Path
    $WindowsRoot = Join-Path $Archive 'Windows'
    $Executable = Join-Path $WindowsRoot 'Titan.exe'
    $Container = Join-Path $WindowsRoot 'Titan\Content\Paks\Titan-Windows.utoc'
    $MainData = Join-Path $WindowsRoot 'Titan\Content\Paks\Titan-Windows.ucas'
    $ReadyMarker = Join-Path $Archive 'REDMMO_PACKAGE_READY.txt'
    $ContainerList = "$Log.iostore.list.txt"

    Assert-ProtectedHashes -Phase 'Pre-smoke'

    foreach ($Path in @($Executable, $Container, $MainData, $ReadyMarker, $UnrealPak)) {
        if (-not (Test-Path -LiteralPath $Path)) {
            throw "Required packaged verification input is missing: $Path"
        }
    }

    # Path presence in IoStore cannot prove which workspace bytes were cooked.
    # Older archives without this package-time input marker fail closed.
    Assert-PackagedSourceCurrency -ReadyMarker $ReadyMarker

    & $UnrealPak $Container -List 2>&1 | Set-Content -LiteralPath $ContainerList
    if ($LASTEXITCODE -ne 0) {
        throw "UnrealPak failed to list the packaged IoStore container (exit $LASTEXITCODE)."
    }

    $RequiredContainerEntries = @(
        '../../../Titan/Content/RedMMO/Maps/RedPlanetGen_50km_FusedPrototype.umap',
        '../../../Titan/Content/RedMMO/Environment/DA_RED_Planet50Km_FusedHeightfield.uasset',
        '../../../Titan/Content/RedMMO/Environment/MI_RedClearWater.uasset',
        '../../../Titan/Content/RedMMO/Environment/M_RedStarSpriteMasked.uasset',
        '../../../Titan/Content/RedMMO/Environment/M_RedBabyBlueSurfaceSky.uasset',
        '../../../Titan/Content/SoStylized/Environment/Sky/BP_StylizedSky_Lite.uasset',
        '../../../Titan/Content/SoStylized/Environment/Sky/Meshes/SM_StylizedSkyDome.uasset',
        '../../../Titan/Content/ProjectilesVol1/Textures/T_Point5.uasset'
    )
    foreach ($RequiredEntry in $RequiredContainerEntries) {
        if (-not (Select-String -LiteralPath $ContainerList -SimpleMatch $RequiredEntry -Quiet)) {
            throw "Required fused packaged entry is missing: $RequiredEntry"
        }
    }

    $Arguments = @(
        '/Game/RedMMO/Maps/RedPlanetGen_50km_FusedPrototype',
        '-nullrhi',
        '-unattended',
        '-nosound',
        '-nosplash',
        '-benchmark',
        '-seconds=180',
        "-AbsLog=$Log",
        '-log'
    )
    $Process = Start-Process -FilePath $Executable -ArgumentList $Arguments -WindowStyle Hidden -PassThru
    if (-not $Process.WaitForExit(240000)) {
        Stop-Process -Id $Process.Id -Force -ErrorAction SilentlyContinue
        throw 'Packaged fused-prototype smoke exceeded the 240 second external timeout.'
    }
    $ExitCode = $Process.ExitCode
    if ($ExitCode -ne 0) {
        throw "Packaged fused-prototype smoke exited with code $ExitCode."
    }

    Assert-LogContains -Pattern 'UEngine::LoadMap Load map complete /Game/RedMMO/Maps/RedPlanetGen_50km_FusedPrototype' -Description 'fused map-load completion'
    Assert-LogContains -Pattern "PlanetGen: captured macro heightfield 'DA_RED_Planet50Km_FusedHeightfield' (257x257 x 6, surface masks=yes, authored blend 1.00, detail amplitude 1500 cm)." -Description 'authenticated fused macro capture'
    Assert-LogContains -Pattern 'PlanetGen: resolved 27 enabled terrain stamp(s).' -Description 'all 27 enabled terrain stamps'
    Assert-LogContains -Pattern 'PlanetGen: terrain mesh consumed authored surface masks' -Description 'a live terrain surface-mask consumer'
    Assert-LogContains -Pattern 'PlanetGen: built resident authored macro surface proxy (99846 vertices, 196608 triangles, 128 subdivisions/face, inset 75cm, collision off).' -Description 'the collisionless always-resident orbital land fallback'
    Assert-LogContains -Pattern 'EnsureAtmosphereAndClouds: soft orbital limb height=8.5km rayleigh=0.0450/2.15km bottomR=7.46' -Description 'the datum-adjusted eight-kilometre physical atmosphere'
    Assert-LogContains -Pattern 'EnsureSoStylizedOceanWater: applied project-authored spherical SoStylized water' -Description 'the authored spherical night-water presentation'
    Assert-LogContains -Pattern '(18721 vertices)' -Description 'the repaired 192-subdivision spherical water mesh'
    Assert-LogContains -Pattern 'EnsureHighFiveCloudVolumes: configured 12 evenly distributed atmosphere clouds' -Description 'twelve atmosphere-bounded High Five cloud volumes'
    Assert-LogContains -Pattern 'Surface sky fallback spawned: actor=Red_LocalStylizedSurfaceSkyFallback dome=SkyDome material=MID_M_RedBabyBlueSurfaceSky_' -Description 'the cooked stylized dome using the baby-blue surface material'
    Assert-SpaceSceneryComposition
    Assert-LogContains -Pattern 'Bound coherent moon fill' -Description 'the visible physical moon and moonlight binding'
    Assert-LogContains -Pattern 'LogExit: Game engine shut down' -Description 'clean engine shutdown'

    $FailurePattern = 'Fatal error:|Critical error:|LowLevelFatalError|Assertion failed:|Ensure condition failed|Unhandled Exception|EXCEPTION_ACCESS_VIOLATION|Bad export index|Out of memory|Out of video memory|bad allocation|ONNX Runtime error|GPU Crashed|D3D Device Removed|SkipPackage.*M_RedBabyBlueSurfaceSky|SkipPackage.*BP_StylizedSky_Lite|SkipPackage.*SM_StylizedSkyDome|Failed to find.*M_RedBabyBlueSurfaceSky|CDO Constructor.*M_RedBabyBlueSurfaceSky|Surface baby-blue sky material failed to load|Surface sky fallback unavailable: BP_StylizedSky_Lite did not load'
    $FailureMatches = Select-String -LiteralPath $Log -Pattern $FailurePattern
    if ($FailureMatches) {
        throw "Packaged fused-prototype smoke contains fatal/assert/ensure/unhandled/bad-export markers."
    }

    Assert-ProtectedHashes -Phase 'Post-smoke'
    Set-Content -LiteralPath $ExitFile -Value 0
    Write-Output "REDMMO_PACKAGED_FUSED_READY archive=$Archive log=$Log container_list=$ContainerList"
}
catch {
    Set-Content -LiteralPath $ExitFile -Value 1
    Write-Error $_
    exit 1
}
