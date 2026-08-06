# Старт без PPG / PlanetGen (обов’язково для онбордингу)

**Мета:** збирати й запускати PIE **без** встановлення PPG чи PlanetGen.  
**English:** [PPG_PLANETGEN_FREE_START.md](./PPG_PLANETGEN_FREE_START.md)

## Вердикт

| Шлях | PPG? | PlanetGen? | Для чого |
|---|---|---|---|
| **`TitanFundamentals.uproject` + ThirdPersonMap** | Ні | Ні | Збірка, controls, зброя, HUD, **netcode PIE** |
| `Titan.uproject` + RedPlanetGen | Ні | Так | Повний Titan-планета |
| Clean `RedMMO.uproject` + PPG Home | Так | Окремо | R92 planetary baseline |

## Як стартувати

1. Відкрий `TitanFundamentals.uproject`.  
2. PlanetGen / WorldGen / FocalRig = **false**; PPG відсутній у цьому uproject.  
3. Карта: `/Game/ThirdPerson/Maps/ThirdPersonMap`.  
4. Build TitanEditor → PIE → (для мережі) 2 Players Listen Server.

## Шими в коді

- `RedPlanetGenCompat.*` — лінк без fork API  
- FocalRig optional у `RedMMO.Build.cs` + ControlRig substitute  

## Пізніше

Планетарні плагіни — див. Fab-інвентар. Для мережі/PvP це **не блокер**.
