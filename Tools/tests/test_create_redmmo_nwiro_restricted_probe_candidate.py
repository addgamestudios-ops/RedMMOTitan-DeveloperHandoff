import copy
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


PROJECT_ROOT = Path(r"D:\RedMMOTitan")
MODULE_PATH = (
    PROJECT_ROOT
    / "Tools"
    / "create_redmmo_nwiro_restricted_probe_candidate.py"
)
TOOLS_ROOT = PROJECT_ROOT / "Tools"
if str(TOOLS_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOLS_ROOT))
SPEC = importlib.util.spec_from_file_location("nwiro_candidate_creator", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
creator = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = creator
SPEC.loader.exec_module(creator)


def make_snapshot(root: str = "D:/Example") -> creator.TreeSnapshot:
    directories = (
        {
            "path": "Source",
            "attributes_hex": "00000010",
            "volume_serial_hex": "0000000000000001",
            "file_id_128_hex": "01" * 16,
            "alternate_streams": [],
        },
    )
    files = (
        {
            "path": "NwiroIntegrationKit.uplugin",
            "bytes": 3,
            "sha256": creator._sha256_bytes(b"abc"),
            "attributes_hex": "00000020",
            "volume_serial_hex": "0000000000000001",
            "file_id_128_hex": "02" * 16,
            "hard_link_count": 1,
            "alternate_streams": [],
        },
    )
    return creator.TreeSnapshot(
        root=root,
        directories=directories,
        files=files,
        file_count=1,
        directory_count_excluding_root=1,
        total_bytes=3,
        record_set_sha256=creator._record_digest(files),
        topology_sha256=creator._topology_digest(directories, files),
    )


class CandidateCreatorContractTests(unittest.TestCase):
    def test_cli_has_no_caller_supplied_path_surface(self):
        with self.assertRaises(SystemExit):
            creator._parse_args(["--create", "--candidate-root", "D:/Elsewhere"])

    def test_fixed_candidate_is_outside_unreal_discovery(self):
        creator._require_fixed_layout()
        candidate = creator._path_text(creator.CANDIDATE_ROOT).casefold()
        self.assertFalse(
            candidate.startswith(
                creator._path_text(creator.PROJECT_ROOT / "Plugins")
                .casefold()
                .rstrip("/")
                + "/"
            )
        )
        self.assertFalse(
            candidate.startswith("d:/ue_5.8/engine/plugins/")
        )

    def test_exact_copy_ignores_identity_but_not_bytes(self):
        baseline = make_snapshot("D:/Baseline")
        candidate = make_snapshot("D:/Candidate")
        changed_identity = copy.deepcopy(candidate.semantic_payload())
        changed_identity["files"][0]["file_id_128_hex"] = "03" * 16
        candidate = creator.TreeSnapshot(
            root="D:/Candidate",
            directories=candidate.directories,
            files=tuple(changed_identity["files"]),
            file_count=candidate.file_count,
            directory_count_excluding_root=candidate.directory_count_excluding_root,
            total_bytes=candidate.total_bytes,
            record_set_sha256=candidate.record_set_sha256,
            topology_sha256=candidate.topology_sha256,
        )
        creator._require_byte_exact_copy(baseline, candidate)
        changed_bytes = list(candidate.files)
        changed_bytes[0] = dict(changed_bytes[0])
        changed_bytes[0]["sha256"] = "A" * 64
        bad = creator.TreeSnapshot(
            root="D:/Candidate",
            directories=candidate.directories,
            files=tuple(changed_bytes),
            file_count=1,
            directory_count_excluding_root=1,
            total_bytes=3,
            record_set_sha256="A" * 64,
            topology_sha256="B" * 64,
        )
        with self.assertRaises(creator.CandidateCreationError):
            creator._require_byte_exact_copy(baseline, bad)

    def test_delta_is_complete_exact_copy_and_keeps_authority_false(self):
        baseline = make_snapshot("D:/Baseline")
        candidate = make_snapshot("D:/Candidate")
        delta = creator._build_exact_delta(
            captured_utc="2026-07-25T00:00:00Z",
            baseline=baseline,
            candidate=candidate,
            baseline_manifest_sha256="A" * 64,
            candidate_manifest_sha256="B" * 64,
            baseline_manifest_semantic_sha256="C" * 64,
            candidate_manifest_semantic_sha256="D" * 64,
            baseline_manifest_bytes=101,
            candidate_manifest_bytes=102,
            execution_authorization_hash="E" * 64,
        )
        self.assertEqual(delta["classification_counts"]["copied_exact"], 1)
        self.assertEqual(
            delta["classification_counts"]["unchanged_directories"], 1
        )
        self.assertEqual(delta["unchanged_directories"], [{"path": "Source"}])
        self.assertEqual(delta["modified"], [])
        self.assertFalse(delta["source_default_off"])
        self.assertFalse(delta["restricted_mode_implemented"])
        self.assertFalse(delta["runtime_authorized"])
        self.assertFalse(delta["candidate_static_accepted"])
        self.assertTrue(delta["inert_only_by_external_location_and_no_binary"])
        self.assertTrue(delta["outside_two_checked_automatic_plugin_roots"])
        self.assertFalse(
            delta["universal_plugin_discovery_exclusion_proven"]
        )
        for key in (
            "build_authorized",
            "install_authorized",
            "unreal_launch_authorized",
            "mcp_initialize_authorized",
            "mcp_tool_call_authorized",
            "network_authorized",
            "provider_call_authorized",
        ):
            self.assertFalse(delta[key])
        self.assertEqual(
            delta["execution_authorization"]["sha256"], "E" * 64
        )

    def test_manifest_semantic_hash_detects_claim_mutation(self):
        snapshot = make_snapshot()
        manifest = creator._manifest_object(
            manifest_id="nwiro-restricted-probe-baseline-fork-input-v1",
            role="baseline_fork_input",
            captured_utc="2026-07-25T00:00:00Z",
            snapshot=snapshot,
            contract_hash=creator.CONTRACT_SHA256,
            execution_authorization_hash="C" * 64,
            project_descriptor_hash="A" * 64,
            creator_hash="B" * 64,
        )
        expected = creator._sha256_bytes(
            creator.canonical_json_bytes(
                creator._manifest_semantic_payload(manifest)
            )
        )
        self.assertEqual(manifest["manifest_semantic_sha256"], expected)
        mutated = copy.deepcopy(manifest)
        mutated["runtime_authorized"] = True
        with self.assertRaises(creator.CandidateCreationError):
            creator._validate_manifest_shape(
                mutated,
                manifest_id="nwiro-restricted-probe-baseline-fork-input-v1",
                role="baseline_fork_input",
                root=Path("D:/Example"),
                snapshot=snapshot,
                project_descriptor_hash="A" * 64,
                execution_authorization_hash="C" * 64,
            )

    def test_manifest_shape_rejects_unknown_key(self):
        snapshot = make_snapshot()
        manifest = creator._manifest_object(
            manifest_id="nwiro-restricted-probe-baseline-fork-input-v1",
            role="baseline_fork_input",
            captured_utc="2026-07-25T00:00:00Z",
            snapshot=snapshot,
            contract_hash=creator.CONTRACT_SHA256,
            execution_authorization_hash="C" * 64,
            project_descriptor_hash="A" * 64,
            creator_hash="B" * 64,
        )
        manifest["unknown"] = False
        with self.assertRaises(creator.CandidateCreationError):
            creator._validate_manifest_shape(
                manifest,
                manifest_id="nwiro-restricted-probe-baseline-fork-input-v1",
                role="baseline_fork_input",
                root=Path("D:/Example"),
                snapshot=snapshot,
                project_descriptor_hash="A" * 64,
                execution_authorization_hash="C" * 64,
            )

    def test_manifest_canonical_file_has_exactly_one_final_lf(self):
        payload = creator._canonical_file_bytes({"z": 1, "a": 2})
        self.assertTrue(payload.endswith(b"\n"))
        self.assertFalse(payload.endswith(b"\n\n"))
        self.assertEqual(payload.count(b"\n"), 1)
        self.assertEqual(json.loads(payload), {"a": 2, "z": 1})

    def test_manifest_shape_rejects_timestamp_and_claim_tamper(self):
        snapshot = make_snapshot()
        manifest = creator._manifest_object(
            manifest_id="nwiro-restricted-probe-baseline-fork-input-v1",
            role="baseline_fork_input",
            captured_utc="2026-07-25T00:00:00Z",
            snapshot=snapshot,
            contract_hash=creator.CONTRACT_SHA256,
            execution_authorization_hash="C" * 64,
            project_descriptor_hash="A" * 64,
            creator_hash="B" * 64,
        )
        for key, changed in (
            ("captured_utc", "2026-07-25 00:00:00"),
            ("claim_limit", "broader than reviewed"),
        ):
            mutated = copy.deepcopy(manifest)
            mutated[key] = changed
            creator._attach_manifest_semantic_hash(mutated)
            with self.assertRaises(creator.CandidateCreationError):
                creator._validate_manifest_shape(
                    mutated,
                    manifest_id=(
                        "nwiro-restricted-probe-baseline-fork-input-v1"
                    ),
                    role="baseline_fork_input",
                    root=Path("D:/Example"),
                    snapshot=snapshot,
                    project_descriptor_hash="A" * 64,
                    execution_authorization_hash="C" * 64,
                )

    def test_reserved_namespace_rejects_orphan_transaction_and_extra_manifest(self):
        diagnostics = Path(r"D:\RedMMOTitanWindowsData\Diagnostics")
        diagnostics.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(
            prefix="NwiroCandidateNamespace_", dir=diagnostics
        ) as temporary:
            staging = Path(temporary)
            with mock.patch.object(creator, "STAGING_PARENT", staging):
                creator._require_reserved_namespace(set())
                orphan = staging / (
                    ".NwiroRestrictedProbeForkCandidateV1.txn.orphan"
                )
                orphan.mkdir()
                with self.assertRaises(creator.CandidateCreationError):
                    creator._require_reserved_namespace(set())
                orphan.rmdir()
                extra = staging / (
                    "NwiroRestrictedProbeForkCandidateV1.extra.v1.json"
                )
                extra.write_bytes(b"{}\n")
                with self.assertRaises(creator.CandidateCreationError):
                    creator._require_reserved_namespace(set())

    def test_execution_authorization_expected_denies_expansive_authority(self):
        diagnostics = Path(r"D:\RedMMOTitanWindowsData\Diagnostics")
        diagnostics.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(
            prefix="NwiroCandidateAuth_", dir=diagnostics
        ) as temporary:
            protected = Path(temporary) / "protected.bin"
            protected.write_bytes(b"protected")
            value = creator._execution_authorization_expected(
                authorized_utc="2026-07-25T00:00:00Z",
                creator_hash="A" * 64,
                creator_bytes=1,
                creator_test_hash="B" * 64,
                creator_test_bytes=2,
                project_descriptor_hash="C" * 64,
                project_descriptor_bytes=3,
                protected_inputs={
                    protected.resolve(strict=True).as_posix(): "D" * 64
                },
            )
        self.assertTrue(
            value["execution"]["candidate_creation_authorized"]
        )
        self.assertTrue(
            value["execution"]["manifest_publication_authorized"]
        )
        for key, allowed in value["execution"].items():
            if key not in {
                "candidate_creation_authorized",
                "manifest_publication_authorized",
                "staging_parent_creation_authorized",
                "private_transaction_authorized",
                "rollback_reservation_authorized",
                "source_read_and_hash_authorized",
                "diagnostic_stdout_authorized",
            }:
                self.assertFalse(allowed, key)
        self.assertFalse(value["facts"]["source_default_off"])
        self.assertFalse(
            value["facts"]["universal_plugin_discovery_exclusion_proven"]
        )

    def test_private_acl_probe_for_directory_and_file(self):
        diagnostics = Path(r"D:\RedMMOTitanWindowsData\Diagnostics")
        diagnostics.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(
            prefix="NwiroCandidateAcl_", dir=diagnostics
        ) as temporary:
            private_root = Path(temporary) / "private"
            private_root.mkdir()
            creator._apply_private_directory_acl(private_root)
            creator._require_exact_private_acl(private_root)
            private_file = private_root / "manifest.json"
            private_file.write_bytes(b"{}\n")
            creator._apply_private_file_acl(private_file)
            creator._require_exact_private_acl(private_file)

    def test_quarantine_moves_only_authenticated_current_run_paths(self):
        diagnostics = Path(r"D:\RedMMOTitanWindowsData\Diagnostics")
        diagnostics.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(
            prefix="NwiroCandidateQuarantine_", dir=diagnostics
        ) as temporary:
            root = Path(temporary)
            staging = root / "Staging"
            rollback = root / "Rollback"
            staging.mkdir()
            rollback.mkdir()
            quarantine = rollback / "FixedReservation"
            nonce = "a" * 32
            transaction = staging / (
                f".NwiroRestrictedProbeForkCandidateV1.txn.{nonce}"
            )
            transaction.mkdir()
            (transaction / "remainder.txt").write_bytes(b"remainder")
            published_file = (
                staging
                / "NwiroRestrictedProbeForkCandidateV1.baseline.v1.json"
            )
            published_file.write_bytes(b"{}\n")
            with mock.patch.multiple(
                creator,
                STAGING_PARENT=staging,
                ROLLBACK_PARENT=rollback,
                QUARANTINE_ROOT=quarantine,
            ):
                rollback_identity, quarantine_identity = (
                    creator._create_quarantine_reservation()
                )
                transaction_identity = creator._windows_identity(
                    transaction, is_directory=True
                )
                published_identity = creator._windows_identity(
                    published_file, is_directory=False
                )
                observed = creator._quarantine_failed_publication(
                    transaction_root=transaction,
                    transaction_identity=transaction_identity,
                    nonce=nonce,
                    published=[
                        (published_file, published_identity, False)
                    ],
                    rollback_parent_identity=rollback_identity,
                    quarantine_identity=quarantine_identity,
                )
            self.assertEqual(observed, quarantine)
            self.assertFalse(published_file.exists())
            self.assertTrue((quarantine / published_file.name).is_file())
            self.assertTrue(
                (quarantine / "transaction_remainder").is_dir()
            )

    def test_no_clobber_move_refuses_existing_destination(self):
        diagnostics = Path(r"D:\RedMMOTitanWindowsData\Diagnostics")
        diagnostics.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(
            prefix="NwiroCandidateNoClobber_", dir=diagnostics
        ) as temporary:
            root = Path(temporary)
            source = root / "source.txt"
            destination = root / "destination.txt"
            source.write_bytes(b"source")
            destination.write_bytes(b"destination")
            with self.assertRaises(creator.CandidateCreationError):
                creator._move_no_clobber(source, destination)
            self.assertEqual(source.read_bytes(), b"source")
            self.assertEqual(destination.read_bytes(), b"destination")

    def test_verify_mode_does_not_offer_mutation_flags(self):
        parsed = creator._parse_args(["--verify"])
        self.assertTrue(parsed.verify)
        self.assertFalse(parsed.create)


if __name__ == "__main__":
    unittest.main()
