"""Read-only dependency and notify audit for the R87 A01 Trooper AnimBP."""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import unreal


ROOT_PACKAGE = "/Game/Action_Trooper/Animations/Tall_Female/ABP_ThirdPerson_Female_Tall"
RESULT = Path(
    r"D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_R87_GroundedFootstepAudit_20260806T0813Z\animation_notifies.json"
)
_EXIT = {"handle": None}


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def now():
    return datetime.now(timezone.utc).isoformat()


def schedule_exit(delay=6.0):
    started = time.monotonic()

    def tick(_delta):
        if time.monotonic() - started < delay:
            return
        handle = _EXIT.get("handle")
        if handle is not None:
            try:
                unreal.unregister_slate_post_tick_callback(handle)
            except Exception:
                pass
            _EXIT["handle"] = None
        unreal.SystemLibrary.quit_editor()

    _EXIT["handle"] = unreal.register_slate_post_tick_callback(tick)


def safe(call, default=None):
    try:
        return call()
    except Exception:
        return default


def class_name(asset_data):
    class_path = getattr(asset_data, "asset_class_path", None)
    return str(getattr(class_path, "asset_name", "")) or str(class_path)


def dependency_options(*, hard=False, soft=False):
    return unreal.AssetRegistryDependencyOptions(
        include_soft_package_references=soft,
        include_hard_package_references=hard,
        include_searchable_names=False,
        include_soft_management_references=False,
        include_hard_management_references=False,
    )


def object_path(asset_data):
    return f"{asset_data.package_name}.{asset_data.asset_name}"


def object_record(value):
    if value is None:
        return None
    return {
        "text": str(value),
        "class": safe(lambda: value.get_class().get_name()),
        "path": safe(lambda: value.get_path_name()),
    }


def notify_record(event):
    fields = {}
    for name in (
        "notify_name",
        "display_time",
        "trigger_time_offset",
        "end_trigger_time_offset",
        "duration",
        "track_index",
        "notify",
        "notify_state_class",
    ):
        value = safe(lambda name=name: event.get_editor_property(name))
        fields[name] = object_record(value) if name in ("notify", "notify_state_class") else str(value)
    fields["get_time"] = safe(lambda: float(event.get_time()))
    fields["get_trigger_time"] = safe(lambda: float(event.get_trigger_time()))
    return fields


def main():
    payload = {
        "schema": "redmmo.r87.a01_trooper.animation_notifies.audit.v1",
        "started_utc": now(),
        "status": "RUNNING",
        "root_package": ROOT_PACKAGE,
        "mutation_policy": "read_only_no_save",
    }
    try:
        require(not RESULT.exists(), "No-clobber result already exists")
        registry = unreal.AssetRegistryHelpers.get_asset_registry()
        registry.search_all_assets(True)
        require(
            list(registry.get_assets_by_package_name(unreal.Name(ROOT_PACKAGE)) or []),
            "A01 Trooper AnimBP package missing",
        )

        closure = set()
        edges = set()
        pending = [ROOT_PACKAGE]
        while pending:
            package = pending.pop()
            if package in closure or not package.startswith("/Game/"):
                continue
            closure.add(package)
            for kind, options in (
                ("hard", dependency_options(hard=True)),
                ("soft", dependency_options(soft=True)),
            ):
                for dependency in registry.get_dependencies(unreal.Name(package), options) or []:
                    dep = str(dependency)
                    edges.add((package, dep, kind))
                    if dep.startswith("/Game/") and dep not in closure:
                        pending.append(dep)

        asset_records = []
        animation_records = []
        sound_records = []
        load_failures = []
        for package in sorted(closure):
            for asset_data in list(
                registry.get_assets_by_package_name(unreal.Name(package)) or []
            ):
                cls = class_name(asset_data)
                path = object_path(asset_data)
                asset_records.append(
                    {"package": package, "object_path": path, "class": cls}
                )
                if cls not in (
                    "AnimSequence",
                    "AnimMontage",
                    "AnimComposite",
                    "BlendSpace",
                    "BlendSpace1D",
                    "SoundWave",
                    "SoundCue",
                    "MetaSoundSource",
                ):
                    continue
                asset = unreal.load_asset(path)
                if asset is None:
                    load_failures.append(path)
                    continue
                if cls in ("SoundWave", "SoundCue", "MetaSoundSource"):
                    sound_records.append(
                        {"package": package, "object_path": path, "class": cls}
                    )
                    continue
                notifies = safe(lambda: list(asset.get_editor_property("notifies")), [])
                animation_records.append(
                    {
                        "package": package,
                        "object_path": path,
                        "class": cls,
                        "play_length_seconds": safe(lambda: float(asset.get_play_length())),
                        "notify_count": len(notifies),
                        "notifies": [notify_record(event) for event in notifies],
                    }
                )

        dirty_content = [
            str(value)
            for value in unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages()
        ]
        dirty_maps = [
            str(value)
            for value in unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages()
        ]
        require(not dirty_content and not dirty_maps, "Read-only audit dirtied packages")
        payload.update(
            {
                "status": "PASS_READ_ONLY",
                "closure_package_count": len(closure),
                "edge_count": len(edges),
                "asset_count": len(asset_records),
                "assets": asset_records,
                "animations": animation_records,
                "animation_count": len(animation_records),
                "animation_notify_count": sum(
                    record["notify_count"] for record in animation_records
                ),
                "sounds": sound_records,
                "sound_asset_count": len(sound_records),
                "load_failures": load_failures,
                "edges": [
                    {"source": source, "dependency": dependency, "kind": kind}
                    for source, dependency, kind in sorted(edges)
                ],
                "dirty_content_packages": dirty_content,
                "dirty_map_packages": dirty_maps,
            }
        )
    except Exception as exc:
        payload["status"] = "FAIL"
        payload["error"] = repr(exc)
    finally:
        payload["completed_utc"] = now()
        RESULT.parent.mkdir(parents=True, exist_ok=True)
        with RESULT.open("x", encoding="utf-8") as stream:
            json.dump(payload, stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        unreal.log("REDMMO_R87_A01_ANIMATION_NOTIFY_AUDIT " + payload["status"])
        schedule_exit()


main()
