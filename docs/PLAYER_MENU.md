# RED player menu

Press **Escape** from on-foot play, the fighter, or the shuttle. The menu is
owned by `ARedHUD`, so changing possession does not remove the binding.

- **Multiplayer / Lobby** appears directly below Resume. It closes Escape and opens the native Steam lobby with Create Game, Find Games, Join Selected, Reconnect, Invite Friends, and Leave Game.

## Pages

- **Overview** — current control reference and multiplayer pause warning.
- **Inventory** — the Vibe MMO inventory screen with the two currently carried
  weapon cards. Empty slots are shown honestly; persistent loot/crafting data is
  waiting for the inventory backend.
- **Skills + Loadout** — shows the current replicated Q/E assignments. Choose
  **Open Interactive Loadout** to enter the same on-foot editor used by **Tab**.
- **Settings** — applies and saves Performance, Balanced, or Cinematic Unreal
  scalability presets and toggles windowed/fullscreen mode locally.
- **Exit to Desktop** — requires a second confirmation click.

Placeholder/mock inventory and skills entries are disabled. These pages now show
only live carried/loadout state or explicit empty slots, so packaged testing cannot
mistake sample data for an implemented persistence backend. **I** intentionally
opens the character creator; it is not an inventory shortcut.

Escape or **Resume** restores game-only input and hides the cursor. A standalone
world is paused while the menu is open. Steam/client/listen-server sessions are
never world-paused: only the local controller's move/look input is captured, so
other players, enemies, and ships continue normally.
