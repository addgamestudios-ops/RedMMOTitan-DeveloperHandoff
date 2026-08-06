"""Character Creator 5 in-process bridge.

Copy this folder to CC5's Bin64/OpenPlugin only after reviewing and creating the
disabled-by-default local config.  RLPy is imported only inside CC5.
"""

import builtins
import hashlib
import hmac
import json
import math
import os
import shutil
import time
import traceback
import uuid
from pathlib import Path

import RLPy

try:
    from . import bridge_core
except ImportError:
    import bridge_core


rl_plugin_info = {"ap": "Character Creator", "ap_version": "5.0"}

_config = None
_timer = None
_timer_callback = None
_last_error = None
_requests_processed = 0
_bridge_instance_id = uuid.uuid4().hex
_project_epoch = 0
_last_project_path = None
_event_callback = None
_event_callback_id = None
_queue_paths = None
_last_status_write = 0.0
_process_owner_token = uuid.uuid4().hex
_PROCESS_REGISTRY_ATTRIBUTE = "_redmmo_cc5_mcp_bridge_runtime_v1"
_accepting_requests = False


def _status_path():
    if _config is None or not _config["enabled"]:
        raise bridge_core.BridgeValidationError(
            "bridge_disabled",
            "No status file is written until the private bridge is enabled.",
        )
    return bridge_core._confined_path(
        str(_config["queue_root"] / "status" / "cc5_bridge_status.json"),
        _config["queue_root"],
        "status file",
    )


def _capabilities():
    shaping_methods = (
        "GetShapingMorphCatergoryNames",
        "GetShapingMorphIDs",
        "GetShapingMorphDisplayNames",
        "GetShapingMorphMinMax",
        "GetShapingMorphWeight",
        "SetShapingMorphWeight",
    )
    return {
        "selected_avatar_inspection": hasattr(RLPy.RScene, "GetSelectedObjects"),
        "avatar_shaping_component": hasattr(
            RLPy.RIAvatar, "GetAvatarShapingComponent"
        ),
        "shaping_methods_present": all(
            hasattr(RLPy.RIAvatarShapingComponent, name)
            for name in shaping_methods
        ),
        "save_project_as": hasattr(RLPy.RFileIO, "SaveProject"),
        "timer_polling": hasattr(RLPy, "RPyTimer"),
    }


def _write_status(state, error=None, layout_verified=False):
    global _last_error
    if error is not None:
        _last_error = str(error)[:400]
    status = {
        "protocol_version": bridge_core.PROTOCOL_VERSION,
        "state": state,
        "heartbeat_utc": bridge_core.format_utc(),
        "product_name": str(RLPy.RApplication.GetProductName()),
        "product_version": str(RLPy.RApplication.GetProductVersion()),
        "api_version": str(RLPy.RApplication.GetApiVersion()),
        "bridge_instance_id": _bridge_instance_id,
        "project_epoch": _project_epoch,
        "capabilities": _capabilities(),
        "last_error": _last_error,
        "requests_processed": _requests_processed,
    }
    if _config is None or not _config["enabled"]:
        return
    if not layout_verified:
        bridge_core.require_private_runtime_layout(_config)
    status["status_mac"] = bridge_core.message_mac(
        status,
        _config["bridge_token"],
    )
    bridge_core.atomic_write_json(
        _status_path(),
        status,
        _config["max_message_bytes"],
    )


def _require_cc5_compatible():
    product_name = str(RLPy.RApplication.GetProductName())
    major = int(RLPy.RApplication.GetProductMajorVersion())
    if os.name != "nt" or "character creator" not in product_name.lower() or major != 5:
        raise bridge_core.BridgeValidationError(
            "host_incompatible",
            "This bridge requires Character Creator 5.x.",
        )
    capabilities = _capabilities()
    missing = [name for name, available in capabilities.items() if not available]
    if missing:
        raise bridge_core.BridgeValidationError(
            "api_incompatible",
            "Required CC5 API capabilities are absent: %s." % ", ".join(missing),
        )


def _active_avatar():
    selected = list(RLPy.RScene.GetSelectedObjects())
    avatars = [
        item
        for item in selected
        if item is not None and item.GetType() == RLPy.EObjectType_Avatar
    ]
    if len(avatars) != 1 or len(selected) != 1:
        raise bridge_core.BridgeValidationError(
            "active_character_ambiguous",
            "Select exactly one avatar in CC5 and no other scene objects.",
        )
    if hasattr(avatars[0], "IsValid") and not avatars[0].IsValid():
        raise bridge_core.BridgeValidationError(
            "active_character_invalid",
            "The selected avatar is no longer valid.",
        )
    return avatars[0]


def _current_project_path():
    current = str(RLPy.RApplication.GetCurrentProjectPath())
    return os.path.normcase(os.path.abspath(current)) if current else ""


def _bump_project_epoch():
    global _project_epoch
    _project_epoch += 1


def _refresh_project_epoch():
    global _last_project_path
    observed = _current_project_path()
    if _last_project_path is None:
        _last_project_path = observed
    elif observed != _last_project_path:
        _last_project_path = observed
        _bump_project_epoch()


def _project_identity():
    _refresh_project_epoch()
    descriptor = {
        "bridge_instance_id": _bridge_instance_id,
        "project_epoch": _project_epoch,
        "current_project_path": _current_project_path(),
    }
    return bridge_core.message_mac(descriptor, _config["bridge_token"])


def _project_summary():
    current_path = _current_project_path()
    identity = _project_identity()
    return {
        "bridge_instance_id": _bridge_instance_id,
        "project_epoch": _project_epoch,
        "project_identity": identity,
        "current_project_name": Path(current_path).name if current_path else "",
        "is_untitled": not bool(current_path),
    }


def _character_object_id(avatar):
    identifier = str(avatar.GetID())
    if not bridge_core.OBJECT_ID_RE.fullmatch(identifier):
        raise bridge_core.BridgeValidationError(
            "character_id_invalid",
            "CC5 returned an invalid avatar object ID.",
        )
    return identifier


def _file_sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            block = handle.read(1024 * 1024)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def _require_operation_binding(avatar, payload):
    if not hmac.compare_digest(
        _character_object_id(avatar),
        payload["expected_character_id"],
    ):
        raise bridge_core.BridgeValidationError(
            "character_binding_mismatch",
            "The selected avatar changed after it was inspected.",
        )
    if not hmac.compare_digest(
        _project_identity(),
        payload["expected_project_identity"],
    ):
        raise bridge_core.BridgeValidationError(
            "project_binding_mismatch",
            "The CC5 project session changed after it was inspected.",
        )


def _shaping_component(avatar):
    component = avatar.GetAvatarShapingComponent()
    if component is None or (
        hasattr(component, "IsValid") and not component.IsValid()
    ):
        raise bridge_core.BridgeValidationError(
            "shaping_unavailable",
            "The selected avatar does not expose a valid shaping component.",
        )
    return component


def _float_pair(value):
    if hasattr(value, "first") and hasattr(value, "second"):
        first, second = value.first, value.second
    elif isinstance(value, (list, tuple)) and len(value) >= 2:
        first, second = value[0], value[1]
    else:
        raise bridge_core.BridgeValidationError(
            "shaping_api_error", "CC5 returned an unreadable slider range."
        )
    minimum = _finite_host_float(
        first,
        "CC5 returned a non-finite slider minimum.",
    )
    maximum = _finite_host_float(
        second,
        "CC5 returned a non-finite slider maximum.",
    )
    return minimum, maximum


def _finite_host_float(value, message):
    try:
        numeric = float(value)
    except (TypeError, ValueError, OverflowError):
        raise bridge_core.BridgeValidationError(
            "shaping_api_error",
            message,
        )
    if not math.isfinite(numeric):
        raise bridge_core.BridgeValidationError(
            "shaping_api_error",
            message,
        )
    return numeric


def _character_summary(avatar):
    shaping = _shaping_component(avatar)
    return {
        "name": str(avatar.GetName()),
        "object_id": _character_object_id(avatar),
        "character_signature": _character_signature(avatar, shaping),
        "generation": str(avatar.GetGeneration()),
        "avatar_type": str(avatar.GetAvatarType()),
        "mesh_names": [str(name) for name in avatar.GetMeshNames()],
        "shaping_categories": [
            str(name) for name in shaping.GetShapingMorphCatergoryNames()
        ],
    }


def _character_signature(avatar, shaping=None):
    component = shaping or _shaping_component(avatar)
    categories = [
        str(name) for name in component.GetShapingMorphCatergoryNames()
    ]
    signature_data = {
        "name": str(avatar.GetName()),
        "generation": str(avatar.GetGeneration()),
        "avatar_type": str(avatar.GetAvatarType()),
        "mesh_names": [str(name) for name in avatar.GetMeshNames()],
        "shaping": [
            {
                "category": category,
                "morph_ids": [
                    str(value)
                    for value in component.GetShapingMorphIDs(category)
                ],
            }
            for category in categories
        ],
    }
    encoded = json.dumps(
        signature_data,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _all_slider_rows(shaping, requested_category):
    categories = list(shaping.GetShapingMorphCatergoryNames())
    if any(
        not isinstance(name, str) or not name
        for name in categories
    ):
        raise bridge_core.BridgeValidationError(
            "shaping_api_error",
            "CC5 returned an invalid shaping category name.",
        )
    if requested_category:
        exact = [name for name in categories if name == requested_category]
        if len(exact) != 1:
            raise bridge_core.BridgeValidationError(
                "category_not_found",
                "The requested shaping category was not found exactly once.",
            )
        categories = exact
    approved_by_id = {}
    for alias, rule in _config["morph_allowlist"].items():
        approved_by_id.setdefault(rule["morph_id"], []).append(alias)

    rows = []
    for category in categories:
        ids = list(shaping.GetShapingMorphIDs(category))
        names = list(shaping.GetShapingMorphDisplayNames(category))
        if len(ids) != len(names):
            raise bridge_core.BridgeValidationError(
                "shaping_api_error",
                "CC5 returned mismatched shaping IDs and display names.",
            )
        if any(not isinstance(value, str) or not value for value in ids):
            raise bridge_core.BridgeValidationError(
                "shaping_api_error",
                "CC5 returned an invalid shaping morph ID.",
            )
        if any(not isinstance(value, str) or not value for value in names):
            raise bridge_core.BridgeValidationError(
                "shaping_api_error",
                "CC5 returned an invalid shaping display name.",
            )
        for morph_id, display_name in zip(ids, names):
            minimum, maximum = _float_pair(
                shaping.GetShapingMorphMinMax(morph_id)
            )
            rows.append(
                {
                    "category": category,
                    "morph_id": morph_id,
                    "display_name": display_name,
                    "minimum": minimum,
                    "maximum": maximum,
                    "value": _finite_host_float(
                        shaping.GetShapingMorphWeight(morph_id),
                        "CC5 returned a non-finite shaping value.",
                    ),
                    "approved_aliases": sorted(approved_by_id.get(morph_id, [])),
                }
            )
    return rows


def _resolve_canonical_slider_row(rows, morph_id):
    if not isinstance(morph_id, str) or not morph_id:
        raise bridge_core.BridgeValidationError(
            "morph_id_invalid",
            "The approved morph ID is invalid.",
        )

    matches = []
    for row in rows:
        if not isinstance(row, dict):
            raise bridge_core.BridgeValidationError(
                "shaping_api_error",
                "CC5 returned a non-object shaping record.",
            )
        row_id = row.get("morph_id")
        if not isinstance(row_id, str) or not row_id:
            raise bridge_core.BridgeValidationError(
                "shaping_api_error",
                "CC5 returned an invalid shaping morph ID.",
            )
        if row_id == morph_id:
            matches.append(row)
    if not matches:
        raise bridge_core.BridgeValidationError(
            "morph_id_not_found",
            "The approved morph ID was not found on the selected avatar.",
        )

    canonical = None
    categories = []
    required_fields = {
        "morph_id",
        "display_name",
        "minimum",
        "maximum",
        "value",
        "approved_aliases",
    }
    for row in matches:
        category = row.get("category")
        if not isinstance(category, str) or not category:
            raise bridge_core.BridgeValidationError(
                "shaping_api_error",
                "CC5 returned an invalid shaping category.",
            )
        if not required_fields.issubset(row):
            raise bridge_core.BridgeValidationError(
                "shaping_api_error",
                "CC5 returned an incomplete shaping record.",
            )
        if (
            not isinstance(row["display_name"], str)
            or not row["display_name"]
            or any(
                isinstance(row[field], bool)
                or not isinstance(row[field], (int, float))
                or not math.isfinite(float(row[field]))
                for field in ("minimum", "maximum", "value")
            )
            or float(row["minimum"]) > float(row["maximum"])
            or not isinstance(row["approved_aliases"], list)
            or any(
                not isinstance(alias, str) or not alias
                for alias in row["approved_aliases"]
            )
        ):
            raise bridge_core.BridgeValidationError(
                "shaping_api_error",
                "CC5 returned invalid shaping record values.",
            )
        comparable = dict(row)
        comparable.pop("category")
        if canonical is None:
            canonical = comparable
        elif comparable != canonical:
            raise bridge_core.BridgeValidationError(
                "morph_id_conflict",
                "CC5 returned conflicting records for one approved morph ID.",
            )
        categories.append(category)
    result = dict(canonical)
    result["categories"] = categories
    return result


def _inspect_active_character(_payload):
    avatar = _active_avatar()
    return {
        "character": _character_summary(avatar),
        "project": _project_summary(),
    }


def _list_active_character_morphs(payload):
    avatar = _active_avatar()
    shaping = _shaping_component(avatar)
    rows = _all_slider_rows(shaping, payload["category"])
    offset = payload["offset"]
    limit = payload["limit"]
    return {
        "character_name": str(avatar.GetName()),
        "character_object_id": _character_object_id(avatar),
        "project": _project_summary(),
        "category_filter": payload["category"],
        "total": len(rows),
        "offset": offset,
        "limit": limit,
        "morphs": rows[offset : offset + limit],
    }


def _set_approved_morph(payload):
    alias = payload["morph_alias"]
    rule = _config["morph_allowlist"].get(alias)
    if rule is None:
        raise bridge_core.BridgeValidationError(
            "morph_not_approved",
            "That morph alias is not approved in the local bridge config.",
        )
    requested = float(payload["value"])
    if not rule["minimum"] <= requested <= rule["maximum"]:
        raise bridge_core.BridgeValidationError(
            "morph_value_denied",
            "Requested value is outside the configured safe range.",
        )

    avatar = _active_avatar()
    _require_operation_binding(avatar, payload)
    shaping = _shaping_component(avatar)
    row = _resolve_canonical_slider_row(
        _all_slider_rows(shaping, ""),
        rule["morph_id"],
    )
    effective_min = max(rule["minimum"], row["minimum"])
    effective_max = min(rule["maximum"], row["maximum"])
    if not effective_min <= requested <= effective_max:
        raise bridge_core.BridgeValidationError(
            "morph_value_denied",
            "Requested value is outside the live CC5 slider range.",
        )
    previous = _finite_host_float(
        shaping.GetShapingMorphWeight(rule["morph_id"]),
        "CC5 returned a non-finite shaping value.",
    )
    avatar = _active_avatar()
    _require_operation_binding(avatar, payload)
    shaping = _shaping_component(avatar)
    try:
        shaping.SetShapingMorphWeight(rule["morph_id"], requested)
        RLPy.RGlobal.ObjectModified(
            avatar,
            RLPy.EObjectModifiedType_MorphWeight,
        )
        observed = _finite_host_float(
            shaping.GetShapingMorphWeight(rule["morph_id"]),
            "CC5 returned a non-finite shaping readback.",
        )
    except Exception:
        restored = _restore_morph_value(
            avatar,
            shaping,
            rule["morph_id"],
            previous,
        )
        raise bridge_core.BridgeValidationError(
            "morph_write_failed" if restored else "morph_state_uncertain",
            (
                "CC5 rejected the approved morph write; rollback succeeded."
                if restored
                else "CC5 rejected the approved morph write and rollback could not be verified."
            ),
        )
    if abs(observed - requested) > 0.0001:
        restored = _restore_morph_value(
            avatar,
            shaping,
            rule["morph_id"],
            previous,
        )
        raise bridge_core.BridgeValidationError(
            "morph_write_unverified" if restored else "morph_state_uncertain",
            "CC5 did not report the requested shaping value; rollback %s."
            % ("succeeded" if restored else "could not be verified"),
        )
    return {
        "character_name": str(avatar.GetName()),
        "morph_alias": alias,
        "morph_id": rule["morph_id"],
        "label": rule["label"],
        "previous_value": previous,
        "value": observed,
    }


def _restore_morph_value(avatar, shaping, morph_id, previous):
    try:
        shaping.SetShapingMorphWeight(morph_id, previous)
        RLPy.RGlobal.ObjectModified(
            avatar,
            RLPy.EObjectModifiedType_MorphWeight,
        )
        observed = float(shaping.GetShapingMorphWeight(morph_id))
        if not math.isfinite(observed):
            return False
        return abs(observed - previous) <= 0.0001
    except Exception:
        return False


def _restore_linked_preset_values(avatar, shaping, changes):
    restored = True
    for change in reversed(changes):
        try:
            shaping.SetShapingMorphWeight(
                change["morph_id"],
                change["previous_value"],
            )
            RLPy.RGlobal.ObjectModified(
                avatar,
                RLPy.EObjectModifiedType_MorphWeight,
            )
        except Exception:
            restored = False
    for change in changes:
        try:
            observed = float(
                shaping.GetShapingMorphWeight(change["morph_id"])
            )
            if (
                not math.isfinite(observed)
                or abs(observed - change["previous_value"]) > 0.0001
            ):
                restored = False
        except Exception:
            restored = False
    return restored


def _apply_approved_linked_preset(payload):
    preset_alias = payload["preset_alias"]
    preset = _config["linked_presets"].get(preset_alias)
    if preset is None:
        raise bridge_core.BridgeValidationError(
            "linked_preset_not_approved",
            "That linked preset is not approved in the local bridge config.",
        )
    if not hmac.compare_digest(
        payload["expected_preset_digest"],
        preset["definition_digest"],
    ):
        raise bridge_core.BridgeValidationError(
            "linked_preset_definition_mismatch",
            "The linked preset changed after the external bridge loaded it.",
        )

    avatar = _active_avatar()
    _require_operation_binding(avatar, payload)
    shaping = _shaping_component(avatar)
    signature = _character_signature(avatar, shaping)
    if not hmac.compare_digest(
        signature,
        preset["required_character_signature"],
    ):
        raise bridge_core.BridgeValidationError(
            "linked_preset_character_denied",
            "The selected avatar is not the character approved for this preset.",
        )

    slider_rows = _all_slider_rows(shaping, "")
    changes = []
    for role in ("body", "head"):
        member = preset[role]
        rule = _config["morph_allowlist"].get(member["morph_alias"])
        if rule is None:
            raise bridge_core.BridgeValidationError(
                "linked_preset_invalid",
                "The approved linked preset references a missing morph rule.",
            )
        row = _resolve_canonical_slider_row(
            slider_rows,
            rule["morph_id"],
        )
        requested = float(member["value"])
        effective_min = max(rule["minimum"], row["minimum"])
        effective_max = min(rule["maximum"], row["maximum"])
        if not effective_min <= requested <= effective_max:
            raise bridge_core.BridgeValidationError(
                "morph_value_denied",
                "A linked preset value is outside the live CC5 slider range.",
            )
        changes.append(
            {
                "role": role,
                "morph_alias": member["morph_alias"],
                "morph_id": rule["morph_id"],
                "label": rule["label"],
                "previous_value": _finite_host_float(
                    shaping.GetShapingMorphWeight(rule["morph_id"]),
                    "CC5 returned a non-finite linked-preset baseline.",
                ),
                "requested_value": requested,
            }
        )

    avatar = _active_avatar()
    _require_operation_binding(avatar, payload)
    shaping = _shaping_component(avatar)
    if not hmac.compare_digest(
        _character_signature(avatar, shaping),
        preset["required_character_signature"],
    ):
        raise bridge_core.BridgeValidationError(
            "linked_preset_character_denied",
            "The selected avatar changed before the linked preset write.",
        )

    character_name = str(avatar.GetName())
    character_object_id = _character_object_id(avatar)
    failure_code = "linked_preset_write_failed"
    try:
        for change in changes:
            shaping.SetShapingMorphWeight(
                change["morph_id"],
                change["requested_value"],
            )
            RLPy.RGlobal.ObjectModified(
                avatar,
                RLPy.EObjectModifiedType_MorphWeight,
            )
            observed = _finite_host_float(
                shaping.GetShapingMorphWeight(change["morph_id"]),
                "CC5 returned a non-finite linked-preset readback.",
            )
            if abs(observed - change["requested_value"]) > 0.0001:
                failure_code = "linked_preset_write_unverified"
                raise RuntimeError("linked preset readback mismatch")
            change["value"] = observed
    except Exception:
        restored = _restore_linked_preset_values(
            avatar,
            shaping,
            changes,
        )
        raise bridge_core.BridgeValidationError(
            failure_code if restored else "linked_preset_state_uncertain",
            (
                "CC5 rejected the linked preset; rollback succeeded."
                if restored
                else "CC5 rejected the linked preset and rollback could not be verified."
            ),
        )

    return {
        "character_name": character_name,
        "character_object_id": character_object_id,
        "character_signature": preset["required_character_signature"],
        "preset_alias": preset_alias,
        "label": preset["label"],
        "changes": changes,
    }


def _save_project_as(payload):
    if not hmac.compare_digest(
        _project_identity(),
        payload["expected_project_identity"],
    ):
        raise bridge_core.BridgeValidationError(
            "project_binding_mismatch",
            "The CC5 project session changed after it was inspected.",
        )
    target = bridge_core.safe_save_target(
        _config,
        payload["version_name"],
    )
    bridge_core.require_private_runtime_layout(_config)
    staging = bridge_core.unique_save_staging_target(_config)
    publish_temp = bridge_core.unique_save_staging_target(_config)
    source_path_before = _current_project_path()
    keep_staging = False
    staging_owned = False
    publish_temp_owned = False
    binding_known = False
    try:
        if staging.exists() or publish_temp.exists():
            raise bridge_core.BridgeValidationError(
                "save_staging_collision",
                "A generated private staging name already exists.",
            )
        if not hmac.compare_digest(
            _project_identity(),
            payload["expected_project_identity"],
        ):
            raise bridge_core.BridgeValidationError(
                "project_binding_mismatch",
                "The CC5 project session changed before the snapshot began.",
            )
        result = RLPy.RFileIO.SaveProject(str(staging))
        if hasattr(result, "IsError") and result.IsError():
            raise bridge_core.BridgeValidationError(
                "save_failed",
                "CC5 SaveProject returned status code %s."
                % str(result.GetStatusCode()),
            )
        if (
            not staging.is_file()
            or staging.is_symlink()
            or staging.stat().st_size <= 0
        ):
            raise bridge_core.BridgeValidationError(
                "save_unverified",
                "CC5 did not create a valid private staging snapshot.",
            )
        staging_owned = True
        try:
            source_path_after = _current_project_path()
            binding_known = True
        except Exception:
            raise bridge_core.BridgeValidationError(
                "project_binding_unknown_after_save",
                "CC5 saved a staging snapshot, but its active project path could not be verified.",
            )
        keep_staging = (
            os.path.normcase(source_path_after)
            == os.path.normcase(str(staging))
        )
        staging_size = staging.stat().st_size
        staging_digest = _file_sha256(staging)
        with staging.open("rb") as source, publish_temp.open("xb") as output:
            publish_temp_owned = True
            shutil.copyfileobj(source, output, 1024 * 1024)
            output.flush()
            os.fsync(output.fileno())
        if (
            publish_temp.stat().st_size != staging_size
            or _file_sha256(publish_temp) != staging_digest
            or staging.stat().st_size != staging_size
            or _file_sha256(staging) != staging_digest
        ):
            raise bridge_core.BridgeValidationError(
                "save_copy_unverified",
                "The private snapshot changed during publication.",
            )
        publish_identity = publish_temp.stat()
        try:
            bridge_core.publish_file_no_replace(publish_temp, target)
        except FileExistsError:
            raise bridge_core.BridgeValidationError(
                "save_target_exists",
                "The requested project version already exists.",
            )
        final_identity = target.stat()
        if (
            publish_identity.st_dev != final_identity.st_dev
            or publish_identity.st_ino != final_identity.st_ino
            or final_identity.st_size != staging_size
            or _file_sha256(target) != staging_digest
        ):
            raise bridge_core.BridgeValidationError(
                "save_publish_unverified",
                "The final project snapshot identity could not be verified.",
            )
        return {
            "version_name": payload["version_name"],
            "saved_path": str(target),
            "saved_sha256": staging_digest,
            "saved_bytes": staging_size,
            "overwrote_existing": False,
            "session_rebound_to_final": (
                os.path.normcase(source_path_after)
                == os.path.normcase(str(target))
            ),
            "session_rebound_to_private_staging": keep_staging,
            "source_project_changed_during_save": (
                source_path_before != source_path_after
            ),
        }
    finally:
        bridge_core.cleanup_owned_file(publish_temp, publish_temp_owned)
        bound_to_staging = keep_staging
        if staging_owned:
            try:
                current_path = _current_project_path()
                binding_known = True
                bound_to_staging = (
                    os.path.normcase(current_path)
                    == os.path.normcase(str(staging))
                )
            except Exception:
                binding_known = False
        bridge_core.cleanup_owned_file(
            staging,
            staging_owned and binding_known and not bound_to_staging,
        )


_HANDLERS = {
    "inspect_active_character": _inspect_active_character,
    "list_active_character_morphs": _list_active_character_morphs,
    "set_approved_morph": _set_approved_morph,
    "apply_approved_linked_preset": _apply_approved_linked_preset,
    "save_project_as": _save_project_as,
}


def _queue_dirs(revalidate=True):
    if revalidate:
        bridge_core.require_private_runtime_layout(_config)
    root = _config["queue_root"]
    result = {
        name: bridge_core._confined_path(
            str(root / name),
            root,
            "%s directory" % name,
        )
        for name in (
            "requests",
            "processing",
            "responses",
            "completed",
            "quarantine",
            "status",
        )
    }
    return result


def _safe_request_identity(message):
    if not isinstance(message, dict):
        return None, None
    request_id = message.get("request_id")
    operation = message.get("operation")
    if (
        not isinstance(request_id, str)
        or not bridge_core.REQUEST_ID_RE.fullmatch(request_id)
        or operation not in bridge_core.ALLOWED_OPERATIONS
    ):
        return None, None
    return request_id, operation


def _process_one_request():
    global _requests_processed
    if not _accepting_requests:
        return False
    dirs = _queue_paths
    if dirs is None:
        return False
    candidates = sorted(dirs["requests"].glob("*.request.json"))
    if not candidates:
        return False
    bridge_core.require_private_runtime_layout(_config)
    candidates = sorted(dirs["requests"].glob("*.request.json"))
    if not candidates:
        return False
    request_path = candidates[0]
    processing_path = dirs["processing"] / request_path.name
    try:
        os.replace(str(request_path), str(processing_path))
    except OSError:
        return False

    request = None
    request_id = None
    operation = None
    try:
        request = bridge_core.read_json_limited(
            processing_path,
            _config["max_message_bytes"],
        )
        request_id, operation = _safe_request_identity(request)
        bridge_core.validate_request(request, _config)
        completed_path = dirs["completed"] / processing_path.name
        response_path = dirs["responses"] / (
            request_id + ".response.json"
        )
        if completed_path.exists() or response_path.exists():
            raise bridge_core.BridgeValidationError(
                "duplicate_request",
                "This request ID has already been processed.",
            )
        result = _HANDLERS[operation](request["payload"])
        response = bridge_core.success_response(
            request,
            result,
            _config["bridge_token"],
        )
        bridge_core.atomic_write_json(
            response_path,
            response,
            _config["max_message_bytes"],
        )
        os.replace(str(processing_path), str(completed_path))
        _requests_processed += 1
    except bridge_core.BridgeValidationError as exc:
        if request_id is not None and operation is not None:
            failure_path = dirs["responses"] / (
                request_id + ".response.json"
            )
            if not failure_path.exists():
                response = bridge_core.failure_response(
                    request_id,
                    operation,
                    exc.code,
                    exc.message,
                    _config["bridge_token"],
                )
                bridge_core.atomic_write_json(
                    failure_path,
                    response,
                    _config["max_message_bytes"],
                )
        if processing_path.exists():
            quarantine = dirs["quarantine"] / processing_path.name
            os.replace(str(processing_path), str(quarantine))
    except Exception:
        if request_id is not None and operation is not None:
            failure_path = dirs["responses"] / (
                request_id + ".response.json"
            )
            if not failure_path.exists():
                response = bridge_core.failure_response(
                    request_id,
                    operation,
                    "cc5_operation_failed",
                    "CC5 failed the allowlisted operation without exposing host details.",
                    _config["bridge_token"],
                )
                bridge_core.atomic_write_json(
                    failure_path,
                    response,
                    _config["max_message_bytes"],
                )
        if processing_path.exists():
            quarantine = dirs["quarantine"] / processing_path.name
            os.replace(str(processing_path), str(quarantine))
        raise
    return True


class _BridgeTimerCallback(RLPy.RPyTimerCallback):
    def __init__(self):
        RLPy.RPyTimerCallback.__init__(self)

    def Timeout(self):
        global _last_status_write
        if not _accepting_requests:
            return
        try:
            _refresh_project_epoch()
            processed = _process_one_request()
            now = time.monotonic()
            if bridge_core.interval_due(
                now,
                _last_status_write,
                1.0,
            ):
                _write_status("running", layout_verified=processed)
                _last_status_write = now
        except Exception as exc:
            now = time.monotonic()
            if bridge_core.interval_due(now, _last_status_write, 1.0):
                try:
                    _write_status("error", "%s: %s" % (type(exc).__name__, exc))
                except Exception:
                    traceback.print_exc()
                finally:
                    _last_status_write = now


class _ProjectEventCallback(RLPy.REventCallback):
    def __init__(self):
        RLPy.REventCallback.__init__(self)

    def OnBeforeLoadFile(self, _file_type):
        try:
            _bump_project_epoch()
        except Exception:
            traceback.print_exc()

    def OnBeforeLoadFileWithPath(self, _file_type, _file_path):
        try:
            _bump_project_epoch()
        except Exception:
            traceback.print_exc()

    def OnAfterFileLoaded(self, _file_type):
        try:
            _bump_project_epoch()
            _refresh_project_epoch()
        except Exception:
            traceback.print_exc()

    def OnAfterFileLoadedWithPath(self, _file_type, _file_path):
        try:
            _bump_project_epoch()
            _refresh_project_epoch()
        except Exception:
            traceback.print_exc()

    def OnFileSaved(self, _file_type, _project_name):
        try:
            _refresh_project_epoch()
        except Exception:
            traceback.print_exc()


def _release_process_slot():
    current = getattr(builtins, _PROCESS_REGISTRY_ATTRIBUTE, None)
    if (
        isinstance(current, dict)
        and current.get("owner_token") == _process_owner_token
    ):
        delattr(builtins, _PROCESS_REGISTRY_ATTRIBUTE)


def _stop_bridge(require_success=False):
    global _timer, _timer_callback, _event_callback, _event_callback_id
    global _queue_paths, _accepting_requests
    _accepting_requests = False
    teardown_failed = False
    if _timer is not None:
        try:
            if _timer.IsRunning():
                _timer.Stop()
            _timer.UnregisterPyTimerCallback()
        except Exception:
            teardown_failed = True
        else:
            _timer = None
            _timer_callback = None
    else:
        _timer_callback = None
    if _event_callback_id is not None:
        try:
            RLPy.REventHandler.UnregisterCallback(_event_callback_id)
        except Exception:
            teardown_failed = True
        else:
            _event_callback = None
            _event_callback_id = None
    else:
        _event_callback = None
    if not teardown_failed:
        _queue_paths = None
        _release_process_slot()
    if teardown_failed and require_success:
        raise bridge_core.BridgeValidationError(
            "bridge_teardown_failed",
            "The previous CC5 bridge instance could not be stopped safely.",
        )
    return not teardown_failed


def _claim_process_slot():
    previous = getattr(builtins, _PROCESS_REGISTRY_ATTRIBUTE, None)
    if previous is not None and not isinstance(previous, dict):
        raise bridge_core.BridgeValidationError(
            "bridge_registry_invalid",
            "The CC5 bridge process registry is not trustworthy.",
        )
    if isinstance(previous, dict):
        if previous.get("owner_token") == _process_owner_token:
            return
        previous_stop = previous.get("stop")
        if not callable(previous_stop):
            raise bridge_core.BridgeValidationError(
                "bridge_registry_invalid",
                "The prior CC5 bridge instance has no safe teardown hook.",
            )
        stopped = previous_stop(require_success=True)
        if (
            stopped is not True
            or getattr(builtins, _PROCESS_REGISTRY_ATTRIBUTE, None) is not None
        ):
            raise bridge_core.BridgeValidationError(
                "bridge_teardown_failed",
                "The prior CC5 bridge instance still owns the process slot.",
            )
    setattr(
        builtins,
        _PROCESS_REGISTRY_ATTRIBUTE,
        {
            "owner_token": _process_owner_token,
            "stop": _stop_bridge,
        },
    )


def _start_bridge():
    global _config, _timer, _timer_callback, _last_error
    global _bridge_instance_id, _project_epoch, _last_project_path
    global _event_callback, _event_callback_id
    global _queue_paths, _last_status_write, _accepting_requests
    _stop_bridge(require_success=True)
    _last_error = None
    _bridge_instance_id = uuid.uuid4().hex
    _project_epoch = 0
    _last_project_path = None
    _last_status_write = 0.0
    _accepting_requests = False
    _claim_process_slot()
    _config = bridge_core.load_config()
    _require_cc5_compatible()
    if not _config["enabled"]:
        return
    _queue_paths = _queue_dirs()
    _last_project_path = _current_project_path()
    _event_callback = _ProjectEventCallback()
    _event_callback_id = RLPy.REventHandler.RegisterCallback(_event_callback)
    _timer_callback = _BridgeTimerCallback()
    _timer = RLPy.RPyTimer()
    _timer.SetInterval(
        max(50, int(_config["poll_interval_seconds"] * 1000.0))
    )
    _timer.RegisterPyTimerCallback(_timer_callback)
    _write_status("running")
    _accepting_requests = True
    _timer.Start()


def initialize_plugin():
    try:
        _start_bridge()
    except Exception as exc:
        _stop_bridge(require_success=False)
        try:
            _write_status("error", "%s: %s" % (type(exc).__name__, exc))
        except Exception:
            pass
        traceback.print_exc()


def run_script():
    """Manual Script > Load Python entry point; reloads the local config."""

    initialize_plugin()


def shutdown_plugin():
    """Best-effort cleanup for hosts that call a shutdown hook."""

    stopped = _stop_bridge(require_success=False)
    try:
        if stopped:
            _write_status("stopped")
        else:
            _write_status(
                "error",
                "BridgeValidationError: prior callbacks did not stop cleanly.",
            )
    except Exception:
        pass


# CC5's loader imports this module under a host-managed name rather than
# __main__.  This module is a bridge entry point, so loading it is the explicit
# activation action; _start_bridge is idempotent and first tears down any prior
# timer/callback registration.
run_script()
