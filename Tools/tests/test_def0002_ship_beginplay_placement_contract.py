import re
import unittest
from pathlib import Path

from Tools.tests.test_def0002_ship_placement_transaction_contract import (
    balanced_region,
    compact,
    function_body,
    helper_contract_passes,
    if_condition_and_block,
    statement_from,
)


ROOT = Path(__file__).resolve().parents[2]
SHIP_CPP = ROOT / "Source/RedMMO/RedShip.cpp"
MOVEMENT_CPP = ROOT / "Source/RedMMO/RedShipMovementComponent.cpp"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="strict")


def enclosing_if_conditions(function: str, marker: str):
    marker_index = function.index(marker)
    conditions = []
    search_index = 0
    while True:
        if_index = function.find("if", search_index)
        if if_index < 0:
            break
        before = function[if_index - 1] if if_index else " "
        after = function[if_index + 2] if if_index + 2 < len(function) else " "
        search_index = if_index + 2
        if (before.isalnum() or before == "_") or (after.isalnum() or after == "_"):
            continue
        condition_open = function.find("(", if_index + 2)
        if condition_open < 0:
            continue
        condition = balanced_region(function, condition_open, "(", ")")
        block_open = function.find("{", condition_open + len(condition))
        if block_open < 0:
            continue
        block = balanced_region(function, block_open, "{", "}")
        block_end = block_open + len(block)
        if block_open < marker_index < block_end:
            conditions.append(condition)
    return conditions


def root_transform_references(function: str):
    pattern = re.compile(
        r"\b("
        r"(?:K2_)?(?:Set|Add|Apply)[A-Za-z0-9_]*"
        r"(?:Location|Rotation|Transform|Offset|Scale)[A-Za-z0-9_]*"
        r"|Get[A-Za-z0-9_]*(?:Location|Rotation|Scale3D)_DirectMutable"
        r"|MoveComponent|TeleportTo|SetComponentToWorld"
        r")\b"
    )
    return pattern.findall(function)


def begin_play_contract_passes(ship_source: str) -> bool:
    try:
        begin_play = function_body(ship_source, "void ARedShip::BeginPlay")
        from_center_statement = statement_from(
            begin_play, "const FVector FromCenter"
        )
        radial_up_statement = statement_from(begin_play, "const FVector RadialUp")
        min_radius_statement = statement_from(
            begin_play, "const float MinShipRadius"
        )
        recovery_location_statement = statement_from(
            begin_play, "const FVector BeginPlayRecoveryLocation"
        )
        call_statement = statement_from(
            begin_play, "const bool bBeginPlayRecoveryCommitted"
        )
        call_index = begin_play.index(call_statement)
        enclosing_conditions = enclosing_if_conditions(
            begin_play, "const bool bBeginPlayRecoveryCommitted"
        )
        success_condition, success_block = if_condition_and_block(
            begin_play, "if (bBeginPlayRecoveryCommitted)"
        )
        success_if = begin_play.index("if (bBeginPlayRecoveryCommitted)")
        success_open = begin_play.index("{", success_if)
        success_end = success_open + len(success_block)
        else_index = begin_play.index("else", success_end)
        rejection_open = begin_play.index("{", else_index)
        rejection_block = balanced_region(begin_play, rejection_open, "{", "}")
        rejection_end = rejection_open + len(rejection_block)
    except (AssertionError, ValueError):
        return False

    expected_outer_condition = compact(
        "(HasAuthority()"
        " && ShipMovement"
        " && bRuntimeCollisionHullsConfigured"
        " && FVector::Dist(GetActorLocation(), PlanetController->PlanetCenter)"
        " < MinShipRadius)"
    )
    expected_from_center = compact(
        "const FVector FromCenter ="
        " GetActorLocation() - PlanetController->PlanetCenter;"
    )
    expected_radial_up = compact(
        "const FVector RadialUp = FromCenter.IsNearlyZero()"
        " ? FVector::UpVector : FromCenter.GetSafeNormal();"
    )
    expected_min_radius = compact(
        "const float MinShipRadius ="
        " PlanetController->GetGameplaySurfaceRadius()"
        " + (ShipMovement ? ShipMovement->MinimumSurfaceClearance : 300.0f);"
    )
    expected_recovery_location = compact(
        "const FVector BeginPlayRecoveryLocation ="
        " PlanetController->PlanetCenter + RadialUp * MinShipRadius;"
    )
    expected_call = compact(
        "const bool bBeginPlayRecoveryCommitted ="
        " ShipMovement->TryCommitClearPlacement("
        "BeginPlayRecoveryLocation,"
        "GetActorQuat(),"
        "true,"
        "ETeleportType::TeleportPhysics);"
    )
    expected_success = compact("{ ForceNetUpdate(); }")

    return all(
        (
            root_transform_references(begin_play) == [],
            len(re.findall(r"\bTryCommitClearPlacement\b", begin_play)) == 1,
            begin_play.count("const FVector FromCenter") == 1,
            begin_play.count("const FVector RadialUp") == 1,
            begin_play.count("const float MinShipRadius") == 1,
            begin_play.count("const FVector BeginPlayRecoveryLocation") == 1,
            begin_play.count("const bool bBeginPlayRecoveryCommitted") == 1,
            begin_play.count("bBeginPlayRecoveryCommitted") == 2,
            begin_play.count("ShipMovement->PlanetCenter =") == 1,
            begin_play.count("ShipMovement->PlanetRadius =") == 1,
            compact(from_center_statement) == expected_from_center,
            compact(radial_up_statement) == expected_radial_up,
            compact(min_radius_statement) == expected_min_radius,
            compact(recovery_location_statement) == expected_recovery_location,
            compact(call_statement) == expected_call,
            enclosing_conditions.count(
                next(
                    (
                        condition
                        for condition in enclosing_conditions
                        if "HasAuthority" in condition
                    ),
                    "",
                )
            )
            == 1,
            any(
                compact(condition) == expected_outer_condition
                for condition in enclosing_conditions
            ),
            begin_play.index("bRuntimeCollisionHullsConfigured = "
                             "TryConfigureRuntimeCollisionHulls();")
            < call_index,
            begin_play.index(
                "ShipMovement->PlanetCenter = PlanetController->PlanetCenter;"
            )
            < call_index,
            begin_play.index(
                "ShipMovement->PlanetRadius = "
                "PlanetController->GetGameplaySurfaceRadius();"
            )
            < call_index,
            compact(success_condition) == "(bBeginPlayRecoveryCommitted)",
            compact(success_block) == expected_success,
            success_end < else_index < rejection_open < rejection_end,
            "UE_LOG(LogRedShip, Warning" in rejection_block,
            root_transform_references(rejection_block) == [],
            "TryCommitClearPlacement(" not in rejection_block,
            "ForceNetUpdate();" not in rejection_block,
        )
    )


class Def0002ShipBeginPlayPlacementContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ship_source = read(SHIP_CPP)
        cls.movement_source = read(MOVEMENT_CPP)
        cls.begin_play = function_body(cls.ship_source, "void ARedShip::BeginPlay")

    def test_begin_play_correction_is_authority_owned_and_transactional(self):
        self.assertTrue(begin_play_contract_passes(self.ship_source))

    def test_contract_rejects_authority_or_scope_bypass(self):
        mutants = (
            self.ship_source.replace(
                "if (HasAuthority()\n\t\t\t&& ShipMovement",
                "if (ShipMovement",
                1,
            ),
            self.ship_source.replace(
                "if (HasAuthority()\n\t\t\t&& ShipMovement",
                "if (!HasAuthority()\n\t\t\t&& ShipMovement",
                1,
            ),
            self.ship_source.replace(
                "&& ShipMovement\n\t\t\t&& bRuntimeCollisionHullsConfigured"
                "\n\t\t\t&& FVector::Dist",
                "|| ShipMovement\n\t\t\t&& bRuntimeCollisionHullsConfigured"
                "\n\t\t\t&& FVector::Dist",
                1,
            ),
            self.ship_source.replace(
                "\n\t\t\t&& bRuntimeCollisionHullsConfigured",
                "",
                1,
            ),
            self.ship_source.replace(
                "const bool bBeginPlayRecoveryCommitted =",
                "if (HasAuthority()) {}\n\t\t\tconst bool bBeginPlayRecoveryCommitted =",
                1,
            ).replace(
                "if (HasAuthority()\n\t\t\t&& ShipMovement",
                "if (ShipMovement",
                1,
            ),
        )
        for mutant in mutants:
            with self.subTest(mutant=mutant[:80]):
                self.assertFalse(begin_play_contract_passes(mutant))

    def test_contract_rejects_wrong_placement_policy_or_ignored_result(self):
        mutations = (
            ("BeginPlayRecoveryLocation,", "GetActorLocation(),"),
            ("GetActorQuat(),", "FQuat::Identity,"),
            ("\n\t\t\t\t\ttrue,", "\n\t\t\t\t\tfalse,"),
            ("ETeleportType::TeleportPhysics", "ETeleportType::None"),
            (
                "const bool bBeginPlayRecoveryCommitted =",
                "const bool bBeginPlayRecoveryCommitted = true ||",
            ),
            (
                "if (bBeginPlayRecoveryCommitted)",
                "if (true)",
            ),
        )
        for original, replacement in mutations:
            with self.subTest(replacement=replacement):
                self.assertIn(original, self.ship_source)
                mutant = self.ship_source.replace(original, replacement, 1)
                self.assertFalse(begin_play_contract_passes(mutant))

    def test_contract_rejects_direct_or_duplicate_root_mutation(self):
        direct = self.ship_source.replace(
            "const bool bBeginPlayRecoveryCommitted =\n"
            "\t\t\t\tShipMovement->TryCommitClearPlacement(\n"
            "\t\t\t\t\tBeginPlayRecoveryLocation,\n"
            "\t\t\t\t\tGetActorQuat(),\n"
            "\t\t\t\t\ttrue,\n"
            "\t\t\t\t\tETeleportType::TeleportPhysics);",
            "SetActorLocation(BeginPlayRecoveryLocation, false, nullptr, "
            "ETeleportType::TeleportPhysics);\n"
            "\t\t\tconst bool bBeginPlayRecoveryCommitted = true;",
            1,
        )
        duplicate = self.ship_source.replace(
            "const bool bBeginPlayRecoveryCommitted =",
            "ShipMovement->TryCommitClearPlacement("
            "BeginPlayRecoveryLocation, GetActorQuat(), true, "
            "ETeleportType::TeleportPhysics);\n"
            "\t\t\tconst bool bBeginPlayRecoveryCommitted =",
            1,
        )
        self.assertFalse(begin_play_contract_passes(direct))
        self.assertFalse(begin_play_contract_passes(duplicate))

    def test_contract_rejects_frame_setup_after_attempt(self):
        assignment = (
            "ShipMovement->PlanetRadius = "
            "PlanetController->GetGameplaySurfaceRadius();"
        )
        mutant = self.ship_source.replace(assignment, "", 1).replace(
            "\t\t\t\t\tETeleportType::TeleportPhysics);\n"
            "\t\t\tif (bBeginPlayRecoveryCommitted)",
            "\t\t\t\t\tETeleportType::TeleportPhysics);\n"
            f"\t\t\t{assignment}\n"
            "\t\t\tif (bBeginPlayRecoveryCommitted)",
            1,
        )
        self.assertFalse(begin_play_contract_passes(mutant))

    def test_contract_rejects_geometry_alias_or_obfuscated_bypasses(self):
        insert_marker = "\t\tbreak;\n\t}"
        mutants = (
            self.ship_source.replace(
                "PlanetController->PlanetCenter + RadialUp * MinShipRadius;",
                "GetActorLocation();",
                1,
            ),
            self.ship_source.replace(
                "PlanetController->GetGameplaySurfaceRadius()\n"
                "\t\t\t+ (ShipMovement ? ShipMovement->MinimumSurfaceClearance : 300.0f);",
                "1.0f;",
                1,
            ),
            self.ship_source.replace(
                insert_marker,
                "\t\tAddActorLocalOffset(FVector::UpVector);\n" + insert_marker,
                1,
            ),
            self.ship_source.replace(
                insert_marker,
                "\t\tGetRootComponent()->AddWorldOffset(FVector::UpVector);\n"
                + insert_marker,
                1,
            ),
            self.ship_source.replace(
                insert_marker,
                "\t\tauto* SelfAlias = this;\n"
                "\t\tSelfAlias->SetActorLocation(FVector::ZeroVector);\n"
                + insert_marker,
                1,
            ),
            self.ship_source.replace(
                insert_marker,
                "\t\tShipMovement /* no bypass */ -> "
                "TryCommitClearPlacement /* still a call */ "
                "(GetActorLocation(), GetActorQuat(), true, "
                "ETeleportType::TeleportPhysics);\n"
                + insert_marker,
                1,
            ),
            self.ship_source.replace(
                insert_marker,
                "\t\tauto* MovementAlias = ShipMovement;\n"
                "\t\tMovementAlias->TryCommitClearPlacement("
                "GetActorLocation(), GetActorQuat(), true, "
                "ETeleportType::TeleportPhysics);\n"
                + insert_marker,
                1,
            ),
            self.ship_source.replace(
                insert_marker,
                "\t\tauto* RootAlias = GetRootComponent();\n"
                "\t\tRootAlias->MoveComponent(FVector::UpVector, "
                "GetActorQuat(), false);\n"
                + insert_marker,
                1,
            ),
            self.ship_source.replace(
                insert_marker,
                "\t\tCollisionSphere->AddWorldOffset("
                "FVector::UpVector, false, nullptr, "
                "ETeleportType::TeleportPhysics);\n"
                + insert_marker,
                1,
            ),
            self.ship_source.replace(
                insert_marker,
                "\t\tSetActorRelativeLocation("
                "FVector::UpVector, false, nullptr, "
                "ETeleportType::TeleportPhysics);\n"
                + insert_marker,
                1,
            ),
        )
        for mutant in mutants:
            with self.subTest(mutant=mutant[-160:]):
                self.assertNotEqual(self.ship_source, mutant)
                self.assertFalse(begin_play_contract_passes(mutant))

    def test_contract_rejects_decoys_member_pointers_and_transform_families(self):
        insert_marker = "\t\tbreak;\n\t}"
        exact_target = (
            "const FVector BeginPlayRecoveryLocation =\n"
            "\t\t\t\tPlanetController->PlanetCenter + RadialUp * MinShipRadius;"
        )
        exact_center = (
            "ShipMovement->PlanetCenter = PlanetController->PlanetCenter;"
        )
        mutants = (
            self.ship_source.replace(
                exact_target,
                "if (false)\n\t\t\t{\n"
                f"\t\t\t\t{exact_target}\n"
                "\t\t\t}\n"
                "\t\t\tconst FVector BeginPlayRecoveryLocation = "
                "GetActorLocation();",
                1,
            ),
            self.ship_source.replace(
                exact_center,
                "if (false) { "
                + exact_center
                + " }\n"
                "\t\t\tShipMovement->PlanetCenter = FVector::ZeroVector;",
                1,
            ),
            self.ship_source.replace(
                "if (bBeginPlayRecoveryCommitted)",
                "if (true) { const bool bBeginPlayRecoveryCommitted = true; }\n"
                "\t\t\tif (bBeginPlayRecoveryCommitted)",
                1,
            ),
            self.ship_source.replace(
                insert_marker,
                "\t\tauto PlacementMember = "
                "&URedShipMovementComponent::TryCommitClearPlacement;\n"
                + insert_marker,
                1,
            ),
            self.ship_source.replace(
                insert_marker,
                "\t\tauto LocationMember = &ARedShip::SetActorLocation;\n"
                + insert_marker,
                1,
            ),
            self.ship_source.replace(
                insert_marker,
                "\t\tSetActorScale3D(FVector(2.0f));\n" + insert_marker,
                1,
            ),
            self.ship_source.replace(
                insert_marker,
                "\t\tGetRootComponent()->SetComponentToWorld(FTransform());\n"
                + insert_marker,
                1,
            ),
            self.ship_source.replace(
                insert_marker,
                "\t\tK2_SetActorLocationAndRotation("
                "FVector::ZeroVector, FRotator::ZeroRotator, false, "
                "FHitResult(), true);\n"
                + insert_marker,
                1,
            ),
            self.ship_source.replace(
                insert_marker,
                "\t\tAddActorWorldTransformKeepScale(FTransform());\n"
                + insert_marker,
                1,
            ),
            self.ship_source.replace(
                insert_marker,
                "\t\tGetRootComponent()->K2_SetWorldLocationAndRotation("
                "FVector::ZeroVector, FRotator::ZeroRotator, false, "
                "FHitResult(), true);\n"
                + insert_marker,
                1,
            ),
            self.ship_source.replace(
                insert_marker,
                "\t\tGetRootComponent()->AddRelativeLocation("
                "FVector::UpVector);\n"
                + insert_marker,
                1,
            ),
        )
        for mutant in mutants:
            with self.subTest(mutant=mutant[-180:]):
                self.assertNotEqual(self.ship_source, mutant)
                self.assertFalse(begin_play_contract_passes(mutant))

    def test_contract_rejects_direct_no_physics_and_world_offset_apis(self):
        insert_marker = "\t\tbreak;\n\t}"
        statements = (
            "ApplyWorldOffset(FVector::UpVector, false);",
            "GetRootComponent()->ApplyWorldOffset(FVector::UpVector, false);",
            "GetRootComponent()->SetWorldLocationAndRotationNoPhysics("
            "FVector::ZeroVector, FQuat::Identity);",
            "GetRootComponent()->SetRelativeLocation_Direct(FVector::ZeroVector);",
            "GetRootComponent()->GetRelativeLocation_DirectMutable() = "
            "FVector::ZeroVector;",
        )
        for statement in statements:
            with self.subTest(statement=statement):
                mutant = self.ship_source.replace(
                    insert_marker,
                    f"\t\t{statement}\n" + insert_marker,
                    1,
                )
                self.assertNotEqual(self.ship_source, mutant)
                self.assertFalse(begin_play_contract_passes(mutant))

    def test_existing_transaction_still_fails_closed_before_mutation(self):
        self.assertTrue(helper_contract_passes(self.movement_source))
        helper = function_body(
            self.movement_source,
            "bool URedShipMovementComponent::TryCommitClearPlacement",
        )
        readiness = statement_from(helper, "const bool bPlacementReady")
        route_inputs, rejected_route = if_condition_and_block(
            helper, "if (RootStart.ContainsNaN()"
        )
        self.assertIn("Envelope", readiness)
        self.assertIn("PlanetCenter.ContainsNaN()", readiness)
        self.assertIn("PlanetRadius > 0.0f", readiness)
        self.assertIn(
            "PlacementDistance > RedShipPlacementRouteMaxTranslationCm",
            route_inputs,
        )
        self.assertEqual("{returnfalse;}", compact(rejected_route))
        self.assertLess(
            helper.index("if (!bPlacementReady)"),
            helper.index("FScopedMovementUpdate ScopedMove"),
        )


if __name__ == "__main__":
    unittest.main()
