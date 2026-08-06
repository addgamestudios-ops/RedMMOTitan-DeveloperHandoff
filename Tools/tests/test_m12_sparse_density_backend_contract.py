import copy
import hashlib
import json
import math
import re
import unittest
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
HEADER = ROOT / "Source/RedMMO/Mining/RedInMemorySparseVoxelBackend.h"
CPP = ROOT / "Source/RedMMO/Mining/RedInMemorySparseVoxelBackend.cpp"
CONTRACT_HEADER = ROOT / "Source/RedMMO/Mining/RedVoxelMiningContracts.h"
CONTRACT_CPP = ROOT / "Source/RedMMO/Mining/RedVoxelMiningContracts.cpp"
INTERFACE = ROOT / "Source/RedMMO/Mining/RedVoxelAsteroidBackend.h"
BUILD_RULES = ROOT / "Source/RedMMO/RedMMO.Build.cs"
UPROJECT = ROOT / "Titan.uproject"

PROTOTYPE_TABLE = "red.material-table.prototype-v1"
MATERIALS = ("empty", "red.material.stone", "red.material.iron", "red.material.crystal")


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def strip_cpp_comments_and_literals(source: str) -> str:
    source = re.sub(r"//[^\n]*", "", source)
    source = re.sub(r"/\*.*?\*/", "", source, flags=re.S)
    source = re.sub(r'"(?:\\.|[^"\\])*"', '""', source)
    return source


def function_body(source: str, signature: str) -> str:
    start = source.index(signature)
    brace = source.index("{", start)
    depth = 0
    for index in range(brace, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[brace : index + 1]
    raise AssertionError(f"unterminated function: {signature}")


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def mix32(value: int) -> int:
    value &= 0xFFFFFFFF
    value ^= value >> 16
    value = (value * 0x7FEB352D) & 0xFFFFFFFF
    value ^= value >> 15
    value = (value * 0x846CA68B) & 0xFFFFFFFF
    value ^= value >> 16
    return value & 0xFFFFFFFF


@dataclass(frozen=True)
class Spec:
    stable_id: str = "asteroid.red.m12-test"
    material_table: str = PROTOTYPE_TABLE
    dims: tuple[int, int, int] = (16, 16, 16)
    chunk: tuple[int, int, int] = (8, 8, 8)
    cell_cm: float = 100.0
    seed: int = 0x1234ABCD
    generation: int = 1

    @property
    def fingerprint(self) -> str:
        payload = json.dumps(
            {
                "stable": self.stable_id,
                "table": self.material_table,
                "dims": self.dims,
                "chunk": self.chunk,
                "cell": self.cell_cm,
                "seed": self.seed,
                "generation": self.generation,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return sha(payload)


@dataclass
class Limits:
    max_edited: int = 2048
    max_dirty: int = 8
    max_yields: int = 4
    max_journal: int = 512
    max_checkpoint_chunks: int = 64
    max_compressed_chunk: int = 256 * 1024
    max_uncompressed_chunk: int = 64 * 1024
    max_checkpoint_bytes: int = 16 * 1024 * 1024


def linear(coord: tuple[int, int, int], dims: tuple[int, int, int]) -> int:
    x, y, z = coord
    return x + dims[0] * (y + dims[1] * z)


def base_material(spec: Spec, coord: tuple[int, int, int]) -> int:
    x, y, z = coord
    dx = 2 * x + 1 - spec.dims[0]
    dy = 2 * y + 1 - spec.dims[1]
    dz = 2 * z + 1 - spec.dims[2]
    radius = max(1, min(spec.dims) * 9 // 16)
    if dx * dx + dy * dy + dz * dz > radius * radius:
        return 0
    value = spec.seed
    value ^= (spec.generation * 0x9E3779B9) & 0xFFFFFFFF
    value ^= (x * 0x85EBCA6B) & 0xFFFFFFFF
    value ^= (y * 0xC2B2AE35) & 0xFFFFFFFF
    value ^= (z * 0x27D4EB2F) & 0xFFFFFFFF
    bucket = mix32(value) % 1000
    if bucket < 35:
        return 3
    if bucket < 130:
        return 2
    return 1


def base_cells(spec: Spec) -> bytearray:
    cells = bytearray(math.prod(spec.dims))
    for z in range(spec.dims[2]):
        for y in range(spec.dims[1]):
            for x in range(spec.dims[0]):
                cells[linear((x, y, z), spec.dims)] = base_material(spec, (x, y, z))
    return cells


def canonical_rle_encode(cells: bytes) -> bytes:
    if not cells:
        raise ValueError("empty")
    result = bytearray()
    cursor = 0
    while cursor < len(cells):
        value = cells[cursor]
        if value > 3:
            raise ValueError("material")
        run = 1
        while cursor + run < len(cells) and cells[cursor + run] == value and run < 65535:
            run += 1
        result.extend((run & 0xFF, run >> 8, value))
        cursor += run
    return bytes(result)


def canonical_rle_decode(payload: bytes, expected: int, compressed_cap=262144, raw_cap=65536) -> bytes:
    if not payload or len(payload) > compressed_cap or len(payload) % 3:
        raise ValueError("size")
    if expected <= 0 or expected > raw_cap:
        raise ValueError("expected")
    result = bytearray()
    for offset in range(0, len(payload), 3):
        run = payload[offset] | payload[offset + 1] << 8
        value = payload[offset + 2]
        if run <= 0 or value > 3 or run > expected - len(result):
            raise ValueError("run")
        result.extend([value] * run)
    if len(result) != expected:
        raise ValueError("length")
    if canonical_rle_encode(result) != payload:
        raise ValueError("noncanonical")
    return bytes(result)


class VolumeModel:
    def __init__(self, spec: Spec, limits: Limits | None = None):
        if spec.material_table != PROTOTYPE_TABLE:
            raise ValueError("table")
        self.spec = spec
        self.limits = limits or Limits()
        chunk_cells = math.prod(spec.chunk)
        chunk_count = math.prod(
            tuple(spec.dims[index] // spec.chunk[index] for index in range(3))
        )
        if (
            chunk_cells > self.limits.max_uncompressed_chunk
            or chunk_cells * 3 > self.limits.max_compressed_chunk
            or chunk_count * chunk_cells * 4 > self.limits.max_checkpoint_bytes
        ):
            raise ValueError("checkpoint capacity")
        self.cells = base_cells(spec)
        self.revision = 0
        self.generation = 1
        self.journal: list[dict] = []
        self.outputs: dict[tuple[int, int, int], dict] = {}
        self._reset_outputs()

    @property
    def chunk_counts(self):
        return tuple(self.spec.dims[i] // self.spec.chunk[i] for i in range(3))

    def chunk_coordinates(self):
        return sorted(
            (
                (x, y, z)
                for z in range(self.chunk_counts[2])
                for y in range(self.chunk_counts[1])
                for x in range(self.chunk_counts[0])
            )
        )

    def chunk_bytes(self, chunk_coord):
        result = bytearray()
        for lz in range(self.spec.chunk[2]):
            for ly in range(self.spec.chunk[1]):
                for lx in range(self.spec.chunk[0]):
                    global_coord = tuple(
                        chunk_coord[i] * self.spec.chunk[i] + (lx, ly, lz)[i]
                        for i in range(3)
                    )
                    result.append(self.cells[linear(global_coord, self.spec.dims)])
        return bytes(result)

    def chunk_hash(self, coord):
        prefix = (
            f"red.voxel-chunk-content.v1|spec={self.spec.fingerprint}"
            f"|chunk={coord[0]},{coord[1]},{coord[2]}|"
        ).encode()
        return sha(prefix + self.chunk_bytes(coord))

    def _reset_outputs(self):
        self.outputs = {
            coord: {
                "revision": self.revision,
                "sha": self.chunk_hash(coord),
                "generation": self.generation,
                "presentation": False,
                "collision": False,
                "queued": False,
            }
            for coord in self.chunk_coordinates()
        }

    def snapshot(self):
        return (
            bytes(self.cells),
            self.revision,
            self.generation,
            copy.deepcopy(self.journal),
            copy.deepcopy(self.outputs),
        )

    def apply(self, center, radius, expected=None, generation=None):
        before = self.snapshot()
        expected = self.revision if expected is None else expected
        generation = self.generation if generation is None else generation
        if expected != self.revision:
            return {"accepted": False, "reason": "stale", "before": before}
        if generation != self.generation:
            return {"accepted": False, "reason": "generation", "before": before}
        if len(self.journal) >= self.limits.max_journal:
            return {"accepted": False, "reason": "journal", "before": before}
        if not math.isfinite(radius) or radius <= 0 or any(not math.isfinite(v) for v in center):
            return {"accepted": False, "reason": "brush", "before": before}

        removed = []
        dirty = set()
        counts = [0, 0, 0, 0]
        for z in range(self.spec.dims[2]):
            for y in range(self.spec.dims[1]):
                for x in range(self.spec.dims[0]):
                    position = tuple(
                        ((x, y, z)[i] + 0.5 - self.spec.dims[i] * 0.5)
                        * self.spec.cell_cm
                        for i in range(3)
                    )
                    if sum((position[i] - center[i]) ** 2 for i in range(3)) > radius**2:
                        continue
                    index = linear((x, y, z), self.spec.dims)
                    material = self.cells[index]
                    if not material:
                        continue
                    removed.append(index)
                    counts[material] += 1
                    dirty.add(
                        tuple((x, y, z)[i] // self.spec.chunk[i] for i in range(3))
                    )
        if not removed:
            return {"accepted": False, "reason": "zero", "before": before}
        if len(removed) > self.limits.max_edited or len(dirty) > self.limits.max_dirty:
            return {"accepted": False, "reason": "cap", "before": before}
        yields = [
            (MATERIALS[material], counts[material])
            for material in (1, 2, 3)
            if counts[material]
        ]
        if len(yields) > self.limits.max_yields:
            return {"accepted": False, "reason": "yield", "before": before}

        for index in removed:
            self.cells[index] = 0
        self.revision += 1
        dirty = sorted(dirty)
        operation = {
            "revision": self.revision,
            "center": tuple(center),
            "radius": radius,
            "removed": len(removed),
            "dirty": dirty,
            "yields": yields,
        }
        operation["sha"] = sha(
            json.dumps(operation, sort_keys=True, separators=(",", ":")).encode()
        )
        self.journal.append(operation)
        for coord in dirty:
            self.outputs[coord] = {
                "revision": self.revision,
                "sha": self.chunk_hash(coord),
                "generation": self.generation,
                "presentation": False,
                "collision": False,
                "queued": False,
            }
        return {
            "accepted": True,
            "removed": len(removed),
            "dirty": dirty,
            "yields": yields,
            "revision": self.revision,
            "operation_sha": operation["sha"],
        }

    def capture(self):
        chunks = []
        for coord in self.chunk_coordinates():
            raw = self.chunk_bytes(coord)
            chunks.append(
                {
                    "coord": coord,
                    "through": self.revision,
                    "raw_count": len(raw),
                    "codec": "red.codec.rle-v1",
                    "payload": canonical_rle_encode(raw),
                    "sha": sha(raw),
                }
            )
        manifest_fields = [
            (
                chunk["coord"],
                chunk["through"],
                chunk["raw_count"],
                chunk["codec"],
                chunk["sha"],
            )
            for chunk in sorted(chunks, key=lambda chunk: chunk["coord"])
        ]
        manifest = {
            "spec": self.spec.fingerprint,
            "stable": self.spec.stable_id,
            "table": self.spec.material_table,
            "dims": self.spec.dims,
            "chunk": self.spec.chunk,
            "cell": self.spec.cell_cm,
            "seed": self.spec.seed,
            "generation_version": self.spec.generation,
            "through": self.revision,
            "limits": vars(self.limits),
            "chunks": manifest_fields,
        }
        return {
            "spec": self.spec,
            "limits": copy.deepcopy(self.limits),
            "through": self.revision,
            "chunks": chunks,
            "manifest": sha(
                json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
            ),
        }

    @staticmethod
    def inspect(checkpoint):
        spec = checkpoint["spec"]
        limits = checkpoint["limits"]
        if spec.material_table != PROTOTYPE_TABLE:
            raise ValueError("table")
        counts = tuple(spec.dims[i] // spec.chunk[i] for i in range(3))
        expected_coords = sorted(
            (x, y, z)
            for x in range(counts[0])
            for y in range(counts[1])
            for z in range(counts[2])
        )
        if len(checkpoint["chunks"]) != math.prod(counts):
            raise ValueError("chunk count")
        if len(checkpoint["chunks"]) > limits.max_checkpoint_chunks:
            raise ValueError("chunk cap")
        seen = set()
        verification = []
        stored_bytes = 0
        removed_cells = 0
        full = bytearray(math.prod(spec.dims))
        manifest_fields = []
        for chunk in checkpoint["chunks"]:
            coord = tuple(chunk["coord"])
            if coord not in expected_coords or coord in seen:
                raise ValueError("coord")
            seen.add(coord)
            if chunk["through"] != checkpoint["through"]:
                raise ValueError("revision")
            raw = canonical_rle_decode(
                chunk["payload"],
                math.prod(spec.chunk),
                limits.max_compressed_chunk,
                limits.max_uncompressed_chunk,
            )
            if sha(raw) != chunk["sha"]:
                raise ValueError("payload hash")
            stored_bytes += len(raw) + len(chunk["payload"])
            if stored_bytes > limits.max_checkpoint_bytes:
                raise ValueError("aggregate")
            cursor = 0
            for lz in range(spec.chunk[2]):
                for ly in range(spec.chunk[1]):
                    for lx in range(spec.chunk[0]):
                        global_coord = tuple(
                            coord[i] * spec.chunk[i] + (lx, ly, lz)[i]
                            for i in range(3)
                        )
                        value = raw[cursor]
                        base = base_material(spec, global_coord)
                        if value not in ((base,) if base == 0 else (0, base)):
                            raise ValueError("material injection")
                        if base and not value:
                            removed_cells += 1
                        full[linear(global_coord, spec.dims)] = value
                        cursor += 1
            verification.append((coord, len(raw), sha(raw)))
            manifest_fields.append(
                (
                    coord,
                    chunk["through"],
                    len(raw),
                    chunk["codec"],
                    sha(raw),
                )
            )
        if sorted(seen) != expected_coords:
            raise ValueError("manifest coverage")
        max_removed = checkpoint["through"] * limits.max_edited
        if (
            checkpoint["through"] == 0
            and removed_cells
            or checkpoint["through"] > 0
            and not checkpoint["through"] <= removed_cells <= max_removed
        ):
            raise ValueError("revision plausibility")
        manifest = {
            "spec": spec.fingerprint,
            "stable": spec.stable_id,
            "table": spec.material_table,
            "dims": spec.dims,
            "chunk": spec.chunk,
            "cell": spec.cell_cm,
            "seed": spec.seed,
            "generation_version": spec.generation,
            "through": checkpoint["through"],
            "limits": vars(limits),
            "chunks": sorted(manifest_fields),
        }
        manifest_hash = sha(
            json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
        )
        if manifest_hash != checkpoint["manifest"]:
            raise ValueError("manifest")
        return {
            "manifest": manifest_hash,
            "chunks": sorted(verification),
            "cells": bytes(full),
        }

    def restore(self, checkpoint, supplied_verification, expected_revision, expected_generation):
        before = self.snapshot()
        trusted = self.inspect(checkpoint)
        if supplied_verification != trusted:
            raise ValueError("forged verification")
        if expected_revision != self.revision or expected_generation != self.generation:
            raise ValueError("cas")
        if checkpoint["through"] < self.revision:
            raise ValueError("rollback")
        if checkpoint["through"] == self.revision and checkpoint["manifest"] != self.capture()["manifest"]:
            raise ValueError("equivocation")
        newly_removed = 0
        for live, candidate in zip(self.cells, trusted["cells"]):
            if live == 0 and candidate != 0:
                raise ValueError("material restoration")
            if live != 0 and candidate == 0:
                newly_removed += 1
        revision_delta = checkpoint["through"] - self.revision
        if (
            revision_delta == 0
            and newly_removed
            or revision_delta > 0
            and not (
                revision_delta
                <= newly_removed
                <= revision_delta * self.limits.max_edited
            )
        ):
            raise ValueError("revision delta")
        if self.generation >= (1 << 64) - 2:
            raise ValueError("generation")
        candidate_cells = bytearray(trusted["cells"])
        self.cells = candidate_cells
        self.revision = checkpoint["through"]
        self.generation += 1
        self.journal = []
        self._reset_outputs()
        return before

    def queue(self, coord, revision, content_sha, generation):
        state = self.outputs[coord]
        if (
            revision != state["revision"]
            or content_sha != state["sha"]
            or generation != self.generation
        ):
            return False
        state["queued"] = True
        state["presentation"] = False
        state["collision"] = False
        return True


class SparseDensityBackendContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.header = read(HEADER)
        cls.cpp = read(CPP)
        cls.contract_header = read(CONTRACT_HEADER)
        cls.contract_cpp = read(CONTRACT_CPP)

    def test_backend_is_plain_project_owned_complete_and_bounded(self):
        for token in (
            "class REDMMO_API FRedInMemorySparseVoxelBackend final",
            "public IRedVoxelAsteroidBackend",
            "class FImpl;",
            "TUniquePtr<FImpl> Impl",
            "PrototypeMaterialTableId",
            "MaxEditedCellsPerRequest",
            "MaxDirtyChunksPerEdit",
            "MaxJournalOperationsPerCheckpoint",
            "MaxCheckpointSetBytes",
            "ComputeCanonicalSha256(",
            "HashChunkContent(",
            "WorstCaseCompressedChunkBytes",
            "WorstCaseCheckpointBytes",
        ):
            self.assertIn(token, self.header + self.cpp)
        for method in (
            "InitializeVolume",
            "HasVolume",
            "GetCurrentRevision",
            "GetAuthorityGenerationToken",
            "ApplyValidatedEdit",
            "ReadChunkRevision",
            "CaptureCheckpointSet",
            "InspectCheckpointSet",
            "RestoreCheckpointSetAtomically",
            "QueueChunkRebuild",
            "CompleteChunkRebuild",
            "QueryGeneratedOutputState",
            "InvalidateBuildsOlderThan",
            "ReleaseVolume",
        ):
            self.assertIn(method + "(", self.header)
            self.assertIn(
                f"FRedInMemorySparseVoxelBackend::{method}(",
                self.cpp,
            )
        for forbidden in (
            "UCLASS",
            "USTRUCT",
            "UFUNCTION",
            "AActor",
            "UObject",
            "SpawnActor",
            "DOREPLIFETIME",
            "Server, Reliable",
            "Inventory",
            "ARedResourcePickup",
            "DynamicMesh",
            "ProceduralMesh",
            "VoxelWorld",
            "FMath::Rand",
            "GetTypeHash(",
        ):
            self.assertNotIn(forbidden, self.header + self.cpp)

    def test_initialize_validates_builds_locally_then_commits(self):
        body = function_body(
            self.cpp,
            "bool FRedInMemorySparseVoxelBackend::InitializeVolume",
        )
        for token in (
            "ValidateSupportedSpec(Spec, Limits, OutError)",
            "FStoredVolume Candidate",
            "GenerateCellMaterial(Spec, GlobalCell)",
            "HashChunkContent(",
            "Candidate.NonEmptyChunks.Add",
            "Impl->Volumes.Add(Spec.StableId, MoveTemp(Candidate))",
            "Candidate.CurrentRevision = 0",
            "LastIssuedGenerationTokens.FindRef(Spec.StableId)",
            "Candidate.AuthorityGenerationToken = NewGenerationToken",
            "LastIssuedGenerationTokens.Add(",
        ):
            self.assertIn(token, body)
        self.assertLess(body.index("ValidateSupportedSpec"), body.index("FStoredVolume Candidate"))
        self.assertLess(body.index("HashChunkContent"), body.index("Impl->Volumes.Add"))

    def test_apply_source_is_two_phase_and_result_validated_before_commit(self):
        body = function_body(
            self.cpp,
            "bool FRedInMemorySparseVoxelBackend::ApplyValidatedEdit",
        )
        for token in (
            "TMap<int32, TArray<uint8>> CandidateChunks",
            "TSet<int32> DirtyChunkIndices",
            "RemovedCellCount",
            "CandidateChunkHashes",
            "ValidateApplyResult(",
            "BuildEditContentSha256(",
            "Commit begins only after",
            "Volume->CurrentRevision = AppliedRevision",
            "Volume->Journal.Add",
            "JournalCapacityReached",
        ):
            self.assertIn(token, body)
        self.assertLess(body.index("ValidateApplyResult("), body.index("Commit begins only after"))
        self.assertLess(body.index("BuildEditContentSha256("), body.index("Commit begins only after"))

    def test_checkpoint_restore_source_reinspects_and_swaps_whole_state(self):
        inspect_body = function_body(
            self.cpp,
            "bool FRedInMemorySparseVoxelBackend::InspectCheckpointSet",
        )
        restore = function_body(
            self.cpp,
            "bool FRedInMemorySparseVoxelBackend::RestoreCheckpointSetAtomically",
        )
        for token in (
            "DecodeCanonicalRle(",
            "ValidateChunkCellsAgainstBase(",
            "BuildManifestSha256(",
            "ValidateVolumeCheckpoint(",
        ):
            self.assertIn(token, inspect_body)
        for token in (
            "FVolumeCheckpointVerification TrustedVerification",
            "InspectCheckpointSet(",
            "VerificationsEquivalent(",
            "ValidateCheckpointRestorePrecondition(",
            "equal-revision checkpoint content",
            "DecodeCheckpointToTemporaryState(",
            "ValidateSubtractiveReplacement(",
            "FStoredVolume Candidate",
            "final game-thread commit block",
            "Impl->Volumes.Add(",
            "Impl->LastIssuedGenerationTokens.Add(",
        ):
            self.assertIn(token, restore)
        self.assertLess(restore.index("InspectCheckpointSet("), restore.index("Impl->Volumes.Add("))
        self.assertLess(
            restore.index("DecodeCheckpointToTemporaryState("),
            restore.index("Impl->Volumes.Add("),
        )

    def test_backend_remains_unwired(self):
        admitted = {
            HEADER.resolve(),
            CPP.resolve(),
            CONTRACT_HEADER.resolve(),
            CONTRACT_CPP.resolve(),
            INTERFACE.resolve(),
            (
                ROOT
                / "Source/RedMMO/Mining/RedInMemorySparseVoxelBackendTests.cpp"
            ).resolve(),
        }
        for path in (ROOT / "Source/RedMMO").rglob("*"):
            if path.suffix.lower() not in (".h", ".cpp") or path.resolve() in admitted:
                continue
            source = strip_cpp_comments_and_literals(read(path))
            for forbidden in (
                "RedInMemorySparseVoxelBackend",
                "IRedVoxelAsteroidBackend",
                "RedVoxelMiningContracts",
            ):
                self.assertNotIn(forbidden, source, str(path))
        self.assertFalse((ROOT / "Content/RedMMO/Maps/Tests/RedVoxelAsteroid_M12.umap").exists())
        self.assertNotIn('"Voxel"', read(BUILD_RULES))
        voxel = [
            item
            for item in json.loads(read(UPROJECT))["Plugins"]
            if item.get("Name") == "Voxel"
        ]
        self.assertEqual(voxel, [{"Name": "Voxel", "Enabled": False}])

    def test_deterministic_base_generation_and_seed_separation(self):
        spec = Spec()
        first = VolumeModel(spec)
        second = VolumeModel(spec)
        self.assertEqual(first.snapshot(), second.snapshot())
        self.assertEqual(first.capture(), second.capture())
        seeded = VolumeModel(Spec(seed=spec.seed + 1))
        versioned = VolumeModel(Spec(generation=spec.generation + 1))
        self.assertNotEqual(bytes(first.cells), bytes(seeded.cells))
        self.assertNotEqual(bytes(first.cells), bytes(versioned.cells))
        self.assertNotIn("FMath::Rand", self.cpp)
        self.assertIn("MixDeterministic32", self.cpp)

    def test_accepted_brush_has_exact_yield_revision_and_dirty_chunks(self):
        volume = VolumeModel(Spec())
        before_hashes = {coord: volume.chunk_hash(coord) for coord in volume.chunk_coordinates()}
        result = volume.apply((0.0, 0.0, 0.0), 260.0)
        self.assertTrue(result["accepted"])
        self.assertEqual(result["revision"], 1)
        self.assertEqual(sum(count for _, count in result["yields"]), result["removed"])
        self.assertEqual(result["dirty"], sorted(set(result["dirty"])))
        self.assertTrue(all(material in MATERIALS[1:] for material, _ in result["yields"]))
        self.assertEqual(len({material for material, _ in result["yields"]}), len(result["yields"]))
        for coord in volume.chunk_coordinates():
            if coord not in result["dirty"]:
                self.assertEqual(volume.chunk_hash(coord), before_hashes[coord])
        cell_volume = volume.spec.cell_cm**3
        self.assertEqual(
            sum(count * cell_volume for _, count in result["yields"]),
            result["removed"] * cell_volume,
        )

    def test_zero_volume_and_repeated_brush_are_idempotent_rejections(self):
        volume = VolumeModel(Spec())
        self.assertTrue(volume.apply((0.0, 0.0, 0.0), 260.0)["accepted"])
        before = volume.snapshot()
        repeated = volume.apply((0.0, 0.0, 0.0), 260.0)
        self.assertFalse(repeated["accepted"])
        self.assertEqual(repeated["reason"], "zero")
        self.assertEqual(volume.snapshot(), before)
        outside = volume.apply((100000.0, 0.0, 0.0), 100.0)
        self.assertFalse(outside["accepted"])
        self.assertEqual(volume.snapshot(), before)

    def test_every_rejection_path_is_atomic(self):
        cases = [
            lambda v: v.apply((0, 0, 0), 260, expected=99),
            lambda v: v.apply((0, 0, 0), 260, generation=99),
            lambda v: v.apply((0, 0, 0), float("nan")),
            lambda v: v.apply((float("nan"), 0, 0), 100),
            lambda v: v.apply((100000, 0, 0), 100),
        ]
        for case in cases:
            with self.subTest(case=case):
                volume = VolumeModel(Spec())
                before = volume.snapshot()
                result = case(volume)
                self.assertFalse(result["accepted"])
                self.assertEqual(volume.snapshot(), before)
        capped = VolumeModel(Spec(), Limits(max_edited=1))
        before = capped.snapshot()
        self.assertFalse(capped.apply((0, 0, 0), 260)["accepted"])
        self.assertEqual(capped.snapshot(), before)
        dirty_capped = VolumeModel(Spec(), Limits(max_dirty=1))
        before = dirty_capped.snapshot()
        self.assertFalse(dirty_capped.apply((0, 0, 0), 260)["accepted"])
        self.assertEqual(dirty_capped.snapshot(), before)

    def test_journal_ceiling_fails_closed(self):
        volume = VolumeModel(Spec(), Limits(max_journal=1))
        first = volume.apply((-300.0, 0.0, 0.0), 180.0)
        self.assertTrue(first["accepted"])
        before = volume.snapshot()
        blocked = volume.apply((300.0, 0.0, 0.0), 180.0)
        self.assertFalse(blocked["accepted"])
        self.assertEqual(blocked["reason"], "journal")
        self.assertEqual(volume.snapshot(), before)
        self.assertEqual(len(volume.journal), 1)

    def test_ordered_replay_reconstructs_exact_state(self):
        operations = [
            ((-300.0, 0.0, 0.0), 180.0),
            ((300.0, 0.0, 0.0), 180.0),
            ((0.0, 300.0, 0.0), 180.0),
        ]
        left = VolumeModel(Spec())
        right = VolumeModel(Spec())
        left_results = [left.apply(*operation) for operation in operations]
        right_results = [right.apply(*operation) for operation in operations]
        self.assertEqual(left_results, right_results)
        self.assertEqual(left.snapshot(), right.snapshot())
        self.assertEqual(left.capture(), right.capture())

    def test_rle_roundtrip_is_canonical_and_bounded(self):
        samples = (
            bytes([0] * 512),
            bytes([1] * 300 + [2] * 212),
            bytes(index % 4 for index in range(512)),
            bytes([1, 1, 0, 0, 0, 3, 2, 2] * 64),
        )
        for sample in samples:
            with self.subTest(prefix=sample[:8]):
                encoded = canonical_rle_encode(sample)
                self.assertEqual(canonical_rle_decode(encoded, len(sample)), sample)
                self.assertEqual(canonical_rle_encode(sample), encoded)
        malformed = (
            b"",
            b"\x00\x00\x01",
            b"\x01\x00",
            b"\xff\xff\x01",
            b"\x01\x00\x04",
            b"\x01\x00\x01\x01\x00\x01",
        )
        for payload in malformed:
            with self.subTest(payload=payload):
                with self.assertRaises(ValueError):
                    canonical_rle_decode(payload, 2)

    def test_checkpoint_capture_is_complete_and_deterministic(self):
        volume = VolumeModel(Spec())
        volume.apply((0.0, 0.0, 0.0), 260.0)
        first = volume.capture()
        second = volume.capture()
        self.assertEqual(first, second)
        expected_count = math.prod(volume.chunk_counts)
        self.assertEqual(len(first["chunks"]), expected_count)
        self.assertEqual(
            sorted(chunk["coord"] for chunk in first["chunks"]),
            volume.chunk_coordinates(),
        )
        self.assertEqual({chunk["through"] for chunk in first["chunks"]}, {volume.revision})
        verification = volume.inspect(first)
        self.assertEqual(verification["manifest"], first["manifest"])

    def test_checkpoint_corruption_and_stale_verification_fail_closed(self):
        volume = VolumeModel(Spec())
        checkpoint = volume.capture()
        valid = volume.inspect(checkpoint)
        corruptions = []
        flipped = copy.deepcopy(checkpoint)
        payload = bytearray(flipped["chunks"][0]["payload"])
        payload[-1] ^= 1
        flipped["chunks"][0]["payload"] = bytes(payload)
        corruptions.append(flipped)
        truncated = copy.deepcopy(checkpoint)
        truncated["chunks"][0]["payload"] = truncated["chunks"][0]["payload"][:-1]
        corruptions.append(truncated)
        duplicate = copy.deepcopy(checkpoint)
        duplicate["chunks"][1]["coord"] = duplicate["chunks"][0]["coord"]
        corruptions.append(duplicate)
        manifest = copy.deepcopy(checkpoint)
        manifest["manifest"] = "0" * 64
        corruptions.append(manifest)
        injected = copy.deepcopy(checkpoint)
        raw = bytearray(
            canonical_rle_decode(
                injected["chunks"][0]["payload"],
                math.prod(volume.spec.chunk),
            )
        )
        raw[0] = 3
        injected["chunks"][0]["payload"] = canonical_rle_encode(raw)
        injected["chunks"][0]["sha"] = sha(raw)
        corruptions.append(injected)
        revision_zero_deletion = VolumeModel(Spec())
        first_solid = next(
            index
            for index, value in enumerate(revision_zero_deletion.cells)
            if value
        )
        revision_zero_deletion.cells[first_solid] = 0
        revision_zero_deletion._reset_outputs()
        corruptions.append(revision_zero_deletion.capture())
        over_cap_deletion = VolumeModel(Spec(), Limits(max_edited=1))
        solid_indices = [
            index
            for index, value in enumerate(over_cap_deletion.cells)
            if value
        ][:2]
        for index in solid_indices:
            over_cap_deletion.cells[index] = 0
        over_cap_deletion.revision = 1
        over_cap_deletion._reset_outputs()
        corruptions.append(over_cap_deletion.capture())
        for corrupted in corruptions:
            with self.subTest(kind=id(corrupted)):
                before = volume.snapshot()
                with self.assertRaises(ValueError):
                    volume.inspect(corrupted)
                self.assertEqual(volume.snapshot(), before)
        forged = copy.deepcopy(valid)
        forged["manifest"] = "F" * 64
        with self.assertRaises(ValueError):
            volume.restore(
                checkpoint,
                forged,
                volume.revision,
                volume.generation,
            )
        for impossible_limits in (
            Limits(max_uncompressed_chunk=1),
            Limits(max_compressed_chunk=1),
            Limits(max_checkpoint_bytes=1),
        ):
            with self.subTest(impossible_limits=impossible_limits):
                with self.assertRaises(ValueError):
                    VolumeModel(Spec(), impossible_limits)

    def test_whole_volume_restore_obeys_cas_no_rollback_and_generation(self):
        source = VolumeModel(Spec())
        source.apply((0.0, 0.0, 0.0), 260.0)
        checkpoint = source.capture()
        verification = source.inspect(checkpoint)

        target = VolumeModel(Spec())
        with self.assertRaises(ValueError):
            target.restore(checkpoint, verification, 99, target.generation)
        before = target.snapshot()
        target.restore(
            checkpoint,
            verification,
            target.revision,
            target.generation,
        )
        self.assertEqual(bytes(target.cells), verification["cells"])
        self.assertEqual(target.revision, checkpoint["through"])
        self.assertEqual(target.generation, before[2] + 1)
        self.assertEqual(target.journal, [])
        self.assertTrue(
            all(
                not state["presentation"] and not state["collision"]
                for state in target.outputs.values()
            )
        )
        old = VolumeModel(Spec()).capture()
        with self.assertRaises(ValueError):
            target.restore(old, VolumeModel.inspect(old), target.revision, target.generation)

        live = VolumeModel(Spec())
        self.assertTrue(live.apply((-300.0, 0.0, 0.0), 180.0)["accepted"])
        unrelated = VolumeModel(Spec())
        self.assertTrue(unrelated.apply((300.0, 0.0, 0.0), 180.0)["accepted"])
        self.assertTrue(unrelated.apply((0.0, 300.0, 0.0), 180.0)["accepted"])
        unrelated_checkpoint = unrelated.capture()
        with self.assertRaises(ValueError):
            live.restore(
                unrelated_checkpoint,
                unrelated.inspect(unrelated_checkpoint),
                live.revision,
                live.generation,
            )

        absent_cells = VolumeModel.inspect(checkpoint)["cells"]
        initialized = VolumeModel(checkpoint["spec"], checkpoint["limits"])
        initialized.cells = bytearray(absent_cells)
        initialized.revision = checkpoint["through"]
        initialized.generation = 1
        initialized.journal = []
        initialized._reset_outputs()
        self.assertEqual(bytes(initialized.cells), verification["cells"])
        self.assertEqual(initialized.generation, 1)

    def test_generated_output_and_release_lifecycle_rejects_stale_work(self):
        volume = VolumeModel(Spec())
        coord = volume.chunk_coordinates()[0]
        current = copy.deepcopy(volume.outputs[coord])
        self.assertFalse(volume.queue(coord, current["revision"] + 1, current["sha"], 1))
        self.assertFalse(volume.queue(coord, current["revision"], "0" * 64, 1))
        self.assertFalse(volume.queue(coord, current["revision"], current["sha"], 2))
        self.assertTrue(volume.queue(coord, current["revision"], current["sha"], 1))
        self.assertFalse(volume.outputs[coord]["presentation"])
        self.assertFalse(volume.outputs[coord]["collision"])
        volume.apply((0.0, 0.0, 0.0), 260.0)
        self.assertFalse(volume.queue(coord, current["revision"], current["sha"], 1))
        registry = {"asteroid.red.first": volume}
        generation_tombstones = {"asteroid.red.first": volume.generation}

        def release(expected_generation: int) -> bool:
            live = registry.get("asteroid.red.first")
            if (
                live is None
                or expected_generation == 0
                or live.generation != expected_generation
            ):
                return False
            del registry["asteroid.red.first"]
            return True

        first_generation = volume.generation
        self.assertFalse(release(0))
        self.assertTrue(release(first_generation))
        recreated = VolumeModel(Spec(stable_id="asteroid.red.first"))
        recreated.generation = generation_tombstones["asteroid.red.first"] + 1
        recreated._reset_outputs()
        registry["asteroid.red.first"] = recreated
        self.assertGreater(recreated.generation, current["generation"])
        self.assertFalse(release(first_generation))
        self.assertIs(registry["asteroid.red.first"], recreated)
        self.assertFalse(
            recreated.queue(
                coord,
                current["revision"],
                current["sha"],
                current["generation"],
            )
        )
        release = function_body(
            self.cpp,
            "bool FRedInMemorySparseVoxelBackend::ReleaseVolume",
        )
        for token in (
            "RequireGameThread(OutError)",
            "ExpectedAuthorityGenerationToken == 0",
            "Impl->Volumes.Find(StableId)",
            (
                "Volume->AuthorityGenerationToken"
                "\n\t\t!= ExpectedAuthorityGenerationToken"
            ),
            "Impl->Volumes.Remove(StableId)",
            "RemovedCount != 1",
            "OutError.Reset()",
            "return true",
        ):
            self.assertIn(token, release)
        require_thread = release.index("RequireGameThread(OutError)")
        reject_zero = release.index(
            "ExpectedAuthorityGenerationToken == 0"
        )
        find_live = release.index("Impl->Volumes.Find(StableId)")
        reject_missing = release.index("if (!Volume)")
        compare_generation = release.index(
            "Volume->AuthorityGenerationToken"
        )
        remove_live = release.index("Impl->Volumes.Remove(StableId)")
        clear_error = release.index("OutError.Reset()")
        success = release.rindex("return true")
        self.assertLess(require_thread, reject_zero)
        self.assertLess(reject_zero, find_live)
        self.assertLess(find_live, reject_missing)
        self.assertLess(reject_missing, compare_generation)
        self.assertLess(compare_generation, remove_live)
        self.assertLess(remove_live, clear_error)
        self.assertLess(clear_error, success)
        self.assertEqual(
            release.count("Impl->Volumes.Remove(StableId)"),
            1,
        )
        self.assertRegex(
            self.header,
            r"virtual bool ReleaseVolume\(\s*FName StableId,\s*"
            r"uint64 ExpectedAuthorityGenerationToken,\s*"
            r"FString& OutError\) override;",
        )
        self.assertNotIn("LastIssuedGenerationTokens.Remove", release)
        self.assertIn("LastIssuedGenerationTokens", self.cpp)


if __name__ == "__main__":
    unittest.main()
