# Мережа / Реплікація / Мультиплеєр / PvP — старт для програміста

**Аудиторія:** програміст геймплею / netcode (listen-server, реплікація, PvP).  
**English:** [NETWORKING_PVP.md](./NETWORKING_PVP.md)  
**PPG/PlanetGen:** для першого PIE з netcode **не потрібні** — відкривай `TitanFundamentals.uproject` + ThirdPersonMap.

### Володіння світом (коротко)

Те саме GitHub-репо, що й у environment-артистів. Хаб-геймплей / networked actors — у **`/Game/RedMMO/Maps/Hubs/L_Hub_Gameplay_Logic`** (HubLogic). **`L_Hub_Env_Visuals`** не редагуй. Тонкий **`L_Hub_Persistent`** збирає обидва, щоб env-delivery не змушував переписувати netcode. Повні правила: [MERGE_SAFE_WORLD_UK.md](./MERGE_SAFE_WORLD_UK.md).

---

## Поточна архітектура (чесно)

| Шар | Що є | Доведено? |
|---|---|---|
| **Топологія** | Unreal **listen-server** (хост також гравець). Dedicated server не прийнятий. | Історично: PIE 2 клієнти listen-server для aim/jetpack/fire |
| **Транспорт** | **Steam Integration Kit (SIK) v1.9** — єдиний Steam-стек (заміна OnlineSubsystemSteam + SteamSockets). Стандартні Epic OSS Steam **вимкнені**. Dev App ID **480** (Spacewar), `steam_appid.txt` | Packaged smoke: auth/relay + хост з одного акаунта. **Реальний join/PvP двох Steam-акаунтів не доведено** |
| **UI сесій** | Escape → Multiplayer/Lobby; **F8** у runtime / **F6** у PIE. Create / Find / Join / Reconnect / Invite / Leave. ≥8 гравців. Немає тихого auto-host після порожнього пошуку | UI + життєвий цикл хоста; join друга — відкрито |
| **Авторитет** | Сервер: heat/overheat зброї, спавн болтів, пілот/зброя корабля, урон; реплікуються aim + прапорці jetpack | Two-client listen-server PIE (шлях NULL OSS — **реплікація геймплею, не Steam-транспорт**) |
| **GameState** | Celestial/PPG frame + registry; реальний 1S/2C late-join + radar **відкриті** (M05) | Докази single-process ≠ прийняття мультиплеєра |
| **PvP** | `bIsEnemy`, health/shield/armor, downed, grapple по гравцю, lethal ragdoll / смерть у кораблі | Не завершений PvP-режим; немає matchmaking |

---

## Ключові класи (починай тут)

| Система | Файли | Нотатки по мережі |
|---|---|---|
| Гравець / jetpack / aim / зброя | `Source/RedMMO/RedPlayerCharacter.h/.cpp` | Великий блок `DOREPLIFETIME`: Health/Shield/Armor/Fuel, aim, heat, jetpack, abilities, grapple/slam |
| Рух | `RedCharacterMovement.*` | Радіальна гравітація — обережно під listen-server |
| Снаряди | `RedBolt.*`, `WeaponFirer.*` | Болти зі спавном на сервері |
| Корабель (StarSparrow) | `RedShip.*`, `RedShipMovementComponent.*` | Health, WeaponHeat, Pilot, landing |
| Шател | `RedShuttleBase.*` | Окупанти / історія GC аудіо |
| Сесії / Steam | `RedGameInstance.*`, `RedSessionBrowserWidget.*`, `RedHUD.*` | SIK browser; App 480 |
| Меню | `RedPauseMenuWidget.*` | Рядок Multiplayer в Escape |
| GameMode | `RedGameMode.*`, у clean — `RedPPGGameplayGameMode.cpp` | Різні дефолти Titan vs clean RedMMO |
| Celestial / MP consumers | `RedCelestialFrameRegistry.*` | M05 ще відкритий |
| Тести MP | `Source/RedMMO/Tests/RedDEF0003TwoClientPIETests.cpp` | Listen-server helpers — не вважати повним Steam-доказом |

**Анімація (захищено):** `ABP_RedTrooperFemale` — **не переписуй run/locomotion** без окремого дозволу. Aim/jetpack — адитивно. FocalRig з Fab відсутній → substitute ControlRig у `RedMMOEditorTools`.

---

## З чого починати (порядок)

1. **День 1 — без планетарних Fab:** `TitanFundamentals.uproject` → TitanEditor → PIE ThirdPersonMap. Переконайся, що збірка йде без PlanetGen/PPG/FocalRig/WorldGen.
2. **День 1–2 — реплікація listen-server:** Play → 2 Players, Net Mode = Listen Server. Перевір move/aim/fire/jetpack між вікнами (NULL OSS ок для цього гейту).
3. **День 2–3 — цикл урону PvP:** Health/Shield, `bIsEnemy`, downed, авторитет попадань у `RedPlayerCharacter` / `RedBolt`. Deathmatch/score — лише після стабільної реплікації.
4. **Розміщення хаба:** networked actors / PlayerStarts, що мають переживати env-delivery, тримай у `L_Hub_Gameplay_Logic`, не в env-саблевелі.
5. **Коли готові Steam:** увімкнути/скопіювати `Plugins/SteamIntegrationKit`, Epic OSS Steam **вимкнені**, клієнт Steam, App **480**. Хост на A, join на B з **різних** акаунтів.
6. **Відкласти:** PPG home, карти PlanetGen, fused terrain, фінальний арт — не блокують netcode.

---

## Відомі прогалини (мережа / MP)

- Реальний **1 server + 2 clients** Steam-транспорт (initial/update/stale/late-join)  
- Dedicated server, persistence, matchmaking, власний Steam App ID  
- Radar/minimap consumers у мультиплеєрі  
- Warp / міжпланетна реплікація  
- Packaged PvP двох акаунтів  
- Паритет сесій clean RedMMO vs Titan  

---

## Захищені речі

- **Running animation** / locomotion guard на trooper ABP  
- Ідентичність пакета R92; хеші fused 27/6  
- Не вмикай одночасно SIK і Epic OnlineSubsystemSteam  

---

## Fab / плагіни для цього треку

Див. [FAB_MARKETPLACE_INVENTORY_UK.md](./FAB_MARKETPLACE_INVENTORY_UK.md).

| Потрібно | Плагін |
|---|---|
| Netcode PIE fundamentals | **Нічого** з Fab |
| Steam-сесії з друзями | **SteamIntegrationKit** (~297 MB — може знадобитися копія з машини власника) |
| Планетарні карти | PPG / PlanetGen — **опційно пізніше** |
