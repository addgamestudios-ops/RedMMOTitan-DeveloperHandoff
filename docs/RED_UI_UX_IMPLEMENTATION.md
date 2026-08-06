# RED MMO UI/UX implementation contract

## Source of truth

- Functional roadmap: `C:\Users\user\Downloads\RED MMO UI-UX Specification.pdf`.
- Artistic direction: the four supplied gameplay, inventory, character, and stylized HUD screenshots in `D:\RedMMOTitanWindowsData\UserTemp`.
- Runtime source: `UVibeMMOHUDWidget` for the combat HUD, `URedPauseMenuWidget` for the game menu, and the existing PO-Art character creator for functional body/equipment editing.

The target is a readable stylized sci-fi interface, not a literal copy of another game's branded art. The PDF controls behavior and information priority; the screenshots control composition, glass depth, angled silhouettes, and visual energy.

## Visual system

| Token | Runtime target |
|---|---|
| Primary text | Near-white `#F5FAFF`; never dark red |
| Secondary text | Cool light gray `#B8C7D9` |
| Glass base | Deep navy `#07121F` at 72-82% opacity |
| Glass highlight | Icy white/cyan, low opacity |
| Technical accent | Cyan `#59D8FF` |
| Action/selection accent | Warm orange `#FF9D3D`, used selectively |
| Health / shield / energy | Semantic red-coral / cyan / gold |
| Epic / legendary rarity | Solid purple / solid gold behind a clean weapon silhouette |
| Corners | 10-14 px radius with clipped or angled outer corners |
| Blur | One background blur per major cluster, never one blur per small child |

Typography stays white in all headings and controls. State changes use border, icon, glow, fill, and motion instead of recoloring labels to dark red. Focus and hover must remain distinguishable without relying on color alone.

## HUD composition

- Top-left: close helmet/face portrait, player name and level, health/shield/energy bars.
- Top-center: compact compass with the current heading emphasized.
- Top-right: circular or rounded tactical minimap plus a separate objective card.
- Left: party frames only when a party exists.
- Bottom-left: chat with Global/Squad/Faction tabs; it auto-hides when inactive.
- Bottom-center: five ability cards with live bindings, cooldown masks, charge/heat state, and clear unavailable reasons.
- Bottom-right: two weapon cards with transparent weapon cutouts, solid rarity fills, selected/cooling/overheat feedback, and live heat rails.
- Center: the installed stylized crosshair material; targeting and heat never compete in the same visual channel.

## Customization contract

Every HUD element has its own persisted settings:

- position in normalized safe-area coordinates;
- size or scale within authored limits;
- opacity from 20-100%;
- visible/hidden state;
- locked/unlocked state;
- Z order;
- reset-this-element and reset-all;
- optional combat-only auto-hide.

Layouts are stored per local player with `ULocalPlayerSaveGame`, not in replicated state and not in machine-wide graphics settings. The immutable layout data asset remains the baseline; saves store only overrides. Remote players can never change another player's HUD.

Customization mode must support mouse and controller/keyboard navigation. Changes are previewed immediately and saved on Apply or when customization closes. Save operations are debounced; dragging never writes every frame.

## No-dead-control rule

A visible interactive control is accepted only when all six conditions pass:

1. It has a stable command identifier and an explicit callback.
2. Its enabled state reflects whether the command is currently legal.
3. Activation produces immediate visual/audio feedback.
4. Failure explains why in the UI; it never silently does nothing.
5. Persistent or authoritative state is written to the correct owner (local save, game user settings, or server RPC).
6. An automation test or recorded PIE acceptance test proves its outcome.

Controls whose backend is not implemented are rendered as disabled with a short reason, or omitted. Placeholder text styled like a button is forbidden.

## Command ownership

| Surface | Command | Owner | Acceptance result |
|---|---|---|---|
| Pause | Resume | Local HUD/controller | Menu closes and gameplay input returns |
| Pause | Multiplayer/lobby | Session browser/game instance | Browser opens and reports provider/session state |
| Pause | Inventory | Local UI presenter | Inventory page opens with selectable real entries |
| Pause | Skills/loadout | Character/server ability state | Legal swap is requested and replicated; unavailable state explains why |
| Pause | Settings | Local settings presenters | Graphics and HUD pages open; Apply persists |
| Pause | Exit | Local platform | Two-step confirmation before quitting |
| HUD settings | Move/resize/opacity/visibility/lock | Local-player UI persistence subsystem | Survives HUD rebuild and relaunch |
| Inventory | Tab/select/equip/unequip/drop/split | Inventory presenter plus server authority | State updates or an explicit disabled reason is shown |
| Character | Equipment slot/customization option/apply | Existing PO-Art creator plus character presenter | Preview and resulting character state match |
| Abilities | Select/assign/swap | Ability presenter plus server authority | HUD, input binding, cooldown state, and replicated loadout agree |
| Weapons | Select/swap | Character weapon state plus server authority | Active card, held mesh, projectile, rarity, and heat state agree |

## Delivery phases

### Phase 1 - foundation

- Shared style tokens and white typography.
- Stable HUD element IDs and a per-local-player persistence subsystem.
- Customization mode with move, resize/scale, opacity, visibility, lock, reset, Apply, and Cancel.
- A command/action contract and test matrix for every visible control.

### Phase 2 - combat HUD

- Replace status, minimap/objective, ability, and weapon clusters with the stylized glass composition.
- Preserve all existing live gameplay bindings.
- Add party/chat/objective presenters only when their data sources exist.

### Phase 3 - inventory, character, skills, and settings

- Make inventory slots, categories, tooltips, and legal actions interactive.
- Wrap the working PO-Art character creator in the same style instead of replacing its functional customization logic.
- Add a dedicated HUD customization settings page with per-element controls.

## Verification gate

- Editor build succeeds with no new compile errors.
- Persistence round-trip, validation/migration, identity, and resolution-independence automation tests pass.
- PIE at 1920x1080 and an ultrawide resolution shows no safe-zone clipping.
- Mouse/keyboard and controller navigation both reach every enabled control.
- A button audit finds zero visible enabled controls without a callback and zero silent failure paths.
- A packaged Windows client retains the layout after restart.

