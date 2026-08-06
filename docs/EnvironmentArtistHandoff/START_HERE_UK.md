# START HERE — Red MMO передача художнику середовища (UK)

**Дата:** 2026-08-07  
**English:** [START_HERE.md](./START_HERE.md)  
**PDF (EN):** [RedMMO_Environment_Artist_Handoff.pdf](./RedMMO_Environment_Artist_Handoff.pdf)  
**Злиття з геймплеєм:** [MERGE_ENV_AND_GAMEPLAY_UK.md](./MERGE_ENV_AND_GAMEPLAY_UK.md) · повна EN [MERGE_ENV_AND_GAMEPLAY.md](./MERGE_ENV_AND_GAMEPLAY.md)  
**Fab / паки:** [ENV_FAB_INVENTORY.md](./ENV_FAB_INVENTORY.md)  
**Папки:** [FOLDER_OWNERSHIP.md](./FOLDER_OWNERSHIP.md)

Назва продукту: **Red MMO**. Шляхи `Titan.uproject` / `RedMMOTitan*` — лише технічні.

Окрема роль (геймплей / мережа): `Docs/DeveloperHandoff/`.

---

## Шлях на 60 секунд

1. Встановіть **Unreal Engine 5.8**.
2. Відкрийте **Titan**: `D:\RedMMOTitan\Titan.uproject` (для планетарних карт потрібен PlanetGen).
3. Відкрийте **одну** з двох тестових карт (нижче).
4. Прочитайте [MERGE_ENV_AND_GAMEPLAY_UK.md](./MERGE_ENV_AND_GAMEPLAY_UK.md) перед злиттям хаба з геймплей-картою.
5. Лише **один** Unreal Editor одночасно.

---

## Дві карти для роботи

Обидві в проєкті **Titan** (`D:\RedMMOTitan`).

| # | Soft path | Роль |
|---|---|---|
| **1** | `/Game/RedMMO/Maps/RedPlanetGen_50km_ArtistCanvas` | Планетарний canvas середовища (50 км) |
| **2** | `/Game/RedMMO/Maps/Sandbox_DesertDemoSparkle_T01` | Пустельний sandbox для level design / props / light |

**Пов’язані (не основна пара):** TropicalTile R15 V3 (Titan Tests); `RedMMO_PPG_HomeWorld` лише в clean RedMMO + PPG.

---

## Не чіпати

- Player pawn / Character BP і C++  
- **Running animation**  
- Зброя, снаряди, aim chain  
- Реплікація / GameMode / netcode  
- Захищені карти: `RedPlanetGen`, `RedPlanetGen_50km_Test`, `RedPlanetGen_50km_FusedPrototype`  
- Майстер-матеріали marketplace (лише project-owned MI)

---

## Пакет

- GitHub: https://github.com/addgamestudios-ops/RedMMOTitan-DeveloperHandoff → `Docs/EnvironmentArtistHandoff/`  
- Desktop: `C:\Users\user\Desktop\RedMMO_EnvironmentArtist_Handoff\`
