#!/usr/bin/env python3
"""Fail-closed audit of RedMMOTitan Windows target currency.

This tool is intentionally separate from packaging. It never builds targets and
never enables SkipBuild. A target is current only when an explicit build proof
matches the current project-input digest, receipt, required project products,
and a preserved successful build log. Both Titan and TitanEditor must pass.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


SCHEMA_VERSION = 1
HASH_CHUNK_SIZE = 4 * 1024 * 1024
BUILD_INPUT_SUFFIXES = {
    ".c",
    ".cc",
    ".cpp",
    ".cxx",
    ".h",
    ".hh",
    ".hpp",
    ".hxx",
    ".inl",
    ".ixx",
    ".cs",
    ".def",
    ".lib",
    ".dll",
    ".natvis",
    ".props",
    ".targets",
}
BUILD_RESOURCE_SUFFIXES = {".ico", ".manifest", ".rc"}
EXCLUDED_PARTS = {
    "binaries",
    "intermediate",
    "saved",
    "deriveddatacache",
    "content",
    "__pycache__",
}
REQUIRED_PRODUCT_TYPES = {"Executable", "DynamicLibrary", "RequiredResource"}
OPTIONAL_PRODUCT_TYPES = {"SymbolFile"}


@dataclass(frozen=True)
class TargetSpec:
    name: str
    target_type: str
    receipt_relative: str
    primary_product_relative: str


TARGET_SPECS = (
    TargetSpec(
        name="Titan",
        target_type="Game",
        receipt_relative="Binaries/Win64/Titan.target",
        primary_product_relative="Binaries/Win64/Titan.exe",
    ),
    TargetSpec(
        name="TitanEditor",
        target_type="Editor",
        receipt_relative="Binaries/Win64/TitanEditor.target",
        primary_product_relative="Binaries/Win64/UnrealEditor-RedMMO.dll",
    ),
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(HASH_CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def utc_iso_from_ns(timestamp_ns: int) -> str:
    return datetime.fromtimestamp(timestamp_ns / 1_000_000_000, timezone.utc).isoformat()


def _relative_inside_root(path: Path, root: Path, *, must_exist: bool) -> tuple[Path, str]:
    resolved_root = root.resolve(strict=True)
    resolved = path.resolve(strict=must_exist)
    try:
        relative = resolved.relative_to(resolved_root)
    except ValueError as exc:
        raise ValueError(f"path escapes project root: {path}") from exc
    return resolved, relative.as_posix()


def _candidate_input_paths(project_root: Path) -> Iterable[Path]:
    project_file = project_root / "Titan.uproject"
    if project_file.is_file():
        yield project_file

    config_root = project_root / "Config"
    if config_root.is_dir():
        yield from (path for path in config_root.rglob("*") if path.is_file())

    source_root = project_root / "Source"
    if source_root.is_dir():
        for path in source_root.rglob("*"):
            if path.is_file() and path.suffix.lower() in BUILD_INPUT_SUFFIXES:
                yield path

    plugins_root = project_root / "Plugins"
    if plugins_root.is_dir():
        for path in plugins_root.rglob("*"):
            if not path.is_file():
                continue
            relative_parts = tuple(part.casefold() for part in path.relative_to(project_root).parts)
            if any(part in EXCLUDED_PARTS for part in relative_parts):
                continue
            if path.suffix.casefold() == ".uplugin":
                yield path
                continue
            if "source" in relative_parts and path.suffix.casefold() in BUILD_INPUT_SUFFIXES:
                yield path

    windows_build_root = project_root / "Build" / "Windows"
    if windows_build_root.is_dir():
        for path in windows_build_root.rglob("*"):
            if path.is_file() and path.suffix.casefold() in BUILD_RESOURCE_SUFFIXES:
                yield path


def discover_project_build_inputs(project_root: Path) -> list[Path]:
    project_root = project_root.resolve(strict=True)
    by_casefolded_relative: dict[str, Path] = {}
    for candidate in _candidate_input_paths(project_root):
        resolved, relative = _relative_inside_root(candidate, project_root, must_exist=True)
        key = relative.casefold()
        existing = by_casefolded_relative.get(key)
        if existing is not None and existing != resolved:
            raise ValueError(
                f"case-insensitive duplicate build input: {existing} and {resolved}"
            )
        by_casefolded_relative[key] = resolved
    if "titan.uproject" not in by_casefolded_relative:
        raise FileNotFoundError("Titan.uproject is missing from the project root")
    return [by_casefolded_relative[key] for key in sorted(by_casefolded_relative)]


def build_input_manifest(project_root: Path) -> tuple[list[dict[str, Any]], str]:
    records: list[dict[str, Any]] = []
    digest = hashlib.sha256()
    for path in discover_project_build_inputs(project_root):
        _, relative = _relative_inside_root(path, project_root, must_exist=True)
        stat = path.stat()
        file_hash = sha256_file(path)
        record = {
            "path": relative,
            "sha256": file_hash,
            "size": stat.st_size,
            "last_write_utc": utc_iso_from_ns(stat.st_mtime_ns),
            "last_write_ns": stat.st_mtime_ns,
        }
        records.append(record)
        digest.update(relative.casefold().encode("utf-8"))
        digest.update(b"\0")
        digest.update(file_hash.encode("ascii"))
        digest.update(b"\0")
    return records, digest.hexdigest().upper()


def _category(relative_path: str) -> str:
    folded = relative_path.casefold()
    if folded.startswith("config/"):
        return "config"
    if folded.startswith("plugins/"):
        return "plugin"
    if folded.startswith("source/"):
        return "source"
    if folded.startswith("build/windows/"):
        return "windows_build_resource"
    return "project_descriptor"


def _project_product_path(raw_path: str, project_root: Path) -> tuple[Path, str] | None:
    normalized = raw_path.replace("\\", "/")
    prefix = "$(ProjectDir)/"
    if not normalized.casefold().startswith(prefix.casefold()):
        return None
    relative_text = normalized[len(prefix) :]
    candidate = project_root / Path(relative_text)
    resolved, relative = _relative_inside_root(candidate, project_root, must_exist=False)
    return resolved, relative


def _product_manifest_digest(records: list[dict[str, Any]]) -> str:
    digest = hashlib.sha256()
    for record in sorted(records, key=lambda item: item["path"].casefold()):
        digest.update(record["path"].casefold().encode("utf-8"))
        digest.update(b"\0")
        digest.update(record["type"].encode("utf-8"))
        digest.update(b"\0")
        digest.update((record.get("sha256") or "MISSING").encode("ascii"))
        digest.update(b"\0")
    return digest.hexdigest().upper()


def inspect_target(
    project_root: Path,
    spec: TargetSpec,
    input_manifest: list[dict[str, Any]],
    input_manifest_sha256: str,
) -> dict[str, Any]:
    errors: list[str] = []
    receipt_path = project_root / Path(spec.receipt_relative)
    report: dict[str, Any] = {
        "target_name": spec.name,
        "expected_platform": "Win64",
        "expected_configuration": "Development",
        "expected_target_type": spec.target_type,
        "receipt_path": spec.receipt_relative,
        "primary_product_path": spec.primary_product_relative,
    }

    if not receipt_path.is_file():
        report.update(
            {
                "receipt_exists": False,
                "errors": [f"missing receipt: {spec.receipt_relative}"],
                "currency_state": "invalid_or_missing",
                "proof_status": "not_checked",
                "skip_build_allowed": False,
            }
        )
        return report

    receipt_stat = receipt_path.stat()
    report.update(
        {
            "receipt_exists": True,
            "receipt_sha256": sha256_file(receipt_path),
            "receipt_last_write_utc": utc_iso_from_ns(receipt_stat.st_mtime_ns),
            "receipt_last_write_ns": receipt_stat.st_mtime_ns,
        }
    )
    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        report.update(
            {
                "errors": [f"malformed receipt: {exc}"],
                "currency_state": "invalid_or_missing",
                "proof_status": "not_checked",
                "skip_build_allowed": False,
            }
        )
        return report

    identity = {
        "TargetName": receipt.get("TargetName"),
        "Platform": receipt.get("Platform"),
        "Configuration": receipt.get("Configuration"),
        "TargetType": receipt.get("TargetType"),
        "Architecture": receipt.get("Architecture"),
        "Project": receipt.get("Project"),
        "BuildId": (receipt.get("Version") or {}).get("BuildId"),
    }
    report["receipt_identity"] = identity
    expected_identity = {
        "TargetName": spec.name,
        "Platform": "Win64",
        "Configuration": "Development",
        "TargetType": spec.target_type,
    }
    for key, expected in expected_identity.items():
        if identity.get(key) != expected:
            errors.append(
                f"receipt identity mismatch for {key}: {identity.get(key)!r} != {expected!r}"
            )

    required_products: list[dict[str, Any]] = []
    optional_products: list[dict[str, Any]] = []
    primary_declared = False
    for build_product in receipt.get("BuildProducts") or []:
        raw_path = str(build_product.get("Path") or "")
        product_type = str(build_product.get("Type") or "")
        if product_type not in REQUIRED_PRODUCT_TYPES | OPTIONAL_PRODUCT_TYPES:
            continue
        try:
            resolved = _project_product_path(raw_path, project_root)
        except ValueError as exc:
            errors.append(str(exc))
            continue
        if resolved is None:
            continue
        product_path, relative = resolved
        record: dict[str, Any] = {
            "path": relative,
            "type": product_type,
            "exists": product_path.is_file(),
        }
        if product_path.is_file():
            stat = product_path.stat()
            record.update(
                {
                    "sha256": sha256_file(product_path),
                    "size": stat.st_size,
                    "last_write_utc": utc_iso_from_ns(stat.st_mtime_ns),
                    "last_write_ns": stat.st_mtime_ns,
                }
            )
        if relative.casefold() == spec.primary_product_relative.casefold():
            primary_declared = True
        if product_type in REQUIRED_PRODUCT_TYPES:
            required_products.append(record)
            if not record["exists"]:
                errors.append(f"missing required project product: {relative}")
        else:
            optional_products.append(record)

    if not primary_declared:
        errors.append(
            f"receipt does not declare primary product: {spec.primary_product_relative}"
        )
    report["required_project_products"] = sorted(
        required_products, key=lambda item: item["path"].casefold()
    )
    report["optional_symbol_products"] = sorted(
        optional_products, key=lambda item: item["path"].casefold()
    )
    report["required_product_manifest_sha256"] = _product_manifest_digest(
        required_products
    )

    newer_inputs = [
        record
        for record in input_manifest
        if int(record["last_write_ns"]) > receipt_stat.st_mtime_ns
    ]
    category_counts: dict[str, int] = {}
    for record in newer_inputs:
        category = _category(str(record["path"]))
        category_counts[category] = category_counts.get(category, 0) + 1
    report["newer_project_input_count"] = len(newer_inputs)
    report["newer_project_input_categories"] = category_counts
    report["newer_project_inputs"] = newer_inputs
    report["input_manifest_sha256"] = input_manifest_sha256
    report["input_count"] = len(input_manifest)
    report["errors"] = errors
    report["currency_state"] = (
        "invalid_or_missing"
        if errors
        else "stale_unproven"
        if newer_inputs
        else "timestamp_clean_unproven"
    )
    report["proof_status"] = "missing"
    report["skip_build_allowed"] = False
    return report


def _load_and_validate_proof(
    proof_path: Path | None,
    target: dict[str, Any],
) -> tuple[str, list[str], dict[str, Any] | None]:
    if proof_path is None:
        return "missing", ["no explicit build-time proof supplied"], None
    if not proof_path.is_file():
        return "missing", [f"proof file does not exist: {proof_path}"], None
    try:
        proof = json.loads(proof_path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return "invalid", [f"malformed proof: {exc}"], None

    errors: list[str] = []
    expected_fields = {
        "schema_version": SCHEMA_VERSION,
        "target_name": target["target_name"],
        "platform": target["expected_platform"],
        "configuration": target["expected_configuration"],
        "target_type": target["expected_target_type"],
        "input_count": target.get("input_count"),
        "input_manifest_sha256": target.get("input_manifest_sha256"),
        "receipt_sha256": target.get("receipt_sha256"),
        "required_product_manifest_sha256": target.get(
            "required_product_manifest_sha256"
        ),
    }
    for key, expected in expected_fields.items():
        if proof.get(key) != expected:
            errors.append(f"proof mismatch for {key}")

    build_log = proof.get("build_log")
    if not isinstance(build_log, dict):
        errors.append("proof build_log record is missing")
    else:
        raw_log_path = build_log.get("path")
        declared_log_hash = build_log.get("sha256")
        if not isinstance(raw_log_path, str) or not raw_log_path:
            errors.append("proof build_log path is missing")
        else:
            log_path = Path(raw_log_path)
            if not log_path.is_absolute():
                log_path = proof_path.parent / log_path
            if not log_path.is_file():
                errors.append(f"proof build log does not exist: {log_path}")
            else:
                actual_hash = sha256_file(log_path)
                if actual_hash != declared_log_hash:
                    errors.append("proof build log hash mismatch")
                log_text = log_path.read_text(encoding="utf-8", errors="replace")
                signature = re.compile(
                    rf"\b{re.escape(target['target_name'])}\s+Win64\s+Development\b",
                    flags=re.IGNORECASE,
                )
                if signature.search(log_text) is None:
                    errors.append("proof build log lacks exact target/platform/configuration marker")
                if "Result: Succeeded" not in log_text:
                    errors.append("proof build log lacks Result: Succeeded")

    return ("valid" if not errors else "invalid"), errors, proof


def _git_snapshot(project_root: Path) -> dict[str, Any]:
    try:
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=project_root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        branch = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=project_root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        status = subprocess.run(
            ["git", "status", "--porcelain=v1"],
            cwd=project_root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.splitlines()
        return {
            "head": head,
            "branch": branch,
            "dirty": bool(status),
            "porcelain_entry_count": len(status),
        }
    except (OSError, subprocess.CalledProcessError):
        return {"head": None, "branch": None, "dirty": None, "porcelain_entry_count": None}


def audit_project(
    project_root: Path,
    *,
    titan_proof: Path | None = None,
    titan_editor_proof: Path | None = None,
) -> dict[str, Any]:
    project_root = project_root.resolve(strict=True)
    input_manifest, input_manifest_sha256 = build_input_manifest(project_root)
    proof_paths = {"Titan": titan_proof, "TitanEditor": titan_editor_proof}
    targets: list[dict[str, Any]] = []
    for spec in TARGET_SPECS:
        target = inspect_target(
            project_root, spec, input_manifest, input_manifest_sha256
        )
        if target["currency_state"] != "invalid_or_missing":
            proof_status, proof_errors, _ = _load_and_validate_proof(
                proof_paths[spec.name], target
            )
            target["proof_status"] = proof_status
            target["proof_errors"] = proof_errors
            if proof_status == "valid":
                target["currency_state"] = "current_proven"
                target["skip_build_allowed"] = True
            elif proof_status == "invalid":
                target["currency_state"] = "proof_invalid"
        targets.append(target)

    skip_build_allowed = len(targets) == len(TARGET_SPECS) and all(
        target.get("skip_build_allowed") is True for target in targets
    )
    stale_targets = [
        target["target_name"]
        for target in targets
        if target.get("currency_state") != "current_proven"
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "captured_utc": datetime.now(timezone.utc).isoformat(),
        "project_root": project_root.as_posix(),
        "source_revision": _git_snapshot(project_root),
        "input_scope": {
            "includes": [
                "Titan.uproject",
                "Config/**",
                "Source build inputs",
                "Plugins/**/*.uplugin",
                "Plugins/**/Source build inputs",
                "Build/Windows build resources",
            ],
            "excludes": sorted(EXCLUDED_PARTS),
            "input_count": len(input_manifest),
            "input_manifest_sha256": input_manifest_sha256,
        },
        "input_manifest": input_manifest,
        "targets": targets,
        "gate": {
            "skip_build_allowed": skip_build_allowed,
            "targets_requiring_current_build_proof": stale_targets,
            "result": "dual_target_proof_passed" if skip_build_allowed else "refused_fail_closed",
            "rule": "Titan and TitanEditor require separate exact matching build-time proofs",
        },
        "claim_limit": (
            "This static audit does not compile, cook, package, launch, render, or prove "
            "gameplay or multiplayer. Timestamp cleanliness alone never authorizes SkipBuild."
        ),
    }


def _write_report_atomic(output: Path, report: dict[str, Any]) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(output.name + ".tmp")
    temporary.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    os.replace(temporary, output)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument("--titan-proof", type=Path)
    parser.add_argument("--titan-editor-proof", type=Path)
    parser.add_argument(
        "--allow-unverified-report",
        action="store_true",
        help="Return zero after writing a refused diagnostic report.",
    )
    args = parser.parse_args(argv)
    report = audit_project(
        args.project_root,
        titan_proof=args.titan_proof,
        titan_editor_proof=args.titan_editor_proof,
    )
    if args.output:
        _write_report_atomic(args.output, report)
    else:
        print(json.dumps(report, indent=2, sort_keys=True))
    if report["gate"]["skip_build_allowed"] or args.allow_unverified_report:
        return 0
    return 10


if __name__ == "__main__":
    raise SystemExit(main())
