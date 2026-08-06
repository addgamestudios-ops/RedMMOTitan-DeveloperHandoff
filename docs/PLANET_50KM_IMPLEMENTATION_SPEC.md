# RedMMOTitan 50 km seamless planet specification

Source design export: `C:/Users/user/Desktop/fortnite-maps-on-octosphere-planet-20260714.json`

The JSON is a 32-message design conversation. It is requirements input, not a height map, biome mask, or directly importable terrain file.

## Product definition

Build one continuous spherical world with no invisible walls, loading gates, or player-facing region borders. The 27 Fortnite-sized maps are **real square authoring inputs**, not merely density labels: each map can carry authored elevation, land/water intent, biome masks, and protected hubs. They overlap in tangent-local space and are fused into one seam-safe planetary height field before runtime streaming.

| Quantity | Target |
|---|---:|
| Circumference | 50.000 km |
| Datum radius | 7.957747 km / 795,774.715 cm |
| Diameter | 15.915494 km |
| Surface area | 795.774715 km2 |
| Macro authoring regions | 27 |
| Average authoring area | 29.473138 km2 |
| Equivalent square width | about 5.429 km |

The 27 authoring maps are distributed over the sphere with deterministic tangent frames. They own elevation and biome data as well as art direction, POI budgets, and production responsibility, but their source-square borders must never become collision, teleport, streaming, or visual boundaries.

## Corrected fused-square topology

A closed sphere cannot be built from eight or 27 equal square faces without singularities, overlap, or gaps. RED therefore separates **authoring topology** from **runtime topology**:

- Six square cube-map height fields (`+X`, `-X`, `+Y`, `-Y`, `+Z`, `-Z`) are the exact closed storage topology.
- Twenty-seven approximately 5.4 km square authoring maps are projected from local tangent frames onto that cube-sphere.
- Overlapping authoring maps are blended by deterministic normalized weights, with an explicit edge feather and stable priority for protected handcrafted areas.
- The fused six-face field is sampled for render vertices, extended normal samples, collision, water classification, foliage/PCG queries, radar, and distant-planet rendering.
- Runtime chunks are much smaller than either a cube face or an authoring map. Neither source-map edges nor cube-face edges are gameplay zones.

This is the buildable version of "place separate flat square maps around a sphere and fuse them together." The original production map and **playable Unreal checkpoint** remain unchanged: the checkpoint still has the noise sphere plus 27 metadata anchors and small constant-height hub stamps. A separate `RedPlanetGen_50km_FusedPrototype` now assigns the populated six-face height asset. Runtime startup proves both capture and a terrain-chunk consumer: authored land/biome samples project into per-vertex material-layer weights and the existing foliage climate contract. Focused headless PIE tests now prove cooked collision and runtime-mesh continuity across all 12 cube edges and all 8 corners, one authored patch feather, one live terrain-stamp feather, and four moving collision-ring waypoints. The fused prototype's physical ocean datum is calibrated to the source masks at `0 cm` (`SeaLevel=0.50`), with a six-face authored-coast scan and SoStylized water-sphere structural gate. A current-pawn shoreline gate samples the exact final stamped terrain field, validates visible crest topology/material, and traces the matching physical coast. A transient `WorldStatic` positive control plus 199 bounded current-pawn route sweeps prove the automated non-terrain blocker detector and sampled baselines. Later real-Chaos checkpoints prove the production ship's swept `260 cm` root sphere stops on exact active terrain at the cooked `+X/+Y` seam while preserving an earlier native `WorldStatic` hit, completes 12 high-speed edge crossings and 24 corner-neighborhood legs across every cube boundary, and depenetrates a deterministic `50 cm` initial seam overlap both when movement is requested and when an authoritative unpossessed ship receives zero input. Full rendered biome appearance, actual foliage/PCG placement, hands-on whole-world traversal, fitted hull/wing collision, packaged and multiplayer behavior, and visual shoreline approval are still open.

### Macro-biome target

The labeled planet reference supplied on 2026-07-14 defines the high-level mask grammar, not exact coast geometry:

- permanent polar caps at both poles;
- tundra transitioning into a northern boreal-forest belt;
- one recognizable major desert landmass rather than uniform sand everywhere;
- tropical belts, peninsulas, and island chains closer to the equatorial climate band; and
- navigable oceans that separate major player hubs and exploration regions.

This reference must be translated into the 27 editable land/height/biome source squares. It is not a directly importable heightmap, and it does not override the user-authored square maps.

### Tangent-patch source contract

The deterministic source profile lives at
`SourceArt/Planet50Km/AuthoringPatches/RED_PatchProfile.json` and is generated by
`Tools/planet_patch_compositor.py`.

- Patch IDs `0..26` reuse the existing `FPlanetRegionService` spherical-Fibonacci sites exactly.
- Each patch has a 542,891.680 cm full-authority core (one twenty-seventh of the
  795.775 km2 surface-area target) inside an 800,000 cm padded source raster.
- Raster `+U` is local east; row zero is the local-north edge.
- The 128,554.160 cm padding on each edge is a cubic smoothstep feather. Overlaps are
  accumulated in ascending patch ID and normalized; a zero total contribution is a bake error.
- A 0.20-radian center kernel prefers the nearest map smoothly. Optional per-pixel authority
  raises protected handcrafted ownership by as much as 256x, while integer priority contributes
  deterministic powers of two; neither mechanism creates a hard edge.
- A deterministic 500,000-direction coverage audit reported zero uncovered samples,
  minimum best contributor weight `0.1762824533`, and required full square support
  `731,246.206 cm`, leaving explicit margin inside the 800,000 cm source footprint.
- Patch rasters are source-art coordinates only. Their edges do not create collision,
  teleport, streaming, biome, or rendering boundaries.

### Verified source bake checkpoint

`Tools/generate_planet_authoring_patches.py` now materializes the source contract rather
than leaving it as metadata:

- exactly 27 tangent-local raster sets at the current 257 x 257 blockout resolution;
- one little-endian R16 height field, matching 16-bit PNG, land mask, RGBA biome mask,
  and protected-authority mask per source square;
- deterministic original RED blockout continents, island chains, ocean floor, mountain
  envelopes, desert, temperate, cold/mountain, and alien-biome weights;
- exactly six canonical PlanetGen cube faces baked only from those persisted source
  rasters; and
- fatal validation for a missing contributor, bad source hash, invalid resolution, or
  encoded edge/corner mismatch.

The persisted patch-raster data set hash is
`228E1CDAC65F0AFFB51101E8639AC65C57063FC4C72D74588D24A194A87504ED`. The resulting
six-face data set hash is
`AAE25CCA654D3D966C7AE3C5A00A911BA2576E67592D5B1443D9145D0BC2399A`. At 257 x 257,
all 396,294 face samples had contributors and all 3,076 shared edge/corner comparisons
matched bit-for-bit for height, land, and biome data. The source authoring CLI is fail-closed:
strict bake changes none of the 135 source files, accepting edits records exact parent/new
provenance, derived R16 and face publication are staged with rollback, and analytic regeneration
requires an explicit destructive flag. Thirty focused compositor and authoring-workflow tests
passed, including snapshot/edit/restore round-trip, invalid preflight inputs, transaction rollback,
tampered content-addressed backups, source changes during a bake, and concurrent editor saves.

The initial approved source snapshot is
`SourceArt/Planet50Km/AuthoringPatches/RevisionBackups/APPROVED_SOURCE_81F1E8E9D1C25BB8E9CF1D4E17423B2D81AF0DFE839CADEBB5569F408CBF75B6`.
The operator workflow is documented in `docs/PLANET_PATCH_AUTHORING_GUIDE.md`.

This source-pipeline result is now imported at
`/Game/RedMMO/Environment/DA_RED_Planet50Km_FusedHeightfield`. The constrained serial
`TitanEditor` rebuild succeeded, the importer authenticated both persisted data-set hashes,
and the resulting asset contains six height faces, six land faces, and six RGBA biome faces.
Its SHA-256 is
`412E26B75DAD95CE0EF4FA63BFF21CCA0EDB755B5D08BA1A4CFA3EEFEC06E562`. A separate fused
prototype map assigns it; no production map or rollback map was replaced.

Rollback hashes captured after the source bake:

- production `RedPlanetGen.umap`: `1DF9E6ED913A267875F1EF452F6ED51DAF337DBBAAE4C6EC3379EA6299346724`;
- isolated `RedPlanetGen_50km_Test.umap`: `DA5987012EEB8F550254F5FCF0F47F42B8F5E03428CF4881C83D8687537F6E7D`.

Fused prototype checkpoints:

- the current ascent-safe `RedPlanetGen_50km_FusedPrototype.umap` is
  `4C84D7752C87854C70987ED9988C64C124C577FBE1DE3DEF3CC826F81B0B6284`;
- `D:/RedMMOTitanWindowsData/BuildLogs/FixFusedAscentWater_20260719.log` records the
  intentional July 19 save as `changed=1`, emits that exact prototype hash, preserves production
  hash `1DF9E6ED...9346724` and protected-checkpoint hash `DA598701...7F6E7D`, and exits with zero
  errors;
- the unchanged authoring script records the intent of that save as disabling the global
  PlanetGen water sphere after it became an overhead shell during ascent. This is source/log
  provenance, not a decoded-property assertion about the binary package;
- the exact prior July 14 water-enabled fused bytes remain retained at
  `Content/RedMMO/Maps/Tests/RedPlanetGen_50km_FusedPrototype_Night_T03.umap` with hash
  `211429783F757F3CD8DE4A37B1E37B4A117125BF26EBFCBACF97CCFA9EFBE8D7`;
- the pre-water-calibration package remains retained outside Content at
  `D:/RedMMOTitanWindowsData/Rollback/BeforeCoastDatum_20260714/RedPlanetGen_50km_FusedPrototype.umap`
  with hash `A9C42C0D1B0429DD1018F00F0D2AB8A18F66C07291611964EFF5F9710F3B0C6A`;
- the immediate null-RHI `RedMMO.Planet.FusedTerrain` retry crashed in `NotNull.cpp` with
  `Null assigned to TNotNull` before any successful test-completion marker, so it is failed
  diagnostic evidence and does not validate the July 19 change;
- the current map asset later loaded in editor runtime and ran under real GPU for the bounded July 21 sky/cloud
  capture, but that run did not decode or accept terrain, shoreline, or water behavior;
- the default July 17 packaged archive predates this save and its ready marker records only paths,
  not the fused input hash. The packaged verifier therefore treats it as currency-unverified and
  now fails closed until a future fresh archive records
  `fused_prototype_source_sha256=4C84D7752C87854C70987ED9988C64C124C577FBE1DE3DEF3CC826F81B0B6284`;

The remaining acceptance bullets in this checkpoint section apply to the retained July 14
water-enabled bytes, not to the current July 19 ascent-safe package:

- a fresh editor process reported `changed=0` and exited cleanly after generated Unreal/Epic
  caches were redirected from the full C: drive to D:;
- a separate clean Unreal process reloaded all six height, six land, and six biome faces at
  `257x257`, with 66,049 samples per face and the expected package SHA-256;
- game-mode null-RHI startup captured `surface masks=yes`, authored blend `1.00`, detail amplitude
  `1500 cm`, resolved 27 stamps, loaded the prototype, and returned exit code `0`;
- the final `TitanEditor` build compiled and linked worker-safe projection into the established
  vertex-color/UV1 material contract and both foliage paths;
- all four `PlanetGen.MacroHeightfield` automation tests passed, including linear vertex-mask
  encoding, authored-ocean suppression, height-water preservation, and biome-channel mapping; and
- a final null-RHI smoke logged terrain consumption for 1,024 vertices with 56 cold-dominant
  authored samples while `MI_PlanetBiome_RED` was active, then exited `0` without fatal, assert,
  or ensure markers; and
- a focused headless PIE automation waited for real Chaos complex collision, passed 13 probes
  across the `+X`/`+Y` cube-face seam, matched 193 shared runtime vertex pairs within
  `0.028756 cm` with minimum normal dot `0.999207199`, passed 25 authored patch-feather probes
  and 8 live stamp core/feather/outside probes, and found no lifted PlanetGen blocker on those
  sampled paths;
- a moving-source regression kept the deterministic 21-chunk collision ring across four
  waypoints, preserved all 48 retained-chunk hits, and passed 75 grounded plus 72 lifted
  route probes; and
- the strict water-datum test scanned all 396,294 fused capture samples across all six faces,
  found zero binary or high-confidence land/ocean violations, bounded 616 gray feather samples
  to `347.447 cm`, and verified the collision-free 2,145-vertex SoStylized water sphere at the
  `795,774.688 cm` radius with `0.0581 cm` maximum radial error;
- the resolved-surface audit reconstructed all 27 sorted stamps independently and matched the
  public runtime sampler across 351 samples with `0.0000 cm` maximum error; the stamps produced a
  measurable `3,579.356 cm` maximum surface effect; and
- current-pawn headless PIE built 37 shoreline crest segments (148 vertices / 222 indices),
  validated non-degenerate outward visible winding and the SoStylized material, then matched eight
  real PlanetGen collision probes within `169.173 cm` with minimum normal dot `0.992389`.

This is contract plus bounded headless runtime-collision, resolved shoreline, and water-datum evidence. It does not
replace full rendered biome approval, actual foliage/PCG placement, hands-on or fast-vehicle
traversal, packaged/cooked client and multiplayer checks, complete invisible-wall coverage, or
visual shoreline approval under the normal rendered day/night presentation.

Evidence:

- `D:/RedMMOTitanWindowsData/BuildLogs/TitanEditor_MacroHeightfieldImporter_SerialRetry_20260714.log`
- `D:/RedMMOTitanWindowsData/BuildLogs/TitanEditor_MacroMasks_LinkRetry_20260714_175959.log`
- `D:/RedMMOTitanWindowsData/BuildLogs/PlanetGen_MacroHeightfield_Automation_Retry_20260714_181126.log`
- `D:/RedMMOTitanWindowsData/BuildLogs/FusedMacroHeightfield_Import_20260714_181346.log`
- `D:/RedMMOTitanWindowsData/BuildLogs/FusedMacroHeightfield_FreshVerify_20260714_182210.log`
- `D:/RedMMOTitanWindowsData/BuildLogs/FusedPrototype_RuntimeSmoke_20260714_182328.log`
- `D:/RedMMOTitanWindowsData/BuildLogs/VerifyFused50kmPrototype_AfterRedirect_20260714.log`
- `D:/RedMMOTitanWindowsData/BuildLogs/SmokeFused50kmPrototype_ExitCode_20260714.log`
- `D:/RedMMOTitanWindowsData/BuildLogs/TitanEditor_SurfaceMaskConsumer_FinalFix_20260714_195516.log`
- `D:/RedMMOTitanWindowsData/BuildLogs/PlanetGen_SurfaceMaskConsumer_FinalFix_20260714_195642.log`
- `D:/RedMMOTitanWindowsData/BuildLogs/FusedPrototype_SurfaceMaskConsumer_FinalFix_20260714_195909.log`
- `D:/RedMMOTitanWindowsData/BuildLogs/TitanEditor_FusedTerrainContinuity_Final_20260714.log`
- `D:/RedMMOTitanWindowsData/BuildLogs/FusedTerrainContinuity_Final_20260714.log`
- `D:/RedMMOTitanWindowsData/AutomationReports/FusedTerrainContinuity_Final_20260714/index.json`
- `D:/RedMMOTitanWindowsData/BuildLogs/TitanEditor_FusedWaterDatum_Strict_20260714.log`
- `D:/RedMMOTitanWindowsData/BuildLogs/FusedWaterDatum_Strict_20260714.log`
- `D:/RedMMOTitanWindowsData/AutomationReports/FusedWaterDatum_Strict_20260714/index.json`
- `D:/RedMMOTitanWindowsData/BuildLogs/FusedTerrainContinuity_AfterSeaDatum_20260714.log`
- `D:/RedMMOTitanWindowsData/BuildLogs/VerifyFusedPrototype_CoastDatum_Idempotent_20260714.log`

## Required architecture

```text
Planet profile (one source of scale and seed truth)
  -> 27 tangent-local square authoring maps
       -> elevation, land mask, biome masks, protected hubs
       -> deterministic overlap and feather rules
  -> six-face fused macro height field
  -> spherical terrain and collision streamer
  -> deterministic surface query
       -> 27 blended authoring regions
       -> biome/climate weights
       -> ocean/lake/river state
       -> slope/normal/elevation
       -> hub/road/manual-placement reservations
  -> many small runtime cells
       -> handcrafted hubs and POIs
       -> approved PCG filler
       -> encounters, resources, and creatures
```

### Terrain substrate

- Use the existing PlanetGen cube-sphere mesh/streamer as the first runtime substrate, but replace its noise-only macro shape with the fused authored macro height field.
- Keep PlanetGen detail noise as a low-amplitude, nondestructive layer over authored continents and mountains; it must not decide the primary coastline.
- Maintain a pinned project-local fork; never make the project depend on an untracked edit inside the UE installation.
- Use radial gravity and the same planet center/radius for terrain, water, atmosphere, clouds, ships, radar, spawn, moon logic, and surface effects.
- Keep an always-available coarse terrain fallback under detailed chunks so slow generation cannot expose holes or invisible walls.
- Runtime chunks are smaller than authoring regions. Authoring regions do not load/unload as single pieces.

### Determinism

Every procedural decision derives from stable keys such as:

```text
Hash(WorldSeed, GeneratorVersion, RegionId, FeatureType, RuntimeCellId)
```

Do not use a random stream whose results depend on which chunk loaded first. Server and clients must resolve the same terrain, region, biome, water, and reservation samples.

### Square authoring maps and flat-ish hubs

Each authoring map is a square height/mask source in a tangent frame. Its full 5.4 km footprint is not forced planar: its samples are reprojected radially onto the sphere so large-scale curvature remains correct. Only selected hub/build footprints inside a map are flattened.

Do not flatten an entire 5.4 km authoring map. On a 7.96 km radius planet, that would visibly fight the planet curvature. Preserve the map's relative height field while wrapping it onto the sphere. Flatten only hub/build footprints, normally 250-500 m radius, and blend them into the radial terrain over a geodesic feather.

Use tangent coordinates for authoring and project them to the sphere with an exponential-map transform:

```text
Direction = CenterDir * cos(distance / Radius)
          + TangentDir * sin(distance / Radius)
Position  = PlanetCenter + Direction * (Radius + SurfaceHeight)
```

Large roads, walls, imported maps, and modular structures must be segmented and conformed rather than placed as one rigid multi-kilometre object.

## First smoke profile

The first test intentionally favors stability over terrain detail:

| Setting | Value |
|---|---:|
| PlanetRadius | 795,774.715 cm |
| GravityRadius | 1,591,549.431 cm |
| TileSize | 200,000 cm |
| MaxChunksPerFace | 8 |
| Resolution | 32 |
| Terrain preset | Smooth |
| MinHeight | -30,000 cm |
| MaxHeight | 30,000 cm |
| MaxMountainHeight | 30,000 cm |
| Rollback-checkpoint SeaLevel | 0.45 |
| Fused authored SeaLevel | 0.50 = source-mask sea height 0 cm |
| Rollback/checkpoint water | enabled |
| Current fused prototype global water sphere | disabled by the July 19 ascent-safety authoring intent; rendered shoreline/water acceptance pending |
| Foliage/grass | disabled |

This profile is a rollback-safe test, not the replacement production map.

## Implementation modules

### P0 - Preserve and isolate

- Keep the current playable map unchanged.
- Preserve `/Game/RedMMO/Maps/RedPlanetGen_50km_Test` as the rollback checkpoint and duplicate
  that checkpoint as `/Game/RedMMO/Maps/RedPlanetGen_50km_FusedPrototype` for fused-field work.
- Add one named 50 km profile and log its revision at runtime.
- Retire the old eight-flat-face `RedOctosphere` illusion from the test path.

### P1 - Correct terrain streaming

- Make view distance control an angular load cap.
- Union streaming sources from every player, occupied ship, landing target, and teleport destination.
- Add load/unload hysteresis and velocity look-ahead.
- Add an async build generation/key token so recycled chunks cannot receive stale results.
- Bound the actor pool and generation/upload/collision-cook work per frame.
- Generate expensive collision only in a near ring.
- Add coarse-to-fine LOD with edge stitching or skirts.

### P2 - Shared surface and 27 regions

- Create 27 seeded spherical-Fibonacci sites.
- Resolve nearest ownership and blended great-circle weights.
- Expose elevation, normal, slope, temperature, moisture, biome weights, water state, region weights, and reservation masks from one surface query.
- Add a debug overlay, but keep region borders authoring-only.

#### M03 generic geodesic hub stamps

The earlier region-anchor checkpoint did not alter terrain. The implemented terrain-stamp slice
lives in the pinned PlanetGen fork and remains generic so PlanetGen never depends on RedMMO:

- Add reflected terrain-stamp authoring data to `ACLMPlanet`, then resolve it on the game thread
  into sorted, plain-data captures before any asynchronous chunk build.
- Define target height as radial altitude above the datum sphere, never world Z or normalized
  height. Resolve each automatic target once from the ordinary noise plus beach pipeline.
- Compute stamp distance with great-circle arc length. Keep the core constant and use a smooth
  geodesic feather; overlapping stamps combine by normalized weights in stable-ID order.
- Apply the same pure modifier to main mesh vertices, extended normal-border samples, and foliage
  samples. Collision must continue to use the same stamped mesh as rendering.
- Pass owned value copies to chunk workers. Never capture an anchor, `ACLMPlanet`, a UPROPERTY
  array, or another UObject across the async boundary; retain the existing generation-token gate.
- Populate 27 stamps in `RedPlanetGen_50km_Test`, keyed by region index and sourced from the
  deterministic site/core/feather metadata. The fused prototype inherits the same ordered stamps;
  keep both rollback maps byte-identical.
- Acceptance requires pure continuity/order/no-op/seam tests, a fresh-process idempotency pass,
  clean runtime initialization with 27 stamps, and traced traversal across at least one feather.
  Hands-on visual and vehicle traversal approval are still required before M03 can be complete.

Verified implementation checkpoint (2026-07-14):

- `TitanEditor` compiled successfully with the pinned PlanetGen terrain-stamp implementation.
- `RedMMO.Planet.TerrainStamp.DeterministicGeodesicMath` passed with automation exit code `0`,
  covering deterministic great-circle distance, influence continuity, stable overlap ordering,
  disabled/invalid no-op behavior, and representative cube-face seam symmetry.
- The first isolated-map authoring run reported `count=27 changed=1` and reused all 27 managed
  region anchors. A second fresh-process run reported `count=27 changed=0`, confirming
  deterministic, idempotent stamp authoring.
- The isolated 50 km runtime smoke resolved 27 enabled terrain stamps and exited with status `0`
  without fatal, assert, ensure, or bad-export errors.
- Focused headless PIE automation waited for real cooked complex collision and traced the live
  fused prototype across one cube-face seam, authored patch 13's feather, and terrain stamp 13's
  core/feather/outside range. All 46 probes passed; 193 shared runtime vertex pairs matched within
  `0.028756 cm`, and lifted sweeps found no PlanetGen blocker on the sampled paths.
- A separate full-topology PIE gate cooked the complete 6x6x6 fixture once and verified all 12
  cube edges plus all 8 corners. Every one of the 2,244 canonical edge pairs and 24 three-face
  corner pairs matched; maximum edge separation was `0.090703 cm`, minimum edge normal dot was
  `0.999494314`, and all corner positions matched at the reported precision. It also passed 144
  edge support probes, 48 corner support probes, 60 pawn-capsule edge sweeps, and 24 closed-corner
  sweeps. The capsule gate ignores outward floor contacts but fails penetration and tangent/side
  contacts, so it checks the terrain-wall failure mode rather than ordinary ground support.
- The representative seam, patch-feather, stamp-feather, and moving-stream routes now run the same
  current-pawn capsule. One transient `WorldStatic` Pawn-blocking box was detected as the exact
  positive-control component and removed; all 115 baseline segments then passed (43 static and 72
  moving). Together with the full-topology routes, bounded headless coverage is 199 pawn sweeps.
- A read-only production-map audit reported `count=0 terrain_stamps=0`; the production map stayed
  byte-identical at SHA256
  `1DF9E6ED913A267875F1EF452F6ED51DAF337DBBAAE4C6EC3379EA6299346724`.

Evidence logs:

- `D:/RedMMOTitanWindowsData/BuildLogs/TitanEditor_M03HubStamps_20260714.log`
- `D:/RedMMOTitanWindowsData/BuildLogs/TerrainStampAutomation_20260714.log`
- `D:/RedMMOTitanWindowsData/BuildLogs/Create50kmHubStamps_First_20260714.log`
- `D:/RedMMOTitanWindowsData/BuildLogs/Create50kmHubStamps_Idempotent_20260714.log`
- `D:/RedMMOTitanWindowsData/BuildLogs/Smoke50kmHubStamps_20260714.log`
- `D:/RedMMOTitanWindowsData/BuildLogs/AuditProductionHubStamps_20260714.log`
- `D:/RedMMOTitanWindowsData/BuildLogs/TitanEditor_FusedTerrainContinuity_Final_20260714.log`
- `D:/RedMMOTitanWindowsData/BuildLogs/FusedTerrainContinuity_Final_20260714.log`
- `D:/RedMMOTitanWindowsData/AutomationReports/FusedTerrainContinuity_Final_20260714/index.json`
- `D:/RedMMOTitanWindowsData/BuildLogs/TitanEditor_AllCubeBoundaries_20260715_final.out.log`
- `D:/RedMMOTitanWindowsData/BuildLogs/FusedAllCubeBoundaries_20260715_final.log`
- `D:/RedMMOTitanWindowsData/AutomationReports/FusedAllCubeBoundaries_20260715_final/index.json`
- `D:/RedMMOTitanWindowsData/AutomationReports/FusedContinuity_AfterAllCubeBoundaries_20260715/index.json`
- `D:/RedMMOTitanWindowsData/BuildLogs/TitanEditor_PawnRouteWorldStatic_20260715.out.log`
- `D:/RedMMOTitanWindowsData/AutomationReports/FusedContinuity_PawnRouteWorldStatic_20260715/index.json`
- `D:/RedMMOTitanWindowsData/AutomationReports/FusedAllCubeBoundaries_AfterPawnRouteWorldStatic_20260715/index.json`

This is a verified code, authoring, and bounded headless runtime-collision checkpoint, not M03
completion. Hands-on whole-world invisible-wall traversal, visual approval of hub flattening and
source-map blending, packaged/multiplayer behavior, and water/coastline agreement remain open
acceptance gates. The test also does not approve terrain-build or streaming performance; 27-stamp
sampling cost remains a profiling gate for M04.

The exact PlanetGen-only active-terrain line/sphere/capsule/oriented-box API now walks past unrelated
`WorldDynamic` blockers and deterministically returns the exact owned procedural chunk. Real cooked
collision coverage includes a 37-degree rotated capsule and stable repetition
(`ActiveTerrainQuery_Capsule_20260715_0440`, plus the post-capsule five-test fused regression).
The later box gate uses rotation-aware candidate bounds and a `1100 x 900 x 300 cm` hull-sized box;
direct and adapter sweeps matched component, key `(0,5,2)`, and distance `79751.382812 cm` across the
cooked seam (`ActiveTerrainBox_AcceptanceRetry_20260715_134509`). The same gate rejects a
finite-component quaternion whose magnitude overflows before it can reach Chaos.

The shared `RedPlanetTerrainQuery` adapter is also integrated at actor level. Ship landing, parking,
exit probes, void recovery, and forward governor paths; shuttle landing, terrain clamp, and camera
clearance; and the inherited mini-fighter path now distinguish an exact PlanetGen hit from a
matching-planet miss and use legacy `WorldStatic` fallback only when no matching PlanetGen actor
exists. `ShipPlanetTerrainQuery_Focused_20260715_0615` passed with a deliberately closer dynamic
blocker on the route, and `ShipPlanetTerrainQuery_Regressions_20260715_0635` retained all five fused
runtime tests (`5/5 Success`, failed `0`).

The next filtered physical checkpoint now covers the production ship's swept `260 cm` root sphere.
`URedShipMovementComponent::MoveUpdatedComponentImpl` merges exact owned active-terrain contact with
native movement so a closer generic `WorldDynamic` blocker is ignored while an earlier
`QueryAndPhysics` `WorldStatic` component still wins. Local controlled flight and
server-authoritative remote flight share `MoveWithPlanetCollision`. Focused real-Chaos PIE stopped
the actual root transform on the cooked `+X/+Y` seam with the same exact-query contact data; the
native static-wall control retained its component and `3400.000 cm` hit distance. The focused test
and the post-change five-test fused regression both exited `0`.

The next headless checkpoint moves that same production root through every parametric cube
boundary. It performs one constant-radius step across each of the 12 edges and a three-leg signed
X/Y/Z loop at each of the 8 corner neighborhoods. All 36 exact PlanetGen preflights returned clear;
all 12 edge moves, all 24 corner legs, and all 8 loops completed through the shared production
mover. Maximum endpoint error was `0.000000 cm` and minimum route speed was `25993.982 cm/s`.
`RuntimeAllCubeBoundaries` and the subsequent five-test fused prefix both completed `Success` with
exit `0`.

This remains root-sphere headless acceptance, not complete vehicle acceptance. The attached runtime
body/deck/wing boxes still teleport with the swept root. The exact API now accepts oriented boxes,
but production movement still lacks per-piece fitted-hull/wing compound sweeps. Landing, exit, packaged
rendered traversal, and two-client authority/replication tests remain required before the acceptance
gate can close.

The movement-triggered initial-penetration gate is verified. After the first attempt was blocked by
system commit pressure, the constrained serial retry built successfully with exit `0`. Focused
real-Chaos PIE embedded the production `260 cm` root `50.007141 cm` into the active `+X/+Y` seam,
repeated the same owned-chunk MTD four times, corrected `50.132141 cm` outward, completed the full
`100.000549 cm` tangential `SafeMove` with `0.000000 cm` endpoint error, and ended on a clear exact
probe (`RED_SHIP_INITIAL_OVERLAP_PASS`, `Success`, errors `0`). The five-test fused regression then
passed five `Success`, failed `0`, errors `0`, with no fatal/assert/ensure signatures. The four
protected hashes remain unchanged. This validates the existing production movement-triggered path
without a production movement-code change.

The passive zero-input root-sphere gate is now also verified. Production movement performs a
throttled authority-only exact zero-length sweep before its controller early return, skips attached
craft, and applies one bounded MTD to a stationary penetrating sphere/capsule root. The latent PIE
fixture enabled only the unpossessed production movement component, held the analytic datum fallback
below the authored overlap, and observed actual world ticks beyond the second 0.1-second probe.
`RED_SHIP_PASSIVE_ZERO_INPUT_PASS` reported 16 ticks, `50.007141 cm` penetration,
`50.132141 cm` expected/observed outward correction, `0.000546 cm` tangent displacement,
`0.000000 cm` expected error and settle drift, and a final `NoHit`. Focused and five-test regression
reports passed with failed `0`, errors `0`, exit `0`; all four protected hashes remain unchanged.
This does not yet prove fitted hull boxes, landing/exit, packaged behavior, or client replication.

The oriented-box query primitive is now separately verified. A `1100 x 900 x 300 cm` asymmetric
box, tangent-aligned then rotated `37 degrees`, passed the exact active-terrain query at the cooked
`+X/+Y` seam while a nearer arbitrary `WorldDynamic` component was ignored. The direct PlanetGen
path and `RedPlanetTerrainQuery` adapter selected the same owned component/key and identical hit
distance, and eight repeats were stable (`RED_FUSED_ACTIVE_TERRAIN_BOX_PASS`). This is deliberately
not wired into movement yet: transforming and selecting the earliest contact from multiple attached
hull pieces, preserving native `WorldStatic` precedence, rotation-only contacts, and box initial
overlaps require their own compound-movement acceptance.
The target-candidacy portion of the candidate-AABB broadphase is now independently verified. A
query-only control temporarily restores the selected cooked chunk to raw `BoundsScale=1`, places the
rotated box centre outside the target's raw and naïve unrotated-expanded bounds but inside only the
rotation-aware expansion, proves a real start penetration with a raw zero-length Chaos sweep, and
requires PlanetGen to select the same target/key eight times. The resulting marker is
`RED_FUSED_ACTIVE_TERRAIN_BOX_BROADPHASE_PASS axis=2 side=1 margin_cm=5.0`; focused acceptance and the
five-test fused regression both pass with errors `0` and exit `0`. Neighbor chunks retain their
production `BoundsScale=2`, so this proves the intended target could not be accepted under the old
candidate formula; it does not claim the query centre misses every active chunk bound. Per-piece
compound movement, native-contact ordering across all pieces, rotation-only contacts, and production
box-overlap recovery remain separate acceptance gates.

The fitted-box initial-overlap query primitive is now separately accepted. A production-sized
`1100 x 900 x 300 cm` rotated box embedded `50.000 cm` at the cooked seam produced one finite MTD
through raw Chaos, direct PlanetGen, and the project adapter. Eight repeats preserved its
component/key, `50.006725 cm` depth, and normal; one bounded `52.006725 cm` correction then made the
same exact zero-length query return `NoHit`
(`RED_FUSED_ACTIVE_TERRAIN_BOX_MTD_PASS`, focused `Success`, errors `0`, exit `0`). The five-test
fused prefix also remains green. This is only an MTD query/clearance primitive.

The adjacent-contact query handoff is now accepted. From the clear pose, the deterministic `100 cm`
tangent/ownerward request preserves primary key `(0,5,2)` and contacts adjacent key `(2,0,3)` after
`3.936044 cm`, with `start_penetrating=0` and `depth=0`. Raw Chaos, direct PlanetGen, and the adapter
agree; eight repetitions preserve component, key, `FaceIndex`, time/distance, location/impact, and
normal. `RED_FUSED_ACTIVE_TERRAIN_BOX_ADJACENT_CONTACT_PASS` is recorded in
`D:/RedMMOTitanWindowsData/AutomationReports/ActiveTerrainBoxAdjacentContact_Acceptance_20260715_163349/index.json`,
and the five fused runtime regressions remain `Success` with no fatal/assert/ensure signatures.

This is deterministic two-contact query history, not fitted-hull traversal.

The production-derived live fighter query is now also accepted. The fixture loads and transiently
spawns `BP_RedModularStarSparrow`, independently reconstructs its 29 visible modular mesh bounds,
and matches the production `RuntimeHullCollision` centre `(203.80,0.00,88.02) cm` and half-extents
`(746.67,668.38,220.54) cm`. Raw Chaos, direct PlanetGen, and the adapter preserve one complete owned
contact on key `(0,5,2)` across eight repeats. In a nose-radial attitude, projected live-box support
predicts `282.872101 cm` lead over the root sphere and the real queries observe `284.000000 cm`.
Focused and five-test fused acceptance are `Success`, the transient actor is never moved or saved,
and protected hashes remain unchanged.

This remains query-only. The next movement gate must apply one bounded whole-actor translation from
the live fitted-box contact while preserving nearer native `WorldStatic` precedence. Production
rotation, multi-piece contact arbitration/manifold response, and box-overlap recovery remain open.

The bounded test-only translation gate is now accepted. Native collision uses
`UWorld::ComponentSweepMulti` on the actual registered `RuntimeHullCollision`, so the result depends
on the live `Vehicle` response container: a generic `WorldDynamic` control at `24.999882 cm` is
ignored, while a `WorldStatic` control at `49.999882 cm` wins over the exact terrain contact at
`99.985832 cm`. With the static control disabled, exact terrain key `(0,5,2)` wins; one `2 cm`
pullback moves the whole transient actor `97.985832 cm`, including the hull and a visible modular
mesh, without changing rotation or relative fit. The final exact box pose is clear and eight
pre-move repeats are deterministic.

Evidence is
`D:/RedMMOTitanWindowsData/AutomationReports/ActiveTerrainLiveFighterHullTranslation_First_20260715_144115/index.json`
and
`D:/RedMMOTitanWindowsData/AutomationReports/ActiveTerrainLiveFighterHullTranslation_Regressions_20260715_144115/index.json`;
the focused test and all five fused regressions are `Success`, and protected hashes are unchanged.
This does not yet alter playable movement. The next production slice must expose one typed,
fit-ready translation envelope to `URedShipMovementComponent`, preflight the live box against native
collision and exact terrain at fixed rotation, and still translate the root through the existing
movement path. Box start-overlap recovery, rotation, and multiple hull pieces remain excluded.

That production translation slice is now accepted in source/runtime. `ARedShip` publishes its typed
fitted box only after the complete virtual fit returns success, which also fixes envelope wiring for
`ARedMiniFighter`'s override. For supported non-overlapping fixed-rotation moves, the live box's native
`Vehicle` mask arbitrates with exact owned PlanetGen terrain; a clear fitted box is authoritative and
only the root is moved. The real-Chaos fixture records static raw/moved distances
`49.999882/47.999882 cm` and terrain raw/moved distances `99.985832/97.985832 cm`, with clear root
counterfactuals. Focused and all five fused tests are `Success` in
`D:/RedMMOTitanWindowsData/AutomationReports/ProductionFittedHullTranslation_Focused_20260715_185444/index.json`
and
`D:/RedMMOTitanWindowsData/AutomationReports/ProductionFittedHullTranslation_Regressions_20260715_185621/index.json`.
Rotation changes, fitted-box start-overlap recovery, multi-piece manifold response, child query-event
dispatch, packaged-client behavior, and hands-on visual traversal are not claimed by this slice.

### P3 - One vertical slice

- One 250-500 m protected hub core.
- One road/trail leaving the hub.
- One shoreline/ocean test and one local lake/river prototype.
- Two approved wilderness recipes from user-selected packs.
- One ecology-driven creature/resource rule.
- Two-client traversal across internal cells with no hole, wall, or teleport.

### P4 - Handcrafted content streaming

Use UE 5.8 World Partition Runtime Hash Set with a 3D grid for handcrafted actors after the terrain test is stable. PlanetGen terrain keeps its spherical streamer; World Partition streams hubs, props, encounters, local dressing, and navigation patches.

## Acceptance gates

The 50 km test is not complete until:

- two clients can stand on opposite sides while terrain remains bounded and deterministic;
- a fast ship, including its fitted hull, crosses terrain seams in packaged play without holes, walls, or stale collision;
- exit/teleport waits for local collision readiness instead of snapping to a fallback surface;
- ocean, atmosphere, gravity, clouds, radar, moon, and spawn share the same planet frame;
- region changes are invisible during ordinary traversal;
- a changed seed never deletes protected manual POIs;
- the current production map can be restored by selecting the old map/profile, not by reverting source files.

## External mini-map reference intake

The supplied Sketchfab [`Heightmap Mini Map Fortnite`](https://sketchfab.com/3d-models/heightmap-mini-map-fortnite-b268c76c06b8425f8cafb57da58feda4) model is a useful scale and landform
blockout reference, but it is not approved shipping terrain. The listing exposes a downloadable
524,300-triangle / 263,200-vertex mesh under CC Attribution and asks that it not be reposted.
Because the work is explicitly presented as Fortnite-derived, the uploader's ability to license
the underlying landform is not established by the listing alone.

- Keep any downloaded copy in a non-shipping `Quarantine/ReferenceOnly` folder.
- Preserve the author, listing URL, license text, download date, and original archive unchanged.
- Use it to study island scale, coast-to-interior proportions, route density, and height bands.
- Do not copy its identifiable coastline, POIs, textures, materials, names, or Fortnite assets.
- Rebuild an original RED heightfield from the project JSON and mood-board biome grammar.
- Only a project-owned derived heightmap that no longer reproduces protected Fortnite layout may
  be promoted into the 50 km test.

## Explicit non-goals for the first pass

- Do not populate all 27 regions.
- Do not copy or ship Fortnite terrain/IP; external references are scale/composition aids only.
- Do not enable automatic foliage before the user approves the pack palette.
- Do not claim production LOD, hydrology, navigation, or multiplayer readiness from a visual-only sphere.
