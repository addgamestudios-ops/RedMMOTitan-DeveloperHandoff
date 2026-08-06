"""R62 no-save review adapter for the proven R37 SoStylized surface closure."""

from pathlib import Path


SOURCE = Path(r"D:\RedMMOTitan\Build\Automation\apply_redmmo_sostylized_ground_r37.py")
scope = {"__name__": "redmmo_r62_apply"}
text = SOURCE.read_text(encoding="utf-8")
suffix = "\nmain()\n"
if not text.endswith(suffix):
    raise RuntimeError("R37 apply bootstrap shape changed")
exec(compile(text[: -len(suffix)], str(SOURCE), "exec"), scope)

scope["ROLLBACK"] = Path(r"D:\RedMMOTitanWindowsData\Rollback\BeforeSoStylizedGround_R62_20260805T2102Z")
scope["DIAG"] = Path(r"D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_SoStylizedGround_R62_20260805T2102Z")
scope["RESULT"] = scope["DIAG"] / "apply_result.json"
scope["main"]()
