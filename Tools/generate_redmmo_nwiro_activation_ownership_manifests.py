"""Publish or verify the exact offline NWIRO activation/ownership source delta.

This tool is intentionally fixed to the external, unbuilt candidate and its
authenticated historical baseline.  It never loads Unreal, starts MCP, binds a
socket, installs a plugin, or calls a provider.  Publication is no-clobber.
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
HISTORICAL_CANDIDATE_MANIFEST = (
    STAGING_ROOT / "NwiroRestrictedProbeForkCandidateV1.candidate.v1.json"
)
HISTORICAL_DELTA_MANIFEST = (
    STAGING_ROOT / "NwiroRestrictedProbeForkCandidateV1.delta.v1.json"
)
AUTHORIZATION = (
    PROJECT_ROOT
    / "Build"
    / "Automation"
    / "redmmo_nwiro_activation_ownership_execution_authorization_v1.json"
)
SOURCE_CONTRACT_TEST = (
    PROJECT_ROOT
    / "Tools"
    / "tests"
    / "test_redmmo_nwiro_activation_ownership_source.py"
)
OUTPUT_ROOT = STAGING_ROOT / "NwiroRestrictedProbeActivationOwnershipEvidenceV1"
OUTPUT_CANDIDATE_MANIFEST = OUTPUT_ROOT / "candidate.v1.json"
OUTPUT_DELTA_MANIFEST = OUTPUT_ROOT / "delta.v1.json"

BASELINE_MANIFEST_SHA256 = (
    "AACAC06301F470A270870DD48FF4085CCA44A3370E9CE504592F79D11EA7996A"
)
HISTORICAL_CANDIDATE_MANIFEST_SHA256 = (
    "089695420CDEA6C5A1C3E4FC8F392C6F0124900CD8D1D6EA660AF58A681423CE"
)
HISTORICAL_DELTA_MANIFEST_SHA256 = (
    "46353DB99034745DEFA7974B8A7A2491F23B8837D2BA3C97AEC6B4576183566C"
)
AUTHORIZATION_SHA256 = (
    "4FA858EA6FF7EE70EE8B9FB5C5234B647851421E96B90B3BB3C80F6EC934BB42"
)
EXPECTED_CHANGED_FILES = (
    "NwiroIntegrationKit.uplugin",
    "Source/NwiroIntegrationKit/Private/NwiroIKMCPServer.cpp",
    "Source/NwiroIntegrationKit/Private/NwiroIKMCPServer.h",
    "Source/NwiroIntegrationKit/Private/NwiroIntegrationKit.cpp",
    "Source/NwiroIntegrationKit/Public/NwiroIK.h",
)
EXPECTED_CURRENT_FILES = {
    "NwiroIntegrationKit.uplugin": (
        "88A59B34604759DE0657446E78DC8CB88A23837D70F0E27AF523733D8FA421F0"
    ),
    "Source/NwiroIntegrationKit/Private/NwiroIKMCPServer.cpp": (
        "AA3FD57690EB52EEADCC473DA5C15C0F6A555199A06C9EEA4EF18258ECE20099"
    ),
    "Source/NwiroIntegrationKit/Private/NwiroIKMCPServer.h": (
        "E6161EFD3E4F34DE037D329766A61D792ECC572FDCF8D83592AE99277F4AF747"
    ),
    "Source/NwiroIntegrationKit/Private/NwiroIntegrationKit.cpp": (
        "C3899FD2D50B5A13E170EC77FE2B67B1FFCFA919AB01D0B55424B322FD663E74"
    ),
    "Source/NwiroIntegrationKit/Public/NwiroIK.h": (
        "45A3E39F1E5AC4A41B716E2B2904F1D7810567423B9E04264F2605F22070C090"
    ),
}
EXPECTED_CURRENT_RECORD_SET_SHA256 = (
    "761CB39071366A680D1CE0B2900FEC1103B64206D05E67904661CD3EE215CE11"
)
EXPECTED_CURRENT_TOPOLOGY_SHA256 = (
    "7A2C6EE72ACA073C16D79DC01E6E8CB63A76DF8C9CD9291FA5D6413BF1137D18"
)
EXPECTED_SOURCE_CONTRACT_TEST_SHA256 = (
    "DA540889BC1C9B75A287CABF1B1E194A5141234BFE5DAE3D79D16A8A29E5D25A"
)
FORBIDDEN_BINARY_SUFFIXES = {
    ".dll",
    ".exe",
    ".lib",
    ".obj",
    ".pdb",
}
UTC_PATTERN = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z$"
)


class ActivationOwnershipManifestError(RuntimeError):
    """Raised when the fixed evidence boundary cannot be authenticated."""


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest().upper()


def _read_authenticated_json(path: Path, expected_sha256: str) -> dict[str, Any]:
    payload = path.read_bytes()
    observed = _sha256(payload)
    if observed != expected_sha256:
        raise ActivationOwnershipManifestError(
            f"authenticated input drift: {path} ({observed})"
        )
    value = json.loads(payload.decode("utf-8"))
    if not isinstance(value, dict):
        raise ActivationOwnershipManifestError(f"expected JSON object: {path}")
    return value


def _semantic_hash(value: Mapping[str, Any]) -> str:
    payload = dict(value)
    payload.pop("manifest_semantic_sha256", None)
    return _sha256(_canonical_file_bytes(payload))


def _with_semantic_hash(value: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(value)
    result["manifest_semantic_sha256"] = _semantic_hash(result)
    return result


def _baseline_records(
    baseline: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    tree = baseline.get("tree")
    if not isinstance(tree, dict):
        raise ActivationOwnershipManifestError("baseline tree is missing")
    files = tree.get("files")
    if not isinstance(files, list):
        raise ActivationOwnershipManifestError("baseline file list is missing")
    records: dict[str, dict[str, Any]] = {}
    for raw in files:
        if not isinstance(raw, dict):
            raise ActivationOwnershipManifestError("malformed baseline record")
        path = raw.get("path")
        if not isinstance(path, str) or path in records:
            raise ActivationOwnershipManifestError("duplicate baseline path")
        records[path] = dict(raw)
    return records


def _candidate_records(snapshot: TreeSnapshot) -> dict[str, dict[str, Any]]:
    return {str(record["path"]): dict(record) for record in snapshot.files}


def _authenticate_boundary() -> tuple[
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
    TreeSnapshot,
    TreeSnapshot,
    tuple[dict[str, Any], ...],
]:
    baseline = _read_authenticated_json(
        BASELINE_MANIFEST, BASELINE_MANIFEST_SHA256
    )
    historical_candidate = _read_authenticated_json(
        HISTORICAL_CANDIDATE_MANIFEST,
        HISTORICAL_CANDIDATE_MANIFEST_SHA256,
    )
    historical_delta = _read_authenticated_json(
        HISTORICAL_DELTA_MANIFEST,
        HISTORICAL_DELTA_MANIFEST_SHA256,
    )
    authorization = _read_authenticated_json(
        AUTHORIZATION, AUTHORIZATION_SHA256
    )
    if authorization.get("candidate_root") != CANDIDATE_ROOT.as_posix():
        raise ActivationOwnershipManifestError("authorization root drift")
    if tuple(authorization.get("exact_mutation_allowlist", ())) != (
        EXPECTED_CHANGED_FILES
    ):
        raise ActivationOwnershipManifestError("authorization allowlist drift")
    if authorization.get("file_addition_authorized") is not False:
        raise ActivationOwnershipManifestError("file additions became authorized")
    if authorization.get("file_removal_authorized") is not False:
        raise ActivationOwnershipManifestError("file removals became authorized")

    snapshot = _scan_two_pass(CANDIDATE_ROOT)
    if (
        snapshot.file_count != 90
        or snapshot.directory_count_excluding_root != 10
        or snapshot.total_bytes != 2_207_742
        or snapshot.record_set_sha256 != EXPECTED_CURRENT_RECORD_SET_SHA256
        or snapshot.topology_sha256 != EXPECTED_CURRENT_TOPOLOGY_SHA256
    ):
        raise ActivationOwnershipManifestError(
            "exact reviewed candidate snapshot drift"
        )
    baseline_records = _baseline_records(baseline)
    candidate_records = _candidate_records(snapshot)
    if set(baseline_records) != set(candidate_records):
        raise ActivationOwnershipManifestError(
            "candidate paths differ from the authenticated baseline"
        )
    changed: list[dict[str, Any]] = []
    for path in sorted(baseline_records):
        before = baseline_records[path]
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
        raise ActivationOwnershipManifestError("exact five-file delta drift")
    for path, expected_hash in EXPECTED_CURRENT_FILES.items():
        if candidate_records[path]["sha256"] != expected_hash:
            raise ActivationOwnershipManifestError(
                f"reviewed current file hash drift: {path}"
            )
    binary_paths = [
        path
        for path in candidate_records
        if Path(path).suffix.lower() in FORBIDDEN_BINARY_SUFFIXES
        or any(
            part.casefold() in {"binaries", "intermediate"}
            for part in Path(path).parts
        )
    ]
    if binary_paths:
        raise ActivationOwnershipManifestError(
            f"binary or generated candidate output refused: {binary_paths[0]}"
        )

    for protected_path, expected_hash in authorization["protected_inputs"].items():
        observed = _sha256(Path(protected_path).read_bytes())
        if observed != expected_hash:
            raise ActivationOwnershipManifestError(
                f"protected input drift: {protected_path}"
            )
    rollback_root = Path(authorization["rollback_root"])
    rollback_snapshot = _scan_two_pass(rollback_root)
    rollback_records = _candidate_records(rollback_snapshot)
    initial_files = authorization["exact_initial_files"]
    if set(rollback_records) != set(initial_files):
        raise ActivationOwnershipManifestError("rollback path-set drift")
    for path, expected_hash in initial_files.items():
        if rollback_records[path]["sha256"] != expected_hash:
            raise ActivationOwnershipManifestError(
                f"rollback hash drift: {path}"
            )
    return (
        baseline,
        historical_candidate,
        historical_delta,
        authorization,
        snapshot,
        rollback_snapshot,
        tuple(changed),
    )


def build_documents(
    captured_utc: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Build deterministic current-candidate and delta evidence documents."""

    if not UTC_PATTERN.fullmatch(captured_utc):
        raise ActivationOwnershipManifestError("noncanonical captured UTC")
    if _sha256(SOURCE_CONTRACT_TEST.read_bytes()) != (
        EXPECTED_SOURCE_CONTRACT_TEST_SHA256
    ):
        raise ActivationOwnershipManifestError("source contract test drift")
    (
        baseline,
        historical_candidate,
        historical_delta,
        authorization,
        snapshot,
        rollback_snapshot,
        changed,
    ) = _authenticate_boundary()
    lineage = {
        "baseline_manifest": {
            "path": BASELINE_MANIFEST.as_posix(),
            "raw_sha256": BASELINE_MANIFEST_SHA256,
            "semantic_sha256": baseline["manifest_semantic_sha256"],
        },
        "historical_candidate_manifest": {
            "path": HISTORICAL_CANDIDATE_MANIFEST.as_posix(),
            "raw_sha256": HISTORICAL_CANDIDATE_MANIFEST_SHA256,
            "semantic_sha256": historical_candidate[
                "manifest_semantic_sha256"
            ],
        },
        "historical_delta_manifest": {
            "path": HISTORICAL_DELTA_MANIFEST.as_posix(),
            "raw_sha256": HISTORICAL_DELTA_MANIFEST_SHA256,
            "semantic_sha256": historical_delta["manifest_semantic_sha256"],
        },
        "authorization": {
            "path": AUTHORIZATION.as_posix(),
            "raw_sha256": AUTHORIZATION_SHA256,
            "parent_queue": dict(authorization["parent_queue"]),
        },
        "source_contract_test": {
            "path": SOURCE_CONTRACT_TEST.as_posix(),
            "raw_sha256": EXPECTED_SOURCE_CONTRACT_TEST_SHA256,
        },
    }
    controls = {
        "source_default_off_implemented": True,
        "source_default_off_accepted": False,
        "process_wide_single_owner_implemented": True,
        "process_wide_single_owner_accepted": False,
        "restricted_mode_implemented": False,
        "candidate_static_accepted": False,
        "production_activation_authorized": False,
        "build_authorized": False,
        "compile_authorized": False,
        "install_authorized": False,
        "unreal_launch_authorized": False,
        "mcp_initialize_authorized": False,
        "mcp_tool_call_authorized": False,
        "network_authorized": False,
        "provider_call_authorized": False,
        "runtime_authorized": False,
        "project_asset_or_map_mutation_authorized": False,
    }
    candidate = _with_semantic_hash(
        {
            "schema_version": 1,
            "manifest_id": (
                "nwiro-restricted-probe-activation-ownership-candidate-v1"
            ),
            "captured_utc": captured_utc,
            "evidence_class": "static",
            "role": "external_unbuilt_candidate_source",
            "candidate_root": CANDIDATE_ROOT.as_posix(),
            "lineage": lineage,
            "controls": controls,
            "process_owner_scope": (
                "One retained named system-wide mutex owner across processes "
                "in the same Windows logon/session namespace; native two-process "
                "behavior and cross-session exclusivity are not proven."
            ),
            "known_open_bypasses": [
                (
                    "Unchanged reflected UNwiroIKBridge entrypoints can still "
                    "write MCP config, launch ACP processes, and enumerate "
                    "providers if an in-process caller instantiates the bridge."
                ),
                (
                    "Future live listener/request state is not yet uniformly "
                    "synchronized across admission and teardown."
                ),
                (
                    "UE HTTP route handles and per-port listener lifetime are "
                    "not retained for ownership-safe teardown or transfer."
                ),
                (
                    "Session permission state is not reset across every "
                    "restart and session-deletion path."
                ),
            ],
            "rollback_subset": rollback_snapshot.semantic_payload(),
            "claim_limit": (
                "Exact offline source inventory and authorized five-file delta "
                "only. No Unreal compile, native two-process ownership test, "
                "installation, plugin load, listener, MCP, provider, network, "
                "asset, map, visual, gameplay, or runtime acceptance is claimed."
            ),
            "tree": snapshot.semantic_payload(),
        }
    )
    candidate_payload = _canonical_file_bytes(candidate)
    delta = _with_semantic_hash(
        {
            "schema_version": 1,
            "manifest_id": (
                "nwiro-restricted-probe-activation-ownership-delta-v1"
            ),
            "captured_utc": captured_utc,
            "evidence_class": "static",
            "baseline_manifest": lineage["baseline_manifest"],
            "candidate_manifest": {
                "path": OUTPUT_CANDIDATE_MANIFEST.as_posix(),
                "raw_sha256": _sha256(candidate_payload),
                "semantic_sha256": candidate[
                    "manifest_semantic_sha256"
                ],
            },
            "baseline_record_set_sha256": baseline["tree"][
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
            "whole_pair_atomic_publication_proven": False,
            "same_volume_no_replace_bundle_rename_used": True,
            "power_loss_durability_proven": False,
            "claim_limit": candidate["claim_limit"],
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
        raise ActivationOwnershipManifestError(
            "published evidence bundle topology drift"
        )
    candidate, candidate_hash = _load_manifest(OUTPUT_CANDIDATE_MANIFEST)
    delta, delta_hash = _load_manifest(OUTPUT_DELTA_MANIFEST)
    records = _candidate_records(snapshot)
    if records["candidate.v1.json"]["sha256"] != candidate_hash:
        raise ActivationOwnershipManifestError(
            "candidate manifest identity/hash drift"
        )
    if records["delta.v1.json"]["sha256"] != delta_hash:
        raise ActivationOwnershipManifestError("delta manifest identity/hash drift")
    return snapshot, candidate, candidate_hash, delta, delta_hash


def publish() -> dict[str, Any]:
    if _lexists(OUTPUT_ROOT):
        raise ActivationOwnershipManifestError(
            "fixed evidence root already exists; publication is no-clobber"
        )
    transaction_prefix = f".{OUTPUT_ROOT.name}.txn."
    orphans = sorted(
        child.name
        for child in STAGING_ROOT.iterdir()
        if child.name.startswith(transaction_prefix)
    )
    if orphans:
        raise ActivationOwnershipManifestError(
            f"orphan transaction namespace refused: {orphans[0]}"
        )
    captured_utc = _captured_utc_now()
    candidate, delta = build_documents(captured_utc)
    candidate_payload = _canonical_file_bytes(candidate)
    delta_payload = _canonical_file_bytes(delta)
    before = _scan_two_pass(CANDIDATE_ROOT)
    nonce = uuid.uuid4().hex
    transaction_root = STAGING_ROOT / (
        f".{OUTPUT_ROOT.name}.txn.{nonce}"
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
            transaction_root, is_directory=True
        )
        _apply_private_directory_acl(transaction_root)
        _require_exact_private_acl(transaction_root)
        _write_exclusive(candidate_temp, candidate_payload)
        _write_exclusive(delta_temp, delta_payload)
        for temp in (candidate_temp, delta_temp):
            _apply_private_file_acl(temp)
            _require_exact_private_acl(temp)
        if _scan_two_pass(CANDIDATE_ROOT) != before:
            raise ActivationOwnershipManifestError(
                "candidate changed before evidence publication"
            )
        # One same-volume, no-replace directory rename commits both manifests.
        # Delta was created last inside the private transaction root.
        _move_no_clobber(transaction_root, OUTPUT_ROOT)
        published = True
    finally:
        if (
            transaction_owned
            and not published
            and _lexists(transaction_root)
        ):
            if _windows_identity(
                transaction_root, is_directory=True
            ) != transaction_identity:
                raise ActivationOwnershipManifestError(
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
        published_candidate,
        published_candidate_hash,
        published_delta,
        published_delta_hash,
    ) = _load_output_bundle()
    if published_candidate != candidate or published_delta != delta:
        raise ActivationOwnershipManifestError(
            "published bundle failed exact object readback"
        )
    after = _scan_two_pass(CANDIDATE_ROOT)
    if before != after:
        raise ActivationOwnershipManifestError(
            "candidate changed during evidence publication"
        )
    return {
        "candidate_manifest": OUTPUT_CANDIDATE_MANIFEST.as_posix(),
        "candidate_manifest_sha256": published_candidate_hash,
        "delta_manifest": OUTPUT_DELTA_MANIFEST.as_posix(),
        "delta_manifest_sha256": published_delta_hash,
        "modified_count": len(delta["modified"]),
        "candidate_record_set_sha256": candidate["tree"][
            "record_set_sha256"
        ],
        "delta_is_commit_record": True,
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
        raise ActivationOwnershipManifestError("saved capture timestamps differ")
    expected_candidate, expected_delta = build_documents(str(captured_utc))
    if saved_candidate != expected_candidate:
        raise ActivationOwnershipManifestError("candidate manifest drift")
    if saved_delta != expected_delta:
        raise ActivationOwnershipManifestError("delta manifest drift")
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
    except (ActivationOwnershipManifestError, CandidateCreationError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True))
        return 1
    print(json.dumps({"ok": True, **result}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
