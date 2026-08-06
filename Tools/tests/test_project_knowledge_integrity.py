"""Contracts for the fail-closed ProjectKnowledge integrity audit."""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import yaml

from Tools.audit_project_knowledge_integrity import audit_project, main


def write_yaml(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(value, sort_keys=False), encoding="utf-8")


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


class ProjectKnowledgeIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.diagnostics_root = self.root.parent / f"{self.root.name}WindowsData" / "Diagnostics"
        self._create_valid_fixture()

    def tearDown(self):
        self.temporary.cleanup()
        shutil.rmtree(self.diagnostics_root.parent, ignore_errors=True)

    def _create_directory_link(self, link_path: Path, target_path: Path) -> None:
        try:
            link_path.symlink_to(target_path, target_is_directory=True)
            return
        except (NotImplementedError, OSError) as symbolic_link_error:
            if os.name != "nt":
                self.skipTest(f"directory links unavailable: {symbolic_link_error}")

        completed = subprocess.run(
            ["cmd.exe", "/d", "/c", "mklink", "/J", str(link_path), str(target_path)],
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            self.skipTest(
                "directory links unavailable: "
                f"symlink failed and junction exit={completed.returncode}"
            )

    @staticmethod
    def _remove_directory_link(link_path: Path) -> None:
        try:
            link_path.unlink()
        except (IsADirectoryError, PermissionError):
            link_path.rmdir()

    def _create_valid_fixture(self):
        for extra_name in (
            "fixture-completion-duplicate.yaml",
            "fixture-completion-build.yaml",
            "fixture-completion-path-id.yaml",
            "fixture-completion-pathlike-id.yaml",
        ):
            (self.root / "ProjectKnowledge/evidence" / extra_name).unlink(missing_ok=True)
        queue = {
            "schema_version": 1,
            "status_values": [
                "queued",
                "in_progress",
                "awaiting_input",
                "incomplete_retry",
                "blocked",
                "completed",
            ],
            "modules": [
                {
                    "id": "M00",
                    "status": "completed",
                    "dependencies": [],
                    "evidence": ["ProjectKnowledge/evidence/fixture-completion.yaml"],
                    "completion_evidence_classes": ["static"],
                    "last_blocker": None,
                    "retry_count": 0,
                },
                {
                    "id": "M10",
                    "status": "queued",
                    "dependencies": ["M00"],
                    "evidence": [],
                    "last_blocker": None,
                    "retry_count": 0,
                },
            ],
        }
        queue_path = self.root / "Build/Automation/redmmotitan_module_queue.json"
        write_json(queue_path, queue)
        queue_hash = hashlib.sha256(queue_path.read_bytes()).hexdigest().upper()

        write_yaml(
            self.root / "ProjectKnowledge/current_state.yaml",
            {"schema_version": 1, "queue": {"snapshot_sha256": queue_hash}},
        )
        write_yaml(self.root / "ProjectKnowledge/invariants.yaml", {"schema_version": 1})
        write_yaml(self.root / "ProjectKnowledge/systems/fixture.yml", {"schema_version": 1})
        write_yaml(
            self.root / "ProjectKnowledge/evidence/fixture-completion.yaml",
            {
                "schema_version": 1,
                "id": "evidence.fixture.completion.static",
                "module": "M00",
                "evidence_class": "static",
                "result": "passed",
            },
        )
        write_yaml(
            self.root / "ProjectKnowledge/evidence/fixture-static.yaml",
            {
                "schema_version": 1,
                "id": "evidence.fixture.static",
                "evidence_class": "static",
                "result": "passed_structure_only_runtime_open",
                "protected_map_sha256": "A" * 64,
            },
        )
        write_yaml(
            self.root / "ProjectKnowledge/defects/DEF-FIXTURE.yaml",
            {
                "schema_version": 1,
                "id": "DEF-FIXTURE",
                "status": "open",
                "evidence": {"static": "ProjectKnowledge/evidence/fixture-static.yaml"},
            },
        )
        write_yaml(
            self.root / "ProjectKnowledge/INDEX.yaml",
            {
                "schema_version": 1,
                "path_convention": "repo_relative_forward_slash",
                "authoritative_sources": {
                    "work_queue": {"path": "Build/Automation/redmmotitan_module_queue.json"},
                    "current_snapshot": {"path": "ProjectKnowledge/current_state.yaml"},
                    "invariants": {"path": "ProjectKnowledge/invariants.yaml"},
                },
                "systems": ["ProjectKnowledge/systems/fixture.yml"],
                "evidence": [
                    "ProjectKnowledge/evidence/fixture-completion.yaml",
                    "ProjectKnowledge/evidence/fixture-static.yaml",
                ],
                "defects": ["ProjectKnowledge/defects/DEF-FIXTURE.yaml"],
            },
        )

    def _codes(self):
        return [finding["code"] for finding in audit_project(self.root)["findings"]]

    def test_valid_fixture_passes(self):
        report = audit_project(self.root)
        self.assertEqual(report["result"], "pass")
        self.assertEqual(report["error_count"], 0)
        self.assertEqual(report["summary"]["module_count"], 2)

    def test_index_paths_must_be_safe_and_exist(self):
        index_path = self.root / "ProjectKnowledge/INDEX.yaml"
        index = yaml.safe_load(index_path.read_text(encoding="utf-8"))
        index["evidence"].extend(
            [
                "../escape.yaml",
                ".",
                "ProjectKnowledge//evidence/fixture-static.yaml",
                "ProjectKnowledge/evidence/missing.yaml",
            ]
        )
        write_yaml(index_path, index)
        codes = self._codes()
        self.assertIn("PKI002", codes)
        self.assertIn("PKI003", codes)

        index["authoritative_sources"] = []
        index["domain_specs"] = "not-a-list"
        index["systems"] = ["ProjectKnowledge/systems/malformed.yaml"]
        write_yaml(index_path, index)
        malformed = self.root / "ProjectKnowledge/systems/malformed.yaml"
        malformed.parent.mkdir(parents=True, exist_ok=True)
        malformed.write_text("value: [unterminated\n", encoding="utf-8")
        codes = self._codes()
        self.assertIn("PKI020", codes)
        self.assertIn("PKI021", codes)

        index["authoritative_sources"] = {"bad": "not-a-mapping"}
        index["domain_specs"] = [{"id": "missing-path"}]
        write_yaml(index_path, index)
        self.assertIn("PKI020", self._codes())

    def test_duplicate_module_and_evidence_ids_fail(self):
        queue_path = self.root / "Build/Automation/redmmotitan_module_queue.json"
        queue = json.loads(queue_path.read_text(encoding="utf-8"))
        queue["modules"].append({**queue["modules"][0], "status": "queued"})
        write_json(queue_path, queue)

        duplicate_path = self.root / "ProjectKnowledge/evidence/duplicate.yaml"
        write_yaml(
            duplicate_path,
            {
                "schema_version": 1,
                "id": "EVIDENCE.FIXTURE.STATIC",
                "evidence_class": "static",
                "result": "passed",
            },
        )
        index_path = self.root / "ProjectKnowledge/INDEX.yaml"
        index = yaml.safe_load(index_path.read_text(encoding="utf-8"))
        index["evidence"].append("ProjectKnowledge/evidence/duplicate.yaml")
        write_yaml(index_path, index)
        state_path = self.root / "ProjectKnowledge/current_state.yaml"
        state = yaml.safe_load(state_path.read_text(encoding="utf-8"))
        state["queue"]["snapshot_sha256"] = hashlib.sha256(queue_path.read_bytes()).hexdigest().upper()
        write_yaml(state_path, state)

        codes = self._codes()
        self.assertIn("PKI004", codes)
        self.assertIn("PKI010", codes)
        self.assertEqual(set(codes), {"PKI004", "PKI010"})

    def test_retry_requires_blocker_and_snapshot_must_match(self):
        queue_path = self.root / "Build/Automation/redmmotitan_module_queue.json"
        queue = json.loads(queue_path.read_text(encoding="utf-8"))
        queue["modules"][1].update(status="incomplete_retry", retry_count=1, last_blocker=None)
        write_json(queue_path, queue)
        codes = self._codes()
        self.assertIn("PKI007", codes)
        self.assertIn("PKI015", codes)

        queue = json.loads(queue_path.read_text(encoding="utf-8"))
        queue["modules"][0]["evidence"] = ["unresolved prose is not durable evidence"]
        write_json(queue_path, queue)
        state_path = self.root / "ProjectKnowledge/current_state.yaml"
        state = yaml.safe_load(state_path.read_text(encoding="utf-8"))
        state["queue"]["snapshot_sha256"] = hashlib.sha256(queue_path.read_bytes()).hexdigest().upper()
        write_yaml(state_path, state)
        self.assertIn("PKI022", self._codes())

        queue["modules"][0].update(
            status="incomplete_retry",
            retry_count=1,
            last_blocker="fixture blocker",
            evidence=["ProjectKnowledge/evidence/fixture-completion.yaml"],
        )
        queue["modules"][1].update(
            status="completed",
            retry_count=0,
            last_blocker=None,
            evidence=["ProjectKnowledge/evidence/fixture-completion.yaml"],
            completion_evidence_classes=["static"],
        )
        completion_path = self.root / "ProjectKnowledge/evidence/fixture-completion.yaml"
        completion = yaml.safe_load(completion_path.read_text(encoding="utf-8"))
        completion["module"] = "M10"
        write_yaml(completion_path, completion)
        write_json(queue_path, queue)
        state["queue"]["snapshot_sha256"] = hashlib.sha256(queue_path.read_bytes()).hexdigest().upper()
        write_yaml(state_path, state)
        self.assertIn("PKI023", self._codes())

    def test_completed_module_evidence_requires_success_association_and_class_coverage(self):
        queue_path = self.root / "Build/Automation/redmmotitan_module_queue.json"
        state_path = self.root / "ProjectKnowledge/current_state.yaml"
        index_path = self.root / "ProjectKnowledge/INDEX.yaml"
        completion_path = self.root / "ProjectKnowledge/evidence/fixture-completion.yaml"

        def write_queue(queue):
            write_json(queue_path, queue)
            state = yaml.safe_load(state_path.read_text(encoding="utf-8"))
            state["queue"]["snapshot_sha256"] = hashlib.sha256(queue_path.read_bytes()).hexdigest().upper()
            write_yaml(state_path, state)

        for evidence_value in (
            "EVIDENCE.FIXTURE.COMPLETION.STATIC",
            "Evidence: ProjectKnowledge/evidence/fixture-completion.yaml.",
        ):
            with self.subTest(kind="resolution", evidence_value=evidence_value):
                self._create_valid_fixture()
                queue = json.loads(queue_path.read_text(encoding="utf-8"))
                queue["modules"][0]["evidence"] = [evidence_value]
                write_queue(queue)
                self.assertEqual(audit_project(self.root)["error_count"], 0)

        with self.subTest(kind="unresolved"):
            self._create_valid_fixture()
            queue = json.loads(queue_path.read_text(encoding="utf-8"))
            queue["modules"][0]["evidence"] = ["unresolved completion prose"]
            write_queue(queue)
            report = audit_project(self.root)
            self.assertEqual(report["finding_code_counts"], {"PKI022": 1})

        for malformed_evidence in (
            "evidence.fixture.completion.static",
            {"nested": "evidence.fixture.completion.static"},
            [123, "evidence.fixture.completion.static"],
            [["evidence.fixture.completion.static"]],
            [],
            [""],
        ):
            with self.subTest(kind="malformed_evidence_shape", value=malformed_evidence):
                self._create_valid_fixture()
                queue = json.loads(queue_path.read_text(encoding="utf-8"))
                queue["modules"][0]["evidence"] = malformed_evidence
                write_queue(queue)
                report = audit_project(self.root)
                self.assertIn("PKI022", report["finding_code_counts"])

        for evidence_value in (
            "xxProjectKnowledge/evidence/fixture-completion.yaml",
            "prefix/ProjectKnowledge/evidence/fixture-completion.yaml",
            "ProjectKnowledge/evidence/fixture-completion.yamlxx",
            "ProjectKnowledge/evidence/fixture-completion.yaml.evil",
            "ProjectKnowledge/evidence/fixture-completion.ymlbackup",
            "C:\\ProjectKnowledge/evidence/fixture-completion.yaml",
            "C:ProjectKnowledge/evidence/fixture-completion.yaml",
            "ProjectKnowledge/evidence/fixture-completion.yaml:evil",
            "ProjectKnowledge/evidence/fixture-completion.yaml,evil",
            "ProjectKnowledge/evidence/fixture-completion.yaml;evil",
            'ProjectKnowledge/evidence/fixture-completion.yaml"evil',
            "ProjectKnowledge/evidence/fixture-completion.yaml]evil",
            "ProjectKnowledge/evidence/fixture-completion.yaml)evil",
            "éProjectKnowledge/evidence/fixture-completion.yaml",
            "ЖProjectKnowledge/evidence/fixture-completion.yaml",
            "１ProjectKnowledge/evidence/fixture-completion.yaml",
            "\u0301ProjectKnowledge/evidence/fixture-completion.yaml",
        ):
            with self.subTest(kind="unsafe_resolution_boundary", evidence_value=evidence_value):
                self._create_valid_fixture()
                queue = json.loads(queue_path.read_text(encoding="utf-8"))
                queue["modules"][0]["evidence"] = [evidence_value]
                write_queue(queue)
                report = audit_project(self.root)
                self.assertEqual(report["finding_code_counts"], {"PKI022": 1})

        with self.subTest(kind="ambiguous_id"):
            self._create_valid_fixture()
            duplicate_path = self.root / "ProjectKnowledge/evidence/fixture-completion-duplicate.yaml"
            duplicate = yaml.safe_load(completion_path.read_text(encoding="utf-8"))
            write_yaml(duplicate_path, duplicate)
            index = yaml.safe_load(index_path.read_text(encoding="utf-8"))
            index["evidence"].append("ProjectKnowledge/evidence/fixture-completion-duplicate.yaml")
            write_yaml(index_path, index)
            queue = json.loads(queue_path.read_text(encoding="utf-8"))
            queue["modules"][0]["evidence"] = ["evidence.fixture.completion.static"]
            write_queue(queue)
            report = audit_project(self.root)
            self.assertEqual(report["finding_code_counts"], {"PKI010": 1, "PKI022": 1})

        with self.subTest(kind="path_takes_precedence_over_id_collision"):
            self._create_valid_fixture()
            collision_path = self.root / "ProjectKnowledge/evidence/fixture-completion-path-id.yaml"
            write_yaml(
                collision_path,
                {
                    "schema_version": 1,
                    "id": "ProjectKnowledge/evidence/fixture-completion.yaml",
                    "module": "M00",
                    "evidence_class": "static",
                    "result": "passed",
                },
            )
            index = yaml.safe_load(index_path.read_text(encoding="utf-8"))
            index["evidence"].append("ProjectKnowledge/evidence/fixture-completion-path-id.yaml")
            write_yaml(index_path, index)
            completion = yaml.safe_load(completion_path.read_text(encoding="utf-8"))
            completion.update(module="M01", result="failed")
            write_yaml(completion_path, completion)
            report = audit_project(self.root)
            self.assertIn("PKI024", report["finding_code_counts"])

        with self.subTest(kind="pathlike_string_cannot_fall_back_to_id"):
            self._create_valid_fixture()
            pathlike_id_path = self.root / "ProjectKnowledge/evidence/fixture-completion-pathlike-id.yaml"
            write_yaml(
                pathlike_id_path,
                {
                    "schema_version": 1,
                    "id": "ProjectKnowledge/evidence/fixture-completion.yaml.evil",
                    "module": "M00",
                    "evidence_class": "static",
                    "result": "passed",
                },
            )
            index = yaml.safe_load(index_path.read_text(encoding="utf-8"))
            index["evidence"].append("ProjectKnowledge/evidence/fixture-completion-pathlike-id.yaml")
            write_yaml(index_path, index)
            queue = json.loads(queue_path.read_text(encoding="utf-8"))
            queue["modules"][0]["evidence"] = ["ProjectKnowledge/evidence/fixture-completion.yaml.evil"]
            write_queue(queue)
            report = audit_project(self.root)
            self.assertIn("PKI022", report["finding_code_counts"])

        for success_value in (
            True,
            "pass",
            "passed",
            "success",
            "successful",
            "succeeded",
            "complete",
            "completed",
            "accepted",
            "verified",
        ):
            with self.subTest(kind="success", success_value=success_value):
                self._create_valid_fixture()
                evidence = yaml.safe_load(completion_path.read_text(encoding="utf-8"))
                evidence["result"] = success_value
                write_yaml(completion_path, evidence)
                self.assertEqual(audit_project(self.root)["error_count"], 0)

        for failure_value in (
            False,
            "failed",
            "incomplete_retry",
            "refused",
            "pending",
            "passed_runtime_pending",
            {"gate": "passed"},
            ["passed"],
            None,
        ):
            with self.subTest(kind="failure", failure_value=failure_value):
                self._create_valid_fixture()
                evidence = yaml.safe_load(completion_path.read_text(encoding="utf-8"))
                if failure_value is None:
                    evidence.pop("result")
                else:
                    evidence["result"] = failure_value
                write_yaml(completion_path, evidence)
                report = audit_project(self.root)
                self.assertEqual(report["finding_code_counts"], {"PKI024": 1})

        with self.subTest(kind="contradictory_outcomes"):
            self._create_valid_fixture()
            evidence = yaml.safe_load(completion_path.read_text(encoding="utf-8"))
            evidence.update(result="passed", status="pending")
            write_yaml(completion_path, evidence)
            self.assertEqual(audit_project(self.root)["finding_code_counts"], {"PKI024": 1})

        for association in (
            {"module": "M00"},
            {"module": "module.M00.fixture"},
            {"module_id": "M00"},
            {"module": "module.M00.fixture", "module_id": "M00"},
        ):
            with self.subTest(kind="valid_association", association=association):
                self._create_valid_fixture()
                evidence = yaml.safe_load(completion_path.read_text(encoding="utf-8"))
                evidence.pop("module")
                evidence.update(association)
                write_yaml(completion_path, evidence)
                self.assertEqual(audit_project(self.root)["error_count"], 0)

        invalid_associations = (
            {},
            {"module": "M01"},
            {"module": "M000"},
            {"module": "fifty kilometre design export"},
            {"module": "audit note for M00 but not a module identifier"},
            {"module": "prefix/M00/suffix"},
            {"module": "M00", "module_id": "M01"},
            {"metadata": {"module": "M00"}},
            {"target": "M00"},
        )
        for association in invalid_associations:
            with self.subTest(kind="invalid_association", association=association):
                self._create_valid_fixture()
                evidence = yaml.safe_load(completion_path.read_text(encoding="utf-8"))
                evidence.pop("module")
                evidence.update(association)
                write_yaml(completion_path, evidence)
                report = audit_project(self.root)
                self.assertEqual(report["finding_code_counts"], {"PKI025": 1})

        invalid_policies = (None, "static", [], ["static", "static"], ["static_and_log_only"])
        for policy in invalid_policies:
            with self.subTest(kind="invalid_policy", policy=policy):
                self._create_valid_fixture()
                queue = json.loads(queue_path.read_text(encoding="utf-8"))
                if policy is None:
                    queue["modules"][0].pop("completion_evidence_classes")
                else:
                    queue["modules"][0]["completion_evidence_classes"] = policy
                write_queue(queue)
                findings = audit_project(self.root)["findings"]
                matching = [finding for finding in findings if finding["code"] == "PKI026"]
                self.assertEqual(len(matching), 1)
                self.assertEqual(matching[0]["path"], "queue.modules[0].completion_evidence_classes")

        for policy in (["build"], ["static", "build"]):
            with self.subTest(kind="missing_class_coverage", policy=policy):
                self._create_valid_fixture()
                queue = json.loads(queue_path.read_text(encoding="utf-8"))
                queue["modules"][0]["completion_evidence_classes"] = policy
                write_queue(queue)
                findings = audit_project(self.root)["findings"]
                matching = [finding for finding in findings if finding["code"] == "PKI026"]
                self.assertEqual(len(matching), 1)
                self.assertEqual(matching[0]["path"], "queue.modules[0].evidence")

        for malformed_class in ([], {"kind": "static"}):
            with self.subTest(kind="malformed_evidence_class_fails_closed", value=malformed_class):
                self._create_valid_fixture()
                evidence = yaml.safe_load(completion_path.read_text(encoding="utf-8"))
                evidence["evidence_class"] = malformed_class
                write_yaml(completion_path, evidence)
                report = audit_project(self.root)
                self.assertIn("PKI011", report["finding_code_counts"])
                self.assertIn("PKI026", report["finding_code_counts"])

        with self.subTest(kind="all_classes_covered"):
            self._create_valid_fixture()
            build_path = self.root / "ProjectKnowledge/evidence/fixture-completion-build.yaml"
            write_yaml(
                build_path,
                {
                    "schema_version": 1,
                    "id": "evidence.fixture.completion.build",
                    "module_id": "M00",
                    "evidence_class": "build",
                    "status": "verified",
                },
            )
            index = yaml.safe_load(index_path.read_text(encoding="utf-8"))
            index["evidence"].append("ProjectKnowledge/evidence/fixture-completion-build.yaml")
            write_yaml(index_path, index)
            queue = json.loads(queue_path.read_text(encoding="utf-8"))
            queue["modules"][0]["completion_evidence_classes"] = ["static", "build"]
            queue["modules"][0]["evidence"].append("evidence.fixture.completion.build")
            write_queue(queue)
            self.assertEqual(audit_project(self.root)["error_count"], 0)

    def test_defect_evidence_pointer_must_resolve(self):
        defect_path = self.root / "ProjectKnowledge/defects/DEF-FIXTURE.yaml"
        defect = yaml.safe_load(defect_path.read_text(encoding="utf-8"))
        defect["evidence"]["static"] = "ProjectKnowledge/evidence/not-there.yaml"
        write_yaml(defect_path, defect)
        self.assertIn("PKI014", self._codes())

    def test_evidence_requires_id_and_canonical_class(self):
        evidence_path = self.root / "ProjectKnowledge/evidence/fixture-static.yaml"
        evidence = yaml.safe_load(evidence_path.read_text(encoding="utf-8"))
        evidence.pop("id")
        evidence["evidence_class"] = "static_and_log_only"
        write_yaml(evidence_path, evidence)
        codes = self._codes()
        self.assertIn("PKI009", codes)
        self.assertIn("PKI012", codes)

        evidence["evidence_class"] = "static"
        evidence["result"] = "visual_accepted"
        write_yaml(evidence_path, evidence)
        self.assertIn("PKI013", self._codes())

        evidence["evidence_class"] = "automation"
        evidence["result"] = "passed"
        evidence["verification"] = {"visual_accepted": True}
        write_yaml(evidence_path, evidence)
        self.assertIn("PKI013", self._codes())

    def test_low_evidence_high_gate_semantics_are_token_aware(self):
        evidence_path = self.root / "ProjectKnowledge/evidence/fixture-static.yaml"
        evidence_location = "ProjectKnowledge/evidence/fixture-static.yaml"
        positive_fields = (
            ("static", "result", "visual_verified"),
            ("build", "status", "package_succeeded"),
            ("automation", "result", "runtime_verified"),
            ("static", "status", "gameplay_acceptance_succeeded"),
            ("build", "result", "visual_accepted"),
            ("automation", "status", "multiplayer_acceptance_passed"),
            ("static", "result", "visual_acceptance_verified"),
            ("static", "result", "visual_accepted_runtime_pending"),
            ("static", "result", "runtime_pending_visual_accepted"),
            ("static", "result", "runtime_unverified_visual_accepted"),
            ("static", "result", "runtime_acceptance_failed_visual_accepted"),
            ("static", "result", "runtime_verified_false_visual_accepted"),
            ("static", "result", "runtime_acceptance_succeeded_pending_visual_accepted"),
            ("static", "result", "package_failed_gameplay_verified"),
            ("static", "result", "runtime_verified_not_visual_accepted"),
            ("static", "result", "runtime_verified_not_yet_visual_accepted"),
        )
        for evidence_class, field_name, field_value in positive_fields:
            with self.subTest(kind="positive_field", field_value=field_value):
                self._create_valid_fixture()
                evidence = yaml.safe_load(evidence_path.read_text(encoding="utf-8"))
                evidence["evidence_class"] = evidence_class
                evidence[field_name] = field_value
                write_yaml(evidence_path, evidence)
                report = audit_project(self.root)
                gate_findings = [finding for finding in report["findings"] if finding["code"] == "PKI013"]
                self.assertEqual(len(gate_findings), 1)
                self.assertEqual(gate_findings[0]["path"], f"{evidence_location}.{field_name}")
                self.assertEqual(report["error_count"], 1)

        negative_fields = (
            "not_visual_accepted",
            "not_runtime_verified",
            "visual_acceptance_failed",
            "false",
            "rejected",
            "incomplete",
            "pending",
            "unverified",
            "unsuccessful",
            "runtime_unverified",
            "package_unsuccessful",
            "visual_accepted_false",
            "visual_accepted_not",
            "pending_visual_accepted",
            "not_visual_accepted_runtime_pending",
        )
        for field_value in negative_fields:
            with self.subTest(kind="negative_field", field_value=field_value):
                self._create_valid_fixture()
                evidence = yaml.safe_load(evidence_path.read_text(encoding="utf-8"))
                evidence["result"] = field_value
                write_yaml(evidence_path, evidence)
                report = audit_project(self.root)
                self.assertNotIn("PKI013", report["finding_code_counts"])
                self.assertEqual(report["error_count"], 0)

        nested_positive = (
            ({"verification": {"visual_accepted": "verified"}}, "verification.visual_accepted"),
            ({"gates": {"package_acceptance_passed": "succeeded"}}, "gates.package_acceptance_passed"),
        )
        for nested_value, nested_path in nested_positive:
            with self.subTest(kind="nested_positive", nested_path=nested_path):
                self._create_valid_fixture()
                evidence = yaml.safe_load(evidence_path.read_text(encoding="utf-8"))
                evidence.update(nested_value)
                write_yaml(evidence_path, evidence)
                report = audit_project(self.root)
                gate_findings = [finding for finding in report["findings"] if finding["code"] == "PKI013"]
                self.assertEqual(len(gate_findings), 1)
                self.assertEqual(gate_findings[0]["path"], f"{evidence_location}.{nested_path}")
                self.assertEqual(report["error_count"], 1)

        for nested_value in (False, "false", "rejected", "incomplete", "pending", "unverified", "unsuccessful"):
            with self.subTest(kind="nested_negative", nested_value=nested_value):
                self._create_valid_fixture()
                evidence = yaml.safe_load(evidence_path.read_text(encoding="utf-8"))
                evidence["verification"] = {"visual_accepted": nested_value}
                write_yaml(evidence_path, evidence)
                report = audit_project(self.root)
                self.assertNotIn("PKI013", report["finding_code_counts"])
                self.assertEqual(report["error_count"], 0)

        for evidence_class in ("real_gpu_visual", "player_playtest", "package", "multiplayer"):
            with self.subTest(kind="high_evidence_exempt", evidence_class=evidence_class):
                self._create_valid_fixture()
                evidence = yaml.safe_load(evidence_path.read_text(encoding="utf-8"))
                evidence["evidence_class"] = evidence_class
                evidence["result"] = "visual_verified"
                write_yaml(evidence_path, evidence)
                report = audit_project(self.root)
                self.assertNotIn("PKI013", report["finding_code_counts"])
                self.assertEqual(report["error_count"], 0)

    def test_hash_fields_require_full_sha256(self):
        state_path = self.root / "ProjectKnowledge/current_state.yaml"
        state = yaml.safe_load(state_path.read_text(encoding="utf-8"))
        state["protected_map_sha256"] = "exact"
        write_yaml(state_path, state)
        self.assertIn("PKI016", self._codes())

    def test_orphan_evidence_discovery_is_recursive_and_extension_complete(self):
        evidence_root = self.root / "ProjectKnowledge/evidence"
        orphan_paths = (
            "ProjectKnowledge/evidence/orphan.yaml",
            "ProjectKnowledge/evidence/nested/orphan.yml",
            "ProjectKnowledge/evidence/nested/deep/orphan.YAML",
            "ProjectKnowledge/evidence/.hidden/orphan.Yml",
        )
        for position, relative_path in enumerate(orphan_paths):
            write_yaml(
                self.root / relative_path,
                {
                    "schema_version": 1,
                    "id": f"evidence.orphan.{position}",
                    "evidence_class": "static",
                    "result": "passed",
                },
            )

        write_json(evidence_root / "nested/ignored.json", {"not": "evidence"})
        (evidence_root / "nested/ignored.yaml.bak").write_text("ignored\n", encoding="utf-8")
        (evidence_root / "nested/directory.yml").mkdir()

        report = audit_project(self.root)
        orphan_findings = [finding for finding in report["findings"] if finding["code"] == "PKI018"]
        self.assertEqual([finding["path"] for finding in orphan_findings], sorted(orphan_paths))
        self.assertEqual(report["finding_code_counts"], {"PKI018": len(orphan_paths)})

        index_path = self.root / "ProjectKnowledge/INDEX.yaml"
        index = yaml.safe_load(index_path.read_text(encoding="utf-8"))
        index["evidence"].extend(orphan_paths)
        write_yaml(index_path, index)
        report = audit_project(self.root)
        self.assertNotIn("PKI018", report["finding_code_counts"])
        self.assertEqual(report["error_count"], 0)

    def test_orphan_discovery_refuses_linked_directory_when_supported(self):
        evidence_root = self.root / "ProjectKnowledge/evidence"
        outside_evidence = self.root / "ProjectKnowledge/outside-evidence"
        write_yaml(
            outside_evidence / "hidden-orphan.yaml",
            {
                "schema_version": 1,
                "id": "evidence.hidden.behind.link",
                "evidence_class": "static",
                "result": "passed",
            },
        )
        linked_directory = evidence_root / "linked"
        self._create_directory_link(linked_directory, outside_evidence)
        try:
            report = audit_project(self.root)
        finally:
            self._remove_directory_link(linked_directory)

        matching = [
            finding
            for finding in report["findings"]
            if finding["code"] == "PKI018"
            and finding["path"] == "ProjectKnowledge/evidence/linked"
        ]
        self.assertEqual(len(matching), 1)
        self.assertEqual(matching[0]["message"], "linked evidence directory cannot be recursively audited")
        self.assertEqual(report["finding_code_counts"], {"PKI018": 1})

    def test_orphan_discovery_refuses_linked_root_fail_closed(self):
        evidence_root = self.root / "ProjectKnowledge/evidence"

        with mock.patch(
            "Tools.audit_project_knowledge_integrity._is_link_or_reparse_point",
            side_effect=lambda path: path == evidence_root,
        ):
            report = audit_project(self.root)

        matching = [
            finding
            for finding in report["findings"]
            if finding["code"] == "PKI018"
            and finding["path"] == "ProjectKnowledge/evidence"
        ]
        self.assertEqual(len(matching), 1)
        self.assertEqual(matching[0]["message"], "linked evidence directory cannot be recursively audited")

    def test_orphan_discovery_refuses_linked_file_entry_fail_closed(self):
        linked_file = self.root / "ProjectKnowledge/evidence/nested/linked.yaml"
        write_yaml(
            linked_file,
            {
                "schema_version": 1,
                "id": "evidence.simulated.linked.file",
                "evidence_class": "static",
                "result": "passed",
            },
        )

        with mock.patch(
            "Tools.audit_project_knowledge_integrity._is_link_or_reparse_point",
            side_effect=lambda path: path == linked_file,
        ):
            report = audit_project(self.root)

        matching = [
            finding
            for finding in report["findings"]
            if finding["code"] == "PKI018"
            and finding["path"] == "ProjectKnowledge/evidence/nested/linked.yaml"
        ]
        self.assertEqual(len(matching), 1)
        self.assertEqual(matching[0]["message"], "linked evidence entry cannot be safely audited")
        self.assertEqual(report["finding_code_counts"], {"PKI018": 1})

    def test_orphan_discovery_reports_scan_error_deterministically(self):
        unreadable_directory = self.root / "ProjectKnowledge/evidence/unreadable"
        unreadable_directory.mkdir()

        def classify_entry(path: Path) -> bool:
            if path == unreadable_directory:
                raise PermissionError(13, "localized detail is intentionally excluded", str(path))
            return False

        with mock.patch(
            "Tools.audit_project_knowledge_integrity._is_link_or_reparse_point",
            side_effect=classify_entry,
        ):
            report = audit_project(self.root)

        matching = [
            finding
            for finding in report["findings"]
            if finding["code"] == "PKI018"
            and finding["path"] == "ProjectKnowledge/evidence/unreadable"
        ]
        self.assertEqual(len(matching), 1)
        self.assertEqual(
            matching[0]["message"],
            "evidence discovery could not inspect path (PermissionError, errno=13)",
        )
        self.assertEqual(report["finding_code_counts"], {"PKI018": 1})

    def test_orphan_discovery_missing_root_fails_closed(self):
        evidence_root = self.root / "ProjectKnowledge/evidence"
        shutil.rmtree(evidence_root)

        report = audit_project(self.root)
        matching = [
            finding
            for finding in report["findings"]
            if finding["code"] == "PKI018"
            and finding["path"] == "ProjectKnowledge/evidence"
        ]
        self.assertEqual(len(matching), 1)
        self.assertEqual(matching[0]["message"], "evidence discovery path does not exist")

    def test_queue_and_current_state_record_links_must_resolve(self):
        queue_path = self.root / "Build/Automation/redmmotitan_module_queue.json"
        queue = json.loads(queue_path.read_text(encoding="utf-8"))
        queue["modules"][1]["evidence"] = [
            "Evidence: ProjectKnowledge/evidence/missing-from-queue.yaml"
        ]
        write_json(queue_path, queue)

        state_path = self.root / "ProjectKnowledge/current_state.yaml"
        state = yaml.safe_load(state_path.read_text(encoding="utf-8"))
        state["evidence"] = ["ProjectKnowledge/evidence/missing-from-state.yaml"]
        state["queue"]["snapshot_sha256"] = hashlib.sha256(queue_path.read_bytes()).hexdigest().upper()
        write_yaml(state_path, state)

        codes = self._codes()
        self.assertEqual(codes.count("PKI019"), 2)

    def test_current_state_queue_wrong_shapes_report_instead_of_raising(self):
        state_path = self.root / "ProjectKnowledge/current_state.yaml"
        for malformed in ("oops", [], True, 1, None):
            with self.subTest(malformed=malformed):
                write_yaml(state_path, {"schema_version": 1, "queue": malformed})
                report = audit_project(self.root)
                self.assertEqual(report["result"], "fail")
                self.assertEqual(
                    [
                        finding["code"] == "PKI020"
                        and finding["path"] == "ProjectKnowledge/current_state.yaml.queue"
                        and finding["message"] == "queue must be a mapping"
                        for finding in report["findings"]
                    ].count(True),
                    1,
                )
                self.assertEqual(report["finding_code_counts"].get("PKI015"), 1)

    def test_schema_version_requires_exact_integer_one_for_every_indexed_record(self):
        missing = object()
        invalid_values = (True, False, 1.0, 2.0, 0, 2, "1", None, missing)
        targets = (
            ("ProjectKnowledge/INDEX.yaml", "yaml"),
            ("Build/Automation/redmmotitan_module_queue.json", "json"),
            ("ProjectKnowledge/current_state.yaml", "yaml"),
            ("ProjectKnowledge/invariants.yaml", "yaml"),
            ("ProjectKnowledge/systems/fixture.yml", "yaml"),
            ("ProjectKnowledge/evidence/fixture-static.yaml", "yaml"),
            ("ProjectKnowledge/defects/DEF-FIXTURE.yaml", "yaml"),
        )

        for relative_path, record_format in targets:
            for invalid_value in invalid_values:
                with self.subTest(relative_path=relative_path, invalid_value=invalid_value):
                    self._create_valid_fixture()
                    path = self.root / relative_path
                    if record_format == "json":
                        record = json.loads(path.read_text(encoding="utf-8"))
                    else:
                        record = yaml.safe_load(path.read_text(encoding="utf-8"))

                    if invalid_value is missing:
                        record.pop("schema_version")
                    else:
                        record["schema_version"] = invalid_value

                    if record_format == "json":
                        write_json(path, record)
                        state_path = self.root / "ProjectKnowledge/current_state.yaml"
                        state = yaml.safe_load(state_path.read_text(encoding="utf-8"))
                        state["queue"]["snapshot_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest().upper()
                        write_yaml(state_path, state)
                    else:
                        write_yaml(path, record)

                    report = audit_project(self.root)
                    schema_findings = [
                        finding
                        for finding in report["findings"]
                        if finding["code"] == "PKI020"
                        and finding["path"] == relative_path
                        and finding["message"] == "schema_version must be integer 1"
                    ]
                    self.assertEqual(len(schema_findings), 1)
                    self.assertEqual(report["error_count"], 1)

    def test_canonical_state_and_invariants_schema_checked_without_index_routes(self):
        index_path = self.root / "ProjectKnowledge/INDEX.yaml"
        index = yaml.safe_load(index_path.read_text(encoding="utf-8"))
        index["authoritative_sources"].pop("current_snapshot")
        index["authoritative_sources"].pop("invariants")
        write_yaml(index_path, index)

        state_path = self.root / "ProjectKnowledge/current_state.yaml"
        state = yaml.safe_load(state_path.read_text(encoding="utf-8"))
        state["schema_version"] = True
        write_yaml(state_path, state)

        invariants_path = self.root / "ProjectKnowledge/invariants.yaml"
        invariants = yaml.safe_load(invariants_path.read_text(encoding="utf-8"))
        invariants.pop("schema_version")
        write_yaml(invariants_path, invariants)

        report = audit_project(self.root)
        schema_paths = {
            finding["path"]
            for finding in report["findings"]
            if finding["code"] == "PKI020"
            and finding["message"] == "schema_version must be integer 1"
        }
        self.assertEqual(
            schema_paths,
            {"ProjectKnowledge/current_state.yaml", "ProjectKnowledge/invariants.yaml"},
        )
        self.assertEqual(report["error_count"], 2)

    def test_cli_fails_closed_but_can_write_a_failed_diagnostic(self):
        evidence_path = self.root / "ProjectKnowledge/evidence/fixture-static.yaml"
        evidence = yaml.safe_load(evidence_path.read_text(encoding="utf-8"))
        evidence.pop("evidence_class")
        write_yaml(evidence_path, evidence)
        output = self.diagnostics_root / "integrity.json"

        self.assertEqual(main(["--project-root", str(self.root), "--output", str(output)]), 1)
        report = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(report["result"], "fail")
        self.assertIn("PKI011", report["finding_code_counts"])

        index_path = self.root / "ProjectKnowledge/INDEX.yaml"
        original_index = index_path.read_bytes()
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                main(["--project-root", str(self.root), "--output", str(index_path)])
        self.assertEqual(index_path.read_bytes(), original_index)


if __name__ == "__main__":
    unittest.main()
