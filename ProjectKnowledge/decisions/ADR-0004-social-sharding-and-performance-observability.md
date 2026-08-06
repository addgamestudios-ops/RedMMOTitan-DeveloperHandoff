# ADR-0004: Relationship-aware dynamic sharding and mandatory performance observability

- Status: Accepted as architecture; implementation not started
- Date: 2026-07-30
- Decision owners: networking, online services, world systems, performance

## Context

RedMMOTitan needs many players to occupy one logical universe without requiring one
Unreal process to simulate every detailed planet, authored district, procedural
chunk, and replicated actor. Players should not be separated arbitrarily from their
party, friends, guild, or recent collaborators when population pressure creates
another copy of a busy area.

World Partition streams cells inside one Unreal world/process. It is not a shard
allocator, server orchestrator, social-affinity service, or cross-server persistence
system. PlanetGen surface chunks are likewise a terrain-streaming mechanism rather
than a population-routing system.

The installed CodeLikeMe PlanetGen 1.4 contains prediction-aware radial-gravity
movement and limited replicated character state. The same-author WorldGen 1.14 is a
deterministic planar terrain/biome/road/river/foliage generator, but its streaming
manager and generated chunks explicitly do not replicate. The installed PPG 1.0 is
from ChrumBum studio and is a separate product family. No pack replaces MMO
orchestration, persistence, authoritative shard ownership, or performance evidence.

## Decision

### Logical world and shard identity

Every authoritative simulation instance is addressed by immutable IDs:

`RealmId / CelestialBodyId / ZoneId / PhaseId / LayerId`.

- `CelestialBodyId` binds to the existing celestial registry.
- `ZoneId` identifies an authoritative geographic or orbital ownership region.
- `PhaseId` represents deliberate gameplay phasing, not capacity balancing.
- `LayerId` is the capacity shard for otherwise equivalent world state.
- World Partition and PlanetGen/PPG streaming remain internal implementation details
  of one authoritative layer.

An orchestration service owns layer health, capacity, admission, draining, startup,
and shutdown. A layer is opened at a configurable high-water mark before the current
layer is saturated and drained only below a separate low-water mark. Hysteresis and
minimum lifetime prevent repeated spin-up and shutdown.

### Social-cohesion placement

Admission is performed on a social atom, never by independently scattering members.

Priority is:

1. active party or raid;
2. explicit join-on-friend or group invitation;
3. recent party membership with a bounded expiry;
4. guild affinity as a soft preference;
5. unrelated players used to balance capacity.

Party/raid membership is atomic. Guild, friend, and recent-party edges contribute a
bounded affinity score but may not overfill a layer or override safety. Existing
players receive sticky assignments with a time-to-live. Rebalancing does not move a
player during combat, trade, matchmaking, a scripted event, landing, gravity capture,
or a persistence transaction. Cross-layer friend joins use an explicit safe transfer.

The allocator records a stable reason code for every placement so routing can be
tested and audited. Clients never choose their authoritative layer.

### World state and handoff

- Persistent character, guild, inventory, quest, and economy state lives outside an
  individual layer process.
- Mutable world entities have exactly one authoritative owner at a time.
- Cross-zone or cross-layer travel uses a signed handoff ticket and the existing
  server-authoritative preload/transition concepts.
- Deterministic procedural generation may reconstruct static terrain from a versioned
  seed and configuration. Deformation, mining, construction, encounters, and loot
  remain authoritative persisted deltas.
- A client may render distant celestial proxies, but full terrain, collision, AI, and
  replication are loaded only for its current authoritative zone/layer.

### Mandatory PIE and runtime performance evidence

Every performance-relevant PIE run must show a compact live overlay and write a
durable capture. The always-on lightweight set is:

- FPS plus frame, game-thread, render-thread, GPU, and RHI times;
- memory and streaming-pool pressure;
- network ping, packet loss, bandwidth, actor/channel counts, and replication cost
  when networking is active;
- World Partition loaded/pending cell counts and streaming-source count;
- active celestial body, zone/layer ID, relevant player count, active procedural
  chunks, and queued generation work.

Each capture records UTC timestamp, revision/source identity, map, RHI/GPU, resolution,
screen percentage, scalability, PIE topology, client count, server mode, seed/config,
body/zone/layer IDs, and test action. CSV or equivalent time-series output is stored
on `D:` and linked from the acceptance evidence.

Heavy diagnostics such as a full Unreal Insights trace, detailed GPU events, or many
simultaneous stat groups are bounded samples rather than permanent overhead. They are
triggered for a representative window or when a frame-time threshold is exceeded.
The compact overlay stays visible throughout the run. This avoids the measurement
system becoming a material source of the frame-rate loss it is measuring.

A PIE result is not accepted as performance evidence without the capture path and a
summary containing median, 95th percentile, 99th percentile, worst sustained frame
time, hitch count, memory high-water mark, streaming backlog, and network health.
Multi-client tests distinguish server and each client instead of reporting one
combined FPS number.

## Consequences

- Busy regions can scale horizontally while parties remain together and unrelated
  players absorb most capacity balancing.
- World Partition reduces per-process loaded content but does not increase the player
  capacity of one authoritative process by itself.
- Deterministic vendor generation can reduce static terrain replication, but mutable
  gameplay state still requires project-owned authority, persistence, and replication.
- PlanetGen gravity code may inform or adapt into the RedMMO celestial contract; it
  does not replace stable identity, shard routing, or cross-server handoff.
- A consistent frame-rate target must be stated per hardware/profile. The required
  captures make regressions comparable but cannot guarantee a target before load tests.

## Initial acceptance gates

1. A pure allocator test keeps parties atomic, prefers friends/recent parties, uses
   guild affinity softly, and distributes unrelated players across layers.
2. High/low-water hysteresis opens and drains layers without oscillation.
3. A two-layer dedicated-server test performs a safe friend join and preserves
   authoritative state.
4. A multi-client World Partition test records per-process loaded cells, streaming
   sources, replication cost, and frame-time percentiles.
5. A planet/zone handoff preserves stable celestial identity and never renders the
   playable surface and distant proxy simultaneously.
6. Every gate publishes the mandatory performance capture and run manifest.

## Rollback

This ADR is documentation-only. Rollback is removal of this file and its index entry;
no runtime source, map, asset, plugin, configuration, or running process was changed.

## References

- `ProjectKnowledge/decisions/ADR-0001-celestial-registry-and-gravity.md`
- `ProjectKnowledge/decisions/ADR-0002-server-authoritative-warp-state-machine.md`
- `ProjectKnowledge/invariants.yaml`
- `docs/PLANET_50KM_IMPLEMENTATION_SPEC.md`
- `docs/WINDOWS_STEAM.md`
- `Source/RedMMO/RedPlayerCharacter.cpp`
- `D:/UE_5.8/Engine/Plugins/Marketplace/PlanetGe5e8f23ed72d1V5/PlanetGen.uplugin`
- `D:/UE_5.8/Engine/Plugins/Marketplace/WorldGenab6305bc725eV5/WorldGen.uplugin`
- `D:/UE_5.8/Engine/Plugins/Marketplace/Procedur890d9e860517V2/PPG.uplugin`
