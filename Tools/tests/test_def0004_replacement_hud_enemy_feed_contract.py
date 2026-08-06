import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
HUD_CPP = ROOT / "Source/RedMMO/RedHUD.cpp"
WIDGET_CPP = (
    ROOT
    / "Plugins/RedHUD/Source/RedHUDRuntime/Private/RedHUDWidget.cpp"
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


class Def0004ReplacementHUDEnemyFeedContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.hud_cpp = read(HUD_CPP)
        cls.widget_cpp = read(WIDGET_CPP)
        cls.draw_hud = function_body(cls.hud_cpp, "void ARedHUD::DrawHUD")
        cls.set_visible = function_body(
            cls.hud_cpp, "void ARedHUD::SetPixelExactHUDVisible"
        )
        cls.set_enemy = function_body(
            cls.widget_cpp, "void URedHUDWidget::SetEnemyState"
        )

    def test_target_dependent_early_returns_cannot_retain_stale_enemy_state(self):
        hidden = self.draw_hud.index("EnemyState.bVisible = false;")
        publish = self.draw_hud.index(
            "PixelExactHUDWidget->SetEnemyState(EnemyState);"
        )
        no_target_return = self.draw_hud.index("if (!TargetCharacter)")
        behind_camera_return = self.draw_hud.index("if (Projected.Z <= 0.0f")
        self.assertLess(hidden, publish)
        self.assertLess(publish, no_target_return)
        self.assertLess(publish, behind_camera_return)
        self.assertEqual(self.draw_hud.count("SetEnemyState("), 1)

    def test_visibility_transition_clears_target_data_before_re_show(self):
        hidden = self.set_visible.index("HiddenEnemyState.bVisible = false;")
        publish = self.set_visible.index(
            "PixelExactHUDWidget->SetEnemyState(HiddenEnemyState);"
        )
        root_visibility = self.set_visible.index(
            "PixelExactHUDWidget->SetVisibility("
        )
        self.assertLess(hidden, publish)
        self.assertLess(publish, root_visibility)

    def test_repeated_hidden_frames_are_a_no_op(self):
        guard = self.set_enemy.index("if (!State.bVisible && !bEnemyVisible)")
        visibility_assignment = self.set_enemy.index(
            "bEnemyVisible = State.bVisible;"
        )
        self.assertLess(guard, visibility_assignment)
        self.assertIn("return;", self.set_enemy[guard:visibility_assignment])

    def test_only_a_valid_live_enemy_can_become_visible(self):
        self.assertIn(
            "if (IsValid(TargetCharacter) && TargetCharacter->bIsEnemy",
            self.draw_hud,
        )
        self.assertIn("&& !TargetCharacter->IsDowned())", self.draw_hud)
        conditional = self.draw_hud.index("if (IsValid(TargetCharacter)")
        visible = self.draw_hud.index("EnemyState.bVisible = true;")
        publish = self.draw_hud.index(
            "PixelExactHUDWidget->SetEnemyState(EnemyState);"
        )
        self.assertLess(conditional, visible)
        self.assertLess(visible, publish)

    def test_health_is_normalized_and_bounded(self):
        self.assertIn("EnemyState.Health = 0.0f;", self.draw_hud)
        self.assertIn("EnemyState.MaxHealth = 1.0f;", self.draw_hud)
        self.assertIn(
            "TargetCharacter->GetHealthFraction(), 0.0f, 1.0f);",
            self.draw_hud,
        )

    def test_missing_metadata_uses_an_honest_generic_label_without_a_fake_level(self):
        self.assertIn('EnemyState.Name = TEXT("HOSTILE");', self.draw_hud)
        self.assertIn("EnemyState.Level = 0;", self.draw_hud)
        self.assertIn("State.Level > 0", self.set_enemy)
        self.assertIn('TEXT("LV %d  %s")', self.set_enemy)
        self.assertIn(": UpperName", self.set_enemy)
        self.assertNotIn('TEXT("LV 0', self.set_enemy)

    def test_existing_sight_and_world_bar_paths_are_preserved(self):
        for token in (
            "SweepSingleByObjectType(",
            "FMath::FInterpTo(TargetAlpha",
            "DrawLine(",
            "LocalCharacter->SetHUDReticleTargetAlpha(TargetAlpha);",
            "TargetCharacter->GetShieldFraction()",
            "TargetCharacter->GetHealthFraction()",
        ):
            self.assertIn(token, self.draw_hud)

    def test_enemy_feed_does_not_mutate_gameplay_state(self):
        for forbidden in (
            "ApplyDamage(",
            "SetActorLocation(",
            "SetActorTransform(",
            "Destroy(",
            "ForceNetUpdate(",
        ):
            self.assertNotIn(forbidden, self.draw_hud)


if __name__ == "__main__":
    unittest.main()
