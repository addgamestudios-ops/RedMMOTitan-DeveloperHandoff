import unittest
from pathlib import Path

from Tools.tests.test_def0002_ship_placement_transaction_contract import (
    function_body,
)


ROOT = Path(__file__).resolve().parents[2]
SHIP_CPP = ROOT / "Source/RedMMO/RedShip.cpp"
MOVEMENT_CPP = ROOT / "Source/RedMMO/RedShipMovementComponent.cpp"
CHARACTER_CPP = ROOT / "Source/RedMMO/RedPlayerCharacter.cpp"
DEFECT = ROOT / "ProjectKnowledge/defects/DEF-0002-fighter-landing-gravity-recovery.yaml"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="strict")


class Def0002ShipReboardContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ship = read(SHIP_CPP)
        cls.movement = read(MOVEMENT_CPP)
        cls.character = read(CHARACTER_CPP)
        cls.defect = read(DEFECT)

    def test_dominant_body_refresh_precedes_controller_early_return(self):
        tick = function_body(
            self.movement, "void URedShipMovementComponent::TickComponent"
        )
        body_query = tick.index("RedGravity::QueryDominantBodyDetailed(")
        controller_gate = tick.index("const AController* Controller")
        self.assertLess(body_query, controller_gate)
        for token in (
            "CurrentGravityBodyId",
            "GravityBodySwitchHysteresis",
            "CurrentGravityBodyId = Body.StableId;",
            "PlanetCenter = Body.Center;",
            "PlanetRadius = Body.SurfaceRadius;",
        ):
            self.assertIn(token, tick)

    def test_exit_parks_against_exact_terrain_in_the_radial_frame(self):
        exit_ship = function_body(self.ship, "void ARedShip::ExitShipAuthority")
        for token in (
            "ShipMovement->ClearFlightInputState();",
            "ShipMovement->StopMovementImmediately();",
            "RedPlanetTerrainQuery::LineTrace(",
            "FVector::VectorPlaneProject(GetActorForwardVector(), PlanetUp)",
            "FRotationMatrix::MakeFromXZ(",
            "ParkForward, PlanetUp",
            "GetLandingSupportDistance(",
            "PlanetUp, ParkRotation",
            "SetLandingAssistEnabled(true);",
            "SetLandingSettled(true);",
        ):
            self.assertIn(token, exit_ship)

        query = function_body(self.ship, "bool ARedShip::QueryLandingSurface")
        self.assertIn("RedPlanetTerrainQuery::LineTrace(", query)
        self.assertIn("ShipMovement->PlanetCenter", query)
        self.assertIn("NoMatchingPlanet", query)

    def test_reboard_clears_stale_flight_state_and_takeoff_input_releases_lock(self):
        enter_ship = function_body(self.ship, "void ARedShip::EnterShip")
        for token in (
            "SetLandingAssistEnabled(false);",
            "SetLandingSettled(false);",
            "LocalMoveAxes = FVector::ZeroVector;",
            "LocalRotationAxes = FVector::ZeroVector;",
            "ServerMoveAxes = FVector::ZeroVector;",
            "ServerRotationAxes = FVector::ZeroVector;",
            "RemoteFlightVelocity = FVector::ZeroVector;",
            "ShipMovement->ClearFlightInputState();",
            "ShipMovement->StopMovementImmediately();",
            "C->Possess(this);",
            "PC->SetIgnoreMoveInput(false);",
            "PC->SetIgnoreLookInput(false);",
        ):
            self.assertIn(token, enter_ship)

        thrust = function_body(self.ship, "void ARedShip::ThrustInput")
        lift = function_body(self.ship, "void ARedShip::LiftInput")
        server = function_body(
            self.ship, "void ARedShip::ServerSetFlightInput_Implementation"
        )
        self.assertIn("if (V > 0.35f) { SetLandingAssistEnabled(false); }", thrust)
        self.assertIn("if (V > 0.35f) { SetLandingAssistEnabled(false); }", lift)
        self.assertIn("MoveAxes.X > 0.35f || MoveAxes.Z > 0.35f", server)

    def test_landing_assist_uses_radial_up_and_zeroes_touchdown_velocity(self):
        assist = function_body(self.ship, "void ARedShip::ApplyLandingAssist")
        for token in (
            "const FVector SurfaceNormal = RadialUp;",
            "FVector::VectorPlaneProject(GetActorForwardVector(), SurfaceNormal)",
            "FRotationMatrix::MakeFromXZ(Forward, SurfaceNormal)",
            "GetLandingSupportDistance(",
            "SurfaceNormal, DesiredRotation",
            "SetLandingFlightVelocity(FVector::ZeroVector);",
            "SetLandingSettled(true);",
        ):
            self.assertIn(token, assist)

    def test_ship_compass_uses_tangent_frame_with_stable_fallback(self):
        for token in (
            "ReferenceMovement->PlanetCenter",
            "FVector::VectorPlaneProject(",
            "FVector TangentNorth",
            "FVector TangentEast = FVector::CrossProduct(",
            "FMath::Atan2(",
            "LastStableCompassHeadingDegrees = HeadingYaw;",
            "else if (bHasStableCompassHeading)",
            "ReplacementHUD->UpdateReplacementHUDCompass(HeadingYaw);",
        ):
            self.assertIn(token, self.character)

    def test_reversible_placement_lands_while_broader_recovery_keeps_defect_open(self):
        passive = function_body(
            self.movement,
            "bool URedShipMovementComponent::TryResolvePassiveTerrainPenetration",
        )
        self.assertIn("TranslationCollisionEnvelope.Get()", passive)
        self.assertIn("Envelope->IsAttachedTo(UpdatedPrimitive)", passive)
        self.assertIn("return false;", passive)

        assist = function_body(self.ship, "void ARedShip::ApplyLandingAssist")
        exit_ship = function_body(self.ship, "void ARedShip::ExitShipAuthority")
        self.assertIn("ShipMovement->TryCommitClearPlacement(", assist)
        self.assertIn("ShipMovement->TryCommitClearPlacement(", exit_ship)
        for unsafe_call in (
            "SetActorLocation(",
            "SetActorRotation(",
            "SetActorTransform(",
            "AddActorWorldOffset(",
        ):
            self.assertNotIn(unsafe_call, assist)

        self.assertIn("status: open", self.defect)
        self.assertIn("log dominant gravity body and radial up agreement", self.defect)
        self.assertNotIn("status: closed", self.defect)


if __name__ == "__main__":
    unittest.main()
