"""Read-only R12 pawn camera/component layout probe."""

import json
import os
import traceback

import unreal


PAWN = "/Game/RedMMO/Gameplay/Player/BP_RedPlanetCharacter_R11"
OUT = r"D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_PPG_CharacterShip_R12_20260802\probe_redmmo_r12_camera_components.json"


def path(value):
    return value.get_path_name() if value is not None else None


def prop(value, name):
    try:
        result = value.get_editor_property(name)
        return path(result) if isinstance(result, unreal.Object) else str(result)
    except Exception:
        return None


try:
    bp = unreal.load_asset(PAWN)
    cls = bp.generated_class()
    cdo = unreal.get_default_object(cls)
    records = []
    for component in cdo.get_components_by_class(unreal.ActorComponent):
        record = {
            "name": component.get_name(),
            "path": component.get_path_name(),
            "class": component.get_class().get_name(),
        }
        if isinstance(component, unreal.SceneComponent):
            record.update({
                "attach_parent": path(component.get_attach_parent()),
                "relative_location": str(component.get_editor_property("relative_location")),
                "relative_rotation": str(component.get_editor_property("relative_rotation")),
                "relative_scale3d": str(component.get_editor_property("relative_scale3d")),
                "visible": prop(component, "visible"),
                "hidden_in_game": prop(component, "hidden_in_game"),
            })
        if isinstance(component, unreal.SpringArmComponent):
            record.update({
                "target_arm_length": prop(component, "target_arm_length"),
                "socket_offset": prop(component, "socket_offset"),
                "target_offset": prop(component, "target_offset"),
                "use_pawn_control_rotation": prop(component, "use_pawn_control_rotation"),
                "do_collision_test": prop(component, "do_collision_test"),
                "inherit_pitch": prop(component, "inherit_pitch"),
                "inherit_yaw": prop(component, "inherit_yaw"),
                "inherit_roll": prop(component, "inherit_roll"),
            })
        if isinstance(component, unreal.CameraComponent):
            record.update({
                "field_of_view": prop(component, "field_of_view"),
                "use_pawn_control_rotation": prop(component, "use_pawn_control_rotation"),
            })
        records.append(record)
    subobject_records = []
    subsystem = unreal.get_engine_subsystem(unreal.SubobjectDataSubsystem)
    library = unreal.SubobjectDataBlueprintFunctionLibrary
    for handle in subsystem.k2_gather_subobject_data_for_blueprint(bp):
        data = library.get_data(handle)
        associated = library.get_associated_object(data)
        local_object = library.get_object_for_blueprint(data, bp)
        record = {
            "variable": str(library.get_variable_name(data)),
            "display": str(library.get_display_name(data)),
            "is_actor": bool(library.is_actor(data)),
            "is_component": bool(library.is_component(data)),
            "is_inherited": bool(library.is_inherited_component(data)),
            "associated": path(associated),
            "object_for_blueprint": path(local_object),
            "associated_class": associated.get_class().get_name() if associated is not None else None,
            "object_for_blueprint_class": local_object.get_class().get_name() if local_object is not None else None,
        }
        for prefix, component in (("associated", associated), ("local", local_object)):
            if isinstance(component, unreal.SceneComponent):
                parent = component.get_attach_parent()
                record[prefix + "_attach_parent"] = path(parent)
                for property_name in (
                    "relative_location", "relative_rotation", "relative_scale3d",
                    "visible", "hidden_in_game",
                ):
                    record[prefix + "_" + property_name] = prop(component, property_name)
            if isinstance(component, unreal.SpringArmComponent):
                for property_name in (
                    "target_arm_length", "socket_offset", "target_offset",
                    "use_pawn_control_rotation", "do_collision_test",
                    "inherit_pitch", "inherit_yaw", "inherit_roll",
                ):
                    record[prefix + "_" + property_name] = prop(component, property_name)
            if isinstance(component, unreal.CameraComponent):
                for property_name in ("field_of_view", "use_pawn_control_rotation"):
                    record[prefix + "_" + property_name] = prop(component, property_name)
        subobject_records.append(record)
    result = {
        "status": "PASS_READ_ONLY",
        "pawn": PAWN,
        "components": records,
        "subobjects": subobject_records,
    }
except Exception as error:
    result = {"status": "FAIL", "error": str(error), "traceback": traceback.format_exc()}
os.makedirs(os.path.dirname(OUT), exist_ok=True)
with open(OUT + ".tmp", "w", encoding="utf-8") as handle:
    json.dump(result, handle, indent=2, sort_keys=True)
    handle.write("\n")
os.replace(OUT + ".tmp", OUT)
unreal.log("REDMMO_R12_CAMERA_PROBE " + result["status"])
