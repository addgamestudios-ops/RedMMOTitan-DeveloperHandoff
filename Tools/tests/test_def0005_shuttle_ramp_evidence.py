import hashlib
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DEFECT = ROOT / "ProjectKnowledge/defects/DEF-0005-shuttle-loading-ramp-nonwalkable.yaml"
LEGACY_EVIDENCE = ROOT / "ProjectKnowledge/evidence/2026-07-22-def-0005-shuttle-ramp-build-reconciliation-static.yaml"
SOURCE_H = ROOT / "Source/RedMMO/RedShuttleBase.h"
SOURCE_CPP = ROOT / "Source/RedMMO/RedShuttleBase.cpp"
SNAPSHOT_ROOT = Path(
    "D:/RedMMOTitanWindowsData/Diagnostics/"
    "Heartbeat_20260724_060908_DEF0005Lineage/lineage_snapshot"
)
OBJECT = SNAPSHOT_ROOT / "RedShuttleBase.cpp.obj"
SARIF = SNAPSHOT_ROOT / "RedShuttleBase.cpp.sarif"
LINK_RESPONSE = SNAPSHOT_ROOT / "UnrealEditor-RedMMO.dll.rsp"
DLL = SNAPSHOT_ROOT / "UnrealEditor-RedMMO.dll"
TARGET = SNAPSHOT_ROOT / "TitanEditor.target"
COMPILE_LOG = SNAPSHOT_ROOT / "TitanEditor_compile_link_20260723.log"
GAME_COMPILE_LOG = SNAPSHOT_ROOT / "Titan_compile_link_20260723.log"
FINAL_LINK_LOG = SNAPSHOT_ROOT / "TitanEditor_final_link_20260723.log"

EXPECTED_HASHES = {
    SOURCE_H: "FECD06BBDB6D6623638EC89D9BC092B40741A19EFEA48EE7A90239591C4244F6",
    SOURCE_CPP: "8AA71FB81C38FC44662726EA40DF61262F73F61296C7185920DA99AD72479610",
    OBJECT: "957269F24817EA50BBC16A26E827E1970283547307180B4F2B122F1A1309CC8A",
    SARIF: "82FA5F5E0E126CFBC7227F1AD9B23A4A6CB22136E9ED3895CF7A161496F0F9DB",
    LINK_RESPONSE: "A580852C135F856C65052F0AA46F28150FC020A6415711DC73CB237F9E70B942",
    DLL: "D623A8F365C09B10665B75A66AA5F55BA2D7BEC2D10681E83BDE237BBBCB00BD",
    TARGET: "46770F8EA77398C32A0927D31F5BBB32BDCAC3CAD41DD7F855BF541C709008A2",
    COMPILE_LOG: "3F68D755D096825A223C6B3B0C2DAD24931C941A0ADDD56CBC2ADC7F8C3E3B93",
    GAME_COMPILE_LOG: "CFCD8C12A4A9483EBC0DF1104A5FCF8032876A2E83545BD9DF44796502587846",
    FINAL_LINK_LOG: "43B7071278B809E064D6CFBF861E44F7CBC3971C5EF0E1659233AA157CA19657",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def read_build_text(path: Path) -> str:
    data = path.read_bytes()
    encoding = "utf-16" if data.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8"
    return data.decode(encoding, errors="replace")


class Def0005ShuttleRampEvidenceTests(unittest.TestCase):
    def test_all_lineage_artifacts_are_hash_pinned(self) -> None:
        for path, expected in EXPECTED_HASHES.items():
            self.assertTrue(path.is_file(), path)
            self.assertEqual(sha256(path), expected, path)

    def test_mutable_build_outputs_are_not_used_as_evidence_inputs(self) -> None:
        mutable_roots = (
            (ROOT / "Intermediate").resolve(),
            (ROOT / "Binaries").resolve(),
        )
        for path in EXPECTED_HASHES:
            if path in (SOURCE_H, SOURCE_CPP):
                continue
            resolved = path.resolve()
            self.assertTrue(
                all(root not in resolved.parents for root in mutable_roots),
                f"mutable build output was treated as preserved evidence: {resolved}",
            )

    def test_compile_link_and_binary_anchors_exist(self) -> None:
        compile_text = read_build_text(COMPILE_LOG)
        game_compile_text = read_build_text(GAME_COMPILE_LOG)
        final_link_text = read_build_text(FINAL_LINK_LOG)
        response_text = LINK_RESPONSE.read_text(encoding="utf-8", errors="replace")
        dll_bytes = DLL.read_bytes()

        self.assertIn("Compile [x64] RedShuttleBase.cpp", compile_text)
        self.assertIn("Link [x64] UnrealEditor-RedMMO.dll", compile_text)
        self.assertIn("Result: Succeeded", compile_text)
        self.assertIn("Compile [x64] RedShuttleBase.cpp", game_compile_text)
        self.assertIn("Link [x64] Titan.exe", game_compile_text)
        self.assertIn("WriteMetadata Titan.target", game_compile_text)
        self.assertIn("Result: Succeeded", game_compile_text)
        self.assertIn("RedShuttleBase.cpp.obj", response_text)
        self.assertIn("Link [x64] UnrealEditor-RedMMO.dll", final_link_text)
        self.assertIn("WriteMetadata TitanEditor.target", final_link_text)
        self.assertIn("Result: Succeeded", final_link_text)
        self.assertIn("RuntimeLoadingRampCollision".encode("utf-16le"), dll_bytes)
        self.assertIn("3 hull + 3 roof deck + 1 loading-ramp pieces".encode("utf-16le"), dll_bytes)

    def test_runtime_collision_gate_remains_open(self) -> None:
        defect_text = DEFECT.read_text(encoding="utf-8")
        legacy_evidence_text = LEGACY_EVIDENCE.read_text(encoding="utf-8")

        self.assertIn("status: implemented_awaiting_runtime_acceptance", defect_text)
        self.assertIn("evidence_class: real_gpu_gameplay_collision", defect_text)
        self.assertIn("walking, projectile-clearance, and closed-door", defect_text)
        self.assertIn("does not prove packaged output", legacy_evidence_text)
        self.assertNotIn("status: closed", defect_text)


if __name__ == "__main__":
    unittest.main()
