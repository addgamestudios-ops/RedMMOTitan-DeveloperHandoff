from pathlib import Path
import re
import unittest


SCRIPT = (
    Path(__file__).resolve().parents[2]
    / "Build"
    / "Automation"
    / "Invoke-RedStylizedSourceImportBatch.ps1"
)


class StylizedImportLauncherContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = SCRIPT.read_text(encoding="utf-8")

    def test_uses_exact_project_engine_source_and_destination(self) -> None:
        self.assertIn(r'$ProjectRoot = "D:\RedMMOTitan"', self.text)
        self.assertIn(
            r'$ProjectFile = Join-Path $ProjectRoot "Titan_AssetImport.uproject"',
            self.text,
        )
        self.assertIn(
            r'$UnrealEditorCmd = "D:\UE_5.8\Engine\Binaries\Win64\UnrealEditor-Cmd.exe"',
            self.text,
        )
        self.assertIn(r'$SourceRoot = "D:\styled assets"', self.text)
        self.assertIn(
            '$DestinationAssetRoot = '
            '"/Game/RedMMO/ArtLibrary/StylizedSource"',
            self.text,
        )
        self.assertIn("import_redmmo_stylized_source_library.py", self.text)

    def test_categories_are_mandatory_and_batch_is_bounded(self) -> None:
        categories_block = re.search(
            r"\[Parameter\(Mandatory = \$true\)\]\s*"
            r"\[ValidateNotNullOrEmpty\(\)\]\s*"
            r"\[string\]\$Categories",
            self.text,
        )
        self.assertIsNotNone(categories_block)
        self.assertIn("[ValidateRange(1, 64)]", self.text)
        self.assertIn("$MaximumSelectedSourceBytes = 512MB", self.text)
        self.assertIn("Categories must be unique", self.text)

    def test_authenticates_plan_identity_approval_and_handoff(self) -> None:
        for token in (
            "redmmotitan.stylized_source_import.v2",
            "approved_by_explicit_user_conversion_instruction",
            "user_supplied_local_source_tree",
            "$ExpectedApprovalBasis",
            "dataset_sha256",
            "plan_sha256",
            "Get-FileHash -LiteralPath $resolvedPlan",
            "RED_STYLIZED_IMPORT_PLAN_FILE_SHA256",
        ):
            self.assertIn(token, self.text)
        self.assertIn(
            "Plan destination root must be exactly $DestinationAssetRoot",
            self.text,
        )
        self.assertIn(
            "Plan source root must be exactly $SourceRoot",
            self.text,
        )

    def test_has_overlap_ram_commit_disk_and_output_boundary_gates(self) -> None:
        for token in (
            "$blockingProcesses",
            "$MinimumFreePhysicalGiB = 6.0",
            "$MinimumFreeCommitGiB = 12.0",
            "$MinimumFreeDDriveGiB = 64.0",
            r"D:\RedMMOTitanWindowsData\AssetImports\StylizedSource",
            "OutputDirectory must be a child",
            "OutputDirectory must be fresh",
        ):
            self.assertIn(token, self.text)

    def test_uses_windows_powershell_compatible_relative_paths(self) -> None:
        self.assertNotIn(
            "[System.IO.Path]::GetRelativePath",
            self.text,
        )
        self.assertIn(
            "Protected workspace file escaped the project root",
            self.text,
        )

    def test_output_and_result_publication_are_no_clobber(self) -> None:
        self.assertIn(
            "New-Item -ItemType Directory -Path $resolvedOutput | Out-Null",
            self.text,
        )
        self.assertNotIn(
            "New-Item -ItemType Directory -Path $resolvedOutput -Force",
            self.text,
        )
        self.assertIn(
            "[System.IO.File]::Move($temporaryPath, $resultPath)",
            self.text,
        )
        self.assertNotIn(
            "Move-Item -LiteralPath $temporaryPath "
            "-Destination $resultPath -Force",
            self.text,
        )
        self.assertIn("Import state must be fresh", self.text)

    def test_bounds_integrity_checks_outside_destination(self) -> None:
        for token in (
            "function Get-OutsideDestinationFileCount",
            "function Get-OutsideDestinationRecentChanges",
            'Join-Path $ProjectRoot "Content"',
            'Join-Path $ProjectRoot "Plugins"',
            "$destinationPrefix",
            "created_or_changed:",
            "file_count:",
            "outside_destination_files_unchanged",
            "outside_destination_changes",
        ):
            self.assertIn(token, self.text)
        self.assertNotIn("Get-OutsideDestinationSnapshot", self.text)
        self.assertNotIn(
            "Get-FileHash -LiteralPath $fullPath -Algorithm SHA256",
            self.text,
        )

    def test_stages_dds_before_unreal_and_authenticates_manifest(self) -> None:
        for token in (
            '"stage-batch"',
            "stage_manifest.json",
            "RED_STYLIZED_IMPORT_STAGE_MANIFEST",
            "RED_STYLIZED_IMPORT_STAGE_MANIFEST_FILE_SHA256",
            "stage_manifest_file_sha256",
            "stylized_source_import_state.v3",
        ):
            self.assertIn(token, self.text)

    def test_preserves_all_four_protected_checkpoints(self) -> None:
        for relative in (
            r"Content\RedMMO\Maps\RedPlanetGen.umap",
            r"Content\RedMMO\Maps\RedPlanetGen_50km_Test.umap",
            r"Content\RedMMO\Maps\RedPlanetGen_50km_FusedPrototype.umap",
            r"Content\RedMMO\Environment\DA_RED_Planet50Km_FusedHeightfield.uasset",
        ):
            self.assertIn(relative, self.text)
        self.assertIn("protected_checkpoints_unchanged", self.text)

    def test_runs_one_hidden_nullrhi_commandlet_and_requires_state(self) -> None:
        self.assertEqual(self.text.count("Start-Process"), 1)
        for token in (
            "-run=pythonscript",
            "-NullRHI",
            "-WindowStyle Hidden",
            "-Wait",
            "-PassThru",
            "-abslog=",
            "did not publish the batch state",
            "RED_STYLIZED_IMPORT_COMPLETE",
            "Published state does not authenticate the selected plan",
        ):
            self.assertIn(token, self.text)


if __name__ == "__main__":
    unittest.main()
