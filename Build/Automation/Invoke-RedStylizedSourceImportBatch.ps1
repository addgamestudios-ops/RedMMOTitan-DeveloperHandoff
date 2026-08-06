[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateNotNullOrEmpty()]
    [string]$PlanPath,

    [Parameter(Mandatory = $true)]
    [ValidateNotNullOrEmpty()]
    [string]$Categories,

    [ValidateRange(0, 1000000)]
    [int]$Start = 0,

    [ValidateRange(1, 64)]
    [int]$Limit = 64,

    [Parameter(Mandatory = $true)]
    [ValidateNotNullOrEmpty()]
    [string]$OutputDirectory
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$ProjectRoot = "D:\RedMMOTitan"
$ProjectFile = Join-Path $ProjectRoot "Titan_AssetImport.uproject"
$UnrealEditorCmd = "D:\UE_5.8\Engine\Binaries\Win64\UnrealEditor-Cmd.exe"
$ImportScript = Join-Path $ProjectRoot "Tools\import_redmmo_stylized_source_library.py"
$SourceRoot = "D:\styled assets"
$DestinationAssetRoot = "/Game/RedMMO/ArtLibrary/StylizedSource"
$DestinationDiskRoot = Join-Path $ProjectRoot "Content\RedMMO\ArtLibrary\StylizedSource"
$AllowedOutputRoot = "D:\RedMMOTitanWindowsData\AssetImports\StylizedSource"
$ExpectedPlanSchema = "redmmotitan.stylized_source_import.v2"
$ExpectedApprovalStatus = "approved_by_explicit_user_conversion_instruction"
$ExpectedApprovalBasis = "The user explicitly instructed conversion of the supplied D:/styled assets source tree on 2026-07-24."
$ExpectedSourceProvenance = "user_supplied_local_source_tree"
$MinimumFreePhysicalGiB = 6.0
$MinimumFreeCommitGiB = 12.0
$MinimumFreeDDriveGiB = 64.0
$MaximumSelectedSourceBytes = 512MB

$ProtectedFiles = @(
    "Content\RedMMO\Maps\RedPlanetGen.umap",
    "Content\RedMMO\Maps\RedPlanetGen_50km_Test.umap",
    "Content\RedMMO\Maps\RedPlanetGen_50km_FusedPrototype.umap",
    "Content\RedMMO\Environment\DA_RED_Planet50Km_FusedHeightfield.uasset"
)

function Test-IsStrictChildPath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Candidate,
        [Parameter(Mandatory = $true)]
        [string]$Parent
    )

    $candidateFull = [System.IO.Path]::GetFullPath($Candidate)
    $parentFull = [System.IO.Path]::GetFullPath($Parent).TrimEnd(
        [System.IO.Path]::DirectorySeparatorChar,
        [System.IO.Path]::AltDirectorySeparatorChar
    )
    return $candidateFull.StartsWith(
        $parentFull + [System.IO.Path]::DirectorySeparatorChar,
        [System.StringComparison]::OrdinalIgnoreCase
    )
}

function Assert-NoReparsePoint {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,
        [Parameter(Mandatory = $true)]
        [string]$Label
    )

    $item = Get-Item -LiteralPath $Path -Force
    if (($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
        throw "$Label cannot be a reparse point: $Path"
    }
}

function Assert-JsonProperty {
    param(
        [Parameter(Mandatory = $true)]
        [object]$Object,
        [Parameter(Mandatory = $true)]
        [string]$Name
    )

    if ($Object.PSObject.Properties.Name -notcontains $Name) {
        throw "Plan is missing required property: $Name"
    }
}

function Get-FileHashes {
    param([string[]]$RelativePaths)

    $result = [ordered]@{}
    foreach ($relativePath in $RelativePaths) {
        $absolutePath = Join-Path $ProjectRoot $relativePath
        if (-not (Test-Path -LiteralPath $absolutePath -PathType Leaf)) {
            throw "Protected file is missing: $absolutePath"
        }
        Assert-NoReparsePoint -Path $absolutePath -Label "Protected file"
        $result[$relativePath] = (
            Get-FileHash -LiteralPath $absolutePath -Algorithm SHA256
        ).Hash
    }
    return $result
}

function Get-ResourceSnapshot {
    $operatingSystem = Get-CimInstance Win32_OperatingSystem
    $dDrive = Get-CimInstance Win32_LogicalDisk -Filter "DeviceID='D:'"
    if ($null -eq $dDrive) {
        throw "Cannot query free space for D:"
    }
    return [ordered]@{
        free_physical_gib = [math]::Round(
            $operatingSystem.FreePhysicalMemory / 1MB,
            3
        )
        free_commit_gib = [math]::Round(
            $operatingSystem.FreeVirtualMemory / 1MB,
            3
        )
        free_d_drive_gib = [math]::Round($dDrive.FreeSpace / 1GB, 3)
    }
}

function Get-OutsideDestinationFileCount {
    [int64]$count = 0
    $projectPrefix = [System.IO.Path]::GetFullPath(
        $ProjectRoot
    ).TrimEnd(
        [System.IO.Path]::DirectorySeparatorChar,
        [System.IO.Path]::AltDirectorySeparatorChar
    ) + [System.IO.Path]::DirectorySeparatorChar
    $roots = @(
        (Join-Path $ProjectRoot "Content"),
        (Join-Path $ProjectRoot "Plugins")
    )
    $destinationPrefix = [System.IO.Path]::GetFullPath(
        $DestinationDiskRoot
    ).TrimEnd(
        [System.IO.Path]::DirectorySeparatorChar,
        [System.IO.Path]::AltDirectorySeparatorChar
    ) + [System.IO.Path]::DirectorySeparatorChar

    foreach ($root in $roots) {
        if (-not (Test-Path -LiteralPath $root -PathType Container)) {
            continue
        }
        Assert-NoReparsePoint -Path $root -Label "Protected workspace root"
        Get-ChildItem -LiteralPath $root -Recurse -Force | ForEach-Object {
            $file = $_
            if ($file.PSIsContainer) {
                return
            }
            if (
                ($file.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne
                0
            ) {
                throw "Protected workspace contains a reparse point: $($file.FullName)"
            }
            $fullPath = [System.IO.Path]::GetFullPath($file.FullName)
            if ($fullPath.StartsWith(
                $destinationPrefix,
                [System.StringComparison]::OrdinalIgnoreCase
            )) {
                return
            }
            if (-not $fullPath.StartsWith(
                $projectPrefix,
                [System.StringComparison]::OrdinalIgnoreCase
            )) {
                throw "Protected workspace file escaped the project root: $fullPath"
            }
            $count += 1
        }
    }
    return $count
}

function Get-OutsideDestinationRecentChanges {
    param(
        [Parameter(Mandatory = $true)]
        [datetime]$SinceUtc
    )

    $projectPrefix = [System.IO.Path]::GetFullPath(
        $ProjectRoot
    ).TrimEnd(
        [System.IO.Path]::DirectorySeparatorChar,
        [System.IO.Path]::AltDirectorySeparatorChar
    ) + [System.IO.Path]::DirectorySeparatorChar
    $destinationPrefix = [System.IO.Path]::GetFullPath(
        $DestinationDiskRoot
    ).TrimEnd(
        [System.IO.Path]::DirectorySeparatorChar,
        [System.IO.Path]::AltDirectorySeparatorChar
    ) + [System.IO.Path]::DirectorySeparatorChar
    $changes = [System.Collections.Generic.List[string]]::new()
    foreach ($root in @(
        (Join-Path $ProjectRoot "Content"),
        (Join-Path $ProjectRoot "Plugins")
    )) {
        if (-not (Test-Path -LiteralPath $root -PathType Container)) {
            continue
        }
        Assert-NoReparsePoint -Path $root -Label "Protected workspace root"
        Get-ChildItem -LiteralPath $root -Recurse -Force | ForEach-Object {
            $file = $_
            if ($file.PSIsContainer) {
                return
            }
            if (
                ($file.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne
                0
            ) {
                throw "Protected workspace contains a reparse point: $($file.FullName)"
            }
            $fullPath = [System.IO.Path]::GetFullPath($file.FullName)
            if ($fullPath.StartsWith(
                $destinationPrefix,
                [System.StringComparison]::OrdinalIgnoreCase
            )) {
                return
            }
            if (-not $fullPath.StartsWith(
                $projectPrefix,
                [System.StringComparison]::OrdinalIgnoreCase
            )) {
                throw "Protected workspace file escaped the project root: $fullPath"
            }
            if ($file.LastWriteTimeUtc -ge $SinceUtc) {
                $relativePath = $fullPath.Substring($projectPrefix.Length)
                $changes.Add("created_or_changed:$relativePath")
                if ($changes.Count -gt 256) {
                    throw "More than 256 files changed outside the import destination"
                }
            }
        }
    }
    return @($changes | Sort-Object)
}

function Publish-Result {
    param([System.Collections.IDictionary]$Payload)

    $resultPath = Join-Path $resolvedOutput "result.json"
    $temporaryPath = Join-Path $resolvedOutput "result.json.tmp"
    if (
        (Test-Path -LiteralPath $resultPath) -or
        (Test-Path -LiteralPath $temporaryPath)
    ) {
        throw "Refusing to overwrite an import result file"
    }
    $json = $Payload | ConvertTo-Json -Depth 12
    [System.IO.File]::WriteAllText(
        $temporaryPath,
        $json + [Environment]::NewLine,
        [System.Text.UTF8Encoding]::new($false)
    )
    [System.IO.File]::Move($temporaryPath, $resultPath)
}

$resolvedAllowedOutputRoot = [System.IO.Path]::GetFullPath($AllowedOutputRoot)
if (-not (Test-Path -LiteralPath $resolvedAllowedOutputRoot -PathType Container)) {
    throw "Allowed diagnostics root is missing: $resolvedAllowedOutputRoot"
}
Assert-NoReparsePoint -Path $resolvedAllowedOutputRoot -Label "Diagnostics root"

$resolvedPlan = [System.IO.Path]::GetFullPath($PlanPath)
if (-not (Test-IsStrictChildPath -Candidate $resolvedPlan -Parent $resolvedAllowedOutputRoot)) {
    throw "PlanPath must be a child of $resolvedAllowedOutputRoot"
}
if (-not (Test-Path -LiteralPath $resolvedPlan -PathType Leaf)) {
    throw "Required plan file is missing: $resolvedPlan"
}
Assert-NoReparsePoint -Path $resolvedPlan -Label "Plan file"

$resolvedOutput = [System.IO.Path]::GetFullPath($OutputDirectory)
if (-not (Test-IsStrictChildPath -Candidate $resolvedOutput -Parent $resolvedAllowedOutputRoot)) {
    throw "OutputDirectory must be a child of $resolvedAllowedOutputRoot"
}
if (Test-Path -LiteralPath $resolvedOutput) {
    throw "OutputDirectory must be fresh and must not already exist: $resolvedOutput"
}
$outputParent = Split-Path -Parent $resolvedOutput
if (-not (Test-Path -LiteralPath $outputParent -PathType Container)) {
    throw "OutputDirectory parent must already exist: $outputParent"
}
Assert-NoReparsePoint -Path $outputParent -Label "Output directory parent"

foreach ($requiredPath in @(
    $ProjectFile,
    $UnrealEditorCmd,
    $ImportScript,
    $SourceRoot
)) {
    if (-not (Test-Path -LiteralPath $requiredPath)) {
        throw "Required path is missing: $requiredPath"
    }
    Assert-NoReparsePoint -Path $requiredPath -Label "Required path"
}

$plan = Get-Content -LiteralPath $resolvedPlan -Raw | ConvertFrom-Json
foreach ($requiredProperty in @(
    "schema",
    "source_root",
    "source_policy",
    "source_provenance",
    "destination_root",
    "diagnostics_root",
    "project_file",
    "expected_engine_version_prefix",
    "license_approval",
    "record_count",
    "source_bytes",
    "category_counts",
    "dataset_sha256",
    "plan_sha256",
    "records"
)) {
    Assert-JsonProperty -Object $plan -Name $requiredProperty
}
foreach ($approvalProperty in @(
    "approved",
    "status",
    "basis",
    "provenance",
    "source_root"
)) {
    Assert-JsonProperty -Object $plan.license_approval -Name $approvalProperty
}

if ($plan.schema -cne $ExpectedPlanSchema) {
    throw "Unexpected plan schema: $($plan.schema)"
}
if ([System.IO.Path]::GetFullPath([string]$plan.source_root) -cne $SourceRoot) {
    throw "Plan source root must be exactly $SourceRoot"
}
if ($plan.source_policy -cne "immutable") {
    throw "Plan source policy must be immutable"
}
if ($plan.source_provenance -cne $ExpectedSourceProvenance) {
    throw "Plan source provenance is invalid"
}
if ($plan.destination_root -cne $DestinationAssetRoot) {
    throw "Plan destination root must be exactly $DestinationAssetRoot"
}
if (
    [System.IO.Path]::GetFullPath([string]$plan.diagnostics_root) -cne
    $resolvedAllowedOutputRoot
) {
    throw "Plan diagnostics root identity is invalid"
}
if ([System.IO.Path]::GetFullPath([string]$plan.project_file) -cne $ProjectFile) {
    throw "Plan project identity is invalid"
}
if ($plan.expected_engine_version_prefix -cne "5.8") {
    throw "Plan Unreal engine identity is invalid"
}
if (
    $plan.license_approval.approved -ne $true -or
    $plan.license_approval.status -cne $ExpectedApprovalStatus -or
    $plan.license_approval.basis -cne $ExpectedApprovalBasis -or
    $plan.license_approval.provenance -cne $ExpectedSourceProvenance -or
    [System.IO.Path]::GetFullPath(
        [string]$plan.license_approval.source_root
    ) -cne $SourceRoot
) {
    throw "Plan license approval or provenance is invalid"
}
if (
    [string]$plan.dataset_sha256 -cnotmatch "^[0-9A-F]{64}$" -or
    [string]$plan.plan_sha256 -cnotmatch "^[0-9A-F]{64}$"
) {
    throw "Plan content fingerprints are invalid"
}
if ([int64]$plan.record_count -ne @($plan.records).Count) {
    throw "Plan record_count does not match its records"
}

$rawCategoryParts = @($Categories -split ",")
if (
    $rawCategoryParts.Count -eq 0 -or
    @($rawCategoryParts | Where-Object { [string]::IsNullOrWhiteSpace($_) }).Count -gt 0
) {
    throw "Categories must contain one or more comma-separated category names"
}
$requestedCategories = @($rawCategoryParts | ForEach-Object { $_.Trim() })
$categorySet = [System.Collections.Generic.HashSet[string]]::new(
    [System.StringComparer]::Ordinal
)
foreach ($category in $requestedCategories) {
    if (-not $categorySet.Add($category)) {
        throw "Categories must be unique: $category"
    }
}

$availableCategories = [System.Collections.Generic.HashSet[string]]::new(
    [System.StringComparer]::Ordinal
)
foreach ($record in @($plan.records)) {
    Assert-JsonProperty -Object $record -Name "category"
    Assert-JsonProperty -Object $record -Name "source_size"
    [void]$availableCategories.Add([string]$record.category)
}
foreach ($category in $requestedCategories) {
    if (-not $availableCategories.Contains($category)) {
        throw "Unknown stylized import category: $category"
    }
}
$matchingRecords = @(
    $plan.records |
        Where-Object { $categorySet.Contains([string]$_.category) }
)
$selectedRecords = @(
    $matchingRecords |
        Select-Object -Skip $Start -First $Limit
)
if ($selectedRecords.Count -eq 0) {
    throw (
        "Import selection is empty: filtered=$($matchingRecords.Count) " +
        "start=$Start limit=$Limit"
    )
}
$selectedSourceBytes = [int64](
    ($selectedRecords | Measure-Object -Property source_size -Sum).Sum
)
if ($selectedSourceBytes -gt $MaximumSelectedSourceBytes) {
    throw (
        "Selected source bytes $selectedSourceBytes exceed the per-batch gate " +
        "$MaximumSelectedSourceBytes"
    )
}

$blockingProcesses = Get-CimInstance Win32_Process |
    Where-Object {
        $_.Name -match "^(UnrealEditor|UnrealEditor-Cmd|UnrealBuildTool|AutomationTool|RunUAT|UnrealPak|ShaderCompileWorker)\.exe$"
    }
if ($blockingProcesses) {
    $summary = (
        $blockingProcesses |
            ForEach-Object { "$($_.Name):$($_.ProcessId)" }
    ) -join ", "
    throw "Refusing to overlap an Unreal or build process: $summary"
}

$resourcesBefore = Get-ResourceSnapshot
if ($resourcesBefore.free_physical_gib -lt $MinimumFreePhysicalGiB) {
    throw (
        "Only $($resourcesBefore.free_physical_gib) GiB physical RAM is free; " +
        "the import gate is $MinimumFreePhysicalGiB GiB"
    )
}
if ($resourcesBefore.free_commit_gib -lt $MinimumFreeCommitGiB) {
    throw (
        "Only $($resourcesBefore.free_commit_gib) GiB commit is free; " +
        "the import gate is $MinimumFreeCommitGiB GiB"
    )
}
if ($resourcesBefore.free_d_drive_gib -lt $MinimumFreeDDriveGiB) {
    throw (
        "Only $($resourcesBefore.free_d_drive_gib) GiB is free on D:; " +
        "the import gate is $MinimumFreeDDriveGiB GiB"
    )
}

$planFileSha256 = (
    Get-FileHash -LiteralPath $resolvedPlan -Algorithm SHA256
).Hash
$protectedBefore = Get-FileHashes -RelativePaths $ProtectedFiles
$startedAt = (Get-Date).ToUniversalTime()
$outsideDestinationBeforeCount = Get-OutsideDestinationFileCount

New-Item -ItemType Directory -Path $resolvedOutput | Out-Null
$stageLogPath = Join-Path $resolvedOutput "stage.log"
$stageManifestPath = Join-Path $resolvedOutput "stage_manifest.json"
$logPath = Join-Path $resolvedOutput "unreal_import.log"
$errorLogPath = Join-Path $resolvedOutput "unreal_import.stderr.log"
$engineLogPath = Join-Path $resolvedOutput "unreal_engine.log"
$statePath = Join-Path $resolvedOutput "state.json"
if (Test-Path -LiteralPath $statePath) {
    throw "Import state must be fresh: $statePath"
}

$arguments = @(
    "`"$ProjectFile`"",
    "-run=pythonscript",
    "-script=`"$ImportScript`"",
    "-unattended",
    "-nop4",
    "-nosplash",
    "-NoSound",
    "-NullRHI",
    "-stdout",
    "-FullStdOutLogOutput",
    "-UTF8Output",
    "-abslog=`"$engineLogPath`""
)

$exitCode = -1
$status = "failed"
$failure = $null
$stageManifestFileSha256 = $null
try {
    $stagePython = (Get-Command python.exe -ErrorAction Stop).Source
    $stageArguments = @(
        $ImportScript,
        "stage-batch",
        "--plan",
        $resolvedPlan,
        "--categories",
        ($requestedCategories -join ","),
        "--start",
        $Start.ToString([Globalization.CultureInfo]::InvariantCulture),
        "--limit",
        $Limit.ToString([Globalization.CultureInfo]::InvariantCulture),
        "--output-directory",
        $resolvedOutput
    )
    $stageOutput = (& $stagePython @stageArguments 2>&1 | Out-String)
    [System.IO.File]::WriteAllText(
        $stageLogPath,
        $stageOutput,
        [System.Text.UTF8Encoding]::new($false)
    )
    if ($LASTEXITCODE -ne 0) {
        throw "Stylized source staging exited with code $LASTEXITCODE"
    }
    if (-not (Test-Path -LiteralPath $stageManifestPath -PathType Leaf)) {
        throw "Staging did not publish the authenticated manifest"
    }
    $stageManifestFileSha256 = (
        Get-FileHash -LiteralPath $stageManifestPath -Algorithm SHA256
    ).Hash

    $env:RED_STYLIZED_IMPORT_PLAN = $resolvedPlan
    $env:RED_STYLIZED_IMPORT_PLAN_FILE_SHA256 = $planFileSha256
    $env:RED_STYLIZED_IMPORT_STAGE_MANIFEST = $stageManifestPath
    $env:RED_STYLIZED_IMPORT_STAGE_MANIFEST_FILE_SHA256 = (
        $stageManifestFileSha256
    )
    $env:RED_STYLIZED_IMPORT_CATEGORIES = (
        $requestedCategories -join ","
    )
    $env:RED_STYLIZED_IMPORT_START = $Start.ToString(
        [Globalization.CultureInfo]::InvariantCulture
    )
    $env:RED_STYLIZED_IMPORT_LIMIT = $Limit.ToString(
        [Globalization.CultureInfo]::InvariantCulture
    )
    $env:RED_STYLIZED_IMPORT_STATE = $statePath

    $process = Start-Process `
        -FilePath $UnrealEditorCmd `
        -ArgumentList $arguments `
        -WorkingDirectory $ProjectRoot `
        -WindowStyle Hidden `
        -RedirectStandardOutput $logPath `
        -RedirectStandardError $errorLogPath `
        -Wait `
        -PassThru
    $exitCode = $process.ExitCode
    if ($exitCode -ne 0) {
        throw "Unreal PythonScriptCommandlet exited with code $exitCode"
    }
    if (-not (Test-Path -LiteralPath $statePath -PathType Leaf)) {
        throw "Unreal exited successfully but did not publish the batch state"
    }
    $logText = Get-Content -LiteralPath $logPath -Raw
    if ($logText -notmatch "RED_STYLIZED_IMPORT_COMPLETE") {
        throw "The Unreal log is missing RED_STYLIZED_IMPORT_COMPLETE"
    }
    $stateCandidate = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json
    if (
        $stateCandidate.schema -cne
        "redmmotitan.stylized_source_import_state.v3" -or
        $stateCandidate.plan_file_sha256 -cne $planFileSha256 -or
        $stateCandidate.stage_manifest_file_sha256 -cne
        $stageManifestFileSha256 -or
        $stateCandidate.plan_sha256 -cne $plan.plan_sha256 -or
        $stateCandidate.dataset_sha256 -cne $plan.dataset_sha256
    ) {
        throw "Published state does not authenticate the selected plan"
    }
    $status = "passed"
}
catch {
    $failure = $_.Exception.Message
}
finally {
    Remove-Item Env:\RED_STYLIZED_IMPORT_PLAN -ErrorAction SilentlyContinue
    Remove-Item Env:\RED_STYLIZED_IMPORT_PLAN_FILE_SHA256 -ErrorAction SilentlyContinue
    Remove-Item Env:\RED_STYLIZED_IMPORT_STAGE_MANIFEST -ErrorAction SilentlyContinue
    Remove-Item Env:\RED_STYLIZED_IMPORT_STAGE_MANIFEST_FILE_SHA256 -ErrorAction SilentlyContinue
    Remove-Item Env:\RED_STYLIZED_IMPORT_CATEGORIES -ErrorAction SilentlyContinue
    Remove-Item Env:\RED_STYLIZED_IMPORT_START -ErrorAction SilentlyContinue
    Remove-Item Env:\RED_STYLIZED_IMPORT_LIMIT -ErrorAction SilentlyContinue
    Remove-Item Env:\RED_STYLIZED_IMPORT_STATE -ErrorAction SilentlyContinue
}

$protectedAfter = $null
$outsideDestinationAfterCount = $null
$outsideDestinationChanges = @()
$protectedUnchanged = $false
$outsideDestinationUnchanged = $false
try {
    $protectedAfter = Get-FileHashes -RelativePaths $ProtectedFiles
    $protectedChanges = @()
    foreach ($relativePath in $ProtectedFiles) {
        if ($protectedBefore[$relativePath] -ne $protectedAfter[$relativePath]) {
            $protectedChanges += $relativePath
        }
    }
    $protectedUnchanged = $protectedChanges.Count -eq 0
    if (-not $protectedUnchanged) {
        throw "Protected checkpoint changed: $($protectedChanges -join ', ')"
    }

    $outsideDestinationAfterCount = Get-OutsideDestinationFileCount
    $outsideDestinationChanges = @(
        Get-OutsideDestinationRecentChanges -SinceUtc $startedAt
    )
    if ($outsideDestinationAfterCount -ne $outsideDestinationBeforeCount) {
        $outsideDestinationChanges += (
            "file_count:" +
            "$outsideDestinationBeforeCount->$outsideDestinationAfterCount"
        )
    }
    $outsideDestinationUnchanged = $outsideDestinationChanges.Count -eq 0
    if (-not $outsideDestinationUnchanged) {
        throw (
            "Project files outside the allowed stylized destination changed: " +
            ($outsideDestinationChanges -join ", ")
        )
    }
}
catch {
    $status = "failed"
    $failure = $_.Exception.Message
}

$state = $null
if (Test-Path -LiteralPath $statePath -PathType Leaf) {
    $state = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json
}
$finishedAt = (Get-Date).ToUniversalTime()
$resourcesAfter = Get-ResourceSnapshot
$payload = [ordered]@{
    schema = "redmmotitan.stylized_source_import_batch_result.v3"
    status = $status
    failure = $failure
    started_at_utc = $startedAt.ToString("o")
    finished_at_utc = $finishedAt.ToString("o")
    duration_seconds = [math]::Round(
        ($finishedAt - $startedAt).TotalSeconds,
        3
    )
    commandlet_exit_code = $exitCode
    plan_path = $resolvedPlan
    plan_file_sha256 = $planFileSha256
    stage_manifest_path = $stageManifestPath
    stage_manifest_file_sha256 = $stageManifestFileSha256
    plan_sha256 = $plan.plan_sha256
    dataset_sha256 = $plan.dataset_sha256
    source_provenance = $ExpectedSourceProvenance
    license_approval_status = $ExpectedApprovalStatus
    categories = @($requestedCategories)
    batch_start = $Start
    batch_limit = $Limit
    selected_record_count = $selectedRecords.Count
    selected_source_bytes = $selectedSourceBytes
    resource_gates = [ordered]@{
        minimum_free_physical_gib = $MinimumFreePhysicalGiB
        minimum_free_commit_gib = $MinimumFreeCommitGiB
        minimum_free_d_drive_gib = $MinimumFreeDDriveGiB
        maximum_selected_source_bytes = $MaximumSelectedSourceBytes
    }
    resources_before = $resourcesBefore
    resources_after = $resourcesAfter
    protected_checkpoints_unchanged = $protectedUnchanged
    protected_before = $protectedBefore
    protected_after = $protectedAfter
    outside_destination_files_unchanged = $outsideDestinationUnchanged
    outside_destination_change_count = $outsideDestinationChanges.Count
    outside_destination_changes = @($outsideDestinationChanges)
    outside_destination_before_count = $outsideDestinationBeforeCount
    outside_destination_after_count = $outsideDestinationAfterCount
    state = $state
    stage_log_path = $stageLogPath
    log_path = $logPath
    stderr_log_path = $errorLogPath
    engine_log_path = $engineLogPath
}
Publish-Result -Payload $payload

if ($status -ne "passed") {
    if ([string]::IsNullOrWhiteSpace($failure)) {
        throw "Stylized source import batch failed without a diagnostic"
    }
    throw $failure
}

Write-Output (
    "RED_STYLIZED_IMPORT_BATCH_PASSED " +
    "categories=$($requestedCategories -join ',') start=$Start limit=$Limit " +
    "result=$(Join-Path $resolvedOutput 'result.json')"
)
