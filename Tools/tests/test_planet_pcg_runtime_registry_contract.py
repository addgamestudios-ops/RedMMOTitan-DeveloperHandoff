import hashlib
import json
import math
import re
import unittest
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DATASET = ROOT / "docs" / "PLANET_50KM_PCG_RESERVATIONS.json"
REGISTRY_HEADER = (
    ROOT
    / "Source"
    / "RedMMO"
    / "WorldAuthoring"
    / "RedPlanetHubReservationRegistry.h"
)
REGISTRY_CPP = REGISTRY_HEADER.with_suffix(".cpp")
REGISTRY_AUTOMATION_TEST = REGISTRY_HEADER.with_name(
    "RedPlanetHubReservationRegistryTests.cpp"
)
PROTECTED_MAP = ROOT / "Content" / "RedMMO" / "Maps" / "RedPlanetGen_50km_Test.umap"
PROJECT_FILE = ROOT / "Titan.uproject"
DEFAULT_ENGINE = ROOT / "Config" / "DefaultEngine.ini"
GAME_MODE_HEADER = ROOT / "Source" / "RedMMO" / "RedGameMode.h"
FOLIAGE_HEADER = ROOT / "Source" / "RedMMO" / "RedFoliageField.h"
PALETTE_HEADER = (
    ROOT / "Source" / "RedMMO" / "WorldAuthoring" / "RedWorldAssetPalette.h"
)
BUILD_RULES = ROOT / "Source" / "RedMMO" / "RedMMO.Build.cs"
GRAVITY_HEADER = ROOT / "Source" / "RedMMO" / "RedGravityBodies.h"
GRAVITY_CPP = GRAVITY_HEADER.with_suffix(".cpp")
FRAME_REGISTRY_HEADER = ROOT / "Source" / "RedMMO" / "RedCelestialFrameRegistry.h"
FRAME_REGISTRY_CPP = FRAME_REGISTRY_HEADER.with_suffix(".cpp")

EXPECTED_DATASET_FILE_SHA256 = "8E2952B8CB6530019BD9D1FFCAB526FB483B448B2B8D48164CCD10D00A78EDA8"
EXPECTED_RESERVATION_SHA256 = "D6DE83918473FFD5D8E27AF5502A39A1E25B3370F7D837F62C831A302F66F3B5"
EXPECTED_PROTECTED_MAP_SHA256 = "DA5987012EEB8F550254F5FCF0F47F42B8F5E03428CF4881C83D8687537F6E7D"


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def mask_cpp_comments_and_literals(text: str) -> str:
    masked = list(text)

    def blank(start: int, end: int) -> None:
        for index in range(start, min(end, len(masked))):
            if masked[index] not in "\r\n":
                masked[index] = " "

    cursor = 0
    while cursor < len(text):
        if text.startswith("//", cursor):
            end = text.find("\n", cursor + 2)
            end = len(text) if end < 0 else end
            blank(cursor, end)
            cursor = end
            continue
        if text.startswith("/*", cursor):
            closing = text.find("*/", cursor + 2)
            end = len(text) if closing < 0 else closing + 2
            blank(cursor, end)
            cursor = end
            continue
        if text.startswith('R"', cursor):
            delimiter_end = text.find("(", cursor + 2)
            line_end = text.find("\n", cursor + 2)
            if delimiter_end >= 0 and (line_end < 0 or delimiter_end < line_end):
                delimiter = text[cursor + 2 : delimiter_end]
                if len(delimiter) <= 16:
                    closing_token = ")" + delimiter + '"'
                    closing = text.find(closing_token, delimiter_end + 1)
                    end = (
                        len(text)
                        if closing < 0
                        else closing + len(closing_token)
                    )
                    blank(cursor, end)
                    cursor = end
                    continue
        if text[cursor] in ('"', "'"):
            quote = text[cursor]
            end = cursor + 1
            while end < len(text):
                if text[end] == "\\":
                    end += 2
                    continue
                end += 1
                if text[end - 1] == quote:
                    break
            blank(cursor, end)
            cursor = end
            continue
        cursor += 1
    return "".join(masked)


def find_function_calls(text: str, identifier: str) -> list[tuple[int, int, int]]:
    masked = mask_cpp_comments_and_literals(text)
    calls = []
    start = 0
    identifier_pattern = re.compile(
        rf"(?<![A-Za-z0-9_]){re.escape(identifier)}(?![A-Za-z0-9_])"
    )
    while True:
        match = identifier_pattern.search(masked, start)
        if match is None:
            return calls
        call = match.start()
        cursor = match.end()
        while cursor < len(masked) and masked[cursor].isspace():
            cursor += 1
        if cursor >= len(masked) or masked[cursor] != "(":
            start = match.end()
            continue
        cursor += 1
        depth = 1
        commas = 0
        has_argument = False
        while cursor < len(masked) and depth:
            char = masked[cursor]
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
            elif char == "," and depth == 1:
                commas += 1
            elif not char.isspace() and depth == 1:
                has_argument = True
            cursor += 1
        if depth:
            raise ValueError(f"unterminated call identifier: {identifier}")
        calls.append((commas + 1 if has_argument else 0, call, cursor))
        start = cursor


def find_function_call_arities(text: str, identifier: str) -> list[int]:
    return [arity for arity, _, _ in find_function_calls(text, identifier)]


def normalize_function_call(text: str) -> str:
    return re.sub(r"\s+", "", text)


def find_cpp_if_guard_bounds(text: str, condition: str) -> tuple[int, int]:
    masked = mask_cpp_comments_and_literals(text)
    directive_pattern = re.compile(
        r"(?m)^[ \t]*#[ \t]*(if|ifdef|ifndef|elif|else|endif)\b([^\r\n]*)"
    )
    directives = list(directive_pattern.finditer(masked))
    normalized_condition = re.sub(r"\s+", "", condition)
    matching_guards = [
        directive
        for directive in directives
        if directive.group(1) == "if"
        and re.sub(r"\s+", "", directive.group(2)) == normalized_condition
    ]
    if len(matching_guards) != 1:
        raise ValueError(
            f"expected exactly one #if guard for {condition!r}, "
            f"found {len(matching_guards)}"
        )

    guard = matching_guards[0]
    depth = 0
    inside_guard = False
    for directive in directives:
        if directive.start() == guard.start():
            inside_guard = True
        if not inside_guard:
            continue
        if directive.group(1) in ("if", "ifdef", "ifndef"):
            depth += 1
        elif directive.group(1) in ("elif", "else") and depth == 1:
            return guard.end(), directive.start()
        elif directive.group(1) == "endif":
            depth -= 1
            if depth == 0:
                return guard.end(), directive.start()
    raise ValueError(f"unterminated #if guard for {condition!r}")


class PlanetPcgRuntimeRegistryContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.document = json.loads(DATASET.read_text(encoding="utf-8"))
        cls.header = REGISTRY_HEADER.read_text(encoding="utf-8-sig")
        cls.source = REGISTRY_CPP.read_text(encoding="utf-8-sig")
        cls.automation_test = REGISTRY_AUTOMATION_TEST.read_text(
            encoding="utf-8-sig"
        )
        cls.frame_header = FRAME_REGISTRY_HEADER.read_text(encoding="utf-8-sig")
        cls.frame_source = FRAME_REGISTRY_CPP.read_text(encoding="utf-8-sig")

    def test_frozen_bindings_match_every_authenticated_record_field(self):
        table_start = self.source.index(
            "// BEGIN GENERATED AUTHENTICATED RESERVATION BINDINGS"
        )
        table_end = self.source.index(
            "// END GENERATED AUTHENTICATED RESERVATION BINDINGS", table_start
        )
        row_pattern = re.compile(
            r"\{\s*(\d+),\s*(\d+)u,\s*ERegionArchetype::(\w+),\s*"
            r"([-+0-9.eE]+),\s*([-+0-9.eE]+),\s*([-+0-9.eE]+),\s*"
            r"([-+0-9.eE]+),\s*([-+0-9.eE]+),\s*([-+0-9.eE]+),\s*"
            r'TEXT\("([^"]+)"\),\s*TEXT\("([^"]+)"\),\s*'
            r'TEXT\("([^"]+)"\)\s*\}',
        )
        rows = row_pattern.findall(self.source[table_start:table_end])
        self.assertEqual(len(rows), 27)
        for row, expected in zip(rows, self.document["reservations"], strict=True):
            self.assertEqual(int(row[0]), expected["region_index"])
            self.assertEqual(int(row[1]), expected["stable_seed"])
            self.assertEqual(row[2], expected["archetype"])
            for actual, expected_value in zip(
                (float(value) for value in row[3:6]),
                expected["center_direction"],
                strict=True,
            ):
                self.assertAlmostEqual(actual, expected_value, delta=1.0e-15)
            self.assertEqual(float(row[6]), expected["suggested_hub_radius_cm"])
            self.assertEqual(float(row[7]), expected["protected_radius_cm"])
            self.assertEqual(float(row[8]), expected["blend_radius_cm"])
            self.assertEqual(row[9], expected["reservation_id"])
            self.assertEqual(row[10], expected["stable_guid"])
            self.assertEqual(row[11], expected["source_patch"])

        self.assertIn(EXPECTED_RESERVATION_SHA256, self.source)
        self.assertEqual(len({row[10] for row in rows}), 27)

    def test_runtime_records_authenticate_service_and_expose_stable_identity(self):
        self.assertIn('TEXT("planet.red.mars")', self.source)
        self.assertIn("FPlanetRegionService::Get().GetRegions()", self.source)
        self.assertIn("FPlanet50KmProfile::RegionCount", self.source)
        self.assertIn("FPlanet50KmProfile::RadiusCm", self.source)
        self.assertIn("Metadata.StableSeed", self.source)
        self.assertIn("Metadata.UnitSite", self.source)
        self.assertIn("Metadata.SuggestedFlattenCoreRadiusCm", self.source)
        self.assertIn("Metadata.SuggestedFlattenBlendRadiusCm", self.source)
        self.assertIn("bool IsAuthenticatedLayout()", self.source)
        self.assertIn("if (!IsAuthenticatedLayout())", self.source)
        self.assertGreaterEqual(self.source.count("GetAuthenticatedReservations()"), 5)
        self.assertIn('TEXT("planet.red.mars.authoring-region.r%02d")', self.source)
        self.assertIn("FName AuthoringRegionId", self.header)
        self.assertIn("GetReservationDatasetSha256", self.header)
        self.assertIn("int64 StableSeed", self.header)

    def test_feature_query_is_geodesic_and_invalid_inputs_fail_closed(self):
        for token in (
            "BodyId.IsNone()",
            "BodyId != GetReservationBodyIdName()",
            "FeatureTag.IsNone()",
            "WorldPoint.ContainsNaN()",
            "ResolvedBodyCenter.ContainsNaN()",
            "FMath::IsFinite(NominalRadiusCm)",
            "PointOffset.IsNearlyZero()",
            "FMath::Acos(Dot) * NominalRadiusCm",
            "GetBlockedFeatureTags().Contains(FeatureTag)",
            "Result.bQueryValid = true",
            "Result.bBlocked = Result.ProtectionWeight > 0.0f",
        ):
            self.assertIn(token, self.source)
        self.assertIn("bool bQueryValid = false", self.header)
        self.assertIn("bool bBlocked = true", self.header)
        self.assertIn("float ProtectionWeight = 1.0f", self.header)

        query_start = self.source.index(
            "URedPlanetHubReservationRegistry::QueryFeatureProtection"
        )
        query_source = self.source[query_start:]
        taxonomy_check = query_source.index(
            "if (!GetBlockedFeatureTags().Contains(FeatureTag))"
        )
        valid_assignment = query_source.index("Result.bQueryValid = true")
        self.assertLess(taxonomy_check, valid_assignment)
        self.assertIn("return Result;", query_source[taxonomy_check:valid_assignment])

    def test_automation_invalid_feature_fixture_uses_homogeneous_fnames(self):
        self.assertNotIn(
            '{ NAME_None, FName(TEXT("Folige")) }',
            self.automation_test,
        )
        self.assertRegex(
            self.automation_test,
            r"const\s+TArray<FName>\s+InvalidTags\s*=\s*\{\s*"
            r"FName\(\)\s*,\s*FName\(TEXT\(\"Folige\"\)\)\s*\};",
        )
        self.assertIn(
            "for (const FName InvalidTag : InvalidTags)",
            self.automation_test,
        )
        self.assertNotIn("NewObject<UObject>()", self.automation_test)
        self.assertIn(
            '#include "Components/SceneComponent.h"',
            self.automation_test,
        )
        self.assertIn(
            "NewObject<USceneComponent>()",
            self.automation_test,
        )

    def test_public_query_resolves_world_frame_without_caller_center(self):
        declaration_start = self.header.index(
            "static FRedPlanetHubProtectionQuery QueryFeatureProtection("
        )
        declaration_end = self.header.index(");", declaration_start)
        declaration = self.header[declaration_start:declaration_end]
        self.assertIn("const UObject* WorldContextObject", declaration)
        self.assertIn("const FVector& WorldPoint", declaration)
        self.assertNotIn("PlanetCenter", declaration)
        self.assertNotIn("ResolvedBodyCenter", declaration)
        self.assertIn('WorldContext = "WorldContextObject"', self.header)
        self.assertIn("BlueprintCallable", self.header)

        public_start = self.source.index(
            "URedPlanetHubReservationRegistry::QueryFeatureProtection("
        )
        helper_start = self.source.index(
            "URedPlanetHubReservationRegistry::QueryFeatureProtectionAtCenter("
        )
        public_source = self.source[public_start:helper_start]
        for token in (
            "IsInGameThread()",
            "GetWorldFromContextObject",
            "EGetWorldErrorMode::ReturnNull",
            "RedCelestialFrames::FFrameSnapshot BodyFrame",
            "RedCelestialFrames::ResolveExact(World, BodyId, BodyFrame)",
            "BodyFrame.StableId != BodyId",
            "BodyFrame.Center",
            "BodyFrame.NominalRadiusCm",
            "FPlanet50KmProfile::RadiusCm",
            "QueryFeatureProtectionAtCenter(",
        ):
            self.assertIn(token, public_source)
        self.assertNotIn("FMath::Acos", public_source)
        self.assertNotIn("FindMeshPlanet", public_source)
        self.assertNotIn("CLMPlanet", public_source)
        self.assertNotIn("TActorIterator", public_source)

    def test_shared_frame_registry_is_exact_revalidated_and_fail_closed(self):
        combined = self.frame_header + self.frame_source
        for token in (
            "FName StableId = NAME_None",
            "TWeakObjectPtr<UWorld> World",
            "TWeakObjectPtr<AActor> Authority",
            "double NominalRadiusCm = -1.0",
            "uint64 Revision = 0",
            "bool RegisterOrUpdate",
            "bool ResolveExact",
            "OutSnapshot = RedCelestialFrames::FFrameSnapshot()",
            "MatchingRegistrationCount",
            "MatchingRegistrationCount > 1",
            "MatchingRegistrationCount != 1",
            "IsNextRevision(Existing.Revision, Registration.Revision)",
            "Existing.StableId != Registration.StableId",
            "HighWaterRevision",
            "State->bConflict",
            "IsNextRevision(State->HighWaterRevision, Registration.Revision)",
            "Registration.Revision != 1",
            "Registration.Revision < TNumericLimits<uint64>::Max()",
            "Authority->GetWorld() == World",
            "Authority->GetActorLocation().Equals",
            "World->GetNetMode() != NM_Client",
            "Authority->HasAuthority()",
            "struct FAuthorityState",
            "TArray<FAuthorityState> AuthorityStates",
            "World->IsBeingCleanedUp()",
            "World->IsCleanedUp()",
        ):
            self.assertIn(token, combined)

        registry_start = self.frame_source.index("class FCelestialFrameRegistry")
        resolve_start = self.frame_source.index("bool ResolveExact(", registry_start)
        resolve_end = self.frame_source.index("void RemoveWorld", resolve_start)
        resolve_source = self.frame_source[resolve_start:resolve_end]
        self.assertLess(
            resolve_source.index("IsInGameThread()"),
            resolve_source.index("Registration.World.Get()"),
        )
        for forbidden in (
            "FindMeshPlanet",
            "CLMPlanet",
            "TActorIterator",
            "GetActorNameOrLabel",
            "GetName()",
            "GMeshPlanetCache",
            "GetRegistry()",
        ):
            self.assertNotIn(forbidden, combined)
        snapshot_start = self.frame_header.index("struct REDMMO_API FFrameSnapshot")
        snapshot_end = self.frame_header.index(
            "REDMMO_API bool RegisterOrUpdate", snapshot_start
        )
        snapshot_source = self.frame_header[snapshot_start:snapshot_end]
        self.assertNotIn("TWeakObjectPtr", snapshot_source)
        self.assertNotIn("UObject*", snapshot_source)

    def test_exact_frame_contract_model_rejects_ambiguity_and_stale_updates(self):
        def valid(record):
            center = record["center"]
            return (
                record["world"] is not None
                and record["authority"] is not None
                and bool(record["stable_id"])
                and len(center) == 3
                and all(math.isfinite(value) for value in center)
                and math.isfinite(record["radius"])
                and record["radius"] > 0.0
                and record["revision"] > 0
                and record["revision"] < (2**64 - 1)
                and record["server_world"]
                and record["has_authority"]
            )

        def register(records, states, authority_states, incoming):
            if not valid(incoming):
                return False
            key = (incoming["world"], incoming["stable_id"])
            state = states.get(key)
            authority_state = authority_states.get(incoming["authority"])
            if authority_state and authority_state != key:
                return False
            for index, existing in enumerate(records):
                if existing["authority"] != incoming["authority"]:
                    continue
                if (
                    existing["world"] != incoming["world"]
                    or existing["stable_id"] != incoming["stable_id"]
                    or state is None
                    or incoming["revision"] != existing["revision"] + 1
                    or incoming["revision"] != state["high_water"] + 1
                ):
                    return False
                records[index] = incoming
                states[key] = {
                    "high_water": incoming["revision"],
                    "conflict": state["conflict"] if state else False,
                }
                authority_states.setdefault(incoming["authority"], key)
                return True

            same_id = any(
                existing["world"] == incoming["world"]
                and existing["stable_id"] == incoming["stable_id"]
                for existing in records
            )
            if same_id:
                states[key] = {
                    "high_water": state["high_water"] if state else 0,
                    "conflict": True,
                }
                return False

            if state and incoming["revision"] != state["high_water"] + 1:
                return False
            if state is None and incoming["revision"] != 1:
                return False
            states[key] = {
                "high_water": incoming["revision"],
                "conflict": False,
            }
            records.append(incoming)
            authority_states.setdefault(incoming["authority"], key)
            return True

        def unregister(records, world, stable_id, revision):
            for index, existing in enumerate(records):
                if (
                    existing["world"] == world
                    and existing["stable_id"] == stable_id
                    and existing["revision"] == revision
                ):
                    records.pop(index)
                    return True
            return False

        def resolve(records, states, world, stable_id):
            state = states.get((world, stable_id))
            if not state or state["conflict"]:
                return None
            matches = [
                record
                for record in records
                if record["world"] == world and record["stable_id"] == stable_id
            ]
            return (
                matches[0]
                if len(matches) == 1
                and valid(matches[0])
                and matches[0]["revision"] == state["high_water"]
                else None
            )

        home = {
            "world": "world-a",
            "authority": "actor-a",
            "stable_id": "planet.red.mars",
            "center": (0.0, 0.0, 0.0),
            "radius": 795774.7154594767,
            "revision": 1,
            "server_world": True,
            "has_authority": True,
        }
        duplicate = {**home, "authority": "actor-b"}
        for ordered in ([home, duplicate], [duplicate, home]):
            records = []
            states = {}
            authority_states = {}
            self.assertTrue(register(records, states, authority_states, ordered[0]))
            self.assertFalse(register(records, states, authority_states, ordered[1]))
            self.assertIsNone(
                resolve(records, states, "world-a", "planet.red.mars")
            )

        records = []
        states = {}
        authority_states = {}
        self.assertIsNone(resolve(records, states, "world-a", "planet.red.mars"))
        self.assertTrue(register(records, states, authority_states, home))
        self.assertIs(resolve(records, states, "world-a", "planet.red.mars"), home)
        self.assertIsNone(resolve(records, states, "world-b", "planet.red.mars"))
        self.assertIsNone(resolve(records, states, "world-a", "planet.red.wrong"))
        self.assertFalse(
            register(records, states, authority_states, {**home, "revision": 1})
        )
        self.assertFalse(
            register(records, states, authority_states, {**home, "revision": 0})
        )
        self.assertFalse(
            register(records, states, authority_states, {**home, "revision": 3})
        )
        replacement = {**home, "revision": 2, "center": (10.0, 0.0, 0.0)}
        self.assertTrue(register(records, states, authority_states, replacement))
        self.assertIs(
            resolve(records, states, "world-a", "planet.red.mars"), replacement
        )
        self.assertTrue(unregister(records, "world-a", "planet.red.mars", 2))
        self.assertIsNone(resolve(records, states, "world-a", "planet.red.mars"))
        self.assertFalse(register(records, states, authority_states, replacement))
        changed_identity = {
            **home,
            "stable_id": "planet.red.venus",
            "revision": 3,
        }
        self.assertFalse(
            register(records, states, authority_states, changed_identity)
        )
        rebound = {**home, "authority": "actor-b", "revision": 3}
        self.assertTrue(register(records, states, authority_states, rebound))
        self.assertIs(resolve(records, states, "world-a", "planet.red.mars"), rebound)
        for invalid in (
            {**home, "authority": None},
            {**home, "center": (math.nan, 0.0, 0.0)},
            {**home, "radius": 0.0},
            {**home, "stable_id": ""},
            {**home, "server_world": False},
            {**home, "has_authority": False},
            {**home, "revision": 2**64 - 1},
        ):
            self.assertFalse(register([], {}, {}, invalid))

        # Once ambiguity is observed, even the original authority's newer update remains
        # unresolvable. Recovery requires exact teardown and a fresh higher-revision bind.
        records = []
        states = {}
        authority_states = {}
        self.assertTrue(register(records, states, authority_states, home))
        self.assertFalse(register(records, states, authority_states, duplicate))
        recovery_update = {**home, "revision": 2}
        self.assertTrue(
            register(records, states, authority_states, recovery_update)
        )
        self.assertIsNone(resolve(records, states, "world-a", "planet.red.mars"))
        self.assertTrue(unregister(records, "world-a", "planet.red.mars", 2))
        recovered = {**duplicate, "revision": 3}
        self.assertTrue(register(records, states, authority_states, recovered))
        self.assertIs(resolve(records, states, "world-a", "planet.red.mars"), recovered)

    def test_legacy_mesh_planet_abi_and_callers_remain_unchanged(self):
        gravity_header = GRAVITY_HEADER.read_text(encoding="utf-8-sig")
        gravity_source = GRAVITY_CPP.read_text(encoding="utf-8-sig")
        self.assertEqual(gravity_header.count("REDMMO_API bool FindMeshPlanet("), 2)
        self.assertIn("float* OutNominalRadius", gravity_header)
        self.assertIn("OutPeakRadius, nullptr, false", gravity_source)
        self.assertIn("OutNominalRadius, true", gravity_source)

        source_root = ROOT / "Source" / "RedMMO"
        calls_by_path = {}
        call_records_by_path = {}
        unsupported_calls = []
        strict_five_argument_calls = []
        for path in source_root.rglob("*.cpp"):
            if path == GRAVITY_CPP:
                continue
            relative_path = path.relative_to(source_root).as_posix()
            source_text = path.read_text(encoding="utf-8-sig")
            call_records = find_function_calls(
                source_text,
                "FindMeshPlanet",
            )
            arities = [arity for arity, _, _ in call_records]
            calls_by_path[relative_path] = arities
            call_records_by_path[relative_path] = (source_text, call_records)
            unsupported_calls.extend(
                (relative_path, arity)
                for arity in arities
                if arity not in (3, 4, 5)
            )
            strict_five_argument_calls.extend(
                (relative_path, arity)
                for arity in arities
                if arity == 5
            )

        # Preserve every normalized legacy caller recorded by the M05 frame-registry
        # checkpoint. Later modules may add supported calls, but additions cannot
        # compensate for deletion of a historical caller signature or multiplicity.
        legacy_call_signatures = {
            "FootstepTrailComponent.cpp": [
                "FindMeshPlanet(GetWorld(),PlanetCenter,DatumRadius)",
                "FindMeshPlanet(GetWorld(),PlanetCenter,DatumRadius)",
            ],
            "RedCharacterMovement.cpp": [
                "FindMeshPlanet(GetWorld(),LivePlanetCenter,LiveDatumRadius,&LivePeakRadius)",
            ],
            "RedFoliageField.cpp": [
                "FindMeshPlanet(World,PlanetCenter,DatumRadius,&PeakRadius)",
            ],
            "RedGameMode.cpp": [
                "FindMeshPlanet(const_cast<UWorld*>(World),OutCenter,OutRadius)",
                "FindMeshPlanet(World,PlanetCenter,SurfaceRadius)",
                "FindMeshPlanet(World,Center,SurfaceRadius)",
                "FindMeshPlanet(World,PlanetCenter,DatumRadius,&PeakRadius)",
                "FindMeshPlanet(World,MeshCenter,MeshRadius)",
                "FindMeshPlanet(World,PlanetCenter,DatumRadius)",
                "FindMeshPlanet(World,PlanetCenter,DatumRadius,&PeakRadius)",
                "FindMeshPlanet(World,PlanetCenter,PlanetDatumRadiusCm,&PlanetPeakRadiusCm)",
                "FindMeshPlanet(GetWorld(),MeshCenter,MeshRadius)",
                "FindMeshPlanet(GetWorld(),MeshCenter,MeshRadius)",
                "FindMeshPlanet(GetWorld(),MeshCenter,MeshRadius,&PeakRadius)",
            ],
            "RedMMOEditorTools.cpp": [
                "FindMeshPlanet(World,PlanetCenter,DatumRadius,&PeakRadius)",
            ],
            "RedPlayerCharacter.cpp": [
                "FindMeshPlanet(World,Center,DatumRadius,&PeakRadius)",
                "FindMeshPlanet(World,MeshPlanetCenter,MeshPlanetDatumRadius,&MeshPlanetPeakRadius)",
                "FindMeshPlanet(GetWorld(),PlanetCenter,DatumRadius,&PeakRadius)",
                "FindMeshPlanet(World,PlanetCenter,MeshPlanetDatumRadius,&MeshPlanetPeakRadius)",
                "FindMeshPlanet(GetWorld(),PlanetCenter,SafetyDatumRadius,&PeakRadius)",
            ],
            "RedShipMovementComponent.cpp": [
                "FindMeshPlanet(World,HomeCenter,HomeDatumRadius,&HomePeakRadius)",
            ],
            "RedShuttleBase.cpp": [
                "FindMeshPlanet(GetWorld(),HomeCenter,HomeDatumRadius,&HomePeakRadius)",
                "FindMeshPlanet(GetWorld(),HomeCenter,HomeDatumRadius,&HomePeakRadius)",
            ],
            "RedSpaceScenery.cpp": [
                "FindMeshPlanet(World,Center,DatumRadius,&PeakRadius)",
            ],
            "Tests/RedEditorPlacementTests.cpp": [
                "FindMeshPlanet(CurrentWorld,PlanetCenter,DatumRadius,&PeakRadius)",
            ],
        }
        for relative_path, expected_signatures in legacy_call_signatures.items():
            self.assertIn(relative_path, call_records_by_path)
            source_text, call_records = call_records_by_path[relative_path]
            current_signatures = Counter(
                normalize_function_call(source_text[start:end])
                for _, start, end in call_records
            )
            for signature, minimum_count in Counter(expected_signatures).items():
                self.assertGreaterEqual(
                    current_signatures[signature],
                    minimum_count,
                    f"{relative_path} lost legacy caller: {signature}",
                )

        self.assertEqual(unsupported_calls, [])
        self.assertEqual(
            strict_five_argument_calls,
            [("Tests/RedDEF0003ActualFieldPIETests.cpp", 5)],
        )
        strict_test_source = (
            source_root / "Tests" / "RedDEF0003ActualFieldPIETests.cpp"
        ).read_text(encoding="utf-8-sig")
        guard_start, guard_end = find_cpp_if_guard_bounds(
            strict_test_source,
            "WITH_DEV_AUTOMATION_TESTS && WITH_EDITOR",
        )
        strict_records = [
            (start, end)
            for arity, start, end in call_records_by_path[
                "Tests/RedDEF0003ActualFieldPIETests.cpp"
            ][1]
            if arity == 5
        ]
        self.assertEqual(len(strict_records), 1)
        self.assertGreater(strict_records[0][0], guard_start)
        self.assertLessEqual(strict_records[0][1], guard_end)

    def test_find_mesh_planet_call_parser_is_nested_and_fail_closed(self):
        self.assertEqual(
            find_function_call_arities(
                "// FindMeshPlanet(World, Center, Radius)\n"
                'const TCHAR* Label = TEXT("FindMeshPlanet(A, B, C)");\n'
                "/* FindMeshPlanet(D, E, F, G) */",
                "FindMeshPlanet",
            ),
            [],
        )
        self.assertEqual(
            find_function_call_arities(
                "FakeFindMeshPlanet(A, B, C)",
                "FindMeshPlanet",
            ),
            [],
        )
        self.assertEqual(
            find_function_call_arities(
                "FindMeshPlanet()",
                "FindMeshPlanet",
            ),
            [0],
        )
        self.assertEqual(
            find_function_call_arities(
                "FindMeshPlanet(World, Center, Radius)",
                "FindMeshPlanet",
            ),
            [3],
        )
        self.assertEqual(
            find_function_call_arities(
                "FindMeshPlanet(GetWorld(), Center, Radius, ResolvePeak(A, B))",
                "FindMeshPlanet",
            ),
            [4],
        )
        unsupported_mutant = find_function_call_arities(
            'FindMeshPlanet /* gap */\n'
            ' (World, Center, Radius, Peak, TEXT(")"), Ambiguous)',
            "FindMeshPlanet",
        )
        self.assertEqual(
            [arity for arity in [0, *unsupported_mutant] if arity not in (3, 4, 5)],
            [0, 6],
        )
        with self.assertRaises(ValueError):
            find_function_call_arities(
                "FindMeshPlanet(World, Center, Radius",
                "FindMeshPlanet",
            )

        guarded_mutant = (
            "#if WITH_DEV_AUTOMATION_TESTS && WITH_EDITOR\n"
            "FindMeshPlanet(A, B, C, D, E);\n"
            "#endif // WITH_DEV_AUTOMATION_TESTS && WITH_EDITOR\n"
            "// #endif // WITH_DEV_AUTOMATION_TESTS && WITH_EDITOR\n"
            "FindMeshPlanet(A, B, C, D, E);\n"
        )
        guard_start, guard_end = find_cpp_if_guard_bounds(
            guarded_mutant,
            "WITH_DEV_AUTOMATION_TESTS && WITH_EDITOR",
        )
        guarded_records = find_function_calls(guarded_mutant, "FindMeshPlanet")
        self.assertEqual(len(guarded_records), 2)
        self.assertGreater(guarded_records[0][1], guard_start)
        self.assertLessEqual(guarded_records[0][2], guard_end)
        self.assertGreater(guarded_records[1][1], guard_end)

        for branch_directive in (
            "#else",
            "#elif !WITH_EDITOR",
        ):
            branched_mutant = (
                "#if WITH_DEV_AUTOMATION_TESTS && WITH_EDITOR\n"
                "FindMeshPlanet(A, B, C, D);\n"
                f"{branch_directive}\n"
                "FindMeshPlanet(A, B, C, D, E);\n"
                "#endif\n"
            )
            branch_start, branch_end = find_cpp_if_guard_bounds(
                branched_mutant,
                "WITH_DEV_AUTOMATION_TESTS && WITH_EDITOR",
            )
            branched_records = find_function_calls(
                branched_mutant,
                "FindMeshPlanet",
            )
            self.assertEqual(len(branched_records), 2)
            self.assertGreater(branched_records[0][1], branch_start)
            self.assertLessEqual(branched_records[0][2], branch_end)
            self.assertGreater(branched_records[1][1], branch_end)

    def test_radius_weight_contract_matches_every_persisted_reservation(self):
        planet_radius = float(self.document["planet_radius_cm"])
        for record in self.document["reservations"]:
            hard = float(record["protected_radius_cm"])
            blend = float(record["blend_radius_cm"])
            self.assertGreater(planet_radius, hard + blend)
            for distance, expected in (
                (0.0, 1.0),
                (hard, 1.0),
                (hard + blend * 0.5, 0.5),
                (hard + blend, 0.0),
            ):
                angle = distance / planet_radius
                reconstructed = math.acos(max(-1.0, min(1.0, math.cos(angle)))) * planet_radius
                if reconstructed <= hard:
                    actual = 1.0
                elif reconstructed >= hard + blend:
                    actual = 0.0
                else:
                    actual = 1.0 - ((reconstructed - hard) / blend)
                self.assertAlmostEqual(actual, expected, places=5)

    def test_registry_does_not_activate_worldgen_pcg_or_actor_streaming(self):
        combined = self.header + self.source
        for forbidden in (
            "#include \"WorldGen",
            "#include \"PCG",
            "SpawnActor",
            "GetActorIterator",
            "SetActorLocation",
            "bSurfaceDressingEnabled = true",
            "runtime_consumed = true",
        ):
            self.assertNotIn(forbidden, combined)
        self.assertIn("never enables or spawns PCG/WorldGen", self.header)

    def test_project_owned_runtime_integration_remains_unwired_and_dressing_suppressed(self):
        project = json.loads(PROJECT_FILE.read_text(encoding="utf-8-sig"))
        enabled_plugins = {
            plugin["Name"] for plugin in project["Plugins"] if plugin.get("Enabled")
        }
        self.assertIn("PCG", enabled_plugins)
        self.assertIn("WorldGen", enabled_plugins)

        project_owned_runtime_files = list((ROOT / "Source" / "RedMMO").rglob("*.h"))
        project_owned_runtime_files += list((ROOT / "Source" / "RedMMO").rglob("*.cpp"))
        callsites = []
        dataset_references = []
        frame_registration_callsites = []
        for path in project_owned_runtime_files:
            text = path.read_text(encoding="utf-8-sig", errors="replace")
            if path not in (
                REGISTRY_HEADER,
                REGISTRY_CPP,
                REGISTRY_AUTOMATION_TEST,
            ) and "QueryFeatureProtection" in text:
                callsites.append(path)
            if path not in (REGISTRY_HEADER, REGISTRY_CPP) and DATASET.name in text:
                dataset_references.append(path)
            if path not in (FRAME_REGISTRY_HEADER, FRAME_REGISTRY_CPP) and (
                "RegisterOrUpdate(" in text or ".RegisterOrUpdate(" in text
            ):
                frame_registration_callsites.append(path)
        self.assertEqual(callsites, [])
        self.assertEqual(dataset_references, [])
        self.assertEqual(frame_registration_callsites, [])
        automation_source = REGISTRY_AUTOMATION_TEST.read_text(encoding="utf-8-sig")
        self.assertIn("AuthenticatedRecords", automation_source)
        self.assertIn("ProtectionQueries", automation_source)
        self.assertIn("QueryFeatureProtection", automation_source)

        build_rules = BUILD_RULES.read_text(encoding="utf-8-sig")
        self.assertNotIn('"PCG"', build_rules)
        self.assertNotIn('"WorldGen"', build_rules)
        self.assertIn(
            "bSuppressProceduralSurfaceDressing = true",
            GAME_MODE_HEADER.read_text(encoding="utf-8-sig"),
        )
        self.assertIn(
            "bSuppressAllProceduralDressing = true",
            FOLIAGE_HEADER.read_text(encoding="utf-8-sig"),
        )
        palette = PALETTE_HEADER.read_text(encoding="utf-8-sig")
        self.assertIn("bApprovedForPCG = false", palette)
        self.assertIn("bHandPlacementOnly = true", palette)
        engine = DEFAULT_ENGINE.read_text(encoding="utf-8-sig")
        self.assertIn("GlobalDefaultGameMode=/Script/RedMMO.RedGameMode", engine)

    def test_dataset_and_protected_checkpoint_are_unchanged(self):
        self.assertEqual(sha256_file(DATASET), EXPECTED_DATASET_FILE_SHA256)
        self.assertEqual(
            self.document["reservation_dataset_sha256"], EXPECTED_RESERVATION_SHA256
        )
        self.assertEqual(sha256_file(PROTECTED_MAP), EXPECTED_PROTECTED_MAP_SHA256)


if __name__ == "__main__":
    unittest.main()
