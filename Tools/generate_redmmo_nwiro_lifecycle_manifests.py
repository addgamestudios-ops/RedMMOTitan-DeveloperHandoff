"""Publish/verify the exact offline NWIRO lifecycle source revision.

This fixed-boundary tool never loads Unreal, starts MCP, binds a socket,
installs a plugin, contacts a provider, or touches an asset/map. Publication
is private, same-volume, no-clobber, and consists of one atomic directory
rename containing both the current-candidate and complete-delta manifests.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

_TOOLS_DIR = Path(__file__).resolve().parent
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from create_redmmo_nwiro_restricted_probe_candidate import (
    CandidateCreationError,
    TreeSnapshot,
    _apply_private_directory_acl,
    _apply_private_file_acl,
    _canonical_file_bytes,
    _lexists,
    _load_manifest,
    _move_no_clobber,
    _require_exact_private_acl,
    _scan_two_pass,
    _windows_identity,
    _write_exclusive,
)


PROJECT_ROOT = Path(r"D:\RedMMOTitan")
STAGING_ROOT = Path(r"D:\RedMMOTitanWindowsData\Staging")
CANDIDATE_ROOT = STAGING_ROOT / "NwiroRestrictedProbeForkCandidateV1"
BASELINE_MANIFEST = (
    STAGING_ROOT / "NwiroRestrictedProbeForkCandidateV1.baseline.v1.json"
)
AUTHORIZATION = (
    PROJECT_ROOT
    / "Build"
    / "Automation"
    / "redmmo_nwiro_lifecycle_execution_authorization_v1.json"
)
PARENT_EVIDENCE_ROOT = (
    STAGING_ROOT / "NwiroRestrictedProbeActivationOwnershipEvidenceV1"
)
PARENT_CANDIDATE_MANIFEST = PARENT_EVIDENCE_ROOT / "candidate.v1.json"
PARENT_DELTA_MANIFEST = PARENT_EVIDENCE_ROOT / "delta.v1.json"
SOURCE_CONTRACT_TEST = (
    PROJECT_ROOT
    / "Tools"
    / "tests"
    / "test_redmmo_nwiro_lifecycle_source.py"
)
ROLLBACK_ROOT = Path(
    r"D:\RedMMOTitanWindowsData\Rollback"
    r"\NwiroRestrictedProbeLifecycle_20260725_1223Z"
)
OUTPUT_ROOT = STAGING_ROOT / "NwiroRestrictedProbeLifecycleEvidenceV1"
OUTPUT_CANDIDATE_MANIFEST = OUTPUT_ROOT / "candidate.v1.json"
OUTPUT_DELTA_MANIFEST = OUTPUT_ROOT / "delta.v1.json"

BASELINE_MANIFEST_SHA256 = (
    "AACAC06301F470A270870DD48FF4085CCA44A3370E9CE504592F79D11EA7996A"
)
AUTHORIZATION_SHA256 = (
    "203F1B7A7C7BB2B594B8BF8DFCD8182B8B6386106CCA00AEC15AFF1F1FCF5983"
)
SOURCE_CONTRACT_TEST_SHA256 = (
    "17B17802255EC8DD12A3988D05F9B76F6F6FB617BAB3281FF3BB8D4423A061E9"
)
EXPECTED_FILE_COUNT = 90
EXPECTED_DIRECTORY_COUNT = 10
EXPECTED_TOTAL_BYTES = 2_228_379
EXPECTED_RECORD_SET_SHA256 = (
    "4857CA12853867F77C7B81F1133A7E9DB6A8078DDC804AB6D92631791BE9C761"
)
EXPECTED_TOPOLOGY_SHA256 = (
    "8788A05E64243D692AD4764421645E68D02951D33DD9C86ED546F0F40A88D6D5"
)
EXPECTED_CUMULATIVE_CHANGED_FILES = (
    "NwiroIntegrationKit.uplugin",
    "Source/NwiroIntegrationKit/Private/NwiroIKBridge.cpp",
    "Source/NwiroIntegrationKit/Private/NwiroIKMCPServer.cpp",
    "Source/NwiroIntegrationKit/Private/NwiroIKMCPServer.h",
    "Source/NwiroIntegrationKit/Private/NwiroIntegrationKit.cpp",
    "Source/NwiroIntegrationKit/Public/NwiroIK.h",
)
EXPECTED_CHANGED_FILES = (
    "Source/NwiroIntegrationKit/Private/NwiroIKBridge.cpp",
    "Source/NwiroIntegrationKit/Private/NwiroIKMCPServer.cpp",
    "Source/NwiroIntegrationKit/Private/NwiroIKMCPServer.h",
)
EXPECTED_CURRENT_FILES = {
    "NwiroIntegrationKit.uplugin": (
        "88A59B34604759DE0657446E78DC8CB88A23837D70F0E27AF523733D8FA421F0"
    ),
    "Source/NwiroIntegrationKit/Private/NwiroIKBridge.cpp": (
        "7BC0F35567D5BAB9EF909A2C1AAB72041E097D4EFCEC28CDCA04048A3B5E9406"
    ),
    "Source/NwiroIntegrationKit/Private/NwiroIKMCPServer.cpp": (
        "3188840914AC8644741717FE9EA29DBB8654A906C0D6F1D64FEDE5E4F5FDCEC7"
    ),
    "Source/NwiroIntegrationKit/Private/NwiroIKMCPServer.h": (
        "F280BD2FF13190FFEE46EAA22EF36F622E8FAC9FA4AB733C345115B596EC86AE"
    ),
    "Source/NwiroIntegrationKit/Private/NwiroIntegrationKit.cpp": (
        "C3899FD2D50B5A13E170EC77FE2B67B1FFCFA919AB01D0B55424B322FD663E74"
    ),
    "Source/NwiroIntegrationKit/Public/NwiroIK.h": (
        "45A3E39F1E5AC4A41B716E2B2904F1D7810567423B9E04264F2605F22070C090"
    ),
}
EXPECTED_INITIAL_FILES = {
    "Source/NwiroIntegrationKit/Private/NwiroIKBridge.cpp": (
        "80C8A3194148C86D1F4E1D479133BB2B76A627698F2E35DC4D6CE822E5FC1AA1"
    ),
    "Source/NwiroIntegrationKit/Private/NwiroIKMCPServer.cpp": (
        "AA3FD57690EB52EEADCC473DA5C15C0F6A555199A06C9EEA4EF18258ECE20099"
    ),
    "Source/NwiroIntegrationKit/Private/NwiroIKMCPServer.h": (
        "E6161EFD3E4F34DE037D329766A61D792ECC572FDCF8D83592AE99277F4AF747"
    ),
}
FORBIDDEN_BINARY_SUFFIXES = {".dll", ".exe", ".lib", ".obj", ".pdb"}
UTC_PATTERN = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z$"
)


class LifecycleManifestError(RuntimeError):
    """Raised when the exact authorized lifecycle boundary drifts."""


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest().upper()


def _read_authenticated_json(
    path: Path,
    expected_sha256: str,
) -> dict[str, Any]:
    payload = path.read_bytes()
    observed = _sha256(payload)
    if observed != expected_sha256:
        raise LifecycleManifestError(
            f"authenticated input drift: {path} ({observed})"
        )
    value = json.loads(payload.decode("utf-8"))
    if not isinstance(value, dict):
        raise LifecycleManifestError(f"expected JSON object: {path}")
    return value


def _semantic_hash(value: Mapping[str, Any]) -> str:
    payload = dict(value)
    payload.pop("manifest_semantic_sha256", None)
    return _sha256(_canonical_file_bytes(payload))


def _with_semantic_hash(value: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(value)
    result["manifest_semantic_sha256"] = _semantic_hash(result)
    return result


def _records_from_manifest(
    manifest: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    tree = manifest.get("tree")
    files = tree.get("files") if isinstance(tree, dict) else None
    if not isinstance(files, list):
        raise LifecycleManifestError("baseline file list missing")
    records: dict[str, dict[str, Any]] = {}
    for raw in files:
        if not isinstance(raw, dict):
            raise LifecycleManifestError("malformed baseline file record")
        path = raw.get("path")
        if not isinstance(path, str) or path in records:
            raise LifecycleManifestError("duplicate baseline path")
        records[path] = dict(raw)
    return records


def _records_from_snapshot(
    snapshot: TreeSnapshot,
) -> dict[str, dict[str, Any]]:
    return {
        str(record["path"]): dict(record)
        for record in snapshot.files
    }


def _authenticate_boundary() -> tuple[
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
    TreeSnapshot,
    TreeSnapshot,
    tuple[dict[str, Any], ...],
    tuple[dict[str, Any], ...],
]:
    baseline = _read_authenticated_json(
        BASELINE_MANIFEST,
        BASELINE_MANIFEST_SHA256,
    )
    authorization = _read_authenticated_json(
        AUTHORIZATION,
        AUTHORIZATION_SHA256,
    )
    if authorization.get("status") != (
        "approved_once_offline_candidate_lifecycle_source_only"
    ):
        raise LifecycleManifestError("authorization status drift")
    candidate = authorization.get("candidate")
    if not isinstance(candidate, dict) or candidate.get("root") != (
        CANDIDATE_ROOT.as_posix()
    ):
        raise LifecycleManifestError("authorization candidate root drift")
    parent_evidence = authorization.get("parent_evidence")
    if not isinstance(parent_evidence, dict):
        raise LifecycleManifestError("parent evidence reference missing")
    parent_evidence_path = Path(str(parent_evidence.get("path", "")))
    parent_evidence_hash = str(parent_evidence.get("sha256", ""))
    if _sha256(parent_evidence_path.read_bytes()) != parent_evidence_hash:
        raise LifecycleManifestError("parent evidence hash drift")
    parent_candidate = _read_authenticated_json(
        PARENT_CANDIDATE_MANIFEST,
        str(candidate.get("candidate_manifest_sha256", "")),
    )
    parent_delta = _read_authenticated_json(
        PARENT_DELTA_MANIFEST,
        str(candidate.get("delta_manifest_sha256", "")),
    )
    for document, label in (
        (parent_candidate, "parent candidate"),
        (parent_delta, "parent delta"),
    ):
        if document.get("manifest_semantic_sha256") != _semantic_hash(document):
            raise LifecycleManifestError(f"{label} semantic hash drift")
    parent_tree = parent_candidate.get("tree")
    if not isinstance(parent_tree, dict):
        raise LifecycleManifestError("parent candidate tree missing")
    parent_expected = {
        "file_count": candidate.get("file_count"),
        "directory_count_excluding_root": candidate.get("directory_count_excluding_root"),
        "total_bytes": candidate.get("total_bytes"),
        "record_set_sha256": candidate.get("record_set_sha256"),
        "topology_sha256": candidate.get("topology_sha256"),
    }
    for key, expected in parent_expected.items():
        if parent_tree.get(key) != expected:
            raise LifecycleManifestError(
                f"parent candidate authorization mismatch: {key}"
            )
    parent_candidate_hash = str(candidate["candidate_manifest_sha256"])
    parent_delta_candidate = parent_delta.get("candidate_manifest")
    if (
        not isinstance(parent_delta_candidate, dict)
        or parent_delta_candidate.get("raw_sha256")
        != parent_candidate_hash
    ):
        raise LifecycleManifestError("parent delta/candidate linkage drift")
    authorities = authorization.get("authorities")
    if not isinstance(authorities, dict):
        raise LifecycleManifestError("authorization capability map missing")
    required_false = (
        "compile_authorized",
        "install_authorized",
        "unreal_launch_authorized",
        "mcp_initialize_authorized",
        "mcp_tool_call_authorized",
        "network_authorized",
        "provider_call_authorized",
        "asset_or_map_mutation_authorized",
        "vendor_plugin_mutation_authorized",
        "project_plugin_activation_authorized",
    )
    for key in required_false:
        if authorities.get(key) is not False:
            raise LifecycleManifestError(f"forbidden authority became true: {key}")

    allowlist = authorization.get("exact_candidate_mutation_allowlist")
    if not isinstance(allowlist, list):
        raise LifecycleManifestError("authorization allowlist missing")
    authorized_initial = {
        str(item["path"]): str(item["sha256"])
        for item in allowlist
        if isinstance(item, dict)
    }
    if authorized_initial != EXPECTED_INITIAL_FILES:
        raise LifecycleManifestError("exact initial source allowlist drift")

    if _sha256(SOURCE_CONTRACT_TEST.read_bytes()) != (
        SOURCE_CONTRACT_TEST_SHA256
    ):
        raise LifecycleManifestError("source contract test drift")

    snapshot = _scan_two_pass(CANDIDATE_ROOT)
    if (
        snapshot.file_count != EXPECTED_FILE_COUNT
        or snapshot.directory_count_excluding_root
        != EXPECTED_DIRECTORY_COUNT
        or snapshot.total_bytes != EXPECTED_TOTAL_BYTES
        or snapshot.record_set_sha256 != EXPECTED_RECORD_SET_SHA256
        or snapshot.topology_sha256 != EXPECTED_TOPOLOGY_SHA256
    ):
        raise LifecycleManifestError("exact reviewed candidate snapshot drift")
    baseline_records = _records_from_manifest(baseline)
    parent_records = _records_from_manifest(parent_candidate)
    candidate_records = _records_from_snapshot(snapshot)
    if (
        set(baseline_records) != set(parent_records)
        or set(parent_records) != set(candidate_records)
    ):
        raise LifecycleManifestError(
            "candidate paths differ across authenticated lineage"
        )

    cumulative_changed: list[dict[str, Any]] = []
    for path in sorted(baseline_records):
        before = baseline_records[path]
        after = candidate_records[path]
        if (
            int(before["bytes"]) != int(after["bytes"])
            or str(before["sha256"]) != str(after["sha256"])
        ):
            cumulative_changed.append(
                {
                    "path": path,
                    "before": {
                        "bytes": int(before["bytes"]),
                        "sha256": str(before["sha256"]),
                    },
                    "after": {
                        "bytes": int(after["bytes"]),
                        "sha256": str(after["sha256"]),
                    },
                }
            )
    if tuple(item["path"] for item in cumulative_changed) != (
        EXPECTED_CUMULATIVE_CHANGED_FILES
    ):
        raise LifecycleManifestError("exact cumulative six-file delta drift")

    changed: list[dict[str, Any]] = []
    for path in sorted(parent_records):
        before = parent_records[path]
        after = candidate_records[path]
        if (
            int(before["bytes"]) != int(after["bytes"])
            or str(before["sha256"]) != str(after["sha256"])
        ):
            changed.append(
                {
                    "path": path,
                    "before": {
                        "bytes": int(before["bytes"]),
                        "sha256": str(before["sha256"]),
                    },
                    "after": {
                        "bytes": int(after["bytes"]),
                        "sha256": str(after["sha256"]),
                    },
                }
            )
    if tuple(item["path"] for item in changed) != EXPECTED_CHANGED_FILES:
        raise LifecycleManifestError("exact lifecycle three-file delta drift")
    for item in changed:
        if item["before"]["sha256"] != EXPECTED_INITIAL_FILES[item["path"]]:
            raise LifecycleManifestError(
                f"lifecycle prestate drift: {item['path']}"
            )
    for path, expected_hash in EXPECTED_CURRENT_FILES.items():
        if candidate_records[path]["sha256"] != expected_hash:
            raise LifecycleManifestError(
                f"reviewed current file hash drift: {path}"
            )

    forbidden = [
        path
        for path in candidate_records
        if Path(path).suffix.lower() in FORBIDDEN_BINARY_SUFFIXES
        or any(
            part.casefold() in {"binaries", "intermediate"}
            for part in Path(path).parts
        )
    ]
    if forbidden:
        raise LifecycleManifestError(
            f"compiled/generated candidate output refused: {forbidden[0]}"
        )

    rollback_snapshot = _scan_two_pass(ROLLBACK_ROOT)
    rollback_records = _records_from_snapshot(rollback_snapshot)
    rollback_names = {
        "NwiroIKBridge.cpp": EXPECTED_INITIAL_FILES[
            "Source/NwiroIntegrationKit/Private/NwiroIKBridge.cpp"
        ],
        "NwiroIKMCPServer.cpp": EXPECTED_INITIAL_FILES[
            "Source/NwiroIntegrationKit/Private/NwiroIKMCPServer.cpp"
        ],
        "NwiroIKMCPServer.h": EXPECTED_INITIAL_FILES[
            "Source/NwiroIntegrationKit/Private/NwiroIKMCPServer.h"
        ],
    }
    if set(rollback_records) != set(rollback_names):
        raise LifecycleManifestError("rollback path set drift")
    for path, expected_hash in rollback_names.items():
        if rollback_records[path]["sha256"] != expected_hash:
            raise LifecycleManifestError(f"rollback hash drift: {path}")

    protected = authorization.get("protected_inputs")
    if not isinstance(protected, list):
        raise LifecycleManifestError("protected input list missing")
    for item in protected:
        if not isinstance(item, dict):
            raise LifecycleManifestError("malformed protected input")
        path = Path(str(item["path"]))
        expected_hash = str(item["sha256"])
        if _sha256(path.read_bytes()) != expected_hash:
            raise LifecycleManifestError(f"protected input drift: {path}")
    return (
        baseline,
        authorization,
        parent_candidate,
        parent_delta,
        snapshot,
        rollback_snapshot,
        tuple(changed),
        tuple(cumulative_changed),
    )


def build_documents(
    captured_utc: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if not UTC_PATTERN.fullmatch(captured_utc):
        raise LifecycleManifestError("noncanonical captured UTC")
    (
        baseline,
        authorization,
        parent_candidate,
        parent_delta,
        snapshot,
        rollback_snapshot,
        changed,
        cumulative_changed,
    ) = _authenticate_boundary()
    lineage = {
        "baseline_manifest": {
            "path": BASELINE_MANIFEST.as_posix(),
            "raw_sha256": BASELINE_MANIFEST_SHA256,
            "semantic_sha256": baseline["manifest_semantic_sha256"],
        },
        "authorization": {
            "path": AUTHORIZATION.as_posix(),
            "raw_sha256": AUTHORIZATION_SHA256,
            "parent_queue": dict(authorization["parent_queue"]),
            "parent_evidence": dict(authorization["parent_evidence"]),
        },
        "parent_activation_revision": {
            "candidate_manifest": {
                "path": PARENT_CANDIDATE_MANIFEST.as_posix(),
                "raw_sha256": authorization["candidate"][
                    "candidate_manifest_sha256"
                ],
                "semantic_sha256": parent_candidate[
                    "manifest_semantic_sha256"
                ],
            },
            "delta_manifest": {
                "path": PARENT_DELTA_MANIFEST.as_posix(),
                "raw_sha256": authorization["candidate"][
                    "delta_manifest_sha256"
                ],
                "semantic_sha256": parent_delta[
                    "manifest_semantic_sha256"
                ],
            },
            "record_set_sha256": authorization["candidate"][
                "record_set_sha256"
            ],
            "topology_sha256": authorization["candidate"][
                "topology_sha256"
            ],
        },
        "source_contract_test": {
            "path": SOURCE_CONTRACT_TEST.as_posix(),
            "raw_sha256": SOURCE_CONTRACT_TEST_SHA256,
        },
    }
    controls = {
        "central_admission_source_present": True,
        "request_lease_source_present": True,
        "retained_checked_route_handles_source_present": True,
        "partial_route_bind_rollback_source_present": True,
        "route_unbind_source_present": True,
        "session_permission_reset_source_present": True,
        "permission_id_process_monotonic_source_present": True,
        "permission_lifecycle_and_session_binding_source_present": True,
        "noninitialize_post_session_header_source_present": True,
        "owner_retained_when_listener_may_remain_source_present": True,
        "source_controls_accepted": False,
        "candidate_static_accepted": False,
        "runtime_accepted": False,
        "production_activation_authorized": False,
        "compile_authorized": False,
        "install_authorized": False,
        "unreal_launch_authorized": False,
        "mcp_authorized": False,
        "network_authorized": False,
        "provider_authorized": False,
        "asset_or_map_mutation_authorized": False,
    }
    claim_limit = (
        "Exact offline source inventory and authorized lifecycle/session delta "
        "only. No compile, plugin load, listener readiness, native concurrency, "
        "installation, MCP, provider, network, asset, map, visual, gameplay, "
        "or runtime acceptance is claimed."
    )
    candidate = _with_semantic_hash(
        {
            "schema_version": 1,
            "manifest_id": "nwiro-restricted-probe-lifecycle-candidate-v1",
            "captured_utc": captured_utc,
            "evidence_class": "static",
            "role": "external_unbuilt_candidate_source",
            "candidate_root": CANDIDATE_ROOT.as_posix(),
            "lineage": lineage,
            "controls": controls,
            "rollback_subset": rollback_snapshot.semantic_payload(),
            "known_open_blockers": [
                (
                    "UE 5.8 exposes global StartAllListeners and "
                    "StopAllListeners but no plugin-local per-port readiness "
                    "or shutdown API; listener lifecycle remains unaccepted."
                ),
                (
                    "The unchanged broad tool registry, permission-bypass "
                    "modes, reflected Bridge/Panel surfaces, ACP/provider "
                    "paths, and client-config writer remain readiness blockers."
                ),
                (
                    "The exact candidate is uncompiled, uninstalled, unrun, "
                    "and activation/readiness remain literal false."
                ),
            ],
            "cumulative_vendor_baseline_modified_paths": [
                item["path"] for item in cumulative_changed
            ],
            "claim_limit": claim_limit,
            "tree": snapshot.semantic_payload(),
        }
    )
    candidate_payload = _canonical_file_bytes(candidate)
    delta = _with_semantic_hash(
        {
            "schema_version": 1,
            "manifest_id": "nwiro-restricted-probe-lifecycle-delta-v1",
            "captured_utc": captured_utc,
            "evidence_class": "static",
            "delta_role": "cumulative_authorized_vendor_baseline_delta",
            "baseline_manifest": lineage["parent_activation_revision"][
                "candidate_manifest"
            ],
            "candidate_manifest": {
                "path": OUTPUT_CANDIDATE_MANIFEST.as_posix(),
                "raw_sha256": _sha256(candidate_payload),
                "semantic_sha256": candidate[
                    "manifest_semantic_sha256"
                ],
            },
            "baseline_record_set_sha256": parent_candidate["tree"][
                "record_set_sha256"
            ],
            "candidate_record_set_sha256": snapshot.record_set_sha256,
            "expected_modified_paths": list(EXPECTED_CHANGED_FILES),
            "counts": {
                "unchanged": snapshot.file_count - len(changed),
                "modified": len(changed),
                "added": 0,
                "removed": 0,
                "renamed": 0,
                "directories_unchanged": snapshot.directory_count_excluding_root,
                "directories_added": 0,
                "directories_removed": 0,
            },
            "modified": list(changed),
            "controls": controls,
            "same_volume_no_replace_bundle_rename_used": True,
            "whole_pair_atomic_publication_proven": False,
            "power_loss_durability_proven": False,
            "claim_limit": claim_limit,
        }
    )
    return candidate, delta


def _captured_utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )


def _load_output_bundle() -> tuple[
    TreeSnapshot,
    dict[str, Any],
    str,
    dict[str, Any],
    str,
]:
    snapshot = _scan_two_pass(OUTPUT_ROOT)
    if (
        snapshot.file_count != 2
        or snapshot.directory_count_excluding_root != 0
        or {str(record["path"]) for record in snapshot.files}
        != {"candidate.v1.json", "delta.v1.json"}
    ):
        raise LifecycleManifestError("published bundle topology drift")
    candidate, candidate_hash = _load_manifest(OUTPUT_CANDIDATE_MANIFEST)
    delta, delta_hash = _load_manifest(OUTPUT_DELTA_MANIFEST)
    records = _records_from_snapshot(snapshot)
    if records["candidate.v1.json"]["sha256"] != candidate_hash:
        raise LifecycleManifestError("candidate manifest hash drift")
    if records["delta.v1.json"]["sha256"] != delta_hash:
        raise LifecycleManifestError("delta manifest hash drift")
    return snapshot, candidate, candidate_hash, delta, delta_hash


def publish() -> dict[str, Any]:
    if _lexists(OUTPUT_ROOT):
        raise LifecycleManifestError(
            "fixed evidence root already exists; publication is no-clobber"
        )
    transaction_prefix = f".{OUTPUT_ROOT.name}.txn."
    orphans = sorted(
        child.name
        for child in STAGING_ROOT.iterdir()
        if child.name.startswith(transaction_prefix)
    )
    if orphans:
        raise LifecycleManifestError(
            f"orphan transaction namespace refused: {orphans[0]}"
        )
    captured_utc = _captured_utc_now()
    candidate, delta = build_documents(captured_utc)
    candidate_payload = _canonical_file_bytes(candidate)
    delta_payload = _canonical_file_bytes(delta)
    before = _scan_two_pass(CANDIDATE_ROOT)
    transaction_root = STAGING_ROOT / (
        f".{OUTPUT_ROOT.name}.txn.{uuid.uuid4().hex}"
    )
    candidate_temp = transaction_root / OUTPUT_CANDIDATE_MANIFEST.name
    delta_temp = transaction_root / OUTPUT_DELTA_MANIFEST.name
    published = False
    transaction_owned = False
    transaction_identity: tuple[str, str] | None = None
    try:
        transaction_root.mkdir()
        transaction_owned = True
        transaction_identity = _windows_identity(
            transaction_root,
            is_directory=True,
        )
        _apply_private_directory_acl(transaction_root)
        _require_exact_private_acl(transaction_root)
        _write_exclusive(candidate_temp, candidate_payload)
        _write_exclusive(delta_temp, delta_payload)
        for temp in (candidate_temp, delta_temp):
            _apply_private_file_acl(temp)
            _require_exact_private_acl(temp)
        if _scan_two_pass(CANDIDATE_ROOT) != before:
            raise LifecycleManifestError(
                "candidate changed before evidence publication"
            )
        _move_no_clobber(transaction_root, OUTPUT_ROOT)
        published = True
    finally:
        if (
            transaction_owned
            and not published
            and _lexists(transaction_root)
        ):
            if _windows_identity(
                transaction_root,
                is_directory=True,
            ) != transaction_identity:
                raise LifecycleManifestError(
                    "owned transaction root identity changed; cleanup refused"
                )
            for temp in (candidate_temp, delta_temp):
                if _lexists(temp):
                    temp.unlink()
            transaction_root.rmdir()
    _require_exact_private_acl(OUTPUT_ROOT)
    _require_exact_private_acl(OUTPUT_CANDIDATE_MANIFEST)
    _require_exact_private_acl(OUTPUT_DELTA_MANIFEST)
    (
        _,
        saved_candidate,
        candidate_hash,
        saved_delta,
        delta_hash,
    ) = _load_output_bundle()
    if saved_candidate != candidate or saved_delta != delta:
        raise LifecycleManifestError("published object readback drift")
    if _scan_two_pass(CANDIDATE_ROOT) != before:
        raise LifecycleManifestError("candidate changed during publication")
    return {
        "candidate_manifest": OUTPUT_CANDIDATE_MANIFEST.as_posix(),
        "candidate_manifest_sha256": candidate_hash,
        "delta_manifest": OUTPUT_DELTA_MANIFEST.as_posix(),
        "delta_manifest_sha256": delta_hash,
        "candidate_record_set_sha256": candidate["tree"][
            "record_set_sha256"
        ],
        "modified_count": len(delta["modified"]),
        "bundle_root_published_atomically": True,
    }


def verify() -> dict[str, Any]:
    _require_exact_private_acl(OUTPUT_ROOT)
    (
        _,
        saved_candidate,
        candidate_hash,
        saved_delta,
        delta_hash,
    ) = _load_output_bundle()
    captured_utc = saved_candidate.get("captured_utc")
    if saved_delta.get("captured_utc") != captured_utc:
        raise LifecycleManifestError("saved timestamps differ")
    expected_candidate, expected_delta = build_documents(str(captured_utc))
    if saved_candidate != expected_candidate:
        raise LifecycleManifestError("candidate manifest drift")
    if saved_delta != expected_delta:
        raise LifecycleManifestError("delta manifest drift")
    _require_exact_private_acl(OUTPUT_CANDIDATE_MANIFEST)
    _require_exact_private_acl(OUTPUT_DELTA_MANIFEST)
    return {
        "candidate_manifest_sha256": candidate_hash,
        "delta_manifest_sha256": delta_hash,
        "candidate_record_set_sha256": expected_candidate["tree"][
            "record_set_sha256"
        ],
        "modified_count": len(expected_delta["modified"]),
        "verified": True,
    }


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--publish", action="store_true")
    mode.add_argument("--verify", action="store_true")
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        result = publish() if args.publish else verify()
    except (LifecycleManifestError, CandidateCreationError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True))
        return 1
    print(json.dumps({"ok": True, **result}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
