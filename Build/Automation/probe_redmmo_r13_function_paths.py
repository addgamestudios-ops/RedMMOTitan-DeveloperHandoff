"""Read-only UE 5.8 reflection probe for the R13 spawn-camera Blueprint nodes."""

from __future__ import annotations

import json
import os

import unreal


OUT = (
    r"D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_PPG_CharacterShip_R13_20260802"
    r"\probe_redmmo_r13_function_paths.json"
)

CLASSES = [
    unreal.Controller,
    unreal.CharacterMovementComponent,
    unreal.GravityController,
]

MEMBERS = {
    "Controller": ["get_control_rotation", "set_control_rotation"],
    "CharacterMovementComponent": ["get_gravity_direction"],
    "GravityController": ["get_gravity_relative_rotation", "get_gravity_world_rotation"],
}

PATH_CANDIDATES = [
    "/Script/Engine.Controller:GetControlRotation",
    "/Script/Engine.Controller:SetControlRotation",
    "/Script/Engine.Controller.GetControlRotation",
    "/Script/Engine.Controller.SetControlRotation",
    "/Script/Engine.CharacterMovementComponent:GetGravityDirection",
    "/Script/Engine.CharacterMovementComponent.GetGravityDirection",
    "/Script/PPG.GravityController:GetGravityRelativeRotation",
    "/Script/PPG.GravityController:GetGravityWorldRotation",
    "/Script/PPG.GravityController.GetGravityRelativeRotation",
    "/Script/PPG.GravityController.GetGravityWorldRotation",
    "/Script/Engine.KismetMathLibrary:MakeRotator",
    "/Script/Engine.KismetMathLibrary:BreakRotator",
    "/Script/Engine.KismetMathLibrary.MakeRotator",
    "/Script/Engine.KismetMathLibrary.BreakRotator",
]


def safe(call):
    try:
        value = call()
        if value is None:
            return None
        return {
            "type": type(value).__name__,
            "str": str(value),
            "path": value.get_path_name() if hasattr(value, "get_path_name") else None,
            "class": value.get_class().get_path_name() if hasattr(value, "get_class") else None,
        }
    except Exception as exc:  # diagnostics only
        return {"error": f"{type(exc).__name__}: {exc}"}


payload = {
    "class_paths": {cls.__name__: cls.static_class().get_path_name() for cls in CLASSES},
    "members": {},
    "path_candidates": {},
}

for cls in CLASSES:
    name = cls.__name__
    payload["members"][name] = {}
    for member in MEMBERS.get(name, []):
        value = getattr(cls, member, None)
        payload["members"][name][member] = {
            "exists": value is not None,
            "doc": str(getattr(value, "__doc__", None)),
            "repr": repr(value),
        }

for candidate in PATH_CANDIDATES:
    payload["path_candidates"][candidate] = {
        "find_object": safe(lambda value=candidate: unreal.find_object(None, value)),
        "load_object": safe(lambda value=candidate: unreal.load_object(None, value)),
    }

os.makedirs(os.path.dirname(OUT), exist_ok=True)
with open(OUT + ".tmp", "w", encoding="utf-8") as handle:
    json.dump(payload, handle, indent=2, sort_keys=True)
    handle.write("\n")
os.replace(OUT + ".tmp", OUT)
unreal.log("REDMMO_R13_FUNCTION_PATH_PROBE PASS")
