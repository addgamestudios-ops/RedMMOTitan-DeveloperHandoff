"""Provider-off, fixture-only RedMMOTitan AI orchestration dry run.

This module deliberately has no transport, MCP client, model client, Unreal
client, subprocess runner, dynamic import, generic dispatcher, or action
executor. It authenticates three immutable mock candidate responses, validates
them against one strict contract, applies a deterministic review rubric, and
publishes a no-clobber audit report on D:.

The output disposition is only ``review_recommended`` or ``no_selection``.
Neither disposition is approval, consent, authorization, or execution.
"""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import math
import re
import stat
import sys
from contextlib import contextmanager
from ctypes import wintypes
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator, Mapping, Sequence

try:
    from Tools import verify_redmmo_content_storage_restore as secure_io
except ModuleNotFoundError:
    # Direct ``python Tools\...py`` invocation places Tools on sys.path.
    import verify_redmmo_content_storage_restore as secure_io


DEFAULT_CONTRACT = Path(
    r"D:\RedMMOTitan\Build\Automation"
    r"\redmmo_ai_orchestration_dry_run_contract_v1.json"
)
DEFAULT_DIAGNOSTICS_ROOT = Path(r"D:\RedMMOTitanWindowsData\Diagnostics")
PROJECT_ROOT = Path(r"D:\RedMMOTitan")
FIXTURE_ROOT = PROJECT_ROOT / "Build" / "Automation" / "RedMMOUnifiedAIDryRunFixtures"
EVIDENCE_ROOT = PROJECT_ROOT / "ProjectKnowledge" / "evidence"
# Patched only after the contract is final. This code-side digest prevents a
# coordinated contract re-pin from silently changing the dry-run policy.
EXPECTED_CONTRACT_SHA256 = "2592FC1DDEB8A21C96B62C6178809B501D36C0AFE6E0BA7780CF17DAA142CC16"
MAX_JSON_BYTES = 256 * 1024
MAX_TEXT_LENGTH = 16 * 1024
MAX_NODES = 5000
MAX_DEPTH = 12
MAX_SEQUENCE_LENGTH = 128
SHA256_RE = re.compile(r"^[0-9A-F]{64}$")
RUN_ID_RE = re.compile(r"^UnifiedAIDryRun_[0-9]{8}_[0-9]{6}Z$")
SECRET_OR_ENDPOINT_RE = re.compile(
    r"(?i)(https?://|127\.0\.0\.1|localhost|authorization|bearer\s+|"
    r"api[_-]?key|password|secret|token\s*=)"
)

EXPECTED_TOP_LEVEL_KEYS = {
    "schema_version",
    "contract_id",
    "status",
    "evidence_class",
    "implementation",
    "execution_policy",
    "request",
    "judge_policy",
    "candidates",
    "failure_policy",
    "consent_boundary",
    "publication",
    "claim_limits",
}
EXPECTED_IMPLEMENTATION_KEYS = {
    "language",
    "source_path",
    "tests_path",
    "verified_test_count",
    "secure_publisher_path",
    "secure_publisher_sha256",
    "secure_publisher_tests_path",
    "secure_publisher_tests_sha256",
}
EXPECTED_EXECUTION_POLICY_KEYS = {
    "network_allowed",
    "mcp_calls_allowed",
    "model_inference_allowed",
    "providers_allowed",
    "editor_launch_allowed",
    "editor_mutation_allowed",
    "tool_execution_allowed",
    "action_routing_allowed",
    "autonomous_execution_allowed",
    "report_publication_allowed",
}
EXPECTED_REQUEST_KEYS = {
    "request_id",
    "request_text",
    "request_sha256",
    "required_scope_claims",
    "required_safety_controls",
    "required_uncertainty_disclosures",
    "required_reproducibility_steps",
}
EXPECTED_JUDGE_KEYS = {
    "policy_id",
    "candidate_self_scores_accepted",
    "free_text_used_for_control_or_scoring",
    "weights",
    "tie_break_order",
    "substantive_tie_result",
    "allowed_dispositions",
}
EXPECTED_WEIGHT_KEYS = {
    "evidence",
    "scope",
    "safety",
    "uncertainty",
    "reproducibility",
}
EXPECTED_CANDIDATE_KEYS = {
    "candidate_id",
    "service_label",
    "protocol_version",
    "observed_tool_count",
    "service_evidence_path",
    "service_evidence_sha256",
    "fixture_path",
    "fixture_sha256",
    "allowed_capability_id",
    "allowed_evidence_refs",
    "allowed_assumption_ids",
    "live_execution_authorized",
}
EXPECTED_FAILURE_KEYS = {
    "invalid_candidate_result",
    "hash_drift_result",
    "unknown_field_result",
    "nonfinite_result",
    "secret_or_endpoint_result",
    "output_collision_result",
    "partial_results_allowed",
    "resume_after_poison_allowed",
}
EXPECTED_CONSENT_KEYS = {
    "action_gate_present",
    "winning_candidate_is_authorization",
    "future_action_requires_explicit_user_consent",
    "future_binding_fields",
    "ranking_can_execute",
    "prior_consent_reusable",
}
EXPECTED_PUBLICATION_KEYS = {
    "diagnostics_root",
    "no_clobber",
    "include_endpoints",
    "include_credentials",
    "include_asset_bytes",
    "include_executable_commands",
}
EXPECTED_FIXTURE_KEYS = {
    "schema_version",
    "candidate_id",
    "request_id",
    "request_sha256",
    "service_evidence_sha256",
    "response",
}
EXPECTED_RESPONSE_KEYS = {
    "answer_text",
    "evidence_refs",
    "scope_claims",
    "safety_controls",
    "uncertainty_disclosures",
    "reproducibility_steps",
    "assumptions",
    "recommended_capability",
    "tool_calls",
    "provider_calls",
    "mutations",
    "action_intents",
}
EXPECTED_CAPABILITY_KEYS = {"capability_id", "kind", "description"}

EXPECTED_CANDIDATE_IDS = ("epic_mcp", "uaip", "nwiro")
EXPECTED_PROTOCOLS = {
    "epic_mcp": "2025-11-25",
    "uaip": "2024-11-05",
    "nwiro": "2025-03-26",
}
EXPECTED_TOOL_COUNTS = {"epic_mcp": 3, "uaip": 5, "nwiro": 224}
EXPECTED_CAPABILITY_IDS = {
    "epic_mcp": "asset_registry_read_only_inspection",
    "uaip": "capability_inventory_review",
    "nwiro": "restricted_exact_identity_metadata_review",
}
EXPECTED_EVIDENCE_REFS = {
    "epic_mcp": [
        "live_runtime_identity",
        "asset_registry_closure",
        "protected_checkpoint_hashes",
    ],
    "uaip": ["live_runtime_identity", "capability_inventory"],
    "nwiro": [
        "live_runtime_identity",
        "static_wrapper_contract",
        "offline_firewall_tests",
    ],
}
EXPECTED_ASSUMPTION_IDS = {
    "epic_mcp": [],
    "uaip": ["future_exact_command_allowlist_required"],
    "nwiro": [
        "restricted_wrapper_not_live_vendor_endpoint",
        "rights_review_required",
    ],
}
EXPECTED_WEIGHTS = {
    "evidence": 30,
    "scope": 25,
    "safety": 20,
    "uncertainty": 15,
    "reproducibility": 10,
}
EXPECTED_TIE_BREAK = [
    "total_desc",
    "safety_desc",
    "evidence_desc",
    "assumption_count_asc",
]
EXPECTED_BINDING_FIELDS = [
    "candidate_digest",
    "tool_identity",
    "arguments_digest",
    "target_identity",
    "risk_class",
    "rights_boundary",
    "nonce",
    "expiry",
]
EXPECTED_SCOPE = [
    "service_identity_bound",
    "read_only_capability_only",
    "provider_off",
    "no_editor_or_asset_mutation",
    "separate_future_action_gate",
]
EXPECTED_SAFETY = [
    "pinned_fixture",
    "strict_schema",
    "no_generic_dispatch",
    "no_runtime_transport",
]
EXPECTED_UNCERTAINTY = [
    "mock_not_live_call",
    "installed_service_not_unified",
    "winning_response_not_execution_authority",
]
EXPECTED_REPRODUCIBILITY = [
    "verify_input_hashes",
    "rerun_provider_off_harness",
]
EXPECTED_CLAIM_LIMITS = [
    "This harness proves only deterministic offline scoring over three pinned mock responses.",
    "It does not call or isolate a live MCP service, provider, model, Unreal tool, or editor action.",
    "A recommendation is not approval, authorization, execution, visual acceptance, or gameplay acceptance.",
    "The code-pinned contract authenticates this dry-run policy but is not independent execution authority.",
]

EXPECTED_EXACT_PATHS = {
    "implementation.source_path": "D:/RedMMOTitan/Tools/redmmo_ai_orchestration_dry_run.py",
    "implementation.tests_path": "D:/RedMMOTitan/Tools/tests/test_redmmo_ai_orchestration_dry_run.py",
    "implementation.secure_publisher_path": (
        "D:/RedMMOTitan/Tools/verify_redmmo_content_storage_restore.py"
    ),
    "implementation.secure_publisher_tests_path": (
        "D:/RedMMOTitan/Tools/tests/test_verify_redmmo_content_storage_restore.py"
    ),
    "service_evidence_path": (
        "D:/RedMMOTitan/ProjectKnowledge/evidence/"
        "2026-07-25-unreal-ai-integration-live-runtime.yaml"
    ),
    "fixture.epic_mcp": (
        "D:/RedMMOTitan/Build/Automation/RedMMOUnifiedAIDryRunFixtures/"
        "epic_mcp_candidate.json"
    ),
    "fixture.uaip": (
        "D:/RedMMOTitan/Build/Automation/RedMMOUnifiedAIDryRunFixtures/"
        "uaip_candidate.json"
    ),
    "fixture.nwiro": (
        "D:/RedMMOTitan/Build/Automation/RedMMOUnifiedAIDryRunFixtures/"
        "nwiro_candidate.json"
    ),
}

_publication_checkpoint: Callable[[str, Path], None] | None = None


class OrchestrationDryRunError(RuntimeError):
    """Fail-closed validation or publication error."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise OrchestrationDryRunError(message)


def _require_exact_keys(value: Mapping[str, Any], expected: set[str], label: str) -> None:
    actual = set(value)
    _require(
        actual == expected,
        f"{label} keys differ: missing={sorted(expected - actual)!r} "
        f"unknown={sorted(actual - expected)!r}",
    )


def _reject_duplicate_keys(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise OrchestrationDryRunError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_nonfinite(value: str) -> None:
    raise OrchestrationDryRunError(f"nonfinite JSON number: {value}")


def _walk_limits(value: Any, *, depth: int = 0, counter: list[int] | None = None) -> None:
    if counter is None:
        counter = [0]
    counter[0] += 1
    _require(counter[0] <= MAX_NODES, "JSON node limit exceeded")
    _require(depth <= MAX_DEPTH, "JSON nesting limit exceeded")
    if isinstance(value, str):
        _require(len(value) <= MAX_TEXT_LENGTH, "JSON string limit exceeded")
    elif isinstance(value, bool) or value is None:
        return
    elif isinstance(value, int):
        _require(-(2**63) <= value <= (2**63 - 1), "JSON integer out of range")
    elif isinstance(value, float):
        _require(math.isfinite(value), "nonfinite JSON number")
    elif isinstance(value, list):
        _require(len(value) <= MAX_SEQUENCE_LENGTH, "JSON list limit exceeded")
        for item in value:
            _walk_limits(item, depth=depth + 1, counter=counter)
    elif isinstance(value, dict):
        _require(len(value) <= MAX_SEQUENCE_LENGTH, "JSON object limit exceeded")
        for key, item in value.items():
            _require(isinstance(key, str), "JSON object key must be text")
            _require(len(key) <= 128, "JSON object key limit exceeded")
            _walk_limits(item, depth=depth + 1, counter=counter)
    else:
        raise OrchestrationDryRunError(f"unsupported JSON type: {type(value).__name__}")


def canonical_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        + b"\n"
    )


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest().upper()


def read_snapshot(
    path: Path,
    max_bytes: int = MAX_JSON_BYTES,
    root: Path = PROJECT_ROOT,
) -> bytes:
    """Read through one stable file handle with path/identity cross-checks."""

    try:
        trusted_root = secure_io._require_plain_directory(root, "snapshot root")
        lexical = path.absolute()
        expected = secure_io._require_regular_file(lexical, trusted_root, "snapshot input")
        _require(0 < expected.size <= max_bytes, f"input size out of bounds: {path}")
        with secure_io._open_binary_read(lexical) as handle:
            opened = secure_io._open_file_metadata(handle, lexical, "snapshot input")
            _require(opened == expected, f"input identity changed before read: {path}")
            before = secure_io._require_regular_file(
                lexical, trusted_root, "snapshot input"
            )
            _require(before == opened, f"input path changed before read: {path}")
            payload = handle.read(max_bytes + 1)
            _require(len(payload) <= max_bytes, f"input exceeds byte limit: {path}")
            after_handle = secure_io._open_file_metadata(
                handle, lexical, "snapshot input"
            )
            _require(
                after_handle == opened and len(payload) == opened.size,
                f"input changed through stable handle: {path}",
            )
            after_path = secure_io._require_regular_file(
                lexical, trusted_root, "snapshot input"
            )
            _require(after_path == opened, f"input path changed after read: {path}")
            return payload
    except OrchestrationDryRunError:
        raise
    except secure_io.RestoreVerificationError as exc:
        raise OrchestrationDryRunError(f"secure snapshot failed: {path}: {exc}") from exc


def load_json_bytes_strict(payload: bytes, label: str) -> dict[str, Any]:
    _require(len(payload) <= MAX_JSON_BYTES, f"{label} exceeds JSON byte limit")
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise OrchestrationDryRunError(f"{label} is not UTF-8") from exc
    try:
        value = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_nonfinite,
        )
    except OrchestrationDryRunError:
        raise
    except (json.JSONDecodeError, ValueError) as exc:
        raise OrchestrationDryRunError(f"{label} is not strict JSON: {exc}") from exc
    _require(isinstance(value, dict), f"{label} root must be an object")
    _walk_limits(value)
    return value


def load_json_strict(path: Path) -> dict[str, Any]:
    return load_json_bytes_strict(read_snapshot(path), str(path))


def _require_sha(value: Any, label: str) -> str:
    _require(isinstance(value, str) and bool(SHA256_RE.fullmatch(value)), f"{label} invalid")
    return value


def _require_exact_int(value: Any, expected: int, label: str) -> int:
    _require(type(value) is int and value == expected, f"{label} must be integer {expected}")
    return value


def _require_string(value: Any, label: str, *, max_length: int = 2048) -> str:
    _require(isinstance(value, str), f"{label} must be text")
    _require(0 < len(value) <= max_length, f"{label} length invalid")
    return value


def _require_exact_path(value: Any, expected_key: str, label: str) -> Path:
    text = _require_string(value, label, max_length=512)
    expected = EXPECTED_EXACT_PATHS[expected_key]
    _require(text == expected, f"{label} path identity drift")
    path = Path(text)
    _require(path.is_absolute(), f"{label} must be absolute")
    return path


def _require_unique_string_list(
    value: Any,
    label: str,
    *,
    maximum: int = 32,
    allowed: Iterable[str] | None = None,
) -> list[str]:
    _require(isinstance(value, list), f"{label} must be a list")
    _require(len(value) <= maximum, f"{label} is too long")
    _require(all(isinstance(item, str) and item for item in value), f"{label} entries invalid")
    _require(len(value) == len(set(value)), f"{label} contains duplicates")
    if allowed is not None:
        allowed_set = set(allowed)
        unknown = set(value) - allowed_set
        _require(not unknown, f"{label} contains unknown entries: {sorted(unknown)!r}")
    return list(value)


def _iter_strings(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for item in value:
            yield from _iter_strings(item)
    elif isinstance(value, dict):
        for item in value.values():
            yield from _iter_strings(item)


def _require_no_secret_or_endpoint(value: Any, label: str) -> None:
    for text in _iter_strings(value):
        _require(
            SECRET_OR_ENDPOINT_RE.search(text) is None,
            f"{label} contains an endpoint or credential-like string",
        )


def validate_contract_schema(contract: dict[str, Any]) -> None:
    _require_exact_keys(contract, EXPECTED_TOP_LEVEL_KEYS, "contract")
    _require_exact_int(contract["schema_version"], 1, "contract.schema_version")
    _require(
        contract["contract_id"] == "REDMMO-M07-UNIFIED-AI-ORCHESTRATION-DRY-RUN-V1",
        "contract identity drift",
    )
    _require(contract["status"] == "provider_off_static_dry_run", "contract status drift")
    _require(contract["evidence_class"] == "static_mock_dry_run", "evidence class drift")

    implementation = contract["implementation"]
    _require(isinstance(implementation, dict), "implementation must be an object")
    _require_exact_keys(implementation, EXPECTED_IMPLEMENTATION_KEYS, "implementation")
    _require(implementation["language"] == "python_standard_library_only", "language drift")
    _require_exact_path(
        implementation["source_path"],
        "implementation.source_path",
        "implementation.source_path",
    )
    _require_exact_path(
        implementation["tests_path"],
        "implementation.tests_path",
        "implementation.tests_path",
    )
    _require_exact_int(
        implementation["verified_test_count"], 28, "implementation.verified_test_count"
    )
    _require_exact_path(
        implementation["secure_publisher_path"],
        "implementation.secure_publisher_path",
        "implementation.secure_publisher_path",
    )
    _require_sha(
        implementation["secure_publisher_sha256"],
        "implementation.secure_publisher_sha256",
    )
    _require_exact_path(
        implementation["secure_publisher_tests_path"],
        "implementation.secure_publisher_tests_path",
        "implementation.secure_publisher_tests_path",
    )
    _require_sha(
        implementation["secure_publisher_tests_sha256"],
        "implementation.secure_publisher_tests_sha256",
    )

    execution = contract["execution_policy"]
    _require(isinstance(execution, dict), "execution_policy must be an object")
    _require_exact_keys(execution, EXPECTED_EXECUTION_POLICY_KEYS, "execution_policy")
    for key, value in execution.items():
        expected = key == "report_publication_allowed"
        _require(value is expected, f"execution_policy.{key} must be {expected}")

    request = contract["request"]
    _require(isinstance(request, dict), "request must be an object")
    _require_exact_keys(request, EXPECTED_REQUEST_KEYS, "request")
    _require(request["request_id"] == "M07-UNIFIED-AI-DRY-RUN-001", "request id drift")
    request_text = _require_string(request["request_text"], "request_text")
    request_sha = _require_sha(request["request_sha256"], "request_sha256")
    _require(sha256_bytes(request_text.encode("utf-8")) == request_sha, "request hash drift")
    _require(request["required_scope_claims"] == EXPECTED_SCOPE, "scope rubric drift")
    _require(request["required_safety_controls"] == EXPECTED_SAFETY, "safety rubric drift")
    _require(
        request["required_uncertainty_disclosures"] == EXPECTED_UNCERTAINTY,
        "uncertainty rubric drift",
    )
    _require(
        request["required_reproducibility_steps"] == EXPECTED_REPRODUCIBILITY,
        "reproducibility rubric drift",
    )

    judge = contract["judge_policy"]
    _require(isinstance(judge, dict), "judge_policy must be an object")
    _require_exact_keys(judge, EXPECTED_JUDGE_KEYS, "judge_policy")
    _require(judge["policy_id"] == "REDMMO-DETERMINISTIC-REVIEW-JUDGE-V1", "judge drift")
    _require(judge["candidate_self_scores_accepted"] is False, "self scores forbidden")
    _require(judge["free_text_used_for_control_or_scoring"] is False, "free text forbidden")
    _require(isinstance(judge["weights"], dict), "weights must be an object")
    _require_exact_keys(judge["weights"], EXPECTED_WEIGHT_KEYS, "weights")
    for key, expected in EXPECTED_WEIGHTS.items():
        _require_exact_int(judge["weights"][key], expected, f"weights.{key}")
    _require(judge["tie_break_order"] == EXPECTED_TIE_BREAK, "tie break drift")
    _require(judge["substantive_tie_result"] == "no_selection", "tie result drift")
    _require(
        judge["allowed_dispositions"] == ["review_recommended", "no_selection"],
        "disposition set drift",
    )

    candidates = contract["candidates"]
    _require(isinstance(candidates, list) and len(candidates) == 3, "exactly three candidates required")
    candidate_ids: list[str] = []
    fixture_paths: list[str] = []
    capability_ids: list[str] = []
    for index, candidate in enumerate(candidates):
        _require(isinstance(candidate, dict), f"candidate[{index}] must be an object")
        _require_exact_keys(candidate, EXPECTED_CANDIDATE_KEYS, f"candidate[{index}]")
        candidate_id = _require_string(candidate["candidate_id"], "candidate_id", max_length=32)
        candidate_ids.append(candidate_id)
        _require(
            candidate["protocol_version"] == EXPECTED_PROTOCOLS.get(candidate_id),
            f"{candidate_id} protocol drift",
        )
        _require_exact_int(
            candidate["observed_tool_count"],
            EXPECTED_TOOL_COUNTS.get(candidate_id, -1),
            f"{candidate_id}.observed_tool_count",
        )
        _require_string(candidate["service_label"], f"{candidate_id}.service_label", max_length=128)
        evidence_path = _require_exact_path(
            candidate["service_evidence_path"],
            "service_evidence_path",
            f"{candidate_id}.service_evidence_path",
        )
        _require_sha(candidate["service_evidence_sha256"], f"{candidate_id}.evidence_sha256")
        fixture_path = _require_exact_path(
            candidate["fixture_path"],
            f"fixture.{candidate_id}",
            f"{candidate_id}.fixture_path",
        )
        fixture_paths.append(fixture_path.as_posix())
        _require_sha(candidate["fixture_sha256"], f"{candidate_id}.fixture_sha256")
        capability_id = _require_string(
            candidate["allowed_capability_id"], f"{candidate_id}.allowed_capability_id"
        )
        _require(
            capability_id == EXPECTED_CAPABILITY_IDS[candidate_id],
            f"{candidate_id} capability allowlist drift",
        )
        capability_ids.append(capability_id)
        evidence_refs = _require_unique_string_list(
            candidate["allowed_evidence_refs"],
            f"{candidate_id}.allowed_evidence_refs",
            maximum=8,
        )
        _require(
            evidence_refs == EXPECTED_EVIDENCE_REFS[candidate_id],
            f"{candidate_id} evidence allowlist drift",
        )
        assumption_ids = _require_unique_string_list(
            candidate["allowed_assumption_ids"],
            f"{candidate_id}.allowed_assumption_ids",
            maximum=4,
        )
        _require(
            assumption_ids == EXPECTED_ASSUMPTION_IDS[candidate_id],
            f"{candidate_id} assumption allowlist drift",
        )
        _require(candidate["live_execution_authorized"] is False, "live execution forbidden")
    _require(tuple(candidate_ids) == EXPECTED_CANDIDATE_IDS, "candidate identity/order drift")
    _require(len(set(fixture_paths)) == 3, "fixture paths must be unique")
    _require(len(set(capability_ids)) == 3, "capability ids must be unique")

    failure = contract["failure_policy"]
    _require(isinstance(failure, dict), "failure_policy must be an object")
    _require_exact_keys(failure, EXPECTED_FAILURE_KEYS, "failure_policy")
    for key in (
        "invalid_candidate_result",
        "hash_drift_result",
        "unknown_field_result",
        "nonfinite_result",
        "secret_or_endpoint_result",
    ):
        _require(failure[key] == "poison_run_no_selection", f"{key} must poison")
    _require(failure["output_collision_result"] == "fail_no_clobber", "collision policy drift")
    _require(failure["partial_results_allowed"] is False, "partial results forbidden")
    _require(failure["resume_after_poison_allowed"] is False, "resume after poison forbidden")

    consent = contract["consent_boundary"]
    _require(isinstance(consent, dict), "consent_boundary must be an object")
    _require_exact_keys(consent, EXPECTED_CONSENT_KEYS, "consent_boundary")
    _require(consent["action_gate_present"] is False, "action gate must be absent")
    _require(consent["winning_candidate_is_authorization"] is False, "winner is not authority")
    _require(
        consent["future_action_requires_explicit_user_consent"] is True,
        "future consent requirement cannot be removed",
    )
    _require(consent["future_binding_fields"] == EXPECTED_BINDING_FIELDS, "binding fields drift")
    _require(consent["ranking_can_execute"] is False, "ranking cannot execute")
    _require(consent["prior_consent_reusable"] is False, "prior consent cannot be reused")

    publication = contract["publication"]
    _require(isinstance(publication, dict), "publication must be an object")
    _require_exact_keys(publication, EXPECTED_PUBLICATION_KEYS, "publication")
    _require(
        publication["diagnostics_root"] == DEFAULT_DIAGNOSTICS_ROOT.as_posix(),
        "diagnostics root drift",
    )
    _require(publication["no_clobber"] is True, "publication must be no-clobber")
    for key in (
        "include_endpoints",
        "include_credentials",
        "include_asset_bytes",
        "include_executable_commands",
    ):
        _require(publication[key] is False, f"publication.{key} must be false")

    _require(contract["claim_limits"] == EXPECTED_CLAIM_LIMITS, "claim limits drift")


def _snapshot_record(kind: str, path: Path, payload: bytes) -> dict[str, Any]:
    return {
        "kind": kind,
        "path": path.as_posix(),
        "bytes": len(payload),
        "sha256": sha256_bytes(payload),
    }


def authenticate_contract_inputs(
    contract: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, bytes]]:
    records: list[dict[str, Any]] = []
    snapshots: dict[str, bytes] = {}
    for kind, path_key in (
        ("implementation_source", "source_path"),
        ("implementation_tests", "tests_path"),
    ):
        path = Path(contract["implementation"][path_key])
        payload = read_snapshot(path, max_bytes=2 * 1024 * 1024)
        snapshots[path.as_posix()] = payload
        records.append(_snapshot_record(kind, path, payload))
    for kind, path_key, hash_key in (
        (
            "secure_publisher_source",
            "secure_publisher_path",
            "secure_publisher_sha256",
        ),
        (
            "secure_publisher_tests",
            "secure_publisher_tests_path",
            "secure_publisher_tests_sha256",
        ),
    ):
        path = Path(contract["implementation"][path_key])
        payload = read_snapshot(path, max_bytes=4 * 1024 * 1024)
        _require(
            sha256_bytes(payload) == contract["implementation"][hash_key],
            f"{kind} hash drift",
        )
        snapshots[path.as_posix()] = payload
        records.append(_snapshot_record(kind, path, payload))
    seen_evidence: set[str] = set()
    for candidate in contract["candidates"]:
        candidate_id = candidate["candidate_id"]
        fixture_path = Path(candidate["fixture_path"])
        fixture_payload = read_snapshot(fixture_path)
        _require(
            sha256_bytes(fixture_payload) == candidate["fixture_sha256"],
            f"{candidate_id} fixture hash drift",
        )
        snapshots[fixture_path.as_posix()] = fixture_payload
        records.append(_snapshot_record("candidate_fixture", fixture_path, fixture_payload))

        evidence_path = Path(candidate["service_evidence_path"])
        key = evidence_path.as_posix()
        if key not in seen_evidence:
            evidence_payload = read_snapshot(evidence_path, max_bytes=2 * 1024 * 1024)
            _require(
                sha256_bytes(evidence_payload) == candidate["service_evidence_sha256"],
                f"{candidate_id} service evidence hash drift",
            )
            snapshots[key] = evidence_payload
            records.append(_snapshot_record("service_evidence", evidence_path, evidence_payload))
            seen_evidence.add(key)
    return records, snapshots


def validate_candidate_fixture(
    fixture: dict[str, Any],
    candidate_contract: dict[str, Any],
    request: dict[str, Any],
) -> dict[str, Any]:
    candidate_id = candidate_contract["candidate_id"]
    _require_exact_keys(fixture, EXPECTED_FIXTURE_KEYS, f"{candidate_id} fixture")
    _require_exact_int(fixture["schema_version"], 1, f"{candidate_id}.schema_version")
    _require(fixture["candidate_id"] == candidate_id, f"{candidate_id} identity drift")
    _require(fixture["request_id"] == request["request_id"], f"{candidate_id} request id drift")
    _require(
        fixture["request_sha256"] == request["request_sha256"],
        f"{candidate_id} request hash drift",
    )
    _require(
        fixture["service_evidence_sha256"] == candidate_contract["service_evidence_sha256"],
        f"{candidate_id} evidence identity drift",
    )

    response = fixture["response"]
    _require(isinstance(response, dict), f"{candidate_id} response must be an object")
    _require_exact_keys(response, EXPECTED_RESPONSE_KEYS, f"{candidate_id} response")
    answer_text = _require_string(response["answer_text"], f"{candidate_id}.answer_text")
    _require_no_secret_or_endpoint(response, f"{candidate_id} response")

    evidence_refs = _require_unique_string_list(
        response["evidence_refs"],
        f"{candidate_id}.evidence_refs",
        maximum=3,
        allowed=candidate_contract["allowed_evidence_refs"],
    )
    scope_claims = _require_unique_string_list(
        response["scope_claims"],
        f"{candidate_id}.scope_claims",
        maximum=len(EXPECTED_SCOPE),
        allowed=request["required_scope_claims"],
    )
    _require(
        scope_claims == request["required_scope_claims"],
        f"{candidate_id} missing required scope claim",
    )
    safety_controls = _require_unique_string_list(
        response["safety_controls"],
        f"{candidate_id}.safety_controls",
        maximum=len(EXPECTED_SAFETY),
        allowed=request["required_safety_controls"],
    )
    _require(
        safety_controls == request["required_safety_controls"],
        f"{candidate_id} missing required safety control",
    )
    uncertainty = _require_unique_string_list(
        response["uncertainty_disclosures"],
        f"{candidate_id}.uncertainty_disclosures",
        maximum=len(EXPECTED_UNCERTAINTY),
        allowed=request["required_uncertainty_disclosures"],
    )
    _require(
        uncertainty == request["required_uncertainty_disclosures"],
        f"{candidate_id} missing required uncertainty disclosure",
    )
    reproducibility = _require_unique_string_list(
        response["reproducibility_steps"],
        f"{candidate_id}.reproducibility_steps",
        maximum=len(EXPECTED_REPRODUCIBILITY),
        allowed=request["required_reproducibility_steps"],
    )
    _require(
        reproducibility == request["required_reproducibility_steps"],
        f"{candidate_id} missing required reproducibility step",
    )
    assumptions = _require_unique_string_list(
        response["assumptions"],
        f"{candidate_id}.assumptions",
        maximum=4,
        allowed=candidate_contract["allowed_assumption_ids"],
    )
    _require(
        assumptions == candidate_contract["allowed_assumption_ids"],
        f"{candidate_id} assumption-id set drift",
    )

    capability = response["recommended_capability"]
    _require(isinstance(capability, dict), f"{candidate_id} capability must be an object")
    _require_exact_keys(capability, EXPECTED_CAPABILITY_KEYS, f"{candidate_id} capability")
    _require(
        capability["capability_id"] == candidate_contract["allowed_capability_id"],
        f"{candidate_id} capability id drift",
    )
    _require(capability["kind"] == "read_only_planning", f"{candidate_id} capability kind drift")
    _require_string(capability["description"], f"{candidate_id}.capability.description")

    for key in ("tool_calls", "provider_calls", "mutations", "action_intents"):
        _require(response[key] == [], f"{candidate_id}.{key} must be empty")

    normalized = {
        "candidate_id": candidate_id,
        "answer_text_display_only": answer_text,
        "answer_text_used_for_control_or_scoring": False,
        "evidence_refs": sorted(evidence_refs),
        "scope_claims": sorted(scope_claims),
        "safety_controls": sorted(safety_controls),
        "uncertainty_disclosures": sorted(uncertainty),
        "reproducibility_steps": sorted(reproducibility),
        "assumptions": assumptions,
        "recommended_capability": {
            "capability_id": capability["capability_id"],
            "kind": capability["kind"],
            "description_display_only": capability["description"],
        },
        "forbidden_lists_empty": True,
        "eligible_for_offline_review": True,
    }
    normalized["normalized_sha256"] = sha256_bytes(canonical_json_bytes(normalized))
    return normalized


def score_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    evidence = len(candidate["evidence_refs"]) * 10
    scope = len(candidate["scope_claims"]) * 5
    safety = len(candidate["safety_controls"]) * 5
    uncertainty = len(candidate["uncertainty_disclosures"]) * 5
    reproducibility = len(candidate["reproducibility_steps"]) * 5
    _require(evidence <= EXPECTED_WEIGHTS["evidence"], "evidence score overflow")
    _require(scope <= EXPECTED_WEIGHTS["scope"], "scope score overflow")
    _require(safety <= EXPECTED_WEIGHTS["safety"], "safety score overflow")
    _require(uncertainty <= EXPECTED_WEIGHTS["uncertainty"], "uncertainty score overflow")
    _require(
        reproducibility <= EXPECTED_WEIGHTS["reproducibility"],
        "reproducibility score overflow",
    )
    breakdown = {
        "evidence": evidence,
        "scope": scope,
        "safety": safety,
        "uncertainty": uncertainty,
        "reproducibility": reproducibility,
    }
    return {
        "candidate_id": candidate["candidate_id"],
        "eligible": candidate["eligible_for_offline_review"],
        "breakdown": breakdown,
        "total": sum(breakdown.values()),
        "assumption_count": len(candidate["assumptions"]),
        "candidate_self_score_used": False,
        "free_text_used": False,
    }


def select_review_candidate(scores: list[dict[str, Any]]) -> tuple[str, str | None, str]:
    eligible = [item for item in scores if item["eligible"]]
    if not eligible:
        return "no_selection", None, "no eligible candidate"
    finalists = eligible
    for key, reverse in (
        ("total", True),
        ("safety", True),
        ("evidence", True),
        ("assumption_count", False),
    ):
        if key in {"safety", "evidence"}:
            values = [item["breakdown"][key] for item in finalists]
            target = max(values) if reverse else min(values)
            finalists = [item for item in finalists if item["breakdown"][key] == target]
        else:
            values = [item[key] for item in finalists]
            target = max(values) if reverse else min(values)
            finalists = [item for item in finalists if item[key] == target]
        if len(finalists) == 1:
            return (
                "review_recommended",
                finalists[0]["candidate_id"],
                f"unique winner after {key}",
            )
    return "no_selection", None, "substantive tie after all approved tie breaks"


def build_report(
    contract: dict[str, Any],
    contract_path: Path,
    contract_payload: bytes,
    authenticated_inputs: list[dict[str, Any]],
    normalized_candidates: list[dict[str, Any]],
) -> dict[str, Any]:
    scores = [score_candidate(candidate) for candidate in normalized_candidates]
    disposition, selected, reason = select_review_candidate(scores)
    report = {
        "schema_version": 1,
        "report_id": "REDMMO-M07-UNIFIED-AI-ORCHESTRATION-DRY-RUN-REPORT-V1",
        "status": disposition,
        "evidence_class": "static_mock_dry_run",
        "contract": {
            "path": contract_path.as_posix(),
            "sha256": sha256_bytes(contract_payload),
            "contract_id": contract["contract_id"],
        },
        "authenticated_inputs": sorted(
            authenticated_inputs, key=lambda item: (item["kind"], item["path"])
        ),
        "execution_observed": {
            "network_calls": False,
            "mcp_calls": False,
            "model_or_provider_calls": False,
            "editor_launch": False,
            "tool_calls": False,
            "action_routing": False,
            "mutations": False,
            "autonomous_execution": False,
        },
        "judge": {
            "policy_id": contract["judge_policy"]["policy_id"],
            "weights": contract["judge_policy"]["weights"],
            "tie_break_order": contract["judge_policy"]["tie_break_order"],
            "scores": sorted(scores, key=lambda item: item["candidate_id"]),
            "selected_candidate_id": selected,
            "selection_reason": reason,
            "candidate_self_scores_accepted": False,
            "free_text_used_for_control_or_scoring": False,
        },
        "candidates": sorted(normalized_candidates, key=lambda item: item["candidate_id"]),
        "consent_boundary": {
            **contract["consent_boundary"],
            "execution_authorized_by_this_report": False,
            "winning_action_executed": False,
        },
        "claim_limits": contract["claim_limits"],
    }
    report["report_content_sha256"] = sha256_bytes(canonical_json_bytes(report))
    return report


def validate_contract_file(
    contract_path: Path = DEFAULT_CONTRACT,
) -> tuple[
    dict[str, Any],
    bytes,
    list[dict[str, Any]],
    dict[str, bytes],
    list[dict[str, Any]],
]:
    contract_path = contract_path.resolve()
    contract_payload = read_snapshot(contract_path)
    _require(
        sha256_bytes(contract_payload) == EXPECTED_CONTRACT_SHA256,
        "canonical contract digest does not match the code-pinned policy",
    )
    contract = load_json_bytes_strict(contract_payload, str(contract_path))
    validate_contract_schema(contract)
    records, snapshots = authenticate_contract_inputs(contract)
    normalized: list[dict[str, Any]] = []
    for candidate in contract["candidates"]:
        fixture_path = Path(candidate["fixture_path"])
        fixture_payload = snapshots[fixture_path.as_posix()]
        fixture = load_json_bytes_strict(fixture_payload, str(fixture_path))
        normalized.append(validate_candidate_fixture(fixture, candidate, contract["request"]))
    _require(
        tuple(item["candidate_id"] for item in normalized) == EXPECTED_CANDIDATE_IDS,
        "normalized candidate set drift",
    )
    snapshots[contract_path.as_posix()] = contract_payload
    return contract, contract_payload, records, snapshots, normalized


def reauthenticate_before_publication(snapshots: Mapping[str, bytes]) -> None:
    for path_text, expected_payload in sorted(snapshots.items()):
        path = Path(path_text)
        current = read_snapshot(path, max_bytes=max(MAX_JSON_BYTES, len(expected_payload)))
        _require(current == expected_payload, f"input changed before publication: {path}")


def _emit_publication_checkpoint(name: str, path: Path) -> None:
    callback = _publication_checkpoint
    if callback is not None:
        callback(name, path)


def _windows_create_new_directory_relative(parent_handle: int, name: str) -> int:
    """Create one must-be-new child directory relative to a retained handle."""

    secure_io._validate_windows_component(name, "orchestration run directory")
    _, ntdll = secure_io._windows_apis()
    name_storage = ctypes.create_unicode_buffer(name)
    encoded = name.encode("utf-16-le")
    counted_name = secure_io._WindowsUnicodeString(
        len(encoded),
        len(encoded) + 2,
        ctypes.cast(name_storage, wintypes.LPWSTR),
    )
    attributes = secure_io._WindowsObjectAttributes(
        ctypes.sizeof(secure_io._WindowsObjectAttributes),
        parent_handle,
        ctypes.pointer(counted_name),
        secure_io.WINDOWS_OBJ_CASE_INSENSITIVE,
        None,
        None,
    )
    io_status = secure_io._WindowsIoStatusBlock()
    output = wintypes.HANDLE()
    status = int(
        ntdll.NtCreateFile(
            ctypes.byref(output),
            secure_io.WINDOWS_DIRECTORY_ACCESS,
            ctypes.byref(attributes),
            ctypes.byref(io_status),
            None,
            secure_io.WINDOWS_FILE_ATTRIBUTE_DIRECTORY,
            secure_io.WINDOWS_FILE_SHARE_ALL,
            secure_io.WINDOWS_FILE_CREATE,
            secure_io.WINDOWS_FILE_DIRECTORY_FILE
            | secure_io.WINDOWS_FILE_WRITE_THROUGH
            | secure_io.WINDOWS_FILE_SYNCHRONOUS_IO_NONALERT
            | secure_io.WINDOWS_FILE_OPEN_REPARSE_POINT,
            None,
            0,
        )
    )
    if status < 0:
        _, error = secure_io._windows_nt_error(
            status,
            f"exclusive orchestration run-directory create for {name!r}",
        )
        raise error
    if (
        not output.value
        or output.value == secure_io.WINDOWS_INVALID_HANDLE_VALUE
    ):
        raise secure_io.RestoreVerificationError(
            f"exclusive run-directory create returned an invalid handle: {name!r}"
        )
    return int(output.value)


@contextmanager
def _windows_exclusive_run_directory(
    root: Path,
    run_id: str,
) -> Iterator[tuple[int, secure_io.WindowsHandleMetadata, Path]]:
    resolved_root = secure_io._require_plain_directory(root, "diagnostics root")
    expected_root = secure_io._metadata(resolved_root)
    root_handle, _ = secure_io._windows_open_pinned_directory(
        resolved_root,
        expected_root,
        "diagnostics root",
    )
    run_handle: int | None = None
    run_path = resolved_root / run_id
    try:
        secure_io._windows_require_ntfs(root_handle, "diagnostics root")
        _emit_publication_checkpoint("before_run_directory_create", run_path)
        run_handle = _windows_create_new_directory_relative(root_handle, run_id)
        run_identity = secure_io._windows_require_plain_directory_handle(
            run_handle,
            "orchestration run directory",
        )
        observed_path = secure_io._metadata(run_path)
        if (
            secure_io._is_link_or_reparse(run_path, observed_path)
            or (observed_path.device, observed_path.inode)
            != (run_identity.volume_serial, run_identity.file_id)
        ):
            raise secure_io.RestoreVerificationError(
                "new run-directory path does not name the retained directory handle"
            )
        yield run_handle, run_identity, run_path
    finally:
        if run_handle is not None:
            secure_io._windows_close_handle(run_handle)
        secure_io._windows_close_handle(root_handle)


def _windows_publish_report_in_new_run_directory(
    root: Path,
    run_id: str,
    payload: bytes,
) -> Path:
    with _windows_exclusive_run_directory(root, run_id) as (
        run_handle,
        run_identity,
        run_path,
    ):
        stage_name = ".orchestration-report-stage.tmp"
        final_name = "orchestration_report.json"
        stage_handle, _ = secure_io._windows_nt_create_relative(
            run_handle,
            stage_name,
            directory=False,
        )
        committed = False
        try:
            opened = secure_io._windows_handle_metadata(
                stage_handle,
                "orchestration report stage file",
            )
            if (
                opened.attributes
                & (
                    secure_io.WINDOWS_FILE_ATTRIBUTE_DIRECTORY
                    | secure_io.WINDOWS_FILE_ATTRIBUTE_REPARSE_POINT
                )
                or opened.link_count != 1
                or opened.size != 0
            ):
                raise secure_io.RestoreVerificationError(
                    "new orchestration report stage handle has unsafe metadata"
                )
            secure_io._windows_write_and_flush(stage_handle, payload)
            written = secure_io._windows_handle_metadata(
                stage_handle,
                "written orchestration report stage file",
            )
            if (
                (
                    written.identity_volume_serial,
                    written.file_id_128,
                )
                != (
                    opened.identity_volume_serial,
                    opened.file_id_128,
                )
                or written.size != len(payload)
                or written.link_count != 1
                or written.attributes & secure_io.WINDOWS_FILE_ATTRIBUTE_REPARSE_POINT
            ):
                raise secure_io.RestoreVerificationError(
                    "orchestration report stage identity changed before publication"
                )
            secure_io._windows_publish_open_file_no_clobber(
                stage_handle,
                run_handle,
                final_name,
            )
            path_parent = secure_io._metadata(run_path)
            report_path = run_path / final_name
            published = secure_io._metadata(report_path)
            if (
                secure_io._is_link_or_reparse(run_path, path_parent)
                or (path_parent.device, path_parent.inode)
                != (run_identity.volume_serial, run_identity.file_id)
                or not stat.S_ISREG(published.mode)
                or secure_io._is_link_or_reparse(report_path, published)
                or published.link_count != 1
                or published.size != len(payload)
                or (published.device, published.inode)
                != (written.volume_serial, written.file_id)
            ):
                raise secure_io.RestoreVerificationError(
                    "published orchestration report path or parent identity changed"
                )
            committed = True
            return report_path
        finally:
            try:
                if not committed:
                    secure_io._windows_delete_open_file_on_close(stage_handle)
            finally:
                secure_io._windows_close_handle(stage_handle)


def validate_output_directory(root: Path, run_id: str) -> Path:
    _require(bool(RUN_ID_RE.fullmatch(run_id)), "run id format invalid")
    try:
        trusted_root = secure_io._require_plain_directory(root, "diagnostics root")
        output_directory = trusted_root / run_id
        _require(
            not output_directory.exists() and not output_directory.is_symlink(),
            f"output directory already exists: {output_directory}",
        )
        return output_directory
    except OrchestrationDryRunError:
        raise
    except secure_io.RestoreVerificationError as exc:
        raise OrchestrationDryRunError(f"invalid diagnostics root: {exc}") from exc


def publish_report_no_clobber(
    root: Path,
    run_id: str,
    report: dict[str, Any],
) -> tuple[Path, str]:
    output_directory = validate_output_directory(root, run_id)
    payload = canonical_json_bytes(report)
    try:
        _require(sys.platform == "win32", "secure publication requires Windows")
        report_path = _windows_publish_report_in_new_run_directory(
            root,
            run_id,
            payload,
        )
        _require(report_path.parent == output_directory, "published run path drift")
        verified = read_snapshot(
            report_path,
            max_bytes=max(MAX_JSON_BYTES, len(payload)),
            root=root,
        )
        _require(verified == payload, "published report verification failed")
    except OrchestrationDryRunError:
        raise
    except secure_io.RestoreVerificationError as exc:
        raise OrchestrationDryRunError(f"secure report publication failed: {exc}") from exc
    return report_path, sha256_bytes(payload)


def run_dry_run(
    contract_path: Path = DEFAULT_CONTRACT,
) -> tuple[dict[str, Any], dict[str, bytes]]:
    contract, contract_payload, records, snapshots, normalized = validate_contract_file(
        contract_path
    )
    report = build_report(
        contract,
        contract_path.resolve(),
        contract_payload,
        records,
        normalized,
    )
    return report, snapshots


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument("--run-id", required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        contract_path = args.contract.resolve()
        _require(
            contract_path == DEFAULT_CONTRACT.resolve(),
            "CLI accepts only the canonical orchestration contract",
        )
        report, snapshots = run_dry_run(contract_path)
        reauthenticate_before_publication(snapshots)
        report_path, report_sha = publish_report_no_clobber(
            DEFAULT_DIAGNOSTICS_ROOT,
            args.run_id,
            report,
        )
        sys.stdout.write(
            json.dumps(
                {
                    "status": report["status"],
                    "selected_candidate_id": report["judge"]["selected_candidate_id"],
                    "report_path": report_path.as_posix(),
                    "report_sha256": report_sha,
                    "execution_authorized": False,
                },
                sort_keys=True,
            )
            + "\n"
        )
        return 0
    except OrchestrationDryRunError as exc:
        sys.stderr.write(f"orchestration dry run failed closed: {exc}\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
