# Unreal storage migration - 2026-07-14

## Outcome

The Unreal Engine 5.8 installation and RedMMOTitan workspace are on D:, and the high-churn Unreal/Epic caches that could safely be moved without administrator rights now resolve to D:. No project asset, source file, screenshot, Fab pack, or rollback map was deleted.

- Engine: `D:/UE_5.8` (about 40.915 GiB)
- Project: `D:/RedMMOTitan` (about 22.264 GiB)
- Build products, logs, temporary files, and diagnostics: `D:/RedMMOTitanWindowsData`
- User `TEMP` and `TMP`: `D:/RedMMOTitanWindowsData/UserTemp`
- Active project DDC override: `D:/RedMMOTitanWindowsData/DDC`
- Verified free space after migration: C: 1.560 GiB; D: 1157.928 GiB

## Verified D-drive redirects

The original C: paths remain as junction-compatible entry points so Unreal and Epic tools do not lose their expected paths:

- Unreal Engine common analytics, DDC, trace, and Zen data
- Unreal Engine version/editor/intermediate AppData directories, including 5.8
- UnrealBuildTool local data
- roaming `Unreal Engine` data
- the user's `Documents/Unreal Projects` directory
- Epic Games Launcher local `com`, `Intermediate`, and `Saved` data
- Epic Games Launcher ProgramData `Data`
- Unreal Build Accelerator ProgramData
- Epic VaultCache (already redirected to `D:/EpicGamesLauncher/VaultCache`)

The post-migration build, automation tests, fresh asset reload, and game-mode smoke all ran successfully with temporary/build/cache activity on D:.

## Intentionally retained on C:

These items were not deleted or force-moved:

- `C:/Program Files (x86)/Epic Games/Launcher` (about 1.609 GiB)
- `C:/Program Files (x86)/Epic Games/Epic Online Services` (about 0.770 GiB)
- Windows SDK files required by the UE Windows toolchain
- the Windows-managed page file

The Epic Launcher/EOS folders are protected by Program Files ACLs. A non-elevated move was denied before any source file was removed; the source installations remain intact and the empty partial destination was removed. Finishing that optional 2.379 GiB relocation requires an elevated Epic Launcher reinstall or administrator-managed move to D:. The Windows SDK must remain available to Unreal, and the page file should only be relocated through Windows virtual-memory settings followed by a reboot.

## Safety rule

Do not manually delete the retained C: components. Reinstall Launcher/EOS to D: with administrator rights, verify Fab/Vault access and Unreal launch, and only then remove an obsolete installation through Windows Apps/Installed Apps.
