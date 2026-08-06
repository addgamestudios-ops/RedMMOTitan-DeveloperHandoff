"""Static and independent-model contracts for M12 generated-output completion."""

from __future__ import annotations

import copy
import hashlib
import re
import unittest
from dataclasses import dataclass, replace
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CONTRACT_HEADER = ROOT / "Source/RedMMO/Mining/RedVoxelMiningContracts.h"
CONTRACT_CPP = ROOT / "Source/RedMMO/Mining/RedVoxelMiningContracts.cpp"
INTERFACE = ROOT / "Source/RedMMO/Mining/RedVoxelAsteroidBackend.h"
BACKEND_HEADER = ROOT / "Source/RedMMO/Mining/RedInMemorySparseVoxelBackend.h"
BACKEND_CPP = ROOT / "Source/RedMMO/Mining/RedInMemorySparseVoxelBackend.cpp"
UINT64_MAX = (1 << 64) - 1
PROFILE = "red.voxel-output.profile.sparse-binary-v1"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def sha256(value: bytes | str) -> str:
    if isinstance(value, str):
        value = value.encode("utf-8")
    return hashlib.sha256(value).hexdigest().upper()


def is_sha256(value: str) -> bool:
    return bool(re.fullmatch(r"[0-9A-Fa-f]{64}", value))


def function_body(source: str, signature: str) -> str:
    start = source.find(signature)
    if start < 0:
        raise AssertionError(f"missing function signature: {signature}")
    brace = source.find("{", start)
    if brace < 0:
        raise AssertionError(f"missing function body: {signature}")
    depth = 0
    for cursor in range(brace, len(source)):
        if source[cursor] == "{":
            depth += 1
        elif source[cursor] == "}":
            depth -= 1
            if depth == 0:
                return source[brace : cursor + 1]
    raise AssertionError(f"unterminated function body: {signature}")


@dataclass(frozen=True)
class Ticket:
    target: str
    spec_sha: str
    coord: tuple[int, int, int]
    revision: int
    content_sha: str
    generation: int
    role: str
    profile: str
    profile_version: int
    instance: str
    token: int


class Chunk:
    def __init__(self, stable_id: str, coord: tuple[int, int, int], generation: int):
        self.coord = coord
        self.cells = bytes([1 + (coord[0] % 3)] * 64)
        self.revision = 0
        self.generation = generation
        self.content_sha = sha256(
            f"{stable_id}|{coord}|{self.revision}|".encode("utf-8") + self.cells
        )
        self.ready = {"P": False, "C": False}
        self.output_sha = {"P": "", "C": ""}
        self.ticket: dict[str, Ticket | None] = {"P": None, "C": None}
        self.pending = {"P": False, "C": False}

    def reset_identity(self, stable_id: str, generation: int) -> None:
        self.generation = generation
        self.revision += 1
        self.cells = sha256(self.cells).encode("ascii")[:64]
        self.content_sha = sha256(
            f"{stable_id}|{self.coord}|{self.revision}|".encode("utf-8")
            + self.cells
        )
        self.ready = {"P": False, "C": False}
        self.output_sha = {"P": "", "C": ""}
        self.ticket = {"P": None, "C": None}
        self.pending = {"P": False, "C": False}


class Volume:
    def __init__(self, stable_id: str, generation: int):
        self.stable_id = stable_id
        self.spec_sha = sha256(f"spec|{stable_id}")
        self.generation = generation
        self.chunks = {
            coord: Chunk(stable_id, coord, generation)
            for coord in ((0, 0, 0), (1, 0, 0))
        }


class OutputBackendModel:
    next_instance = 1

    def __init__(self):
        self.instance = f"backend-instance-{OutputBackendModel.next_instance}"
        OutputBackendModel.next_instance += 1
        self.last_token = 0
        self.volumes: dict[str, Volume] = {}
        self.generation_tombstones: dict[str, int] = {}

    def create(self, stable_id: str) -> Volume:
        generation = self.generation_tombstones.get(stable_id, 0) + 1
        volume = Volume(stable_id, generation)
        self.volumes[stable_id] = volume
        self.generation_tombstones[stable_id] = generation
        return volume

    def revision(self, stable_id: str, coord=(0, 0, 0)) -> dict:
        volume = self.volumes[stable_id]
        chunk = volume.chunks[coord]
        return {
            "target": stable_id,
            "coord": coord,
            "revision": chunk.revision,
            "sha": chunk.content_sha,
            "generation": volume.generation,
        }

    def queue(self, revision: dict, role: str):
        if role not in ("P", "C"):
            return None
        volume = self.volumes.get(revision.get("target"))
        if not volume:
            return None
        chunk = volume.chunks.get(revision.get("coord"))
        if not chunk:
            return None
        expected = self.revision(volume.stable_id, chunk.coord)
        if revision != expected or chunk.ready[role]:
            return None
        if self.last_token >= UINT64_MAX - 1:
            return None
        token = self.last_token + 1
        ticket = Ticket(
            target=volume.stable_id,
            spec_sha=volume.spec_sha,
            coord=chunk.coord,
            revision=chunk.revision,
            content_sha=chunk.content_sha,
            generation=volume.generation,
            role=role,
            profile=PROFILE,
            profile_version=1,
            instance=self.instance,
            token=token,
        )
        request = {"ticket": ticket, "cells": bytes(chunk.cells)}
        chunk.ticket[role] = ticket
        chunk.pending[role] = True
        self.last_token = token
        return request

    def complete(self, ticket: Ticket, output_sha: str) -> bool:
        if ticket.role not in ("P", "C") or not is_sha256(output_sha):
            return False
        volume = self.volumes.get(ticket.target)
        if not volume:
            return False
        chunk = volume.chunks.get(ticket.coord)
        if not chunk:
            return False
        live_identity = (
            ticket.spec_sha == volume.spec_sha
            and ticket.revision == chunk.revision
            and ticket.content_sha == chunk.content_sha
            and ticket.generation == volume.generation
            and ticket.profile == PROFILE
            and ticket.profile_version == 1
            and ticket.instance == self.instance
        )
        if not live_identity or chunk.ticket[ticket.role] != ticket:
            return False
        if not chunk.pending[ticket.role]:
            return (
                chunk.ready[ticket.role]
                and chunk.output_sha[ticket.role] == output_sha
            )
        chunk.ready[ticket.role] = True
        chunk.output_sha[ticket.role] = output_sha
        chunk.pending[ticket.role] = False
        return True

    def edit(self, stable_id: str, coord=(0, 0, 0)) -> None:
        volume = self.volumes[stable_id]
        volume.chunks[coord].reset_identity(stable_id, volume.generation)

    def restore(self, stable_id: str) -> None:
        volume = self.volumes[stable_id]
        volume.generation += 1
        self.generation_tombstones[stable_id] = volume.generation
        for chunk in volume.chunks.values():
            chunk.generation = volume.generation
            chunk.ready = {"P": False, "C": False}
            chunk.output_sha = {"P": "", "C": ""}
            chunk.ticket = {"P": None, "C": None}
            chunk.pending = {"P": False, "C": False}

    def release_recreate(self, stable_id: str) -> Volume:
        del self.volumes[stable_id]
        return self.create(stable_id)

    def current(self, stable_id: str, coord, requirement: str) -> bool:
        chunk = self.volumes[stable_id].chunks[coord]
        if requirement == "P":
            roles = ("P",)
        elif requirement == "C":
            roles = ("C",)
        elif requirement == "PC":
            roles = ("P", "C")
        else:
            return False
        return all(chunk.ready[role] and is_sha256(chunk.output_sha[role]) for role in roles)


class GeneratedOutputCompletionContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contract_header = read(CONTRACT_HEADER)
        cls.contract_cpp = read(CONTRACT_CPP)
        cls.interface = read(INTERFACE)
        cls.backend_header = read(BACKEND_HEADER)
        cls.backend_cpp = read(BACKEND_CPP)

    def test_source_exposes_private_single_role_ticket_request_and_completion(self):
        combined = self.contract_header + self.interface
        for token in (
            "FGeneratedChunkBuildTicket",
            "FGeneratedChunkBuildRequest",
            "FGeneratedChunkBuildCompletion",
            "VolumeSpecSha256",
            "BuildProfileId",
            "BuildProfileVersion",
            "BackendInstanceId",
            "BuildRequestToken",
            "CanonicalDensityAndMaterial",
            "OutputSha256",
            "EGeneratedOutputRequirement OutputRole",
            "FGeneratedChunkBuildRequest& OutRequest",
            "CompleteChunkRebuild(",
        ):
            self.assertIn(token, combined)
        for forbidden in ("USTRUCT", "UFUNCTION", "Server, Reliable", "DOREPLIFETIME"):
            self.assertNotIn(forbidden, combined)

    def test_queue_issues_immutable_attempt_bound_request_before_commit(self):
        body = function_body(
            self.backend_cpp,
            "bool FRedInMemorySparseVoxelBackend::QueueChunkRebuild",
        )
        for token in (
            "OutRequest = FGeneratedChunkBuildRequest()",
            "IsSingleGeneratedOutputRole(OutputRole)",
            "GetChunkCells(*Volume, ChunkIndex, ImmutableCells)",
            "HashChunkContent(",
            "RecomputedContentSha256 != Revision.ContentSha256",
            "Impl->LastIssuedBuildRequestToken + 1",
            "GeneratedOutputBuildProfileId",
            "GeneratedOutputBuildProfileVersion",
            "Impl->BackendInstanceId",
            "ValidateGeneratedChunkBuildTicket(",
            "CanonicalDensityAndMaterial",
            "Commit begins only after source identity",
        ):
            self.assertIn(token, body)
        self.assertNotIn("SetGeneratedOutputIdentity(", body)
        self.assertLess(
            body.index("ValidateGeneratedChunkBuildTicket("),
            body.index("Commit begins only after source identity"),
        )

    def test_completion_revalidates_live_ticket_and_commits_one_role(self):
        body = function_body(
            self.backend_cpp,
            "bool FRedInMemorySparseVoxelBackend::CompleteChunkRebuild",
        )
        for token in (
            "ValidateGeneratedChunkBuildCompletion(",
            "Ticket.VolumeSpecSha256",
            "GeneratedOutputBuildProfileId",
            "GeneratedOutputBuildProfileVersion",
            "Ticket.BackendInstanceId",
            "Ticket.SourceRevision.ContentRevision",
            "Ticket.SourceRevision.ContentSha256",
            "Ticket.SourceRevision.GenerationToken",
            "Volume->MinimumAcceptedBuildGenerationToken",
            "AreBuildTicketsEquivalent(Ticket, StoredTicket)",
            "StoredOutputSha256 == Completion.OutputSha256",
            "Role readiness changes only after",
            "bOutputReady = true",
            "StoredOutputSha256 = Completion.OutputSha256",
            "bBuildPending = false",
        ):
            self.assertIn(token, body)
        self.assertNotIn("Volume->CurrentRevision", body)

    def test_identity_reset_and_generation_invalidation_clear_both_roles(self):
        identity = function_body(
            self.backend_cpp,
            "void SetGeneratedOutputIdentity",
        )
        invalidate = function_body(
            self.backend_cpp,
            "void FRedInMemorySparseVoxelBackend::InvalidateBuildsOlderThan",
        )
        for body in (identity, invalidate):
            for token in (
                "PresentationOutputSha256.Reset()",
                "CollisionOutputSha256.Reset()",
                "PresentationBuildTicket",
                "CollisionBuildTicket",
                "bPresentationBuildPending = false",
                "bCollisionBuildPending = false",
            ):
                self.assertIn(token, body)

    def test_exact_role_completions_are_independent_and_queryable(self):
        backend = OutputBackendModel()
        backend.create("asteroid.red.one")
        coord = (0, 0, 0)
        p = backend.queue(backend.revision("asteroid.red.one", coord), "P")
        c = backend.queue(backend.revision("asteroid.red.one", coord), "C")
        self.assertFalse(backend.current("asteroid.red.one", coord, "PC"))
        self.assertTrue(backend.complete(p["ticket"], sha256("presentation")))
        self.assertTrue(backend.current("asteroid.red.one", coord, "P"))
        self.assertFalse(backend.current("asteroid.red.one", coord, "C"))
        self.assertTrue(backend.complete(c["ticket"], sha256("collision")))
        self.assertTrue(backend.current("asteroid.red.one", coord, "PC"))

    def test_invalid_roles_and_completion_before_queue_reject_without_mutation(self):
        backend = OutputBackendModel()
        backend.create("asteroid.red.one")
        revision = backend.revision("asteroid.red.one")
        before = copy.deepcopy(backend.volumes)
        self.assertIsNone(backend.queue(revision, ""))
        self.assertIsNone(backend.queue(revision, "PC"))
        self.assertEqual(before["asteroid.red.one"].chunks[(0, 0, 0)].ready,
                         backend.volumes["asteroid.red.one"].chunks[(0, 0, 0)].ready)
        forged = Ticket(
            "asteroid.red.one",
            backend.volumes["asteroid.red.one"].spec_sha,
            (0, 0, 0),
            0,
            revision["sha"],
            1,
            "P",
            PROFILE,
            1,
            backend.instance,
            1,
        )
        self.assertFalse(backend.complete(forged, sha256("output")))
        self.assertFalse(backend.complete(forged, "not-a-sha"))

    def test_wrong_identity_profile_epoch_and_token_reject_atomically(self):
        backend = OutputBackendModel()
        volume = backend.create("asteroid.red.one")
        request = backend.queue(backend.revision(volume.stable_id), "P")
        ticket = request["ticket"]
        digest = sha256("presentation")
        mutations = (
            replace(ticket, target="asteroid.red.other"),
            replace(ticket, spec_sha=sha256("wrong-spec")),
            replace(ticket, coord=(1, 0, 0)),
            replace(ticket, revision=ticket.revision + 1),
            replace(ticket, content_sha=sha256("wrong-content")),
            replace(ticket, generation=ticket.generation + 1),
            replace(ticket, profile="red.voxel-output.profile.other"),
            replace(ticket, profile_version=2),
            replace(ticket, instance="backend-instance-other"),
            replace(ticket, token=ticket.token + 1),
            replace(ticket, role="C"),
        )
        for candidate in mutations:
            with self.subTest(candidate=candidate):
                before = copy.deepcopy(volume.chunks[(0, 0, 0)].__dict__)
                self.assertFalse(backend.complete(candidate, digest))
                self.assertEqual(before, volume.chunks[(0, 0, 0)].__dict__)

    def test_same_role_requeue_rotates_token_and_rejects_older_attempt(self):
        backend = OutputBackendModel()
        backend.create("asteroid.red.one")
        revision = backend.revision("asteroid.red.one")
        first = backend.queue(revision, "P")
        second = backend.queue(revision, "P")
        self.assertGreater(second["ticket"].token, first["ticket"].token)
        self.assertFalse(backend.complete(first["ticket"], sha256("old")))
        self.assertTrue(backend.complete(second["ticket"], sha256("new")))

    def test_ready_role_is_monotonic_and_missing_role_preserves_it(self):
        backend = OutputBackendModel()
        backend.create("asteroid.red.one")
        revision = backend.revision("asteroid.red.one")
        p = backend.queue(revision, "P")
        self.assertTrue(backend.complete(p["ticket"], sha256("presentation")))
        token_before = backend.last_token
        self.assertIsNone(backend.queue(revision, "P"))
        self.assertEqual(backend.last_token, token_before)
        c = backend.queue(revision, "C")
        self.assertTrue(backend.current("asteroid.red.one", (0, 0, 0), "P"))
        self.assertTrue(backend.complete(c["ticket"], sha256("collision")))

    def test_editing_ticket_chunk_stales_it_but_other_chunk_edit_does_not(self):
        backend = OutputBackendModel()
        backend.create("asteroid.red.one")
        first = backend.queue(backend.revision("asteroid.red.one", (0, 0, 0)), "P")
        backend.edit("asteroid.red.one", (0, 0, 0))
        self.assertFalse(backend.complete(first["ticket"], sha256("stale")))

        second = backend.queue(backend.revision("asteroid.red.one", (0, 0, 0)), "P")
        backend.edit("asteroid.red.one", (1, 0, 0))
        self.assertTrue(backend.complete(second["ticket"], sha256("still-current")))

    def test_restore_release_recreate_and_new_backend_reject_old_ticket(self):
        backend = OutputBackendModel()
        backend.create("asteroid.red.one")
        restore_ticket = backend.queue(backend.revision("asteroid.red.one"), "P")
        backend.restore("asteroid.red.one")
        self.assertFalse(backend.complete(restore_ticket["ticket"], sha256("stale")))

        recreate_ticket = backend.queue(backend.revision("asteroid.red.one"), "P")
        backend.release_recreate("asteroid.red.one")
        self.assertFalse(backend.complete(recreate_ticket["ticket"], sha256("stale")))

        new_backend = OutputBackendModel()
        new_backend.create("asteroid.red.one")
        self.assertFalse(new_backend.complete(recreate_ticket["ticket"], sha256("stale")))

    def test_cross_volume_and_cross_chunk_completion_isolated(self):
        backend = OutputBackendModel()
        first = backend.create("asteroid.red.one")
        second = backend.create("asteroid.red.two")
        request = backend.queue(backend.revision(first.stable_id, (0, 0, 0)), "P")
        digest = sha256("presentation")
        self.assertFalse(
            backend.complete(
                replace(
                    request["ticket"],
                    target=second.stable_id,
                    spec_sha=second.spec_sha,
                ),
                digest,
            )
        )
        self.assertFalse(
            backend.complete(replace(request["ticket"], coord=(1, 0, 0)), digest)
        )
        self.assertTrue(backend.complete(request["ticket"], digest))
        self.assertFalse(second.chunks[(0, 0, 0)].ready["P"])

    def test_duplicate_completion_is_idempotent_but_conflict_rejects(self):
        backend = OutputBackendModel()
        backend.create("asteroid.red.one")
        request = backend.queue(backend.revision("asteroid.red.one"), "C")
        digest = sha256("collision")
        self.assertTrue(backend.complete(request["ticket"], digest))
        snapshot = copy.deepcopy(
            backend.volumes["asteroid.red.one"].chunks[(0, 0, 0)].__dict__
        )
        self.assertTrue(backend.complete(request["ticket"], digest))
        self.assertEqual(
            snapshot,
            backend.volumes["asteroid.red.one"].chunks[(0, 0, 0)].__dict__,
        )
        self.assertFalse(backend.complete(request["ticket"], sha256("conflict")))
        self.assertEqual(
            snapshot,
            backend.volumes["asteroid.red.one"].chunks[(0, 0, 0)].__dict__,
        )

    def test_immutable_request_snapshot_and_counter_overflow_fail_closed(self):
        backend = OutputBackendModel()
        volume = backend.create("asteroid.red.one")
        request = backend.queue(backend.revision(volume.stable_id), "P")
        original = request["cells"]
        volume.chunks[(0, 0, 0)].cells = b"different"
        self.assertEqual(request["cells"], original)
        backend = OutputBackendModel()
        backend.create("asteroid.red.one")
        backend.last_token = UINT64_MAX - 1
        before = copy.deepcopy(backend.volumes)
        self.assertIsNone(backend.queue(backend.revision("asteroid.red.one"), "P"))
        self.assertEqual(
            before["asteroid.red.one"].chunks[(0, 0, 0)].__dict__,
            backend.volumes["asteroid.red.one"].chunks[(0, 0, 0)].__dict__,
        )


if __name__ == "__main__":
    unittest.main()
