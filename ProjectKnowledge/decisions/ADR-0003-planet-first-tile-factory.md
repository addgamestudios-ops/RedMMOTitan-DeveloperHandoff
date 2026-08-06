# ADR-0003: Planet-first tile factory for authored surface districts

- Status: Accepted for scratch proof only
- Date: 2026-07-29
- Decision owners: world systems, environment art, gameplay

## Context

The M07 island experiments showed that dropping a self-contained vendor map
onto a spherical level instance creates ambiguous terrain, water, collision,
and transform ownership.  It does not scale to a 50 km-circumference world or
to repeatable district placement.

The project already owns the correct planetary substrate: one PlanetGen
surface, a stable celestial frame, and 27 overlapping tangent-local authoring
patches fused into six seam-safe cube-sphere fields.  What is missing is a
repeatable adapter that turns a pack square into a compatible authored tile.

## Decision

Use a planet-first tile factory.

- PlanetGen remains the sole runtime owner of the spherical terrain surface,
  terrain LOD, collision, and gravity frame.
- Each pack-derived square is converted offline into a tile payload: bounded
  height delta, material/biome masks, road-edge sockets, placement masks, and
  optional prop recipes.
- Placement selects a stable tangent authoring region and uses its explicit
  local east, north, and up frame.  The adapter projects the payload onto the
  native planet; it does not place a second terrain world or a flat level
  instance beside it.
- Neighboring tiles share an edge contract and a normalized feather.  Height,
  material, road, and foliage transitions are validated before publication.
- Chaos, voxel, caves, and destructible features are local optional overlays.
  They may never become a competing whole-planet terrain, collision, or
  gravity authority.

## First scratch proof

Build one disposable native-planet map containing two adjacent locked tile
placements.  It must prove one shared terrain/material seam, a road crossing,
native collision and gravity, and a bounded local Chaos overlay.  Run static,
build, runtime, and D3D12 visual/performance gates separately.  No production
map, fused authoring input, vendor map, or prior experiment may be replaced.

## Consequences

- Districts become catalog placements with deterministic transforms instead of
  hand-aligned maps.
- Art iteration targets a documented tile contract and conversion tool.
- A failed tile can be withheld without disturbing the base planet or another
  district.
- This ADR establishes a scratch architecture direction only.  It does not
  prove visual quality, frame rate, road quality, Chaos behavior, or migration
  readiness.

## Rejected alternatives

- A full second terrain body per environment pack.
- Global voxel terrain as the primary 50 km planet.
- Runtime World Partition cells derived directly from the 27 source squares.
- Manual per-map placement and edge repair.

## References

- `docs/PLANET_50KM_IMPLEMENTATION_SPEC.md`
- `docs/PLANET_PATCH_AUTHORING_GUIDE.md`
- `ProjectKnowledge/invariants.yaml`
