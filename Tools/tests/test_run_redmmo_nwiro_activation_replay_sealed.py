from __future__ import annotations

import ast
import contextlib
import hashlib
import json
import os
import sys
import types
import unittest
from pathlib import Path
from unittest import mock


PROJECT_ROOT = Path(r"D:\RedMMOTitan")
SUT_PATH = (
    PROJECT_ROOT
    / "Tools"
    / "run_redmmo_nwiro_activation_replay_sealed.py"
)
AUTH_PATH = (
    PROJECT_ROOT
    / "Build"
    / "Automation"
    / "redmmo_nwiro_activation_replay_bootstrap_execution_authorization_v1.json"
)


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest().upper()


def _load_sut() -> types.ModuleType:
    payload = SUT_PATH.read_bytes()
    module = types.ModuleType("_sealed_bootstrap_test_subject")
    module.__file__ = str(SUT_PATH)
    module.__package__ = ""
    exec(
        compile(payload, str(SUT_PATH), "exec", dont_inherit=True),
        module.__dict__,
    )
    return module


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


class SealedBootstrapContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = SUT_PATH.read_bytes()
        cls.sut = _load_sut()

    def tearDown(self) -> None:
        for name in self.sut.MODULE_NAMES:
            sys.modules.pop(name, None)

    def test_exact_graph_hashes_lengths_and_authorization(self) -> None:
        for (
            role,
            _sealed_name,
            project_path,
            expected_sha256,
            expected_bytes,
        ) in self.sut.GRAPH:
            with self.subTest(role=role):
                payload = project_path.read_bytes()
                self.assertEqual(len(payload), expected_bytes)
                self.assertEqual(_sha256(payload), expected_sha256)

        authorization_payload = AUTH_PATH.read_bytes()
        authorization = json.loads(authorization_payload)
        self.assertEqual(authorization_payload, _canonical(authorization))
        self.assertEqual(
            authorization,
            self.sut._expected_authorization(self.source),
        )
        self.assertEqual(
            authorization["launcher"]["sha256"],
            _sha256(self.source),
        )

    def test_source_is_stdlib_only_and_fixed_byte_exec_only(self) -> None:
        tree = ast.parse(self.source, filename=str(SUT_PATH))
        imports: set[str] = set()
        compile_calls: list[ast.Call] = []
        exec_calls: list[ast.Call] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name.split(".", 1)[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module.split(".", 1)[0])
            elif isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name) and node.func.id == "compile":
                    compile_calls.append(node)
                if isinstance(node.func, ast.Name) and node.func.id == "exec":
                    exec_calls.append(node)
        self.assertEqual(
            imports,
            {
                "__future__",
                "base64",
                "contextlib",
                "ctypes",
                "hashlib",
                "importlib",
                "json",
                "msvcrt",
                "os",
                "stat",
                "subprocess",
                "sys",
                "types",
                "typing",
                "pathlib",
            },
        )
        self.assertEqual(len(compile_calls), 1)
        self.assertEqual(len(exec_calls), 1)
        parent_map: dict[ast.AST, ast.AST] = {}
        for parent in ast.walk(tree):
            for child in ast.iter_child_nodes(parent):
                parent_map[child] = parent
        for call in (*compile_calls, *exec_calls):
            current: ast.AST | None = call
            owner = None
            while current is not None:
                if isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    owner = current.name
                    break
                current = parent_map.get(current)
            self.assertEqual(owner, "_exec_module")
        decoded = self.source.decode("utf-8")
        self.assertNotIn("importlib.util", decoded)
        self.assertNotIn("runpy", decoded)
        self.assertNotIn("socket", decoded)
        self.assertNotIn("urllib", decoded)

    def test_fixed_modes_isolation_and_no_bytecode_contract(self) -> None:
        self.assertEqual(
            self.sut.ALLOWED_MODES,
            ("--publish", "--verify", "--run-replay"),
        )
        authorization = json.loads(AUTH_PATH.read_bytes())
        self.assertEqual(
            authorization["execution"]["python_flags"],
            ["-I", "-S", "-B"],
        )
        self.assertTrue(
            authorization["execution"][
                "project_graph_pyc_not_read_or_written"
            ]
        )
        self.assertTrue(
            authorization["execution"][
                "project_graph_loaded_only_from_authenticated_source_bytes"
            ]
        )
        self.assertTrue(
            authorization["execution"][
                "sealed_and_project_copies_retained_and_byte_equal"
            ]
        )
        self.assertTrue(
            authorization["execution"][
                "retained_handles_until_entrypoint_return"
            ]
        )
        self.assertNotIn("__pycache__", self.sut.EXPECTED_BUNDLE_NAMES)

    def test_canonical_json_refuses_noncanonical_and_nonobject(self) -> None:
        value = {"b": False, "a": [1, 2]}
        self.assertEqual(
            self.sut._canonical_json(_canonical(value), "fixture"),
            value,
        )
        with self.assertRaises(self.sut.BootstrapRefusal):
            self.sut._canonical_json(
                json.dumps(value).encode("utf-8"),
                "fixture",
            )
        with self.assertRaises(self.sut.BootstrapRefusal):
            self.sut._canonical_json(b"[]\n", "fixture")

    def test_exec_module_refuses_poison_and_cleans_owned_failure(self) -> None:
        name = self.sut.MODULE_NAMES[0]
        poison = object()
        sys.modules[name] = poison
        with self.assertRaises(self.sut.BootstrapRefusal):
            self.sut._exec_module(name, b"VALUE = 1\n", Path("X.py"))
        self.assertIs(sys.modules[name], poison)
        sys.modules.pop(name)

        with self.assertRaises(RuntimeError):
            self.sut._exec_module(
                name,
                b"raise RuntimeError('fixture')\n",
                Path("X.py"),
            )
        self.assertNotIn(name, sys.modules)

        module = self.sut._exec_module(
            name,
            b"VALUE = 7\n",
            Path("X.py"),
        )
        self.assertEqual(module.VALUE, 7)
        self.assertIsNone(module.__cached__)
        self.assertIs(sys.modules[name], module)

    def test_exact_helper_object_bindings(self) -> None:
        contract = types.ModuleType("contract")
        creator = types.ModuleType("creator")
        publisher = types.ModuleType("publisher")
        contract_names = (
            "CandidateContractError",
            "_hash_stable_regular_file",
            "_is_reparse",
            "_named_alternate_streams",
            "_read_stable_regular_file",
            "_validate_existing_ancestor_chain",
            "authenticate_plugin_tree_two_pass",
            "canonical_json_bytes",
            "load_json_bytes_strict",
            "validate_contract_file",
            "validate_contract_schema",
        )
        creator_names = (
            "CandidateCreationError",
            "TreeSnapshot",
            "_canonical_file_bytes",
            "_current_token_sid",
            "_lexists",
            "_move_no_clobber",
            "_scan_two_pass",
            "_write_exclusive",
            "_windows_identity",
        )
        for name in contract_names:
            sentinel = object()
            setattr(contract, name, sentinel)
            setattr(creator, name, sentinel)
            if name in {
                "_is_reparse",
                "_named_alternate_streams",
                "_validate_existing_ancestor_chain",
                "load_json_bytes_strict",
            }:
                setattr(publisher, name, sentinel)
        for name in creator_names:
            sentinel = object()
            setattr(creator, name, sentinel)
            setattr(publisher, name, sentinel)
        self.sut._require_bindings(contract, creator, publisher)
        publisher._move_no_clobber = object()
        with self.assertRaises(self.sut.BootstrapRefusal):
            self.sut._require_bindings(contract, creator, publisher)

    def _payload_map(self) -> dict[str, bytes]:
        result = {
            str(self.sut.SEALED_LAUNCHER): self.source,
            str(self.sut.SEALED_AUTHORIZATION): AUTH_PATH.read_bytes(),
        }
        for (
            _role,
            sealed_name,
            project_path,
            _expected_sha256,
            _expected_bytes,
        ) in self.sut.GRAPH:
            payload = project_path.read_bytes()
            result[str(self.sut.SEALED_ROOT / sealed_name)] = payload
            result[str(project_path)] = payload
        return result

    def _run_with_payloads(
        self,
        payloads: dict[str, bytes],
        events: list[str],
    ) -> tuple[int, mock.Mock]:
        @contextlib.contextmanager
        def locked(path: Path, _max_bytes: int = 32 * 1024 * 1024):
            key = str(path)
            events.append(f"enter:{key}")
            try:
                yield payloads[key]
            finally:
                events.append(f"exit:{key}")

        publisher_main = mock.Mock(
            side_effect=lambda argv: events.append(f"main:{argv[0]}") or 0
        )

        def exec_module(name: str, _payload: bytes, _path: Path):
            events.append(f"exec:{name}")
            module = types.ModuleType(name)
            if name == self.sut.MODULE_NAMES[2]:
                module.main = publisher_main
            sys.modules[name] = module
            return module

        with (
            mock.patch.object(
                self.sut,
                "_require_process_isolation",
                return_value="--verify",
            ),
            mock.patch.object(self.sut, "_all_bundle_paths", return_value=[]),
            mock.patch.object(
                self.sut,
                "_require_exact_private_acl",
                return_value="S-1-fixture",
            ),
            mock.patch.object(self.sut, "_locked_payload", side_effect=locked),
            mock.patch.object(self.sut, "_preload_stdlib"),
            mock.patch.object(self.sut, "_exec_module", side_effect=exec_module),
            mock.patch.object(self.sut, "_require_bindings"),
            mock.patch.object(
                self.sut,
                "_get_windows_directory",
                return_value=Path(r"C:\Windows"),
            ),
            mock.patch.object(self.sut.os, "environ", {}),
            mock.patch.object(self.sut.os, "chdir"),
        ):
            result = self.sut._run(["--verify"])
        return result, publisher_main

    def test_complete_graph_locked_before_first_project_exec_and_until_return(
        self,
    ) -> None:
        events: list[str] = []
        result, publisher_main = self._run_with_payloads(
            self._payload_map(),
            events,
        )
        self.assertEqual(result, 0)
        publisher_main.assert_called_once_with(["--verify"])
        first_exec = next(i for i, event in enumerate(events) if event.startswith("exec:"))
        main_index = next(i for i, event in enumerate(events) if event.startswith("main:"))
        enter_events = [event for event in events if event.startswith("enter:")]
        self.assertEqual(len(enter_events), len(self.sut.GRAPH) * 2 + 2)
        self.assertTrue(
            all(
                events.index(event) < first_exec
                for event in enter_events
            )
        )
        exit_indices = [
            i for i, event in enumerate(events) if event.startswith("exit:")
        ]
        self.assertTrue(exit_indices)
        self.assertTrue(all(index > main_index for index in exit_indices))
        self.assertEqual(
            [event for event in events if event.startswith("exec:")],
            [f"exec:{name}" for name in self.sut.MODULE_NAMES],
        )
        for name in self.sut.MODULE_NAMES:
            self.assertNotIn(name, sys.modules)

    def test_each_tampered_graph_member_refuses_before_compile(self) -> None:
        for role, sealed_name, *_rest in self.sut.GRAPH:
            with self.subTest(role=role):
                payloads = self._payload_map()
                key = str(self.sut.SEALED_ROOT / sealed_name)
                payloads[key] = payloads[key][:-1] + bytes(
                    [payloads[key][-1] ^ 1]
                )
                events: list[str] = []
                with self.assertRaises(self.sut.BootstrapRefusal):
                    self._run_with_payloads(payloads, events)
                self.assertFalse(
                    any(event.startswith("exec:") for event in events)
                )
                self.assertFalse(
                    any(event.startswith("main:") for event in events)
                )

    def test_each_tampered_live_project_member_refuses_before_compile(self) -> None:
        for role, _sealed_name, project_path, *_rest in self.sut.GRAPH:
            with self.subTest(role=role):
                payloads = self._payload_map()
                key = str(project_path)
                payloads[key] = payloads[key][:-1] + bytes(
                    [payloads[key][-1] ^ 1]
                )
                events: list[str] = []
                with self.assertRaises(self.sut.BootstrapRefusal):
                    self._run_with_payloads(payloads, events)
                self.assertFalse(
                    any(event.startswith("exec:") for event in events)
                )
                self.assertFalse(
                    any(event.startswith("main:") for event in events)
                )

    def test_tampered_launcher_refuses_before_compile(self) -> None:
        payloads = self._payload_map()
        key = str(self.sut.SEALED_LAUNCHER)
        payloads[key] = payloads[key][:-1] + bytes(
            [payloads[key][-1] ^ 1]
        )
        events: list[str] = []
        with self.assertRaises(self.sut.BootstrapRefusal):
            self._run_with_payloads(payloads, events)
        self.assertFalse(any(event.startswith("exec:") for event in events))

    def test_tampered_bootstrap_authorization_refuses_before_compile(self) -> None:
        payloads = self._payload_map()
        key = str(self.sut.SEALED_AUTHORIZATION)
        authorization = json.loads(payloads[key])
        authorization["status"] = "tampered"
        payloads[key] = _canonical(authorization)
        events: list[str] = []
        with self.assertRaises(self.sut.BootstrapRefusal):
            self._run_with_payloads(payloads, events)
        self.assertFalse(any(event.startswith("exec:") for event in events))

    def test_project_and_bundle_have_no_launcher_bytecode(self) -> None:
        caches = [
            PROJECT_ROOT / "Tools" / "__pycache__",
            PROJECT_ROOT / "Tools" / "tests" / "__pycache__",
            self.sut.SEALED_ROOT / "__pycache__",
        ]
        matches: list[Path] = []
        for cache in caches:
            if cache.is_dir():
                matches.extend(
                    cache.glob(
                        "run_redmmo_nwiro_activation_replay_sealed*.pyc"
                    )
                )
        self.assertEqual(matches, [])


if __name__ == "__main__":
    unittest.main()
