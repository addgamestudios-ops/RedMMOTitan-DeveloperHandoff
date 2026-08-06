import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CHARACTER_HEADER = ROOT / "Source/RedMMO/RedPlayerCharacter.h"
CHARACTER_CPP = ROOT / "Source/RedMMO/RedPlayerCharacter.cpp"


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


class Def0002CompassBodyIdentityContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.header = read(CHARACTER_HEADER)
        cls.tick = function_body(read(CHARACTER_CPP), "void ARedPlayerCharacter::Tick")

    def test_stable_heading_cache_declares_an_explicit_empty_body_identity(self):
        self.assertIn(
            "FName LastStableCompassGravityBodyId = NAME_None;", self.header
        )

    def test_compass_uses_the_movement_components_stable_body_identity(self):
        self.assertIn(
            "ReferenceMovement->GetCurrentGravityBodyId()", self.tick
        )
        self.assertNotIn("RedGravity::QueryDominantBody", self.tick)

    def test_missing_or_changed_body_invalidates_before_tangent_evaluation(self):
        body_read = self.tick.index("const FName CompassGravityBodyId")
        invalidation = self.tick.index("if (CompassGravityBodyId.IsNone()", body_read)
        tangent = self.tick.index("const FVector TangentForward", invalidation)
        self.assertLess(body_read, invalidation)
        self.assertLess(invalidation, tangent)
        invalidation_block = self.tick[invalidation:tangent]
        for token in (
            "LastStableCompassGravityBodyId != CompassGravityBodyId",
            "bHasStableCompassHeading = false;",
            "LastStableCompassGravityBodyId = NAME_None;",
        ):
            self.assertIn(token, invalidation_block)

    def test_valid_tangent_heading_is_cached_only_with_a_valid_body(self):
        valid_tangent = self.tick.index("if (!TangentForward.IsNearlyZero()")
        fallback = self.tick.index("else if (bHasStableCompassHeading)", valid_tangent)
        cache_block = self.tick[valid_tangent:fallback]
        for token in (
            "if (!CompassGravityBodyId.IsNone())",
            "LastStableCompassHeadingDegrees = HeadingYaw;",
            "LastStableCompassGravityBodyId = CompassGravityBodyId;",
            "bHasStableCompassHeading = true;",
        ):
            self.assertIn(token, cache_block)

    def test_degenerate_tangent_fallback_requires_the_same_valid_body(self):
        fallback = self.tick.index("else if (bHasStableCompassHeading)")
        no_ship = self.tick.index("HeadingYaw = ReferenceActor->GetActorRotation().Yaw;", fallback)
        fallback_block = self.tick[fallback:no_ship]
        for token in (
            "!CompassGravityBodyId.IsNone()",
            "LastStableCompassGravityBodyId == CompassGravityBodyId",
            "HeadingYaw = LastStableCompassHeadingDegrees;",
        ):
            self.assertIn(token, fallback_block)

    def test_leaving_ship_context_clears_cached_body_and_validity(self):
        no_ship_heading = self.tick.index(
            "HeadingYaw = ReferenceActor->GetActorRotation().Yaw;"
        )
        no_ship_block = self.tick[no_ship_heading - 160:no_ship_heading]
        self.assertIn("bHasStableCompassHeading = false;", no_ship_block)
        self.assertIn("LastStableCompassGravityBodyId = NAME_None;", no_ship_block)


if __name__ == "__main__":
    unittest.main()
