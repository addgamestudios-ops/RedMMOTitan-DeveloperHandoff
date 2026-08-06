from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import Tools.validate_redmmo_nwiro_metadata_dry_run as nwiro
from Tools.validate_redmmo_nwiro_metadata_dry_run import (
    NwiroContractError,
    authenticate_contract_inputs,
    build_report,
    load_json_strict,
    report_json_bytes,
    reauthenticate_before_publication,
    validate_find_assets_tool_definition,
    validate_contract_file,
    validate_contract_schema,
    validate_future_probe_jsonrpc_request,
    validate_future_probe_jsonrpc_request_bytes,
    validate_future_probe_jsonrpc_response,
    validate_future_probe_jsonrpc_response_bytes,
    validate_future_probe_request,
    validate_future_probe_response,
    validate_output_path,
    write_report_no_clobber,
)


CONTRACT_PATH = Path(
    r"D:\RedMMOTitan\Build\Automation"
    r"\redmmo_nwiro_metadata_dry_run_contract_v1.json"
)


def _contract() -> dict[str, object]:
    return copy.deepcopy(load_json_strict(CONTRACT_PATH))


class RedMMONwiroMetadataDryRunContractTests(unittest.TestCase):
    def test_canonical_contract_schema_and_all_inputs_authenticate(self):
        contract, payload, authenticated = validate_contract_file(CONTRACT_PATH)
        self.assertEqual(contract["status"], "static_dry_run_only")
        self.assertEqual(payload, CONTRACT_PATH.read_bytes())
        self.assertEqual(len(authenticated), 11)
        self.assertEqual(
            {record["kind"] for record in authenticated},
            {
                "uproject",
                "plugin_descriptor",
                "plugin_binary",
                "plugin_source",
                "crosspack_request",
                "crosspack_manifest",
            },
        )

    def test_execution_and_runtime_states_cannot_be_enabled(self):
        for section, key in (
            ("execution", "execution_authorized"),
            ("execution", "unreal_launch_allowed"),
            ("execution", "mcp_initialize_allowed"),
            ("execution", "mcp_tool_call_allowed"),
            ("execution", "network_allowed"),
            ("execution", "provider_call_allowed"),
            ("execution", "asset_load_allowed"),
            ("execution", "map_or_actor_mutation_allowed"),
            ("source_selection", "nwiro_ready"),
            ("source_selection", "map_authoring_ready"),
            ("known_blockers", "tools_list_observed"),
            ("known_blockers", "real_gpu_acceptance_complete"),
        ):
            contract = _contract()
            contract[section][key] = True
            with self.assertRaises(NwiroContractError, msg=f"{section}.{key}"):
                validate_contract_schema(contract)
        contract = _contract()
        contract["execution"]["validator_diagnostic_report_publication_allowed"] = False
        with self.assertRaises(NwiroContractError):
            validate_contract_schema(contract)

    def test_allowlist_is_exact_singleton_and_unknowns_default_deny(self):
        contract = _contract()
        validate_contract_schema(contract)
        self.assertEqual(
            [item["tool_name"] for item in contract["tool_policy"]["allowlist"]],
            ["find_assets"],
        )
        self.assertEqual(contract["tool_policy"]["default_action"], "deny")
        self.assertEqual(contract["tool_policy"]["unknown_tools"], "deny")
        self.assertEqual(contract["tool_policy"]["unknown_namespaces"], "deny")

        contract["tool_policy"]["allowlist"].append(
            copy.deepcopy(contract["tool_policy"]["allowlist"][0])
        )
        contract["tool_policy"]["allowlist"][1]["tool_name"] = "read_asset"
        with self.assertRaises(NwiroContractError):
            validate_contract_schema(contract)

    def test_provider_and_mutation_denials_cannot_be_removed(self):
        for tool in (
            "generate_3d_model_meshy",
            "generate_texture_meshy",
            "generate_3d_model_tripo",
            "list_voices_elevenlabs",
            "generate_material_fal",
            "read_asset",
            "get_asset_thumbnail",
            "execute_python",
            "spawn_actor",
            "create_landscape",
            "paint_foliage",
            "pcg_generate",
        ):
            contract = _contract()
            contract["tool_policy"]["explicit_denied_tools"].remove(tool)
            with self.assertRaises(NwiroContractError, msg=tool):
                validate_contract_schema(contract)

    def test_query_arguments_are_exact_bounded_and_disabled(self):
        mutations = (
            lambda query: query.update({"execution_enabled": True}),
            lambda query: query["arguments"].update({"maxResults": 1}),
            lambda query: query["arguments"].update({"path": "/Game"}),
            lambda query: query["arguments"].update({"searchTerm": ""}),
            lambda query: query["arguments"].update({"classFilter": "Actor"}),
            lambda query: query["arguments"].update({"wildcard": "*"}),
            lambda query: query["expected_result"].update(
                {"path": "/Game/Zenscape_Savanna/Wrong.Wrong"}
            ),
        )
        for mutate in mutations:
            contract = _contract()
            mutate(contract["query_templates"][0])
            with self.assertRaises(NwiroContractError):
                validate_contract_schema(contract)

    def test_tropical_queries_remain_unmounted_and_unverified(self):
        contract = _contract()
        tropical = [
            item
            for item in contract["query_templates"]
            if item["pack_id"].endswith("934c1286-7388-4aa5-a300-e0a7cdf65675")
        ]
        self.assertEqual(len(tropical), 4)
        self.assertTrue(
            all(item["asset_files_present_in_active_project"] is False for item in tropical)
        )
        self.assertTrue(
            all(item["asset_registry_visibility_verified"] is False for item in tropical)
        )
        tropical[0]["asset_files_present_in_active_project"] = True
        with self.assertRaises(NwiroContractError):
            validate_contract_schema(contract)

    def test_manifest_candidate_identity_is_pinned_before_authentication(self):
        contract = _contract()
        validate_contract_schema(contract)
        contract["query_templates"][0]["stable_candidate_id"] = (
            "RED-FAB-ASSET-000000000000000000000000"
        )
        with self.assertRaises(NwiroContractError):
            validate_contract_schema(contract)

    def test_plugin_binary_and_source_contract_mutation_fails_before_io(self):
        for target_key in ("binary_file", "source_files"):
            contract = _contract()
            if target_key == "binary_file":
                contract["plugins"][0][target_key]["sha256"] = "A" * 64
            else:
                contract["plugins"][0][target_key][0]["sha256"] = "A" * 64
            with self.assertRaises(NwiroContractError):
                validate_contract_schema(contract)

    def test_noai_and_authority_cannot_be_relaxed(self):
        contract = _contract()
        contract["data_boundary"]["vendor_or_derived_bytes_may_be_uploaded"] = True
        with self.assertRaises(NwiroContractError):
            validate_contract_schema(contract)

        contract = _contract()
        contract["source_selection"][
            "source_reauthentication_required_before_runtime"
        ] = False
        with self.assertRaises(NwiroContractError):
            validate_contract_schema(contract)

    def test_unknown_fields_duplicate_keys_and_nonfinite_json_fail_closed(self):
        contract = _contract()
        contract["endpoint"] = "http://127.0.0.1:5353"
        with self.assertRaises(NwiroContractError):
            validate_contract_schema(contract)

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            duplicate = root / "duplicate.json"
            duplicate.write_text('{"schema_version":1,"schema_version":1}', "utf-8")
            with self.assertRaises(NwiroContractError):
                load_json_strict(duplicate)

            nonfinite = root / "nonfinite.json"
            nonfinite.write_text('{"value":NaN}', "utf-8")
            with self.assertRaises(NwiroContractError):
                load_json_strict(nonfinite)

    def test_authenticated_hash_mismatch_fails_before_report(self):
        contract = _contract()
        original = nwiro.read_snapshot

        def corrupt_project(path: Path, max_bytes: int) -> bytes:
            payload = original(path, max_bytes)
            if str(path).replace("\\", "/") == contract["project"]["uproject_path"]:
                return payload + b" "
            return payload

        with patch.object(nwiro, "read_snapshot", side_effect=corrupt_project):
            with self.assertRaises(NwiroContractError):
                authenticate_contract_inputs(contract)

    def test_report_states_only_static_nonexecution_evidence(self):
        contract, payload, authenticated = validate_contract_file(CONTRACT_PATH)
        report = build_report(contract, CONTRACT_PATH, payload, authenticated)
        self.assertEqual(report["evidence_class"], "static")
        self.assertEqual(report["policy"]["allowed_tools"], ["find_assets"])
        self.assertEqual(report["policy"]["enabled_query_count"], 0)
        self.assertTrue(all(value is False for value in report["observed"].values()))
        self.assertTrue(
            any("does not constrain raw NWIRO" in item for item in report["limitations"])
        )

    def test_report_publication_is_no_clobber_and_confined(self):
        contract, payload, authenticated = validate_contract_file(CONTRACT_PATH)
        report = build_report(contract, CONTRACT_PATH, payload, authenticated)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            output = root / "report.json"
            self.assertEqual(validate_output_path(output, root), output)
            write_report_no_clobber(output, report)
            self.assertTrue(output.is_file())
            with self.assertRaises(NwiroContractError):
                write_report_no_clobber(output, report)
            with self.assertRaises(NwiroContractError):
                validate_output_path(output, root)
            outside = root.parent / "outside-report.json"
            with self.assertRaises(NwiroContractError):
                validate_output_path(outside, root)

    def test_extra_query_does_not_gain_authority(self):
        contract = _contract()
        contract["query_templates"].append(copy.deepcopy(contract["query_templates"][0]))
        with self.assertRaises(NwiroContractError):
            validate_contract_schema(contract)

    def test_every_external_identity_is_independently_pinned(self):
        mutations = (
            lambda value: value["project"].update(
                {"uproject_path": "D:/RedMMOTitan/Alternate.uproject"}
            ),
            lambda value: value["project"].update({"uproject_sha256": "A" * 64}),
            lambda value: value["plugins"][0].update({"role": "alternate"}),
            lambda value: value["plugins"][0].update(
                {"descriptor_path": "D:/alternate/Nwiro.uplugin"}
            ),
            lambda value: value["plugins"][0]["binary_file"].update(
                {"path": "D:/alternate/UnrealEditor-Nwiro.dll"}
            ),
            lambda value: value["plugins"][1]["source_files"][0].update(
                {"path": "D:/alternate/NwiroIKMCPServer.cpp"}
            ),
            lambda value: value["source_selection"].update(
                {"request_path": "D:/alternate/request.json"}
            ),
            lambda value: value["source_selection"].update(
                {"manifest_sha256": "B" * 64}
            ),
            lambda value: value["source_selection"]["pack_source_tree_sha256"].update(
                {
                    "fab.12ec20bd-ce21-4d3d-8051-13ffb0fe851e": "C"
                    * 64
                }
            ),
            lambda value: value["query_templates"][0]["expected_result"].update(
                {
                    "path": (
                        "/Game/Zenscape_Savanna/Landscape/Texture/"
                        "T_Sand_basecolor_Alternate.T_Sand_basecolor_Alternate"
                    )
                }
            ),
        )
        for mutate in mutations:
            contract = _contract()
            mutate(contract)
            with self.assertRaises(NwiroContractError):
                validate_contract_schema(contract)

    def test_vendor_tool_definition_must_match_exact_observed_schema(self):
        definition = copy.deepcopy(nwiro.EXPECTED_VENDOR_TOOL_DEFINITION)
        validate_find_assets_tool_definition(definition)
        for mutate in (
            lambda value: value.update({"name": "find_static_meshes"}),
            lambda value: value.update({"description": "Search everything"}),
            lambda value: value["inputSchema"]["properties"].pop("path"),
            lambda value: value["inputSchema"]["properties"].update(
                {"extra": {"type": "string"}}
            ),
            lambda value: value["annotations"].update({"readOnlyHint": False}),
            lambda value: value["annotations"].update({"extra": True}),
            lambda value: value.update({"extra": "x"}),
        ):
            candidate = copy.deepcopy(definition)
            mutate(candidate)
            with self.assertRaises(NwiroContractError):
                validate_find_assets_tool_definition(candidate)

    def test_future_probe_request_firewall_is_exact_and_pure(self):
        contract = _contract()
        arguments = copy.deepcopy(contract["query_templates"][0]["arguments"])
        validate_future_probe_request(contract, "find_assets", arguments)
        for tool_name, mutate in (
            ("read_asset", lambda value: None),
            ("find_assets", lambda value: value.update({"maxResults": 1})),
            ("find_assets", lambda value: value.update({"path": "/Game"})),
            ("find_assets", lambda value: value.update({"extra": "x"})),
            ("find_assets", lambda value: value.update({"maxResults": 2.0})),
        ):
            candidate = copy.deepcopy(arguments)
            mutate(candidate)
            with self.assertRaises(NwiroContractError):
                validate_future_probe_request(contract, tool_name, candidate)

    def test_future_probe_response_firewall_requires_one_exact_identity(self):
        contract = _contract()
        expected = copy.deepcopy(contract["query_templates"][0]["expected_result"])
        response = {"success": True, "assets": [expected], "count": 1}
        self.assertEqual(
            validate_future_probe_response(contract, response),
            expected,
        )
        mutations = (
            lambda value: value.update({"success": False}),
            lambda value: value.update({"count": 0, "assets": []}),
            lambda value: value.update({"count": 2, "assets": [expected, expected]}),
            lambda value: value.update({"extra": "x"}),
            lambda value: value["assets"][0].update({"class": "Material"}),
            lambda value: value["assets"][0].update({"extra": "x"}),
            lambda value: value.update({"count": 1.0}),
        )
        for mutate in mutations:
            candidate = copy.deepcopy(response)
            mutate(candidate)
            with self.assertRaises(NwiroContractError):
                validate_future_probe_response(contract, candidate)

    def test_future_probe_jsonrpc_request_firewall_validates_raw_envelope(self):
        contract = _contract()
        arguments = copy.deepcopy(contract["query_templates"][0]["arguments"])
        request = {
            "jsonrpc": "2.0",
            "id": 7,
            "method": "tools/call",
            "params": {"name": "find_assets", "arguments": arguments},
        }
        validate_future_probe_jsonrpc_request(contract, request, 7)
        validate_future_probe_jsonrpc_request_bytes(
            contract, json.dumps(request).encode("utf-8"), 7
        )
        mutations = (
            lambda value: value.update({"jsonrpc": "1.0"}),
            lambda value: value.update({"id": 8}),
            lambda value: value.update({"id": "7"}),
            lambda value: value.update({"method": "tools/list"}),
            lambda value: value.update({"extra": "x"}),
            lambda value: value["params"].update({"extra": "x"}),
            lambda value: value["params"].update({"name": "read_asset"}),
        )
        for mutate in mutations:
            candidate = copy.deepcopy(request)
            mutate(candidate)
            with self.assertRaises(NwiroContractError):
                validate_future_probe_jsonrpc_request(contract, candidate, 7)
        with self.assertRaises(NwiroContractError):
            validate_future_probe_jsonrpc_request_bytes(
                contract,
                b'{"jsonrpc":"2.0","id":7,"id":7,"method":"tools/call","params":{}}',
                7,
            )

    def test_future_probe_jsonrpc_response_firewall_validates_text_content(self):
        contract = _contract()
        expected = copy.deepcopy(contract["query_templates"][0]["expected_result"])
        inner = {"success": True, "assets": [expected], "count": 1}
        response = {
            "jsonrpc": "2.0",
            "id": "probe-1",
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
            validate_future_probe_jsonrpc_response(contract, response, "probe-1"),
            expected,
        )
        self.assertEqual(
            validate_future_probe_jsonrpc_response_bytes(
                contract, json.dumps(response).encode("utf-8"), "probe-1"
            ),
            expected,
        )
        mutations = (
            lambda value: value.update({"id": "probe-2"}),
            lambda value: value.update({"error": {"code": -1}}),
            lambda value: value["result"].update({"isError": False}),
            lambda value: value["result"].update({"extra": "x"}),
            lambda value: value["result"].update({"content": []}),
            lambda value: value["result"]["content"].append(
                {"type": "text", "text": "{}"}
            ),
            lambda value: value["result"]["content"][0].update({"type": "image"}),
            lambda value: value["result"]["content"][0].update({"extra": "x"}),
            lambda value: value["result"]["content"][0].update({"text": "not-json"}),
        )
        for mutate in mutations:
            candidate = copy.deepcopy(response)
            mutate(candidate)
            with self.assertRaises(NwiroContractError):
                validate_future_probe_jsonrpc_response(
                    contract, candidate, "probe-1"
                )
        duplicate_inner = copy.deepcopy(response)
        duplicate_inner["result"]["content"][0]["text"] = (
            '{"success":true,"success":true,"assets":[],"count":0}'
        )
        with self.assertRaises(NwiroContractError):
            validate_future_probe_jsonrpc_response(
                contract, duplicate_inner, "probe-1"
            )

    def test_report_bytes_are_deterministic_and_reauthentication_is_stable(self):
        contract, payload, authenticated = validate_contract_file(CONTRACT_PATH)
        first = build_report(contract, CONTRACT_PATH, payload, authenticated)
        second = build_report(
            copy.deepcopy(contract),
            CONTRACT_PATH,
            bytes(payload),
            copy.deepcopy(authenticated),
        )
        self.assertEqual(report_json_bytes(first), report_json_bytes(second))
        reauthenticate_before_publication(
            CONTRACT_PATH, contract, payload, authenticated
        )

    def test_report_path_rejects_relative_and_missing_parent(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            with self.assertRaises(NwiroContractError):
                validate_output_path(Path("relative/report.json"), root)
            with self.assertRaises(NwiroContractError):
                validate_output_path(root / "missing" / "report.json", root)


if __name__ == "__main__":
    unittest.main()
