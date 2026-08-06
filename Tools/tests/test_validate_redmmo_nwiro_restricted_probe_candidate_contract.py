from __future__ import annotations

import ast
import copy
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from Tools.validate_redmmo_nwiro_restricted_probe_candidate_contract import (
    DEFAULT_CONTRACT,
    EXPECTED_CONTRACT_SHA256,
    CandidateContractError,
    _hash_stable_regular_file,
    _read_stable_regular_file,
    _validate_existing_ancestor_chain,
    authenticate_plugin_tree_two_pass,
    build_plugin_tree_manifests,
    load_json_bytes_strict,
    runtime_authorized,
    validate_contract_file,
    validate_contract_schema,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
PLUGIN_ROOT = Path(
    "D:/UE_5.8/Engine/Plugins/Marketplace/NWIROAIIf0b7fbfe049eV4"
)
CANDIDATE_ROOT = Path(
    "D:/RedMMOTitanWindowsData/Staging/NwiroRestrictedProbeForkCandidateV1"
)
TEST_TEMP_ROOT = Path("D:/RedMMOTitanWindowsData/UserTemp")


def _canonical_contract() -> dict[str, object]:
    return load_json_bytes_strict(
        DEFAULT_CONTRACT.read_bytes(), "canonical candidate contract"
    )


def _tree_metadata(root: Path) -> dict[str, tuple[int, int]]:
    return {
        path.relative_to(root).as_posix(): (
            path.stat(follow_symlinks=False).st_size,
            path.stat(follow_symlinks=False).st_mtime_ns,
        )
        for path in root.rglob("*")
        if path.is_file() and not path.is_symlink()
    }


class NwiroRestrictedProbeCandidateContractTests(unittest.TestCase):
    def test_canonical_contract_authenticates_complete_and_fork_input_trees(self):
        report = validate_contract_file()
        self.assertEqual(
            report["status"],
            "candidate_contract_only_source_absent_runtime_forbidden",
        )
        self.assertEqual(report["evidence_class"], "static")
        self.assertEqual(report["installed_tree_inventory"]["file_count"], 106)
        self.assertEqual(
            report["installed_tree_inventory"]["directory_count_excluding_root"],
            29,
        )
        self.assertEqual(
            report["installed_tree_inventory"]["record_set_sha256"],
            "DF5067FAEB002FCC10F52D212AB9C8133973D28070EB4D5C969A4205F0A833F0",
        )
        self.assertEqual(report["fork_input_tree"]["file_count"], 90)
        self.assertEqual(report["fork_input_tree"]["source_file_count"], 87)
        self.assertEqual(
            report["fork_input_tree"]["record_set_sha256"],
            "F1D91F85B8D7BE403D3AEFAA3348CE65B4CDC6EC52F1627CB141339C39FD1D4A",
        )
        self.assertFalse(report["candidate_static_accepted"])
        self.assertFalse(report["runtime_authorized"])
        self.assertTrue(report["candidate_root_absent"])
        self.assertEqual(report["complete_observation_passes"], 2)
        self.assertFalse(report["whole_tree_snapshot_stability_proven"])
        self.assertFalse(report["concurrent_mutation_resistance_proven"])

    def test_embedded_contract_hash_is_exact_and_nonplaceholder(self):
        actual = hashlib.sha256(DEFAULT_CONTRACT.read_bytes()).hexdigest().upper()
        self.assertEqual(actual, EXPECTED_CONTRACT_SHA256)
        self.assertNotEqual(EXPECTED_CONTRACT_SHA256, "0" * 64)

    def test_contract_schema_rejects_unknown_key_and_runtime_authority(self):
        contract = _canonical_contract()
        validate_contract_schema(contract)

        with_unknown = copy.deepcopy(contract)
        with_unknown["unexpected"] = False
        with self.assertRaises(CandidateContractError):
            validate_contract_schema(with_unknown)

        runtime_enabled = copy.deepcopy(contract)
        runtime_enabled["execution"]["runtime_authorized"] = True
        with self.assertRaises(CandidateContractError):
            validate_contract_schema(runtime_enabled)

        false_snapshot_claim = copy.deepcopy(contract)
        false_snapshot_claim["baseline"]["installed_tree_inventory"][
            "whole_tree_snapshot_stability_proven"
        ] = True
        with self.assertRaises(CandidateContractError):
            validate_contract_schema(false_snapshot_claim)

    def test_contract_schema_rejects_candidate_acceptance_and_creation(self):
        contract = _canonical_contract()
        for section, key in (
            ("execution", "candidate_creation_authorized"),
            ("candidate", "candidate_source_present"),
            ("candidate", "candidate_static_accepted"),
            ("candidate", "candidate_runtime_accepted"),
            ("acceptance_gates", "candidate_source_manifest_authenticated"),
        ):
            mutated = copy.deepcopy(contract)
            mutated[section][key] = True
            with self.subTest(section=section, key=key):
                with self.assertRaises(CandidateContractError):
                    validate_contract_schema(mutated)

    def test_contract_schema_rejects_lineage_or_allowlist_broadening(self):
        contract = _canonical_contract()

        binary_lineage = copy.deepcopy(contract)
        binary_lineage["baseline"]["fork_input_tree"][
            "vendor_binaries_allowed_in_candidate_lineage"
        ] = True
        with self.assertRaises(CandidateContractError):
            validate_contract_schema(binary_lineage)

        missing_third_party = copy.deepcopy(contract)
        missing_third_party["baseline"]["fork_input_tree"][
            "included_directories"
        ].pop()
        with self.assertRaises(CandidateContractError):
            validate_contract_schema(missing_third_party)

        broader_change = copy.deepcopy(contract)
        broader_change["allowed_change_surface"][
            "baseline_files_allowed_to_change_in_candidate"
        ].append("Private/Anything.cpp")
        with self.assertRaises(CandidateContractError):
            validate_contract_schema(broader_change)

    def test_contract_schema_rejects_control_or_probe_relaxation(self):
        contract = _canonical_contract()

        accepted_control = copy.deepcopy(contract)
        accepted_control["required_controls"][0]["accepted"] = True
        with self.assertRaises(CandidateContractError):
            validate_contract_schema(accepted_control)

        broader_query = copy.deepcopy(contract)
        broader_query["probe_contract"]["arguments"]["path"] = "/Game"
        with self.assertRaises(CandidateContractError):
            validate_contract_schema(broader_query)

        ai_usage = copy.deepcopy(contract)
        ai_usage["probe_contract"]["all_source_packs_allow_usage_with_ai"] = True
        with self.assertRaises(CandidateContractError):
            validate_contract_schema(ai_usage)

    def test_strict_json_rejects_duplicates_nonfinite_and_nonobjects(self):
        with self.assertRaises(CandidateContractError):
            load_json_bytes_strict(b'{"a":1,"a":2}', "duplicate")
        with self.assertRaises(CandidateContractError):
            load_json_bytes_strict(b'{"a":NaN}', "nan")
        with self.assertRaises(CandidateContractError):
            load_json_bytes_strict(b"[]", "array")

    def test_live_manifest_is_deterministic_and_excludes_generated_lineage(self):
        first = build_plugin_tree_manifests(PLUGIN_ROOT)
        second = build_plugin_tree_manifests(PLUGIN_ROOT)
        self.assertEqual(first, second)
        self.assertEqual(first["installed_tree_inventory"]["file_count"], 106)
        self.assertEqual(first["fork_input_tree"]["file_count"], 90)
        self.assertEqual(
            first["installed_tree_inventory"]["top_level_file_counts"][
                "Binaries"
            ],
            5,
        )
        self.assertEqual(
            first["installed_tree_inventory"]["top_level_file_counts"][
                "Intermediate"
            ],
            11,
        )
        self.assertNotIn(
            "Binaries", first["fork_input_tree"]["included_directories"]
        )
        self.assertNotIn(
            "Intermediate", first["fork_input_tree"]["included_directories"]
        )

    def test_stable_file_hash_rejects_hardlinks(self):
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as td:
            root = Path(td)
            original = root / "original.txt"
            linked = root / "linked.txt"
            original.write_bytes(b"review-only")
            os.link(original, linked)
            with self.assertRaises(CandidateContractError):
                _hash_stable_regular_file(original)

    def test_stable_file_hash_rejects_named_alternate_streams(self):
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as td:
            original = Path(td) / "streamed.txt"
            original.write_bytes(b"review-only")
            Path(f"{original}:unexpected").write_bytes(b"hidden")
            with self.assertRaises(CandidateContractError):
                _hash_stable_regular_file(original)

    def test_contract_style_reader_rejects_named_alternate_streams(self):
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as td:
            original = Path(td) / "contract.json"
            original.write_bytes(b'{"schema_version":1}')
            Path(f"{original}:unexpected").write_bytes(b"hidden")
            with self.assertRaises(CandidateContractError):
                _read_stable_regular_file(original)

    def test_contract_style_reader_authenticates_existing_ancestor_chain(self):
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as td:
            original = Path(td) / "contract.json"
            original.write_bytes(b'{"schema_version":1}')
            with patch(
                "Tools.validate_redmmo_nwiro_restricted_probe_candidate_contract."
                "_validate_existing_ancestor_chain",
                wraps=_validate_existing_ancestor_chain,
            ) as ancestor_check:
                self.assertEqual(
                    _read_stable_regular_file(original),
                    b'{"schema_version":1}',
                )
            ancestor_check.assert_called_once_with(original.parent)

    def test_tree_rejects_directory_alternate_streams(self):
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as td:
            root = Path(td)
            (root / "Source").mkdir()
            (root / "Source/minimal.cpp").write_bytes(b"int minimal;\n")
            Path(f"{root}:unexpected").write_bytes(b"hidden")
            with self.assertRaises(CandidateContractError):
                build_plugin_tree_manifests(root)

    def test_tree_rejects_symlink_when_host_allows_fixture(self):
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as td:
            root = Path(td)
            target = root / "target.txt"
            link = root / "linked.txt"
            target.write_bytes(b"target")
            try:
                os.symlink(target, link)
            except OSError as error:
                self.skipTest(f"symlink fixture unavailable: {error}")
            with self.assertRaises(CandidateContractError):
                build_plugin_tree_manifests(root)

    def test_two_pass_authentication_rejects_post_hash_content_change(self):
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as td:
            root = Path(td)
            earlier = root / "b.txt"
            later = root / "a.txt"
            earlier.write_bytes(b"before")
            later.write_bytes(b"stable")
            original_hash = _hash_stable_regular_file
            mutated = False

            def mutate_after_earlier_hash(
                path: Path, max_bytes: int = 160 * 1024 * 1024
            ) -> tuple[int, str]:
                nonlocal mutated
                if path.name == "a.txt" and not mutated:
                    earlier.write_bytes(b"after!")
                    mutated = True
                return original_hash(path, max_bytes)

            with patch(
                "Tools.validate_redmmo_nwiro_restricted_probe_candidate_contract."
                "_hash_stable_regular_file",
                side_effect=mutate_after_earlier_hash,
            ):
                with self.assertRaisesRegex(
                    CandidateContractError,
                    "between consecutive complete observations",
                ):
                    authenticate_plugin_tree_two_pass(root)

    def test_only_canonical_contract_path_is_accepted(self):
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as td:
            copy_path = Path(td) / DEFAULT_CONTRACT.name
            copy_path.write_bytes(DEFAULT_CONTRACT.read_bytes())
            with self.assertRaises(CandidateContractError):
                validate_contract_file(copy_path)

    def test_offline_module_imports_no_transport_or_process_modules(self):
        source_path = (
            PROJECT_ROOT
            / "Tools/validate_redmmo_nwiro_restricted_probe_candidate_contract.py"
        )
        tree = ast.parse(source_path.read_text(encoding="utf-8"))
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".", 1)[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".", 1)[0])
        self.assertTrue(
            imported.isdisjoint(
                {
                    "socket",
                    "requests",
                    "urllib",
                    "http",
                    "httpx",
                    "subprocess",
                }
            )
        )

    def test_cli_is_read_only_and_reports_no_runtime_authority(self):
        script = (
            PROJECT_ROOT
            / "Tools/validate_redmmo_nwiro_restricted_probe_candidate_contract.py"
        )
        before_plugin = _tree_metadata(PLUGIN_ROOT)
        before_contract = (
            DEFAULT_CONTRACT.stat().st_size,
            DEFAULT_CONTRACT.stat().st_mtime_ns,
        )
        self.assertFalse(CANDIDATE_ROOT.exists())

        result = subprocess.run(
            [sys.executable, "-B", str(script)],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertFalse(report["runtime_authorized"])
        self.assertFalse(report["candidate_static_accepted"])
        self.assertEqual(_tree_metadata(PLUGIN_ROOT), before_plugin)
        self.assertEqual(
            (
                DEFAULT_CONTRACT.stat().st_size,
                DEFAULT_CONTRACT.stat().st_mtime_ns,
            ),
            before_contract,
        )
        self.assertFalse(CANDIDATE_ROOT.exists())

    def test_runtime_authority_function_is_permanently_false(self):
        self.assertFalse(runtime_authorized())


if __name__ == "__main__":
    unittest.main()
