# Rear-bay modular mini fighter

`ARedMiniFighter` is a compact `ARedShip` assembled at runtime from the local StarSparrow
`Core`, `Wing_01/02/03`, `Engine`, `Thruster`, `Weapon`, and `Plasma` module meshes. It does
not use a combined example mesh or relabel the existing map fighter. Hard C++ asset references
keep the module meshes and red/black/cyan materials reachable by packaged cooks.

The authoritative `URedMiniFighterWorldSubsystem` waits until world actors have begun play,
then spawns one fighter if none exists and attaches it to the rear bay of the first replicated
`ARedShuttleBase`. A replicated actor whose object/class name contains `Carrier` is the fallback.
The fighter's normal replicated movement is retained; a replicated dock-parent reference plus
the engine's actor attachment replication keeps late joiners synchronized.

## Controls

- On foot near the rear bay: press **F** to select and board the mini fighter. **B/V** are reserved for the main shuttle, which prevents proximity to the carrier from possessing the wrong craft.
- Selecting the hard-docked fighter with **F** launches it clear of the parent craft before restoring compact collision and flight. **R** remains the explicit launch/dock control while piloting.
- Near the parent's rear bay at low relative speed: **R** docks.
- **W/S** thrust, **A/D** strafe, **Space/Ctrl** lift, mouse pitch/yaw, **Q/E** roll, **Shift** boost.
- **LMB** fires the normal server-authoritative heat weapon; there is no reload.
- **C** switches the functional inherited cockpit/chase cameras; **L** toggles inherited landing assist.
- **F** exits normally after launch. Do not use B/V for the mini fighter; those keys target the main shuttle.

## Stabilized client behavior

- Runtime modular collision is fitted to the live hull/deck, removing the oversized invisible walkable rail and allowing the fighter to be stood on, targeted, shot, and boarded from its own bounds.
- The flight contract is **+X forward** (the pointed nose), with exactly one rear engine plume. Runtime construction and flight use that axis, but final screenshot-level art orientation/plume seating still needs user approval.
- First-person seating and the pulled-back third-person chase camera are separate working modes; **C** switched the packaged runtime into chase view without the old unstable orbit/free-look inheritance. Final framing still needs a human visual pass.
- Landing assist and physical-surface snapping support the main PlanetGen body and the reachable moon. Vacuum travel receives the faster space speed profile while surface flight remains governed.
- Ship engine audio was replaced/reworked rather than merely attenuated; final ear/comfort judgment still requires the user's play session.
- Distinct weapon/impact profiles remain server-authoritative. Destroying an occupied craft kills/ejects the occupant through the replicated destruction path.

## Current packaged evidence

- Current package: `D:\RedMMOTitanWindowsData\PackagedBuilds\Development_DESERT_STABILITY_20260713_181525\Windows` (launch `Titan.exe`).
- Runtime log: `D:\RedMMOTitanWindowsData\PackagedBuilds\Development_DESERT_STABILITY_20260713_181525\Windows\Titan\Saved\Logs\Titan.log`.
- The packaged process ran **3m46s** from main-shuttle board at 16:20:06 to **F** mini-fighter launch at 16:23:52, restored compact fighter collision, and produced no fatal/critical/assert/unhandled matches or crash folder.
- The shuttle's raw UObject sound/attenuation caches now use `TStrongObjectPtr`, fixing the garbage-collection crash path seen during the earlier longer shuttle flight.
- This evidence proves the code path survived and launched; it does **not** claim the mini fighter's final orientation/plume appearance has been visually approved or that real Steam multiplayer has been tested.

## First-pass limitations

- Docking is a server-validated snap, not an authored rail, gear, or hangar animation.
- The rear-bay point is derived from live parent bounds; a future carrier with an authored socket
  should override this with a named bay socket for exact art alignment.
- Docking is rejected beyond 35 m from the rear-bay target or above 30 m/s relative speed.
- Movement, collision, weapons, and streaming collision support are suspended while attached. Collision is restored after launch.
- The shuttle's **O** hangar-door control is not automatically interlocked with fighter launch.
- This first pass does not support leaving the pilot while the fighter remains hard-docked; launch with **F** selection or **R** before exiting.
- Build/package/runtime verification is complete, but final visual orientation, plume seating, both camera framings, collision feel, landing, audio comfort, vacuum speed, docking, and occupant death still need a human gameplay pass.

Planet continent/elevation work is separate and held in [`PLANET_TERRAIN_AUTHORING_PLAN.md`](PLANET_TERRAIN_AUTHORING_PLAN.md).
