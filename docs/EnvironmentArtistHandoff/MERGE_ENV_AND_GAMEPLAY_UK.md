# Спільне репо: злиття env + HubLogic (погляд артиста)

**Це головне правило колаборації для Red MMO — сторона середовища.**  
Геймплей і оточення працюють у **тому самому GitHub-репозиторії**, на **окремих Unreal map-пакетах**, щоб арт хаба міг підключитись без переписування геймплею і без бінарних конфліктів `.umap`.

Дзеркало для розробника: [../DeveloperHandoff/MERGE_SAFE_WORLD_UK.md](../DeveloperHandoff/MERGE_SAFE_WORLD_UK.md) · повна EN: [MERGE_ENV_AND_GAMEPLAY.md](./MERGE_ENV_AND_GAMEPLAY.md).

---

## Що тобі гарантовано

| Потреба | Як забезпечено |
|---|---|
| Візуали хаба, що **живуть поруч** із HubLogic | Твій декор у **`L_Hub_Env_Visuals`**. Актори розробника — у **`L_Hub_Gameplay_Logic`**. |
| Розробник **не перезапише** твій env-delivery | Розробники не комітять твій env-саблевел; ти не редагуєш HubLogic. |
| **Не** переробляти pawn / зброю / netcode після compose | Це окремі пакети від env `.umap`. Persistent лише стрімить обидва. |

---

## Структура карт

```text
/Game/RedMMO/Maps/Hubs/L_Hub_Persistent          ← тонка оболонка (лише streaming; рідко чіпають)
/Game/RedMMO/Maps/Hubs/L_Hub_Env_Visuals         ← ти (environment)
/Game/RedMMO/Maps/Hubs/L_Hub_Gameplay_Logic      ← gameplay developer (HubLogic)
```

| Власник | Володіє | Не чіпати |
|---|---|---|
| **Environment artist** | `L_Hub_Env_Visuals`, landscape/lighting/foliage/dressing, ArtistCanvas / Desert sandbox за завданням | `L_Hub_Gameplay_Logic`, Character/GameMode/зброя/netcode |
| **Gameplay developer** | `L_Hub_Gameplay_Logic`, `Source/`, gameplay BP, netcode | Env `.umap` артистів |
| **Lead / за домовленістю** | Склад `L_Hub_Persistent` | Щоденний арт або combat всередині Persistent |

```text
L_Hub_Persistent          ← тонка оболонка
├── L_Hub_Env_Visuals     ← ти
└── L_Hub_Gameplay_Logic  ← розробник / HubLogic (не чіпати)
```

---

## Правила роботи

1. Клонуй **те саме** handoff-репо, що й геймплей-розробник.  
2. Хаб-візуали — у **`L_Hub_Env_Visuals`**.  
3. ArtistCanvas / Desert sandbox — для експериментів; фінальний hub look віддавай у `L_Hub_Env_Visuals`, не в HubLogic.  
4. Не клади PlayerStarts, combat volumes, spawn managers, networked actors у свій env-пакет.  
5. Не сейв одночасно той самий `.umap`, що й розробник.

**Бінарна правда:** двоє, що сейвлять той самий `.umap`, не змержаться через git. Спочатку розділи пакети.

---

## Варіанти (рейтинг)

| | Метод | Коли |
|---|---|---|
| **A** | Іменовані hub-пакети Persistent / Env / HubLogic (найкраще) | Нова робота хаба |
| **B** | Міграція лише env-акторів | Вже є дві роз’їхані карти |
| **C** | OFPA / external actors (WP) | Великі WP-карти; не замінює ownership |

---

## Гарантії

- Злити hub graphics + HubLogic **без переробки хаба з нуля** — так (A/B).  
- Залишити C++/BP геймплею при зміні env `.umap` — так.  
- Обидва зберігають один `.umap` і «змерджать у git» — **ні**.

---

## Одне речення для художника середовища

Клонуй те саме handoff-репо, володій `L_Hub_Env_Visuals` (+ ArtistCanvas / Desert sandbox за потреби); gameplay-розробник володіє HubLogic і не перезапише твій env-пакет, якщо обидва тримають цей split.
