import hashlib
import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
ENGINE_PLUGINS = Path("D:/UE_5.8/Engine/Plugins")
UPROJECT = ROOT / "Titan.uproject"
BUILD_RULES = ROOT / "Source/RedMMO/RedMMO.Build.cs"
VOXEL_LIBRARY_HEADER = ROOT / "Source/RedMMO/RedMMOVoxelLibrary.h"
VOXEL_LIBRARY_CPP = ROOT / "Source/RedMMO/RedMMOVoxelLibrary.cpp"
BOLT_CPP = ROOT / "Source/RedMMO/RedBolt.cpp"
PLAYER_CPP = ROOT / "Source/RedMMO/RedPlayerCharacter.cpp"
PICKUP_HEADER = ROOT / "Source/RedMMO/RedResourcePickup.h"
PICKUP_CPP = ROOT / "Source/RedMMO/RedResourcePickup.cpp"
ASTEROID_HEADER = ROOT / "Source/RedMMO/RedMineableAsteroid.h"
ASTEROID_CPP = ROOT / "Source/RedMMO/RedMineableAsteroid.cpp"
SYSTEM_RECORD = (
    ROOT / "ProjectKnowledge/systems/on-foot-voxel-asteroid-mining.yaml"
)
QUEUE = ROOT / "Build/Automation/redmmotitan_module_queue.json"
RUNTIME_LOG = Path(
    "D:/RedMMOTitanWindowsData/Diagnostics/"
    "M09_DEF0004_UltrawideInventory_20260723_202937Z/"
    "runtime_3440x1440_final_candidate3.log"
)
RUNTIME_LOG_SHA256 = (
    "AB4C58EE4781EECF43CAF8EE782C46AF6360C4244604B421846FC814A0C1D446"
)


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="strict")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


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


class M12VoxelCapabilityContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.uproject = json.loads(read(UPROJECT))
        cls.build_rules = read(BUILD_RULES)
        cls.voxel_library_header = read(VOXEL_LIBRARY_HEADER)
        cls.voxel_library = read(VOXEL_LIBRARY_CPP)
        cls.bolt = read(BOLT_CPP)
        cls.player = read(PLAYER_CPP)
        cls.pickup_header = read(PICKUP_HEADER)
        cls.pickup = read(PICKUP_CPP)
        cls.asteroid_header = read(ASTEROID_HEADER)
        cls.asteroid = read(ASTEROID_CPP)
        cls.system_record = read(SYSTEM_RECORD)
        cls.queue = json.loads(read(QUEUE))
        cls.runtime = read(RUNTIME_LOG)

    def test_voxel_plugin_is_explicitly_disabled_and_no_descriptor_is_installed(self):
        voxel_entries = [
            plugin
            for plugin in self.uproject["Plugins"]
            if plugin.get("Name") == "Voxel"
        ]
        self.assertEqual(voxel_entries, [{"Name": "Voxel", "Enabled": False}])

        project_descriptors = list((ROOT / "Plugins").rglob("*.uplugin"))
        self.assertEqual(
            [path for path in project_descriptors if path.stem.casefold() == "voxel"],
            [],
        )
        self.assertTrue(ENGINE_PLUGINS.is_dir())
        engine_descriptors = list(ENGINE_PLUGINS.rglob("*.uplugin"))
        self.assertEqual(
            [path for path in engine_descriptors if path.stem.casefold() == "voxel"],
            [],
        )

    def test_redmmo_has_geometry_primitives_but_no_voxel_module_dependency(self):
        plugin_state = {
            plugin["Name"]: plugin.get("Enabled", False)
            for plugin in self.uproject["Plugins"]
        }
        self.assertTrue(plugin_state["GeometryScripting"])
        self.assertIn('"ProceduralMeshComponent"', self.build_rules)
        self.assertNotIn('"Voxel"', self.build_rules)
        self.assertNotIn('"GeometryScriptingCore"', self.build_rules)

    def test_named_voxel_library_is_only_an_editor_sky_curve_tool(self):
        exported_static_functions = re.findall(
            r"\bstatic\s+bool\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(",
            self.voxel_library_header,
        )
        self.assertEqual(exported_static_functions, ["SetColorCurveKeys"])
        for token in (
            "UCurveLinearColor",
            "UCurveLinearColorAtlas",
            "#if WITH_EDITOR",
            "SetColorCurveKeys is editor-only",
        ):
            self.assertIn(token, self.voxel_library)
        for forbidden in (
            "SetDensity",
            "GetDensity",
            "EditVoxel",
            "RemoveVoxel",
            "VoxelWorld",
            "VoxelStamp",
        ):
            self.assertNotIn(forbidden, self.voxel_library_header)
            self.assertNotIn(forbidden, self.voxel_library)

    def test_current_runtime_terrain_carve_is_a_noop_and_player_fire_disables_it(self):
        crater = function_body(
            self.bolt, "void ARedBolt::SpawnVoxelCraterStamp"
        )
        self.assertIn("(void)Hit;", crater)
        self.assertIn(
            "Runtime terrain deformation is disabled while the project runs "
            "without the Voxel plugin.",
            crater,
        )
        for forbidden in ("SpawnActor", "SetDensity", "VoxelWorld", "VoxelStamp"):
            self.assertNotIn(forbidden, crater)

        spawn_bolt = function_body(
            self.player, "void ARedPlayerCharacter::SpawnBolt"
        )
        self.assertIn("Bolt->ConfigureGroundImpact(false, false, false);", spawn_bolt)
        self.assertIn("Mining carve DISABLED again", spawn_bolt)

    def test_existing_resource_pickup_is_authority_overlap_collection_not_suction(self):
        constructor = function_body(
            self.pickup, "ARedResourcePickup::ARedResourcePickup"
        )
        self.assertIn("bReplicates = true;", constructor)
        self.assertIn("SetReplicateMovement(false);", constructor)
        self.assertIn(
            "CollectSphere->SetCollisionResponseToChannel(ECC_Pawn, ECR_Overlap);",
            constructor,
        )

        collect = function_body(
            self.pickup, "void ARedResourcePickup::OnCollectOverlap"
        )
        for token in (
            "!HasAuthority()",
            "bConsumed = true;",
            "Player->AddResource(ResourceType, Amount);",
            "Destroy();",
        ):
            self.assertIn(token, collect)
        for forbidden in (
            "Suction",
            "Tractor",
            "CollectionTarget",
            "VInterpTo",
            "SetActorLocation",
        ):
            self.assertNotIn(forbidden, self.pickup_header)
            self.assertNotIn(forbidden, self.pickup)

    def test_current_asteroid_is_scalar_whole_mesh_depletion_not_voxel_storage(self):
        self.assertIn(
            "TObjectPtr<UStaticMeshComponent> RockMesh;",
            self.asteroid_header,
        )
        mining = function_body(
            self.asteroid, "float ARedMineableAsteroid::RegisterMiningHit"
        )
        for token in (
            "FMath::Min(OreRemaining, MiningStrength * 18.f)",
            "OreRemaining = FMath::Max(0.f, OreRemaining - Extracted);",
            "BeginDepletion(MiningInstigator);",
        ):
            self.assertIn(token, mining)
        for forbidden in (
            "Density",
            "VoxelChunk",
            "MaterialVolume",
            "EditJournal",
        ):
            self.assertNotIn(forbidden, self.asteroid_header)
            self.assertNotIn(forbidden, self.asteroid)

    def test_latest_real_gpu_log_confirms_the_voxel_runtime_class_is_absent(self):
        self.assertEqual(sha256(RUNTIME_LOG), RUNTIME_LOG_SHA256)
        self.assertNotIn("Mounting project plugin Voxel", self.runtime)
        self.assertIn(
            "Failed to find object 'Class "
            "/Script/Voxel.VoxelCollisionInvokerComponent'",
            self.runtime,
        )
        self.assertGreaterEqual(
            self.runtime.count(
                "invoker class '/Script/Voxel.VoxelCollisionInvokerComponent' "
                "not found"
            ),
            2,
        )

    def test_canonical_m12_contract_keeps_destruction_and_voxel_mining_distinct(self):
        m12 = next(module for module in self.queue["modules"] if module["id"] == "M12")
        self.assertEqual(m12["name"], "On-foot voxel asteroid mining and suction collection")
        self.assertIn(
            "localized mutable voxel volume",
            " ".join(m12["acceptance"]),
        )
        self.assertIn("must not be represented as completed mining", m12["last_blocker"])
        for token in (
            "in_memory_sparse_density_backend_static_verified_uncompiled_unwired",
            "current_static_mesh_depletion_is_not_mining",
            "FRedInMemorySparseVoxelBackend",
            "server_authoritative",
            "monotonic edit revision",
            "suction collection",
            "Inventory",
            "late join",
        ):
            self.assertIn(token, self.system_record)


if __name__ == "__main__":
    unittest.main()
