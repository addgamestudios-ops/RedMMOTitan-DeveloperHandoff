"""Build a deterministic, non-authoritative stylized-source review request.

The request expands exact seed IDs to complete source-parent families and binds
them to the authenticated semantic taxonomy.  It is review material only: it
cannot approve, select, import, move, merge, delete, or rename any source or
Unreal asset.

Positive authorization remains impossible until the user provisions an
external reviewer public key whose fingerprint is pinned outside request and
decision payloads.  No production CLI or environment override can supply that
trust root.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import re
from typing import Any, Mapping, Sequence

try:
    from Tools import build_redmmo_stylized_source_taxonomy as taxonomy
    from Tools import import_redmmo_stylized_source_library as source_import
    from Tools import resolve_redmmo_stylized_source_selection as resolver
except ModuleNotFoundError as exc:
    if exc.name != "Tools":
        raise
    import build_redmmo_stylized_source_taxonomy as taxonomy
    import import_redmmo_stylized_source_library as source_import
    import resolve_redmmo_stylized_source_selection as resolver


REQUEST_SCHEMA = "redmmotitan.stylized_source_review_request.v1"
TRUST_CONTRACT_SCHEMA = (
    "redmmotitan.stylized_source_review_trust_contract.v1"
)
ATTESTATION_SCHEMA = "redmmotitan.stylized_source_review_attestation.v1"
REQUEST_ROOT = source_import.DEFAULT_DIAGNOSTICS_ROOT / "ReviewRequests"
TRUST_CONTRACT_PATH = Path(
    r"D:\RedMMOTitan\Build\Automation"
    r"\redmmo_stylized_review_trust_contract_v1.json"
)
PINNED_TRUST_CONTRACT_SHA256 = (
    "547A46F55307DF57B07E59E7BAD3F513AB6769633DC2568FCE5224305DC5928A"
)
MAX_REQUEST_RECORDS = source_import.MAX_UNREAL_BATCH
MAX_JSON_BYTES = 128 * 1024 * 1024
ALLOWED_CLASSIFICATION_CONFIDENCE = frozenset(
    {"ambiguous", "high", "medium", "none"}
)
ALLOWED_OBJECT_FAMILIES = frozenset(taxonomy.FAMILY_LIBRARY_PATHS) | frozenset(
    {"ambiguous", "unresolved"}
)
ALLOWED_TEXTURE_SEMANTICS = frozenset({"color", "mask", "normal"})
_TAXONOMY_IDENTIFIER = re.compile(r"^[a-z0-9_]+$")

REQUIRED_REVIEW_CLAIMS = (
    "curated_destination",
    "dependency_completeness",
    "family_completeness",
    "source_identity",
    "source_texture_visual_review",
    "usage_rights",
)
AUTHORIZATION_SUBJECT_BINDINGS = (
    "decision_file_sha256",
    "decisions_semantic_sha256",
    "final_destination_set_sha256",
    "final_stable_id_set_sha256",
    "review_request_file_sha256",
    "review_request_sha256",
    "reviewer_id",
    "reviewer_public_key_fingerprint_sha256",
    "taxonomy_file_sha256",
    "taxonomy_sha256",
)
TRUST_CONTRACT_KEYS = frozenset(
    {
        "approval_enabled",
        "attestation_schema",
        "authorization_subject_bindings",
        "caller_supplied_trust_roots_allowed",
        "claim_limit",
        "contract_sha256",
        "contract_version",
        "private_keys_permitted_in_repository",
        "schema",
        "signature_algorithm",
        "trust_anchor_source",
        "trust_anchor_status",
        "trusted_reviewer_key_fingerprints_sha256",
    }
)


def _canonical_json_bytes(payload: object) -> bytes:
    return resolver._canonical_json_bytes(payload)


def _digest(payload: object) -> str:
    return resolver._digest(payload)


def _reject_duplicate_json_keys(
    pairs: list[tuple[str, Any]],
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_nonfinite_json_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant: {value}")


def _parse_finite_json_float(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed):
        raise ValueError(f"non-finite JSON number: {value}")
    return parsed


def _read_json_once(
    path: str | Path,
    *,
    root: str | Path,
    label: str,
    expected_file_sha256: str | None = None,
) -> tuple[Path, str, dict[str, Any]]:
    resolved = resolver._validate_file_below_root(
        path,
        root=root,
        must_exist=True,
        label=label,
    )
    with resolved.open("rb") as handle:
        raw = handle.read(MAX_JSON_BYTES + 1)
    if len(raw) > MAX_JSON_BYTES:
        raise RuntimeError(f"{label} exceeds the {MAX_JSON_BYTES}-byte limit")
    actual_sha256 = hashlib.sha256(raw).hexdigest().upper()
    if expected_file_sha256 is not None:
        expected = resolver._validate_expected_sha256(
            expected_file_sha256,
            label=f"Expected {label} file SHA256",
        )
        if actual_sha256 != expected:
            raise RuntimeError(
                f"Authenticated {label} file SHA256 mismatch: "
                f"expected {expected}, got {actual_sha256}"
            )
    try:
        payload = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_json_keys,
            parse_constant=_reject_nonfinite_json_constant,
            parse_float=_parse_finite_json_float,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise RuntimeError(f"{label} is not strict UTF-8 JSON") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"{label} root must be an object")
    return resolved, actual_sha256, payload


def validate_trust_contract(payload: Mapping[str, Any]) -> None:
    resolver._require_exact_keys(
        payload,
        TRUST_CONTRACT_KEYS,
        label="Review trust contract",
    )
    semantic_sha256 = resolver._validate_expected_sha256(
        payload.get("contract_sha256"),
        label="Review trust contract semantic SHA256",
    )
    without_digest = dict(payload)
    without_digest.pop("contract_sha256", None)
    if _digest(without_digest) != semantic_sha256:
        raise RuntimeError("Review trust contract semantic digest mismatch")
    if semantic_sha256 != PINNED_TRUST_CONTRACT_SHA256:
        raise RuntimeError("Review trust contract is not the pinned production contract")
    expected_scalars = {
        "schema": TRUST_CONTRACT_SCHEMA,
        "contract_version": 1,
        "signature_algorithm": "ed25519",
        "trust_anchor_source": "externally_provisioned_pinned_public_key",
        "trust_anchor_status": "not_configured",
        "attestation_schema": ATTESTATION_SCHEMA,
        "claim_limit": (
            "This contract configures no reviewer key and grants no import "
            "authority."
        ),
    }
    for key, expected in expected_scalars.items():
        if payload.get(key) != expected:
            raise RuntimeError(f"Review trust contract {key} is not pinned")
    for key in (
        "approval_enabled",
        "caller_supplied_trust_roots_allowed",
        "private_keys_permitted_in_repository",
    ):
        if payload.get(key) is not False:
            raise RuntimeError(f"Review trust contract {key} must remain false")
    if payload.get("trusted_reviewer_key_fingerprints_sha256") != []:
        raise RuntimeError("External reviewer trust is not configured")
    if payload.get("authorization_subject_bindings") != list(
        AUTHORIZATION_SUBJECT_BINDINGS
    ):
        raise RuntimeError("Review trust contract signed bindings changed")


def load_pinned_trust_contract() -> tuple[str, dict[str, Any]]:
    resolved, file_sha256, payload = _read_json_once(
        TRUST_CONTRACT_PATH,
        root=TRUST_CONTRACT_PATH.parent,
        label="Review trust contract",
    )
    if resolved != TRUST_CONTRACT_PATH.resolve(strict=True):
        raise RuntimeError("Review trust contract path is not pinned")
    validate_trust_contract(payload)
    return file_sha256, payload


def _require_sorted_identifier_list(value: object, *, label: str) -> list[str]:
    if (
        not isinstance(value, list)
        or any(
            not isinstance(item, str)
            or not item
            or item != item.strip()
            or not _TAXONOMY_IDENTIFIER.fullmatch(item)
            for item in value
        )
        or value != sorted(set(value))
    ):
        raise RuntimeError(
            f"{label} must be a sorted unique list of canonical identifiers"
        )
    return value


def _validate_rendered_taxonomy_fields(record: Mapping[str, Any]) -> None:
    confidence = record.get("classification_confidence")
    if confidence not in ALLOWED_CLASSIFICATION_CONFIDENCE:
        raise RuntimeError("Taxonomy classification_confidence is invalid")
    matched_tokens = _require_sorted_identifier_list(
        record.get("matched_family_tokens"),
        label="Taxonomy matched_family_tokens",
    )
    review_reasons = _require_sorted_identifier_list(
        record.get("review_reasons"),
        label="Taxonomy review_reasons",
    )
    if record.get("object_family") not in ALLOWED_OBJECT_FAMILIES:
        raise RuntimeError("Taxonomy object_family is invalid")
    if record.get("texture_semantic") not in ALLOWED_TEXTURE_SEMANTICS:
        raise RuntimeError("Taxonomy texture_semantic is invalid")
    if record.get("review_required") is not bool(review_reasons):
        raise RuntimeError("Taxonomy review_required/review_reasons mismatch")
    if record.get("review_required") and record.get("recommended_library_path") is not None:
        raise RuntimeError(
            "Review-required taxonomy record cannot recommend a library path"
        )
    if confidence == "none" and matched_tokens:
        raise RuntimeError(
            "Taxonomy confidence none cannot contain matched family tokens"
        )


def _taxonomy_record_payload(record: Mapping[str, Any]) -> dict[str, Any]:
    _validate_rendered_taxonomy_fields(record)
    return {
        "classification_confidence": record.get("classification_confidence"),
        "current_v2_object_path": record["v2_object_path"],
        "index": record["index"],
        "matched_family_tokens": list(record.get("matched_family_tokens", [])),
        "material_tags": list(record["material_tags"]),
        "object_family": record["object_family"],
        "relative_path": record["relative_path"],
        "review_reasons": list(record.get("review_reasons", [])),
        "review_required": record["review_required"],
        "source_category": record["source_category"],
        "source_sha256": record["source_sha256"],
        "stable_source_id": record["stable_source_id"],
        "taxonomy_record_sha256": _digest(record),
        "texture_semantic": record["texture_semantic"],
        "unreviewed_recommended_library_path": record.get(
            "recommended_library_path"
        ),
    }


def build_review_request(
    *,
    taxonomy_payload: Mapping[str, Any],
    taxonomy_file_sha256: str,
    trust_contract_payload: Mapping[str, Any],
    trust_contract_file_sha256: str,
    seed_stable_source_ids: Sequence[str],
    max_records: int = MAX_REQUEST_RECORDS,
) -> dict[str, Any]:
    if type(max_records) is not int or not 1 <= max_records <= MAX_REQUEST_RECORDS:
        raise RuntimeError(
            f"Review request requires 1 <= max_records <= {MAX_REQUEST_RECORDS}"
        )
    if (
        not isinstance(seed_stable_source_ids, (list, tuple))
        or not seed_stable_source_ids
        or any(not isinstance(value, str) for value in seed_stable_source_ids)
    ):
        raise RuntimeError("Review request seeds must be a non-empty string sequence")
    if len(seed_stable_source_ids) != len(set(seed_stable_source_ids)):
        raise RuntimeError("Review request seed stable IDs must be unique")

    taxonomy_file_sha = resolver._validate_expected_sha256(
        taxonomy_file_sha256,
        label="Taxonomy file SHA256",
    )
    trust_file_sha = resolver._validate_expected_sha256(
        trust_contract_file_sha256,
        label="Review trust contract file SHA256",
    )
    validate_trust_contract(trust_contract_payload)
    (
        records_by_id,
        group_members,
        record_groups,
        group_member_set_sha256,
        payload_members,
    ) = resolver.validate_taxonomy_payload(
        taxonomy_payload,
        expected_file_sha256=taxonomy_file_sha,
    )

    for seed_id in seed_stable_source_ids:
        if seed_id not in records_by_id:
            raise RuntimeError(f"Unknown exact review seed stable ID: {seed_id}")
    requested_group_ids = tuple(
        sorted({record_groups[stable_id] for stable_id in seed_stable_source_ids})
    )
    requested_ids = tuple(
        sorted(
            stable_id
            for group_id in requested_group_ids
            for stable_id in group_members[group_id]
        )
    )
    if len(requested_ids) > max_records:
        raise RuntimeError(
            f"Complete review-family expansion contains {len(requested_ids)} "
            f"records; the gate is {max_records}"
        )

    requested_set = set(requested_ids)
    groups: list[dict[str, Any]] = []
    for group_id in requested_group_ids:
        member_ids = group_members[group_id]
        first_record = records_by_id[member_ids[0]]
        family = resolver.family_path(first_record["relative_path"])
        if any(
            resolver.family_path(records_by_id[stable_id]["relative_path"])
            != family
            for stable_id in member_ids
        ):
            raise RuntimeError(f"Review family path mismatch: {group_id}")
        groups.append(
            {
                "family_path": family,
                "member_count": len(member_ids),
                "member_set_sha256": group_member_set_sha256[group_id],
                "member_stable_source_ids": list(member_ids),
                "stable_group_id": group_id,
            }
        )

    duplicate_groups: list[dict[str, Any]] = []
    for source_sha256 in sorted(
        {
            records_by_id[stable_id]["source_sha256"]
            for stable_id in requested_ids
            if len(payload_members[records_by_id[stable_id]["source_sha256"]]) > 1
        }
    ):
        global_members = payload_members[source_sha256]
        requested_members = tuple(
            stable_id for stable_id in global_members if stable_id in requested_set
        )
        outside_members = tuple(
            stable_id for stable_id in global_members if stable_id not in requested_set
        )
        duplicate_groups.append(
            {
                "global_member_count": len(global_members),
                "global_member_set_sha256": _digest(list(global_members)),
                "global_stable_source_ids": list(global_members),
                "outside_request_member_count": len(outside_members),
                "outside_request_stable_source_ids": list(outside_members),
                "requested_member_count": len(requested_members),
                "requested_stable_source_ids": list(requested_members),
                "source_sha256": source_sha256,
            }
        )

    records = [
        _taxonomy_record_payload(records_by_id[stable_id])
        for stable_id in requested_ids
    ]
    result: dict[str, Any] = {
        "max_records": max_records,
        "purpose": "isolated_import_staging_review_only",
        "request_kind": "review_only",
        "requested_group_count": len(groups),
        "requested_group_ids": list(requested_group_ids),
        "requested_groups": groups,
        "requested_record_count": len(records),
        "requested_records": records,
        "required_review_claims": list(REQUIRED_REVIEW_CLAIMS),
        "schema": REQUEST_SCHEMA,
        "taxonomy_binding": {
            "dataset_sha256": taxonomy_payload["dataset_sha256"],
            "plan_file_sha256": taxonomy_payload["plan_file_sha256"],
            "plan_sha256": taxonomy_payload["plan_sha256"],
            "record_count": taxonomy_payload["record_count"],
            "ruleset_sha256": taxonomy_payload["ruleset_sha256"],
            "taxonomy_file_sha256": taxonomy_file_sha,
            "taxonomy_sha256": taxonomy_payload["taxonomy_sha256"],
        },
        "touched_global_duplicate_payload_group_count": len(duplicate_groups),
        "touched_global_duplicate_payload_groups": duplicate_groups,
        "trust_contract_binding": {
            "attestation_schema": trust_contract_payload["attestation_schema"],
            "contract_file_sha256": trust_file_sha,
            "contract_sha256": trust_contract_payload["contract_sha256"],
            "external_trust_state": trust_contract_payload["trust_anchor_status"],
        },
        "unresolved_review_questions": [
            "Does the source identity match the intended asset family?",
            "Do project usage and redistribution rights permit this exact use?",
            "Are all mesh, material, texture, and plugin dependencies present?",
            "Is the suggested curated library destination correct?",
            "Do the pixels and eventual material meet the hand-painted PBR art direction?",
            "Does an isolated Unreal staging test preserve scale, alpha, normal orientation, and performance?",
        ],
    }
    result["request_sha256"] = _digest(result)
    return result


def validate_review_request(
    request: Mapping[str, Any],
    *,
    taxonomy_payload: Mapping[str, Any],
    taxonomy_file_sha256: str,
    trust_contract_payload: Mapping[str, Any],
    trust_contract_file_sha256: str,
) -> None:
    group_ids = request.get("requested_group_ids")
    max_records = request.get("max_records")
    if not isinstance(group_ids, list) or not group_ids:
        raise RuntimeError("Review request group IDs must be a non-empty list")
    (
        _records_by_id,
        group_members,
        _record_groups,
        _group_hashes,
        _payload_members,
    ) = resolver.validate_taxonomy_payload(
        taxonomy_payload,
        expected_file_sha256=taxonomy_file_sha256,
    )
    seeds: list[str] = []
    for group_id in group_ids:
        if not isinstance(group_id, str) or group_id not in group_members:
            raise RuntimeError(f"Unknown review request group ID: {group_id}")
        seeds.append(group_members[group_id][0])
    expected = build_review_request(
        taxonomy_payload=taxonomy_payload,
        taxonomy_file_sha256=taxonomy_file_sha256,
        trust_contract_payload=trust_contract_payload,
        trust_contract_file_sha256=trust_contract_file_sha256,
        seed_stable_source_ids=seeds,
        max_records=max_records,
    )
    if dict(request) != expected:
        raise RuntimeError(
            "Review request is not the exact deterministic result for its inputs"
        )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("build", "verify"):
        subparser = subparsers.add_parser(command)
        subparser.add_argument("--taxonomy", required=True)
        subparser.add_argument("--expected-taxonomy-file-sha256", required=True)
        if command == "build":
            subparser.add_argument(
                "--seed-stable-source-id",
                action="append",
                required=True,
            )
            subparser.add_argument(
                "--max-records",
                type=int,
                default=MAX_REQUEST_RECORDS,
            )
            subparser.add_argument("--output", required=True)
        else:
            subparser.add_argument("--request", required=True)
            subparser.add_argument(
                "--expected-request-file-sha256",
                required=True,
            )
    return parser


def cli(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    _taxonomy_path, taxonomy_file_sha256, taxonomy_payload = _read_json_once(
        args.taxonomy,
        root=taxonomy.TAXONOMY_DIAGNOSTICS_ROOT,
        label="Taxonomy",
        expected_file_sha256=args.expected_taxonomy_file_sha256,
    )
    trust_file_sha256, trust_payload = load_pinned_trust_contract()
    if args.command == "build":
        result = build_review_request(
            taxonomy_payload=taxonomy_payload,
            taxonomy_file_sha256=taxonomy_file_sha256,
            trust_contract_payload=trust_payload,
            trust_contract_file_sha256=trust_file_sha256,
            seed_stable_source_ids=args.seed_stable_source_id,
            max_records=args.max_records,
        )
        output = resolver._validate_file_below_root(
            args.output,
            root=REQUEST_ROOT,
            must_exist=False,
            label="Review request",
        )
        source_import.write_json_no_clobber(output, result)
        print(
            "RED_STYLIZED_REVIEW_REQUEST_BUILT "
            f"groups={result['requested_group_count']} "
            f"records={result['requested_record_count']} "
            f"sha256={result['request_sha256']} output={output}"
        )
        return 0

    _request_path, _request_file_sha256, request_payload = _read_json_once(
        args.request,
        root=REQUEST_ROOT,
        label="Review request",
        expected_file_sha256=args.expected_request_file_sha256,
    )
    validate_review_request(
        request_payload,
        taxonomy_payload=taxonomy_payload,
        taxonomy_file_sha256=taxonomy_file_sha256,
        trust_contract_payload=trust_payload,
        trust_contract_file_sha256=trust_file_sha256,
    )
    print(
        "RED_STYLIZED_REVIEW_REQUEST_VALID "
        f"groups={request_payload['requested_group_count']} "
        f"records={request_payload['requested_record_count']} "
        f"sha256={request_payload['request_sha256']} "
        f"request={args.request}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(cli())
