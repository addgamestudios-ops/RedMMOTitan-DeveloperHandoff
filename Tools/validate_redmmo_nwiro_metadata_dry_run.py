"""Validate the offline-only NWIRO metadata dry-run contract.

This tool does not launch Unreal, connect to MCP, call NWIRO, load assets,
write Unreal packages, or contact providers. It authenticates the pinned
project/plugin/source-selection inputs and proves that the future client-side
contract is a singleton positive allowlist for ``find_assets`` with every
query disabled.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
from pathlib import Path, PurePosixPath
from typing import Any, Iterable


DEFAULT_CONTRACT = Path(
    r"D:\RedMMOTitan\Build\Automation"
    r"\redmmo_nwiro_metadata_dry_run_contract_v1.json"
)
DEFAULT_DIAGNOSTICS_ROOT = Path(r"D:\RedMMOTitanWindowsData\Diagnostics")
MAX_JSON_BYTES = 2 * 1024 * 1024
SHA256_RE = re.compile(r"^[0-9A-F]{64}$")

EXPECTED_TOP_LEVEL_KEYS = {
    "schema_version",
    "contract_id",
    "status",
    "evidence_class",
    "execution",
    "project",
    "plugins",
    "source_selection",
    "data_boundary",
    "tool_policy",
    "query_templates",
    "known_blockers",
    "future_runtime_sequence",
}
EXECUTION_KEYS = {
    "execution_authorized",
    "unreal_launch_allowed",
    "mcp_initialize_allowed",
    "mcp_tools_list_allowed",
    "mcp_tool_call_allowed",
    "nwiro_chat_allowed",
    "network_allowed",
    "provider_call_allowed",
    "credit_use_allowed",
    "nwiro_or_unreal_file_write_allowed",
    "validator_diagnostic_report_publication_allowed",
    "asset_load_allowed",
    "asset_import_allowed",
    "asset_migration_allowed",
    "map_or_actor_mutation_allowed",
}
PROJECT_KEYS = {"uproject_path", "uproject_sha256", "runtime_state"}
PLUGIN_KEYS = {
    "plugin_id",
    "version",
    "role",
    "descriptor_path",
    "descriptor_sha256",
    "enabled_in_project",
    "module_startup_verified",
    "in_process_mcp_server_verified",
    "binary_file",
    "source_files",
}
SOURCE_FILE_KEYS = {"path", "bytes", "sha256"}
SOURCE_SELECTION_KEYS = {
    "request_path",
    "request_sha256",
    "manifest_path",
    "manifest_sha256",
    "manifest_semantic_sha256",
    "selected_primary_count",
    "offline_reference_closure_count",
    "pack_source_tree_sha256",
    "selection_ready",
    "migration_ready",
    "nwiro_ready",
    "map_authoring_ready",
    "source_reauthentication_required_before_runtime",
}
DATA_BOUNDARY_KEYS = {
    "all_source_packs_allow_usage_with_ai",
    "vendor_or_derived_bytes_may_be_uploaded",
    "reference_images_may_be_uploaded",
    "thumbnails_may_be_rendered",
    "asset_properties_may_be_loaded",
    "remote_model_may_receive_metadata",
    "local_loopback_metadata_query_may_be_considered_after_all_runtime_gates",
    "permitted_response_fields_after_authorization",
}
TOOL_POLICY_KEYS = {
    "default_action",
    "unknown_tools",
    "unknown_namespaces",
    "allowed_tool_definition_exact_match_required",
    "input_schema_exact_match_required",
    "future_single_probe_candidate_id",
    "allowlist",
    "explicit_denied_tools",
    "denied_namespaces",
    "denied_tool_prefixes",
}
ALLOWLIST_KEYS = {
    "tool_name",
    "implementation",
    "plugin_input_properties",
    "wrapper_required_arguments",
    "observed_vendor_input_schema_sha256",
    "observed_vendor_tool_definition_sha256",
    "future_mcp_method",
    "additional_arguments_allowed",
    "max_results",
    "response_requires_exact_single_identity_match",
}
QUERY_KEYS = {
    "stable_candidate_id",
    "pack_id",
    "tool_name",
    "execution_enabled",
    "asset_files_present_in_active_project",
    "asset_registry_visibility_verified",
    "arguments",
    "expected_result",
}
QUERY_ARGUMENT_KEYS = {"searchTerm", "classFilter", "path", "maxResults"}
QUERY_RESULT_KEYS = {"name", "path", "class"}
KNOWN_BLOCKER_KEYS = {
    "nwiro_pro_environment_workflow_runtime_proven",
    "integration_kit_mcp_runtime_proven",
    "tools_list_observed",
    "metadata_query_observed",
    "predispatch_wrapper_implemented",
    "raw_mcp_direct_path_blocked",
    "integration_kit_headless_permission_bypass_fixed_in_vendor_source",
    "paid_provider_bridge_null_bypass_fixed_in_vendor_source",
    "paid_provider_tools_blocked_by_this_contract",
    "rights_and_noai_boundary_reviewed",
    "ue58_compatibility_reviewed",
    "authoritative_asset_registry_dependency_closure_reviewed",
    "isolated_migration_approved",
    "mini_hub_map_created",
    "real_gpu_acceptance_complete",
}
FUTURE_STEP_KEYS = {"step", "complete"}

EXPECTED_RESPONSE_FIELDS = [
    "success",
    "assets",
    "count",
    "name",
    "path",
    "class",
]
EXPECTED_PLUGIN_PROPERTIES = [
    "searchTerm",
    "classFilter",
    "path",
    "maxResults",
]
EXPECTED_DENIED_NAMESPACES = ["plugin.", "ue.", "mcp."]
EXPECTED_DENIED_PREFIXES = [
    "apply_",
    "create_",
    "delete_",
    "duplicate_",
    "edit_",
    "erase_",
    "execute_",
    "generate_",
    "import_",
    "paint_",
    "rename_",
    "save_",
    "set_",
    "spawn_",
    "take_",
]
REQUIRED_EXPLICIT_DENIALS = {
    "read_asset",
    "get_asset_thumbnail",
    "find_static_meshes",
    "spawn_actor",
    "execute_python",
    "create_landscape",
    "set_landscape_material",
    "add_foliage_type",
    "paint_foliage",
    "erase_foliage",
    "create_pcg_graph",
    "pcg_generate",
    "create_material",
    "apply_material",
    "save_level",
    "import_data_table_json",
    "generate_3d_model_meshy",
    "generate_texture_meshy",
    "generate_3d_model_tripo",
    "list_voices_elevenlabs",
    "generate_voice_elevenlabs",
    "generate_sfx_elevenlabs",
    "generate_music_elevenlabs",
    "generate_material_fal",
}
EXPECTED_FUTURE_STEPS = [
    "verify_module_startup",
    "initialize_loopback_mcp",
    "observe_tools_list_and_enforce_exact_allowlist",
    "perform_one_local_exact_identity_find_assets_query",
]
EXPECTED_PLUGIN_IDS = ["nwiro_pro", "nwiro_integration_kit"]
EXPECTED_PROJECT = {
    "uproject_path": "D:/RedMMOTitan/Titan.uproject",
    "uproject_sha256": (
        "0EB6D5622267A520C829846C3A66E81A3BDFE9A9931D7F98138C754A84A66B23"
    ),
    "runtime_state": "not_started_not_verified",
}
EXPECTED_PLUGINS = [
    {
        "plugin_id": "nwiro_pro",
        "version": "1.1.9",
        "role": "environment_authoring_ui_not_runtime_proven",
        "descriptor_path": (
            "D:/UE_5.8/Engine/Plugins/Marketplace/"
            "NWIROAIP1a0f5c32b7eeV3/Nwiro.uplugin"
        ),
        "descriptor_sha256": (
            "2E264C661C1DE87207031F6607FE0D97C375511085091BC742AA298DF7EEB79D"
        ),
        "enabled_in_project": True,
        "module_startup_verified": False,
        "in_process_mcp_server_verified": False,
        "binary_file": {
            "path": (
                "D:/UE_5.8/Engine/Plugins/Marketplace/"
                "NWIROAIP1a0f5c32b7eeV3/Binaries/Win64/UnrealEditor-Nwiro.dll"
            ),
            "bytes": 3159040,
            "sha256": (
                "E76E6EE3A609E424A8116AEB7A5EDE180CF20055679707CEFA964A9D4BF08453"
            ),
        },
        "source_files": [
            {
                "path": (
                    "D:/UE_5.8/Engine/Plugins/Marketplace/"
                    "NWIROAIP1a0f5c32b7eeV3/Source/Nwiro/Private/"
                    "NwiroToolDispatch.cpp"
                ),
                "bytes": 154843,
                "sha256": (
                    "E26EB78630F51311D3A0536F68EEA2CA37792E06B3E254F70B5042865DFE10FA"
                ),
            },
            {
                "path": (
                    "D:/UE_5.8/Engine/Plugins/Marketplace/"
                    "NWIROAIP1a0f5c32b7eeV3/Source/Nwiro/Private/"
                    "NwiroAssetTools.cpp"
                ),
                "bytes": 14018,
                "sha256": (
                    "F558B723A3927E2D6F01015A3EEC16F5D55CDF8CD498AE5604B35AB5F6F6F189"
                ),
            },
        ],
    },
    {
        "plugin_id": "nwiro_integration_kit",
        "version": "1.0.9",
        "role": "future_loopback_mcp_transport_not_runtime_proven",
        "descriptor_path": (
            "D:/UE_5.8/Engine/Plugins/Marketplace/"
            "NWIROAIIf0b7fbfe049eV4/NwiroIntegrationKit.uplugin"
        ),
        "descriptor_sha256": (
            "D6CCBFA2F08D478F0C53C67E0D8FCD5FF275C57948425D55D560309AD1C60B2E"
        ),
        "enabled_in_project": True,
        "module_startup_verified": False,
        "in_process_mcp_server_verified": False,
        "binary_file": {
            "path": (
                "D:/UE_5.8/Engine/Plugins/Marketplace/"
                "NWIROAIIf0b7fbfe049eV4/Binaries/Win64/"
                "UnrealEditor-NwiroIntegrationKit.dll"
            ),
            "bytes": 3491840,
            "sha256": (
                "6C72757C068FAD28174C9A2F2F4960C6FA69C908E993E854AC94454540A43C0C"
            ),
        },
        "source_files": [
            {
                "path": (
                    "D:/UE_5.8/Engine/Plugins/Marketplace/"
                    "NWIROAIIf0b7fbfe049eV4/Source/NwiroIntegrationKit/Private/"
                    "NwiroIKMCPServer.cpp"
                ),
                "bytes": 199619,
                "sha256": (
                    "34C1BB2E81A7FFF742D043EC8E983783C047BA9C5ABBA4BE9CDB4806AD7CD8D7"
                ),
            },
            {
                "path": (
                    "D:/UE_5.8/Engine/Plugins/Marketplace/"
                    "NWIROAIIf0b7fbfe049eV4/Source/NwiroIntegrationKit/Private/"
                    "NwiroIKAssetTools.cpp"
                ),
                "bytes": 14823,
                "sha256": (
                    "E30B47D984781D45B5C34B9C8F595AED9769725F80F2BB7223889C1E6C5FC519"
                ),
            },
        ],
    },
]
EXPECTED_SOURCE_SELECTION = {
    "request_path": (
        "D:/RedMMOTitan/Build/Automation/"
        "redmmo_crosspack_minihub_selection_request_v1.json"
    ),
    "request_sha256": (
        "C2791F1FD3D4472D8B433E964335E5BFE44B449C64AE9D9500497B050BC2DF09"
    ),
    "manifest_path": (
        "D:/RedMMOTitanWindowsData/Diagnostics/"
        "M07_CrosspackMinihubSelection_20260724_2209Z/selection_manifest_v3.json"
    ),
    "manifest_sha256": (
        "331427762643D2C3A5CFEF7FAB88C5985310B1768C1683BB0685D53C859CAC37"
    ),
    "manifest_semantic_sha256": (
        "8D61DE6B1A7561E746BC893A2C1BBB440589D3CC80DDD65801C6A8D529512517"
    ),
    "selected_primary_count": 9,
    "offline_reference_closure_count": 68,
    "pack_source_tree_sha256": {
        "fab.12ec20bd-ce21-4d3d-8051-13ffb0fe851e": (
            "69F083AF85959AF5DA257D36B5B374C3766C242791D9ED9DC9452F5C445EC661"
        ),
        "fab.934c1286-7388-4aa5-a300-e0a7cdf65675": (
            "610F447CAF47269676D0301330411F3A9B42E04DDF0D18782E7D61085A211732"
        ),
    },
    "selection_ready": False,
    "migration_ready": False,
    "nwiro_ready": False,
    "map_authoring_ready": False,
    "source_reauthentication_required_before_runtime": True,
}
EXPECTED_VENDOR_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "searchTerm": {"type": "string"},
        "classFilter": {"type": "string"},
        "path": {"type": "string"},
        "maxResults": {"type": "number"},
    },
}
EXPECTED_VENDOR_INPUT_SCHEMA_SHA256 = (
    "1B0BFC2EAD394C9C424B047137B0DBFEFE4B091605A7DA979912D4C6EA697658"
)
EXPECTED_VENDOR_ANNOTATIONS = {
    "readOnlyHint": True,
    "destructiveHint": False,
    "idempotentHint": True,
}
EXPECTED_VENDOR_TOOL_DEFINITION = {
    "name": "find_assets",
    "description": "Search assets by name and optional class filter",
    "inputSchema": EXPECTED_VENDOR_INPUT_SCHEMA,
    "annotations": EXPECTED_VENDOR_ANNOTATIONS,
}
EXPECTED_VENDOR_TOOL_DEFINITION_SHA256 = (
    "58DCD431CFCB943C9C2B8215F7FF8D69B43450A5CB4959377D47BFBFEE4C70C2"
)
EXPECTED_QUERY_CANDIDATES = [
    (
        "RED-FAB-ASSET-8021792003EC13E7D10DBB1B",
        "fab.12ec20bd-ce21-4d3d-8051-13ffb0fe851e",
        "Texture2D",
        "/Game/Zenscape_Savanna/Landscape/Texture/"
        "T_Sand_basecolor.T_Sand_basecolor",
        True,
    ),
    (
        "RED-FAB-ASSET-0136F15C7D44ADF6C94C719B",
        "fab.12ec20bd-ce21-4d3d-8051-13ffb0fe851e",
        "Texture2D",
        "/Game/Zenscape_Savanna/Landscape/Texture/T_Sand_normal.T_Sand_normal",
        True,
    ),
    (
        "RED-FAB-ASSET-A4ECC3D88041390347B5EB9E",
        "fab.12ec20bd-ce21-4d3d-8051-13ffb0fe851e",
        "Texture2D",
        "/Game/Zenscape_Savanna/Landscape/Texture/"
        "T_Sand_Roughness.T_Sand_Roughness",
        True,
    ),
    (
        "RED-FAB-ASSET-55D22F834072AFF6229BB14A",
        "fab.12ec20bd-ce21-4d3d-8051-13ffb0fe851e",
        "StaticMesh",
        "/Game/Zenscape_Savanna/Model/Rocks/"
        "SM_RockRoundDesert_02.SM_RockRoundDesert_02",
        True,
    ),
    (
        "RED-FAB-ASSET-A4F6D5680DC132465128D65B",
        "fab.12ec20bd-ce21-4d3d-8051-13ffb0fe851e",
        "StaticMesh",
        "/Game/Zenscape_Savanna/Model/Tree/SM_AcaciaTree_01.SM_AcaciaTree_01",
        True,
    ),
    (
        "RED-FAB-ASSET-F3C4A00B0686FACCA17356E9",
        "fab.934c1286-7388-4aa5-a300-e0a7cdf65675",
        "Blueprint",
        "/Game/Zenscape_Island/Blueprint/BP_WaterPlane.BP_WaterPlane",
        False,
    ),
    (
        "RED-FAB-ASSET-3897AB32061911E704F9DEB4",
        "fab.934c1286-7388-4aa5-a300-e0a7cdf65675",
        "StaticMesh",
        "/Game/Zenscape_Island/Model/Plants/SM_Coral_01.SM_Coral_01",
        False,
    ),
    (
        "RED-FAB-ASSET-71C6AF42FBE6C8C807395EC0",
        "fab.934c1286-7388-4aa5-a300-e0a7cdf65675",
        "StaticMesh",
        "/Game/Zenscape_Island/Model/Plants/SM_Plant_01.SM_Plant_01",
        False,
    ),
    (
        "RED-FAB-ASSET-020D6DAAE70219B6F907C75B",
        "fab.934c1286-7388-4aa5-a300-e0a7cdf65675",
        "StaticMesh",
        "/Game/Zenscape_Island/Model/Tree/"
        "SM_CoconutTree_01.SM_CoconutTree_01",
        False,
    ),
]


class NwiroContractError(RuntimeError):
    """Raised when the dry-run contract fails closed."""


def expected_query_templates() -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for candidate_id, pack_id, asset_class, object_path, active_present in (
        EXPECTED_QUERY_CANDIDATES
    ):
        package_name, object_name = object_path.rsplit(".", 1)
        parent = PurePosixPath(package_name).parent.as_posix()
        records.append(
            {
                "stable_candidate_id": candidate_id,
                "pack_id": pack_id,
                "tool_name": "find_assets",
                "execution_enabled": False,
                "asset_files_present_in_active_project": active_present,
                "asset_registry_visibility_verified": False,
                "arguments": {
                    "searchTerm": object_name,
                    "classFilter": asset_class,
                    "path": parent,
                    "maxResults": 2,
                },
                "expected_result": {
                    "name": object_name,
                    "path": object_path,
                    "class": asset_class,
                },
            }
        )
    return records


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise NwiroContractError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise NwiroContractError(f"non-finite JSON number: {value}")


def _validate_finite(value: Any, path: str = "$") -> None:
    if isinstance(value, bool) or value is None or isinstance(value, (str, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise NwiroContractError(f"non-finite value at {path}")
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _validate_finite(item, f"{path}[{index}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise NwiroContractError(f"non-string key at {path}")
            _validate_finite(item, f"{path}.{key}")
        return
    raise NwiroContractError(f"unsupported JSON value at {path}")


def read_snapshot(path: Path, max_bytes: int) -> bytes:
    if type(max_bytes) is not int or max_bytes <= 0:
        raise NwiroContractError("snapshot byte limit must be a positive integer")
    try:
        with path.open("rb") as handle:
            payload = handle.read(max_bytes + 1)
    except OSError as exc:
        raise NwiroContractError(f"cannot read {path}: {exc}") from exc
    if not payload or len(payload) > max_bytes:
        raise NwiroContractError(f"snapshot size out of bounds: {path}")
    return payload


def load_json_bytes_strict(payload: bytes, label: str) -> dict[str, Any]:
    try:
        value = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise NwiroContractError(f"invalid JSON in {label}: {exc}") from exc
    if not isinstance(value, dict):
        raise NwiroContractError(f"top-level JSON must be an object: {label}")
    _validate_finite(value)
    return value


def load_json_snapshot(path: Path) -> tuple[dict[str, Any], bytes]:
    payload = read_snapshot(path, MAX_JSON_BYTES)
    return load_json_bytes_strict(payload, str(path)), payload


def load_json_strict(path: Path) -> dict[str, Any]:
    value, _payload = load_json_snapshot(path)
    return value


def canonical_json_bytes(value: Any) -> bytes:
    _validate_finite(value)
    return (
        json.dumps(
            value,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        + b"\n"
    )


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest().upper()


def _require_keys(value: dict[str, Any], expected: set[str], label: str) -> None:
    actual = set(value)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise NwiroContractError(
            f"{label} keys mismatch; missing={missing}, extra={extra}"
        )


def _require_plain_bool(value: Any, expected: bool, label: str) -> None:
    if type(value) is not bool or value is not expected:
        raise NwiroContractError(f"{label} must be {expected}")


def _require_sha(value: Any, label: str) -> str:
    if not isinstance(value, str) or not SHA256_RE.fullmatch(value):
        raise NwiroContractError(f"{label} must be uppercase SHA-256")
    return value


def _require_nonempty_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise NwiroContractError(f"{label} must be a nonempty string")
    return value


def _require_absolute_d_path(value: Any, label: str) -> Path:
    text = _require_nonempty_string(value, label)
    if not re.match(r"^D:/[^/].*", text) or "\\" in text or ".." in text:
        raise NwiroContractError(f"{label} must be a canonical absolute D:/ path")
    return Path(text)


def _plugin_source_tokens(plugin_id: str, file_name: str) -> tuple[str, ...]:
    if file_name in {"NwiroToolDispatch.cpp", "NwiroIKMCPServer.cpp"}:
        dispatch = (
            'if (ToolName == TEXT("find_assets"))',
            'if (ToolName == TEXT("get_asset_thumbnail"))',
            'if (ToolName == TEXT("generate_3d_model_meshy"))',
            'if (ToolName == TEXT("generate_3d_model_tripo"))',
            'if (ToolName == TEXT("generate_material_fal"))',
        )
        schema = (
            '\\"name\\":\\"find_assets\\"',
            '\\"searchTerm\\"',
            '\\"classFilter\\"',
            '\\"maxResults\\"',
        )
        return (*schema, *dispatch)
    if file_name in {"NwiroAssetTools.cpp", "NwiroIKAssetTools.cpp"}:
        class_name = (
            "FNwiroAssetTools" if plugin_id == "nwiro_pro" else "FNwiroIKAssetTools"
        )
        return (
            f"FString {class_name}::FindAssets",
            "FAssetRegistryModule",
            "Filter.PackagePaths.Add",
            'SetStringField(TEXT("name")',
            'SetStringField(TEXT("path")',
            'SetStringField(TEXT("class")',
        )
    raise NwiroContractError(f"unexpected plugin source file: {file_name}")


def validate_contract_schema(contract: dict[str, Any]) -> None:
    _require_keys(contract, EXPECTED_TOP_LEVEL_KEYS, "contract")
    if contract["schema_version"] != 1:
        raise NwiroContractError("schema_version must be 1")
    if contract["contract_id"] != "redmmo-nwiro-local-metadata-dry-run":
        raise NwiroContractError("unexpected contract_id")
    if contract["status"] != "static_dry_run_only":
        raise NwiroContractError("status must remain static_dry_run_only")
    if contract["evidence_class"] != "static":
        raise NwiroContractError("evidence_class must remain static")

    execution = contract["execution"]
    if not isinstance(execution, dict):
        raise NwiroContractError("execution must be an object")
    _require_keys(execution, EXECUTION_KEYS, "execution")
    for key, value in execution.items():
        expected = key == "validator_diagnostic_report_publication_allowed"
        _require_plain_bool(value, expected, f"execution.{key}")

    project = contract["project"]
    if not isinstance(project, dict):
        raise NwiroContractError("project must be an object")
    _require_keys(project, PROJECT_KEYS, "project")
    _require_absolute_d_path(project["uproject_path"], "project.uproject_path")
    _require_sha(project["uproject_sha256"], "project.uproject_sha256")
    if project["runtime_state"] != "not_started_not_verified":
        raise NwiroContractError("project runtime_state is not a dry-run state")
    if project != EXPECTED_PROJECT:
        raise NwiroContractError("project identity differs from pinned contract")

    plugins = contract["plugins"]
    if not isinstance(plugins, list) or len(plugins) != 2:
        raise NwiroContractError("plugins must contain the two pinned NWIRO plugins")
    if [item.get("plugin_id") for item in plugins if isinstance(item, dict)] != (
        EXPECTED_PLUGIN_IDS
    ):
        raise NwiroContractError("plugin order or identity mismatch")
    for index, plugin in enumerate(plugins):
        if not isinstance(plugin, dict):
            raise NwiroContractError(f"plugins[{index}] must be an object")
        _require_keys(plugin, PLUGIN_KEYS, f"plugins[{index}]")
        _require_nonempty_string(plugin["version"], f"plugins[{index}].version")
        _require_nonempty_string(plugin["role"], f"plugins[{index}].role")
        _require_absolute_d_path(
            plugin["descriptor_path"], f"plugins[{index}].descriptor_path"
        )
        _require_sha(
            plugin["descriptor_sha256"], f"plugins[{index}].descriptor_sha256"
        )
        _require_plain_bool(
            plugin["enabled_in_project"], True, f"plugins[{index}].enabled_in_project"
        )
        _require_plain_bool(
            plugin["module_startup_verified"],
            False,
            f"plugins[{index}].module_startup_verified",
        )
        _require_plain_bool(
            plugin["in_process_mcp_server_verified"],
            False,
            f"plugins[{index}].in_process_mcp_server_verified",
        )
        binary = plugin["binary_file"]
        if not isinstance(binary, dict):
            raise NwiroContractError(f"plugins[{index}].binary_file must be an object")
        _require_keys(binary, SOURCE_FILE_KEYS, f"plugins[{index}].binary_file")
        _require_absolute_d_path(
            binary["path"], f"plugins[{index}].binary_file.path"
        )
        if type(binary["bytes"]) is not int or binary["bytes"] <= 0:
            raise NwiroContractError("plugin binary byte count must be positive int")
        _require_sha(binary["sha256"], f"plugins[{index}].binary_file.sha256")
        sources = plugin["source_files"]
        if not isinstance(sources, list) or len(sources) != 2:
            raise NwiroContractError(f"plugins[{index}].source_files must have two files")
        for source_index, source in enumerate(sources):
            if not isinstance(source, dict):
                raise NwiroContractError("source file record must be an object")
            _require_keys(
                source,
                SOURCE_FILE_KEYS,
                f"plugins[{index}].source_files[{source_index}]",
            )
            _require_absolute_d_path(
                source["path"],
                f"plugins[{index}].source_files[{source_index}].path",
            )
            if type(source["bytes"]) is not int or source["bytes"] <= 0:
                raise NwiroContractError("source file byte count must be positive int")
            _require_sha(source["sha256"], "plugin source sha256")
    if plugins != EXPECTED_PLUGINS:
        raise NwiroContractError("plugin identities differ from pinned contract")

    selection = contract["source_selection"]
    if not isinstance(selection, dict):
        raise NwiroContractError("source_selection must be an object")
    _require_keys(selection, SOURCE_SELECTION_KEYS, "source_selection")
    for key in ("request_path", "manifest_path"):
        _require_absolute_d_path(selection[key], f"source_selection.{key}")
    for key in ("request_sha256", "manifest_sha256", "manifest_semantic_sha256"):
        _require_sha(selection[key], f"source_selection.{key}")
    if selection["selected_primary_count"] != 9:
        raise NwiroContractError("selected_primary_count must be 9")
    if selection["offline_reference_closure_count"] != 68:
        raise NwiroContractError("offline_reference_closure_count must be 68")
    tree_hashes = selection["pack_source_tree_sha256"]
    if not isinstance(tree_hashes, dict) or set(tree_hashes) != {
        "fab.12ec20bd-ce21-4d3d-8051-13ffb0fe851e",
        "fab.934c1286-7388-4aa5-a300-e0a7cdf65675",
    }:
        raise NwiroContractError("pack source-tree identity set mismatch")
    for pack_id, digest in tree_hashes.items():
        _require_sha(digest, f"source_selection.pack_source_tree_sha256.{pack_id}")
    for key in (
        "selection_ready",
        "migration_ready",
        "nwiro_ready",
        "map_authoring_ready",
    ):
        _require_plain_bool(selection[key], False, f"source_selection.{key}")
    _require_plain_bool(
        selection["source_reauthentication_required_before_runtime"],
        True,
        "source_selection.source_reauthentication_required_before_runtime",
    )
    if selection != EXPECTED_SOURCE_SELECTION:
        raise NwiroContractError("source-selection identity differs from pinned contract")

    boundary = contract["data_boundary"]
    if not isinstance(boundary, dict):
        raise NwiroContractError("data_boundary must be an object")
    _require_keys(boundary, DATA_BOUNDARY_KEYS, "data_boundary")
    for key in (
        "all_source_packs_allow_usage_with_ai",
        "vendor_or_derived_bytes_may_be_uploaded",
        "reference_images_may_be_uploaded",
        "thumbnails_may_be_rendered",
        "asset_properties_may_be_loaded",
        "remote_model_may_receive_metadata",
    ):
        _require_plain_bool(boundary[key], False, f"data_boundary.{key}")
    _require_plain_bool(
        boundary["local_loopback_metadata_query_may_be_considered_after_all_runtime_gates"],
        True,
        "data_boundary.local_loopback_metadata_query_may_be_considered_after_all_runtime_gates",
    )
    if boundary["permitted_response_fields_after_authorization"] != (
        EXPECTED_RESPONSE_FIELDS
    ):
        raise NwiroContractError("permitted response fields mismatch")

    policy = contract["tool_policy"]
    if not isinstance(policy, dict):
        raise NwiroContractError("tool_policy must be an object")
    _require_keys(policy, TOOL_POLICY_KEYS, "tool_policy")
    for key in ("default_action", "unknown_tools", "unknown_namespaces"):
        if policy[key] != "deny":
            raise NwiroContractError(f"tool_policy.{key} must be deny")
    _require_plain_bool(
        policy["allowed_tool_definition_exact_match_required"],
        True,
        "tool_policy.allowed_tool_definition_exact_match_required",
    )
    _require_plain_bool(
        policy["input_schema_exact_match_required"],
        True,
        "tool_policy.input_schema_exact_match_required",
    )
    if (
        policy["future_single_probe_candidate_id"]
        != "RED-FAB-ASSET-8021792003EC13E7D10DBB1B"
    ):
        raise NwiroContractError("future single-probe candidate mismatch")
    allowlist = policy["allowlist"]
    if not isinstance(allowlist, list) or len(allowlist) != 1:
        raise NwiroContractError("allowlist must contain only find_assets")
    allowed = allowlist[0]
    if not isinstance(allowed, dict):
        raise NwiroContractError("allowlist entry must be an object")
    _require_keys(allowed, ALLOWLIST_KEYS, "tool_policy.allowlist[0]")
    if allowed["tool_name"] != "find_assets":
        raise NwiroContractError("only find_assets may be allowed")
    if allowed["implementation"] != "asset_registry_metadata_only":
        raise NwiroContractError("unexpected allowed implementation")
    if allowed["plugin_input_properties"] != EXPECTED_PLUGIN_PROPERTIES:
        raise NwiroContractError("plugin input properties mismatch")
    if allowed["wrapper_required_arguments"] != EXPECTED_PLUGIN_PROPERTIES:
        raise NwiroContractError("wrapper required arguments mismatch")
    if (
        allowed["observed_vendor_input_schema_sha256"]
        != EXPECTED_VENDOR_INPUT_SCHEMA_SHA256
    ):
        raise NwiroContractError("observed vendor input-schema digest mismatch")
    if (
        allowed["observed_vendor_tool_definition_sha256"]
        != EXPECTED_VENDOR_TOOL_DEFINITION_SHA256
    ):
        raise NwiroContractError("observed vendor tool-definition digest mismatch")
    if allowed["future_mcp_method"] != "tools/call":
        raise NwiroContractError("future MCP method must be tools/call")
    _require_plain_bool(
        allowed["additional_arguments_allowed"],
        False,
        "allowlist.additional_arguments_allowed",
    )
    if allowed["max_results"] != 2:
        raise NwiroContractError("allowlist max_results must be 2")
    _require_plain_bool(
        allowed["response_requires_exact_single_identity_match"],
        True,
        "allowlist.response_requires_exact_single_identity_match",
    )
    denials = policy["explicit_denied_tools"]
    if (
        not isinstance(denials, list)
        or any(not isinstance(item, str) or not item for item in denials)
        or len(denials) != len(set(denials))
        or not REQUIRED_EXPLICIT_DENIALS.issubset(set(denials))
        or "find_assets" in denials
    ):
        raise NwiroContractError("explicit denial set is incomplete or invalid")
    if policy["denied_namespaces"] != EXPECTED_DENIED_NAMESPACES:
        raise NwiroContractError("denied namespaces mismatch")
    if policy["denied_tool_prefixes"] != EXPECTED_DENIED_PREFIXES:
        raise NwiroContractError("denied tool prefixes mismatch")

    queries = contract["query_templates"]
    if not isinstance(queries, list) or len(queries) != 9:
        raise NwiroContractError("query_templates must contain exactly 9 entries")
    seen_ids: set[str] = set()
    for index, query in enumerate(queries):
        if not isinstance(query, dict):
            raise NwiroContractError(f"query_templates[{index}] must be an object")
        _require_keys(query, QUERY_KEYS, f"query_templates[{index}]")
        candidate_id = _require_nonempty_string(
            query["stable_candidate_id"],
            f"query_templates[{index}].stable_candidate_id",
        )
        if candidate_id in seen_ids:
            raise NwiroContractError(f"duplicate candidate query: {candidate_id}")
        seen_ids.add(candidate_id)
        _require_nonempty_string(query["pack_id"], f"query_templates[{index}].pack_id")
        if query["tool_name"] != "find_assets":
            raise NwiroContractError("all templates must use find_assets")
        _require_plain_bool(
            query["execution_enabled"],
            False,
            f"query_templates[{index}].execution_enabled",
        )
        if type(query["asset_files_present_in_active_project"]) is not bool:
            raise NwiroContractError("asset presence must be a plain bool")
        _require_plain_bool(
            query["asset_registry_visibility_verified"],
            False,
            f"query_templates[{index}].asset_registry_visibility_verified",
        )
        arguments = query["arguments"]
        result = query["expected_result"]
        if not isinstance(arguments, dict) or not isinstance(result, dict):
            raise NwiroContractError("query arguments/result must be objects")
        _require_keys(arguments, QUERY_ARGUMENT_KEYS, "query arguments")
        _require_keys(result, QUERY_RESULT_KEYS, "query expected_result")
        if arguments["maxResults"] != 2:
            raise NwiroContractError("every query maxResults must be 2")
        if arguments["searchTerm"] != result["name"]:
            raise NwiroContractError("searchTerm must exactly equal expected name")
        if arguments["classFilter"] != result["class"]:
            raise NwiroContractError("classFilter must exactly equal expected class")
        object_path = _require_nonempty_string(result["path"], "expected result path")
        if not object_path.startswith("/Game/") or object_path.count(".") != 1:
            raise NwiroContractError("expected result path is not an object path")
        package_name, object_name = object_path.rsplit(".", 1)
        package = PurePosixPath(package_name)
        if package.name != object_name or package.parent.as_posix() != arguments["path"]:
            raise NwiroContractError("query path/name do not bind exact object identity")
        if query["pack_id"].endswith("12ec20bd-ce21-4d3d-8051-13ffb0fe851e"):
            _require_plain_bool(
                query["asset_files_present_in_active_project"],
                True,
                "Desert active-project presence",
            )
        elif query["pack_id"].endswith("934c1286-7388-4aa5-a300-e0a7cdf65675"):
            _require_plain_bool(
                query["asset_files_present_in_active_project"],
                False,
                "Tropical active-project presence",
            )
        else:
            raise NwiroContractError("unexpected pack_id in query")
    if queries != expected_query_templates():
        raise NwiroContractError("query templates differ from pinned identities")

    blockers = contract["known_blockers"]
    if not isinstance(blockers, dict):
        raise NwiroContractError("known_blockers must be an object")
    _require_keys(blockers, KNOWN_BLOCKER_KEYS, "known_blockers")
    for key, value in blockers.items():
        _require_plain_bool(value, False, f"known_blockers.{key}")

    future = contract["future_runtime_sequence"]
    if not isinstance(future, list) or len(future) != len(EXPECTED_FUTURE_STEPS):
        raise NwiroContractError("future_runtime_sequence mismatch")
    for index, (record, expected_step) in enumerate(zip(future, EXPECTED_FUTURE_STEPS)):
        if not isinstance(record, dict):
            raise NwiroContractError("future runtime step must be an object")
        _require_keys(record, FUTURE_STEP_KEYS, f"future_runtime_sequence[{index}]")
        if record["step"] != expected_step:
            raise NwiroContractError("future runtime step order mismatch")
        _require_plain_bool(
            record["complete"], False, f"future_runtime_sequence[{index}].complete"
        )


def validate_find_assets_tool_definition(definition: dict[str, Any]) -> None:
    if not isinstance(definition, dict):
        raise NwiroContractError("find_assets definition must be an object")
    _require_keys(
        definition,
        {"name", "description", "inputSchema", "annotations"},
        "tool definition",
    )
    if definition != EXPECTED_VENDOR_TOOL_DEFINITION:
        raise NwiroContractError("find_assets tool definition mismatch")
    schema = definition["inputSchema"]
    if sha256_bytes(canonical_json_bytes(schema)) != EXPECTED_VENDOR_INPUT_SCHEMA_SHA256:
        raise NwiroContractError("find_assets input schema digest mismatch")
    if (
        sha256_bytes(canonical_json_bytes(definition))
        != EXPECTED_VENDOR_TOOL_DEFINITION_SHA256
    ):
        raise NwiroContractError("find_assets tool definition digest mismatch")


def _future_probe_query(contract: dict[str, Any]) -> dict[str, Any]:
    candidate_id = contract["tool_policy"]["future_single_probe_candidate_id"]
    matches = [
        query
        for query in contract["query_templates"]
        if query["stable_candidate_id"] == candidate_id
    ]
    if len(matches) != 1:
        raise NwiroContractError("future probe candidate is not unique")
    return matches[0]


def validate_future_probe_request(
    contract: dict[str, Any], tool_name: Any, arguments: Any
) -> None:
    validate_contract_schema(contract)
    if tool_name != "find_assets":
        raise NwiroContractError("future probe permits only find_assets")
    if not isinstance(arguments, dict):
        raise NwiroContractError("future probe arguments must be an object")
    _require_keys(arguments, QUERY_ARGUMENT_KEYS, "future probe arguments")
    if (
        type(arguments["searchTerm"]) is not str
        or type(arguments["classFilter"]) is not str
        or type(arguments["path"]) is not str
        or type(arguments["maxResults"]) is not int
    ):
        raise NwiroContractError("future probe argument types mismatch")
    if arguments != _future_probe_query(contract)["arguments"]:
        raise NwiroContractError("future probe arguments differ from exact contract")


def validate_future_probe_response(
    contract: dict[str, Any], response: Any
) -> dict[str, str]:
    validate_contract_schema(contract)
    if not isinstance(response, dict):
        raise NwiroContractError("future probe response must be an object")
    _require_keys(response, {"success", "assets", "count"}, "future probe response")
    _require_plain_bool(response["success"], True, "future probe response.success")
    if type(response["count"]) is not int or response["count"] != 1:
        raise NwiroContractError("future probe response count must be exactly 1")
    assets = response["assets"]
    if not isinstance(assets, list) or len(assets) != 1:
        raise NwiroContractError("future probe response must contain exactly one asset")
    asset = assets[0]
    if not isinstance(asset, dict):
        raise NwiroContractError("future probe asset must be an object")
    _require_keys(asset, QUERY_RESULT_KEYS, "future probe asset")
    expected = _future_probe_query(contract)["expected_result"]
    if asset != expected:
        raise NwiroContractError("future probe asset identity mismatch")
    return asset


def _validate_json_rpc_id(value: Any, label: str) -> None:
    if type(value) is int and value >= 0:
        return
    if type(value) is str and value and not value.isspace():
        return
    raise NwiroContractError(f"{label} must be a nonnegative integer or nonempty string")


def validate_future_probe_jsonrpc_request(
    contract: dict[str, Any], envelope: Any, expected_id: Any
) -> None:
    _validate_json_rpc_id(expected_id, "expected JSON-RPC id")
    if not isinstance(envelope, dict):
        raise NwiroContractError("future probe JSON-RPC request must be an object")
    _require_keys(
        envelope,
        {"jsonrpc", "id", "method", "params"},
        "future probe JSON-RPC request",
    )
    if envelope["jsonrpc"] != "2.0":
        raise NwiroContractError("future probe JSON-RPC version mismatch")
    if envelope["id"] != expected_id or type(envelope["id"]) is not type(expected_id):
        raise NwiroContractError("future probe JSON-RPC request id mismatch")
    if envelope["method"] != "tools/call":
        raise NwiroContractError("future probe JSON-RPC method must be tools/call")
    params = envelope["params"]
    if not isinstance(params, dict):
        raise NwiroContractError("future probe JSON-RPC params must be an object")
    _require_keys(params, {"name", "arguments"}, "future probe JSON-RPC params")
    validate_future_probe_request(contract, params["name"], params["arguments"])


def validate_future_probe_jsonrpc_response(
    contract: dict[str, Any], envelope: Any, expected_id: Any
) -> dict[str, str]:
    _validate_json_rpc_id(expected_id, "expected JSON-RPC id")
    if not isinstance(envelope, dict):
        raise NwiroContractError("future probe JSON-RPC response must be an object")
    _require_keys(
        envelope,
        {"jsonrpc", "id", "result"},
        "future probe JSON-RPC response",
    )
    if envelope["jsonrpc"] != "2.0":
        raise NwiroContractError("future probe JSON-RPC version mismatch")
    if envelope["id"] != expected_id or type(envelope["id"]) is not type(expected_id):
        raise NwiroContractError("future probe JSON-RPC response id mismatch")
    result = envelope["result"]
    if not isinstance(result, dict):
        raise NwiroContractError("future probe JSON-RPC result must be an object")
    _require_keys(result, {"content"}, "future probe JSON-RPC result")
    content = result["content"]
    if not isinstance(content, list) or len(content) != 1:
        raise NwiroContractError(
            "future probe JSON-RPC result must have exactly one content item"
        )
    item = content[0]
    if not isinstance(item, dict):
        raise NwiroContractError("future probe JSON-RPC content must be an object")
    _require_keys(item, {"type", "text"}, "future probe JSON-RPC content")
    if item["type"] != "text" or type(item["text"]) is not str:
        raise NwiroContractError("future probe JSON-RPC content must be text")
    inner_payload = item["text"].encode("utf-8")
    if not inner_payload or len(inner_payload) > MAX_JSON_BYTES:
        raise NwiroContractError("future probe JSON-RPC content size out of bounds")
    inner = load_json_bytes_strict(inner_payload, "future probe MCP result content")
    return validate_future_probe_response(contract, inner)


def validate_future_probe_jsonrpc_request_bytes(
    contract: dict[str, Any], payload: bytes, expected_id: Any
) -> None:
    if not payload or len(payload) > MAX_JSON_BYTES:
        raise NwiroContractError("future probe JSON-RPC request size out of bounds")
    envelope = load_json_bytes_strict(payload, "future probe JSON-RPC request")
    validate_future_probe_jsonrpc_request(contract, envelope, expected_id)


def validate_future_probe_jsonrpc_response_bytes(
    contract: dict[str, Any], payload: bytes, expected_id: Any
) -> dict[str, str]:
    if not payload or len(payload) > MAX_JSON_BYTES:
        raise NwiroContractError("future probe JSON-RPC response size out of bounds")
    envelope = load_json_bytes_strict(payload, "future probe JSON-RPC response")
    return validate_future_probe_jsonrpc_response(contract, envelope, expected_id)


def authenticate_contract_inputs(contract: dict[str, Any]) -> list[dict[str, Any]]:
    authenticated: list[dict[str, Any]] = []

    project = contract["project"]
    project_path = Path(project["uproject_path"])
    project_payload = read_snapshot(project_path, MAX_JSON_BYTES)
    if sha256_bytes(project_payload) != project["uproject_sha256"]:
        raise NwiroContractError("uproject hash mismatch")
    uproject = load_json_bytes_strict(project_payload, str(project_path))
    enabled_plugins = {
        entry.get("Name")
        for entry in uproject.get("Plugins", [])
        if isinstance(entry, dict) and entry.get("Enabled") is True
    }
    if not {"Nwiro", "NwiroIntegrationKit"}.issubset(enabled_plugins):
        raise NwiroContractError("both pinned NWIRO plugins must be enabled")
    authenticated.append(
        {
            "kind": "uproject",
            "path": project["uproject_path"],
            "sha256": project["uproject_sha256"],
        }
    )

    expected_names = {
        "nwiro_pro": ("Nwiro Pro", "1.1.9"),
        "nwiro_integration_kit": ("Nwiro Integration Kit", "1.0.9"),
    }
    for plugin in contract["plugins"]:
        descriptor_path = Path(plugin["descriptor_path"])
        descriptor_payload = read_snapshot(descriptor_path, MAX_JSON_BYTES)
        if sha256_bytes(descriptor_payload) != plugin["descriptor_sha256"]:
            raise NwiroContractError(f"descriptor hash mismatch: {plugin['plugin_id']}")
        descriptor = load_json_bytes_strict(descriptor_payload, str(descriptor_path))
        friendly_name, version = expected_names[plugin["plugin_id"]]
        if (
            descriptor.get("FriendlyName") != friendly_name
            or descriptor.get("VersionName") != version
            or plugin["version"] != version
        ):
            raise NwiroContractError(f"descriptor identity mismatch: {plugin['plugin_id']}")
        authenticated.append(
            {
                "kind": "plugin_descriptor",
                "plugin_id": plugin["plugin_id"],
                "path": plugin["descriptor_path"],
                "sha256": plugin["descriptor_sha256"],
            }
        )
        binary = plugin["binary_file"]
        binary_path = Path(binary["path"])
        binary_payload = read_snapshot(binary_path, binary["bytes"])
        if len(binary_payload) != binary["bytes"]:
            raise NwiroContractError(f"binary byte count mismatch: {binary_path}")
        if sha256_bytes(binary_payload) != binary["sha256"]:
            raise NwiroContractError(f"binary hash mismatch: {binary_path}")
        authenticated.append(
            {
                "kind": "plugin_binary",
                "plugin_id": plugin["plugin_id"],
                "path": binary["path"],
                "bytes": binary["bytes"],
                "sha256": binary["sha256"],
            }
        )
        for source in plugin["source_files"]:
            source_path = Path(source["path"])
            source_payload = read_snapshot(source_path, source["bytes"])
            if len(source_payload) != source["bytes"]:
                raise NwiroContractError(f"source byte count mismatch: {source_path}")
            if sha256_bytes(source_payload) != source["sha256"]:
                raise NwiroContractError(f"source hash mismatch: {source_path}")
            try:
                text = source_payload.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise NwiroContractError(f"cannot inspect {source_path}: {exc}") from exc
            for token in _plugin_source_tokens(plugin["plugin_id"], source_path.name):
                if token not in text:
                    raise NwiroContractError(
                        f"source contract token absent from {source_path.name}: {token}"
                    )
            authenticated.append(
                {
                    "kind": "plugin_source",
                    "plugin_id": plugin["plugin_id"],
                    "path": source["path"],
                    "bytes": source["bytes"],
                    "sha256": source["sha256"],
                }
            )

    selection = contract["source_selection"]
    request_path = Path(selection["request_path"])
    manifest_path = Path(selection["manifest_path"])
    request_payload = read_snapshot(request_path, MAX_JSON_BYTES)
    manifest_payload = read_snapshot(manifest_path, MAX_JSON_BYTES)
    if sha256_bytes(request_payload) != selection["request_sha256"]:
        raise NwiroContractError("cross-pack request hash mismatch")
    if sha256_bytes(manifest_payload) != selection["manifest_sha256"]:
        raise NwiroContractError("cross-pack manifest hash mismatch")
    request = load_json_bytes_strict(request_payload, str(request_path))
    manifest = load_json_bytes_strict(manifest_payload, str(manifest_path))
    semantic_payload = {
        key: value for key, value in manifest.items() if key != "semantic_sha256"
    }
    computed_manifest_semantic = sha256_bytes(canonical_json_bytes(semantic_payload))
    if (
        manifest.get("semantic_sha256") != selection["manifest_semantic_sha256"]
        or computed_manifest_semantic != selection["manifest_semantic_sha256"]
        or manifest.get("status") != "review_request_only"
        or manifest.get("request", {}).get("request_sha256")
        != selection["request_sha256"]
    ):
        raise NwiroContractError("cross-pack manifest identity mismatch")
    summary = manifest.get("summary")
    if not isinstance(summary, dict):
        raise NwiroContractError("manifest summary missing")
    expected_summary = {
        "selected_primary_count": selection["selected_primary_count"],
        "offline_reference_closure_count": selection[
            "offline_reference_closure_count"
        ],
        "selection_ready": False,
        "migration_ready": False,
        "nwiro_ready": False,
        "map_authoring_ready": False,
    }
    for key, value in expected_summary.items():
        if summary.get(key) != value:
            raise NwiroContractError(f"manifest summary mismatch: {key}")
    packs = manifest.get("packs")
    if (
        not isinstance(packs, list)
        or len(packs) != 2
        or any(pack.get("allows_usage_with_ai") is not False for pack in packs)
    ):
        raise NwiroContractError("manifest pack NoAI boundary mismatch")
    manifest_tree_hashes = {
        pack.get("pack_id"): pack.get("source_tree_sha256")
        for pack in packs
        if isinstance(pack, dict)
    }
    if manifest_tree_hashes != selection["pack_source_tree_sha256"]:
        raise NwiroContractError("manifest pack source-tree identities mismatch")
    if (
        request.get("no_category_fallback") is not True
        or request.get("authority", {}).get("approval_enabled") is not False
        or any(
            pack.get("allows_usage_with_ai") is not False
            for pack in request.get("packs", [])
        )
    ):
        raise NwiroContractError("request authority or NoAI boundary mismatch")

    selected = manifest.get("selected_candidates")
    if not isinstance(selected, list) or len(selected) != 9:
        raise NwiroContractError("manifest selected candidates mismatch")
    candidates_by_id = {
        item.get("stable_candidate_id"): item
        for item in selected
        if isinstance(item, dict)
    }
    if len(candidates_by_id) != 9 or None in candidates_by_id:
        raise NwiroContractError("manifest candidate IDs are not unique")
    query_ids = {query["stable_candidate_id"] for query in contract["query_templates"]}
    if query_ids != set(candidates_by_id):
        raise NwiroContractError("query candidate set does not match manifest")
    for query in contract["query_templates"]:
        candidate = candidates_by_id[query["stable_candidate_id"]]
        result = query["expected_result"]
        if (
            candidate.get("pack_id") != query["pack_id"]
            or candidate.get("object_path") != result["path"]
            or candidate.get("expected_asset_kind") != result["class"]
        ):
            raise NwiroContractError(
                f"query does not bind manifest candidate: {query['stable_candidate_id']}"
            )

    authenticated.extend(
        [
            {
                "kind": "crosspack_request",
                "path": selection["request_path"],
                "sha256": selection["request_sha256"],
            },
            {
                "kind": "crosspack_manifest",
                "path": selection["manifest_path"],
                "sha256": selection["manifest_sha256"],
                "semantic_sha256": selection["manifest_semantic_sha256"],
            },
        ]
    )
    return authenticated


def build_report(
    contract: dict[str, Any],
    contract_path: Path,
    contract_payload: bytes,
    authenticated_inputs: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "report_id": "redmmo-nwiro-local-metadata-dry-run-validation",
        "evidence_class": "static",
        "status": "contract_valid_generation_disabled",
        "contract": {
            "path": str(contract_path).replace("\\", "/"),
            "sha256": sha256_bytes(contract_payload),
            "semantic_sha256": sha256_bytes(canonical_json_bytes(contract)),
        },
        "authenticated_inputs": authenticated_inputs,
        "policy": {
            "allowed_tool_count": 1,
            "allowed_tools": ["find_assets"],
            "query_template_count": len(contract["query_templates"]),
            "enabled_query_count": 0,
            "default_action": "deny",
            "contract_allows_provider_and_generation_tools": False,
            "contract_allows_asset_or_map_mutation": False,
            "predispatch_wrapper_implemented": False,
            "raw_mcp_direct_path_blocked": False,
        },
        "observed": {
            "unreal_started": False,
            "plugin_module_started": False,
            "mcp_initialized": False,
            "tools_list_called": False,
            "tool_called": False,
            "provider_called": False,
            "asset_loaded": False,
            "file_or_package_written_by_nwiro": False,
            "map_changed": False,
            "real_gpu_evidence": False,
        },
        "limitations": [
            "This report validates an offline client-side contract; it does not constrain raw NWIRO dispatch by itself.",
            "NWIRO Pro and Integration Kit runtime startup, MCP transport, tools/list, and tool execution remain unverified.",
            "The Integration Kit headless permission bypass is not fixed; a later probe requires a deterministic local pre-dispatch wrapper.",
            "The vendor-source bridge-null provider-consent bypass is not fixed; provider and generation tools remain forbidden.",
            "The packs remain allows_usage_with_ai=false; no vendor or derived bytes were sent to any model or provider.",
            "No import, migration, placement, mini-hub map, curved-tile blend, or real-GPU acceptance occurred.",
        ],
    }


def report_json_bytes(report: dict[str, Any]) -> bytes:
    _validate_finite(report)
    return json.dumps(
        report,
        ensure_ascii=True,
        sort_keys=True,
        indent=2,
        allow_nan=False,
    ).encode("utf-8") + b"\n"


def validate_output_path(path: Path, diagnostics_root: Path) -> Path:
    if not path.is_absolute():
        raise NwiroContractError("report path must be absolute")
    try:
        resolved_root = diagnostics_root.resolve(strict=True)
        resolved_parent = path.parent.resolve(strict=True)
    except OSError as exc:
        raise NwiroContractError(f"report parent/root unavailable: {exc}") from exc
    if resolved_parent != resolved_root and resolved_root not in resolved_parent.parents:
        raise NwiroContractError("report path must be below diagnostics root")
    if path.exists():
        raise NwiroContractError("report path already exists")
    return path


def write_report_no_clobber(path: Path, report: dict[str, Any]) -> None:
    payload = report_json_bytes(report)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    try:
        descriptor = os.open(path, flags, 0o600)
    except OSError as exc:
        raise NwiroContractError(f"cannot exclusively create report: {exc}") from exc
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        try:
            path.unlink(missing_ok=True)
        finally:
            raise


def validate_contract_file(
    contract_path: Path,
) -> tuple[dict[str, Any], bytes, list[dict[str, Any]]]:
    contract, contract_payload = load_json_snapshot(contract_path)
    validate_contract_schema(contract)
    authenticated_inputs = authenticate_contract_inputs(contract)
    return contract, contract_payload, authenticated_inputs


def reauthenticate_before_publication(
    contract_path: Path,
    contract: dict[str, Any],
    contract_payload: bytes,
    authenticated_inputs: list[dict[str, Any]],
) -> None:
    current_contract, current_payload = load_json_snapshot(contract_path)
    if current_payload != contract_payload or current_contract != contract:
        raise NwiroContractError("contract changed before report publication")
    validate_contract_schema(current_contract)
    current_inputs = authenticate_contract_inputs(current_contract)
    if current_inputs != authenticated_inputs:
        raise NwiroContractError("authenticated inputs changed before publication")


def _parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument("--report", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: Iterable[str] | None = None) -> int:
    args = _parse_args(argv)
    report_path = validate_output_path(args.report, DEFAULT_DIAGNOSTICS_ROOT)
    try:
        contract_path = args.contract.resolve(strict=True)
    except OSError as exc:
        raise NwiroContractError(f"contract path unavailable: {exc}") from exc
    contract, contract_payload, authenticated_inputs = validate_contract_file(
        contract_path
    )
    report = build_report(
        contract, contract_path, contract_payload, authenticated_inputs
    )
    reauthenticate_before_publication(
        contract_path, contract, contract_payload, authenticated_inputs
    )
    write_report_no_clobber(report_path, report)
    print(
        json.dumps(
            {
                "status": report["status"],
                "report": str(report_path),
                "contract_sha256": report["contract"]["sha256"],
                "contract_semantic_sha256": report["contract"]["semantic_sha256"],
                "authenticated_input_count": len(authenticated_inputs),
                "allowed_tools": report["policy"]["allowed_tools"],
                "enabled_query_count": report["policy"]["enabled_query_count"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except NwiroContractError as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, sort_keys=True))
        raise SystemExit(2)
