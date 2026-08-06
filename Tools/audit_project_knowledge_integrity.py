"""Fail-closed structural audit for RedMMOTitan's canonical project knowledge.

This tool is deliberately offline. It reads ProjectKnowledge plus the module
queue, never imports Unreal, and writes only the optional JSON report selected
by the caller.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

import yaml


CANONICAL_EVIDENCE_CLASSES = {
    "static",
    "build",
    "automation",
    "real_gpu_visual",
    "player_playtest",
    "package",
    "multiplayer",
}

COMPLETION_SUCCESS_VALUES = {
    "accepted",
    "complete",
    "completed",
    "pass",
    "passed",
    "success",
    "successful",
    "succeeded",
    "verified",
}
LOW_EVIDENCE_CLASSES = {"static", "build", "automation"}
HIGH_GATE_SUBJECT_TOKENS = {"runtime", "visual", "gameplay", "package", "multiplayer"}
HIGH_GATE_DIRECT_AFFIRMATIVE_TOKENS = {"accepted", "verified", "succeeded"}
HIGH_GATE_ACCEPTANCE_AFFIRMATIVE_TOKENS = {"passed", "verified", "succeeded"}
HIGH_GATE_PREFIX_NEGATION_TOKENS = {"never", "no", "not", "without"}
HIGH_GATE_NEGATIVE_OUTCOME_TOKENS = {
    "blocked",
    "deferred",
    "denied",
    "fail",
    "failed",
    "failure",
    "false",
    "incomplete",
    "missing",
    "open",
    "pending",
    "refused",
    "rejected",
    "unsuccessful",
    "unverified",
}
SHA256_PATTERN = re.compile(r"[0-9A-Fa-f]{64}")
EVIDENCE_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*")
REPO_RECORD_POINTER_PATTERN = re.compile(
    r"(?:^|(?<=[\s(\[<{\x27\x60\"]))"
    r"ProjectKnowledge/[A-Za-z0-9_.\-/]+\.ya?ml"
    r"(?=$|\s|[)\]}>.,;:\x27\x60\"]+(?:$|\s))"
)
HIGH_GATE_FIELD_NAMES = {
    "visual_accepted",
    "visual_acceptance_passed",
    "gameplay_accepted",
    "gameplay_acceptance_passed",
    "package_accepted",
    "package_acceptance_passed",
    "multiplayer_accepted",
    "multiplayer_acceptance_passed",
    "runtime_verified",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def _finding(code: str, path: str, message: str, severity: str = "error") -> dict[str, str]:
    return {
        "severity": severity,
        "code": code,
        "path": path,
        "message": message,
    }


def _load_mapping(path: Path, findings: list[dict[str, str]], code: str) -> dict[str, Any] | None:
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover - exact parser wording is environment-owned
        findings.append(_finding(code, str(path), f"YAML parse failed: {exc}"))
        return None
    if not isinstance(value, dict):
        findings.append(_finding(code, str(path), "record must be a YAML mapping"))
        return None
    return value


def _safe_repo_path(project_root: Path, raw_path: Any) -> tuple[Path | None, str | None]:
    if not isinstance(raw_path, str) or not raw_path.strip():
        return None, "path must be a non-empty string"
    if raw_path != raw_path.strip():
        return None, "path must not contain leading or trailing whitespace"
    if "\\" in raw_path:
        return None, "path must use forward slashes"
    raw_parts = raw_path.split("/")
    if any(part in {"", ".", ".."} for part in raw_parts):
        return None, "path must not contain empty, dot, or parent segments"
    posix_path = PurePosixPath(raw_path)
    if posix_path.is_absolute() or ":" in raw_parts[0]:
        return None, "path must be repository-relative"

    root_resolved = project_root.resolve()
    candidate = project_root.joinpath(*posix_path.parts).resolve()
    try:
        candidate.relative_to(root_resolved)
    except ValueError:
        return None, "path escapes the repository"
    return candidate, None


def _repo_relative_display(project_root: Path, path: Path) -> str:
    try:
        return path.relative_to(project_root).as_posix()
    except ValueError:
        return path.as_posix()


def _is_link_or_reparse_point(path: Path) -> bool:
    metadata = path.lstat()
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    file_attributes = getattr(metadata, "st_file_attributes", 0)
    return path.is_symlink() or bool(reparse_flag and file_attributes & reparse_flag)


def _discover_evidence_yaml_files(
    project_root: Path,
    evidence_directory: Path,
    findings: list[dict[str, str]],
) -> list[Path]:
    def record_walk_error(error: OSError, fallback_path: Path | None = None) -> None:
        raw_path = getattr(error, "filename", None)
        failed_path = Path(raw_path) if isinstance(raw_path, str) and raw_path else (fallback_path or evidence_directory)
        error_details = [type(error).__name__]
        error_number = getattr(error, "errno", None)
        windows_error = getattr(error, "winerror", None)
        if error_number is not None:
            error_details.append(f"errno={error_number}")
        if windows_error is not None and windows_error != error_number:
            error_details.append(f"winerror={windows_error}")
        findings.append(
            _finding(
                "PKI018",
                _repo_relative_display(project_root, failed_path),
                f"evidence discovery could not inspect path ({', '.join(error_details)})",
            )
        )

    try:
        relative_root = evidence_directory.relative_to(project_root)
    except ValueError:
        findings.append(
            _finding(
                "PKI018",
                _repo_relative_display(project_root, evidence_directory),
                "evidence discovery root must remain within the repository",
            )
        )
        return []

    current_directory = project_root
    for path_part in relative_root.parts:
        current_directory /= path_part
        try:
            if _is_link_or_reparse_point(current_directory):
                findings.append(
                    _finding(
                        "PKI018",
                        _repo_relative_display(project_root, current_directory),
                        "linked evidence directory cannot be recursively audited",
                    )
                )
                return []
        except FileNotFoundError:
            findings.append(
                _finding(
                    "PKI018",
                    _repo_relative_display(project_root, current_directory),
                    "evidence discovery path does not exist",
                )
            )
            return []
        except OSError as exc:
            record_walk_error(exc, current_directory)
            return []

    if not evidence_directory.is_dir():
        findings.append(
            _finding(
                "PKI018",
                _repo_relative_display(project_root, evidence_directory),
                "evidence discovery root must be a directory",
            )
        )
        return []

    discovered: list[Path] = []

    for raw_directory, directory_names, file_names in os.walk(
        evidence_directory,
        topdown=True,
        onerror=record_walk_error,
        followlinks=False,
    ):
        directory = Path(raw_directory)
        traversable_directories: list[str] = []
        for directory_name in sorted(directory_names, key=lambda value: (value.casefold(), value)):
            candidate = directory / directory_name
            try:
                if _is_link_or_reparse_point(candidate):
                    findings.append(
                        _finding(
                            "PKI018",
                            _repo_relative_display(project_root, candidate),
                            "linked evidence directory cannot be recursively audited",
                        )
                    )
                else:
                    traversable_directories.append(directory_name)
            except OSError as exc:
                record_walk_error(exc)
        directory_names[:] = traversable_directories

        for file_name in sorted(file_names, key=lambda value: (value.casefold(), value)):
            candidate = directory / file_name
            try:
                if _is_link_or_reparse_point(candidate):
                    findings.append(
                        _finding(
                            "PKI018",
                            _repo_relative_display(project_root, candidate),
                            "linked evidence entry cannot be safely audited",
                        )
                    )
                    continue
            except OSError as exc:
                record_walk_error(exc, candidate)
                continue
            if candidate.suffix.casefold() in {".yaml", ".yml"}:
                discovered.append(candidate)

    return sorted(
        discovered,
        key=lambda path: (_repo_relative_display(project_root, path).casefold(), _repo_relative_display(project_root, path)),
    )


def _validate_schema_version(record: dict[str, Any], location: str, findings: list[dict[str, str]]) -> None:
    schema_version = record.get("schema_version")
    if type(schema_version) is not int or schema_version != 1:
        findings.append(_finding("PKI020", location, "schema_version must be integer 1"))


def _validate_index_sections(index: dict[str, Any], findings: list[dict[str, str]]) -> None:
    mapping_sections = ("authoritative_sources", "templates", "acceptance")
    list_sections = ("domain_specs", "references", "systems", "evidence", "defects", "playtests", "decisions")
    for section in mapping_sections:
        value = index.get(section)
        if value is not None and not isinstance(value, dict):
            findings.append(_finding("PKI020", f"INDEX.{section}", "section must be a mapping"))
    for section in list_sections:
        value = index.get(section)
        if value is not None and not isinstance(value, list):
            findings.append(_finding("PKI020", f"INDEX.{section}", "section must be a list"))

    authoritative_sources = index.get("authoritative_sources")
    if isinstance(authoritative_sources, dict):
        for name, value in authoritative_sources.items():
            if not isinstance(value, dict) or "path" not in value:
                findings.append(
                    _finding(
                        "PKI020",
                        f"INDEX.authoritative_sources.{name}",
                        "entry must be a mapping with a path",
                    )
                )

    domain_specs = index.get("domain_specs")
    if isinstance(domain_specs, list):
        for position, value in enumerate(domain_specs):
            if not isinstance(value, dict) or "path" not in value:
                findings.append(
                    _finding(
                        "PKI020",
                        f"INDEX.domain_specs[{position}]",
                        "entry must be a mapping with a path",
                    )
                )


def _iter_index_routes(index: dict[str, Any]) -> Iterable[tuple[str, Any]]:
    authoritative_sources = index.get("authoritative_sources")
    if not isinstance(authoritative_sources, dict):
        authoritative_sources = {}
    for name, value in authoritative_sources.items():
        if isinstance(value, dict) and "path" in value:
            yield f"authoritative_sources.{name}", value["path"]

    domain_specs = index.get("domain_specs")
    if not isinstance(domain_specs, list):
        domain_specs = []
    for position, value in enumerate(domain_specs):
        if isinstance(value, dict) and "path" in value:
            yield f"domain_specs[{position}]", value["path"]

    templates = index.get("templates")
    if not isinstance(templates, dict):
        templates = {}
    for name, value in templates.items():
        yield f"templates.{name}", value

    for section in ("references", "systems", "evidence", "defects", "playtests", "decisions"):
        values = index.get(section)
        if not isinstance(values, list):
            values = []
        for position, value in enumerate(values):
            yield f"{section}[{position}]", value

    acceptance = index.get("acceptance")
    if not isinstance(acceptance, dict):
        acceptance = {}
    for name, value in acceptance.items():
        yield f"acceptance.{name}", value


def _walk_repo_record_pointers(value: Any, location: str = "") -> Iterable[tuple[str, str]]:
    if isinstance(value, dict):
        for key, child in value.items():
            child_location = f"{location}.{key}" if location else str(key)
            yield from _walk_repo_record_pointers(child, child_location)
    elif isinstance(value, list):
        for position, child in enumerate(value):
            yield from _walk_repo_record_pointers(child, f"{location}[{position}]")
    elif isinstance(value, str) and value.startswith("ProjectKnowledge/"):
        yield location, value


def _walk_embedded_repo_record_pointers(value: Any, location: str = "") -> Iterable[tuple[str, str]]:
    if isinstance(value, dict):
        for key, child in value.items():
            child_location = f"{location}.{key}" if location else str(key)
            yield from _walk_embedded_repo_record_pointers(child, child_location)
    elif isinstance(value, list):
        for position, child in enumerate(value):
            yield from _walk_embedded_repo_record_pointers(child, f"{location}[{position}]")
    elif isinstance(value, str):
        for match in REPO_RECORD_POINTER_PATTERN.finditer(value):
            yield location, match.group(0)


def _walk_high_gate_claims(value: Any, location: str = "") -> Iterable[tuple[str, Any]]:
    if isinstance(value, dict):
        for key, child in value.items():
            child_location = f"{location}.{key}" if location else str(key)
            if str(key).casefold() in HIGH_GATE_FIELD_NAMES:
                yield child_location, child
            yield from _walk_high_gate_claims(child, child_location)
    elif isinstance(value, list):
        for position, child in enumerate(value):
            yield from _walk_high_gate_claims(child, f"{location}[{position}]")


def _walk_strings(value: Any) -> Iterable[str]:
    if isinstance(value, dict):
        for child in value.values():
            yield from _walk_strings(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_strings(child)
    elif isinstance(value, str):
        yield value


def _is_affirmative_claim(value: Any) -> bool:
    if value is True:
        return True
    if isinstance(value, str):
        return value.strip().casefold() in {
            "true",
            "yes",
            "pass",
            "passed",
            "accepted",
            "complete",
            "completed",
            "verified",
            "succeeded",
        }
    return False


def _has_affirmative_high_gate_result(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    tokens = re.findall(r"[a-z0-9]+", value.casefold())

    def negative_outcome_belongs_to_previous_gate(negative_position: int) -> bool:
        for subject_position in range(max(0, negative_position - 3), negative_position):
            if tokens[subject_position] not in HIGH_GATE_SUBJECT_TOKENS:
                continue
            between = tokens[subject_position + 1 : negative_position]
            if between in (
                [],
                ["acceptance"],
            ):
                return True
            if len(between) == 1 and between[0] in HIGH_GATE_DIRECT_AFFIRMATIVE_TOKENS:
                return True
            if (
                len(between) == 2
                and between[0] == "acceptance"
                and between[1] in HIGH_GATE_ACCEPTANCE_AFFIRMATIVE_TOKENS
            ):
                return True
        return False

    def prefix_negation_starts_next_gate(negative_position: int) -> bool:
        if negative_position + 1 < len(tokens) and tokens[negative_position + 1] in HIGH_GATE_SUBJECT_TOKENS:
            return True
        return (
            negative_position + 2 < len(tokens)
            and tokens[negative_position + 1] == "yet"
            and tokens[negative_position + 2] in HIGH_GATE_SUBJECT_TOKENS
        )

    for position, subject in enumerate(tokens):
        if subject not in HIGH_GATE_SUBJECT_TOKENS:
            continue
        if position > 0 and tokens[position - 1] in HIGH_GATE_PREFIX_NEGATION_TOKENS:
            continue
        if position > 1 and tokens[position - 2 : position] == ["not", "yet"]:
            continue
        if (
            position > 0
            and tokens[position - 1] in HIGH_GATE_NEGATIVE_OUTCOME_TOKENS
            and not negative_outcome_belongs_to_previous_gate(position - 1)
        ):
            continue

        end_position: int | None = None
        if position + 1 < len(tokens) and tokens[position + 1] in HIGH_GATE_DIRECT_AFFIRMATIVE_TOKENS:
            end_position = position + 2
        elif (
            position + 2 < len(tokens)
            and tokens[position + 1] == "acceptance"
            and tokens[position + 2] in HIGH_GATE_ACCEPTANCE_AFFIRMATIVE_TOKENS
        ):
            end_position = position + 3

        if end_position is None:
            continue
        if end_position < len(tokens):
            suffix = tokens[end_position]
            if suffix in HIGH_GATE_NEGATIVE_OUTCOME_TOKENS:
                continue
            if suffix in HIGH_GATE_PREFIX_NEGATION_TOKENS and not prefix_negation_starts_next_gate(end_position):
                continue
        return True
    return False


def _walk_hash_fields(value: Any, location: str = "") -> Iterable[tuple[str, Any]]:
    if isinstance(value, dict):
        for key, child in value.items():
            child_location = f"{location}.{key}" if location else str(key)
            key_lower = str(key).lower()
            is_hash_name = key_lower == "sha256" or key_lower.endswith("_sha256")
            is_boolean_capability = isinstance(child, bool) and (
                key_lower.startswith("report_contains_")
                or key_lower.startswith("contains_")
                or key_lower.startswith("has_")
            )
            if is_hash_name and not is_boolean_capability:
                yield child_location, child
            yield from _walk_hash_fields(child, child_location)
    elif isinstance(value, list):
        for position, child in enumerate(value):
            yield from _walk_hash_fields(child, f"{location}[{position}]")


def _audit_module_queue(queue: dict[str, Any], findings: list[dict[str, str]]) -> dict[str, Any]:
    modules = queue.get("modules")
    if not isinstance(modules, list):
        findings.append(_finding("PKI004", "queue.modules", "modules must be a list"))
        return {"module_count": 0, "m10_dependencies": []}

    allowed_statuses = set(queue.get("status_values") or [])
    module_ids: dict[str, str] = {}
    for position, module in enumerate(modules):
        location = f"queue.modules[{position}]"
        if not isinstance(module, dict):
            findings.append(_finding("PKI004", location, "module must be a mapping"))
            continue
        module_id = module.get("id")
        if not isinstance(module_id, str) or not module_id:
            findings.append(_finding("PKI004", location, "module id is required"))
        elif module_id.casefold() in module_ids:
            findings.append(
                _finding(
                    "PKI004",
                    location,
                    f"duplicate module id {module_id!r}; first seen at {module_ids[module_id.casefold()]}",
                )
            )
        else:
            module_ids[module_id.casefold()] = location

        status = module.get("status")
        if status not in allowed_statuses:
            findings.append(_finding("PKI005", location, f"unsupported module status {status!r}"))

        retry_count = module.get("retry_count", 0)
        if not isinstance(retry_count, int) or isinstance(retry_count, bool) or retry_count < 0:
            findings.append(_finding("PKI007", location, "retry_count must be a non-negative integer"))
            retry_count = 0
        blocker = module.get("last_blocker")
        if (retry_count > 0 or status in {"incomplete_retry", "blocked"}) and not (
            isinstance(blocker, str) and blocker.strip()
        ):
            findings.append(_finding("PKI007", location, "retry or blocked module requires a non-empty last_blocker"))
        if status in {"incomplete_retry", "blocked"} and retry_count < 1:
            findings.append(_finding("PKI007", location, "blocked module requires retry_count >= 1"))
        if status == "completed" and not module.get("evidence"):
            findings.append(_finding("PKI008", location, "completed module requires evidence"))

    valid_ids = set(module_ids)
    for position, module in enumerate(modules):
        if not isinstance(module, dict):
            continue
        for dependency in module.get("dependencies") or []:
            if not isinstance(dependency, str) or dependency.casefold() not in valid_ids:
                findings.append(
                    _finding(
                        "PKI006",
                        f"queue.modules[{position}].dependencies",
                        f"unknown module dependency {dependency!r}",
                    )
                )

    module_by_id = {
        module.get("id"): module for module in modules if isinstance(module, dict) and isinstance(module.get("id"), str)
    }
    for position, module in enumerate(modules):
        if not isinstance(module, dict) or module.get("status") != "completed":
            continue
        incomplete_dependencies = [
            dependency
            for dependency in module.get("dependencies") or []
            if (module_by_id.get(dependency) or {}).get("status") != "completed"
        ]
        if incomplete_dependencies:
            findings.append(
                _finding(
                    "PKI023",
                    f"queue.modules[{position}].dependencies",
                    f"completed module has incomplete dependencies: {incomplete_dependencies}",
                )
            )

    m10 = module_by_id.get("M10", {})
    m10_dependencies = [
        {
            "id": dependency,
            "status": (module_by_id.get(dependency) or {}).get("status", "missing"),
        }
        for dependency in m10.get("dependencies") or []
    ]
    return {"module_count": len(modules), "m10_dependencies": m10_dependencies}


def _is_explicit_completion_success(value: Any) -> bool:
    if value is True:
        return True
    return isinstance(value, str) and value.strip().casefold() in COMPLETION_SUCCESS_VALUES


def _record_has_explicit_completion_success(record: dict[str, Any]) -> bool:
    outcomes = [record[field_name] for field_name in ("result", "status") if field_name in record]
    return bool(outcomes) and all(_is_explicit_completion_success(value) for value in outcomes)


def _record_associates_completed_module(record: dict[str, Any], module_id: str) -> bool:
    checks: list[bool] = []
    if "module_id" in record:
        module_id_value = record["module_id"]
        checks.append(
            isinstance(module_id_value, str)
            and module_id_value == module_id_value.strip()
            and module_id_value.casefold() == module_id.casefold()
        )
    if "module" in record:
        module_value = record["module"]
        if isinstance(module_value, str) and module_value == module_value.strip():
            folded_value = module_value.casefold()
            folded_id = module_id.casefold()
            namespace = f"module.{folded_id}"
            if folded_value in {folded_id, namespace}:
                checks.append(True)
            elif folded_value.startswith(f"{namespace}."):
                suffix_segments = folded_value[len(namespace) + 1 :].split(".")
                checks.append(
                    all(
                        re.fullmatch(r"[a-z0-9][a-z0-9_-]*", segment) is not None
                        for segment in suffix_segments
                    )
                )
            else:
                checks.append(False)
        else:
            checks.append(False)
    return bool(checks) and all(checks)


def _completion_evidence_class_policy(module: dict[str, Any]) -> list[str] | None:
    value = module.get("completion_evidence_classes")
    if not isinstance(value, list) or not value:
        return None
    if any(not isinstance(item, str) or item not in CANONICAL_EVIDENCE_CLASSES for item in value):
        return None
    if len(set(value)) != len(value):
        return None
    return value


def _audit_completed_module_evidence(
    queue: dict[str, Any],
    evidence_records_by_path: dict[str, dict[str, Any]],
    evidence_ids: dict[str, str],
    ambiguous_evidence_ids: set[str],
    findings: list[dict[str, str]],
) -> None:
    modules = queue.get("modules")
    if not isinstance(modules, list):
        return
    for position, module in enumerate(modules):
        if not isinstance(module, dict) or module.get("status") != "completed":
            continue
        evidence_values = module.get("evidence")
        if (
            not isinstance(evidence_values, list)
            or not evidence_values
            or any(not isinstance(value, str) or not value.strip() for value in evidence_values)
        ):
            findings.append(
                _finding(
                    "PKI022",
                    f"queue.modules[{position}].evidence",
                    "completed module evidence must be a non-empty flat list of strings",
                )
            )
            continue
        resolved_paths: list[str] = []
        for value in evidence_values:
            path_matches = list(REPO_RECORD_POINTER_PATTERN.finditer(value))
            for match in path_matches:
                raw_path = match.group(0)
                if raw_path in evidence_records_by_path:
                    resolved_paths.append(raw_path)
            if not path_matches:
                candidate_id = value.strip()
                folded = candidate_id.casefold()
                if (
                    EVIDENCE_ID_PATTERN.fullmatch(candidate_id)
                    and folded in evidence_ids
                    and folded not in ambiguous_evidence_ids
                ):
                    resolved_paths.append(evidence_ids[folded])
        resolved_paths = list(dict.fromkeys(resolved_paths))
        if not resolved_paths:
            findings.append(
                _finding(
                    "PKI022",
                    f"queue.modules[{position}].evidence",
                    "completed module requires at least one resolvable indexed evidence ID or path",
                )
            )
            continue

        successful_records = [
            evidence_records_by_path[path]
            for path in resolved_paths
            if _record_has_explicit_completion_success(evidence_records_by_path[path])
        ]
        if not successful_records:
            findings.append(
                _finding(
                    "PKI024",
                    f"queue.modules[{position}].evidence",
                    "completed module requires an explicitly successful top-level evidence result or status",
                )
            )
            continue

        module_id = module.get("id")
        associated_records = [
            record
            for record in successful_records
            if isinstance(module_id, str) and _record_associates_completed_module(record, module_id)
        ]
        if not associated_records:
            findings.append(
                _finding(
                    "PKI025",
                    f"queue.modules[{position}].evidence",
                    f"successful evidence must explicitly associate with completed module {module_id!r}",
                )
            )
            continue

        required_classes = _completion_evidence_class_policy(module)
        if required_classes is None:
            findings.append(
                _finding(
                    "PKI026",
                    f"queue.modules[{position}].completion_evidence_classes",
                    "completed module requires a non-empty unique list of canonical evidence classes",
                )
            )
            continue

        covered_classes = {
            record.get("evidence_class")
            for record in associated_records
            if isinstance(record.get("evidence_class"), str)
            and record.get("evidence_class") in CANONICAL_EVIDENCE_CLASSES
        }
        missing_classes = [value for value in required_classes if value not in covered_classes]
        if missing_classes:
            findings.append(
                _finding(
                    "PKI026",
                    f"queue.modules[{position}].evidence",
                    f"successful associated evidence does not cover required classes: {missing_classes}",
                )
            )


def audit_project(project_root: Path) -> dict[str, Any]:
    project_root = project_root.resolve()
    findings: list[dict[str, str]] = []
    index_path = project_root / "ProjectKnowledge/INDEX.yaml"
    if not index_path.is_file():
        findings.append(_finding("PKI001", "ProjectKnowledge/INDEX.yaml", "canonical index is missing"))
        return _finish_report(project_root, findings, {})

    index = _load_mapping(index_path, findings, "PKI001")
    if index is None:
        return _finish_report(project_root, findings, {})
    _validate_schema_version(index, "ProjectKnowledge/INDEX.yaml", findings)
    validated_schema_paths = {os.path.normcase(str(index_path.resolve()))}
    _validate_index_sections(index, findings)

    indexed_routes: dict[str, Path] = {}
    for location, raw_path in _iter_index_routes(index):
        candidate, error = _safe_repo_path(project_root, raw_path)
        if error:
            findings.append(_finding("PKI002", f"INDEX.{location}", f"{raw_path!r}: {error}"))
            continue
        assert candidate is not None
        indexed_routes[str(raw_path)] = candidate
        if not candidate.is_file():
            findings.append(_finding("PKI003", f"INDEX.{location}", f"indexed record is missing: {raw_path}"))

    for raw_path, candidate in indexed_routes.items():
        if not candidate.is_file() or candidate.suffix.casefold() not in {".yaml", ".yml"}:
            continue
        try:
            indexed_record = yaml.safe_load(candidate.read_text(encoding="utf-8"))
        except Exception as exc:  # pragma: no cover - exact parser wording is environment-owned
            findings.append(_finding("PKI021", raw_path, f"indexed YAML parse failed: {exc}"))
            continue
        if isinstance(indexed_record, dict):
            normalized_path = os.path.normcase(str(candidate.resolve()))
            if normalized_path not in validated_schema_paths:
                _validate_schema_version(indexed_record, raw_path, findings)
                validated_schema_paths.add(normalized_path)

    invariants_path = project_root / "ProjectKnowledge/invariants.yaml"
    loaded_invariants = _load_mapping(invariants_path, findings, "PKI001")
    invariants_schema_path = os.path.normcase(str(invariants_path.resolve()))
    if loaded_invariants is not None and invariants_schema_path not in validated_schema_paths:
        _validate_schema_version(loaded_invariants, "ProjectKnowledge/invariants.yaml", findings)
        validated_schema_paths.add(invariants_schema_path)

    queue_path = project_root / "Build/Automation/redmmotitan_module_queue.json"
    try:
        queue = json.loads(queue_path.read_text(encoding="utf-8"))
    except Exception as exc:
        findings.append(_finding("PKI001", "Build/Automation/redmmotitan_module_queue.json", f"JSON parse failed: {exc}"))
        queue = {}
    if not isinstance(queue, dict):
        findings.append(_finding("PKI001", "Build/Automation/redmmotitan_module_queue.json", "queue must be a JSON object"))
        queue = {}
    _validate_schema_version(queue, "Build/Automation/redmmotitan_module_queue.json", findings)

    module_summary = _audit_module_queue(queue, findings)

    evidence_paths: list[tuple[str, Path]] = []
    evidence_routes = index.get("evidence")
    if not isinstance(evidence_routes, list):
        evidence_routes = []
    for raw_path in evidence_routes:
        candidate, error = _safe_repo_path(project_root, raw_path)
        if not error and candidate is not None and candidate.is_file():
            evidence_paths.append((raw_path, candidate))

    indexed_evidence = {raw_path for raw_path, _ in evidence_paths}
    evidence_directory = project_root / "ProjectKnowledge/evidence"
    for path in _discover_evidence_yaml_files(project_root, evidence_directory, findings):
        relative = path.relative_to(project_root).as_posix()
        if relative not in indexed_evidence:
            findings.append(_finding("PKI018", relative, "evidence file is not indexed"))

    evidence_records: list[tuple[str, dict[str, Any]]] = []
    evidence_records_by_path: dict[str, dict[str, Any]] = {}
    evidence_ids: dict[str, str] = {}
    ambiguous_evidence_ids: set[str] = set()
    evidence_classes: Counter[str] = Counter()
    for raw_path, path in evidence_paths:
        record = _load_mapping(path, findings, "PKI001")
        if record is None:
            continue
        evidence_records.append((raw_path, record))
        evidence_records_by_path[raw_path] = record
        evidence_id = record.get("id")
        if not isinstance(evidence_id, str) or not evidence_id.strip():
            findings.append(_finding("PKI009", raw_path, "indexed evidence requires a stable id"))
        else:
            folded = evidence_id.casefold()
            if folded in evidence_ids:
                ambiguous_evidence_ids.add(folded)
                findings.append(
                    _finding(
                        "PKI010",
                        raw_path,
                        f"duplicate evidence id {evidence_id!r}; first seen at {evidence_ids[folded]}",
                    )
                )
            else:
                evidence_ids[folded] = raw_path

        evidence_class = record.get("evidence_class")
        if not isinstance(evidence_class, str) or not evidence_class.strip():
            findings.append(_finding("PKI011", raw_path, "indexed evidence requires evidence_class"))
            evidence_classes["<missing>"] += 1
        else:
            evidence_classes[evidence_class] += 1
            if evidence_class not in CANONICAL_EVIDENCE_CLASSES:
                findings.append(
                    _finding(
                        "PKI012",
                        raw_path,
                        f"unsupported evidence_class {evidence_class!r}; use a canonical class",
                    )
                )
            if evidence_class in LOW_EVIDENCE_CLASSES:
                for field_name in ("result", "status"):
                    field_value = record.get(field_name)
                    if _has_affirmative_high_gate_result(field_value):
                        findings.append(
                            _finding(
                                "PKI013",
                                f"{raw_path}.{field_name}",
                                f"{evidence_class} appears to satisfy a higher runtime/visual/gameplay/package gate: {field_value!r}",
                            )
                        )
                for location, value in _walk_high_gate_claims(record):
                    if _is_affirmative_claim(value):
                        findings.append(
                            _finding(
                                "PKI013",
                                f"{raw_path}.{location}",
                                f"{evidence_class} cannot affirm a higher runtime/visual/gameplay/package gate",
                            )
                        )

    _audit_completed_module_evidence(
        queue,
        evidence_records_by_path,
        evidence_ids,
        ambiguous_evidence_ids,
        findings,
    )

    defect_paths: list[tuple[str, Path]] = []
    defect_routes = index.get("defects")
    if not isinstance(defect_routes, list):
        defect_routes = []
    for raw_path in defect_routes:
        candidate, error = _safe_repo_path(project_root, raw_path)
        if not error and candidate is not None and candidate.is_file():
            defect_paths.append((raw_path, candidate))

    defect_records: list[tuple[str, dict[str, Any]]] = []
    defect_ids: dict[str, str] = {}
    for raw_path, path in defect_paths:
        record = _load_mapping(path, findings, "PKI001")
        if record is None:
            continue
        defect_records.append((raw_path, record))
        defect_id = record.get("id")
        if not isinstance(defect_id, str) or not defect_id.strip():
            findings.append(_finding("PKI017", raw_path, "indexed defect requires a stable id"))
        else:
            folded = defect_id.casefold()
            if folded in defect_ids:
                findings.append(
                    _finding(
                        "PKI017",
                        raw_path,
                        f"duplicate defect id {defect_id!r}; first seen at {defect_ids[folded]}",
                    )
                )
            else:
                defect_ids[folded] = raw_path

        for location, pointer in _walk_repo_record_pointers(record.get("evidence") or {}, "evidence"):
            candidate, error = _safe_repo_path(project_root, pointer)
            if error:
                findings.append(_finding("PKI014", f"{raw_path}.{location}", f"{pointer!r}: {error}"))
            elif candidate is None or not candidate.is_file():
                findings.append(_finding("PKI014", f"{raw_path}.{location}", f"evidence pointer is missing: {pointer}"))

    current_state_path = project_root / "ProjectKnowledge/current_state.yaml"
    loaded_current_state = _load_mapping(current_state_path, findings, "PKI001")
    current_state = loaded_current_state or {}
    current_state_schema_path = os.path.normcase(str(current_state_path.resolve()))
    if loaded_current_state is not None and current_state_schema_path not in validated_schema_paths:
        _validate_schema_version(current_state, "ProjectKnowledge/current_state.yaml", findings)
        validated_schema_paths.add(current_state_schema_path)
    current_state_queue = current_state.get("queue")
    if not isinstance(current_state_queue, dict):
        findings.append(
            _finding(
                "PKI020",
                "ProjectKnowledge/current_state.yaml.queue",
                "queue must be a mapping",
            )
        )
        current_state_queue = {}

    pointer_sources = [
        ("Build/Automation/redmmotitan_module_queue.json", queue),
        ("ProjectKnowledge/current_state.yaml", current_state),
    ]
    for source_path, record in pointer_sources:
        for location, pointer in _walk_embedded_repo_record_pointers(record):
            candidate, error = _safe_repo_path(project_root, pointer)
            if error:
                findings.append(_finding("PKI019", f"{source_path}.{location}", f"{pointer!r}: {error}"))
            elif candidate is None or not candidate.is_file():
                findings.append(
                    _finding(
                        "PKI019",
                        f"{source_path}.{location}",
                        f"referenced ProjectKnowledge record is missing: {pointer}",
                    )
                )

    if queue_path.is_file():
        actual_queue_hash = sha256_file(queue_path)
        recorded_queue_hash = current_state_queue.get("snapshot_sha256")
        if recorded_queue_hash != actual_queue_hash:
            findings.append(
                _finding(
                    "PKI015",
                    "ProjectKnowledge/current_state.yaml.queue.snapshot_sha256",
                    f"recorded {recorded_queue_hash!r}, actual {actual_queue_hash}",
                )
            )
    else:
        actual_queue_hash = None

    hash_records: list[tuple[str, dict[str, Any]]] = [
        ("ProjectKnowledge/current_state.yaml", current_state),
        *defect_records,
        *evidence_records,
    ]
    for raw_path, record in hash_records:
        for location, value in _walk_hash_fields(record):
            if not isinstance(value, str) or SHA256_PATTERN.fullmatch(value) is None:
                findings.append(
                    _finding(
                        "PKI016",
                        f"{raw_path}.{location}",
                        f"SHA-256 field must contain exactly 64 hexadecimal characters, found {value!r}",
                    )
                )

    summary = {
        **module_summary,
        "indexed_route_count": len(indexed_routes),
        "indexed_evidence_count": len(evidence_paths),
        "indexed_defect_count": len(defect_paths),
        "evidence_class_counts": dict(sorted(evidence_classes.items())),
        "queue_sha256": actual_queue_hash,
        "index_sha256": sha256_file(index_path),
        "current_state_sha256": sha256_file(current_state_path) if current_state_path.is_file() else None,
    }
    return _finish_report(project_root, findings, summary)


def _finish_report(
    project_root: Path,
    findings: list[dict[str, str]],
    summary: dict[str, Any],
) -> dict[str, Any]:
    findings.sort(key=lambda item: (item["severity"], item["code"], item["path"], item["message"]))
    error_count = sum(item["severity"] == "error" for item in findings)
    warning_count = sum(item["severity"] == "warning" for item in findings)
    code_counts = Counter(item["code"] for item in findings)
    return {
        "schema_version": 1,
        "tool": "Tools/audit_project_knowledge_integrity.py",
        "project_root": project_root.as_posix(),
        "result": "pass" if error_count == 0 else "fail",
        "error_count": error_count,
        "warning_count": warning_count,
        "finding_code_counts": dict(sorted(code_counts.items())),
        "summary": summary,
        "findings": findings,
        "claim_limit": (
            "This static audit validates canonical record structure and policy metadata only. "
            "It does not compile, launch Unreal, render, exercise gameplay, package, or test multiplayer."
        ),
    }


def _write_json_atomic(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + f".tmp.{os.getpid()}")
    try:
        temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _resolve_diagnostics_output(project_root: Path, output: Path) -> Path:
    diagnostics_root = (project_root.parent / f"{project_root.name}WindowsData" / "Diagnostics").resolve()
    candidate = output.resolve()
    try:
        relative = candidate.relative_to(diagnostics_root)
    except ValueError as exc:
        raise ValueError(f"output must remain under {diagnostics_root}") from exc
    if not relative.parts or candidate.suffix.casefold() != ".json":
        raise ValueError("output must name a JSON file below the diagnostics root")
    return candidate


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="RedMMOTitan repository root",
    )
    parser.add_argument("--output", type=Path, help="Optional JSON diagnostics path")
    args = parser.parse_args(argv)

    project_root = args.project_root.resolve()
    output = None
    if args.output:
        try:
            output = _resolve_diagnostics_output(project_root, args.output)
        except ValueError as exc:
            parser.error(str(exc))

    report = audit_project(project_root)
    report["captured_utc"] = datetime.now(timezone.utc).isoformat()
    if output:
        _write_json_atomic(output, report)

    print(
        json.dumps(
            {
                "result": report["result"],
                "error_count": report["error_count"],
                "warning_count": report["warning_count"],
                "finding_code_counts": report["finding_code_counts"],
                "output": str(output) if output else None,
            },
            sort_keys=True,
        )
    )
    if report["result"] == "pass":
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
