"""Create a clean, reproducible RED MMO Titan Windows friend ZIP.

The builder consumes an already packaged ``Windows`` directory.  It does not cook,
build, launch, or otherwise modify the packaged source.  Runtime-generated files,
debug symbols, credentials, and staging manifests are excluded; the output receives
a strict all-payload hash manifest and is verified before being reported ready.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import sys
from typing import BinaryIO
import zipfile

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from Tools.verify_windows_multiplayer_artifact import (
    REQUIRED_RELATIVE_FILES,
    distributable_exclusion_reason,
    sha256_file,
    verify_artifact,
)


LABEL_RE = re.compile(r"^[A-Za-z0-9_-]+$")
UTC_TIMESTAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
FIXED_ZIP_TIME = (2026, 1, 1, 0, 0, 0)
OVERLAY_PATHS = {
    "BUILD_INFO.txt",
    "BUILD_MANIFEST.json",
    "READ_ME_FIRST.txt",
    "READ_ME_FIRST.pdf",
}


@dataclass(frozen=True)
class Payload:
    source_path: Path | None = None
    data: bytes | None = None

    def size(self) -> int:
        if self.source_path is not None:
            return self.source_path.stat().st_size
        return len(self.data or b"")

    def sha256(self) -> str:
        if self.source_path is not None:
            return sha256_file(self.source_path)
        return hashlib.sha256(self.data or b"").hexdigest().upper()

    def copy_to(self, destination: BinaryIO) -> None:
        if self.source_path is not None:
            with self.source_path.open("rb") as source:
                shutil.copyfileobj(source, destination, length=1024 * 1024)
        else:
            destination.write(self.data or b"")


def _collect_source_payloads(packaged_root: Path) -> tuple[dict[str, Payload], list[dict[str, str]]]:
    payloads: dict[str, Payload] = {}
    exclusions: list[dict[str, str]] = []
    casefold_paths: dict[str, str] = {}
    for source in sorted(packaged_root.rglob("*"), key=lambda item: item.as_posix().casefold()):
        if source.is_symlink() or (hasattr(source, "is_junction") and source.is_junction()):
            raise ValueError(f"packaged source contains a symlink or junction: {source}")
        if not source.is_file():
            continue
        relative = source.relative_to(packaged_root).as_posix()
        folded = relative.casefold()
        if folded in casefold_paths:
            raise ValueError(
                f"packaged source contains a case-insensitive path collision: "
                f"{relative} and {casefold_paths[folded]}"
            )
        casefold_paths[folded] = relative
        if relative in OVERLAY_PATHS:
            exclusions.append({"path": relative, "reason": "replaced by generated artifact metadata"})
            continue
        reason = distributable_exclusion_reason(relative)
        if reason:
            if "credential" in reason or "key material" in reason:
                raise ValueError(f"packaged source contains forbidden {reason}: {relative}")
            exclusions.append({"path": relative, "reason": reason})
            continue
        payloads[relative] = Payload(source_path=source)
    return payloads, exclusions


def _validate_packaged_source(payloads: dict[str, Payload]) -> None:
    source_required = set(REQUIRED_RELATIVE_FILES) - {
        "BUILD_INFO.txt",
        "READ_ME_FIRST.txt",
        "READ_ME_FIRST.pdf",
        "steam_appid.txt",
        "Titan/Binaries/Win64/steam_appid.txt",
    }
    missing = sorted(source_required - set(payloads), key=str.casefold)
    if missing:
        raise ValueError("packaged source is missing required files: " + ", ".join(missing))
    empty = sorted(
        relative
        for relative in source_required
        if relative in payloads and payloads[relative].size() == 0
    )
    if empty:
        raise ValueError("packaged source has empty required files: " + ", ".join(empty))
    pak_payloads = {
        relative: payload
        for relative, payload in payloads.items()
        if relative.casefold().startswith("titan/content/paks/") and payload.size() > 0
    }
    utoc_stems = {
        str(PurePosixPath(relative).with_suffix("")).casefold()
        for relative in pak_payloads
        if relative.casefold().endswith(".utoc")
    }
    ucas_stems = {
        str(PurePosixPath(relative).with_suffix("")).casefold()
        for relative in pak_payloads
        if relative.casefold().endswith(".ucas")
    }
    has_pak = any(relative.casefold().endswith(".pak") for relative in pak_payloads)
    if not has_pak or not (utoc_stems & ucas_stems):
        raise ValueError("packaged source requires a nonempty Pak and matching nonempty UTOC/UCAS pair")


def _build_info(
    *,
    artifact_name: str,
    build_timestamp_utc: str,
    configuration: str,
    source_archive_name: str,
    source_revision: str,
    uat_log_sha256: str,
    game_exe_sha256: str,
) -> bytes:
    return (
        "RED MMO TITAN - FRIEND MULTIPLAYER TEST BUILD\n"
        f"Artifact: {artifact_name}.zip\n"
        f"Build timestamp (UTC): {build_timestamp_utc}\n"
        f"Platform: Windows 64-bit {configuration} build\n"
        f"Source archive: {source_archive_name}\n"
        f"Source revision: {source_revision}\n"
        f"UAT log SHA-256: {uat_log_sha256}\n"
        "Steam development App ID: 480 (Spacewar transport identity)\n\n"
        "Launch Titan.exe at the top level of the extracted folder.\n"
        "Do not move only the EXE or run the game from inside the ZIP.\n\n"
        "Correct game executable SHA-256:\n"
        f"{game_exe_sha256}\n\n"
        "Runtime multiplayer acceptance: UNVERIFIED by this static builder.\n"
        "This file records package identity only. It does not claim that Steam transport,\n"
        "host/find/join, replication, combat, respawn, or craft possession passed. Check\n"
        "the separately supplied runtime acceptance report for those results.\n\n"
        "App ID 480 is a development transport identity, not a native RED MMO Titan\n"
        "Steam Library SKU. A Valve-assigned App ID, depot, branch, and entitlement are\n"
        "still required for native Steam Library distribution.\n\n"
        "Read READ_ME_FIRST.pdf for the host/join walkthrough and controls.\n"
    ).encode("utf-8")


def _zip_info(name: str, size: int) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, FIXED_ZIP_TIME)
    info.compress_type = zipfile.ZIP_STORED
    info.create_system = 3
    info.external_attr = 0o100644 << 16
    info.file_size = size
    return info


def _write_zip(zip_path: Path, label: str, payloads: dict[str, Payload]) -> None:
    partial = Path(str(zip_path) + ".partial")
    if partial.exists():
        partial.unlink()
    try:
        with zipfile.ZipFile(partial, "w", allowZip64=True) as archive:
            for relative in sorted(payloads, key=str.casefold):
                payload = payloads[relative]
                member = f"{label}/{PurePosixPath(relative).as_posix()}"
                info = _zip_info(member, payload.size())
                with archive.open(info, "w", force_zip64=True) as destination:
                    payload.copy_to(destination)
        partial.replace(zip_path)
    except Exception:
        if partial.exists():
            partial.unlink()
        raise


def _validate_ready_marker(
    packaged_root: Path,
    ready_marker: Path,
    uat_log: Path,
    *,
    configuration: str,
    build_timestamp_utc: str,
    source_revision: str,
    source_dirty: bool,
) -> None:
    expected_windows = (ready_marker.parent / "Windows").resolve()
    if packaged_root.resolve() != expected_windows:
        raise ValueError(
            f"packaged root must be the Windows directory beside the explicit ready marker: "
            f"expected {expected_windows}"
        )
    fields: dict[str, str] = {}
    for line in ready_marker.read_text(encoding="utf-8", errors="replace").splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            fields[key.strip().casefold()] = value.strip()
    required_fields = {
        "archive",
        "build_log",
        "uat_exit_file",
        "configuration",
        "build_timestamp_utc",
        "source_revision",
        "source_dirty",
    }
    missing = sorted(required_fields - set(fields))
    if missing:
        raise ValueError("ready marker is missing packaging-time fields: " + ", ".join(missing))
    if Path(fields["archive"]).resolve() != ready_marker.parent.resolve():
        raise ValueError("ready marker archive= does not match its containing UAT archive")
    if Path(fields["build_log"]).resolve() != uat_log.resolve():
        raise ValueError("ready marker build_log= does not match --uat-log")
    exit_file = Path(str(uat_log) + ".exitcode")
    if Path(fields["uat_exit_file"]).resolve() != exit_file.resolve():
        raise ValueError("ready marker uat_exit_file= does not match the UAT exit-code evidence")
    if not exit_file.is_file() or exit_file.read_text(encoding="utf-8", errors="replace").strip() != "0":
        raise ValueError(f"successful UAT exit-code evidence is missing or nonzero: {exit_file}")
    expected_values = {
        "configuration": configuration,
        "build_timestamp_utc": build_timestamp_utc,
        "source_revision": source_revision,
        "source_dirty": str(source_dirty).lower(),
    }
    mismatches = [
        f"{key}={fields[key]!r} expected {value!r}"
        for key, value in expected_values.items()
        if fields[key] != value
    ]
    if mismatches:
        raise ValueError("ready marker metadata does not match builder inputs: " + "; ".join(mismatches))


def create_friend_artifact(
    *,
    packaged_root: Path,
    ready_marker: Path,
    output_dir: Path,
    label: str,
    quickstart_text: Path,
    quickstart_pdf: Path,
    steam_app_id_file: Path,
    uat_log: Path,
    configuration: str,
    build_timestamp_utc: str,
    source_revision: str,
    source_dirty: bool,
    source_archive_name: str,
) -> dict:
    if not LABEL_RE.fullmatch(label):
        raise ValueError("label must contain only letters, digits, underscore, or hyphen")
    if not UTC_TIMESTAMP_RE.fullmatch(build_timestamp_utc):
        raise ValueError("build_timestamp_utc must be an explicit RFC3339 UTC timestamp ending in Z")
    if not source_revision.strip():
        raise ValueError("source_revision must record the packaging-time revision")
    for path, description in (
        (packaged_root, "packaged Windows root"),
        (ready_marker, "package ready marker"),
        (quickstart_text, "quickstart text"),
        (quickstart_pdf, "quickstart PDF"),
        (steam_app_id_file, "canonical Steam App ID file"),
        (uat_log, "UAT log"),
    ):
        if not path.exists():
            raise ValueError(f"{description} does not exist: {path}")
    if not packaged_root.is_dir():
        raise ValueError(f"packaged Windows root is not a directory: {packaged_root}")
    if not ready_marker.is_file():
        raise ValueError(f"package ready marker is not a file: {ready_marker}")
    expected_archive_name = ready_marker.parent.resolve().name
    if source_archive_name != expected_archive_name:
        raise ValueError(
            f"source_archive_name must equal the explicit UAT archive leaf {expected_archive_name!r}"
        )
    _validate_ready_marker(
        packaged_root,
        ready_marker,
        uat_log,
        configuration=configuration,
        build_timestamp_utc=build_timestamp_utc,
        source_revision=source_revision,
        source_dirty=source_dirty,
    )

    packaged_resolved = packaged_root.resolve()
    output_resolved = output_dir.resolve()
    if output_resolved == packaged_resolved or packaged_resolved in output_resolved.parents or output_resolved in packaged_resolved.parents:
        raise ValueError("output directory and packaged source must not overlap")

    output_dir.mkdir(parents=True, exist_ok=True)
    zip_path = output_dir / f"{label}.zip"
    sidecar_path = Path(str(zip_path) + ".sha256")
    verification_path = Path(str(zip_path) + ".verification.json")
    existing = [path for path in (zip_path, sidecar_path, verification_path) if path.exists()]
    if existing:
        raise FileExistsError("immutable output already exists; choose a new artifact label: " + ", ".join(map(str, existing)))

    payloads, exclusions = _collect_source_payloads(packaged_root)
    _validate_packaged_source(payloads)
    canonical_app_id = steam_app_id_file.read_text(encoding="utf-8", errors="replace").strip()
    if canonical_app_id != "480":
        raise ValueError(
            f"canonical Steam App ID file must equal development App ID 480, got {canonical_app_id!r}"
        )
    app_id_payload = Payload(data=b"480\n")
    payloads["steam_appid.txt"] = app_id_payload
    payloads["Titan/Binaries/Win64/steam_appid.txt"] = app_id_payload
    payloads["READ_ME_FIRST.txt"] = Payload(data=quickstart_text.read_bytes())
    payloads["READ_ME_FIRST.pdf"] = Payload(data=quickstart_pdf.read_bytes())
    game_exe_hash = payloads["Titan/Binaries/Win64/Titan.exe"].sha256()
    uat_log_hash = sha256_file(uat_log)
    payloads["BUILD_INFO.txt"] = Payload(
        data=_build_info(
            artifact_name=label,
            build_timestamp_utc=build_timestamp_utc,
            configuration=configuration,
            source_archive_name=source_archive_name,
            source_revision=source_revision,
            uat_log_sha256=uat_log_hash,
            game_exe_sha256=game_exe_hash,
        )
    )

    file_hashes = {
        relative: payload.sha256()
        for relative, payload in sorted(payloads.items(), key=lambda item: item[0].casefold())
    }
    manifest = {
        "schema_version": 1,
        "project": "RedMMOTitan",
        "source_archive_name": source_archive_name,
        "configuration": configuration,
        "build_timestamp_utc": build_timestamp_utc,
        "source_revision": source_revision,
        "source_dirty": source_dirty,
        "uat_log_name": uat_log.name,
        "uat_log_sha256": uat_log_hash,
        "steam_app_id": 480,
        "runtime_acceptance": "UNVERIFIED",
        "excluded_source_files": exclusions,
        "files": file_hashes,
    }
    payloads["BUILD_MANIFEST.json"] = Payload(
        data=(json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")
    )

    building_zip = output_dir / f".{label}.zip.building"
    building_sidecar = output_dir / f".{label}.zip.building.sha256"
    for temporary in (building_zip, building_sidecar):
        if temporary.exists():
            temporary.unlink()
    try:
        _write_zip(building_zip, label, payloads)
        artifact_hash = sha256_file(building_zip)
        building_sidecar.write_text(f"{artifact_hash} *{zip_path.name}\n", encoding="utf-8")
        verification = verify_artifact(building_zip, building_sidecar, strict=True)
        if not verification.get("success"):
            failures = [
                item["id"] + ": " + item["detail"]
                for item in verification.get("criteria", [])
                if item.get("status") == "fail"
            ]
            raise RuntimeError("created artifact failed strict verification: " + "; ".join(failures))
        building_zip.replace(zip_path)
        sidecar_partial = Path(str(sidecar_path) + ".partial")
        sidecar_partial.write_text(f"{artifact_hash} *{zip_path.name}\n", encoding="utf-8")
        sidecar_partial.replace(sidecar_path)
        verification["artifact"] = str(zip_path.resolve())
        verification_partial = Path(str(verification_path) + ".partial")
        verification_partial.write_text(
            json.dumps(verification, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        verification_partial.replace(verification_path)
    finally:
        for temporary in (building_zip, building_sidecar):
            if temporary.exists():
                temporary.unlink()
    return {
        "zip": str(zip_path.resolve()),
        "sidecar": str(sidecar_path.resolve()),
        "verification": str(verification_path.resolve()),
        "artifact_sha256": artifact_hash,
        "payload_count": len(payloads),
        "excluded_count": len(exclusions),
        "runtime_acceptance": verification["runtime_acceptance"],
    }


def _build_parser() -> argparse.ArgumentParser:
    project_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packaged-root", type=Path, required=True)
    parser.add_argument("--ready-marker", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--label", required=True)
    parser.add_argument(
        "--quickstart-text",
        type=Path,
        default=project_root / "docs" / "FRIEND_MULTIPLAYER_QUICKSTART.txt",
    )
    parser.add_argument("--quickstart-pdf", type=Path, required=True)
    parser.add_argument(
        "--steam-appid-file",
        type=Path,
        default=project_root / "steam_appid.txt",
    )
    parser.add_argument("--uat-log", type=Path, required=True)
    parser.add_argument("--configuration", default="Development")
    parser.add_argument("--build-timestamp-utc", required=True)
    parser.add_argument("--source-revision", required=True)
    parser.add_argument("--source-dirty", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    source_archive_name = args.ready_marker.resolve().parent.name
    try:
        result = create_friend_artifact(
            packaged_root=args.packaged_root.resolve(),
            ready_marker=args.ready_marker.resolve(),
            output_dir=args.output_dir.resolve(),
            label=args.label,
            quickstart_text=args.quickstart_text.resolve(),
            quickstart_pdf=args.quickstart_pdf.resolve(),
            steam_app_id_file=args.steam_appid_file.resolve(),
            uat_log=args.uat_log.resolve(),
            configuration=args.configuration,
            build_timestamp_utc=args.build_timestamp_utc,
            source_revision=args.source_revision,
            source_dirty=args.source_dirty,
            source_archive_name=source_archive_name,
        )
    except (OSError, ValueError, FileExistsError, RuntimeError, zipfile.BadZipFile) as exc:
        print(f"RED_FRIEND_ARTIFACT_FAILED {exc}", file=sys.stderr)
        return 1
    print("RED_FRIEND_ARTIFACT_READY " + json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
