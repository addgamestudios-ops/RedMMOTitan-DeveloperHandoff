# Fab / Marketplace inventory checklist

**Purpose:** What came from Fab/Marketplace, whether it is required for fundamentals, and what happens if missing.  
**Sources:** `Titan.uproject`, `RedMMO.uproject`, `Plugins/`, `ProjectKnowledge`, R92 dependency disposition.

Legend: **Req** = required for fundamentals (PPG-free) · **Planet** = required for planetary maps · **Opt** = optional · **Off** = disabled / substituted now

---

## Plugins / engine marketplace

| Name | Purpose | Fundamentals | If missing | Fab / notes |
|---|---|---|---|---|
| **PlanetGen** | Spherical planet (`ACLMPlanet`), Titan `RedPlanetGen` maps | **Off** for fundamentals; **Planet** for Titan maps | TitanFundamentals disables it. Live Titan enables Marketplace **1.7** at `D:\UE_5.8\Engine\Plugins\Marketplace\PlanetGe5e8f23ed72d1V5\`. Pinned fork `Plugins/PlanetGenPinned_1_4_0_RedMMO` **absent**; `RedPlanetGenCompat` shims link without fork APIs | Fab/Epic Marketplace “PlanetGen” / CLM — install via Epic Launcher into UE 5.8 |
| **PPG** (Procedural Planet Generator) | Clean RedMMO home world, ProfileV1, chunks/water/foliage | **Off** for fundamentals; **Planet** for clean RedMMO | Clean `RedMMO.uproject` will not generate home world. Fundamentals uproject has no PPG entry | Engine path seen: `...\Marketplace\Procedur890d9e860517V2\PPG.uplugin` |
| **FocalRig** | Rifle aim chain / AimWeapon ControlRig units | **Off** — substituted | Plugin **Enabled: false**. Marketplace folder Intermediate-only (no `FocalRig.uplugin`). Stock ControlRig `AimItem` substitute preserves `FocalAimTarget` / `FocalAimWeight` | Restore official Fab payload → enable in uproject → rebuild (Build.cs auto-links) |
| **WorldGen** | World-gen marketplace companion | **Off** | **Enabled: false**; Intermediate-only; documented rollback | Same as FocalRig — restore `WorldGen.uplugin` then enable |
| **Nwiro** + **NwiroIntegrationKit** | Optional editor / environment kit | **Opt** | Not needed for packaged play or fundamentals PIE | MarketplaceURL product `22e3bc90-ed91-4154-8bea-21c33e6a51b7` (Epic Fab deep link in `Titan.uproject`) |
| **UnrealAIIntegrationPlatform (UAIP)** | Optional editor remote tools | **Opt** / blocked | **Enabled: false**; payload Intermediate-only; skip Fab stall | Fab: https://www.fab.com/listings/0eedf909-00ac-4d95-b109-8fda51800fff |
| **VibeMMOUIKit** | VibeMMO player HUD kit (project `Plugins/`) | **Opt** (HUD) | HUD may fall back / miss widgets; gameplay C++ can still run | Project plugin (from Mac/Vibe handoff); keep with project |
| **RedHUD** | Project HUD plugin | **Opt** / project | Status texture / fuel pixels incomplete without content | Project-owned under `Plugins/RedHUD` |
| **SteamIntegrationKit** | Steam OSS / sessions (SIK v1.9, App 480) | **Opt** (MP later) | Multiplayer lobby/Steam transport unavailable; PIE listen-server still possible with NULL OSS | Project `Plugins/SteamIntegrationKit` (~297 MB) — transfer deliberately |
| **VibeUE** | Vibe tooling | **Off** on Win64 | `PlatformDenyList: Win64` | Marketplace `VibeUE581860d1833205V1` |
| **BpGeneratorUltimate** | Blueprint generator tooling | **Off** on Win64 | Denied Win64 | Skip |
| **OnlineSubsystemSteam** / **SteamSockets** (Epic) | Legacy Steam | **Off** | Replaced by SIK | Keep disabled |

---

## Content packs (Fab / Marketplace / purchased) — high level

| Pack / area | Purpose | Fundamentals | If missing |
|---|---|---|---|
| **Action Trooper / Tall Female** (`Content/Action_Trooper`, characters) | Playable trooper mesh/anims | Needed for full infantry feel; ThirdPerson pawn works without | Use ThirdPerson template character first |
| **StarSparrow** | Modular ship | Planet/ship work | Skip until planetary session |
| **Projectiles Vol.1 / Muzzles / BeamsPack** | Weapon VFX, grapple cable | Nice-to-have for weapons polish | Bolt tracer C++ still compiles |
| **Jet_Packs_Sci-Fi** | Jetpack meshes/VFX | Jetpack presentation | Logic may exist without mesh |
| **SoStylized / Stylized Desert Oasis / Stylized Rocks / TropicalAlienWorld / Alien_* packs** | Biome art | Planet art only | Not needed for fundamentals map |
| **Ultimate Stylized UI Crosshair** | Arc sight | HUD polish | https://www.fab.com/listings/707a878d-0d11-431a-813c-a7aaad10109f |
| **SciFi_Skills_Icon** | Ability icons for Vibe HUD | HUD | See project cook notes if icons missing |
| **SpaceColony / AsteroidSpaceport / Cloudz_Hi5 / Vefects / etc.** | Environment dressing | No | Exclude from fundamentals |

**Size note:** Full `Content/` on owner machine is tens of GB and is **not** all in git. Handoff repo ships **ThirdPerson** + git-whitelisted RedMMO crumbs + docs/source. Remaining packs travel via drive / separate sync.

---

## Quick “install only if you need…” 

| You want… | Install |
|---|---|
| Day-1 C++ / PIE / controls | **Nothing from Fab** — use `TitanFundamentals.uproject` |
| Clean R92 planetary home | **PPG** + clean project Content under `WindowsData\Projects\RedMMO` |
| Titan `RedPlanetGen` planet | **PlanetGen** UE 5.8 Marketplace |
| Official rifle aim rig | **FocalRig** full Fab payload (not Intermediate leftovers) |
| Steam friend sessions | **SteamIntegrationKit** + Steam client + App 480 |

---

## Owner-machine disposition snapshot (2026-08-07)

From `R92_DEPENDENCY_DISPOSITION.md`:

- FocalRig / WorldGen: **not recoverable** as official payloads → **substituted / disabled**
- PlanetGen pinned fork: **absent**; Marketplace 1.7 present; APIs **shimmed**
- TitanEditor Win64 Development: **Succeeded** after dependency unblock
