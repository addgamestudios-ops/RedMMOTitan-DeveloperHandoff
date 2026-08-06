from __future__ import annotations

import hashlib
import subprocess
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path
from unittest.mock import patch

from Tools.build_redmmo_asset_curation_manifest import (
    CurationManifestError,
    build_manifest,
    classify_asset_class,
    discover_local_provenance_files,
    family_identity,
    manifest_bytes,
    validate_diagnostics_path,
    write_manifest_atomic,
)
from Tools.export_redmmo_asset_registry_catalog import PRIORITY_LIBRARY_ROOTS


ROOT = Path(__file__).resolve().parents[2]


def _candidate(root: str, index: int, asset_class_path: str, name: str):
    package_name = f"{root}/Meshes/{name}"
    object_path = f"{package_name}.{name}"
    return {
        "stable_candidate_id": hashlib.sha256(
            object_path.encode("utf-8")
        ).hexdigest()[:24].upper(),
        "library_root": root,
        "package_name": package_name,
        "package_path": f"{root}/Meshes",
        "asset_name": name,
        "object_path": object_path,
        "asset_class_path": asset_class_path,
        "candidate_roles": ["Vegetation.Plant"],
        "registry_tags": {},
        "source_policy": "vendor_source_immutable",
        "review_status": "unreviewed_asset_registry_candidate",
        "requires_license_review": True,
        "requires_visual_and_performance_review": True,
    }


def _raw_report(candidates):
    root_counts = Counter(candidate["library_root"] for candidate in candidates)
    class_counts = Counter(candidate["asset_class_path"] for candidate in candidates)
    basename_counts = Counter(
        candidate["asset_name"].casefold() for candidate in candidates
    )
    return {
        "schema_version": 1,
        "audit_id": "redmmo-unreal-asset-registry-catalog-candidates",
        "evidence_class": "static",
        "status": "candidate_only",
        "scope": {
            "library_roots": list(PRIORITY_LIBRARY_ROOTS),
            "candidate_count": len(candidates),
            "root_candidate_counts": {
                root: root_counts[root] for root in PRIORITY_LIBRARY_ROOTS
            },
            "asset_class_counts": dict(sorted(class_counts.items())),
            "duplicate_basename_group_count": sum(
                1 for count in basename_counts.values() if count > 1
            ),
        },
        "candidates": candidates,
    }


class RedMMOAssetCurationManifestTests(unittest.TestCase):
    def _all_roots_fixture(self):
        classes = (
            "/Script/Engine.StaticMesh",
            "/Script/Engine.MaterialInstanceConstant",
            "/Script/Engine.Texture2D",
            "/Script/Engine.World",
            "/Script/CoreUObject.ObjectRedirector",
            "/Script/Niagara.NiagaraSystem",
        )
        return [
            _candidate(root, index, classes[index], f"SM_Plant_Alien_Aloe_01_{index}")
            for index, root in enumerate(PRIORITY_LIBRARY_ROOTS)
        ]

    def test_class_policy_separates_primary_support_deferred_and_excluded(self):
        self.assertEqual(
            classify_asset_class("/Script/Engine.StaticMesh")[0],
            "primary_environment_candidate",
        )
        self.assertEqual(
            classify_asset_class("/Script/Engine.Texture2D")[0],
            "support_dependency_candidate",
        )
        self.assertEqual(
            classify_asset_class("/Script/Niagara.NiagaraSystem")[0],
            "deferred_specialty_candidate",
        )
        self.assertEqual(
            classify_asset_class("/Script/Engine.World")[0],
            "excluded_technical_or_reference",
        )
        self.assertEqual(
            classify_asset_class("/Script/Unknown.NewType")[0],
            "deferred_unknown_class",
        )

    def test_every_candidate_is_retained_once_without_approval(self):
        candidates = self._all_roots_fixture()
        manifest = build_manifest(
            _raw_report(candidates),
            input_path=Path("candidate.json"),
            input_sha256="A" * 64,
            provenance_files={root: [] for root in PRIORITY_LIBRARY_ROOTS},
        )
        self.assertEqual(manifest["summary"]["entry_count"], len(candidates))
        self.assertEqual(
            {entry["stable_candidate_id"] for entry in manifest["entries"]},
            {candidate["stable_candidate_id"] for candidate in candidates},
        )
        self.assertEqual(manifest["summary"]["license_approved_count"], 0)
        self.assertEqual(manifest["summary"]["asset_approved_count"], 0)
        for entry in manifest["entries"]:
            self.assertFalse(entry["license_approved"])
            self.assertFalse(entry["asset_approved"])
            self.assertEqual(entry["approved_roles"], [])
            self.assertEqual(entry["source_policy"], "vendor_source_immutable")
            self.assertIn(
                "RED MMO/Candidates/Needs License Review",
                entry["proposed_collections"],
            )

    def test_manifest_bytes_and_family_ids_are_deterministic(self):
        candidates = self._all_roots_fixture()
        report = _raw_report(candidates)
        kwargs = {
            "input_path": Path("candidate.json"),
            "input_sha256": "B" * 64,
            "provenance_files": {root: [] for root in PRIORITY_LIBRARY_ROOTS},
        }
        first = build_manifest(report, **kwargs)
        second = build_manifest(_raw_report(list(reversed(candidates))), **kwargs)
        self.assertEqual(manifest_bytes(first), manifest_bytes(second))
        aloe_a = family_identity("/Game/Alien_Plants_Pack", "SM_Plant_Alien_Aloe_01_A")
        aloe_b = family_identity("/Game/Alien_Plants_Pack", "MI_Plant_Alien_Aloe_02_B")
        self.assertEqual(aloe_a, aloe_b)

    def test_candidate_gate_regressions_fail_closed(self):
        candidates = self._all_roots_fixture()
        bad_status = _raw_report(candidates)
        bad_status["status"] = "approved"
        with self.assertRaises(CurationManifestError):
            build_manifest(
                bad_status,
                input_path=Path("candidate.json"),
                input_sha256="C" * 64,
                provenance_files={root: [] for root in PRIORITY_LIBRARY_ROOTS},
            )

        bad_candidate = dict(candidates[0])
        bad_candidate["requires_license_review"] = False
        with self.assertRaises(CurationManifestError):
            build_manifest(
                _raw_report([bad_candidate, *candidates[1:]]),
                input_path=Path("candidate.json"),
                input_sha256="D" * 64,
                provenance_files={root: [] for root in PRIORITY_LIBRARY_ROOTS},
            )

        for field, invalid_value in (
            ("source_policy", "project_owned"),
            ("review_status", "approved"),
            ("requires_visual_and_performance_review", False),
            ("candidate_roles", "Vegetation.Plant"),
            ("registry_tags", []),
        ):
            mutated = [dict(candidate) for candidate in candidates]
            mutated[0][field] = invalid_value
            with self.subTest(field=field), self.assertRaises(CurationManifestError):
                build_manifest(
                    _raw_report(mutated),
                    input_path=Path("candidate.json"),
                    input_sha256="D" * 64,
                    provenance_files={
                        root: [] for root in PRIORITY_LIBRARY_ROOTS
                    },
                )

    def test_candidate_identity_and_scope_mutations_fail_closed(self):
        candidates = self._all_roots_fixture()
        mutations = {
            "claimed_root": ("library_root", PRIORITY_LIBRARY_ROOTS[1]),
            "package_path": ("package_path", "/Game/Wrong"),
            "object_path": ("object_path", "/Game/Wrong.Asset"),
            "stable_candidate_id": ("stable_candidate_id", "0" * 24),
        }
        for label, (field, invalid_value) in mutations.items():
            mutated = [dict(candidate) for candidate in candidates]
            mutated[0][field] = invalid_value
            with self.subTest(label=label), self.assertRaises(
                CurationManifestError
            ):
                build_manifest(
                    _raw_report(mutated),
                    input_path=Path("candidate.json"),
                    input_sha256="F" * 64,
                    provenance_files={
                        root: [] for root in PRIORITY_LIBRARY_ROOTS
                    },
                )

        for scope_field in (
            "root_candidate_counts",
            "asset_class_counts",
            "duplicate_basename_group_count",
        ):
            report = _raw_report(candidates)
            report["scope"][scope_field] = {}
            with self.subTest(scope_field=scope_field), self.assertRaises(
                CurationManifestError
            ):
                build_manifest(
                    report,
                    input_path=Path("candidate.json"),
                    input_sha256="F" * 64,
                    provenance_files={
                        root: [] for root in PRIORITY_LIBRARY_ROOTS
                    },
                )

        duplicate = [*candidates, dict(candidates[0])]
        with self.assertRaises(CurationManifestError):
            build_manifest(
                _raw_report(duplicate),
                input_path=Path("candidate.json"),
                input_sha256="F" * 64,
                provenance_files={root: [] for root in PRIORITY_LIBRARY_ROOTS},
            )

    def test_review_batch_includes_same_family_support_dependencies(self):
        candidates = self._all_roots_fixture()
        support = _candidate(
            PRIORITY_LIBRARY_ROOTS[0],
            99,
            "/Script/Engine.Texture2D",
            "T_Plant_Alien_Aloe_02_A",
        )
        manifest = build_manifest(
            _raw_report([*candidates, support]),
            input_path=Path("candidate.json"),
            input_sha256="G" * 64,
            provenance_files={root: [] for root in PRIORITY_LIBRARY_ROOTS},
        )
        primary_id = candidates[0]["stable_candidate_id"]
        batch = next(
            item
            for item in manifest["review_batches"]
            if primary_id in item["primary_member_ids"]
        )
        self.assertIn(support["stable_candidate_id"], batch["member_ids"])
        self.assertIn(
            support["stable_candidate_id"],
            batch["support_dependency_member_ids"],
        )
        self.assertEqual(batch["primary_member_count"], 1)
        self.assertEqual(batch["support_dependency_member_count"], 1)

    def test_local_provenance_is_discovered_but_never_approved(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            for root in PRIORITY_LIBRARY_ROOTS:
                disk_root = project / "Content" / root.removeprefix("/Game/")
                disk_root.mkdir(parents=True)
            license_file = (
                project / "Content" / "SoStylized" / "README_LICENSE.txt"
            )
            license_file.write_text("fixture only", encoding="utf-8")
            provenance = discover_local_provenance_files(project)
            self.assertEqual(len(provenance["/Game/SoStylized"]), 1)
            self.assertEqual(provenance["/Game/AlienJungle"], [])

            manifest = build_manifest(
                _raw_report(self._all_roots_fixture()),
                input_path=Path("candidate.json"),
                input_sha256="E" * 64,
                provenance_files=provenance,
            )
            source = {
                item["library_root"]: item for item in manifest["source_packs"]
            }
            self.assertFalse(source["/Game/SoStylized"]["license_approved"])
            self.assertIn(
                "requires_human_review",
                source["/Game/SoStylized"]["license_review_status"],
            )

    def test_provenance_scan_rejects_content_or_nested_reparse_and_walk_error(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            for root in PRIORITY_LIBRARY_ROOTS:
                disk_root = project / "Content" / root.removeprefix("/Game/")
                disk_root.mkdir(parents=True)
            nested = project / "Content" / "SoStylized" / "LinkedDocs"
            nested.mkdir()

            with patch(
                "Tools.build_redmmo_asset_curation_manifest._is_link_or_reparse",
                side_effect=lambda path: path.name == "Content",
            ), self.assertRaises(CurationManifestError):
                discover_local_provenance_files(project)

            with patch(
                "Tools.build_redmmo_asset_curation_manifest._is_link_or_reparse",
                side_effect=lambda path: path.name == "LinkedDocs",
            ), self.assertRaises(CurationManifestError):
                discover_local_provenance_files(project)

            def fail_walk(*args, **kwargs):
                kwargs["onerror"](PermissionError("fixture access denied"))
                return iter(())

            with patch(
                "Tools.build_redmmo_asset_curation_manifest.os.walk",
                side_effect=fail_walk,
            ), self.assertRaises(CurationManifestError):
                discover_local_provenance_files(project)

    def test_output_path_is_external_atomic_and_no_clobber(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            diagnostics = root / "Diagnostics"
            output = diagnostics / "M07" / "manifest.json"
            resolved = validate_diagnostics_path(
                output,
                diagnostics_root=diagnostics,
                must_exist=False,
            )
            write_manifest_atomic(resolved, b"{}\n")
            self.assertEqual(resolved.read_bytes(), b"{}\n")
            with self.assertRaises(CurationManifestError):
                write_manifest_atomic(resolved, b"{\"replace\":true}\n")
            with self.assertRaises(CurationManifestError):
                validate_diagnostics_path(
                    root / "Content" / "manifest.json",
                    diagnostics_root=diagnostics,
                    must_exist=False,
                )
            outside_input = root / "candidate.json"
            outside_input.write_text("{}\n", encoding="utf-8")
            with self.assertRaises(CurationManifestError):
                validate_diagnostics_path(
                    outside_input,
                    diagnostics_root=diagnostics,
                    must_exist=True,
                )

    def test_script_can_be_invoked_directly_from_project_root(self):
        result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "Tools" / "build_redmmo_asset_curation_manifest.py"),
                "--help",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("--project-root", result.stdout)


if __name__ == "__main__":
    unittest.main()
