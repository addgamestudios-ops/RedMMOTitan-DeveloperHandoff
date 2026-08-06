# ADR-0002: Server-authoritative warp state machine

## Status

Accepted as architecture; implementation not started.

## Context

The reviewed hyper-speed tutorial demonstrates a useful single-player targeting
prototype: trace a destination, align the craft, and move toward an arrival point
near the target body's gravity boundary. Direct local interpolation is not enough
for RedMMOTitan because destination terrain may be streamed or hosted by another
server zone, and PvP clients must not author their own arrival state.

## Decision

Warp uses the ordered states `target`, `validate`, `spool`, `align`, `preload`,
`transit`, `decelerate`, `gravity_capture`, and `cooldown`. The server owns route
admission, destination body ID, preload readiness, arrival transform, interruption,
damage outcomes, and final gravity capture. Clients may predict presentation only.

Every route references immutable celestial IDs from the registry. Arrival is
computed from a reviewed warp anchor or an explicit radius-plus-clearance contract,
never from a visual mesh scale. Transit may use seamless travel or a zone handoff;
the destination cannot become playable until its authoritative surface, collision,
and relevant actors report ready.

## Consequences

- Warp has meaning as a world-streaming and server-zone transition, not only a
  speed multiplier.
- A cancelled or damaged spool returns a deterministic failure state.
- Moons, ring systems, and mineable asteroid fields can be destinations without
  keeping every detailed world loaded at once.
- Visual streaks, camera effects, and audio remain replaceable presentation layers.
