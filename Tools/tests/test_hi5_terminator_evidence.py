import hashlib
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DEFECT = ROOT / "ProjectKnowledge/defects/DEF-0007-hi5-cloud-terminator-volume-steps.yaml"
BUILD_EVIDENCE = ROOT / "ProjectKnowledge/evidence/2026-07-21-hi5-terminator-fade-build.yaml"
RUNTIME_BLOCKER = ROOT / "ProjectKnowledge/evidence/2026-07-22-hi5-terminator-runtime-startup-blocker.yaml"
RESOURCE_REFUSAL = ROOT / "ProjectKnowledge/evidence/2026-07-22-hi5-terminator-real-gpu-resource-refusal.yaml"
BUILD_LOG = Path(
    "D:/RedMMOTitanWindowsData/Diagnostics/AtmosphereTerminator_20260721_235829_stdout.log"
)
MISSING_LOG_NAME = "AtmosphereTerminator_20260721_233933_stdout.log"
BUILD_LOG_SHA256 = "BD6DA4797434CCABA65D8A80628C429C77947D3F7B963FAF04A6D0A5BF761524"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


class Hi5TerminatorEvidenceTests(unittest.TestCase):
    def test_build_pointer_is_existing_and_hash_pinned(self) -> None:
        defect_text = DEFECT.read_text(encoding="utf-8")
        build_text = BUILD_EVIDENCE.read_text(encoding="utf-8")

        self.assertNotIn(MISSING_LOG_NAME, defect_text)
        self.assertNotIn(MISSING_LOG_NAME, build_text)
        self.assertTrue(BUILD_LOG.is_file())
        self.assertEqual(sha256(BUILD_LOG), BUILD_LOG_SHA256)
        self.assertIn(BUILD_LOG.as_posix(), defect_text)
        self.assertIn(BUILD_LOG.as_posix(), build_text)
        self.assertIn(BUILD_LOG_SHA256, defect_text)
        self.assertIn(BUILD_LOG_SHA256, build_text)

    def test_preserved_log_proves_compile_link_and_success_only(self) -> None:
        log_text = BUILD_LOG.read_text(encoding="utf-8", errors="replace")

        self.assertIn("Compile [x64] RedGameMode.cpp", log_text)
        self.assertIn("Link [x64] UnrealEditor-RedMMO.dll", log_text)
        self.assertIn("WriteMetadata TitanEditor.target", log_text)
        self.assertIn("Result: Succeeded", log_text)
        self.assertIn("Total execution time: 59.19 seconds", log_text)
        self.assertNotIn("fatal error", log_text.lower())
        self.assertNotRegex(log_text.lower(), r"\berror [a-z]?\d{3,}\b")

    def test_visual_gate_remains_explicitly_open(self) -> None:
        defect_text = DEFECT.read_text(encoding="utf-8")
        build_text = BUILD_EVIDENCE.read_text(encoding="utf-8")

        self.assertIn("status: implemented_awaiting_runtime_acceptance", defect_text)
        self.assertIn("evidence_class: real_gpu_visual", defect_text)
        self.assertIn(RUNTIME_BLOCKER.relative_to(ROOT).as_posix(), defect_text)
        self.assertIn(RESOURCE_REFUSAL.relative_to(ROOT).as_posix(), defect_text)
        self.assertIn("real-GPU visual acceptance", build_text)


if __name__ == "__main__":
    unittest.main()
