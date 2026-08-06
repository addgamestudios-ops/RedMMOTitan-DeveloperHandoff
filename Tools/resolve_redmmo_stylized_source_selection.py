"""Resolve reviewed stylized-source decisions into an exact import selection.

This offline tool consumes the authenticated semantic taxonomy overlay plus one
explicit review-decision document. It emits stable source IDs only; it never
imports, moves, deletes, renames, or edits Unreal assets or source textures.

The current category-range importer must not consume this output until a later
bounded integration slice adds and verifies that exact-ID gate.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat as stat_module
from typing import Any, Mapping, Sequence

try:
    from Tools import build_redmmo_stylized_source_taxonomy as taxonomy
    from Tools import import_redmmo_stylized_source_library as source_import
except ModuleNotFoundError as exc:
    if exc.name != "Tools":
        raise
    import build_redmmo_stylized_source_taxonomy as taxonomy
    import import_redmmo_stylized_source_library as source_import


DECISION_SCHEMA = "redmmotitan.stylized_source_review_decisions.v1"
SELECTION_SCHEMA = "redmmotitan.stylized_source_resolved_selection.v1"
DECISIONS_ROOT = Path(r"D:\RedMMOTitan\Build\Automation")
SELECTION_ROOT = source_import.DEFAULT_DIAGNOSTICS_ROOT / "Selections"
MAX_SELECTION_RECORDS = source_import.MAX_UNREAL_BATCH
_SHA256 = re.compile(r"^[0-9A-F]{64}$")
_STABLE_ID = re.compile(r"^RED-STYLIZED-[0-9A-F]{24}$")
_GROUP_ID = re.compile(r"^RED-STYLIZED-GROUP-[0-9A-F]{24}$")
_ALLOWED_ACTIONS = frozenset(
    {"approve_import", "defer", "retain_quarantined_in_place"}
)
_ALLOWED_AUTHORITIES = frozenset({"canonical_evidence", "human_review"})
_DECISION_KEYS = frozenset(
    {
        "action",
        "expected_object_family",
        "expected_relative_path",
        "expected_review_required",
        "expected_source_sha256",
        "expected_v2_object_path",
        "reason",
        "stable_source_id",
    }
)


def _canonical_json_bytes(payload: object) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
        allow_nan=False,
    ).encode("utf-8")


def _digest(payload: object) -> str:
    return hashlib.sha256(_canonical_json_bytes(payload)).hexdigest().upper()


def _require_exact_keys(
    payload: Mapping[str, Any],
    expected: frozenset[str],
    *,
    label: str,
) -> None:
    actual = frozenset(payload)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise RuntimeError(
            f"{label} keys are invalid: missing={missing} extra={extra}"
        )


def _require_trimmed_text(value: object, *, label: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise RuntimeError(f"{label} must be a non-empty trimmed string")
    return value


def _validate_expected_sha256(value: object, *, label: str) -> str:
    text = _require_trimmed_text(value, label=label)
    if not _SHA256.fullmatch(text):
        raise RuntimeError(f"{label} must be exactly 64 uppercase hex characters")
    return text


def family_path(relative_path: str) -> str:
    relative = PurePosixPath(relative_path)
    if (
        relative.is_absolute()
        or len(relative.parts) < 3
        or "\\" in relative_path
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        raise RuntimeError(
            f"Taxonomy record lacks a canonical family path: {relative_path}"
        )
    return relative.parent.as_posix()


def stable_group_id(member_ids: Sequence[str]) -> tuple[str, str]:
    normalized = tuple(sorted(member_ids))
    if (
        not normalized
        or len(normalized) != len(set(normalized))
        or any(not _STABLE_ID.fullmatch(stable_id) for stable_id in normalized)
    ):
        raise RuntimeError("Stable group members must be non-empty and unique")
    member_set_sha256 = _digest(list(normalized))
    group_id = f"RED-STYLIZED-GROUP-{member_set_sha256[:24]}"
    if not _GROUP_ID.fullmatch(group_id):
        raise RuntimeError("Derived stable group ID is invalid")
    return group_id, member_set_sha256


def _validate_file_below_root(
    path: str | Path,
    *,
    root: str | Path,
    must_exist: bool,
    label: str,
) -> Path:
    supplied = Path(path)
    root_path = Path(root).resolve(strict=False)
    if root_path.exists() or root_path.is_symlink():
        source_import._reject_link_or_reparse(root_path, f"{label} root")
    if supplied.exists() or supplied.is_symlink():
        source_import._reject_link_or_reparse(supplied, label)
    candidate = supplied.resolve(strict=must_exist)
    try:
        relative = candidate.relative_to(root_path)
    except ValueError as exc:
        raise RuntimeError(f"{label} must be below {root_path}: {candidate}") from exc
    if not relative.parts or candidate.suffix.casefold() != ".json":
        raise RuntimeError(f"{label} must be a strict child JSON file")
    current = root_path
    for part in relative.parts[:-1]:
        current = current / part
        if current.exists() or current.is_symlink():
            metadata = source_import._reject_link_or_reparse(
                current, f"{label} directory"
            )
            if not stat_module.S_ISDIR(metadata.st_mode):
                raise RuntimeError(f"{label} parent is not a directory: {current}")
    return candidate


def _load_json_authenticated(
    path: str | Path,
    *,
    expected_file_sha256: str,
    allowed_root: str | Path,
    label: str,
) -> tuple[Path, dict[str, Any]]:
    expected = _validate_expected_sha256(
        expected_file_sha256, label=f"Expected {label} file SHA256"
    )
    resolved = _validate_file_below_root(
        path,
        root=allowed_root,
        must_exist=True,
        label=label,
    )
    actual = source_import.sha256_file(resolved)
    if actual != expected:
        raise RuntimeError(
            f"Authenticated {label} file SHA256 mismatch: "
            f"expected {expected}, got {actual}"
        )
    with resolved.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise RuntimeError(f"{label} root must be an object")
    return resolved, payload


def validate_taxonomy_payload(
    payload: Mapping[str, Any],
    *,
    expected_file_sha256: str,
) -> tuple[
    dict[str, Mapping[str, Any]],
    dict[str, tuple[str, ...]],
    dict[str, str],
    dict[str, str],
    dict[str, tuple[str, ...]],
]:
    if payload.get("schema") != taxonomy.TAXONOMY_SCHEMA:
        raise RuntimeError("Unexpected taxonomy schema")
    semantic_sha = _validate_expected_sha256(
        payload.get("taxonomy_sha256"), label="Taxonomy semantic SHA256"
    )
    without_digest = dict(payload)
    without_digest.pop("taxonomy_sha256", None)
    if _digest(without_digest) != semantic_sha:
        raise RuntimeError("Taxonomy semantic digest mismatch")
    _validate_expected_sha256(
        payload.get("plan_file_sha256"), label="Taxonomy plan file SHA256"
    )
    _validate_expected_sha256(
        payload.get("plan_sha256"), label="Taxonomy plan SHA256"
    )
    _validate_expected_sha256(
        payload.get("dataset_sha256"), label="Taxonomy dataset SHA256"
    )
    _validate_expected_sha256(
        payload.get("ruleset_sha256"), label="Taxonomy ruleset SHA256"
    )
    records = payload.get("records")
    if not isinstance(records, list):
        raise RuntimeError("Taxonomy records must be a list")
    if type(payload.get("record_count")) is not int:
        raise RuntimeError("Taxonomy record_count must be an integer")
    if payload["record_count"] != len(records):
        raise RuntimeError("Taxonomy record_count does not match records")

    by_id: dict[str, Mapping[str, Any]] = {}
    family_members: dict[str, list[str]] = defaultdict(list)
    payload_members: dict[str, list[str]] = defaultdict(list)
    casefold_ids: set[str] = set()
    for position, record in enumerate(records):
        if not isinstance(record, dict):
            raise RuntimeError(f"Taxonomy record {position} must be an object")
        if type(record.get("index")) is not int or record["index"] != position:
            raise RuntimeError(
                f"Taxonomy record {position} index must equal its position"
            )
        stable_id = record.get("stable_source_id")
        if not isinstance(stable_id, str) or not _STABLE_ID.fullmatch(stable_id):
            raise RuntimeError(f"Taxonomy record {position} stable ID is invalid")
        folded = stable_id.casefold()
        if folded in casefold_ids:
            raise RuntimeError(f"Taxonomy stable ID collision: {stable_id}")
        casefold_ids.add(folded)
        for field in (
            "relative_path",
            "source_sha256",
            "source_category",
            "texture_semantic",
            "object_family",
            "v2_object_path",
        ):
            _require_trimmed_text(
                record.get(field), label=f"Taxonomy {stable_id} {field}"
            )
        _validate_expected_sha256(
            record["source_sha256"],
            label=f"Taxonomy {stable_id} source SHA256",
        )
        if type(record.get("review_required")) is not bool:
            raise RuntimeError(
                f"Taxonomy {stable_id} review_required must be a boolean"
            )
        material_tags = record.get("material_tags")
        if (
            not isinstance(material_tags, list)
            or any(
                not isinstance(tag, str) or not tag or tag != tag.strip()
                for tag in material_tags
            )
            or material_tags != sorted(set(material_tags))
        ):
            raise RuntimeError(
                f"Taxonomy {stable_id} material_tags must be sorted and unique"
            )
        if record["source_category"] != PurePosixPath(record["relative_path"]).parts[0]:
            raise RuntimeError(
                f"Taxonomy {stable_id} source category/path mismatch"
            )
        if not record["v2_object_path"].startswith("/Game/RedMMO/"):
            raise RuntimeError(f"Taxonomy {stable_id} v2 object path is unsafe")
        recommended = record.get("recommended_library_path")
        if recommended is not None:
            _require_trimmed_text(
                recommended,
                label=f"Taxonomy {stable_id} recommended library path",
            )
            recommended_path = PurePosixPath(recommended)
            if (
                recommended_path.is_absolute()
                or "\\" in recommended
                or any(part in {"", ".", ".."} for part in recommended_path.parts)
            ):
                raise RuntimeError(
                    f"Taxonomy {stable_id} recommended library path is unsafe"
                )
        source_family_path = family_path(record["relative_path"])
        family_members[source_family_path].append(stable_id)
        payload_members[record["source_sha256"]].append(stable_id)
        by_id[stable_id] = record

    expected_file_sha = _validate_expected_sha256(
        expected_file_sha256, label="Taxonomy file SHA256"
    )
    if expected_file_sha != expected_file_sha256:
        raise RuntimeError("Taxonomy file SHA256 normalization changed")
    group_members: dict[str, tuple[str, ...]] = {}
    record_groups: dict[str, str] = {}
    group_member_set_sha256: dict[str, str] = {}
    seen_group_ids: set[str] = set()
    for source_family_path, member_ids in sorted(family_members.items()):
        normalized_members = tuple(sorted(member_ids))
        group_id, member_set_sha256 = stable_group_id(normalized_members)
        if group_id in seen_group_ids:
            raise RuntimeError(f"Stable group ID collision: {group_id}")
        seen_group_ids.add(group_id)
        group_members[group_id] = normalized_members
        group_member_set_sha256[group_id] = member_set_sha256
        for stable_id in normalized_members:
            record_groups[stable_id] = group_id
    return (
        by_id,
        group_members,
        record_groups,
        group_member_set_sha256,
        {
            source_sha: tuple(sorted(member_ids))
            for source_sha, member_ids in sorted(payload_members.items())
        },
    )


def validate_decisions(
    payload: Mapping[str, Any],
    *,
    taxonomy_payload: Mapping[str, Any],
    taxonomy_file_sha256: str,
    taxonomy_records: Mapping[str, Mapping[str, Any]],
) -> tuple[dict[str, Any], list[Mapping[str, Any]]]:
    expected_root_keys = frozenset(
        {
            "authority",
            "decision_count",
            "decisions",
            "schema",
            "taxonomy_binding",
        }
    )
    _require_exact_keys(payload, expected_root_keys, label="Decision root")
    if payload.get("schema") != DECISION_SCHEMA:
        raise RuntimeError("Unexpected review-decision schema")

    binding = payload.get("taxonomy_binding")
    if not isinstance(binding, dict):
        raise RuntimeError("Decision taxonomy_binding must be an object")
    _require_exact_keys(
        binding,
        frozenset(
            {
                "dataset_sha256",
                "plan_file_sha256",
                "plan_sha256",
                "record_count",
                "ruleset_sha256",
                "taxonomy_file_sha256",
                "taxonomy_sha256",
            }
        ),
        label="Decision taxonomy binding",
    )
    exact_binding = {
        "taxonomy_file_sha256": taxonomy_file_sha256,
        "taxonomy_sha256": taxonomy_payload["taxonomy_sha256"],
        "plan_file_sha256": taxonomy_payload["plan_file_sha256"],
        "plan_sha256": taxonomy_payload["plan_sha256"],
        "dataset_sha256": taxonomy_payload["dataset_sha256"],
        "ruleset_sha256": taxonomy_payload["ruleset_sha256"],
        "record_count": taxonomy_payload["record_count"],
    }
    if binding != exact_binding:
        raise RuntimeError("Review decisions are stale or bound to another taxonomy")

    authority = payload.get("authority")
    if not isinstance(authority, dict):
        raise RuntimeError("Decision authority must be an object")
    _require_exact_keys(
        authority,
        frozenset({"evidence_ids", "kind", "name"}),
        label="Decision authority",
    )
    authority_kind = authority.get("kind")
    if authority_kind not in _ALLOWED_AUTHORITIES:
        raise RuntimeError("Decision authority kind is invalid")
    _require_trimmed_text(authority.get("name"), label="Decision authority name")
    evidence_ids = authority.get("evidence_ids")
    if (
        not isinstance(evidence_ids, list)
        or not evidence_ids
        or any(
            not isinstance(value, str) or not value or value != value.strip()
            for value in evidence_ids
        )
        or evidence_ids != sorted(set(evidence_ids))
    ):
        raise RuntimeError(
            "Decision authority evidence_ids must be non-empty, sorted, and unique"
        )

    decisions = payload.get("decisions")
    if not isinstance(decisions, list):
        raise RuntimeError("Decisions must be a list")
    if type(payload.get("decision_count")) is not int:
        raise RuntimeError("Decision decision_count must be an integer")
    if payload["decision_count"] != len(decisions):
        raise RuntimeError("Decision decision_count does not match decisions")
    if not decisions:
        raise RuntimeError("At least one explicit decision is required")

    prior_id = ""
    seen_casefold: set[str] = set()
    validated: list[Mapping[str, Any]] = []
    for position, decision in enumerate(decisions):
        if not isinstance(decision, dict):
            raise RuntimeError(f"Decision {position} must be an object")
        _require_exact_keys(
            decision, _DECISION_KEYS, label=f"Decision {position}"
        )
        stable_id = decision.get("stable_source_id")
        if not isinstance(stable_id, str) or not _STABLE_ID.fullmatch(stable_id):
            raise RuntimeError(f"Decision {position} stable ID is invalid")
        if stable_id <= prior_id:
            raise RuntimeError("Decisions must be strictly sorted by stable source ID")
        prior_id = stable_id
        folded = stable_id.casefold()
        if folded in seen_casefold:
            raise RuntimeError(f"Duplicate decision stable ID: {stable_id}")
        seen_casefold.add(folded)
        record = taxonomy_records.get(stable_id)
        if record is None:
            raise RuntimeError(f"Decision references unknown stable ID: {stable_id}")

        action = decision.get("action")
        if action not in _ALLOWED_ACTIONS:
            raise RuntimeError(f"Decision action is invalid for {stable_id}")
        _require_trimmed_text(
            decision.get("reason"), label=f"Decision {stable_id} reason"
        )
        expected_fields = {
            "expected_relative_path": record["relative_path"],
            "expected_source_sha256": record["source_sha256"],
            "expected_object_family": record["object_family"],
            "expected_review_required": record["review_required"],
            "expected_v2_object_path": record["v2_object_path"],
        }
        for field, expected in expected_fields.items():
            if decision.get(field) != expected:
                raise RuntimeError(
                    f"Decision identity mismatch for {stable_id}: {field}"
                )
        _validate_expected_sha256(
            decision["expected_source_sha256"],
            label=f"Decision {stable_id} source SHA256",
        )
        if type(decision["expected_review_required"]) is not bool:
            raise RuntimeError(
                f"Decision {stable_id} expected_review_required must be boolean"
            )
        if action == "approve_import":
            raise RuntimeError(
                "Import approval is disabled until human-review identity and "
                "the decision hash are anchored outside the caller-supplied file"
            )
        validated.append(decision)
    return dict(authority), validated


def build_resolved_selection(
    *,
    taxonomy_payload: Mapping[str, Any],
    taxonomy_file_sha256: str,
    decisions_payload: Mapping[str, Any],
    decisions_file_sha256: str,
    max_records: int = MAX_SELECTION_RECORDS,
) -> dict[str, Any]:
    if type(max_records) is not int or not 1 <= max_records <= MAX_SELECTION_RECORDS:
        raise RuntimeError(
            f"Resolved selection requires 1 <= max_records <= "
            f"{MAX_SELECTION_RECORDS}"
        )
    taxonomy_file_sha = _validate_expected_sha256(
        taxonomy_file_sha256, label="Taxonomy file SHA256"
    )
    decisions_file_sha = _validate_expected_sha256(
        decisions_file_sha256, label="Decision file SHA256"
    )
    (
        records_by_id,
        group_members,
        record_groups,
        group_member_set_sha256,
        payload_members,
    ) = validate_taxonomy_payload(
        taxonomy_payload, expected_file_sha256=taxonomy_file_sha
    )
    authority, decisions = validate_decisions(
        decisions_payload,
        taxonomy_payload=taxonomy_payload,
        taxonomy_file_sha256=taxonomy_file_sha,
        taxonomy_records=records_by_id,
    )

    decisions_by_id = {
        decision["stable_source_id"]: decision for decision in decisions
    }
    selected_ids = tuple(
        decision["stable_source_id"]
        for decision in decisions
        if decision["action"] == "approve_import"
    )
    if len(selected_ids) > max_records:
        raise RuntimeError(
            f"Resolved selection contains {len(selected_ids)} records; "
            f"the gate is {max_records}"
        )

    decision_group_members: dict[str, list[str]] = defaultdict(list)
    for stable_id in sorted(decisions_by_id):
        decision_group_members[record_groups[stable_id]].append(stable_id)
    for group_id, decided_members in decision_group_members.items():
        expected_members = group_members[group_id]
        if tuple(sorted(decided_members)) != expected_members:
            missing = sorted(set(expected_members) - set(decided_members))
            raise RuntimeError(
                f"Reviewed family group is incomplete: {group_id} missing={missing}"
            )

    selected_groups: dict[str, list[str]] = defaultdict(list)
    for stable_id in selected_ids:
        record = records_by_id[stable_id]
        if record["review_required"]:
            raise RuntimeError(
                f"Review-required taxonomy record cannot be approved: {stable_id}"
            )
        if not record.get("recommended_library_path"):
            raise RuntimeError(
                f"Approved record lacks a recommended library path: {stable_id}"
            )
        group_id = record_groups[stable_id]
        selected_groups[group_id].append(stable_id)
        duplicate_members = payload_members[record["source_sha256"]]
        if len(duplicate_members) > 1:
            raise RuntimeError(
                "Approved selection contains an unresolved globally duplicate "
                f"source payload: {stable_id} duplicates={list(duplicate_members)}"
            )

    for group_id, selected_members in selected_groups.items():
        expected_members = group_members[group_id]
        if tuple(sorted(selected_members)) != expected_members:
            missing = sorted(set(expected_members) - set(selected_members))
            raise RuntimeError(
                f"Approved family group is incomplete: {group_id} missing={missing}"
            )
        families = {
            records_by_id[stable_id]["object_family"]
            for stable_id in expected_members
        }
        destinations = {
            records_by_id[stable_id]["recommended_library_path"]
            for stable_id in expected_members
        }
        if len(families) != 1 or len(destinations) != 1:
            raise RuntimeError(
                f"Approved family group is semantically inconsistent: {group_id}"
            )

    decision_payload_shas = {
        records_by_id[stable_id]["source_sha256"]
        for stable_id in decisions_by_id
    }
    duplicate_payload_groups = [
        {
            "source_sha256": source_sha,
            "member_count": len(payload_members[source_sha]),
            "member_set_sha256": _digest(list(payload_members[source_sha])),
            "stable_source_ids": list(payload_members[source_sha]),
        }
        for source_sha in sorted(decision_payload_shas)
        if len(payload_members[source_sha]) > 1
    ]
    global_duplicate_groups = {
        source_sha: member_ids
        for source_sha, member_ids in payload_members.items()
        if len(member_ids) > 1
    }
    global_duplicate_record_count = sum(
        len(member_ids) for member_ids in global_duplicate_groups.values()
    )

    def resolved_record(stable_id: str) -> dict[str, Any]:
        record = records_by_id[stable_id]
        group_id = record_groups[stable_id]
        return {
            "stable_source_id": stable_id,
            "v2_index": record["index"],
            "stable_group_id": group_id,
            "family_member_set_sha256": group_member_set_sha256[group_id],
            "family_path": family_path(record["relative_path"]),
            "relative_path": record["relative_path"],
            "source_sha256": record["source_sha256"],
            "taxonomy_record_sha256": _digest(record),
            "texture_semantic": record["texture_semantic"],
            "source_category": record["source_category"],
            "object_family": record["object_family"],
            "material_tags": list(record["material_tags"]),
            "review_required": record["review_required"],
            "current_v2_object_path": record["v2_object_path"],
            "recommended_library_path": record["recommended_library_path"],
        }

    selected_records = [
        resolved_record(stable_id) for stable_id in sorted(selected_ids)
    ]
    quarantined_records = [
        {
            **resolved_record(decision["stable_source_id"]),
            "reason": decision["reason"],
        }
        for decision in decisions
        if decision["action"] == "retain_quarantined_in_place"
    ]
    deferred_records = [
        {
            **resolved_record(decision["stable_source_id"]),
            "reason": decision["reason"],
        }
        for decision in decisions
        if decision["action"] == "defer"
    ]
    action_counts = Counter(decision["action"] for decision in decisions)

    result: dict[str, Any] = {
        "schema": SELECTION_SCHEMA,
        "taxonomy_binding": {
            "taxonomy_file_sha256": taxonomy_file_sha,
            "taxonomy_sha256": taxonomy_payload["taxonomy_sha256"],
            "plan_file_sha256": taxonomy_payload["plan_file_sha256"],
            "plan_sha256": taxonomy_payload["plan_sha256"],
            "dataset_sha256": taxonomy_payload["dataset_sha256"],
            "ruleset_sha256": taxonomy_payload["ruleset_sha256"],
            "record_count": taxonomy_payload["record_count"],
        },
        "decisions_file_sha256": decisions_file_sha,
        "decisions_semantic_sha256": _digest(decisions_payload),
        "authority": authority,
        "max_records": max_records,
        "decision_count": len(decisions),
        "decision_action_counts": dict(sorted(action_counts.items())),
        "decision_group_count": len(decision_group_members),
        "global_duplicate_payload_group_count": len(global_duplicate_groups),
        "global_duplicate_payload_record_count": global_duplicate_record_count,
        "duplicate_payload_group_count": len(duplicate_payload_groups),
        "duplicate_payload_groups": duplicate_payload_groups,
        "selection_count": len(selected_records),
        "selected_records": selected_records,
        "quarantine_count": len(quarantined_records),
        "quarantined_records": quarantined_records,
        "deferred_count": len(deferred_records),
        "deferred_records": deferred_records,
        "undecided_count": taxonomy_payload["record_count"] - len(decisions),
        "selection_ready": bool(selected_records),
        "importer_ready": False,
        "selection_kind": (
            "bounded_import_candidate"
            if selected_records
            else "quarantine_resolution"
        ),
        "approval_gate": (
            "disabled_until_externally_anchored_human_review"
        ),
        "importer_gate": "not_integrated_category_import_remains_paused",
    }
    result["selection_sha256"] = _digest(result)
    return result


def validate_resolved_selection(
    resolved: Mapping[str, Any],
    *,
    taxonomy_payload: Mapping[str, Any],
    taxonomy_file_sha256: str,
    decisions_payload: Mapping[str, Any],
    decisions_file_sha256: str,
    max_records: int,
) -> None:
    expected = build_resolved_selection(
        taxonomy_payload=taxonomy_payload,
        taxonomy_file_sha256=taxonomy_file_sha256,
        decisions_payload=decisions_payload,
        decisions_file_sha256=decisions_file_sha256,
        max_records=max_records,
    )
    if dict(resolved) != expected:
        raise RuntimeError(
            "Resolved selection is not the exact deterministic result for its inputs"
        )


def _load_inputs(
    *,
    taxonomy_path: str | Path,
    taxonomy_file_sha256: str,
    decisions_path: str | Path,
    decisions_file_sha256: str,
) -> tuple[Path, dict[str, Any], Path, dict[str, Any]]:
    taxonomy_resolved, taxonomy_payload = _load_json_authenticated(
        taxonomy_path,
        expected_file_sha256=taxonomy_file_sha256,
        allowed_root=taxonomy.TAXONOMY_DIAGNOSTICS_ROOT,
        label="Taxonomy",
    )
    decisions_resolved, decisions_payload = _load_json_authenticated(
        decisions_path,
        expected_file_sha256=decisions_file_sha256,
        allowed_root=DECISIONS_ROOT,
        label="Review decisions",
    )
    return (
        taxonomy_resolved,
        taxonomy_payload,
        decisions_resolved,
        decisions_payload,
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("resolve", "verify"):
        subparser = subparsers.add_parser(command)
        subparser.add_argument("--taxonomy", required=True)
        subparser.add_argument("--expected-taxonomy-file-sha256", required=True)
        subparser.add_argument("--decisions", required=True)
        subparser.add_argument("--expected-decisions-file-sha256", required=True)
        subparser.add_argument(
            "--max-records",
            type=int,
            default=MAX_SELECTION_RECORDS,
        )
        if command == "resolve":
            subparser.add_argument("--output", required=True)
        else:
            subparser.add_argument("--selection", required=True)
            subparser.add_argument(
                "--expected-selection-file-sha256", required=True
            )
    return parser


def cli(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    (
        taxonomy_path,
        taxonomy_payload,
        decisions_path,
        decisions_payload,
    ) = _load_inputs(
        taxonomy_path=args.taxonomy,
        taxonomy_file_sha256=args.expected_taxonomy_file_sha256,
        decisions_path=args.decisions,
        decisions_file_sha256=args.expected_decisions_file_sha256,
    )
    result = build_resolved_selection(
        taxonomy_payload=taxonomy_payload,
        taxonomy_file_sha256=args.expected_taxonomy_file_sha256,
        decisions_payload=decisions_payload,
        decisions_file_sha256=args.expected_decisions_file_sha256,
        max_records=args.max_records,
    )
    if args.command == "resolve":
        output = _validate_file_below_root(
            args.output,
            root=SELECTION_ROOT,
            must_exist=False,
            label="Resolved selection",
        )
        source_import.write_json_no_clobber(output, result)
        print(
            "RED_STYLIZED_SELECTION_RESOLVED "
            f"selected={result['selection_count']} "
            f"quarantined={result['quarantine_count']} "
            f"undecided={result['undecided_count']} "
            f"sha256={result['selection_sha256']} output={output}"
        )
        return 0

    selection_path, selection_payload = _load_json_authenticated(
        args.selection,
        expected_file_sha256=args.expected_selection_file_sha256,
        allowed_root=SELECTION_ROOT,
        label="Resolved selection",
    )
    validate_resolved_selection(
        selection_payload,
        taxonomy_payload=taxonomy_payload,
        taxonomy_file_sha256=args.expected_taxonomy_file_sha256,
        decisions_payload=decisions_payload,
        decisions_file_sha256=args.expected_decisions_file_sha256,
        max_records=args.max_records,
    )
    print(
        "RED_STYLIZED_SELECTION_VALID "
        f"selected={selection_payload['selection_count']} "
        f"quarantined={selection_payload['quarantine_count']} "
        f"sha256={selection_payload['selection_sha256']} "
        f"selection={selection_path} taxonomy={taxonomy_path} "
        f"decisions={decisions_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(cli())
