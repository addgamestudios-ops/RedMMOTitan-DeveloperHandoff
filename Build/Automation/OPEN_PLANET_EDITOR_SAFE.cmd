@echo off
setlocal
set "PROJECT=%~dp0Titan.uproject"

for %%E in (
  "D:\UE_5.8\Engine\Binaries\Win64\UnrealEditor.exe"
  "C:\Program Files\Epic Games\UE_5.8\Engine\Binaries\Win64\UnrealEditor.exe"
) do (
  if exist "%%~E" (
    start "RED Mars Planet Artist" "%%~E" "%PROJECT%" /Game/RedMMO/Maps/RedPlanetGen_50km_ArtistCanvas -dx11 -NoLiveCoding -NoSound -NoSplash -ddc=InstalledNoZenLocalFallback "-cvarsini=%~dp0Config\ConsoleVariables.ini" "-abslog=%~dp0Saved\Logs\Titan_ArtistSafe.log"
    exit /b 0
  )
)

echo Unreal Engine 5.8 was not found in either supported location:
echo   D:\UE_5.8
echo   C:\Program Files\Epic Games\UE_5.8
echo.
echo Edit OPEN_PLANET_EDITOR_SAFE.cmd and add the artist's UnrealEditor.exe path.
pause
exit /b 1
