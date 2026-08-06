$ErrorActionPreference = 'Stop'

$projectRoot = 'D:\RedMMOTitanWindowsData\Projects\RedMMO'
$destination = Join-Path $projectRoot 'Content\RedMMO\Maps\RedMMO_PPG_HomeWorld.umap'
$rollbackRoot = 'D:\RedMMOTitanWindowsData\Rollback\RedMMO_PPG_ContinentBiome_R15_20260802_211912_A01'
$source = Join-Path $rollbackRoot 'RedMMO_PPG_HomeWorld.pre_r15.umap'
$r15Checkpoint = 'D:\RedMMOTitanWindowsData\Rollback\RedMMO_R15_Playability_20260803_012126\manifest.json'

$expectedCurrent = '7BA68701F4B1A96777407FC8C349D90878037917CD3212878164B9A28BB37059'
$expectedSource = 'C9BE88085575E75E1790CB9306D564EB100F5ED2E75E012C1FD09EA110FDDFE0'

$unreal = Get-CimInstance Win32_Process | Where-Object {
    $_.Name -match '^(UnrealEditor|UnrealEditor-Cmd|ShaderCompileWorker).*'
}
if ($unreal) {
    throw "Unreal process is active; refusing map restore: $($unreal.ProcessId -join ', ')"
}

foreach ($required in @($destination, $source, $r15Checkpoint)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
        throw "Required rollback input is missing: $required"
    }
}

$currentHash = (Get-FileHash -LiteralPath $destination -Algorithm SHA256).Hash
$sourceHash = (Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash
if ($currentHash -ne $expectedCurrent) {
    throw "Current map hash changed; expected $expectedCurrent but found $currentHash"
}
if ($sourceHash -ne $expectedSource) {
    throw "Rollback map hash mismatch; expected $expectedSource but found $sourceHash"
}

Copy-Item -LiteralPath $source -Destination $destination -Force
$restoredHash = (Get-FileHash -LiteralPath $destination -Algorithm SHA256).Hash
if ($restoredHash -ne $expectedSource) {
    throw "Restored map verification failed: $restoredHash"
}

[ordered]@{
    status = 'RESTORED_PRE_R15_MAP_ONLY'
    destination = $destination
    previous_sha256 = $currentHash
    restored_sha256 = $restoredHash
    retained_r15_checkpoint = $r15Checkpoint
    retained_r15_content = 'D:\RedMMOTitanWindowsData\Projects\RedMMO\Content\RedMMO\World\PPG\HomeWorld\ContinentBiome\R15'
} | ConvertTo-Json -Depth 4
