# Спільне репо, merge-safe володіння світом

**Це головне правило колаборації для Red MMO.**  
Геймплей і оточення працюють у **тому самому GitHub-репозиторії**, на **окремих Unreal map-пакетах**, щоб арт хаба міг підключитись без переписування геймплею і без бінарних конфліктів `.umap`.

Повна версія для арт-ролі: [../EnvironmentArtistHandoff/MERGE_ENV_AND_GAMEPLAY_UK.md](../EnvironmentArtistHandoff/MERGE_ENV_AND_GAMEPLAY_UK.md) · EN: [MERGE_ENV_AND_GAMEPLAY.md](../EnvironmentArtistHandoff/MERGE_ENV_AND_GAMEPLAY.md).

---

## Що тобі гарантовано

| Потреба | Як забезпечено |
|---|---|
| Світ/карта, яку **не втратять**, коли збудують env хаба | Твої gameplay-актори в **`L_Hub_Gameplay_Logic`** (HubLogic). Env-декор — у **`L_Hub_Env_Visuals`**. |
| **Не перепрограмовувати все** після фінішу env-артистів | C++ / Blueprint (Character, GameMode, зброя, AnimBP) — окремі пакети від env `.umap`. Арт міняє env-саблевел; твоя логіка лишається. |
| Колаборація в **тому ж репо** без overwrite іншої дисципліни | Артисти не комітять gameplay-саблевел; ти не редагуєш env-саблевел. Тонкий Persistent лише підключає обидва. |

---

## Структура карт (стартер у fundamentals)

```text
/Game/RedMMO/Maps/Hubs/L_Hub_Persistent          ← тонка оболонка (лише streaming; рідко чіпають)
/Game/RedMMO/Maps/Hubs/L_Hub_Env_Visuals         ← environment artists
/Game/RedMMO/Maps/Hubs/L_Hub_Gameplay_Logic      ← ти (HubLogic): PlayerStarts, volumes, replicated actors
```

| Власник | Володіє | Не чіпати |
|---|---|---|
| **Gameplay developer** | `L_Hub_Gameplay_Logic`, `Source/`, gameplay BP, netcode | Env `.umap` артистів |
| **Environment artist** | `L_Hub_Env_Visuals`, landscape/lighting/foliage/dressing | Gameplay-саблевел, Character/GameMode |
| **Lead / за домовленістю** | Склад `L_Hub_Persistent` (які саблевели грузяться) | Щоденний арт або combat всередині Persistent |

День 1: збірка / listen-server PIE можна на `/Game/ThirdPerson/Maps/ThirdPersonMap`. **Хаб**-геймплей, який має переживати env-delivery, клади в **`L_Hub_Gameplay_Logic`**.

---

## Правила роботи

1. Клонуй handoff-репо; відкривай **`TitanFundamentals.uproject`**.
2. PlayerStarts, combat volumes, spawn managers, networked actors — у **`L_Hub_Gameplay_Logic`**.
3. Не роби довгостроковий вигляд хаба всередині gameplay-саблевела чи в одному спільному `HubWorld.umap`.
4. Не редагуй `L_Hub_Env_Visuals` (і env-delivery карти) як свій ownership-файл.
5. Коли env готовий — Persistent грузить обидва; фіксиш лише cross-level посилання, не повний rewrite.

**Бінарна правда:** двоє, що сейвлять той самий `.umap`, не змержаться через git. Спочатку розділи пакети.

---

## Одне речення для розробника

Клонуй handoff-репо, працюй у шарі HubLogic / gameplay (`L_Hub_Gameplay_Logic` + C++/BP); артисти володіють env-саблевелом і не перезапишуть твій код чи gameplay-карту.
