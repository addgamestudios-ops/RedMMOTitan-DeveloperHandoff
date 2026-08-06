from __future__ import annotations

import copy
from contextlib import redirect_stdout
import hashlib
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from Tools import build_redmmo_stylized_review_request as review_request
from Tools import build_redmmo_stylized_source_taxonomy as taxonomy
from Tools import import_redmmo_stylized_source_library as source_import


TAXONOMY_FILE_SHA256 = "A" * 64


def make_record(
    relative_path: str,
    *,
    index: int,
    source_sha256: str | None = None,
) -> source_import.ImportRecord:
    relative = Path(relative_path)
    source_sha = source_sha256 or hashlib.sha256(
        relative_path.encode("utf-8")
    ).hexdigest().upper()
    stable_id = source_import._stable_source_id(
        relative_path.replace("\\", "/")
    )
    destination_path = (
        "/Game/RedMMO/ArtLibrary/StylizedSource/"
        f"{relative.parts[0]}/{relative.parent.name}"
    )
    return source_import.ImportRecord(
        index=index,
        stable_source_id=stable_id,
        relative_path=relative_path.replace("\\", "/"),
        category=relative.parts[0],
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
        "plan_sha256": "B" * 64,
        "dataset_sha256": "C" * 64,
        "source_root": "D:/styled assets",
        "source_provenance": source_import.SOURCE_PROVENANCE,
        "source_policy": "immutable",
    }
    return taxonomy.build_taxonomy(
        plan_path=Path(
            "D:/RedMMOTitanWindowsData/AssetImports/StylizedSource/plan.json"
        ),
        plan_file_sha256="D" * 64,
        plan=plan,
        records=records,
    )


def walk_keys(value: object) -> set[str]:
    keys: set[str] = set()
    if isinstance(value, dict):
        keys.update(value)
        for child in value.values():
            keys.update(walk_keys(child))
    elif isinstance(value, list):
        for child in value:
            keys.update(walk_keys(child))
    return keys


def resign_taxonomy(payload: dict[str, object]) -> None:
    without_digest = dict(payload)
    without_digest.pop("taxonomy_sha256", None)
    payload["taxonomy_sha256"] = review_request._digest(without_digest)


class StylizedSourceReviewRequestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        (
            cls.trust_file_sha256,
            cls.trust_contract,
        ) = review_request.load_pinned_trust_contract()

    def setUp(self) -> None:
        duplicate_sha = "E" * 64
        self.overlay = build_taxonomy(
            [
                make_record(
                    "Stylized_Grass/PRP_Grass_WildField_000/"
                    "PRP_Grass_WildField_000_Color.png",
                    index=0,
                ),
                make_record(
                    "Stylized_Grass/PRP_Grass_WildField_000/"
                    "PRP_Grass_WildField_000_Normal.png",
                    index=1,
                ),
                make_record(
                    "Stylized_Rocks/SM_Crystal_A/"
                    "SM_Crystal_A_Color.png",
                    index=2,
                    source_sha256=duplicate_sha,
                ),
                make_record(
                    "Stylized_Rocks/SM_Crystal_B/"
                    "SM_Crystal_B_Color.png",
                    index=3,
                    source_sha256=duplicate_sha,
                ),
            ]
        )
        self.grass_ids = [
            record["stable_source_id"]
            for record in self.overlay["records"]
            if "PRP_Grass_WildField_000" in record["relative_path"]
        ]

    def build(self, seeds: list[str], *, max_records: int = 64) -> dict[str, object]:
        return review_request.build_review_request(
            taxonomy_payload=self.overlay,
            taxonomy_file_sha256=TAXONOMY_FILE_SHA256,
            trust_contract_payload=self.trust_contract,
            trust_contract_file_sha256=self.trust_file_sha256,
            seed_stable_source_ids=seeds,
            max_records=max_records,
        )

    def test_either_family_member_expands_to_same_complete_request(self) -> None:
        first = self.build([self.grass_ids[0]])
        second = self.build([self.grass_ids[1]])
        self.assertEqual(first, second)
        self.assertEqual(first["requested_group_count"], 1)
        self.assertEqual(first["requested_record_count"], 2)
        self.assertEqual(
            {
                record["stable_source_id"]
                for record in first["requested_records"]
            },
            set(self.grass_ids),
        )
        self.assertEqual(first["request_kind"], "review_only")
        self.assertEqual(
            first["trust_contract_binding"]["external_trust_state"],
            "not_configured",
        )

    def test_request_contains_no_decision_or_import_authority(self) -> None:
        result = self.build([self.grass_ids[0]])
        self.assertEqual(
            set(result),
            {
                "max_records",
                "purpose",
                "request_kind",
                "request_sha256",
                "requested_group_count",
                "requested_group_ids",
                "requested_groups",
                "requested_record_count",
                "requested_records",
                "required_review_claims",
                "schema",
                "taxonomy_binding",
                "touched_global_duplicate_payload_group_count",
                "touched_global_duplicate_payload_groups",
                "trust_contract_binding",
                "unresolved_review_questions",
            },
        )
        self.assertEqual(
            set(result["trust_contract_binding"]),
            {
                "attestation_schema",
                "contract_file_sha256",
                "contract_sha256",
                "external_trust_state",
            },
        )
        forbidden = {
            "action",
            "approval",
            "approval_capability",
            "approval_enabled",
            "approved",
            "authority",
            "decision",
            "decision_authority",
            "decisions",
            "final_destination",
            "importer_ready",
            "reviewer",
            "reviewer_identity",
            "selected_records",
            "selection_ready",
            "signature",
        }
        self.assertFalse(forbidden & walk_keys(result))
        self.assertEqual(
            result["purpose"], "isolated_import_staging_review_only"
        )
        self.assertIn("usage_rights", result["required_review_claims"])
        self.assertIn(
            "source_texture_visual_review",
            result["required_review_claims"],
        )

    def test_global_duplicate_payload_members_are_reported_not_deduplicated(
        self,
    ) -> None:
        crystal_id = self.overlay["records"][2]["stable_source_id"]
        result = self.build([crystal_id])
        self.assertEqual(
            result["touched_global_duplicate_payload_group_count"], 1
        )
        duplicate = result["touched_global_duplicate_payload_groups"][0]
        self.assertEqual(duplicate["global_member_count"], 2)
        self.assertEqual(duplicate["requested_member_count"], 1)
        self.assertEqual(duplicate["outside_request_member_count"], 1)
        self.assertEqual(
            set(duplicate["global_stable_source_ids"]),
            {
                self.overlay["records"][2]["stable_source_id"],
                self.overlay["records"][3]["stable_source_id"],
            },
        )
        self.assertEqual(
            duplicate["requested_stable_source_ids"],
            [self.overlay["records"][2]["stable_source_id"]],
        )
        self.assertEqual(
            duplicate["outside_request_stable_source_ids"],
            [self.overlay["records"][3]["stable_source_id"]],
        )
        self.assertEqual(
            duplicate["global_member_set_sha256"],
            review_request._digest(
                sorted(duplicate["global_stable_source_ids"])
            ),
        )

    def test_family_cannot_be_truncated_by_max_records(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "family expansion contains 2"):
            self.build([self.grass_ids[0]], max_records=1)

    def test_unknown_or_duplicate_seeds_fail_closed(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "Unknown exact review seed"):
            self.build(["RED-STYLIZED-" + "F" * 24])
        with self.assertRaisesRegex(RuntimeError, "must be unique"):
            self.build([self.grass_ids[0], self.grass_ids[0]])

    def test_contract_tamper_and_request_tamper_fail_closed(self) -> None:
        changed_contract = copy.deepcopy(self.trust_contract)
        changed_contract["approval_enabled"] = True
        with self.assertRaisesRegex(RuntimeError, "semantic digest mismatch"):
            review_request.validate_trust_contract(changed_contract)
        changed_contract["contract_sha256"] = review_request._digest(
            {
                key: value
                for key, value in changed_contract.items()
                if key != "contract_sha256"
            }
        )
        with self.assertRaisesRegex(
            RuntimeError, "not the pinned production contract"
        ):
            review_request.validate_trust_contract(changed_contract)

        changed_contract = copy.deepcopy(self.trust_contract)
        changed_contract["trusted_reviewer_key_fingerprints_sha256"] = [
            "F" * 64
        ]
        changed_contract["contract_sha256"] = review_request._digest(
            {
                key: value
                for key, value in changed_contract.items()
                if key != "contract_sha256"
            }
        )
        with self.assertRaisesRegex(
            RuntimeError, "not the pinned production contract"
        ):
            review_request.validate_trust_contract(changed_contract)

        result = self.build([self.grass_ids[0]])
        changed_request = copy.deepcopy(result)
        changed_request["purpose"] = "import"
        with self.assertRaisesRegex(RuntimeError, "not the exact deterministic"):
            review_request.validate_review_request(
                changed_request,
                taxonomy_payload=self.overlay,
                taxonomy_file_sha256=TAXONOMY_FILE_SHA256,
                trust_contract_payload=self.trust_contract,
                trust_contract_file_sha256=self.trust_file_sha256,
            )

    def test_json_reader_rejects_duplicate_keys_and_nonfinite_values(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            duplicate = root / "duplicate.json"
            duplicate.write_text('{"value":1,"value":2}', encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "not strict UTF-8 JSON"):
                review_request._read_json_once(
                    duplicate,
                    root=root,
                    label="Fixture",
                )

            nonfinite = root / "nonfinite.json"
            nonfinite.write_text('{"value":NaN}', encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "not strict UTF-8 JSON"):
                review_request._read_json_once(
                    nonfinite,
                    root=root,
                    label="Fixture",
                )

            overflow = root / "overflow.json"
            overflow.write_text('{"value":1e9999}', encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "not strict UTF-8 JSON"):
                review_request._read_json_once(
                    overflow,
                    root=root,
                    label="Fixture",
                )
            negative_overflow = root / "negative_overflow.json"
            negative_overflow.write_text(
                '{"value":-1e9999}',
                encoding="utf-8",
            )
            with self.assertRaisesRegex(RuntimeError, "not strict UTF-8 JSON"):
                review_request._read_json_once(
                    negative_overflow,
                    root=root,
                    label="Fixture",
                )

    def test_rendered_taxonomy_fields_are_strictly_typed(self) -> None:
        mutations = (
            ("classification_confidence", 123),
            ("matched_family_tokens", "grass"),
            ("review_reasons", "not_a_list"),
            ("object_family", "invented_family"),
            ("texture_semantic", "roughness"),
        )
        for field, value in mutations:
            with self.subTest(field=field):
                changed = copy.deepcopy(self.overlay)
                changed["records"][0][field] = value
                resign_taxonomy(changed)
                with self.assertRaisesRegex(RuntimeError, "Taxonomy"):
                    review_request.build_review_request(
                        taxonomy_payload=changed,
                        taxonomy_file_sha256=TAXONOMY_FILE_SHA256,
                        trust_contract_payload=self.trust_contract,
                        trust_contract_file_sha256=self.trust_file_sha256,
                        seed_stable_source_ids=[self.grass_ids[0]],
                    )

    def test_validate_reconstructs_exact_request(self) -> None:
        result = self.build([self.grass_ids[0]])
        review_request.validate_review_request(
            result,
            taxonomy_payload=self.overlay,
            taxonomy_file_sha256=TAXONOMY_FILE_SHA256,
            trust_contract_payload=self.trust_contract,
            trust_contract_file_sha256=self.trust_file_sha256,
        )
        expected_sha = review_request._digest(
            {
                key: value
                for key, value in result.items()
                if key != "request_sha256"
            }
        )
        self.assertEqual(result["request_sha256"], expected_sha)

    def test_cli_enforces_boundaries_verification_and_no_clobber(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            taxonomy_root = root / "Taxonomy"
            request_root = root / "ReviewRequests"
            taxonomy_root.mkdir()
            taxonomy_path = taxonomy_root / "taxonomy.json"
            taxonomy_path.write_text(
                json.dumps(self.overlay, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            taxonomy_file_sha = hashlib.sha256(
                taxonomy_path.read_bytes()
            ).hexdigest().upper()
            output_a = request_root / "request_a.json"
            output_b = request_root / "request_b.json"
            common = [
                "--taxonomy",
                str(taxonomy_path),
                "--expected-taxonomy-file-sha256",
                taxonomy_file_sha,
                "--max-records",
                "64",
            ]
            with (
                mock.patch.object(
                    review_request.taxonomy,
                    "TAXONOMY_DIAGNOSTICS_ROOT",
                    taxonomy_root,
                ),
                mock.patch.object(
                    review_request,
                    "REQUEST_ROOT",
                    request_root,
                ),
                redirect_stdout(StringIO()),
            ):
                self.assertEqual(
                    review_request.cli(
                        [
                            "build",
                            *common,
                            "--seed-stable-source-id",
                            self.grass_ids[0],
                            "--output",
                            str(output_a),
                        ]
                    ),
                    0,
                )
                self.assertEqual(
                    review_request.cli(
                        [
                            "build",
                            *common,
                            "--seed-stable-source-id",
                            self.grass_ids[1],
                            "--output",
                            str(output_b),
                        ]
                    ),
                    0,
                )
                self.assertEqual(output_a.read_bytes(), output_b.read_bytes())
                output_sha = hashlib.sha256(
                    output_a.read_bytes()
                ).hexdigest().upper()
                self.assertEqual(
                    review_request.cli(
                        [
                            "verify",
                            "--taxonomy",
                            str(taxonomy_path),
                            "--expected-taxonomy-file-sha256",
                            taxonomy_file_sha,
                            "--request",
                            str(output_a),
                            "--expected-request-file-sha256",
                            output_sha,
                        ]
                    ),
                    0,
                )
                before = output_a.read_bytes()
                with self.assertRaisesRegex(RuntimeError, "Refusing to overwrite"):
                    review_request.cli(
                        [
                            "build",
                            *common,
                            "--seed-stable-source-id",
                            self.grass_ids[0],
                            "--output",
                            str(output_a),
                        ]
                    )
                self.assertEqual(output_a.read_bytes(), before)
                with self.assertRaisesRegex(RuntimeError, "must be below"):
                    review_request.cli(
                        [
                            "build",
                            *common,
                            "--seed-stable-source-id",
                            self.grass_ids[0],
                            "--output",
                            str(root / "outside.json"),
                        ]
                    )
                with self.assertRaisesRegex(RuntimeError, "SHA256 mismatch"):
                    review_request.cli(
                        [
                            "verify",
                            "--taxonomy",
                            str(taxonomy_path),
                            "--expected-taxonomy-file-sha256",
                            taxonomy_file_sha,
                            "--request",
                            str(output_a),
                            "--expected-request-file-sha256",
                            "F" * 64,
                        ]
                    )


if __name__ == "__main__":
    unittest.main()
