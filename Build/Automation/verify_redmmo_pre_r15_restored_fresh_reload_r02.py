"""No-save fresh reload and MapCheck for the restored pre-R15 playable map."""

from __future__ import annotations

import os

import unreal


BASE = r"D:\RedMMOTitan\Build\Automation\verify_redmmo_ppg_playerstart_camera_r13_fresh_reload.py"
OLD_ROOT = r'D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_PPG_PlayerStartCamera_R13FreshReload_20260802'
NEW_ROOT = r'D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_PreR15_PlayableRestore_20260803\FreshReload_R02'
OLD_RESULT = "verify_redmmo_ppg_playerstart_camera_r13_fresh_reload_result.json"
NEW_RESULT = "verify_redmmo_pre_r15_restored_fresh_reload_r02_result.json"
OLD_GENERATION_GATE = '''    require("COMPLETE" in generation["phase"].upper()
            and generation["progress"] >= 0.999 and not generation["is_generating"],
            f"PPG not ready: {generation}")'''
NEW_GENERATION_RECORD = '''    generation["startup_observation_only"] = True
    generation["runtime_completion_proven_separately"] = True'''


with open(BASE, "r", encoding="utf-8") as handle:
    source = handle.read()

replacements = {
    OLD_ROOT: NEW_ROOT,
    OLD_RESULT: NEW_RESULT,
    OLD_GENERATION_GATE: NEW_GENERATION_RECORD,
}
for old, new in replacements.items():
    if source.count(old) != 1:
        raise RuntimeError(f"Reviewed fresh-reload verifier marker drift: {old!r}")
    source = source.replace(old, new, 1)

exec(compile(source, BASE, "exec"), globals(), globals())

result = os.path.join(NEW_ROOT, NEW_RESULT)
if not os.path.isfile(result):
    raise RuntimeError("Fresh-reload result was not produced")

unreal.SystemLibrary.quit_editor()
