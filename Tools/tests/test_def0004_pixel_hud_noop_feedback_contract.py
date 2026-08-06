import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

REPLACEMENT_H = ROOT / "Plugins/RedHUD/Source/RedHUDRuntime/Public/RedHUDWidget.h"
REPLACEMENT_CPP = ROOT / "Plugins/RedHUD/Source/RedHUDRuntime/Private/RedHUDWidget.cpp"
PAUSE_CPP = ROOT / "Source/RedMMO/RedPauseMenuWidget.cpp"
VIBE_SUBSYSTEM_CPP = (
    ROOT
    / "Plugins/VibeMMOUIKit/Source/VibeMMOUIKit/Private/Persistence/"
    "VibeMMOHUDLayoutSubsystem.cpp"
)


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


class Def0004ReplacementHUDNoOpFeedbackContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.replacement_h = read(REPLACEMENT_H)
        cls.replacement_cpp = read(REPLACEMENT_CPP)
        cls.pause_cpp = read(PAUSE_CPP)
        cls.vibe_subsystem_cpp = read(VIBE_SUBSYSTEM_CPP)

    def test_public_contract_describes_change_signal_semantics(self):
        self.assertIn("Mutation results are change signals", self.replacement_h)
        self.assertIn("clamped/already-equal no-ops", self.replacement_h)

    def test_commit_sanitizes_and_rejects_equal_state_before_delegating(self):
        commit = function_body(
            self.replacement_cpp,
            "bool URedHUDWidget::CommitHUDElementLayout(",
        )
        sanitize = commit.index("Sanitized.Sanitize();")
        compare = commit.index("GetHUDElementLayout(Element).NearlyEquals(Sanitized)")
        delegate = commit.index("HUDLayoutSubsystem->SetElementLayout(Element, Sanitized)")
        self.assertLess(sanitize, compare)
        self.assertLess(compare, delegate)
        self.assertNotIn("SetElementLayout(Element, Layout)", commit)
        self.assertRegex(
            commit,
            re.compile(
                r"if\s*\(GetHUDElementLayout\(Element\)\.NearlyEquals\(Sanitized\)\)"
                r"\s*\{\s*return false;\s*\}",
                re.DOTALL,
            ),
        )

    def test_every_replacement_mutation_delegates_through_the_change_gate(self):
        for name in (
            "NudgeHUDElement",
            "SetHUDElementScale",
            "SetHUDElementOpacity",
            "SetHUDElementHidden",
            "SetHUDElementLocked",
        ):
            body = function_body(
                self.replacement_cpp,
                f"bool URedHUDWidget::{name}",
            )
            self.assertIn("CommitHUDElementLayout(Element, Layout)", body, name)

    def test_resets_reject_already_default_profiles_before_delegating(self):
        reset = function_body(
            self.replacement_cpp,
            "bool URedHUDWidget::ResetHUDElement",
        )
        reset_all = function_body(
            self.replacement_cpp,
            "bool URedHUDWidget::ResetAllHUDElements",
        )
        self.assertIn("GetHUDElementLayout(Element).IsDefault()", reset)
        self.assertLess(reset.index("return false;"), reset.index("ResetElementLayout"))
        self.assertLess(
            reset.index("GetHUDElementLayout(Element).IsDefault()"),
            reset.index("HUDLayoutSubsystem->ResetElementLayout(Element)"),
        )
        self.assertIn("GetLayoutProfile().ElementOverrides.IsEmpty()", reset_all)
        self.assertLess(reset_all.index("return false;"), reset_all.index("ResetLayout"))
        self.assertLess(
            reset_all.index("GetLayoutProfile().ElementOverrides.IsEmpty()"),
            reset_all.index("HUDLayoutSubsystem->ResetLayout()"),
        )

    def test_pause_feedback_distinguishes_locked_limited_and_unavailable(self):
        for name in (
            "HandleHUDMoveLeft",
            "HandleHUDMoveRight",
            "HandleHUDMoveUp",
            "HandleHUDMoveDown",
        ):
            body = function_body(
                self.pause_cpp,
                f"void URedPauseMenuWidget::{name}",
            )
            self.assertIn("Layout.bLocked", body, name)
            self.assertIn("HUD unavailable.", body, name)
            self.assertIn("movement limit or the profile is read-only", body, name)
        for name in ("HandleHUDScaleDown", "HandleHUDScaleUp"):
            body = function_body(
                self.pause_cpp,
                f"void URedPauseMenuWidget::{name}",
            )
            self.assertIn("Layout.bLocked", body, name)
            self.assertIn("HUD unavailable.", body, name)
            self.assertIn("size limit or the profile is read-only", body, name)

    def test_mutations_stop_when_preview_transaction_cannot_start(self):
        begin = function_body(
            self.pause_cpp,
            "bool URedPauseMenuWidget::BeginHUDCustomizationPreview",
        )
        self.assertIn("return false;", begin)
        self.assertIn("return true;", begin)
        for name in (
            "HandleHUDMoveLeft",
            "HandleHUDMoveRight",
            "HandleHUDMoveUp",
            "HandleHUDMoveDown",
            "HandleHUDScaleDown",
            "HandleHUDScaleUp",
            "HandleHUDOpacityDown",
            "HandleHUDOpacityUp",
            "HandleHUDToggleVisibility",
            "HandleHUDToggleLock",
            "HandleHUDResetElement",
            "HandleHUDResetAll",
        ):
            body = function_body(
                self.pause_cpp,
                f"void URedPauseMenuWidget::{name}",
            )
            self.assertRegex(
                body,
                re.compile(
                    r"if\s*\(!BeginHUDCustomizationPreview\(\)\)"
                    r"\s*\{\s*return;\s*\}",
                    re.DOTALL,
                ),
                name,
            )

        for name in (
            "HandleHUDMoveLeft",
            "HandleHUDMoveRight",
            "HandleHUDMoveUp",
            "HandleHUDMoveDown",
            "HandleHUDScaleDown",
            "HandleHUDScaleUp",
            "HandleHUDOpacityDown",
            "HandleHUDOpacityUp",
            "HandleHUDToggleVisibility",
            "HandleHUDToggleLock",
            "HandleHUDResetElement",
        ):
            body = function_body(
                self.pause_cpp,
                f"void URedPauseMenuWidget::{name}",
            )
            self.assertLess(
                body.index("bHUDResetAllArmed = false;"),
                body.index("if (!BeginHUDCustomizationPreview())"),
                name,
            )

    def test_reset_all_confirmation_survives_preview_refresh(self):
        begin = function_body(
            self.pause_cpp,
            "bool URedPauseMenuWidget::BeginHUDCustomizationPreview",
        )
        reset_all = function_body(
            self.pause_cpp,
            "void URedPauseMenuWidget::HandleHUDResetAll",
        )
        self.assertNotIn("bHUDResetAllArmed", begin)
        preview = reset_all.index("if (!BeginHUDCustomizationPreview())")
        arm_check = reset_all.index("if (!bHUDResetAllArmed)")
        confirm_disarm = reset_all.index("bHUDResetAllArmed = false;")
        delegate = reset_all.index("HUD->ResetAllHUDElements()")
        self.assertLess(preview, arm_check)
        self.assertLess(arm_check, confirm_disarm)
        self.assertLess(confirm_disarm, delegate)

    def test_shared_vibe_subsystem_keeps_compatibility_success_semantics(self):
        set_element = function_body(
            self.vibe_subsystem_cpp,
            "bool UVibeMMOHUDLayoutSubsystem::SetElementLayout(",
        )
        reset = function_body(
            self.vibe_subsystem_cpp,
            "bool UVibeMMOHUDLayoutSubsystem::ResetElementLayout",
        )
        self.assertIn("Before.NearlyEquals", set_element)
        self.assertRegex(
            set_element,
            re.compile(
                r"if\s*\(Before\.NearlyEquals\(Profile\.GetElementLayout\(Element\)\)\)"
                r"\s*\{\s*return true;\s*\}",
                re.DOTALL,
            ),
        )
        self.assertIn("!Profile.HasElementOverride(Element)", reset)
        self.assertRegex(
            reset,
            re.compile(
                r"if\s*\(!Profile\.HasElementOverride\(Element\)\)"
                r"\s*\{\s*return true;\s*\}",
                re.DOTALL,
            ),
        )


if __name__ == "__main__":
    unittest.main()
