import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
PLAN_PATH = ROOT / "docs" / "M07_DISPOSABLE_VOLUME_RECOVERY_HARNESS_PLAN.json"
DESIGN_PATH = ROOT / "docs" / "M07_DISPOSABLE_VOLUME_RECOVERY_HARNESS.md"


class M07DisposableVolumeRecoveryPlanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.plan = json.loads(PLAN_PATH.read_text(encoding="utf-8"))
        cls.design = DESIGN_PATH.read_text(encoding="utf-8")

    def test_plan_is_static_dry_run_source_only(self) -> None:
        self.assertEqual(self.plan["module_id"], "M07")
        self.assertEqual(self.plan["evidence_class"], "static")
        self.assertEqual(
            self.plan["status"],
            "dry_run_source_implemented_not_executed",
        )
        self.assertTrue(self.plan["requires_separate_execution_authorization"])
        self.assertFalse(self.plan["subject"]["live_project_payload_allowed"])
        self.assertFalse(self.plan["subject"]["restore_scan_allowed"])
        self.assertIn("dry-run source implemented", self.design)
        self.assertIn("Worker execution remains", self.design)

    def test_paths_are_d_bounded_no_clobber_and_fail_closed(self) -> None:
        paths = self.plan["paths"]
        self.assertTrue(paths["case_root_template"].startswith(
            "D:/RedMMOTitanWindowsData/DisposableRecoveryHarness/"
        ))
        self.assertTrue(paths["ledger_root_template"].startswith(
            "D:/RedMMOTitanWindowsData/DisposableRecoveryHarnessLedger/"
        ))
        self.assertIn("D:/RedMMOTitan", paths["denied_write_roots"])
        self.assertIn("C:/Users/user", paths["denied_write_roots"])
        self.assertFalse(paths["network_namespaces_allowed"])
        self.assertFalse(paths["reparse_points_allowed"])
        self.assertFalse(paths["drive_letter_mount_allowed"])
        self.assertTrue(paths["require_previously_absent_run_and_case_paths"])
        self.assertIn(
            "case roots, report names, ledgers, and outputs are no-clobber and single-use",
            {guard["rule"] for guard in self.plan["safety_guards"]},
        )

    def test_privileged_provisioning_is_separate_from_worker(self) -> None:
        split = self.plan["privilege_split"]
        self.assertEqual(split["controller"], "unelevated")
        self.assertEqual(split["worker"], "unelevated_direct_child")
        self.assertFalse(split["worker_may_elevate"])
        self.assertFalse(split["automatic_elevation_allowed"])
        self.assertFalse(split["worker_may_manage_disks"])
        self.assertFalse(split["controller_may_manage_disks"])
        phases = {phase["id"]: phase for phase in self.plan["implementation_phases"]}
        self.assertEqual(
            phases["P1"]["status"],
            "source_implemented_static_verified_not_executed",
        )
        self.assertEqual(phases["P2"]["status"], "future_separate_authorization")

    def test_vhdx_contract_uses_exact_handle_identity_not_disk_number(self) -> None:
        contract = self.plan["vhdx_contract"]
        self.assertEqual(contract["format"], "VHDX")
        self.assertEqual(contract["allocation"], "fixed")
        self.assertTrue(contract["one_fresh_standalone_image_per_case"])
        self.assertFalse(contract["differencing_chain_allowed"])
        self.assertIn(
            "ATTACH_VIRTUAL_DISK_FLAG_NO_DRIVE_LETTER",
            contract["attach_flags_required"],
        )
        self.assertFalse(contract["permanent_lifetime_allowed"])
        self.assertTrue(contract["retain_creating_handle_through_case"])
        self.assertEqual(
            self.plan["identity_chain"],
            [
                "run_id",
                "canonical_image_path",
                "virtual_disk_id",
                "physical_device_path_from_creating_handle",
                "disk_unique_id",
                "partition_guid",
                "volume_guid",
                "canonical_mount_path",
                "ntfs_volume_serial",
            ],
        )
        self.assertIn(
            "destructive provisioning authority is the complete creating-handle identity chain, never a disk number alone",
            {guard["rule"] for guard in self.plan["safety_guards"]},
        )

    def test_checkpoint_matrix_is_complete_and_ordered(self) -> None:
        expected = [
            "before_temp_create",
            "after_temp_create",
            "mid_payload_write",
            "after_payload_write_before_preflush",
            "after_preflush_before_rename",
            "after_rename_before_postflush",
            "after_postflush_before_final_validation",
            "after_final_validation_before_return",
            "after_return_before_complete_ack",
            "after_complete_ack_before_clean_exit",
            "normal_success",
        ]
        self.assertEqual(
            self.plan["checkpoint_protocol"]["ordered_checkpoints"],
            expected,
        )
        self.assertEqual(
            [case["checkpoint"] for case in self.plan["case_matrix"]],
            expected,
        )
        self.assertTrue(self.plan["checkpoint_protocol"]["nonce_bound"])
        self.assertFalse(
            self.plan["checkpoint_protocol"]["public_cli_worker_mode_allowed"]
        )

    def test_exact_final_without_ack_and_clean_exit_is_not_committed(self) -> None:
        cases = {
            case["checkpoint"]: case for case in self.plan["case_matrix"]
        }
        for checkpoint in (
            "after_rename_before_postflush",
            "after_postflush_before_final_validation",
            "after_final_validation_before_return",
            "after_return_before_complete_ack",
            "after_complete_ack_before_clean_exit",
        ):
            self.assertEqual(cases[checkpoint]["expected_final"], "exact")
            self.assertEqual(
                cases[checkpoint]["classification"],
                "interrupted_valid_final_uncommitted",
            )
        self.assertTrue(
            self.plan["committed_predicate"][
                "final_file_presence_alone_is_never_committed"
            ]
        )
        required = self.plan["committed_predicate"]["all_required"]
        self.assertIn("authenticated_complete_ack", required)
        self.assertIn("clean_worker_exit_code_zero", required)
        self.assertIn("fresh_process_scan_exact_final", required)

    def test_corruption_ambiguity_and_cleanup_fail_closed(self) -> None:
        failures = set(self.plan["global_fail_conditions"])
        self.assertIn("corrupt_or_partial_final", failures)
        self.assertIn("final_and_staging_both_present", failures)
        self.assertIn("unexpected_namespace_entry", failures)
        self.assertIn("write_outside_allowlist", failures)
        self.assertIn("cleanup_targets_unrecorded_identity", failures)
        cleanup = self.plan["cleanup"]
        self.assertFalse(cleanup["automatic_cleanup_allowed"])
        self.assertFalse(cleanup["broad_recursive_delete_allowed"])
        self.assertTrue(cleanup["exact_detach_handle_required"])
        self.assertTrue(cleanup["verify_not_attached_before_explicit_delete"])
        self.assertTrue(
            self.plan["recovery"]["preserve_on_corruption_or_identity_mismatch"]
        )

    def test_process_vm_and_physical_claims_remain_separate(self) -> None:
        tiers = {tier["id"]: tier for tier in self.plan["acceptance_tiers"]}
        self.assertEqual(tiers["T0"]["claim"], "static_contract_only")
        self.assertEqual(
            tiers["T1"]["claim"], "process_interruption_recovery_only"
        )
        self.assertEqual(
            tiers["T2"]["claim"], "virtualized_abrupt_interruption_only"
        )
        self.assertTrue(tiers["T2"]["requires_separate_authorization"])
        self.assertTrue(tiers["T3"]["requires_separate_authorization"])
        limits = " ".join(self.plan["claim_limits"]).lower()
        self.assertIn("process termination does not simulate", limits)
        self.assertIn("normal detach and clean remount", limits)
        self.assertIn("physical storage durability", limits)
        self.assertIn("hardware caches", limits)

    def test_all_platform_references_are_primary_microsoft_sources(self) -> None:
        sources = self.plan["primary_sources"]
        self.assertGreaterEqual(len(sources), 8)
        for source in sources:
            self.assertTrue(
                source.startswith("https://learn.microsoft.com/"),
                source,
            )


if __name__ == "__main__":
    unittest.main()
