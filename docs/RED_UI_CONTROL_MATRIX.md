# RED UI control matrix

This is the blocking checklist for the rule: no visible enabled control may lead to a silent dead end.

## Production surfaces

| Surface | Controls | Backend and current behavior | Automated evidence |
|---|---|---|---|
| Pause navigation | Resume, Multiplayer / Lobby, Overview, Inventory, Character, Skills + Loadout, Settings, Customize HUD, Exit | Every control is a native `UButton` with a native handler. Character is enabled only when the installed controller exposes `ToggleCharacterWindow`; otherwise its tooltip states the exact reason and the pause menu stays open. Exit requires confirmation. | `RedMMO.UI.Controls.NoDeadEnds` |
| Settings | Performance, Balanced, Cinematic, Fullscreen / Windowed | Applies through `UGameUserSettings`, persists, and refreshes the visible state label. | `RedMMO.UI.Controls.NoDeadEnds`; PIE still required for display-mode confirmation |
| HUD customization | Previous/next element, move 4 directions, size +/-, opacity +/-, show/hide, lock/unlock, reset element, reset all, Apply + Save, Cancel | Mutates the selected HUD element only, rejects locked/no-op edits truthfully, previews immediately, and persists per local player. | `RedMMO.UI.Controls.NoDeadEnds`; `VibeMMO.UI.HUDLayout.*` |
| Inventory | All, Weapons, Resources, Consumables, 40 item slots | Categories are real filters with selected state. Populated slots select stable backend indices and update detail text. Empty slots are disabled and explain why. The two carried rifles use distinct records, icons, descriptions, heat behavior, and purple/gold rarity. No equip/drop button is displayed until those server commands exist. | `VibeMMO.UI.Inventory.NativeInteractions` |
| Session browser | Close, Create Game, Find Games, Join Selected, Reconnect, Invite Friends, Leave Game, dynamic server rows | Routes to the game-instance/session layer. Disabled commands explain the missing legal state: current session, busy operation, no reconnect target, no selected server, or host requirement. | `RedMMO.UI.Controls.NoDeadEnds`; two-client Steam flow remains a separate integration gate |
| Ability loadout | Swap Q / E | Routes to the server-validated character command. The overlay remains passive except for this real action. | `RedMMO.UI.Controls.NoDeadEnds`; replication test still required |

The audited native slice currently constructs 30 pause/settings/customization buttons, 7 static session controls, 1 ability-loadout button, 4 inventory category controls, and 40 inventory slot controls. Dynamic session rows are audited separately. Empty inventory slots and contextually illegal session/character controls are deliberately disabled with a visible reason.

## Intentionally excluded latent demo surfaces

The Vibe kit contains decorative demo compositions made from `UOverlay` rather than controls. They are not connected to production navigation and must remain unexposed until replaced:

| Latent surface | Noninteractive representation | Required action before exposure |
|---|---|---|
| Vibe main menu | Play, Select Character, Options, and navigation overlays | Replace with native command controls and route to production state |
| Vibe server select | Decorative realm cards and Connect overlay | Use live session result rows and the production join command |
| Vibe character select | Decorative cards, New Character, Enter World overlays | Add profile ownership, selection, and authoritative spawn |
| Vibe character creator | Decorative option chips and Create overlay | Keep unused; production wraps the installed PO-Art creator |
| Equipment panel | Twelve decorative slot overlays | Add select/equip/unequip/compare commands and replicated equipment state |

Weapon and Q/E combat cards are display-only and activated by 1/2 and Q/E. They retain a non-button visual treatment unless click/touch activation is intentionally added.

## Required metadata for every new control

- Stable command ID and explicit native/Blueprint callback.
- Owning presenter/backend and authority boundary.
- Enabled predicate plus a short disabled reason.
- Hover, focus, pressed, success, and failure feedback.
- Keyboard/controller binding and navigation order.
- Persistence target when applicable.
- Automation outcome test or recorded PIE acceptance evidence.

## Current evidence

- Editor target: `D:\RedMMOTitanWindowsData\BuildLogs\TitanEditor_UI_20260716_033643.out.log` - succeeded.
- Control gate: `D:\RedMMOTitanWindowsData\AutomationReports\UIControls_20260716_033721\index.json` - 1 passed, 0 failed, 0 warnings/errors.
- Inventory gate: `D:\RedMMOTitanWindowsData\AutomationReports\InventoryUI_20260716_032811\index.json` - 1 passed, 0 failed, 0 warnings/errors.
- HUD persistence gate: `D:\RedMMOTitanWindowsData\AutomationReports\HUDLayout_20260716_031201\index.json` - 4 passed, 0 failed.

The remaining release gate is recorded PIE input/navigation plus a packaged-client persistence check. A callback-only result is not considered sufficient for final release acceptance.
