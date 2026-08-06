from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

from Tools import build_redmmo_stylized_source_taxonomy as taxonomy
from Tools import import_redmmo_stylized_source_library as source_import


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "resolve_redmmo_stylized_source_selection.py"
)
SPEC = importlib.util.spec_from_file_location("stylized_selection", SCRIPT_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)

TAXONOMY_FILE_SHA = "C" * 64
DECISIONS_FILE_SHA = "D" * 64


def make_record(
    relative_path: str,
    *,
    index: int,
    source_sha256: str | None = None,
) -> source_import.ImportRecord:
    relative = Path(relative_path)
    category = relative.parts[0]
    source_sha = source_sha256 or hashlib.sha256(
        relative_path.encode("utf-8")
    ).hexdigest().upper()
    stable_id = source_import._stable_source_id(
        relative_path.replace("\\", "/")
    )
    destination_path = (
        f"/Game/RedMMO/ArtLibrary/StylizedSource/"
        f"{category}/{relative.parent.name}"
    )
    return source_import.ImportRecord(
        index=index,
        stable_source_id=stable_id,
        relative_path=relative_path.replace("\\", "/"),
        category=category,
        source_size=1,
        source_mtime_ns=1,
        source_sha256=source_sha,
        source_suffix=relative.suffix.casefold(),
        semantic=source_import.classify_texture_semantic(relative.name),
        destination_path=destination_path,
        destination_name=relative.stem,
        object_path=f"{destination_path}/{relative.stem}",
    )


def build_taxonomy(
    records: list[source_import.ImportRecord],
) -> dict[str, object]:
    plan = {
        "plan_sha256": "A" * 64,
        "dataset_sha256": "B" * 64,
        "source_root": "D:/styled assets",
        "source_provenance": source_import.SOURCE_PROVENANCE,
        "source_policy": "immutable",
    }
    return taxonomy.build_taxonomy(
        plan_path=Path(
            "D:/RedMMOTitanWindowsData/AssetImports/StylizedSource/plan.json"
        ),
        plan_file_sha256="E" * 64,
        plan=plan,
        records=records,
    )


def decision_for(
    record: dict[str, object],
    *,
    action: str,
) -> dict[str, object]:
    return {
        "action": action,
        "expected_object_family": record["object_family"],
        "expected_relative_path": record["relative_path"],
        "expected_review_required": record["review_required"],
        "expected_source_sha256": record["source_sha256"],
        "expected_v2_object_path": record["v2_object_path"],
        "reason": "Explicit bounded review decision.",
        "stable_source_id": record["stable_source_id"],
    }


def build_decisions(
    taxonomy_payload: dict[str, object],
    decisions: list[dict[str, object]],
    *,
    authority_kind: str,
) -> dict[str, object]:
    normalized = sorted(decisions, key=lambda value: value["stable_source_id"])
    return {
        "authority": {
            "evidence_ids": ["evidence.fixture.static"],
            "kind": authority_kind,
            "name": "Fixture reviewer",
        },
        "decision_count": len(normalized),
        "decisions": normalized,
        "schema": MODULE.DECISION_SCHEMA,
        "taxonomy_binding": {
            "dataset_sha256": taxonomy_payload["dataset_sha256"],
            "plan_file_sha256": taxonomy_payload["plan_file_sha256"],
            "plan_sha256": taxonomy_payload["plan_sha256"],
            "record_count": taxonomy_payload["record_count"],
            "ruleset_sha256": taxonomy_payload["ruleset_sha256"],
            "taxonomy_file_sha256": TAXONOMY_FILE_SHA,
            "taxonomy_sha256": taxonomy_payload["taxonomy_sha256"],
        },
    }


def resolve(
    taxonomy_payload: dict[str, object],
    decisions_payload: dict[str, object],
    *,
    max_records: int = 64,
) -> dict[str, object]:
    return MODULE.build_resolved_selection(
        taxonomy_payload=taxonomy_payload,
        taxonomy_file_sha256=TAXONOMY_FILE_SHA,
        decisions_payload=decisions_payload,
        decisions_file_sha256=DECISIONS_FILE_SHA,
        max_records=max_records,
    )


class StylizedSourceResolvedSelectionTests(unittest.TestCase):
    def test_complete_quarantine_group_emits_no_import_authority(self) -> None:
        duplicate_sha = "F" * 64
        records = [
            make_record(
                "Stylized_Trees/DEC_Door_Wood/"
                "DEC_Door_Wood_Color.png",
                index=0,
                source_sha256=duplicate_sha,
            ),
            make_record(
                "Stylized_Trees/DEC_Door_Wood/"
                "DEC_Door_Wood_Normal.png",
                index=1,
                source_sha256=duplicate_sha,
            ),
        ]
        overlay = build_taxonomy(records)
        decisions = build_decisions(
            overlay,
            [
                decision_for(record, action="retain_quarantined_in_place")
                for record in overlay["records"]
            ],
            authority_kind="canonical_evidence",
        )
        result = resolve(overlay, decisions)
        self.assertEqual(result["selection_count"], 0)
        self.assertFalse(result["selection_ready"])
        self.assertFalse(result["importer_ready"])
        self.assertEqual(result["selection_kind"], "quarantine_resolution")
        self.assertEqual(result["quarantine_count"], 2)
        self.assertEqual(result["decision_group_count"], 1)
        self.assertEqual(result["duplicate_payload_group_count"], 1)
        self.assertEqual(result["global_duplicate_payload_group_count"], 1)
        self.assertEqual(
            len(
                {
                    record["stable_group_id"]
                    for record in result["quarantined_records"]
                }
            ),
            1,
        )

    def test_nonhuman_authority_cannot_approve_candidate(self) -> None:
        overlay = build_taxonomy(
            [
                make_record(
                    "Stylized_Trees/SM_AcaciaTree/"
                    "SM_AcaciaTree_Color.png",
                    index=0,
                )
            ]
        )
        decisions = build_decisions(
            overlay,
            [decision_for(overlay["records"][0], action="approve_import")],
            authority_kind="canonical_evidence",
        )
        with self.assertRaisesRegex(RuntimeError, "approval is disabled"):
            resolve(overlay, decisions)

    def test_review_required_record_cannot_be_human_approved(self) -> None:
        overlay = build_taxonomy(
            [
                make_record(
                    "Stylized_Trees/DEC_Door_Wood/"
                    "DEC_Door_Wood_Color.png",
                    index=0,
                )
            ]
        )
        decisions = build_decisions(
            overlay,
            [decision_for(overlay["records"][0], action="approve_import")],
            authority_kind="human_review",
        )
        with self.assertRaisesRegex(RuntimeError, "approval is disabled"):
            resolve(overlay, decisions)

    def test_partial_family_review_fails_closed(self) -> None:
        overlay = build_taxonomy(
            [
                make_record(
                    "Stylized_Trees/SM_AcaciaTree/"
                    "SM_AcaciaTree_Color.png",
                    index=0,
                ),
                make_record(
                    "Stylized_Trees/SM_AcaciaTree/"
                    "SM_AcaciaTree_Normal.png",
                    index=1,
                ),
            ]
        )
        decisions = build_decisions(
            overlay,
            [decision_for(overlay["records"][0], action="defer")],
            authority_kind="human_review",
        )
        with self.assertRaisesRegex(RuntimeError, "Reviewed family group is incomplete"):
            resolve(overlay, decisions)

    def test_globally_duplicate_payload_approval_is_closed_before_selection(self) -> None:
        duplicate_sha = "F" * 64
        overlay = build_taxonomy(
            [
                make_record(
                    "Stylized_Trees/SM_AcaciaTree/"
                    "SM_AcaciaTree_Color.png",
                    index=0,
                    source_sha256=duplicate_sha,
                ),
                make_record(
                    "Stylized_Trees/SM_OtherTree/"
                    "SM_OtherTree_Color.png",
                    index=1,
                    source_sha256=duplicate_sha,
                ),
            ]
        )
        decisions = build_decisions(
            overlay,
            [decision_for(overlay["records"][0], action="approve_import")],
            authority_kind="human_review",
        )
        with self.assertRaisesRegex(RuntimeError, "approval is disabled"):
            resolve(overlay, decisions)

    def test_self_asserted_human_candidate_group_cannot_resolve(self) -> None:
        overlay = build_taxonomy(
            [
                make_record(
                    "Stylized_Trees/SM_AcaciaTree/"
                    "SM_AcaciaTree_Color.png",
                    index=0,
                ),
                make_record(
                    "Stylized_Trees/SM_AcaciaTree/"
                    "SM_AcaciaTree_Normal.png",
                    index=1,
                ),
            ]
        )
        decisions = build_decisions(
            overlay,
            [
                decision_for(record, action="approve_import")
                for record in overlay["records"]
            ],
            authority_kind="human_review",
        )
        with self.assertRaisesRegex(RuntimeError, "approval is disabled"):
            resolve(overlay, decisions)

    def test_stale_taxonomy_binding_is_rejected(self) -> None:
        overlay = build_taxonomy(
            [
                make_record(
                    "Stylized_Trees/SM_AcaciaTree/"
                    "SM_AcaciaTree_Color.png",
                    index=0,
                )
            ]
        )
        decisions = build_decisions(
            overlay,
            [decision_for(overlay["records"][0], action="defer")],
            authority_kind="human_review",
        )
        decisions["taxonomy_binding"]["taxonomy_sha256"] = "0" * 64
        with self.assertRaisesRegex(RuntimeError, "stale"):
            resolve(overlay, decisions)

    def test_decision_identity_mismatch_is_rejected(self) -> None:
        overlay = build_taxonomy(
            [
                make_record(
                    "Stylized_Trees/SM_AcaciaTree/"
                    "SM_AcaciaTree_Color.png",
                    index=0,
                )
            ]
        )
        decision = decision_for(overlay["records"][0], action="defer")
        decision["expected_source_sha256"] = "F" * 64
        decisions = build_decisions(
            overlay, [decision], authority_kind="human_review"
        )
        with self.assertRaisesRegex(RuntimeError, "identity mismatch"):
            resolve(overlay, decisions)

    def test_selection_limit_is_enforced_after_exact_resolution(self) -> None:
        overlay = build_taxonomy(
            [
                make_record(
                    "Stylized_Trees/SM_AcaciaTree/"
                    "SM_AcaciaTree_Color.png",
                    index=0,
                ),
                make_record(
                    "Stylized_Trees/SM_AcaciaTree/"
                    "SM_AcaciaTree_Normal.png",
                    index=1,
                ),
            ]
        )
        decisions = build_decisions(
            overlay,
            [
                decision_for(record, action="approve_import")
                for record in overlay["records"]
            ],
            authority_kind="human_review",
        )
        with self.assertRaisesRegex(RuntimeError, "approval is disabled"):
            resolve(overlay, decisions, max_records=1)

    def test_output_is_deterministic_and_tamper_fails_validation(self) -> None:
        overlay = build_taxonomy(
            [
                make_record(
                    "Stylized_Trees/DEC_Door_Wood/"
                    "DEC_Door_Wood_Color.png",
                    index=0,
                )
            ]
        )
        decisions = build_decisions(
            overlay,
            [
                decision_for(
                    overlay["records"][0],
                    action="retain_quarantined_in_place",
                )
            ],
            authority_kind="canonical_evidence",
        )
        first = resolve(overlay, decisions)
        second = resolve(overlay, copy.deepcopy(decisions))
        self.assertEqual(first, second)
        MODULE.validate_resolved_selection(
            first,
            taxonomy_payload=overlay,
            taxonomy_file_sha256=TAXONOMY_FILE_SHA,
            decisions_payload=decisions,
            decisions_file_sha256=DECISIONS_FILE_SHA,
            max_records=64,
        )
        tampered = copy.deepcopy(first)
        tampered["quarantined_records"][0]["object_family"] = "vegetation_tree"
        with self.assertRaisesRegex(RuntimeError, "exact deterministic result"):
            MODULE.validate_resolved_selection(
                tampered,
                taxonomy_payload=overlay,
                taxonomy_file_sha256=TAXONOMY_FILE_SHA,
                decisions_payload=decisions,
                decisions_file_sha256=DECISIONS_FILE_SHA,
                max_records=64,
            )

    def test_decisions_must_be_strictly_sorted(self) -> None:
        overlay = build_taxonomy(
            [
                make_record(
                    "Stylized_Trees/SM_AcaciaTree/"
                    "SM_AcaciaTree_Color.png",
                    index=0,
                ),
                make_record(
                    "Stylized_Trees/SM_AcaciaTree/"
                    "SM_AcaciaTree_Normal.png",
                    index=1,
                ),
            ]
        )
        decisions = build_decisions(
            overlay,
            [
                decision_for(record, action="defer")
                for record in overlay["records"]
            ],
            authority_kind="human_review",
        )
        decisions["decisions"].reverse()
        with self.assertRaisesRegex(RuntimeError, "strictly sorted"):
            resolve(overlay, decisions)

    def test_no_clobber_preserves_existing_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "selection.json"
            source_import.write_json_no_clobber(output, {"first": True})
            before = output.read_bytes()
            with self.assertRaisesRegex(RuntimeError, "Refusing to overwrite"):
                source_import.write_json_no_clobber(output, {"second": True})
            self.assertEqual(output.read_bytes(), before)

    def test_json_round_trip_validates_exactly(self) -> None:
        overlay = build_taxonomy(
            [
                make_record(
                    "Stylized_Trees/DEC_Door_Wood/"
                    "DEC_Door_Wood_Color.png",
                    index=0,
                )
            ]
        )
        decisions = build_decisions(
            overlay,
            [
                decision_for(
                    overlay["records"][0],
                    action="retain_quarantined_in_place",
                )
            ],
            authority_kind="canonical_evidence",
        )
        result = resolve(overlay, decisions)
        decoded = json.loads(json.dumps(result, sort_keys=True))
        MODULE.validate_resolved_selection(
            decoded,
            taxonomy_payload=overlay,
            taxonomy_file_sha256=TAXONOMY_FILE_SHA,
            decisions_payload=decisions,
            decisions_file_sha256=DECISIONS_FILE_SHA,
            max_records=64,
        )


if __name__ == "__main__":
    unittest.main()
