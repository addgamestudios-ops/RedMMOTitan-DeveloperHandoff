"""Static and independent-model contracts for M12 journal/checkpoint persistence."""

from __future__ import annotations

import copy
import hashlib
import struct
import unittest
from dataclasses import dataclass, replace
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CONTRACT_HEADER = ROOT / "Source/RedMMO/Mining/RedVoxelMiningContracts.h"
CONTRACT_CPP = ROOT / "Source/RedMMO/Mining/RedVoxelMiningContracts.cpp"
INTERFACE = ROOT / "Source/RedMMO/Mining/RedVoxelAsteroidBackend.h"
BACKEND_HEADER = ROOT / "Source/RedMMO/Mining/RedInMemorySparseVoxelBackend.h"
BACKEND_CPP = ROOT / "Source/RedMMO/Mining/RedInMemorySparseVoxelBackend.cpp"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest().upper()


def f32_bits(value: float) -> str:
    return struct.pack(">f", value).hex().upper()


def f64_bits(value: float) -> str:
    return struct.pack(">d", value).hex().upper()


def function_body(source: str, signature: str) -> str:
    start = source.find(signature)
    if start < 0:
        raise AssertionError(f"missing function signature: {signature}")
    opening = source.find("{", start)
    if opening < 0:
        raise AssertionError(f"missing function body: {signature}")
    depth = 0
    for cursor in range(opening, len(source)):
        if source[cursor] == "{":
            depth += 1
        elif source[cursor] == "}":
            depth -= 1
            if depth == 0:
                return source[opening : cursor + 1]
    raise AssertionError(f"unterminated function: {signature}")


@dataclass(frozen=True)
class Operation:
    target: str
    spec: str
    operation_id: str
    collector: str
    tool: str
    algorithm: int
    previous_revision: int
    revision: int
    sequence: int
    prediction: str
    center: tuple[float, float, float]
    normal: tuple[float, float, float]
    radius: float
    removed: int
    result_sha: str
    previous_sha: str
    canonical_sha: str = ""

    def hashed(self) -> "Operation":
        fields = (
            "red.voxel-edit-operation.v1",
            self.target,
            self.spec,
            self.operation_id,
            self.collector,
            self.tool,
            str(self.algorithm),
            str(self.previous_revision),
            str(self.revision),
            str(self.sequence),
            self.prediction,
            *(f64_bits(value) for value in self.center),
            *(f64_bits(value) for value in self.normal),
            f32_bits(self.radius),
            str(self.removed),
            self.result_sha,
            self.previous_sha or "none",
        )
        return replace(self, canonical_sha=sha256("|".join(fields)))


@dataclass(frozen=True)
class Ticket:
    target: str
    spec: str
    expected_acknowledged_base: bool
    expected_base_revision: int
    expected_base_manifest: str
    expected_base_tail: str
    through_revision: int
    checkpoint_manifest: str
    checkpoint_tail: str
    generation: int
    backend_instance: str
    token: int


class PersistenceModel:
    next_backend = 1

    def __init__(self, target: str = "asteroid.red.m12.test", max_journal: int = 8):
        self.target = target
        self.spec = sha256(f"spec|{target}")
        self.generation = 1
        self.backend_instance = f"backend-{PersistenceModel.next_backend}"
        PersistenceModel.next_backend += 1
        self.max_journal = max_journal
        self.current_revision = 0
        self.base_revision = 0
        self.acknowledged = False
        self.base_manifest = ""
        self.base_tail = ""
        self.journal: list[Operation] = []
        self.last_token = 0
        self.pending: Ticket | None = None
        self.last_ack: Ticket | None = None

    def current_tail(self) -> str:
        return self.journal[-1].canonical_sha if self.journal else self.base_tail

    def validate_journal(self) -> bool:
        if self.base_revision > self.current_revision:
            return False
        if self.acknowledged:
            if len(self.base_manifest) != 64:
                return False
        elif self.base_manifest or self.base_tail:
            return False
        if self.current_revision - self.base_revision != len(self.journal):
            return False
        previous_revision = self.base_revision
        previous_sha = self.base_tail
        operation_ids: set[str] = set()
        collector_sequences: set[tuple[str, int]] = set()
        for operation in self.journal:
            if (
                operation.target != self.target
                or operation.spec != self.spec
                or operation.previous_revision != previous_revision
                or operation.revision != previous_revision + 1
                or operation.previous_sha != previous_sha
                or operation.hashed().canonical_sha != operation.canonical_sha
                or operation.operation_id in operation_ids
                or (operation.collector, operation.sequence)
                in collector_sequences
            ):
                return False
            operation_ids.add(operation.operation_id)
            collector_sequences.add((operation.collector, operation.sequence))
            previous_revision = operation.revision
            previous_sha = operation.canonical_sha
        return previous_revision == self.current_revision

    def apply(self, sequence: int | None = None) -> bool:
        if not self.validate_journal() or len(self.journal) >= self.max_journal:
            return False
        previous = self.current_revision
        revision = previous + 1
        sequence = sequence or revision
        if any(
            operation.collector == "player.red.test"
            and operation.sequence == sequence
            for operation in self.journal
        ):
            return False
        operation = Operation(
            target=self.target,
            spec=self.spec,
            operation_id=f"operation-{self.generation}-{revision}",
            collector="player.red.test",
            tool="tool.red.mining-beam",
            algorithm=1,
            previous_revision=previous,
            revision=revision,
            sequence=sequence,
            prediction=f"prediction-{revision}",
            center=(revision + 0.25, -2.0, 4.5),
            normal=(0.0, 0.0, 1.0),
            radius=100.0,
            removed=revision + 3,
            result_sha=sha256(f"result|{self.target}|{revision}"),
            previous_sha=self.current_tail(),
        ).hashed()
        self.journal.append(operation)
        self.current_revision = revision
        return self.validate_journal()

    def checkpoint_manifest(self, revision: int | None = None) -> str:
        revision = self.current_revision if revision is None else revision
        return sha256(
            f"checkpoint|{self.target}|{self.spec}|{self.generation}|{revision}"
        )

    def capture(self) -> Ticket:
        if not self.validate_journal():
            raise ValueError("journal")
        self.last_token += 1
        ticket = Ticket(
            target=self.target,
            spec=self.spec,
            expected_acknowledged_base=self.acknowledged,
            expected_base_revision=self.base_revision,
            expected_base_manifest=self.base_manifest if self.acknowledged else "",
            expected_base_tail=self.base_tail if self.acknowledged else "",
            through_revision=self.current_revision,
            checkpoint_manifest=self.checkpoint_manifest(),
            checkpoint_tail=self.current_tail(),
            generation=self.generation,
            backend_instance=self.backend_instance,
            token=self.last_token,
        )
        self.pending = ticket
        return ticket

    def acknowledge(self, ticket: Ticket) -> bool:
        if (
            ticket.target != self.target
            or ticket.spec != self.spec
            or ticket.generation != self.generation
            or ticket.backend_instance != self.backend_instance
        ):
            return False
        if (
            self.acknowledged
            and ticket == self.last_ack
            and self.base_revision == ticket.through_revision
            and self.base_manifest == ticket.checkpoint_manifest
            and self.base_tail == ticket.checkpoint_tail
        ):
            return True
        if ticket != self.pending or not self.validate_journal():
            return False
        if (
            ticket.expected_acknowledged_base != self.acknowledged
            or ticket.expected_base_revision != self.base_revision
            or ticket.expected_base_manifest
            != (self.base_manifest if self.acknowledged else "")
            or ticket.expected_base_tail
            != (self.base_tail if self.acknowledged else "")
            or not self.base_revision <= ticket.through_revision <= self.current_revision
        ):
            return False
        prefix_count = ticket.through_revision - self.base_revision
        checkpoint_tail = (
            self.base_tail
            if prefix_count == 0
            else self.journal[prefix_count - 1].canonical_sha
        )
        if checkpoint_tail != ticket.checkpoint_tail:
            return False
        if (
            ticket.through_revision == self.current_revision
            and ticket.checkpoint_manifest != self.checkpoint_manifest()
        ):
            return False
        suffix = copy.deepcopy(self.journal[prefix_count:])
        if suffix and suffix[0].previous_sha != ticket.checkpoint_tail:
            return False
        self.acknowledged = True
        self.base_revision = ticket.through_revision
        self.base_manifest = ticket.checkpoint_manifest
        self.base_tail = ticket.checkpoint_tail
        self.journal = suffix
        self.last_ack = ticket
        self.pending = None
        return self.validate_journal()

    def export(self) -> dict | None:
        if not self.acknowledged or not self.validate_journal():
            return None
        operations = copy.deepcopy(self.journal)
        final_tail = self.current_tail()
        canonical = "|".join(
            (
                "red.voxel-edit-journal-export.v1",
                self.target,
                self.spec,
                str(self.base_revision),
                self.base_manifest,
                self.base_tail or "none",
                str(self.current_revision),
                str(len(operations)),
                final_tail or "none",
                *(operation.canonical_sha for operation in operations),
            )
        )
        return {
            "target": self.target,
            "spec": self.spec,
            "base_revision": self.base_revision,
            "base_manifest": self.base_manifest,
            "base_tail": self.base_tail,
            "through_revision": self.current_revision,
            "operations": operations,
            "final_tail": final_tail,
            "manifest": sha256(canonical),
        }

    def restore(self, through_revision: int) -> None:
        self.generation += 1
        self.current_revision = through_revision
        self.base_revision = through_revision
        self.acknowledged = False
        self.base_manifest = ""
        self.base_tail = ""
        self.journal = []
        self.pending = None
        self.last_ack = None

    def release_recreate(self) -> None:
        self.generation += 1
        self.current_revision = 0
        self.base_revision = 0
        self.acknowledged = False
        self.base_manifest = ""
        self.base_tail = ""
        self.journal = []
        self.pending = None
        self.last_ack = None


class JournalCheckpointPersistenceContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contract_header = read(CONTRACT_HEADER)
        cls.contract_cpp = read(CONTRACT_CPP)
        cls.interface = read(INTERFACE)
        cls.backend_header = read(BACKEND_HEADER)
        cls.backend_cpp = read(BACKEND_CPP)

    def test_source_exposes_non_reflected_persistence_boundary(self):
        combined = self.contract_header + self.interface + self.backend_header
        for token in (
            "FEditOperation",
            "FEditJournalExport",
            "FCheckpointPersistenceTicket",
            "FCheckpointPersistenceRequest",
            "FCheckpointPersistenceAcknowledgement",
            "ValidateCheckpointPersistenceRequest(",
            "ExportOperationJournal(",
            "CaptureCheckpointForPersistence(",
            "AcknowledgePersistedCheckpoint(",
        ):
            self.assertIn(token, combined)
        for forbidden in ("USTRUCT", "UFUNCTION", "Server, Reliable", "DOREPLIFETIME"):
            self.assertNotIn(forbidden, combined)

    def test_operation_hash_covers_authority_and_exact_brush_fields(self):
        body = function_body(
            self.contract_cpp,
            "bool RedVoxelMining::ComputeCanonicalEditOperationSha256(",
        )
        for token in (
            "red.voxel-edit-operation.v1",
            "TargetStableId",
            "VolumeSpecSha256",
            "OperationId",
            "CollectorStableId",
            "MiningToolStableId",
            "EditAlgorithmVersion",
            "PreviousRevision",
            "Revision",
            "RequestSequence",
            "PredictionToken",
            "LocalBrushCenter.X",
            "LocalBrushCenter.Y",
            "LocalBrushCenter.Z",
            "LocalSurfaceNormal.X",
            "LocalSurfaceNormal.Y",
            "LocalSurfaceNormal.Z",
            "BrushRadiusCm",
            "RemovedCellCount",
            "ResultContentSha256",
            "PreviousOperationSha256",
            "DoubleBits64",
            "FloatBits32",
        ):
            self.assertIn(token, body)
        self.assertLess(
            body.index("IsCanonicalSha256(Operation.ResultContentSha256)"),
            body.index("const FString Canonical"),
        )

    def test_public_journal_hash_is_bounded_before_string_construction(self):
        body = function_body(
            self.contract_cpp,
            "bool RedVoxelMining::ComputeCanonicalEditJournalSha256(",
        )
        for token in (
            "PrototypeHardMaxJournalOperationsPerCheckpoint",
            "RevisionDelta",
            "Operations.Num()",
            "IsCanonicalSha256",
            "CanonicalOperationSha256",
        ):
            self.assertIn(token, body)
        self.assertLess(
            body.index("PrototypeHardMaxJournalOperationsPerCheckpoint"),
            body.index("FString Canonical"),
        )

    def test_source_validates_exact_contiguous_hash_chained_suffix(self):
        live = function_body(self.backend_cpp, "bool ValidateStoredJournalState(")
        exported = function_body(
            self.contract_cpp,
            "bool RedVoxelMining::ValidateEditJournalExport(",
        )
        for body in (live, exported):
            self.assertIn("PreviousRevision", body)
            self.assertIn("PreviousOperationSha256", body)
            self.assertIn("CanonicalOperationSha256", body)
        self.assertIn("JournalBaseRevision", live)
        self.assertIn("CurrentRevision", live)
        self.assertIn("SeenOperationIds", live)
        self.assertIn("SeenCollectorSequences", live)
        self.assertIn("Operations.Num()", exported)
        self.assertIn("ThroughRevision", exported)
        self.assertIn("SeenOperationIds", exported)
        self.assertIn("SeenCollectorSequences", exported)

    def test_source_cross_checks_ticket_and_checkpoint_request_identity(self):
        body = function_body(
            self.contract_cpp,
            "bool RedVoxelMining::ValidateCheckpointPersistenceRequest(",
        )
        for token in (
            "ValidateCheckpointPersistenceTicket",
            "Checkpoint.TargetStableId",
            "Checkpoint.VolumeSpec.StableId",
            "Checkpoint.VolumeSpecSha256",
            "Checkpoint.VolumeSpec.CanonicalSpecSha256",
            "Checkpoint.ThroughRevision",
            "Checkpoint.CanonicalManifestSha256",
            "Ticket.CheckpointThroughRevision",
            "Ticket.CheckpointManifestSha256",
        ):
            self.assertIn(token, body)

    def test_same_revision_checkpoint_cannot_equivocate_manifest(self):
        ticket_validation = function_body(
            self.contract_cpp,
            "bool RedVoxelMining::ValidateCheckpointPersistenceTicket(",
        )
        self.assertIn("bExpectedAcknowledgedBase", ticket_validation)
        self.assertIn("CheckpointThroughRevision", ticket_validation)
        self.assertIn("ExpectedJournalBaseRevision", ticket_validation)
        self.assertIn("CheckpointManifestSha256", ticket_validation)
        self.assertIn(
            "ExpectedBaseCheckpointManifestSha256",
            ticket_validation,
        )

        model = PersistenceModel()
        self.assertTrue(model.acknowledge(model.capture()))
        same_revision = model.capture()
        conflicting = replace(
            same_revision,
            checkpoint_manifest=sha256("conflicting-same-revision-state"),
        )
        model.pending = conflicting
        self.assertFalse(model.acknowledge(conflicting))
        self.assertEqual(model.base_manifest, same_revision.expected_base_manifest)

    def test_source_acknowledges_exact_pending_ticket_and_stages_suffix(self):
        body = function_body(
            self.backend_cpp,
            "bool FRedInMemorySparseVoxelBackend::AcknowledgePersistedCheckpoint(",
        )
        for token in (
            "ValidateCheckpointPersistenceTicket",
            "AreCheckpointPersistenceTicketsEquivalent",
            "PendingCheckpointTicket",
            "AuthorityGenerationToken",
            "BackendInstanceId",
            "ExpectedJournalBaseRevision",
            "CheckpointManifestSha256",
            "CheckpointJournalTailSha256",
            "StagedJournalSuffix",
            "MoveTemp(StagedJournalSuffix)",
        ):
            self.assertIn(token, body)
        self.assertLess(
            body.index("TArray<FEditOperation> StagedJournalSuffix"),
            body.index("Volume->bHasAcknowledgedCheckpoint = true"),
        )

    def test_source_restore_requires_fresh_acknowledgement(self):
        body = function_body(
            self.backend_cpp,
            "bool FRedInMemorySparseVoxelBackend::RestoreCheckpointSetAtomically(",
        )
        self.assertIn(
            "Candidate.JournalBaseRevision =\n\t\tCheckpoint.ThroughRevision",
            body,
        )
        self.assertIn("Candidate.bHasAcknowledgedCheckpoint = false", body)
        self.assertIn("Candidate.BaseCheckpointManifestSha256.Reset()", body)
        self.assertIn("Candidate.BaseJournalTailSha256.Reset()", body)
        self.assertIn("Candidate.bCheckpointPersistencePending = false", body)

    def test_initial_capture_ack_enables_empty_detached_export(self):
        model = PersistenceModel()
        self.assertIsNone(model.export())
        ticket = model.capture()
        self.assertTrue(model.acknowledge(ticket))
        exported = model.export()
        self.assertIsNotNone(exported)
        self.assertEqual(exported["base_revision"], 0)
        self.assertEqual(exported["through_revision"], 0)
        self.assertEqual(exported["operations"], [])
        self.assertEqual(exported["final_tail"], "")

    def test_hash_tamper_reorder_and_gap_fail_closed(self):
        model = PersistenceModel()
        self.assertTrue(model.acknowledge(model.capture()))
        self.assertTrue(model.apply())
        self.assertTrue(model.apply())
        pristine = copy.deepcopy(model.journal)

        model.journal[0] = replace(model.journal[0], removed=999)
        self.assertFalse(model.validate_journal())
        model.journal = copy.deepcopy(pristine)
        model.journal.reverse()
        self.assertFalse(model.validate_journal())
        model.journal = copy.deepcopy(pristine)
        model.journal[1] = replace(model.journal[1], previous_revision=0).hashed()
        self.assertFalse(model.validate_journal())

    def test_duplicate_operation_or_collector_sequence_fails(self):
        model = PersistenceModel()
        self.assertTrue(model.acknowledge(model.capture()))
        self.assertTrue(model.apply())
        self.assertTrue(model.apply())
        first, second = copy.deepcopy(model.journal)

        duplicate_id = replace(
            second,
            operation_id=first.operation_id,
            previous_sha=first.canonical_sha,
        ).hashed()
        model.journal[1] = duplicate_id
        self.assertFalse(model.validate_journal())

        duplicate_sequence = replace(
            second,
            sequence=first.sequence,
            previous_sha=first.canonical_sha,
        ).hashed()
        model.journal[1] = duplicate_sequence
        self.assertFalse(model.validate_journal())

    def test_prediction_token_reuse_with_distinct_sequence_does_not_poison_journal(self):
        model = PersistenceModel()
        self.assertTrue(model.acknowledge(model.capture()))
        self.assertTrue(model.apply())
        self.assertTrue(model.apply())
        first, second = copy.deepcopy(model.journal)

        same_collector_reuse = replace(
            second,
            prediction=first.prediction,
            previous_sha=first.canonical_sha,
        ).hashed()
        model.journal[1] = same_collector_reuse
        self.assertTrue(model.validate_journal())

        cross_collector_reuse = replace(
            second,
            collector="player.red.other",
            prediction=first.prediction,
            previous_sha=first.canonical_sha,
        ).hashed()
        model.journal[1] = cross_collector_reuse
        self.assertTrue(model.validate_journal())

    def test_apply_rejects_retained_collector_sequence_before_mutation(self):
        body = function_body(
            self.backend_cpp,
            "bool FRedInMemorySparseVoxelBackend::ApplyValidatedEdit(",
        )
        self.assertIn("Journal.ContainsByPredicate", body)
        self.assertIn("Operation.CollectorStableId", body)
        self.assertIn("Operation.RequestSequence", body)
        self.assertIn("EEditRejectReason::DuplicateRequest", body)
        self.assertIn("CandidateOperationId", body)
        self.assertLess(
            body.index("EEditRejectReason::DuplicateRequest"),
            body.index("// Commit begins only after"),
        )

        model = PersistenceModel()
        self.assertTrue(model.apply(sequence=1))
        before = copy.deepcopy(model.__dict__)
        self.assertFalse(model.apply(sequence=1))
        self.assertEqual(model.__dict__, before)

    def test_export_is_read_only_and_detached(self):
        model = PersistenceModel()
        self.assertTrue(model.acknowledge(model.capture()))
        self.assertTrue(model.apply())
        before = copy.deepcopy(model.journal)
        exported = model.export()
        self.assertEqual(model.journal, before)
        exported["operations"].clear()
        exported["base_manifest"] = "tampered"
        self.assertEqual(model.journal, before)
        self.assertEqual(len(model.journal), 1)
        self.assertEqual(len(model.base_manifest), 64)

    def test_pending_ticket_is_exact_and_reissue_supersedes(self):
        model = PersistenceModel()
        first = model.capture()
        second = model.capture()
        self.assertNotEqual(first.token, second.token)
        self.assertFalse(model.acknowledge(first))
        self.assertFalse(model.acknowledge(replace(second, token=second.token + 10)))
        self.assertTrue(model.acknowledge(second))

    def test_ack_compacts_only_covered_prefix_and_preserves_suffix(self):
        model = PersistenceModel()
        self.assertTrue(model.acknowledge(model.capture()))
        self.assertTrue(model.apply())
        self.assertTrue(model.apply())
        ticket = model.capture()
        checkpoint_tail = ticket.checkpoint_tail
        self.assertTrue(model.apply())
        self.assertTrue(model.apply())
        self.assertTrue(model.acknowledge(ticket))
        self.assertEqual(model.base_revision, 2)
        self.assertEqual(model.current_revision, 4)
        self.assertEqual([operation.revision for operation in model.journal], [3, 4])
        self.assertEqual(model.journal[0].previous_sha, checkpoint_tail)
        self.assertIsNotNone(model.export())

    def test_duplicate_is_idempotent_but_cross_authority_is_rejected(self):
        model = PersistenceModel()
        ticket = model.capture()
        self.assertTrue(model.acknowledge(ticket))
        before = copy.deepcopy(model.__dict__)
        self.assertTrue(model.acknowledge(ticket))
        self.assertEqual(model.__dict__, before)

        other = PersistenceModel(target="asteroid.red.m12.other")
        self.assertFalse(other.acknowledge(ticket))
        model.release_recreate()
        self.assertFalse(model.acknowledge(ticket))

    def test_acknowledgement_releases_bounded_journal_capacity(self):
        model = PersistenceModel(max_journal=2)
        self.assertTrue(model.apply())
        self.assertTrue(model.apply())
        self.assertFalse(model.apply())
        self.assertTrue(model.acknowledge(model.capture()))
        self.assertEqual(model.journal, [])
        self.assertTrue(model.apply())

    def test_restore_invalidates_old_ticket_and_requires_explicit_reack(self):
        model = PersistenceModel()
        self.assertTrue(model.apply())
        old_ticket = model.capture()
        model.restore(5)
        self.assertFalse(model.acknowledge(old_ticket))
        self.assertIsNone(model.export())
        self.assertTrue(model.apply())
        fresh_ticket = model.capture()
        self.assertTrue(model.acknowledge(fresh_ticket))
        self.assertIsNotNone(model.export())

    def test_contract_does_not_overclaim_fsync_replay_or_import(self):
        combined = self.contract_header + self.interface
        self.assertIn("not proof of fsync", combined)
        self.assertIn("Replay,", combined)
        self.assertIn("import, replication", combined)
        self.assertIn("unimplemented trust boundaries", combined)
        self.assertIn("must never be exposed to clients or RPCs", combined)


if __name__ == "__main__":
    unittest.main()
