# ПОЧНИ ТУТ — передача RedMMOTitan розробнику

**Створено:** 2026-08-07  
**Мова:** українська · English: [START_HERE.md](./START_HERE.md)  
**PDF (UA):** [RedMMOTitan_Developer_Handoff_UK.pdf](./RedMMOTitan_Developer_Handoff_UK.pdf)  
**PDF (EN):** [RedMMOTitan_Developer_Handoff.pdf](./RedMMOTitan_Developer_Handoff.pdf)  
**Мережа / PvP (для тебе):** [NETWORKING_PVP_UK.md](./NETWORKING_PVP_UK.md)  
**Fab-інвентар:** [FAB_MARKETPLACE_INVENTORY_UK.md](./FAB_MARKETPLACE_INVENTORY_UK.md)  
**Без PPG/PlanetGen:** [PPG_PLANETGEN_FREE_START_UK.md](./PPG_PLANETGEN_FREE_START_UK.md)

---

## Хто ти в цій передачі

Ти **програміст** з фокусом на **мережу, реплікацію, мультиплеєр, PvP і геймплей-системи**.  
Планетарний арт / PPG — **не** твій обов’язковий старт. Спочатку збирай і PIE без PlanetGen/PPG, потім listen-server реплікація, потім Steam.

**Колаборатор:** `sanyarud@gmail.com` → GitHub **`sanyarud`** (write/push, запрошення pending accept).

---

## 60 секунд

1. Клонуй standalone handoff (**public**, invite не потрібен):  
   `git clone https://github.com/addgamestudios-ops/RedMMOTitan-DeveloperHandoff.git`
2. Для write у повний private Titan — прийми запрошення GitHub (якщо ще pending).
3. Встанови **Unreal Engine 5.8**.
4. Відкрий **`TitanFundamentals.uproject`** (не потребує PPG/PlanetGen).
5. Збери **TitanEditor** Win64 Development → PIE на `/Game/ThirdPerson/Maps/ThirdPersonMap`.
6. Читай [NETWORKING_PVP_UK.md](./NETWORKING_PVP_UK.md) перед змінами реплікації.

---

## Збірка / PIE

```powershell
git clone https://github.com/addgamestudios-ops/RedMMOTitan-DeveloperHandoff.git
cd RedMMOTitan-DeveloperHandoff
start TitanFundamentals.uproject
```

| Перевірка | Очікування |
|---|---|
| Редактор відкриває ThirdPersonMap | Немає жорсткого фейлу через відсутність PPG/PlanetGen |
| PIE | WASD + миша |
| 2 Players + Listen Server | Реплікація руху/пострілу/jetpack між вікнами |
| **Running anim** | **Не ламай** locomotion на `ABP_RedTrooperFemale` |

---

## Репозиторії

| Репо | URL | Доступ |
|---|---|---|
| **Standalone handoff (почни тут)** | https://github.com/addgamestudios-ops/RedMMOTitan-DeveloperHandoff | **public** — clone без invite |
| Повний Titan (історичний) | https://github.com/addgamestudios-ops/RedMMOTitan | private, write invite → `sanyarud` |

---

## Захищено

- Running / locomotion на trooper ABP  
- Не вмикай одночасно SIK і Epic OnlineSubsystemSteam  
- Не `git reset --hard` брудний worktree власника на `D:\RedMMOTitan`

Повна передача: [DEVELOPER_HANDOFF_UK.md](./DEVELOPER_HANDOFF_UK.md).
