import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SHIP_H = ROOT / "Source/RedMMO/RedShip.h"
SHIP_CPP = ROOT / "Source/RedMMO/RedShip.cpp"
MOVEMENT_H = ROOT / "Source/RedMMO/RedShipMovementComponent.h"
DEFECT = ROOT / "ProjectKnowledge/defects/DEF-0002-fighter-landing-gravity-recovery.yaml"


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


class Def0002ShipGravityTelemetryContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ship_h = read(SHIP_H)
        cls.ship_cpp = read(SHIP_CPP)
        cls.movement_h = read(MOVEMENT_H)
        cls.defect = read(DEFECT)
        cls.telemetry = function_body(
            cls.ship_cpp, "void ARedShip::LogGravityAcceptanceSnapshot"
        )

    def test_movement_exposes_only_a_read_only_stable_body_id(self):
        self.assertIn("FName GetCurrentGravityBodyId() const", self.movement_h)
        self.assertIn("return CurrentGravityBodyId;", self.movement_h)
        self.assertNotIn("SetCurrentGravityBodyId", self.movement_h)

    def test_snapshot_is_explicitly_invoked_and_never_per_tick(self):
        self.assertIn(
            'UFUNCTION(Exec, BlueprintCallable, Category = "Red|Ship|Diagnostics")',
            self.ship_h,
        )
        self.assertIn(
            "void LogGravityAcceptanceSnapshot(FString Phase, "
            "bool bRequireShipUpAlignment = false);",
            self.ship_h,
        )
        for signature in (
            "void ARedShip::Tick",
            "void ARedShip::ApplyLandingAssist",
            "void ARedShip::EnterShip",
            "void ARedShip::ExitShipAuthority",
        ):
            self.assertNotIn(
                "LogGravityAcceptanceSnapshot(",
                function_body(self.ship_cpp, signature),
                signature,
            )

    def test_query_reuses_the_movement_stable_id_and_hysteresis(self):
        for token in (
            '#include "RedGravityBodies.h"',
            "const FName CachedBodyId = ShipMovement->GetCurrentGravityBodyId();",
            "RedGravity::QueryDominantBodyDetailed(",
            "World, Location, CachedBodyId,",
            "ShipMovement->GravityBodySwitchHysteresis, QueriedBody",
        ):
            self.assertIn(token, self.ship_cpp if token.startswith("#include") else self.telemetry)
        self.assertNotIn("GetName()", self.telemetry)
        self.assertNotIn("GetActorLabel", self.telemetry)

    def test_snapshot_reports_identity_frame_alignment_and_landing_state(self):
        for token in (
            "RED_SHIP_GRAVITY_ACCEPTANCE",
            r'phase=\"%s\"',
            "result=%s",
            "reason=%s",
            "localRole=%d",
            "netMode=%d",
            "authority=%d",
            "cachedBody=%s",
            "queriedBody=%s",
            r'cachedCenter=\"%s\"',
            r'queriedCenter=\"%s\"',
            "cachedRadiusCm=%.3f",
            "queriedRadiusCm=%.3f",
            "centerDeltaCm=%.3f",
            "radiusDeltaCm=%.3f",
            "radialUpDot=%.6f",
            "shipUpDot=%.6f",
            "framePass=%d",
            "alignmentRequired=%d",
            "alignmentPass=%d",
            "landingAssist=%d",
            "settled=%d",
        ):
            self.assertIn(token, self.telemetry)

    def test_missing_or_discordant_frames_fail_explicitly(self):
        for reason in (
            "missing_movement",
            "missing_world",
            "no_dominant_body",
            "invalid_cached_frame",
            "invalid_queried_frame",
            "body_id_mismatch",
            "center_mismatch",
            "radius_mismatch",
            "radial_up_mismatch",
            "ship_up_mismatch",
        ):
            self.assertIn(f'TEXT("{reason}")', self.telemetry)
        self.assertIn('bAcceptancePass ? TEXT("PASS") : TEXT("FAIL")', self.telemetry)
        self.assertIn("RadialUpDot >= 0.9999f", self.telemetry)
        self.assertIn("ShipUpDot >= 0.95f", self.telemetry)
        self.assertIn(
            "!bRequireShipUpAlignment || bShipUpMatch", self.telemetry
        )

    def test_phase_token_is_bounded_and_machine_safe(self):
        self.assertIn("FChar::IsAlnum(Character)", self.telemetry)
        for safe_character in ("TEXT('_')", "TEXT('-')", "TEXT('.')"):
            self.assertIn(safe_character, self.telemetry)
        self.assertIn("Phase[Index] = TEXT('_');", self.telemetry)
        self.assertIn("Phase = Phase.Left(64);", self.telemetry)

    def test_snapshot_does_not_mutate_flight_or_landing_state(self):
        for forbidden in (
            "CurrentGravityBodyId =",
            "PlanetCenter =",
            "PlanetRadius =",
            "SetActorLocation",
            "SetActorRotation",
            "SetLandingAssistEnabled",
            "SetLandingSettled",
            "ClearFlightInputState",
            "StopMovementImmediately",
            "ForceNetUpdate",
            "ShipMovement->Velocity =",
        ):
            self.assertNotIn(forbidden, self.telemetry)
        self.assertIn("status: open", self.defect)
        self.assertNotIn("status: closed", self.defect)


if __name__ == "__main__":
    unittest.main()
