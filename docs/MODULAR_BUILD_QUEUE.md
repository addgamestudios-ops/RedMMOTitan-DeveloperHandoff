# RedMMOTitan modular build queue

The machine-readable queue is [`Build/Automation/redmmotitan_module_queue.json`](../Build/Automation/redmmotitan_module_queue.json).

## Scheduling behavior

- A module is `completed` only after its listed acceptance tests have evidence.
- If the same blocker produces no meaningful progress for about 10 minutes, record the blocker, set the module to `incomplete_retry`, and continue with the next independent module.
- After each forward pass, revisit `incomplete_retry` modules whose dependencies or environment changed.
- `awaiting_input` does not stop independent work. The alien mood board has now arrived, so its art taxonomy and generation pipeline are queued without blocking planet, combat, water, or packaging work.
- Preserve user assets and unrelated dirty work. Never solve a blocked module by deleting or resetting user changes.

## 50 km planet interpretation

The supplied JSON is an exported design conversation, not a terrain heightmap or biome-data file. Its actionable target is:

- one seamless 50 km circumference planet;
- radius `7.957747 km` (`795774.715 cm` in Unreal units);
- about `795.775 km2` total surface area;
- 27 square authoring-map inputs averaging `29.473 km2` each;
- locally flat hub/build areas that blend continuously into spherical terrain;
- authoring regions and streaming cells are never gameplay zones;
- no invisible walls or border teleports;
- handcrafted hubs protected from seeded PCG wilderness;
- deterministic oceans, deserts, fields, rivers, lakes, creatures, and resources;
- user-controlled pack selection and hand placement before any new foliage pass.

The requested 27 maps are actual tangent-local square height/mask inputs on one continuous surface. They are not 27 disconnected planes: they overlap and fuse into six seam-safe cube-map height fields, which PlanetGen subdivides into many smaller runtime chunks. The current checkpoint has only anchors and small flatten stamps; it does not yet contain those 27 authored heightmaps.

Eight square faces cannot close a sphere cleanly. An octahedron has eight triangular faces. For square heightmap authoring, the exact closed topology is six cube faces; the 27 user-facing maps are projected and baked across those faces so their borders never become gameplay seams.

## Alien asset-gap workflow

For the supplied mood board:

1. Extract silhouette families, scale, palette, surface language, and biome roles.
2. Search installed Fab packs for close matches.
3. Put unresolved items on a small generation list; do not generate duplicates indiscriminately.
4. Use Meshy or Tripo for individual missing assets.
5. Validate every candidate for rights, topology, LODs, collision, pivot, centimeters, material slots, wind deformation, Nanite suitability, and target performance.
6. Import accepted assets into a quarantined review folder first.
7. Promote approved meshes into hand-placement and PCG palettes with explicit biome tags.

## Verified package checkpoint

The corrected Windows Development package completed build, cook, stage, pak, IoStore, and archive successfully. Its IoStore listing contains both `RedPlanetGen.umap` and the isolated `RedPlanetGen_50km_Test.umap`, plus `NS_BeamOnly_02` and its cooked dependencies.

Both packaged maps completed null-RHI launch smokes and clean shutdowns without fatal, assert, ensure, or bad-export errors. The isolated map reported the 50 km datum (`surfaceRadius=795775cm`), while the production map retained its existing `surfaceRadius=600000cm`. Runtime initialization also reported the moon fill, star/asteroid scenery, and SoStylized night-water configuration.

Evidence:

- `D:/RedMMOTitanWindowsData/BuildLogs/Package50km_20260714_035718.log`
- `D:/RedMMOTitanWindowsData/BuildLogs/Package50km_20260714_035718.log.iostore.list.txt`
- `D:/RedMMOTitanWindowsData/BuildLogs/PackagedSmoke50km_20260714.log`
- `D:/RedMMOTitanWindowsData/BuildLogs/PackagedSmokeProduction_20260714.log`

This checkpoint does not complete the related modules. Null-RHI smoke does not prove rendered grapple alignment, hands-on night-scene appearance, octosphere seam traversal, flat hubs, region anchors, finished biomes, or multiplayer host/join behavior.

## Latest M00 night-water retry

M00 remains `incomplete_retry` at retry 23. The project now compiles with the verified
one-sided exterior water-sphere winding, and the focused winding automation passes. The F7
test camera also exposes substantially more of the shoreline. A clean RTX 3080 D3D12 run
removed the former cyan/white shell failure, but did **not** pass presentation: the ocean reads
dark brown/black, settled water-region animation above two color levels measured only `0.2401%`,
no lapping crest was visible, and the orbit view had no readable blue ocean. The next bounded
retry is a project-owned radial Single Layer Water material with normalized or angle-corrected
purchased normals, followed by a radial-safe shoreline crest. The oversized blue atmosphere
ring remains an M06 issue rather than a water-material acceptance result.

Evidence:

- `D:/RedMMOTitanWindowsData/Diagnostics/NightWater_T04_RadialV2_20260719_0750/T04_RadialV2_ExteriorWinding_Camera_build.log`
- `D:/RedMMOTitanWindowsData/Diagnostics/NightWater_T04_RadialV2_20260719_0750/WindingAutomation4/WindingAutomation.log`
- `D:/RedMMOTitanWindowsData/Diagnostics/NightWater_T04_RadialV2_20260719_0750/Titan_T04_RadialV2_GPU6.log`
- `D:/RedMMOTitanWindowsData/Diagnostics/NightWater_T04_RadialV2_20260719_0750/AutoCaptures_GPU6/NightWater_T04_Shore.png`
- `D:/RedMMOTitanWindowsData/Diagnostics/NightWater_T04_RadialV2_20260719_0750/AutoCaptures_GPU6/NightWater_T04_Orbit.png`

## Latest M00 Beams tether retry

M00 remains `incomplete_retry` at retry 24. A deterministic non-Shipping harness now holds
the grapple for multiple settled frames, disables the fallback ribbons for vendor-only proof,
and logs the projected hand/endpoint plus Niagara render state. TitanEditor compiled serially,
and one real RTX 3080 D3D12 run produced all three requested frames and exited cleanly.

The visual gate still failed. `NS_BeamOnly_02` reported active, visible, `ShouldRender=1`, and
`WasRecentlyRendered=1`, both endpoints were on-screen, and both fallback ribbons were off; the
actual A/B/C frames nevertheless contained no readable tether. The measured corridor contained
`0.0%` emissive candidates in every frame and only `0.611-2.788` luma levels of separation from
adjacent sand. The next bounded retry is to validate the pack demo and A/B a stronger continuous
variant such as `NS_BeamOnly_10`, or correct the emitter coordinate-space/width presentation
before spending another GPU run.

Evidence:

- `D:/RedMMOTitanWindowsData/Diagnostics/GrappleTether_Beams_20260719_0930/GrappleTether_TitanEditor_build.log`
- `D:/RedMMOTitanWindowsData/Diagnostics/GrappleTether_Beams_20260719_0930/Titan_GrappleTether_VendorOnly_GPU3_NoZen.log`
- `D:/RedMMOTitanWindowsData/Diagnostics/GrappleTether_Beams_20260719_0930/AutoCaptures_VendorOnly_GPU3_NoZen/GrappleTether_A.png`
- `D:/RedMMOTitanWindowsData/Diagnostics/GrappleTether_Beams_20260719_0930/AutoCaptures_VendorOnly_GPU3_NoZen/GrappleTether_B.png`
- `D:/RedMMOTitanWindowsData/Diagnostics/GrappleTether_Beams_20260719_0930/AutoCaptures_VendorOnly_GPU3_NoZen/GrappleTether_C.png`

## Verified M00 dark-side surface readability gate

The fused T04 terrain's true dark-side readability now passes from existing authoritative
real RTX 3080 D3D12 evidence, so this audit did not spend memory on another editor launch.
The matching runtime telemetry proves `surfaceNight=1`, `night=1.000`,
`nightPP=1.000`, `sunElev=-1.000`, and `moonElev=0.731`.

In the 1280x720 shoreline frame, the bottom 55% has median luma `120.53/255`,
only `0.001%` near-black pixels below luma 5, and no clipping at luma 250 or above.
The readable left land field has median `126.45`, P10 `111.11`, and `0%` below luma 16.
This closes terrain visibility only. The independent water presentation still fails in the same
frame: water-side median is `30.52`, `29.26%` is below luma 16, settled movement above two
luma levels is only `0.0256%`, and no readable shoreline crest is present. The later
player-plus-surface moon frame also remains too hot around the character, so balanced artistic
moonlight remains open even though terrain readability passes.

Evidence:

- `D:/RedMMOTitanWindowsData/Diagnostics/NightWater_T04_RadialV2_20260719_0750/AutoCaptures_GPU6/NightWater_T04_Shore.png`
- `D:/RedMMOTitanWindowsData/Diagnostics/NightWater_T04_RadialV2_20260719_0750/Titan_T04_RadialV2_GPU6.log`
- `D:/RedMMOTitanWindowsData/Diagnostics/NightWater_T04_RadialV2_20260719_0750/DarkSideReadability_Acceptance_20260719.txt`

## Verified M03 hub-stamp checkpoint

The generic geodesic terrain-stamp slice compiled into `TitanEditor`, and
`RedMMO.Planet.TerrainStamp.DeterministicGeodesicMath` completed successfully with exit code `0`.
The isolated 50 km map authoring pass populated exactly 27 terrain stamps while reusing all 27
managed region anchors. A second fresh-process pass reported the same 27 stamps with `changed=0`,
proving this authoring slice is idempotent.

The isolated-map runtime smoke resolved 27 enabled terrain stamps and exited with status `0`
without fatal, assert, ensure, or bad-export errors. A read-only production-map audit found zero
managed region anchors and zero terrain stamps. The production map remained byte-identical at
SHA256 `1DF9E6ED913A267875F1EF452F6ED51DAF337DBBAAE4C6EC3379EA6299346724`.

Evidence:

- `D:/RedMMOTitanWindowsData/BuildLogs/TitanEditor_M03HubStamps_20260714.log`
- `D:/RedMMOTitanWindowsData/BuildLogs/TerrainStampAutomation_20260714.log`
- `D:/RedMMOTitanWindowsData/BuildLogs/Create50kmHubStamps_First_20260714.log`
- `D:/RedMMOTitanWindowsData/BuildLogs/Create50kmHubStamps_Idempotent_20260714.log`
- `D:/RedMMOTitanWindowsData/BuildLogs/Smoke50kmHubStamps_20260714.log`
- `D:/RedMMOTitanWindowsData/BuildLogs/AuditProductionHubStamps_20260714.log`

M03 remains `in_progress`. Bounded headless continuity now passes every cube edge/corner, one
authoring patch feather, one stamp feather, and a four-waypoint moving collision ring. Hands-on
whole-world blocker traversal and visual approval of the flattened hubs remain open.

## Verified M02 resolved-shore checkpoint

The fused prototype shoreline now samples the exact PlanetGen runtime height order, including all
27 resolved terrain stamps, without reflecting or retaining the private noise generator. Focused
headless PIE independently audited 351 stamped samples, built 37 valid current-pawn SoStylized
crest segments, and matched eight real coast-collision probes within 169.173 cm. The strict
six-face water-datum test and full seam/patch/stamp/moving-ring collision regression also passed.

Evidence:

- `D:/RedMMOTitanWindowsData/BuildLogs/TitanEditor_ResolvedPhysicalShore_20260714_03.out.log`
- `D:/RedMMOTitanWindowsData/BuildLogs/PhysicalShorelineRuntime_Strict_20260714.log`
- `D:/RedMMOTitanWindowsData/AutomationReports/PhysicalShorelineRuntime_Strict_20260714/index.json`
- `D:/RedMMOTitanWindowsData/BuildLogs/FusedWaterDatum_AfterResolvedShore_20260714.log`
- `D:/RedMMOTitanWindowsData/BuildLogs/FusedContinuity_AfterResolvedShore_20260714.log`

## Verified M02 all-cube-boundary checkpoint

The isolated fused prototype now has a dedicated full-topology runtime gate. It cooks the complete
6x6x6 low-resolution fixture once, then checks all 12 unique cube edges and all 8 corners without
streaming-order bias. All 2,244 canonical edge pairs and 24 corner pairs passed; maximum edge
position delta was `0.090703 cm`, minimum edge normal dot was `0.999494314`, and the reported
corner position delta was zero. Exact procedural-component/key support checks and player-sized
capsule routes passed 144 edge probes, 48 corner probes, 60 edge sweeps, and 24 corner sweeps.

Evidence:

- `D:/RedMMOTitanWindowsData/BuildLogs/TitanEditor_AllCubeBoundaries_20260715_final.out.log`
- `D:/RedMMOTitanWindowsData/BuildLogs/FusedAllCubeBoundaries_20260715_final.log`
- `D:/RedMMOTitanWindowsData/AutomationReports/FusedAllCubeBoundaries_20260715_final/index.json`
- `D:/RedMMOTitanWindowsData/AutomationReports/FusedContinuity_AfterAllCubeBoundaries_20260715/index.json`

## Verified M02 bounded WorldStatic/pawn-route checkpoint

The representative seam, authoring-patch feather, terrain-stamp feather, and three moving-stream
routes now use the current player capsule (`34 cm` radius, `88 cm` half-height) at gameplay
clearance. A transient `WorldStatic` box that blocks `Pawn` was detected as the exact expected
component and removed before the baseline run. All 115 baseline segments then passed: 43 static
seam/patch/stamp sweeps plus 72 moving-stream sweeps. Combined with the 84 full-topology edge and
corner sweeps, bounded headless coverage now totals 199 pawn-sized route segments.

Evidence:

- `D:/RedMMOTitanWindowsData/BuildLogs/TitanEditor_PawnRouteWorldStatic_20260715.out.log`
- `D:/RedMMOTitanWindowsData/BuildLogs/FusedContinuity_PawnRouteWorldStatic_20260715.log`
- `D:/RedMMOTitanWindowsData/AutomationReports/FusedContinuity_PawnRouteWorldStatic_20260715/index.json`
- `D:/RedMMOTitanWindowsData/AutomationReports/FusedAllCubeBoundaries_AfterPawnRouteWorldStatic_20260715/index.json`

M02 remains `in_progress`: rendered visual approval, hands-on whole-world traversal, actual
foliage/PCG placement, packaged-client recovery, and multiplayer validation remain open. The later
root-sphere checkpoints below add bounded physical vehicle contact plus high-speed traversal across
all cube edges and corner neighborhoods; fitted hull/wing coverage remains a separate acceptance
gate.

## Verified M02 PlanetGen-only terrain-query checkpoint

The pinned PlanetGen fork now provides a narrow game-thread collision API for active terrain: one
line trace and sphere/capsule/oriented-box sweeps. It accepts only exact root procedural-mesh components in
that planet actor's current `ActiveChunks`; unrelated `WorldDynamic` objects are iteratively ignored.
Candidate chunks are bounds-culled, and equal-distance seam results use a deterministic
`(Face, U, V)` key rather than Chaos hit ordering.

Focused real-Chaos PIE placed a closer transient `WorldDynamic` box in front of the fused planet.
Ordinary world line, sphere, and 37-degree rotated-capsule queries hit the box first; both PlanetGen
APIs skipped it and returned the nearest active owned terrain component and exact key. The same
positive seam selection remained stable across 32 repeated lines, 8 repeated sphere sweeps, and 8
repeated rotated-capsule sweeps. A five-test fused runtime regression then retained all-cube
boundaries, physical shoreline, moving-ring continuity, authored coast, and water-datum acceptance.

Evidence:

- `D:/RedMMOTitanWindowsData/BuildLogs/TitanEditor_ActiveTerrainQuery_20260715.out.log`
- `D:/RedMMOTitanWindowsData/BuildLogs/TitanEditor_ActiveTerrainQuery_TestFix_20260715.out.log`
- `D:/RedMMOTitanWindowsData/AutomationReports/ActiveTerrainQuery_20260715_Retry2/index.json`
- `D:/RedMMOTitanWindowsData/AutomationReports/ActiveTerrainQuery_Regressions_20260715/index.json`
- `D:/RedMMOTitanWindowsData/BuildLogs/TitanEditor_ActiveTerrainQuery_Capsule_20260715.out.log`
- `D:/RedMMOTitanWindowsData/AutomationReports/ActiveTerrainQuery_Capsule_20260715_0440/index.json`
- `D:/RedMMOTitanWindowsData/AutomationReports/ActiveTerrainQuery_CapsuleRegressions_20260715_0500/index.json`

## Verified M02 ship/shuttle active-terrain query integration checkpoint

`RedPlanetTerrainQuery` now resolves the `ACLMPlanet` at the gameplay system's expected planet
centre and exposes a three-state result: exact active-terrain hit, matching-planet miss, or no
matching PlanetGen body. A matching-planet miss deliberately does **not** fall back to arbitrary
`WorldDynamic` or presentation geometry. Legacy `WorldStatic` fallback remains available only for a
body that has no matching PlanetGen actor.

The shared query is now used by `ARedShip` landing assist, exit parking, exit ground probes, the
movement void guard, and the forward collision governor. The governor reads `Owner->GetVelocity()`
so server-authoritative remote flight supplies its actual direction, and its exact PlanetGen
backstop is no longer disabled by the conservative datum-based altitude gate. `ARedShuttleBase`
uses the same exact query for terrain clamp, landing assist, and camera clearance. The mini fighter
inherits the ship path.

Focused real-Chaos PIE moved a closer transient `WorldDynamic` box onto the actor query route. A raw
dynamic trace hit that box first, while the ship landing query, shuttle surface query, and collision
governor still returned/capped against the same active owned PlanetGen terrain. The command emitted
`RED_FUSED_ACTIVE_TERRAIN_QUERY status=pass` and completed `Success`. The post-integration five-test
fused prefix then completed `5/5 Success`, failed `0`, with the existing environment warnings.

Evidence:

- `D:/RedMMOTitanWindowsData/BuildLogs/TitanEditor_ShipPlanetTerrainQueries_Serial_20260715.log`
- `D:/RedMMOTitanWindowsData/BuildLogs/ShipPlanetTerrainQuery_Focused_20260715_0615.log`
- `D:/RedMMOTitanWindowsData/AutomationReports/ShipPlanetTerrainQuery_Focused_20260715_0615/index.json`
- `D:/RedMMOTitanWindowsData/BuildLogs/ShipPlanetTerrainQuery_Regressions_20260715_0635.log`
- `D:/RedMMOTitanWindowsData/AutomationReports/ShipPlanetTerrainQuery_Regressions_20260715_0635/index.json`

## Verified M02 filtered physical ship-root checkpoint

`URedShipMovementComponent::MoveUpdatedComponentImpl` now merges the production ship's swept root
with the exact active PlanetGen terrain query. For a query-enabled sphere/capsule it queries only the
owned active chunks, clips native movement to the exact terrain time, and still lets an earlier
native blocking component win. Native hits are reported in the original requested delta's time
space. Non-swept moves, unsupported shapes, legacy bodies, and matching-planet paths with no active
terrain contact retain native behavior.

Local controlled flight and server-authoritative remote flight now both call
`MoveWithPlanetCollision`: the same `SafeMoveUpdatedComponent`, impact/slide, crater-aware recovery,
velocity correction, and component-velocity update. The accumulated penetration-return bug was
also fixed so an earlier correction cannot make a later failed resolution report success.

Focused real-Chaos PIE used the production `260 cm` `Vehicle` root on the cooked `+X/+Y` seam. A
closer generic `WorldDynamic` box was visible to a raw sweep but ignored by ship movement. A nearer
`QueryAndPhysics` `WorldStatic` wall remained the selected native component at exactly `3400.000 cm`;
native and filtered full-delta times were `0.218008` and `0.218686`, with a bounded conservative
pullback. After removing that wall, the actual root transform stopped on the exact active owned
terrain mesh with the exact-query time, distance, location, impact point, and trace endpoints. The
focused test exited `0`; the full fused prefix then passed all five tests, failed `0`.

Evidence:

- `D:/RedMMOTitanWindowsData/BuildLogs/TitanEditor_ShipPhysicalSweep_Serial_20260715.log`
- `D:/RedMMOTitanWindowsData/AutomationReports/ShipPhysicalSweep_Acceptance_20260715_0749/index.json`
- `D:/RedMMOTitanWindowsData/BuildLogs/ShipPhysicalSweep_FusedRegressions_20260715_0751.log`
- `D:/RedMMOTitanWindowsData/AutomationReports/ShipPhysicalSweep_FusedRegressions_20260715_0751/index.json`

The production, rollback, fused-prototype, and fused-asset SHA-256 values remain unchanged. M02 is
still `in_progress`: this proves the swept root sphere, not the attached runtime body/deck/wing
boxes, which still teleport with the root. The later oriented-box checkpoint closes the exact-query
primitive only, not compound movement. The all-boundary root traversal below closes the headless fast-route slice; passive
zero-input initial-overlap recovery, packaged-client recovery, hands-on visual traversal, and two-client
authority/replication remain open.

## Verified M02 production ship-root all-boundary checkpoint

The full cooked all-boundary fixture now owns one transient native `ARedShip`, keeps its production
`260 cm` `Vehicle` root at `QueryAndPhysics`, and calls the same `MoveWithPlanetCollision` path used
by local controlled and server-authoritative flight. It performs one constant-radius high-speed
move across each of the 12 cube edges and a three-leg loop through the signed X/Y/Z face
neighborhood at each of the 8 cube corners: 36 production moves total.

Every leg first requires the exact owned PlanetGen sphere sweep to return a clear route, preventing
`NoMatchingPlanet` from becoming a false pass. The shared mover then must reach the requested
endpoint without a stop, slide loss, overshoot, clamp teleport, velocity mismatch, lost root
clearance, or lost physics state. Focused real-Chaos PIE completed all `12` edge moves, all `24`
corner legs, and all `8` closed corner loops. Maximum endpoint error was `0.000000 cm`; minimum
route speed was `25993.982 cm/s` (about `260 m/s`). The focused test and the post-change five-test
fused prefix both exited `0` with failed `0`.

Evidence:

- `D:/RedMMOTitanWindowsData/BuildLogs/TitanEditor_ShipAllBoundaries_Serial_20260715.log`
- `D:/RedMMOTitanWindowsData/AutomationReports/ShipAllBoundaries_Acceptance_20260715_0815/index.json`
- `D:/RedMMOTitanWindowsData/BuildLogs/ShipAllBoundaries_FusedRegressions_20260715_0815.log`
- `D:/RedMMOTitanWindowsData/AutomationReports/ShipAllBoundaries_FusedRegressions_20260715_0815/index.json`

All four protected hashes remain byte-identical. This checkpoint is still root-sphere-only: fitted
body/deck/wing boxes, passive zero-input initial-overlap recovery, landing/exit,
packaged-client traversal, hands-on rendered traversal, and two-client authority/replication remain
open.

### Verified M02 movement-triggered initial-overlap checkpoint

The deterministic acceptance in the production-root seam fixture places
the `260 cm` root `50 cm` inside the active `+X/+Y` cooked seam, repeats the zero-length exact query
four times to require a stable owned chunk/MTD, then issues exactly one tangential production
`SafeMove`. Passing requires the MTD correction, the full requested tangent move, and a final exact
probe with no remaining penetration. The existing production depenetration path passed without a
production movement-code change.

After the first attempt was blocked by system commit pressure, the constrained serial retry compiled
and linked with exit `0`. Focused real-Chaos PIE reported
`RED_SHIP_INITIAL_OVERLAP_PASS`: `repeats=4`, `depth_cm=50.007141`,
`initial_adjustment_cm=50.132141`, `outward_displacement_cm=50.132141`,
`tangent_displacement_cm=100.000549`, `endpoint_error_cm=0.000000`, and `final_probe=1`.
The focused report is `Success` with zero errors. The subsequent five-test fused prefix is also five
`Success`, failed `0`, errors `0`, with no fatal/assert/ensure signature. Evidence:

- `D:/RedMMOTitanWindowsData/BuildLogs/TitanEditor_ShipInitialOverlap_SerialRetry_20260715_0940.log`
- `D:/RedMMOTitanWindowsData/BuildLogs/ShipInitialOverlap_Acceptance_20260715_0911.log`
- `D:/RedMMOTitanWindowsData/AutomationReports/ShipInitialOverlap_Acceptance_20260715_0911/index.json`
- `D:/RedMMOTitanWindowsData/BuildLogs/ShipInitialOverlap_FusedRegressions_20260715_0911.log`
- `D:/RedMMOTitanWindowsData/AutomationReports/ShipInitialOverlap_FusedRegressions_20260715_0911/index.json`

The production, rollback-checkpoint, fused-prototype, and fused-asset hashes remain byte-identical.
Movement-triggered recovery is closed for the production root sphere; the passive checkpoint below
closes the corresponding authoritative zero-input root-sphere slice.

### Verified M02 passive zero-input initial-overlap checkpoint

`URedShipMovementComponent` now checks exact active terrain before its controller early return. The
check is authority-only, throttled to 10 Hz, limited to query-enabled sphere/capsule roots, and skips
attached craft. A stationary penetrating root receives one bounded standard MTD correction; a
successful unpossessed correction also clears stale flight velocity and forces a net update.

The focused fixture reuses the real transient production `ARedShip`, its `260 cm` `Vehicle` root,
and its production movement component. Actor and unrelated component ticks are disabled; only the
movement component is re-enabled for actual PIE world ticks. The fixture has no controller or input,
and its test-only analytic clearance is held below the authored overlap so the old radius clamp
cannot produce a false pass. The first run correctly rejected that false-pass condition; the
corrected serial retry built with exit `0`.

Focused real-Chaos PIE reported `RED_SHIP_PASSIVE_ZERO_INPUT_PASS`: `repeats=4`, `ticks=16`,
`depth_cm=50.007141`, `adjustment_cm=50.132141`, `outward_displacement_cm=50.132141`,
`tangent_displacement_cm=0.000546`, `expected_error_cm=0.000000`,
`settle_drift_cm=0.000000`, and `final_probe=1` (`NoHit`). Observation continued beyond the next
0.1-second production probe interval. The focused report is `Success`, failed `0`, errors `0`; the
subsequent five-test fused prefix is five `Success`, failed `0`, errors `0`, exit `0`, with no
fatal/assert/ensure signature. Evidence:

- `D:/RedMMOTitanWindowsData/BuildLogs/TitanEditor_ShipPassiveOverlap_SerialRetry_20260715_1249.log`
- `D:/RedMMOTitanWindowsData/BuildLogs/ShipPassiveOverlap_AcceptanceRetry_20260715_1249.log`
- `D:/RedMMOTitanWindowsData/AutomationReports/ShipPassiveOverlap_AcceptanceRetry_20260715_1249/index.json`
- `D:/RedMMOTitanWindowsData/BuildLogs/ShipPassiveOverlap_FusedRegressionsRetry_20260715_1249.log`
- `D:/RedMMOTitanWindowsData/AutomationReports/ShipPassiveOverlap_FusedRegressionsRetry_20260715_1249/index.json`

All four protected hashes remain byte-identical. M02 stays `in_progress`: fitted body/deck/wing
collision, packaged-client recovery, hands-on rendered traversal, landing/exit, two-client
authority/replication of this correction, rendered shoreline/visible-seam approval, actual
foliage/PCG placement, and multiplayer validation remain open.

### Verified M02 oriented fitted-hull box-query checkpoint

The pinned PlanetGen exact active-terrain sweep now validates oriented box shapes. Candidate chunks
are conservatively expanded by the rotation-aware world AABB of the box, which is required to avoid
false-negative culling for asymmetric rotated hulls while leaving the existing exact Chaos sweep, active-component
filter, and deterministic seam-key selection intact. `RedPlanetTerrainQuery` passes the box through
the same project-owned adapter.

Focused real-Chaos PIE first rejected a finite-component quaternion whose magnitude overflows, then
swept a fitted-hull-sized `1100 x 900 x 300 cm` box rotated `37 degrees`
through the cooked `+X/+Y` seam. The raw `WorldDynamic` control hit the deliberately closer box;
both the direct PlanetGen query and project adapter ignored that blocker, selected owned active key
`(0,5,2)`, returned the same `79751.382812 cm` distance, and the direct query stayed stable across
eight repetitions. `RED_FUSED_ACTIVE_TERRAIN_BOX_PASS` was emitted. The focused report is
`Success`, errors `0`, exit `0`; the five-test fused prefix is five `Success`, failed `0`, errors
`0`, exit `0`, with no fatal/assert/ensure signature. Evidence:

- `D:/RedMMOTitanWindowsData/BuildLogs/TitanEditor_ActiveTerrainBox_SerialRetry_20260715_134509.log`
- `D:/RedMMOTitanWindowsData/BuildLogs/ActiveTerrainBox_AcceptanceRetry_20260715_134509.log`
- `D:/RedMMOTitanWindowsData/AutomationReports/ActiveTerrainBox_AcceptanceRetry_20260715_134509/index.json`
- `D:/RedMMOTitanWindowsData/BuildLogs/ActiveTerrainBox_FusedRegressionsRetry_20260715_134509.log`
- `D:/RedMMOTitanWindowsData/AutomationReports/ActiveTerrainBox_FusedRegressionsRetry_20260715_134509/index.json`

All four protected hashes remain byte-identical. This closes only the oriented-box query primitive.
Production flight still moves a `260 cm` root sphere; attached body/wing boxes are not yet
per-piece compound sweeps, deck boxes are Pawn-only, and rotated-box initial-overlap behavior is not
claimed. M02 therefore remains `in_progress` with fitted compound movement, landing/exit,
packaged-client, rendered traversal, and two-client replication gates open.

### Verified M02 off-centre rotated-box candidate checkpoint

The candidate-expansion path is now independently exercised without changing a protected map or
recooking collision. For the duration of the query-only fixture, the already-cooked target component
is restored from its deliberate production `BoundsScale=2` rendering allowance to raw
`BoundsScale=1`, then restored in the same game-thread call. The `1100 x 900 x 300 cm` box centre is
placed outside that target's raw bounds and its naïve unrotated expansion, but inside the
rotation-aware expansion. A raw zero-length Chaos control proves the target is genuinely overlapped;
the exact PlanetGen query then selects the same owned component/key `(0,5,2)` eight times with
`bStartPenetrating`, zero time, and marker
`RED_FUSED_ACTIVE_TERRAIN_BOX_BROADPHASE_PASS axis=2 side=1 margin_cm=5.0`.

Evidence:

- `D:/RedMMOTitanWindowsData/BuildLogs/TitanEditor_ActiveTerrainBoxBroadphase_20260715_141718.log`
- `D:/RedMMOTitanWindowsData/AutomationReports/ActiveTerrainBoxBroadphase_Acceptance_20260715_141718/index.json`
- `D:/RedMMOTitanWindowsData/AutomationReports/ActiveTerrainBoxBroadphase_FusedRegressions_20260715_141718/index.json`

The focused test is one `Success` with errors `0` and exit `0`; the post-change fused prefix is five
`Success` results with failed `0`, errors `0`, exit `0`, and no fatal/assert/ensure signatures. All
four protected hashes remain byte-identical. This closes only target candidacy for the exact
oriented-box query. Neighboring production chunks retain their normal inflated bounds, and this is
not a claim that every active chunk is excluded by the control. Production flight still lacks
per-piece compound sweeps and production box-overlap recovery, so M02 remains `in_progress`.

### Verified M02 rotated-box MTD query checkpoint

The exact fitted-box query now has a bounded initial-overlap acceptance independent of production
movement. Real Chaos embeds the `1100 x 900 x 300 cm` box `50.000 cm` into the cooked `+X/+Y`
seam; raw Chaos, direct PlanetGen, and `RedPlanetTerrainQuery` must agree on one finite
MTD/component/key, and eight repeats must preserve its depth and normal. One standard MTD plus a
`2 cm` pullback must then make an identical zero-length exact query return `NoHit`.

The accepted run reports
`RED_FUSED_ACTIVE_TERRAIN_BOX_MTD_PASS embed_cm=50.000 depth_cm=50.006725 adjustment_cm=52.006725 normal_dot_radial=0.999993 key=(0,5,2) repeats=8`.

Evidence:

- `D:/RedMMOTitanWindowsData/BuildLogs/TitanEditor_ActiveTerrainBoxMTD_Query_20260715_152542.log`
- `D:/RedMMOTitanWindowsData/AutomationReports/ActiveTerrainBoxMTD_QueryAcceptance_20260715_152542/index.json`
- `D:/RedMMOTitanWindowsData/AutomationReports/ActiveTerrainBoxMTD_QueryRegressions_20260715_152542/index.json`

The focused test is one `Success` with errors `0` and exit `0`; the fused prefix is five `Success`
results with failed `0`, errors `0`, exit `0`, and no fatal/assert/ensure signatures. All four
protected hashes remain byte-identical.

Compound egress is explicitly `incomplete_retry`, not hidden by this checkpoint. A deterministic
`100 cm` MTD-plane sweep toward the owner chunk interior started from the clear corrected pose, then
made a new non-penetrating contact after `3.936044 cm` with adjacent +Y-face key `(2,0,3)`
(`time=0.039360434`, `depth=0`). The failed control is preserved at
`D:/RedMMOTitanWindowsData/AutomationReports/ActiveTerrainBoxMTD_OwnerwardAcceptance_20260715_151847/index.json`.
That result requires multi-surface contact/manifold handling; it is not residual MTD failure.
Production movement remains root-sphere-only, so per-piece compound movement, production box
recovery, landing/exit, packaged-client, rendered traversal, and replication gates stay open and
M02 remains `in_progress`.

### Verified M02 adjacent-contact handoff checkpoint

The formerly deferred adjacent contact is now captured as deterministic query history. Starting
from the exact-clear MTD-corrected pose, the same `100 cm` tangent/ownerward request preserves
primary key `(0,5,2)` and reaches adjacent key `(2,0,3)` after `3.936044 cm` at
`time=0.039360434`. The contact is finite, non-penetrating, and has depth `0`. Raw Chaos, direct
PlanetGen, and `RedPlanetTerrainQuery` agree; eight repetitions preserve component, key,
`FaceIndex`, time/distance, location/impact, and normal.

The accepted marker is
`RED_FUSED_ACTIVE_TERRAIN_BOX_ADJACENT_CONTACT_PASS primary_key=(0,5,2) secondary_key=(2,0,3) distance_cm=3.936044 time=0.039360434 requested_primary_dot=-0.000000000 requested_secondary_dot=0.258098881 planes=2 retained_fraction=1.000000 repeats=8`.

Evidence:

- `D:/RedMMOTitanWindowsData/BuildLogs/TitanEditor_ActiveTerrainBoxAdjacentContact_20260715_163349.log`
- `D:/RedMMOTitanWindowsData/AutomationReports/ActiveTerrainBoxAdjacentContact_Acceptance_20260715_163349/index.json`
- `D:/RedMMOTitanWindowsData/AutomationReports/ActiveTerrainBoxAdjacentContact_Regressions_20260715_163349/index.json`

The focused report is one `Success`; the fused prefix is five `Success` results with failed `0`,
not-run `0`, exit `0`, and no fatal/assert/ensure signatures. All four protected hashes remain
byte-identical. This closes the query-handoff gate only. It does not simulate or approve a
production movement response: the next gate must use the live Blueprint modular fighter's fitted
`RuntimeHullCollision` geometry rather than the hardcoded test box, then verify one bounded
live-piece translation/contact response. Per-piece compound response and box-overlap recovery remain
open, so M02 stays `in_progress`.

### Verified M02 production-derived live fighter hull query checkpoint

The exact query now loads `/Game/RedMMO/Ships/BP_RedModularStarSparrow`, spawns a separate
`RF_Transient` actor, allows `BeginPlay` to run the production hull fit, and copies the resulting
`RuntimeHullCollision` transform and scaled shape. An independent union of the 29 registered
non-plume modular meshes matches the live relative centre `(203.80, 0.00, 88.02) cm` and
half-extents `(746.67, 668.38, 220.54) cm`; the fixture no longer substitutes the earlier
`(550,450,150) cm` hardcoded half-extents.

In a valid nose-radial 6DOF attitude, raw Chaos, direct PlanetGen, and
`RedPlanetTerrainQuery` preserve the complete owned contact on key `(0,5,2)`. Eight repetitions keep
component, key, `FaceIndex`, time/distance, location/impact, and normal stable. Projected box support
predicts a `282.872101 cm` lead over the production `260 cm` sphere; the real queries observe
`284.000000 cm` (`79359.312500 cm` box versus `79643.312500 cm` sphere). The actor transform and
Blueprint package dirty state remain unchanged, and the transient actor is destroyed after the
query.

Accepted marker:

`RED_FUSED_ACTIVE_TERRAIN_LIVE_FIGHTER_HULL_QUERY_PASS class=/Game/RedMMO/Ships/BP_RedModularStarSparrow.BP_RedModularStarSparrow_C center_cm=(203.80,0.00,88.02) half_extent_cm=(746.67,668.38,220.54) visible_meshes=29 box_distance_cm=79359.312500 sphere_distance_cm=79643.312500 expected_lead_cm=282.872101 observed_lead_cm=284.000000 key=(0,5,2) repeats=8`

Evidence:

- `D:/RedMMOTitanWindowsData/BuildLogs/TitanEditor_ActiveTerrainLiveFighterHullQuery_Retry_20260715_172926.log`
- `D:/RedMMOTitanWindowsData/AutomationReports/ActiveTerrainLiveFighterHullQuery_RetryAcceptance_20260715_172926/index.json`
- `D:/RedMMOTitanWindowsData/AutomationReports/ActiveTerrainLiveFighterHullQuery_RetryRegressions_20260715_172926/index.json`

The build succeeds, the focused report is one `Success`, and all five fused tests are `Success` with
failed `0`, not-run `0`, exit `0`, and no fatal/assert/ensure signatures. Protected hashes are
unchanged. This proves the live query geometry, not movement: the next bounded gate must translate
the whole actor from one live-box contact response while production still uses its root sphere.

### Verified M02 production-derived live fighter hull translation checkpoint

The next test-only gate now uses the registered live `RuntimeHullCollision` component for native
Chaos arbitration instead of bypassing its response mask with an object-type-only sweep. In one
fixed nose-radial attitude, a deliberately closer arbitrary `WorldDynamic` control contacts the
live box at `24.999882 cm` but is ignored by its production `Vehicle` response mask. A transient
`WorldStatic` control contacts at `49.999882 cm` and wins the probe-only native branch. After that
control is disabled, the exact owned PlanetGen contact wins at `99.985832 cm` on key `(0,5,2)`.

The fixture then commits exactly one translation with a `2 cm` pullback. The actor root, fitted hull,
and one visible modular mesh all move `97.985832 cm`; actor rotation, hull-relative transform, and
fitted extent remain unchanged. A final zero-length exact box query is clear. Eight query repeats
preserve the terrain component, key, `FaceIndex`, distance, and normal before that single move.

Accepted marker:

`RED_FUSED_ACTIVE_TERRAIN_LIVE_FIGHTER_HULL_TRANSLATION_PASS dynamic_distance_cm=24.999882 static_distance_cm=49.999882 terrain_distance_cm=99.985832 accepted_distance_cm=97.985832 key=(0,5,2) pullback_cm=2.0 iterations=1 repeats=8`

Evidence:

- `D:/RedMMOTitanWindowsData/BuildLogs/TitanEditor_ActiveTerrainLiveFighterHullTranslation_ComponentSweep_20260715_144115.log`
- `D:/RedMMOTitanWindowsData/AutomationReports/ActiveTerrainLiveFighterHullTranslation_First_20260715_144115/index.json`
- `D:/RedMMOTitanWindowsData/AutomationReports/ActiveTerrainLiveFighterHullTranslation_Regressions_20260715_144115/index.json`

The focused report is `Success`; all five fused regression tests are `Success`; exit is `0`; and the
focused/regression fatal, assert, and ensure scans are empty. All four protected hashes remain
unchanged. This is still an automation-only response proof. Playable `URedShipMovementComponent`
continues to sweep the sphere/capsule root. The next gate must add a typed, fit-ready translation
envelope and use it for fixed-rotation, single-box native/exact preflight while continuing to move
the actor root. Rotation, box-overlap recovery, and multi-piece compound response remain open.

### Verified M02 production fitted-envelope movement checkpoint

Playable source movement now publishes one typed `RuntimeHullCollision` envelope only after the
complete virtual fit succeeds. A non-virtual `ARedShip` wrapper clears the pointer before fitting and
publishes it after success, so both the full Sparrow and the mini-fighter override acquire their fit
while the production sphere remains `UpdatedComponent`. Supported fixed-rotation translation sweeps
the live box against its native `Vehicle` response mask and exact owned PlanetGen terrain, applies a
verified `2 cm` pullback, and moves only the actor root through the existing movement path. A clear
fitted box is authoritative; it no longer falls through to the oversized root's exact-terrain query.

The focused real-Chaos fixture calls production `SafeMoveUpdatedComponent` twice without setting the
envelope from test code. It ignores the geometrically closer `WorldDynamic` contact at `24.999882 cm`,
stops at the `WorldStatic` contact after moving `47.999882 cm`, then stops at exact terrain key
`(0,5,2)` after moving `97.985832 cm`. Root exact/native counterfactuals are clear, proving these stops
come from the live fitted box. Actor root, hull, and a visible mesh remain synchronized, with rotation
and relative fit unchanged.

Accepted marker:

`RED_FUSED_ACTIVE_TERRAIN_PRODUCTION_FIGHTER_HULL_TRANSLATION_PASS dynamic_distance_cm=24.999882 static_contact_cm=49.999882 static_move_cm=47.999882 terrain_contact_cm=99.985832 terrain_move_cm=97.985832 key=(0,5,2) pullback_cm=2.0 root_counterfactual=clear iterations=2 repeats=8`

Evidence:

- `D:/RedMMOTitanWindowsData/BuildLogs/TitanEditor_ProductionFittedHullTranslation_Acceptance_20260715_185230.log`
- `D:/RedMMOTitanWindowsData/AutomationReports/ProductionFittedHullTranslation_Focused_20260715_185444/index.json`
- `D:/RedMMOTitanWindowsData/AutomationReports/ProductionFittedHullTranslation_Regressions_20260715_185621/index.json`

The focused test and all five fused regressions are `Success`, both processes exit `0`, fatal/assert/
ensure scans are empty, and the four protected world assets plus the Sparrow Blueprint retain their
pre-test hashes. Rotation-changing moves, production fitted-box initial-overlap recovery, multi-piece
body/wing arbitration, child hit-event dispatch, and a fresh packaged Windows client remain open.

### Verified M02 production fitted-envelope initial-overlap checkpoint

Playable fixed-rotation fitted-box movement now handles an exact owned-terrain start overlap without
feeding a child-box MTD into the root-sphere resolver. The one-shot envelope token revalidates the
overlap, constrains and bounds `Depth + 2 cm`, requires a clear candidate for root-native,
fitted-box-native, and fitted-box-exact probes, moves the actor root once without sweep at unchanged
rotation, post-validates the synchronized pose, and lets `SafeMoveUpdatedComponent` retry the original
request. Native fitted-box overlaps remain fail-closed and deferred rather than applying an unproved
root correction.

The focused real-Chaos fixture embeds the live Sparrow fitted hull `50.000 cm` into exact owned terrain.
Production movement applies exactly one `52.013332 cm` recovery, then completes the requested
`25.000 cm` outward and `100.000 cm` tangential move. Actor root, fitted hull, and visible mesh remain
synchronized, fit and rotation remain unchanged, eight repeats are deterministic, and final exact and
native probes are clear with zero endpoint error.

Accepted marker:

`RED_FUSED_ACTIVE_TERRAIN_PRODUCTION_FIGHTER_HULL_INITIAL_OVERLAP_PASS embed_cm=50.000 depth_cm=50.013332 adjustment_cm=52.013332 request_out_cm=25.000 request_tangent_cm=100.000 observed_out_cm=77.013336 observed_tangent_cm=100.000000 endpoint_error_cm=0.000000 key=(0,5,2) pieces=1 root_counterfactual=clear iterations=1 repeats=8 final=clear`

Evidence:

- `D:/RedMMOTitanWindowsData/BuildLogs/TitanEditor_ProductionFittedHullInitialOverlap_20260715.log`
- `D:/RedMMOTitanWindowsData/AutomationReports/ProductionFittedHullInitialOverlap_Focused_20260715_202645/index.json`
- `D:/RedMMOTitanWindowsData/AutomationReports/ProductionFittedHullInitialOverlap_Regressions_20260715_202645/index.json`

The focused report is `Success`; all five fused prefix tests are `Success`; both Unreal exits are `0`;
fatal/assert/ensure scans are empty; and the production map, rollback checkpoint, fused prototype,
fused data asset, and Sparrow Blueprint retain their protected hashes. Rotation-changing fitted
movement, native fitted-box depenetration, multi-piece body/wing arbitration and manifold response,
passive fitted-envelope recovery, child event dispatch, rendered traversal, and a fresh packaged
Windows client remain open.

### Verified M02 bounded production fitted-envelope angular-corridor checkpoint

Playable fitted-fighter movement now rejects or commits one bounded translation-plus-rotation request
using the real off-centre `RuntimeHullCollision` fit instead of allowing UE's sphere-root sweep to
apply the child rotation unswept. The accepted slice is deliberately narrow: nonzero translation,
shortest-path rotation no larger than `6 degrees`, a direct rigid child box, and at most three
`2 degree` corridor segments. Each segment computes the rotated child-centre arc, sweeps a
mid-orientation box inflated by the maximum root-pivot-to-corner angular bound, preserves the live
`Vehicle` response table, and independently probes exact owned PlanetGen terrain. The full native
sphere-root route is preflighted too. Any contact vetoes the complete transform at time zero and
`MoveWithPlanetCollision` suppresses its normal slide response; a clear request commits inside a
revertible scoped movement and rechecks the predicted root/hull endpoint.

The focused real-Chaos fixture uses the actual transient production Sparrow, a `30 cm` tangential
translation, and a `6 degree` local roll. A `WorldStatic` control touches only the chosen wing
corner's intermediate arc (`47.141948 cm` clearance from both endpoint corner poses), while the
actual start hull, end hull, exact terrain, and complete root route are clear. An earlier
`WorldDynamic` control is geometrically present but ignored by the fitted hull's production response.
Eight blocked repeats preserve the complete actor, root, hull, and farthest-visible-mesh transforms;
the shared movement wrapper does not slide. After disabling only the static control, eight identical
requests reach the exact target transforms and end native/exact clear. A separate clear request
temporarily moves the terrain-query centre away from every PlanetGen body and proves the same
angular move completes through native-only collision instead of being rolled back by
`NoMatchingPlanet`.

The hardened exact-only control uses the same bounded `30 cm` plus `6 degree` request against real
streamed PlanetGen collision with both transient native controls disabled. Its actual fitted-box
start and endpoint poses are exact-clear, while the true midpoint overlaps active owned chunk
`(0,5,2)` by `0.152307 cm` inside a measured `1.521254 cm` support window. Native fitted-box poses
and the complete native/exact root route remain clear. Eight production `SafeMove` repeats veto at
time zero without changing the actor, root, fitted hull, or visible witness; the shared wrapper does
not slide. A route-specific counterfactual changes only the query centre, asserts
`NoMatchingPlanet`, and commits the identical complete transform. The production proxy also now
honors PlanetGen's full result contract by accepting either `bBlockingHit` or
`bStartPenetrating` as an exact contact.

Accepted marker:

`RED_FUSED_ACTIVE_TERRAIN_PRODUCTION_FIGHTER_HULL_ANGULAR_CORRIDOR_PASS angle_deg=6.000 translation_cm=30.000 segments=3 corner_clearance_cm=47.141948 blocked_repeats=8 clear_repeats=8 native=WorldStatic dynamic=ignored exact=midarc_blocked exact_translation_cm=30.000 exact_support_clearance_cm=1.521254 exact_embed_cm=0.152125 exact_depth_cm=0.152307 exact_repeats=8 exact_key=(0,5,2) exact_counterfactual=commit legacy=native_clear root=clear slide=suppressed final=clear`

The hardened build is
`D:\RedMMOTitanWindowsData\BuildLogs\TitanEditor_ProductionAngularExactMidArc_Counterfactual_20260715.log`.
The focused report remains
`D:\RedMMOTitanWindowsData\AutomationReports\ProductionFittedHullAngularCorridor_Focused_20260715\index.json`;
the five-test fused regression report is
`D:\RedMMOTitanWindowsData\AutomationReports\ProductionFittedHullAngularCorridor_Regressions_20260715\index.json`.

Evidence:

- `D:/RedMMOTitanWindowsData/BuildLogs/TitanEditor_ProductionAngularCorridor_20260715.log`
- `D:/RedMMOTitanWindowsData/BuildLogs/TitanEditor_ProductionAngularExactMidArc_Counterfactual_20260715.log`
- `D:/RedMMOTitanWindowsData/AutomationReports/ProductionFittedHullAngularCorridor_Focused_20260715/index.json`
- `D:/RedMMOTitanWindowsData/AutomationReports/ProductionFittedHullAngularCorridor_Regressions_20260715/index.json`

The focused report is `Success`; all five fused prefix tests are `Success`; both Unreal exits are `0`;
fatal/assert/ensure/unhandled scans are empty; and the production map, rollback checkpoint, fused
prototype, fused data asset, and Sparrow Blueprint retain their protected hashes. M02 remains
`in_progress`: pure rotation, requests above `6 degrees` and hitch substepping, rotating initial
penetration, partial angular TOI/slide, native fitted depenetration, multi-piece body/wing arbitration
and manifold response, passive fitted recovery, child
hit/overlap event dispatch, rendered traversal, landing/exit, two-client authority/replication,
rendered shoreline and visible-seam approval, actual foliage/PCG placement, multiplayer validation,
and a fresh packaged Windows client remain open.

### M00 night-water V3 retry — 2026-07-19

The project-owned `M_RedRadialWater_T04_V3` and
`MI_RedRadialWater_Night_T04_V3` assets were created successfully from a
sphere-safe Single Layer Water graph that reuses the purchased So Stylized
demo water normal. TitanEditor then passed all 15 serialized compile/link
actions. A real RTX 3080 D3D12 T04 run proved that the V3 instance was bound
to the correct `795774.69 cm` PlanetGen water sphere, captured three shoreline
frames and one orbit frame, and exited without fatal, assertion, OOM, or GPU
device-loss markers.

The visual gate did not pass. The old flashing white shell is gone, but the
water is still nearly pure black both at the shoreline and from orbit; the
complete orbit frame measured `80.51%` below luma 5. M00 therefore remains
`incomplete_retry`. The next bounded pass will correct the water-body color
and optical response before adding a separate stitched shoreline crest, so
the old detached white fragments cannot return.

Evidence:

- `D:/RedMMOTitanWindowsData/Diagnostics/NightWater_T04_SingleLayerV3_20260719_1031/Create_V3.log`
- `D:/RedMMOTitanWindowsData/Diagnostics/NightWater_T04_SingleLayerV3_20260719_1031/Titan_T04_SingleLayerV3_GPU.log`
- `D:/RedMMOTitanWindowsData/Diagnostics/NightWater_T04_SingleLayerV3_20260719_1031/AutoCaptures_V3/NightWater_T04_Shore.png`
- `D:/RedMMOTitanWindowsData/Diagnostics/NightWater_T04_SingleLayerV3_20260719_1031/AutoCaptures_V3/NightWater_T04_Orbit.png`

The protected 50 km foundation package was not modified. Its marker remains
SHA256 `26B00A20C4B18717CEC36B5CA289CC9001AE1E65DA649404ACC8721F14EF26E8`.
