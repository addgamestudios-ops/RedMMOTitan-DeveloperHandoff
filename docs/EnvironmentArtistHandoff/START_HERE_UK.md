# ПОЧНИ ТУТ — передача **Red MMO** художнику середовища

**Створено:** 2026-08-07  
**English:** [START_HERE.md](./START_HERE.md)  
**PDF (UA):** [RedMMO_Environment_Artist_Handoff_UK.pdf](./RedMMO_Environment_Artist_Handoff_UK.pdf) · **PDF (EN):** [RedMMO_Environment_Artist_Handoff.pdf](./RedMMO_Environment_Artist_Handoff.pdf)

Продукт у текстах: **Red MMO**. Імена на кшталт `Titan.uproject` / `RedMMOTitan*` — лише технічні шляхи.

Роль геймплею / netcode (окремо): [../DeveloperHandoff/START_HERE_UK.md](../DeveloperHandoff/START_HERE_UK.md)

---

## Головне: те саме репо, merge-safe світ (читай першим)

Ти і gameplay-розробник працюєте в **тому самому GitHub-репозиторії**. Твій env хаба **не перезапише** HubLogic, і розробник **не перезапише** твій env-пакет — **якщо тримаєш розділене володіння**:

| Шар | Пакет | Власник |
|---|---|---|
| Тонкий persistent | `/Game/RedMMO/Maps/Hubs/L_Hub_Persistent` | Lead / рідкі правки |
| **Environment (ти)** | `/Game/RedMMO/Maps/Hubs/L_Hub_Env_Visuals` | **Environment artist** |
| HubLogic | `/Game/RedMMO/Maps/Hubs/L_Hub_Gameplay_Logic` | Gameplay developer |

- Landscape, lighting, fog/post, foliage, static meshes, set dressing — у **`L_Hub_Env_Visuals`**.
- **Не** редагуй **`L_Hub_Gameplay_Logic`** (PlayerStarts, combat volumes, replicated actors).
- **Не** чіпай pawn / Character BP, running animation, зброю, netcode.
- Деталі: [MERGE_ENV_AND_GAMEPLAY_UK.md](./MERGE_ENV_AND_GAMEPLAY_UK.md) · дзеркало для розробника: [../DeveloperHandoff/MERGE_SAFE_WORLD_UK.md](../DeveloperHandoff/MERGE_SAFE_WORLD_UK.md).

**Одним реченням:** клонуй те саме handoff-репо, що й геймплей-розробник; володій `L_Hub_Env_Visuals` (+ ArtistCanvas / Desert sandbox для тестів); HubLogic і gameplay-код не чіпай.

---

## 60 секунд

1. Клон: `https://github.com/addgamestudios-ops/RedMMOTitan-DeveloperHandoff.git`
2. Встанови **Unreal Engine 5.8**.
3. Відкрий проєкт із потрібним Content:
   - Stub-и хаба / fundamentals: **`TitanFundamentals.uproject`** у клоні  
   - Повний Titan Content: **`Titan.uproject`**
4. Відкривай **свої** карти. Не сейв у HubLogic.
5. Прочитай [MERGE_ENV_AND_GAMEPLAY_UK.md](./MERGE_ENV_AND_GAMEPLAY_UK.md) перед delivery хаба.
6. Лише **один** Unreal Editor одночасно.

```powershell
git clone https://github.com/addgamestudios-ops/RedMMOTitan-DeveloperHandoff.git
cd RedMMOTitan-DeveloperHandoff
start TitanFundamentals.uproject
```

| Перевірка | Очікування |
|---|---|
| Stub-и хаба | `L_Hub_Persistent`, `L_Hub_Env_Visuals`, `L_Hub_Gameplay_Logic` |
| Твій save target | **`L_Hub_Env_Visuals`** для hub delivery |
| HubLogic | Є, але **не** твоя зона редагування |
| Тестові карти (повний Titan) | ArtistCanvas і/або Desert sandbox |
| **Running anim / pawn / зброя** | Не чіпати |

---

## Карти, які відкриваєш

**Hub delivery:** володієш **`L_Hub_Env_Visuals`**. Persistent — лише інтеграція. **`L_Hub_Gameplay_Logic`** — не чіпати.

**Тести (повний Titan Content):**

| Soft path | Роль |
|---|---|
| `/Game/RedMMO/Maps/RedPlanetGen_50km_ArtistCanvas` | Планетарний canvas (PlanetGen) |
| `/Game/RedMMO/Maps/Sandbox_DesertDemoSparkle_T01` | Пустельний sandbox для LD / props / light |

---

## Не чіпати

- **`L_Hub_Gameplay_Logic`** (HubLogic розробника)  
- Player pawn / Character BP і C++  
- **Running animation**  
- Зброя, снаряди, aim chain  
- Реплікація / GameMode / netcode  
- Захищені карти: `RedPlanetGen`, `RedPlanetGen_50km_Test`, `RedPlanetGen_50km_FusedPrototype`  
- Майстер-матеріали marketplace (лише project-owned MI)

---

## Далі читати

| Док | Навіщо |
|---|---|
| [MERGE_ENV_AND_GAMEPLAY_UK.md](./MERGE_ENV_AND_GAMEPLAY_UK.md) | Merge без overwrite |
| [ENVIRONMENT_ARTIST_HANDOFF_UK.md](./ENVIRONMENT_ARTIST_HANDOFF_UK.md) | Шляхи, плагіни, чеклист |
| [MAPS.md](./MAPS.md) | Ідентичність карт |
| [ENV_FAB_INVENTORY.md](./ENV_FAB_INVENTORY.md) | Fab / арт-паки |

---

## Пакет

- GitHub: https://github.com/addgamestudios-ops/RedMMOTitan-DeveloperHandoff/tree/main/docs/EnvironmentArtistHandoff  
- Desktop: `C:\Users\user\Desktop\RedMMO_EnvironmentArtist_Handoff\`
