import json
import os
import tempfile
import unittest
from pathlib import Path

from Tools.audit_windows_target_currency import (
    audit_project,
    build_input_manifest,
    main,
    sha256_file,
)


class WindowsTargetCurrencyAuditTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self._write("Titan.uproject", "{}\n", 100)
        self._write("Config/DefaultEngine.ini", "[Core]\n", 100)
        self._write("Source/Titan.Target.cs", "// target\n", 100)
        self._write("Source/RedMMO/Test.cpp", "int x = 1;\n", 100)
        self._write("Plugins/Test/Test.uplugin", "{}\n", 100)
        self._write("Plugins/Test/Source/Test/Test.Build.cs", "// build\n", 100)
        self._write("Binaries/Win64/Titan.exe", "titan-exe\n", 200)
        self._write("Binaries/Win64/UnrealEditor-RedMMO.dll", "editor-dll\n", 200)
        self._write("Binaries/Win64/UnrealEditor.modules", "{}\n", 200)
        self._write_receipt(
            "Titan",
            "Game",
            "Binaries/Win64/Titan.target",
            [
                ("$(ProjectDir)/Binaries/Win64/Titan.exe", "Executable"),
                ("$(ProjectDir)/Binaries/Win64/Titan.pdb", "SymbolFile"),
            ],
            300,
        )
        self._write_receipt(
            "TitanEditor",
            "Editor",
            "Binaries/Win64/TitanEditor.target",
            [
                (
                    "$(ProjectDir)/Binaries/Win64/UnrealEditor-RedMMO.dll",
                    "DynamicLibrary",
                ),
                (
                    "$(ProjectDir)/Binaries/Win64/UnrealEditor.modules",
                    "RequiredResource",
                ),
                (
                    "$(ProjectDir)/Binaries/Win64/UnrealEditor-RedMMO.pdb",
                    "SymbolFile",
                ),
            ],
            300,
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _write(self, relative: str, text: str, timestamp_ns: int) -> Path:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        os.utime(path, ns=(timestamp_ns, timestamp_ns))
        return path

    def _write_receipt(
        self,
        name: str,
        target_type: str,
        relative: str,
        products: list[tuple[str, str]],
        timestamp_ns: int,
    ) -> Path:
        payload = {
            "TargetName": name,
            "Platform": "Win64",
            "Configuration": "Development",
            "TargetType": target_type,
            "Architecture": "x64",
            "Project": "../../Titan.uproject",
            "Version": {"BuildId": "test"},
            "BuildProducts": [
                {"Path": path, "Type": product_type}
                for path, product_type in products
            ],
        }
        return self._write(relative, json.dumps(payload), timestamp_ns)

    def _write_proof(self, target: dict, filename: str) -> Path:
        log = self._write(
            f"Diagnostics/{filename}.log",
            f"Running {target['target_name']} Win64 Development\nResult: Succeeded\n",
            400,
        )
        proof = {
            "schema_version": 1,
            "target_name": target["target_name"],
            "platform": target["expected_platform"],
            "configuration": target["expected_configuration"],
            "target_type": target["expected_target_type"],
            "input_count": target["input_count"],
            "input_manifest_sha256": target["input_manifest_sha256"],
            "receipt_sha256": target["receipt_sha256"],
            "required_product_manifest_sha256": target[
                "required_product_manifest_sha256"
            ],
            "build_log": {"path": str(log), "sha256": sha256_file(log)},
        }
        return self._write(
            f"Proofs/{filename}.json", json.dumps(proof), 500
        )

    def _dual_proofs(self) -> tuple[Path, Path]:
        initial = audit_project(self.root)
        by_name = {target["target_name"]: target for target in initial["targets"]}
        return (
            self._write_proof(by_name["Titan"], "Titan"),
            self._write_proof(by_name["TitanEditor"], "TitanEditor"),
        )

    def test_input_manifest_is_deterministic_and_scoped(self) -> None:
        first, first_digest = build_input_manifest(self.root)
        second, second_digest = build_input_manifest(self.root)
        paths = {record["path"] for record in first}
        self.assertEqual(first_digest, second_digest)
        self.assertEqual(first, second)
        self.assertIn("Titan.uproject", paths)
        self.assertIn("Config/DefaultEngine.ini", paths)
        self.assertIn("Source/RedMMO/Test.cpp", paths)
        self.assertIn("Plugins/Test/Test.uplugin", paths)
        self.assertNotIn("Binaries/Win64/Titan.exe", paths)

    def test_no_proof_refuses_even_when_timestamps_are_clean(self) -> None:
        report = audit_project(self.root)
        self.assertFalse(report["gate"]["skip_build_allowed"])
        self.assertEqual(report["gate"]["result"], "refused_fail_closed")
        for target in report["targets"]:
            self.assertEqual(target["currency_state"], "timestamp_clean_unproven")
            self.assertEqual(target["proof_status"], "missing")

    def test_newer_input_is_reported_as_stale(self) -> None:
        self._write("Source/RedMMO/Test.cpp", "int x = 2;\n", 600)
        report = audit_project(self.root)
        for target in report["targets"]:
            self.assertEqual(target["currency_state"], "stale_unproven")
            self.assertEqual(target["newer_project_input_count"], 1)
            self.assertEqual(
                target["newer_project_inputs"][0]["path"],
                "Source/RedMMO/Test.cpp",
            )

    def test_exact_dual_proofs_are_required_for_authorization(self) -> None:
        titan_proof, editor_proof = self._dual_proofs()
        only_one = audit_project(self.root, titan_proof=titan_proof)
        self.assertFalse(only_one["gate"]["skip_build_allowed"])
        complete = audit_project(
            self.root,
            titan_proof=titan_proof,
            titan_editor_proof=editor_proof,
        )
        self.assertTrue(complete["gate"]["skip_build_allowed"])
        self.assertTrue(
            all(target["currency_state"] == "current_proven" for target in complete["targets"])
        )

    def test_content_change_with_older_mtime_invalidates_proof_digest(self) -> None:
        titan_proof, editor_proof = self._dual_proofs()
        self._write("Source/RedMMO/Test.cpp", "int x = 999;\n", 50)
        report = audit_project(
            self.root,
            titan_proof=titan_proof,
            titan_editor_proof=editor_proof,
        )
        self.assertFalse(report["gate"]["skip_build_allowed"])
        self.assertTrue(all(target["proof_status"] == "invalid" for target in report["targets"]))

    def test_wrong_receipt_identity_and_missing_product_fail_closed(self) -> None:
        titan_receipt = self.root / "Binaries/Win64/Titan.target"
        data = json.loads(titan_receipt.read_text(encoding="utf-8"))
        data["Platform"] = "Linux"
        self._write("Binaries/Win64/Titan.target", json.dumps(data), 300)
        (self.root / "Binaries/Win64/UnrealEditor.modules").unlink()
        report = audit_project(self.root)
        by_name = {target["target_name"]: target for target in report["targets"]}
        self.assertEqual(by_name["Titan"]["currency_state"], "invalid_or_missing")
        self.assertEqual(by_name["TitanEditor"]["currency_state"], "invalid_or_missing")

    def test_receipt_project_path_escape_is_rejected(self) -> None:
        receipt = self.root / "Binaries/Win64/Titan.target"
        data = json.loads(receipt.read_text(encoding="utf-8"))
        data["BuildProducts"].append(
            {"Path": "$(ProjectDir)/../outside.dll", "Type": "DynamicLibrary"}
        )
        self._write("Binaries/Win64/Titan.target", json.dumps(data), 300)
        report = audit_project(self.root)
        titan = next(target for target in report["targets"] if target["target_name"] == "Titan")
        self.assertEqual(titan["currency_state"], "invalid_or_missing")
        self.assertTrue(any("escapes project root" in error for error in titan["errors"]))

    def test_gate_exit_code_is_fail_closed_but_report_mode_is_available(self) -> None:
        output = self.root / "Diagnostics/currency.json"
        refused = main(["--project-root", str(self.root), "--output", str(output)])
        self.assertEqual(refused, 10)
        self.assertTrue(output.is_file())
        allowed_report = main(
            [
                "--project-root",
                str(self.root),
                "--output",
                str(output),
                "--allow-unverified-report",
            ]
        )
        self.assertEqual(allowed_report, 0)
        self.assertFalse(json.loads(output.read_text(encoding="utf-8"))["gate"]["skip_build_allowed"])


if __name__ == "__main__":
    unittest.main()
