# Choosing packs and hand-placing a spherical biome

This workflow keeps the user in control of foliage, rocks, and hero composition. PCG is introduced only after a small hand-authored sample looks right.

## 1. Approve a pack before it enters the live palette

Create a small neutral review map with a mannequin, noon light, saturated dusk light, a flat pad, and a curved planet patch. Review every candidate pack there.

Score each pack from 0-5:

| Criterion | Weight | Pass question |
|---|---:|---|
| Mood-board fit | 30% | Does the silhouette read as stylized alien science fiction rather than a normal Earth fern pack? |
| Useful variation | 20% | Are there at least three visible variants plus scale tiers? |
| Unreal readiness | 20% | Are pivots, scale, collisions, LOD/Nanite, folders, and materials usable? |
| Editability | 15% | Can color, roughness, wind, emission, and instance variation be changed? |
| Runtime cost | 15% | Does it survive shader-complexity, overdraw, shadow, and streaming review? |

Reject packs dominated by baked lighting, one repeated silhouette, opaque rectangular leaf cards, uneditable fixed colors, or heavy translucent foliage.

Record approved assets in a data-driven palette with:

- asset soft path;
- role: hero, satellite, filler, ground cover, rock, landmark, VFX;
- biome tags;
- allowed scale range and slope range;
- water/elevation preferences;
- collision policy;
- hand-placement-only or PCG-approved state.

## 2. Folder and actor rules

Use a predictable content layout:

```text
/Game/RedMMO/World/Quarantine/<PackName>/
/Game/RedMMO/World/Approved/<PackName>/
/Game/RedMMO/World/Biomes/<BiomeName>/Palettes/
/Game/RedMMO/World/ManualPOI/<RegionId>/<POIName>/
```

New imports stay in `Quarantine` until scale, pivot, material, collision, and performance checks pass. Never edit a marketplace master material in place; create project-owned instances.

### Exact editor workflow for an approved palette

1. In the Content Drawer, create `/Game/RedMMO/World/Biomes/<BiomeName>/Palettes`.
2. Right-click in that folder, choose **Miscellaneous > Data Asset**, then select
   **Red World Asset Palette** (`URedWorldAssetPalette`). Name it
   `DA_RED_<BiomeName>_Palette`.
3. Set a stable `PaletteId` and one or more `BiomeTags`. Tags describe visual/ecological intent;
   they are not display labels. Examples: `CoralCoast`, `FungalCathedral`, `Wet`, `Shade`, and
   `CliffBase`.
4. Add one entry per approved mesh. Give every entry a unique `EntryId`, assign the mesh, choose
   its role, scale and slope ranges, elevation range, and collision policy, then record the review
   outcome in `ReviewNotes`.
5. Keep `bHandPlacementOnly=true` and `bApprovedForPCG=false` during the manual practice pass.
   Flip PCG approval only after the practice patch is accepted. `bNaniteReviewed` means the asset
   was actually inspected in Nanite/LOD views; it is not a request to enable Nanite blindly.
6. Drag only meshes referenced by the palette into
   `/Game/RedMMO/World/ManualPOI/<RegionId>/<POIName>` or its matching World Outliner folder.
   Do not drag marketplace assets directly from `Quarantine` into the planet map.
7. For trunks, large rocks, and architecture, apply the palette collision policy in the Static
   Mesh Editor and verify the player capsule against it. Keep tiny ground cover non-colliding.
8. Add **Red Manual Placement Protection** to the root actor of each hand-authored colony or POI.
   Set a stable `ReservationId`, the shared planet center, a hard protected radius, a blend radius,
   and blocked feature tags such as `Foliage`, `Rock`, `Resource`, or `POI`.

Native editor **End / Snap to Floor** traces along world down, so it is valid only near the planet's
world-up pole. Do not use it on arbitrary cube faces. On a test-map duplicate, select one or more
unattached Static Mesh Actors and run the editor console command
`RedMMO.SnapSelectedMeshesToPlanet 0`. The optional number is a centimetre offset for assets whose
approved base pivot needs clearance. The compiled tool traces only exact active PlanetGen terrain,
preserves tangent heading and scale, aligns local Z to radial up, and supports one-step Undo. It
refuses the production and protected 50 km maps while its runtime placement acceptance remains in
progress; do not replace that guard with ordinary world-down snapping.

## 3. Place one practice biome by hand

1. Choose one 150-250 m practice patch near a shoreline or route, not the whole planet.
2. Add a local hub/biome anchor whose up vector is the normalized direction from planet center to the anchor.
3. Surface-snap the anchor using the shared planet surface query.
4. Align its local Z to radial up while keeping its tangent heading stable. The terrain hit locates
   the origin; it does not replace the planet's gravity-up convention. For a rock that is approved
   to lean with the slope, add a restrained pitch/roll afterward in the local tangent frame and
   record that authored tilt explicitly.
5. Place one XL landmark or hero tree first.
6. Add two or three different biome anchors at 15-50 m scale.
7. Around each anchor, place an uneven colony of 3-7 satellites. Do not distribute them at equal intervals.
8. Bias colonies toward water, shade, roots, cliff bases, material transitions, and wind shelter.
9. Preserve a clear traversal corridor and clean landmark silhouette.
10. Add ground cover last, using patches with gaps rather than uniform carpet.
11. Review from player height, jetpack height, and a fast ship approach.

### Reproducible 200 m practice recipe

Use this fixed recipe before authoring a full biome:

The exact tangent-local placement worksheet is
`docs/PRACTICE_BIOME_200M_LAYOUT.json`. Treat its `local_xy_m` values as metres in the
anchor's tangent plane, then run `RedMMO.SnapSelectedMeshesToPlanet 0` after placing each batch.
The worksheet deliberately uses palette entry IDs instead of marketplace paths, so the same
composition can be rebuilt with any approved alien pack without changing its spacing test. Run
`python Tools/tests/test_practice_biome_layout.py` before a practice session to catch accidental
changes to the recipe.

- one `200 m` diameter protected patch near the world-up pole;
- one hero landmark at the ecological focal point;
- three biome anchors separated by unequal distances of roughly `25 m`, `38 m`, and `55 m`;
- satellite colonies of `3`, `5`, and `7` meshes respectively, with non-uniform angles and gaps;
- two rock clusters, each using at least two silhouettes and different scale ranges;
- three ground-cover islands with visible bare-terrain gaps;
- one clear traversal corridor at least `8 m` wide from edge to edge;
- one protected POI root using a `10000 cm` hard radius and `2500 cm` blend radius;
- no PCG-approved entries during this first pass.

The recipe passes only when the Outliner contains the expected `1 + 3 + 15` primary composition
actors, every placed mesh resolves to an entry in the palette, the reservation component blocks
`Foliage`, `Rock`, and `POI`, the corridor is traversable by the player capsule, and screenshots
from player, jetpack, and ship-approach views show no even spacing, floating pivots, or repeated
orientation. Record those screenshots beside the palette review notes before enabling PCG.

Recommended variation:

- scale: usually 0.80-1.25;
- yaw: randomized around the local radial up vector;
- pitch/roll: restrained unless the asset is a rock;
- hue: small per-instance shift inside the biome palette;
- density: high near ecological anchors, low in travel space.

## 4. Correct transform storage on a planet

For durable manual placement, store:

- unit direction from planet center;
- radial offset above the sampled surface;
- tangent heading;
- local scale;
- asset ID and biome/POI tags.

Do not store only an arbitrary world transform. A radius or terrain profile change should be able to reproject the actor onto the new surface without losing its authored intent.

For a placed actor:

```text
RadialUp = normalize(WorldPosition - PlanetCenter)
Surface  = QueryPlanetSurface(RadialUp)
PlacementUp = RadialUp
Forward  = normalize(ProjectVectorOnPlane(AuthoredForward, PlacementUp))
Right    = normalize(cross(PlacementUp, Forward))
```

Build the default final rotation from `Forward`, `Right`, and `PlacementUp`. Store any approved
slope-conforming rock pitch/roll separately in this local tangent frame so re-projection remains
deterministic when the terrain profile changes.

## 5. Protect handcrafted work

Every hub, road, landing pad, portal, hand-placed colony, and authored vista gets a reservation volume or surface mask.

Reservation records need:

- stable GUID;
- sphere direction/center and geodesic radius;
- optional height range;
- blocked feature types such as foliage, rocks, creatures, resources, water, or POIs;
- soft blend distance;
- owning authoring region and POI.

PCG must query reservations before spawning. Regeneration may move or replace procedural filler, but it must never delete or overlap protected manual actors.

The deterministic offline reservation contract for the fused 50 km prototype is
[`PLANET_50KM_PCG_RESERVATIONS.json`](PLANET_50KM_PCG_RESERVATIONS.json). Regenerate or verify it
with `python Tools/generate_planet_pcg_reservations.py --write` or `--check`. It reserves every one
of the 27 tangent-local authoring regions and blocks foliage, rocks, creatures, resources, water,
and POIs inside each hub footprint.

The authority rasters referenced by that contract describe ownership and overlap feathering only;
they are never accepted as PCG biome or exclusion masks. Lake, river, and road masks are explicitly
marked absent until authored. The runtime PCG consumer and WorldGen adapter are also deliberately
marked unavailable, so surface dressing must remain disabled until those integrations and their
visible placement acceptance tests pass.

## 6. Turn the approved sample into PCG filler

Only after the practice patch is approved:

1. Extract the recurring anchor/satellite/ground-cover relationships.
2. Convert those relationships into a biome palette and density rules.
3. Feed the rules surface slope, elevation, moisture, temperature, water distance, hub distance, and reservation masks.
4. Keep hero landmarks and composition-critical clusters hand placed.
5. Compare the PCG result beside the approved hand-authored patch.
6. Reject any graph that produces even spacing, repeated orientation, blocked routes, or silhouettes crossing landmarks.

## 7. Per-asset acceptance checklist

- [ ] centimetre scale and Z-up orientation
- [ ] base/root pivot and applied transforms
- [ ] no floating shells, internal faces, or accidental non-manifold geometry
- [ ] clean UVs, packed ORM, correct normal maps
- [ ] editable project-owned material instance
- [ ] foliage uses masked two-sided shading, subsurface tint, wind, hue variation, and correct WPO bounds
- [ ] simple collision for trunks/rocks; none on tiny cover
- [ ] Nanite evaluated for rocks/large trunks; foliage overdraw and LOD evaluated separately
- [ ] neutral-noon and saturated-dusk review
- [ ] silhouette, collision, shadows, shader complexity, streaming, and multiplayer relevance checked
- [ ] promoted from Quarantine only after approval
