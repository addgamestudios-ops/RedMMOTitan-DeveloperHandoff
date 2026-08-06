"""R77 wrapper: retain stock PPG absorption and add only verified Oasis normals/tint."""

from pathlib import Path


SOURCE = Path(r"D:\RedMMOTitan\Build\Automation\apply_redmmo_profile_v1_oasis_water_r76.py")
text = SOURCE.read_text(encoding="utf-8")
text = text.replace("R76", "R77").replace("r76", "r77")
text = text.replace("20260806T0026Z", "20260806T0051Z")

active_absorption_link = '            (editing.connect_material_expressions(absorption, "", water_output, absorption_input), "absorption"),\n'
if text.count(active_absorption_link) != 1:
    raise RuntimeError("R77 source absorption-link contract drift")
text = text.replace(
    active_absorption_link,
    '            # R77 deliberately retains the inherited stock PPG absorption input.\n',
)

exec(compile(text, str(SOURCE), "exec"), {"__name__": "__main__", "__file__": str(SOURCE)})
