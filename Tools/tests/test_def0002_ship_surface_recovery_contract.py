import re
import unittest
from pathlib import Path

from Tools.tests.test_def0002_ship_placement_transaction_contract import (
    balanced_region,
    compact,
    function_body,
    if_condition_and_block,
    statement_from,
    strip_cpp_comments_and_literals,
)


ROOT = Path(__file__).resolve().parents[2]
MOVEMENT_CPP = ROOT / "Source/RedMMO/RedShipMovementComponent.cpp"
MOVEMENT_H = ROOT / "Source/RedMMO/RedShipMovementComponent.h"
HELPER_SIGNATURE = (
    "URedShipMovementComponent::TryCommitBoundedSurfaceRecovery"
)
CLAMP_SIGNATURE = (
    "void URedShipMovementComponent::ClampToPlanetSurface"
)


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="strict")


DIRECT_ROOT_MUTATOR = re.compile(
    r"(?:"
    r"\b(?:K2_)?Set(?:World|Actor|Relative|Component)[A-Za-z0-9_]*\b"
    r"|\b(?:K2_)?Add(?:World|Actor|Relative|Local)[A-Za-z0-9_]*\b"
    r"|\b(?:ApplyWorldOffset|TeleportTo|SetComponentToWorld"
    r"|InternalSetWorldLocationAndRotation|SetBodyTransform"
    r"|SetKinematicTarget|SetGlobalPose|SetLocation|SetRotation"
    r"|SetTranslation|SetScale3D|PropagateTransformUpdate"
    r"|MoveComponent|MoveComponentImpl"
    r"|ConditionalUpdateComponentToWorld|UpdateComponentToWorld)\b"
    r"|\bSet[A-Z][A-Za-z0-9_]*\b"
    r"|\b(?:ComponentToWorld|RelativeLocation|RelativeRotation"
    r"|RelativeScale3D)\s*(?:=|\+=|-=|\*=|/=)"
    r")"
)


def lambda_body(source: str, marker: str) -> str:
    start = source.index(marker)
    opening = source.index("{", start)
    return balanced_region(source, opening, "{", "}")


def switch_body(source: str, marker: str) -> str:
    start = source.index(marker)
    opening = source.index("{", start)
    return balanced_region(source, opening, "{", "}")


def nth_statement(source: str, marker: str, occurrence: int) -> str:
    start = -1
    for _ in range(occurrence + 1):
        start = source.index(marker, start + 1)
    end = source.index(";", start) + 1
    return source[start:end]


def mutate_function_once(
    source: str, signature: str, original: str, replacement: str
) -> str:
    clean = strip_cpp_comments_and_literals(source)
    start = clean.index(signature)
    opening = clean.index("{", start)
    clean_body = balanced_region(clean, opening, "{", "}")
    end = opening + len(clean_body)
    region = source[start:end]
    if original not in region:
        raise AssertionError(
            f"mutation target absent from {signature}: {original}"
        )
    mutated = region.replace(original, replacement, 1)
    return source[:start] + mutated + source[end:]


def rejected_guard_is_exact(helper: str, marker: str, condition: str) -> bool:
    try:
        actual_condition, actual_block = if_condition_and_block(helper, marker)
    except (AssertionError, ValueError):
        return False
    return (
        compact(actual_condition) == compact(condition)
        and compact(actual_block)
        == "{returnESurfaceRecoveryResult::Rejected;}"
    )


def helper_contract_passes(source: str, header: str) -> bool:
    try:
        helper = function_body(source, HELPER_SIGNATURE)
        ready_statement = statement_from(helper, "const bool bRecoveryReady")
        fitted_geometry_statement = statement_from(
            helper, "const bool bValidFittedGeometry"
        )
        recovery_geometry_statement = statement_from(
            helper, "const bool bValidRecoveryGeometry"
        )
        initial_clean_statement = statement_from(
            helper, "const bool bInitialExactCleanNoHit"
        )
        initial_query_statement = statement_from(
            helper,
            "const ERedPlanetTerrainQueryResult InitialExactResult",
        )
        initial_penetration_statement = statement_from(
            helper, "const bool bInitialExactWitnessPenetration"
        )
        root_native_route_statement = nth_statement(
            helper, "World->ComponentSweepMulti(", 0
        )
        envelope_native_route_statement = nth_statement(
            helper, "World->ComponentSweepMulti(", 1
        )
        witness_ready_statement = statement_from(
            helper, "const bool bAuthenticatedWitnessReady"
        )
        forward_statement = statement_from(
            helper,
            "const ERedPlanetTerrainQueryResult ExactForwardRouteResult",
        )
        reverse_statement = statement_from(
            helper,
            "const ERedPlanetTerrainQueryResult ExactReverseRouteResult",
        )
        routes_statement = statement_from(
            helper, "const bool bExactRoutesAuthenticated"
        )
        route_hit_validator = lambda_body(
            helper, "auto IsAuthenticatedExactRouteHit"
        )
        route_reject_condition, route_reject_block = if_condition_and_block(
            route_hit_validator, "if (!Candidate.bBlockingHit"
        )
        route_surface_return = statement_from(
            route_hit_validator,
            "return !Candidate.ImpactPoint.ContainsNaN()",
        )
        endpoint = lambda_body(helper, "auto IsTargetEndpointClear")
        endpoint_envelope_statement = statement_from(
            endpoint, "const bool bEnvelopeNativeBlocked"
        )
        endpoint_root_statement = statement_from(
            endpoint, "const bool bRootNativeBlocked"
        )
        endpoint_exact_statement = statement_from(
            endpoint,
            "const ERedPlanetTerrainQueryResult EndpointExactResult",
        )
        endpoint_return = statement_from(endpoint, "return !bEnvelopeNativeBlocked")
        commit_statement = statement_from(helper, "const bool bMoveReported")
        target_pose_statement = statement_from(
            helper, "const bool bTargetPoseReached"
        )
        failure_condition, failure_block = if_condition_and_block(
            helper, "if (!bTargetPoseReached"
        )
        not_required_condition, not_required_block = if_condition_and_block(
            helper,
            "if (bInitialExactCleanNoHit\n"
            "\t\t\t&& CurrentEnvelopeMinimumRadius",
        )
        not_required_return_index = helper.index(
            "return ESurfaceRecoveryResult::NotRequired;"
        )
        ambiguous_shell_index = helper.index(
            "CurrentEnvelopeMaximumRadius + 0.05"
        )
        endpoint_preflight_index = helper.index(
            "if (!IsTargetEndpointClear())"
        )
        scoped_move_index = helper.index(
            "FScopedMovementUpdate ScopedMove"
        )
    except (AssertionError, ValueError):
        return False

    header_compact = compact(header)
    helper_compact = compact(helper)
    helper_clean = strip_cpp_comments_and_literals(helper)
    expected_ready_terms = (
        "World",
        "PawnOwner",
        "PawnOwner->HasAuthority()",
        "!PawnOwner->GetAttachParentActor()",
        "UpdatedComponent",
        "UpdatedPrimitive",
        "UpdatedPrimitive->GetOwner() == PawnOwner",
        "UpdatedPrimitive->GetMobility() == EComponentMobility::Movable",
        "UpdatedPrimitive->IsRegistered()",
        "UpdatedPrimitive->IsPhysicsStateCreated()",
        "UpdatedPrimitive->IsQueryCollisionEnabled()",
        "Envelope",
        "Envelope != UpdatedPrimitive",
        "Envelope->GetOwner() == PawnOwner",
        "Envelope->IsRegistered()",
        "Envelope->IsPhysicsStateCreated()",
        "Envelope->IsQueryCollisionEnabled()",
        "Envelope->GetAttachParent() == UpdatedPrimitive",
        "!Envelope->IsUsingAbsoluteLocation()",
        "!Envelope->IsUsingAbsoluteRotation()",
        "!Envelope->IsUsingAbsoluteScale()",
        "!PlanetCenter.ContainsNaN()",
        "FMath::IsFinite(PlanetRadius)",
        "PlanetRadius > 0.0f",
        "FMath::IsFinite(MinimumSurfaceClearance)",
        "MinimumSurfaceClearance >= 0.0f",
        "!RequestedRootLocation.ContainsNaN()",
    )
    expected_ready = compact(
        "const bool bRecoveryReady = "
        + " && ".join(expected_ready_terms)
        + ";"
    )
    required_fitted_terms = (
        "TargetEnvelopeRotation.Equals(CurrentEnvelopeRotation, 1.0e-6f)",
        "BoxExtent.X > UE_KINDA_SMALL_NUMBER",
        "BoxExtent.Y > UE_KINDA_SMALL_NUMBER",
        "BoxExtent.Z > UE_KINDA_SMALL_NUMBER",
        "FMath::IsFinite(EnvelopeRadialSupport)",
        "FMath::IsFinite(FittedEnvelopeLift)",
        "FMath::IsFinite(CurrentEnvelopeMinimumRadius)",
        "FMath::IsFinite(CurrentEnvelopeMaximumRadius)",
        "FMath::IsFinite(TargetEnvelopeMinimumRadius)",
        "FMath::IsFinite(ExpectedTargetEnvelopeMinimumRadius)",
        "TargetEnvelopeMinimumRadius + 0.05 >= RequestedRadius",
        "TargetEnvelopeMinimumRadius - ExpectedTargetEnvelopeMinimumRadius",
    )
    required_recovery_terms = (
        "!RecoveryDelta.ContainsNaN()",
        "FMath::IsFinite(RecoveryDistance)",
        "RecoveryDistance > UE_KINDA_SMALL_NUMBER",
        "RecoveryDistance <= RedShipSurfaceRecoveryMaxTranslationCm",
        "ConstrainedRecoveryDelta.Equals(RecoveryDelta, 0.01f)",
        "RecoveryDelta.GetSafeNormal(), RadialUp) > 0.999999f",
    )
    expected_commit = compact(
        "const bool bMoveReported = Super::MoveUpdatedComponentImpl("
        "RecoveryDelta, CurrentRootRotation, false, &RecoveryMoveHit,"
        " ETeleportType::TeleportPhysics);"
    )
    expected_initial_query = compact(
        "const ERedPlanetTerrainQueryResult InitialExactResult ="
        " RedPlanetTerrainQuery::Sweep("
        "World, PlanetCenter, CurrentEnvelopeLocation,"
        " CurrentEnvelopeLocation, CurrentEnvelopeRotation,"
        " EnvelopeShape, InitialExactHit, &InitialExactChunkKey);"
    )
    expected_forward_query = compact(
        "const ERedPlanetTerrainQueryResult ExactForwardRouteResult ="
        " RedPlanetTerrainQuery::Sweep("
        "World, PlanetCenter, CurrentEnvelopeLocation,"
        " TargetEnvelopeLocation, CurrentEnvelopeRotation,"
        " EnvelopeShape, ExactForwardRouteHit,"
        " &ExactForwardRouteChunkKey);"
    )
    expected_reverse_query = compact(
        "const ERedPlanetTerrainQueryResult ExactReverseRouteResult ="
        " RedPlanetTerrainQuery::Sweep("
        "World, PlanetCenter, TargetEnvelopeLocation,"
        " CurrentEnvelopeLocation, CurrentEnvelopeRotation,"
        " EnvelopeShape, ExactReverseRouteHit,"
        " &ExactReverseRouteChunkKey);"
    )
    expected_root_native_route = compact(
        "World->ComponentSweepMulti("
        "RootRouteHits, UpdatedPrimitive, RootStart,"
        " TargetRootLocation, CurrentRootRotation,"
        " RootNativeParams);"
    )
    expected_envelope_native_route = compact(
        "World->ComponentSweepMulti("
        "EnvelopeRouteHits, Envelope, CurrentEnvelopeLocation,"
        " TargetEnvelopeLocation, CurrentEnvelopeRotation,"
        " EnvelopeNativeParams);"
    )
    expected_target_pose = compact(
        "const bool bTargetPoseReached = bMoveReported"
        " && !RecoveryMoveHit.bBlockingHit"
        " && !RecoveryMoveHit.bStartPenetrating"
        " && UpdatedPrimitive->GetComponentLocation().Equals("
        "TargetRootLocation, 0.05f)"
        " && UpdatedPrimitive->GetComponentQuat().Equals("
        "CurrentRootRotation, 1.0e-6f);"
    )
    expected_route_reject_condition = compact(
        "(!Candidate.bBlockingHit"
        " || Candidate.bStartPenetrating != bExpectedStartPenetrating"
        " || Candidate.GetComponent() != ExactWitnessComponent"
        " || Candidate.GetActor() != ExactWitnessActor"
        " || CandidateChunkKey != ExactWitnessChunkKey)"
    )
    expected_route_surface_return = compact(
        "return !Candidate.ImpactPoint.ContainsNaN()"
        " && !Candidate.ImpactNormal.ContainsNaN()"
        " && !CandidateNormal.IsNearlyZero()"
        " && FMath::IsFinite(CandidateSurfaceRadius)"
        " && FVector::Dist(Candidate.ImpactPoint,"
        " AuthenticatedSurfaceHit->ImpactPoint) <= ExactWitnessToleranceCm"
        " && FMath::Abs(CandidateSurfaceRadius"
        " - ExactWitnessSurfaceRadius) <= ExactWitnessToleranceCm"
        " && (bRequireOutwardNormal"
        " ? WitnessNormalAlignment > 0.1f"
        " : FMath::Abs(WitnessNormalAlignment) > 0.1f)"
        " && (bRequireOutwardNormal"
        " ? RadialNormalAlignment > 0.01f"
        " : FMath::Abs(RadialNormalAlignment) > 0.01f);"
    )
    expected_endpoint_envelope = compact(
        "const bool bEnvelopeNativeBlocked ="
        " World->OverlapBlockingTestByChannel("
        "TargetEnvelopeLocation, TargetEnvelopeRotation,"
        " Envelope->GetCollisionObjectType(), EnvelopeShape,"
        " EnvelopeNativeParams, EnvelopeResponseParams);"
    )
    expected_endpoint_root = compact(
        "const bool bRootNativeBlocked ="
        " World->OverlapBlockingTestByChannel("
        "TargetRootLocation, CurrentRootRotation,"
        " UpdatedPrimitive->GetCollisionObjectType(), RootShape,"
        " RootNativeParams, RootResponseParams);"
    )
    expected_endpoint_exact = compact(
        "const ERedPlanetTerrainQueryResult EndpointExactResult ="
        " RedPlanetTerrainQuery::Sweep("
        "World, PlanetCenter, TargetEnvelopeLocation,"
        " TargetEnvelopeLocation, TargetEnvelopeRotation,"
        " EnvelopeShape, EndpointExactHit, &EndpointExactChunkKey);"
    )
    expected_endpoint_return = compact(
        "return !bEnvelopeNativeBlocked"
        " && !bRootNativeBlocked"
        " && bExactEndpointClear"
        " && !EndpointExactHit.bBlockingHit"
        " && !EndpointExactHit.bStartPenetrating"
        " && EndpointExactChunkKey == InvalidChunkKey;"
    )
    expected_routes_statement = compact(
        "const bool bExactRoutesAuthenticated ="
        " (bExactPolicy"
        " && ExactForwardRouteResult"
        " == ERedPlanetTerrainQueryResult::Hit"
        " && ExactReverseRouteResult"
        " == ERedPlanetTerrainQueryResult::Hit"
        " && IsAuthenticatedExactRouteHit("
        "ExactForwardRouteHit, ExactForwardRouteChunkKey,"
        " bInitialExactWitnessPenetration, false)"
        " && IsAuthenticatedExactRouteHit("
        "ExactReverseRouteHit, ExactReverseRouteChunkKey,"
        " false, true))"
        " || (bLegacyPolicy"
        " && ExactForwardRouteResult"
        " == ERedPlanetTerrainQueryResult::NoMatchingPlanet"
        " && ExactReverseRouteResult"
        " == ERedPlanetTerrainQueryResult::NoMatchingPlanet"
        " && !ExactForwardRouteHit.bBlockingHit"
        " && !ExactForwardRouteHit.bStartPenetrating"
        " && !ExactReverseRouteHit.bBlockingHit"
        " && !ExactReverseRouteHit.bStartPenetrating"
        " && ExactForwardRouteChunkKey == InvalidChunkKey"
        " && ExactReverseRouteChunkKey == InvalidChunkKey);"
    )

    witness_terms = (
        "AuthenticatedSurfaceHit->bBlockingHit",
        "!AuthenticatedSurfaceHit->bStartPenetrating",
        "IsValid(ExactWitnessComponent)",
        "IsValid(ExactWitnessActor)",
        "ExactWitnessComponent->GetOwner() == ExactWitnessActor",
        "ExactWitnessChunkKey.X != INDEX_NONE",
        "ExactWitnessChunkKey.Y != INDEX_NONE",
        "ExactWitnessChunkKey.Z != INDEX_NONE",
        "!AuthenticatedSurfaceHit->ImpactPoint.ContainsNaN()",
        "!AuthenticatedSurfaceHit->ImpactNormal.ContainsNaN()",
        "!AuthenticatedSurfaceHit->TraceStart.ContainsNaN()",
        "!AuthenticatedSurfaceHit->TraceEnd.ContainsNaN()",
        "FMath::IsFinite(AuthenticatedSurfaceHit->Time)",
        "AuthenticatedSurfaceHit->Time >= 0.0f",
        "AuthenticatedSurfaceHit->Time <= 1.0f",
        "FVector::DotProduct(WitnessTraceDirection,-RadialUp)>0.999999f",
        "FVector::DotProduct(WitnessRadialUp,RadialUp)>0.999999f",
        "ExactWitnessNormal, RadialUp) > 0.01f",
        "AuthenticatedSurfaceHit->TraceStart - PlanetCenter",
        "RadialUp) > ExactWitnessSurfaceRadius",
        "AuthenticatedSurfaceHit->TraceEnd.Equals",
        "PlanetCenter, 0.1f",
        "RequestedRootLocation.Equals",
        "ExpectedRequestedRootLocation, 0.1f",
    )
    route_terms = (
        "ExactForwardRouteResult",
        "ExactReverseRouteResult",
        "ExactForwardRouteChunkKey",
        "ExactReverseRouteChunkKey",
        "Candidate.GetComponent() != ExactWitnessComponent",
        "Candidate.GetActor() != ExactWitnessActor",
        "CandidateChunkKey != ExactWitnessChunkKey",
        "Candidate.bStartPenetrating != bExpectedStartPenetrating",
        "Candidate.ImpactPoint",
        "ExactWitnessToleranceCm",
        "CandidateSurfaceRadius-ExactWitnessSurfaceRadius",
        "WitnessNormalAlignment",
        "RadialNormalAlignment",
        "bInitialExactWitnessPenetration",
        "ExactForwardRouteChunkKey == InvalidChunkKey",
        "ExactReverseRouteChunkKey == InvalidChunkKey",
    )

    return all(
        (
            "enumclassESurfaceRecoveryResult:uint8"
            "{Rejected,NotRequired,Committed};" in header_compact,
            "constFHitResult*AuthenticatedSurfaceHit=nullptr"
            in header_compact,
            "constFIntVector*AuthenticatedSurfaceChunkKey=nullptr"
            in header_compact,
            compact(ready_statement) == expected_ready,
            helper_clean.count("bAuthenticatedWitnessReady") == 2,
            helper_clean.count("bInitialExactCleanNoHit") == 4,
            helper_clean.count("bInitialExactWitnessPenetration") == 3,
            helper_clean.count("bExactRoutesAuthenticated") == 2,
            rejected_guard_is_exact(
                helper, "if (!bRecoveryReady)", "(!bRecoveryReady)"
            ),
            rejected_guard_is_exact(
                helper,
                "if (!bValidFittedGeometry)",
                "(!bValidFittedGeometry)",
            ),
            rejected_guard_is_exact(
                helper,
                "if (!bValidRecoveryGeometry)",
                "(!bValidRecoveryGeometry)",
            ),
            "if (!RootShape.IsSphere() || !EnvelopeShape.IsBox())"
            in helper,
            rejected_guard_is_exact(
                helper,
                "if (!RootShape.IsSphere() || !EnvelopeShape.IsBox())",
                "(!RootShape.IsSphere() || !EnvelopeShape.IsBox())",
            ),
            all(
                compact(term) in compact(fitted_geometry_statement)
                for term in required_fitted_terms
            ),
            all(
                compact(term) in compact(recovery_geometry_statement)
                for term in required_recovery_terms
            ),
            "const double EnvelopeRadialSupport" in helper,
            "const double RequestedEnvelopeMinimumRadius" in helper,
            "RequestedRootLocation + RadialUp * FittedEnvelopeLift"
            in helper,
            "CurrentEnvelopeCenterRadius - EnvelopeRadialSupport"
            in helper,
            "CurrentEnvelopeCenterRadius + EnvelopeRadialSupport"
            in helper,
            "TargetEnvelopeLocation - PlanetCenter, RadialUp)"
            in helper,
            "!AuthenticatedSurfaceHit" in helper,
            "!AuthenticatedSurfaceChunkKey" in helper,
            "*AuthenticatedSurfaceChunkKey == InvalidChunkKey" in helper,
            "ExactWitnessComponent = AuthenticatedSurfaceHit->GetComponent();"
            in helper,
            "ExactWitnessActor = AuthenticatedSurfaceHit->GetActor();"
            in helper,
            all(
                compact(term) in compact(witness_ready_statement)
                for term in witness_terms
            ),
            "||" not in witness_ready_statement,
            rejected_guard_is_exact(
                helper,
                "if (!bAuthenticatedWitnessReady)",
                "(!bAuthenticatedWitnessReady)",
            ),
            compact("else if (AuthenticatedSurfaceHit || "
                    "AuthenticatedSurfaceChunkKey)")
            in helper_compact,
            "FMath::Abs(RequestedRadius - LegacyDatumRadius) > 0.05"
            in helper,
            "RootStartRadius + 0.01 >= RequestedRadius" in helper,
            "InitialExactResult == ERedPlanetTerrainQueryResult::NoHit"
            in initial_clean_statement,
            compact(initial_query_statement) == expected_initial_query,
            "!InitialExactHit.bBlockingHit" in initial_clean_statement,
            "!InitialExactHit.bStartPenetrating" in initial_clean_statement,
            "InitialExactChunkKey == InvalidChunkKey"
            in initial_clean_statement,
            "InitialExactResult == ERedPlanetTerrainQueryResult::Hit"
            in initial_penetration_statement,
            "InitialExactHit.bBlockingHit" in initial_penetration_statement,
            "InitialExactHit.bStartPenetrating"
            in initial_penetration_statement,
            "InitialExactHit.GetComponent() == ExactWitnessComponent"
            in initial_penetration_statement,
            "InitialExactHit.GetActor() == ExactWitnessActor"
            in initial_penetration_statement,
            "InitialExactChunkKey == ExactWitnessChunkKey"
            in initial_penetration_statement,
            rejected_guard_is_exact(
                helper,
                "if (!bInitialExactCleanNoHit",
                "(!bInitialExactCleanNoHit"
                " && !bInitialExactWitnessPenetration)",
            ),
            compact(not_required_condition)
            == compact(
                "(bInitialExactCleanNoHit"
                " && CurrentEnvelopeMinimumRadius"
                " > ExactWitnessSurfaceRadius + 0.05)"
            ),
            compact(not_required_block)
            == "{returnESurfaceRecoveryResult::NotRequired;}",
            not_required_return_index < ambiguous_shell_index,
            "CurrentEnvelopeMaximumRadius + 0.05"
            in helper,
            ">= ExactWitnessSurfaceRadius" in helper,
            rejected_guard_is_exact(
                helper,
                "if (bInitialExactCleanNoHit\n"
                "\t\t\t&& CurrentEnvelopeMaximumRadius",
                "(bInitialExactCleanNoHit"
                " && CurrentEnvelopeMaximumRadius + 0.05"
                " >= ExactWitnessSurfaceRadius)",
            ),
            helper.count("AddIgnoredComponent(ExactWitnessComponent);") == 2,
            helper.count("World->ComponentSweepMulti(") == 2,
            compact(root_native_route_statement)
            == expected_root_native_route,
            compact(envelope_native_route_statement)
            == expected_envelope_native_route,
            compact(
                lambda_body(helper, "auto IsDisallowedNativeRouteHit")
            )
            == "{returnCandidate.bBlockingHit||"
            "Candidate.bStartPenetrating;}",
            "RootRouteHits.ContainsByPredicate(IsDisallowedNativeRouteHit)"
            in helper,
            "EnvelopeRouteHits.ContainsByPredicate(IsDisallowedNativeRouteHit)"
            in helper,
            "CurrentEnvelopeLocation,\n\t\t\tTargetEnvelopeLocation"
            in forward_statement,
            "TargetEnvelopeLocation,\n\t\t\tCurrentEnvelopeLocation"
            in reverse_statement,
            compact(forward_statement) == expected_forward_query,
            compact(reverse_statement) == expected_reverse_query,
            all(compact(term) in helper_compact for term in route_terms),
            compact(routes_statement) == expected_routes_statement,
            compact(
                "FVector::Dist(Candidate.ImpactPoint,"
                " AuthenticatedSurfaceHit->ImpactPoint)"
            )
            in compact(route_hit_validator),
            compact(route_reject_condition)
            == expected_route_reject_condition,
            compact(route_reject_block) == "{returnfalse;}",
            compact(route_surface_return)
            == expected_route_surface_return,
            compact(
                "IsAuthenticatedExactRouteHit("
                "ExactForwardRouteHit, ExactForwardRouteChunkKey,"
                "bInitialExactWitnessPenetration, false)"
            )
            in compact(routes_statement),
            compact(
                "IsAuthenticatedExactRouteHit("
                "ExactReverseRouteHit, ExactReverseRouteChunkKey,"
                "false, true)"
            )
            in compact(routes_statement),
            "ExactForwardRouteResult"
            " == ERedPlanetTerrainQueryResult::Hit"
            in routes_statement.replace("\n\t\t\t\t", " "),
            "ExactReverseRouteResult"
            " == ERedPlanetTerrainQueryResult::Hit"
            in routes_statement.replace("\n\t\t\t\t", " "),
            routes_statement.count("IsAuthenticatedExactRouteHit(") == 2,
            rejected_guard_is_exact(
                helper,
                "if (!bExactRoutesAuthenticated)",
                "(!bExactRoutesAuthenticated)",
            ),
            route_hit_validator.count("return ") == 3,
            endpoint.count("OverlapBlockingTestByChannel(") == 2,
            compact(endpoint_envelope_statement)
            == expected_endpoint_envelope,
            compact(endpoint_root_statement) == expected_endpoint_root,
            compact(endpoint_exact_statement) == expected_endpoint_exact,
            endpoint.count("return ") == 1,
            compact(endpoint_return) == expected_endpoint_return,
            "EndpointExactResult == ERedPlanetTerrainQueryResult::NoHit"
            in endpoint,
            "ERedPlanetTerrainQueryResult::NoMatchingPlanet" in endpoint,
            helper.count("IsTargetEndpointClear()") == 2,
            endpoint_preflight_index < scoped_move_index,
            rejected_guard_is_exact(
                helper,
                "if (!IsTargetEndpointClear())",
                "(!IsTargetEndpointClear())",
            ),
            "EScopedUpdate::DeferredUpdates" in helper,
            compact(commit_statement) == expected_commit,
            helper.count("Super::MoveUpdatedComponentImpl(") == 1,
            compact(target_pose_statement) == expected_target_pose,
            compact(failure_condition)
            == "(!bTargetPoseReached||!IsTargetEndpointClear())",
            compact(failure_block)
            == "{ScopedMove.RevertMove();"
            "returnESurfaceRecoveryResult::Rejected;}",
            helper.rfind("return ESurfaceRecoveryResult::Committed;")
            > helper.find("ScopedMove.RevertMove();"),
            "TryCommitClearPlacement" not in helper,
            "Velocity" not in helper_clean,
            "bPositionCorrected" not in helper_clean,
            "bSurfaceVelocityAdjusted" not in helper_clean,
            not DIRECT_ROOT_MUTATOR.search(helper_clean),
        )
    )


def clamp_contract_passes(source: str, header: str) -> bool:
    try:
        clamp = function_body(source, CLAMP_SIGNATURE)
        finalize = lambda_body(clamp, "auto FinalizeSurfaceAttempt")
        pose_condition, pose_block = if_condition_and_block(
            finalize, "if (bPoseCommitted)"
        )
        changed_condition, changed_block = if_condition_and_block(
            finalize, "if (bPoseCommitted || bVelocityAdjusted)"
        )
        velocity_condition, velocity_block = if_condition_and_block(
            finalize, "if (bVelocityAdjusted)"
        )
        terrain_result_statement = statement_from(
            clamp,
            "const ERedPlanetTerrainQueryResult TerrainResult",
        )
        terrain_switch = switch_body(clamp, "switch (TerrainResult)")
        not_required_condition, not_required_block = if_condition_and_block(
            terrain_switch,
            "if (RecoveryResult == ESurfaceRecoveryResult::NotRequired)",
        )
        move = function_body(
            source, "void URedShipMovementComponent::MoveWithPlanetCollision"
        )
    except (AssertionError, ValueError):
        return False

    switch_compact = compact(terrain_switch)
    clamp_without_finalize = clamp.replace(finalize, "{}", 1)
    try:
        not_required_index = terrain_switch.index(
            "if (RecoveryResult == ESurfaceRecoveryResult::NotRequired)"
        )
        finalize_after_not_required = terrain_switch.index(
            "FinalizeSurfaceAttempt(", not_required_index
        )
        no_hit_case_index = switch_compact.index(
            "caseERedPlanetTerrainQueryResult::NoHit:"
        )
        no_matching_case_index = switch_compact.index(
            "caseERedPlanetTerrainQueryResult::NoMatchingPlanet:"
        )
        exact_result_index = terrain_switch.index(
            "const ESurfaceRecoveryResult RecoveryResult"
        )
        not_required_return_index = terrain_switch.index(
            "return;", not_required_index
        )
    except ValueError:
        return False
    clamp_clean = strip_cpp_comments_and_literals(clamp)
    expected_case_tail = compact(
        "case ERedPlanetTerrainQueryResult::NoHit:"
        " FinalizeSurfaceAttempt(false); return;"
        " case ERedPlanetTerrainQueryResult::NoMatchingPlanet: break;"
        " default: FinalizeSurfaceAttempt(false); return;"
    )
    exact_call = compact(
        "TryCommitBoundedSurfaceRecovery("
        "TerrainCorrectedLocation,"
        "ESurfaceRecoveryPolicy::ExactTerrainPenetration,"
        "&TerrainHit,"
        "&TerrainChunkKey);"
    )
    legacy_call = compact(
        "TryCommitBoundedSurfaceRecovery("
        "CorrectedLocation,"
        "ESurfaceRecoveryPolicy::LegacyVoid,"
        "nullptr,"
        "nullptr);"
    )
    expected_terrain_result = compact(
        "const ERedPlanetTerrainQueryResult TerrainResult ="
        " RedPlanetTerrainQuery::LineTrace("
        "World, PlanetCenter,"
        " PlanetCenter + RadialUp * OuterTraceRadius,"
        " PlanetCenter, TerrainHit, &TerrainChunkKey);"
    )
    expected_finalize = compact(
        "{"
        "const float InwardSpeed ="
        " FVector::DotProduct(Velocity, -RadialUp);"
        "const bool bVelocityAdjusted = InwardSpeed > 0.0f;"
        "if (bVelocityAdjusted)"
        "{Velocity += RadialUp * InwardSpeed;"
        "bSurfaceVelocityAdjusted = true;}"
        "if (bPoseCommitted){bPositionCorrected = true;}"
        "if (bPoseCommitted || bVelocityAdjusted)"
        "{UpdateComponentVelocity();PawnOwner->ForceNetUpdate();}"
        "}"
    )

    return all(
        (
            clamp.index("PawnOwner->HasAuthority()")
            < clamp.index("const FVector FromCenter"),
            len(re.findall(r"\bTerrainResult\b", clamp_clean)) == 2,
            clamp.index("PawnOwner->HasAuthority()")
            < clamp.index("RedPlanetTerrainQuery::LineTrace("),
            "|| PawnOwner->GetAttachParentActor()" in clamp,
            clamp.count("TryCommitBoundedSurfaceRecovery(") == 2,
            clamp.count("ESurfaceRecoveryPolicy::ExactTerrainPenetration")
            == 1,
            clamp.count("ESurfaceRecoveryPolicy::LegacyVoid") == 1,
            "FIntVector TerrainChunkKey(INDEX_NONE, INDEX_NONE, INDEX_NONE);"
            in clamp,
            compact(terrain_result_statement) == expected_terrain_result,
            "TerrainHit,\n\t\t\t&TerrainChunkKey);" in clamp,
            exact_call in compact(clamp),
            legacy_call in compact(clamp),
            "caseERedPlanetTerrainQueryResult::Hit:" in switch_compact,
            expected_case_tail in switch_compact,
            compact(not_required_condition)
            == "(RecoveryResult==ESurfaceRecoveryResult::NotRequired)",
            compact(not_required_block) == "{return;}",
            not_required_index < finalize_after_not_required,
            "FinalizeSurfaceAttempt"
            not in terrain_switch[
                exact_result_index:not_required_return_index
            ],
            "TryCommitBoundedSurfaceRecovery"
            not in switch_compact[no_hit_case_index:no_matching_case_index],
            compact(pose_condition) == "(bPoseCommitted)",
            compact(pose_block) == "{bPositionCorrected=true;}",
            finalize.count("bPositionCorrected") == 1,
            compact(velocity_condition) == "(bVelocityAdjusted)",
            compact(velocity_block)
            == "{Velocity+=RadialUp*InwardSpeed;"
            "bSurfaceVelocityAdjusted=true;}",
            compact(finalize) == expected_finalize,
            "Velocity" not in clamp_without_finalize,
            "bSurfaceVelocityAdjusted" not in clamp_without_finalize,
            "bPositionCorrected" not in clamp_without_finalize,
            compact(changed_condition)
            == "(bPoseCommitted||bVelocityAdjusted)",
            "bSurfaceVelocityAdjusted = true;" in finalize,
            "UpdateComponentVelocity();" in changed_block,
            "PawnOwner->ForceNetUpdate();" in changed_block,
            clamp.index("World->LineTraceSingleByObjectType")
            < clamp.rindex("ESurfaceRecoveryPolicy::LegacyVoid"),
            "TryCommitClearPlacement" not in clamp,
            not DIRECT_ROOT_MUTATOR.search(clamp_clean),
            "bSurfaceVelocityAdjusted = false;" in move,
            "&& !bSurfaceVelocityAdjusted" in move,
            "bool bSurfaceVelocityAdjusted = false;" in header,
        )
    )


def complete_contract_passes(source: str, header: str) -> bool:
    return helper_contract_passes(
        source, header
    ) and clamp_contract_passes(source, header)


class Def0002ShipSurfaceRecoveryContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = read(MOVEMENT_CPP)
        cls.header = read(MOVEMENT_H)

    def assert_helper_mutation_rejected(self, original: str, replacement: str):
        self.assertIn(original, self.source)
        mutant = mutate_function_once(
            self.source,
            HELPER_SIGNATURE,
            original,
            replacement,
        )
        self.assertFalse(complete_contract_passes(mutant, self.header))

    def assert_clamp_mutation_rejected(self, original: str, replacement: str):
        self.assertIn(original, self.source)
        mutant = mutate_function_once(
            self.source,
            CLAMP_SIGNATURE,
            original,
            replacement,
        )
        self.assertFalse(complete_contract_passes(mutant, self.header))

    def test_surface_recovery_contract_is_complete(self):
        self.assertTrue(complete_contract_passes(self.source, self.header))

    def test_contract_rejects_role_readiness_or_geometry_bypass(self):
        mutations = (
            ("&& PawnOwner->HasAuthority()", "&& PawnOwner->IsLocallyControlled()"),
            ("if (!bRecoveryReady)", "if (false && !bRecoveryReady)"),
            (
                "if (!RootShape.IsSphere() || !EnvelopeShape.IsBox())",
                "if (!RootShape.IsSphere() && !EnvelopeShape.IsBox())",
            ),
            (
                "if (!RootShape.IsSphere() || !EnvelopeShape.IsBox())\n"
                "\t{\n\t\treturn ESurfaceRecoveryResult::Rejected;\n\t}",
                "if (!RootShape.IsSphere() || !EnvelopeShape.IsBox())\n"
                "\t{\n\t}",
            ),
            (
                "if (!bValidFittedGeometry)",
                "if (false && !bValidFittedGeometry)",
            ),
            (
                "if (!bValidRecoveryGeometry)",
                "if (false && !bValidRecoveryGeometry)",
            ),
            (
                "RecoveryDistance <= RedShipSurfaceRecoveryMaxTranslationCm",
                "RecoveryDistance <= TNumericLimits<double>::Max()",
            ),
            (
                "ConstrainedRecoveryDelta.Equals(RecoveryDelta, 0.01f)",
                "true",
            ),
            (
                "RecoveryDelta.GetSafeNormal(), RadialUp) > 0.999999f",
                "RecoveryDelta.GetSafeNormal(), RadialUp) < 0.999999f",
            ),
            (
                "RequestedRootLocation + RadialUp * FittedEnvelopeLift",
                "RequestedRootLocation",
            ),
            (
                "CurrentEnvelopeCenterRadius - EnvelopeRadialSupport",
                "CurrentEnvelopeCenterRadius + EnvelopeRadialSupport",
            ),
            (
                "TargetEnvelopeMinimumRadius + 0.05 >= RequestedRadius",
                "TargetEnvelopeMinimumRadius + 0.05 <= RequestedRadius",
            ),
        )
        for original, replacement in mutations:
            with self.subTest(replacement=replacement):
                self.assert_helper_mutation_rejected(original, replacement)

    def test_contract_rejects_witness_or_initial_state_bypass(self):
        helper_mutations = (
            (
                "ExactWitnessChunkKey.X != INDEX_NONE",
                "ExactWitnessChunkKey.X == INDEX_NONE",
            ),
            (
                "ExactWitnessComponent->GetOwner() == ExactWitnessActor",
                "ExactWitnessComponent->GetOwner() != ExactWitnessActor",
            ),
            (
                "if (!bAuthenticatedWitnessReady)",
                "if (false && !bAuthenticatedWitnessReady)",
            ),
            (
                "AuthenticatedSurfaceHit->Time >= 0.0f",
                "true",
            ),
            (
                "AuthenticatedSurfaceHit->Time <= 1.0f",
                "true",
            ),
            (
                "AuthenticatedSurfaceHit->TraceStart - PlanetCenter",
                "AuthenticatedSurfaceHit->ImpactPoint - PlanetCenter",
            ),
            (
                "RequestedRootLocation.Equals(",
                "true || RequestedRootLocation.Equals(",
            ),
            (
                "InitialExactResult == ERedPlanetTerrainQueryResult::NoHit",
                "InitialExactResult == ERedPlanetTerrainQueryResult::NoMatchingPlanet",
            ),
            (
                "InitialExactChunkKey == InvalidChunkKey",
                "InitialExactChunkKey != InvalidChunkKey",
            ),
            (
                "InitialExactHit.GetComponent() == ExactWitnessComponent",
                "InitialExactHit.GetComponent() != ExactWitnessComponent",
            ),
            (
                "CurrentEnvelopeLocation,\n\t\t\tCurrentEnvelopeLocation,\n"
                "\t\t\tCurrentEnvelopeRotation,\n\t\t\tEnvelopeShape,\n"
                "\t\t\tInitialExactHit",
                "RootStart,\n\t\t\tRootStart,\n"
                "\t\t\tCurrentRootRotation,\n\t\t\tRootShape,\n"
                "\t\t\tInitialExactHit",
            ),
            (
                "if (!bInitialExactCleanNoHit\n"
                "\t\t\t&& !bInitialExactWitnessPenetration)",
                "if (false && (!bInitialExactCleanNoHit\n"
                "\t\t\t&& !bInitialExactWitnessPenetration))",
            ),
            (
                "return ESurfaceRecoveryResult::NotRequired;",
                "return ESurfaceRecoveryResult::Rejected;",
            ),
            (
                "CurrentEnvelopeMinimumRadius\n"
                "\t\t\t\t> ExactWitnessSurfaceRadius + 0.05",
                "CurrentEnvelopeMinimumRadius\n"
                "\t\t\t\t< ExactWitnessSurfaceRadius + 0.05",
            ),
            (
                "CurrentEnvelopeMaximumRadius + 0.05",
                "CurrentEnvelopeMinimumRadius + 0.05",
            ),
        )
        for original, replacement in helper_mutations:
            with self.subTest(replacement=replacement):
                self.assert_helper_mutation_rejected(original, replacement)

        clamp_mutations = (
            ("TerrainHit,\n\t\t\t&TerrainChunkKey);", "TerrainHit);"),
            ("&TerrainHit,\n\t\t\t\t\t\t&TerrainChunkKey", "nullptr,\n\t\t\t\t\t\tnullptr"),
        )
        for original, replacement in clamp_mutations:
            with self.subTest(replacement=replacement):
                self.assert_clamp_mutation_rejected(original, replacement)

    def test_contract_rejects_native_or_reciprocal_route_bypass(self):
        mutations = (
            (
                "EnvelopeNativeParams.AddIgnoredComponent(ExactWitnessComponent);",
                "",
            ),
            (
                "return Candidate.bBlockingHit || Candidate.bStartPenetrating;",
                "return false;",
            ),
            (
                "RootRouteHits.ContainsByPredicate(IsDisallowedNativeRouteHit)",
                "false",
            ),
            (
                "EnvelopeRouteHits.ContainsByPredicate(IsDisallowedNativeRouteHit)",
                "false",
            ),
            (
                "RootRouteHits,\n\t\tUpdatedPrimitive,\n\t\tRootStart,\n"
                "\t\tTargetRootLocation,\n\t\tCurrentRootRotation,\n"
                "\t\tRootNativeParams",
                "RootRouteHits,\n\t\tEnvelope,\n\t\tCurrentEnvelopeLocation,\n"
                "\t\tTargetEnvelopeLocation,\n\t\tCurrentEnvelopeRotation,\n"
                "\t\tEnvelopeNativeParams",
            ),
            (
                "EnvelopeRouteHits,\n\t\tEnvelope,\n"
                "\t\tCurrentEnvelopeLocation,\n\t\tTargetEnvelopeLocation,\n"
                "\t\tCurrentEnvelopeRotation,\n\t\tEnvelopeNativeParams",
                "EnvelopeRouteHits,\n\t\tUpdatedPrimitive,\n"
                "\t\tRootStart,\n\t\tTargetRootLocation,\n"
                "\t\tCurrentRootRotation,\n\t\tRootNativeParams",
            ),
            (
                "TargetEnvelopeLocation,\n\t\t\tCurrentEnvelopeLocation",
                "CurrentEnvelopeLocation,\n\t\t\tTargetEnvelopeLocation",
            ),
            (
                "EnvelopeShape,\n\t\t\tExactForwardRouteHit",
                "RootShape,\n\t\t\tExactForwardRouteHit",
            ),
            (
                "EnvelopeShape,\n\t\t\tExactReverseRouteHit",
                "RootShape,\n\t\t\tExactReverseRouteHit",
            ),
            (
                "Candidate.GetComponent() != ExactWitnessComponent",
                "false",
            ),
            (
                "Candidate.GetActor() != ExactWitnessActor",
                "false",
            ),
            (
                "CandidateChunkKey != ExactWitnessChunkKey",
                "false",
            ),
            (
                "if (!Candidate.bBlockingHit",
                "if (false && !Candidate.bBlockingHit",
            ),
            (
                "Candidate.ImpactPoint,\n\t\t\t\t\tAuthenticatedSurfaceHit->ImpactPoint",
                "AuthenticatedSurfaceHit->ImpactPoint,\n"
                "\t\t\t\t\tAuthenticatedSurfaceHit->ImpactPoint",
            ),
            (
                "ExactReverseRouteChunkKey,\n\t\t\t\tfalse,",
                "ExactReverseRouteChunkKey,\n\t\t\t\ttrue,",
            ),
            (
                "Candidate.bStartPenetrating\n"
                "\t\t\t\t\t!= bExpectedStartPenetrating",
                "!bExpectedStartPenetrating\n"
                "\t\t\t\t\t&& Candidate.bStartPenetrating",
            ),
            (
                "ExactReverseRouteResult\n\t\t\t\t== ERedPlanetTerrainQueryResult::Hit",
                "ExactReverseRouteResult\n\t\t\t\t== ERedPlanetTerrainQueryResult::NoHit",
            ),
            (
                "const bool bExactRoutesAuthenticated =",
                "const bool bExactRoutesAuthenticated = true ||",
            ),
            (
                "if (!bExactRoutesAuthenticated)",
                "if (false && !bExactRoutesAuthenticated)",
            ),
        )
        for original, replacement in mutations:
            with self.subTest(replacement=replacement):
                self.assert_helper_mutation_rejected(original, replacement)

    def test_contract_rejects_endpoint_or_atomicity_bypass(self):
        mutations = (
            (
                "EndpointExactResult == ERedPlanetTerrainQueryResult::NoHit",
                "EndpointExactResult == ERedPlanetTerrainQueryResult::Hit",
            ),
            (
                "&& EndpointExactChunkKey == InvalidChunkKey",
                "|| EndpointExactChunkKey == InvalidChunkKey",
            ),
            (
                "return !bEnvelopeNativeBlocked",
                "return true || !bEnvelopeNativeBlocked",
            ),
            (
                "TargetEnvelopeLocation,\n"
                "\t\t\t\tTargetEnvelopeRotation,\n"
                "\t\t\t\tEnvelope->GetCollisionObjectType()",
                "CurrentEnvelopeLocation,\n"
                "\t\t\t\tCurrentEnvelopeRotation,\n"
                "\t\t\t\tEnvelope->GetCollisionObjectType()",
            ),
            (
                "TargetRootLocation,\n"
                "\t\t\t\tCurrentRootRotation,\n"
                "\t\t\t\tUpdatedPrimitive->GetCollisionObjectType()",
                "RootStart,\n"
                "\t\t\t\tCurrentRootRotation,\n"
                "\t\t\t\tUpdatedPrimitive->GetCollisionObjectType()",
            ),
            (
                "TargetEnvelopeLocation,\n"
                "\t\t\t\tTargetEnvelopeLocation,\n"
                "\t\t\t\tTargetEnvelopeRotation",
                "CurrentEnvelopeLocation,\n"
                "\t\t\t\tCurrentEnvelopeLocation,\n"
                "\t\t\t\tCurrentEnvelopeRotation",
            ),
            (
                "UpdatedPrimitive->GetComponentLocation().Equals(\n"
                "\t\t\t\tTargetRootLocation, 0.05f)",
                "UpdatedPrimitive->GetComponentLocation().Equals(\n"
                "\t\t\t\tRootStart, 0.05f)",
            ),
            (
                "&& UpdatedPrimitive->GetComponentQuat().Equals(\n"
                "\t\t\t\tCurrentRootRotation, 1.0e-6f)",
                "",
            ),
            (
                "if (!IsTargetEndpointClear())",
                "if (false && !IsTargetEndpointClear())",
            ),
            (
                "EScopedUpdate::DeferredUpdates",
                "EScopedUpdate::ImmediateUpdates",
            ),
            (
                "if (!bTargetPoseReached || !IsTargetEndpointClear())",
                "if (!bTargetPoseReached && !IsTargetEndpointClear())",
            ),
            ("ScopedMove.RevertMove();", "if (false) { ScopedMove.RevertMove(); }"),
            (
                "return ESurfaceRecoveryResult::Committed;",
                "return ESurfaceRecoveryResult::Rejected;",
            ),
        )
        for original, replacement in mutations:
            with self.subTest(replacement=replacement):
                self.assert_helper_mutation_rejected(original, replacement)

    def test_contract_rejects_matching_no_hit_or_crater_regressions(self):
        mutations = (
            (
                "case ERedPlanetTerrainQueryResult::NoHit:",
                "case ERedPlanetTerrainQueryResult::NoMatchingPlanet:",
            ),
            (
                "if (RecoveryResult == ESurfaceRecoveryResult::NotRequired)",
                "if (false)",
            ),
            (
                "case ERedPlanetTerrainQueryResult::NoMatchingPlanet:\n"
                "\t\t\tbreak;",
                "case ERedPlanetTerrainQueryResult::NoMatchingPlanet:\n"
                "\t\t\tFinalizeSurfaceAttempt(false);\n"
                "\t\t\treturn;",
            ),
            (
                "if (World->LineTraceSingleByObjectType",
                "TryCommitBoundedSurfaceRecovery(CorrectedLocation,"
                " ESurfaceRecoveryPolicy::LegacyVoid, nullptr, nullptr);\n"
                "\t\t\tif (World->LineTraceSingleByObjectType",
            ),
            (
                "if (bPoseCommitted)\n\t\t{\n\t\t\tbPositionCorrected = true;",
                "bPositionCorrected |= !bPoseCommitted;\n"
                "\t\tif (bPoseCommitted)\n\t\t{\n"
                "\t\t\tbPositionCorrected = true;",
            ),
            (
                "if (bPoseCommitted || bVelocityAdjusted)",
                "if (true)",
            ),
            (
                "Velocity += RadialUp * InwardSpeed;",
                "Velocity -= RadialUp * InwardSpeed;",
            ),
            (
                "auto FinalizeSurfaceAttempt =",
                "Velocity = FVector::ZeroVector;\n"
                "\tauto FinalizeSurfaceAttempt =",
            ),
            (
                "auto FinalizeSurfaceAttempt =",
                "bSurfaceVelocityAdjusted = true;\n"
                "\tauto FinalizeSurfaceAttempt =",
            ),
            (
                "if (RecoveryResult == ESurfaceRecoveryResult::NotRequired)",
                "FinalizeSurfaceAttempt(false);\n"
                "\t\t\t\tif (RecoveryResult"
                " == ESurfaceRecoveryResult::NotRequired)",
            ),
        )
        for original, replacement in mutations:
            with self.subTest(replacement=replacement):
                self.assert_clamp_mutation_rejected(original, replacement)

    def test_contract_rejects_direct_or_low_level_transform_writes(self):
        marker = (
            "\n\treturn ESurfaceRecoveryResult::Committed;\n"
            "}\n\nvoid URedShipMovementComponent::Clamp"
        )
        self.assertIn(marker, self.source)
        injections = (
            "\n\tUpdatedComponent->SetWorldLocation(TargetRootLocation);",
            "\n\tUpdatedComponent->AddWorldRotation(FQuat::Identity);",
            "\n\tUpdatedComponent->AddWorldTransform(FTransform::Identity);",
            "\n\tUpdatedComponent->MoveComponent("
            "RecoveryDelta, CurrentRootRotation, false);",
            "\n\tUpdatedPrimitive->GetBodyInstance()->SetBodyTransform("
            "FTransform::Identity, ETeleportType::TeleportPhysics);",
            "\n\tUpdatedPrimitive->GetBodyInstance()->SetKinematicTarget("
            "FTransform::Identity);",
            "\n\tPhysicsActor->SetGlobalPose(PxTransform());",
            "\n\tUpdatedComponent->RelativeLocation = TargetRootLocation;",
            "\n\tSuper::MoveUpdatedComponentImpl("
            "RecoveryDelta, CurrentRootRotation, false, nullptr,"
            " ETeleportType::TeleportPhysics);",
            "\n\tVelocity = FVector::ZeroVector;",
            "\n\tbPositionCorrected = true;",
            "\n\tUpdatedPrimitive->SetCollisionEnabled("
            "ECollisionEnabled::NoCollision);",
            "\n\tPawnOwner->SetReplicateMovement(false);",
        )
        for injection in injections:
            with self.subTest(injection=injection):
                mutant = self.source.replace(
                    marker, injection + marker, 1
                )
                self.assertFalse(
                    complete_contract_passes(mutant, self.header)
                )


if __name__ == "__main__":
    unittest.main()
