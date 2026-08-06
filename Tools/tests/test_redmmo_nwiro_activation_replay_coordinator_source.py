from __future__ import annotations

import hashlib
import re
import unittest
from pathlib import Path


PROJECT_ROOT = Path(r"D:\RedMMOTitan")
SUT_PATH = (
    PROJECT_ROOT
    / "Tools"
    / "redmmo_nwiro_activation_replay_coordinator.cs"
)
EXPECTED_SOURCE_BYTES = 59_206
EXPECTED_SOURCE_SHA256 = (
    "5D0EF2DAB3F32EFE86E76F2D1350B19DBCE440CBDD9197CB535E83E7D03CA3DF"
)


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest().upper()


def _method_body(source: str, signature: str) -> str:
    start = source.index(signature)
    opening = source.index("{", start)
    depth = 0
    for index in range(opening, len(source)):
        token = source[index]
        if token == "{":
            depth += 1
        elif token == "}":
            depth -= 1
            if depth == 0:
                return source[opening + 1 : index]
    raise AssertionError(f"unclosed method body for {signature}")


class DirectCoordinatorReviewSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.payload = SUT_PATH.read_bytes()
        cls.source = cls.payload.decode("utf-8")

    def test_source_is_exact_reviewed_input(self) -> None:
        self.assertEqual(len(self.payload), EXPECTED_SOURCE_BYTES)
        self.assertEqual(_sha256(self.payload), EXPECTED_SOURCE_SHA256)
        self.assertIn("REVIEW SOURCE ONLY", self.source)
        self.assertIn(
            "never execute this source by project pathname",
            self.source,
        )
        self.assertIn(
            "This revision deliberately stops with NotImplementedException",
            self.source,
        )

    def test_public_entry_is_fixed_byte_arrays_only(self) -> None:
        outer_public_methods = re.findall(
            r"^        public static (?:void|[A-Z][A-Za-z0-9_<>,\[\]]*) "
            r"([A-Za-z0-9_]+)\s*\(",
            self.source,
            flags=re.MULTILINE,
        )
        self.assertEqual(outer_public_methods, ["PublishOnly"])
        self.assertRegex(
            self.source,
            r"public static void PublishOnly\(\s*"
            r"byte\[\] preauthenticatedAuthorizationBytes,\s*"
            r"byte\[\] preauthenticatedRuntimeManifestBytes\s*\)",
        )
        publish_body = _method_body(
            self.source,
            "public static void PublishOnly(",
        )
        self.assertNotRegex(
            publish_body,
            r"\b(string|Action|Delegate|Type|Assembly|Stream)\b",
        )
        self.assertIn('public const string ApprovedMode = "--publish";', self.source)

    def test_exact_stage_two_and_runtime_pins_are_literal(self) -> None:
        expected_facts = (
            (
                "launcher",
                "run_redmmo_nwiro_activation_replay_sealed.py",
                "30222",
                "D27FED1D4D917D616316AA35746BCC9951C821C34BD24A0477A7095E1A5E72DA",
            ),
            (
                "bootstrap_authorization",
                "redmmo_nwiro_activation_replay_bootstrap_execution_authorization_v1.json",
                "2987",
                "70E38DF14A052ED797B8260EE7F7C4156F077D9C1F43A641E1216B9A7027E56C",
            ),
            (
                "contract",
                "validate_redmmo_nwiro_restricted_probe_candidate_contract.py",
                "53011",
                "A829BC5E131BA7812E1F003F2BEA3E684D6DCA2D7CFEFAFC5048502BCBBE3B02",
            ),
            (
                "creator",
                "create_redmmo_nwiro_restricted_probe_candidate.py",
                "77039",
                "28BCF5F28CB94C136355536D9E1386E21895BA597F857CC2E892E6CB336AC47E",
            ),
            (
                "publisher",
                "create_redmmo_nwiro_activation_replay.py",
                "73579",
                "C4D718666C602CB981C4603A8D621FD34BAFBEF64E93E2D48773C6921AB6D1BA",
            ),
            (
                "publisher_test",
                "test_create_redmmo_nwiro_activation_replay.py",
                "9971",
                "8C563D619937D4EF993B9A40AFCA780DC1BC93819A5E321BBB147150F102BDF9",
            ),
            (
                "replay_authorization",
                "redmmo_nwiro_activation_replay_execution_authorization_v1.json",
                "7699",
                "E72E8426A1F9DD35326F3259B359C6460BD584B9F0B889AFE142D0942074410A",
            ),
            (
                "python_executable",
                "python.exe",
                "91648",
                "AE7E969410D751D010C2CA03394FE5C53230FBF48CA7D368B897E455ECA14FBA",
            ),
            (
                "python_dll",
                "python311.dll",
                "5842944",
                "E1B53C741751563ECA9EAC70378DE5BE36994ADAC8C27E8EC375971579E23B50",
            ),
        )
        for role, filename, byte_count, digest in expected_facts:
            with self.subTest(role=role):
                self.assertIn(f'"{role}"', self.source)
                self.assertIn(filename, self.source)
                self.assertRegex(self.source, rf"\b{byte_count}\b")
                self.assertIn(digest, self.source)
        self.assertIn(
            "A6CBE97F22C8AB928059FFF83F7887D5819B2AF45E1FE9494BA34AD6EA4E215A",
            self.source,
        )
        self.assertIn("private const int RuntimeManifestBytes = 622905;", self.source)

    def test_publish_preflight_order_ends_in_mandatory_refusal(self) -> None:
        body = _method_body(self.source, "public static void PublishOnly(")
        ordered = (
            "ValidateCoordinatorAuthorizationEnvelope(authorization)",
            "ValidateRuntimeManifestEnvelope(runtimeManifest)",
            "CreateExclusiveProtectedMutex()",
            "VerifySystem32Host()",
            "RejectPersistentTargetState()",
            "LockedInput.Open(StageTwoGraph[index])",
            "LockedInput.Open(RuntimePins[index])",
            "VerifyStageTwoAuthorizationBinding(retained)",
            "VerifyAllRetainedInputs(retained)",
            "RefuseBeforeFirstPersistentMutation()",
        )
        positions = [body.index(token) for token in ordered]
        self.assertEqual(positions, sorted(positions))
        self.assertEqual(
            len(
                re.findall(
                    r"\bRefuseBeforeFirstPersistentMutation\(\);",
                    self.source,
                )
            ),
            1,
        )
        refusal = _method_body(
            self.source,
            "private static void RefuseBeforeFirstPersistentMutation()",
        )
        self.assertIn("throw new NotImplementedException(", refusal)
        self.assertIn("REVIEW_ONLY_NOT_IMPLEMENTED_BEFORE_MUTATION", refusal)

    def test_current_revision_has_no_persistent_mutation_or_launch_calls(self) -> None:
        forbidden_calls = (
            "Directory.CreateDirectory(",
            "Directory.Delete(",
            "Directory.Move(",
            "File.Create(",
            "File.Delete(",
            "File.Move(",
            "File.OpenWrite(",
            "File.WriteAllBytes(",
            "File.WriteAllText(",
            "Process.Start(",
            "NativeMethods.MoveFileEx(",
            "NativeMethods.CreateProcess(",
            "NativeMethods.CreateJobObject(",
            "NativeMethods.SetInformationJobObject(",
            "NativeMethods.AssignProcessToJobObject(",
            "NativeMethods.ResumeThread(",
            "NativeMethods.TerminateProcess(",
            "NativeMethods.FlushFileBuffers(",
        )
        for call in forbidden_calls:
            with self.subTest(call=call):
                self.assertNotIn(call, self.source)
        for network_marker in (
            "System.Net",
            "HttpClient",
            "WebRequest",
            "Socket",
            "TcpClient",
            "UdpClient",
        ):
            self.assertNotIn(network_marker, self.source)

    def test_retained_inputs_are_read_only_and_reverified(self) -> None:
        self.assertIn("private const uint FileShareRead = 0x00000001U;", self.source)
        self.assertNotIn("FileShareWrite", self.source)
        self.assertNotIn("FileShareDelete", self.source)
        self.assertRegex(
            self.source,
            r"NativeMethods\.CreateFile\(\s*fullPath,\s*GenericRead,\s*"
            r"FileShareRead,",
        )
        self.assertIn("FileFlagOpenReparsePoint", self.source)
        self.assertIn("RejectReparseChain(", self.source)
        self.assertIn("RejectNamedStreams(fullPath);", self.source)
        self.assertIn("openedIdentity.LinkCount != 1", self.source)
        self.assertIn("member.ExpectedSha256", self.source)
        self.assertIn("public void VerifyUnchanged()", self.source)
        self.assertIn("FixedTimeBytesEqual(initialBytes, observed)", self.source)

    def test_authority_is_single_mode_and_explicitly_non_operational(self) -> None:
        for marker in (
            '"network_authorized":false',
            '"unreal_launch_authorized":false',
            '"asset_or_map_mutation_authorized":false',
            '"build_authorized":false',
            '"codex_config_mutation_authorized":false',
        ):
            escaped = marker.replace('"', '\\"')
            self.assertIn(escaped, self.source)
        self.assertIn('text.IndexOf("\\"allowed_modes\\""', self.source)
        self.assertIn('text.IndexOf("--verify"', self.source)
        self.assertIn('text.IndexOf("--run-replay"', self.source)
        self.assertIn(
            "This is not a\n"
            "                 * claim of a full runtime lock",
            self.source,
        )
        self.assertIn("all 4,206 files plus all 366", self.source)

    def test_fixed_targets_mutex_and_cleanup_are_bound(self) -> None:
        self.assertIn(
            r'@"Local\RedMMO.NwiroActivationReplayCoordinator.Publish.V1"',
            self.source,
        )
        self.assertIn(
            r'@"D:\RedMMOTitanWindowsData\Staging\NwiroActivationReplayBootstrapV1"',
            self.source,
        )
        self.assertIn(
            r'@"D:\RedMMOTitanWindowsData\Staging\NwiroRestrictedProbeActivationReplayV1"',
            self.source,
        )
        self.assertIn("RejectPersistentTargetState();", self.source)
        self.assertIn("DisposeReverse(retained);", self.source)
        self.assertIn("mutex.ReleaseMutex();", self.source)
        self.assertIn("Array.Clear(authorization, 0, authorization.Length);", self.source)
        self.assertIn("Array.Clear(runtimeManifest, 0, runtimeManifest.Length);", self.source)


if __name__ == "__main__":
    unittest.main()
