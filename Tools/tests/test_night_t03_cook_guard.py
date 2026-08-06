import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "Build" / "Automation" / "Invoke-NightT03TargetedCook.ps1"


class NightT03CookGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = SCRIPT.read_text(encoding="utf-8-sig")

    def single_quoted_assignment(self, variable):
        matches = re.findall(
            rf"(?m)^\${re.escape(variable)}\s*=\s*'([^']+)'\s*$",
            self.source,
        )
        self.assertEqual(
            len(matches),
            1,
            f"expected one literal assignment for ${variable}",
        )
        return matches[0]

    def test_reports_commit_limit_and_committed_bytes_without_old_mislabel(self):
        self.assertIn("CommitLimitGB", self.source)
        self.assertIn("CommittedGB", self.source)
        self.assertNotIn("TotalCommitGB", self.source)
        self.assertRegex(
            self.source,
            r"CommittedGB\s*=\s*\[math\]::Round\(\(\$commitLimitGB\s*-\s*\$freeCommitGB\)",
        )

    def test_has_preflight_and_runtime_memory_floors(self):
        for token in (
            "MinimumFreeCommitGB = 12.0",
            "MinimumFreePhysicalGB = 8.0",
            "AbortFreeCommitGB = 8.0",
            "AbortFreePhysicalGB = 6.0",
        ):
            self.assertIn(token, self.source)
        self.assertIn("$memory.FreePhysicalGB -lt $AbortFreePhysicalGB", self.source)

    def test_detects_native_and_dotnet_hosted_unreal_build_processes(self):
        for process_name in (
            "UnrealEditor-Cmd",
            "AutomationTool",
            "UnrealBuildTool",
            "MSBuild",
            "ShaderCompileWorker",
            "CrashReportClient",
        ):
            self.assertIn(f"'{process_name}'", self.source)
        self.assertIn("$baseName -eq 'dotnet'", self.source)
        for command_line_marker in (
            "AutomationTool",
            "UnrealBuildTool",
            "RunUAT",
            "BuildCookRun",
        ):
            self.assertIn(command_line_marker, self.source)

    def test_scans_all_cook_logs_for_actual_memory_failure_signatures(self):
        self.assertIn("@($stdoutLog, $stderrLog, $absoluteLog)", self.source)
        self.assertIn("NNERuntimeORT.*bad allocation", self.source)
        self.assertIn("VirtualAlloc.*failed", self.source)
        self.assertIn("paging file is too small", self.source)
        fatal_pattern = next(
            line for line in self.source.splitlines() if "$fatalLine =" in line
        )
        self.assertNotIn("FULL COOK", fatal_pattern)

    def test_command_is_request_scoped_and_not_cook_all(self):
        self.assertIn("('-PACKAGE={0}' -f $packageList)", self.source)
        self.assertIn("'-NoGameAlwaysCook'", self.source)
        self.assertIn("'-NoDefaultMaps'", self.source)
        arguments_block = self.source.split("$arguments = @(", 1)[1].split(")\n\n", 1)[0]
        self.assertNotIn("-CookAll", arguments_block)
        self.assertNotIn("-COOKDIR", arguments_block)

    def test_milky_way_sky_dependencies_are_explicit_and_validated(self):
        package_assignments = {
            "MilkyWayMaterialPackage":
                "/Game/RedMMO/Environment/Tests/M_RedStar_T03MilkyWayWorldDir",
            "MilkyWayTexturePackage":
                "/Game/SpaceColony/Textures/T_milky_way",
            "EngineBasicSpherePackage": "/Engine/BasicShapes/Sphere",
            "EngineSkySpherePackage": "/Engine/EngineSky/SM_SkySphere",
        }
        artifact_assignments = {
            "milkyWayMaterialFile":
                r"Titan\Content\RedMMO\Environment\Tests"
                r"\M_RedStar_T03MilkyWayWorldDir.uasset",
            "milkyWayTextureFile":
                r"Titan\Content\SpaceColony\Textures\T_milky_way.uasset",
            "engineBasicSphereFile":
                r"Engine\Content\BasicShapes\Sphere.uasset",
            "engineSkySphereFile":
                r"Engine\Content\EngineSky\SM_SkySphere.uasset",
        }

        for variable, expected in package_assignments.items():
            self.assertEqual(self.single_quoted_assignment(variable), expected)

        package_list_match = re.search(
            r"(?ms)^\$packageList\s*=\s*@\((.*?)^\)\s*-join\s*'\+'",
            self.source,
        )
        self.assertIsNotNone(package_list_match)
        package_list = package_list_match.group(1)
        for variable in package_assignments:
            self.assertEqual(
                len(re.findall(rf"(?m)^\s*\${variable},?\s*$", package_list)),
                1,
            )

        for variable, expected_suffix in artifact_assignments.items():
            matches = re.findall(
                rf"(?m)^\${variable}\s*=\s*Join-Path\s+\$SandboxRoot\s+"
                rf"'([^']+)'\s*$",
                self.source,
            )
            self.assertEqual(
                matches,
                [expected_suffix],
                f"unexpected artifact path for ${variable}",
            )
            self.assertRegex(
                self.source,
                rf"(?m)^if \(-not \(Test-Path -LiteralPath \${variable}\)\) "
                rf"\{{ \$missing \+= \${variable} \}}$",
            )

    def test_missing_process_exit_code_requires_unreal_success_and_clean_exit(self):
        for token in (
            "$null -eq $exitCode",
            "Success - 0 error(s)",
            "LogExit: Exiting.",
            "$hasFailureMarker",
            "<unavailable>",
        ):
            self.assertIn(token, self.source)

    def test_refuses_existing_sandbox_before_start_process(self):
        refusal = self.source.index("Refusing to reuse or clean an existing cook sandbox")
        start = self.source.index("Start-Process -FilePath $EditorCmd")
        self.assertLess(refusal, start)
        self.assertEqual(
            len(re.findall(r"Start-Process\s+-FilePath\s+\$EditorCmd", self.source)),
            1,
        )


if __name__ == "__main__":
    unittest.main()
