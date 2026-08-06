"""Read-only UE 5.8 attachment API availability probe for R12."""

import json
import os
import traceback

import unreal


OUT = r"D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_PPG_CharacterShip_R12_20260802\probe_redmmo_r12_attachment_api.json"
PAWN = "/Game/RedMMO/Gameplay/Player/BP_RedPlanetCharacter_R11"


def matching(value, terms):
    return sorted(name for name in dir(value) if any(term in name.lower() for term in terms))


try:
    bp = unreal.load_asset(PAWN)
    subsystem = unreal.get_engine_subsystem(unreal.SubobjectDataSubsystem)
    library = unreal.SubobjectDataBlueprintFunctionLibrary
    components = {}
    for handle in subsystem.k2_gather_subobject_data_for_blueprint(bp):
        data = library.get_data(handle)
        variable = str(library.get_variable_name(data))
        local_object = library.get_object_for_blueprint(data, bp)
        if variable in ("Camera", "SpringArm", "CollisionCylinder"):
            components[variable] = {
                "object": local_object.get_path_name() if local_object else None,
                "methods": matching(local_object, ("attach", "parent", "socket")) if local_object else [],
                "handle": str(handle),
            }
    result = {
        "status": "PASS_READ_ONLY",
        "subsystem_methods": matching(subsystem, ("attach", "parent", "reparent", "move")),
        "library_methods": matching(library, ("attach", "parent", "reparent", "move")),
        "subsystem_docs": {
            name: str(getattr(getattr(subsystem, name, None), "__doc__", None))
            for name in ("attach_subobject", "reparent_subobject", "reparent_subobjects")
        },
        "component_docs": {
            name: str(getattr(getattr(components_object, name, None), "__doc__", None))
            for name in ("attach_to_component", "k2_attach_to", "attach_to")
        } if (components_object := next(
            (library.get_object_for_blueprint(library.get_data(handle), bp)
             for handle in subsystem.k2_gather_subobject_data_for_blueprint(bp)
             if str(library.get_variable_name(library.get_data(handle))) == "Camera"),
            None,
        )) is not None else {},
        "components": components,
    }
except Exception as error:
    result = {"status": "FAIL", "error": str(error), "traceback": traceback.format_exc()}

os.makedirs(os.path.dirname(OUT), exist_ok=True)
with open(OUT + ".tmp", "w", encoding="utf-8") as handle:
    json.dump(result, handle, indent=2, sort_keys=True)
    handle.write("\n")
os.replace(OUT + ".tmp", OUT)
unreal.log("REDMMO_R12_ATTACHMENT_API_PROBE " + result["status"])
