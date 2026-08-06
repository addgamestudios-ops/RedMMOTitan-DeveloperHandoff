# Чеклист Fab / Marketplace (UK)

**English:** [FAB_MARKETPLACE_INVENTORY.md](./FAB_MARKETPLACE_INVENTORY.md)

**Легенда:** **Req** = потрібно для fundamentals · **Planet** = для планет · **Opt** = опційно · **Off** = вимкнено/замінено

## Плагіни

| Назва | Призначення | Fundamentals / netcode | Якщо немає | Примітка / Fab |
|---|---|---|---|---|
| **PlanetGen** | Сферична планета Titan | **Off** | Fundamentals вимикає | Marketplace UE 5.8 |
| **PPG** | Clean home world | **Off** | Немає home generation | `Procedur890d9e860517V2` |
| **FocalRig** | Aim chain гвинтівки | **Off** — substitute | ControlRig AimItem | Intermediate-only на машині власника |
| **WorldGen** | Companion world-gen | **Off** | Disabled | Intermediate-only |
| **Nwiro** | Опційний editor kit | **Opt** | Не потрібен для PIE/netcode | Fab product у Titan.uproject |
| **UAIP** | Опційні remote editor tools | **Opt** / blocked | Enabled false | https://www.fab.com/listings/0eedf909-00ac-4d95-b109-8fda51800fff |
| **VibeMMOUIKit** / **RedHUD** | HUD | **Opt** | Геймплей C++ може йти | Project plugins |
| **SteamIntegrationKit** | Steam сесії / MP | **Opt** (пізніше для Steam PvP) | Немає friend join | ~297 MB; копіювати з owner machine |
| **VibeUE** / **BpGeneratorUltimate** | Tooling | **Off** на Win64 | Skip | — |

## Контент-паки (скорочено)

Action Trooper, StarSparrow, Projectiles/Muzzles/Beams, Jet packs, SoStylized/Oasis/Tropical тощо — **не потрібні** для першого netcode дня. Crosshair pack: https://www.fab.com/listings/707a878d-0d11-431a-813c-a7aaad10109f

## «Встановлюй лише якщо…»

| Хочеш | Встанови |
|---|---|
| День-1 C++ / PIE / listen-server | **Нічого з Fab** |
| Steam join з другом | SteamIntegrationKit + Steam client + App 480 |
| Clean R92 планета | PPG + clean project Content |
| Titan RedPlanetGen | PlanetGen |
| Офіційний rifle aim rig | Повний FocalRig Fab payload |
