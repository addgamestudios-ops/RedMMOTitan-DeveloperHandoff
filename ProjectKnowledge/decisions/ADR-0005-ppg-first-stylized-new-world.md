# ADR-0005: PPG-first stylized planet architecture for the clean MMO world

- Status: Accepted as architecture; isolated prototype not started
- Date: 2026-07-30
- Decision owners: creative direction, world systems, networking, environment art
- Supersedes: the PlanetGen-as-terrain-provider portions of ADR-0001 and ADR-0003
  for the new clean MMO world only

## Context

The user's hands-on comparison selected Procedural Planet Generation (PPG) as the
preferred visual and world-generation substrate. Its current planet presentation,
biome transitions, terrain character, volumetric-cloud presentation, water, and
lighting are a stronger starting point for the intended world than the currently
installed PlanetGen implementation.

The desired art direction is stylized and lower-poly rather than realistic. The
accepted PPG look is therefore a structural baseline, not a mandate to keep its
realistic surface textures, foliage meshes, rocks, grass, color grading, or material
response.

This is a creative-direction decision based on the user's comparison. It is not yet a
recorded real-GPU acceptance result tied to an exact map, build, camera set, metrics
capture, or multiplayer topology.

## Decision

### World-generation ownership

For the new clean MMO world:

- PPG owns spherical terrain generation, biome masks and blending, surface chunk LOD,
  near-player terrain collision, water generation, foliage placement, and the
  currently accepted planet/cloud presentation.
- RedMMO owns immutable celestial-body identity, server-authoritative gravity,
  character/ship/projectile movement, replication, persistence, sharding, zone
  handoff, World Partition authored content, and performance observability.
- Bio Maker remains a standalone planning and validation layer. A project-owned PPG
  adapter may translate reviewed climate, hydrology, biome, composition, and asset
  catalogs into PPG data assets and materials.
- WorldGen remains a planar reference/optional flat-zone tool. It does not become a
  competing spherical terrain owner.
- PlanetGen is not the production terrain generator for this new line. The protected
  RedMMO 1.4 fork remains intact as a rollback/reference and may inform gravity and
  prediction behavior. No PlanetGen upgrade, removal, or migration is required by
  this decision.

The existing protected production maps and 50 km PlanetGen checkpoint remain legacy
assets. This ADR does not migrate, replace, or reinterpret them.

### Integration boundary

Do not copy PlanetGen source wholesale into PPG or edit the Marketplace PPG plugin as
the first integration step. Create a project-owned adapter boundary, provisionally:

`URedPPGPlanetAdapterComponent`

The adapter registers:

- stable `CelestialBodyId`;
- planet center, terrain datum, surface radius, atmosphere bounds, water datum, and
  gravity influence;
- server collision-readiness regions for all relevant players;
- client visual relevance and distant-proxy handoff;
- active PPG chunk, foliage, generation-queue, and memory telemetry.

Characters, ships, projectiles, AI, and physics actors query the RedMMO celestial and
gravity services, not a PPG example character. PPG remains replaceable behind the
adapter.

Reuse RedMMO-owned deterministic gravity selection and hysteresis first. PlanetGen's
prediction-aware gravity movement may be used as a private implementation reference
only where the applicable license permits; public repositories contain only
project-owned adapter and gameplay code.

### Stylized art layer

Keep PPG's generation pipeline while replacing its presentation through duplicated
project-owned assets:

- one stylized planet surface parent with biome-specific children or parameters;
- hand-authored palette ramps and controlled value grouping;
- low-frequency macro color, restrained micro-normal detail, and optional triplanar
  stylized textures;
- selectable flat, faceted, or softened normal response without changing the
  collision surface;
- lower-poly trees, grass, plants, rocks, cliffs, and debris supplied through PPG
  foliage data assets;
- weighted mesh variants, deterministic clusters, intentional gaps, slope/height
  limits, biome masks, and terrain vertex-color density masks;
- restrained specular response and a reviewed stylized water material;
- stylized cloud materials/parameters that preserve the accepted volumetric structure
  and lighting relationship.

PPG supports this boundary statically: `UPlanetData` separates the visible planet
material, generation material, biome-mask material, biome layers, water materials, and
per-biome foliage data. `UFoliageData` exposes weighted mesh variants, scale, slope,
height, density masks, clustering, culling, collision, WPO, and LODs.

Terrain shape and art style are tuned independently. Rolling hills should be produced
by lowering high-frequency displacement and erosion contribution, adjusting noise
amplitude/octaves/gain, and using smooth macro forms. Deliberately low-poly vegetation
does not require deliberately jagged terrain. Chunk quality/LOD may be reduced only
after surface silhouette, collision, seams, and frame-time captures pass.

### Multiplayer, multiple planets, and sharding

PPG is treated as a terrain/render provider, not an MMO networking solution.

- The server owns body selection, gravity, movement results, mutable terrain-adjacent
  gameplay state, mining, construction, loot, and shard placement.
- Clients may reconstruct deterministic terrain and predict movement but cannot
  author authoritative planet state.
- Only the nearest/relevant body uses full PPG terrain, collision, water, clouds, and
  foliage. Other bodies use cheap non-colliding proxies until a hysteretic handoff.
- Server collision relevance considers every player, not player-controller index zero.
- A project-owned global scheduler budgets PPG generation across all relevant bodies.
- Relationship-aware layer assignment and cross-zone handoff follow ADR-0004.

## First isolated prototype

Create a clean disposable project or scratch world after the current texture-import
and plugin operations are idle. Do not begin from a protected production map.

The first prototype contains:

1. one unchanged PPG reference planet;
2. one duplicated stylized PPG profile using a very small reviewed asset subset;
3. three clearly readable biome bands with rolling terrain and no deliberate terrain
   faceting;
4. stylized low-poly grass, one tree family, and one rock family;
5. the accepted water/cloud/lighting structure with stylized presentation changes;
6. the RedMMO adapter reporting stable body identity and radial gravity;
7. mandatory PIE overlay plus time-series performance capture.

## Acceptance gates

1. Matched-camera reference versus stylized screenshots establish that biome shape,
   clouds, water, and lighting remain readable while the surface and foliage become
   intentionally stylized.
2. Terrain seams, silhouette, collision, rolling-hill smoothness, foliage grounding,
   and biome boundaries pass at surface, flight, and orbit distances.
3. A two-client dedicated-server test proves authoritative gravity-body selection,
   movement correction, collision readiness, and remote presentation.
4. A two-body test proves proxy/full-detail handoff without showing both playable
   surface and proxy simultaneously.
5. Performance evidence reports median, p95, p99, hitches, memory, streaming backlog,
   PPG generation backlog, foliage count, and network health under ADR-0004.
6. No production map, protected checkpoint, vendor source package, or imported asset
   library is overwritten.

## Rejected alternatives

- Continue investing in PlanetGen as the new world's primary visual terrain provider.
- Replace the accepted PPG generation pipeline with a flat WorldGen terrain.
- Copy an entire vendor gravity plugin into another vendor plugin.
- Modify the Marketplace PPG source before a project-owned adapter proves the needed
  integration.
- Equate a stylized art direction with visibly jagged collision terrain.
- Load every planet at full terrain, foliage, water, clouds, collision, and replication
  detail simultaneously.

## Rollback

This ADR is documentation-only. Rollback is removal of this file and its index entry.
No map, asset, source module, plugin installation, import queue, or running process was
changed.

## References

- `ProjectKnowledge/decisions/ADR-0001-celestial-registry-and-gravity.md`
- `ProjectKnowledge/decisions/ADR-0003-planet-first-tile-factory.md`
- `ProjectKnowledge/decisions/ADR-0004-social-sharding-and-performance-observability.md`
- `ProjectKnowledge/invariants.yaml`
- `D:/UE_5.8/Engine/Plugins/Marketplace/Procedur890d9e860517V2/PPG.uplugin`
- `D:/UE_5.8/Engine/Plugins/Marketplace/Procedur890d9e860517V2/Source/PPG/Public/PlanetData.h`
- `D:/UE_5.8/Engine/Plugins/Marketplace/Procedur890d9e860517V2/Source/PPG/Public/FoliageData.h`
