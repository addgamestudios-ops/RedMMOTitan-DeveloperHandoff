"""R64 surface-only adapter over the proven rollback-backed R37 apply path."""

from pathlib import Path


SOURCE = Path(r"D:\RedMMOTitan\Build\Automation\apply_redmmo_sostylized_ground_r37.py")
scope = {"__name__": "redmmo_r64_apply"}
text = SOURCE.read_text(encoding="utf-8")
suffix = "\nmain()\n"
if not text.endswith(suffix):
    raise RuntimeError("R37 apply bootstrap shape changed")

old = '''        neutral = unreal.LinearColor(1.0, 1.0, 1.0, 1.0)
        for name in sorted(required_vectors):
            before["vectors"][name] = color(editing.get_material_instance_vector_parameter_value(instance, name))
            editing.set_material_instance_vector_parameter_value(instance, name, neutral)
            after["vectors"][name] = color(editing.get_material_instance_vector_parameter_value(instance, name))
            require(max(abs(value - 1.0) for value in after["vectors"][name]) <= 0.0001, "vector postcondition failed: " + name)
'''
new = '''        tint_targets = {
            "R10L_GroundTintA": unreal.LinearColor(0.92, 0.80, 0.48, 1.0),
            "R10L_GroundTintB": unreal.LinearColor(0.58, 0.48, 0.22, 1.0),
        }
        for name in sorted(required_vectors):
            target = tint_targets[name]
            before["vectors"][name] = color(editing.get_material_instance_vector_parameter_value(instance, name))
            editing.set_material_instance_vector_parameter_value(instance, name, target)
            after["vectors"][name] = color(editing.get_material_instance_vector_parameter_value(instance, name))
            require(max(abs(value - expected) for value, expected in zip(after["vectors"][name], color(target))) <= 0.0001, "vector postcondition failed: " + name)
'''
if text.count(old) != 1:
    raise RuntimeError("R37 tint block changed")
text = text.replace(old, new)
exec(compile(text[: -len(suffix)], str(SOURCE), "exec"), scope)

scope["ROLLBACK"] = Path(r"D:\RedMMOTitanWindowsData\Rollback\BeforeGroundHueSeparation_R64_20260805T2124Z")
scope["DIAG"] = Path(r"D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_GroundHueSeparation_R64_20260805T2124Z\Apply")
scope["RESULT"] = scope["DIAG"] / "apply_result.json"
scope["main"]()
