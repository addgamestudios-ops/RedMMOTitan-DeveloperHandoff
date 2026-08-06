import ast
import copy
import ctypes
import hashlib
import json
from contextlib import contextmanager
from pathlib import Path
import stat
import unittest
from unittest.mock import patch

from Tools import verify_redmmo_content_storage_restore as publisher
from Tools import verify_redmmo_report_publication_recovery as recovery


ROOT = Path(__file__).resolve().parents[2]
PLAN_PATH = ROOT / "docs" / "M07_DISPOSABLE_VOLUME_RECOVERY_HARNESS_PLAN.json"
SOURCE_PATH = ROOT / "Tools" / "verify_redmmo_report_publication_recovery.py"
RUN_ID = "123e4567-e89b-42d3-a456-426614174000"
VIRTUAL_DISK_ID = "123e4567-e89b-42d3-a456-426614174001"
PARTITION_GUID = "123e4567-e89b-42d3-a456-426614174002"
RUN_NONCE = "A" * 64
CASE_NONCE = "B" * 64
SENTINEL_NONCE = "C" * 64
SENTINEL_SHA = "D" * 64


def _plan() -> dict[str, object]:
    return json.loads(PLAN_PATH.read_text(encoding="utf-8"))


def _ledger_value(value: str) -> dict[str, object]:
    return {"value": value, "verification": "ledger_only"}


def _contract(case_id: str) -> dict[str, object]:
    mount_root = (
        "D:/RedMMOTitanWindowsData/DisposableRecoveryHarness/"
        f"{RUN_ID}/mount/{case_id}"
    )
    return {
        "schema_version": 1,
        "contract_id": recovery.VOLUME_CONTRACT_ID,
        "status": recovery.VOLUME_CONTRACT_STATUS,
        "run_id": RUN_ID,
        "case_id": case_id,
        "run_nonce": RUN_NONCE,
        "case_nonce": CASE_NONCE,
        "dry_run_worker_pid": 4242,
        "actual_volume_observed": False,
        "ready_for_execution": False,
        "filesystem": "NTFS",
        "volume_label": recovery.VOLUME_LABEL,
        "capacity_bytes": 240 * 1024 * 1024,
        "mount_root": mount_root,
        "ledger_root": (
            "D:/RedMMOTitanWindowsData/DisposableRecoveryHarnessLedger/"
            f"{RUN_ID}"
        ),
        "terminal_mount_point_policy": (
            "future_probe_may_accept_exact_authenticated_terminal_mount_point_only"
        ),
        "identity_chain": {
            "canonical_image_path": _ledger_value(
                "D:/RedMMOTitanWindowsData/DisposableRecoveryHarness/"
                f"{RUN_ID}/images/{case_id}.vhdx"
            ),
            "virtual_disk_id": _ledger_value(VIRTUAL_DISK_ID),
            "physical_device_path": _ledger_value(r"\\.\PhysicalDrive42"),
            "disk_unique_id": _ledger_value(
                "A1B2C3D4E5F60718293A4B5C6D7E8F90"
            ),
            "partition_guid": _ledger_value(PARTITION_GUID),
            "volume_guid": _ledger_value(
                r"\\?\Volume{123e4567-e89b-42d3-a456-426614174003}\\"
                [:-1]
            ),
            "canonical_mount_path": _ledger_value(mount_root),
            "ntfs_volume_serial": _ledger_value("0123456789ABCDEF"),
        },
        "sentinel": {
            "relative_path": recovery.SAFE_SENTINEL_NAME,
            "nonce": SENTINEL_NONCE,
            "sha256": SENTINEL_SHA,
            "verification": "ledger_only",
        },
        "requested_actions": [],
        "claim_limit": [
            "descriptor_validation_only",
            "no_actual_volume",
            "no_process_termination",
            "no_power_loss",
            "no_physical_media_claim",
        ],
    }


def _observation(
    case_id: str,
    *,
    plan: dict[str, object] | None = None,
) -> dict[str, object]:
    plan_value = plan or _plan()
    case = next(
        row for row in plan_value["case_matrix"]
        if row["checkpoint"] == case_id
    )
    if case_id == "normal_success":
        complete_ack = True
        clean_exit = True
        exit_code = 0
    elif case_id == "after_complete_ack_before_clean_exit":
        complete_ack = True
        clean_exit = False
        exit_code = -9
    else:
        complete_ack = False
        clean_exit = False
        exit_code = -9
    result = {
        "schema_version": 1,
        "run_id": RUN_ID,
        "case_id": case_id,
        "worker_pid": 4242,
        "run_nonce": RUN_NONCE,
        "case_nonce": CASE_NONCE,
        "armed_checkpoint": case_id,
        "acknowledged_checkpoint": case_id,
        "final_state": case["expected_final"],
        "staging_state": case["expected_staging"],
        "complete_ack": complete_ack,
        "clean_exit": clean_exit,
        "exit_code": exit_code,
        "native_identity_continuity": True,
        "unexpected_namespace_entries": 0,
        "outside_writes": 0,
        "auth_hmac_sha256": "0" * 64,
    }
    result["auth_hmac_sha256"] = recovery.observation_hmac(result)
    return result


class _FakeKernel:
    def __init__(self) -> None:
        self.blocks: list[bytes] = []

    def WriteFile(
        self,
        _handle: int,
        storage: object,
        length: int,
        written: object,
        _overlapped: object,
    ) -> bool:
        self.blocks.append(ctypes.string_at(storage, length))
        written._obj.value = length
        return True


class _FakeNtdll:
    def NtSetInformationFile(self, *_args: object) -> int:
        return 0


class ReportPublicationRecoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.plan = _plan()

    def test_plan_and_authenticated_json_contract(self) -> None:
        payload = PLAN_PATH.read_bytes()
        digest = hashlib.sha256(payload).hexdigest().upper()
        parsed = recovery.parse_authenticated_json(
            payload,
            digest,
            "recovery plan",
        )
        self.assertEqual(recovery.validate_plan(parsed)["plan_id"], recovery.PLAN_ID)
        with self.assertRaisesRegex(recovery.RecoveryHarnessError, "SHA-256 mismatch"):
            recovery.parse_authenticated_json(payload, "0" * 64, "recovery plan")
        duplicate = b'{"schema_version":1,"schema_version":1}'
        with self.assertRaisesRegex(recovery.RecoveryHarnessError, "duplicate"):
            recovery.parse_authenticated_json(
                duplicate,
                hashlib.sha256(duplicate).hexdigest().upper(),
                "duplicate fixture",
            )

    def test_valid_descriptor_remains_unattested_and_not_ready(self) -> None:
        contract = _contract("before_temp_create")
        observed = recovery.validate_volume_contract(contract, self.plan)
        self.assertFalse(observed["actual_volume_observed"])
        self.assertFalse(observed["ready_for_execution"])
        self.assertEqual(observed["requested_actions"], [])

    def test_descriptor_rejects_actual_claim_actions_and_type_confusion(self) -> None:
        for mutate, pattern in (
            (
                lambda value: value.__setitem__("actual_volume_observed", True),
                "cannot claim an actual volume",
            ),
            (
                lambda value: value.__setitem__("ready_for_execution", True),
                "cannot be ready",
            ),
            (
                lambda value: value.__setitem__(
                    "requested_actions", ["Format-Volume"]
                ),
                "cannot request actions",
            ),
            (
                lambda value: value.__setitem__("capacity_bytes", True),
                "must be an integer",
            ),
        ):
            with self.subTest(pattern=pattern):
                contract = _contract("before_temp_create")
                mutate(contract)
                with self.assertRaisesRegex(recovery.RecoveryHarnessError, pattern):
                    recovery.validate_volume_contract(contract, self.plan)

    def test_descriptor_rejects_path_escape_network_and_identity_drift(self) -> None:
        fixtures = (
            ("mount_root", "C:/Users/user/escape", "canonical"),
            ("mount_root", "D:/RedMMOTitan/escape", "differs"),
            ("mount_root", "//server/share/escape", "canonical"),
        )
        for key, value, pattern in fixtures:
            with self.subTest(value=value):
                contract = _contract("before_temp_create")
                contract[key] = value
                with self.assertRaisesRegex(recovery.RecoveryHarnessError, pattern):
                    recovery.validate_volume_contract(contract, self.plan)

        contract = _contract("before_temp_create")
        contract["identity_chain"]["canonical_mount_path"]["value"] = (
            "D:/different"
        )
        with self.assertRaisesRegex(recovery.RecoveryHarnessError, "mount path"):
            recovery.validate_volume_contract(contract, self.plan)

        contract = _contract("before_temp_create")
        contract["identity_chain"]["volume_guid"]["verification"] = "verified"
        with self.assertRaisesRegex(recovery.RecoveryHarnessError, "ledger_only"):
            recovery.validate_volume_contract(contract, self.plan)

    def test_all_checkpoint_cases_classify_without_execution(self) -> None:
        expected = {
            row["checkpoint"]: row["classification"]
            for row in self.plan["case_matrix"]
        }
        for checkpoint in recovery.EXPECTED_PLAN_CHECKPOINTS:
            with self.subTest(checkpoint=checkpoint):
                classification = recovery.classify_dry_run_observation(
                    _observation(checkpoint, plan=self.plan),
                    _contract(checkpoint),
                    self.plan,
                )
                self.assertEqual(classification, expected[checkpoint])

    def test_exact_final_needs_both_complete_ack_and_clean_exit(self) -> None:
        checkpoint = "after_return_before_complete_ack"
        observation = _observation(checkpoint, plan=self.plan)
        self.assertEqual(
            recovery.classify_dry_run_observation(
                observation,
                _contract(checkpoint),
                self.plan,
            ),
            "interrupted_valid_final_uncommitted",
        )

        checkpoint = "after_complete_ack_before_clean_exit"
        observation = _observation(checkpoint, plan=self.plan)
        self.assertEqual(
            recovery.classify_dry_run_observation(
                observation,
                _contract(checkpoint),
                self.plan,
            ),
            "interrupted_valid_final_uncommitted",
        )

        checkpoint = "normal_success"
        observation = _observation(checkpoint, plan=self.plan)
        observation["clean_exit"] = False
        observation["exit_code"] = -9
        observation["auth_hmac_sha256"] = recovery.observation_hmac(observation)
        self.assertEqual(
            recovery.classify_dry_run_observation(
                observation,
                _contract(checkpoint),
                self.plan,
            ),
            "interrupted_valid_final_uncommitted",
        )

    def test_nonce_pid_and_hmac_mismatch_fail_closed(self) -> None:
        checkpoint = "before_temp_create"
        for field, value, pattern in (
            ("run_nonce", "E" * 64, "run_nonce differs"),
            ("case_nonce", "F" * 64, "case_nonce differs"),
            ("worker_pid", 4444, "worker PID differs"),
        ):
            with self.subTest(field=field):
                observation = _observation(checkpoint, plan=self.plan)
                observation[field] = value
                observation["auth_hmac_sha256"] = recovery.observation_hmac(
                    observation
                )
                with self.assertRaisesRegex(
                    recovery.RecoveryHarnessError,
                    pattern,
                ):
                    recovery.classify_dry_run_observation(
                        observation,
                        _contract(checkpoint),
                        self.plan,
                    )

        observation = _observation(checkpoint, plan=self.plan)
        observation["auth_hmac_sha256"] = "F" * 64
        with self.assertRaisesRegex(recovery.RecoveryHarnessError, "HMAC"):
            recovery.classify_dry_run_observation(
                observation,
                _contract(checkpoint),
                self.plan,
            )

    def test_corrupt_ambiguous_or_outside_write_state_fails_closed(self) -> None:
        checkpoint = "after_rename_before_postflush"
        mutations = (
            ("final_state", "partial"),
            ("staging_state", "unexpected"),
            ("native_identity_continuity", False),
            ("unexpected_namespace_entries", 1),
            ("outside_writes", 1),
        )
        for field, value in mutations:
            with self.subTest(field=field):
                observation = _observation(checkpoint, plan=self.plan)
                observation[field] = value
                observation["auth_hmac_sha256"] = recovery.observation_hmac(
                    observation
                )
                self.assertEqual(
                    recovery.classify_dry_run_observation(
                        observation,
                        _contract(checkpoint),
                        self.plan,
                    ),
                    "failed_unsafe_state",
                )

    def test_report_is_deterministic_and_all_live_evidence_is_false(self) -> None:
        checkpoint = "normal_success"
        first = recovery.build_dry_run_report(
            self.plan,
            _contract(checkpoint),
            _observation(checkpoint, plan=self.plan),
        )
        second = recovery.build_dry_run_report(
            copy.deepcopy(self.plan),
            copy.deepcopy(_contract(checkpoint)),
            copy.deepcopy(_observation(checkpoint, plan=self.plan)),
        )
        self.assertEqual(
            recovery.serialize_report(first),
            recovery.serialize_report(second),
        )
        self.assertEqual(first["state"], recovery.DRY_RUN_STATE)
        self.assertFalse(first["ready_for_execution"])
        self.assertFalse(first["actual_volume_observed"])
        self.assertTrue(
            all(value is False for value in first["evidence_booleans"].values())
        )
        self.assertIn("complete_outside_write_trace_is_unavailable",
                      first["execution_blockers"])

    def test_private_worker_refuses_before_write_or_transport(self) -> None:
        sent: list[dict[str, object]] = []
        with patch.object(publisher, "write_report_atomic") as write:
            with self.assertRaisesRegex(
                recovery.RecoveryHarnessError,
                "execution is disabled",
            ):
                recovery._publication_worker_once(
                    case_root=Path("D:/synthetic"),
                    payload=b"{}\n",
                    armed_checkpoint="normal_success",
                    run_id=RUN_ID,
                    case_id="normal_success",
                    run_nonce=RUN_NONCE,
                    case_nonce=CASE_NONCE,
                    worker_pid=4242,
                    send=sent.append,
                )
        write.assert_not_called()
        self.assertEqual(sent, [])

    def test_cli_and_source_have_no_disk_process_power_or_mutating_surface(self) -> None:
        help_text = recovery._parser().format_help().casefold()
        for option in (
            "--create",
            "--attach",
            "--mount",
            "--format",
            "--detach",
            "--delete",
            "--kill",
            "--power",
            "--output",
            "--worker",
        ):
            self.assertNotIn(option, help_text)

        tree = ast.parse(SOURCE_PATH.read_text(encoding="utf-8"))
        imports = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.Import, ast.ImportFrom))
            for alias in node.names
        }
        self.assertNotIn("subprocess", imports)
        self.assertNotIn("ctypes", imports)
        self.assertNotIn("shutil", imports)
        forbidden_calls = {
            "system",
            "run",
            "Popen",
            "call",
            "mkdir",
            "write_bytes",
            "write_text",
            "unlink",
            "rmdir",
            "rename",
            "rmtree",
            "remove",
            "kill",
            "terminate",
            "CreateVirtualDisk",
            "OpenVirtualDisk",
            "AttachVirtualDisk",
            "DetachVirtualDisk",
            "SetVolumeMountPointW",
            "DeleteVolumeMountPointW",
            "TerminateProcess",
            "ExitWindowsEx",
        }
        observed_calls = {
            node.func.attr
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
        } | {
            node.func.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
        }
        self.assertEqual(forbidden_calls & observed_calls, set())

    def test_private_context_is_process_local_reset_and_scalar_only(self) -> None:
        events: list[publisher.PublicationCheckpointEvent] = []
        publisher._emit_publication_checkpoint("before_temp_create")
        self.assertEqual(events, [])
        with publisher._publication_checkpoint_scope(
            events.append,
            armed_checkpoint="before_temp_create",
        ):
            publisher._emit_publication_checkpoint(
                "before_temp_create",
                candidate_name="candidate.tmp",
                payload_size=3,
            )
            publisher._emit_publication_checkpoint("after_temp_create")
        publisher._emit_publication_checkpoint("before_temp_create")
        self.assertEqual(
            events,
            [
                publisher.PublicationCheckpointEvent(
                    name="before_temp_create",
                    candidate_name="candidate.tmp",
                    payload_size=3,
                )
            ],
        )

    def test_write_helper_splits_only_when_midpoint_is_armed(self) -> None:
        events: list[publisher.PublicationCheckpointEvent] = []
        kernel = _FakeKernel()
        with patch.object(
            publisher,
            "_windows_apis",
            return_value=(kernel, object()),
        ), patch.object(publisher, "_windows_flush_handle") as flush:
            with publisher._publication_checkpoint_scope(
                events.append,
                armed_checkpoint=None,
            ):
                publisher._windows_write_and_flush(99, b"ABCD")
        self.assertEqual(kernel.blocks, [b"AB", b"CD"])
        self.assertEqual(
            [event.name for event in events],
            [
                "mid_payload_write",
                "after_payload_write_before_preflush",
            ],
        )
        flush.assert_called_once_with(
            99,
            "report temporary file before publication",
        )

        kernel = _FakeKernel()
        with patch.object(
            publisher,
            "_windows_apis",
            return_value=(kernel, object()),
        ), patch.object(publisher, "_windows_flush_handle"):
            publisher._windows_write_and_flush(99, b"ABCD")
        self.assertEqual(kernel.blocks, [b"ABCD"])

    def test_rename_checkpoint_precedes_postrename_flush(self) -> None:
        events: list[publisher.PublicationCheckpointEvent] = []
        order: list[str] = []
        fake_ntdll = _FakeNtdll()

        def flush(_handle: int, _label: str) -> None:
            order.append("flush")

        def observe(event: publisher.PublicationCheckpointEvent) -> None:
            events.append(event)
            order.append(event.name)

        with patch.object(
            publisher,
            "_windows_apis",
            return_value=(object(), fake_ntdll),
        ), patch.object(
            publisher,
            "_windows_flush_handle",
            side_effect=flush,
        ), publisher._publication_checkpoint_scope(
            observe,
            armed_checkpoint="after_rename_before_postflush",
        ):
            publisher._windows_publish_open_file_no_clobber(
                10,
                20,
                "report.json",
            )
        self.assertEqual(
            order,
            ["after_rename_before_postflush", "flush"],
        )

    def test_full_publication_checkpoint_order_uses_one_algorithm(self) -> None:
        output = Path("D:/synthetic/case/restore_report.json")
        parent_identity = publisher.WindowsHandleMetadata(
            attributes=publisher.WINDOWS_FILE_ATTRIBUTE_DIRECTORY,
            volume_serial=101,
            file_id=202,
            identity_volume_serial=303,
            file_id_128=bytes.fromhex("01" * 16),
            size=0,
            link_count=1,
        )
        opened = publisher.WindowsHandleMetadata(
            attributes=publisher.WINDOWS_FILE_ATTRIBUTE_NORMAL,
            volume_serial=101,
            file_id=404,
            identity_volume_serial=303,
            file_id_128=bytes.fromhex("02" * 16),
            size=0,
            link_count=1,
        )
        written = publisher.WindowsHandleMetadata(
            attributes=publisher.WINDOWS_FILE_ATTRIBUTE_NORMAL,
            volume_serial=101,
            file_id=404,
            identity_volume_serial=303,
            file_id_128=bytes.fromhex("02" * 16),
            size=3,
            link_count=1,
        )
        parent_metadata = publisher.FileMetadata(
            size=0,
            mtime_ns=1,
            ctime_ns=1,
            device=101,
            inode=202,
            mode=stat.S_IFDIR,
            attributes=0,
            link_count=1,
        )
        published_metadata = publisher.FileMetadata(
            size=3,
            mtime_ns=1,
            ctime_ns=1,
            device=101,
            inode=404,
            mode=stat.S_IFREG,
            attributes=0,
            link_count=1,
        )

        @contextmanager
        def pinned(*_args: object, **_kwargs: object):
            yield 20, parent_identity

        def write_and_flush(_handle: int, payload: bytes) -> None:
            publisher._emit_publication_checkpoint(
                "after_payload_write_before_preflush",
                payload_size=len(payload),
                bytes_written=len(payload),
            )

        def publish(*_args: object, **_kwargs: object) -> None:
            publisher._emit_publication_checkpoint(
                "after_rename_before_postflush"
            )

        def metadata(path: Path) -> publisher.FileMetadata:
            return (
                parent_metadata
                if path == output.parent
                else published_metadata
            )

        events: list[publisher.PublicationCheckpointEvent] = []
        with patch.object(
            publisher,
            "_windows_pinned_output_parent",
            side_effect=pinned,
        ), patch.object(
            publisher,
            "_windows_nt_create_relative",
            return_value=(10, 2),
        ), patch.object(
            publisher,
            "_windows_handle_metadata",
            side_effect=(opened, written),
        ), patch.object(
            publisher,
            "_windows_write_and_flush",
            side_effect=write_and_flush,
        ), patch.object(
            publisher,
            "_windows_publish_open_file_no_clobber",
            side_effect=publish,
        ), patch.object(
            publisher,
            "_metadata",
            side_effect=metadata,
        ), patch.object(
            publisher,
            "_windows_close_handle",
        ), publisher._publication_checkpoint_scope(
            events.append,
            armed_checkpoint=None,
        ):
            publisher._write_report_atomic_windows(
                output,
                b"{}\n",
                Path("D:/synthetic"),
            )
        self.assertEqual(
            [event.name for event in events],
            [
                "before_temp_create",
                "after_temp_create",
                "after_payload_write_before_preflush",
                "after_preflush_before_rename",
                "after_rename_before_postflush",
                "after_postflush_before_final_validation",
                "after_final_validation_before_return",
            ],
        )


if __name__ == "__main__":
    unittest.main()
