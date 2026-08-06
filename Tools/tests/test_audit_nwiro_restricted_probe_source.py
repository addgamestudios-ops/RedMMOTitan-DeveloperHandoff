from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from Tools.audit_nwiro_restricted_probe_source import (
    DEFAULT_PLUGIN_ROOT,
    PINNED_FILES,
    NwiroSourceAuditError,
    _extract_function,
    _mask_cpp_noncode,
    audit_installed_source,
    evaluate_source_controls,
)


class NwiroRestrictedProbeSourceAuditTests(unittest.TestCase):
    def test_installed_reviewed_source_is_authenticated_and_blocked(self):
        report = audit_installed_source()
        self.assertEqual(
            report["source_revision"],
            "reviewed_blocked_baseline_critical_files_exact",
        )
        self.assertEqual(report["status"], "blocked")
        self.assertFalse(report["runtime_authorized"])
        self.assertFalse(report["candidate_static_acceptance_supported"])
        self.assertFalse(report["running_binary_authenticated"])
        self.assertEqual(
            report["file_scope"],
            "named_critical_files_only_not_complete_plugin_tree",
        )
        self.assertEqual(len(report["files"]), len(PINNED_FILES))
        self.assertTrue(
            all(record["matches_reviewed_revision"] for record in report["files"])
        )
        self.assertEqual(
            set(report["blocking_controls"]),
            {
                "candidate_hardened_source_contract_absent",
                "restricted_mode_declared",
                "exclusive_process_lock_before_listener",
                "alternate_http_routes_suppressed",
                "vendor_config_publication_suppressed",
                "process_jsonrpc_predispatch_gate",
                "runtime_tool_registry_generation_bound",
                "dispatch_tool_exact_allowlist",
                "headless_permission_fail_closed",
                "bridge_null_extension_fail_closed",
                "acp_direct_dispatch_suppressed",
            },
        )

    def test_comments_and_strings_cannot_satisfy_missing_controls(self):
        server_path = (
            DEFAULT_PLUGIN_ROOT
            / "Source/NwiroIntegrationKit/Private/NwiroIKMCPServer.cpp"
        )
        bridge_path = (
            DEFAULT_PLUGIN_ROOT
            / "Source/NwiroIntegrationKit/Private/NwiroIKBridge.cpp"
        )
        blocked_server = server_path.read_text(encoding="utf-8") + r'''
        // ValidateRestrictedFindAssetsCall DispatchToolImpl
        const char* Fake = "ValidateRestrictedFindAssetsCall DispatchToolImpl";
        '''
        checks = {
            check.control: check.source_shape_observed
            for check in evaluate_source_controls(
                blocked_server, bridge_path.read_text(encoding="utf-8")
            )
        }
        self.assertFalse(checks["dispatch_tool_exact_allowlist"])

    def test_function_extractor_ignores_braces_in_comments_and_strings(self):
        source = r'''
        // Target::Run() { not a definition }
        void Target::Run()
        {
            FString Text = TEXT("{ quoted }");
            /* } commented { */
            if (true) { Call(); }
        }
        '''
        body = _extract_function(source, "Target::Run")
        self.assertIn("Call();", body)
        self.assertTrue(body.rstrip().endswith("}"))

    def test_unterminated_lexical_construct_is_rejected(self):
        with self.assertRaises(NwiroSourceAuditError):
            _mask_cpp_noncode('void A() { FString X = "unterminated; }')

    def test_source_drift_fails_closed_before_control_evaluation(self):
        with tempfile.TemporaryDirectory() as temporary:
            copied_root = Path(temporary) / "plugin"
            for relative in PINNED_FILES:
                source = DEFAULT_PLUGIN_ROOT / Path(relative)
                target = copied_root / Path(relative)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(source.read_bytes())
            server = (
                copied_root
                / "Source/NwiroIntegrationKit/Private/NwiroIKMCPServer.cpp"
            )
            server.write_bytes(server.read_bytes() + b"\n")
            report = audit_installed_source(copied_root)
            self.assertEqual(report["status"], "source_drift")
            self.assertFalse(report["runtime_authorized"])
            self.assertFalse(report["candidate_static_acceptance_supported"])
            self.assertFalse(report["running_binary_authenticated"])
            self.assertEqual(report["checks"], [])
            self.assertEqual(
                report["blocking_controls"], ["reviewed_source_revision"]
            )

    def test_offline_module_imports_no_transport_or_process_modules(self):
        source_path = (
            Path(__file__).resolve().parents[1]
            / "audit_nwiro_restricted_probe_source.py"
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
                {
                    "socket",
                    "requests",
                    "urllib",
                    "http",
                    "httpx",
                    "subprocess",
                }
            )
        )

    def test_cli_reports_expected_blocked_state_without_writing(self):
        project_root = Path(__file__).resolve().parents[2]
        script = project_root / "Tools" / "audit_nwiro_restricted_probe_source.py"
        before = {
            path: path.stat().st_mtime_ns
            for path in DEFAULT_PLUGIN_ROOT.rglob("*")
            if path.is_file()
        }
        result = subprocess.run(
            [sys.executable, "-B", str(script), "--expect", "blocked"],
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["status"], "blocked")
        after = {
            path: path.stat().st_mtime_ns
            for path in DEFAULT_PLUGIN_ROOT.rglob("*")
            if path.is_file()
        }
        self.assertEqual(after, before)

    def test_cli_has_no_ready_expectation_or_positive_state(self):
        project_root = Path(__file__).resolve().parents[2]
        script = project_root / "Tools" / "audit_nwiro_restricted_probe_source.py"
        result = subprocess.run(
            [sys.executable, "-B", str(script), "--expect", "ready"],
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertIn("invalid choice", result.stderr)


if __name__ == "__main__":
    unittest.main()
