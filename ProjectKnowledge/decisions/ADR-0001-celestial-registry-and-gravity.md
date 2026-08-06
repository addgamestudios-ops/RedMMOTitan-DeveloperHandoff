# ADR-0001: Stable celestial registry with server-authoritative gravity and warp

- Status: Accepted
- Date: 2026-07-20
- Decision owners: gameplay, networking, world systems

## Context

RedMMOTitan now has a home planet, a physical moon, a ring-world presentation,
additional playable moons, mineable asteroid fields, and future warp routes. Actor
names, component indices, and whichever body happens to be closest on one client are
not durable identities and cannot safely drive saves, replication, gravity, or travel.

PlanetGen also streams procedural surface chunks, while World Partition is intended
for authored hubs, props, encounters, navigation patches, and local dressing. The 27
square regions are source-authoring inputs to the fused planet, not runtime cells.

## Decision

Introduce one celestial registry boundary keyed by immutable, namespaced stable IDs.
Every planet, moon, ring world, asteroid field, arrival anchor, and warp route has a
registry record. A record carries the physical center/radius contract, gravity
influence and priority, presentation references, and streaming references appropriate
to its type. Runtime actors bind to those IDs; display labels and transient actor names
do not become identity.

The authoritative server owns:

- registry bindings and lifecycle;
- dominant-gravity-body selection, including deterministic priority and hysteresis;
- authoritative movement results, with optional client prediction and reconciliation;
- warp admission, route and phase state, destination readiness, and arrival transform;
- mineable-field spawning and persistent/replicated resource state.

Clients may render proxies, pre-stream destinations, predict local gravity, and present
warp effects, but they cannot choose the authoritative body, route, phase, or arrival.

PlanetGen remains the owner of procedural surface chunks, surface LOD, and near-player
terrain collision. World Partition remains the owner of authored content around that
surface. The authoring-region IDs retain provenance through the offline fuse but do not
become World Partition cell IDs.

## Consequences

- Saves, replication, telemetry, defects, and evidence can refer to the same durable
  celestial objects.
- Multiple players may occupy different bodies without fighting over a global
  "closest planet" visual toggle.
- Gravity and warp require explicit multiplayer tests and reconciliation behavior.
- Body deletion or ID renaming requires a migration, not a silent rename.
- Existing Blueprint and C++ actors need adapters that register and resolve stable IDs;
  this ADR does not claim those adapters are already implemented.

## Rejected alternatives

- Actor labels, array indices, or spawn order as identity.
- Client-authoritative nearest-body gravity or warp teleportation.
- One all-owning planet Blueprint as the network, save, and streaming authority.
- Treating the 27 authoring regions as runtime World Partition cells.
- Treating PlanetGen surface chunks as authored World Partition content.

## References

- `ProjectKnowledge/invariants.yaml`
- `ProjectKnowledge/acceptance/planetary-system.yaml`
- `docs/PLANET_50KM_IMPLEMENTATION_SPEC.md`
- `docs/PLANETGEN_PINNED_FORK.md`
