# RedMMOTitan — передача розробнику (UK, 2026-08-07)

**Статус:** достатньо добре для takeover. Багато проблем лишається.  
**English:** [DEVELOPER_HANDOFF.md](./DEVELOPER_HANDOFF.md)  
**Netcode/PvP:** [NETWORKING_PVP_UK.md](./NETWORKING_PVP_UK.md) · [NETWORKING_PVP.md](./NETWORKING_PVP.md)

| Артефакт | Шлях |
|---|---|
| START_HERE (UK) | [START_HERE_UK.md](./START_HERE_UK.md) |
| PDF UK | [RedMMOTitan_Developer_Handoff_UK.pdf](./RedMMOTitan_Developer_Handoff_UK.pdf) |
| PDF EN | [RedMMOTitan_Developer_Handoff.pdf](./RedMMOTitan_Developer_Handoff.pdf) |
| Fab | [FAB_MARKETPLACE_INVENTORY_UK.md](./FAB_MARKETPLACE_INVENTORY_UK.md) |
| Без PPG | [PPG_PLANETGEN_FREE_START_UK.md](./PPG_PLANETGEN_FREE_START_UK.md) |
| GitHub | [GITHUB_ACCESS.md](./GITHUB_ACCESS.md) |
| Діагностика | `D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_DeveloperHandoff_20260807\` |

**Колаборатор:** sanyarud@gmail.com → GitHub **sanyarud** (write, pending accept).

---

## 1. Шляхи

| Роль | Шлях |
|---|---|
| Standalone clone | `RedMMOTitan-DeveloperHandoff` → `TitanFundamentals.uproject` |
| Owner repo | `D:\RedMMOTitan` |
| Clean planetary RedMMO | `D:\RedMMOTitanWindowsData\Projects\RedMMO\RedMMO.uproject` (потрібен PPG) |
| R92 package | `...\Builds\RedMMO_R92_Playable_20260806T1740Z\Windows\RedMMO.exe` |
| Engine | `D:\UE_5.8` |

---

## 2. Що працює / що ні

**Працює (з обмеженнями доказів):** TitanEditor збірка з вимкненими FocalRig/WorldGen і shim PlanetGen; live PIE-фікси (wheel→thrust, atmosphere exit, weapons/plumes/jetpack, terrain blend); R92 packaged baseline; listen-server реплікація aim/fire/jetpack (не Steam two-account).

**Відкрито:** фізичний feel, HUD fuel pixels, біоми, fused consumer, M04/M05, Steam two-account PvP, dedicated server.

---

## 3. FocalRig / WorldGen / PlanetGen

| Плагін | Статус |
|---|---|
| FocalRig | Disabled + ControlRig substitute |
| WorldGen | Disabled |
| PlanetGen fork | Відсутній; `RedPlanetGenCompat` shim |
| PPG | Лише clean RedMMO; **не потрібен** для fundamentals/netcode |

---

## 4. Збірка / PIE без PPG

Див. [PPG_PLANETGEN_FREE_START_UK.md](./PPG_PLANETGEN_FREE_START_UK.md).  
`TitanFundamentals.uproject` + ThirdPersonMap.

## 5. MCP порти

Epic `:8000`, Nwiro `:5353`, UAIP `:8765` (заблокований — немає payload).

## 6. Захищено

Running anim; fused hashes; R92 package; один UnrealEditor; не dual Steam OSS.

## 7. Наступна робота для netcode/PvP програміста

1. Fundamentals PIE без планет.  
2. Listen-server 2P реплікація.  
3. Цикл урону PvP.  
4. Потім Steam SIK + два акаунти.  

Деталі: [NETWORKING_PVP_UK.md](./NETWORKING_PVP_UK.md).
