from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

from Tools import import_redmmo_stylized_source_library as source_import


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "build_redmmo_stylized_source_taxonomy.py"
)
SPEC = importlib.util.spec_from_file_location("stylized_taxonomy", SCRIPT_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def make_record(
    relative_path: str,
    *,
    index: int = 0,
    category: str | None = None,
) -> source_import.ImportRecord:
    relative = Path(relative_path)
    selected_category = category or relative.parts[0]
    source_sha = hashlib.sha256(relative_path.encode("utf-8")).hexdigest().upper()
    stable_id = "RED-STYLIZED-" + hashlib.sha256(
        relative_path.encode("utf-8")
    ).hexdigest()[:24].upper()
    name = relative.stem
    destination_path = (
        f"/Game/RedMMO/ArtLibrary/StylizedSource/"
        f"{selected_category}/{relative.parent.name}"
    )
    return source_import.ImportRecord(
        index=index,
        stable_source_id=stable_id,
        relative_path=relative_path.replace("\\", "/"),
        category=selected_category,
        source_size=1,
        source_mtime_ns=1,
        source_sha256=source_sha,
        source_suffix=relative.suffix.casefold(),
        semantic=source_import.classify_texture_semantic(relative.name),
        destination_path=destination_path,
        destination_name=name,
        object_path=f"{destination_path}/{name}",
    )


class StylizedSourceTaxonomyTests(unittest.TestCase):
    def test_door_under_trees_is_object_family_conflict(self) -> None:
        record = make_record(
            "Stylized_Trees/DEC_Door_Assorted_Wood_000/"
            "DEC_Door_Assorted_Wood_000_Color.png"
        )
        result = MODULE.classify_record(record)
        self.assertEqual(result.object_family, "architecture_door")
        self.assertEqual(result.classification_confidence, "high")
        self.assertEqual(result.material_tags, ("wood",))
        self.assertTrue(result.review_required)
        self.assertIn(
            "source_category_conflicts_object_family", result.review_reasons
        )
        self.assertIsNone(result.recommended_library_path)

    def test_entry_basewood_under_trees_hits_same_regression(self) -> None:
        record = make_record(
            "Stylized_Trees/DEC_EntryLrg_SancCommon_BaseWood_000/"
            "DEC_EntryLrg_SancCommon_BaseWood_000_Normal.png"
        )
        result = MODULE.classify_record(record)
        self.assertEqual(result.object_family, "architecture_door")
        self.assertEqual(result.material_tags, ("wood",))
        self.assertTrue(result.review_required)

    def test_real_tree_under_trees_can_be_promotion_candidate(self) -> None:
        record = make_record(
            "Stylized_Trees/SM_AcaciaTree_01/SM_AcaciaTree_01_Color.png"
        )
        result = MODULE.classify_record(record)
        self.assertEqual(result.object_family, "vegetation_tree")
        self.assertFalse(result.review_required)
        self.assertEqual(
            result.recommended_library_path, "Environment/Vegetation/Trees"
        )

    def test_source_category_is_not_used_as_object_identity(self) -> None:
        record = make_record(
            "Stylized_Trees/BaseWoodSurface/BaseWoodSurface_Color.png"
        )
        result = MODULE.classify_record(record)
        self.assertEqual(result.object_family, "unresolved")
        self.assertEqual(result.material_tags, ("wood",))
        self.assertTrue(result.review_required)

    def test_material_substance_does_not_override_specific_object(self) -> None:
        record = make_record(
            "Stylized_Metal/PRP_Iron_Door/PRP_Iron_Door_Color.png"
        )
        result = MODULE.classify_record(record)
        self.assertEqual(result.object_family, "architecture_door")
        self.assertEqual(result.material_tags, ("metal",))
        self.assertFalse(
            "source_category_conflicts_object_family" in result.review_reasons
        )

    def test_multiple_specific_families_fail_to_ambiguous_review(self) -> None:
        record = make_record(
            "Stylized_Props/RockGrassBridge/RockGrassBridge_Color.png"
        )
        result = MODULE.classify_record(record)
        self.assertEqual(result.object_family, "ambiguous")
        self.assertEqual(result.classification_confidence, "ambiguous")
        self.assertTrue(result.review_required)
        self.assertIn("multiple_object_family_matches", result.review_reasons)

    def test_generic_prop_never_auto_promotes(self) -> None:
        record = make_record(
            "Stylized_Props/PRP_ControlPanel/PRP_ControlPanel_Color.png"
        )
        result = MODULE.classify_record(record)
        self.assertEqual(result.object_family, "prop_generic")
        self.assertTrue(result.review_required)
        self.assertIsNone(result.recommended_library_path)

    def test_build_is_deterministic_and_summary_is_exact(self) -> None:
        records = [
            make_record(
                "Stylized_Trees/DEC_Door_Wood/DEC_Door_Wood_Color.png",
                index=0,
            ),
            make_record(
                "Stylized_Trees/SM_AcaciaTree/SM_AcaciaTree_Normal.png",
                index=1,
            ),
        ]
        plan = {
            "plan_sha256": "A" * 64,
            "dataset_sha256": "B" * 64,
            "source_root": "D:/styled assets",
            "source_provenance": source_import.SOURCE_PROVENANCE,
            "source_policy": "immutable",
        }
        kwargs = {
            "plan_path": Path("D:/Diagnostics/plan.json"),
            "plan_file_sha256": "C" * 64,
            "plan": plan,
            "records": records,
        }
        first = MODULE.build_taxonomy(**kwargs)
        second = MODULE.build_taxonomy(**kwargs)
        self.assertEqual(first, second)
        self.assertEqual(first["record_count"], 2)
        self.assertEqual(first["review_required_count"], 1)
        self.assertEqual(first["promotion_candidate_count"], 1)
        self.assertEqual(first["source_category_conflict_count"], 1)
        MODULE.validate_taxonomy(first, **kwargs)

    def test_taxonomy_tamper_fails_exact_validation(self) -> None:
        record = make_record(
            "Stylized_Trees/SM_AcaciaTree/SM_AcaciaTree_Color.png"
        )
        plan = {
            "plan_sha256": "A" * 64,
            "dataset_sha256": "B" * 64,
            "source_root": "D:/styled assets",
            "source_provenance": source_import.SOURCE_PROVENANCE,
            "source_policy": "immutable",
        }
        kwargs = {
            "plan_path": Path("D:/Diagnostics/plan.json"),
            "plan_file_sha256": "C" * 64,
            "plan": plan,
            "records": [record],
        }
        taxonomy = MODULE.build_taxonomy(**kwargs)
        tampered = copy.deepcopy(taxonomy)
        tampered["records"][0]["object_family"] = "architecture_door"
        with self.assertRaisesRegex(RuntimeError, "exact deterministic result"):
            MODULE.validate_taxonomy(tampered, **kwargs)

    def test_ruleset_digest_covers_rule_changes(self) -> None:
        payload = MODULE._ruleset_payload()
        changed = copy.deepcopy(payload)
        changed["policy"]["material_tokens_never_imply_object_family"] = False
        self.assertNotEqual(MODULE._digest(payload), MODULE._digest(changed))
        self.assertEqual(MODULE.RULESET_SHA256, MODULE._digest(payload))

    def test_no_clobber_writer_refuses_existing_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "taxonomy.json"
            source_import.write_json_no_clobber(output, {"first": True})
            before = output.read_bytes()
            with self.assertRaisesRegex(RuntimeError, "Refusing to overwrite"):
                source_import.write_json_no_clobber(output, {"second": True})
            self.assertEqual(output.read_bytes(), before)

    def test_taxonomy_json_round_trip_is_strict(self) -> None:
        record = make_record(
            "Stylized_Water/Waterfall/Waterfall_Color.png"
        )
        plan = {
            "plan_sha256": "A" * 64,
            "dataset_sha256": "B" * 64,
            "source_root": "D:/styled assets",
            "source_provenance": source_import.SOURCE_PROVENANCE,
            "source_policy": "immutable",
        }
        kwargs = {
            "plan_path": Path("D:/Diagnostics/plan.json"),
            "plan_file_sha256": "C" * 64,
            "plan": plan,
            "records": [record],
        }
        taxonomy = MODULE.build_taxonomy(**kwargs)
        encoded = json.dumps(taxonomy, sort_keys=True)
        decoded = json.loads(encoded)
        MODULE.validate_taxonomy(decoded, **kwargs)


if __name__ == "__main__":
    unittest.main()
