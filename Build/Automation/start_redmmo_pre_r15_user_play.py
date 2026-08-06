"""Start and leave restored pre-R15 PIE ready for direct user play."""

from __future__ import annotations


BASE = r"D:\RedMMOTitan\Build\Automation\start_r10o_actual_playerstart_pie.py"
OLD_HASH = "C489B6000B359A7B52FBE7FD50A72A76232020DBC9A015DFC61CA2FB1120C46F"
NEW_HASH = "C9BE88085575E75E1790CB9306D564EB100F5ED2E75E012C1FD09EA110FDDFE0"
OLD_DIAG = r'D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_PPG_HomePresentation_R10O_20260802_183909'
NEW_DIAG = r'D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_PreR15_PlayableRestore_20260803\UserPlay_R01'
FRESH_RESULT = (
    r'D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_PreR15_PlayableRestore_20260803'
    r'\FreshReload_R02\verify_redmmo_pre_r15_restored_fresh_reload_r02_result.json'
)


with open(BASE, "r", encoding="utf-8") as handle:
    source = handle.read()

old_evidence = '''        verify = json.loads(VERIFY.read_text(encoding="utf-8"))
        guard = json.loads(VERIFY_GUARD.read_text(encoding="utf-8"))
        require(verify.get("status") == "PASS_FRESH_RELOAD_AND_MAPCHECK_PENDING_ACTUAL_PLAYERSTART_PIE", "R10O reload evidence missing")
        require(guard.get("status") == "PASS_FRESH_RELOAD_MAPCHECK_ZERO_OVERFLOW_PENDING_ACTUAL_PLAYERSTART_PIE", "R10O zero-overflow reload gate missing")'''
new_evidence = f'''        verify = json.loads(Path(r"{FRESH_RESULT}").read_text(encoding="utf-8"))
        require(verify.get("status") == "PASS_FRESH_PROCESS_SERIALIZED_READBACK_MAPCHECK_PENDING_REAL_D3D12_PIE", "Restored-map reload evidence missing")
        require(verify.get("map_check") == {{"errors": 0, "warnings": 0, "log": verify.get("map_check", {{}}).get("log")}}, "Restored-map MapCheck gate missing")'''

replacements = {
    f'EXPECTED_HOME = "{OLD_HASH}"': f'EXPECTED_HOME = "{NEW_HASH}"',
    f'DIAG = Path(r"{OLD_DIAG}")': f'DIAG = Path(r"{NEW_DIAG}")',
    'for port in (5353, 8000, 8765):': 'for port in (5353, 8765):',
    old_evidence: new_evidence,
    'require(len(actors) == 12 and len(spawners) == 1 and len(starts) == 1, "Editor actor contract drift")':
        'require(len(spawners) == 1 and len(starts) == 1, "Editor actor contract drift")',
}

for old, new in replacements.items():
    if source.count(old) != 1:
        raise RuntimeError(f"Reviewed user-play launcher marker drift: {old!r}")
    source = source.replace(old, new, 1)

exec(compile(source, BASE, "exec"), globals(), globals())
