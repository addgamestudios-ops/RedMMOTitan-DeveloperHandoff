# ПОЧНИ ТУТ — передача **Red MMO** розробнику

**Створено:** 2026-08-07  
**English:** [START_HERE.md](./START_HERE.md)  
**PDF (UA):** [RedMMOTitan_Developer_Handoff_UK.pdf](./RedMMOTitan_Developer_Handoff_UK.pdf) · **PDF (EN):** [RedMMOTitan_Developer_Handoff.pdf](./RedMMOTitan_Developer_Handoff.pdf)

Продукт у текстах: **Red MMO**. Імена на кшталт `TitanFundamentals.uproject` / `RedMMOTitan*` — лише технічні шляхи.

---

## Головне: те саме репо, merge-safe світ (читай першим)

Ти і environment-артисти працюєте в **тому самому GitHub-репозиторії**. Ти **не втратиш** hub-геймплей, коли збудують оточення player hub, і **не переписуватимеш усе** після арту — **якщо тримаєш розділене володіння**:

| Шар | Пакет | Власник |
|---|---|---|
| Тонкий persistent | `/Game/RedMMO/Maps/Hubs/L_Hub_Persistent` | Lead / рідкі правки |
| Environment | `/Game/RedMMO/Maps/Hubs/L_Hub_Env_Visuals` | Environment artists |
| **HubLogic (ти)** | `/Game/RedMMO/Maps/Hubs/L_Hub_Gameplay_Logic` | **Gameplay developer** |

- PlayerStarts, volumes, spawn managers, replicated / networked actors — у **`L_Hub_Gameplay_Logic`**.
- **Не** редагуй artist-owned env `.umap`.
- C++ / gameplay Blueprint лишаються в твоїх пакетах — незалежно від сейвів env-карти.
- Деталі: [MERGE_SAFE_WORLD_UK.md](./MERGE_SAFE_WORLD_UK.md) · merge для артистів: [../EnvironmentArtistHandoff/MERGE_ENV_AND_GAMEPLAY_UK.md](../EnvironmentArtistHandoff/MERGE_ENV_AND_GAMEPLAY_UK.md).

**Одним реченням:** клонуй це handoff-репо, працюй у шарі HubLogic / gameplay; артисти не перезапишуть твій код чи gameplay-карту.

---

## 60 секунд

1. Клон: `https://github.com/addgamestudios-ops/RedMMOTitan-DeveloperHandoff.git`
2. Встанови **Unreal Engine 5.8**.
3. Відкрий **`TitanFundamentals.uproject`** (PlanetGen / PPG не потрібні).
4. Збери **TitanEditor** Win64 Development.
5. День 1 PIE: `/Game/ThirdPerson/Maps/ThirdPersonMap` (controls / listen-server).  
   Хаб-робота, що має переживати env: **`L_Hub_Gameplay_Logic`** у `/Game/RedMMO/Maps/Hubs/`.
6. Netcode: [NETWORKING_PVP_UK.md](./NETWORKING_PVP_UK.md). Повний пак: [DEVELOPER_HANDOFF_UK.md](./DEVELOPER_HANDOFF_UK.md).

```powershell
git clone https://github.com/addgamestudios-ops/RedMMOTitan-DeveloperHandoff.git
cd RedMMOTitan-DeveloperHandoff
start TitanFundamentals.uproject
```

| Перевірка | Очікування |
|---|---|
| Редактор без планетарних плагінів | Немає жорсткого фейлу через PPG / PlanetGen |
| PIE на ThirdPersonMap | Рух; listen-server 2P для реплікації |
| Stub-и хаба | `L_Hub_Persistent`, `L_Hub_Env_Visuals`, `L_Hub_Gameplay_Logic` |
| Env-саблевел | Не сейвиш свою ownership у цей пакет |
| **Running anim** | Не перезаписуй locomotion trooper без дозволу |

---

## Далі читати

| Док | Навіщо |
|---|---|
| [MERGE_SAFE_WORLD_UK.md](./MERGE_SAFE_WORLD_UK.md) | Володіння в одному репо + шлях без overwrite |
| [NETWORKING_PVP_UK.md](./NETWORKING_PVP_UK.md) | Listen-server, реплікація, PvP |
| [DEVELOPER_HANDOFF_UK.md](./DEVELOPER_HANDOFF_UK.md) | Шляхи, захищене, плагіни |
| [PPG_PLANETGEN_FREE_START_UK.md](./PPG_PLANETGEN_FREE_START_UK.md) | Fundamentals без планетарних плагінів |
| [FAB_MARKETPLACE_INVENTORY_UK.md](./FAB_MARKETPLACE_INVENTORY_UK.md) | Опційні marketplace-плагіни пізніше |

**Роль environment artist (окремо):** [../EnvironmentArtistHandoff/START_HERE_UK.md](../EnvironmentArtistHandoff/START_HERE_UK.md)

---

## Захищено (коротко)

- Running / locomotion на `ABP_RedTrooperFemale`
- Env map-пакети артистів (не роби з них свій hub-файл)
- Не вмикай одночасно Steam Integration Kit і Epic OnlineSubsystemSteam
