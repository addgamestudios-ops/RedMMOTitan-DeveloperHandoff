from __future__ import annotations

import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import Tools.build_redmmo_crosspack_hub_selection as selection
from Tools.build_redmmo_crosspack_hub_selection import (
    CrosspackSelectionError,
    PACK_CONTRACTS,
    build_manifest,
    canonical_json_bytes,
    load_request,
    sha256_bytes,
    validate_output_path,
    validate_request,
    write_authenticated_manifest_no_clobber,
    write_manifest_no_clobber,
)


DESERT_ID = "fab.12ec20bd-ce21-4d3d-8051-13ffb0fe851e"
TROPICAL_ID = "fab.934c1286-7388-4aa5-a300-e0a7cdf65675"


def _request() -> dict[str, object]:
    return {
        "schema_version": 1,
        "request_id": "redmmo-crosspack-minihub-source-selection",
        "request_status": "candidate_only",
        "selection_method": "explicit_exact_path_allowlist",
        "no_category_fallback": True,
        "intended_use": "isolated_redmmo_crosspack_minihub_review",
        "packs": [
            {"pack_id": pack_id, **copy.deepcopy(contract)}
            for pack_id, contract in PACK_CONTRACTS.items()
        ],
        "candidates": [
            {
                "pack_id": pack_id,
                "relative_source_path": relative,
                **copy.deepcopy(contract),
            }
            for (pack_id, relative), contract in selection.CANDIDATE_CONTRACTS.items()
        ],
        "review_gates": {
            "source_identity_reviewed": False,
            "rights_and_noai_boundary_reviewed": False,
            "ue58_compatibility_reviewed": False,
            "dependency_closure_reviewed": False,
            "visual_style_reviewed": False,
            "performance_reviewed": False,
            "nwiro_metadata_only_workflow_reviewed": False,
            "migration_approved": False,
            "map_placement_approved": False,
        },
        "authority": {
            "approval_enabled": False,
            "reviewer_public_keys": [],
            "caller_supplied_trust_roots_allowed": False,
        },
    }


class RedMMOCrosspackHubSelectionTests(unittest.TestCase):
    def _roots(self, parent: Path) -> dict[str, Path]:
        desert = parent / "Titan" / "Content" / "Zenscape_Savanna"
        tropical_project = parent / "TropicalProject"
        tropical = tropical_project / "Content" / "Zenscape_Island"
        (desert / "Model/Tree").mkdir(parents=True)
        (desert / "Material").mkdir(parents=True)
        (tropical / "Blueprint").mkdir(parents=True)
        (tropical / "Material").mkdir(parents=True)
        (tropical_project / "TropicalProject.uproject").write_text(
            json.dumps({"FileVersion": 3, "EngineAssociation": "5.4"}),
            encoding="utf-8",
        )
        (desert / "Model/Tree/SM_A.uasset").write_bytes(
            b"/Game/Zenscape_Savanna/Material/MI_A"
        )
        (desert / "Material/MI_A.uasset").write_bytes(b"desert material")
        (tropical / "Blueprint/BP_Water.uasset").write_bytes(
            b"/Game/Zenscape_Island/Material/MI_Water"
        )
        (tropical / "Material/MI_Water.uasset").write_bytes(b"water material")
        return {DESERT_ID: desert, TROPICAL_ID: tropical}

    def _fixture_contracts(
        self, roots: dict[str, Path]
    ) -> tuple[dict[str, dict[str, object]], dict[tuple[str, str], dict[str, object]]]:
        source_contracts: dict[str, dict[str, object]] = {}
        for pack_id, root in roots.items():
            records, tree_sha256 = selection._walk_source_tree(root.resolve(), {})
            descriptor = None
            if pack_id == TROPICAL_ID:
                descriptor_path = (
                    root.parent.parent / "TropicalProject.uproject"
                ).resolve()
                descriptor_payload = descriptor_path.read_bytes()
                descriptor = {
                    "path": str(descriptor_path),
                    "bytes": len(descriptor_payload),
                    "sha256": sha256_bytes(descriptor_payload),
                    "engine_association": "5.4",
                }
            source_contracts[pack_id] = {
                "canonical_root": str(root.resolve()),
                "source_file_count": len(records),
                "source_bytes": sum(int(record["bytes"]) for record in records),
                "source_tree_sha256": tree_sha256,
                "source_project_descriptor": descriptor,
            }

        candidates: dict[tuple[str, str], dict[str, object]] = {}
        for pack_id, relative, asset_kind, role in (
            (
                DESERT_ID,
                "Model/Tree/SM_A.uasset",
                "StaticMesh",
                "desert_canopy_anchor",
            ),
            (
                TROPICAL_ID,
                "Blueprint/BP_Water.uasset",
                "Blueprint",
                "water_system_candidate",
            ),
        ):
            path = roots[pack_id] / relative
            candidates[(pack_id, relative)] = {
                "stable_candidate_id": selection._candidate_id(pack_id, relative),
                "source_bytes": path.stat().st_size,
                "source_sha256": selection.sha256_file(path),
                "expected_asset_kind": asset_kind,
                "proposed_role": role,
            }
        return source_contracts, candidates

    def _contract_patches(
        self,
        source_contracts: dict[str, dict[str, object]],
        candidate_contracts: dict[tuple[str, str], dict[str, object]],
    ):
        return (
            patch.object(
                selection, "SOURCE_IDENTITY_CONTRACTS", source_contracts
            ),
            patch.object(selection, "CANDIDATE_CONTRACTS", candidate_contracts),
        )

    def test_exact_request_is_valid_and_all_authority_remains_disabled(self):
        request = _request()
        validate_request(request)
        self.assertTrue(request["no_category_fallback"])
        self.assertFalse(request["authority"]["approval_enabled"])
        self.assertTrue(
            all(value is False for value in request["review_gates"].values())
        )

    def test_manifest_is_deterministic_and_follows_only_serialized_references(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            roots = self._roots(root)
            extra = roots[DESERT_ID] / "Model/Tree/SM_Unselected.uasset"
            extra.write_bytes(b"unselected")
            source_contracts, candidate_contracts = self._fixture_contracts(roots)
            source_patch, candidate_patch = self._contract_patches(
                source_contracts, candidate_contracts
            )
            with source_patch, candidate_patch:
                request = _request()
                manifest_a = build_manifest(
                    request,
                    request_sha256="A" * 64,
                    roots_by_pack=roots,
                )
                manifest_b = build_manifest(
                    copy.deepcopy(request),
                    request_sha256="A" * 64,
                    roots_by_pack=roots,
                )
            self.assertEqual(
                canonical_json_bytes(manifest_a), canonical_json_bytes(manifest_b)
            )
            closure_paths = {
                record["relative_source_path"]
                for record in manifest_a["offline_serialized_reference_closure"]
            }
            self.assertIn("Material/MI_A.uasset", closure_paths)
            self.assertIn("Material/MI_Water.uasset", closure_paths)
            self.assertNotIn("Model/Tree/SM_Unselected.uasset", closure_paths)
            self.assertEqual(manifest_a["summary"]["selected_primary_count"], 2)
            self.assertEqual(
                manifest_a["summary"]["offline_reference_closure_count"], 4
            )
            self.assertFalse(manifest_a["summary"]["selection_ready"])
            self.assertFalse(manifest_a["summary"]["nwiro_ready"])

    def test_tampered_authority_rights_and_category_fallback_fail_closed(self):
        for mutate in (
            lambda value: value["authority"].update({"approval_enabled": True}),
            lambda value: value["authority"].update(
                {"reviewer_public_keys": ["self-issued"]}
            ),
            lambda value: value["review_gates"].update(
                {"rights_and_noai_boundary_reviewed": True}
            ),
            lambda value: value.update({"no_category_fallback": False}),
            lambda value: value["packs"][0].update({"allows_usage_with_ai": True}),
        ):
            request = _request()
            mutate(request)
            with self.assertRaises(CrosspackSelectionError):
                validate_request(request)

    def test_duplicate_missing_and_traversal_candidates_fail_closed(self):
        request = _request()
        request["candidates"].append(copy.deepcopy(request["candidates"][0]))
        with self.assertRaises(CrosspackSelectionError):
            validate_request(request)

        request = _request()
        request["candidates"][0]["relative_source_path"] = "../Escape.uasset"
        with self.assertRaises(CrosspackSelectionError):
            validate_request(request)

        with tempfile.TemporaryDirectory() as temporary:
            roots = self._roots(Path(temporary))
            source_contracts, candidate_contracts = self._fixture_contracts(roots)
            (roots[DESERT_ID] / "Model/Tree/SM_A.uasset").unlink()
            source_patch, candidate_patch = self._contract_patches(
                source_contracts, candidate_contracts
            )
            with source_patch, candidate_patch:
                with self.assertRaises(CrosspackSelectionError):
                    build_manifest(
                        _request(),
                        request_sha256="B" * 64,
                        roots_by_pack=roots,
                    )

    def test_unresolved_internal_package_reference_fails_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            roots = self._roots(Path(temporary))
            (roots[DESERT_ID] / "Model/Tree/SM_A.uasset").write_bytes(
                b"/Game/Zenscape_Savanna/Material/MI_Missing"
            )
            source_contracts, candidate_contracts = self._fixture_contracts(roots)
            source_patch, candidate_patch = self._contract_patches(
                source_contracts, candidate_contracts
            )
            with source_patch, candidate_patch:
                with self.assertRaises(CrosspackSelectionError):
                    build_manifest(
                        _request(),
                        request_sha256="C" * 64,
                        roots_by_pack=roots,
                    )

    def test_output_is_diagnostics_bounded_and_no_clobber(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "report.json"
            validate_output_path(output, root)
            digest = write_manifest_no_clobber(
                output, {"schema_version": 1}, root
            )
            self.assertEqual(digest, sha256_bytes(output.read_bytes()))
            with self.assertRaises(CrosspackSelectionError):
                write_manifest_no_clobber(
                    output, {"schema_version": 1}, root
                )
            with self.assertRaises(CrosspackSelectionError):
                validate_output_path(root.parent / "outside.json", root)

    def test_request_reader_rejects_duplicate_keys(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "request.json"
            path.write_text(
                '{"schema_version":1,"schema_version":1}',
                encoding="utf-8",
            )
            with self.assertRaises(CrosspackSelectionError):
                load_request(path)

    def test_wrong_tropical_engine_association_fails_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            roots = self._roots(Path(temporary))
            source_contracts, candidate_contracts = self._fixture_contracts(roots)
            descriptor = (
                roots[TROPICAL_ID].parent.parent / "TropicalProject.uproject"
            )
            descriptor.write_text(
                json.dumps({"FileVersion": 3, "EngineAssociation": "5.6"}),
                encoding="utf-8",
            )
            source_patch, candidate_patch = self._contract_patches(
                source_contracts, candidate_contracts
            )
            with source_patch, candidate_patch:
                with self.assertRaises(CrosspackSelectionError):
                    build_manifest(
                        _request(),
                        request_sha256="E" * 64,
                        roots_by_pack=roots,
                    )

    def test_manifest_semantic_hash_authenticates_content_without_itself(self):
        with tempfile.TemporaryDirectory() as temporary:
            roots = self._roots(Path(temporary))
            source_contracts, candidate_contracts = self._fixture_contracts(roots)
            source_patch, candidate_patch = self._contract_patches(
                source_contracts, candidate_contracts
            )
            with source_patch, candidate_patch:
                manifest = build_manifest(
                    _request(),
                    request_sha256="D" * 64,
                    roots_by_pack=roots,
                )
            payload = {
                key: value
                for key, value in manifest.items()
                if key != "semantic_sha256"
            }
            self.assertEqual(
                manifest["semantic_sha256"],
                hashlib.sha256(canonical_json_bytes(payload)).hexdigest().upper(),
            )

    def test_candidate_id_hash_size_and_membership_are_pinned(self):
        for field, value in (
            ("stable_candidate_id", "RED-FAB-ASSET-" + "0" * 24),
            ("source_bytes", 1),
            ("source_sha256", "0" * 64),
            ("proposed_role", "unapproved_role"),
        ):
            request = _request()
            request["candidates"][0][field] = value
            with self.assertRaises(CrosspackSelectionError):
                validate_request(request)

        request = _request()
        request["candidates"].pop()
        with self.assertRaises(CrosspackSelectionError):
            validate_request(request)

    def test_byte_identical_substitute_root_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            parent = Path(temporary)
            roots = self._roots(parent / "source")
            source_contracts, candidate_contracts = self._fixture_contracts(roots)
            substitute = self._roots(parent / "substitute")
            source_patch, candidate_patch = self._contract_patches(
                source_contracts, candidate_contracts
            )
            with source_patch, candidate_patch:
                with self.assertRaises(CrosspackSelectionError):
                    build_manifest(
                        _request(),
                        request_sha256="F" * 64,
                        roots_by_pack=substitute,
                    )

    def test_linked_or_reparse_source_ancestor_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            roots = self._roots(Path(temporary))
            source_contracts, candidate_contracts = self._fixture_contracts(roots)
            blocked_ancestor = roots[DESERT_ID].parent
            original = selection._is_link_or_reparse

            def report_reparse(path: Path) -> bool:
                return path == blocked_ancestor or original(path)

            source_patch, candidate_patch = self._contract_patches(
                source_contracts, candidate_contracts
            )
            with source_patch, candidate_patch, patch.object(
                selection, "_is_link_or_reparse", side_effect=report_reparse
            ):
                with self.assertRaises(CrosspackSelectionError):
                    build_manifest(
                        _request(),
                        request_sha256="1" * 64,
                        roots_by_pack=roots,
                    )

    def test_source_mutation_during_publication_removes_output(self):
        with tempfile.TemporaryDirectory() as temporary:
            parent = Path(temporary)
            roots = self._roots(parent / "source")
            source_contracts, candidate_contracts = self._fixture_contracts(roots)
            diagnostics = parent / "diagnostics"
            output = diagnostics / "manifest.json"
            source_patch, candidate_patch = self._contract_patches(
                source_contracts, candidate_contracts
            )
            with source_patch, candidate_patch:
                manifest = build_manifest(
                    _request(),
                    request_sha256="2" * 64,
                    roots_by_pack=roots,
                )
                original_write = selection.write_manifest_no_clobber

                def mutate_after_write(*args, **kwargs):
                    digest = original_write(*args, **kwargs)
                    (roots[DESERT_ID] / "Material/MI_A.uasset").write_bytes(
                        b"mutated after publication"
                    )
                    return digest

                with patch.object(
                    selection,
                    "write_manifest_no_clobber",
                    side_effect=mutate_after_write,
                ):
                    with self.assertRaises(CrosspackSelectionError):
                        write_authenticated_manifest_no_clobber(
                            output,
                            manifest,
                            roots,
                            diagnostics,
                        )
            self.assertFalse(output.exists())

    def test_descriptor_mutation_before_publication_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            parent = Path(temporary)
            roots = self._roots(parent / "source")
            source_contracts, candidate_contracts = self._fixture_contracts(roots)
            source_patch, candidate_patch = self._contract_patches(
                source_contracts, candidate_contracts
            )
            with source_patch, candidate_patch:
                manifest = build_manifest(
                    _request(),
                    request_sha256="3" * 64,
                    roots_by_pack=roots,
                )
                descriptor = (
                    roots[TROPICAL_ID].parent.parent
                    / "TropicalProject.uproject"
                )
                descriptor.write_text(
                    json.dumps({"FileVersion": 3, "EngineAssociation": "5.4"})
                    + " ",
                    encoding="utf-8",
                )
                with self.assertRaises(CrosspackSelectionError):
                    write_authenticated_manifest_no_clobber(
                        parent / "diagnostics" / "manifest.json",
                        manifest,
                        roots,
                        parent / "diagnostics",
                    )


if __name__ == "__main__":
    unittest.main()
