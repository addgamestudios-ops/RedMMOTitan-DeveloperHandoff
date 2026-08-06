import hashlib
import json
import pathlib
import re
import subprocess
import tempfile
import unittest
import base64


ROOT = pathlib.Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "Build" / "Automation" / "Invoke-RedSandSparkleMaskProbe.ps1"


class RedSandMaskProbeLauncherTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = SCRIPT.read_text(encoding="utf-8")

    def run_powershell_fixture(self, body, timeout=30):
        script_path = str(SCRIPT).replace("'", "''")
        command = f". '{script_path}'; {body}"
        return subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                command,
            ],
            capture_output=True,
            text=True,
            timeout=timeout,
        )

    @staticmethod
    def ps_quote(path):
        return "'" + str(path).replace("'", "''") + "'"

    @staticmethod
    def sha256(data):
        return hashlib.sha256(data).hexdigest().upper()

    def test_powershell_ast_has_no_errors(self):
        command = (
            "$tokens=$null;$errors=$null;"
            "[System.Management.Automation.Language.Parser]::ParseFile("
            f"'{SCRIPT}',[ref]$tokens,[ref]$errors)|Out-Null;"
            "if($errors.Count){$errors|ForEach-Object{$_.Message};exit 1}"
        )
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", command],
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_exact_probe_and_protected_paths_are_pinned(self):
        self.assertIn("prepare_red_sand_sparkle_mask_probe.py", self.source)
        self.assertIn("-RedSandSparkleMaskProbeWrite", self.source)
        self.assertIn("MI_PlanetBiome_DesertSparkle_T02.uasset", self.source)
        self.assertIn("RedPlanetGen_50km_Test.umap", self.source)
        self.assertIn(
            "DA5987012EEB8F550254F5FCF0F47F42B8F5E03428CF4881C83D8687537F6E7D",
            self.source,
        )
        self.assertIn(
            "26B00A20C4B18717CEC36B5CA289CC9001AE1E65DA649404ACC8721F14EF26E8",
            self.source,
        )

    def test_sustained_preflight_and_runtime_abort_guards_exist(self):
        for token in (
            "$SustainedSampleCount",
            "$MinimumFreeCommitGB",
            "$MinimumFreePhysicalGB",
            "$MinimumFreeVramMB",
            "$AbortFreeCommitGB",
            "$AbortFreePhysicalGB",
            "$AbortFreeVramMB",
            "Get-RedBlockingProcesses",
            "taskkill.exe",
        ):
            self.assertIn(token, self.source)
        self.assertRegex(
            self.source,
            re.compile(r"\$minimumObservedPhysicalGB\s+-ge\s+\$MinimumFreePhysicalGB"),
        )
        self.assertIn("$MaximumRuntimeMinutes", self.source)
        self.assertIn("Test-RedRuntimeDeadlineExceeded", self.source)
        self.assertIn("Stop-RedExactProcessTree", self.source)
        self.assertIn("Restore-RedTargetFromBackupIfNeeded", self.source)

    def test_commandlet_is_headless_and_exactly_flagged(self):
        for argument in (
            "'-run=pythonscript'",
            "'-NullRHI'",
            "'-unattended'",
            "$WriteFlag",
        ):
            self.assertIn(argument, self.source)
        self.assertNotIn("-run=Cook", self.source)
        argument_block = self.source.split("$arguments = @(", 1)[1].split(")\n\nWrite-Host", 1)[0]
        self.assertNotIn("BuildCookRun", argument_block)

    def test_postconditions_require_marker_hashes_backup_and_switch_pair(self):
        for token in (
            "RED_SAND_MASK_PROBE_PREPARED",
            "target_hash_before",
            "target_hash_after",
            "rollback_backup",
            "SimpleSparkle?",
            "SparklShrinkNear?",
            "Assert-RedProtectedCheckpoints",
            "Assert-RedProbeMarkerSchema",
            "Assert-RedProbeResultPostconditions",
        ):
            self.assertIn(token, self.source)

    def test_launcher_has_no_destructive_filesystem_operations(self):
        forbidden = (
            "Remove-Item",
            "Clear-Content",
            "Format-Volume",
            "del /",
            "rmdir",
        )
        for token in forbidden:
            self.assertNotIn(token.lower(), self.source.lower())

    def test_runtime_deadline_helper_is_bounded(self):
        body = (
            "$start=[datetime]'2026-07-21T00:00:00Z';"
            "$before=Test-RedRuntimeDeadlineExceeded -StartedUtc $start "
            "-MaximumMinutes 10 -NowUtc ([datetime]'2026-07-21T00:09:59Z');"
            "$at=Test-RedRuntimeDeadlineExceeded -StartedUtc $start "
            "-MaximumMinutes 10 -NowUtc ([datetime]'2026-07-21T00:10:00Z');"
            "if($before -or -not $at){exit 91}"
        )
        result = self.run_powershell_fixture(body)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_process_enumeration_failure_is_fail_closed(self):
        body = (
            "function Get-CimInstance { throw 'fixture CIM failure' };"
            "try { Get-RedBlockingProcesses | Out-Null; exit 91 } "
            "catch { if($_.Exception.Message -notlike "
            "'Unable to enumerate blocking processes*'){exit 92}; exit 0 }"
        )
        result = self.run_powershell_fixture(body)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_marker_schema_accepts_complete_typed_idempotent_result(self):
        marker = {
            "target": "/Game/Test/Target",
            "target_hash_before": "A" * 64,
            "target_hash_after": "A" * 64,
            "rollback_backup": None,
            "desired_switches": {
                "SimpleSparkle?": True,
                "SparklShrinkNear?": False,
            },
            "changed": False,
            "protected_hash_count": 6,
        }
        encoded = json.dumps(marker).replace("'", "''")
        result = self.run_powershell_fixture(
            f"$result='{encoded}' | ConvertFrom-Json; "
            "Assert-RedProbeMarkerSchema -Result $result"
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_marker_schema_rejects_missing_or_wrong_typed_changed(self):
        base = {
            "target": "/Game/Test/Target",
            "target_hash_before": "A" * 64,
            "target_hash_after": "A" * 64,
            "rollback_backup": None,
            "desired_switches": {
                "SimpleSparkle?": True,
                "SparklShrinkNear?": False,
            },
            "protected_hash_count": 6,
        }
        for changed in (None, "false"):
            marker = dict(base)
            if changed is not None:
                marker["changed"] = changed
            encoded = json.dumps(marker).replace("'", "''")
            result = self.run_powershell_fixture(
                f"$result='{encoded}' | ConvertFrom-Json; "
                "Assert-RedProbeMarkerSchema -Result $result"
            )
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_target_rollback_restores_exact_fixture_hash(self):
        baseline = b"red-sand-baseline-fixture"
        changed = b"changed-or-partial-unreal-save"
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            target = root / "target.uasset"
            backup = root / "backup.uasset"
            target.write_bytes(changed)
            backup.write_bytes(baseline)
            body = (
                "$restored=Restore-RedTargetFromBackupIfNeeded "
                f"-TargetPath {self.ps_quote(target)} "
                f"-ExpectedHash '{self.sha256(baseline)}' "
                f"-BackupPath {self.ps_quote(backup)};"
                "if(-not $restored){exit 91}"
            )
            result = self.run_powershell_fixture(body)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(target.read_bytes(), baseline)

    def test_target_rollback_fails_closed_without_exact_backup(self):
        baseline = b"expected-baseline"
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            target = root / "target.uasset"
            missing_backup = root / "missing.uasset"
            target.write_bytes(b"changed")
            body = (
                "Restore-RedTargetFromBackupIfNeeded "
                f"-TargetPath {self.ps_quote(target)} "
                f"-ExpectedHash '{self.sha256(baseline)}' "
                f"-BackupPath {self.ps_quote(missing_backup)}"
            )
            result = self.run_powershell_fixture(body)
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(target.read_bytes(), b"changed")

    def test_exact_process_tree_cleanup_terminates_spawned_parent_and_child(self):
        with tempfile.TemporaryDirectory() as directory:
            pid_file = pathlib.Path(directory) / "grandchild.pid"
            grandchild_command = "Start-Sleep -Seconds 120"
            grandchild_encoded = base64.b64encode(
                grandchild_command.encode("utf-16-le")
            ).decode("ascii")
            parent_command = (
                "$grandchild=Start-Process powershell -PassThru -WindowStyle Hidden "
                "-ArgumentList @('-NoProfile','-EncodedCommand',"
                f"'{grandchild_encoded}');"
                f"Set-Content -LiteralPath {self.ps_quote(pid_file)} "
                "-Value $grandchild.Id -NoNewline;"
                "$grandchild.WaitForExit()"
            )
            parent_encoded = base64.b64encode(
                parent_command.encode("utf-16-le")
            ).decode("ascii")
            body = (
                "$parent=$null;$grandchildId=$null;"
                "try {"
                "$parent=Start-Process powershell -PassThru -WindowStyle Hidden "
                "-ArgumentList @('-NoProfile','-EncodedCommand',"
                f"'{parent_encoded}');"
                f"$deadline=[datetime]::UtcNow.AddSeconds(10);"
                f"while(-not (Test-Path -LiteralPath {self.ps_quote(pid_file)})){{"
                "if([datetime]::UtcNow -ge $deadline){throw 'PID fixture timed out'};"
                "Start-Sleep -Milliseconds 50};"
                f"$grandchildId=[int](Get-Content -Raw -LiteralPath {self.ps_quote(pid_file)});"
                "Stop-RedExactProcessTree -Process $parent;"
                "Start-Sleep -Milliseconds 250;"
                "if(Get-Process -Id $parent.Id -ErrorAction SilentlyContinue){exit 91};"
                "if(Get-Process -Id $grandchildId -ErrorAction SilentlyContinue){exit 92};"
                "} finally {"
                "if($parent -and (Get-Process -Id $parent.Id -ErrorAction SilentlyContinue)){"
                "& taskkill.exe /PID $parent.Id /T /F | Out-Null};"
                "if($grandchildId -and (Get-Process -Id $grandchildId -ErrorAction SilentlyContinue)){"
                "& taskkill.exe /PID $grandchildId /T /F | Out-Null}"
                "}"
            )
            result = self.run_powershell_fixture(body, timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_exit_tracking_preserves_zero_exit_code_after_process_exits(self):
        body = (
            "$fixture=Start-Process -FilePath $env:SystemRoot\\System32\\cmd.exe "
            "-ArgumentList '/c ping 127.0.0.1 -n 2 >nul & exit 0' "
            "-PassThru -NoNewWindow;"
            "$fixture=Initialize-RedProcessExitTracking -Process $fixture;"
            "$fixture.WaitForExit();$fixture.Refresh();"
            "if($null -eq $fixture.ExitCode){exit 91};"
            "if($fixture.ExitCode -ne 0){exit 92}"
        )
        result = self.run_powershell_fixture(body, timeout=10)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_postrun_blocker_drain_allows_bounded_helper_shutdown(self):
        body = (
            "$script:fixtureCalls=0;"
            "function Get-RedBlockingProcesses {"
            "$script:fixtureCalls++;"
            "if($script:fixtureCalls -lt 3){return @([pscustomobject]@{ProcessName='CrashReportClientEditor'})};"
            "return @()};"
            "$remaining=@(Wait-RedBlockingProcessesToDrain -TimeoutSeconds 2 -PollMilliseconds 25);"
            "if($remaining.Count -ne 0){exit 91};"
            "if($script:fixtureCalls -ne 3){exit 92}"
        )
        result = self.run_powershell_fixture(body, timeout=10)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_changed_postconditions_require_matching_backup(self):
        baseline = b"before"
        after = b"after"
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            backup = root / "backup.uasset"
            backup.write_bytes(baseline)
            marker = {
                "target": "/Game/Test/Target",
                "target_hash_before": self.sha256(baseline),
                "target_hash_after": self.sha256(after),
                "rollback_backup": str(backup),
                "desired_switches": {
                    "SimpleSparkle?": True,
                    "SparklShrinkNear?": False,
                },
                "changed": True,
                "protected_hash_count": 6,
            }
            encoded = json.dumps(marker).replace("'", "''")
            body = (
                f"$result='{encoded}' | ConvertFrom-Json;"
                "Assert-RedProbeResultPostconditions -Result $result "
                "-ExpectedTarget '/Game/Test/Target' "
                f"-TargetHashBefore '{self.sha256(baseline)}' "
                f"-TargetHashAfter '{self.sha256(after)}'"
            )
            result = self.run_powershell_fixture(body)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

            backup.write_bytes(b"wrong backup")
            result = self.run_powershell_fixture(body)
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_failure_paths_do_not_use_write_error_before_exit(self):
        self.assertNotIn("Write-Error", self.source)
        self.assertIn("[Console]::Error.WriteLine", self.source)


if __name__ == "__main__":
    unittest.main()
