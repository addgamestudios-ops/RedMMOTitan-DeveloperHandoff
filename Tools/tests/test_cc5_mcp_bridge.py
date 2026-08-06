import ast
import asyncio
import builtins
import json
import sys
import tempfile
import threading
import time
import types
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from Tools.CC5MCP import protocol
from Tools.CC5MCP.cc5_plugin import bridge_core
from Tools.CC5MCP.cc5_plugin import windows_security


DATA_ROOT = Path(r"D:\RedMMOTitanWindowsData")
PROJECT_ROOT = Path(r"D:\RedMMOTitan")
TOKEN = "a1" * 32
PROJECT_IDENTITY = "b2" * 32


class CC5MCPBridgeTests(unittest.TestCase):
    def _load_plugin_main_without_autostart(self):
        path = (
            PROJECT_ROOT / "Tools" / "CC5MCP" / "cc5_plugin" / "main.py"
        )
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        self.assertIsInstance(tree.body[-1], ast.Expr)
        self.assertIsInstance(tree.body[-1].value, ast.Call)
        self.assertIsInstance(tree.body[-1].value.func, ast.Name)
        self.assertEqual(tree.body[-1].value.func.id, "run_script")
        tree.body.pop()
        ast.fix_missing_locations(tree)

        fake_rlpy = types.ModuleType("RLPy")

        class FakeTimerCallback:
            def __init__(self):
                pass

        class FakeEventCallback:
            def __init__(self):
                pass

        fake_rlpy.RPyTimerCallback = FakeTimerCallback
        fake_rlpy.REventCallback = FakeEventCallback
        previous_rlpy = sys.modules.get("RLPy")
        previous_bridge_core = sys.modules.get("bridge_core")
        sys.modules["RLPy"] = fake_rlpy
        sys.modules["bridge_core"] = bridge_core
        namespace = {
            "__name__": "cc5_plugin_main_test",
            "__package__": "",
        }
        try:
            exec(compile(tree, str(path), "exec"), namespace)
        finally:
            if previous_rlpy is None:
                del sys.modules["RLPy"]
            else:
                sys.modules["RLPy"] = previous_rlpy
            if previous_bridge_core is None:
                del sys.modules["bridge_core"]
            else:
                sys.modules["bridge_core"] = previous_bridge_core
        return namespace

    def _raw_config(self, root, enabled=True):
        return {
            "enabled": enabled,
            "queue_root": str(root / "queue"),
            "save_root": str(root / "versions"),
            "bridge_token": TOKEN,
            "request_timeout_seconds": 1.5,
            "poll_interval_seconds": 0.05,
            "max_message_bytes": 65536,
            "morph_allowlist": {
                "reviewed_head": {
                    "morph_id": "CC5/Reviewed/Head",
                    "minimum": -10.0,
                    "maximum": 10.0,
                    "label": "Reviewed head test",
                }
            },
            "linked_presets": {},
        }

    def _raw_config_with_linked_preset(self, root):
        raw = self._raw_config(root)
        raw["morph_allowlist"]["reviewed_body"] = {
            "morph_id": "CC5/Reviewed/Body",
            "minimum": -10.0,
            "maximum": 100.0,
            "label": "Reviewed Brute body",
        }
        raw["linked_presets"] = {
            "brute_balanced": {
                "required_character_signature": "c3" * 32,
                "label": "Reviewed Brute body and head pair",
                "body": {
                    "morph_alias": "reviewed_body",
                    "value": 30.0,
                },
                "head": {
                    "morph_alias": "reviewed_head",
                    "value": 4.0,
                },
            }
        }
        return raw

    def _create_runtime_dirs(self, root):
        for path in (
            root / "queue" / "requests",
            root / "queue" / "processing",
            root / "queue" / "responses",
            root / "queue" / "completed",
            root / "queue" / "quarantine",
            root / "queue" / "status",
            root / "versions",
        ):
            path.mkdir(parents=True, exist_ok=True)

    def test_config_accepts_confined_d_storage_and_exact_allowlist(self):
        with tempfile.TemporaryDirectory(dir=DATA_ROOT) as temp:
            root = Path(temp)
            config = protocol.BridgeConfig.from_mapping(
                self._raw_config(root),
                allowed_storage_root=root,
            )
            self.assertTrue(config.enabled)
            self.assertEqual(config.bridge_token, TOKEN)
            self.assertEqual(
                config.morph_allowlist["reviewed_head"].morph_id,
                "CC5/Reviewed/Head",
            )

    def test_config_rejects_storage_outside_allowed_root(self):
        with tempfile.TemporaryDirectory(dir=DATA_ROOT) as temp:
            root = Path(temp)
            raw = self._raw_config(root)
            raw["save_root"] = r"C:\unsafe\versions"
            with self.assertRaisesRegex(protocol.BridgeError, "outside"):
                protocol.BridgeConfig.from_mapping(
                    raw,
                    allowed_storage_root=root,
                )

    def test_config_rejects_bad_token_and_inverted_morph_range(self):
        with tempfile.TemporaryDirectory(dir=DATA_ROOT) as temp:
            root = Path(temp)
            raw = self._raw_config(root)
            raw["bridge_token"] = "not-a-token"
            with self.assertRaisesRegex(protocol.BridgeError, "64 hexadecimal"):
                protocol.BridgeConfig.from_mapping(
                    raw,
                    allowed_storage_root=root,
                )
            raw = self._raw_config(root)
            raw["morph_allowlist"]["reviewed_head"]["minimum"] = 20.0
            with self.assertRaisesRegex(protocol.BridgeError, "minimum"):
                protocol.BridgeConfig.from_mapping(
                    raw,
                    allowed_storage_root=root,
                )

    def test_linked_preset_requires_exact_distinct_allowlisted_pair(self):
        with tempfile.TemporaryDirectory(dir=DATA_ROOT) as temp:
            root = Path(temp)
            raw = self._raw_config_with_linked_preset(root)
            config = protocol.BridgeConfig.from_mapping(
                raw,
                allowed_storage_root=root,
            )
            preset = config.linked_presets["brute_balanced"]
            self.assertEqual(preset.body.morph_alias, "reviewed_body")
            self.assertEqual(preset.head.morph_alias, "reviewed_head")
            self.assertRegex(preset.definition_digest, r"^[0-9a-f]{64}$")

            unknown = self._raw_config_with_linked_preset(root)
            unknown["linked_presets"]["brute_balanced"]["head"][
                "morph_alias"
            ] = "not_approved"
            with self.assertRaisesRegex(protocol.BridgeError, "not allowlisted"):
                protocol.BridgeConfig.from_mapping(
                    unknown,
                    allowed_storage_root=root,
                )

            duplicate = self._raw_config_with_linked_preset(root)
            duplicate["linked_presets"]["brute_balanced"]["head"][
                "morph_alias"
            ] = "reviewed_body"
            with self.assertRaisesRegex(protocol.BridgeError, "distinct"):
                protocol.BridgeConfig.from_mapping(
                    duplicate,
                    allowed_storage_root=root,
                )

            out_of_range = self._raw_config_with_linked_preset(root)
            out_of_range["linked_presets"]["brute_balanced"]["body"][
                "value"
            ] = 101.0
            with self.assertRaisesRegex(protocol.BridgeError, "between"):
                protocol.BridgeConfig.from_mapping(
                    out_of_range,
                    allowed_storage_root=root,
                )

    def test_request_schema_is_expiring_authenticated_and_operation_allowlisted(self):
        with tempfile.TemporaryDirectory(dir=DATA_ROOT) as temp:
            root = Path(temp)
            config = protocol.BridgeConfig.from_mapping(
                self._raw_config(root),
                allowed_storage_root=root,
            )
            now = datetime.now(timezone.utc)
            request = protocol.build_request(
                config,
                "set_approved_morph",
                {
                    "expected_character_id": "1234",
                    "expected_project_identity": PROJECT_IDENTITY,
                    "morph_alias": "reviewed_head",
                    "value": 2.5,
                },
                now=now,
            )
            validated = protocol.validate_request(request, config, now=now)
            self.assertEqual(validated["operation"], "set_approved_morph")
            self.assertNotIn("path", validated["payload"])

            bad = dict(request)
            bad["request_mac"] = "b2" * 32
            with self.assertRaisesRegex(protocol.BridgeError, "authentication"):
                protocol.validate_request(bad, config, now=now)

            with self.assertRaisesRegex(protocol.BridgeError, "allowlisted"):
                protocol.build_request(config, "execute_python", {})

    def test_payloads_reject_extra_fields_paths_and_bulk_mutation(self):
        with self.assertRaisesRegex(protocol.BridgeError, "exactly"):
            protocol.validate_payload(
                "save_project_as",
                {"version_name": "safe", "path": r"D:\elsewhere"},
            )
        with self.assertRaisesRegex(protocol.BridgeError, "exactly"):
            protocol.validate_payload(
                "set_approved_morph",
                {
                    "expected_character_id": "1234",
                    "expected_project_identity": PROJECT_IDENTITY,
                    "morph_alias": "reviewed_head",
                    "value": 1.0,
                    "second_morph": "bulk-not-permitted",
                },
            )

    def test_version_name_is_simple_non_overwriting_name(self):
        self.assertEqual(protocol.validate_version_name("Brute_Test_01"), "Brute_Test_01")
        for invalid in (
            r"..\escape",
            "nested/name",
            "name.ccProject",
            "",
            "..",
        ):
            with self.subTest(invalid=invalid):
                with self.assertRaises(protocol.BridgeError):
                    protocol.validate_version_name(invalid)

    def test_filesystem_queue_round_trip(self):
        with tempfile.TemporaryDirectory(dir=DATA_ROOT) as temp:
            root = Path(temp)
            config = protocol.BridgeConfig.from_mapping(
                self._raw_config(root),
                allowed_storage_root=root,
            )
            self._create_runtime_dirs(root)
            client = protocol.QueueBridgeClient(config)
            observed = {}

            def responder():
                deadline = time.monotonic() + 1.0
                while time.monotonic() < deadline:
                    requests = list(client.requests_dir.glob("*.request.json"))
                    if requests:
                        request = protocol.read_json_limited(
                            requests[0],
                            config.max_message_bytes,
                        )
                        protocol.validate_request(request, config)
                        observed.update(request)
                        response = {
                            "protocol_version": protocol.PROTOCOL_VERSION,
                            "request_id": request["request_id"],
                            "operation": request["operation"],
                            "ok": True,
                            "completed_utc": protocol.format_utc(
                                datetime.now(timezone.utc)
                            ),
                            "result": {"character": {"name": "OfflineTest"}},
                            "error": None,
                        }
                        response["response_mac"] = protocol.message_mac(
                            response,
                            config.bridge_token,
                        )
                        protocol.atomic_write_json(
                            client.responses_dir
                            / (request["request_id"] + ".response.json"),
                            response,
                            config.max_message_bytes,
                        )
                        return
                    time.sleep(0.01)

            with mock.patch.object(
                protocol,
                "_require_private_runtime_layout",
            ):
                thread = threading.Thread(target=responder, daemon=True)
                thread.start()
                result = client.call("inspect_active_character", {})
                thread.join(timeout=1.0)
            self.assertEqual(result["character"]["name"], "OfflineTest")
            self.assertEqual(observed["operation"], "inspect_active_character")

    def test_response_authentication_rejects_local_forgery(self):
        with tempfile.TemporaryDirectory(dir=DATA_ROOT) as temp:
            root = Path(temp)
            config = protocol.BridgeConfig.from_mapping(
                self._raw_config(root),
                allowed_storage_root=root,
            )
            request = protocol.build_request(
                config,
                "inspect_active_character",
                {},
            )
            response = {
                "protocol_version": protocol.PROTOCOL_VERSION,
                "request_id": request["request_id"],
                "operation": request["operation"],
                "ok": True,
                "completed_utc": protocol.format_utc(protocol.utc_now()),
                "result": {"character": {"name": "Forged"}},
                "error": None,
            }
            response["response_mac"] = "00" * 32
            with self.assertRaisesRegex(protocol.BridgeError, "authentication"):
                protocol.validate_response(response, request, config)

    def test_status_requires_valid_authentication(self):
        with tempfile.TemporaryDirectory(dir=DATA_ROOT) as temp:
            root = Path(temp)
            config = protocol.BridgeConfig.from_mapping(
                self._raw_config(root),
                allowed_storage_root=root,
            )
            self._create_runtime_dirs(root)
            client = protocol.QueueBridgeClient(config)
            status = {
                "protocol_version": protocol.PROTOCOL_VERSION,
                "state": "running",
                "heartbeat_utc": protocol.format_utc(protocol.utc_now()),
                "product_name": "Character Creator",
                "product_version": "5.11",
                "api_version": "test",
                "capabilities": {"avatar_shaping_component": True},
                "last_error": None,
                "requests_processed": 0,
            }
            status["status_mac"] = protocol.message_mac(
                status,
                config.bridge_token,
            )
            protocol.atomic_write_json(
                client.status_file,
                status,
                config.max_message_bytes,
            )
            with mock.patch.object(
                protocol,
                "_require_private_runtime_layout",
            ):
                self.assertTrue(client.read_status()["live"])

            status["state"] = "forged"
            protocol.atomic_write_json(
                client.status_file,
                status,
                config.max_message_bytes,
            )
            with mock.patch.object(
                protocol,
                "_require_private_runtime_layout",
            ):
                with self.assertRaisesRegex(protocol.BridgeError, "authentication"):
                    client.read_status()

    def test_plugin_core_matches_external_request_validation(self):
        with tempfile.TemporaryDirectory(dir=DATA_ROOT) as temp:
            root = Path(temp)
            raw = self._raw_config_with_linked_preset(root)
            config_path = root / "config.json"
            config_path.write_text(json.dumps(raw), encoding="utf-8")
            with (
                mock.patch.object(bridge_core, "ALLOWED_STORAGE_ROOT", root),
                mock.patch.object(
                    bridge_core,
                    "require_private_runtime_layout",
                ),
            ):
                plugin_config = bridge_core.load_config(config_path)
            external_config = protocol.BridgeConfig.from_mapping(
                raw,
                allowed_storage_root=root,
            )
            self.assertEqual(
                bridge_core.PROTOCOL_VERSION,
                protocol.PROTOCOL_VERSION,
            )
            self.assertEqual(
                plugin_config["linked_presets"]["brute_balanced"]["body"][
                    "morph_alias"
                ],
                external_config.linked_presets[
                    "brute_balanced"
                ].body.morph_alias,
            )
            self.assertEqual(
                plugin_config["linked_presets"]["brute_balanced"][
                    "definition_digest"
                ],
                external_config.linked_presets[
                    "brute_balanced"
                ].definition_digest,
            )
            request = protocol.build_request(
                external_config,
                "apply_approved_linked_preset",
                {
                    "expected_character_id": "42",
                    "expected_project_identity": PROJECT_IDENTITY,
                    "preset_alias": "brute_balanced",
                    "expected_preset_digest": external_config.linked_presets[
                        "brute_balanced"
                    ].definition_digest,
                },
            )
            self.assertEqual(
                bridge_core.validate_request(request, plugin_config)["request_id"],
                request["request_id"],
            )

    def test_plugin_save_target_is_confined_adds_extension_and_rejects_existing(self):
        with tempfile.TemporaryDirectory(dir=DATA_ROOT) as temp:
            root = Path(temp)
            config = {
                "save_root": root / "versions",
            }
            with mock.patch.object(bridge_core, "ALLOWED_STORAGE_ROOT", root):
                target = bridge_core.safe_save_target(config, "Version_001")
            self.assertEqual(target.name, "Version_001.ccProject")
            target.parent.mkdir(parents=True)
            target.write_bytes(b"existing")
            with self.assertRaisesRegex(
                bridge_core.BridgeValidationError, "already exists"
            ):
                with mock.patch.object(bridge_core, "ALLOWED_STORAGE_ROOT", root):
                    bridge_core.safe_save_target(config, "Version_001")

    def test_sources_have_no_network_shell_or_dynamic_code_surface(self):
        source_paths = [
            PROJECT_ROOT / "Tools" / "CC5MCP" / "protocol.py",
            PROJECT_ROOT / "Tools" / "CC5MCP" / "server.py",
            PROJECT_ROOT
            / "Tools"
            / "CC5MCP"
            / "cc5_plugin"
            / "bridge_core.py",
            PROJECT_ROOT / "Tools" / "CC5MCP" / "cc5_plugin" / "main.py",
            PROJECT_ROOT
            / "Tools"
            / "CC5MCP"
            / "cc5_plugin"
            / "windows_security.py",
        ]
        banned_modules = {
            "socket",
            "subprocess",
            "requests",
            "urllib",
            "http",
            "httpx",
            "ftplib",
            "telnetlib",
        }
        banned_calls = {"eval", "exec", "compile", "__import__"}
        for path in source_paths:
            with self.subTest(path=path):
                source = path.read_text(encoding="utf-8")
                tree = ast.parse(source)
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        imported = {alias.name.split(".")[0] for alias in node.names}
                        self.assertTrue(imported.isdisjoint(banned_modules))
                    elif isinstance(node, ast.ImportFrom) and node.module:
                        self.assertNotIn(node.module.split(".")[0], banned_modules)
                    elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                        self.assertNotIn(node.func.id, banned_calls)

    def test_cc5_plugin_source_parses_as_python_3_8(self):
        for name in ("bridge_core.py", "main.py", "windows_security.py"):
            source = (
                PROJECT_ROOT / "Tools" / "CC5MCP" / "cc5_plugin" / name
            ).read_text(encoding="utf-8")
            ast.parse(source, filename=name, feature_version=(3, 8))

    def test_server_is_stdio_only_and_never_imports_rlpy(self):
        source = (
            PROJECT_ROOT / "Tools" / "CC5MCP" / "server.py"
        ).read_text(encoding="utf-8")
        self.assertIn('mcp.run(transport="stdio")', source)
        self.assertNotIn('transport="sse"', source)
        self.assertNotIn('transport="streamable-http"', source)
        self.assertNotIn("import RLPy", source)

    def test_server_registers_only_the_six_narrow_tools(self):
        from Tools.CC5MCP import server

        registered = set(server.mcp._tool_manager._tools)
        self.assertEqual(
            registered,
            {
                "cc5_get_bridge_status",
                "cc5_inspect_active_character",
                "cc5_list_active_character_morphs",
                "cc5_set_approved_morph",
                "cc5_apply_approved_linked_preset",
                "cc5_save_project_as",
            },
        )
        for tool in server.mcp._tool_manager._tools.values():
            self.assertIs(tool.parameters.get("additionalProperties"), False)
        linked = server.mcp._tool_manager._tools[
            "cc5_apply_approved_linked_preset"
        ]
        self.assertEqual(
            set(linked.parameters["properties"]),
            {
                "expected_character_id",
                "expected_project_identity",
                "preset_alias",
            },
        )

    def test_server_rejects_extra_linked_preset_arguments_before_dispatch(self):
        from Tools.CC5MCP import server

        linked = server.mcp._tool_manager._tools[
            "cc5_apply_approved_linked_preset"
        ]

        async def invoke():
            return await linked.run(
                {
                    "expected_character_id": "42",
                    "expected_project_identity": PROJECT_IDENTITY,
                    "preset_alias": "brute_balanced",
                    "value": 100.0,
                    "expression": "ignored-before-this-fix",
                }
            )

        with self.assertRaisesRegex(Exception, "Extra inputs"):
            asyncio.run(invoke())

    def test_dependency_is_stable_mcp_v1_not_alpha(self):
        requirement = (
            PROJECT_ROOT / "Tools" / "CC5MCP" / "requirements.txt"
        ).read_text(encoding="utf-8")
        self.assertIn("mcp==1.28.1", requirement)
        self.assertNotIn("alpha", requirement.lower())
        self.assertNotIn("2.0.0", requirement)

    def test_mutations_require_character_and_project_bindings(self):
        payload = protocol.validate_payload(
            "set_approved_morph",
            {
                "expected_character_id": "42",
                "expected_project_identity": PROJECT_IDENTITY,
                "morph_alias": "reviewed_head",
                "value": 1.0,
            },
        )
        self.assertEqual(payload["expected_character_id"], "42")
        for missing in ("expected_character_id", "expected_project_identity"):
            malformed = dict(payload)
            malformed.pop(missing)
            with self.assertRaisesRegex(protocol.BridgeError, "exactly"):
                protocol.validate_payload("set_approved_morph", malformed)
        with self.assertRaises(protocol.BridgeError):
            protocol.validate_payload(
                "save_project_as",
                {
                    "expected_project_identity": "not-a-binding",
                    "version_name": "Version_01",
                },
            )

        linked = protocol.validate_payload(
            "apply_approved_linked_preset",
            {
                "expected_character_id": "42",
                "expected_project_identity": PROJECT_IDENTITY,
                "preset_alias": "brute_balanced",
                "expected_preset_digest": "d4" * 32,
            },
        )
        self.assertEqual(linked["preset_alias"], "brute_balanced")
        with self.assertRaisesRegex(protocol.BridgeError, "exactly"):
            protocol.validate_payload(
                "apply_approved_linked_preset",
                {
                    **linked,
                    "value": 50.0,
                },
            )

    def test_linked_preset_applies_pair_and_rolls_back_both_on_failure(self):
        namespace = self._load_plugin_main_without_autostart()
        signature = "c3" * 32

        class FakeAvatar:
            def GetName(self):
                return "CC3_Base_Plus"

            def GetID(self):
                return 42

        class FakeShaping:
            def __init__(self, fail_head=False):
                self.weights = {"Body/Exact": 10.0, "Head/Exact": 20.0}
                self.fail_head = fail_head
                self.writes = []

            def SetShapingMorphWeight(self, morph_id, value):
                if (
                    self.fail_head
                    and morph_id == "Head/Exact"
                    and float(value) == 40.0
                ):
                    raise RuntimeError("simulated head write failure")
                self.weights[morph_id] = float(value)
                self.writes.append((morph_id, float(value)))

            def GetShapingMorphWeight(self, morph_id):
                return self.weights[morph_id]

        class FakeGlobal:
            @staticmethod
            def ObjectModified(_avatar, _kind):
                pass

        avatar = FakeAvatar()
        namespace["RLPy"].RGlobal = FakeGlobal
        namespace["RLPy"].EObjectModifiedType_MorphWeight = object()
        namespace["_active_avatar"] = lambda: avatar
        namespace["_require_operation_binding"] = lambda *_args: None
        namespace["_character_signature"] = lambda *_args: signature
        duplicate_rows = [
            {
                "category": "Actor/Body/HD Caricature Mixer",
                "morph_id": "Body/Exact",
                "display_name": "Brute_Body Ratio",
                "minimum": -10.0,
                "maximum": 100.0,
                "value": 10.0,
                "approved_aliases": ["brute_body"],
            },
            {
                "category": "Actor/Body/HD Caricature Mixer/Body Ratio",
                "morph_id": "Body/Exact",
                "display_name": "Brute_Body Ratio",
                "minimum": -10.0,
                "maximum": 100.0,
                "value": 10.0,
                "approved_aliases": ["brute_body"],
            },
            {
                "category": "Actor/Head/HD Caricature Mixer",
                "morph_id": "Head/Exact",
                "display_name": "Brute_Head Shape",
                "minimum": -10.0,
                "maximum": 100.0,
                "value": 20.0,
                "approved_aliases": ["brute_head"],
            },
            {
                "category": "Actor/Head/HD Caricature Mixer/Head Shape",
                "morph_id": "Head/Exact",
                "display_name": "Brute_Head Shape",
                "minimum": -10.0,
                "maximum": 100.0,
                "value": 20.0,
                "approved_aliases": ["brute_head"],
            },
        ]
        namespace["_all_slider_rows"] = lambda *_args: duplicate_rows
        namespace["_config"] = {
            "morph_allowlist": {
                "brute_body": {
                    "morph_id": "Body/Exact",
                    "minimum": -10.0,
                    "maximum": 100.0,
                    "label": "Brute body",
                },
                "brute_head": {
                    "morph_id": "Head/Exact",
                    "minimum": -10.0,
                    "maximum": 100.0,
                    "label": "Brute head",
                },
            },
            "linked_presets": {
                "brute_balanced": {
                    "required_character_signature": signature,
                    "label": "Brute balanced",
                    "definition_digest": "d4" * 32,
                    "body": {
                        "morph_alias": "brute_body",
                        "value": 30.0,
                    },
                    "head": {
                        "morph_alias": "brute_head",
                        "value": 40.0,
                    },
                }
            },
        }
        payload = {
            "expected_character_id": "42",
            "expected_project_identity": PROJECT_IDENTITY,
            "preset_alias": "brute_balanced",
            "expected_preset_digest": "d4" * 32,
        }

        conflicting = [dict(row) for row in duplicate_rows]
        conflicting[1]["value"] = 11.0
        preflight_conflict = FakeShaping()
        namespace["_all_slider_rows"] = lambda *_args: conflicting
        namespace["_shaping_component"] = lambda _avatar: preflight_conflict
        with self.assertRaisesRegex(
            bridge_core.BridgeValidationError,
            "conflicting records",
        ):
            namespace["_apply_approved_linked_preset"](payload)
        self.assertEqual(preflight_conflict.writes, [])
        self.assertEqual(
            preflight_conflict.weights,
            {"Body/Exact": 10.0, "Head/Exact": 20.0},
        )

        missing_head = [
            row for row in duplicate_rows if row["morph_id"] != "Head/Exact"
        ]
        preflight_missing = FakeShaping()
        namespace["_all_slider_rows"] = lambda *_args: missing_head
        namespace["_shaping_component"] = lambda _avatar: preflight_missing
        with self.assertRaisesRegex(
            bridge_core.BridgeValidationError,
            "not found",
        ):
            namespace["_apply_approved_linked_preset"](payload)
        self.assertEqual(preflight_missing.writes, [])
        self.assertEqual(
            preflight_missing.weights,
            {"Body/Exact": 10.0, "Head/Exact": 20.0},
        )

        namespace["_all_slider_rows"] = lambda *_args: duplicate_rows
        success = FakeShaping()
        namespace["_shaping_component"] = lambda _avatar: success
        result = namespace["_apply_approved_linked_preset"](payload)
        self.assertEqual(success.weights["Body/Exact"], 30.0)
        self.assertEqual(success.weights["Head/Exact"], 40.0)
        self.assertEqual([item["role"] for item in result["changes"]], ["body", "head"])

        failure = FakeShaping(fail_head=True)
        namespace["_shaping_component"] = lambda _avatar: failure
        with self.assertRaisesRegex(
            bridge_core.BridgeValidationError,
            "rollback succeeded",
        ):
            namespace["_apply_approved_linked_preset"](payload)
        self.assertEqual(failure.weights["Body/Exact"], 10.0)
        self.assertEqual(failure.weights["Head/Exact"], 20.0)

        class MismatchedHeadReadbackShaping(FakeShaping):
            def __init__(self):
                FakeShaping.__init__(self)
                self.mismatch_pending = False

            def SetShapingMorphWeight(self, morph_id, value):
                FakeShaping.SetShapingMorphWeight(self, morph_id, value)
                if morph_id == "Head/Exact" and float(value) == 40.0:
                    self.mismatch_pending = True

            def GetShapingMorphWeight(self, morph_id):
                if morph_id == "Head/Exact" and self.mismatch_pending:
                    self.mismatch_pending = False
                    return 39.0
                return FakeShaping.GetShapingMorphWeight(self, morph_id)

        mismatch = MismatchedHeadReadbackShaping()
        namespace["_shaping_component"] = lambda _avatar: mismatch
        with self.assertRaises(bridge_core.BridgeValidationError) as raised:
            namespace["_apply_approved_linked_preset"](payload)
        self.assertEqual(raised.exception.code, "linked_preset_write_unverified")
        self.assertEqual(
            mismatch.writes,
            [
                ("Body/Exact", 30.0),
                ("Head/Exact", 40.0),
                ("Head/Exact", 20.0),
                ("Body/Exact", 10.0),
            ],
        )
        self.assertEqual(
            mismatch.weights,
            {"Body/Exact": 10.0, "Head/Exact": 20.0},
        )

        stale = dict(payload)
        stale["expected_preset_digest"] = "e5" * 32
        with self.assertRaisesRegex(
            bridge_core.BridgeValidationError,
            "changed after the external bridge",
        ):
            namespace["_apply_approved_linked_preset"](stale)
        self.assertEqual(failure.weights["Body/Exact"], 10.0)
        self.assertEqual(failure.weights["Head/Exact"], 20.0)

    def test_slider_row_resolver_rejects_missing_or_conflicting_duplicates(self):
        namespace = self._load_plugin_main_without_autostart()
        resolver = namespace["_resolve_canonical_slider_row"]
        body = {
            "category": "Actor/Body/HD Caricature Mixer",
            "morph_id": "Body/Exact",
            "display_name": "Brute_Body Ratio",
            "minimum": 0.0,
            "maximum": 1.0,
            "value": 1.0,
            "approved_aliases": ["brute_body"],
        }
        child = dict(
            body,
            category="Actor/Body/HD Caricature Mixer/Body Ratio",
        )
        resolved = resolver([body, child], "Body/Exact")
        self.assertEqual(
            resolved["categories"],
            [
                "Actor/Body/HD Caricature Mixer",
                "Actor/Body/HD Caricature Mixer/Body Ratio",
            ],
        )
        self.assertEqual(
            {
                key: value
                for key, value in resolved.items()
                if key != "categories"
            },
            {
                key: value
                for key, value in body.items()
                if key != "category"
            },
        )
        reversed_result = resolver([child, body], "Body/Exact")
        self.assertEqual(
            reversed_result["categories"],
            [
                "Actor/Body/HD Caricature Mixer/Body Ratio",
                "Actor/Body/HD Caricature Mixer",
            ],
        )

        with self.assertRaisesRegex(
            bridge_core.BridgeValidationError,
            "not found",
        ):
            resolver([body, child], "Missing/Exact")

        for malformed in (
            {},
            {"morph_id": ""},
            "not-a-row",
        ):
            with self.subTest(malformed=malformed):
                with self.assertRaisesRegex(
                    bridge_core.BridgeValidationError,
                    "shaping",
                ):
                    resolver([body, malformed], "Body/Exact")

        for field, conflicting_value in (
            ("display_name", "Different Name"),
            ("minimum", -1.0),
            ("maximum", 2.0),
            ("value", 0.5),
            ("approved_aliases", ["different_alias"]),
        ):
            with self.subTest(field=field):
                conflicting = dict(child)
                conflicting[field] = conflicting_value
                with self.assertRaisesRegex(
                    bridge_core.BridgeValidationError,
                    "conflicting records",
                ):
                    resolver([body, conflicting], "Body/Exact")

        incomplete = dict(child)
        incomplete.pop("display_name")
        with self.assertRaisesRegex(
            bridge_core.BridgeValidationError,
            "incomplete shaping record",
        ):
            resolver([body, incomplete], "Body/Exact")

        future_body = dict(body, future_host_field="alpha")
        future_child = dict(child, future_host_field="beta")
        with self.assertRaisesRegex(
            bridge_core.BridgeValidationError,
            "conflicting records",
        ):
            resolver([future_body, future_child], "Body/Exact")

    def test_all_slider_rows_rejects_untyped_host_names_before_string_coercion(self):
        namespace = self._load_plugin_main_without_autostart()
        namespace["_config"] = {"morph_allowlist": {}}

        class FakeHostRows:
            def __init__(self, category, morph_id, display_name):
                self.category = category
                self.morph_id = morph_id
                self.display_name = display_name

            def GetShapingMorphCatergoryNames(self):
                return [self.category]

            def GetShapingMorphIDs(self, _category):
                return [self.morph_id]

            def GetShapingMorphDisplayNames(self, _category):
                return [self.display_name]

            def GetShapingMorphMinMax(self, _morph_id):
                return (0.0, 1.0)

            def GetShapingMorphWeight(self, _morph_id):
                return 0.5

        malformed = (
            FakeHostRows(None, "Body/Exact", "Brute_Body Ratio"),
            FakeHostRows("Actor/Body", None, "Brute_Body Ratio"),
            FakeHostRows("Actor/Body", "Body/Exact", None),
        )
        for shaping in malformed:
            with self.subTest(
                category=shaping.category,
                morph_id=shaping.morph_id,
                display_name=shaping.display_name,
            ):
                with self.assertRaisesRegex(
                    bridge_core.BridgeValidationError,
                    "invalid shaping",
                ):
                    namespace["_all_slider_rows"](shaping, "")

    def test_set_approved_morph_accepts_identical_cross_category_rows(self):
        namespace = self._load_plugin_main_without_autostart()

        class FakeAvatar:
            def GetName(self):
                return "CC3_Base_Plus"

        class FakeShaping:
            def __init__(self):
                self.weights = {"Body/Exact": 0.25}
                self.writes = []

            def GetShapingMorphWeight(self, morph_id):
                return self.weights[morph_id]

            def SetShapingMorphWeight(self, morph_id, value):
                self.weights[morph_id] = float(value)
                self.writes.append((morph_id, float(value)))

        class FakeGlobal:
            @staticmethod
            def ObjectModified(_avatar, _kind):
                pass

        avatar = FakeAvatar()
        namespace["RLPy"].RGlobal = FakeGlobal
        namespace["RLPy"].EObjectModifiedType_MorphWeight = object()
        namespace["_active_avatar"] = lambda: avatar
        namespace["_require_operation_binding"] = lambda *_args: None
        duplicate_rows = [
            {
                "category": "Actor/Body/HD Caricature Mixer",
                "morph_id": "Body/Exact",
                "display_name": "Brute_Body Ratio",
                "minimum": 0.0,
                "maximum": 1.0,
                "value": 0.25,
                "approved_aliases": ["brute_body"],
            },
            {
                "category": "Actor/Body/HD Caricature Mixer/Body Ratio",
                "morph_id": "Body/Exact",
                "display_name": "Brute_Body Ratio",
                "minimum": 0.0,
                "maximum": 1.0,
                "value": 0.25,
                "approved_aliases": ["brute_body"],
            },
        ]
        namespace["_config"] = {
            "morph_allowlist": {
                "brute_body": {
                    "morph_id": "Body/Exact",
                    "minimum": 0.0,
                    "maximum": 1.0,
                    "label": "Brute body",
                }
            },
            "linked_presets": {},
        }
        payload = {
            "expected_character_id": "42",
            "expected_project_identity": PROJECT_IDENTITY,
            "morph_alias": "brute_body",
            "value": 0.75,
        }

        conflict_rows = [dict(row) for row in duplicate_rows]
        conflict_rows[1]["display_name"] = "Conflicting Body"
        conflict = FakeShaping()
        namespace["_all_slider_rows"] = lambda *_args: conflict_rows
        namespace["_shaping_component"] = lambda _avatar: conflict
        with self.assertRaisesRegex(
            bridge_core.BridgeValidationError,
            "conflicting records",
        ):
            namespace["_set_approved_morph"](payload)
        self.assertEqual(conflict.writes, [])
        self.assertEqual(conflict.weights, {"Body/Exact": 0.25})

        missing_rows = [
            dict(
                duplicate_rows[0],
                category="Actor/Body/Other",
                morph_id="Other/Exact",
            )
        ]
        missing = FakeShaping()
        namespace["_all_slider_rows"] = lambda *_args: missing_rows
        namespace["_shaping_component"] = lambda _avatar: missing
        with self.assertRaisesRegex(
            bridge_core.BridgeValidationError,
            "not found",
        ):
            namespace["_set_approved_morph"](payload)
        self.assertEqual(missing.writes, [])
        self.assertEqual(missing.weights, {"Body/Exact": 0.25})

        shaping = FakeShaping()
        namespace["_all_slider_rows"] = lambda *_args: duplicate_rows
        namespace["_shaping_component"] = lambda _avatar: shaping
        result = namespace["_set_approved_morph"](payload)
        self.assertEqual(shaping.writes, [("Body/Exact", 0.75)])
        self.assertEqual(result["previous_value"], 0.25)
        self.assertEqual(result["value"], 0.75)
        self.assertEqual(
            set(result),
            {
                "character_name",
                "morph_alias",
                "morph_id",
                "label",
                "previous_value",
                "value",
            },
        )

        class MismatchedReadbackShaping(FakeShaping):
            def __init__(self):
                FakeShaping.__init__(self)
                self.mismatch_pending = False

            def SetShapingMorphWeight(self, morph_id, value):
                FakeShaping.SetShapingMorphWeight(self, morph_id, value)
                if float(value) == 0.75:
                    self.mismatch_pending = True

            def GetShapingMorphWeight(self, morph_id):
                if self.mismatch_pending:
                    self.mismatch_pending = False
                    return 0.5
                return FakeShaping.GetShapingMorphWeight(self, morph_id)

        mismatch = MismatchedReadbackShaping()
        namespace["_shaping_component"] = lambda _avatar: mismatch
        with self.assertRaises(bridge_core.BridgeValidationError) as raised:
            namespace["_set_approved_morph"](payload)
        self.assertEqual(raised.exception.code, "morph_write_unverified")
        self.assertEqual(
            mismatch.writes,
            [("Body/Exact", 0.75), ("Body/Exact", 0.25)],
        )
        self.assertEqual(mismatch.weights, {"Body/Exact": 0.25})

    def test_linked_preset_rejects_nonfinite_readback_and_restores_or_refuses(self):
        namespace = self._load_plugin_main_without_autostart()
        signature = "c3" * 32

        class FakeAvatar:
            def GetName(self):
                return "CC3_Base_Plus"

            def GetID(self):
                return 42

        class NonfiniteReadbackShaping:
            def __init__(self):
                self.weights = {"Body/Exact": 10.0, "Head/Exact": 20.0}
                self.after_write = False

            def SetShapingMorphWeight(self, _morph_id, _value):
                self.after_write = True

            def GetShapingMorphWeight(self, morph_id):
                if self.after_write:
                    return float("nan")
                return self.weights[morph_id]

        class FakeGlobal:
            @staticmethod
            def ObjectModified(_avatar, _kind):
                pass

        avatar = FakeAvatar()
        shaping = NonfiniteReadbackShaping()
        namespace["RLPy"].RGlobal = FakeGlobal
        namespace["RLPy"].EObjectModifiedType_MorphWeight = object()
        namespace["_active_avatar"] = lambda: avatar
        namespace["_require_operation_binding"] = lambda *_args: None
        namespace["_character_signature"] = lambda *_args: signature
        namespace["_shaping_component"] = lambda _avatar: shaping
        namespace["_all_slider_rows"] = lambda *_args: [
            {
                "category": "Actor/Body/HD Caricature Mixer/Body Ratio",
                "morph_id": "Body/Exact",
                "display_name": "Brute_Body Ratio",
                "minimum": -10.0,
                "maximum": 100.0,
                "value": 10.0,
                "approved_aliases": ["brute_body"],
            },
            {
                "category": "Actor/Head/HD Caricature Mixer/Head Shape",
                "morph_id": "Head/Exact",
                "display_name": "Brute_Head Shape",
                "minimum": -10.0,
                "maximum": 100.0,
                "value": 20.0,
                "approved_aliases": ["brute_head"],
            },
        ]
        namespace["_config"] = {
            "morph_allowlist": {
                "brute_body": {
                    "morph_id": "Body/Exact",
                    "minimum": -10.0,
                    "maximum": 100.0,
                    "label": "Brute body",
                },
                "brute_head": {
                    "morph_id": "Head/Exact",
                    "minimum": -10.0,
                    "maximum": 100.0,
                    "label": "Brute head",
                },
            },
            "linked_presets": {
                "brute_balanced": {
                    "required_character_signature": signature,
                    "label": "Brute balanced",
                    "definition_digest": "d4" * 32,
                    "body": {"morph_alias": "brute_body", "value": 30.0},
                    "head": {"morph_alias": "brute_head", "value": 40.0},
                }
            },
        }
        payload = {
            "expected_character_id": "42",
            "expected_project_identity": PROJECT_IDENTITY,
            "preset_alias": "brute_balanced",
            "expected_preset_digest": "d4" * 32,
        }
        with self.assertRaisesRegex(
            bridge_core.BridgeValidationError,
            "could not be verified",
        ):
            namespace["_apply_approved_linked_preset"](payload)
        self.assertEqual(shaping.weights["Body/Exact"], 10.0)
        self.assertEqual(shaping.weights["Head/Exact"], 20.0)

    def test_linked_preset_caches_response_metadata_before_writes(self):
        namespace = self._load_plugin_main_without_autostart()
        signature = "c3" * 32

        class OneReadAvatar:
            def __init__(self):
                self.name_reads = 0
                self.id_reads = 0

            def GetName(self):
                self.name_reads += 1
                if self.name_reads > 1:
                    raise RuntimeError("metadata read after mutation")
                return "CC3_Base_Plus"

            def GetID(self):
                self.id_reads += 1
                if self.id_reads > 1:
                    raise RuntimeError("metadata read after mutation")
                return 42

        class FakeShaping:
            def __init__(self):
                self.weights = {"Body/Exact": 10.0, "Head/Exact": 20.0}

            def SetShapingMorphWeight(self, morph_id, value):
                self.weights[morph_id] = float(value)

            def GetShapingMorphWeight(self, morph_id):
                return self.weights[morph_id]

        class FakeGlobal:
            @staticmethod
            def ObjectModified(_avatar, _kind):
                pass

        avatar = OneReadAvatar()
        shaping = FakeShaping()
        namespace["RLPy"].RGlobal = FakeGlobal
        namespace["RLPy"].EObjectModifiedType_MorphWeight = object()
        namespace["_active_avatar"] = lambda: avatar
        namespace["_require_operation_binding"] = lambda *_args: None
        namespace["_character_signature"] = lambda *_args: signature
        namespace["_shaping_component"] = lambda _avatar: shaping
        namespace["_all_slider_rows"] = lambda *_args: [
            {
                "category": "Actor/Body/HD Caricature Mixer/Body Ratio",
                "morph_id": "Body/Exact",
                "display_name": "Brute_Body Ratio",
                "minimum": -10.0,
                "maximum": 100.0,
                "value": 10.0,
                "approved_aliases": ["brute_body"],
            },
            {
                "category": "Actor/Head/HD Caricature Mixer/Head Shape",
                "morph_id": "Head/Exact",
                "display_name": "Brute_Head Shape",
                "minimum": -10.0,
                "maximum": 100.0,
                "value": 20.0,
                "approved_aliases": ["brute_head"],
            },
        ]
        namespace["_config"] = {
            "morph_allowlist": {
                "brute_body": {
                    "morph_id": "Body/Exact",
                    "minimum": -10.0,
                    "maximum": 100.0,
                    "label": "Brute body",
                },
                "brute_head": {
                    "morph_id": "Head/Exact",
                    "minimum": -10.0,
                    "maximum": 100.0,
                    "label": "Brute head",
                },
            },
            "linked_presets": {
                "brute_balanced": {
                    "required_character_signature": signature,
                    "label": "Brute balanced",
                    "definition_digest": "d4" * 32,
                    "body": {"morph_alias": "brute_body", "value": 30.0},
                    "head": {"morph_alias": "brute_head", "value": 40.0},
                }
            },
        }
        result = namespace["_apply_approved_linked_preset"](
            {
                "expected_character_id": "42",
                "expected_project_identity": PROJECT_IDENTITY,
                "preset_alias": "brute_balanced",
                "expected_preset_digest": "d4" * 32,
            }
        )
        self.assertEqual(result["character_name"], "CC3_Base_Plus")
        self.assertEqual(result["character_object_id"], "42")
        self.assertEqual(avatar.name_reads, 1)
        self.assertEqual(avatar.id_reads, 1)

    def test_windows_publication_never_replaces_existing_target(self):
        with tempfile.TemporaryDirectory(dir=DATA_ROOT) as temp:
            root = Path(temp)
            source = root / "source.ccProject"
            target = root / "target.ccProject"
            source.write_bytes(b"new")
            target.write_bytes(b"existing")
            with self.assertRaises(FileExistsError):
                windows_security.publish_file_no_replace(source, target)
            self.assertEqual(target.read_bytes(), b"existing")
            self.assertEqual(source.read_bytes(), b"new")

    def test_enabled_client_rechecks_private_runtime_layout(self):
        with tempfile.TemporaryDirectory(dir=DATA_ROOT) as temp:
            root = Path(temp)
            config = protocol.BridgeConfig.from_mapping(
                self._raw_config(root),
                allowed_storage_root=root,
            )
            client = protocol.QueueBridgeClient(config)
            with mock.patch.object(
                protocol,
                "_require_private_runtime_layout",
                side_effect=protocol.BridgeError(
                    "storage_security_invalid",
                    "private ACL required",
                ),
            ) as check:
                with self.assertRaisesRegex(protocol.BridgeError, "private ACL"):
                    client.call("inspect_active_character", {})
                check.assert_called_once()

    def test_storage_root_reparse_resolution_is_rejected(self):
        with tempfile.TemporaryDirectory(dir=DATA_ROOT) as temp:
            root = Path(temp)
            outside = Path(r"C:\outside")
            real_realpath = windows_security.os.path.realpath

            def redirected(value):
                if windows_security._normal(value) == windows_security._normal(root):
                    return str(outside)
                return real_realpath(value)

            with mock.patch.object(
                windows_security.os.path,
                "realpath",
                side_effect=redirected,
            ):
                with self.assertRaisesRegex(
                    windows_security.WindowsSecurityError,
                    "reparse",
                ):
                    windows_security.secure_storage_path(
                        root,
                        storage_root=root,
                        allow_root=True,
                    )

    def test_acl_checker_rejects_shared_project_data_parent(self):
        with self.assertRaises(windows_security.WindowsSecurityError):
            windows_security.require_private_windows_acl(
                DATA_ROOT,
                require_protected=True,
            )

    def test_plugin_failure_paths_preserve_bound_snapshot_and_restore_morph(self):
        source = (
            PROJECT_ROOT / "Tools" / "CC5MCP" / "cc5_plugin" / "main.py"
        ).read_text(encoding="utf-8")
        save_start = source.index("def _save_project_as")
        save_end = source.index("\ndef _queue_dirs", save_start)
        save_source = source[save_start:save_end]
        save_call = save_source.index("RLPy.RFileIO.SaveProject")
        binding_check = save_source.index(
            "source_path_after = _current_project_path()",
            save_call,
        )
        copy_call = save_source.index("shutil.copyfileobj", save_call)
        self.assertLess(binding_check, copy_call)
        self.assertIn("bound_to_staging", save_source)
        self.assertIn("staging_owned", save_source)
        self.assertIn("publish_temp_owned", save_source)
        self.assertIn("binding_known", save_source)
        self.assertIn("bridge_core.cleanup_owned_file", save_source)

        morph_start = source.index("def _set_approved_morph")
        morph_end = source.index("\ndef _save_project_as", morph_start)
        morph_source = source[morph_start:morph_end]
        self.assertGreaterEqual(morph_source.count("_restore_morph_value("), 2)
        self.assertIn("morph_state_uncertain", morph_source)

    def test_idle_heartbeat_is_throttled_and_operation_revalidation_remains(self):
        source = (
            PROJECT_ROOT / "Tools" / "CC5MCP" / "cc5_plugin" / "main.py"
        ).read_text(encoding="utf-8")
        self.assertGreaterEqual(
            source.count("bridge_core.interval_due("),
            2,
        )
        process_start = source.index("def _process_one_request")
        process_end = source.index("\nclass _BridgeTimerCallback", process_start)
        process_source = source[process_start:process_end]
        self.assertIn(
            "bridge_core.require_private_runtime_layout(_config)",
            process_source,
        )
        self.assertNotIn(
            "if processed or bridge_core.interval_due(",
            source,
        )

    def test_timer_success_heartbeat_is_coalesced_after_processed_request(self):
        namespace = self._load_plugin_main_without_autostart()
        writes = []
        times = iter((10.0, 10.6))
        namespace["_last_status_write"] = 9.5
        namespace["_accepting_requests"] = True
        namespace["_refresh_project_epoch"] = lambda: None
        namespace["_process_one_request"] = lambda: True
        namespace["_write_status"] = lambda *args, **kwargs: writes.append(
            (args, kwargs)
        )
        namespace["time"] = mock.Mock(monotonic=lambda: next(times))
        callback = namespace["_BridgeTimerCallback"]()

        callback.Timeout()
        self.assertEqual(writes, [])
        self.assertEqual(namespace["_last_status_write"], 9.5)

        callback.Timeout()
        self.assertEqual(len(writes), 1)
        self.assertEqual(namespace["_last_status_write"], 10.6)

    def test_process_registry_stops_prior_module_namespace_on_reload(self):
        first = self._load_plugin_main_without_autostart()
        second = self._load_plugin_main_without_autostart()
        registry_name = first["_PROCESS_REGISTRY_ATTRIBUTE"]

        class FakeTimer:
            def __init__(self):
                self.stopped = False
                self.unregistered = False

            def IsRunning(self):
                return True

            def Stop(self):
                self.stopped = True

            def UnregisterPyTimerCallback(self):
                self.unregistered = True

        timer = FakeTimer()
        first["_timer"] = timer
        first["_timer_callback"] = object()
        try:
            first["_claim_process_slot"]()
            self.assertEqual(
                getattr(builtins, registry_name)["owner_token"],
                first["_process_owner_token"],
            )
            second["_claim_process_slot"]()
            self.assertTrue(timer.stopped)
            self.assertTrue(timer.unregistered)
            self.assertIsNone(first["_timer"])
            self.assertIsNone(first["_timer_callback"])
            self.assertEqual(
                getattr(builtins, registry_name)["owner_token"],
                second["_process_owner_token"],
            )
        finally:
            if hasattr(builtins, registry_name):
                delattr(builtins, registry_name)

    def test_process_registry_refuses_reload_when_prior_teardown_fails(self):
        first = self._load_plugin_main_without_autostart()
        second = self._load_plugin_main_without_autostart()
        registry_name = first["_PROCESS_REGISTRY_ATTRIBUTE"]

        class FailingTimer:
            def IsRunning(self):
                return True

            def Stop(self):
                raise RuntimeError("simulated teardown failure")

            def UnregisterPyTimerCallback(self):
                raise AssertionError("unreachable")

        first["_timer"] = FailingTimer()
        first["_timer_callback"] = object()
        first["_accepting_requests"] = True
        try:
            first["_claim_process_slot"]()
            with self.assertRaisesRegex(
                bridge_core.BridgeValidationError,
                "could not be stopped safely",
            ):
                second["_claim_process_slot"]()
            self.assertEqual(
                getattr(builtins, registry_name)["owner_token"],
                first["_process_owner_token"],
            )
            self.assertFalse(first["_accepting_requests"])
            first["_process_one_request"] = mock.Mock(
                side_effect=AssertionError("disabled timer consumed a request")
            )
            first["_BridgeTimerCallback"]().Timeout()
            first["_process_one_request"].assert_not_called()
        finally:
            if hasattr(builtins, registry_name):
                delattr(builtins, registry_name)

    def test_invalid_fresh_reload_stops_prior_instance_and_releases_slot(self):
        first = self._load_plugin_main_without_autostart()
        second = self._load_plugin_main_without_autostart()
        registry_name = first["_PROCESS_REGISTRY_ATTRIBUTE"]

        class FakeTimer:
            def __init__(self):
                self.stopped = False

            def IsRunning(self):
                return True

            def Stop(self):
                self.stopped = True

            def UnregisterPyTimerCallback(self):
                pass

        timer = FakeTimer()
        first["_timer"] = timer
        first["_timer_callback"] = object()
        first["_accepting_requests"] = True
        failing_core = mock.Mock()
        failing_core.BridgeValidationError = bridge_core.BridgeValidationError
        failing_core.load_config.side_effect = bridge_core.BridgeValidationError(
            "config_invalid",
            "simulated invalid config",
        )
        second["bridge_core"] = failing_core
        second["_write_status"] = mock.Mock()
        second["traceback"] = mock.Mock()
        try:
            first["_claim_process_slot"]()
            second["initialize_plugin"]()
            self.assertTrue(timer.stopped)
            self.assertFalse(first["_accepting_requests"])
            self.assertFalse(second["_accepting_requests"])
            self.assertFalse(hasattr(builtins, registry_name))
            second["traceback"].print_exc.assert_called_once()
        finally:
            if hasattr(builtins, registry_name):
                delattr(builtins, registry_name)

    def test_owned_file_cleanup_and_interval_backoff_are_conservative(self):
        with tempfile.TemporaryDirectory(dir=DATA_ROOT) as temp:
            root = Path(temp)
            collision = root / "collision.ccProject"
            collision.write_bytes(b"pre-existing")
            self.assertFalse(
                bridge_core.cleanup_owned_file(collision, owned=False)
            )
            self.assertEqual(collision.read_bytes(), b"pre-existing")

            owned = root / "owned.ccProject"
            owned.write_bytes(b"bridge-owned")
            self.assertTrue(
                bridge_core.cleanup_owned_file(owned, owned=True)
            )
            self.assertFalse(owned.exists())

        self.assertTrue(bridge_core.interval_due(10.0, 0.0, 1.0))
        self.assertFalse(bridge_core.interval_due(10.5, 10.0, 1.0))
        self.assertTrue(bridge_core.interval_due(11.0, 10.0, 1.0))


if __name__ == "__main__":
    unittest.main()
