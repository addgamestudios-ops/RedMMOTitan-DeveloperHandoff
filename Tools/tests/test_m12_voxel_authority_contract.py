import json
import re
import unittest
from dataclasses import dataclass, field
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CONTRACT_HEADER = (
    ROOT / "Source/RedMMO/Mining/RedVoxelMiningContracts.h"
)
CONTRACT_CPP = (
    ROOT / "Source/RedMMO/Mining/RedVoxelMiningContracts.cpp"
)
BACKEND_HEADER = (
    ROOT / "Source/RedMMO/Mining/RedVoxelAsteroidBackend.h"
)
BUILD_RULES = ROOT / "Source/RedMMO/RedMMO.Build.cs"
UPROJECT = ROOT / "Titan.uproject"
QUEUE = ROOT / "Build/Automation/redmmotitan_module_queue.json"
SYSTEM_RECORD = (
    ROOT / "ProjectKnowledge/systems/on-foot-voxel-asteroid-mining.yaml"
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


def strip_cpp_comments_and_literals(source: str) -> str:
    """Return code tokens while preventing comments/strings from faking proof."""
    output = []
    index = 0
    state = "code"
    while index < len(source):
        current = source[index]
        following = source[index + 1] if index + 1 < len(source) else ""
        if state == "code":
            if current == "/" and following == "/":
                output.extend("  ")
                index += 2
                state = "line_comment"
                continue
            if current == "/" and following == "*":
                output.extend("  ")
                index += 2
                state = "block_comment"
                continue
            if current == '"':
                output.append(" ")
                index += 1
                state = "string"
                continue
            if current == "'":
                output.append(" ")
                index += 1
                state = "character"
                continue
            output.append(current)
            index += 1
            continue
        if state == "line_comment":
            if current in "\r\n":
                output.append(current)
                state = "code"
            else:
                output.append(" ")
            index += 1
            continue
        if state == "block_comment":
            if current == "*" and following == "/":
                output.extend("  ")
                index += 2
                state = "code"
            else:
                output.append(current if current in "\r\n" else " ")
                index += 1
            continue
        if state in ("string", "character"):
            if current == "\\" and following:
                output.extend("  ")
                index += 2
                continue
            terminal = '"' if state == "string" else "'"
            output.append(" ")
            index += 1
            if current == terminal:
                state = "code"
            continue
    return "".join(output)


@dataclass
class EditModel:
    target: str = "asteroid.red.m12.prototype.001"
    revision: int = 0
    last_sequences: dict[str, int] = field(default_factory=dict)
    journal_entries: int = 0

    def apply(
        self,
        collector: str,
        target: str,
        sequence: int,
        expected_revision: int,
        removed: int,
    ):
        if (
            target != self.target
            or sequence != self.last_sequences.get(collector, 0) + 1
            or expected_revision != self.revision
            or removed <= 0
            or self.revision >= (2**64 - 1)
        ):
            return False, 0
        self.last_sequences[collector] = sequence
        self.revision += 1
        self.journal_entries += 1
        return True, removed


@dataclass
class ClusterModel:
    phase: str = "loose"
    revision: int = 1
    collector: str | None = None
    token: str | None = None
    credited: bool = False

    def reserve(self, collector: str, token: str) -> bool:
        if self.phase != "loose" or not collector or not token:
            return False
        self.phase = "reserved"
        self.collector = collector
        self.token = token
        self.revision += 1
        return True

    def attract(self, collector: str, token: str) -> bool:
        if (
            self.phase != "reserved"
            or collector != self.collector
            or token != self.token
        ):
            return False
        self.phase = "attracting"
        self.revision += 1
        return True

    def arrive(
        self,
        collector: str,
        token: str,
        *,
        eligible: bool = True,
        line_of_sight: bool = True,
        distance_cm: float = 100.0,
        observed_time: float = 3.0,
        expiry_time: float = 5.0,
        expected_arrival: float = 3.5,
        grace: float = 0.5,
    ) -> int:
        if (
            self.phase != "attracting"
            or collector != self.collector
            or token != self.token
            or self.credited
            or not eligible
            or not line_of_sight
            or distance_cm > 150.0
            or observed_time > expiry_time
            or observed_time > expected_arrival + grace
        ):
            return 0
        self.phase = "collected"
        self.credited = True
        self.revision += 1
        return 1


class M12VoxelAuthorityContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.header = read(CONTRACT_HEADER)
        cls.cpp = read(CONTRACT_CPP)
        cls.backend = read(BACKEND_HEADER)
        cls.code = strip_cpp_comments_and_literals(
            cls.header + "\n" + cls.cpp + "\n" + cls.backend
        )
        cls.queue = json.loads(read(QUEUE))
        cls.system = read(SYSTEM_RECORD)

    def test_client_envelope_is_untrusted_and_carries_no_yield(self):
        start = self.header.index("struct REDMMO_API FClientEditRequest")
        end = self.header.index("struct REDMMO_API FValidatedEdit", start)
        request = self.header[start:end]
        for required in (
            "TargetStableId",
            "MiningToolStableId",
            "RequestSequence",
            "ExpectedRevision",
            "AimOrigin",
            "AimDirection",
            "BrushRadiusCm",
            "PredictionToken",
        ):
            self.assertIn(required, request)
        for forbidden in (
            "Yield",
            "Amount",
            "RemovedVolume",
            "RemovedCell",
            "MaterialId",
        ):
            self.assertNotIn(forbidden, request)
        self.assertIn(
            "Passing structural validation never authorizes an",
            self.header,
        )
        self.assertIn(
            "the server still re-traces tool state, range, line of sight",
            self.header,
        )

    def test_isolated_candidate_has_explicit_bounded_limits(self):
        expected_defaults = {
            "MaxVolumeCellsPerAxis": "64",
            "MaxChunkCellsPerAxis": "16",
            "MaxEditedCellsPerRequest": "2048",
            "MaxDirtyChunksPerEdit": "8",
            "MaxYieldEntriesPerEdit": "4",
            "MaxClustersPerEdit": "4",
            "MaxJournalOperationsPerCheckpoint": "512",
            "MaxRequestsPerSecond": "8",
            "MaxCheckpointChunks": "64",
            "MaxCompressedCheckpointBytesPerChunk": "256 * 1024",
            "MaxUncompressedCheckpointBytesPerChunk": "64 * 1024",
            "MaxCheckpointSetBytes": "16 * 1024 * 1024",
            "MaxMiningRangeCm": "2500.f",
            "MaxSuctionRangeCm": "2000.f",
            "MaxSuctionDurationSeconds": "4.f",
            "MaxReservationDurationSeconds": "6.f",
            "MaxCollectionArrivalDistanceCm": "150.f",
            "MaxCollectionArrivalGraceSeconds": "0.5f",
        }
        for name, value in expected_defaults.items():
            self.assertRegex(
                self.header,
                rf"\b{name}\s*=\s*{re.escape(value)}\s*;",
            )
        limits = function_body(
            self.cpp, "bool RedVoxelMining::ValidateAuthorityLimits"
        )
        for name in expected_defaults:
            self.assertIn(name, limits)
        for hard_ceiling in (
            "PrototypeHardMaxCheckpointChunks",
            "PrototypeHardMaxCompressedBytesPerChunk",
            "PrototypeHardMaxUncompressedBytesPerChunk",
            "PrototypeHardMaxCheckpointSetBytes",
            "PrototypeHardMaxCollectionArrivalDistanceCm",
            "PrototypeHardMaxCollectionArrivalGraceSeconds",
        ):
            self.assertIn(hard_ceiling, limits)

    def test_volume_and_brush_validation_fail_closed(self):
        fingerprint = function_body(
            self.cpp, "bool RedVoxelMining::ComputeCanonicalVolumeSpecSha256"
        )
        for token in (
            "Spec.StableId.ToString().ToLower()",
            "Spec.MaterialTableId.ToString().ToLower()",
            "Spec.VolumeCellDimensions.X",
            "Spec.ChunkCellDimensions.X",
            "CellSizeBits",
            "Spec.BaseSeed",
            "Spec.GenerationVersion",
            "Sha256Hex(",
        ):
            self.assertIn(token, fingerprint)
        stable_id = function_body(
            self.cpp, "bool RedVoxelMining::IsNamespacedStableId"
        )
        for token in (
            'Text.Contains(TEXT("|"))',
            'Text.Contains(TEXT("="))',
            "FChar::IsWhitespace(Character)",
        ):
            self.assertIn(token, stable_id)
        for token in (
            "0x428a2f98U",
            "0xc67178f2U",
            "Padded[DataLength] = 0x80U",
            "static_cast<uint64>(DataLength) * 8U",
            "RotateRight32(E, 6)",
            "RotateRight32(A, 2)",
        ):
            self.assertIn(token, self.cpp)

        volume = function_body(
            self.cpp, "bool RedVoxelMining::ValidateVolumeSpec"
        )
        for token in (
            "IsNamespacedStableId(Spec.StableId)",
            "IsNamespacedStableId(Spec.MaterialTableId)",
            "IsCanonicalSha256(Spec.CanonicalSpecSha256)",
            "Spec.VolumeCellDimensions.X % Spec.ChunkCellDimensions.X != 0",
            "Spec.VolumeCellDimensions.Y % Spec.ChunkCellDimensions.Y != 0",
            "Spec.VolumeCellDimensions.Z % Spec.ChunkCellDimensions.Z != 0",
            "TryMultiplyPositive(",
            "TotalChunkCount > Limits.MaxCheckpointChunks",
            "ComputeCanonicalVolumeSpecSha256(Spec, RecomputedSpecSha256)",
            "Spec.CanonicalSpecSha256 != RecomputedSpecSha256",
            "Spec.BaseSeed == 0",
            "Spec.GenerationVersion == 0",
        ):
            self.assertIn(token, volume)

        client = function_body(
            self.cpp, "bool RedVoxelMining::ValidateClientRequestEnvelope"
        )
        for token in (
            "Request.RequestSequence == 0",
            "Request.ExpectedRevision == TNumericLimits<uint64>::Max()",
            "!Request.AimDirection.IsUnit(0.02)",
            "Request.BrushRadiusCm < Limits.MinBrushRadiusCm",
            "Request.BrushRadiusCm > Limits.MaxBrushRadiusCm",
            "!Request.PredictionToken.IsValid()",
        ):
            self.assertIn(token, client)

        server = function_body(
            self.cpp, "bool RedVoxelMining::ValidateServerEdit"
        )
        for token in (
            "Edit.AuthorityGenerationToken == 0",
            "!Edit.LocalSurfaceNormal.IsUnit(0.02)",
            "Edit.BrushRadiusCm < Limits.MinBrushRadiusCm",
            "Edit.BrushRadiusCm > Limits.MaxBrushRadiusCm",
        ):
            self.assertIn(token, server)

    def test_backend_result_is_atomic_bounded_and_volume_derived(self):
        apply = function_body(
            self.cpp, "bool RedVoxelMining::ValidateApplyResult"
        )
        for token in (
            "Edit.TargetStableId != Volume.StableId",
            "Result.TargetStableId != Edit.TargetStableId",
            "Result.RequestSequence != Edit.RequestSequence",
            "Result.PredictionToken != Edit.PredictionToken",
            "Result.AuthorityGenerationToken != Edit.AuthorityGenerationToken",
            "Result.PreviousRevision != Edit.ExpectedRevision",
            "Result.AppliedRevision != Result.PreviousRevision",
            "!Result.MaterialYields.IsEmpty()",
            "!Result.DirtyChunkCoordinates.IsEmpty()",
            "!IsNextRevision(Result.PreviousRevision, Result.AppliedRevision)",
            "Result.TotalRemovedCellCount > Limits.MaxEditedCellsPerRequest",
            "YieldCellTotal != Result.TotalRemovedCellCount",
            "Yield.RemovedCellCount * CellVolumeCm3",
            "FMath::IsNearlyEqual(",
            "MaterialIds.Contains(Yield.MaterialId)",
            "DirtyChunks.Contains(ChunkCoordinate)",
            "ChunkCoordinate.X >= ChunkCounts.X",
            "ChunkCoordinate.Y >= ChunkCounts.Y",
            "ChunkCoordinate.Z >= ChunkCounts.Z",
        ):
            self.assertIn(token, apply)

    def test_request_high_water_rejects_replay_skip_stale_and_overflow(self):
        accept = function_body(
            self.cpp, "bool RedVoxelMining::CanAcceptNextClientRequest"
        )
        for token in (
            "State.CollectorStableId != AuthorityCollectorStableId",
            "State.TargetStableId != Request.TargetStableId",
            "CurrentVolumeRevision == TNumericLimits<uint64>::Max()",
            "Request.ExpectedRevision != CurrentVolumeRevision",
            "!IsNextRevision(State.LastAcceptedSequence, Request.RequestSequence)",
            "Request.PredictionToken == State.LastAcceptedPredictionToken",
        ):
            self.assertIn(token, accept)
        self.assertNotIn(
            "State.LastAcceptedRevision != CurrentVolumeRevision",
            accept,
        )

        commit = function_body(
            self.cpp, "bool RedVoxelMining::CommitAcceptedClientRequest"
        )
        for token in (
            "!CanAcceptNextClientRequest(",
            "!ValidatedResult.bAccepted",
            "Request.TargetStableId != Edit.TargetStableId",
            "Request.MiningToolStableId != Edit.MiningToolStableId",
            "Request.RequestSequence != Edit.RequestSequence",
            "Request.ExpectedRevision != Edit.ExpectedRevision",
            "Request.PredictionToken != Edit.PredictionToken",
            "!ValidateApplyResult(",
        ):
            self.assertIn(token, commit)
        first_mutation = commit.index(
            "State.LastAcceptedSequence = Request.RequestSequence;"
        )
        self.assertGreater(first_mutation, commit.index("return false;"))
        self.assertIn(
            "State.LastAcceptedRevision = ValidatedResult.AppliedRevision;",
            commit[first_mutation:],
        )
        self.assertIn(
            "State.LastAcceptedPredictionToken = Request.PredictionToken;",
            commit[first_mutation:],
        )

    def test_checkpoint_is_identity_revision_coordinate_and_size_bounded(self):
        checkpoint = function_body(
            self.cpp, "bool RedVoxelMining::ValidateChunkCheckpoint"
        )
        for token in (
            "Checkpoint.TargetStableId != Volume.StableId",
            "Checkpoint.GenerationVersion != Volume.GenerationVersion",
            "Checkpoint.ThroughRevision == TNumericLimits<uint64>::Max()",
            "Checkpoint.BaseSeed != Volume.BaseSeed",
            "Checkpoint.MaterialTableId != Volume.MaterialTableId",
            "Checkpoint.VolumeSpecSha256 != Volume.CanonicalSpecSha256",
            "!IsAllowedCheckpointCodec(Checkpoint.CodecId)",
            "!IsCanonicalSha256(Checkpoint.CanonicalPayloadSha256)",
            "Verification.RecomputedCanonicalPayloadSha256",
            "Checkpoint.ChunkCoordinate.X >= ChunkCounts.X",
            "Checkpoint.ChunkCoordinate.Y >= ChunkCounts.Y",
            "Checkpoint.ChunkCoordinate.Z >= ChunkCounts.Z",
            "Checkpoint.UncompressedCellCount != ExpectedCellCount",
            "Checkpoint.UncompressedByteCount",
            "Verification.ActualUncompressedByteCount",
            "Checkpoint.CompressedDensityAndMaterial.IsEmpty()",
            "Limits.MaxCompressedCheckpointBytesPerChunk",
            "Limits.MaxUncompressedCheckpointBytesPerChunk",
        ):
            self.assertIn(token, checkpoint)

        volume_checkpoint = function_body(
            self.cpp, "bool RedVoxelMining::ValidateVolumeCheckpoint"
        )
        for token in (
            "ValidateAuthorityLimits(Checkpoint.AuthorityLimits",
            "Checkpoint.VolumeSpec",
            "Checkpoint.AuthorityLimits",
            "HasSameAuthorityLimits(",
            "HasSameVolumeSpec(",
            "Checkpoint.ThroughRevision == TNumericLimits<uint64>::Max()",
            "Checkpoint.CanonicalManifestSha256",
            "Verification.RecomputedCanonicalManifestSha256",
            "Checkpoint.Chunks.Num() != ExpectedChunkCount",
            "Verification.Chunks.Num() != ExpectedChunkCount",
            "Chunk.ThroughRevision != Checkpoint.ThroughRevision",
            "SeenChunks.Contains(Chunk.ChunkCoordinate)",
            "Verification.Chunks.FindByPredicate(",
            "ValidateChunkCheckpoint(",
            "TotalStoredBytes > Limits.MaxCheckpointSetBytes",
        ):
            self.assertIn(token, volume_checkpoint)

        restore = function_body(
            self.cpp,
            "bool RedVoxelMining::ValidateCheckpointRestorePrecondition",
        )
        for token in (
            "Precondition.TargetStableId != Checkpoint.TargetStableId",
            "ECheckpointRestoreMode::InitializeAbsentVolume",
            "Precondition.ExpectedCurrentRevision != 0",
            "Precondition.ExpectedAuthorityGenerationToken != 0",
            "ECheckpointRestoreMode::ReplaceQuiescedVolume",
            "Precondition.ExpectedAuthorityGenerationToken == 0",
            ">= TNumericLimits<uint64>::Max() - 1",
            "TNumericLimits<uint64>::Max()",
            "Checkpoint.ThroughRevision < Precondition.ExpectedCurrentRevision",
        ):
            self.assertIn(token, restore)

    def test_generated_outputs_require_exact_identity_and_role_specific_readiness(self):
        current = function_body(
            self.cpp, "bool RedVoxelMining::AreGeneratedOutputsCurrent"
        )
        for token in (
            "IsCanonicalSha256(Expected.ContentSha256)",
            "Expected.GenerationToken > 0",
            "Expected.GenerationToken < TNumericLimits<uint64>::Max()",
            "EGeneratedOutputRequirement::Presentation",
            "EGeneratedOutputRequirement::Collision",
            "Actual.TargetStableId == Expected.TargetStableId",
            "Actual.ChunkCoordinate == Expected.ChunkCoordinate",
            "Actual.ContentRevision == Expected.ContentRevision",
            "Actual.ContentSha256 == Expected.ContentSha256",
            "Actual.GenerationToken == Expected.GenerationToken",
            "IsCanonicalSha256(Actual.PresentationOutputSha256)",
            "IsCanonicalSha256(Actual.CollisionOutputSha256)",
            "Actual.PresentationOutputSha256.IsEmpty()",
            "Actual.CollisionOutputSha256.IsEmpty()",
            "!bRequiresPresentation || Actual.bPresentationReady",
            "!bRequiresCollision || Actual.bCollisionReady",
        ):
            self.assertIn(token, current)

    def test_generated_output_completion_ticket_is_single_role_and_bounded(self):
        ticket = function_body(
            self.cpp,
            "bool RedVoxelMining::ValidateGeneratedChunkBuildTicket",
        )
        completion = function_body(
            self.cpp,
            "bool RedVoxelMining::ValidateGeneratedChunkBuildCompletion",
        )
        for token in (
            "IsNamespacedStableId(Ticket.SourceRevision.TargetStableId)",
            "Ticket.SourceRevision.ChunkCoordinate.X < 0",
            "IsCanonicalSha256(Ticket.SourceRevision.ContentSha256)",
            "Ticket.SourceRevision.GenerationToken == 0",
            "IsCanonicalSha256(Ticket.VolumeSpecSha256)",
            "EGeneratedOutputRequirement::Presentation",
            "EGeneratedOutputRequirement::Collision",
            "IsNamespacedStableId(Ticket.BuildProfileId)",
            "Ticket.BuildProfileVersion == 0",
            "!Ticket.BackendInstanceId.IsValid()",
            "Ticket.BuildRequestToken == 0",
            "Ticket.BuildRequestToken == TNumericLimits<uint64>::Max()",
        ):
            self.assertIn(token, ticket)
        self.assertIn(
            "ValidateGeneratedChunkBuildTicket(",
            completion,
        )
        self.assertIn(
            "IsCanonicalSha256(Completion.OutputSha256)",
            completion,
        )

    def test_suction_credit_requires_matching_reserved_arrival_once(self):
        transition = function_body(
            self.cpp, "bool RedVoxelMining::CanTransitionLooseCluster"
        )
        credit = function_body(
            self.cpp, "bool RedVoxelMining::BuildInventoryCreditCommit"
        )
        for token in (
            "ValidateLooseClusterState(Current, Limits)",
            "ValidateLooseClusterState(Next, Limits)",
            "HasSameImmutableClusterIdentity(Current, Next)",
            "IsNextRevision(Current.Revision, Next.Revision)",
            "Next.ReservationToken == Current.ReservationToken",
            "ELooseClusterPhase::Collected",
        ):
            self.assertIn(token, transition)
        for token in (
            "Current.Phase != ELooseClusterPhase::Attracting",
            "Collected.Phase != ELooseClusterPhase::Collected",
            "CanTransitionLooseCluster(Current, Collected, Limits)",
            "Evidence.ClusterId != Current.ClusterId",
            "Evidence.SourceAsteroidStableId != Current.SourceAsteroidStableId",
            "Evidence.CollectorStableId != Current.CollectorStableId",
            "Evidence.ReservationToken != Current.ReservationToken",
            "Evidence.ObservedClusterRevision != Current.Revision",
            "!Evidence.bCollectorEligible",
            "!Evidence.bLineOfSightClear",
            "Limits.MaxCollectionArrivalDistanceCm",
            "Current.ReservationExpiryServerTimeSeconds",
            "Current.ExpectedArrivalServerTimeSeconds",
            "OutCommit.ClusterId = Collected.ClusterId",
            "OutCommit.CollectedRevision = Collected.Revision",
            "ELooseClusterPhase::Collected",
        ):
            self.assertIn(token, credit)

        model = ClusterModel()
        self.assertEqual(model.arrive("player.one", "token-a"), 0)
        self.assertTrue(model.reserve("player.one", "token-a"))
        self.assertEqual(model.arrive("player.one", "token-a"), 0)
        self.assertFalse(model.attract("player.two", "token-a"))
        self.assertTrue(model.attract("player.one", "token-a"))
        self.assertEqual(model.arrive("player.one", "wrong-token"), 0)
        self.assertEqual(
            model.arrive("player.one", "token-a", eligible=False),
            0,
        )
        self.assertEqual(
            model.arrive("player.one", "token-a", line_of_sight=False),
            0,
        )
        self.assertEqual(
            model.arrive("player.one", "token-a", distance_cm=151.0),
            0,
        )
        self.assertEqual(
            model.arrive(
                "player.one",
                "token-a",
                observed_time=5.1,
                expiry_time=5.0,
            ),
            0,
        )
        self.assertEqual(model.arrive("player.one", "token-a"), 1)
        self.assertEqual(model.arrive("player.one", "token-a"), 0)

    def test_revision_and_replay_reference_model_is_atomic(self):
        model = EditModel()
        self.assertEqual(
            model.apply("player.one", model.target, 1, 0, 12),
            (True, 12),
        )
        snapshot = (
            model.revision,
            dict(model.last_sequences),
            model.journal_entries,
        )
        for request in (
            ("player.one", model.target, 1, 1, 12),
            ("player.one", model.target, 3, 1, 12),
            ("player.one", model.target, 2, 0, 12),
            ("player.one", "asteroid.red.wrong", 2, 1, 12),
            ("player.one", model.target, 2, 1, 0),
        ):
            self.assertEqual(model.apply(*request), (False, 0))
            self.assertEqual(
                (
                    model.revision,
                    model.last_sequences,
                    model.journal_entries,
                ),
                snapshot,
            )
        self.assertEqual(
            model.apply("player.two", model.target, 1, 1, 7),
            (True, 7),
        )
        self.assertEqual(
            model.apply("player.one", model.target, 2, 2, 5),
            (True, 5),
        )
        self.assertEqual(model.revision, 3)
        self.assertEqual(model.last_sequences, {"player.one": 2, "player.two": 1})
        self.assertEqual(model.journal_entries, 3)

    def test_backend_interface_exposes_only_validated_authority_outputs(self):
        for token in (
            "class REDMMO_API IRedVoxelAsteroidBackend",
            "InitializeVolume(",
            "GetAuthorityGenerationToken(",
            "ApplyValidatedEdit(",
            "const RedVoxelMining::FValidatedEdit& Edit",
            "RedVoxelMining::FApplyResult& OutResult",
            "CaptureCheckpointSet(",
            "InspectCheckpointSet(",
            "RestoreCheckpointSetAtomically(",
            "const RedVoxelMining::FCheckpointRestorePrecondition& Precondition",
            "QueueChunkRebuild(",
            "const RedVoxelMining::FChunkRevision& Revision",
            "RedVoxelMining::EGeneratedOutputRequirement OutputRole",
            "RedVoxelMining::FGeneratedChunkBuildRequest& OutRequest",
            "CompleteChunkRebuild(",
            "const RedVoxelMining::FGeneratedChunkBuildCompletion& Completion",
            "QueryGeneratedOutputState(",
            "InvalidateBuildsOlderThan(",
            "ReleaseVolume(",
            "uint64 ExpectedAuthorityGenerationToken",
        ):
            self.assertIn(token, self.backend)
        self.assertRegex(
            self.backend,
            r"virtual bool ReleaseVolume\(\s*FName StableId,\s*"
            r"uint64 ExpectedAuthorityGenerationToken,\s*"
            r"FString& OutError\) = 0;",
        )
        self.assertNotIn("RestoreChunkCheckpoint(", self.backend)
        for forbidden in (
            "FClientEditRequest",
            "ERedResourceType",
            "ARedResourcePickup",
            "ARedPlayerCharacter",
        ):
            self.assertNotIn(forbidden, self.backend)

    def test_contract_layer_has_no_actor_rpc_inventory_or_triangle_coupling(self):
        for forbidden in (
            "AActor",
            "UObject",
            "UActorComponent",
            "SpawnActor",
            "NewObject",
            "UFUNCTION",
            "NetMulticast",
            "DOREPLIFETIME",
            "ReplicatedUsing",
            "AddResource",
            "SetResourceTally",
            "ARedResourcePickup",
            "TArray<FVector>",
            "Triangles",
            "VoxelWorld",
            "DynamicMesh",
            "ProceduralMesh",
            "GeometryScript",
        ):
            self.assertNotIn(forbidden, self.code, forbidden)

    def test_contracts_remain_unwired_from_runtime_and_production_content(self):
        contract_paths = {
            CONTRACT_HEADER.resolve(),
            CONTRACT_CPP.resolve(),
            BACKEND_HEADER.resolve(),
            (ROOT / "Source/RedMMO/Mining/RedInMemorySparseVoxelBackend.h").resolve(),
            (ROOT / "Source/RedMMO/Mining/RedInMemorySparseVoxelBackend.cpp").resolve(),
            (
                ROOT
                / "Source/RedMMO/Mining/RedInMemorySparseVoxelBackendTests.cpp"
            ).resolve(),
        }
        for path in (ROOT / "Source/RedMMO").rglob("*"):
            if path.suffix.lower() not in (".h", ".cpp") or path.resolve() in contract_paths:
                continue
            source = strip_cpp_comments_and_literals(read(path))
            for forbidden in (
                "RedVoxelMiningContracts",
                "IRedVoxelAsteroidBackend",
                "RedVoxelMining::",
            ):
                self.assertNotIn(forbidden, source, str(path))

        self.assertFalse(
            (
                ROOT
                / "Content/RedMMO/Maps/Tests/RedVoxelAsteroid_M12.umap"
            ).exists()
        )
        self.assertFalse(
            (ROOT / "Source/RedMMO/Mining/RedVoxelAsteroidPrototype.h").exists()
        )
        self.assertFalse(
            (ROOT / "Source/RedMMO/Mining/RedLooseResourceCluster.h").exists()
        )
        build_rules = read(BUILD_RULES)
        self.assertNotIn('"Voxel"', build_rules)
        self.assertNotIn('"GeometryScriptingCore"', build_rules)
        voxel_entries = [
            plugin
            for plugin in json.loads(read(UPROJECT))["Plugins"]
            if plugin.get("Name") == "Voxel"
        ]
        self.assertEqual(voxel_entries, [{"Name": "Voxel", "Enabled": False}])

    def test_canonical_module_remains_in_progress_and_static_only(self):
        modules = {module["id"]: module for module in self.queue["modules"]}
        self.assertEqual(modules["M00"]["status"], "incomplete_retry")
        self.assertEqual(modules["M12"]["status"], "in_progress")
        self.assertEqual(modules["M12"]["dependencies"], ["M00"])
        for token in (
            "IRedVoxelAsteroidBackend",
            "backend-neutral",
            "offline_verification",
            "production_enabled: false",
        ):
            self.assertIn(token, self.system)


if __name__ == "__main__":
    unittest.main()
