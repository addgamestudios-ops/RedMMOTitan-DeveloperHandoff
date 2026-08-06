"""Offline source contracts for the isolated NWIRO activation/ownership slice.

These tests never load Unreal, bind a socket, initialize MCP, or call a
provider.  They authenticate the historical exact-copy baseline, inspect only
the external candidate source, and exercise a small reference model for the
two controls implemented by this slice.  Passing is static evidence only.
"""

from __future__ import annotations

import hashlib
import json
import re
import unittest
from dataclasses import dataclass
from pathlib import Path

from Tools.audit_nwiro_restricted_probe_source import (
    _extract_function,
    _mask_cpp_noncode,
)


CANDIDATE_ROOT = Path(
    r"D:\RedMMOTitanWindowsData\Staging\NwiroRestrictedProbeForkCandidateV1"
)
BASELINE_MANIFEST = Path(
    r"D:\RedMMOTitanWindowsData\Staging"
    r"\NwiroRestrictedProbeForkCandidateV1.baseline.v1.json"
)
BASELINE_MANIFEST_SHA256 = (
    "AACAC06301F470A270870DD48FF4085CCA44A3370E9CE504592F79D11EA7996A"
)
PROCESS_LOCK_NAME = (
    "RedMMO_NwiroRestrictedMetadataProbe_"
    "redmmo_m07_metadata_readonly_v1"
)
EXPECTED_CHANGED_FILES = {
    "NwiroIntegrationKit.uplugin",
    "Source/NwiroIntegrationKit/Private/NwiroIKMCPServer.cpp",
    "Source/NwiroIntegrationKit/Private/NwiroIKMCPServer.h",
    "Source/NwiroIntegrationKit/Private/NwiroIntegrationKit.cpp",
    "Source/NwiroIntegrationKit/Public/NwiroIK.h",
}
EXPECTED_NORMALIZED_FUNCTION_SHA256 = {
    (
        "Source/NwiroIntegrationKit/Private/NwiroIKMCPServer.cpp",
        "FNwiroIKMCPServer::IsRestrictedMetadataProbeMode",
    ): "7415F71E31E8D34EEF5E53D3C4792F315DD11891171E71A80DE5FFB1CA619DDE",
    (
        "Source/NwiroIntegrationKit/Private/NwiroIKMCPServer.cpp",
        "FNwiroIKMCPServer::IsRestrictedProbeRuntimeReady",
    ): "16F67F95A4AA6BAF72C78047F99BC56B45DFAD2C1718CCFF0F788ACAC91938D7",
    (
        "Source/NwiroIntegrationKit/Private/NwiroIntegrationKit.cpp",
        "FNwiroIKModule::StartupModule",
    ): "14C4F23B201C903BC52CCD21698F7F9CA122777BAFC146227F65D37FCD700452",
    (
        "Source/NwiroIntegrationKit/Private/NwiroIKMCPServer.cpp",
        "FNwiroIKMCPServer::AcquireRestrictedProbeProcessLock",
    ): "60C90A97711A16509FF2E7B76558236B144271344B7A075F753E9D77B117C079",
    (
        "Source/NwiroIntegrationKit/Private/NwiroIKMCPServer.cpp",
        "FNwiroIKMCPServer::ReleaseRestrictedProbeProcessLock",
    ): "44D59547F9DCC1E06865AC93E40F246BD8BBCD449C2582665E5CAD2CCFDF78C5",
    (
        "Source/NwiroIntegrationKit/Private/NwiroIKMCPServer.cpp",
        "FNwiroIKMCPServer::CanAcceptRestrictedProbeTraffic",
    ): "9EFAA68A21BEE2127355BEF916D580A0249C550306E82835AD14B37D3A3A16FF",
    (
        "Source/NwiroIntegrationKit/Private/NwiroIKMCPServer.cpp",
        "FNwiroIKMCPServer::Start",
    ): "74E092F63CA639BAE4CCFA8DEFC7716EDDF59A3DF82656DBFF3179CF0FFE0D99",
    (
        "Source/NwiroIntegrationKit/Private/NwiroIKMCPServer.cpp",
        "FNwiroIKMCPServer::Stop",
    ): "D05B50D6B9E776496DA9F21CE0D6690903DF79EDC93CAA5EB484B3547C4C8DF9",
    (
        "Source/NwiroIntegrationKit/Private/NwiroIKMCPServer.cpp",
        "FNwiroIKMCPServer::Restart",
    ): "9157AAA4A27555B63EF07674864874B0A6F4E22CC347FE76C1A643FF051D2754",
    (
        "Source/NwiroIntegrationKit/Private/NwiroIKMCPServer.cpp",
        "FNwiroIKMCPServer::WriteClaudeConfig",
    ): "2623BC301C49CD269DA2DC915C201CE4E05DAE85F1F6FACE0879EE5551FD67F0",
    (
        "Source/NwiroIntegrationKit/Private/NwiroIKMCPServer.cpp",
        "FNwiroIKMCPServer::HandleMCPPost",
    ): "CE07650399BC3A99B1ED13E4F71BC93EBFB136AB59DF5D5AADA3C2084769A160",
    (
        "Source/NwiroIntegrationKit/Private/NwiroIKMCPServer.cpp",
        "FNwiroIKMCPServer::ProcessJsonRpc",
    ): "3FD0A472DA3469033E337321D1AF7EFA43E31E5DA3631F67E368C8919B66D73F",
    (
        "Source/NwiroIntegrationKit/Private/NwiroIKMCPServer.cpp",
        "FNwiroIKMCPServer::DispatchTool",
    ): "BC6B58580CDEB4AACDD739F3F27CD14DB15B061230051D0C391D7E38ACE7A537",
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def _read(relative: str) -> str:
    return (CANDIDATE_ROOT / relative).read_text(encoding="utf-8")


def _function(relative: str, qualified_name: str) -> str:
    return _mask_cpp_noncode(_extract_function(_read(relative), qualified_name))


def _current_files() -> dict[str, tuple[int, str]]:
    records: dict[str, tuple[int, str]] = {}
    for path in sorted(CANDIDATE_ROOT.rglob("*")):
        if path.is_file():
            relative = path.relative_to(CANDIDATE_ROOT).as_posix()
            records[relative] = (path.stat().st_size, _sha256(path))
    return records


def _baseline_files() -> dict[str, tuple[int, str]]:
    raw = BASELINE_MANIFEST.read_bytes()
    if hashlib.sha256(raw).hexdigest().upper() != BASELINE_MANIFEST_SHA256:
        raise AssertionError("historical baseline manifest hash drift")
    document = json.loads(raw.decode("utf-8"))
    return {
        item["path"]: (item["bytes"], item["sha256"])
        for item in document["tree"]["files"]
    }


@dataclass
class _OwnershipModel:
    owner_pid: int = 0

    def acquire(self, pid: int, *, private_test_authority: bool = False) -> bool:
        if not private_test_authority:
            return False
        if pid <= 0 or self.owner_pid != 0:
            return False
        self.owner_pid = pid
        return True

    def release(self, pid: int) -> bool:
        if pid <= 0 or pid != self.owner_pid:
            return False
        self.owner_pid = 0
        return True


class NwiroActivationOwnershipSourceTests(unittest.TestCase):
    def test_reviewed_control_flow_functions_match_exact_normalized_revision(
        self,
    ) -> None:
        for (relative, name), expected in (
            EXPECTED_NORMALIZED_FUNCTION_SHA256.items()
        ):
            normalized = re.sub(
                r"\s+",
                " ",
                _function(relative, name),
            ).strip()
            observed = hashlib.sha256(
                normalized.encode("utf-8")
            ).hexdigest().upper()
            self.assertEqual(expected, observed, name)

    def test_both_activation_authority_functions_are_literal_false_only(
        self,
    ) -> None:
        relative = "Source/NwiroIntegrationKit/Private/NwiroIKMCPServer.cpp"
        for name in (
            "FNwiroIKMCPServer::IsRestrictedMetadataProbeMode",
            "FNwiroIKMCPServer::IsRestrictedProbeRuntimeReady",
        ):
            body = _function(relative, name)
            block = body[body.index("{") :]
            statements = [
                statement.strip()
                for statement in block.strip("{} \t\r\n").split(";")
                if statement.strip()
            ]
            self.assertEqual(["return false"], statements, name)

    def test_historical_baseline_and_current_delta_are_exactly_bounded(self) -> None:
        baseline = _baseline_files()
        current = _current_files()
        self.assertEqual(set(baseline), set(current))
        changed = {
            path
            for path in baseline
            if baseline[path] != current[path]
        }
        self.assertEqual(EXPECTED_CHANGED_FILES, changed)
        self.assertFalse(
            any(
                part.lower() in {"binaries", "intermediate"}
                for path in current
                for part in Path(path).parts
            )
        )

    def test_descriptor_is_explicitly_default_off(self) -> None:
        descriptor = json.loads(_read("NwiroIntegrationKit.uplugin"))
        self.assertIs(descriptor.get("EnabledByDefault"), False)
        self.assertEqual("1.0.9-redmmo-restricted-probe-candidate.1", descriptor["VersionName"])

    def test_production_activation_authority_is_hard_off(self) -> None:
        body = _function(
            "Source/NwiroIntegrationKit/Private/NwiroIKMCPServer.cpp",
            "FNwiroIKMCPServer::IsRestrictedMetadataProbeMode",
        )
        self.assertRegex(body, r"return\s+false\s*;")
        self.assertNotRegex(body, r"return\s+true\s*;")
        self.assertNotIn("FCommandLine", body)
        self.assertNotIn("GetEnvironmentVariable", body)
        self.assertNotIn("LoadConfig", body)
        self.assertNotIn("IConsole", body)

    def test_runtime_readiness_remains_hard_false(self) -> None:
        body = _function(
            "Source/NwiroIntegrationKit/Private/NwiroIKMCPServer.cpp",
            "FNwiroIKMCPServer::IsRestrictedProbeRuntimeReady",
        )
        self.assertRegex(body, r"return\s+false\s*;")
        self.assertNotRegex(body, r"return\s+true\s*;")

    def test_module_checks_activation_and_server_gate_before_ui(self) -> None:
        body = _function(
            "Source/NwiroIntegrationKit/Private/NwiroIntegrationKit.cpp",
            "FNwiroIKModule::StartupModule",
        )
        mode = body.index("IsRestrictedMetadataProbeMode")
        port = body.index("LoadSavedPort")
        start = body.index("FNwiroIKMCPServer::Start")
        running = body.index("FNwiroIKMCPServer::IsRunning")
        style = body.index("FNwiroIKStyle::Initialize")
        self.assertLess(mode, port)
        self.assertLess(port, start)
        self.assertLess(start, running)
        self.assertLess(running, style)

    def test_start_acquires_owner_before_every_listener_side_effect(self) -> None:
        body = _function(
            "Source/NwiroIntegrationKit/Private/NwiroIKMCPServer.cpp",
            "FNwiroIKMCPServer::Start",
        )
        sequence = [
            "IsRestrictedMetadataProbeMode",
            "IsRestrictedProbeRuntimeReady",
            "AcquireRestrictedProbeProcessLock",
            "FHttpServerModule::Get",
            "GetHttpRouter",
            "BindRoute",
            "StartAllListeners",
        ]
        positions = [body.index(item) for item in sequence]
        self.assertEqual(positions, sorted(positions))

    def test_system_wide_mutex_is_fixed_retained_and_nonblocking(self) -> None:
        relative = "Source/NwiroIntegrationKit/Private/NwiroIKMCPServer.cpp"
        raw_body = _extract_function(
            _read(relative),
            "FNwiroIKMCPServer::AcquireRestrictedProbeProcessLock",
        )
        body = _mask_cpp_noncode(raw_body)
        self.assertIn(PROCESS_LOCK_NAME, raw_body)
        self.assertIn(
            "FSystemWideCriticalSection",
            _read("Source/NwiroIntegrationKit/Private/NwiroIKMCPServer.h"),
        )
        self.assertRegex(
            body,
            r"MakeUnique\s*<\s*FSystemWideCriticalSection\s*>\s*"
            r"\([^;]+FTimespan::Zero\s*\(\s*\)\s*\)",
        )
        self.assertIn("IsValid", body)
        self.assertIn("GetCurrentProcessId", body)
        self.assertIn("RestrictedProbeProcessLock", body)
        self.assertIn("IsInGameThread", body)

    def test_stop_releases_owner_even_when_listener_never_started(self) -> None:
        body = _function(
            "Source/NwiroIntegrationKit/Private/NwiroIKMCPServer.cpp",
            "FNwiroIKMCPServer::Stop",
        )
        self.assertIn("ReleaseRestrictedProbeProcessLock", body)
        self.assertNotRegex(
            body,
            r"if\s*\(\s*!bRunning\s*\)\s*return\s*;",
        )
        release = _function(
            "Source/NwiroIntegrationKit/Private/NwiroIKMCPServer.cpp",
            "FNwiroIKMCPServer::ReleaseRestrictedProbeProcessLock",
        )
        self.assertLess(release.index("Release"), release.index("Reset"))

    def test_direct_jsonrpc_and_http_entrypoints_fail_before_parsing(self) -> None:
        process = _function(
            "Source/NwiroIntegrationKit/Private/NwiroIKMCPServer.cpp",
            "FNwiroIKMCPServer::ProcessJsonRpc",
        )
        post = _function(
            "Source/NwiroIntegrationKit/Private/NwiroIKMCPServer.cpp",
            "FNwiroIKMCPServer::HandleMCPPost",
        )
        self.assertLess(
            process.index("CanAcceptRestrictedProbeTraffic"),
            process.index("GetStringField"),
        )
        self.assertLess(
            post.index("CanAcceptRestrictedProbeTraffic"),
            post.index("Request.Body"),
        )

    def test_restart_config_and_dispatch_bypasses_are_callee_gated(self) -> None:
        relative = "Source/NwiroIntegrationKit/Private/NwiroIKMCPServer.cpp"
        restart = _function(relative, "FNwiroIKMCPServer::Restart")
        write_config = _function(relative, "FNwiroIKMCPServer::WriteClaudeConfig")
        dispatch = _function(relative, "FNwiroIKMCPServer::DispatchTool")
        self.assertLess(
            restart.index("IsRestrictedMetadataProbeMode"),
            restart.index("Start(Port)"),
        )
        self.assertLess(
            write_config.index("CanAcceptRestrictedProbeTraffic"),
            write_config.index("FPaths::ProjectDir"),
        )
        self.assertLess(
            dispatch.index("CanAcceptRestrictedProbeTraffic"),
            dispatch.index("DispatchToolImpl"),
        )

    def test_teardown_disables_admission_before_releasing_owner(self) -> None:
        body = _function(
            "Source/NwiroIntegrationKit/Private/NwiroIKMCPServer.cpp",
            "FNwiroIKMCPServer::Stop",
        )
        self.assertLess(body.index("bRunning = false"), body.index("ReleaseRestrictedProbeProcessLock"))
        self.assertLess(body.index("BoundPort = 0"), body.index("ReleaseRestrictedProbeProcessLock"))
        self.assertLess(body.index("IsInGameThread"), body.index("bRunning = false"))

    def test_no_external_activation_input_is_present_in_changed_sources(self) -> None:
        activation = _function(
            "Source/NwiroIntegrationKit/Private/NwiroIKMCPServer.cpp",
            "FNwiroIKMCPServer::IsRestrictedMetadataProbeMode",
        )
        public_headers = "\n".join(
            (
                _read("Source/NwiroIntegrationKit/Private/NwiroIKMCPServer.h"),
                _read("Source/NwiroIntegrationKit/Public/NwiroIK.h"),
            )
        )
        for forbidden in (
            "FCommandLine",
            "GetEnvironmentVariable",
            "FAutoConsoleVariableRef",
            "TAutoConsoleVariable",
        ):
            self.assertNotIn(forbidden, activation)
        for forbidden_public_api in (
            "SetRestrictedMetadataProbeMode",
            "EnableRestrictedMetadataProbe",
            "ActivateRestrictedMetadataProbe",
            "UFUNCTION",
            "UPROPERTY",
        ):
            self.assertNotIn(forbidden_public_api, public_headers)

    def test_ownership_reference_model_allows_exactly_one_process(self) -> None:
        model = _OwnershipModel()
        self.assertFalse(model.acquire(101))
        self.assertTrue(model.acquire(101, private_test_authority=True))
        self.assertFalse(model.acquire(101, private_test_authority=True))
        self.assertFalse(model.acquire(202, private_test_authority=True))
        self.assertFalse(model.release(202))
        self.assertEqual(101, model.owner_pid)
        self.assertTrue(model.release(101))
        self.assertTrue(model.acquire(202, private_test_authority=True))

    def test_candidate_contains_no_binary_or_compiled_output(self) -> None:
        forbidden_suffixes = {".dll", ".exe", ".lib", ".pdb", ".obj"}
        offenders = [
            path.relative_to(CANDIDATE_ROOT).as_posix()
            for path in CANDIDATE_ROOT.rglob("*")
            if path.is_file() and path.suffix.lower() in forbidden_suffixes
        ]
        self.assertEqual([], offenders)


if __name__ == "__main__":
    unittest.main()
