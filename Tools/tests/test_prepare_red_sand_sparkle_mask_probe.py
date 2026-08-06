import ast
import copy
import importlib.util
import pathlib
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "Build" / "Automation" / "prepare_red_sand_sparkle_mask_probe.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("red_sand_mask_probe", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class RedSandMaskProbePolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = _load_module()
        cls.source = SCRIPT.read_text(encoding="utf-8")
        cls.tree = ast.parse(cls.source)

    def _snapshot(self, desired=False):
        switches = {
            name: {"value": value, "overridden": True}
            for name, value in self.module.HELD_SWITCHES.items()
        }
        switches.update(
            {
                "SimpleSparkle?": {"value": bool(desired), "overridden": True},
                "SparklShrinkNear?": {
                    "value": not bool(desired),
                    "overridden": True,
                },
            }
        )
        scalars = {
            name: {"value": value, "overridden": True}
            for name, value in self.module.HELD_SCALARS.items()
        }
        return {
            "switches": switches,
            "scalars": scalars,
            "vector": {
                "value": self.module.HELD_VECTOR["value"],
                "overridden": True,
            },
        }

    def test_baseline_and_idempotent_probe_states_are_valid(self):
        self.module.validate_snapshot(self._snapshot(desired=False), True)
        self.module.validate_snapshot(self._snapshot(desired=True), True)

    def test_partial_probe_state_is_rejected(self):
        snapshot = self._snapshot(desired=False)
        snapshot["switches"]["SimpleSparkle?"]["value"] = True
        with self.assertRaisesRegex(RuntimeError, "partial mask-probe state"):
            self.module.validate_snapshot(snapshot, True)

    def test_held_parameter_drift_is_rejected(self):
        snapshot = self._snapshot(desired=False)
        snapshot["scalars"]["Desert Sparkle Brightness"]["value"] = 121.0
        with self.assertRaisesRegex(RuntimeError, "Held scalar drift"):
            self.module.validate_snapshot(snapshot, True)

    def test_write_is_exactly_scoped(self):
        self.assertEqual(
            self.module.TARGET_ASSET,
            "/Game/RedMMO/Materials/DesertSparkleTest/"
            "MI_PlanetBiome_DesertSparkle_T02",
        )
        self.assertTrue(self.module.TARGET_ASSET.startswith(self.module.ALLOWED_PACKAGE_ROOT))
        save_calls = []
        forbidden_calls = []
        for node in ast.walk(self.tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            if node.func.attr == "save_asset":
                save_calls.append(node)
            if node.func.attr in {"save_directory", "save_loaded_assets", "save_packages"}:
                forbidden_calls.append(node.func.attr)
        self.assertEqual(len(save_calls), 1)
        self.assertIsInstance(save_calls[0].args[0], ast.Name)
        self.assertEqual(save_calls[0].args[0].id, "TARGET_ASSET")
        self.assertEqual(forbidden_calls, [])

    def test_probe_has_explicit_write_flag_and_protected_assets(self):
        self.assertEqual(self.module.WRITE_FLAG, "-RedSandSparkleMaskProbeWrite")
        self.assertIn("/Game/SoStylized/Materials/MF_DesertSand", self.module.PROTECTED_PACKAGES)
        self.assertIn("/Game/SoStylized/Materials/MF_Sparkle", self.module.PROTECTED_PACKAGES)
        self.assertIn("/Game/RedMMO/Materials/MI_PlanetBiome_RED", self.module.PROTECTED_PACKAGES)
        self.assertIn("/Game/RedMMO/Maps/RedPlanetGen_50km_Test", self.module.PROTECTED_PACKAGES)
        self.assertNotIn(self.module.TARGET_ASSET, self.module.PROTECTED_PACKAGES)

    def test_write_flag_is_exact(self):
        self.assertTrue(
            self.module._has_write_flag(
                "Titan.uproject -Unattended -RedSandSparkleMaskProbeWrite"
            )
        )
        self.assertFalse(
            self.module._has_write_flag(
                "Titan.uproject -RedSandSparkleMaskProbeWriteExtra"
            )
        )

    def test_package_resolver_accepts_uasset_and_umap_only(self):
        with tempfile.TemporaryDirectory() as raw:
            root = pathlib.Path(raw)
            asset = root / "Content" / "RedMMO" / "Materials" / "Probe.uasset"
            asset.parent.mkdir(parents=True)
            asset.write_bytes(b"asset")
            self.assertEqual(
                self.module._resolve_package_file(root, "/Game/RedMMO/Materials/Probe"),
                asset,
            )

            world = root / "Content" / "RedMMO" / "Maps" / "Probe.umap"
            world.parent.mkdir(parents=True)
            world.write_bytes(b"map")
            self.assertEqual(
                self.module._resolve_package_file(root, "/Game/RedMMO/Maps/Probe"),
                world,
            )

            duplicate = pathlib.Path(str(world.with_suffix("")) + ".uasset")
            duplicate.write_bytes(b"ambiguous")
            with self.assertRaisesRegex(RuntimeError, "exactly one"):
                self.module._resolve_package_file(root, "/Game/RedMMO/Maps/Probe")

    def test_dirty_policy_distinguishes_write_and_idempotent_paths(self):
        self.module._validate_dirty_after_edit({self.module.TARGET_ASSET}, False)
        self.module._validate_dirty_after_edit(set(), True)
        with self.assertRaisesRegex(RuntimeError, "Unexpected dirty packages"):
            self.module._validate_dirty_after_edit(set(), False)
        with self.assertRaisesRegex(RuntimeError, "Unexpected dirty packages"):
            self.module._validate_dirty_after_edit({self.module.TARGET_ASSET}, True)

    def test_file_restore_is_hash_exact(self):
        with tempfile.TemporaryDirectory() as raw:
            root = pathlib.Path(raw)
            backup = root / "baseline.uasset"
            target = root / "target.uasset"
            backup.write_bytes(b"baseline")
            target.write_bytes(b"changed")
            self.module._restore_target_file(backup, target)
            self.assertEqual(target.read_bytes(), b"baseline")


if __name__ == "__main__":
    unittest.main()
