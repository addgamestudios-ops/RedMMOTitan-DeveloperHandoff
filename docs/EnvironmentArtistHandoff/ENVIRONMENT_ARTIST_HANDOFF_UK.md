# Red MMO — передача художнику середовища (UK, 2026-08-07)

**Статус:** достатньо, щоб підхопити візуали хаба й env-тестові карти. Повний marketplace Content може потребувати sync диска.  
**English:** [ENVIRONMENT_ARTIST_HANDOFF.md](./ENVIRONMENT_ARTIST_HANDOFF.md) · **Старт:** [START_HERE_UK.md](./START_HERE_UK.md)

**Аудиторія:** 3D environmental / level-design художник. Спочатку володіння світом: [MERGE_ENV_AND_GAMEPLAY_UK.md](./MERGE_ENV_AND_GAMEPLAY_UK.md).

| Артефакт | Шлях |
|---|---|
| START_HERE | [START_HERE_UK.md](./START_HERE_UK.md) |
| Merge-safe світ (env) | [MERGE_ENV_AND_GAMEPLAY_UK.md](./MERGE_ENV_AND_GAMEPLAY_UK.md) |
| PDF UK / EN | [RedMMO_Environment_Artist_Handoff_UK.pdf](./RedMMO_Environment_Artist_Handoff_UK.pdf) · [RedMMO_Environment_Artist_Handoff.pdf](./RedMMO_Environment_Artist_Handoff.pdf) |
| Карти / Fab | [MAPS.md](./MAPS.md) · [ENV_FAB_INVENTORY.md](./ENV_FAB_INVENTORY.md) |
| Клон (той самий, що в геймплею) | https://github.com/addgamestudios-ops/RedMMOTitan-DeveloperHandoff.git |

---

## 1. Колаборація в тому ж репо (обов’язково)

Геймплей і оточення — один репозиторій. Розділене володіння захищає від overwrite:

```text
L_Hub_Persistent          ← тонка оболонка (лише streaming)
├── L_Hub_Env_Visuals     ← ти
└── L_Hub_Gameplay_Logic  ← розробник / HubLogic (не редагуй)
```

| Ти володієш | Розробник володіє |
|---|---|
| `L_Hub_Env_Visuals`, landscape, lighting, foliage, dressing | `L_Hub_Gameplay_Logic`, `Source/RedMMO`, gameplay BP, netcode |

**Гарантії:** твій env-delivery ≠ HubLogic-файл; C++/BP не переписуються при зміні env `.umap`; git не змержить двох авторів одного бінарного `.umap`.

Узгоджено з [../DeveloperHandoff/MERGE_SAFE_WORLD_UK.md](../DeveloperHandoff/MERGE_SAFE_WORLD_UK.md).

---

## 2. Шляхи

| Роль | Шлях |
|---|---|
| Standalone handoff (клонуй це) | `RedMMOTitan-DeveloperHandoff` → `TitanFundamentals.uproject` |
| Stub-и хаба | `/Game/RedMMO/Maps/Hubs/` |
| Твій hub save target | `L_Hub_Env_Visuals` |
| Env-тести (повний Titan Content) | ArtistCanvas · Sandbox_DesertDemoSparkle_T01 |
| Engine | Unreal Engine **5.8** |

---

## 3. Що працює / що відкрито

**Достатньо для старту:** іменовані stub-и Persistent / Env / HubLogic; паралельне володіння з геймплеєм; на повному Titan — ArtistCanvas і Desert sandbox; World-папки Quarantine → Approved.

**Відкрито:** повні Fab-дерева (десятки GB) не всі в git; compose Persistent з готовим env + HubLogic; ArtistCanvas потребує PlanetGen на UE 5.8.

---

## 4. День 1

```powershell
git clone https://github.com/addgamestudios-ops/RedMMOTitan-DeveloperHandoff.git
cd RedMMOTitan-DeveloperHandoff
start TitanFundamentals.uproject
```

Хаб-візуали → **`L_Hub_Env_Visuals`**. HubLogic → **не чіпати**. Інтеграція → **`L_Hub_Persistent`**.

---

## 5. Плагіни (env)

Hub stubs у fundamentals — без PlanetGen/PPG. ArtistCanvas / RedPlanetGen* — **PlanetGen**. Desert sandbox зазвичай без PPG. Див. [ENV_FAB_INVENTORY.md](./ENV_FAB_INVENTORY.md).

---

## 6. Захищено

`L_Hub_Gameplay_Logic`; running anim; pawn; зброя; netcode; захищені planetary maps; marketplace masters (лише MI).

---

## 7. Наступна робота

1. Клон того ж репо → **`L_Hub_Env_Visuals`**.  
2. Блокаут хаба без gameplay-акторів.  
3. Look-dev на ArtistCanvas / Desert sandbox, коли є Content.  
4. Віддай env-пакет + скріни; integration day грузить Persistent з HubLogic.  
5. Не «фікси» gameplay-акторів і не переписуй AnimBP.
