# Planet terrain authoring plan

## Decision

Yes: the planet can be reconfigured so its continents, coastlines, ocean coverage, and elevations match designed square maps. The 27-square source compositor and deterministic six-face bake pass offline coverage, seam, provenance, and determinism checks. The original production map and `RedPlanetGen_50km_Test` checkpoint remain unchanged rollback points. A third map, `RedPlanetGen_50km_FusedPrototype`, now consumes the imported six-face height asset while inheriting the 50 km profile, 27 metadata anchors, and 27 hub-flatten stamps.

PlanetGen 1.4 currently builds the spherical terrain from layered 3D noise. Its seed, first continental noise layer, minimum/maximum height, and sea level can change the general character and land-to-ocean ratio, but they cannot reproduce an exact hand-drawn continent map.

## Implemented source model

The project-owned macro terrain layer ahead of PlanetGen's small-scale noise is now represented by:

1. Author up to 27 square 16-bit heightmaps plus land/water and biome masks in tangent-local map space.
2. Assign every map a deterministic planet anchor, heading, physical width, priority, and edge feather.
3. Project and blend those maps into six cube-face fields. A cube map is the exact closed square storage topology and avoids severe latitude/longitude pole stretching.
4. Sample the fused field from the normalized direction between the planet center and each terrain vertex or foliage query point.
5. Treat the authored value as the macro elevation and coastline source. Blend low-amplitude procedural noise on top for dunes and natural surface variation.
6. Keep sea level as a separate nondestructive control. Raising or lowering it changes ocean percentage without repainting continents.
7. Rebuild collision, normals, water intersection, biome weights, and chunk LOD from the same fused sample so visuals and walking surfaces cannot diverge.

## Editor workflow still required

The low-level validated importer exists in source, but the author-facing editor workflow should expose:

- Import/replace any of the 27 square heightmaps and its land/biome masks.
- Preview its tangent placement, heading, overlap, and contribution to all six fused faces.
- Non-destructive sea-level preview with land/ocean percentage.
- Planet preview at low resolution before committing a full regeneration.
- Height, coastline, and noise-blend sliders.
- Seam and pole validation for all six faces.
- Named presets plus an undoable backup of the currently approved planet.

The offline source workflow is now safe for manual editing. It requires an explicit command,
never regenerates patches during `bake-existing`, detects R16/PNG conflicts, stages derived face
publication, and provides content-addressed source snapshot/restore. Follow
`docs/PLANET_PATCH_AUTHORING_GUIDE.md`; this does not replace the missing spherical editor preview
or runtime promotion gate. Accept-and-bake and restore-and-bake are now single transactions:
all face arguments are checked before source mutation, a downstream face failure restores the
exact prior source revision, and a newer concurrent editor save is preserved rather than
overwritten by rollback.

## Implementation phases and status

1. **Source and import transport complete:** 27 persisted R16/land/biome/authority source squares bake to six seam-safe macro faces. The authenticated Unreal asset at `/Game/RedMMO/Environment/DA_RED_Planet50Km_FusedHeightfield` persists six height, six land, and six RGBA biome arrays at 257 x 257.
2. **Runtime capture, querying, and consumer projection complete at contract level:** the pinned PlanetGen fork captures all 18 arrays; authored land/biome samples feed the existing linear vertex-color/UV1 material weights and both foliage climate paths. A game-mode smoke reported `surface masks=yes`, combined authored height with 1,500 cm detail noise, resolved 27 stamps, logged 56 cold-dominant authored samples in a terrain chunk, and returned exit code `0`.
3. **Visual biome and placement acceptance still partial:** null-RHI proves the runtime contracts, not full rendered biome appearance, actual foliage/PCG placement, or water/coastline classification. The author-facing spherical preview and mask promotion path also remain open.
4. **Bounded headless cooked-collision continuity verified:** focused PIE automation passed one `+X`/`+Y` cube-face seam, authored patch 13's feather, and live terrain stamp 13's core/feather/outside range. Rendered/player and vehicle traversal, full invisible-wall coverage, gravity, water/coastline agreement, multiplayer determinism, packaged cooking, and distant-planet rendering remain open; headless automation is not visual acceptance.
5. Only replace the live planet after an approved preview and a packaged traversal test.

Evidence for the runtime consumer checkpoint:

- `D:/RedMMOTitanWindowsData/BuildLogs/TitanEditor_SurfaceMaskConsumer_FinalFix_20260714_195516.log`
- `D:/RedMMOTitanWindowsData/BuildLogs/PlanetGen_SurfaceMaskConsumer_FinalFix_20260714_195642.log`
- `D:/RedMMOTitanWindowsData/BuildLogs/FusedPrototype_SurfaceMaskConsumer_FinalFix_20260714_195909.log`
- `D:/RedMMOTitanWindowsData/BuildLogs/TitanEditor_FusedTerrainContinuity_Final_20260714.log`
- `D:/RedMMOTitanWindowsData/BuildLogs/FusedTerrainContinuity_Final_20260714.log`
- `D:/RedMMOTitanWindowsData/AutomationReports/FusedTerrainContinuity_Final_20260714/index.json`

## Safe starting assets

Keep two source images under source control: a simple black/white land mask for coastline editing and a 16-bit height map for elevation. This makes it possible to move a coast without accidentally changing every mountain, and to adjust ocean coverage independently through sea level.

The 2026-07-14 labeled macro-biome reference supplies the first global painting target: polar caps, tundra/boreal transition, a major desert continent, tropical belts/islands, and separating oceans. It is a design guide rather than a heightmap; exact coastlines and elevations remain editable in the 27 square sources.
