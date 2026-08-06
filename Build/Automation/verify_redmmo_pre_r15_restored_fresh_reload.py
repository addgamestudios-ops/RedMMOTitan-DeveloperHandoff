"""No-save fresh-process verification for the restored pre-R15 playable map."""

from __future__ import annotations

import os

import unreal


BASE = r"D:\RedMMOTitan\Build\Automation\verify_redmmo_ppg_playerstart_camera_r13_fresh_reload.py"
OLD_ROOT = r'D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_PPG_PlayerStartCamera_R13FreshReload_20260802'
NEW_ROOT = r'D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_PreR15_PlayableRestore_20260803'
OLD_RESULT = "verify_redmmo_ppg_playerstart_camera_r13_fresh_reload_result.json"
NEW_RESULT = "verify_redmmo_pre_r15_restored_fresh_reload_result.json"


with open(BASE, "r", encoding="utf-8") as handle:
    source = handle.read()

if source.count(OLD_ROOT) != 1:
    raise RuntimeError("Reviewed fresh-reload verifier root marker drift")
if source.count(OLD_RESULT) != 1:
    raise RuntimeError("Reviewed fresh-reload verifier result marker drift")

source = source.replace(OLD_ROOT, NEW_ROOT, 1)
source = source.replace(OLD_RESULT, NEW_RESULT, 1)
exec(compile(source, BASE, "exec"), globals(), globals())

result = os.path.join(NEW_ROOT, NEW_RESULT)
if not os.path.isfile(result):
    raise RuntimeError("Fresh-reload result was not produced")

unreal.SystemLibrary.quit_editor()
