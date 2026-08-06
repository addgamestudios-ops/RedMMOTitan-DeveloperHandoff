"""Offline-testable pre-dispatch firewall for one NWIRO metadata probe.

This module deliberately has no network transport and no generic dispatch API.
It constructs and validates only the fixed RedMMO initialize -> tools/list ->
find_assets transcript bound by the generation-disabled M07 contract.

Runtime transmission remains impossible through this module until a separately
reviewed, hard-pinned server build closes NWIRO's raw-endpoint, headless
permission, auto-config-publication, and bridge-null provider bypasses.
This client state machine does not itself block the vendor HTTP listener or the
Integration Kit's separate ACP-to-ProcessJsonRpc dispatch path.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import secrets
import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if __package__ in (None, ""):
    sys.path.insert(0, str(PROJECT_ROOT))

from Tools.validate_redmmo_nwiro_metadata_dry_run import (
    DEFAULT_CONTRACT,
    EXPECTED_VENDOR_TOOL_DEFINITION,
    NwiroContractError,
    canonical_json_bytes,
    load_json_bytes_strict,
    reauthenticate_before_publication,
    validate_contract_file,
    validate_find_assets_tool_definition,
    validate_future_probe_jsonrpc_request,
    validate_future_probe_jsonrpc_response_bytes,
)


EXPECTED_PARENT_CONTRACT_SHA256 = (
    "B388D2869D0B13A798A1128705B650EC3CCE071DC5BD8441184C359BBE7D9E68"
)
EXPECTED_PARENT_CONTRACT_SEMANTIC_SHA256 = (
    "F7CB349CB67DD2BC22FF76265ACB5DB1C0EFAB473AF895034B7C6651EE856F1D"
)
PROTOCOL_VERSION = "2025-03-26"
MAX_FIREWALL_BODY_BYTES = 16 * 1024
ENDPOINT_RE = re.compile(r"^http://127[.]0[.]0[.]1:([0-9]{1,5})/mcp$")

# Intentionally empty. Adding a hash is a separate authority-changing review
# after a hardened server build exists. Caller-supplied hashes cannot grant it.
TRUSTED_HARDENED_SERVER_BINARY_SHA256: frozenset[str] = frozenset()


class FirewallError(RuntimeError):
    """The exact offline firewall contract was violated."""


class FirewallState(str, Enum):
    READY = "ready"
    INITIALIZE_REQUEST_ISSUED = "initialize_request_issued"
    INITIALIZED = "initialized"
    TOOLS_LIST_REQUEST_ISSUED = "tools_list_request_issued"
    TOOLS_VERIFIED = "tools_verified"
    PROBE_REQUEST_ISSUED = "probe_request_issued"
    COMPLETE = "complete"
    FAILED = "failed"


@dataclass(frozen=True)
class ToolsListSummary:
    tool_count: int
    denied_tool_count: int
    tools_semantic_sha256: str
    allowed_definition_sha256: str


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest().upper()


def _require_exact_keys(value: dict[str, Any], expected: set[str], label: str) -> None:
    actual = set(value)
    if actual != expected:
        raise FirewallError(
            f"{label} keys mismatch: expected {sorted(expected)}, got {sorted(actual)}"
        )


def validate_future_endpoint(endpoint: str) -> tuple[str, int, str]:
    """Validate the only endpoint shape a later hardened transport may use."""

    if type(endpoint) is not str or not endpoint:
        raise FirewallError("endpoint must be a nonempty string")
    match = ENDPOINT_RE.fullmatch(endpoint)
    if match is None:
        raise FirewallError("endpoint must be exact literal http://127.0.0.1:<port>/mcp")
    port = int(match.group(1))
    if match.group(1) != str(port):
        raise FirewallError("endpoint port must use canonical decimal spelling")
    if not 5353 <= port <= 5362:
        raise FirewallError("endpoint port must be inside the pinned NWIRO range")
    return "127.0.0.1", port, "/mcp"


def runtime_send_authorized() -> bool:
    """This version is permanently offline; a later transport needs a new review."""

    return False


class NwiroPredispatchFirewall:
    """A fixed transcript state machine with no arbitrary request surface."""

    def __init__(self, contract_path: Path = DEFAULT_CONTRACT) -> None:
        try:
            contract, payload, authenticated = validate_contract_file(contract_path)
        except NwiroContractError as exc:
            raise FirewallError(str(exc)) from exc
        if contract_path.resolve() != DEFAULT_CONTRACT.resolve():
            raise FirewallError("only the canonical contract path is accepted")
        if _sha256(payload) != EXPECTED_PARENT_CONTRACT_SHA256:
            raise FirewallError("parent contract byte digest mismatch")
        semantic = _sha256(canonical_json_bytes(contract))
        if semantic != EXPECTED_PARENT_CONTRACT_SEMANTIC_SHA256:
            raise FirewallError("parent contract semantic digest mismatch")
        self._contract = contract
        self._contract_payload = payload
        self._authenticated_inputs = authenticated
        self._authenticated_input_count = len(authenticated)
        if self._authenticated_input_count != 11:
            raise FirewallError("canonical contract must authenticate exactly 11 inputs")
        self._run_nonce = secrets.token_hex(16)
        self._initialize_id = f"{self._run_nonce}:initialize"
        self._tools_list_id = f"{self._run_nonce}:tools-list"
        self._probe_id = f"{self._run_nonce}:find-assets"
        self._state = FirewallState.READY
        self._tools_summary: ToolsListSummary | None = None
        self._asset: dict[str, str] | None = None
        self._phase_transcript: list[dict[str, Any]] = []

    @property
    def state(self) -> FirewallState:
        return self._state

    def _fail(self, message: str, exc: Exception | None = None) -> None:
        self._state = FirewallState.FAILED
        if exc is None:
            raise FirewallError(message)
        raise FirewallError(message) from exc

    def _require_state(self, expected: FirewallState) -> None:
        if self._state is not expected:
            self._fail(
                f"invalid firewall sequence: expected {expected.value}, "
                f"got {self._state.value}"
            )

    def _record_phase(self, phase: str, payload: bytes) -> None:
        self._phase_transcript.append(
            {"phase": phase, "bytes": len(payload), "sha256": _sha256(payload)}
        )

    def _reauthenticate(self) -> None:
        try:
            reauthenticate_before_publication(
                DEFAULT_CONTRACT,
                self._contract,
                self._contract_payload,
                self._authenticated_inputs,
            )
        except Exception as exc:
            self._fail("pinned inputs changed between firewall phases", exc)

    def _load_bounded_envelope(self, payload: bytes, label: str) -> dict[str, Any]:
        if (
            type(payload) is not bytes
            or not payload
            or len(payload) > MAX_FIREWALL_BODY_BYTES
        ):
            self._fail(f"{label} size out of bounds")
        try:
            return load_json_bytes_strict(payload, label)
        except (NwiroContractError, RecursionError, ValueError) as exc:
            self._fail(f"{label} rejected", exc)

    def build_initialize_request(self) -> bytes:
        self._require_state(FirewallState.READY)
        envelope = {
            "jsonrpc": "2.0",
            "id": self._initialize_id,
            "method": "initialize",
            "params": {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {
                    "name": "redmmo-nwiro-firewall",
                    "version": "1.0.0",
                },
            },
        }
        payload = canonical_json_bytes(envelope)
        self._record_phase("initialize_request", payload)
        self._state = FirewallState.INITIALIZE_REQUEST_ISSUED
        return payload

    def accept_initialize_response(self, payload: bytes) -> None:
        self._require_state(FirewallState.INITIALIZE_REQUEST_ISSUED)
        try:
            envelope = self._load_bounded_envelope(
                payload, "NWIRO initialize response"
            )
            _require_exact_keys(
                envelope, {"jsonrpc", "id", "result"}, "initialize response"
            )
            if (
                envelope["jsonrpc"] != "2.0"
                or envelope["id"] != self._initialize_id
            ):
                raise FirewallError("initialize response version or id mismatch")
            result = envelope["result"]
            if not isinstance(result, dict):
                raise FirewallError("initialize result must be an object")
            expected = {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {"listChanged": True}},
                "serverInfo": {"name": "nwiro", "version": "1.0.0"},
            }
            if canonical_json_bytes(result) != canonical_json_bytes(expected):
                raise FirewallError("initialize result differs from pinned server shape")
        except (FirewallError, NwiroContractError) as exc:
            self._fail("initialize response rejected", exc)
        self._record_phase("initialize_response", payload)
        self._state = FirewallState.INITIALIZED

    def build_tools_list_request(self) -> bytes:
        self._require_state(FirewallState.INITIALIZED)
        self._reauthenticate()
        payload = canonical_json_bytes(
            {
                "jsonrpc": "2.0",
                "id": self._tools_list_id,
                "method": "tools/list",
                "params": {},
            }
        )
        self._record_phase("tools_list_request", payload)
        self._state = FirewallState.TOOLS_LIST_REQUEST_ISSUED
        return payload

    def accept_tools_list_response(self, payload: bytes) -> ToolsListSummary:
        self._require_state(FirewallState.TOOLS_LIST_REQUEST_ISSUED)
        try:
            envelope = self._load_bounded_envelope(
                payload, "NWIRO tools/list response"
            )
            _require_exact_keys(
                envelope, {"jsonrpc", "id", "result"}, "tools/list response"
            )
            if (
                envelope["jsonrpc"] != "2.0"
                or envelope["id"] != self._tools_list_id
            ):
                raise FirewallError("tools/list response version or id mismatch")
            result = envelope["result"]
            if not isinstance(result, dict):
                raise FirewallError("tools/list result must be an object")
            _require_exact_keys(result, {"tools"}, "tools/list result")
            tools = result["tools"]
            if not isinstance(tools, list) or len(tools) != 1:
                raise FirewallError(
                    "restricted tools/list must contain exactly one definition"
                )
            names: set[str] = set()
            allowed: list[dict[str, Any]] = []
            for tool in tools:
                if not isinstance(tool, dict):
                    raise FirewallError("tools/list entries must be objects")
                name = tool.get("name")
                if type(name) is not str or not name:
                    raise FirewallError("every tools/list entry needs a name")
                if name in names:
                    raise FirewallError("duplicate tools/list name")
                names.add(name)
                if name == "find_assets":
                    allowed.append(tool)
            if len(allowed) != 1:
                raise FirewallError("tools/list must contain one find_assets definition")
            validate_find_assets_tool_definition(allowed[0])
            summary = ToolsListSummary(
                tool_count=len(tools),
                denied_tool_count=0,
                tools_semantic_sha256=_sha256(canonical_json_bytes(tools)),
                allowed_definition_sha256=_sha256(
                    canonical_json_bytes(allowed[0])
                ),
            )
        except (FirewallError, NwiroContractError) as exc:
            self._fail("tools/list response rejected", exc)
        self._record_phase("tools_list_response", payload)
        self._tools_summary = summary
        self._state = FirewallState.TOOLS_VERIFIED
        return summary

    def build_probe_request(self) -> bytes:
        self._require_state(FirewallState.TOOLS_VERIFIED)
        self._reauthenticate()
        query = next(
            item
            for item in self._contract["query_templates"]
            if item["stable_candidate_id"]
            == self._contract["tool_policy"]["future_single_probe_candidate_id"]
        )
        envelope = {
            "jsonrpc": "2.0",
            "id": self._probe_id,
            "method": "tools/call",
            "params": {
                "name": "find_assets",
                "arguments": dict(query["arguments"]),
            },
        }
        try:
            validate_future_probe_jsonrpc_request(
                self._contract, envelope, self._probe_id
            )
        except NwiroContractError as exc:
            self._fail("constructed probe request rejected", exc)
        payload = canonical_json_bytes(envelope)
        self._record_phase("probe_request", payload)
        self._state = FirewallState.PROBE_REQUEST_ISSUED
        return payload

    def accept_probe_response(self, payload: bytes) -> dict[str, str]:
        self._require_state(FirewallState.PROBE_REQUEST_ISSUED)
        try:
            if (
                type(payload) is not bytes
                or not payload
                or len(payload) > MAX_FIREWALL_BODY_BYTES
            ):
                raise NwiroContractError("probe response size out of bounds")
            asset = validate_future_probe_jsonrpc_response_bytes(
                self._contract, payload, self._probe_id
            )
        except Exception as exc:
            self._fail("probe response rejected", exc)
        self._record_phase("probe_response", payload)
        self._asset = dict(asset)
        self._state = FirewallState.COMPLETE
        return dict(self._asset)

    def redacted_report(self) -> dict[str, Any]:
        if self._state is not FirewallState.COMPLETE:
            self._fail("redacted report requires a complete transcript")
        assert self._tools_summary is not None
        assert self._asset is not None
        query = next(
            item
            for item in self._contract["query_templates"]
            if item["stable_candidate_id"]
            == self._contract["tool_policy"]["future_single_probe_candidate_id"]
        )
        report = {
            "schema_version": 1,
            "status": "synthetic_transcript_valid",
            "evidence_class": "static",
            "network_or_mcp_execution": False,
            "contract_sha256": EXPECTED_PARENT_CONTRACT_SHA256,
            "contract_semantic_sha256": EXPECTED_PARENT_CONTRACT_SEMANTIC_SHA256,
            "authenticated_input_count": self._authenticated_input_count,
            "allowed_tool": "find_assets",
            "denied_tool_count": self._tools_summary.denied_tool_count,
            "tools_semantic_sha256": self._tools_summary.tools_semantic_sha256,
            "allowed_definition_sha256": (
                self._tools_summary.allowed_definition_sha256
            ),
            "phase_transcript": copy.deepcopy(self._phase_transcript),
            "asset_identity": {
                "stable_candidate_id": query["stable_candidate_id"],
                "identity_sha256": _sha256(canonical_json_bytes(self._asset)),
            },
            "runtime_send_authorized": runtime_send_authorized(),
            "raw_mcp_direct_path_blocked": False,
            "acp_direct_dispatch_blocked": False,
            "runtime_tool_registry_generation_bound": False,
            "mcp_initialized_notification_verified": False,
            "exclusive_single_process_lock_verified": False,
            "headless_permission_bypass_fixed": False,
            "bridge_null_provider_bypass_fixed": False,
            "vendor_auto_config_publication_disabled": False,
            "trusted_hardened_server_binary_count": len(
                TRUSTED_HARDENED_SERVER_BINARY_SHA256
            ),
        }
        self._reauthenticate()
        return report


def _synthetic_transcript(firewall: NwiroPredispatchFirewall) -> dict[str, Any]:
    firewall.build_initialize_request()
    firewall.accept_initialize_response(
        canonical_json_bytes(
            {
                "jsonrpc": "2.0",
                "id": firewall._initialize_id,
                "result": {
                    "protocolVersion": PROTOCOL_VERSION,
                    "capabilities": {"tools": {"listChanged": True}},
                    "serverInfo": {"name": "nwiro", "version": "1.0.0"},
                },
            }
        )
    )
    firewall.build_tools_list_request()
    firewall.accept_tools_list_response(
        canonical_json_bytes(
            {
                "jsonrpc": "2.0",
                "id": firewall._tools_list_id,
                "result": {
                    "tools": [
                        EXPECTED_VENDOR_TOOL_DEFINITION,
                    ]
                },
            }
        )
    )
    firewall.build_probe_request()
    query = next(
        item
        for item in firewall._contract["query_templates"]
        if item["stable_candidate_id"]
        == firewall._contract["tool_policy"]["future_single_probe_candidate_id"]
    )
    inner = {
        "success": True,
        "assets": [query["expected_result"]],
        "count": 1,
    }
    firewall.accept_probe_response(
        canonical_json_bytes(
            {
                "jsonrpc": "2.0",
                "id": firewall._probe_id,
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(
                                inner,
                                ensure_ascii=True,
                                sort_keys=True,
                                separators=(",", ":"),
                            ),
                        }
                    ]
                },
            }
        )
    )
    return firewall.redacted_report()


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Validate the offline NWIRO pre-dispatch firewall against a "
            "synthetic transcript. This command has no network transport."
        )
    )
    parser.parse_args()
    try:
        report = _synthetic_transcript(NwiroPredispatchFirewall())
    except FirewallError as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, sort_keys=True))
        return 2
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
