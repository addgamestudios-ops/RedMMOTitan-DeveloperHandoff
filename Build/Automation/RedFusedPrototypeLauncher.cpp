#include <windows.h>

#include <string>
#include <vector>

namespace
{
std::wstring GetLauncherDirectory()
{
	std::vector<wchar_t> Buffer(32768, L'\0');
	const DWORD Length = GetModuleFileNameW(nullptr, Buffer.data(), static_cast<DWORD>(Buffer.size()));
	if (Length == 0 || Length >= Buffer.size())
	{
		return {};
	}

	std::wstring Directory(Buffer.data(), Length);
	const std::wstring::size_type Separator = Directory.find_last_of(L"\\/");
	if (Separator == std::wstring::npos)
	{
		return {};
	}

	Directory.resize(Separator);
	return Directory;
}
}

int WINAPI wWinMain(HINSTANCE, HINSTANCE, PWSTR, int)
{
	const std::wstring LauncherDirectory = GetLauncherDirectory();
	if (LauncherDirectory.empty())
	{
		MessageBoxW(nullptr, L"Could not resolve the launcher directory.", L"RedMMOTitan launcher", MB_OK | MB_ICONERROR);
		return 1;
	}

	const std::wstring TitanExecutable = LauncherDirectory + L"\\Titan.exe";
	std::wstring CommandLine = L"\"" + TitanExecutable
		+ L"\" /Game/RedMMO/Maps/RedPlanetGen_50km_FusedPrototype"
		+ L" -windowed -ResX=1600 -ResY=900 -NoSplash";

	STARTUPINFOW StartupInfo{};
	StartupInfo.cb = sizeof(StartupInfo);
	PROCESS_INFORMATION ProcessInfo{};

	const BOOL Started = CreateProcessW(
		TitanExecutable.c_str(),
		CommandLine.data(),
		nullptr,
		nullptr,
		FALSE,
		CREATE_UNICODE_ENVIRONMENT,
		nullptr,
		LauncherDirectory.c_str(),
		&StartupInfo,
		&ProcessInfo);

	if (!Started)
	{
		const DWORD ErrorCode = GetLastError();
		std::wstring Message = L"Could not start Titan.exe. Windows error: " + std::to_wstring(ErrorCode);
		MessageBoxW(nullptr, Message.c_str(), L"RedMMOTitan launcher", MB_OK | MB_ICONERROR);
		return static_cast<int>(ErrorCode == 0 ? 1 : ErrorCode);
	}

	CloseHandle(ProcessInfo.hThread);
	CloseHandle(ProcessInfo.hProcess);
	return 0;
}
