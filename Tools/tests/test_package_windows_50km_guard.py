import re
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = PROJECT_ROOT / "Build" / "Automation" / "package_windows_50km.ps1"
FUSED_VERIFIER_PATH = (
    PROJECT_ROOT / "Build" / "Automation" / "verify_packaged_fused_prototype.ps1"
)


class PackageWindows50KmGuardContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.script = SCRIPT_PATH.read_text(encoding="utf-8-sig")
        cls.fused_verifier = FUSED_VERIFIER_PATH.read_text(encoding="utf-8-sig")

    def test_packaging_requires_sustained_20_gib_physical_headroom_by_default(self) -> None:
        self.assertRegex(
            self.script,
            r"\[ValidateRange\(24\.0, 128\.0\)\]\s*"
            r"\[double\]\$MinimumFreeCommitGB = 26\.0",
        )
        self.assertRegex(
            self.script,
            r"\[ValidateRange\(18\.0, 128\.0\)\]\s*"
            r"\[double\]\$MinimumFreePhysicalGB = 20\.0",
        )
        self.assertRegex(
            self.script,
            r"\[ValidateRange\(6, 60\)\]\s*\[int\]\$PreflightSamples = 12",
        )
        self.assertRegex(
            self.script,
            r"\[ValidateRange\(1, 10\)\]\s*\[int\]\$PreflightSampleSeconds = 1",
        )
        self.assertIn("Measure-Object -Property FreePhysicalGB -Minimum", self.script)
        self.assertIn("Measure-Object -Property FreeCommitGB -Minimum", self.script)
        self.assertIn("Sort-Object -Property Id -Unique", self.script)

    def test_runtime_abort_preserves_12_gib_physical_headroom(self) -> None:
        self.assertRegex(
            self.script,
            r"\[double\]\$AbortFreeCommitGB = 16\.0",
        )
        self.assertRegex(
            self.script,
            r"\[double\]\$AbortFreePhysicalGB = 12\.0",
        )
        self.assertIn(
            "$memory.FreePhysicalGB -lt $AbortFreePhysicalGB",
            self.script,
        )
        self.assertIn("taskkill.exe\" /PID $uatProcess.Id /T /F", self.script)

    def test_guard_records_non_regressing_buildcookrun_phase(self) -> None:
        expected_markers = (
            "BUILD COMMAND STARTED",
            "COOK COMMAND STARTED",
            "STAGE COMMAND STARTED",
            "PACKAGE COMMAND STARTED",
            "ARCHIVE COMMAND STARTED",
            "BUILD SUCCESSFUL",
        )
        for marker in expected_markers:
            self.assertIn(marker, self.script)

        ranks = {
            key: int(value)
            for key, value in re.findall(
                r"^\s*(automation_startup|build|cook|stage|package|archive|complete)\s*=\s*(\d+)\s*$",
                self.script,
                flags=re.MULTILINE,
            )
        }
        self.assertEqual(
            ranks,
            {
                "automation_startup": 0,
                "build": 1,
                "cook": 2,
                "stage": 3,
                "package": 4,
                "archive": 5,
                "complete": 6,
            },
        )
        self.assertIn("$phaseRank[$candidatePhase] -gt $phaseRank[$PreviousPhase]", self.script)
        self.assertIn("phase={2}", self.script)
        self.assertIn("aborted_phase=$packagePhase", self.script)
        self.assertIn("final_phase=$packagePhase", self.script)

    def test_package_contract_still_builds_serially_and_cooks(self) -> None:
        for argument in (
            "'-UbtArgs=-NoUBA -MaxParallelActions=1'",
            "'-build'",
            "'-cook'",
            "'-stage'",
            "'-pak'",
            "'-iostore'",
            "'-zenstore'",
            "'-archive'",
        ):
            self.assertIn(argument, self.script)
        self.assertNotIn("'-skipbuild'", self.script)

    def test_protected_checkpoint_assertions_remain_before_and_after_packaging(self) -> None:
        self.assertEqual(self.script.count("Assert-RedProtectedCheckpoints"), 3)
        self.assertIn(
            "$ExpectedProtectedMapHash = "
            "'DA5987012EEB8F550254F5FCF0F47F42B8F5E03428CF4881C83D8687537F6E7D'",
            self.script,
        )

    def test_fused_package_marker_records_stable_exact_source_hash(self) -> None:
        producer_match = re.search(
            r"\$ExpectedFusedPrototypeHash\s*=\s*'([0-9A-F]{64})'",
            self.script,
        )
        consumer_match = re.search(
            r"'Content\\RedMMO\\Maps\\RedPlanetGen_50km_FusedPrototype\.umap'\s*=\s*'([0-9A-F]{64})'",
            self.fused_verifier,
        )
        self.assertIsNotNone(producer_match)
        self.assertIsNotNone(consumer_match)
        self.assertEqual(producer_match.group(1), consumer_match.group(1))

        for token in (
            "$Include50KmCheckpoints -and -not $FreshCook",
            "Include50KmCheckpoints requires FreshCook",
            "$FusedPrototypeSourceHash = Get-RedFusedPrototypeSourceHash",
            "$PostPackageFusedPrototypeHash = Get-RedFusedPrototypeSourceHash",
            "$PostPackageFusedPrototypeHash -ne $FusedPrototypeSourceHash",
            '"fused_prototype_source_sha256=$FusedPrototypeSourceHash"',
        ):
            self.assertIn(token, self.script)

        capture = self.script.index(
            "$FusedPrototypeSourceHash = Get-RedFusedPrototypeSourceHash"
        )
        launch = self.script.index("Start-Process -FilePath $env:ComSpec")
        uat_success = self.script.index("if ($ExitCode -ne 0)")
        post_check = self.script.index(
            "$PostPackageFusedPrototypeHash = Get-RedFusedPrototypeSourceHash"
        )
        marker_write = self.script.index("Move-Item -LiteralPath $ReadyMarkerTemp")
        self.assertLess(capture, launch)
        self.assertLess(launch, uat_success)
        self.assertLess(uat_success, post_check)
        self.assertLess(post_check, marker_write)
        self.assertIn(
            '"fused_prototype_source_sha256=$ExpectedFusedPrototypeHash"',
            self.fused_verifier,
        )

    def test_ready_marker_is_atomic_and_requires_zero_exit_evidence(self) -> None:
        for token in (
            '$ReadyMarkerTemp = "$ReadyMarkerPath.tmp"',
            "$ReadyMarkerTempCreatedByThisRun = $false",
            "$ReadyMarkerPublishedByThisRun = $false",
            "$ReadyMarkerTempCreatedByThisRun = $true",
            "Set-Content -LiteralPath $ReadyMarkerTemp -Value $ReadyMarkerLines",
            "Set-Content -LiteralPath $ExitFile -Value 0",
            "Move-Item -LiteralPath $ReadyMarkerTemp -Destination $ReadyMarkerPath",
            "$ReadyMarkerPublishedByThisRun = $true",
            "$ReadyMarkerTempCreatedByThisRun -and",
            "$ReadyMarkerPublishedByThisRun -and",
        ):
            self.assertIn(token, self.script)

        temp_write = self.script.index(
            "Set-Content -LiteralPath $ReadyMarkerTemp -Value $ReadyMarkerLines"
        )
        exit_success = self.script.index(
            "Set-Content -LiteralPath $ExitFile -Value 0"
        )
        publish = self.script.index(
            "Move-Item -LiteralPath $ReadyMarkerTemp -Destination $ReadyMarkerPath"
        )
        latest_pointer = self.script.index(
            "Set-Content -LiteralPath 'D:\\RedMMOTitanWindowsData\\BuildLogs\\LatestPackage50kmArchive.txt'"
        )
        catch_cleanup = self.script.index(
            "$ReadyMarkerTempCreatedByThisRun -and"
        )
        exit_failure = self.script.index(
            "Set-Content -LiteralPath $ExitFile -Value 1"
        )
        self.assertLess(temp_write, exit_success)
        self.assertLess(exit_success, publish)
        self.assertLess(publish, latest_pointer)
        self.assertLess(catch_cleanup, exit_failure)


if __name__ == "__main__":
    unittest.main()
