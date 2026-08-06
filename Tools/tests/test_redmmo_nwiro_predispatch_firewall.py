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

from Tools.redmmo_nwiro_predispatch_firewall import (
    EXPECTED_PARENT_CONTRACT_SHA256,
    FirewallError,
    FirewallState,
    NwiroPredispatchFirewall,
    PROTOCOL_VERSION,
    TRUSTED_HARDENED_SERVER_BINARY_SHA256,
    _synthetic_transcript,
    runtime_send_authorized,
    validate_future_endpoint,
)
from Tools.validate_redmmo_nwiro_metadata_dry_run import (
    DEFAULT_CONTRACT,
    EXPECTED_VENDOR_TOOL_DEFINITION,
    NwiroContractError,
    canonical_json_bytes,
)


def initialize_response(firewall: NwiroPredispatchFirewall) -> bytes:
    return canonical_json_bytes(
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


def tools_response(
    firewall: NwiroPredispatchFirewall, *tools: dict[str, object]
) -> bytes:
    return canonical_json_bytes(
        {
            "jsonrpc": "2.0",
            "id": firewall._tools_list_id,
            "result": {"tools": list(tools)},
        }
    )


def ready_for_tools() -> NwiroPredispatchFirewall:
    firewall = NwiroPredispatchFirewall()
    firewall.build_initialize_request()
    firewall.accept_initialize_response(initialize_response(firewall))
    firewall.build_tools_list_request()
    return firewall


def ready_for_probe() -> NwiroPredispatchFirewall:
    firewall = ready_for_tools()
    firewall.accept_tools_list_response(
        tools_response(
            firewall,
            copy.deepcopy(EXPECTED_VENDOR_TOOL_DEFINITION),
        )
    )
    firewall.build_probe_request()
    return firewall


class RedMMONwiroPredispatchFirewallTests(unittest.TestCase):
    def test_canonical_contract_authenticates_but_runtime_stays_disabled(self):
        firewall = NwiroPredispatchFirewall()
        self.assertEqual(firewall.state, FirewallState.READY)
        self.assertEqual(TRUSTED_HARDENED_SERVER_BINARY_SHA256, frozenset())
        self.assertFalse(runtime_send_authorized())
        self.assertEqual(len(firewall._run_nonce), 32)
        self.assertEqual(firewall._authenticated_input_count, 11)
        self.assertEqual(
            hashlib.sha256(DEFAULT_CONTRACT.read_bytes()).hexdigest().upper(),
            EXPECTED_PARENT_CONTRACT_SHA256,
        )

    def test_noncanonical_contract_path_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            copied = Path(temporary) / "contract.json"
            copied.write_bytes(DEFAULT_CONTRACT.read_bytes())
            with self.assertRaises(FirewallError):
                NwiroPredispatchFirewall(copied)

    def test_offline_module_imports_no_network_or_process_transport(self):
        source_path = (
            Path(__file__).resolve().parents[1]
            / "redmmo_nwiro_predispatch_firewall.py"
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
                {"socket", "requests", "urllib", "http", "httpx", "subprocess"}
            )
        )

    def test_direct_and_module_cli_resist_hostile_tools_package_precedence(self):
        project_root = Path(__file__).resolve().parents[2]
        script = project_root / "Tools" / "redmmo_nwiro_predispatch_firewall.py"
        with tempfile.TemporaryDirectory() as temporary:
            hostile_root = Path(temporary)
            hostile_tools = hostile_root / "Tools"
            hostile_tools.mkdir()
            (hostile_tools / "__init__.py").write_text(
                "raise RuntimeError('hostile Tools package loaded')\n",
                encoding="utf-8",
            )
            environment = os.environ.copy()
            environment["PYTHONPATH"] = str(hostile_root)
            direct = subprocess.run(
                [sys.executable, str(script)],
                cwd=hostile_root,
                env=environment,
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            self.assertEqual(direct.returncode, 0, direct.stderr)
            self.assertEqual(
                json.loads(direct.stdout)["status"], "synthetic_transcript_valid"
            )
            module = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "Tools.redmmo_nwiro_predispatch_firewall",
                ],
                cwd=project_root,
                env=environment,
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            self.assertEqual(module.returncode, 0, module.stderr)
            self.assertEqual(
                json.loads(module.stdout)["status"], "synthetic_transcript_valid"
            )

    def test_endpoint_is_literal_loopback_without_dns_redirect_or_proxy_shape(self):
        self.assertEqual(
            validate_future_endpoint("http://127.0.0.1:5353/mcp"),
            ("127.0.0.1", 5353, "/mcp"),
        )
        for endpoint in (
            "http://localhost:5353/mcp",
            "http://127.0.0.1:5352/mcp",
            "http://127.0.0.1:5363/mcp",
            "http://127.0.0.1:5353/mcp?x=1",
            "http://user@127.0.0.1:5353/mcp",
            "https://127.0.0.1:5353/mcp",
            "http://[::1]:5353/mcp",
            "http://127.0.0.1:5353/redirect",
            "http://127.0.0.1:05353/mcp",
        ):
            with self.subTest(endpoint=endpoint):
                with self.assertRaises(FirewallError):
                    validate_future_endpoint(endpoint)

    def test_fixed_requests_are_deterministic_and_have_no_arbitrary_api(self):
        first = NwiroPredispatchFirewall()
        second = NwiroPredispatchFirewall()
        first_request = json.loads(first.build_initialize_request())
        second_request = json.loads(second.build_initialize_request())
        self.assertNotEqual(first_request["id"], second_request["id"])
        first_request["id"] = "<id>"
        second_request["id"] = "<id>"
        self.assertEqual(first_request, second_request)
        self.assertFalse(hasattr(first, "dispatch"))
        self.assertFalse(hasattr(first, "send"))
        first.accept_initialize_response(initialize_response(first))
        second.accept_initialize_response(initialize_response(second))
        first_tools = json.loads(first.build_tools_list_request())
        second_tools = json.loads(second.build_tools_list_request())
        first_tools["id"] = "<id>"
        second_tools["id"] = "<id>"
        self.assertEqual(first_tools, second_tools)

    def test_out_of_order_call_fails_closed_and_poisoned_session_stays_failed(self):
        firewall = NwiroPredispatchFirewall()
        with self.assertRaises(FirewallError):
            firewall.build_probe_request()
        self.assertEqual(firewall.state, FirewallState.FAILED)
        with self.assertRaises(FirewallError):
            firewall.build_initialize_request()

    def test_reauthentication_failure_poisoned_before_next_request(self):
        firewall = NwiroPredispatchFirewall()
        firewall.build_initialize_request()
        firewall.accept_initialize_response(initialize_response(firewall))
        with patch(
            "Tools.redmmo_nwiro_predispatch_firewall."
            "reauthenticate_before_publication",
            side_effect=NwiroContractError("drift"),
        ):
            with self.assertRaises(FirewallError):
                firewall.build_tools_list_request()
        self.assertEqual(firewall.state, FirewallState.FAILED)

    def test_unexpected_reauthentication_exception_also_poisons_session(self):
        firewall = NwiroPredispatchFirewall()
        firewall.build_initialize_request()
        firewall.accept_initialize_response(initialize_response(firewall))
        with patch(
            "Tools.redmmo_nwiro_predispatch_firewall."
            "reauthenticate_before_publication",
            side_effect=RuntimeError("unexpected reauthentication failure"),
        ):
            with self.assertRaises(FirewallError):
                firewall.build_tools_list_request()
        self.assertEqual(firewall.state, FirewallState.FAILED)

    def test_initialize_response_rejects_id_error_extra_and_shape_drift(self):
        mutations = (
            lambda value: value.update({"id": "wrong"}),
            lambda value: value.update({"error": {"code": -1}}),
            lambda value: value.update({"extra": "x"}),
            lambda value: value["result"].update({"extra": "x"}),
            lambda value: value["result"].update({"protocolVersion": "old"}),
            lambda value: value["result"]["capabilities"]["tools"].update(
                {"listChanged": False}
            ),
            lambda value: value["result"]["capabilities"]["tools"].update(
                {"listChanged": 1}
            ),
        )
        for mutate in mutations:
            firewall = NwiroPredispatchFirewall()
            firewall.build_initialize_request()
            base = json.loads(initialize_response(firewall))
            candidate = copy.deepcopy(base)
            mutate(candidate)
            with self.assertRaises(FirewallError):
                firewall.accept_initialize_response(canonical_json_bytes(candidate))
            self.assertEqual(firewall.state, FirewallState.FAILED)

    def test_tools_list_requires_exact_singleton_allowed_definition(self):
        firewall = ready_for_tools()
        summary = firewall.accept_tools_list_response(
            tools_response(
                firewall,
                copy.deepcopy(EXPECTED_VENDOR_TOOL_DEFINITION),
            )
        )
        self.assertEqual(summary.tool_count, 1)
        self.assertEqual(summary.denied_tool_count, 0)
        self.assertFalse(hasattr(summary, "tool_names"))
        self.assertEqual(firewall.state, FirewallState.TOOLS_VERIFIED)

    def test_tools_list_rejects_missing_duplicate_or_mutated_allowed_definition(self):
        denied = {
            "name": "spawn_actor",
            "description": "denied",
            "inputSchema": {"type": "object", "properties": {}},
        }
        mutated = copy.deepcopy(EXPECTED_VENDOR_TOOL_DEFINITION)
        mutated["annotations"]["readOnlyHint"] = False
        cases = (
            (denied,),
            (denied, copy.deepcopy(EXPECTED_VENDOR_TOOL_DEFINITION)),
            (
                copy.deepcopy(EXPECTED_VENDOR_TOOL_DEFINITION),
                copy.deepcopy(EXPECTED_VENDOR_TOOL_DEFINITION),
            ),
            (mutated,),
            ({"description": "missing name"},),
        )
        for tools in cases:
            firewall = ready_for_tools()
            with self.assertRaises(FirewallError):
                firewall.accept_tools_list_response(tools_response(firewall, *tools))
            self.assertEqual(firewall.state, FirewallState.FAILED)

    def test_tools_list_rejects_duplicate_json_keys_and_oversize_payload(self):
        firewall = ready_for_tools()
        correct_id = firewall._tools_list_id.encode("utf-8")
        with self.assertRaises(FirewallError):
            firewall.accept_tools_list_response(
                b'{"jsonrpc":"2.0","id":"'
                + correct_id
                + b'","id":"'
                + correct_id
                + b'","result":{"tools":[]}}'
            )
        firewall = ready_for_tools()
        with self.assertRaises(FirewallError):
            firewall.accept_tools_list_response(b"{" + b" " * (16 * 1024))
        firewall = ready_for_tools()
        with self.assertRaises(FirewallError):
            firewall.accept_tools_list_response(
                b'{"jsonrpc":"2.0","id":' + b"9" * 5000 + b',"result":{"tools":[]}}'
            )

    def test_probe_request_is_exact_contract_request(self):
        second = ready_for_tools()
        second.accept_tools_list_response(
            tools_response(second, copy.deepcopy(EXPECTED_VENDOR_TOOL_DEFINITION))
        )
        payload = second.build_probe_request()
        envelope = json.loads(payload)
        query = next(
            item
            for item in second._contract["query_templates"]
            if item["stable_candidate_id"]
            == second._contract["tool_policy"]["future_single_probe_candidate_id"]
        )
        expected = {
            "jsonrpc": "2.0",
            "id": second._probe_id,
            "method": "tools/call",
            "params": {
                "name": "find_assets",
                "arguments": query["arguments"],
            },
        }
        self.assertEqual(envelope, expected)
        self.assertEqual(payload, canonical_json_bytes(expected))

    def test_probe_response_requires_exact_one_text_result_and_identity(self):
        firewall = ready_for_probe()
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
        response = {
            "jsonrpc": "2.0",
            "id": firewall._probe_id,
            "result": {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(inner, separators=(",", ":")),
                    }
                ]
            },
        }
        self.assertEqual(
            firewall.accept_probe_response(canonical_json_bytes(response)),
            query["expected_result"],
        )
        self.assertEqual(firewall.state, FirewallState.COMPLETE)

        for mutate in (
            lambda value: value.update({"id": "wrong"}),
            lambda value: value["result"].update({"isError": False}),
            lambda value: value["result"]["content"][0].update({"type": "image"}),
            lambda value: value["result"]["content"][0].update({"text": "{}"}),
        ):
            failed = ready_for_probe()
            candidate = copy.deepcopy(response)
            candidate["id"] = failed._probe_id
            mutate(candidate)
            with self.assertRaises(FirewallError):
                failed.accept_probe_response(canonical_json_bytes(candidate))
            self.assertEqual(failed.state, FirewallState.FAILED)

    def test_probe_response_unexpected_validator_exception_fails_closed(self):
        for hostile_exception in (
            RecursionError("nested input"),
            UnicodeEncodeError("utf-8", "\ud800", 0, 1, "surrogate"),
            RuntimeError("unexpected validator failure"),
        ):
            with self.subTest(exception=type(hostile_exception).__name__):
                firewall = ready_for_probe()
                with patch(
                    "Tools.redmmo_nwiro_predispatch_firewall."
                    "validate_future_probe_jsonrpc_response_bytes",
                    side_effect=hostile_exception,
                ):
                    with self.assertRaises(FirewallError):
                        firewall.accept_probe_response(b"{}")
                self.assertEqual(firewall.state, FirewallState.FAILED)

    def test_report_reauthenticates_immediately_before_publication(self):
        firewall = NwiroPredispatchFirewall()
        report = _synthetic_transcript(firewall)
        self.assertEqual(report["status"], "synthetic_transcript_valid")
        with patch(
            "Tools.redmmo_nwiro_predispatch_firewall."
            "reauthenticate_before_publication",
            side_effect=NwiroContractError("drift"),
        ):
            with self.assertRaises(FirewallError):
                firewall.redacted_report()
        self.assertEqual(firewall.state, FirewallState.FAILED)

    def test_synthetic_transcript_report_is_redacted_and_static(self):
        firewall = NwiroPredispatchFirewall()
        report = _synthetic_transcript(firewall)
        self.assertEqual(report["status"], "synthetic_transcript_valid")
        self.assertEqual(report["evidence_class"], "static")
        self.assertFalse(report["network_or_mcp_execution"])
        self.assertFalse(report["runtime_send_authorized"])
        self.assertFalse(report["raw_mcp_direct_path_blocked"])
        self.assertFalse(report["acp_direct_dispatch_blocked"])
        self.assertFalse(report["runtime_tool_registry_generation_bound"])
        self.assertFalse(report["mcp_initialized_notification_verified"])
        self.assertFalse(report["exclusive_single_process_lock_verified"])
        self.assertFalse(report["headless_permission_bypass_fixed"])
        self.assertFalse(report["bridge_null_provider_bypass_fixed"])
        self.assertFalse(report["vendor_auto_config_publication_disabled"])
        self.assertEqual(report["trusted_hardened_server_binary_count"], 0)
        self.assertEqual(
            [record["phase"] for record in report["phase_transcript"]],
            [
                "initialize_request",
                "initialize_response",
                "tools_list_request",
                "tools_list_response",
                "probe_request",
                "probe_response",
            ],
        )
        rendered = json.dumps(report, sort_keys=True)
        self.assertNotIn("description", rendered)
        self.assertNotIn("/Game/", rendered)
        self.assertNotIn('"name"', rendered)
        self.assertNotIn('"path"', rendered)
        self.assertNotIn('"class"', rendered)
        report["phase_transcript"][0]["phase"] = "tampered"
        second_report = firewall.redacted_report()
        self.assertEqual(
            second_report["phase_transcript"][0]["phase"], "initialize_request"
        )


if __name__ == "__main__":
    unittest.main()
