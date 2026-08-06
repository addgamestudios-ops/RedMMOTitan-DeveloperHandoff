"""Run the reviewed radial-locomotion probe against the restored pre-R15 map."""

from __future__ import annotations


BASE = r"D:\RedMMOTitan\Build\Automation\probe_redmmo_r15_surface_locomotion.py"
OLD_HASH = "7BA68701F4B1A96777407FC8C349D90878037917CD3212878164B9A28BB37059"
NEW_HASH = "C9BE88085575E75E1790CB9306D564EB100F5ED2E75E012C1FD09EA110FDDFE0"
OLD_ROOT = r'D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_R15_Playability_20260803'
NEW_ROOT = r'D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_PreR15_PlayableRestore_20260803\Locomotion_R01'


with open(BASE, "r", encoding="utf-8") as handle:
    source = handle.read()

replacements = {
    f'MAP_SHA = "{OLD_HASH}"': f'MAP_SHA = "{NEW_HASH}"',
    f'ROOT = r"{OLD_ROOT}"': f'ROOT = r"{NEW_ROOT}"',
    '"schema": "redmmo.r15.surface_locomotion_probe.v1"':
        '"schema": "redmmo.pre_r15_restored.surface_locomotion_probe.v1"',
    'unreal.log("REDMMO_R15_LOCOMOTION_PROBE PASS")':
        'unreal.log("REDMMO_PRE_R15_LOCOMOTION_PROBE PASS")\n        unreal.SystemLibrary.quit_editor()',
    'unreal.log_error("REDMMO_R15_LOCOMOTION_PROBE FAIL " + str(error))':
        'unreal.log_error("REDMMO_PRE_R15_LOCOMOTION_PROBE FAIL " + str(error))\n        unreal.SystemLibrary.quit_editor()',
}

for old, new in replacements.items():
    if source.count(old) != 1:
        raise RuntimeError(f"Reviewed locomotion probe marker drift: {old!r}")
    source = source.replace(old, new, 1)

exec(compile(source, BASE, "exec"), globals(), globals())
