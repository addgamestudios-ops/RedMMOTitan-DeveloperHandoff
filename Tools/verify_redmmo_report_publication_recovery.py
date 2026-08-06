"""Static-first recovery protocol for RED MMO report publication.

The default CLI validates authenticated JSON descriptors and prints one
deterministic dry-run report to stdout. It does not provision or inspect a
volume, create paths, spawn or terminate a process, perform a recovery scan, or
write an evidence file.

The private worker body is present for source-contract testing but remains
disabled until a later acceptance slice supplies an authenticated disposable
volume, complete outside-write tracing, and separately reviewed execution
authority.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import re
from pathlib import Path
from typing import Callable, Iterable, Mapping, Sequence

from Tools import verify_redmmo_content_storage_restore as publisher


PLAN_ID = "m07.restore-publication-recovery-harness.v1"
VOLUME_CONTRACT_ID = "m07.preprovisioned-volume-descriptor.v1"
REPORT_ID = "m07.report-publication-recovery-dry-run.v1"
VOLUME_CONTRACT_STATUS = "descriptor_only_unattested"
DRY_RUN_STATE = "VOLUME_CONTRACT_VALIDATED"
VOLUME_LABEL = "REDMMO_M07_DISPOSABLE"
SHA256_PATTERN = re.compile(r"^[0-9A-F]{64}$")
UUID_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-"
    r"[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)
CASE_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
VOLUME_GUID_PATTERN = re.compile(
    r"^\\\\\?\\Volume\{[0-9a-fA-F-]{36}\}\\$"
)
PHYSICAL_DEVICE_PATTERN = re.compile(r"^\\\\\.\\PhysicalDrive[0-9]+$")
SERIAL_PATTERN = re.compile(r"^[0-9A-F]{16}$")
SAFE_SENTINEL_NAME = ".redmmo-m07-volume-sentinel.json"
MINIMUM_DESCRIPTOR_CAPACITY_BYTES = 64 * 1024 * 1024
_WORKER_EXECUTION_ENABLED = False

EXPECTED_PLAN_CHECKPOINTS = (
    "before_temp_create",
    "after_temp_create",
    "mid_payload_write",
    "after_payload_write_before_preflush",
    "after_preflush_before_rename",
    "after_rename_before_postflush",
    "after_postflush_before_final_validation",
    "after_final_validation_before_return",
    "after_return_before_complete_ack",
    "after_complete_ack_before_clean_exit",
    "normal_success",
)

EXPECTED_VOLUME_KEYS = frozenset(
    {
        "schema_version",
        "contract_id",
        "status",
        "run_id",
        "case_id",
        "run_nonce",
        "case_nonce",
        "dry_run_worker_pid",
        "actual_volume_observed",
        "ready_for_execution",
        "filesystem",
        "volume_label",
        "capacity_bytes",
        "mount_root",
        "ledger_root",
        "terminal_mount_point_policy",
        "identity_chain",
        "sentinel",
        "requested_actions",
        "claim_limit",
    }
)
EXPECTED_IDENTITY_KEYS = frozenset(
    {
        "canonical_image_path",
        "virtual_disk_id",
        "physical_device_path",
        "disk_unique_id",
        "partition_guid",
        "volume_guid",
        "canonical_mount_path",
        "ntfs_volume_serial",
    }
)
EXPECTED_LEDGER_VALUE_KEYS = frozenset({"value", "verification"})
EXPECTED_SENTINEL_KEYS = frozenset(
    {"relative_path", "nonce", "sha256", "verification"}
)
EXPECTED_OBSERVATION_KEYS = frozenset(
    {
        "schema_version",
        "run_id",
        "case_id",
        "worker_pid",
        "run_nonce",
        "case_nonce",
        "armed_checkpoint",
        "acknowledged_checkpoint",
        "final_state",
        "staging_state",
        "complete_ack",
        "clean_exit",
        "exit_code",
        "native_identity_continuity",
        "unexpected_namespace_entries",
        "outside_writes",
        "auth_hmac_sha256",
    }
)


class RecoveryHarnessError(RuntimeError):
    """Raised when the dry-run protocol cannot fail closed."""


def _reject_duplicate_keys(
    pairs: Sequence[tuple[str, object]],
) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise RecoveryHarnessError(f"duplicate JSON key is forbidden: {key}")
        result[key] = value
    return result


def _require_plain_dict(value: object, label: str) -> dict[str, object]:
    if type(value) is not dict:
        raise RecoveryHarnessError(f"{label} must be a plain JSON object")
    return value


def _require_exact_keys(
    value: Mapping[str, object],
    expected: frozenset[str],
    label: str,
) -> None:
    observed = frozenset(value)
    if observed != expected:
        raise RecoveryHarnessError(
            f"{label} keys differ: "
            f"missing={sorted(expected - observed)} "
            f"unexpected={sorted(observed - expected)}"
        )


def _require_string(value: object, label: str) -> str:
    if type(value) is not str or not value:
        raise RecoveryHarnessError(f"{label} must be a nonempty string")
    return value


def _require_boolean(value: object, label: str) -> bool:
    if type(value) is not bool:
        raise RecoveryHarnessError(f"{label} must be a JSON boolean")
    return value


def _require_integer(value: object, label: str, *, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise RecoveryHarnessError(
            f"{label} must be an integer greater than or equal to {minimum}"
        )
    return value


def _require_digest(value: object, label: str) -> str:
    text = _require_string(value, label)
    if SHA256_PATTERN.fullmatch(text) is None:
        raise RecoveryHarnessError(
            f"{label} must be an uppercase 64-character SHA-256 digest"
        )
    return text


def _require_uuid(value: object, label: str) -> str:
    text = _require_string(value, label)
    if UUID_PATTERN.fullmatch(text) is None:
        raise RecoveryHarnessError(f"{label} must be a canonical lowercase UUID")
    return text


def _require_case_id(value: object) -> str:
    text = _require_string(value, "case_id")
    if CASE_ID_PATTERN.fullmatch(text) is None:
        raise RecoveryHarnessError("case_id must be a bounded lowercase slug")
    return text


def _require_forward_d_path(value: object, label: str) -> str:
    text = _require_string(value, label)
    if (
        not text.startswith("D:/")
        or "\\" in text
        or "//" in text
        or text.endswith("/")
        or any(component in {"", ".", ".."} for component in text[3:].split("/"))
    ):
        raise RecoveryHarnessError(
            f"{label} must be one canonical absolute forward-slash D path"
        )
    return text


def _require_plain_list(value: object, label: str) -> list[object]:
    if type(value) is not list:
        raise RecoveryHarnessError(f"{label} must be a plain JSON array")
    return value


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest().upper()


def parse_authenticated_json(
    payload: bytes,
    expected_sha256: str,
    label: str,
) -> dict[str, object]:
    _require_digest(expected_sha256, f"expected {label} SHA-256")
    observed = _sha256(payload)
    if not hmac.compare_digest(observed, expected_sha256):
        raise RecoveryHarnessError(
            f"{label} SHA-256 mismatch: "
            f"expected={expected_sha256} observed={observed}"
        )
    try:
        parsed = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=lambda token: (_ for _ in ()).throw(
                RecoveryHarnessError(
                    f"non-finite JSON number is forbidden: {token}"
                )
            ),
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RecoveryHarnessError(
            f"{label} is not valid UTF-8 JSON: {error}"
        ) from error
    return _require_plain_dict(parsed, label)


def validate_plan(plan: Mapping[str, object]) -> dict[str, object]:
    value = _require_plain_dict(plan, "recovery plan")
    if value.get("schema_version") != 1:
        raise RecoveryHarnessError("recovery plan schema_version must equal 1")
    if value.get("plan_id") != PLAN_ID:
        raise RecoveryHarnessError("unexpected recovery plan_id")
    if value.get("module_id") != "M07":
        raise RecoveryHarnessError("recovery plan module_id must equal M07")
    if value.get("evidence_class") != "static":
        raise RecoveryHarnessError("recovery plan evidence_class must be static")
    if value.get("status") not in {
        "design_only_not_executed",
        "dry_run_source_implemented_not_executed",
    }:
        raise RecoveryHarnessError("recovery plan status is not accepted")
    if value.get("requires_separate_execution_authorization") is not True:
        raise RecoveryHarnessError(
            "recovery plan must require separate execution authorization"
        )

    subject = _require_plain_dict(value.get("subject"), "plan subject")
    if subject.get("production_entrypoint") != (
        "Tools.verify_redmmo_content_storage_restore.write_report_atomic"
    ):
        raise RecoveryHarnessError("unexpected production publication entrypoint")
    if subject.get("algorithm_clone_allowed") is not False:
        raise RecoveryHarnessError("publication algorithm cloning must be denied")
    if subject.get("live_project_payload_allowed") is not False:
        raise RecoveryHarnessError("live project payload must be denied")
    if subject.get("restore_scan_allowed") is not False:
        raise RecoveryHarnessError("restore scan must be denied")

    paths = _require_plain_dict(value.get("paths"), "plan paths")
    if paths.get("network_namespaces_allowed") is not False:
        raise RecoveryHarnessError("network namespaces must remain denied")
    if paths.get("drive_letter_mount_allowed") is not False:
        raise RecoveryHarnessError("drive-letter mounts must remain denied")
    if paths.get("reparse_points_allowed") is not False:
        raise RecoveryHarnessError("general reparse points must remain denied")

    split = _require_plain_dict(
        value.get("privilege_split"),
        "plan privilege split",
    )
    for key in (
        "worker_may_elevate",
        "automatic_elevation_allowed",
        "worker_may_manage_disks",
        "controller_may_manage_disks",
    ):
        if split.get(key) is not False:
            raise RecoveryHarnessError(f"plan privilege guard {key} must be false")

    protocol = _require_plain_dict(
        value.get("checkpoint_protocol"),
        "checkpoint protocol",
    )
    checkpoints = _require_plain_list(
        protocol.get("ordered_checkpoints"),
        "ordered checkpoints",
    )
    if tuple(checkpoints) != EXPECTED_PLAN_CHECKPOINTS:
        raise RecoveryHarnessError("checkpoint order differs from the source contract")
    return value


def _validate_ledger_value(
    value: object,
    label: str,
) -> str:
    entry = _require_plain_dict(value, label)
    _require_exact_keys(entry, EXPECTED_LEDGER_VALUE_KEYS, label)
    if entry["verification"] != "ledger_only":
        raise RecoveryHarnessError(
            f"{label} must remain ledger_only during dry-run"
        )
    return _require_string(entry["value"], f"{label}.value")


def validate_volume_contract(
    contract: Mapping[str, object],
    plan: Mapping[str, object],
) -> dict[str, object]:
    value = _require_plain_dict(contract, "volume contract")
    _require_exact_keys(value, EXPECTED_VOLUME_KEYS, "volume contract")
    if value["schema_version"] != 1:
        raise RecoveryHarnessError("volume contract schema_version must equal 1")
    if value["contract_id"] != VOLUME_CONTRACT_ID:
        raise RecoveryHarnessError("unexpected volume contract_id")
    if value["status"] != VOLUME_CONTRACT_STATUS:
        raise RecoveryHarnessError("volume contract must remain descriptor-only")
    run_id = _require_uuid(value["run_id"], "run_id")
    case_id = _require_case_id(value["case_id"])
    _require_digest(value["run_nonce"], "run_nonce")
    _require_digest(value["case_nonce"], "case_nonce")
    _require_integer(value["dry_run_worker_pid"], "dry_run_worker_pid", minimum=1)
    if _require_boolean(
        value["actual_volume_observed"],
        "actual_volume_observed",
    ):
        raise RecoveryHarnessError("dry-run cannot claim an actual volume")
    if _require_boolean(value["ready_for_execution"], "ready_for_execution"):
        raise RecoveryHarnessError("dry-run cannot be ready for execution")
    if value["filesystem"] != "NTFS":
        raise RecoveryHarnessError("descriptor filesystem must equal NTFS")
    if value["volume_label"] != VOLUME_LABEL:
        raise RecoveryHarnessError("descriptor volume label differs")

    plan_value = validate_plan(plan)
    vhdx = _require_plain_dict(
        plan_value.get("vhdx_contract"),
        "plan VHDX contract",
    )
    maximum_capacity = _require_integer(
        vhdx.get("size_mib"),
        "plan VHDX size_mib",
        minimum=1,
    ) * 1024 * 1024
    capacity = _require_integer(
        value["capacity_bytes"],
        "descriptor capacity_bytes",
        minimum=MINIMUM_DESCRIPTOR_CAPACITY_BYTES,
    )
    if capacity > maximum_capacity:
        raise RecoveryHarnessError("descriptor capacity exceeds the bounded plan")

    paths = _require_plain_dict(plan_value.get("paths"), "plan paths")
    expected_mount = _require_string(
        paths.get("case_root_template"),
        "plan case root template",
    ).replace("{run_id}", run_id).replace("{case_id}", case_id)
    expected_ledger = _require_string(
        paths.get("ledger_root_template"),
        "plan ledger root template",
    ).replace("{run_id}", run_id)
    mount_root = _require_forward_d_path(value["mount_root"], "mount_root")
    ledger_root = _require_forward_d_path(value["ledger_root"], "ledger_root")
    if mount_root != expected_mount:
        raise RecoveryHarnessError("mount_root differs from the exact plan template")
    if ledger_root != expected_ledger:
        raise RecoveryHarnessError("ledger_root differs from the exact plan template")
    if value["terminal_mount_point_policy"] != (
        "future_probe_may_accept_exact_authenticated_terminal_mount_point_only"
    ):
        raise RecoveryHarnessError("terminal mount-point policy is not fail-closed")

    actions = _require_plain_list(value["requested_actions"], "requested_actions")
    if actions:
        raise RecoveryHarnessError("dry-run volume contract cannot request actions")
    claims = _require_plain_list(value["claim_limit"], "claim_limit")
    required_claims = {
        "descriptor_validation_only",
        "no_actual_volume",
        "no_process_termination",
        "no_power_loss",
        "no_physical_media_claim",
    }
    if not required_claims.issubset(set(claims)):
        raise RecoveryHarnessError("volume contract claim limits are incomplete")

    identity = _require_plain_dict(value["identity_chain"], "identity chain")
    _require_exact_keys(identity, EXPECTED_IDENTITY_KEYS, "identity chain")
    observed = {
        key: _validate_ledger_value(identity[key], f"identity_chain.{key}")
        for key in sorted(EXPECTED_IDENTITY_KEYS)
    }
    image_root = _require_string(
        paths.get("image_root_template"),
        "plan image root template",
    ).replace("{run_id}", run_id)
    expected_image = f"{image_root}/{case_id}.vhdx"
    if _require_forward_d_path(
        observed["canonical_image_path"],
        "canonical_image_path",
    ) != expected_image:
        raise RecoveryHarnessError("canonical image path differs from the plan")
    _require_uuid(observed["virtual_disk_id"], "virtual_disk_id")
    if PHYSICAL_DEVICE_PATTERN.fullmatch(
        observed["physical_device_path"]
    ) is None:
        raise RecoveryHarnessError("physical device path is malformed")
    _require_string(observed["disk_unique_id"], "disk_unique_id")
    _require_uuid(observed["partition_guid"], "partition_guid")
    if VOLUME_GUID_PATTERN.fullmatch(observed["volume_guid"]) is None:
        raise RecoveryHarnessError("volume GUID path is malformed")
    if observed["canonical_mount_path"] != mount_root:
        raise RecoveryHarnessError("identity mount path differs from mount_root")
    if SERIAL_PATTERN.fullmatch(observed["ntfs_volume_serial"]) is None:
        raise RecoveryHarnessError("NTFS volume serial must be 16 uppercase hex")

    sentinel = _require_plain_dict(value["sentinel"], "sentinel")
    _require_exact_keys(sentinel, EXPECTED_SENTINEL_KEYS, "sentinel")
    if sentinel["relative_path"] != SAFE_SENTINEL_NAME:
        raise RecoveryHarnessError("unexpected sentinel relative path")
    _require_digest(sentinel["nonce"], "sentinel nonce")
    _require_digest(sentinel["sha256"], "sentinel SHA-256")
    if sentinel["verification"] != "ledger_only":
        raise RecoveryHarnessError("sentinel must remain ledger_only in dry-run")
    return value


def _observation_auth_payload(
    observation: Mapping[str, object],
) -> bytes:
    authenticated = {
        key: observation[key]
        for key in sorted(EXPECTED_OBSERVATION_KEYS - {"auth_hmac_sha256"})
    }
    return (
        json.dumps(authenticated, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def observation_hmac(observation: Mapping[str, object]) -> str:
    run_nonce = _require_digest(observation.get("run_nonce"), "run_nonce")
    return hmac.new(
        bytes.fromhex(run_nonce),
        _observation_auth_payload(observation),
        hashlib.sha256,
    ).hexdigest().upper()


def classify_dry_run_observation(
    observation: Mapping[str, object],
    contract: Mapping[str, object],
    plan: Mapping[str, object],
) -> str:
    value = _require_plain_dict(observation, "case observation")
    _require_exact_keys(value, EXPECTED_OBSERVATION_KEYS, "case observation")
    if value["schema_version"] != 1:
        raise RecoveryHarnessError("case observation schema_version must equal 1")
    contract_value = validate_volume_contract(contract, plan)
    if value["run_id"] != contract_value["run_id"]:
        raise RecoveryHarnessError("observation run_id differs")
    if value["case_id"] != contract_value["case_id"]:
        raise RecoveryHarnessError("observation case_id differs")
    if value["run_nonce"] != contract_value["run_nonce"]:
        raise RecoveryHarnessError("observation run_nonce differs")
    if value["case_nonce"] != contract_value["case_nonce"]:
        raise RecoveryHarnessError("observation case_nonce differs")
    if value["worker_pid"] != contract_value["dry_run_worker_pid"]:
        raise RecoveryHarnessError("observation worker PID differs")
    if value["armed_checkpoint"] != contract_value["case_id"]:
        raise RecoveryHarnessError("observation armed checkpoint differs")
    if value["acknowledged_checkpoint"] != value["armed_checkpoint"]:
        return "failed_unsafe_state"
    expected_auth = observation_hmac(value)
    supplied_auth = _require_digest(
        value["auth_hmac_sha256"],
        "observation auth HMAC",
    )
    if not hmac.compare_digest(expected_auth, supplied_auth):
        raise RecoveryHarnessError("observation HMAC is invalid")

    complete_ack = _require_boolean(value["complete_ack"], "complete_ack")
    clean_exit = _require_boolean(value["clean_exit"], "clean_exit")
    identity_ok = _require_boolean(
        value["native_identity_continuity"],
        "native_identity_continuity",
    )
    unexpected = _require_integer(
        value["unexpected_namespace_entries"],
        "unexpected_namespace_entries",
    )
    outside_writes = _require_integer(
        value["outside_writes"],
        "outside_writes",
    )
    exit_code = value["exit_code"]
    if exit_code is not None and type(exit_code) is not int:
        raise RecoveryHarnessError("exit_code must be an integer or null")

    plan_value = validate_plan(plan)
    matrix = _require_plain_list(plan_value.get("case_matrix"), "case matrix")
    expected_case = next(
        (
            _require_plain_dict(row, "case matrix row")
            for row in matrix
            if isinstance(row, dict)
            and row.get("checkpoint") == value["armed_checkpoint"]
        ),
        None,
    )
    if expected_case is None:
        raise RecoveryHarnessError("armed checkpoint is absent from case matrix")

    if (
        not identity_ok
        or unexpected != 0
        or outside_writes != 0
        or value["final_state"] != expected_case.get("expected_final")
        or value["staging_state"] != expected_case.get("expected_staging")
    ):
        return "failed_unsafe_state"

    checkpoint = _require_string(value["armed_checkpoint"], "armed_checkpoint")
    expected_classification = _require_string(
        expected_case.get("classification"),
        "expected classification",
    )
    if checkpoint == "normal_success":
        if complete_ack and clean_exit and exit_code == 0:
            return "committed"
        return "interrupted_valid_final_uncommitted"
    if checkpoint == "after_complete_ack_before_clean_exit":
        if not complete_ack or clean_exit:
            return "failed_unsafe_state"
    elif complete_ack or clean_exit:
        return "failed_unsafe_state"
    return expected_classification


def build_dry_run_report(
    plan: Mapping[str, object],
    contract: Mapping[str, object],
    observation: Mapping[str, object],
) -> dict[str, object]:
    plan_value = validate_plan(plan)
    contract_value = validate_volume_contract(contract, plan_value)
    classification = classify_dry_run_observation(
        observation,
        contract_value,
        plan_value,
    )
    return {
        "schema_version": 1,
        "report_id": REPORT_ID,
        "module_id": "M07",
        "evidence_class": "static",
        "state": DRY_RUN_STATE,
        "ready_for_execution": False,
        "actual_volume_observed": False,
        "run_id": contract_value["run_id"],
        "case_id": contract_value["case_id"],
        "classification": classification,
        "evidence_booleans": {
            "process_termination_tested": False,
            "fresh_process_recovery_scan_tested": False,
            "clean_read_only_remount_tested": False,
            "abrupt_power_loss_tested": False,
            "physical_media_durability_verified": False,
        },
        "execution_blockers": [
            "terminal_mount_point_not_natively_observed",
            "vhdx_identity_chain_is_ledger_only",
            "provisioning_broker_handle_is_unavailable",
            "complete_outside_write_trace_is_unavailable",
            "worker_execution_is_disabled",
        ],
        "claim_limit": [
            "descriptor_validation_only",
            "no_actual_volume",
            "no_filesystem_mutation",
            "no_child_process",
            "no_process_termination",
            "no_recovery_scan",
            "no_remount",
            "no_power_loss",
            "no_physical_media_claim",
        ],
    }


def serialize_report(report: Mapping[str, object]) -> bytes:
    _require_plain_dict(report, "dry-run report")
    return (json.dumps(report, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _publication_worker_once(
    *,
    case_root: Path,
    payload: bytes,
    armed_checkpoint: str,
    run_id: str,
    case_id: str,
    run_nonce: str,
    case_nonce: str,
    worker_pid: int,
    send: Callable[[Mapping[str, object]], None],
) -> None:
    """Private future worker body; execution is deliberately disabled."""

    if not _WORKER_EXECUTION_ENABLED:
        raise RecoveryHarnessError(
            "publication worker execution is disabled pending live-volume "
            "attestation, complete write tracing, and separate authorization"
        )
    if armed_checkpoint not in EXPECTED_PLAN_CHECKPOINTS:
        raise RecoveryHarnessError("worker armed checkpoint is unknown")
    _require_uuid(run_id, "run_id")
    _require_case_id(case_id)
    _require_digest(run_nonce, "run_nonce")
    _require_digest(case_nonce, "case_nonce")
    _require_integer(worker_pid, "worker_pid", minimum=1)

    def emit(event: publisher.PublicationCheckpointEvent) -> None:
        send(
            {
                "run_id": run_id,
                "case_id": case_id,
                "run_nonce": run_nonce,
                "case_nonce": case_nonce,
                "worker_pid": worker_pid,
                "checkpoint": event.name,
                "candidate_name": event.candidate_name,
                "payload_size": event.payload_size,
                "bytes_written": event.bytes_written,
                "identity_volume_serial": event.identity_volume_serial,
                "file_id_128_hex": event.file_id_128_hex,
            }
        )

    with publisher._publication_checkpoint_scope(
        emit,
        armed_checkpoint=armed_checkpoint,
    ):
        publisher.write_report_atomic(
            case_root / "restore_report.json",
            payload,
            diagnostics_root=case_root,
        )
    send({"checkpoint": "after_return_before_complete_ack"})
    send({"checkpoint": "COMPLETE"})
    send({"checkpoint": "after_complete_ack_before_clean_exit"})


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Validate one M07 recovery descriptor and print a static dry-run "
            "report. No live volume or worker operation is performed."
        )
    )
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--expected-plan-sha256", required=True)
    parser.add_argument("--volume-contract", required=True, type=Path)
    parser.add_argument("--expected-volume-contract-sha256", required=True)
    parser.add_argument("--observation", required=True, type=Path)
    parser.add_argument("--expected-observation-sha256", required=True)
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    plan = validate_plan(
        parse_authenticated_json(
            args.plan.read_bytes(),
            args.expected_plan_sha256,
            "recovery plan",
        )
    )
    contract = validate_volume_contract(
        parse_authenticated_json(
            args.volume_contract.read_bytes(),
            args.expected_volume_contract_sha256,
            "volume contract",
        ),
        plan,
    )
    observation = parse_authenticated_json(
        args.observation.read_bytes(),
        args.expected_observation_sha256,
        "dry-run observation",
    )
    print(
        serialize_report(
            build_dry_run_report(plan, contract, observation)
        ).decode("utf-8"),
        end="",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
