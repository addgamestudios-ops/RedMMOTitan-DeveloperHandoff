from __future__ import annotations

import ast
import hashlib
import json
import os
import sys
import types
import unittest
from pathlib import Path


PROJECT_ROOT = Path(r"D:\RedMMOTitan")
SUT_PATH = (
    PROJECT_ROOT
    / "Tools"
    / "generate_redmmo_nwiro_replay_coordinator_runtime_manifest.py"
)
MANIFEST_PATH = (
    PROJECT_ROOT
    / "Build"
    / "Automation"
    / "redmmo_nwiro_replay_python_runtime_manifest_v1.json"
)
EXPECTED_MANIFEST_SHA256 = (
    "A6CBE97F22C8AB928059FFF83F7887D5819B2AF45E1FE9494BA34AD6EA4E215A"
)
EXPECTED_MANIFEST_BYTES = 622_905


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest().upper()


def _canonical(value: object) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=True,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        + b"\n"
    )


def _load_sut() -> types.ModuleType:
    payload = SUT_PATH.read_bytes()
    module = types.ModuleType("_runtime_manifest_generator_test_subject")
    module.__file__ = str(SUT_PATH)
    module.__package__ = ""
    sys.modules[module.__name__] = module
    try:
        exec(
            compile(payload, str(SUT_PATH), "exec", dont_inherit=True),
            module.__dict__,
        )
        return module
    except Exception:
        sys.modules.pop(module.__name__, None)
        raise


class ReplayCoordinatorRuntimeManifestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = SUT_PATH.read_bytes()
        cls.sut = _load_sut()
        cls.manifest_payload = MANIFEST_PATH.read_bytes()
        cls.manifest = json.loads(cls.manifest_payload)

    @classmethod
    def tearDownClass(cls) -> None:
        sys.modules.pop(cls.sut.__name__, None)

    def test_generator_is_fixed_stdlib_only_offline_no_clobber(self) -> None:
        tree = ast.parse(self.source, filename=str(SUT_PATH))
        imports: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(
                    alias.name.split(".", 1)[0] for alias in node.names
                )
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module.split(".", 1)[0])
        self.assertEqual(
            imports,
            {
                "__future__",
                "ctypes",
                "hashlib",
                "json",
                "msvcrt",
                "os",
                "stat",
                "subprocess",
                "sys",
                "typing",
                "pathlib",
            },
        )
        decoded = self.source.decode("utf-8")
        self.assertIn('OUTPUT_PATH.open("xb")', decoded)
        self.assertIn('env={}', decoded)
        self.assertNotIn("socket", decoded)
        self.assertNotIn("urllib", decoded)
        self.assertNotIn("requests", decoded)
        self.assertNotIn("shutil.rmtree", decoded)
        self.assertNotIn("unlink(", decoded)
        self.assertNotIn("os.replace(", decoded)
        self.assertNotIn("OUTPUT_PATH.replace(", decoded)

    def test_manifest_is_exact_canonical_review_input(self) -> None:
        self.assertEqual(len(self.manifest_payload), EXPECTED_MANIFEST_BYTES)
        self.assertEqual(
            _sha256(self.manifest_payload),
            EXPECTED_MANIFEST_SHA256,
        )
        self.assertEqual(
            self.manifest_payload,
            _canonical(self.manifest),
        )
        self.assertEqual(self.manifest["schema_version"], 1)
        self.assertEqual(
            self.manifest["manifest_id"],
            "redmmo.m07.nwiro.replay-python-runtime-v1",
        )
        self.assertEqual(
            self.manifest["status"],
            "review_input_not_execution_authority",
        )
        self.assertEqual(
            self.manifest["required_flags"],
            ["-I", "-S", "-B"],
        )
        self.assertFalse(
            self.manifest["authorities"]["runtime_mutation_authorized"]
        )
        self.assertFalse(
            self.manifest["authorities"]["network_authorized"]
        )
        self.assertFalse(
            self.manifest["authorities"][
                "project_code_execution_authorized"
            ]
        )
        self.assertFalse(
            self.manifest["authorities"]["unreal_launch_authorized"]
        )

    def test_manifest_uses_physical_nonjunction_python_root(self) -> None:
        runtime_root = Path(self.manifest["runtime_root"])
        python_exe = Path(self.manifest["python_executable"])
        self.assertEqual(runtime_root, self.sut.PYTHON_ROOT)
        self.assertEqual(python_exe, self.sut.PYTHON_EXE)
        self.assertIn("cpython-3.11.15-windows-x86_64-none", str(runtime_root))
        self.assertNotIn(
            "cpython-3.11-windows-x86_64-none",
            str(runtime_root),
        )
        info = runtime_root.stat(follow_symlinks=False)
        self.assertFalse(runtime_root.is_symlink())
        self.assertFalse(self.sut._is_reparse(info))
        self.assertEqual(
            self.manifest["version"],
            self.sut.EXPECTED_VERSION,
        )
        self.assertEqual(
            self.manifest["isolated_attestation"]["flags"],
            {
                "isolated": 1,
                "no_site": 1,
                "dont_write_bytecode": 1,
                "safe_path": True,
            },
        )

    def test_manifest_paths_are_complete_unique_and_safe(self) -> None:
        directories = self.manifest["directories"]
        files = self.manifest["files"]
        self.assertEqual(
            len(directories),
            self.manifest["directory_count_excluding_root"],
        )
        self.assertEqual(len(files), self.manifest["file_count"])
        self.assertEqual(len(directories), 366)
        self.assertEqual(len(files), 4_206)
        self.assertEqual(
            sum(int(row["bytes"]) for row in files),
            self.manifest["total_bytes"],
        )
        self.assertEqual(self.manifest["total_bytes"], 74_504_291)

        paths = [*directories, *(row["path"] for row in files)]
        folded = [str(path).casefold() for path in paths]
        self.assertEqual(len(folded), len(set(folded)))
        for relative in paths:
            with self.subTest(relative=relative):
                self.assertTrue(relative)
                self.assertNotIn("\\", relative)
                self.assertFalse(relative.startswith("/"))
                self.assertNotIn("", relative.split("/"))
                self.assertFalse(
                    any(part in {".", ".."} for part in relative.split("/"))
                )

    def test_manifest_digest_contract_recomputes_exactly(self) -> None:
        directories = self.manifest["directories"]
        files = self.manifest["files"]
        topology_payload = "\n".join(
            [f"D:{path}" for path in directories]
            + [f"F:{row['path']}" for row in files]
        ).encode("utf-8")
        record_payload = b"".join(
            (
                f"{row['path']}\0{row['bytes']}\0{row['sha256']}\n"
            ).encode("utf-8")
            for row in files
        )
        self.assertEqual(
            _sha256(topology_payload),
            self.manifest["topology_sha256"],
        )
        self.assertEqual(
            _sha256(record_payload),
            self.manifest["record_set_sha256"],
        )
        self.assertEqual(
            self.manifest["topology_sha256"],
            "1271147F093E605C143239A3BED6EE91CA7361AFC71912550C75B07CF98511C1",
        )
        self.assertEqual(
            self.manifest["record_set_sha256"],
            "A46015AB7005B36A0FCCEA9389426A1DDFD57E41DBC0D66EF86270A6C028CDAE",
        )

    def test_current_runtime_bytes_match_every_manifest_record(self) -> None:
        runtime_root = Path(self.manifest["runtime_root"])
        observed_directories: list[str] = []
        observed_files: list[str] = []
        for current, dir_names, file_names in os.walk(
            runtime_root,
            topdown=True,
            followlinks=False,
        ):
            dir_names.sort(key=str.casefold)
            file_names.sort(key=str.casefold)
            current_path = Path(current)
            if current_path != runtime_root:
                observed_directories.append(
                    current_path.relative_to(runtime_root).as_posix()
                )
            for name in file_names:
                path = current_path / name
                observed_files.append(
                    path.relative_to(runtime_root).as_posix()
                )
        observed_directories.sort(key=str.casefold)
        observed_files.sort(key=str.casefold)
        self.assertEqual(observed_directories, self.manifest["directories"])
        self.assertEqual(
            observed_files,
            [row["path"] for row in self.manifest["files"]],
        )
        for row in self.manifest["files"]:
            path = runtime_root / row["path"]
            payload = path.read_bytes()
            with self.subTest(path=row["path"]):
                self.assertEqual(len(payload), row["bytes"])
                self.assertEqual(_sha256(payload), row["sha256"])

    def test_pinned_python_and_dll_records_are_exact(self) -> None:
        rows = {
            row["path"]: row for row in self.manifest["files"]
        }
        self.assertEqual(
            rows["python.exe"]["sha256"],
            self.sut.EXPECTED_PYTHON_EXE_SHA256,
        )
        self.assertEqual(rows["python.exe"]["bytes"], 91_648)
        self.assertEqual(
            rows["python311.dll"]["sha256"],
            self.sut.EXPECTED_PYTHON_DLL_SHA256,
        )
        self.assertEqual(rows["python311.dll"]["bytes"], 5_842_944)
        self.assertNotIn("python311.zip", rows)


if __name__ == "__main__":
    unittest.main()
