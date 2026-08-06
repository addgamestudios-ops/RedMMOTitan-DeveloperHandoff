"""R78 wrapper: build the PPG-compatible Oasis water with a bracketed low absorption default."""

from pathlib import Path


SOURCE = Path(r"D:\RedMMOTitan\Build\Automation\apply_redmmo_profile_v1_oasis_water_r76.py")
text = SOURCE.read_text(encoding="utf-8")
text = text.replace("R76", "R78").replace("r76", "r78")
text = text.replace("20260806T0026Z", "20260806T0102Z")

source_line = '        oasis_absorption = editing.get_material_instance_vector_parameter_value(oasis_mi, "Absorption Coefficient")\n'
replacement = '''        raw_oasis_absorption = editing.get_material_instance_vector_parameter_value(oasis_mi, "Absorption Coefficient")
        oasis_absorption_scale = 0.18
        oasis_absorption = unreal.LinearColor(
            raw_oasis_absorption.r * oasis_absorption_scale,
            raw_oasis_absorption.g * oasis_absorption_scale,
            raw_oasis_absorption.b * oasis_absorption_scale,
            1.0,
        )
'''
if text.count(source_line) != 1:
    raise RuntimeError("R78 source absorption-read contract drift")
text = text.replace(source_line, replacement)

exec(compile(text, str(SOURCE), "exec"), {"__name__": "__main__", "__file__": str(SOURCE)})
