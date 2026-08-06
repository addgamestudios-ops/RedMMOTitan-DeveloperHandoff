"""Offline contracts for the isolated NWIRO lifecycle source slice.

The suite authenticates the authorization and rollback inputs, inspects only
the unbuilt external candidate source, and exercises small lifecycle reference
models.  It never loads Unreal, binds a socket, initializes MCP, calls a
provider, installs a plugin, or mutates an asset/map.  Passing is static
evidence only and cannot establish runtime acceptance.
"""

from __future__ import annotations

import hashlib
import json
import re
import unittest
from dataclasses import dataclass, field
from pathlib import Path

from Tools.audit_nwiro_restricted_probe_source import (
    NwiroSourceAuditError,
    _extract_function,
    _mask_cpp_noncode,
)


PROJECT_ROOT = Path(r"D:\RedMMOTitan")
CANDIDATE_ROOT = Path(
    r"D:\RedMMOTitanWindowsData\Staging\NwiroRestrictedProbeForkCandidateV1"
)
BASELINE_MANIFEST = Path(
    r"D:\RedMMOTitanWindowsData\Staging"
    r"\NwiroRestrictedProbeForkCandidateV1.baseline.v1.json"
)
ROLLBACK_ROOT = Path(
    r"D:\RedMMOTitanWindowsData\Rollback"
    r"\NwiroRestrictedProbeLifecycle_20260725_1223Z"
)
AUTHORIZATION = (
    PROJECT_ROOT
    / "Build"
    / "Automation"
    / "redmmo_nwiro_lifecycle_execution_authorization_v1.json"
)

BASELINE_MANIFEST_SHA256 = (
    "AACAC06301F470A270870DD48FF4085CCA44A3370E9CE504592F79D11EA7996A"
)
AUTHORIZATION_SHA256 = (
    "203F1B7A7C7BB2B594B8BF8DFCD8182B8B6386106CCA00AEC15AFF1F1FCF5983"
)
SERVER_CPP = (
    "Source/NwiroIntegrationKit/Private/NwiroIKMCPServer.cpp"
)
SERVER_HEADER = (
    "Source/NwiroIntegrationKit/Private/NwiroIKMCPServer.h"
)
BRIDGE_CPP = "Source/NwiroIntegrationKit/Private/NwiroIKBridge.cpp"
AUTHORIZED_INITIAL_SOURCE_SHA256 = {
    SERVER_CPP: (
        "AA3FD57690EB52EEADCC473DA5C15C0F6A555199A06C9EEA4EF18258ECE20099"
    ),
    SERVER_HEADER: (
        "E6161EFD3E4F34DE037D329766A61D792ECC572FDCF8D83592AE99277F4AF747"
    ),
    BRIDGE_CPP: (
        "80C8A3194148C86D1F4E1D479133BB2B76A627698F2E35DC4D6CE822E5FC1AA1"
    ),
}
REVIEWED_CURRENT_SOURCE_SHA256 = {
    SERVER_CPP: (
        "3188840914AC8644741717FE9EA29DBB8654A906C0D6F1D64FEDE5E4F5FDCEC7"
    ),
    SERVER_HEADER: (
        "F280BD2FF13190FFEE46EAA22EF36F622E8FAC9FA4AB733C345115B596EC86AE"
    ),
    BRIDGE_CPP: (
        "7BC0F35567D5BAB9EF909A2C1AAB72041E097D4EFCEC28CDCA04048A3B5E9406"
    ),
}
EXPECTED_CHANGED_FILES = {
    "NwiroIntegrationKit.uplugin",
    BRIDGE_CPP,
    SERVER_CPP,
    SERVER_HEADER,
    "Source/NwiroIntegrationKit/Private/NwiroIntegrationKit.cpp",
    "Source/NwiroIntegrationKit/Public/NwiroIK.h",
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def _read(relative: str) -> str:
    return (CANDIDATE_ROOT / relative).read_text(encoding="utf-8")


def _extract_definition_raw(source: str, qualified_name: str) -> str:
    match = re.search(
        rf"(?m)^[^\n;]*\b{re.escape(qualified_name)}\s*\([^;]*?\)\s*\{{",
        source,
    )
    if match is None:
        raise AssertionError(f"function definition not found: {qualified_name}")
    brace = source.find("{", match.start())
    depth = 0
    for index in range(brace, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[match.start() : index + 1]
    raise AssertionError(f"unterminated function: {qualified_name}")


def _function(relative: str, qualified_name: str) -> str:
    source = _read(relative)
    try:
        return _mask_cpp_noncode(
            _extract_function(source, qualified_name)
        )
    except NwiroSourceAuditError:
        # Route handlers are also referenced by CreateStatic before their
        # definitions, which the shared broad extractor intentionally treats
        # as ambiguous. Anchor a definition line, then balance braces.
        return _mask_cpp_noncode(
            _extract_definition_raw(source, qualified_name)
        )


def _current_files() -> dict[str, tuple[int, str]]:
    return {
        path.relative_to(CANDIDATE_ROOT).as_posix(): (
            path.stat().st_size,
            _sha256(path),
        )
        for path in sorted(CANDIDATE_ROOT.rglob("*"))
        if path.is_file()
    }


def _baseline_files() -> dict[str, tuple[int, str]]:
    payload = BASELINE_MANIFEST.read_bytes()
    if hashlib.sha256(payload).hexdigest().upper() != BASELINE_MANIFEST_SHA256:
        raise AssertionError("historical baseline manifest hash drift")
    document = json.loads(payload.decode("utf-8"))
    return {
        item["path"]: (item["bytes"], item["sha256"])
        for item in document["tree"]["files"]
    }


@dataclass
class _LifecycleModel:
    state: str = "stopped"
    generation: int = 0
    in_flight: int = 0
    listener_may_remain: bool = False
    owner_held: bool = False

    def start(self, *, private_authority: bool = False) -> bool:
        if (
            not private_authority
            or self.state != "stopped"
            or self.in_flight
            or self.listener_may_remain
            or self.owner_held
        ):
            return False
        self.state = "accepting"
        self.generation += 1
        self.listener_may_remain = True
        self.owner_held = True
        return True

    def lease(self) -> int | None:
        if self.state != "accepting" or not self.owner_held:
            return None
        self.in_flight += 1
        return self.generation

    def close_admission(self) -> None:
        self.state = "draining"

    def release_lease(self, generation: int) -> bool:
        if generation != self.generation or self.in_flight <= 0:
            return False
        self.in_flight -= 1
        return True

    def release_owner(self) -> bool:
        if (
            not self.owner_held
            or self.state in {"accepting", "draining"}
            or self.in_flight
            or self.listener_may_remain
        ):
            return False
        self.owner_held = False
        return True


@dataclass
class _PermissionModel:
    generation: int = 1
    session_id: str = "session-a"
    next_id: int = 1000
    pending: dict[int, tuple[int, str]] = field(default_factory=dict)

    def add(self) -> int:
        permission_id = self.next_id
        self.next_id += 1
        self.pending[permission_id] = (self.generation, self.session_id)
        return permission_id

    def reset(self, session_id: str) -> None:
        self.pending.clear()
        self.generation += 1
        self.session_id = session_id

    def respond(
        self,
        permission_id: int,
        generation: int,
        session_id: str,
    ) -> bool:
        if self.pending.get(permission_id) != (generation, session_id):
            return False
        del self.pending[permission_id]
        return True


class NwiroLifecycleSourceTests(unittest.TestCase):
    def test_authorization_and_rollback_are_exact(self) -> None:
        self.assertEqual(AUTHORIZATION_SHA256, _sha256(AUTHORIZATION))
        authorization = json.loads(
            AUTHORIZATION.read_text(encoding="utf-8")
        )
        allowlist = {
            item["path"]: item["sha256"]
            for item in authorization["exact_candidate_mutation_allowlist"]
        }
        self.assertEqual(AUTHORIZED_INITIAL_SOURCE_SHA256, allowlist)
        rollback_names = {
            SERVER_CPP: "NwiroIKMCPServer.cpp",
            SERVER_HEADER: "NwiroIKMCPServer.h",
            BRIDGE_CPP: "NwiroIKBridge.cpp",
        }
        for relative, expected in AUTHORIZED_INITIAL_SOURCE_SHA256.items():
            self.assertEqual(
                expected,
                _sha256(ROLLBACK_ROOT / rollback_names[relative]),
                relative,
            )

    def test_reviewed_source_revision_is_exact(self) -> None:
        for relative, expected in REVIEWED_CURRENT_SOURCE_SHA256.items():
            self.assertEqual(
                expected,
                _sha256(CANDIDATE_ROOT / relative),
                relative,
            )

    def test_historical_baseline_delta_has_no_add_remove_or_rename(self) -> None:
        baseline = _baseline_files()
        current = _current_files()
        self.assertEqual(set(baseline), set(current))
        changed = {
            path
            for path in baseline
            if baseline[path] != current[path]
        }
        self.assertEqual(EXPECTED_CHANGED_FILES, changed)

    def test_activation_and_readiness_remain_literal_false_only(self) -> None:
        for name in (
            "FNwiroIKMCPServer::IsRestrictedMetadataProbeMode",
            "FNwiroIKMCPServer::IsRestrictedProbeRuntimeReady",
        ):
            body = _function(SERVER_CPP, name)
            block = body[body.index("{") :]
            statements = [
                statement.strip()
                for statement in block.strip("{} \t\r\n").split(";")
                if statement.strip()
            ]
            self.assertEqual(["return false"], statements, name)

    def test_start_orders_owner_routes_listener_and_admission(self) -> None:
        body = _function(SERVER_CPP, "FNwiroIKMCPServer::Start")
        sequence = (
            "IsRestrictedMetadataProbeMode",
            "IsRestrictedProbeRuntimeReady",
            "AcquireRestrictedProbeProcessLock",
            "GetHttpRouter",
            "BindRestrictedProbeRoutes",
            "StartAllListeners",
            "ERestrictedProbeLifecycle::Accepting",
        )
        positions = [body.index(token) for token in sequence]
        self.assertEqual(sorted(positions), positions)
        self.assertNotIn("WriteClaudeConfig", body)
        self.assertNotIn("BindRoute", body)
        self.assertLess(
            body.index("GetHttpRouter"),
            body.index("bRestrictedProbeListenerMayRemain = true"),
        )
        self.assertLess(
            body.index("bRestrictedProbeListenerMayRemain = true"),
            body.index("BindRestrictedProbeRoutes"),
        )

    def test_route_handles_are_checked_retained_and_unbound(self) -> None:
        bind = _function(SERVER_CPP, "FNwiroIKMCPServer::BindRestrictedProbeRoutes")
        unbind = _function(
            SERVER_CPP,
            "FNwiroIKMCPServer::UnbindRestrictedProbeRoutes",
        )
        self.assertIn("FHttpRouteHandle Handle", bind)
        self.assertIn("Handle.IsValid", bind)
        self.assertEqual(4, bind.count("BindChecked("))
        self.assertIn("UnbindRoute", bind)
        self.assertIn("RestrictedProbeRouteHandles = MoveTemp", bind)
        self.assertIn("UnbindRoute", unbind)
        self.assertIn("RestrictedProbeRouteHandles.Reset", unbind)
        self.assertLess(
            unbind.index("UnbindRoute"),
            unbind.index("RestrictedProbeRouteHandles.Reset"),
        )

    def test_stop_closes_admission_unbinds_resets_and_drains_in_order(self) -> None:
        body = _function(SERVER_CPP, "FNwiroIKMCPServer::Stop")
        sequence = (
            "CloseRestrictedProbeAdmission",
            "UnbindRestrictedProbeRoutes",
            "ResetRestrictedProbeSessionState",
            "WaitForRestrictedProbeRequestDrain",
            "ReleaseRestrictedProbeProcessLock",
        )
        positions = [body.index(token) for token in sequence]
        self.assertEqual(sorted(positions), positions)
        self.assertNotIn("StopAllListeners(", body)

    def test_owner_release_refuses_live_lifecycle_and_retained_listener(self) -> None:
        body = _function(
            SERVER_CPP,
            "FNwiroIKMCPServer::ReleaseRestrictedProbeProcessLock",
        )
        for token in (
            "RestrictedProbeInFlightRequests != 0",
            "ERestrictedProbeLifecycle::Accepting",
            "ERestrictedProbeLifecycle::Draining",
            "bRestrictedProbeListenerMayRemain",
        ):
            self.assertIn(token, body)
        refusal = body.index("bRestrictedProbeListenerMayRemain")
        release = body.rindex("RestrictedProbeProcessLock->Release")
        self.assertLess(refusal, release)
        source = _mask_cpp_noncode(_read(SERVER_CPP))
        self.assertNotIn("StopAllListeners(", source)

    def test_stale_lifecycle_lease_cannot_decrement_active_epoch(self) -> None:
        body = _function(
            SERVER_CPP,
            "FNwiroIKMCPServer::ReleaseRestrictedProbeRequestLease",
        )
        mismatch = body.index("Generation != RestrictedProbeLifecycleGeneration")
        refusal = body.index("return", mismatch)
        decrement = body.index("--RestrictedProbeInFlightRequests")
        self.assertLess(mismatch, refusal)
        self.assertLess(refusal, decrement)

    def test_all_runtime_entrypoints_acquire_a_request_lease(self) -> None:
        for name in (
            "FNwiroIKMCPServer::HandleMCPOptions",
            "FNwiroIKMCPServer::HandleMCPGet",
            "FNwiroIKMCPServer::HandleMCPDelete",
            "FNwiroIKMCPServer::HandleMCPPost",
            "FNwiroIKMCPServer::ProcessJsonRpc",
            "FNwiroIKMCPServer::RespondToToolPermission",
            "FNwiroIKMCPServer::WriteClaudeConfig",
            "FNwiroIKMCPServer::GetEnabledToolDefinitionsJson",
            "FNwiroIKMCPServer::GetToolDefinitionsForSettingsJson",
        ):
            body = _function(SERVER_CPP, name)
            self.assertIn(
                "TryAcquireRestrictedProbeRequestLease",
                body,
                name,
            )
        post = _function(SERVER_CPP, "FNwiroIKMCPServer::HandleMCPPost")
        self.assertLess(
            post.index("TryAcquireRestrictedProbeRequestLease"),
            post.index("Request.Body"),
        )
        direct = _function(SERVER_CPP, "FNwiroIKMCPServer::ProcessJsonRpc")
        self.assertLess(
            direct.index("TryAcquireRestrictedProbeRequestLease"),
            direct.index("TSharedPtr<FJsonObject> Response"),
        )
        self.assertNotIn("ProcessJsonRpcUnderLease", direct)

    def test_direct_inprocess_acp_jsonrpc_path_is_hard_denied(self) -> None:
        raw = _extract_definition_raw(
            _read(SERVER_CPP),
            "FNwiroIKMCPServer::ProcessJsonRpc",
        )
        body = _mask_cpp_noncode(raw)
        self.assertIn("TryAcquireRestrictedProbeRequestLease", body)
        self.assertNotIn("ProcessJsonRpcUnderLease", body)
        self.assertNotIn("DispatchTool", body)
        self.assertIn(
            'TEXT("Direct in-process MCP dispatch is disabled")',
            raw,
        )

    def test_admission_is_lock_protected_and_game_thread_only(self) -> None:
        acquire = _function(
            SERVER_CPP,
            "FNwiroIKMCPServer::TryAcquireRestrictedProbeRequestLease",
        )
        sequence = (
            "IsInGameThread",
            "HasRestrictedProbeProcessOwnership",
            "FScopeLock",
            "ERestrictedProbeLifecycle::Accepting",
            "++RestrictedProbeInFlightRequests",
        )
        positions = [acquire.index(token) for token in sequence]
        self.assertEqual(sorted(positions), positions)

    def test_callback_and_pending_request_retain_generation_bound_lease(self) -> None:
        callback = _function(
            SERVER_CPP,
            "FNwiroIKMCPServer::MakeRestrictedProbeLeasedCallback",
        )
        post = _function(SERVER_CPP, "FNwiroIKMCPServer::HandleMCPPost")
        response = _function(
            SERVER_CPP,
            "FNwiroIKMCPServer::RespondToToolPermission",
        )
        self.assertIn("[OnComplete, Lease]", callback)
        self.assertIn("Pending.Callback = Complete", post)
        self.assertIn(
            "Pending.LifecycleGeneration = Lease->GetGeneration()",
            post,
        )
        self.assertIn(
            "P.LifecycleGeneration == ActiveGeneration",
            response,
        )

    def test_session_reset_clears_every_permission_surface(self) -> None:
        body = _function(
            SERVER_CPP,
            "FNwiroIKMCPServer::ResetRestrictedProbeSessionState",
        )
        for token in (
            "SessionId.Empty",
            "bSessionAllowed = false",
            "++RestrictedProbeSessionGeneration",
            "OutDrained = MoveTemp(PendingToolCalls)",
            "PendingToolCalls.Reset",
        ):
            self.assertIn(token, body)
        self.assertNotIn("NextPermissionId", body)
        source = _mask_cpp_noncode(_read(SERVER_CPP))
        self.assertNotIn("bSessionAllowed = true", source)

    def test_noninitialize_posts_require_exact_active_session(self) -> None:
        raw = _extract_definition_raw(
            _read(SERVER_CPP),
            "FNwiroIKMCPServer::HandleMCPPost",
        )
        body = _mask_cpp_noncode(raw)
        for token in (
            "GetRestrictedProbeSessionSnapshot",
            "SessionHeaderValues->Num() != 1",
            "(*SessionHeaderValues)[0] != ActiveSessionId",
            "ActiveSessionId.IsEmpty",
        ):
            self.assertIn(token, body)
        self.assertIn('TEXT("MCP-Session-Id")', raw)
        self.assertLess(
            body.index("(*SessionHeaderValues)[0] != ActiveSessionId"),
            body.index("JsonRequest->HasField"),
        )

    def test_pending_permissions_bind_lifecycle_session_and_monotonic_id(self) -> None:
        post = _function(SERVER_CPP, "FNwiroIKMCPServer::HandleMCPPost")
        respond = _function(
            SERVER_CPP,
            "FNwiroIKMCPServer::RespondToToolPermission",
        )
        reset = _function(
            SERVER_CPP,
            "FNwiroIKMCPServer::ResetRestrictedProbeSessionState",
        )
        for token in (
            "Pending.LifecycleGeneration = Lease->GetGeneration()",
            "Pending.SessionGeneration = ActiveSessionGeneration",
            "Pending.SessionId = ActiveSessionId",
            "NextPermissionId++",
            "NextPermissionId == MAX_int32",
        ):
            self.assertIn(token, post)
        for token in (
            "P.LifecycleGeneration == ActiveGeneration",
            "P.SessionGeneration == ActiveSessionGeneration",
            "P.SessionId == ActiveSessionId",
        ):
            self.assertIn(token, respond)
        self.assertNotIn("NextPermissionId", reset)

    def test_delete_requires_one_exact_active_session_and_resets(self) -> None:
        raw = _extract_definition_raw(
            _read(SERVER_CPP),
            "FNwiroIKMCPServer::HandleMCPDelete",
        )
        body = _function(SERVER_CPP, "FNwiroIKMCPServer::HandleMCPDelete")
        for token in (
            "GetRestrictedProbeSessionId",
            "SessionHeaderValues->Num() != 1",
            "(*SessionHeaderValues)[0] != ActiveSessionId",
            "ResetRestrictedProbeSessionState",
        ):
            self.assertIn(token, body)
        self.assertIn('TEXT("MCP-Session-Id")', raw)
        self.assertLess(
            body.index("(*SessionHeaderValues)[0] != ActiveSessionId"),
            body.index("ResetRestrictedProbeSessionState"),
        )

    def test_bridge_has_no_global_session_write_and_exact_permission_ids(self) -> None:
        bridge = _mask_cpp_noncode(_read(BRIDGE_CPP))
        self.assertNotIn("FNwiroIKMCPServer::bSessionAllowed", bridge)
        respond_raw = _extract_function(
            _read(BRIDGE_CPP),
            "UNwiroIKBridge::RespondToPermission",
        )
        respond = _mask_cpp_noncode(respond_raw)
        self.assertNotIn("OptionId.Contains", respond)
        affirmative_ids = set(
            re.findall(
                r'OptionId\.Equals\s*\(\s*TEXT\("([^"]+)"\)',
                respond_raw,
            )
        )
        self.assertEqual({"allow"}, affirmative_ids)

    def test_bridge_persists_config_only_after_admission_opens(self) -> None:
        for name in (
            "UNwiroIKBridge::StartMCPServer",
            "UNwiroIKBridge::SetMCPPort",
        ):
            body = _function(BRIDGE_CPP, name)
            self.assertLess(
                body.index("IsRestrictedProbeAdmissionOpen"),
                body.index("SaveMCPConfig"),
                name,
            )
            self.assertIn(
                "SaveMCPConfig(FNwiroIKMCPServer::GetPort())",
                body,
                name,
            )

    def test_health_and_port_reads_are_game_thread_only(self) -> None:
        for name in (
            "FNwiroIKMCPServer::GetPort",
            "FNwiroIKMCPServer::IsHealthy",
        ):
            body = _function(SERVER_CPP, name)
            self.assertIn("IsInGameThread", body, name)

    def test_stop_drain_check_is_nonblocking_and_release_is_conditional(
        self,
    ) -> None:
        body = _function(SERVER_CPP, "FNwiroIKMCPServer::Stop")
        self.assertIn("WaitForRestrictedProbeRequestDrain(0.0)", body)
        wait = body.index("WaitForRestrictedProbeRequestDrain(0.0)")
        condition = body.index("if (bRequestsDrained)", wait)
        release = body.index("ReleaseRestrictedProbeProcessLock", condition)
        self.assertLess(wait, condition)
        self.assertLess(condition, release)

    def test_lifecycle_model_refuses_new_work_and_owner_release(self) -> None:
        model = _LifecycleModel()
        self.assertFalse(model.start())
        self.assertTrue(model.start(private_authority=True))
        generation = model.lease()
        self.assertEqual(1, generation)
        model.close_admission()
        self.assertIsNone(model.lease())
        self.assertFalse(model.release_owner())
        self.assertTrue(model.release_lease(generation or 0))
        model.state = "stopped"
        self.assertFalse(model.release_owner())
        model.listener_may_remain = False
        self.assertTrue(model.release_owner())

    def test_permission_model_rejects_stale_generation_after_reset(self) -> None:
        model = _PermissionModel()
        old_permission_id = model.add()
        stale_generation = model.generation
        model.reset("session-b")
        new_permission_id = model.add()
        self.assertNotEqual(old_permission_id, new_permission_id)
        self.assertFalse(
            model.respond(
                old_permission_id,
                stale_generation,
                "session-a",
            )
        )
        self.assertFalse(
            model.respond(
                new_permission_id,
                stale_generation,
                "session-a",
            )
        )
        self.assertTrue(
            model.respond(
                new_permission_id,
                model.generation,
                model.session_id,
            )
        )

    def test_candidate_contains_no_compiled_output(self) -> None:
        forbidden_suffixes = {".dll", ".exe", ".lib", ".obj", ".pdb"}
        offenders = [
            path.relative_to(CANDIDATE_ROOT).as_posix()
            for path in CANDIDATE_ROOT.rglob("*")
            if path.is_file() and path.suffix.lower() in forbidden_suffixes
        ]
        self.assertEqual([], offenders)


if __name__ == "__main__":
    unittest.main()
