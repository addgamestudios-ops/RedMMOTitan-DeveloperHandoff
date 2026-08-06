import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

REDHUD_ROOT = ROOT / "Plugins/RedHUD"
REDHUD_SOURCE = REDHUD_ROOT / "Source"
WIDGET_H = REDHUD_SOURCE / "RedHUDRuntime/Public/RedHUDWidget.h"
WIDGET_CPP = REDHUD_SOURCE / "RedHUDRuntime/Private/RedHUDWidget.cpp"
TYPES_H = REDHUD_SOURCE / "RedHUDRuntime/Public/RedHUDTypes.h"
INTEGRATION_SNIPPET = REDHUD_ROOT / "INTEGRATION_SNIPPET.cpp"

REDMMO_SOURCE = ROOT / "Source/RedMMO"
HUD_H = REDMMO_SOURCE / "RedHUD.h"
HUD_CPP = REDMMO_SOURCE / "RedHUD.cpp"
PLAYER_CPP = REDMMO_SOURCE / "RedPlayerCharacter.cpp"
PAUSE_CPP = REDMMO_SOURCE / "RedPauseMenuWidget.cpp"

VIBE_SOURCE = ROOT / "Plugins/VibeMMOUIKit/Source/VibeMMOUIKit"
VIBE_DATA_H = VIBE_SOURCE / "Public/Data/VibeMMOUIDataAssets.h"
VIBE_HUD_H = VIBE_SOURCE / "Public/Widgets/VibeMMOHUDWidget.h"
VIBE_HUD_CPP = VIBE_SOURCE / "Private/Widgets/VibeMMOHUDWidget.cpp"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="strict")


def function_body(source: str, signature: str) -> str:
    start = source.index(signature)
    opening = source.index("{", start)
    depth = 0
    for index in range(opening, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[start : index + 1]
    raise AssertionError(f"unterminated function: {signature}")


def compiled_source_paths(root: Path) -> list[Path]:
    return sorted(
        path
        for path in root.rglob("*")
        if path.is_file() and path.suffix.lower() in {".h", ".cpp"}
    )


def compiled_source_text(root: Path) -> str:
    return "\n".join(read(path) for path in compiled_source_paths(root))


def class_body(source: str, signature: str) -> str:
    return function_body(source, signature)


def symbol_sites(root: Path, symbol: str) -> dict[str, int]:
    pattern = re.compile(rf"\b{re.escape(symbol)}\s*\(")
    sites = {}
    for path in compiled_source_paths(root):
        count = len(pattern.findall(read(path)))
        if count:
            sites[path.relative_to(root).as_posix()] = count
    return sites


def identifier_sites(root: Path, identifier: str) -> dict[str, int]:
    pattern = re.compile(rf"\b{re.escape(identifier)}\b")
    sites = {}
    for path in compiled_source_paths(root):
        count = len(pattern.findall(read(path)))
        if count:
            sites[path.relative_to(root).as_posix()] = count
    return sites


def quest_model_findings(source: str) -> list[str]:
    absent_identifiers = (
        "FRedQuest",
        "ERedQuest",
        "QuestState",
        "QuestProgress",
        "ActiveQuest",
        "QuestId",
        "QuestID",
        "ServerQuest",
        "OnRep_Quest",
        "MissionState",
        "JournalState",
    )
    findings = [
        identifier for identifier in absent_identifiers if identifier in source
    ]
    suspicious_state_names = re.compile(
        r"\b(?:quest|mission|journal)(?:state|progress|id|objective|entry|record)s?\b"
        r"|\b(?:active|completed|current|server|replicated)"
        r"(?:quest|mission|journal|objective)s?\b",
        re.IGNORECASE,
    )
    findings.extend(suspicious_state_names.findall(source))
    return findings


class Def0004ReplacementHUDQuestInventoryContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.widget_h = read(WIDGET_H)
        cls.widget_cpp = read(WIDGET_CPP)
        cls.types_h = read(TYPES_H)
        cls.snippet = read(INTEGRATION_SNIPPET)
        cls.hud_h = read(HUD_H)
        cls.hud_cpp = read(HUD_CPP)
        cls.player_cpp = read(PLAYER_CPP)
        cls.pause_cpp = read(PAUSE_CPP)
        cls.redmmo_source = compiled_source_text(REDMMO_SOURCE)
        cls.vibe_source = compiled_source_text(VIBE_SOURCE)
        cls.vibe_data_h = read(VIBE_DATA_H)
        cls.vibe_hud = read(VIBE_HUD_H) + read(VIBE_HUD_CPP)

    def test_replacement_consumer_exists_and_cache_starts_hidden(self):
        self.assertIn("struct FRedHUDQuestState", self.types_h)
        self.assertIn(
            "void SetQuestState(const FRedHUDQuestState& State);", self.widget_h
        )
        self.assertIn("bool bQuestVisible = false;", self.widget_h)

        initialized = function_body(
            self.widget_cpp, "void URedHUDWidget::NativeOnInitialized"
        )
        self.assertNotIn("ApplySnapshot(", initialized)

        setter = function_body(
            self.widget_cpp, "void URedHUDWidget::SetQuestState"
        )
        for token in (
            "bQuestVisible = State.bVisible;",
            "bLiveDataMode && State.bVisible",
            "State.Title",
            "State.Objective",
            "State.Current",
            "State.Target",
        ):
            self.assertIn(token, setter)

    def test_snapshot_is_the_only_compiled_redhud_quest_caller(self):
        apply_snapshot = function_body(
            self.widget_cpp, "void URedHUDWidget::ApplySnapshot"
        )
        self.assertIn("SetQuestState(Snapshot.Quest);", apply_snapshot)

        self.assertEqual(
            symbol_sites(REDHUD_SOURCE, "SetQuestState"),
            {
                "RedHUDRuntime/Private/RedHUDWidget.cpp": 2,
                "RedHUDRuntime/Public/RedHUDWidget.h": 1,
            },
        )
        self.assertEqual(
            symbol_sites(REDHUD_SOURCE, "ApplySnapshot"),
            {
                "RedHUDRuntime/Private/RedHUDWidget.cpp": 1,
                "RedHUDRuntime/Public/RedHUDWidget.h": 1,
            },
        )

        self.assertEqual(symbol_sites(REDMMO_SOURCE, "SetQuestState"), {})
        self.assertEqual(symbol_sites(REDMMO_SOURCE, "ApplySnapshot"), {})

    def test_redmmo_has_no_authoritative_or_replicated_quest_model(self):
        approved_voxel_helper = "ValidateStoredJournalState"
        self.assertEqual(
            identifier_sites(REDMMO_SOURCE, approved_voxel_helper),
            {"Mining/RedInMemorySparseVoxelBackend.cpp": 5},
        )
        quest_inventory_source = re.sub(
            rf"\b{re.escape(approved_voxel_helper)}\b",
            "ValidateStoredVoxelEditLedger",
            self.redmmo_source,
        )
        self.assertEqual(quest_model_findings(quest_inventory_source), [])

    def test_quest_model_scan_keeps_unapproved_journal_mutations_fail_closed(self):
        approved_voxel_helper = "ValidateStoredJournalState"
        approved_source = re.sub(
            rf"\b{re.escape(approved_voxel_helper)}\b",
            "ValidateStoredVoxelEditLedger",
            f"bool {approved_voxel_helper}(const FStoredVolume& Volume);",
        )
        self.assertEqual(quest_model_findings(approved_source), [])

        rejected_mutations = (
            "struct FJournalState {};",
            "JournalState Current;",
            "struct FRedQuestState {};",
            "int32 QuestProgress = 0;",
            "UPROPERTY(ReplicatedUsing=OnRep_Quest) FName QuestId;",
            "bool FValidateStoredJournalState = false;",
        )
        for mutation in rejected_mutations:
            with self.subTest(mutation=mutation):
                redacted = re.sub(
                    rf"\b{re.escape(approved_voxel_helper)}\b",
                    "ValidateStoredVoxelEditLedger",
                    mutation,
                )
                self.assertNotEqual(quest_model_findings(redacted), [])

    def test_vibe_quest_asset_is_definition_only_not_runtime_progress(self):
        for token in (
            "class VIBEMMOUIKIT_API UVibeMMOQuestDataAsset",
            "FText QuestTitle;",
            "FText QuestBody;",
            "TArray<FText> Objectives;",
        ):
            self.assertIn(token, self.vibe_data_h)

        quest_asset = class_body(
            self.vibe_data_h, "class VIBEMMOUIKIT_API UVibeMMOQuestDataAsset"
        )
        self.assertEqual(self.vibe_source.count("UVibeMMOQuestDataAsset"), 1)
        for missing_runtime_field in (
            "StableQuestId",
            "ActiveObjectiveId",
            "CurrentProgress",
            "CompletedObjectives",
            "ReplicatedUsing",
        ):
            self.assertNotIn(missing_runtime_field, quest_asset)
        for missing_hud_api in (
            "SetQuestState",
            "QuestState",
            "QuestProgress",
            "ActiveQuest",
            "OnQuest",
        ):
            self.assertNotIn(missing_hud_api, self.vibe_hud)

    def test_integration_snippet_is_noncompiled_example_with_placeholders(self):
        self.assertNotIn(REDHUD_SOURCE, INTEGRATION_SNIPPET.parents)
        for token in (
            "Example: add to your existing PlayerController class.",
            "AYourPlayerController",
            "ActiveQuestTitle",
            "ActiveQuestObjective",
            "ActiveQuestCurrent",
            "ActiveQuestTarget",
        ):
            self.assertIn(token, self.snippet)
        self.assertNotIn("AYourPlayerController", compiled_source_text(REDHUD_SOURCE))

    def test_resources_and_sample_defaults_are_not_a_quest_producer(self):
        update_resources = function_body(
            self.player_cpp, "void ARedPlayerCharacter::UpdateHUDResources"
        )
        self.assertIn("UpdateReplacementHUDResources(", update_resources)
        self.assertNotIn("ActiveHUDWidget->SetResourceTally", update_resources)
        self.assertNotIn("Quest", update_resources)
        self.assertNotIn("UpdateReplacementHUDQuest", self.hud_h + self.hud_cpp)

        gameplay_bridge = self.hud_cpp + self.player_cpp + self.pause_cpp
        for sample_default in (
            "Locate the Ancient Waygate",
            "Enter the Sunken Archive",
        ):
            self.assertNotIn(sample_default, gameplay_bridge)


if __name__ == "__main__":
    unittest.main()
