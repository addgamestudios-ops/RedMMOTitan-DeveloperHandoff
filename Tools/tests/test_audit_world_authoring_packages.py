import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from Tools import audit_world_authoring_packages as audit


class WorldAuthoringPackageAuditTests(unittest.TestCase):
    def test_detects_ascii_and_utf16_runtime_references(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "A.umap").write_bytes(b"header/Script/PCG tail")
            (root / "B.uasset").write_bytes("/Script/WorldGen".encode("utf-16-le"))

            report = audit.build_report(root)

            self.assertEqual(report["scope"]["package_count"], 2)
            self.assertEqual(
                report["summary"]["strong_marker_package_counts"][
                    "pcg_runtime_reference"
                ],
                1,
            )
            self.assertEqual(
                report["summary"]["strong_marker_package_counts"][
                    "worldgen_runtime_reference"
                ],
                1,
            )
            self.assertEqual(report["summary"]["runtime_reference_package_count"], 2)

    def test_ue58_split_package_sidecars_are_included(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "Split.uasset").write_bytes(b"package")
            (root / "Split.m.ubulk").write_bytes(
                b"RedManualPlacementProtectionComponent"
            )
            (root / "Split.upayload").write_bytes(
                b"bApprovedForPCG\x00bSuppressAllProceduralDressing"
            )

            report = audit.build_report(root)

            self.assertEqual(report["scope"]["package_count"], 1)
            self.assertEqual(report["scope"]["payload_count"], 3)
            self.assertEqual(report["scope"]["sidecar_count"], 2)
            self.assertEqual(
                report["summary"]["strong_marker_package_counts"][
                    "manual_protection_marker"
                ],
                1,
            )
            self.assertEqual(
                report["summary"]["strong_marker_package_counts"][
                    "palette_pcg_policy_marker"
                ],
                1,
            )
            self.assertEqual(
                report["summary"]["strong_marker_package_counts"][
                    "dressing_policy_marker"
                ],
                1,
            )
            self.assertEqual(report["summary"]["policy_marker_package_count"], 1)

    def test_weak_worldgen_labels_are_not_runtime_references(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "Labels.umap").write_bytes(
                b"WorldGen|Noise EWorldGenNoiseType Enum"
            )

            report = audit.build_report(root)

            self.assertEqual(report["summary"]["runtime_reference_package_count"], 0)
            self.assertEqual(
                report["summary"]["weak_marker_package_counts"][
                    "worldgen_label_only"
                ],
                1,
            )

    def test_report_is_deterministic_and_atomic_output_round_trips(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory) / "content"
            root.mkdir()
            (root / "B.uasset").write_bytes(b"bApprovedForPCG")
            (root / "A.umap").write_bytes(b"plain")
            first = audit.build_report(root)
            second = audit.build_report(root)
            self.assertEqual(audit.report_bytes(first), audit.report_bytes(second))
            self.assertEqual(
                [package["package_path"] for package in first["packages"]],
                ["project_content/A.umap", "project_content/B.uasset"],
            )

            output = Path(temporary_directory) / "diagnostics" / "report.json"
            audit.write_report_atomic(output, audit.report_bytes(first))
            self.assertEqual(json.loads(output.read_text(encoding="utf-8")), first)

    def test_exact_names_reject_substrings_and_find_chunk_boundary(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "FalsePositives.uasset").write_bytes(
                b"NotPCGGraphExtra RedManualPlacementProtectionComponentFactory"
            )
            prefix = b"x" * (audit.SCAN_CHUNK_BYTES - 5) + b"\x00"
            (root / "Boundary.umap").write_bytes(
                prefix + b"PCGGraph\x00" + b"tail"
            )

            report = audit.build_report(root)
            by_path = {package["package_path"]: package for package in report["packages"]}

            self.assertEqual(
                by_path["project_content/FalsePositives.uasset"][
                    "strong_marker_groups"
                ],
                {},
            )
            self.assertEqual(
                by_path["project_content/Boundary.umap"]["strong_marker_groups"][
                    "pcg_runtime_reference"
                ],
                ["PCGGraph"],
            )

    def test_overlapping_groups_count_one_package_once(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "Both.umap").write_bytes(
                b"/Script/PCG\x00/Script/WorldGen\x00"
            )

            report = audit.build_report(root)

            self.assertEqual(report["summary"]["runtime_reference_package_count"], 1)
            self.assertEqual(
                report["summary"]["strong_marker_package_counts"][
                    "pcg_runtime_reference"
                ],
                1,
            )
            self.assertEqual(
                report["summary"]["strong_marker_package_counts"][
                    "worldgen_runtime_reference"
                ],
                1,
            )

    def test_protected_payload_manifest_rejects_hash_or_sidecar_drift(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            protected = root / "Protected.umap"
            protected.write_bytes(b"protected")
            expected = hashlib.sha256(protected.read_bytes()).hexdigest().upper()

            report = audit.build_report(
                root,
                protected_relative=Path("Protected.umap"),
                protected_sha256=expected,
                protected_sidecar_sha256={},
            )
            self.assertTrue(
                report["protected_checkpoint"]["matches_expected_manifest"]
            )
            with self.assertRaises(audit.AuditError):
                audit.build_report(
                    root,
                    protected_relative=Path("Protected.umap"),
                    protected_sha256="0" * 64,
                    protected_sidecar_sha256={},
                )

            (root / "Protected.uexp").write_bytes(b"unexpected")
            with self.assertRaises(audit.AuditError):
                audit.build_report(
                    root,
                    protected_relative=Path("Protected.umap"),
                    protected_sha256=expected,
                    protected_sidecar_sha256={},
                )

    def test_report_writes_are_restricted_to_json_diagnostics(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            diagnostics = Path(temporary_directory) / "Diagnostics"
            allowed = diagnostics / "report.json"
            self.assertEqual(
                audit.validate_diagnostics_report_path(
                    allowed, diagnostics_root=diagnostics
                ),
                allowed.resolve(),
            )
            with self.assertRaises(audit.AuditError):
                audit.validate_diagnostics_report_path(
                    Path(temporary_directory) / "outside.json",
                    diagnostics_root=diagnostics,
                )
            with self.assertRaises(audit.AuditError):
                audit.write_report_atomic(
                    Path(temporary_directory) / "Protected.umap", b"unsafe"
                )

    def test_empty_or_missing_content_root_fails_closed(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            empty = Path(temporary_directory)
            with self.assertRaises(audit.AuditError):
                audit.build_report(empty)
            with self.assertRaises(audit.AuditError):
                audit.build_report(empty / "missing")

    def test_live_project_owned_packages_have_no_strong_runtime_markers(self):
        report = audit.build_report(
            audit.DEFAULT_CONTENT_ROOT,
            additional_roots=(
                ("external_actors", audit.DEFAULT_EXTERNAL_ACTOR_ROOT),
                ("external_objects", audit.DEFAULT_EXTERNAL_OBJECT_ROOT),
            ),
            protected_relative=audit.PROTECTED_MAP_RELATIVE,
            protected_sha256=audit.PROTECTED_MAP_SHA256,
            protected_sidecar_sha256={},
        )

        self.assertGreater(report["scope"]["package_count"], 0)
        self.assertTrue(report["scope"]["tree_quiescent_during_scan"])
        self.assertEqual(report["summary"]["runtime_reference_package_count"], 0)
        self.assertEqual(
            report["summary"]["strong_marker_package_counts"][
                "pcg_runtime_reference"
            ],
            0,
        )
        self.assertEqual(
            report["summary"]["strong_marker_package_counts"][
                "worldgen_runtime_reference"
            ],
            0,
        )
        self.assertEqual(
            {root["label"] for root in report["scope"]["roots"]},
            {"project_content", "external_actors", "external_objects"},
        )
        self.assertTrue(
            report["protected_checkpoint"]["matches_expected_manifest"]
        )


if __name__ == "__main__":
    unittest.main()
