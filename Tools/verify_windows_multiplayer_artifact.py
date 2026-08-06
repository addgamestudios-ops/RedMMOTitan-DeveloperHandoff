"""Offline integrity verifier for a RED MMO Titan Windows friend artifact.

This tool intentionally does not launch the client.  A passing static report proves
archive identity and distributable hygiene only; gameplay and Steam acceptance stay
UNVERIFIED unless separate host/client runtime logs are supplied and satisfy every
required marker.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import ntpath
from pathlib import Path, PurePosixPath
import re
import stat
import sys
from typing import Iterable
import zipfile


PASS = "pass"
FAIL = "fail"
NOT_OBSERVABLE = "not_observable"
SHA256_RE = re.compile(r"\b[0-9a-fA-F]{64}\b")
BUILD_INFO_HASH_RE = re.compile(
    r"(?:correct\s+game\s+executable|game\s+executable)\s+sha-?256\s*:\s*"
    r"([0-9a-fA-F]{64})",
    re.IGNORECASE | re.MULTILINE,
)
FATAL_RE = re.compile(
    r"fatal error|assertion failed|ensure condition failed|bad[ -]?export",
    re.IGNORECASE,
)
STEAM_FAILURE_RE = re.compile(
    r"steam api (?:initialization )?failed|steam subsystem creation failed|"
    r"unable to create (?:the )?onlinesubsystem(?:steam)?|onlinesubsystem\s*=\s*null|"
    r"(?:^|\s)-nosteam(?:\s|$)",
    re.IGNORECASE | re.MULTILINE,
)
BUILD_ID_RE = re.compile(r"\bbuild(?:_|\s*)id\s*[:=]\s*([A-Za-z0-9._-]+)", re.IGNORECASE)

REQUIRED_RELATIVE_FILES = (
    "BUILD_INFO.txt",
    "NOTICES.txt",
    "READ_ME_FIRST.txt",
    "READ_ME_FIRST.pdf",
    "steam_appid.txt",
    "Titan.exe",
    "Titan/Binaries/Win64/steam_appid.txt",
    "Titan/Binaries/Win64/Titan.exe",
    "Titan/Plugins/SteamIntegrationKit/Source/SteamSdk/redistributable_bin/win64/steam_api64.dll",
)

REQUIRED_RUNTIME_MARKERS = (
    "HOST_CREATED",
    "LOBBY_CREATED",
    "LOBBY_FOUND",
    "JOIN_SUCCEEDED",
    "RESPAWN",
    "GRAPPLE",
    "WEAPON",
    "SHUTTLE",
    "FIGHTER",
)


def _criterion(identifier: str, status: str, detail: str) -> dict[str, str]:
    return {"id": identifier, "status": status, "detail": detail}


def _sha256_stream(stream) -> str:
    digest = hashlib.sha256()
    while chunk := stream.read(1024 * 1024):
        digest.update(chunk)
    return digest.hexdigest().upper()


def sha256_file(path: Path) -> str:
    with path.open("rb") as stream:
        return _sha256_stream(stream)


def _sidecar_digest(path: Path) -> str:
    match = SHA256_RE.search(path.read_text(encoding="utf-8", errors="replace"))
    if not match:
        raise ValueError("sidecar does not contain a SHA-256 digest")
    return match.group(0).upper()


def _relative_to_wrapper(name: str, wrapper: str) -> str:
    prefix = wrapper + "/"
    if not name.startswith(prefix):
        return ""
    return name[len(prefix) :]


def _unsafe_archive_name(name: str) -> str | None:
    normalized = name.replace("\\", "/")
    drive, _ = ntpath.splitdrive(normalized)
    path = PurePosixPath(normalized)
    if drive or normalized.startswith("/") or path.is_absolute():
        return "absolute path"
    if any(part in ("", ".", "..") for part in normalized.split("/")):
        return "empty, dot, or parent segment"
    return None


def distributable_exclusion_reason(relative: str) -> str | None:
    lower = "/" + relative.replace("\\", "/").lower().strip("/")
    suffix = PurePosixPath(lower).suffix
    parts = set(PurePosixPath(lower).parts)
    if {"saved", "crashes", "logs"} & parts:
        return "runtime-generated Saved/Crashes/Logs content"
    if suffix == ".pdb":
        return "debug symbol"
    if suffix in {".pem", ".key", ".pfx", ".p12"}:
        return "credential/private-key material"
    filename = PurePosixPath(lower).name
    if "credential" in filename or "secret" in filename:
        return "credential/secret material"
    if "stagingmanifest" in filename or filename.startswith("manifest_"):
        return "staging manifest"
    return None


def _zip_member_hash(archive: zipfile.ZipFile, member: str) -> str:
    with archive.open(member, "r") as stream:
        return _sha256_stream(stream)


def _validate_strict_manifest(
    archive: zipfile.ZipFile,
    by_relative: dict[str, zipfile.ZipInfo],
    wrapper: str,
) -> list[dict[str, str]]:
    criteria: list[dict[str, str]] = []
    info = by_relative.get("BUILD_MANIFEST.json")
    if info is None:
        return [_criterion("strict_manifest", FAIL, "BUILD_MANIFEST.json is required in strict mode")]
    try:
        manifest = json.loads(archive.read(info).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return [_criterion("strict_manifest", FAIL, f"invalid BUILD_MANIFEST.json: {exc}")]

    required = {
        "source_archive_name",
        "configuration",
        "build_timestamp_utc",
        "source_revision",
        "uat_log_sha256",
        "files",
    }
    missing = sorted(required - set(manifest))
    if missing:
        criteria.append(_criterion("strict_manifest", FAIL, f"missing fields: {', '.join(missing)}"))
        return criteria
    if not SHA256_RE.fullmatch(str(manifest["uat_log_sha256"])):
        criteria.append(_criterion("strict_manifest", FAIL, "uat_log_sha256 is not a SHA-256 digest"))
        return criteria
    files = manifest.get("files")
    if not isinstance(files, dict) or not files:
        criteria.append(_criterion("strict_manifest", FAIL, "files must be a non-empty path-to-SHA256 object"))
        return criteria

    failures: list[str] = []
    expected_paths = set(by_relative) - {"BUILD_MANIFEST.json"}
    declared_paths = set(files)
    for relative in sorted(expected_paths - declared_paths, key=str.casefold):
        failures.append(f"undeclared:{relative}")
    for relative in sorted(declared_paths - expected_paths, key=str.casefold):
        failures.append(f"unknown:{relative}")
    for relative, expected in sorted(files.items(), key=lambda item: item[0].casefold()):
        info = by_relative.get(relative)
        if info is None:
            continue
        if not isinstance(expected, str) or not SHA256_RE.fullmatch(expected):
            failures.append(f"invalid_hash:{relative}")
            continue
        actual = _zip_member_hash(archive, f"{wrapper}/{relative}")
        if actual != expected.upper():
            failures.append(f"hash_mismatch:{relative}")
    if failures:
        criteria.append(_criterion("strict_manifest", FAIL, "; ".join(failures)))
    else:
        criteria.append(_criterion("strict_manifest", PASS, f"validated {len(files)} declared payload hashes"))
    return criteria


def _validate_extracted_root(
    archive: zipfile.ZipFile,
    wrapper: str,
    file_infos: Iterable[zipfile.ZipInfo],
    extracted_root: Path,
) -> tuple[dict[str, str], list[str]]:
    root = extracted_root
    if (root / wrapper).is_dir():
        root = root / wrapper
    failures: list[str] = []
    archived_relatives: set[str] = set()
    for info in file_infos:
        relative = _relative_to_wrapper(info.filename, wrapper)
        archived_relatives.add(relative.casefold())
        disk_path = root.joinpath(*PurePosixPath(relative).parts)
        if not disk_path.is_file():
            failures.append(f"missing:{relative}")
            continue
        if disk_path.stat().st_size != info.file_size:
            failures.append(f"size_mismatch:{relative}")
            continue
        disk_hash = sha256_file(disk_path)
        archive_hash = _zip_member_hash(archive, info.filename)
        if disk_hash != archive_hash:
            failures.append(f"hash_mismatch:{relative}")

    allowed_extras: list[str] = []
    disallowed_extras: list[str] = []
    if root.is_dir():
        for disk_path in root.rglob("*"):
            if not disk_path.is_file():
                continue
            relative = disk_path.relative_to(root).as_posix()
            if relative.casefold() in archived_relatives:
                continue
            lower_parts = {part.casefold() for part in PurePosixPath(relative).parts}
            if "saved" in lower_parts:
                allowed_extras.append(relative)
            else:
                disallowed_extras.append(relative)
    if disallowed_extras:
        failures.extend(f"unexpected:{item}" for item in sorted(disallowed_extras))
    if failures:
        return _criterion("extracted_payload", FAIL, "; ".join(failures[:20])), allowed_extras
    return (
        _criterion(
            "extracted_payload",
            PASS,
            f"all archived files match; allowed Saved extras={len(allowed_extras)}",
        ),
        allowed_extras,
    )


def _validate_runtime_logs(host_log: Path | None, client_log: Path | None) -> list[dict[str, str]]:
    if host_log is None and client_log is None:
        return [
            _criterion(
                "runtime_logs",
                NOT_OBSERVABLE,
                "no host/client runtime logs supplied; gameplay and Steam remain unverified",
            )
        ]
    if host_log is None or client_log is None:
        return [_criterion("runtime_logs", FAIL, "both --host-log and --client-log are required together")]
    try:
        host_text = host_log.read_text(encoding="utf-8", errors="replace")
        client_text = client_log.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return [_criterion("runtime_logs", FAIL, f"could not read runtime logs: {exc}")]
    combined = host_text + "\n" + client_text
    failures: list[str] = []
    if FATAL_RE.search(combined):
        failures.append("fatal/assert/ensure/bad-export marker")
    if STEAM_FAILURE_RE.search(combined):
        failures.append("Steam disabled/failed/NULL marker")
    host_ids = set(BUILD_ID_RE.findall(host_text))
    client_ids = set(BUILD_ID_RE.findall(client_text))
    if not host_ids or not client_ids:
        failures.append("missing host/client BuildId marker")
    elif host_ids.isdisjoint(client_ids):
        failures.append(f"build mismatch host={sorted(host_ids)} client={sorted(client_ids)}")
    missing_markers = [marker for marker in REQUIRED_RUNTIME_MARKERS if marker not in combined]
    if missing_markers:
        failures.append("missing action markers: " + ",".join(missing_markers))
    if failures:
        return [_criterion("runtime_logs", FAIL, "; ".join(failures))]
    return [_criterion("runtime_logs", PASS, "host/client Steam and gameplay markers are present")]


def verify_artifact(
    zip_path: Path,
    sidecar_path: Path,
    *,
    strict: bool = False,
    extracted_root: Path | None = None,
    host_log: Path | None = None,
    client_log: Path | None = None,
) -> dict:
    criteria: list[dict[str, str]] = []
    report: dict = {
        "schema_version": 1,
        "artifact": str(zip_path.resolve()),
        "strict": strict,
        "criteria": criteria,
        "runtime_acceptance": "UNVERIFIED",
    }

    try:
        actual_digest = sha256_file(zip_path)
        expected_digest = _sidecar_digest(sidecar_path)
        report["artifact_sha256"] = actual_digest
        criteria.append(
            _criterion(
                "archive_sha256",
                PASS if actual_digest == expected_digest else FAIL,
                "sidecar digest matches" if actual_digest == expected_digest else f"expected {expected_digest}, got {actual_digest}",
            )
        )
    except (OSError, ValueError) as exc:
        criteria.append(_criterion("archive_sha256", FAIL, str(exc)))
        report["success"] = False
        return report

    try:
        with zipfile.ZipFile(zip_path) as archive:
            infos = archive.infolist()
            file_infos = [info for info in infos if not info.is_dir()]
            report["file_count"] = len(file_infos)
            corrupt = archive.testzip()
            criteria.append(
                _criterion("zip_crc", PASS if corrupt is None else FAIL, "all member CRCs pass" if corrupt is None else f"corrupt member: {corrupt}")
            )

            unsafe: list[str] = []
            casefold_names: dict[str, str] = {}
            roots: set[str] = set()
            encrypted: list[str] = []
            symlinks: list[str] = []
            for info in infos:
                name = info.filename.replace("\\", "/").rstrip("/")
                reason = _unsafe_archive_name(name)
                if reason:
                    unsafe.append(f"{name}:{reason}")
                    continue
                roots.add(PurePosixPath(name).parts[0])
                folded = name.casefold()
                if folded in casefold_names:
                    unsafe.append(f"{name}:case-insensitive duplicate of {casefold_names[folded]}")
                casefold_names[folded] = name
                if info.flag_bits & 0x1:
                    encrypted.append(name)
                mode = info.external_attr >> 16
                if stat.S_ISLNK(mode):
                    symlinks.append(name)
            if encrypted:
                unsafe.extend(f"{name}:encrypted" for name in encrypted)
            if symlinks:
                unsafe.extend(f"{name}:symlink" for name in symlinks)
            criteria.append(
                _criterion("archive_paths", PASS if not unsafe else FAIL, "paths are safe and unique" if not unsafe else "; ".join(unsafe[:20]))
            )
            if len(roots) == 1:
                wrapper = next(iter(roots))
                report["wrapper"] = wrapper
                criteria.append(_criterion("single_wrapper", PASS, wrapper))
            else:
                wrapper = ""
                criteria.append(_criterion("single_wrapper", FAIL, f"expected one wrapper root, got {sorted(roots)}"))

            if wrapper:
                by_relative = {
                    _relative_to_wrapper(info.filename.replace("\\", "/"), wrapper): info
                    for info in file_infos
                }
                forbidden = [
                    f"{relative}:{reason}"
                    for relative in sorted(by_relative, key=str.casefold)
                    if (reason := distributable_exclusion_reason(relative))
                ]
                criteria.append(
                    _criterion("distributable_hygiene", PASS if not forbidden else FAIL, "no forbidden runtime/debug/credential files" if not forbidden else "; ".join(forbidden[:20]))
                )

                missing = [relative for relative in REQUIRED_RELATIVE_FILES if relative not in by_relative]
                criteria.append(
                    _criterion("required_payload", PASS if not missing else FAIL, "required executables, guides, notices, and Steam files exist" if not missing else "missing: " + ", ".join(missing))
                )

                app_failures: list[str] = []
                for relative in ("steam_appid.txt", "Titan/Binaries/Win64/steam_appid.txt"):
                    info = by_relative.get(relative)
                    if info is None:
                        continue
                    value = archive.read(info).decode("utf-8", errors="replace").strip()
                    if value != "480":
                        app_failures.append(f"{relative}={value!r}")
                criteria.append(
                    _criterion("steam_appid", PASS if not app_failures and all(item in by_relative for item in ("steam_appid.txt", "Titan/Binaries/Win64/steam_appid.txt")) else FAIL, "both App ID files equal 480" if not app_failures else "; ".join(app_failures))
                )

                pak_infos = {
                    relative: info
                    for relative, info in by_relative.items()
                    if relative.casefold().startswith("titan/content/paks/") and not info.is_dir()
                }
                nonempty_paks = {relative for relative, info in pak_infos.items() if info.file_size > 0}
                utoc_stems = {str(PurePosixPath(relative).with_suffix("")).casefold() for relative in nonempty_paks if relative.casefold().endswith(".utoc")}
                ucas_stems = {str(PurePosixPath(relative).with_suffix("")).casefold() for relative in nonempty_paks if relative.casefold().endswith(".ucas")}
                has_pak = any(relative.casefold().endswith(".pak") for relative in nonempty_paks)
                containers_ok = bool(utoc_stems & ucas_stems) and has_pak
                criteria.append(
                    _criterion("content_containers", PASS if containers_ok else FAIL, "nonempty paired IoStore containers and Pak exist" if containers_ok else "missing nonempty paired .utoc/.ucas or .pak")
                )

                build_info = by_relative.get("BUILD_INFO.txt")
                game_exe = by_relative.get("Titan/Binaries/Win64/Titan.exe")
                declared_match = None
                if build_info and game_exe:
                    text = archive.read(build_info).decode("utf-8", errors="replace")
                    match = BUILD_INFO_HASH_RE.search(text)
                    if match:
                        declared = match.group(1).upper()
                        actual = _zip_member_hash(archive, game_exe.filename)
                        declared_match = declared == actual
                        detail = "BUILD_INFO executable digest matches" if declared_match else f"declared {declared}, got {actual}"
                    else:
                        detail = "BUILD_INFO lacks a declared game executable SHA-256"
                else:
                    detail = "BUILD_INFO or inner game executable is missing"
                criteria.append(_criterion("declared_game_exe_sha256", PASS if declared_match else FAIL, detail))

                if strict:
                    criteria.extend(_validate_strict_manifest(archive, by_relative, wrapper))
                else:
                    criteria.append(_criterion("strict_manifest", NOT_OBSERVABLE, "strict mode was not requested"))

                if extracted_root is not None:
                    extracted_criterion, allowed_extras = _validate_extracted_root(
                        archive, wrapper, file_infos, extracted_root
                    )
                    criteria.append(extracted_criterion)
                    report["allowed_saved_extras"] = allowed_extras
                else:
                    criteria.append(_criterion("extracted_payload", NOT_OBSERVABLE, "no extracted root supplied"))
    except (OSError, zipfile.BadZipFile, RuntimeError) as exc:
        criteria.append(_criterion("zip_open", FAIL, str(exc)))

    runtime_criteria = _validate_runtime_logs(host_log, client_log)
    criteria.extend(runtime_criteria)
    if runtime_criteria and runtime_criteria[0]["status"] == PASS:
        report["runtime_acceptance"] = "LOG_MARKERS_PASS"
    report["success"] = not any(item["status"] == FAIL for item in criteria)
    report["static_acceptance"] = "PASS" if report["success"] else "FAIL"
    return report


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--zip", dest="zip_path", type=Path, required=True)
    parser.add_argument("--sha256-sidecar", type=Path)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--extracted-root", type=Path)
    parser.add_argument("--host-log", type=Path)
    parser.add_argument("--client-log", type=Path)
    parser.add_argument("--report", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    sidecar = args.sha256_sidecar or Path(str(args.zip_path) + ".sha256")
    report = verify_artifact(
        args.zip_path,
        sidecar,
        strict=args.strict,
        extracted_root=args.extracted_root,
        host_log=args.host_log,
        client_log=args.client_log,
    )
    payload = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(payload, encoding="utf-8")
    sys.stdout.write(payload)
    return 0 if report.get("success") else 1


if __name__ == "__main__":
    raise SystemExit(main())
