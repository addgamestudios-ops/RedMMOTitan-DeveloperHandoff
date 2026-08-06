import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SHIP_CPP = ROOT / "Source/RedMMO/RedShip.cpp"
MOVEMENT_CPP = ROOT / "Source/RedMMO/RedShipMovementComponent.cpp"
MOVEMENT_H = ROOT / "Source/RedMMO/RedShipMovementComponent.h"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="strict")


def strip_cpp_comments_and_literals(source: str) -> str:
    """Blank comments and string/character contents while preserving structure and offsets."""
    chars = list(source)
    index = 0
    state = "code"
    while index < len(chars):
        current = chars[index]
        following = chars[index + 1] if index + 1 < len(chars) else ""
        if state == "code":
            if current == "/" and following == "/":
                chars[index] = chars[index + 1] = " "
                index += 2
                state = "line_comment"
                continue
            if current == "/" and following == "*":
                chars[index] = chars[index + 1] = " "
                index += 2
                state = "block_comment"
                continue
            if current == '"':
                chars[index] = " "
                index += 1
                state = "string"
                continue
            if current == "'":
                chars[index] = " "
                index += 1
                state = "character"
                continue
        elif state == "line_comment":
            if current == "\n":
                state = "code"
            else:
                chars[index] = " "
        elif state == "block_comment":
            if current == "*" and following == "/":
                chars[index] = chars[index + 1] = " "
                index += 2
                state = "code"
                continue
            if current != "\n":
                chars[index] = " "
        else:
            quote = '"' if state == "string" else "'"
            if current == "\\":
                chars[index] = " "
                if index + 1 < len(chars):
                    if chars[index + 1] != "\n":
                        chars[index + 1] = " "
                    index += 2
                    continue
            if current == quote:
                chars[index] = " "
                state = "code"
            elif current != "\n":
                chars[index] = " "
        index += 1
    return "".join(chars)


def balanced_region(source: str, opening: int, left: str, right: str) -> str:
    depth = 0
    for index in range(opening, len(source)):
        if source[index] == left:
            depth += 1
        elif source[index] == right:
            depth -= 1
            if depth == 0:
                return source[opening : index + 1]
    raise AssertionError(f"unterminated balanced region at {opening}")


def function_body(source: str, signature: str) -> str:
    clean = strip_cpp_comments_and_literals(source)
    start = clean.index(signature)
    opening = clean.index("{", start)
    return clean[start:opening] + balanced_region(clean, opening, "{", "}")


def compact(source: str) -> str:
    return re.sub(r"\s+", "", source)


def statement_from(source: str, marker: str) -> str:
    start = source.index(marker)
    return source[start : source.index(";", start) + 1]


def if_condition_and_block(source: str, marker: str):
    start = source.index(marker)
    condition_open = source.index("(", start)
    condition = balanced_region(source, condition_open, "(", ")")
    block_open = source.index("{", condition_open + len(condition))
    return condition, balanced_region(source, block_open, "{", "}")


def helper_contract_passes(source: str) -> bool:
    try:
        helper = function_body(
            source, "bool URedShipMovementComponent::TryCommitClearPlacement"
        )
        ready_statement = statement_from(helper, "const bool bPlacementReady")
        ready_condition, ready_block = if_condition_and_block(
            helper, "if (!bPlacementReady)"
        )
        box_condition, box_block = if_condition_and_block(
            helper, "if (!RootShape.IsSphere()"
        )
        route_input_condition, route_input_block = if_condition_and_block(
            helper, "if (RootStart.ContainsNaN()"
        )
        angle_condition, angle_block = if_condition_and_block(
            helper, "if (!FMath::IsFinite(PlacementAngleDegrees))"
        )
        segment_condition, segment_block = if_condition_and_block(
            helper, "if (PlacementSegmentCount < 1"
        )
        scope = helper.index("FScopedMovementUpdate ScopedMove")
        scope_statement = statement_from(helper, "FScopedMovementUpdate ScopedMove")
        envelope_init_statement = statement_from(
            helper, "Envelope->InitSweepCollisionParams("
        )
        root_init_statement = statement_from(
            helper, "UpdatedPrimitive->InitSweepCollisionParams("
        )
        proxy_native_statement = statement_from(
            helper, "World->SweepMultiByChannel("
        )
        proxy_exact_statement = statement_from(
            helper, "const ERedPlanetTerrainQueryResult ProxyExactResult"
        )
        commit_statement = statement_from(helper, "const bool bMoveReported")
        commit = helper.index(commit_statement, scope)
        envelope_native_statement = statement_from(
            helper, "const bool bPostEnvelopeNativeBlocked"
        )
        root_native_statement = statement_from(
            helper, "const bool bPostRootNativeBlocked"
        )
        exact_statement = statement_from(
            helper, "const ERedPlanetTerrainQueryResult PostExactResult"
        )
        exact_clear_statement = statement_from(
            helper, "const bool bPostExactClear"
        )
        target_pose_statement = statement_from(
            helper, "const bool bTargetPoseReached"
        )
        decision_condition, failure = if_condition_and_block(
            helper, "if (!bTargetPoseReached"
        )
        decision = helper.index("if (!bTargetPoseReached")
        success = helper.rindex("return true;")
    except (AssertionError, ValueError):
        return False

    required_readiness_terms = (
        "World",
        "PawnOwner",
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
        "!TargetRootLocation.ContainsNaN()",
        "IsFiniteNormalizedQuat(TargetRootRotation)",
    )
    expected_ready = compact(
        "const bool bPlacementReady = "
        + " && ".join(required_readiness_terms)
        + ";"
    )
    expected_commit = compact(
        "const bool bMoveReported = Super::MoveUpdatedComponentImpl("
        "PlacementDelta, TargetRootRotation, false, &PlacementHit, Teleport);"
    )
    expected_envelope_native = compact(
        "const bool bPostEnvelopeNativeBlocked = World->OverlapBlockingTestByChannel("
        "TargetEnvelopeLocation, TargetEnvelopeRotation, Envelope->GetCollisionObjectType(),"
        "EnvelopeShape, EnvelopeNativeParams, EnvelopeResponseParams);"
    )
    expected_root_native = compact(
        "const bool bPostRootNativeBlocked = World->OverlapBlockingTestByChannel("
        "TargetRootLocation, TargetRootRotation, UpdatedPrimitive->GetCollisionObjectType(),"
        "RootShape, RootNativeParams, RootResponseParams);"
    )
    expected_exact = compact(
        "const ERedPlanetTerrainQueryResult PostExactResult = RedPlanetTerrainQuery::Sweep("
        "World, PlanetCenter, TargetEnvelopeLocation, TargetEnvelopeLocation,"
        "TargetEnvelopeRotation, EnvelopeShape, PostExactHit);"
    )
    expected_exact_clear = compact(
        "const bool bPostExactClear = "
        "(PostExactResult == ERedPlanetTerrainQueryResult::NoHit || "
        "(!bRequireMatchingPlanet && "
        "PostExactResult == ERedPlanetTerrainQueryResult::NoMatchingPlanet)) && "
        "!PostExactHit.bBlockingHit && !PostExactHit.bStartPenetrating;"
    )
    expected_target_pose = compact(
        "const bool bTargetPoseReached = (!bPoseChanged || bMoveReported) && "
        "!PlacementHit.bBlockingHit && !PlacementHit.bStartPenetrating && "
        "UpdatedPrimitive->GetComponentLocation().Equals(TargetRootLocation, 0.05f) && "
        "UpdatedPrimitive->GetComponentQuat().Equals(TargetRootRotation, 1.0e-6f);"
    )
    expected_decision = compact(
        "(!bTargetPoseReached || bPostEnvelopeNativeBlocked || "
        "bPostRootNativeBlocked || !bPostExactClear)"
    )
    expected_route_input = compact(
        "(RootStart.ContainsNaN() || "
        "!IsFiniteNormalizedQuat(CurrentRootRotation) || "
        "PlacementDelta.ContainsNaN() || "
        "!FMath::IsFinite(PlacementDistance) || "
        "PlacementDistance > RedShipPlacementRouteMaxTranslationCm || "
        "!ConstrainedPlacementDelta.Equals(PlacementDelta, 0.01f))"
    )
    expected_segment_gate = compact(
        "(PlacementSegmentCount < 1 || "
        "PlacementSegmentCount > RedShipPlacementRouteMaxSegments)"
    )
    expected_scope = compact(
        "FScopedMovementUpdate ScopedMove("
        "UpdatedComponent, EScopedUpdate::DeferredUpdates);"
    )
    expected_envelope_init = compact(
        "Envelope->InitSweepCollisionParams("
        "EnvelopeNativeParams, EnvelopeResponseParams);"
    )
    expected_root_init = compact(
        "UpdatedPrimitive->InitSweepCollisionParams("
        "RootNativeParams, RootResponseParams);"
    )
    expected_proxy_native = compact(
        "World->SweepMultiByChannel("
        "ProxyNativeHits, EnvelopeLocation0, EnvelopeLocation1, "
        "EnvelopeRotationMid, Envelope->GetCollisionObjectType(), ProxyShape, "
        "EnvelopeNativeParams, EnvelopeResponseParams);"
    )
    expected_proxy_exact = compact(
        "const ERedPlanetTerrainQueryResult ProxyExactResult = "
        "RedPlanetTerrainQuery::Sweep("
        "World, PlanetCenter, EnvelopeLocation0, EnvelopeLocation1, "
        "EnvelopeRotationMid, ProxyShape, ProxyExactHit);"
    )
    compact_preflight = compact(helper[:scope])
    required_route_fragments = (
        compact(
            "const FVector PlacementDelta = TargetRootLocation - RootStart;"
        ),
        compact(
            "const FVector ConstrainedPlacementDelta = "
            "ConstrainDirectionToPlane(PlacementDelta);"
        ),
        compact(
            "PlacementDistance > RedShipPlacementRouteMaxTranslationCm"
        ),
        compact(
            "!ConstrainedPlacementDelta.Equals(PlacementDelta, 0.01f)"
        ),
        compact(
            "const float PlacementAngleDegrees = FMath::RadiansToDegrees("
            "CurrentRootRotation.AngularDistance(TargetRootRotation));"
        ),
        compact(
            "const FVector RootToEnvelopeScaledLocal = "
            "CurrentRootRotation.UnrotateVector("
            "Envelope->GetComponentLocation() - RootStart);"
        ),
        compact(
            "const FVector TargetEnvelopeLocation = TargetRootLocation + "
            "TargetRootRotation.RotateVector(RootToEnvelopeScaledLocal);"
        ),
        compact(
            "const FQuat EnvelopeRelativeRotation = "
            "(CurrentRootRotation.Inverse() * "
            "Envelope->GetComponentQuat()).GetNormalized();"
        ),
        compact(
            "const FQuat TargetEnvelopeRotation = "
            "(TargetRootRotation * "
            "EnvelopeRelativeRotation).GetNormalized();"
        ),
        compact(
            "if ((CurrentRootRotation | RouteTargetRootRotation) < 0.0f)"
            "{"
            "RouteTargetRootRotation = FQuat("
            "-RouteTargetRootRotation.X, -RouteTargetRootRotation.Y, "
            "-RouteTargetRootRotation.Z, -RouteTargetRootRotation.W);"
            "}"
        ),
        compact(
            "return Candidate.bBlockingHit || Candidate.bStartPenetrating;"
        ),
        compact(
            "PlacementAngleDegrees / "
            "RedShipAngularEnvelopeMaxSegmentDegrees"
        ),
        compact(
            "PlacementSegmentCount > RedShipPlacementRouteMaxSegments"
        ),
        compact(
            "World->ComponentSweepMulti(RootRouteHits, UpdatedPrimitive, "
            "RootStart, TargetRootLocation, CurrentRootRotation, "
            "RootNativeParams);"
        ),
        compact(
            "if (HasBlockingRouteHit(RootRouteHits)) { return false; }"
        ),
        compact(
            "World->ComponentSweepMulti(EnvelopeRouteHits, Envelope, "
            "Envelope->GetComponentLocation(), TargetEnvelopeLocation, "
            "Envelope->GetComponentQuat(), EnvelopeNativeParams);"
        ),
        compact(
            "const ERedPlanetTerrainQueryResult ExactRouteResult = "
            "RedPlanetTerrainQuery::Sweep("
        ),
        compact(
            "const bool bExactRouteRejected = "
            "ExactRouteResult == ERedPlanetTerrainQueryResult::Hit"
        ),
        compact(
            "for (int32 SegmentIndex = 0; "
            "SegmentIndex < PlacementSegmentCount; ++SegmentIndex)"
        ),
        compact(
            "const float Alpha0 = "
            "static_cast<float>(SegmentIndex) / PlacementSegmentCount;"
        ),
        compact(
            "const float Alpha1 = "
            "static_cast<float>(SegmentIndex + 1) / PlacementSegmentCount;"
        ),
        compact(
            "const float AlphaMid = (Alpha0 + Alpha1) * 0.5f;"
        ),
        compact(
            "const FVector EnvelopeLocation0 = "
            "RootStart + PlacementDelta * Alpha0 + "
            "RootRotation0.RotateVector(RootToEnvelopeScaledLocal);"
        ),
        compact(
            "const FVector EnvelopeLocation1 = "
            "RootStart + PlacementDelta * Alpha1 + "
            "RootRotation1.RotateVector(RootToEnvelopeScaledLocal);"
        ),
        compact(
            "const float RotationPaddingCm = static_cast<float>("
            "2.0 * PivotCornerRadiusCm * "
            "FMath::Sin(SegmentAngleRadians * 0.25)) "
            "+ RedShipAngularEnvelopePaddingCm;"
        ),
        compact(
            "const FCollisionShape ProxyShape = "
            "FCollisionShape::MakeBox("
            "ScaledBoxExtent + FVector(RotationPaddingCm));"
        ),
        compact(
            "World->SweepMultiByChannel(ProxyNativeHits, "
            "EnvelopeLocation0, EnvelopeLocation1, EnvelopeRotationMid"
        ),
        compact(
            "const ERedPlanetTerrainQueryResult ProxyExactResult = "
            "RedPlanetTerrainQuery::Sweep("
        ),
        compact(
            "if (HasBlockingRouteHit(ProxyNativeHits) "
            "|| bProxyExactRejected) { return false; }"
        ),
    )
    return all(
        (
            compact(ready_statement) == expected_ready,
            compact(ready_condition) == "(!bPlacementReady)",
            compact(ready_block) == "{returnfalse;}",
            compact(box_condition)
            == "(!RootShape.IsSphere()||!EnvelopeShape.IsBox())",
            compact(box_block) == "{returnfalse;}",
            compact(route_input_condition) == expected_route_input,
            compact(route_input_block) == "{returnfalse;}",
            compact(angle_condition)
            == "(!FMath::IsFinite(PlacementAngleDegrees))",
            compact(angle_block) == "{returnfalse;}",
            compact(segment_condition) == expected_segment_gate,
            compact(segment_block) == "{returnfalse;}",
            all(
                fragment in compact_preflight
                for fragment in required_route_fragments
            ),
            helper.index("if (RootStart.ContainsNaN()") <
            helper.index("const float PlacementAngleDegrees"),
            helper.index("const int32 PlacementSegmentCount") <
            helper.index("World->ComponentSweepMulti(", helper.index("RootRouteHits")),
            compact(scope_statement) == expected_scope,
            compact(envelope_init_statement) == expected_envelope_init,
            compact(root_init_statement) == expected_root_init,
            compact(proxy_native_statement) == expected_proxy_native,
            compact(proxy_exact_statement) == expected_proxy_exact,
            scope < commit,
            compact(commit_statement) == expected_commit,
            compact(envelope_native_statement) == expected_envelope_native,
            compact(root_native_statement) == expected_root_native,
            compact(exact_statement) == expected_exact,
            compact(exact_clear_statement) == expected_exact_clear,
            compact(target_pose_statement) == expected_target_pose,
            helper.index(envelope_native_statement) > commit,
            helper.index(root_native_statement) > commit,
            helper.index(exact_statement) > commit,
            helper.index(exact_clear_statement) > helper.index(exact_statement),
            helper.index(target_pose_statement) > helper.index(exact_clear_statement),
            compact(decision_condition) == expected_decision,
            compact(failure) == "{ScopedMove.RevertMove();returnfalse;}",
            decision < success,
        )
    )


def direct_self_transform_calls(function: str):
    calls = []
    pattern = re.compile(
        r"(?:(?P<receiver>[A-Za-z_]\w*)\s*->\s*)?"
        r"(?P<call>SetActorLocation|SetActorRotation|SetActorTransform|"
        r"SetActorLocationAndRotation|AddActorWorldOffset|TeleportTo|"
        r"K2_SetActorLocation|K2_SetActorRotation|K2_SetActorTransform)\s*\("
    )
    for match in pattern.finditer(function):
        receiver = match.group("receiver")
        if receiver in (None, "this"):
            calls.append(match.group("call"))
    component_pattern = re.compile(
        r"(?P<receiver>CollisionSphere|RootComponent|RuntimeHullCollision|"
        r"UpdatedComponent|UpdatedPrimitive|GetRootComponent\(\))\s*->\s*"
        r"(?P<call>SetWorldLocation|SetWorldRotation|SetWorldTransform|"
        r"SetWorldLocationAndRotation|SetRelativeLocation|SetRelativeRotation|"
        r"SetRelativeTransform|MoveComponent)\s*\("
    )
    calls.extend(match.group("call") for match in component_pattern.finditer(function))
    return calls


def rejected_exit_contract_passes(exit_ship: str, exit_request: str) -> bool:
    expected_exit_request = compact(
        "void ARedShip::ExitShip()"
        "{"
        "if (HasAuthority()) { ExitShipAuthority(false); }"
        "else { ServerExitShip(); }"
        "}"
    )
    if compact(exit_request) != expected_exit_request:
        return False

    try:
        rejected_if = exit_ship.index("if (!bParkPlacementCommitted)")
        rejected_condition, rejected = if_condition_and_block(
            exit_ship, "if (!bParkPlacementCommitted)"
        )
        rejected_open = exit_ship.index("{", rejected_if)
        rejected_end = rejected_open + len(rejected)
        committed_condition, committed = if_condition_and_block(
            exit_ship, "if (bParkPlacementCommitted)"
        )
        committed_if = exit_ship.index("if (bParkPlacementCommitted)")
    except (AssertionError, ValueError):
        return False

    if committed_if >= rejected_if:
        return False
    if compact(committed_condition) != "(bParkPlacementCommitted)":
        return False
    if compact(committed) != (
        "{SetLandingAssistEnabled(true);SetLandingSettled(true);}"
    ):
        return False
    if compact(rejected_condition) != "(!bParkPlacementCommitted)":
        return False
    if compact(rejected) != (
        "{UE_LOG(LogRedShip,Warning,TEXT(),*GetNameSafe(this));return;}"
    ):
        return False

    protected_mutations = (
        "bFiring = false;",
        "bBoostHeld = false;",
        "ShipMovement->ClearFlightInputState();",
        "ShipMovement->StopMovementImmediately();",
        "LocalMoveAxes = FVector::ZeroVector;",
        "LocalRotationAxes = FVector::ZeroVector;",
        "ServerMoveAxes = FVector::ZeroVector;",
        "ServerRotationAxes = FVector::ZeroVector;",
        "RemoteFlightVelocity = FVector::ZeroVector;",
        "bServerBoostHeld = false;",
        "LastServerFlightInputTime = -100.0;",
        "Pilot->OnExitedShip(",
        "Pilot = nullptr;",
        "C->Possess(Leaving);",
    )
    for mutation in protected_mutations:
        try:
            if exit_ship.index(mutation) <= rejected_end:
                return False
        except ValueError:
            return False

    pre_rejection = exit_ship[:rejected_if]
    if pre_rejection.count("SetLandingAssistEnabled(") != 1:
        return False
    if pre_rejection.count("SetLandingSettled(") != 1:
        return False
    if re.search(r"\b(?:Pilot|C)\s*->", pre_rejection):
        return False
    if re.search(r"\bGetController\s*\(\s*\)\s*->", pre_rejection):
        return False
    if re.search(
        r"\b(?:bFiring|bBoostHeld|LocalMoveAxes|LocalRotationAxes|"
        r"ServerMoveAxes|ServerRotationAxes|RemoteFlightVelocity|"
        r"bServerBoostHeld|LastServerFlightInputTime)\s*"
        r"(?:\+\+|--|[+\-*/%&|^]?=)",
        pre_rejection,
    ):
        return False
    for direct_mutator in (
        "ForceNetUpdate(",
        "SetActorHiddenInGame(",
        "SetActorEnableCollision(",
    ):
        if direct_mutator in pre_rejection:
            return False
    movement_calls = re.findall(
        r"\bShipMovement\s*->\s*([A-Za-z_]\w*)\s*\(", pre_rejection
    )
    return movement_calls == ["TryCommitClearPlacement"]


def inward_rejection_contract_passes(assist: str) -> bool:
    if assist.count("ShipMovement->TryCommitClearPlacement(") != 4:
        return False
    try:
        lambda_marker = assist.index("const auto StopInwardLandingVelocity")
        lambda_open = assist.index("{", lambda_marker)
        lambda_block = balanced_region(assist, lambda_open, "{", "}")
    except (AssertionError, ValueError):
        return False

    expected_lambda = compact(
        "{"
        "const FVector CurrentVelocity = GetLandingFlightVelocity();"
        "const float InwardSpeed = FVector::DotProduct(CurrentVelocity, SurfaceNormal);"
        "if (InwardSpeed < 0.f)"
        "{"
        "SetLandingFlightVelocity(CurrentVelocity - SurfaceNormal * InwardSpeed);"
        "}"
        "}"
    )
    if compact(lambda_block) != expected_lambda:
        return False

    placement_conditions = []
    placement_failures = []
    for match in re.finditer(r"\bif\s*\(", assist):
        try:
            condition_open = assist.index("(", match.start())
            condition = balanced_region(assist, condition_open, "(", ")")
        except (AssertionError, ValueError):
            return False
        if "ShipMovement->TryCommitClearPlacement" not in condition:
            continue

        try:
            then_open = assist.index("{", condition_open + len(condition))
            then_block = balanced_region(assist, then_open, "{", "}")
        except (AssertionError, ValueError):
            return False
        compact_condition = compact(condition)
        placement_conditions.append(compact_condition)
        if compact_condition.startswith("(!ShipMovement->TryCommitClearPlacement("):
            placement_failures.append(compact(then_block))
            continue
        if not compact_condition.startswith("(ShipMovement->TryCommitClearPlacement("):
            return False

        after_then = then_open + len(then_block)
        while after_then < len(assist) and assist[after_then].isspace():
            after_then += 1
        if not assist.startswith("else", after_then):
            return False
        after_else = after_then + len("else")
        while after_else < len(assist) and assist[after_else].isspace():
            after_else += 1
        if after_else >= len(assist) or assist[after_else] != "{":
            return False
        try:
            else_open = after_else
            else_block = balanced_region(assist, else_open, "{", "}")
        except (AssertionError, ValueError):
            return False
        placement_failures.append(compact(else_block))

    return placement_conditions == [
        "(!ShipMovement->TryCommitClearPlacement(GetActorLocation(),NewRotation,"
        "bMatchingPlanetTerrain,ETeleportType::TeleportPhysics))",
        "(ShipMovement->TryCommitClearPlacement(TouchdownLocation,DesiredRotation,"
        "bMatchingPlanetTerrain,ETeleportType::TeleportPhysics))",
        "(!ShipMovement->TryCommitClearPlacement(AssistedLocation,GetActorQuat(),"
        "bMatchingPlanetTerrain,ETeleportType::TeleportPhysics))",
        "(ShipMovement->TryCommitClearPlacement(TouchdownLocation,DesiredRotation,"
        "bMatchingPlanetTerrain,ETeleportType::TeleportPhysics))",
    ] and placement_failures == [
        "{StopInwardLandingVelocity();SetLandingSettled(false);return;}",
        "{StopInwardLandingVelocity();SetLandingSettled(false);}",
        "{StopInwardLandingVelocity();return;}",
        "{StopInwardLandingVelocity();SetLandingSettled(false);}",
    ]


class Def0002ShipPlacementTransactionContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ship_source = read(SHIP_CPP)
        cls.movement_source = read(MOVEMENT_CPP)
        cls.movement_header = read(MOVEMENT_H)
        cls.assist = function_body(
            cls.ship_source, "void ARedShip::ApplyLandingAssist"
        )
        cls.exit_ship = function_body(
            cls.ship_source, "void ARedShip::ExitShipAuthority"
        )
        cls.exit_request = function_body(
            cls.ship_source, "void ARedShip::ExitShip()"
        )
        cls.helper = function_body(
            cls.movement_source,
            "bool URedShipMovementComponent::TryCommitClearPlacement",
        )

    def test_landing_and_parking_delegate_without_direct_self_teleports(self):
        self.assertGreaterEqual(self.assist.count("TryCommitClearPlacement("), 4)
        self.assertGreaterEqual(self.exit_ship.count("TryCommitClearPlacement("), 1)
        self.assertEqual([], direct_self_transform_calls(self.assist))
        self.assertEqual([], direct_self_transform_calls(self.exit_ship))

    def test_helper_preflights_bounded_full_route_then_runs_all_postchecks(self):
        self.assertTrue(helper_contract_passes(self.movement_source))
        for token in (
            "RootRouteHits",
            "EnvelopeRouteHits",
            "PlacementSegmentCount",
            "ProxyNativeHits",
            "ProxyExactResult",
            "TargetEnvelopeLocation",
            "TargetEnvelopeRotation",
            "bPostEnvelopeNativeBlocked",
            "bPostRootNativeBlocked",
            "bPostExactClear",
            "bTargetPoseReached",
        ):
            self.assertIn(token, self.helper)

    def test_route_limits_cover_shortest_rotation_but_remain_local(self):
        clean = compact(strip_cpp_comments_and_literals(self.movement_source))
        self.assertIn(
            compact(
                "constexpr float RedShipPlacementRouteMaxTranslationCm = "
                "10000.0f;"
            ),
            clean,
        )
        self.assertIn(
            compact(
                "constexpr int32 RedShipPlacementRouteMaxSegments = 90;"
            ),
            clean,
        )
        self.assertIn(
            compact(
                "PlacementAngleDegrees / "
                "RedShipAngularEnvelopeMaxSegmentDegrees"
            ),
            compact(self.helper),
        )

    def test_exact_planet_policy_is_propagated_from_surface_query(self):
        query = function_body(
            self.ship_source, "bool ARedShip::QueryLandingSurface"
        )
        self.assertIn("*bOutMatchingPlanetTerrain = false;", query)
        self.assertIn("*bOutMatchingPlanetTerrain = true;", query)
        self.assertIn("bMatchingPlanetTerrain", self.assist)
        self.assertIn("bRequireMatchingPlanet", self.exit_ship)
        self.assertIn("bRequireMatchingPlanet", self.movement_header)

    def test_settled_lock_is_control_dependent_on_success(self):
        self.assertEqual(1, self.assist.count("SetLandingSettled(true);"))
        self.assertEqual(1, self.exit_ship.count("SetLandingSettled(true);"))
        touchdown_call = self.assist.rindex(
            "if (ShipMovement->TryCommitClearPlacement("
        )
        touchdown_open = self.assist.index("{", touchdown_call)
        touchdown_success = balanced_region(
            self.assist, touchdown_open, "{", "}"
        )
        self.assertIn("if (HasAuthority())", touchdown_success)
        self.assertIn("SetLandingSettled(true);", touchdown_success)

        parked_if = self.exit_ship.index("if (bParkPlacementCommitted)")
        parked_open = self.exit_ship.index("{", parked_if)
        parked_success = balanced_region(self.exit_ship, parked_open, "{", "}")
        self.assertIn("SetLandingAssistEnabled(true);", parked_success)
        self.assertIn("SetLandingSettled(true);", parked_success)

    def test_invalid_pose_or_missing_fitted_envelope_fails_before_mutation(self):
        scope = self.helper.index("FScopedMovementUpdate ScopedMove")
        prefix = self.helper[:scope]
        for token in (
            "UpdatedPrimitive",
            "Envelope",
            "Envelope->GetAttachParent() == UpdatedPrimitive",
            "PlanetRadius > 0.0f",
            "TargetRootLocation.ContainsNaN()",
            "IsFiniteNormalizedQuat(TargetRootRotation)",
            "RedShipPlacementRouteMaxTranslationCm",
            "ConstrainedPlacementDelta.Equals(PlacementDelta, 0.01f)",
            "RedShipPlacementRouteMaxSegments",
            "return false;",
        ):
            self.assertIn(token, prefix)

    def test_rejected_normal_exit_preserves_possession_and_flight_state(self):
        self.assertIn(
            "bool bParkPlacementCommitted = bOrbitalExit || bEmergencyEject;",
            self.exit_ship,
        )
        self.assertTrue(
            rejected_exit_contract_passes(self.exit_ship, self.exit_request)
        )

    def test_rejected_descent_or_touchdown_removes_inward_velocity(self):
        self.assertTrue(inward_rejection_contract_passes(self.assist))

    def test_mutation_fixtures_reject_cosmetic_or_incomplete_safety(self):
        self.assertTrue(helper_contract_passes(self.movement_source))

        missing_exact = self.helper.replace(
            "RedPlanetTerrainQuery::Sweep(", "MissingExactTerrainProbe(", 1
        )
        self.assertFalse(helper_contract_passes(missing_exact))

        missing_native = self.helper.replace(
            "OverlapBlockingTestByChannel(", "MissingNativeProbe("
        )
        self.assertFalse(helper_contract_passes(missing_native))

        missing_revert = self.helper.replace(
            "ScopedMove.RevertMove();", "/* rollback removed */", 1
        )
        self.assertFalse(helper_contract_passes(missing_revert))

        comment_only = missing_exact.replace(
            "bool URedShipMovementComponent::TryCommitClearPlacement",
            "// RedPlanetTerrainQuery::Sweep( fake proof in a comment )\n"
            "bool URedShipMovementComponent::TryCommitClearPlacement",
            1,
        )
        self.assertFalse(helper_contract_passes(comment_only))

        ignored_results = self.helper.replace(
            "if (!bTargetPoseReached\n"
            "\t\t|| bPostEnvelopeNativeBlocked\n"
            "\t\t|| bPostRootNativeBlocked\n"
            "\t\t|| !bPostExactClear)",
            "if (!bTargetPoseReached)",
            1,
        )
        self.assertFalse(helper_contract_passes(ignored_results))

        wrong_native_pose = self.helper.replace(
            "TargetEnvelopeLocation,\n\t\t\tTargetEnvelopeRotation,",
            "RootStart,\n\t\t\tCurrentRootRotation,",
            1,
        )
        self.assertFalse(helper_contract_passes(wrong_native_pose))

        wrong_exact_pose = self.helper.replace(
            "TargetEnvelopeLocation,\n\t\t\tTargetEnvelopeLocation,",
            "RootStart,\n\t\t\tRootStart,",
            1,
        ).replace("\t\t\tEnvelopeShape,\n\t\t\tPostExactHit);",
                  "\t\t\tRootShape,\n\t\t\tPostExactHit);", 1)
        self.assertFalse(helper_contract_passes(wrong_exact_pose))

        disabled_readiness = self.helper.replace(
            "if (!bPlacementReady)", "if (false && !bPlacementReady)", 1
        )
        self.assertFalse(helper_contract_passes(disabled_readiness))

        forced_readiness = self.helper.replace(
            "const bool bPlacementReady = World",
            "const bool bPlacementReady = true || World",
            1,
        )
        self.assertFalse(helper_contract_passes(forced_readiness))

        weakened_readiness = self.helper.replace(
            "World\n\t\t&& PawnOwner", "World\n\t\t|| PawnOwner", 1
        )
        self.assertFalse(helper_contract_passes(weakened_readiness))

        disabled_shape_gate = self.helper.replace(
            "if (!RootShape.IsSphere() || !EnvelopeShape.IsBox())",
            "if (false && (!RootShape.IsSphere() || !EnvelopeShape.IsBox()))",
            1,
        )
        self.assertFalse(helper_contract_passes(disabled_shape_gate))

        missing_radius_gate = self.helper.replace(
            "\n\t\t&& PlanetRadius > 0.0f", "",
            1,
        )
        self.assertFalse(helper_contract_passes(missing_radius_gate))

        unbounded_translation = self.helper.replace(
            "PlacementDistance > RedShipPlacementRouteMaxTranslationCm",
            "false && PlacementDistance > RedShipPlacementRouteMaxTranslationCm",
            1,
        )
        self.assertFalse(helper_contract_passes(unbounded_translation))

        unconstrained_route = self.helper.replace(
            "!ConstrainedPlacementDelta.Equals(PlacementDelta, 0.01f)",
            "false && !ConstrainedPlacementDelta.Equals(PlacementDelta, 0.01f)",
            1,
        )
        self.assertFalse(helper_contract_passes(unconstrained_route))

        unbounded_segments = self.helper.replace(
            "PlacementSegmentCount > RedShipPlacementRouteMaxSegments",
            "false && PlacementSegmentCount > RedShipPlacementRouteMaxSegments",
            1,
        )
        self.assertFalse(helper_contract_passes(unbounded_segments))

        unscaled_envelope_offset = self.helper.replace(
            "CurrentRootRotation.UnrotateVector(\n"
            "\t\t\tEnvelope->GetComponentLocation() - RootStart)",
            "CurrentRootTransform.InverseTransformPosition(\n"
            "\t\t\tEnvelope->GetComponentLocation())",
            1,
        )
        self.assertFalse(helper_contract_passes(unscaled_envelope_offset))

        unreachable_revert = self.helper.replace(
            "ScopedMove.RevertMove();\n\t\treturn false;",
            "if (false) { ScopedMove.RevertMove(); }\n\t\treturn false;",
            1,
        )
        self.assertFalse(helper_contract_passes(unreachable_revert))

        exact_clear_statement = statement_from(
            self.helper, "const bool bPostExactClear"
        )
        forced_exact_clear = self.helper.replace(
            exact_clear_statement, "const bool bPostExactClear = true;", 1
        )
        self.assertFalse(helper_contract_passes(forced_exact_clear))

        appended_exact_bypass = self.helper.replace(
            exact_clear_statement,
            exact_clear_statement[:-1] + " || true;",
            1,
        )
        self.assertFalse(helper_contract_passes(appended_exact_bypass))

        target_pose_statement = statement_from(
            self.helper, "const bool bTargetPoseReached"
        )
        forced_target_pose = self.helper.replace(
            target_pose_statement, "const bool bTargetPoseReached = true;", 1
        )
        self.assertFalse(helper_contract_passes(forced_target_pose))

        missing_root_route = self.helper.replace(
            "World->ComponentSweepMulti(\n"
            "\t\tRootRouteHits,",
            "World->MissingRootRouteSweep(\n"
            "\t\tRootRouteHits,",
            1,
        )
        self.assertFalse(helper_contract_passes(missing_root_route))

        missing_fixed_route = self.helper.replace(
            "World->ComponentSweepMulti(\n"
            "\t\t\tEnvelopeRouteHits,",
            "World->MissingEnvelopeRouteSweep(\n"
            "\t\t\tEnvelopeRouteHits,",
            1,
        )
        self.assertFalse(helper_contract_passes(missing_fixed_route))

        missing_rotated_native_route = self.helper.replace(
            "World->SweepMultiByChannel(\n"
            "\t\t\t\tProxyNativeHits,",
            "World->MissingProxyRouteSweep(\n"
            "\t\t\t\tProxyNativeHits,",
            1,
        )
        self.assertFalse(helper_contract_passes(missing_rotated_native_route))

        swept_commit_after_preflight = self.helper.replace(
            "TargetRootRotation,\n\t\tfalse,\n\t\t&PlacementHit,",
            "TargetRootRotation,\n\t\ttrue,\n\t\t&PlacementHit,",
            1,
        )
        self.assertFalse(helper_contract_passes(swept_commit_after_preflight))

        route_mutations = (
            (
                "disabled shortest-path hemisphere normalization",
                "if ((CurrentRootRotation | RouteTargetRootRotation) < 0.0f)",
                "if (false && "
                "(CurrentRootRotation | RouteTargetRootRotation) < 0.0f)",
            ),
            (
                "blocking and initial-overlap route hits both remain vetoes",
                "return Candidate.bBlockingHit || Candidate.bStartPenetrating;",
                "return Candidate.bBlockingHit && Candidate.bStartPenetrating;",
            ),
            (
                "segment endpoint advances",
                "static_cast<float>(SegmentIndex + 1) / PlacementSegmentCount;",
                "static_cast<float>(SegmentIndex) / PlacementSegmentCount;",
            ),
            (
                "rotated fitted-envelope offset remains in every segment",
                "+ RootRotation0.RotateVector(RootToEnvelopeScaledLocal);",
                "+ FVector::ZeroVector;",
            ),
            (
                "proxy includes angular padding",
                "ScaledBoxExtent + FVector(RotationPaddingCm));",
                "ScaledBoxExtent);",
            ),
            (
                "scoped movement remains deferred",
                "EScopedUpdate::DeferredUpdates",
                "EScopedUpdate::ImmediateUpdates",
            ),
        )
        for label, original, replacement in route_mutations:
            with self.subTest(route_mutation=label):
                self.assertEqual(1, self.helper.count(original))
                mutant = self.helper.replace(original, replacement, 1)
                self.assertNotEqual(self.helper, mutant)
                self.assertFalse(helper_contract_passes(mutant))

        relative_rotation_statement = statement_from(
            self.helper, "const FQuat EnvelopeRelativeRotation"
        )
        relative_rotation_mutant = self.helper.replace(
            relative_rotation_statement,
            "const FQuat EnvelopeRelativeRotation = "
            "Envelope->GetComponentQuat().GetNormalized();",
            1,
        )
        self.assertNotEqual(self.helper, relative_rotation_mutant)
        self.assertFalse(helper_contract_passes(relative_rotation_mutant))

        target_rotation_statement = statement_from(
            self.helper, "const FQuat TargetEnvelopeRotation"
        )
        target_rotation_mutant = self.helper.replace(
            target_rotation_statement,
            "const FQuat TargetEnvelopeRotation = "
            "TargetRootRotation.GetNormalized();",
            1,
        )
        self.assertNotEqual(self.helper, target_rotation_mutant)
        self.assertFalse(helper_contract_passes(target_rotation_mutant))

        envelope_init_statement = statement_from(
            self.helper, "Envelope->InitSweepCollisionParams("
        )
        wrong_envelope_init = envelope_init_statement.replace(
            "EnvelopeResponseParams", "RootResponseParams", 1
        )
        envelope_init_mutant = self.helper.replace(
            envelope_init_statement, wrong_envelope_init, 1
        )
        self.assertNotEqual(self.helper, envelope_init_mutant)
        self.assertFalse(helper_contract_passes(envelope_init_mutant))

        root_init_statement = statement_from(
            self.helper, "UpdatedPrimitive->InitSweepCollisionParams("
        )
        wrong_root_init = root_init_statement.replace(
            "RootResponseParams", "EnvelopeResponseParams", 1
        )
        root_init_mutant = self.helper.replace(
            root_init_statement, wrong_root_init, 1
        )
        self.assertNotEqual(self.helper, root_init_mutant)
        self.assertFalse(helper_contract_passes(root_init_mutant))

        proxy_native_statement = statement_from(
            self.helper, "World->SweepMultiByChannel("
        )
        self.assertEqual(1, proxy_native_statement.count("EnvelopeResponseParams"))
        wrong_proxy_response = proxy_native_statement.replace(
            "EnvelopeResponseParams", "RootResponseParams", 1
        )
        proxy_response_mutant = self.helper.replace(
            proxy_native_statement, wrong_proxy_response, 1
        )
        self.assertNotEqual(self.helper, proxy_response_mutant)
        self.assertFalse(helper_contract_passes(proxy_response_mutant))

        proxy_exact_statement = statement_from(
            self.helper, "const ERedPlanetTerrainQueryResult ProxyExactResult"
        )
        self.assertEqual(1, proxy_exact_statement.count("ProxyShape"))
        wrong_proxy_exact_shape = proxy_exact_statement.replace(
            "ProxyShape", "RootShape", 1
        )
        proxy_exact_shape_mutant = self.helper.replace(
            proxy_exact_statement, wrong_proxy_exact_shape, 1
        )
        self.assertNotEqual(self.helper, proxy_exact_shape_mutant)
        self.assertFalse(helper_contract_passes(proxy_exact_shape_mutant))

        raw_teleport = self.assist.replace(
            "SetLandingFlightVelocity(AssistedVelocity);",
            "SetActorLocation(AssistedLocation);",
            1,
        )
        self.assertEqual(["SetActorLocation"], direct_self_transform_calls(raw_teleport))

        component_teleport = self.assist.replace(
            "SetLandingFlightVelocity(AssistedVelocity);",
            "CollisionSphere->SetWorldLocation(AssistedLocation);",
            1,
        )
        self.assertEqual(
            ["SetWorldLocation"], direct_self_transform_calls(component_teleport)
        )

        teleport_to = self.assist.replace(
            "SetLandingFlightVelocity(AssistedVelocity);",
            "TeleportTo(AssistedLocation, GetActorRotation());",
            1,
        )
        self.assertEqual(["TeleportTo"], direct_self_transform_calls(teleport_to))

        rejected_condition, rejected_block = if_condition_and_block(
            self.exit_ship, "if (!bParkPlacementCommitted)"
        )
        conditional_exit_return = self.exit_ship.replace(
            rejected_block,
            rejected_block.replace("return;", "if (true) { return; }", 1),
            1,
        )
        self.assertFalse(
            rejected_exit_contract_passes(
                conditional_exit_return, self.exit_request
            )
        )

        early_exit_mutation = self.exit_ship.replace(
            "if (!bParkPlacementCommitted)",
            "ServerMoveAxes = FVector::ZeroVector;\n\tif (!bParkPlacementCommitted)",
            1,
        )
        self.assertFalse(
            rejected_exit_contract_passes(early_exit_mutation, self.exit_request)
        )

        alternate_field_write = self.exit_ship.replace(
            "if (!bParkPlacementCommitted)",
            "bFiring = true;\n\tif (!bParkPlacementCommitted)",
            1,
        )
        self.assertFalse(
            rejected_exit_contract_passes(alternate_field_write, self.exit_request)
        )

        early_unpossess = self.exit_ship.replace(
            "if (!bParkPlacementCommitted)",
            "if (C) { C->UnPossess(); }\n\tif (!bParkPlacementCommitted)",
            1,
        )
        self.assertFalse(
            rejected_exit_contract_passes(early_unpossess, self.exit_request)
        )

        expression_unpossess = self.exit_ship.replace(
            "if (!bParkPlacementCommitted)",
            "if (GetController()) { GetController()->UnPossess(); }\n"
            "\tif (!bParkPlacementCommitted)",
            1,
        )
        self.assertFalse(
            rejected_exit_contract_passes(expression_unpossess, self.exit_request)
        )

        early_pilot_mutation = self.exit_ship.replace(
            "if (!bParkPlacementCommitted)",
            "Pilot->SetActorHiddenInGame(true);\n\tif (!bParkPlacementCommitted)",
            1,
        )
        self.assertFalse(
            rejected_exit_contract_passes(early_pilot_mutation, self.exit_request)
        )

        for direct_mutation in (
            "SetLandingSettled(false);",
            "SetLandingAssistEnabled(false);",
            "ForceNetUpdate();",
            "SetActorHiddenInGame(true);",
        ):
            mutated_exit = self.exit_ship.replace(
                "if (!bParkPlacementCommitted)",
                direct_mutation + "\n\tif (!bParkPlacementCommitted)",
                1,
            )
            self.assertFalse(
                rejected_exit_contract_passes(mutated_exit, self.exit_request)
            )

        mutating_exit_wrapper = self.exit_request.replace(
            "{", "{\n\tbFiring = false;", 1
        )
        self.assertFalse(
            rejected_exit_contract_passes(self.exit_ship, mutating_exit_wrapper)
        )

        unpossessing_exit_wrapper = self.exit_request.replace(
            "{", "{\n\tif (AController* C = GetController()) { C->UnPossess(); }", 1
        )
        self.assertFalse(
            rejected_exit_contract_passes(
                self.exit_ship, unpossessing_exit_wrapper
            )
        )

        lambda_marker = self.assist.index("const auto StopInwardLandingVelocity")
        lambda_open = self.assist.index("{", lambda_marker)
        lambda_block = balanced_region(self.assist, lambda_open, "{", "}")
        no_op_inward_stop = self.assist.replace(lambda_block, "{}", 1)
        self.assertFalse(inward_rejection_contract_passes(no_op_inward_stop))

        conditional_inward_stop = self.assist.replace(
            "StopInwardLandingVelocity();\n\t\tSetLandingSettled(false);\n\t\treturn;",
            "if (false) { StopInwardLandingVelocity(); }\n"
            "\t\tSetLandingSettled(false);\n\t\treturn;",
            1,
        )
        self.assertFalse(inward_rejection_contract_passes(conditional_inward_stop))

        settled_call = self.assist.index(
            "if (ShipMovement->TryCommitClearPlacement("
        )
        settled_condition_open = self.assist.index("(", settled_call)
        settled_condition = balanced_region(
            self.assist, settled_condition_open, "(", ")"
        )
        settled_success_open = self.assist.index(
            "{", settled_condition_open + len(settled_condition)
        )
        settled_success = balanced_region(
            self.assist, settled_success_open, "{", "}"
        )
        settled_else = self.assist.index(
            "else", settled_success_open + len(settled_success)
        )
        settled_failure_open = self.assist.index("{", settled_else)
        settled_failure = balanced_region(
            self.assist, settled_failure_open, "{", "}"
        )
        conditional_positive_failure = self.assist.replace(
            settled_failure,
            settled_failure.replace(
                "StopInwardLandingVelocity();",
                "if (false) { StopInwardLandingVelocity(); }",
                1,
            ),
            1,
        )
        cosmetic_insert = conditional_positive_failure.rfind("\n}")
        conditional_positive_failure = (
            conditional_positive_failure[:cosmetic_insert]
            + "\n\tif (true) {} else { StopInwardLandingVelocity(); "
            "SetLandingSettled(false); }"
            + conditional_positive_failure[cosmetic_insert:]
        )
        self.assertFalse(
            inward_rejection_contract_passes(conditional_positive_failure)
        )

        fifth_insert = self.assist.rfind("\n}")
        fifth_uncovered_placement = (
            self.assist[:fifth_insert]
            + "\n\tif (ShipMovement->TryCommitClearPlacement("
            "GetActorLocation(), GetActorQuat(), false, ETeleportType::None)) {}"
            + self.assist[fifth_insert:]
        )
        self.assertFalse(
            inward_rejection_contract_passes(fifth_uncovered_placement)
        )

        standalone_fifth_placement = (
            self.assist[:fifth_insert]
            + "\n\tShipMovement->TryCommitClearPlacement("
            "GetActorLocation(), GetActorQuat(), false, ETeleportType::None);"
            + self.assist[fifth_insert:]
        )
        self.assertFalse(
            inward_rejection_contract_passes(standalone_fifth_placement)
        )

        else_if_failure = self.assist.replace(
            "else\n\t\t{\n\t\t\tStopInwardLandingVelocity();\n"
            "\t\t\tSetLandingSettled(false);",
            "else if (false)\n\t\t{\n\t\t\tStopInwardLandingVelocity();\n"
            "\t\t\tSetLandingSettled(false);",
            1,
        )
        self.assertFalse(inward_rejection_contract_passes(else_if_failure))

        placement_conditions = []
        for match in re.finditer(r"\bif\s*\(", self.assist):
            condition_open = self.assist.index("(", match.start())
            condition = balanced_region(
                self.assist, condition_open, "(", ")"
            )
            if "ShipMovement->TryCommitClearPlacement" in condition:
                placement_conditions.append(condition)
        disabled_negative_condition = self.assist.replace(
            placement_conditions[0], placement_conditions[0][:-1] + " && false)", 1
        )
        self.assertFalse(
            inward_rejection_contract_passes(disabled_negative_condition)
        )
        forced_positive_condition = self.assist.replace(
            placement_conditions[1], placement_conditions[1][:-1] + " || true)", 1
        )
        self.assertFalse(
            inward_rejection_contract_passes(forced_positive_condition)
        )


if __name__ == "__main__":
    unittest.main()
