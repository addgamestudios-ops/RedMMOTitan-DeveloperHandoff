#include <windows.h>

#include <string>

int WINAPI wWinMain(HINSTANCE, HINSTANCE, PWSTR, int)
{
	const std::wstring EditorExecutable =
		L"D:\\UE_5.8\\Engine\\Binaries\\Win64\\UnrealEditor.exe";
	const std::wstring ProjectFile = L"D:\\RedMMOTitan\\Titan.uproject";
	std::wstring CommandLine = L"\"" + EditorExecutable + L"\" \"" + ProjectFile
		+ L"\" /Game/RedMMO/Maps/RedPlanetGen_50km_FusedPrototype"
		+ L" -game -windowed -ResX=1600 -ResY=900 -NoSplash -NoLoadingScreen";

	STARTUPINFOW StartupInfo{};
	StartupInfo.cb = sizeof(StartupInfo);
	PROCESS_INFORMATION ProcessInfo{};
	wchar_t* WritableCommandLine = CommandLine.empty() ? nullptr : &CommandLine[0];
	const BOOL Started = CreateProcessW(
		EditorExecutable.c_str(), WritableCommandLine, nullptr, nullptr, FALSE,
		CREATE_UNICODE_ENVIRONMENT, nullptr, L"D:\\RedMMOTitan", &StartupInfo,
		&ProcessInfo);
	if (!Started)
	{
		const DWORD ErrorCode = GetLastError();
		const std::wstring Message =
			L"Could not start the fused editor-game test. Windows error: "
			+ std::to_wstring(ErrorCode);
		MessageBoxW(nullptr, Message.c_str(), L"RedMMOTitan V4 test launcher",
			MB_OK | MB_ICONERROR);
		return static_cast<int>(ErrorCode == 0 ? 1 : ErrorCode);
	}

	CloseHandle(ProcessInfo.hThread);
	CloseHandle(ProcessInfo.hProcess);
	return 0;
}
