[CmdletBinding()]
param(
    [switch]$PreflightOnly,
    [switch]$RunSensorFailureInjectionProbes,
    [switch]$RunTurnkeyGuardProbes
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$EditorPath = 'D:\UE_5.8\Engine\Binaries\Win64\UnrealEditor.exe'
$ProjectPath = 'D:\RedMMOTitanWindowsData\Scratch\TropBiomeV1A\Titan.uproject'
$MapPackage = '/Game/RedMMO/Maps/Tests/RedPlanetGen_50km_FusedPrototype_M07_TropicalBiomeStage_V1'
$MapFile = 'D:\RedMMOTitanWindowsData\Scratch\TropBiomeV1A\Content\RedMMO\Maps\Tests\RedPlanetGen_50km_FusedPrototype_M07_TropicalBiomeStage_V1.umap'
$ValidationScript = 'D:\RedMMOTitan\Tools\validate_m07_tropical_planetary_biome_stage_live.py'
$StageAuditPath = 'D:\RedMMOTitanWindowsData\Diagnostics\M07_TropBiomeAuthor_20260725_210856Z\authoring_audit.json'
$DiagnosticsParent = 'D:\RedMMOTitanWindowsData\Diagnostics\M07_TropicalBiomeLiveValidation'
$ReusableLocalDdcSourceRunId = '20260725_214256_081Z_3db7db2c'
$ReusableLocalDdcPath = (
    'D:\RedMMOTitanWindowsData\Diagnostics\M07_TropicalBiomeLiveValidation\' +
    "$ReusableLocalDdcSourceRunId\LocalDDC"
)
$AllowedTurnkeyDotNetPath = (
    'D:\UE_5.8\Engine\Binaries\ThirdParty\DotNet\10.0\win-x64\dotnet.exe'
)
$AllowedTurnkeyCommandHostPath = 'C:\Windows\System32\cmd.exe'
$AllowedTurnkeyRunUatPath = 'D:\UE_5.8\Engine\Build\BatchFiles\RunUAT.bat'
$AllowedValidatePlatformsBuildPath = (
    'D:\UE_5.8\Engine\Build\BatchFiles\Build.bat'
)
$ValidatePlatformsBuildUbtPath = (
    'D:\UE_5.8\Engine\Build\BatchFiles\BuildUBT.bat'
)
$AllowedTurnkeyGetDotNetPath = (
    'D:\UE_5.8\Engine\Build\BatchFiles\GetDotnetPath.bat'
)
$AllowedTurnkeyInstalledBuildMarkerPath = (
    'D:\UE_5.8\Engine\Build\InstalledBuild.txt'
)
$AllowedTurnkeyAutomationToolPath = (
    'D:\UE_5.8\Engine\Binaries\DotNET\AutomationTool\AutomationTool.dll'
)
$AllowedTurnkeyAutomationScriptPath = (
    'D:\UE_5.8\Engine\Binaries\DotNET\AutomationTool\' +
    'AutomationScripts\Turnkey\net10.0\Turnkey.Automation.dll'
)
$AllowedTurnkeyUnrealBuildToolPath = (
    'D:\UE_5.8\Engine\Binaries\DotNET\AutomationTool\UnrealBuildTool.dll'
)
$AllowedValidatePlatformsUnrealBuildToolPath = (
    'D:\UE_5.8\Engine\Binaries\DotNET\UnrealBuildTool\UnrealBuildTool.dll'
)
$AllowedValidatePlatformsUnrealBuildToolRoot = (
    'D:\UE_5.8\Engine\Binaries\DotNET\UnrealBuildTool'
)
$AllowedTurnkeyAutomationRoot = (
    'D:\UE_5.8\Engine\Binaries\DotNET\AutomationTool'
)
$AllowedTurnkeyDotNetRoot = (
    'D:\UE_5.8\Engine\Binaries\ThirdParty\DotNet\10.0\win-x64'
)
$TurnkeyPostVariablesPath = (
    'D:\UE_5.8\Engine\Intermediate\Turnkey\PostTurnkeyVariables.bat'
)

$ExpectedEditorSha256 = 'BD2F48D592D69FC04B55B2813CB09D0D4D728BC462E7DF3BA142E3F2662D1D97'
$ExpectedTurnkeyDotNetSha256 = '97EBAA9426FDE1292AA3413D6490EA7514075AD8B71355EFEF1EC49996434E61'
$ExpectedTurnkeyCommandHostSha256 = '65EC268ADD3973B6DCA64222985DA47CAEAEE44A340B0EC1466782914FD743D9'
$ExpectedTurnkeyRunUatSha256 = 'E2DF422B26722A960A0726713336619E65B1013548671CD6CEC6D010F993EABB'
$ExpectedValidatePlatformsBuildSha256 = '4F71B08EBC3FE2BA7918A5BE7A0B3F22CF7CE5530049873E9ECA8DF946BC1CB3'
$ExpectedTurnkeyGetDotNetSha256 = '6383A2535C0E551817289231E1755BDE58456785FE3B3DBC1D7BAA9134EB12CB'
$ExpectedTurnkeyInstalledBuildMarkerSha256 = '2510DF0682BBF178EBE0AB81DA5F36B2D2BFDC19D8CD562466DE649669E70393'
$ExpectedTurnkeyAutomationToolSha256 = '45C62F44B7B17E989BCDFEF26DABD30B5D6975D5300C24936529032B41B20132'
$ExpectedTurnkeyAutomationScriptSha256 = '9A4AFCBAB10D33D97F9902D768C085A4D7A4162F58FB538F8FF14646F5F9E0AF'
$ExpectedTurnkeyUnrealBuildToolSha256 = '4820594723F875C2510FF75BE06039DCA3790A98469124FC3B58602AC5A33224'
$ExpectedValidatePlatformsUnrealBuildToolSha256 = '49DEE1319F2355FEA5626A3A1FD0EEA9AD2DD58F520917C6A546EC3EDA593D2E'
$ExpectedValidatePlatformsUnrealBuildToolTreeManifestSha256 = '02969D6739CFDD4AC371CA5D1EABC44CF93A892B32AE59F6B75E760CA911A6E6'
$ExpectedValidatePlatformsUnrealBuildToolTreeFileCount = 98
$ExpectedValidatePlatformsUnrealBuildToolTreeBytes = [int64]47429728
$ExpectedTurnkeyAutomationTreeManifestSha256 = '44820E492AF83AAFE5855780B5E79C5F293643A403FBDF1B8B5172FC400936A9'
$ExpectedTurnkeyAutomationTreeFileCount = 1408
$ExpectedTurnkeyAutomationTreeBytes = [int64]1132786277
$ExpectedTurnkeyDotNetTreeManifestSha256 = '5075AAE77DC8B2E7579299AB55B924F1FB0CAB3A1D18E6ACA033D54E04AC1DC1'
$ExpectedTurnkeyDotNetTreeFileCount = 5732
$ExpectedTurnkeyDotNetTreeBytes = [int64]855636748
$ExpectedProjectSha256 = '0EB6D5622267A520C829846C3A66E81A3BDFE9A9931D7F98138C754A84A66B23'
$ExpectedMapSha256 = 'FBB0EED0191099B99833CA829834BA08DB5786204ED27A04BA38F053B4F1B491'
$ExpectedValidationScriptSha256 = '28D4501073A74C36FCAD7A4E75A1F0561F55F898757C5AF12C1D9FF96BFA8503'
$ExpectedStageAuditSha256 = '1A1A0A98030D1A7BC6AE1F2617805E9E1080D367051266BFCFF04335CA446ADA'

$RequiredDisabledPlugins = @(
    'AndroidFileServer'
    'AIAssistant'
    'EditorTelemetry'
    'LiveLinkHubMessaging'
    'MetaHumanLiveLink'
    'ModelContextProtocol'
    'Nwiro'
    'NwiroIntegrationKit'
    'OnlineSubsystemSteam'
    'SteamIntegrationKit'
    'SteamSockets'
    'TcpMessaging'
    'UdpMessaging'
    'UnrealAIIntegrationPlatform'
)
$DisablePluginsArgument = '-DisablePlugins=' + ($RequiredDisabledPlugins -join ',')

$PreflightSampleCount = 6
$PreflightIntervalSeconds = 2
$MinimumFreePhysicalGiB = 16.0
$MinimumFreeCommitGiB = 16.0
$AbortFreePhysicalGiB = 8.0
$AbortFreeCommitGiB = 8.0
$MonitorPollSeconds = 2
$MaximumMonitorSeconds = 900

$RequiredEnvironment = [ordered]@{
    REDMMO_M07_TROPICAL_LIVE_PROJECT_FILE = $ProjectPath
    REDMMO_M07_TROPICAL_STAGE_AUDIT_PATH = $StageAuditPath
    REDMMO_M07_TROPICAL_LIVE_DIAGNOSTICS_DIR = $null
    REDMMO_M07_TROPICAL_LIVE_AUDIT_OUTPUT = $null
    UE_USE_SYSTEM_DOTNET = '0'
    UE_DOTNET_VERSION = ''
    DOTNET_ROOT = ''
    DOTNET_ROOT_X64 = ''
    DOTNET_HOST_PATH = $AllowedTurnkeyDotNetPath
    DOTNET_MULTILEVEL_LOOKUP = '0'
    DOTNET_STARTUP_HOOKS = ''
    DOTNET_ADDITIONAL_DEPS = ''
    DOTNET_SHARED_STORE = ''
    CORECLR_ENABLE_PROFILING = '0'
    CORECLR_PROFILER = ''
    CORECLR_PROFILER_PATH = ''
    CORECLR_PROFILER_PATH_32 = ''
    CORECLR_PROFILER_PATH_64 = ''
    CORECLR_PROFILER_PATH_ARM64 = ''
}

$PreflightExecutableNames = @(
    'UnrealEditor'
    'UnrealEditor-Cmd'
    'UnrealBuildTool'
    'AutomationTool'
    'MSBuild'
    'ShaderCompileWorker'
)
$PostLaunchPrimaryNames = @(
    'UnrealEditor'
    'UnrealEditor-Cmd'
    'UnrealBuildTool'
    'AutomationTool'
    'MSBuild'
)
$DotNetHostedBuildPattern = '(?i)(AutomationTool|UnrealBuildTool|RunUAT|BuildCookRun|Titan(?:Editor)?\.Target)'
$ZenExecutableNames = @(
    'zen'
    'zenserver'
    'ZenLaunch'
    'ZenDashboard'
    'UnrealZenStore'
)
$TraceServerExecutableNames = @(
    'UnrealTraceServer'
)

function ConvertTo-RedFullPath {
    param([Parameter(Mandatory = $true)][string]$Path)

    [System.IO.Path]::GetFullPath($Path)
}

function Test-RedPathEqual {
    param(
        [Parameter(Mandatory = $true)][string]$Left,
        [Parameter(Mandatory = $true)][string]$Right
    )

    return [string]::Equals(
        (ConvertTo-RedFullPath -Path $Left).TrimEnd('\'),
        (ConvertTo-RedFullPath -Path $Right).TrimEnd('\'),
        [System.StringComparison]::OrdinalIgnoreCase
    )
}

if ($null -ne ('RedM07NativeProcessIdentityV1' -as [type])) {
    throw (
        'Refusing a preloaded RedM07NativeProcessIdentityV1 type; this guard ' +
        'requires a fresh -NoProfile -File PowerShell host.'
    )
}
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
using System.Text;

public static class RedM07NativeProcessIdentityV1
{
    [DllImport("kernel32.dll", SetLastError = true)]
    public static extern IntPtr OpenProcess(
        uint desiredAccess,
        bool inheritHandle,
        uint processId
    );

    [DllImport(
        "kernel32.dll",
        SetLastError = true,
        CharSet = CharSet.Unicode
    )]
    [return: MarshalAs(UnmanagedType.Bool)]
    public static extern bool QueryFullProcessImageNameW(
        IntPtr process,
        uint flags,
        StringBuilder imageName,
        ref uint size
    );

    [DllImport("kernel32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    public static extern bool GetProcessTimes(
        IntPtr process,
        out long creationTime,
        out long exitTime,
        out long kernelTime,
        out long userTime
    );

    [DllImport("kernel32.dll", SetLastError = true)]
    public static extern uint GetProcessId(IntPtr process);

    [DllImport("kernel32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    public static extern bool CloseHandle(IntPtr handle);
}
'@

function Test-RedStrictAbsoluteDosPath {
    param(
        [Parameter(Mandatory = $true)]
        [AllowEmptyString()]
        [string]$Path
    )

    if ([string]::IsNullOrWhiteSpace($Path)) {
        return $false
    }
    return [regex]::IsMatch(
        $Path,
        '^[A-Za-z]:\\',
        [System.Text.RegularExpressions.RegexOptions]::CultureInvariant
    )
}

function Test-RedSameProcessCreationMicrosecond {
    param(
        [Parameter(Mandatory = $true)][datetime]$Left,
        [Parameter(Mandatory = $true)][datetime]$Right
    )

    [int64]$leftTicks = $Left.ToUniversalTime().Ticks
    [int64]$rightTicks = $Right.ToUniversalTime().Ticks
    [int64]$leftMicrosecondTicks = $leftTicks - ($leftTicks % [int64]10)
    [int64]$rightMicrosecondTicks = $rightTicks - ($rightTicks % [int64]10)
    return $leftMicrosecondTicks -eq $rightMicrosecondTicks
}

function Get-RedNativeProcessImageBinding {
    param([Parameter(Mandatory = $true)][int]$ProcessId)

    $result = [ordered]@{
        success = $false
        requested_pid = $ProcessId
        native_pid = $null
        image_path = $null
        creation_utc = $null
        api_stage = 'not_started'
        win32_error = $null
        error = $null
        process_access_mask = '0x00001000'
        query_image_flags = 0
        same_handle_path_and_creation = $false
        handle_closed = $false
        raw_handle_disclosed = $false
    }
    if ($ProcessId -le 0) {
        $result.api_stage = 'validate_pid'
        $result.error = "Process ID must be positive: $ProcessId"
        return $result
    }

    [IntPtr]$processHandle = [IntPtr]::Zero
    try {
        $result.api_stage = 'open_process'
        $processHandle = [RedM07NativeProcessIdentityV1]::OpenProcess(
            [uint32]0x00001000,
            $false,
            [uint32]$ProcessId
        )
        if ($processHandle -eq [IntPtr]::Zero) {
            $errorCode = [Runtime.InteropServices.Marshal]::GetLastWin32Error()
            $result.win32_error = $errorCode
            throw [System.ComponentModel.Win32Exception]::new(
                $errorCode,
                'OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION) failed.'
            )
        }

        $result.api_stage = 'get_process_id'
        [uint32]$nativePid = (
            [RedM07NativeProcessIdentityV1]::GetProcessId($processHandle)
        )
        if ($nativePid -eq 0) {
            $errorCode = [Runtime.InteropServices.Marshal]::GetLastWin32Error()
            $result.win32_error = $errorCode
            throw [System.ComponentModel.Win32Exception]::new(
                $errorCode,
                'GetProcessId failed.'
            )
        }
        $result.native_pid = [int]$nativePid
        if ([int]$nativePid -ne $ProcessId) {
            throw (
                "Native handle PID mismatch: requested=$ProcessId " +
                "native=$nativePid"
            )
        }

        $result.api_stage = 'query_full_process_image_name'
        $imageName = [System.Text.StringBuilder]::new(32768)
        [uint32]$imageNameSize = [uint32]$imageName.Capacity
        $queriedImage = (
            [RedM07NativeProcessIdentityV1]::QueryFullProcessImageNameW(
                $processHandle,
                [uint32]0,
                $imageName,
                [ref]$imageNameSize
            )
        )
        if (-not $queriedImage) {
            $errorCode = [Runtime.InteropServices.Marshal]::GetLastWin32Error()
            $result.win32_error = $errorCode
            throw [System.ComponentModel.Win32Exception]::new(
                $errorCode,
                'QueryFullProcessImageNameW failed.'
            )
        }
        $result.image_path = $imageName.ToString()
        if (-not (Test-RedStrictAbsoluteDosPath -Path $result.image_path)) {
            throw (
                'Native process image path is not an unprefixed absolute DOS ' +
                "path: $($result.image_path)"
            )
        }

        $result.api_stage = 'get_process_times'
        [int64]$creationFileTime = 0
        [int64]$exitFileTime = 0
        [int64]$kernelFileTime = 0
        [int64]$userFileTime = 0
        $queriedTimes = [RedM07NativeProcessIdentityV1]::GetProcessTimes(
            $processHandle,
            [ref]$creationFileTime,
            [ref]$exitFileTime,
            [ref]$kernelFileTime,
            [ref]$userFileTime
        )
        if (-not $queriedTimes) {
            $errorCode = [Runtime.InteropServices.Marshal]::GetLastWin32Error()
            $result.win32_error = $errorCode
            throw [System.ComponentModel.Win32Exception]::new(
                $errorCode,
                'GetProcessTimes failed.'
            )
        }
        $nativeCreation = [datetime]::FromFileTimeUtc($creationFileTime)
        $result.creation_utc = $nativeCreation.ToString('o')
        $result.same_handle_path_and_creation = $true
        $result.api_stage = 'complete'
        $result.success = $true
    } catch {
        $result.success = $false
        $result.error = $_.Exception.Message
    } finally {
        if ($processHandle -ne [IntPtr]::Zero) {
            $closed = [RedM07NativeProcessIdentityV1]::CloseHandle(
                $processHandle
            )
            $result.handle_closed = [bool]$closed
            if (-not $closed) {
                $closeError = (
                    [Runtime.InteropServices.Marshal]::GetLastWin32Error()
                )
                $result.success = $false
                $result.api_stage = 'close_handle'
                $result.win32_error = $closeError
                $result.error = (
                    "CloseHandle failed with Win32 error $closeError."
                )
            }
        }
    }
    return $result
}

function Test-RedStrictMemberType {
    param(
        [Parameter(Mandatory = $true)]$InputObject,
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][Type]$ExpectedType
    )

    $value = $null
    if ($InputObject -is [System.Collections.IDictionary]) {
        if (-not $InputObject.Contains($Name)) {
            return $false
        }
        $value = $InputObject[$Name]
    } else {
        $property = $InputObject.PSObject.Properties[$Name]
        if ($null -eq $property) {
            return $false
        }
        $value = $property.Value
    }
    return (
        $null -ne $value -and
        $value.GetType() -eq $ExpectedType
    )
}

function Test-RedStrictBooleanMember {
    param(
        [Parameter(Mandatory = $true)]$InputObject,
        [Parameter(Mandatory = $true)][string]$Name
    )

    return Test-RedStrictMemberType `
        -InputObject $InputObject `
        -Name $Name `
        -ExpectedType ([bool])
}

function Test-RedNativeProcessImageBinding {
    param(
        [Parameter(Mandatory = $true)]$Process,
        [Parameter(Mandatory = $true)]$NativeBinding
    )

    $wmiCreationUtc = $null
    try {
        if ($null -eq $Process.CreationDate) {
            throw 'WMI CreationDate is missing.'
        }
        $wmiCreation = ([datetime]$Process.CreationDate).ToUniversalTime()
        $wmiCreationUtc = $wmiCreation.ToString('o')
    } catch {
        return [ordered]@{
            success = $false
            source = 'native_query_full_process_image_name_get_process_times'
            path = $null
            requested_pid = [int]$Process.ProcessId
            native_pid = $null
            wmi_creation_utc = $wmiCreationUtc
            native_creation_utc = $null
            same_creation_microsecond = $false
            reason = $_.Exception.Message
            native_query = $NativeBinding
        }
    }

    if (
        -not (
            Test-RedStrictBooleanMember `
                -InputObject $NativeBinding `
                -Name 'success'
        ) -or
        -not [bool]$NativeBinding.success
    ) {
        return [ordered]@{
            success = $false
            source = 'native_query_full_process_image_name_get_process_times'
            path = $null
            requested_pid = [int]$Process.ProcessId
            native_pid = $NativeBinding.native_pid
            wmi_creation_utc = $wmiCreationUtc
            native_creation_utc = $NativeBinding.creation_utc
            same_creation_microsecond = $false
            reason = 'Native process image binding query failed.'
            native_query = $NativeBinding
        }
    }

    $nativeSuccessShapeValid = (
        (
            Test-RedStrictMemberType `
                -InputObject $NativeBinding `
                -Name 'native_pid' `
                -ExpectedType ([int])
        ) -and
        (
            Test-RedStrictMemberType `
                -InputObject $NativeBinding `
                -Name 'image_path' `
                -ExpectedType ([string])
        ) -and
        (
            Test-RedStrictMemberType `
                -InputObject $NativeBinding `
                -Name 'creation_utc' `
                -ExpectedType ([string])
        )
    )
    if (-not $nativeSuccessShapeValid) {
        return [ordered]@{
            success = $false
            source = 'native_query_full_process_image_name_get_process_times'
            path = $null
            requested_pid = [int]$Process.ProcessId
            native_pid = $null
            wmi_creation_utc = $wmiCreationUtc
            native_creation_utc = $null
            same_creation_microsecond = $false
            reason = (
                'Successful native process image binding has missing or ' +
                'type-confused PID, image path, or creation time evidence.'
            )
            native_query = $NativeBinding
        }
    }

    try {
        $nativeCreation = (
            [datetime]$NativeBinding.creation_utc
        ).ToUniversalTime()
    } catch {
        return [ordered]@{
            success = $false
            source = 'native_query_full_process_image_name_get_process_times'
            path = $NativeBinding.image_path
            requested_pid = [int]$Process.ProcessId
            native_pid = $NativeBinding.native_pid
            wmi_creation_utc = $wmiCreationUtc
            native_creation_utc = $NativeBinding.creation_utc
            same_creation_microsecond = $false
            reason = 'Native process creation time is missing or invalid.'
            native_query = $NativeBinding
        }
    }

    $sameCreation = Test-RedSameProcessCreationMicrosecond `
        -Left $wmiCreation `
        -Right $nativeCreation
    $nativePidMatches = (
        [int]$NativeBinding.native_pid -eq [int]$Process.ProcessId
    )
    $pathIsStrict = Test-RedStrictAbsoluteDosPath `
        -Path ([string]$NativeBinding.image_path)
    $sameHandleBound = (
        (Test-RedStrictBooleanMember `
            -InputObject $NativeBinding `
            -Name 'same_handle_path_and_creation') -and
        [bool]$NativeBinding.same_handle_path_and_creation
    )
    $handleClosed = (
        (Test-RedStrictBooleanMember `
            -InputObject $NativeBinding `
            -Name 'handle_closed') -and
        [bool]$NativeBinding.handle_closed
    )
    $rawHandleHidden = (
        (Test-RedStrictBooleanMember `
            -InputObject $NativeBinding `
            -Name 'raw_handle_disclosed') -and
        (-not [bool]$NativeBinding.raw_handle_disclosed)
    )
    $success = (
        $sameCreation -and
        $nativePidMatches -and
        $pathIsStrict -and
        $sameHandleBound -and
        $handleClosed -and
        $rawHandleHidden
    )
    return [ordered]@{
        success = [bool]$success
        source = 'native_query_full_process_image_name_get_process_times'
        path = [string]$NativeBinding.image_path
        requested_pid = [int]$Process.ProcessId
        native_pid = [int]$NativeBinding.native_pid
        wmi_creation_utc = $wmiCreationUtc
        native_creation_utc = $nativeCreation.ToString('o')
        wmi_creation_ticks_100ns = [int64]$wmiCreation.Ticks
        native_creation_ticks_100ns = [int64]$nativeCreation.Ticks
        same_creation_microsecond = [bool]$sameCreation
        native_pid_matches = [bool]$nativePidMatches
        strict_absolute_dos_path = [bool]$pathIsStrict
        same_handle_path_and_creation = [bool]$sameHandleBound
        handle_closed = [bool]$handleClosed
        raw_handle_hidden = [bool]$rawHandleHidden
        reason = if ($success) {
            'Native path and creation time are bound to the WMI snapshot.'
        } else {
            'Native PID, path, time, handle binding, closure, or evidence ' +
            'redaction invariant did not match.'
        }
        native_query = $NativeBinding
    }
}

function Get-RedEffectiveProcessImageBinding {
    param(
        [Parameter(Mandatory = $true)]$Process,
        [Parameter(Mandatory = $true)][hashtable]$PerSnapshotCache,
        [switch]$AllowBlankWmiNativeFallback
    )

    $creationKey = if ($null -eq $Process.CreationDate) {
        '<missing>'
    } else {
        try {
            ([datetime]$Process.CreationDate).ToUniversalTime().ToString('o')
        } catch {
            '<invalid>'
        }
    }
    $cacheKey = '{0}|{1}|{2}|native_fallback={3}' -f (
        [int]$Process.ProcessId
    ), $creationKey, ([string]$Process.ExecutablePath), (
        [bool]$AllowBlankWmiNativeFallback
    )
    if ($PerSnapshotCache.ContainsKey($cacheKey)) {
        return $PerSnapshotCache[$cacheKey]
    }

    $wmiPath = [string]$Process.ExecutablePath
    if (-not [string]::IsNullOrWhiteSpace($wmiPath)) {
        $pathIsStrict = Test-RedStrictAbsoluteDosPath -Path $wmiPath
        $binding = [ordered]@{
            success = [bool]$pathIsStrict
            source = 'wmi_executable_path'
            path = $wmiPath
            requested_pid = [int]$Process.ProcessId
            native_pid = $null
            wmi_creation_utc = $creationKey
            native_creation_utc = $null
            same_creation_microsecond = $null
            native_pid_matches = $null
            strict_absolute_dos_path = [bool]$pathIsStrict
            reason = if ($pathIsStrict) {
                'WMI supplied an unprefixed absolute DOS executable path.'
            } else {
                'WMI supplied a nonblank but ambiguous executable path.'
            }
            native_query = $null
        }
    } elseif ($AllowBlankWmiNativeFallback) {
        $nativeBinding = Get-RedNativeProcessImageBinding `
            -ProcessId ([int]$Process.ProcessId)
        $binding = Test-RedNativeProcessImageBinding `
            -Process $Process `
            -NativeBinding $nativeBinding
    } else {
        $binding = [ordered]@{
            success = $false
            source = 'wmi_executable_path_required'
            path = $null
            requested_pid = [int]$Process.ProcessId
            native_pid = $null
            wmi_creation_utc = $creationKey
            native_creation_utc = $null
            same_creation_microsecond = $null
            native_pid_matches = $null
            strict_absolute_dos_path = $false
            reason = (
                'Blank WMI executable path is rejected because this callsite ' +
                'does not authorize the narrow dotnet-only native fallback.'
            )
            native_query = $null
        }
    }
    $PerSnapshotCache[$cacheKey] = $binding
    return $binding
}

function Get-RedReusableLocalDdcRecord {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$ExpectedPath,
        [Parameter(Mandatory = $true)][string]$SourceRunId
    )

    $fullPath = ConvertTo-RedFullPath -Path $Path
    if (-not (Test-RedPathEqual -Left $fullPath -Right $ExpectedPath)) {
        throw (
            'Reusable Local DDC path must match the exact reviewed cache: ' +
            "expected=$ExpectedPath actual=$fullPath"
        )
    }
    if (
        -not [string]::Equals(
            [System.IO.Path]::GetPathRoot($fullPath),
            'D:\',
            [System.StringComparison]::OrdinalIgnoreCase
        )
    ) {
        throw "Reusable Local DDC must remain on D: $fullPath"
    }
    if (-not (Test-Path -LiteralPath $fullPath -PathType Container)) {
        throw "Reusable Local DDC is missing: $fullPath"
    }

    $expectedSourceParent = Join-Path $DiagnosticsParent $SourceRunId
    $expectedSourcePath = Join-Path $expectedSourceParent 'LocalDDC'
    if (-not (Test-RedPathEqual -Left $fullPath -Right $expectedSourcePath)) {
        throw (
            'Reusable Local DDC is not the exact prior-run LocalDDC child: ' +
            "expected=$expectedSourcePath actual=$fullPath"
        )
    }

    $scratchProjectRoot = Split-Path -Parent $ProjectPath
    $forbiddenRoots = @(
        'D:\RedMMOTitan\Content'
        'D:\RedMMOTitan\Config'
        'D:\RedMMOTitan\Source'
        'D:\RedMMOTitan\ProjectKnowledge'
        (Join-Path $scratchProjectRoot 'Content')
        (Join-Path $scratchProjectRoot 'Config')
        (Join-Path $scratchProjectRoot 'Source')
        (Join-Path $scratchProjectRoot 'ProjectKnowledge')
    )
    $candidateComparable = $fullPath.TrimEnd('\')
    foreach ($forbiddenRoot in $forbiddenRoots) {
        $forbiddenComparable = (
            ConvertTo-RedFullPath -Path $forbiddenRoot
        ).TrimEnd('\')
        if (
            [string]::Equals(
                $candidateComparable,
                $forbiddenComparable,
                [System.StringComparison]::OrdinalIgnoreCase
            ) -or
            $candidateComparable.StartsWith(
                "$forbiddenComparable\",
                [System.StringComparison]::OrdinalIgnoreCase
            )
        ) {
            throw "Reusable Local DDC is under a forbidden project root: $fullPath"
        }
    }

    Assert-RedNoReparsePath -Path $fullPath
    $rootBefore = Get-Item -LiteralPath $fullPath -Force
    $pending = [System.Collections.Generic.Stack[string]]::new()
    $pending.Push($fullPath)
    [int64]$directoryCount = 0
    [int64]$fileCount = 0
    [int64]$totalBytes = 0
    while ($pending.Count -gt 0) {
        $currentDirectory = $pending.Pop()
        $directory = Get-Item -LiteralPath $currentDirectory -Force
        if (
            ($directory.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0
        ) {
            throw "Reusable Local DDC contains a reparse directory: $currentDirectory"
        }
        $directoryCount += 1
        foreach (
            $item in @(
                Get-ChildItem -LiteralPath $currentDirectory -Force -ErrorAction Stop
            )
        ) {
            if (
                ($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0
            ) {
                throw "Reusable Local DDC contains a reparse entry: $($item.FullName)"
            }
            if ($item.PSIsContainer) {
                $pending.Push($item.FullName)
            } else {
                $fileCount += 1
                $totalBytes += [int64]$item.Length
            }
        }
    }
    if ($fileCount -eq 0 -or $totalBytes -eq 0) {
        throw "Reusable Local DDC is empty: $fullPath"
    }
    $rootAfter = Get-Item -LiteralPath $fullPath -Force
    if (
        $rootBefore.CreationTimeUtc -ne $rootAfter.CreationTimeUtc -or
        $rootBefore.LastWriteTimeUtc -ne $rootAfter.LastWriteTimeUtc
    ) {
        throw "Reusable Local DDC root changed during authentication: $fullPath"
    }

    return [ordered]@{
        path = $rootAfter.FullName
        source_run_id = $SourceRunId
        reuse_mode = 'existing_exact_prior_run_cache'
        created_by_current_run = $false
        moved_or_deleted_by_current_run = $false
        mutable_cache_may_be_extended_by_retry = $true
        content_hash_pinned = $false
        drive_root = 'D:\'
        exact_path_authenticated = $true
        path_and_descendants_reparse_free = $true
        forbidden_project_roots_checked = $forbiddenRoots
        directory_count = $directoryCount
        file_count = $fileCount
        total_bytes = $totalBytes
        creation_utc = $rootAfter.CreationTimeUtc.ToString('o')
        last_write_utc = $rootAfter.LastWriteTimeUtc.ToString('o')
        authenticated_utc = [datetime]::UtcNow.ToString('o')
    }
}

function Assert-RedNoReparsePath {
    param([Parameter(Mandatory = $true)][string]$Path)

    $fullPath = ConvertTo-RedFullPath -Path $Path
    $root = [System.IO.Path]::GetPathRoot($fullPath)
    if ([string]::IsNullOrWhiteSpace($root)) {
        throw "Path has no rooted volume: $Path"
    }
    $relative = $fullPath.Substring($root.Length)
    $current = $root
    foreach ($segment in @($relative -split '[\\/]' | Where-Object { $_ })) {
        $current = Join-Path $current $segment
        if (-not (Test-Path -LiteralPath $current)) {
            continue
        }
        $item = Get-Item -LiteralPath $current -Force
        if (($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw "Reparse points are forbidden in guarded-launch paths: $current"
        }
    }
}

function Get-RedFileRecord {
    param([Parameter(Mandatory = $true)][string]$Path)

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "Required file is missing: $Path"
    }
    Assert-RedNoReparsePath -Path $Path
    $itemBefore = Get-Item -LiteralPath $Path -Force
    $hash = (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToUpperInvariant()
    $itemAfter = Get-Item -LiteralPath $Path -Force
    if (
        $itemBefore.Length -ne $itemAfter.Length -or
        $itemBefore.LastWriteTimeUtc -ne $itemAfter.LastWriteTimeUtc
    ) {
        throw "File changed while hashing: $Path"
    }
    [ordered]@{
        path = $itemAfter.FullName
        bytes = [int64]$itemAfter.Length
        sha256 = $hash
        last_write_utc = $itemAfter.LastWriteTimeUtc.ToString('o')
    }
}

function Assert-RedPinnedFile {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$ExpectedSha256,
        [Parameter(Mandatory = $true)][string]$Label
    )

    $record = Get-RedFileRecord -Path $Path
    if ($record.sha256 -ne $ExpectedSha256.ToUpperInvariant()) {
        throw (
            "$Label hash mismatch: expected=$ExpectedSha256 " +
            "actual=$($record.sha256) path=$Path"
        )
    }
    return $record
}

function Assert-RedPathAbsent {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Label
    )

    $fullPath = ConvertTo-RedFullPath -Path $Path
    Assert-RedNoReparsePath -Path (Split-Path -Parent $fullPath)
    if (Test-Path -LiteralPath $fullPath) {
        throw "$Label must be absent before guarded launch: $fullPath"
    }
    return [ordered]@{
        path = $fullPath
        absent = $true
        checked_utc = [datetime]::UtcNow.ToString('o')
    }
}

function Assert-RedPinnedTreeManifest {
    param(
        [Parameter(Mandatory = $true)][string]$Root,
        [Parameter(Mandatory = $true)][string]$ExpectedSha256,
        [Parameter(Mandatory = $true)][int]$ExpectedFileCount,
        [Parameter(Mandatory = $true)][int64]$ExpectedBytes,
        [Parameter(Mandatory = $true)][string]$Label
    )

    $rootFull = (ConvertTo-RedFullPath -Path $Root).TrimEnd('\')
    if (-not (Test-Path -LiteralPath $rootFull -PathType Container)) {
        throw "$Label root is missing: $rootFull"
    }
    Assert-RedNoReparsePath -Path $rootFull
    $items = @(Get-ChildItem -LiteralPath $rootFull -Recurse -Force)
    $reparseItems = @(
        $items |
            Where-Object {
                ($_.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0
            }
    )
    if ($reparseItems.Count -ne 0) {
        throw (
            "$Label contains forbidden reparse points: " +
            (($reparseItems | ForEach-Object { $_.FullName }) -join ', ')
        )
    }

    $records = @()
    foreach ($file in @($items | Where-Object { -not $_.PSIsContainer })) {
        $relative = $file.FullName.Substring($rootFull.Length).TrimStart('\')
        $relative = $relative.Replace('\', '/')
        $before = Get-Item -LiteralPath $file.FullName -Force
        $hash = (
            Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256
        ).Hash.ToUpperInvariant()
        $after = Get-Item -LiteralPath $file.FullName -Force
        if (
            $before.Length -ne $after.Length -or
            $before.LastWriteTimeUtc -ne $after.LastWriteTimeUtc
        ) {
            throw "$Label file changed while hashing: $($file.FullName)"
        }
        $records += [pscustomobject]@{
            relative_path = $relative
            bytes = [int64]$after.Length
            sha256 = $hash
        }
    }
    $records = @($records | Sort-Object relative_path)
    $totalBytes = [int64](($records | Measure-Object bytes -Sum).Sum)
    $manifestText = (
        $records |
            ForEach-Object {
                "$($_.relative_path)|$($_.bytes)|$($_.sha256)"
            }
    ) -join "`n"
    $sha = [System.Security.Cryptography.SHA256]::Create()
    try {
        $encoding = [System.Text.UTF8Encoding]::new($false)
        $manifestHash = [System.BitConverter]::ToString(
            $sha.ComputeHash($encoding.GetBytes($manifestText))
        ).Replace('-', '')
    } finally {
        $sha.Dispose()
    }

    if ($records.Count -ne $ExpectedFileCount) {
        throw (
            "$Label file-count mismatch: expected=$ExpectedFileCount " +
            "actual=$($records.Count)"
        )
    }
    if ($totalBytes -ne $ExpectedBytes) {
        throw (
            "$Label byte-count mismatch: expected=$ExpectedBytes " +
            "actual=$totalBytes"
        )
    }
    if ($manifestHash -ne $ExpectedSha256.ToUpperInvariant()) {
        throw (
            "$Label manifest mismatch: expected=$ExpectedSha256 " +
            "actual=$manifestHash"
        )
    }
    return [ordered]@{
        root = $rootFull
        file_count = $records.Count
        bytes = $totalBytes
        manifest_sha256 = $manifestHash
        manifest_format = 'relative/path|bytes|sha256 joined by LF'
        path_and_descendants_reparse_free = $true
        checked_utc = [datetime]::UtcNow.ToString('o')
    }
}

function New-RedNoClobberDirectory {
    param([Parameter(Mandatory = $true)][string]$Path)

    $fullPath = ConvertTo-RedFullPath -Path $Path
    if (-not $fullPath.StartsWith('D:\', [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Guarded runtime directories must remain on D:: $fullPath"
    }
    $parent = Split-Path -Parent $fullPath
    if (-not (Test-Path -LiteralPath $parent -PathType Container)) {
        throw "No-clobber directory parent is missing: $parent"
    }
    Assert-RedNoReparsePath -Path $parent
    if (Test-Path -LiteralPath $fullPath) {
        throw "Refusing to reuse an existing directory: $fullPath"
    }
    $created = New-Item -Path $fullPath -ItemType Directory -ErrorAction Stop
    if (-not $created -or -not (Test-Path -LiteralPath $fullPath -PathType Container)) {
        throw "Failed to create guarded directory: $fullPath"
    }
    Assert-RedNoReparsePath -Path $fullPath
    return $fullPath
}

function Write-RedNoClobberJson {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)]$Payload
    )

    $parent = Split-Path -Parent $Path
    if (-not (Test-Path -LiteralPath $parent -PathType Container)) {
        throw "JSON output parent is missing: $parent"
    }
    Assert-RedNoReparsePath -Path $parent
    if (Test-Path -LiteralPath $Path) {
        throw "No-clobber JSON output already exists: $Path"
    }
    $json = ($Payload | ConvertTo-Json -Depth 20) + [Environment]::NewLine
    $bytes = [System.Text.UTF8Encoding]::new($false).GetBytes($json)
    $stream = [System.IO.File]::Open(
        $Path,
        [System.IO.FileMode]::CreateNew,
        [System.IO.FileAccess]::Write,
        [System.IO.FileShare]::None
    )
    try {
        $stream.Write($bytes, 0, $bytes.Length)
        $stream.Flush($true)
    } finally {
        $stream.Dispose()
    }
    Assert-RedNoReparsePath -Path $Path
}

function Get-RedMemorySnapshot {
    $operatingSystem = Get-CimInstance -ClassName Win32_OperatingSystem -ErrorAction Stop
    $performanceMemory = Get-CimInstance `
        -ClassName Win32_PerfFormattedData_PerfOS_Memory `
        -ErrorAction Stop
    $freeCommitBytes = (
        [double]$performanceMemory.CommitLimit -
        [double]$performanceMemory.CommittedBytes
    )
    if ($freeCommitBytes -lt 0) {
        throw (
            'Formatted memory counters reported negative commit headroom: ' +
            "limit=$($performanceMemory.CommitLimit) " +
            "committed=$($performanceMemory.CommittedBytes)"
        )
    }
    [ordered]@{
        captured_utc = [datetime]::UtcNow.ToString('o')
        free_physical_gib = [math]::Round(
            ([double]$operatingSystem.FreePhysicalMemory / 1MB),
            3
        )
        free_commit_gib = [math]::Round(
            ($freeCommitBytes / 1GB),
            3
        )
        commit_limit_gib = [math]::Round(
            ([double]$performanceMemory.CommitLimit / 1GB),
            3
        )
        committed_gib = [math]::Round(
            ([double]$performanceMemory.CommittedBytes / 1GB),
            3
        )
    }
}

function Get-RedAllProcesses {
    $processes = @(Get-CimInstance -ClassName Win32_Process -ErrorAction Stop)
    if ($processes.Count -eq 0) {
        throw 'Win32_Process enumeration returned no result.'
    }
    return $processes
}

function ConvertTo-RedProcessRecord {
    param([Parameter(Mandatory = $true)]$Process)

    $creationUtc = $null
    if ($null -ne $Process.CreationDate) {
        $creationUtc = ([datetime]$Process.CreationDate).ToUniversalTime().ToString('o')
    }
    [ordered]@{
        pid = [int]$Process.ProcessId
        parent_pid = [int]$Process.ParentProcessId
        name = [string]$Process.Name
        executable_path = [string]$Process.ExecutablePath
        creation_utc = $creationUtc
        command_line = [string]$Process.CommandLine
        working_set_bytes = [uint64]$Process.WorkingSetSize
        private_bytes = [uint64]$Process.PrivatePageCount
    }
}

function Get-RedPreflightBlockers {
    $blockers = @()
    foreach ($process in @(Get-RedAllProcesses)) {
        $baseName = [System.IO.Path]::GetFileNameWithoutExtension([string]$process.Name)
        if (
            $PreflightExecutableNames -contains $baseName -or
            (
                $baseName -eq 'dotnet' -and
                (
                    [string]$process.CommandLine -match $DotNetHostedBuildPattern -or
                    (
                        -not [string]::IsNullOrWhiteSpace(
                            [string]$process.ExecutablePath
                        ) -and
                        (
                            Test-RedPathEqual `
                                -Left ([string]$process.ExecutablePath) `
                                -Right $AllowedTurnkeyDotNetPath
                        )
                    )
                )
            )
        ) {
            $blockers += ConvertTo-RedProcessRecord -Process $process
        }
    }
    return @($blockers | Sort-Object pid)
}

function Get-RedAllowedScratchTurnkeyVerifySdkArgumentsPattern {
    $project = (ConvertTo-RedFullPath -Path $ProjectPath).Replace('\', '/')
    $intermediate = (
        Join-Path (Split-Path -Parent $ProjectPath) 'Intermediate'
    ).Replace('\', '/')
    $deviceName = [regex]::Escape([string]$env:COMPUTERNAME)
    $commonPrefix = (
        '-ScriptsForProject="' + [regex]::Escape($project) + '"\s+' +
        'Turnkey\s+-utf8output\s+-WaitForUATMutex\s+' +
        '-command=VerifySdk\s+'
    )
    $commonProject = (
        '-project="' + [regex]::Escape($project) + '"\s+'
    )
    $firstProbe = (
        $commonPrefix +
        '-ReportFilename="' + [regex]::Escape($intermediate) +
        '/TurnkeyReport_0\.log"\s+' +
        '-log="' + [regex]::Escape($intermediate) +
        '/TurnkeyLog_0\.log"\s+' +
        $commonProject +
        '-platform=all'
    )
    $deviceProbe = (
        $commonPrefix +
        '-ReportFilename="' + [regex]::Escape($intermediate) +
        '/TurnkeyReport_1\.log"\s+' +
        '-log="' + [regex]::Escape($intermediate) +
        '/TurnkeyLog_1\.log"\s+' +
        $commonProject +
        '-Device=Win64@' + $deviceName + '\s+-nocompile\s+-nocompileuat'
    )
    return '(?:' + $firstProbe + '|' + $deviceProbe + ')'
}

function Get-RedUniqueSnapshotProcessByPid {
    param(
        [Parameter(Mandatory = $true)][int]$ProcessId,
        [Parameter(Mandatory = $true)][object[]]$Processes
    )

    $matches = @(
        $Processes |
            Where-Object { [int]$_.ProcessId -eq $ProcessId }
    )
    if ($matches.Count -ne 1) {
        return $null
    }
    return $matches[0]
}

function Test-RedAllowedScratchTurnkeyVerifySdkProcess {
    param(
        [Parameter(Mandatory = $true)]$Process,
        [Parameter(Mandatory = $true)][object[]]$Processes,
        [Parameter(Mandatory = $true)]$ExpectedEditorIdentity,
        [Parameter(Mandatory = $true)][hashtable]$ProcessImageBindingCache
    )

    $baseName = [System.IO.Path]::GetFileNameWithoutExtension(
        [string]$Process.Name
    )
    if ($baseName -cne 'dotnet') {
        return $false
    }
    $dotNetImageBinding = Get-RedEffectiveProcessImageBinding `
        -Process $Process `
        -PerSnapshotCache $ProcessImageBindingCache `
        -AllowBlankWmiNativeFallback
    if (
        -not [bool]$dotNetImageBinding.success -or
        -not (
            Test-RedPathEqual `
                -Left ([string]$dotNetImageBinding.path) `
                -Right $AllowedTurnkeyDotNetPath
        )
    ) {
        return $false
    }

    $commandLine = ([string]$Process.CommandLine).Replace('\', '/')
    if ([string]::IsNullOrWhiteSpace($commandLine)) {
        return $false
    }
    $argumentsPattern = Get-RedAllowedScratchTurnkeyVerifySdkArgumentsPattern
    $dotNetPattern = (
        '^\s*"?dotnet"?\s+"?AutomationTool\.dll"?\s+' +
        $argumentsPattern +
        '\s*$'
    )
    if (-not [regex]::IsMatch(
        $commandLine,
        $dotNetPattern,
        [System.Text.RegularExpressions.RegexOptions]::IgnoreCase
    )) {
        return $false
    }

    $commandHost = Get-RedUniqueSnapshotProcessByPid `
        -ProcessId ([int]$Process.ParentProcessId) `
        -Processes $Processes
    if ($null -eq $commandHost) {
        return $false
    }
    $commandHostImageBinding = Get-RedEffectiveProcessImageBinding `
        -Process $commandHost `
        -PerSnapshotCache $ProcessImageBindingCache
    if (
        [System.IO.Path]::GetFileNameWithoutExtension(
            [string]$commandHost.Name
        ) -cne 'cmd' -or
        -not [bool]$commandHostImageBinding.success -or
        -not (
            Test-RedPathEqual `
                -Left ([string]$commandHostImageBinding.path) `
                -Right $AllowedTurnkeyCommandHostPath
        ) -or
        [int]$commandHost.ParentProcessId -ne [int]$ExpectedEditorIdentity.pid
    ) {
        return $false
    }

    $editorSnapshot = Get-RedUniqueSnapshotProcessByPid `
        -ProcessId ([int]$ExpectedEditorIdentity.pid) `
        -Processes $Processes
    if ($null -eq $editorSnapshot) {
        return $false
    }
    $editorSnapshotRecord = ConvertTo-RedProcessRecord -Process $editorSnapshot
    if (-not (
        Test-RedExactIdentity `
            -Expected $ExpectedEditorIdentity `
            -Actual $editorSnapshotRecord
    )) {
        return $false
    }

    $commandHostLine = ([string]$commandHost.CommandLine).Replace('\', '/')
    if ([string]::IsNullOrWhiteSpace($commandHostLine)) {
        return $false
    }
    $commandHostPathPattern = [regex]::Escape(
        $AllowedTurnkeyCommandHostPath.Replace('\', '/')
    )
    $runUatPathPattern = [regex]::Escape(
        $AllowedTurnkeyRunUatPath.Replace('\', '/')
    )
    $commandHostPattern = (
        '^\s*(?:"?' + $commandHostPathPattern +
        '"?|"?cmd(?:\.exe)?"?)\s+/c\s+""' +
        $runUatPathPattern + '"\s+' +
        $argumentsPattern +
        '"\s*$'
    )
    if (-not [regex]::IsMatch(
        $commandHostLine,
        $commandHostPattern,
        [System.Text.RegularExpressions.RegexOptions]::IgnoreCase
    )) {
        return $false
    }

    $commandHostRecord = ConvertTo-RedProcessRecord -Process $commandHost
    $dotNetRecord = ConvertTo-RedProcessRecord -Process $Process
    if (
        [string]::IsNullOrWhiteSpace([string]$commandHostRecord.creation_utc) -or
        [string]::IsNullOrWhiteSpace([string]$dotNetRecord.creation_utc)
    ) {
        return $false
    }
    try {
        $editorCreated = [datetimeoffset]::Parse(
            [string]$ExpectedEditorIdentity.creation_utc
        )
        $commandHostCreated = [datetimeoffset]::Parse(
            [string]$commandHostRecord.creation_utc
        )
        $dotNetCreated = [datetimeoffset]::Parse(
            [string]$dotNetRecord.creation_utc
        )
    } catch {
        return $false
    }
    if (
        $commandHostCreated -lt $editorCreated -or
        $dotNetCreated -lt $commandHostCreated
    ) {
        return $false
    }

    # The pinned RunUAT script is the authority that establishes
    # Engine/Binaries/DotNET/AutomationTool as the relative payload CWD.
    $null = Assert-RedPinnedFile `
        -Path $AllowedTurnkeyCommandHostPath `
        -ExpectedSha256 $ExpectedTurnkeyCommandHostSha256 `
        -Label 'Windows Turnkey command host'
    $null = Assert-RedPinnedFile `
        -Path $AllowedTurnkeyRunUatPath `
        -ExpectedSha256 $ExpectedTurnkeyRunUatSha256 `
        -Label 'UE5.8 RunUAT script'
    $null = Assert-RedPinnedFile `
        -Path $AllowedTurnkeyGetDotNetPath `
        -ExpectedSha256 $ExpectedTurnkeyGetDotNetSha256 `
        -Label 'UE5.8 RunUAT bundled-dotnet selector'
    $null = Assert-RedPinnedFile `
        -Path $AllowedTurnkeyInstalledBuildMarkerPath `
        -ExpectedSha256 $ExpectedTurnkeyInstalledBuildMarkerSha256 `
        -Label 'UE5.8 installed-build marker'
    $null = Assert-RedPinnedFile `
        -Path $AllowedTurnkeyAutomationToolPath `
        -ExpectedSha256 $ExpectedTurnkeyAutomationToolSha256 `
        -Label 'UE5.8 AutomationTool payload'
    $null = Assert-RedPinnedFile `
        -Path $AllowedTurnkeyAutomationScriptPath `
        -ExpectedSha256 $ExpectedTurnkeyAutomationScriptSha256 `
        -Label 'UE5.8 Turnkey VerifySdk implementation'
    $null = Assert-RedPinnedFile `
        -Path $AllowedTurnkeyUnrealBuildToolPath `
        -ExpectedSha256 $ExpectedTurnkeyUnrealBuildToolSha256 `
        -Label 'UE5.8 Turnkey SDK-query implementation'
    $null = Assert-RedPinnedFile `
        -Path $AllowedTurnkeyDotNetPath `
        -ExpectedSha256 $ExpectedTurnkeyDotNetSha256 `
        -Label 'UE5.8 bundled Turnkey dotnet host'

    return $true
}

function Get-RedTurnkeyObservationUpdate {
    param(
        [Parameter(Mandatory = $true)][AllowEmptyCollection()][object[]]$Observed,
        [Parameter(Mandatory = $true)][AllowEmptyCollection()][object[]]$Current
    )

    [object[]]$updated = @($Observed)
    foreach ($turnkeyProcess in $Current) {
        $key = "$($turnkeyProcess.pid)|$($turnkeyProcess.creation_utc)"
        if (
            @(
                $updated |
                    Where-Object { $_.key -ceq $key }
            ).Count -eq 0
        ) {
            $processClassification = [string]$turnkeyProcess.classification
            if ([string]::IsNullOrWhiteSpace($processClassification)) {
                $processClassification = (
                    'exact editor-bound scratch-only UE startup dotnet process; ' +
                    'not build/cook/package'
                )
            }
            $updated += [ordered]@{
                key = $key
                pid = $turnkeyProcess.pid
                parent_pid = $turnkeyProcess.parent_pid
                name = $turnkeyProcess.name
                executable_path = $turnkeyProcess.executable_path
                attested_executable_path = (
                    $turnkeyProcess.attested_executable_path
                )
                executable_path_attestation = (
                    $turnkeyProcess.executable_path_attestation
                )
                creation_utc = $turnkeyProcess.creation_utc
                command_line = $turnkeyProcess.command_line
                observed_wmi_ancestry = $turnkeyProcess.observed_wmi_ancestry
                relative_payload_cwd_basis = (
                    $turnkeyProcess.relative_payload_cwd_basis
                )
                classification = $processClassification
            }
        }
    }
    return [pscustomobject][ordered]@{
        observed = @($updated)
        distinct_sampled_monitor_count = @($updated).Count
        violation = (@($updated).Count -gt 1)
    }
}

function Test-RedAllowedScratchValidatePlatformsProcess {
    param(
        [Parameter(Mandatory = $true)]$Process,
        [Parameter(Mandatory = $true)][object[]]$Processes,
        [Parameter(Mandatory = $true)]$ExpectedEditorIdentity,
        [Parameter(Mandatory = $true)][hashtable]$ProcessImageBindingCache
    )

    $dotNetImageBinding = Get-RedEffectiveProcessImageBinding `
        -Process $Process `
        -PerSnapshotCache $ProcessImageBindingCache `
        -AllowBlankWmiNativeFallback
    if (
        [System.IO.Path]::GetFileNameWithoutExtension(
            [string]$Process.Name
        ) -cne 'dotnet' -or
        -not [bool]$dotNetImageBinding.success -or
        -not (
            Test-RedPathEqual `
                -Left ([string]$dotNetImageBinding.path) `
                -Right $AllowedTurnkeyDotNetPath
        )
    ) {
        return $false
    }

    $commandLine = ([string]$Process.CommandLine).Replace('\', '/')
    if ([string]::IsNullOrWhiteSpace($commandLine)) {
        return $false
    }
    $project = [regex]::Escape(
        (ConvertTo-RedFullPath -Path $ProjectPath).Replace('\', '/')
    )
    $log = [regex]::Escape(
        (Join-Path (Split-Path -Parent $ProjectPath) 'Saved/Logs/AutoSDKInfo.txt').Replace('\', '/')
    )
    $argumentsPattern = (
        '-Mode=ValidatePlatforms\s+-OutputSDKs\s+-AllPlatforms\s+' +
        '-project="' + $project + '"\s+-log="' + $log +
        '"\s+-verbose\s+-timestamps'
    )
    $dotNetPattern = (
        '^\s*dotnet\s+"?\.\./\.\./Engine/Binaries/DotNET/UnrealBuildTool/' +
        'UnrealBuildTool\.dll"?\s+' + $argumentsPattern + '\s*$'
    )
    if (-not [regex]::IsMatch(
        $commandLine,
        $dotNetPattern,
        [System.Text.RegularExpressions.RegexOptions]::IgnoreCase
    )) {
        return $false
    }

    $commandHost = Get-RedUniqueSnapshotProcessByPid `
        -ProcessId ([int]$Process.ParentProcessId) `
        -Processes $Processes
    if ($null -eq $commandHost) {
        return $false
    }
    $commandHostImageBinding = Get-RedEffectiveProcessImageBinding `
        -Process $commandHost `
        -PerSnapshotCache $ProcessImageBindingCache
    if (
        [System.IO.Path]::GetFileNameWithoutExtension(
            [string]$commandHost.Name
        ) -cne 'cmd' -or
        -not [bool]$commandHostImageBinding.success -or
        -not (
            Test-RedPathEqual `
                -Left ([string]$commandHostImageBinding.path) `
                -Right $AllowedTurnkeyCommandHostPath
        ) -or
        [int]$commandHost.ParentProcessId -ne [int]$ExpectedEditorIdentity.pid
    ) {
        return $false
    }

    $editorSnapshot = Get-RedUniqueSnapshotProcessByPid `
        -ProcessId ([int]$ExpectedEditorIdentity.pid) `
        -Processes $Processes
    if ($null -eq $editorSnapshot) {
        return $false
    }
    $editorSnapshotRecord = ConvertTo-RedProcessRecord -Process $editorSnapshot
    if (-not (
        Test-RedExactIdentity `
            -Expected $ExpectedEditorIdentity `
            -Actual $editorSnapshotRecord
    )) {
        return $false
    }

    $commandHostLine = ([string]$commandHost.CommandLine).Replace('\', '/')
    if ([string]::IsNullOrWhiteSpace($commandHostLine)) {
        return $false
    }
    $commandHostPathPattern = [regex]::Escape(
        $AllowedTurnkeyCommandHostPath.Replace('\', '/')
    )
    $buildPathPattern = [regex]::Escape(
        $AllowedValidatePlatformsBuildPath.Replace('\', '/')
    )
    $commandHostPattern = (
        '^\s*(?:"?' + $commandHostPathPattern +
        '"?|"?cmd(?:\.exe)?"?)\s+/c\s+""' +
        $buildPathPattern + '"\s+' +
        $argumentsPattern +
        '"\s*$'
    )
    if (-not [regex]::IsMatch(
        $commandHostLine,
        $commandHostPattern,
        [System.Text.RegularExpressions.RegexOptions]::IgnoreCase
    )) {
        return $false
    }

    $commandHostRecord = ConvertTo-RedProcessRecord -Process $commandHost
    $dotNetRecord = ConvertTo-RedProcessRecord -Process $Process
    if (
        [string]::IsNullOrWhiteSpace([string]$commandHostRecord.creation_utc) -or
        [string]::IsNullOrWhiteSpace([string]$dotNetRecord.creation_utc)
    ) {
        return $false
    }
    try {
        $editorCreated = [datetimeoffset]::Parse(
            [string]$ExpectedEditorIdentity.creation_utc
        )
        $commandHostCreated = [datetimeoffset]::Parse(
            [string]$commandHostRecord.creation_utc
        )
        $dotNetCreated = [datetimeoffset]::Parse(
            [string]$dotNetRecord.creation_utc
        )
    } catch {
        return $false
    }
    if (
        $commandHostCreated -lt $editorCreated -or
        $dotNetCreated -lt $commandHostCreated
    ) {
        return $false
    }

    $null = Assert-RedPinnedFile `
        -Path $AllowedTurnkeyCommandHostPath `
        -ExpectedSha256 $ExpectedTurnkeyCommandHostSha256 `
        -Label 'Windows ValidatePlatforms command host'
    $null = Assert-RedPinnedFile `
        -Path $AllowedValidatePlatformsBuildPath `
        -ExpectedSha256 $ExpectedValidatePlatformsBuildSha256 `
        -Label 'UE5.8 ValidatePlatforms Build script'
    $null = Assert-RedPinnedFile `
        -Path $AllowedValidatePlatformsUnrealBuildToolPath `
        -ExpectedSha256 $ExpectedValidatePlatformsUnrealBuildToolSha256 `
        -Label 'UE5.8 ValidatePlatforms UnrealBuildTool payload'
    $null = Assert-RedPinnedFile `
        -Path $AllowedTurnkeyDotNetPath `
        -ExpectedSha256 $ExpectedTurnkeyDotNetSha256 `
        -Label 'UE5.8 bundled ValidatePlatforms dotnet host'

    return $true
}

function Get-RedPostLaunchProcessClassification {
    param(
        [Parameter(Mandatory = $true)]$ExpectedEditorIdentity,
        [Parameter(Mandatory = $true)][object[]]$Processes
    )

    $expectedPid = [int]$ExpectedEditorIdentity.pid
    $overlaps = @()
    $allowedTurnkey = @()
    $processImageBindingCache = @{}
    foreach ($process in $Processes) {
        if ([int]$process.ProcessId -eq $expectedPid) {
            continue
        }
        $baseName = [System.IO.Path]::GetFileNameWithoutExtension([string]$process.Name)
        if ($PostLaunchPrimaryNames -contains $baseName) {
            $overlaps += ConvertTo-RedProcessRecord -Process $process
            continue
        }
        if (
            $baseName -eq 'dotnet' -and
            (
                [string]$process.CommandLine -match $DotNetHostedBuildPattern -or
                (
                    -not [string]::IsNullOrWhiteSpace(
                        [string]$process.ExecutablePath
                    ) -and
                    (
                        Test-RedPathEqual `
                            -Left ([string]$process.ExecutablePath) `
                            -Right $AllowedTurnkeyDotNetPath
                    )
                )
            )
        ) {
            $isAllowedTurnkey = Test-RedAllowedScratchTurnkeyVerifySdkProcess `
                -Process $process `
                -Processes $Processes `
                -ExpectedEditorIdentity $ExpectedEditorIdentity `
                -ProcessImageBindingCache $processImageBindingCache
            $isAllowedValidatePlatforms = Test-RedAllowedScratchValidatePlatformsProcess `
                -Process $process `
                -Processes $Processes `
                -ExpectedEditorIdentity $ExpectedEditorIdentity `
                -ProcessImageBindingCache $processImageBindingCache
            $processImageBinding = Get-RedEffectiveProcessImageBinding `
                -Process $process `
                -PerSnapshotCache $processImageBindingCache `
                -AllowBlankWmiNativeFallback
            if ($isAllowedTurnkey -or $isAllowedValidatePlatforms) {
                $commandHost = Get-RedUniqueSnapshotProcessByPid `
                    -ProcessId ([int]$process.ParentProcessId) `
                    -Processes $Processes
                $editorSnapshot = Get-RedUniqueSnapshotProcessByPid `
                    -ProcessId $expectedPid `
                    -Processes $Processes
                $allowedRecord = ConvertTo-RedProcessRecord -Process $process
                $commandHostRecord = if ($null -eq $commandHost) {
                    $null
                } else {
                    ConvertTo-RedProcessRecord -Process $commandHost
                }
                $allowedScriptPath = if ($isAllowedTurnkey) {
                    $AllowedTurnkeyRunUatPath
                } else {
                    $AllowedValidatePlatformsBuildPath
                }
                $allowedEstablishedDirectory = if ($isAllowedTurnkey) {
                    Split-Path -Parent $AllowedTurnkeyAutomationToolPath
                } else {
                    Split-Path -Parent $AllowedValidatePlatformsBuildPath
                }
                $allowedBehavior = if ($isAllowedTurnkey) {
                    'pinned RunUAT.bat pushd into the exact AutomationTool ' +
                    'directory before invoking relative AutomationTool.dll'
                } else {
                    'exact editor-cmd-Build.bat-dotnet ValidatePlatforms probe ' +
                    'for the current scratch project only'
                }
                $allowedRecord['executable_path_attestation'] = (
                    $processImageBinding
                )
                $allowedRecord['attested_executable_path'] = (
                    [string]$processImageBinding.path
                )
                $allowedRecord['classification'] = if ($isAllowedTurnkey) {
                    'exact editor-bound scratch-only UE Turnkey VerifySdk; ' +
                    'not build/cook/package'
                } else {
                    'exact editor-bound scratch-only UBT ValidatePlatforms; ' +
                    'not build/cook/package'
                }
                $allowedRecord['observed_wmi_ancestry'] = [ordered]@{
                    editor = ConvertTo-RedProcessRecord -Process $editorSnapshot
                    command_host = $commandHostRecord
                    command_host_executable_path_attestation = (
                        Get-RedEffectiveProcessImageBinding `
                            -Process $commandHost `
                            -PerSnapshotCache $processImageBindingCache
                    )
                    dotnet = ConvertTo-RedProcessRecord -Process $process
                    evidence_limit = (
                        'WMI parent PID and creation ordering are descriptive ' +
                        'normal-operation evidence, not cryptographic ancestry'
                    )
                }
                $allowedRecord['relative_payload_cwd_basis'] = [ordered]@{
                    script = $allowedScriptPath
                    established_directory = $allowedEstablishedDirectory
                    behavior = $allowedBehavior
                    evidence_limit = (
                        'The process snapshot does not directly expose or attest CWD'
                    )
                }
                $allowedTurnkey += $allowedRecord
            } else {
                $rejectedRecord = ConvertTo-RedProcessRecord -Process $process
                $rejectedRecord['executable_path_attestation'] = (
                    $processImageBinding
                )
                $rejectedParent = Get-RedUniqueSnapshotProcessByPid `
                    -ProcessId ([int]$process.ParentProcessId) `
                    -Processes $Processes
                $rejectedRecord['parent_executable_path_attestation'] = if (
                    $null -eq $rejectedParent
                ) {
                    $null
                } else {
                    Get-RedEffectiveProcessImageBinding `
                        -Process $rejectedParent `
                        -PerSnapshotCache $processImageBindingCache
                }
                $overlaps += $rejectedRecord
            }
        }
    }
    return [pscustomobject][ordered]@{
        overlaps = @($overlaps | Sort-Object pid)
        allowed_turnkey_verify_sdk = @($allowedTurnkey | Sort-Object pid)
    }
}

function Get-RedZenProcesses {
    $records = @()
    foreach ($process in @(Get-RedAllProcesses)) {
        $baseName = [System.IO.Path]::GetFileNameWithoutExtension([string]$process.Name)
        if ($ZenExecutableNames -contains $baseName) {
            $records += ConvertTo-RedProcessRecord -Process $process
        }
    }
    return @($records | Sort-Object pid)
}

function Get-RedTraceServerProcesses {
    $records = @()
    foreach ($process in @(Get-RedAllProcesses)) {
        $baseName = [System.IO.Path]::GetFileNameWithoutExtension([string]$process.Name)
        if ($TraceServerExecutableNames -contains $baseName) {
            $records += ConvertTo-RedProcessRecord -Process $process
        }
    }
    return @($records | Sort-Object pid)
}

function Test-RedAllowedCoreTraceListener {
    param(
        [Parameter(Mandatory = $true)]$Listener,
        [Parameter(Mandatory = $true)][int]$ExpectedPid
    )

    return (
        [string]$Listener.protocol -ceq 'TCP' -and
        [int]$Listener.local_port -eq 1985 -and
        [int]$Listener.owning_pid -eq $ExpectedPid
    )
}

function Test-RedAllowedEditorStartupUdpListener {
    param(
        [Parameter(Mandatory = $true)]$Listener,
        [Parameter(Mandatory = $true)][int]$ExpectedPid
    )

    return (
        [string]$Listener.protocol -ceq 'UDP' -and
        [string]$Listener.local_address -ceq '0.0.0.0' -and
        [int]$Listener.local_port -eq 11111 -and
        [int]$Listener.owning_pid -eq $ExpectedPid
    )
}

function Get-RedProcessIdentity {
    param([Parameter(Mandatory = $true)][int]$ProcessId)

    $result = @(
        Get-CimInstance -ClassName Win32_Process `
            -Filter "ProcessId = $ProcessId" `
            -ErrorAction Stop
    )
    if ($result.Count -eq 0) {
        return $null
    }
    if ($result.Count -ne 1) {
        throw "PID identity lookup returned $($result.Count) records for PID $ProcessId."
    }
    return ConvertTo-RedProcessRecord -Process $result[0]
}

function Test-RedExactIdentity {
    param(
        [Parameter(Mandatory = $true)]$Expected,
        [Parameter(Mandatory = $true)]$Actual
    )

    if (
        [string]::IsNullOrWhiteSpace([string]$Expected.executable_path) -or
        [string]::IsNullOrWhiteSpace([string]$Actual.executable_path) -or
        [string]::IsNullOrWhiteSpace([string]$Expected.creation_utc) -or
        [string]::IsNullOrWhiteSpace([string]$Actual.creation_utc) -or
        [string]::IsNullOrWhiteSpace([string]$Expected.command_line) -or
        [string]::IsNullOrWhiteSpace([string]$Actual.command_line)
    ) {
        return $false
    }
    return (
        [int]$Expected.pid -eq [int]$Actual.pid -and
        (Test-RedPathEqual -Left $Expected.executable_path -Right $Actual.executable_path) -and
        [string]$Expected.creation_utc -ceq [string]$Actual.creation_utc -and
        [string]$Expected.command_line -ceq [string]$Actual.command_line
    )
}

function Get-RedEditorOwnedListeners {
    param([Parameter(Mandatory = $true)][int]$ProcessId)

    $listeners = @()
    $tcp = @(
        Get-NetTCPConnection -State Listen -ErrorAction Stop |
            Where-Object { [int]$_.OwningProcess -eq $ProcessId }
    )
    foreach ($endpoint in $tcp) {
        $listeners += [ordered]@{
            protocol = 'TCP'
            local_address = [string]$endpoint.LocalAddress
            local_port = [int]$endpoint.LocalPort
            owning_pid = [int]$endpoint.OwningProcess
        }
    }
    $udp = @(
        Get-NetUDPEndpoint -ErrorAction Stop |
            Where-Object { [int]$_.OwningProcess -eq $ProcessId }
    )
    foreach ($endpoint in $udp) {
        $listeners += [ordered]@{
            protocol = 'UDP'
            local_address = [string]$endpoint.LocalAddress
            local_port = [int]$endpoint.LocalPort
            owning_pid = [int]$endpoint.OwningProcess
        }
    }
    return @($listeners | Sort-Object protocol, local_port, local_address)
}

function Invoke-RedRequiredMonitorSensor {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][scriptblock]$Operation
    )

    $capturedUtc = [datetime]::UtcNow.ToString('o')
    try {
        $value = & $Operation
        return [pscustomobject][ordered]@{
            sensor_name = $Name
            captured_utc = $capturedUtc
            success = $true
            value = $value
            error_type = $null
            error_message = $null
        }
    } catch {
        return [pscustomobject][ordered]@{
            sensor_name = $Name
            captured_utc = $capturedUtc
            success = $false
            value = $null
            error_type = $_.Exception.GetType().FullName
            error_message = $_.Exception.Message
        }
    }
}

function Get-RedMonitorSensorEvidence {
    param([Parameter(Mandatory = $true)]$SensorResult)

    return [ordered]@{
        sensor_name = [string]$SensorResult.sensor_name
        captured_utc = [string]$SensorResult.captured_utc
        success = [bool]$SensorResult.success
        error_type = if ([bool]$SensorResult.success) {
            $null
        } else {
            [string]$SensorResult.error_type
        }
        error_message = if ([bool]$SensorResult.success) {
            $null
        } else {
            [string]$SensorResult.error_message
        }
    }
}

function Get-RedMonitorSensorFailureRecord {
    param([Parameter(Mandatory = $true)]$SensorResult)

    if ([bool]$SensorResult.success) {
        return $null
    }
    return [ordered]@{
        sensor_name = [string]$SensorResult.sensor_name
        captured_utc = [string]$SensorResult.captured_utc
        error_type = [string]$SensorResult.error_type
        error_message = [string]$SensorResult.error_message
    }
}

function Get-RedMonitorSensorGuardReason {
    param([Parameter(Mandatory = $true)]$SensorFailure)

    return (
        "required monitor sensor '$($SensorFailure.sensor_name)' failed: " +
        [string]$SensorFailure.error_message
    )
}

function Stop-RedExactLaunchedEditor {
    param(
        [Parameter(Mandatory = $true)]$ExpectedIdentity,
        [Parameter(Mandatory = $true)]$ProcessObject,
        [Parameter(Mandatory = $true)][string]$Reason
    )

    if (
        [int]$ExpectedIdentity.pid -ne [int]$ProcessObject.Id -or
        [string]::IsNullOrWhiteSpace([string]$ExpectedIdentity.executable_path) -or
        [string]::IsNullOrWhiteSpace([string]$ExpectedIdentity.creation_utc) -or
        [string]::IsNullOrWhiteSpace([string]$ExpectedIdentity.command_line)
    ) {
        return [ordered]@{
            requested = $true
            stopped = $false
            proves_exact_editor_stopped = $false
            authenticated_launch_binding_refused = $true
            reason = $Reason
            expected_identity = $ExpectedIdentity
            process_object_pid = [int]$ProcessObject.Id
        }
    }

    $statusError = $null
    try {
        $ProcessObject.Refresh()
        if ($ProcessObject.HasExited) {
            return [ordered]@{
                requested = $true
                stopped = $false
                proves_exact_editor_stopped = $true
                already_exited = $true
                exact_pid_only = [int]$ExpectedIdentity.pid
                retained_process_handle_used = $true
                fresh_identity_sensor_required = $false
                children_or_name_kill_used = $false
                reason = $Reason
            }
        }
    } catch {
        $statusError = [ordered]@{
            type = $_.Exception.GetType().FullName
            message = $_.Exception.Message
        }
    }

    try {
        $ProcessObject.Kill()
    } catch {
        $killError = $_
        try {
            $ProcessObject.Refresh()
            if ($ProcessObject.HasExited) {
                return [ordered]@{
                    requested = $true
                    stopped = $false
                    proves_exact_editor_stopped = $true
                    already_exited = $true
                    exact_pid_only = [int]$ExpectedIdentity.pid
                    retained_process_handle_used = $true
                    fresh_identity_sensor_required = $false
                    children_or_name_kill_used = $false
                    status_sensor_error = $statusError
                    reason = $Reason
                }
            }
        } catch {
        }
        return [ordered]@{
            requested = $true
            stopped = $false
            proves_exact_editor_stopped = $false
            retained_process_handle_stop_error = $killError.Exception.Message
            exact_pid_only = [int]$ExpectedIdentity.pid
            retained_process_handle_used = $true
            fresh_identity_sensor_required = $false
            children_or_name_kill_used = $false
            status_sensor_error = $statusError
            reason = $Reason
        }
    }

    if (-not $ProcessObject.WaitForExit(30000)) {
        throw (
            "Exact UnrealEditor PID $($ExpectedIdentity.pid) did not exit " +
            'within 30 seconds after retained-process-handle Kill.'
        )
    }
    return [ordered]@{
        requested = $true
        stopped = $true
        proves_exact_editor_stopped = $true
        already_exited = $false
        exact_pid_only = [int]$ExpectedIdentity.pid
        retained_process_handle_used = $true
        fresh_identity_sensor_required = $false
        children_or_name_kill_used = $false
        status_sensor_error = $statusError
        reason = $Reason
    }
}

function Stop-RedRetainedLaunchedProcessBeforeIdentity {
    param(
        [Parameter(Mandatory = $true)]$ProcessObject,
        [Parameter(Mandatory = $true)][string]$Reason
    )

    $retainedPid = [int]$ProcessObject.Id
    $statusError = $null
    try {
        $ProcessObject.Refresh()
        if ($ProcessObject.HasExited) {
            return [ordered]@{
                requested = $true
                stopped = $false
                proves_exact_editor_stopped = $true
                already_exited = $true
                exact_pid_only = $retainedPid
                retained_process_handle_used = $true
                pre_identity_handle_only = $true
                fresh_identity_sensor_required = $false
                children_or_name_kill_used = $false
                reason = $Reason
            }
        }
    } catch {
        $statusError = [ordered]@{
            type = $_.Exception.GetType().FullName
            message = $_.Exception.Message
        }
    }

    try {
        $ProcessObject.Kill()
    } catch {
        $killError = $_
        try {
            $ProcessObject.Refresh()
            if ($ProcessObject.HasExited) {
                return [ordered]@{
                    requested = $true
                    stopped = $false
                    proves_exact_editor_stopped = $true
                    already_exited = $true
                    exact_pid_only = $retainedPid
                    retained_process_handle_used = $true
                    pre_identity_handle_only = $true
                    fresh_identity_sensor_required = $false
                    children_or_name_kill_used = $false
                    status_sensor_error = $statusError
                    reason = $Reason
                }
            }
        } catch {
        }
        return [ordered]@{
            requested = $true
            stopped = $false
            proves_exact_editor_stopped = $false
            retained_process_handle_stop_error = $killError.Exception.Message
            exact_pid_only = $retainedPid
            retained_process_handle_used = $true
            pre_identity_handle_only = $true
            fresh_identity_sensor_required = $false
            children_or_name_kill_used = $false
            status_sensor_error = $statusError
            reason = $Reason
        }
    }

    if (-not $ProcessObject.WaitForExit(30000)) {
        throw (
            "Retained pre-identity process handle for PID $retainedPid did not " +
            'exit within 30 seconds after Kill.'
        )
    }
    return [ordered]@{
        requested = $true
        stopped = $true
        proves_exact_editor_stopped = $true
        already_exited = $false
        exact_pid_only = $retainedPid
        retained_process_handle_used = $true
        pre_identity_handle_only = $true
        fresh_identity_sensor_required = $false
        children_or_name_kill_used = $false
        status_sensor_error = $statusError
        reason = $Reason
    }
}

function Stop-RedLaunchedEditorForGuardFailure {
    param(
        [Parameter(Mandatory = $true)]$ProcessObject,
        $ExpectedIdentity,
        [Parameter(Mandatory = $true)][string]$Reason
    )

    $identityStop = $null
    if ($null -ne $ExpectedIdentity) {
        $identityStop = Stop-RedExactLaunchedEditor `
            -ExpectedIdentity $ExpectedIdentity `
            -ProcessObject $ProcessObject `
            -Reason $Reason
        if ([bool]$identityStop.proves_exact_editor_stopped) {
            return $identityStop
        }
    }
    $handleStop = Stop-RedRetainedLaunchedProcessBeforeIdentity `
        -ProcessObject $ProcessObject `
        -Reason $Reason
    if ($null -ne $identityStop) {
        $handleStop['prior_identity_bound_stop_attempt'] = $identityStop
    }
    return $handleStop
}

function Assert-RedSuccessfulLiveAudit {
    param([Parameter(Mandatory = $true)]$Payload)

    if (-not ($Payload -is [pscustomobject])) {
        throw 'Live audit root must be one JSON object.'
    }
    $failures = @()
    if (
        -not ($Payload.schema_version -is [int]) -or
        $Payload.schema_version -ne 1
    ) {
        $failures += 'schema_version must be the JSON integer 1'
    }
    if (
        -not ($Payload.module -is [string]) -or
        $Payload.module -cne 'M07'
    ) {
        $failures += 'module must be the JSON string M07'
    }
    if (
        -not ($Payload.operation -is [string]) -or
        $Payload.operation -cne
        'tropical_planetary_biome_live_snap_visual_validation_v1'
    ) {
        $failures += 'operation must be the exact JSON string'
    }
    if (
        -not ($Payload.evidence_class -is [string]) -or
        $Payload.evidence_class -cne 'automation'
    ) {
        $failures += 'evidence_class must be the JSON string automation'
    }
    if (
        -not ($Payload.requested_evidence_class -is [string]) -or
        $Payload.requested_evidence_class -cne
        'real_gpu_visual_pending_external_pixel_inspection'
    ) {
        $failures += 'requested_evidence_class must be the exact JSON string'
    }
    if (
        -not ($Payload.result -is [string]) -or
        $Payload.result -cne
        'passed_pending_screenshot_pixel_inspection'
    ) {
        $failures += (
            'result must be the exact successful pending-pixel-review JSON string'
        )
    }
    if (
        -not ($Payload.project_file -is [string]) -or
        -not (Test-RedPathEqual -Left $Payload.project_file -Right $ProjectPath)
    ) {
        $failures += 'project_file must be the exact JSON string path'
    }
    if (
        -not ($Payload.map -is [string]) -or
        $Payload.map -cne $MapPackage
    ) {
        $failures += 'map must be the exact JSON string package'
    }
    if (
        -not ($Payload.scratch_only -is [bool]) -or
        $Payload.scratch_only -ne $true
    ) {
        $failures += 'scratch_only must be the JSON Boolean true'
    }
    if (
        -not ($Payload.PIE_started -is [bool]) -or
        $Payload.PIE_started -ne $false
    ) {
        $failures += 'PIE_started must remain the JSON Boolean false'
    }
    if (
        -not ($Payload.providers_used -is [bool]) -or
        $Payload.providers_used -ne $false
    ) {
        $failures += 'providers_used must remain the JSON Boolean false'
    }
    if (
        -not ($Payload.water_or_cloud_assets_applied -is [bool]) -or
        $Payload.water_or_cloud_assets_applied -ne $false
    ) {
        $failures += (
            'water_or_cloud_assets_applied must remain the JSON Boolean false'
        )
    }
    if (-not ($Payload.claims -is [pscustomobject])) {
        $failures += 'claims must be one JSON object'
    } else {
        if (
            -not ($Payload.claims.scratch_map_native_snap_saved -is [bool]) -or
            $Payload.claims.scratch_map_native_snap_saved -ne $true
        ) {
            $failures += (
                'scratch_map_native_snap_saved must be the JSON Boolean true'
            )
        }
        if (
            -not ($Payload.claims.managed_actors_snapped -is [int]) -or
            $Payload.claims.managed_actors_snapped -ne 17
        ) {
            $failures += 'managed_actors_snapped must be the JSON integer 17'
        }
        if (
            -not ($Payload.claims.screenshot_files_verified -is [bool]) -or
            $Payload.claims.screenshot_files_verified -ne $true
        ) {
            $failures += (
                'screenshot_files_verified must be the JSON Boolean true'
            )
        }
        foreach ($falseClaim in @(
            'collision_accepted'
            'screenshot_pixels_inspected'
            'real_gpu_pixels_verified'
            'PIE_or_gameplay_accepted'
            'water_integrated'
            'cloud_integrated'
            'performance_accepted'
            'surface_to_orbit_accepted'
            'production_integration_accepted'
        )) {
            $falseClaimValue = $Payload.claims.$falseClaim
            if (
                -not ($falseClaimValue -is [bool]) -or
                $falseClaimValue -ne $false
            ) {
                $failures += (
                    "$falseClaim must remain the JSON Boolean false"
                )
            }
        }
    }
    if ($failures.Count -ne 0) {
        throw (
            'Live audit failed its exact success/claim gate: ' +
            ($failures -join '; ')
        )
    }
    return [ordered]@{
        accepted = $true
        exact_result = [string]$Payload.result
        evidence_class = [string]$Payload.evidence_class
        requested_evidence_class = [string]$Payload.requested_evidence_class
        pixels_still_require_external_inspection = $true
        gameplay_or_production_acceptance_claimed = $false
    }
}

function Set-RedChildEnvironment {
    param([Parameter(Mandatory = $true)]$Values)

    $previous = [ordered]@{}
    foreach ($entry in $Values.GetEnumerator()) {
        $previous[$entry.Key] = [Environment]::GetEnvironmentVariable(
            $entry.Key,
            [EnvironmentVariableTarget]::Process
        )
        [Environment]::SetEnvironmentVariable(
            $entry.Key,
            [string]$entry.Value,
            [EnvironmentVariableTarget]::Process
        )
    }
    return $previous
}

function Restore-RedChildEnvironment {
    param([Parameter(Mandatory = $true)]$Previous)

    foreach ($entry in $Previous.GetEnumerator()) {
        [Environment]::SetEnvironmentVariable(
            $entry.Key,
            $entry.Value,
            [EnvironmentVariableTarget]::Process
        )
    }
}

function Assert-RedLaunchArguments {
    param([Parameter(Mandatory = $true)][string[]]$Arguments)

    $expectedExecute = "-ExecutePythonScript=$ValidationScript"
    if (@($Arguments | Where-Object { $_ -ceq $DisablePluginsArgument }).Count -ne 1) {
        throw 'Launch arguments do not contain exactly one exact DisablePlugins contract.'
    }
    if (@($Arguments | Where-Object { $_ -ceq $expectedExecute }).Count -ne 1) {
        throw 'Launch arguments do not contain exactly one exact ExecutePythonScript contract.'
    }
    foreach ($required in @(
        $ProjectPath,
        $MapPackage,
        '-D3D12',
        '-sm6',
        '-NoZenAutoLaunch',
        '-notraceserver',
        '-NoMessaging',
        '-DDC=(ProjectPak,EnginePak,Local)',
        "-LocalDataCachePath=$ReusableLocalDdcPath"
    )) {
        if (@($Arguments | Where-Object { $_ -ceq $required }).Count -ne 1) {
            throw "Launch argument must occur exactly once: $required"
        }
    }
    $joined = $Arguments -join ' '
    foreach ($forbidden in @(
        '-uaip-mcp-enable',
        '-uaip-http-port',
        '-ModelContextProtocolStartServer',
        '-EnablePlugins',
        '-EnableAllPlugins'
    )) {
        if ($joined.IndexOf($forbidden, [System.StringComparison]::OrdinalIgnoreCase) -ge 0) {
            throw "Provider/MCP enable argument is forbidden: $forbidden"
        }
    }
}

function Invoke-RedMonitorSensorFailureInjectionProbes {
    $requiredSensorNames = @(
        'postlaunch_primary_process_enumeration'
        'editor_process_status'
        'exact_editor_identity'
        'memory'
        'overlap_process_enumeration'
        'zen_process_enumeration'
        'unreal_trace_server_enumeration'
        'editor_owned_listener_enumeration'
        'live_audit_presence'
    )
    $sensorProbeResults = @()
    foreach ($sensorName in $requiredSensorNames) {
        $injectedMessage = "injected failure for $sensorName"
        $sensorResult = Invoke-RedRequiredMonitorSensor `
            -Name $sensorName `
            -Operation { throw $injectedMessage }
        $failureRecord = Get-RedMonitorSensorFailureRecord `
            -SensorResult $sensorResult
        if (
            [bool]$sensorResult.success -or
            $null -eq $failureRecord -or
            [string]$failureRecord.sensor_name -cne $sensorName -or
            [string]$failureRecord.error_message -cne $injectedMessage
        ) {
            throw "Sensor failure injection did not fail closed for: $sensorName"
        }
        $guardReason = Get-RedMonitorSensorGuardReason `
            -SensorFailure $failureRecord
        if (
            $guardReason.IndexOf(
                $sensorName,
                [System.StringComparison]::Ordinal
            ) -lt 0 -or
            $guardReason.IndexOf(
                $injectedMessage,
                [System.StringComparison]::Ordinal
            ) -lt 0
        ) {
            throw "Sensor guard reason omitted required evidence for: $sensorName"
        }
        $sensorProbeResults += [ordered]@{
            sensor = Get-RedMonitorSensorEvidence -SensorResult $sensorResult
            failure = $failureRecord
            guard_abort_reason = $guardReason
            passed = $true
        }
    }

    $probeProcess = $null
    $preIdentityProbeProcess = $null
    $stopProbeResult = $null
    $preIdentityStopProbeResult = $null
    $liveAuditContractProbe = $null
    try {
        $hostExecutable = (
            [System.Diagnostics.Process]::GetCurrentProcess().MainModule.FileName
        )
        $probeProcess = Start-Process `
            -FilePath $hostExecutable `
            -ArgumentList (
                '-NoProfile -NonInteractive -Command ' +
                '"Start-Sleep -Seconds 300"'
            ) `
            -WindowStyle Hidden `
            -PassThru
        if ($null -eq $probeProcess) {
            throw 'Exact-process-handle stop probe failed to start.'
        }
        $null = $probeProcess.Handle
        $expectedProbeIdentity = [ordered]@{
            pid = [int]$probeProcess.Id
            name = [System.IO.Path]::GetFileName($hostExecutable)
            executable_path = $hostExecutable
            creation_utc = [datetime]::UtcNow.ToString('o')
            command_line = 'authenticated local sensor-failure probe'
        }
        $stopProbeProxy = [pscustomobject]@{
            Id = [int]$probeProcess.Id
            InnerProcess = $probeProcess
        }
        $stopProbeProxy | Add-Member `
            -MemberType ScriptMethod `
            -Name Refresh `
            -Value {
                throw 'injected retained process status sensor failure'
            }
        $stopProbeProxy | Add-Member `
            -MemberType ScriptMethod `
            -Name Kill `
            -Value {
                $this.InnerProcess.Kill()
            }
        $stopProbeProxy | Add-Member `
            -MemberType ScriptMethod `
            -Name WaitForExit `
            -Value {
                param([int]$Milliseconds)
                return $this.InnerProcess.WaitForExit($Milliseconds)
            }
        $stopProbeResult = Stop-RedExactLaunchedEditor `
            -ExpectedIdentity $expectedProbeIdentity `
            -ProcessObject $stopProbeProxy `
            -Reason 'injected required monitor sensor failure'
        if (
            -not [bool]$stopProbeResult.proves_exact_editor_stopped -or
            [int]$stopProbeResult.exact_pid_only -ne [int]$probeProcess.Id -or
            -not [bool]$stopProbeResult.retained_process_handle_used -or
            [bool]$stopProbeResult.children_or_name_kill_used -or
            ([string]$stopProbeResult.status_sensor_error.message).IndexOf(
                'injected retained process status sensor failure',
                [System.StringComparison]::Ordinal
            ) -lt 0
        ) {
            throw (
                'Authenticated retained-process-handle stop probe failed closed: ' +
                ($stopProbeResult | ConvertTo-Json -Compress -Depth 10)
            )
        }

        $preIdentityProbeProcess = Start-Process `
            -FilePath $hostExecutable `
            -ArgumentList (
                '-NoProfile -NonInteractive -Command ' +
                '"Start-Sleep -Seconds 300"'
            ) `
            -WindowStyle Hidden `
            -PassThru
        if ($null -eq $preIdentityProbeProcess) {
            throw 'Pre-identity retained-process-handle stop probe failed to start.'
        }
        $null = $preIdentityProbeProcess.Handle
        $preIdentityStopProxy = [pscustomobject]@{
            Id = [int]$preIdentityProbeProcess.Id
            InnerProcess = $preIdentityProbeProcess
        }
        $preIdentityStopProxy | Add-Member `
            -MemberType ScriptMethod `
            -Name Refresh `
            -Value {
                throw 'injected pre-identity process status sensor failure'
            }
        $preIdentityStopProxy | Add-Member `
            -MemberType ScriptMethod `
            -Name Kill `
            -Value {
                $this.InnerProcess.Kill()
            }
        $preIdentityStopProxy | Add-Member `
            -MemberType ScriptMethod `
            -Name WaitForExit `
            -Value {
                param([int]$Milliseconds)
                return $this.InnerProcess.WaitForExit($Milliseconds)
            }
        $preIdentityStopProbeResult = Stop-RedRetainedLaunchedProcessBeforeIdentity `
            -ProcessObject $preIdentityStopProxy `
            -Reason 'injected editor identity-capture failure'
        if (
            -not [bool]$preIdentityStopProbeResult.proves_exact_editor_stopped -or
            [int]$preIdentityStopProbeResult.exact_pid_only -ne
                [int]$preIdentityProbeProcess.Id -or
            -not [bool]$preIdentityStopProbeResult.retained_process_handle_used -or
            -not [bool]$preIdentityStopProbeResult.pre_identity_handle_only -or
            [bool]$preIdentityStopProbeResult.children_or_name_kill_used -or
            ([string]$preIdentityStopProbeResult.status_sensor_error.message).IndexOf(
                'injected pre-identity process status sensor failure',
                [System.StringComparison]::Ordinal
            ) -lt 0
        ) {
            throw (
                'Pre-identity retained-process-handle stop probe failed closed: ' +
                ($preIdentityStopProbeResult | ConvertTo-Json -Compress -Depth 10)
            )
        }

        $validAudit = [pscustomobject][ordered]@{
            schema_version = 1
            module = 'M07'
            operation = 'tropical_planetary_biome_live_snap_visual_validation_v1'
            evidence_class = 'automation'
            requested_evidence_class = (
                'real_gpu_visual_pending_external_pixel_inspection'
            )
            result = 'passed_pending_screenshot_pixel_inspection'
            project_file = $ProjectPath
            map = $MapPackage
            scratch_only = $true
            PIE_started = $false
            providers_used = $false
            water_or_cloud_assets_applied = $false
            claims = [pscustomobject][ordered]@{
                scratch_map_native_snap_saved = $true
                managed_actors_snapped = 17
                screenshot_files_verified = $true
                collision_accepted = $false
                screenshot_pixels_inspected = $false
                real_gpu_pixels_verified = $false
                PIE_or_gameplay_accepted = $false
                water_integrated = $false
                cloud_integrated = $false
                performance_accepted = $false
                surface_to_orbit_accepted = $false
                production_integration_accepted = $false
            }
        }
        $validAuditGate = Assert-RedSuccessfulLiveAudit -Payload $validAudit
        $failedAuditRejected = $false
        $unknownEvidenceRejected = $false
        $malformedTypeProbeResults = @()
        try {
            $failedAudit = $validAudit.PSObject.Copy()
            $failedAudit.result = 'failed'
            $null = Assert-RedSuccessfulLiveAudit -Payload $failedAudit
        } catch {
            $failedAuditRejected = $true
        }
        try {
            $unknownEvidenceAudit = $validAudit.PSObject.Copy()
            $unknownEvidenceAudit.evidence_class = 'unknown'
            $null = Assert-RedSuccessfulLiveAudit -Payload $unknownEvidenceAudit
        } catch {
            $unknownEvidenceRejected = $true
        }
        $malformedTypeCases = @(
            [ordered]@{
                name = 'schema_version_string'
                mutate = { param($Probe) $Probe.schema_version = '1' }
            }
            [ordered]@{
                name = 'schema_version_boolean'
                mutate = { param($Probe) $Probe.schema_version = $true }
            }
            [ordered]@{
                name = 'scratch_only_string'
                mutate = { param($Probe) $Probe.scratch_only = 'false' }
            }
            [ordered]@{
                name = 'PIE_started_integer'
                mutate = { param($Probe) $Probe.PIE_started = 0 }
            }
            [ordered]@{
                name = 'providers_used_integer'
                mutate = { param($Probe) $Probe.providers_used = 0 }
            }
            [ordered]@{
                name = 'water_or_cloud_assets_applied_integer'
                mutate = {
                    param($Probe)
                    $Probe.water_or_cloud_assets_applied = 0
                }
            }
            [ordered]@{
                name = 'native_snap_saved_string'
                mutate = {
                    param($Probe)
                    $Probe.claims.scratch_map_native_snap_saved = 'false'
                }
            }
            [ordered]@{
                name = 'managed_actors_snapped_string'
                mutate = {
                    param($Probe)
                    $Probe.claims.managed_actors_snapped = '17'
                }
            }
            [ordered]@{
                name = 'screenshot_files_verified_string'
                mutate = {
                    param($Probe)
                    $Probe.claims.screenshot_files_verified = 'false'
                }
            }
            [ordered]@{
                name = 'false_claim_integer'
                mutate = {
                    param($Probe)
                    $Probe.claims.production_integration_accepted = 0
                }
            }
            [ordered]@{
                name = 'module_singleton_array'
                mutate = { param($Probe) $Probe.module = @('M07') }
            }
            [ordered]@{
                name = 'project_file_singleton_array'
                mutate = {
                    param($Probe)
                    $Probe.project_file = @($ProjectPath)
                }
            }
            [ordered]@{
                name = 'claims_singleton_array'
                mutate = {
                    param($Probe)
                    $Probe.claims = @($Probe.claims)
                }
            }
            [ordered]@{
                name = 'root_singleton_array'
                wrap_root_array = $true
                mutate = { param($Probe) }
            }
        )
        foreach ($malformedTypeCase in $malformedTypeCases) {
            $malformedAudit = (
                $validAudit |
                    ConvertTo-Json -Depth 10 |
                    ConvertFrom-Json -ErrorAction Stop
            )
            if (
                $malformedTypeCase.Contains('wrap_root_array') -and
                [bool]$malformedTypeCase.wrap_root_array
            ) {
                $malformedAudit = @($malformedAudit)
            }
            & $malformedTypeCase.mutate $malformedAudit
            $malformedTypeRejected = $false
            try {
                $null = Assert-RedSuccessfulLiveAudit -Payload $malformedAudit
            } catch {
                $malformedTypeRejected = $true
            }
            if (-not $malformedTypeRejected) {
                throw (
                    'Live-audit malformed JSON type was accepted: ' +
                    [string]$malformedTypeCase.name
                )
            }
            $malformedTypeProbeResults += [ordered]@{
                name = [string]$malformedTypeCase.name
                rejected = $true
                passed = $true
            }
        }
        if (
            -not [bool]$validAuditGate.accepted -or
            -not $failedAuditRejected -or
            -not $unknownEvidenceRejected -or
            $malformedTypeProbeResults.Count -ne $malformedTypeCases.Count
        ) {
            throw 'Live-audit exact success/claim gate probe failed.'
        }
        $liveAuditContractProbe = [ordered]@{
            valid_exact_contract_accepted = $true
            failed_result_rejected = $true
            unknown_evidence_class_rejected = $true
            malformed_json_type_rejection_count = (
                $malformedTypeProbeResults.Count
            )
            malformed_json_type_probes = $malformedTypeProbeResults
            passed = $true
        }
    } finally {
        foreach ($cleanupProcess in @($probeProcess, $preIdentityProbeProcess)) {
            if ($null -eq $cleanupProcess) {
                continue
            }
            try {
                $cleanupProcess.Refresh()
                if (-not $cleanupProcess.HasExited) {
                    $cleanupProcess.Kill()
                    $null = $cleanupProcess.WaitForExit(30000)
                }
            } catch {
                throw (
                    'Failure-injection probe could not prove its exact child exited: ' +
                    $_.Exception.Message
                )
            }
        }
    }

    return [ordered]@{
        schema_version = 1
        module = 'M07'
        operation = 'm07_tropical_guard_sensor_failure_probes_v2'
        result = 'passed'
        unreal_started = $false
        launcher = (Get-RedFileRecord -Path $PSCommandPath)
        injected_sensor_count = $sensorProbeResults.Count
        required_sensor_names = $requiredSensorNames
        sensor_failure_probes = $sensorProbeResults
        exact_process_handle_stop_probe = $stopProbeResult
        pre_identity_retained_process_handle_stop_probe = (
            $preIdentityStopProbeResult
        )
        live_audit_exact_success_contract_probe = $liveAuditContractProbe
    }
}

function New-RedTurnkeyGuardProbeProcess {
    param(
        [Parameter(Mandatory = $true)][int]$ProcessId,
        [Parameter(Mandatory = $true)][int]$ParentProcessId,
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$ExecutablePath,
        [Parameter(Mandatory = $true)][datetime]$CreationDate,
        [Parameter(Mandatory = $true)][string]$CommandLine
    )

    return [pscustomobject][ordered]@{
        ProcessId = $ProcessId
        ParentProcessId = $ParentProcessId
        Name = $Name
        ExecutablePath = $ExecutablePath
        CreationDate = $CreationDate
        CommandLine = $CommandLine
        WorkingSetSize = [uint64]0
        PrivatePageCount = [uint64]0
    }
}

function Copy-RedTurnkeyGuardProbeProcess {
    param(
        [Parameter(Mandatory = $true)]$Process,
        [Parameter(Mandatory = $true)][hashtable]$Overrides
    )

    $values = [ordered]@{
        ProcessId = [int]$Process.ProcessId
        ParentProcessId = [int]$Process.ParentProcessId
        Name = [string]$Process.Name
        ExecutablePath = [string]$Process.ExecutablePath
        CreationDate = [datetime]$Process.CreationDate
        CommandLine = [string]$Process.CommandLine
        WorkingSetSize = [uint64]$Process.WorkingSetSize
        PrivatePageCount = [uint64]$Process.PrivatePageCount
    }
    foreach ($key in $Overrides.Keys) {
        $values[$key] = $Overrides[$key]
    }
    return [pscustomobject]$values
}

function Invoke-RedNativeProcessImageBindingProbes {
    $probeProcess = $null
    $probeResults = [System.Collections.Generic.List[object]]::new()
    try {
        $probeProcess = Start-Process `
            -FilePath "$PSHOME\powershell.exe" `
            -ArgumentList @(
                '-NoProfile'
                '-WindowStyle'
                'Hidden'
                '-Command'
                'Start-Sleep -Seconds 120'
            ) `
            -WindowStyle Hidden `
            -PassThru
        if ($null -eq $probeProcess) {
            throw 'Native process-image binding probe failed to start.'
        }
        $null = $probeProcess.Handle
        Start-Sleep -Milliseconds 200

        $wmiProcess = Get-CimInstance `
            -ClassName Win32_Process `
            -Filter "ProcessId=$($probeProcess.Id)" `
            -ErrorAction Stop
        if ($null -eq $wmiProcess) {
            throw 'Native process-image binding probe WMI record is missing.'
        }
        $blankWmiProcess = [pscustomobject][ordered]@{
            ProcessId = [int]$wmiProcess.ProcessId
            ParentProcessId = [int]$wmiProcess.ParentProcessId
            Name = [string]$wmiProcess.Name
            ExecutablePath = ''
            CreationDate = [datetime]$wmiProcess.CreationDate
            CommandLine = [string]$wmiProcess.CommandLine
            WorkingSetSize = [uint64]$wmiProcess.WorkingSetSize
            PrivatePageCount = [uint64]$wmiProcess.PrivatePageCount
        }
        $expectedPath = ConvertTo-RedFullPath -Path "$PSHOME\powershell.exe"
        $bindingCache = @{}
        $liveBinding = Get-RedEffectiveProcessImageBinding `
            -Process $blankWmiProcess `
            -PerSnapshotCache $bindingCache `
            -AllowBlankWmiNativeFallback
        $livePassed = (
            [bool]$liveBinding.success -and
            [string]$liveBinding.source -ceq (
                'native_query_full_process_image_name_get_process_times'
            ) -and
            [bool]$liveBinding.same_creation_microsecond -and
            [bool]$liveBinding.native_pid_matches -and
            [bool]$liveBinding.native_query.same_handle_path_and_creation -and
            [bool]$liveBinding.native_query.handle_closed -and
            -not [bool]$liveBinding.native_query.raw_handle_disclosed -and
            (
                Test-RedPathEqual `
                    -Left ([string]$liveBinding.path) `
                    -Right $expectedPath
            )
        )
        if (-not $livePassed) {
            throw (
                'Live blank-WMI native process binding probe failed: ' +
                ($liveBinding | ConvertTo-Json -Compress -Depth 12)
            )
        }
        $probeResults.Add([ordered]@{
            name = 'live_blank_wmi_path_same_handle_native_binding'
            passed = $true
            binding = $liveBinding
        }) | Out-Null

        $defaultBlankBinding = Get-RedEffectiveProcessImageBinding `
            -Process $blankWmiProcess `
            -PerSnapshotCache @{}
        if (
            [bool]$defaultBlankBinding.success -or
            [string]$defaultBlankBinding.source -cne (
                'wmi_executable_path_required'
            ) -or
            $null -ne $defaultBlankBinding.native_query
        ) {
            throw (
                'A blank WMI path used native fallback without explicit ' +
                'dotnet-callsite authorization.'
            )
        }
        $probeResults.Add([ordered]@{
            name = 'blank_wmi_path_default_native_fallback_forbidden'
            passed = $true
            binding = $defaultBlankBinding
        }) | Out-Null

        $cacheRepeatBinding = Get-RedEffectiveProcessImageBinding `
            -Process $blankWmiProcess `
            -PerSnapshotCache $bindingCache `
            -AllowBlankWmiNativeFallback
        if (-not [object]::ReferenceEquals($liveBinding, $cacheRepeatBinding)) {
            throw 'Per-snapshot native binding cache did not return one record.'
        }
        $probeResults.Add([ordered]@{
            name = 'same_snapshot_binding_cache_is_idempotent'
            passed = $true
            cache_entry_count = $bindingCache.Count
        }) | Out-Null

        $nonblankWmiProcess = Copy-RedTurnkeyGuardProbeProcess `
            -Process $blankWmiProcess `
            -Overrides @{ ExecutablePath = $expectedPath }
        $nonblankBinding = Get-RedEffectiveProcessImageBinding `
            -Process $nonblankWmiProcess `
            -PerSnapshotCache @{}
        if (
            -not [bool]$nonblankBinding.success -or
            [string]$nonblankBinding.source -cne 'wmi_executable_path' -or
            $null -ne $nonblankBinding.native_query
        ) {
            throw 'Nonblank exact WMI path did not bypass the native fallback.'
        }
        $probeResults.Add([ordered]@{
            name = 'nonblank_exact_wmi_path_bypasses_native_fallback'
            passed = $true
            binding = $nonblankBinding
        }) | Out-Null

        $wrongWmiProcess = Copy-RedTurnkeyGuardProbeProcess `
            -Process $blankWmiProcess `
            -Overrides @{ ExecutablePath = 'C:\Windows\System32\not-dotnet.exe' }
        $wrongWmiBinding = Get-RedEffectiveProcessImageBinding `
            -Process $wrongWmiProcess `
            -PerSnapshotCache @{}
        if (
            -not [bool]$wrongWmiBinding.success -or
            [string]$wrongWmiBinding.source -cne 'wmi_executable_path' -or
            $null -ne $wrongWmiBinding.native_query
        ) {
            throw 'Nonblank wrong WMI path unexpectedly invoked native fallback.'
        }
        $probeResults.Add([ordered]@{
            name = 'nonblank_wrong_wmi_path_never_uses_native_fallback'
            passed = $true
            binding = $wrongWmiBinding
        }) | Out-Null

        $sameMicrosecondBinding = [ordered]@{}
        foreach ($key in $liveBinding.native_query.Keys) {
            $sameMicrosecondBinding[$key] = $liveBinding.native_query[$key]
        }
        $sameMicrosecondWmiCreation = (
            [datetime]$blankWmiProcess.CreationDate
        ).ToUniversalTime()
        [int64]$sameMicrosecondBaseTicks = (
            $sameMicrosecondWmiCreation.Ticks -
            ($sameMicrosecondWmiCreation.Ticks % [int64]10)
        )
        $sameMicrosecondCreation = [datetime]::new(
            $sameMicrosecondBaseTicks + [int64]9,
            [System.DateTimeKind]::Utc
        )
        $sameMicrosecondBinding.creation_utc = $sameMicrosecondCreation.ToString('o')
        $sameMicrosecondValidation = Test-RedNativeProcessImageBinding `
            -Process $blankWmiProcess `
            -NativeBinding $sameMicrosecondBinding
        $sameMicrosecondExpected = (
            (
                ([datetime]$blankWmiProcess.CreationDate).ToUniversalTime().Ticks -
                (
                    ([datetime]$blankWmiProcess.CreationDate).ToUniversalTime().Ticks %
                    [int64]10
                )
            ) -eq
            (
                $sameMicrosecondCreation.Ticks -
                ($sameMicrosecondCreation.Ticks % [int64]10)
            )
        )
        if (
            [bool]$sameMicrosecondValidation.success -ne
                [bool]$sameMicrosecondExpected
        ) {
            throw 'Same-microsecond pure binding probe disagreed with its oracle.'
        }
        $probeResults.Add([ordered]@{
            name = 'creation_binding_uses_exact_wmi_microsecond'
            passed = $true
            expected_success = [bool]$sameMicrosecondExpected
            binding = $sameMicrosecondValidation
        }) | Out-Null

        $nextMicrosecondBinding = [ordered]@{}
        foreach ($key in $liveBinding.native_query.Keys) {
            $nextMicrosecondBinding[$key] = $liveBinding.native_query[$key]
        }
        $wmiCreation = (
            [datetime]$blankWmiProcess.CreationDate
        ).ToUniversalTime()
        [int64]$ticksIntoMicrosecond = $wmiCreation.Ticks % [int64]10
        [int64]$ticksToNextMicrosecond = [int64]10 - $ticksIntoMicrosecond
        $nextMicrosecondBinding.creation_utc = (
            $wmiCreation.AddTicks($ticksToNextMicrosecond).ToString('o')
        )
        $nextMicrosecondValidation = Test-RedNativeProcessImageBinding `
            -Process $blankWmiProcess `
            -NativeBinding $nextMicrosecondBinding
        if ([bool]$nextMicrosecondValidation.success) {
            throw 'Different creation microsecond was accepted.'
        }
        $probeResults.Add([ordered]@{
            name = 'different_creation_microsecond_rejected'
            passed = $true
            binding = $nextMicrosecondValidation
        }) | Out-Null

        $wrongPidBinding = [ordered]@{}
        foreach ($key in $liveBinding.native_query.Keys) {
            $wrongPidBinding[$key] = $liveBinding.native_query[$key]
        }
        $wrongPidBinding.native_pid = [int]$blankWmiProcess.ProcessId + 1
        $wrongPidValidation = Test-RedNativeProcessImageBinding `
            -Process $blankWmiProcess `
            -NativeBinding $wrongPidBinding
        if ([bool]$wrongPidValidation.success) {
            throw 'Native PID mismatch was accepted.'
        }
        $probeResults.Add([ordered]@{
            name = 'native_pid_mismatch_rejected'
            passed = $true
            binding = $wrongPidValidation
        }) | Out-Null

        foreach ($invariantProbe in @(
            [ordered]@{
                name = 'unclosed_native_handle_evidence_rejected'
                field = 'handle_closed'
                value = $false
            }
            [ordered]@{
                name = 'separate_handle_path_time_evidence_rejected'
                field = 'same_handle_path_and_creation'
                value = $false
            }
            [ordered]@{
                name = 'raw_handle_disclosure_evidence_rejected'
                field = 'raw_handle_disclosed'
                value = $true
            }
            [ordered]@{
                name = 'string_same_handle_evidence_rejected'
                field = 'same_handle_path_and_creation'
                value = 'true'
            }
            [ordered]@{
                name = 'string_handle_closed_evidence_rejected'
                field = 'handle_closed'
                value = 'true'
            }
            [ordered]@{
                name = 'string_raw_handle_disclosure_evidence_rejected'
                field = 'raw_handle_disclosed'
                value = 'false'
            }
            [ordered]@{
                name = 'string_native_query_success_evidence_rejected'
                field = 'success'
                value = 'true'
            }
            [ordered]@{
                name = 'string_native_pid_evidence_rejected'
                field = 'native_pid'
                value = [string]$liveBinding.native_query.native_pid
            }
            [ordered]@{
                name = 'string_builder_native_path_evidence_rejected'
                field = 'image_path'
                value = [System.Text.StringBuilder]::new($expectedPath)
            }
            [ordered]@{
                name = 'datetime_native_creation_evidence_rejected'
                field = 'creation_utc'
                value = [datetime]$liveBinding.native_query.creation_utc
            }
        )) {
            $forgedBinding = [ordered]@{}
            foreach ($key in $liveBinding.native_query.Keys) {
                $forgedBinding[$key] = $liveBinding.native_query[$key]
            }
            $forgedBinding[$invariantProbe.field] = $invariantProbe.value
            $forgedValidation = Test-RedNativeProcessImageBinding `
                -Process $blankWmiProcess `
                -NativeBinding $forgedBinding
            if ([bool]$forgedValidation.success) {
                throw (
                    "Forged native binding invariant '$($invariantProbe.field)' " +
                    'was accepted.'
                )
            }
            $probeResults.Add([ordered]@{
                name = $invariantProbe.name
                passed = $true
                binding = $forgedValidation
            }) | Out-Null
        }

        $missingDisclosureBinding = [ordered]@{}
        foreach ($key in $liveBinding.native_query.Keys) {
            if ([string]$key -cne 'raw_handle_disclosed') {
                $missingDisclosureBinding[$key] = (
                    $liveBinding.native_query[$key]
                )
            }
        }
        $missingDisclosureValidation = Test-RedNativeProcessImageBinding `
            -Process $blankWmiProcess `
            -NativeBinding $missingDisclosureBinding
        if ([bool]$missingDisclosureValidation.success) {
            throw 'Missing raw-handle-disclosure evidence was accepted.'
        }
        $probeResults.Add([ordered]@{
            name = 'missing_raw_handle_disclosure_evidence_rejected'
            passed = $true
            binding = $missingDisclosureValidation
        }) | Out-Null

        $missingSuccessBinding = [ordered]@{}
        foreach ($key in $liveBinding.native_query.Keys) {
            if ([string]$key -cne 'success') {
                $missingSuccessBinding[$key] = (
                    $liveBinding.native_query[$key]
                )
            }
        }
        $missingSuccessValidation = Test-RedNativeProcessImageBinding `
            -Process $blankWmiProcess `
            -NativeBinding $missingSuccessBinding
        if ([bool]$missingSuccessValidation.success) {
            throw 'Missing native-query-success evidence was accepted.'
        }
        $probeResults.Add([ordered]@{
            name = 'missing_native_query_success_evidence_rejected'
            passed = $true
            binding = $missingSuccessValidation
        }) | Out-Null

        foreach ($missingField in @(
            [ordered]@{
                name = 'missing_native_pid_evidence_rejected'
                field = 'native_pid'
            }
            [ordered]@{
                name = 'missing_native_path_evidence_rejected'
                field = 'image_path'
            }
            [ordered]@{
                name = 'missing_native_creation_evidence_rejected'
                field = 'creation_utc'
            }
        )) {
            $missingShapeBinding = [ordered]@{}
            foreach ($key in $liveBinding.native_query.Keys) {
                if ([string]$key -cne [string]$missingField.field) {
                    $missingShapeBinding[$key] = (
                        $liveBinding.native_query[$key]
                    )
                }
            }
            $missingShapeValidation = Test-RedNativeProcessImageBinding `
                -Process $blankWmiProcess `
                -NativeBinding $missingShapeBinding
            if ([bool]$missingShapeValidation.success) {
                throw (
                    "Missing native binding field '$($missingField.field)' " +
                    'was accepted.'
                )
            }
            $probeResults.Add([ordered]@{
                name = $missingField.name
                passed = $true
                binding = $missingShapeValidation
            }) | Out-Null
        }

        $wrongPathBinding = [ordered]@{}
        foreach ($key in $liveBinding.native_query.Keys) {
            $wrongPathBinding[$key] = $liveBinding.native_query[$key]
        }
        $wrongPathBinding.image_path = 'C:\Windows\System32\not-dotnet.exe'
        $wrongPathValidation = Test-RedNativeProcessImageBinding `
            -Process $blankWmiProcess `
            -NativeBinding $wrongPathBinding
        if (-not [bool]$wrongPathValidation.success) {
            throw (
                'Pure native binding should preserve a strict wrong path for ' +
                'the caller to compare against its exact expected path.'
            )
        }
        if (Test-RedPathEqual -Left $wrongPathValidation.path -Right $expectedPath) {
            throw 'Wrong native path matched the exact expected path.'
        }
        $probeResults.Add([ordered]@{
            name = 'wrong_native_path_rejected_by_exact_expected_path_gate'
            passed = $true
            binding = $wrongPathValidation
        }) | Out-Null

        $missingCreationProcess = Copy-RedTurnkeyGuardProbeProcess `
            -Process $blankWmiProcess `
            -Overrides @{ CreationDate = $null }
        $missingCreationValidation = Test-RedNativeProcessImageBinding `
            -Process $missingCreationProcess `
            -NativeBinding $liveBinding.native_query
        if ([bool]$missingCreationValidation.success) {
            throw 'Missing WMI creation time was accepted.'
        }
        $probeResults.Add([ordered]@{
            name = 'missing_wmi_creation_rejected'
            passed = $true
            binding = $missingCreationValidation
        }) | Out-Null

        $vanishedBinding = Get-RedNativeProcessImageBinding `
            -ProcessId ([int]::MaxValue)
        if ([bool]$vanishedBinding.success -or [bool]$vanishedBinding.handle_closed) {
            throw 'Nonexistent PID native query did not fail closed before a handle.'
        }
        $probeResults.Add([ordered]@{
            name = 'nonexistent_process_open_rejected'
            passed = $true
            binding = $vanishedBinding
        }) | Out-Null

        return [ordered]@{
            result = 'passed'
            case_count = $probeResults.Count
            cases = @($probeResults)
            unreal_started = $false
            retained_probe_process_handle_used = $true
            process_name_or_tree_kill_used = $false
        }
    } finally {
        if ($null -ne $probeProcess) {
            try {
                if (-not $probeProcess.HasExited) {
                    $probeProcess.Kill()
                    $probeProcess.WaitForExit()
                }
            } finally {
                $probeProcess.Dispose()
            }
        }
    }
}

function Invoke-RedTurnkeyGuardProbes {
    $nativeProcessImageBindingProbes = (
        Invoke-RedNativeProcessImageBindingProbes
    )
    $project = (ConvertTo-RedFullPath -Path $ProjectPath).Replace('\', '/')
    $intermediate = (
        Join-Path (Split-Path -Parent $ProjectPath) 'Intermediate'
    ).Replace('\', '/')
    $turnkeyArguments = (
        "-ScriptsForProject=`"$project`" " +
        'Turnkey -utf8output -WaitForUATMutex -command=VerifySdk ' +
        "-ReportFilename=`"$intermediate/TurnkeyReport_0.log`" " +
        "-log=`"$intermediate/TurnkeyLog_0.log`" " +
        "-project=`"$project`" -platform=all"
    )
    $editorCreated = [datetime]'2026-07-26T00:00:00Z'
    $commandHostCreated = [datetime]'2026-07-26T00:00:01Z'
    $dotNetCreated = [datetime]'2026-07-26T00:00:02Z'
    $editor = New-RedTurnkeyGuardProbeProcess `
        -ProcessId 100 `
        -ParentProcessId 1 `
        -Name 'UnrealEditor.exe' `
        -ExecutablePath $EditorPath `
        -CreationDate $editorCreated `
        -CommandLine (
            "`"$EditorPath`" `"$ProjectPath`" $MapPackage -D3D12 -sm6"
        )
    $commandHost = New-RedTurnkeyGuardProbeProcess `
        -ProcessId 200 `
        -ParentProcessId 100 `
        -Name 'cmd.exe' `
        -ExecutablePath $AllowedTurnkeyCommandHostPath `
        -CreationDate $commandHostCreated `
        -CommandLine (
            '{0} /c ""{1}" {2}"' -f
                $AllowedTurnkeyCommandHostPath,
                $AllowedTurnkeyRunUatPath,
                $turnkeyArguments
        )
    $dotNet = New-RedTurnkeyGuardProbeProcess `
        -ProcessId 300 `
        -ParentProcessId 200 `
        -Name 'dotnet.exe' `
        -ExecutablePath $AllowedTurnkeyDotNetPath `
        -CreationDate $dotNetCreated `
        -CommandLine "dotnet AutomationTool.dll $turnkeyArguments"
    $editorIdentity = ConvertTo-RedProcessRecord -Process $editor

    $caseResults = [System.Collections.Generic.List[object]]::new()
    $assertClassification = {
        param(
            [Parameter(Mandatory = $true)][string]$Name,
            [Parameter(Mandatory = $true)][object[]]$Processes,
            [Parameter(Mandatory = $true)][bool]$ShouldAllow
        )

        $classification = Get-RedPostLaunchProcessClassification `
            -ExpectedEditorIdentity $editorIdentity `
            -Processes $Processes
        $allowedCount = @(
            $classification.allowed_turnkey_verify_sdk
        ).Count
        $overlapCount = @($classification.overlaps).Count
        $passed = if ($ShouldAllow) {
            $allowedCount -eq 1 -and $overlapCount -eq 0
        } else {
            $allowedCount -eq 0 -and $overlapCount -eq 1
        }
        if (-not $passed) {
            throw (
                "Turnkey guard probe '$Name' failed: " +
                "should_allow=$ShouldAllow allowed=$allowedCount " +
                "overlaps=$overlapCount"
            )
        }
        $caseResults.Add([ordered]@{
            name = $Name
            should_allow = $ShouldAllow
            allowed_count = $allowedCount
            overlap_count = $overlapCount
            passed = $true
        }) | Out-Null
        return $classification
    }

    $validClassification = & $assertClassification `
        -Name 'exact_editor_cmd_runuat_dotnet_chain' `
        -Processes @($editor, $commandHost, $dotNet) `
        -ShouldAllow $true

    $validateLog = (
        Join-Path `
            (Split-Path -Parent $ProjectPath) `
            'Saved/Logs/AutoSDKInfo.txt'
    ).Replace('\', '/')
    $validateArguments = (
        '-Mode=ValidatePlatforms -OutputSDKs -AllPlatforms ' +
        "-project=`"$project`" " +
        "-log=`"$validateLog`" -verbose -timestamps"
    )
    $validateCommandHost = New-RedTurnkeyGuardProbeProcess `
        -ProcessId 210 `
        -ParentProcessId 100 `
        -Name 'cmd.exe' `
        -ExecutablePath $AllowedTurnkeyCommandHostPath `
        -CreationDate $commandHostCreated `
        -CommandLine (
            '{0} /c ""{1}" {2}"' -f
                $AllowedTurnkeyCommandHostPath,
                $AllowedValidatePlatformsBuildPath,
                $validateArguments
        )
    $validateDotNet = New-RedTurnkeyGuardProbeProcess `
        -ProcessId 310 `
        -ParentProcessId 210 `
        -Name 'dotnet.exe' `
        -ExecutablePath $AllowedTurnkeyDotNetPath `
        -CreationDate $dotNetCreated `
        -CommandLine (
            'dotnet "../../Engine/Binaries/DotNET/UnrealBuildTool/' +
            'UnrealBuildTool.dll" ' + $validateArguments
        )
    $validValidateClassification = & $assertClassification `
        -Name 'exact_editor_cmd_build_validateplatforms_dotnet_chain' `
        -Processes @($editor, $validateCommandHost, $validateDotNet) `
        -ShouldAllow $true
    $validValidateAllowed = @(
        $validValidateClassification.allowed_turnkey_verify_sdk
    )
    if (
        $validValidateAllowed.Count -ne 1 -or
        [string]$validValidateAllowed[0].executable_path_attestation.source -cne
            'wmi_executable_path' -or
        [string]::IsNullOrWhiteSpace(
            [string]$validValidateAllowed[0].executable_path_attestation.path
        )
    ) {
        throw 'Accepted ValidatePlatforms record lacks executable attestation.'
    }

    $validateBlankWmiPath = Copy-RedTurnkeyGuardProbeProcess `
        -Process $validateDotNet `
        -Overrides @{ ExecutablePath = '' }
    $null = & $assertClassification `
        -Name 'validateplatforms_blank_wmi_path_without_live_binding_rejected' `
        -Processes @($editor, $validateCommandHost, $validateBlankWmiPath) `
        -ShouldAllow $false

    $validateWrongExecutablePath = Copy-RedTurnkeyGuardProbeProcess `
        -Process $validateDotNet `
        -Overrides @{ ExecutablePath = 'D:\Untrusted\dotnet.exe' }
    $null = & $assertClassification `
        -Name 'validateplatforms_nonblank_wrong_executable_path_rejected' `
        -Processes @(
            $editor,
            $validateCommandHost,
            $validateWrongExecutablePath
        ) `
        -ShouldAllow $false

    $validateBlankCommandHostPath = Copy-RedTurnkeyGuardProbeProcess `
        -Process $validateCommandHost `
        -Overrides @{ ExecutablePath = '' }
    $null = & $assertClassification `
        -Name 'validateplatforms_blank_parent_path_without_live_binding_rejected' `
        -Processes @($editor, $validateBlankCommandHostPath, $validateDotNet) `
        -ShouldAllow $false

    $validateWrongParent = Copy-RedTurnkeyGuardProbeProcess `
        -Process $validateCommandHost `
        -Overrides @{ ParentProcessId = 999 }
    $null = & $assertClassification `
        -Name 'validateplatforms_wrong_command_host_parent' `
        -Processes @($editor, $validateWrongParent, $validateDotNet) `
        -ShouldAllow $false

    $null = & $assertClassification `
        -Name 'validateplatforms_missing_command_host' `
        -Processes @($editor, $validateDotNet) `
        -ShouldAllow $false

    $validateWrongBuild = Copy-RedTurnkeyGuardProbeProcess `
        -Process $validateCommandHost `
        -Overrides @{
            CommandLine = $validateCommandHost.CommandLine.Replace(
                'Build.bat',
                'Build-copy.bat'
            )
        }
    $null = & $assertClassification `
        -Name 'validateplatforms_wrong_build_script' `
        -Processes @($editor, $validateWrongBuild, $validateDotNet) `
        -ShouldAllow $false

    $validateWrongPayloadPath = Copy-RedTurnkeyGuardProbeProcess `
        -Process $validateDotNet `
        -Overrides @{
            CommandLine = $validateDotNet.CommandLine.Replace(
                '../../Engine/Binaries/DotNET/UnrealBuildTool/UnrealBuildTool.dll',
                '../../Engine/Binaries/DotNET/AutomationTool/UnrealBuildTool.dll'
            )
        }
    $null = & $assertClassification `
        -Name 'validateplatforms_wrong_ubt_payload_path' `
        -Processes @(
            $editor,
            $validateCommandHost,
            $validateWrongPayloadPath
        ) `
        -ShouldAllow $false

    $validateWrongProject = Copy-RedTurnkeyGuardProbeProcess `
        -Process $validateDotNet `
        -Overrides @{
            CommandLine = $validateDotNet.CommandLine.Replace(
                'Titan.uproject',
                'Other.uproject'
            )
        }
    $null = & $assertClassification `
        -Name 'validateplatforms_wrong_project' `
        -Processes @($editor, $validateCommandHost, $validateWrongProject) `
        -ShouldAllow $false

    $validateTrailingArgument = Copy-RedTurnkeyGuardProbeProcess `
        -Process $validateDotNet `
        -Overrides @{
            CommandLine = $validateDotNet.CommandLine + ' -Target=TitanEditor'
        }
    $null = & $assertClassification `
        -Name 'validateplatforms_trailing_argument_forbidden' `
        -Processes @(
            $editor,
            $validateCommandHost,
            $validateTrailingArgument
        ) `
        -ShouldAllow $false

    $bareCommandHost = Copy-RedTurnkeyGuardProbeProcess `
        -Process $commandHost `
        -Overrides @{
            CommandLine = (
                '"cmd.exe" /c ""{0}" {1}"' -f
                    $AllowedTurnkeyRunUatPath,
                    $turnkeyArguments
            )
        }
    $null = & $assertClassification `
        -Name 'ue_source_shaped_bare_cmd_token' `
        -Processes @($editor, $bareCommandHost, $dotNet) `
        -ShouldAllow $true

    $badCommandHostParent = Copy-RedTurnkeyGuardProbeProcess `
        -Process $commandHost `
        -Overrides @{ ParentProcessId = 999 }
    $null = & $assertClassification `
        -Name 'wrong_command_host_parent' `
        -Processes @($editor, $badCommandHostParent, $dotNet) `
        -ShouldAllow $false

    $null = & $assertClassification `
        -Name 'missing_command_host' `
        -Processes @($editor, $dotNet) `
        -ShouldAllow $false

    $intermediary = New-RedTurnkeyGuardProbeProcess `
        -ProcessId 250 `
        -ParentProcessId 200 `
        -Name 'powershell.exe' `
        -ExecutablePath 'C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe' `
        -CreationDate ([datetime]'2026-07-26T00:00:01.500Z') `
        -CommandLine 'powershell.exe -NoProfile'
    $dotNetWithIntermediary = Copy-RedTurnkeyGuardProbeProcess `
        -Process $dotNet `
        -Overrides @{ ParentProcessId = 250 }
    $null = & $assertClassification `
        -Name 'extra_intermediary_process' `
        -Processes @($editor, $commandHost, $intermediary, $dotNetWithIntermediary) `
        -ShouldAllow $false

    $wrongCommandHostPath = Copy-RedTurnkeyGuardProbeProcess `
        -Process $commandHost `
        -Overrides @{ ExecutablePath = 'D:\Untrusted\cmd.exe' }
    $null = & $assertClassification `
        -Name 'wrong_command_host_path' `
        -Processes @($editor, $wrongCommandHostPath, $dotNet) `
        -ShouldAllow $false

    $wrongRunUat = Copy-RedTurnkeyGuardProbeProcess `
        -Process $commandHost `
        -Overrides @{
            CommandLine = $commandHost.CommandLine.Replace(
                'RunUAT.bat',
                'RunUAT-copy.bat'
            )
        }
    $null = & $assertClassification `
        -Name 'wrong_runuat_path' `
        -Processes @($editor, $wrongRunUat, $dotNet) `
        -ShouldAllow $false

    $wrongPayload = Copy-RedTurnkeyGuardProbeProcess `
        -Process $dotNet `
        -Overrides @{
            CommandLine = $dotNet.CommandLine.Replace(
                'AutomationTool.dll',
                'OtherTool.dll'
            )
        }
    $null = & $assertClassification `
        -Name 'wrong_automationtool_payload' `
        -Processes @($editor, $commandHost, $wrongPayload) `
        -ShouldAllow $false

    $wrongProjectArguments = $turnkeyArguments.Replace(
        'Titan.uproject',
        'Other.uproject'
    )
    $wrongProjectCommandHost = Copy-RedTurnkeyGuardProbeProcess `
        -Process $commandHost `
        -Overrides @{
            CommandLine = (
                '{0} /c ""{1}" {2}"' -f
                    $AllowedTurnkeyCommandHostPath,
                    $AllowedTurnkeyRunUatPath,
                    $wrongProjectArguments
            )
        }
    $wrongProjectDotNet = Copy-RedTurnkeyGuardProbeProcess `
        -Process $dotNet `
        -Overrides @{
            CommandLine = "dotnet AutomationTool.dll $wrongProjectArguments"
        }
    $null = & $assertClassification `
        -Name 'wrong_project' `
        -Processes @($editor, $wrongProjectCommandHost, $wrongProjectDotNet) `
        -ShouldAllow $false

    $buildCookArguments = $turnkeyArguments + ' BuildCookRun'
    $buildCookCommandHost = Copy-RedTurnkeyGuardProbeProcess `
        -Process $commandHost `
        -Overrides @{
            CommandLine = (
                '{0} /c ""{1}" {2}"' -f
                    $AllowedTurnkeyCommandHostPath,
                    $AllowedTurnkeyRunUatPath,
                    $buildCookArguments
            )
        }
    $buildCookDotNet = Copy-RedTurnkeyGuardProbeProcess `
        -Process $dotNet `
        -Overrides @{
            CommandLine = "dotnet AutomationTool.dll $buildCookArguments"
        }
    $null = & $assertClassification `
        -Name 'buildcookrun_forbidden' `
        -Processes @($editor, $buildCookCommandHost, $buildCookDotNet) `
        -ShouldAllow $false

    $updateArguments = $turnkeyArguments.Replace(
        '-platform=all',
        '-UpdateIfNeeded -platform=all'
    )
    $updateCommandHost = Copy-RedTurnkeyGuardProbeProcess `
        -Process $commandHost `
        -Overrides @{
            CommandLine = (
                '{0} /c ""{1}" {2}"' -f
                    $AllowedTurnkeyCommandHostPath,
                    $AllowedTurnkeyRunUatPath,
                    $updateArguments
            )
        }
    $updateDotNet = Copy-RedTurnkeyGuardProbeProcess `
        -Process $dotNet `
        -Overrides @{
            CommandLine = "dotnet AutomationTool.dll $updateArguments"
        }
    $null = & $assertClassification `
        -Name 'update_if_needed_forbidden' `
        -Processes @($editor, $updateCommandHost, $updateDotNet) `
        -ShouldAllow $false

    $mismatchedLogArguments = $turnkeyArguments.Replace(
        'TurnkeyLog_0.log',
        'TurnkeyLog_1.log'
    )
    $mismatchedLogCommandHost = Copy-RedTurnkeyGuardProbeProcess `
        -Process $commandHost `
        -Overrides @{
            CommandLine = (
                '{0} /c ""{1}" {2}"' -f
                    $AllowedTurnkeyCommandHostPath,
                    $AllowedTurnkeyRunUatPath,
                    $mismatchedLogArguments
            )
        }
    $mismatchedLogDotNet = Copy-RedTurnkeyGuardProbeProcess `
        -Process $dotNet `
        -Overrides @{
            CommandLine = "dotnet AutomationTool.dll $mismatchedLogArguments"
        }
    $null = & $assertClassification `
        -Name 'mismatched_report_log_index' `
        -Processes @($editor, $mismatchedLogCommandHost, $mismatchedLogDotNet) `
        -ShouldAllow $false

    $indexOneArguments = $turnkeyArguments.Replace(
        'TurnkeyReport_0.log',
        'TurnkeyReport_1.log'
    ).Replace(
        'TurnkeyLog_0.log',
        'TurnkeyLog_1.log'
    )
    $indexOneCommandHost = Copy-RedTurnkeyGuardProbeProcess `
        -Process $commandHost `
        -Overrides @{
            CommandLine = (
                '{0} /c ""{1}" {2}"' -f
                    $AllowedTurnkeyCommandHostPath,
                    $AllowedTurnkeyRunUatPath,
                    $indexOneArguments
            )
        }
    $indexOneDotNet = Copy-RedTurnkeyGuardProbeProcess `
        -Process $dotNet `
        -Overrides @{
            CommandLine = "dotnet AutomationTool.dll $indexOneArguments"
        }
    $null = & $assertClassification `
        -Name 'matched_later_report_log_index_forbidden' `
        -Processes @($editor, $indexOneCommandHost, $indexOneDotNet) `
        -ShouldAllow $false

    $crossIndexDotNet = Copy-RedTurnkeyGuardProbeProcess `
        -Process $dotNet `
        -Overrides @{
            CommandLine = "dotnet AutomationTool.dll $indexOneArguments"
        }
    $null = & $assertClassification `
        -Name 'parent_child_report_log_index_mismatch' `
        -Processes @($editor, $commandHost, $crossIndexDotNet) `
        -ShouldAllow $false

    $trailingArguments = $turnkeyArguments + ' -nocompile'
    $trailingCommandHost = Copy-RedTurnkeyGuardProbeProcess `
        -Process $commandHost `
        -Overrides @{
            CommandLine = (
                '{0} /c ""{1}" {2}"' -f
                    $AllowedTurnkeyCommandHostPath,
                    $AllowedTurnkeyRunUatPath,
                    $trailingArguments
            )
        }
    $trailingDotNet = Copy-RedTurnkeyGuardProbeProcess `
        -Process $dotNet `
        -Overrides @{
            CommandLine = "dotnet AutomationTool.dll $trailingArguments"
        }
    $null = & $assertClassification `
        -Name 'trailing_arguments_forbidden' `
        -Processes @($editor, $trailingCommandHost, $trailingDotNet) `
        -ShouldAllow $false

    $wrongEditorSnapshot = Copy-RedTurnkeyGuardProbeProcess `
        -Process $editor `
        -Overrides @{ CommandLine = 'UnrealEditor.exe other-project.uproject' }
    $null = & $assertClassification `
        -Name 'editor_snapshot_identity_mismatch' `
        -Processes @($wrongEditorSnapshot, $commandHost, $dotNet) `
        -ShouldAllow $false

    $earlyCommandHost = Copy-RedTurnkeyGuardProbeProcess `
        -Process $commandHost `
        -Overrides @{ CreationDate = [datetime]'2026-07-25T23:59:59Z' }
    $null = & $assertClassification `
        -Name 'parent_creation_order_invalid' `
        -Processes @($editor, $earlyCommandHost, $dotNet) `
        -ShouldAllow $false

    $duplicateCommandHost = Copy-RedTurnkeyGuardProbeProcess `
        -Process $commandHost `
        -Overrides @{ CommandLine = 'cmd.exe /c echo duplicate' }
    $null = & $assertClassification `
        -Name 'duplicate_parent_pid_ambiguous' `
        -Processes @($editor, $commandHost, $duplicateCommandHost, $dotNet) `
        -ShouldAllow $false

    $firstAllowed = @($validClassification.allowed_turnkey_verify_sdk)
    $firstUpdate = Get-RedTurnkeyObservationUpdate `
        -Observed @() `
        -Current $firstAllowed
    if (
        [bool]$firstUpdate.violation -or
        [int]$firstUpdate.distinct_sampled_monitor_count -ne 1
    ) {
        throw 'First exact Turnkey observation did not satisfy the sampled guard.'
    }
    $repeatUpdate = Get-RedTurnkeyObservationUpdate `
        -Observed @($firstUpdate.observed) `
        -Current $firstAllowed
    if (
        [bool]$repeatUpdate.violation -or
        [int]$repeatUpdate.distinct_sampled_monitor_count -ne 1
    ) {
        throw 'Repeated samples of one exact Turnkey process were not idempotent.'
    }
    $secondAllowed = [ordered]@{
        pid = 301
        parent_pid = 201
        name = 'dotnet.exe'
        executable_path = $AllowedTurnkeyDotNetPath
        attested_executable_path = $AllowedTurnkeyDotNetPath
        executable_path_attestation = (
            $firstAllowed[0].executable_path_attestation
        )
        creation_utc = '2026-07-26T00:01:00.0000000Z'
        command_line = "dotnet AutomationTool.dll $turnkeyArguments"
        classification = (
            'exact editor-bound scratch-only UE Turnkey VerifySdk; ' +
            'not build/cook/package'
        )
        observed_wmi_ancestry = $firstAllowed[0].observed_wmi_ancestry
        relative_payload_cwd_basis = $firstAllowed[0].relative_payload_cwd_basis
    }
    $sequentialUpdate = Get-RedTurnkeyObservationUpdate `
        -Observed @($repeatUpdate.observed) `
        -Current @($secondAllowed)
    if (
        -not [bool]$sequentialUpdate.violation -or
        [int]$sequentialUpdate.distinct_sampled_monitor_count -ne 2
    ) {
        throw 'Sequential sampled Turnkey processes did not fail the sampled guard.'
    }

    $listenerCaseDefinitions = @(
        [ordered]@{
            name = 'exact_editor_tcp_1985_allowed'
            listener = [pscustomobject]@{
                protocol = 'TCP'
                local_address = '0.0.0.0'
                local_port = 1985
                owning_pid = 100
            }
            expected_core_trace = $true
            expected_startup_udp = $false
        }
        [ordered]@{
            name = 'exact_editor_udp_11111_allowed'
            listener = [pscustomobject]@{
                protocol = 'UDP'
                local_address = '0.0.0.0'
                local_port = 11111
                owning_pid = 100
            }
            expected_core_trace = $false
            expected_startup_udp = $true
        }
        [ordered]@{
            name = 'udp_11111_wrong_pid_rejected'
            listener = [pscustomobject]@{
                protocol = 'UDP'
                local_address = '0.0.0.0'
                local_port = 11111
                owning_pid = 999
            }
            expected_core_trace = $false
            expected_startup_udp = $false
        }
        [ordered]@{
            name = 'udp_11111_wrong_address_rejected'
            listener = [pscustomobject]@{
                protocol = 'UDP'
                local_address = '127.0.0.1'
                local_port = 11111
                owning_pid = 100
            }
            expected_core_trace = $false
            expected_startup_udp = $false
        }
        [ordered]@{
            name = 'udp_5353_provider_adjacent_rejected'
            listener = [pscustomobject]@{
                protocol = 'UDP'
                local_address = '0.0.0.0'
                local_port = 5353
                owning_pid = 100
            }
            expected_core_trace = $false
            expected_startup_udp = $false
        }
        [ordered]@{
            name = 'tcp_8000_mcp_port_rejected'
            listener = [pscustomobject]@{
                protocol = 'TCP'
                local_address = '127.0.0.1'
                local_port = 8000
                owning_pid = 100
            }
            expected_core_trace = $false
            expected_startup_udp = $false
        }
    )
    $listenerCaseResults = @()
    foreach ($definition in $listenerCaseDefinitions) {
        $actualCoreTrace = Test-RedAllowedCoreTraceListener `
            -Listener $definition.listener `
            -ExpectedPid 100
        $actualStartupUdp = Test-RedAllowedEditorStartupUdpListener `
            -Listener $definition.listener `
            -ExpectedPid 100
        if (
            [bool]$actualCoreTrace -ne [bool]$definition.expected_core_trace -or
            [bool]$actualStartupUdp -ne [bool]$definition.expected_startup_udp
        ) {
            throw (
                "Listener guard probe '$($definition.name)' failed: " +
                "core=$actualCoreTrace startup_udp=$actualStartupUdp"
            )
        }
        $listenerCaseResults += [ordered]@{
            name = $definition.name
            actual_core_trace = [bool]$actualCoreTrace
            actual_startup_udp = [bool]$actualStartupUdp
            passed = $true
        }
    }

    return [ordered]@{
        schema_version = 1
        module = 'M07'
        operation = 'm07_tropical_guard_process_listener_probes_v3'
        result = 'passed'
        unreal_started = $false
        launcher = (Get-RedFileRecord -Path $PSCommandPath)
        native_process_image_binding_probes = $nativeProcessImageBindingProbes
        case_count = $caseResults.Count
        classification_cases = @($caseResults)
        listener_case_count = @($listenerCaseResults).Count
        listener_classification_cases = @($listenerCaseResults)
        sampled_startup_monitor_guard = [ordered]@{
            first_observation_passed = $true
            repeated_same_process_idempotent = $true
            sequential_distinct_process_rejected = $true
            final_distinct_sampled_monitor_count = (
                $sequentialUpdate.distinct_sampled_monitor_count
            )
            complete_process_lifetime_capture_claimed = $false
        }
        pinned_payloads_checked = @(
            $AllowedTurnkeyCommandHostPath
            $AllowedTurnkeyRunUatPath
            $AllowedValidatePlatformsBuildPath
            $AllowedTurnkeyGetDotNetPath
            $AllowedTurnkeyInstalledBuildMarkerPath
            $AllowedTurnkeyAutomationToolPath
            $AllowedTurnkeyAutomationScriptPath
            $AllowedTurnkeyUnrealBuildToolPath
            $AllowedValidatePlatformsUnrealBuildToolPath
            $AllowedTurnkeyDotNetPath
        )
        required_absent_mutation_paths = @(
            $ValidatePlatformsBuildUbtPath
        )
        required_child_environment_contract = $RequiredEnvironment
        full_runtime_tree_manifests_checked_by_probe = $false
        full_runtime_tree_manifests_checked_by_guarded_preflight = $true
    }
}

function Write-RedGuardProbeEvidence {
    param(
        [Parameter(Mandatory = $true)][string]$Prefix,
        [Parameter(Mandatory = $true)]$Payload
    )

    if (-not (Test-Path -LiteralPath $DiagnosticsParent -PathType Container)) {
        throw "Required D: diagnostics parent is missing: $DiagnosticsParent"
    }
    Assert-RedNoReparsePath -Path $DiagnosticsParent
    $probeRunId = (
        $Prefix + '_' +
        [datetime]::UtcNow.ToString('yyyyMMdd_HHmmss_fffZ') + '_' +
        [guid]::NewGuid().ToString('N').Substring(0, 8)
    )
    $probeRunDirectory = New-RedNoClobberDirectory `
        -Path (Join-Path $DiagnosticsParent $probeRunId)
    $probeEvidencePath = Join-Path $probeRunDirectory 'probe_evidence.json'
    $Payload['evidence_path'] = $probeEvidencePath
    Write-RedNoClobberJson -Path $probeEvidencePath -Payload $Payload
    return $probeEvidencePath
}

if ($RunTurnkeyGuardProbes) {
    $turnkeyProbePayload = Invoke-RedTurnkeyGuardProbes
    $turnkeyProbeEvidencePath = Write-RedGuardProbeEvidence `
        -Prefix 'turnkey_guard_probe' `
        -Payload $turnkeyProbePayload
    $turnkeyProbePayload | ConvertTo-Json -Depth 20
    Write-Host "PROBE_EVIDENCE=$turnkeyProbeEvidencePath"
    return
}

if ($RunSensorFailureInjectionProbes) {
    $probePayload = Invoke-RedMonitorSensorFailureInjectionProbes
    $sensorProbeEvidencePath = Write-RedGuardProbeEvidence `
        -Prefix 'sensor_failure_probe' `
        -Payload $probePayload
    $probePayload | ConvertTo-Json -Depth 20
    Write-Host "PROBE_EVIDENCE=$sensorProbeEvidencePath"
    return
}

if ($AbortFreePhysicalGiB -ge $MinimumFreePhysicalGiB) {
    throw 'Abort physical-RAM floor must remain below the preflight threshold.'
}
if ($AbortFreeCommitGiB -ge $MinimumFreeCommitGiB) {
    throw 'Abort commit floor must remain below the preflight threshold.'
}
if ($PreflightSampleCount -ne 6 -or $PreflightIntervalSeconds -ne 2) {
    throw 'This dedicated launcher requires exactly six preflight samples two seconds apart.'
}

if (-not (Test-Path -LiteralPath $DiagnosticsParent -PathType Container)) {
    throw "Required D: diagnostics parent is missing: $DiagnosticsParent"
}
Assert-RedNoReparsePath -Path $DiagnosticsParent
$runId = (
    [datetime]::UtcNow.ToString('yyyyMMdd_HHmmss_fffZ') + '_' +
    [guid]::NewGuid().ToString('N').Substring(0, 8)
)
$runDirectory = New-RedNoClobberDirectory -Path (Join-Path $DiagnosticsParent $runId)
$localDdcDirectory = ConvertTo-RedFullPath -Path $ReusableLocalDdcPath
$liveAuditPath = Join-Path $runDirectory 'live_validation_audit.json'
$unrealLogPath = Join-Path $runDirectory 'UnrealEditor.log'
$launchEvidencePath = Join-Path $runDirectory 'launch_evidence.json'
$monitorEvidencePath = Join-Path $runDirectory 'monitor_evidence.json'
$launcherRecord = Get-RedFileRecord -Path $PSCommandPath

$RequiredEnvironment['REDMMO_M07_TROPICAL_LIVE_DIAGNOSTICS_DIR'] = $runDirectory
$RequiredEnvironment['REDMMO_M07_TROPICAL_LIVE_AUDIT_OUTPUT'] = $liveAuditPath

$editorProcess = $null
$launchedIdentity = $null
$launchEvidenceWritten = $false
$monitorEvidenceWritten = $false
$guardAbortReason = $null
$stopResult = $null
$monitorSamples = @()
$monitorSensorFailures = @()
$editorOwnedListenersObserved = @()
$allowedCoreTraceListenersObserved = @()
$allowedEditorStartupUdpListenersObserved = @()
$unexpectedEditorOwnedListenersObserved = @()
$allowedTurnkeyVerifySdkObserved = @()
$preflightSamples = @()
$capturedFailure = $null
$monitorResult = 'initializing'
$localDdcReuseRecord = $null

$monitorEvidence = [ordered]@{
    schema_version = 1
    module = 'M07'
    operation = 'guarded_tropical_planetary_biome_live_validation_v3'
    launcher = $launcherRecord
    run_id = $runId
    run_directory = $runDirectory
    started_utc = [datetime]::UtcNow.ToString('o')
    result = $monitorResult
    thresholds = [ordered]@{
        preflight_sample_count = $PreflightSampleCount
        preflight_interval_seconds = $PreflightIntervalSeconds
        minimum_free_physical_gib = $MinimumFreePhysicalGiB
        minimum_free_commit_gib = $MinimumFreeCommitGiB
        abort_free_physical_gib = $AbortFreePhysicalGiB
        abort_free_commit_gib = $AbortFreeCommitGiB
        maximum_monitor_seconds = $MaximumMonitorSeconds
    }
    exact_pid_stop_only = $true
    process_tree_or_name_kill_forbidden = $true
    required_monitor_sensors_fail_closed = $true
    required_monitor_sensor_names = @(
        'postlaunch_primary_process_enumeration'
        'editor_process_status'
        'exact_editor_identity'
        'memory'
        'overlap_process_enumeration'
        'zen_process_enumeration'
        'unreal_trace_server_enumeration'
        'editor_owned_listener_enumeration'
        'live_audit_presence'
    )
    unrelated_ports_preserved = $true
    udp_5353_never_modified = $true
    listeners_before = @()
    allowed_core_trace_listener_contract = [ordered]@{
        protocol = 'TCP'
        local_port = 1985
        owning_process = 'exact returned UnrealEditor PID only'
        maximum_count = 1
        classification = 'UE TraceLog control, not provider activity'
    }
    allowed_editor_startup_udp_listener_contract = [ordered]@{
        protocol = 'UDP'
        local_address = '0.0.0.0'
        local_port = 11111
        owning_process = 'exact returned UnrealEditor PID only'
        maximum_count = 1
        classification = (
            'approved normal editor startup listener; not AI, MCP, or provider activity'
        )
    }
    allowed_scratch_turnkey_verify_sdk_contract = [ordered]@{
        executable_path = $AllowedTurnkeyDotNetPath
        executable_path_primary_source = 'Win32_Process.ExecutablePath'
        blank_wmi_executable_path_fallback = [ordered]@{
            source = 'QueryFullProcessImageNameW and GetProcessTimes'
            process_access_mask = 'PROCESS_QUERY_LIMITED_INFORMATION (0x1000)'
            inheritable_handle = $false
            same_native_handle_for_path_pid_and_creation = $true
            wmi_native_creation_match_precision = 'one microsecond'
            native_pid_must_match_wmi_pid = $true
            accepted_path = $AllowedTurnkeyDotNetPath
            absolute_dos_path_required = $true
            access_or_binding_failure_behavior = (
                'reject as overlap and stop only the retained exact editor handle'
            )
            command_line_or_process_name_path_inference_allowed = $false
            cross_sample_cache_allowed = $false
            raw_handle_evidence_allowed = $false
        }
        command_host_path = $AllowedTurnkeyCommandHostPath
        run_uat_path = $AllowedTurnkeyRunUatPath
        validate_platforms_build_path = $AllowedValidatePlatformsBuildPath
        validate_platforms_build_ubt_path = $ValidatePlatformsBuildUbtPath
        bundled_dotnet_selector_path = $AllowedTurnkeyGetDotNetPath
        installed_build_marker_path = $AllowedTurnkeyInstalledBuildMarkerPath
        automation_tool_path = $AllowedTurnkeyAutomationToolPath
        turnkey_automation_script_path = $AllowedTurnkeyAutomationScriptPath
        unreal_build_tool_path = $AllowedTurnkeyUnrealBuildToolPath
        validate_platforms_unreal_build_tool_path = (
            $AllowedValidatePlatformsUnrealBuildToolPath
        )
        validate_platforms_unreal_build_tool_tree_root = (
            $AllowedValidatePlatformsUnrealBuildToolRoot
        )
        automation_tree_root = $AllowedTurnkeyAutomationRoot
        bundled_dotnet_tree_root = $AllowedTurnkeyDotNetRoot
        stale_post_turnkey_variables_path = $TurnkeyPostVariablesPath
        observed_process_chain = 'retained UnrealEditor -> cmd.exe -> dotnet.exe'
        observed_process_chain_limit = (
            'WMI parent PID and creation ordering are descriptive normal-operation ' +
            'evidence, not cryptographic ancestry'
        )
        relative_payload_working_directory_basis = (
            'exact pinned RunUAT.bat pushd to ' +
            'Engine/Binaries/DotNET/AutomationTool'
        )
        relative_payload_working_directory_limit = (
            'WMI process snapshots do not directly expose or attest CWD'
        )
        maximum_concurrent_count = 1
        maximum_distinct_sampled_startup_monitor_count = 1
        observation_scope = (
            'polling samples after retained editor identity capture through the ' +
            'live-audit terminal boundary'
        )
        complete_process_lifetime_capture_claimed = $false
        monitoring_after_editor_left_open_claimed = $false
        adversarial_process_containment_claimed = $false
        operations = @(
            'Turnkey VerifySdk'
            'UnrealBuildTool ValidatePlatforms'
        )
        project = $ProjectPath
        output_root = (
            Join-Path (Split-Path -Parent $ProjectPath) 'Intermediate'
        )
        inherited_dotnet_code_injection_environment_scrubbed = $true
        post_turnkey_variables_prelaunch_absence_required = $true
        generated_post_turnkey_variables_runtime_attested = $false
        build_ubt_mutation_path_prelaunch_absence_required = $true
        build_cook_package_or_install_allowed = $false
    }
    local_ddc_reuse_planned = [ordered]@{
        path = $localDdcDirectory
        source_run_id = $ReusableLocalDdcSourceRunId
        created_by_current_run = $false
    }
}

try {
    $pinnedInputs = [ordered]@{
        editor = Assert-RedPinnedFile `
            -Path $EditorPath `
            -ExpectedSha256 $ExpectedEditorSha256 `
            -Label 'UE5.8 editor'
        turnkey_dotnet = Assert-RedPinnedFile `
            -Path $AllowedTurnkeyDotNetPath `
            -ExpectedSha256 $ExpectedTurnkeyDotNetSha256 `
            -Label 'UE5.8 bundled Turnkey dotnet host'
        turnkey_command_host = Assert-RedPinnedFile `
            -Path $AllowedTurnkeyCommandHostPath `
            -ExpectedSha256 $ExpectedTurnkeyCommandHostSha256 `
            -Label 'Windows Turnkey command host'
        turnkey_run_uat = Assert-RedPinnedFile `
            -Path $AllowedTurnkeyRunUatPath `
            -ExpectedSha256 $ExpectedTurnkeyRunUatSha256 `
            -Label 'UE5.8 RunUAT script'
        validate_platforms_build = Assert-RedPinnedFile `
            -Path $AllowedValidatePlatformsBuildPath `
            -ExpectedSha256 $ExpectedValidatePlatformsBuildSha256 `
            -Label 'UE5.8 ValidatePlatforms Build script'
        turnkey_get_dotnet = Assert-RedPinnedFile `
            -Path $AllowedTurnkeyGetDotNetPath `
            -ExpectedSha256 $ExpectedTurnkeyGetDotNetSha256 `
            -Label 'UE5.8 RunUAT bundled-dotnet selector'
        turnkey_installed_build_marker = Assert-RedPinnedFile `
            -Path $AllowedTurnkeyInstalledBuildMarkerPath `
            -ExpectedSha256 $ExpectedTurnkeyInstalledBuildMarkerSha256 `
            -Label 'UE5.8 installed-build marker'
        turnkey_automation_tool = Assert-RedPinnedFile `
            -Path $AllowedTurnkeyAutomationToolPath `
            -ExpectedSha256 $ExpectedTurnkeyAutomationToolSha256 `
            -Label 'UE5.8 AutomationTool payload'
        turnkey_automation_script = Assert-RedPinnedFile `
            -Path $AllowedTurnkeyAutomationScriptPath `
            -ExpectedSha256 $ExpectedTurnkeyAutomationScriptSha256 `
            -Label 'UE5.8 Turnkey VerifySdk implementation'
        turnkey_unreal_build_tool = Assert-RedPinnedFile `
            -Path $AllowedTurnkeyUnrealBuildToolPath `
            -ExpectedSha256 $ExpectedTurnkeyUnrealBuildToolSha256 `
            -Label 'UE5.8 Turnkey SDK-query implementation'
        validate_platforms_unreal_build_tool = Assert-RedPinnedFile `
            -Path $AllowedValidatePlatformsUnrealBuildToolPath `
            -ExpectedSha256 $ExpectedValidatePlatformsUnrealBuildToolSha256 `
            -Label 'UE5.8 ValidatePlatforms UnrealBuildTool payload'
        validate_platforms_unreal_build_tool_tree = Assert-RedPinnedTreeManifest `
            -Root $AllowedValidatePlatformsUnrealBuildToolRoot `
            -ExpectedSha256 (
                $ExpectedValidatePlatformsUnrealBuildToolTreeManifestSha256
            ) `
            -ExpectedFileCount $ExpectedValidatePlatformsUnrealBuildToolTreeFileCount `
            -ExpectedBytes $ExpectedValidatePlatformsUnrealBuildToolTreeBytes `
            -Label 'UE5.8 ValidatePlatforms UnrealBuildTool runtime tree'
        turnkey_automation_tree = Assert-RedPinnedTreeManifest `
            -Root $AllowedTurnkeyAutomationRoot `
            -ExpectedSha256 $ExpectedTurnkeyAutomationTreeManifestSha256 `
            -ExpectedFileCount $ExpectedTurnkeyAutomationTreeFileCount `
            -ExpectedBytes $ExpectedTurnkeyAutomationTreeBytes `
            -Label 'UE5.8 installed AutomationTool runtime tree'
        turnkey_bundled_dotnet_tree = Assert-RedPinnedTreeManifest `
            -Root $AllowedTurnkeyDotNetRoot `
            -ExpectedSha256 $ExpectedTurnkeyDotNetTreeManifestSha256 `
            -ExpectedFileCount $ExpectedTurnkeyDotNetTreeFileCount `
            -ExpectedBytes $ExpectedTurnkeyDotNetTreeBytes `
            -Label 'UE5.8 bundled .NET runtime tree'
        project = Assert-RedPinnedFile `
            -Path $ProjectPath `
            -ExpectedSha256 $ExpectedProjectSha256 `
            -Label 'exact scratch project'
        pre_snap_map = Assert-RedPinnedFile `
            -Path $MapFile `
            -ExpectedSha256 $ExpectedMapSha256 `
            -Label 'exact pre-snap staging map'
        validation_script = Assert-RedPinnedFile `
            -Path $ValidationScript `
            -ExpectedSha256 $ExpectedValidationScriptSha256 `
            -Label 'exact live validation script'
        authoring_audit = Assert-RedPinnedFile `
            -Path $StageAuditPath `
            -ExpectedSha256 $ExpectedStageAuditSha256 `
            -Label 'exact authoring audit'
    }
    $monitorEvidence['pinned_inputs'] = $pinnedInputs
    $monitorEvidence['turnkey_post_variables_absence_checks'] = @(
        Assert-RedPathAbsent `
            -Path $TurnkeyPostVariablesPath `
            -Label 'stale Turnkey environment replay file'
    )
    $monitorEvidence['validate_platforms_build_ubt_absence_checks'] = @(
        Assert-RedPathAbsent `
            -Path $ValidatePlatformsBuildUbtPath `
            -Label 'UE5.8 BuildUBT mutation path'
    )

    $initialBlockers = @(Get-RedPreflightBlockers)
    $monitorEvidence['initial_blockers'] = $initialBlockers
    if ($initialBlockers.Count -ne 0) {
        throw (
            'Refusing to overlap an existing Unreal editor/cmd/build process: ' +
            (($initialBlockers | ForEach-Object { "$($_.name):$($_.pid)" }) -join ', ')
        )
    }

    for ($sampleIndex = 1; $sampleIndex -le $PreflightSampleCount; $sampleIndex++) {
        $sampleBlockers = @(Get-RedPreflightBlockers)
        $memory = Get-RedMemorySnapshot
        $sample = [ordered]@{
            index = $sampleIndex
            memory = $memory
            blockers = $sampleBlockers
            passed = (
                [double]$memory.free_physical_gib -ge $MinimumFreePhysicalGiB -and
                [double]$memory.free_commit_gib -ge $MinimumFreeCommitGiB -and
                $sampleBlockers.Count -eq 0
            )
        }
        $preflightSamples += $sample
        Write-Host ((
            'M07 preflight {0}/6: freePhysical={1:N3} GiB ' +
            'freeCommit={2:N3} GiB blockers={3}'
        ) -f
            $sampleIndex,
            [double]$memory.free_physical_gib,
            [double]$memory.free_commit_gib,
            $sampleBlockers.Count
        )
        if (-not $sample.passed) {
            throw "Sustained resource/process preflight failed at sample $sampleIndex."
        }
        if ($sampleIndex -lt $PreflightSampleCount) {
            Start-Sleep -Seconds $PreflightIntervalSeconds
        }
    }
    $monitorEvidence['preflight_samples'] = $preflightSamples

    $postSampleBlockers = @(Get-RedPreflightBlockers)
    if ($postSampleBlockers.Count -ne 0) {
        throw (
            'A blocking Unreal/build process appeared after preflight sampling: ' +
            (($postSampleBlockers | ForEach-Object { "$($_.name):$($_.pid)" }) -join ', ')
        )
    }
    $monitorEvidence['turnkey_post_variables_absence_checks'] += @(
        Assert-RedPathAbsent `
            -Path $TurnkeyPostVariablesPath `
            -Label 'stale Turnkey environment replay file after preflight sampling'
    )
    $monitorEvidence['validate_platforms_build_ubt_absence_checks'] += @(
        Assert-RedPathAbsent `
            -Path $ValidatePlatformsBuildUbtPath `
            -Label 'UE5.8 BuildUBT mutation path after preflight sampling'
    )
    $baselineZen = @(Get-RedZenProcesses)
    $baselineZenPids = @($baselineZen | ForEach-Object { [int]$_.pid })
    $monitorEvidence['baseline_zen_processes'] = $baselineZen
    $baselineTraceServers = @(Get-RedTraceServerProcesses)
    $baselineTraceServerPids = @(
        $baselineTraceServers | ForEach-Object { [int]$_.pid }
    )
    $monitorEvidence['baseline_trace_server_processes'] = $baselineTraceServers

    $localDdcReuseRecord = Get-RedReusableLocalDdcRecord `
        -Path $localDdcDirectory `
        -ExpectedPath $ReusableLocalDdcPath `
        -SourceRunId $ReusableLocalDdcSourceRunId
    $monitorEvidence['local_ddc_reuse'] = $localDdcReuseRecord

    if ($PreflightOnly) {
        $monitorResult = 'preflight_passed_no_launch'
        $monitorEvidence['result'] = $monitorResult
        return
    }

    $arguments = @(
        $ProjectPath
        $MapPackage
        '-D3D12'
        '-sm6'
        '-windowed'
        '-ResX=1920'
        '-ResY=1080'
        '-ForceRes'
        '-NoSplash'
        '-NoSound'
        '-NoSourceControl'
        '-NoLiveCoding'
        '-NoEpicPortal'
        '-NoSteam'
        '-NoAutoMatch'
        '-NoZenAutoLaunch'
        '-notraceserver'
        '-NoMessaging'
        '-DDC=(ProjectPak,EnginePak,Local)'
        "-LocalDataCachePath=$localDdcDirectory"
        $DisablePluginsArgument
        "-ExecutePythonScript=$ValidationScript"
        "-AbsLog=$unrealLogPath"
    )
    Assert-RedLaunchArguments -Arguments $arguments
    $argumentLine = $arguments -join ' '
    $monitorEvidence['turnkey_post_variables_absence_checks'] += @(
        Assert-RedPathAbsent `
            -Path $TurnkeyPostVariablesPath `
            -Label 'stale Turnkey environment replay file immediately before launch'
    )
    $monitorEvidence['validate_platforms_build_ubt_absence_checks'] += @(
        Assert-RedPathAbsent `
            -Path $ValidatePlatformsBuildUbtPath `
            -Label 'UE5.8 BuildUBT mutation path immediately before launch'
    )
    $launcherImmediatePrelaunch = Get-RedFileRecord -Path $PSCommandPath
    if (
        [int64]$launcherImmediatePrelaunch.bytes -ne [int64]$launcherRecord.bytes -or
        [string]$launcherImmediatePrelaunch.sha256 -cne [string]$launcherRecord.sha256 -or
        [string]$launcherImmediatePrelaunch.last_write_utc -cne
            [string]$launcherRecord.last_write_utc
    ) {
        throw 'Guard launcher changed between startup attestation and editor launch.'
    }
    $monitorEvidence['launcher_immediate_prelaunch'] = $launcherImmediatePrelaunch

    $previousEnvironment = Set-RedChildEnvironment -Values $RequiredEnvironment
    try {
        $editorProcess = Start-Process `
            -FilePath $EditorPath `
            -ArgumentList $argumentLine `
            -WorkingDirectory (Split-Path -Parent $ProjectPath) `
            -PassThru
    } finally {
        Restore-RedChildEnvironment -Previous $previousEnvironment
    }
    if ($null -eq $editorProcess) {
        throw 'Start-Process returned no process object.'
    }
    $null = $editorProcess.Handle
    $identityDeadlineUtc = [datetime]::UtcNow.AddSeconds(30)
    $lastIdentityCandidate = $null
    do {
        Start-Sleep -Milliseconds 100
        $editorProcess.Refresh()
        if ($editorProcess.HasExited) {
            throw "Returned UnrealEditor PID $($editorProcess.Id) exited during identity capture."
        }
        $lastIdentityCandidate = Get-RedProcessIdentity -ProcessId $editorProcess.Id
        if (
            $null -ne $lastIdentityCandidate -and
            -not [string]::IsNullOrWhiteSpace([string]$lastIdentityCandidate.name) -and
            -not [string]::IsNullOrWhiteSpace([string]$lastIdentityCandidate.executable_path) -and
            -not [string]::IsNullOrWhiteSpace([string]$lastIdentityCandidate.creation_utc) -and
            -not [string]::IsNullOrWhiteSpace([string]$lastIdentityCandidate.command_line) -and
            $lastIdentityCandidate.command_line.IndexOf(
                $ProjectPath,
                [System.StringComparison]::Ordinal
            ) -ge 0 -and
            $lastIdentityCandidate.command_line.IndexOf(
                $MapPackage,
                [System.StringComparison]::Ordinal
            ) -ge 0 -and
            $lastIdentityCandidate.command_line.IndexOf(
                "-AbsLog=$unrealLogPath",
                [System.StringComparison]::Ordinal
            ) -ge 0
        ) {
            $launchedIdentity = $lastIdentityCandidate
        }
    } while ($null -eq $launchedIdentity -and [datetime]::UtcNow -lt $identityDeadlineUtc)
    if ($null -eq $launchedIdentity) {
        $monitorEvidence['last_incomplete_editor_identity_candidate'] = $lastIdentityCandidate
        $guardAbortReason = (
            "unable to retain a complete, command-line-bound identity for returned " +
            "UnrealEditor PID $($editorProcess.Id) within 30 seconds"
        )
        throw $guardAbortReason
    }

    if (
        [System.IO.Path]::GetFileNameWithoutExtension($launchedIdentity.name) -cne
        'UnrealEditor'
    ) {
        $guardAbortReason = (
            "returned PID is not exact UnrealEditor.exe: $($launchedIdentity.name)"
        )
        $stopResult = Stop-RedExactLaunchedEditor `
            -ExpectedIdentity $launchedIdentity `
            -ProcessObject $editorProcess `
            -Reason $guardAbortReason
        throw $guardAbortReason
    }
    if (-not (Test-RedPathEqual -Left $launchedIdentity.executable_path -Right $EditorPath)) {
        $guardAbortReason = (
            'Returned UnrealEditor executable path drifted: ' +
            "$($launchedIdentity.executable_path)"
        )
        $stopResult = Stop-RedExactLaunchedEditor `
            -ExpectedIdentity $launchedIdentity `
            -ProcessObject $editorProcess `
            -Reason $guardAbortReason
        throw $guardAbortReason
    }
    foreach ($token in $arguments) {
        if (
            $launchedIdentity.command_line.IndexOf(
                $token,
                [System.StringComparison]::Ordinal
            ) -lt 0
        ) {
            $guardAbortReason = (
                "returned UnrealEditor command line is missing exact token: $token"
            )
            $stopResult = Stop-RedExactLaunchedEditor `
                -ExpectedIdentity $launchedIdentity `
                -ProcessObject $editorProcess `
                -Reason $guardAbortReason
            throw $guardAbortReason
        }
    }
    foreach ($forbidden in @(
        '-uaip-mcp-enable',
        '-uaip-http-port',
        '-ModelContextProtocolStartServer',
        '-EnablePlugins',
        '-EnableAllPlugins'
    )) {
        if (
            $launchedIdentity.command_line.IndexOf(
                $forbidden,
                [System.StringComparison]::OrdinalIgnoreCase
            ) -ge 0
        ) {
            $guardAbortReason = (
                "returned UnrealEditor command line contains forbidden flag: $forbidden"
            )
            $stopResult = Stop-RedExactLaunchedEditor `
                -ExpectedIdentity $launchedIdentity `
                -ProcessObject $editorProcess `
                -Reason $guardAbortReason
            throw $guardAbortReason
        }
    }

    $postLaunchPrimarySensor = Invoke-RedRequiredMonitorSensor `
        -Name 'postlaunch_primary_process_enumeration' `
        -Operation {
            @(
                Get-RedAllProcesses |
                    Where-Object {
                        $PostLaunchPrimaryNames -contains
                            [System.IO.Path]::GetFileNameWithoutExtension(
                                [string]$_.Name
                            )
                    } |
                    ForEach-Object { ConvertTo-RedProcessRecord -Process $_ }
            )
        }
    $monitorEvidence['postlaunch_primary_process_sensor'] = (
        Get-RedMonitorSensorEvidence -SensorResult $postLaunchPrimarySensor
    )
    if (-not [bool]$postLaunchPrimarySensor.success) {
        $postLaunchFailure = Get-RedMonitorSensorFailureRecord `
            -SensorResult $postLaunchPrimarySensor
        $monitorSensorFailures += $postLaunchFailure
        $guardAbortReason = Get-RedMonitorSensorGuardReason `
            -SensorFailure $postLaunchFailure
        throw $guardAbortReason
    }
    $postLaunchPrimaries = @($postLaunchPrimarySensor.value)
    if (
        $postLaunchPrimaries.Count -ne 1 -or
        [int]$postLaunchPrimaries[0].pid -ne [int]$editorProcess.Id
    ) {
        $guardAbortReason = (
            'postlaunch process set was not only the exact returned UnrealEditor PID'
        )
        $stopResult = Stop-RedExactLaunchedEditor `
            -ExpectedIdentity $launchedIdentity `
            -ProcessObject $editorProcess `
            -Reason $guardAbortReason
        throw $guardAbortReason
    }

    $launchEvidence = [ordered]@{
        schema_version = 1
        module = 'M07'
        operation = 'guarded_tropical_planetary_biome_editor_launch_v2'
        launcher = $launcherRecord
        launched_utc = [datetime]::UtcNow.ToString('o')
        run_id = $runId
        run_directory = $runDirectory
        editor_identity = $launchedIdentity
        editor_file = $pinnedInputs.editor
        project_file = $pinnedInputs.project
        map_package = $MapPackage
        validation_script = $pinnedInputs.validation_script
        arguments = $arguments
        argument_line = $argumentLine
        disabled_plugins = $RequiredDisabledPlugins
        required_environment = $RequiredEnvironment
        local_ddc_directory = $localDdcDirectory
        local_ddc_reuse = $localDdcReuseRecord
        local_ddc_reused_existing = $true
        local_ddc_created_by_current_run = $false
        filesystem_local_ddc = $true
        no_zen_auto_launch = $true
        no_messaging = $true
        provider_enable_flags_present = $false
        visible_start_process = $true
        exact_returned_pid_only = $true
        listeners_before = @()
        preflight_samples = $preflightSamples
        baseline_zen_processes = $baselineZen
        baseline_trace_server_processes = $baselineTraceServers
        external_trace_server_launch_disabled = $true
        allowed_core_trace_listener_contract = (
            $monitorEvidence.allowed_core_trace_listener_contract
        )
        allowed_editor_startup_udp_listener_contract = (
            $monitorEvidence.allowed_editor_startup_udp_listener_contract
        )
        allowed_scratch_turnkey_verify_sdk_contract = (
            $monitorEvidence.allowed_scratch_turnkey_verify_sdk_contract
        )
    }
    Write-RedNoClobberJson -Path $launchEvidencePath -Payload $launchEvidence
    $launchEvidenceWritten = $true
    Write-Host "Started exact guarded UnrealEditor PID $($editorProcess.Id)."

    $deadlineUtc = [datetime]::UtcNow.AddSeconds($MaximumMonitorSeconds)
    while ($true) {
        Start-Sleep -Seconds $MonitorPollSeconds

        $editorStatusSensor = Invoke-RedRequiredMonitorSensor `
            -Name 'editor_process_status' `
            -Operation {
                $editorProcess.Refresh()
                [ordered]@{
                    has_exited = [bool]$editorProcess.HasExited
                }
            }
        if (
            [bool]$editorStatusSensor.success -and
            [bool]$editorStatusSensor.value.has_exited
        ) {
            $monitorSamples += [ordered]@{
                captured_utc = [datetime]::UtcNow.ToString('o')
                sensor_results = @(
                    Get-RedMonitorSensorEvidence `
                        -SensorResult $editorStatusSensor
                )
                sensor_failures = @()
                editor_exited = $true
            }
            $monitorResult = 'editor_exited_before_live_audit'
            throw (
                "Exact UnrealEditor PID $($editorProcess.Id) exited before the live audit."
            )
        }

        $identitySensor = Invoke-RedRequiredMonitorSensor `
            -Name 'exact_editor_identity' `
            -Operation {
                $identity = Get-RedProcessIdentity -ProcessId $editorProcess.Id
                [ordered]@{
                    actual_identity = $identity
                    identity_match = (
                        $null -ne $identity -and
                        (
                            Test-RedExactIdentity `
                                -Expected $launchedIdentity `
                                -Actual $identity
                        )
                    )
                }
            }
        $memorySensor = Invoke-RedRequiredMonitorSensor `
            -Name 'memory' `
            -Operation { Get-RedMemorySnapshot }
        $overlapSensor = Invoke-RedRequiredMonitorSensor `
            -Name 'overlap_process_enumeration' `
            -Operation {
                $allProcesses = @(Get-RedAllProcesses)
                Get-RedPostLaunchProcessClassification `
                    -ExpectedEditorIdentity $launchedIdentity `
                    -Processes $allProcesses
            }
        $zenSensor = Invoke-RedRequiredMonitorSensor `
            -Name 'zen_process_enumeration' `
            -Operation {
                $current = @(Get-RedZenProcesses)
                [ordered]@{
                    current = $current
                    new = @(
                        $current |
                            Where-Object {
                                $baselineZenPids -notcontains [int]$_.pid
                            }
                    )
                }
            }
        $traceServerSensor = Invoke-RedRequiredMonitorSensor `
            -Name 'unreal_trace_server_enumeration' `
            -Operation {
                $current = @(Get-RedTraceServerProcesses)
                [ordered]@{
                    current = $current
                    new = @(
                        $current |
                            Where-Object {
                                $baselineTraceServerPids -notcontains [int]$_.pid
                            }
                    )
                }
            }
        $listenerSensor = Invoke-RedRequiredMonitorSensor `
            -Name 'editor_owned_listener_enumeration' `
            -Operation {
                $owned = @(
                    Get-RedEditorOwnedListeners -ProcessId $editorProcess.Id
                )
                [ordered]@{
                    owned = $owned
                    allowed_core_trace = @(
                        $owned |
                            Where-Object {
                                Test-RedAllowedCoreTraceListener `
                                    -Listener $_ `
                                    -ExpectedPid $editorProcess.Id
                            }
                    )
                    allowed_editor_startup_udp = @(
                        $owned |
                            Where-Object {
                                Test-RedAllowedEditorStartupUdpListener `
                                    -Listener $_ `
                                    -ExpectedPid $editorProcess.Id
                            }
                    )
                    unexpected = @(
                        $owned |
                            Where-Object {
                                -not (
                                    Test-RedAllowedCoreTraceListener `
                                        -Listener $_ `
                                        -ExpectedPid $editorProcess.Id
                                ) -and
                                -not (
                                    Test-RedAllowedEditorStartupUdpListener `
                                        -Listener $_ `
                                        -ExpectedPid $editorProcess.Id
                                )
                            }
                    )
                }
            }
        $liveAuditPresenceSensor = Invoke-RedRequiredMonitorSensor `
            -Name 'live_audit_presence' `
            -Operation {
                Test-Path `
                    -LiteralPath $liveAuditPath `
                    -PathType Leaf `
                    -ErrorAction Stop
            }

        $requiredSensorResults = @(
            $editorStatusSensor
            $identitySensor
            $memorySensor
            $overlapSensor
            $zenSensor
            $traceServerSensor
            $listenerSensor
            $liveAuditPresenceSensor
        )
        [object[]]$sampleSensorEvidence = @()
        [object[]]$sampleSensorFailures = @()
        foreach ($sensorResult in $requiredSensorResults) {
            $sampleSensorEvidence += @(
                Get-RedMonitorSensorEvidence -SensorResult $sensorResult
            )
            if (-not [bool]$sensorResult.success) {
                $sensorFailure = Get-RedMonitorSensorFailureRecord `
                    -SensorResult $sensorResult
                $sampleSensorFailures += @($sensorFailure)
                $monitorSensorFailures += @($sensorFailure)
            }
        }
        if (
            -not $guardAbortReason -and
            $sampleSensorFailures.Count -ne 0
        ) {
            $guardAbortReason = Get-RedMonitorSensorGuardReason `
                -SensorFailure $sampleSensorFailures[0]
        }

        $actualIdentity = if ([bool]$identitySensor.success) {
            $identitySensor.value.actual_identity
        } else {
            $null
        }
        $identityMatch = (
            [bool]$identitySensor.success -and
            [bool]$identitySensor.value.identity_match
        )
        if (
            -not $guardAbortReason -and
            -not $identityMatch
        ) {
            $guardAbortReason = 'exact UnrealEditor PID identity changed during monitoring'
        }

        $memory = if ([bool]$memorySensor.success) {
            $memorySensor.value
        } else {
            $null
        }
        if (
            -not $guardAbortReason -and
            [bool]$memorySensor.success -and
            [double]$memory.free_physical_gib -lt $AbortFreePhysicalGiB
        ) {
            $guardAbortReason = (
                "free physical RAM fell below $AbortFreePhysicalGiB GiB"
            )
        }
        if (
            -not $guardAbortReason -and
            [bool]$memorySensor.success -and
            [double]$memory.free_commit_gib -lt $AbortFreeCommitGiB
        ) {
            $guardAbortReason = "free commit fell below $AbortFreeCommitGiB GiB"
        }

        [object[]]$overlaps = @()
        [object[]]$allowedTurnkeyVerifySdk = @()
        if ([bool]$overlapSensor.success) {
            $overlaps = @($overlapSensor.value.overlaps)
            $allowedTurnkeyVerifySdk = @(
                $overlapSensor.value.allowed_turnkey_verify_sdk
            )
        }
        if (-not $guardAbortReason -and $overlaps.Count -ne 0) {
            $guardAbortReason = (
                'another Unreal editor/cmd/build process appeared: ' +
                (($overlaps | ForEach-Object { "$($_.name):$($_.pid)" }) -join ', ')
            )
        }
        if (
            -not $guardAbortReason -and
            $allowedTurnkeyVerifySdk.Count -gt 1
        ) {
            $guardAbortReason = (
                'more than one exact scratch Turnkey VerifySdk process appeared'
            )
        }
        $turnkeyObservationUpdate = Get-RedTurnkeyObservationUpdate `
            -Observed $allowedTurnkeyVerifySdkObserved `
            -Current $allowedTurnkeyVerifySdk
        $allowedTurnkeyVerifySdkObserved = @(
            $turnkeyObservationUpdate.observed
        )
        if (
            -not $guardAbortReason -and
            [bool]$turnkeyObservationUpdate.violation
        ) {
            $guardAbortReason = (
                'more than one distinct exact scratch Turnkey VerifySdk process ' +
                'was observed during sampled startup monitoring'
            )
        }

        [object[]]$currentZen = @()
        [object[]]$newZen = @()
        if ([bool]$zenSensor.success) {
            $currentZen = @($zenSensor.value.current)
            $newZen = @($zenSensor.value.new)
        }
        if (-not $guardAbortReason -and $newZen.Count -ne 0) {
            $guardAbortReason = (
                'a new Zen process appeared: ' +
                (($newZen | ForEach-Object { "$($_.name):$($_.pid)" }) -join ', ')
            )
        }

        [object[]]$currentTraceServers = @()
        [object[]]$newTraceServers = @()
        if ([bool]$traceServerSensor.success) {
            $currentTraceServers = @($traceServerSensor.value.current)
            $newTraceServers = @($traceServerSensor.value.new)
        }
        if (-not $guardAbortReason -and $newTraceServers.Count -ne 0) {
            $guardAbortReason = (
                'a new external UnrealTraceServer process appeared despite ' +
                '-notraceserver: ' +
                (($newTraceServers | ForEach-Object {
                    "$($_.name):$($_.pid)"
                }) -join ', ')
            )
        }

        [object[]]$ownedListeners = @()
        [object[]]$allowedCoreTraceListeners = @()
        [object[]]$allowedEditorStartupUdpListeners = @()
        [object[]]$unexpectedOwnedListeners = @()
        if ([bool]$listenerSensor.success) {
            $ownedListeners = @($listenerSensor.value.owned)
            $allowedCoreTraceListeners = @(
                $listenerSensor.value.allowed_core_trace
            )
            $allowedEditorStartupUdpListeners = @(
                $listenerSensor.value.allowed_editor_startup_udp
            )
            $unexpectedOwnedListeners = @(
                $listenerSensor.value.unexpected
            )
        }
        if (
            -not $guardAbortReason -and
            $allowedCoreTraceListeners.Count -gt 1
        ) {
            $guardAbortReason = (
                'the exact editor opened more than one TCP 1985 TraceLog ' +
                'control listener'
            )
        }
        if (
            -not $guardAbortReason -and
            $allowedEditorStartupUdpListeners.Count -gt 1
        ) {
            $guardAbortReason = (
                'the exact editor opened more than one approved UDP 11111 ' +
                'startup listener'
            )
        }
        if ($ownedListeners.Count -ne 0) {
            foreach ($listener in $ownedListeners) {
                $key = (
                    "$($listener.protocol)|$($listener.local_address)|" +
                    "$($listener.local_port)|$($listener.owning_pid)"
                )
                if (
                    @(
                        $editorOwnedListenersObserved |
                            Where-Object { $_.key -ceq $key }
                    ).Count -eq 0
                ) {
                    $editorOwnedListenersObserved += [ordered]@{
                        key = $key
                        protocol = $listener.protocol
                        local_address = $listener.local_address
                        local_port = $listener.local_port
                        owning_pid = $listener.owning_pid
                    }
                }
            }
        }
        foreach ($listener in $allowedCoreTraceListeners) {
            $key = (
                "$($listener.protocol)|$($listener.local_address)|" +
                "$($listener.local_port)|$($listener.owning_pid)"
            )
            if (
                @(
                    $allowedCoreTraceListenersObserved |
                        Where-Object { $_.key -ceq $key }
                ).Count -eq 0
            ) {
                $allowedCoreTraceListenersObserved += [ordered]@{
                    key = $key
                    protocol = $listener.protocol
                    local_address = $listener.local_address
                    local_port = $listener.local_port
                    owning_pid = $listener.owning_pid
                    classification = 'UE TraceLog control, not provider activity'
                }
            }
        }
        foreach ($listener in $allowedEditorStartupUdpListeners) {
            $key = (
                "$($listener.protocol)|$($listener.local_address)|" +
                "$($listener.local_port)|$($listener.owning_pid)"
            )
            if (
                @(
                    $allowedEditorStartupUdpListenersObserved |
                        Where-Object { $_.key -ceq $key }
                ).Count -eq 0
            ) {
                $allowedEditorStartupUdpListenersObserved += [ordered]@{
                    key = $key
                    protocol = $listener.protocol
                    local_address = $listener.local_address
                    local_port = $listener.local_port
                    owning_pid = $listener.owning_pid
                    classification = (
                        'approved normal editor startup listener; ' +
                        'not AI, MCP, or provider activity'
                    )
                }
            }
        }
        foreach ($listener in $unexpectedOwnedListeners) {
            $key = (
                "$($listener.protocol)|$($listener.local_address)|" +
                "$($listener.local_port)|$($listener.owning_pid)"
            )
            if (
                @(
                    $unexpectedEditorOwnedListenersObserved |
                        Where-Object { $_.key -ceq $key }
                ).Count -eq 0
            ) {
                $unexpectedEditorOwnedListenersObserved += [ordered]@{
                    key = $key
                    protocol = $listener.protocol
                    local_address = $listener.local_address
                    local_port = $listener.local_port
                    owning_pid = $listener.owning_pid
                }
            }
        }
        if (-not $guardAbortReason -and $unexpectedOwnedListeners.Count -ne 0) {
            $guardAbortReason = (
                'the exact editor opened an unexpected TCP/UDP listener: ' +
                (($unexpectedOwnedListeners | ForEach-Object {
                    "$($_.protocol):$($_.local_address):$($_.local_port)"
                }) -join ', ')
            )
        }

        $liveAuditExists = (
            [bool]$liveAuditPresenceSensor.success -and
            [bool]$liveAuditPresenceSensor.value
        )
        $sample = [ordered]@{
            captured_utc = [datetime]::UtcNow.ToString('o')
            sensor_results = $sampleSensorEvidence
            sensor_failures = $sampleSensorFailures
            memory = $memory
            identity_match = $identityMatch
            overlap_processes = $overlaps
            allowed_turnkey_verify_sdk_processes = $allowedTurnkeyVerifySdk
            current_zen_processes = $currentZen
            new_zen_processes = $newZen
            current_trace_server_processes = $currentTraceServers
            new_trace_server_processes = $newTraceServers
            editor_owned_listeners = $ownedListeners
            allowed_core_trace_listeners = $allowedCoreTraceListeners
            allowed_editor_startup_udp_listeners = (
                $allowedEditorStartupUdpListeners
            )
            unexpected_editor_owned_listeners = $unexpectedOwnedListeners
            live_audit_exists = $liveAuditExists
        }
        $monitorSamples += $sample
        $freePhysicalDisplay = if ([bool]$memorySensor.success) {
            '{0:N3}' -f [double]$memory.free_physical_gib
        } else {
            'SENSOR_FAILED'
        }
        $freeCommitDisplay = if ([bool]$memorySensor.success) {
            '{0:N3}' -f [double]$memory.free_commit_gib
        } else {
            'SENSOR_FAILED'
        }
        Write-Host ((
            'M07 monitor: PID={0} freePhysical={1} GiB freeCommit={2} GiB ' +
            'overlaps={3} newZen={4} listeners={5} unexpectedListeners={6} ' +
            'newTraceServers={7} audit={8} sensorFailures={9}'
        ) -f
            $editorProcess.Id,
            $freePhysicalDisplay,
            $freeCommitDisplay,
            $overlaps.Count,
            $newZen.Count,
            $ownedListeners.Count,
            $unexpectedOwnedListeners.Count,
            $newTraceServers.Count,
            $sample.live_audit_exists,
            $sampleSensorFailures.Count
        )

        if ($guardAbortReason) {
            $stopResult = Stop-RedExactLaunchedEditor `
                -ExpectedIdentity $launchedIdentity `
                -ProcessObject $editorProcess `
                -Reason $guardAbortReason
            $monitorResult = 'guard_aborted_exact_editor_only'
            throw "Guarded live validation aborted: $guardAbortReason"
        }

        if ($liveAuditExists) {
            try {
                $auditText = Get-Content -LiteralPath $liveAuditPath -Raw -ErrorAction Stop
                $auditPayload = $auditText | ConvertFrom-Json -ErrorAction Stop
                $auditGate = Assert-RedSuccessfulLiveAudit -Payload $auditPayload
                $auditRecord = Get-RedFileRecord -Path $liveAuditPath
                $monitorEvidence['live_audit'] = [ordered]@{
                    file = $auditRecord
                    result = [string]$auditPayload.result
                    evidence_class = [string]$auditPayload.evidence_class
                    exact_success_claim_gate = $auditGate
                }
                $monitorResult = 'live_audit_observed_editor_left_open'
                break
            } catch {
                $auditReadError = $_
                $auditMetadataSensor = Invoke-RedRequiredMonitorSensor `
                    -Name 'live_audit_file_metadata' `
                    -Operation {
                        Get-Item `
                            -LiteralPath $liveAuditPath `
                            -Force `
                            -ErrorAction Stop
                    }
                if (-not [bool]$auditMetadataSensor.success) {
                    $auditMetadataFailure = Get-RedMonitorSensorFailureRecord `
                        -SensorResult $auditMetadataSensor
                    $monitorSensorFailures += @($auditMetadataFailure)
                    $guardAbortReason = Get-RedMonitorSensorGuardReason `
                        -SensorFailure $auditMetadataFailure
                    throw "Guarded live validation aborted: $guardAbortReason"
                }
                $ageSeconds = (
                    [datetime]::UtcNow -
                    $auditMetadataSensor.value.LastWriteTimeUtc
                ).TotalSeconds
                if ($ageSeconds -ge 10.0) {
                    $auditReadFailure = [ordered]@{
                        sensor_name = 'live_audit_read'
                        captured_utc = [datetime]::UtcNow.ToString('o')
                        error_type = $auditReadError.Exception.GetType().FullName
                        error_message = $auditReadError.Exception.Message
                    }
                    $monitorSensorFailures += @($auditReadFailure)
                    $guardAbortReason = Get-RedMonitorSensorGuardReason `
                        -SensorFailure $auditReadFailure
                    throw "Guarded live validation aborted: $guardAbortReason"
                }
            }
        }

        if ([datetime]::UtcNow -ge $deadlineUtc) {
            $monitorResult = 'bounded_timeout_exact_editor_stop_required'
            throw (
                "Live audit was not produced within $MaximumMonitorSeconds seconds; " +
                'the guard will stop only the exact launched editor handle.'
            )
        }
    }
} catch {
    $capturedFailure = $_
    if ($null -ne $editorProcess) {
        if (-not $guardAbortReason) {
            $guardAbortReason = (
                'post-launch guarded validation failure: ' +
                $_.Exception.Message
            )
        }
        $stopProven = (
            $null -ne $stopResult -and
            [bool]$stopResult.proves_exact_editor_stopped
        )
        if (-not $stopProven) {
            try {
                $stopResult = Stop-RedLaunchedEditorForGuardFailure `
                    -ProcessObject $editorProcess `
                    -ExpectedIdentity $launchedIdentity `
                    -Reason $guardAbortReason
            } catch {
                $stopResult = [ordered]@{
                    requested = $true
                    stopped = $false
                    proves_exact_editor_stopped = $false
                    stop_error = $_.Exception.Message
                    reason = $guardAbortReason
                }
            }
        }
        $monitorResult = if (
            $null -ne $stopResult -and
            [bool]$stopResult.proves_exact_editor_stopped
        ) {
            'guard_aborted_exact_editor_only'
        } else {
            'guard_abort_stop_not_proven'
        }
    } elseif ($monitorResult -eq 'initializing') {
        $monitorResult = 'preflight_or_launch_failed_no_editor_started'
    }
    $monitorEvidence['failure'] = [ordered]@{
        type = $_.Exception.GetType().FullName
        message = $_.Exception.Message
        guard_abort_reason = $guardAbortReason
    }
} finally {
    if (
        $guardAbortReason -and
        $null -ne $editorProcess -and
        (
            $null -eq $stopResult -or
            -not [bool]$stopResult.proves_exact_editor_stopped
        )
    ) {
        try {
            $retryStop = Stop-RedLaunchedEditorForGuardFailure `
                -ProcessObject $editorProcess `
                -ExpectedIdentity $launchedIdentity `
                -Reason $guardAbortReason
            $stopResult = $retryStop
        } catch {
            $stopResult = [ordered]@{
                requested = $true
                stopped = $false
                proves_exact_editor_stopped = $false
                stop_error = $_.Exception.Message
                reason = $guardAbortReason
            }
        }
        $monitorResult = if (
            $null -ne $stopResult -and
            [bool]$stopResult.proves_exact_editor_stopped
        ) {
            'guard_aborted_exact_editor_only'
        } else {
            'guard_abort_stop_not_proven'
        }
    }
    $monitorEvidence['result'] = $monitorResult
    $monitorEvidence['completed_utc'] = [datetime]::UtcNow.ToString('o')
    $monitorEvidence['preflight_samples'] = $preflightSamples
    $monitorEvidence['monitor_samples'] = $monitorSamples
    $monitorEvidence['monitor_sensor_failures'] = $monitorSensorFailures
    $monitorEvidence['launch_evidence_path'] = if ($launchEvidenceWritten) {
        $launchEvidencePath
    } else {
        $null
    }
    $monitorEvidence['editor_identity'] = $launchedIdentity
    $monitorEvidence['stop_result'] = $stopResult
    $monitorEvidence['listeners_after'] = $editorOwnedListenersObserved
    $monitorEvidence['allowed_core_trace_listeners_observed'] = (
        $allowedCoreTraceListenersObserved
    )
    $monitorEvidence['allowed_editor_startup_udp_listeners_observed'] = (
        $allowedEditorStartupUdpListenersObserved
    )
    $monitorEvidence['allowed_turnkey_verify_sdk_processes_observed'] = (
        $allowedTurnkeyVerifySdkObserved
    )
    $monitorEvidence['unexpected_editor_owned_listeners_observed'] = (
        $unexpectedEditorOwnedListenersObserved
    )
    $monitorEvidence['core_trace_listener_classified_as_provider_activity'] = $false
    $monitorEvidence['editor_startup_udp_listener_classified_as_provider_activity'] = (
        $false
    )
    $monitorEvidence['editor_intentionally_left_open'] = (
        $null -ne $editorProcess -and
        $null -eq $stopResult -and
        -not $editorProcess.HasExited
    )
    if (-not (Test-Path -LiteralPath $monitorEvidencePath)) {
        Write-RedNoClobberJson -Path $monitorEvidencePath -Payload $monitorEvidence
        $monitorEvidenceWritten = $true
    }
    Write-Host "RUN_DIR=$runDirectory"
    Write-Host (
        'UNREAL_PID=' +
        $(if ($null -eq $editorProcess) { 'NOT_STARTED' } else { [string]$editorProcess.Id })
    )
    Write-Host "MONITOR_EVIDENCE=$monitorEvidencePath"
}

if ($capturedFailure) {
    throw $capturedFailure
}
