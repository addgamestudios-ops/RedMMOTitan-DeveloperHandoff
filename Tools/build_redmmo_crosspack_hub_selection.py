"""Build a fail-closed cross-pack mini-hub source-selection manifest.

The input is an exact-path review request. This tool never selects by category,
loads Unreal, imports or migrates packages, invokes Nwiro, or grants approval.
It authenticates the two local vendor trees and the explicitly named candidate
packages, then records a conservative offline serialized-reference closure.
That closure is evidence for review only; Unreal Asset Registry dependency
validation is still required before migration or map authoring.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
from collections import deque
from pathlib import Path, PurePosixPath
from typing import Mapping, Sequence


DEFAULT_DIAGNOSTICS_ROOT = Path(r"D:\RedMMOTitanWindowsData\Diagnostics")
EXPECTED_REQUEST_ID = "redmmo-crosspack-minihub-source-selection"
EXPECTED_REQUEST_STATUS = "candidate_only"
EXPECTED_SELECTION_METHOD = "explicit_exact_path_allowlist"
MAX_PACKAGE_BYTES = 128 * 1024 * 1024

PACK_CONTRACTS = {
    "fab.12ec20bd-ce21-4d3d-8051-13ffb0fe851e": {
        "title": "Stylized Nature - Desert Savanna Environment",
        "listing_id": "12ec20bd-ce21-4d3d-8051-13ffb0fe851e",
        "mount_root": "/Game/Zenscape_Savanna",
        "source_policy": "vendor_source_immutable",
        "fab_license": "Standard License",
        "allows_usage_with_ai": False,
        "declared_unreal_versions": ["5.3", "5.4", "5.5", "5.6"],
        "source_engine_association": None,
        "local_source_state": "project_present_unvalidated_vendor_packages",
    },
    "fab.934c1286-7388-4aa5-a300-e0a7cdf65675": {
        "title": "Stylized Nature - Tropical Island and Underwater Environment",
        "listing_id": "934c1286-7388-4aa5-a300-e0a7cdf65675",
        "mount_root": "/Game/Zenscape_Island",
        "source_policy": "vendor_source_immutable",
        "fab_license": "Standard License",
        "allows_usage_with_ai": False,
        "declared_unreal_versions": ["5.4", "5.5", "5.6"],
        "source_engine_association": "5.4",
        "local_source_state": "isolated_vendor_project_unvalidated_for_migration",
    },
}

SOURCE_IDENTITY_CONTRACTS = {
    "fab.12ec20bd-ce21-4d3d-8051-13ffb0fe851e": {
        "canonical_root": r"D:\RedMMOTitan\Content\Zenscape_Savanna",
        "source_file_count": 321,
        "source_bytes": 750355516,
        "source_tree_sha256": (
            "69F083AF85959AF5DA257D36B5B374C3766C242791D9ED9DC9452F5C445EC661"
        ),
        "source_project_descriptor": None,
    },
    "fab.934c1286-7388-4aa5-a300-e0a7cdf65675": {
        "canonical_root": (
            r"D:\RedMMOTitanWindowsData\UserUnrealProjects"
            r"\StylizedNatureTropicalIs\Content\Zenscape_Island"
        ),
        "source_file_count": 334,
        "source_bytes": 559398662,
        "source_tree_sha256": (
            "610F447CAF47269676D0301330411F3A9B42E04DDF0D18782E7D61085A211732"
        ),
        "source_project_descriptor": {
            "path": (
                r"D:\RedMMOTitanWindowsData\UserUnrealProjects"
                r"\StylizedNatureTropicalIs\StylizedNatureTropicalIs.uproject"
            ),
            "bytes": 175,
            "sha256": (
                "3ABBBF335CC8A1E66BF87F3EAF5804B74890840B493AA57BA7BDD910607CD1AD"
            ),
            "engine_association": "5.4",
        },
    },
}

CANDIDATE_CONTRACTS = {
    (
        "fab.12ec20bd-ce21-4d3d-8051-13ffb0fe851e",
        "Landscape/Texture/T_Sand_basecolor.uasset",
    ): {
        "stable_candidate_id": "RED-FAB-ASSET-8021792003EC13E7D10DBB1B",
        "source_bytes": 2268109,
        "source_sha256": (
            "B1B8AE3AD73DE7DD4DD4215E7D420FA273FA63C897675047B9CE922BA19E9C55"
        ),
        "expected_asset_kind": "Texture2D",
        "proposed_role": "desert_ground_basecolor",
    },
    (
        "fab.12ec20bd-ce21-4d3d-8051-13ffb0fe851e",
        "Landscape/Texture/T_Sand_normal.uasset",
    ): {
        "stable_candidate_id": "RED-FAB-ASSET-0136F15C7D44ADF6C94C719B",
        "source_bytes": 14941055,
        "source_sha256": (
            "F03811DD1E78ECBEE5D8DA1BD4D045DD70E32B9860228C0D4CEBB06A65DC0606"
        ),
        "expected_asset_kind": "Texture2D",
        "proposed_role": "desert_ground_normal",
    },
    (
        "fab.12ec20bd-ce21-4d3d-8051-13ffb0fe851e",
        "Landscape/Texture/T_Sand_Roughness.uasset",
    ): {
        "stable_candidate_id": "RED-FAB-ASSET-A4ECC3D88041390347B5EB9E",
        "source_bytes": 1380500,
        "source_sha256": (
            "C8558DA672079509E2CA0E88F366F8AC09990C10D0C218356CD9C72CE5ECD541"
        ),
        "expected_asset_kind": "Texture2D",
        "proposed_role": "desert_ground_roughness",
    },
    (
        "fab.12ec20bd-ce21-4d3d-8051-13ffb0fe851e",
        "Model/Rocks/SM_RockRoundDesert_02.uasset",
    ): {
        "stable_candidate_id": "RED-FAB-ASSET-55D22F834072AFF6229BB14A",
        "source_bytes": 462968,
        "source_sha256": (
            "C2FA1CB56A81BB9F3436D386326794F7515C6B2470EDF2F884F003463E62C1DF"
        ),
        "expected_asset_kind": "StaticMesh",
        "proposed_role": "desert_geology_anchor",
    },
    (
        "fab.12ec20bd-ce21-4d3d-8051-13ffb0fe851e",
        "Model/Tree/SM_AcaciaTree_01.uasset",
    ): {
        "stable_candidate_id": "RED-FAB-ASSET-A4F6D5680DC132465128D65B",
        "source_bytes": 1486386,
        "source_sha256": (
            "320F5A8419D63B85BE354E1C1A34B9F5A63A2B817923DF4D9A323259D6AE4EC8"
        ),
        "expected_asset_kind": "StaticMesh",
        "proposed_role": "savanna_canopy_anchor",
    },
    (
        "fab.934c1286-7388-4aa5-a300-e0a7cdf65675",
        "Model/Tree/SM_CoconutTree_01.uasset",
    ): {
        "stable_candidate_id": "RED-FAB-ASSET-020D6DAAE70219B6F907C75B",
        "source_bytes": 152377,
        "source_sha256": (
            "925C3DA342358836CEB7F6EAC0933D2B2742459C0F39CB1FFA8D5EA9E4FE82F9"
        ),
        "expected_asset_kind": "StaticMesh",
        "proposed_role": "shoreline_canopy_anchor",
    },
    (
        "fab.934c1286-7388-4aa5-a300-e0a7cdf65675",
        "Model/Plants/SM_Plant_01.uasset",
    ): {
        "stable_candidate_id": "RED-FAB-ASSET-71C6AF42FBE6C8C807395EC0",
        "source_bytes": 56344,
        "source_sha256": (
            "B169632CBB5B73C27616143437B9FD046542260EC60E901E08326453CD46FD7E"
        ),
        "expected_asset_kind": "StaticMesh",
        "proposed_role": "tropical_ground_accent",
    },
    (
        "fab.934c1286-7388-4aa5-a300-e0a7cdf65675",
        "Model/Plants/SM_Coral_01.uasset",
    ): {
        "stable_candidate_id": "RED-FAB-ASSET-3897AB32061911E704F9DEB4",
        "source_bytes": 23931,
        "source_sha256": (
            "D3889034815975E9819CF9439FB657E0D04E139A0EF95555EFA6DE9F8C877CEA"
        ),
        "expected_asset_kind": "StaticMesh",
        "proposed_role": "shallow_water_accent",
    },
    (
        "fab.934c1286-7388-4aa5-a300-e0a7cdf65675",
        "Blueprint/BP_WaterPlane.uasset",
    ): {
        "stable_candidate_id": "RED-FAB-ASSET-F3C4A00B0686FACCA17356E9",
        "source_bytes": 73604,
        "source_sha256": (
            "7AD89A327D9E2D93F6416CA703114827438895B5AB42161A7DF2BC7B1419D219"
        ),
        "expected_asset_kind": "Blueprint",
        "proposed_role": "water_system_candidate",
    },
}

REQUEST_TOP_LEVEL_KEYS = {
    "schema_version",
    "request_id",
    "request_status",
    "selection_method",
    "no_category_fallback",
    "intended_use",
    "packs",
    "candidates",
    "review_gates",
    "authority",
}
PACK_KEYS = {"pack_id", *next(iter(PACK_CONTRACTS.values())).keys()}
CANDIDATE_KEYS = {
    "pack_id",
    "relative_source_path",
    "stable_candidate_id",
    "source_bytes",
    "source_sha256",
    "expected_asset_kind",
    "proposed_role",
}
REVIEW_GATE_KEYS = {
    "source_identity_reviewed",
    "rights_and_noai_boundary_reviewed",
    "ue58_compatibility_reviewed",
    "dependency_closure_reviewed",
    "visual_style_reviewed",
    "performance_reviewed",
    "nwiro_metadata_only_workflow_reviewed",
    "migration_approved",
    "map_placement_approved",
}
AUTHORITY_KEYS = {
    "approval_enabled",
    "reviewer_public_keys",
    "caller_supplied_trust_roots_allowed",
}

PACKAGE_REFERENCE_PATTERN = re.compile(
    rb"/Game/(?:Zenscape_Savanna|Zenscape_Island)/[A-Za-z0-9_./-]+"
)
HEX_64_PATTERN = re.compile(r"^[A-F0-9]{64}$")
SAFE_TOKEN_PATTERN = re.compile(r"^[a-z][a-z0-9_]{2,63}$")


class CrosspackSelectionError(RuntimeError):
    """Raised when the exact source-selection contract cannot be authenticated."""


def canonical_json_bytes(value: object) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest().upper()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def _is_link_or_reparse(path: Path) -> bool:
    metadata = path.lstat()
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    attributes = getattr(metadata, "st_file_attributes", 0)
    return stat.S_ISLNK(metadata.st_mode) or bool(
        reparse_flag and attributes & reparse_flag
    )


def _require_plain_mapping(value: object, label: str) -> dict[str, object]:
    if type(value) is not dict:
        raise CrosspackSelectionError(f"{label} must be a plain object")
    return value


def _reject_duplicate_object_pairs(
    pairs: list[tuple[str, object]],
) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise CrosspackSelectionError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _require_plain_list(value: object, label: str) -> list[object]:
    if type(value) is not list:
        raise CrosspackSelectionError(f"{label} must be a plain array")
    return value


def _require_exact_keys(
    value: Mapping[str, object], expected: set[str], label: str
) -> None:
    actual = set(value)
    if actual != expected:
        raise CrosspackSelectionError(
            f"{label} keys differ: missing={sorted(expected - actual)}, "
            f"extra={sorted(actual - expected)}"
        )


def validate_relative_package_path(raw: object) -> str:
    if type(raw) is not str or not raw:
        raise CrosspackSelectionError("relative_source_path must be a non-empty string")
    if "\\" in raw or ":" in raw or "\x00" in raw:
        raise CrosspackSelectionError(f"unsafe relative_source_path: {raw!r}")
    relative = PurePosixPath(raw)
    if relative.is_absolute() or any(part in {"", ".", ".."} for part in relative.parts):
        raise CrosspackSelectionError(f"unsafe relative_source_path: {raw!r}")
    if relative.suffix != ".uasset":
        raise CrosspackSelectionError(
            f"candidate must name one exact .uasset package: {raw}"
        )
    return relative.as_posix()


def _candidate_id(pack_id: str, relative_path: str) -> str:
    identity = f"{pack_id}\n{relative_path}".encode("utf-8")
    return f"RED-FAB-ASSET-{hashlib.sha256(identity).hexdigest()[:24].upper()}"


def load_request(path: Path) -> tuple[dict[str, object], bytes]:
    if not path.is_file() or _is_link_or_reparse(path):
        raise CrosspackSelectionError(f"request is missing or linked: {path}")
    payload = path.read_bytes()
    try:
        request = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_object_pairs,
            parse_constant=lambda value: (_ for _ in ()).throw(
                CrosspackSelectionError(f"non-finite JSON constant: {value}")
            ),
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CrosspackSelectionError(f"invalid request JSON: {error}") from error
    request = _require_plain_mapping(request, "request")
    validate_request(request)
    return request, payload


def validate_request(request: Mapping[str, object]) -> None:
    _require_exact_keys(request, REQUEST_TOP_LEVEL_KEYS, "request")
    if request["schema_version"] != 1 or type(request["schema_version"]) is not int:
        raise CrosspackSelectionError("schema_version must be exact integer 1")
    if request["request_id"] != EXPECTED_REQUEST_ID:
        raise CrosspackSelectionError("unexpected request_id")
    if request["request_status"] != EXPECTED_REQUEST_STATUS:
        raise CrosspackSelectionError("request_status must remain candidate_only")
    if request["selection_method"] != EXPECTED_SELECTION_METHOD:
        raise CrosspackSelectionError("selection_method must remain exact-path only")
    if request["no_category_fallback"] is not True:
        raise CrosspackSelectionError("no_category_fallback must be true")
    if request["intended_use"] != "isolated_redmmo_crosspack_minihub_review":
        raise CrosspackSelectionError("unexpected intended_use")

    packs = _require_plain_list(request["packs"], "packs")
    if len(packs) != len(PACK_CONTRACTS):
        raise CrosspackSelectionError("request must contain both exact packs once")
    observed_pack_ids: set[str] = set()
    for raw_pack in packs:
        pack = _require_plain_mapping(raw_pack, "pack")
        _require_exact_keys(pack, PACK_KEYS, "pack")
        pack_id = pack["pack_id"]
        if type(pack_id) is not str or pack_id not in PACK_CONTRACTS:
            raise CrosspackSelectionError(f"unknown pack_id: {pack_id!r}")
        if pack_id in observed_pack_ids:
            raise CrosspackSelectionError(f"duplicate pack_id: {pack_id}")
        observed_pack_ids.add(pack_id)
        for key, expected_value in PACK_CONTRACTS[pack_id].items():
            if pack[key] != expected_value or type(pack[key]) is not type(expected_value):
                raise CrosspackSelectionError(
                    f"pack {pack_id} field {key} does not match pinned contract"
                )
    if observed_pack_ids != set(PACK_CONTRACTS):
        raise CrosspackSelectionError("request does not cover both pinned packs")

    candidates = _require_plain_list(request["candidates"], "candidates")
    if not candidates:
        raise CrosspackSelectionError("at least one exact candidate is required")
    observed_candidates: set[tuple[str, str]] = set()
    observed_candidate_packs: set[str] = set()
    for raw_candidate in candidates:
        candidate = _require_plain_mapping(raw_candidate, "candidate")
        _require_exact_keys(candidate, CANDIDATE_KEYS, "candidate")
        pack_id = candidate["pack_id"]
        if type(pack_id) is not str or pack_id not in PACK_CONTRACTS:
            raise CrosspackSelectionError(f"candidate has unknown pack_id: {pack_id!r}")
        relative = validate_relative_package_path(candidate["relative_source_path"])
        exact_key = (pack_id, relative)
        dedupe_key = (pack_id, relative.casefold())
        if dedupe_key in observed_candidates:
            raise CrosspackSelectionError(
                f"duplicate exact candidate: {pack_id}:{relative}"
            )
        observed_candidates.add(dedupe_key)
        observed_candidate_packs.add(pack_id)
        expected = CANDIDATE_CONTRACTS.get(exact_key)
        if expected is None:
            raise CrosspackSelectionError(
                f"candidate is not in the pinned exact-ID allowlist: "
                f"{pack_id}:{relative}"
            )
        for field, expected_value in expected.items():
            if (
                candidate[field] != expected_value
                or type(candidate[field]) is not type(expected_value)
            ):
                raise CrosspackSelectionError(
                    f"candidate {pack_id}:{relative} field {field} does not "
                    "match the pinned exact-ID contract"
                )
        if candidate["stable_candidate_id"] != _candidate_id(pack_id, relative):
            raise CrosspackSelectionError(
                f"candidate stable ID does not authenticate its exact path: "
                f"{pack_id}:{relative}"
            )
        if (
            type(candidate["source_sha256"]) is not str
            or not HEX_64_PATTERN.fullmatch(candidate["source_sha256"])
        ):
            raise CrosspackSelectionError("candidate source_sha256 is not canonical")
        if (
            type(candidate["source_bytes"]) is not int
            or candidate["source_bytes"] <= 0
        ):
            raise CrosspackSelectionError("candidate source_bytes must be positive")
        role = candidate["proposed_role"]
        if type(role) is not str or not SAFE_TOKEN_PATTERN.fullmatch(role):
            raise CrosspackSelectionError(f"invalid proposed_role: {role!r}")
    expected_dedupe_keys = {
        (pack_id, relative.casefold())
        for pack_id, relative in CANDIDATE_CONTRACTS
    }
    if observed_candidates != expected_dedupe_keys:
        raise CrosspackSelectionError(
            "request candidates do not exactly match the pinned exact-ID allowlist"
        )
    if observed_candidate_packs != set(PACK_CONTRACTS):
        raise CrosspackSelectionError("candidate allowlist must represent both packs")

    gates = _require_plain_mapping(request["review_gates"], "review_gates")
    _require_exact_keys(gates, REVIEW_GATE_KEYS, "review_gates")
    if any(value is not False for value in gates.values()):
        raise CrosspackSelectionError("every review and approval gate must remain false")

    authority = _require_plain_mapping(request["authority"], "authority")
    _require_exact_keys(authority, AUTHORITY_KEYS, "authority")
    if authority["approval_enabled"] is not False:
        raise CrosspackSelectionError("approval must remain disabled")
    if authority["caller_supplied_trust_roots_allowed"] is not False:
        raise CrosspackSelectionError("caller-supplied trust roots are forbidden")
    if authority["reviewer_public_keys"] != []:
        raise CrosspackSelectionError("reviewer_public_keys must remain empty")


def _reject_linked_path_chain(path: Path, label: str) -> None:
    for component in (path, *path.parents):
        if not component.exists():
            raise CrosspackSelectionError(
                f"{label} path chain contains a missing component: {component}"
            )
        if _is_link_or_reparse(component):
            raise CrosspackSelectionError(
                f"{label} path chain contains a link or reparse point: {component}"
            )


def validate_source_root(path: Path, label: str) -> Path:
    absolute = path.absolute()
    if not absolute.is_dir():
        raise CrosspackSelectionError(f"{label} is missing or linked: {absolute}")
    _reject_linked_path_chain(absolute, label)
    resolved = absolute.resolve()
    identity_contract = SOURCE_IDENTITY_CONTRACTS[label]
    expected_root = Path(str(identity_contract["canonical_root"])).resolve()
    if os.path.normcase(str(resolved)) != os.path.normcase(str(expected_root)):
        raise CrosspackSelectionError(
            f"{label} source root is not the pinned canonical root: {resolved}"
        )
    expected_leaf = str(PACK_CONTRACTS[label]["mount_root"]).rsplit("/", 1)[-1]
    if resolved.name != expected_leaf:
        raise CrosspackSelectionError(
            f"{label} must bind the exact {expected_leaf} source root: {resolved}"
        )
    return resolved


def _load_tropical_project_descriptor(
    tropical_root: Path,
) -> dict[str, object]:
    if tropical_root.parent.name != "Content":
        raise CrosspackSelectionError(
            f"Tropical root is not beneath one project Content directory: {tropical_root}"
        )
    project_root = tropical_root.parent.parent
    descriptors = sorted(project_root.glob("*.uproject"), key=lambda path: path.name.casefold())
    if len(descriptors) != 1:
        raise CrosspackSelectionError(
            f"Tropical source project must contain exactly one .uproject: {project_root}"
        )
    descriptor = descriptors[0]
    if _is_link_or_reparse(descriptor) or not descriptor.is_file():
        raise CrosspackSelectionError(
            f"Tropical project descriptor is missing or linked: {descriptor}"
        )
    payload = descriptor.read_bytes()
    try:
        parsed = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_object_pairs,
            parse_constant=lambda value: (_ for _ in ()).throw(
                CrosspackSelectionError(
                    f"non-finite Tropical descriptor constant: {value}"
                )
            ),
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CrosspackSelectionError(
            f"invalid Tropical project descriptor: {error}"
        ) from error
    parsed = _require_plain_mapping(parsed, "Tropical project descriptor")
    expected = PACK_CONTRACTS[
        "fab.934c1286-7388-4aa5-a300-e0a7cdf65675"
    ]["source_engine_association"]
    if parsed.get("EngineAssociation") != expected:
        raise CrosspackSelectionError(
            "Tropical EngineAssociation does not match the pinned source identity"
        )
    record = {
        "path": str(descriptor.resolve()),
        "bytes": len(payload),
        "sha256": sha256_bytes(payload),
        "engine_association": expected,
    }
    identity_contract = SOURCE_IDENTITY_CONTRACTS[
        "fab.934c1286-7388-4aa5-a300-e0a7cdf65675"
    ]["source_project_descriptor"]
    if type(identity_contract) is not dict or record != identity_contract:
        raise CrosspackSelectionError(
            "Tropical project descriptor does not match the pinned byte identity"
        )
    return record


def _walk_source_tree(
    root: Path, hash_cache: dict[Path, str]
) -> tuple[list[dict[str, object]], str]:
    records: list[dict[str, object]] = []

    def raise_walk_error(error: OSError) -> None:
        raise CrosspackSelectionError(f"unable to walk {root}: {error}") from error

    for raw_directory, directory_names, file_names in os.walk(
        root, topdown=True, onerror=raise_walk_error, followlinks=False
    ):
        directory = Path(raw_directory)
        if _is_link_or_reparse(directory):
            raise CrosspackSelectionError(f"linked source directory: {directory}")
        directory_names.sort(key=str.casefold)
        file_names.sort(key=str.casefold)
        for name in file_names:
            path = directory / name
            if _is_link_or_reparse(path) or not path.is_file():
                raise CrosspackSelectionError(f"unsafe source file: {path}")
            relative = path.relative_to(root).as_posix()
            digest = hash_cache.setdefault(path, sha256_file(path))
            records.append(
                {
                    "relative_path": relative,
                    "bytes": path.stat().st_size,
                    "sha256": digest,
                }
            )
    records.sort(key=lambda record: str(record["relative_path"]).casefold())
    return records, sha256_bytes(canonical_json_bytes(records))


def _package_name(pack_id: str, relative_path: str) -> str:
    mount_root = str(PACK_CONTRACTS[pack_id]["mount_root"])
    return f"{mount_root}/{PurePosixPath(relative_path).with_suffix('').as_posix()}"


def _reference_to_disk(
    package_name: str, roots_by_pack: Mapping[str, Path]
) -> tuple[str, Path] | None:
    normalized = package_name.split(".", 1)[0].rstrip("/")
    for pack_id, contract in PACK_CONTRACTS.items():
        mount_root = str(contract["mount_root"])
        prefix = mount_root + "/"
        if normalized.startswith(prefix):
            relative_no_suffix = normalized.removeprefix(prefix)
            root = roots_by_pack[pack_id]
            uasset = root / PurePosixPath(relative_no_suffix + ".uasset")
            umap = root / PurePosixPath(relative_no_suffix + ".umap")
            matches = [path for path in (uasset, umap) if path.is_file()]
            if len(matches) != 1:
                raise CrosspackSelectionError(
                    f"serialized package reference does not resolve exactly once: "
                    f"{normalized}"
                )
            return pack_id, matches[0]
    return None


def _serialized_package_references(path: Path) -> list[str]:
    size = path.stat().st_size
    if size > MAX_PACKAGE_BYTES:
        raise CrosspackSelectionError(
            f"package exceeds bounded reference-scan size: {path}: {size}"
        )
    payload = path.read_bytes()
    references = {
        match.group(0).decode("ascii").split(".", 1)[0].rstrip("/")
        for match in PACKAGE_REFERENCE_PATTERN.finditer(payload)
    }
    return sorted(references, key=str.casefold)


def build_manifest(
    request: Mapping[str, object],
    *,
    request_sha256: str,
    roots_by_pack: Mapping[str, Path],
) -> dict[str, object]:
    validate_request(request)
    if not HEX_64_PATTERN.fullmatch(request_sha256):
        raise CrosspackSelectionError("request_sha256 must be 64 uppercase hex")
    if set(roots_by_pack) != set(PACK_CONTRACTS):
        raise CrosspackSelectionError("roots_by_pack must bind both exact packs")
    roots = {
        pack_id: validate_source_root(path, pack_id)
        for pack_id, path in roots_by_pack.items()
    }

    hash_cache: dict[Path, str] = {}
    pack_records: list[dict[str, object]] = []
    initial_tree_signatures: dict[str, tuple[int, int, str]] = {}
    initial_project_descriptors: dict[str, dict[str, object] | None] = {}
    for pack_id in sorted(PACK_CONTRACTS):
        tree_records, tree_sha256 = _walk_source_tree(roots[pack_id], hash_cache)
        initial_tree_signatures[pack_id] = (
            len(tree_records),
            sum(int(record["bytes"]) for record in tree_records),
            tree_sha256,
        )
        identity_contract = SOURCE_IDENTITY_CONTRACTS[pack_id]
        expected_tree_signature = (
            identity_contract["source_file_count"],
            identity_contract["source_bytes"],
            identity_contract["source_tree_sha256"],
        )
        if initial_tree_signatures[pack_id] != expected_tree_signature:
            raise CrosspackSelectionError(
                f"source tree does not match the pinned byte identity: {pack_id}"
            )
        source_project_descriptor = (
            _load_tropical_project_descriptor(roots[pack_id])
            if pack_id == "fab.934c1286-7388-4aa5-a300-e0a7cdf65675"
            else None
        )
        if source_project_descriptor != identity_contract["source_project_descriptor"]:
            raise CrosspackSelectionError(
                f"source project descriptor identity differs: {pack_id}"
            )
        initial_project_descriptors[pack_id] = source_project_descriptor
        pack_records.append(
            {
                "pack_id": pack_id,
                "listing_id": PACK_CONTRACTS[pack_id]["listing_id"],
                "mount_root": PACK_CONTRACTS[pack_id]["mount_root"],
                "source_root": str(roots[pack_id]),
                "source_file_count": len(tree_records),
                "source_bytes": sum(int(record["bytes"]) for record in tree_records),
                "source_tree_sha256": tree_sha256,
                "declared_unreal_versions": PACK_CONTRACTS[pack_id][
                    "declared_unreal_versions"
                ],
                "source_engine_association": PACK_CONTRACTS[pack_id][
                    "source_engine_association"
                ],
                "source_project_descriptor": source_project_descriptor,
                "fab_license": "Standard License",
                "allows_usage_with_ai": False,
                "source_policy": "vendor_source_immutable",
            }
        )

    selected_by_path: dict[Path, dict[str, object]] = {}
    selected_records: list[dict[str, object]] = []
    for raw_candidate in request["candidates"]:
        candidate = dict(raw_candidate)
        pack_id = str(candidate["pack_id"])
        relative = validate_relative_package_path(candidate["relative_source_path"])
        path = roots[pack_id] / PurePosixPath(relative)
        resolved = path.resolve()
        try:
            resolved.relative_to(roots[pack_id])
        except ValueError as error:
            raise CrosspackSelectionError(
                f"candidate escapes source root: {relative}"
            ) from error
        if not resolved.is_file() or _is_link_or_reparse(resolved):
            raise CrosspackSelectionError(f"candidate is missing or linked: {resolved}")
        candidate_contract = CANDIDATE_CONTRACTS[(pack_id, relative)]
        source_bytes = resolved.stat().st_size
        source_sha256 = hash_cache.setdefault(resolved, sha256_file(resolved))
        if (
            source_bytes != candidate_contract["source_bytes"]
            or source_sha256 != candidate_contract["source_sha256"]
        ):
            raise CrosspackSelectionError(
                f"candidate bytes do not match the pinned exact-ID allowlist: "
                f"{pack_id}:{relative}"
            )
        package_name = _package_name(pack_id, relative)
        asset_name = PurePosixPath(relative).stem
        record = {
            "stable_candidate_id": candidate["stable_candidate_id"],
            "pack_id": pack_id,
            "listing_id": PACK_CONTRACTS[pack_id]["listing_id"],
            "relative_source_path": relative,
            "source_bytes": source_bytes,
            "source_sha256": source_sha256,
            "package_name": package_name,
            "object_path": f"{package_name}.{asset_name}",
            "expected_asset_kind": candidate["expected_asset_kind"],
            "proposed_role": candidate["proposed_role"],
            "source_policy": "vendor_source_immutable",
            "review_status": "unreviewed_exact_candidate",
        }
        selected_by_path[resolved] = record
        selected_records.append(record)

    selected_records.sort(key=lambda record: str(record["stable_candidate_id"]))

    closure_paths: set[Path] = set(selected_by_path)
    pending = deque(sorted(closure_paths, key=lambda path: str(path).casefold()))
    while pending:
        path = pending.popleft()
        for package_reference in _serialized_package_references(path):
            resolved_reference = _reference_to_disk(package_reference, roots)
            if resolved_reference is None:
                continue
            _, dependency_path = resolved_reference
            dependency_path = dependency_path.resolve()
            if dependency_path not in closure_paths:
                closure_paths.add(dependency_path)
                pending.append(dependency_path)

    closure_records: list[dict[str, object]] = []
    root_to_pack = {root: pack_id for pack_id, root in roots.items()}
    for path in sorted(closure_paths, key=lambda item: str(item).casefold()):
        matching = [
            (root, pack_id)
            for root, pack_id in root_to_pack.items()
            if path == root or root in path.parents
        ]
        if len(matching) != 1:
            raise CrosspackSelectionError(f"closure path has ambiguous source root: {path}")
        root, pack_id = matching[0]
        relative = path.relative_to(root).as_posix()
        package_name = _package_name(pack_id, relative)
        selected = selected_by_path.get(path)
        closure_records.append(
            {
                "pack_id": pack_id,
                "relative_source_path": relative,
                "package_name": package_name,
                "source_bytes": path.stat().st_size,
                "source_sha256": hash_cache.setdefault(path, sha256_file(path)),
                "selected_primary": selected is not None,
                "stable_candidate_id": (
                    selected["stable_candidate_id"] if selected is not None else None
                ),
                "proposed_role": (
                    selected["proposed_role"] if selected is not None else "dependency"
                ),
            }
        )

    for pack_id in sorted(PACK_CONTRACTS):
        final_records, final_tree_sha256 = _walk_source_tree(roots[pack_id], {})
        final_signature = (
            len(final_records),
            sum(int(record["bytes"]) for record in final_records),
            final_tree_sha256,
        )
        if final_signature != initial_tree_signatures[pack_id]:
            raise CrosspackSelectionError(
                f"source tree changed during manifest construction: {pack_id}"
            )
        final_descriptor = (
            _load_tropical_project_descriptor(roots[pack_id])
            if pack_id == "fab.934c1286-7388-4aa5-a300-e0a7cdf65675"
            else None
        )
        if final_descriptor != initial_project_descriptors[pack_id]:
            raise CrosspackSelectionError(
                f"source project descriptor changed during construction: {pack_id}"
            )

    manifest: dict[str, object] = {
        "schema_version": 1,
        "manifest_id": "redmmo-crosspack-minihub-source-selection-manifest",
        "evidence_class": "static",
        "status": "review_request_only",
        "request": {
            "request_id": request["request_id"],
            "request_sha256": request_sha256,
            "selection_method": EXPECTED_SELECTION_METHOD,
            "no_category_fallback": True,
        },
        "summary": {
            "pack_count": len(pack_records),
            "selected_primary_count": len(selected_records),
            "offline_reference_closure_count": len(closure_records),
            "selection_ready": False,
            "migration_ready": False,
            "nwiro_ready": False,
            "map_authoring_ready": False,
        },
        "packs": pack_records,
        "selected_candidates": selected_records,
        "offline_serialized_reference_closure": closure_records,
        "review_gates": dict(request["review_gates"]),
        "authority": dict(request["authority"]),
        "nwiro_data_boundary": {
            "source_bytes_may_be_uploaded": False,
            "metadata_only_existing_asset_placement_may_be_reviewed": True,
            "actual_plugin_transport_and_provider_behavior_verified": False,
            "reason": (
                "both Fab records carry allows_usage_with_ai=false; no source "
                "mesh, texture, material, map, or derived pixel payload may be "
                "sent to a generative provider"
            ),
        },
        "compatibility": {
            "installed_engine": "5.8",
            "vendor_declared_maximum": "5.6",
            "ue58_forward_conversion_verified": False,
            "isolated_conversion_required": True,
        },
        "limitations": [
            "serialized ASCII package-reference traversal is not Unreal Asset Registry dependency proof",
            "asset class, visual identity, scale, collision, LOD, Nanite, material quality, and performance are unverified",
            "the Tropical packages are not migrated into Titan",
            "the Desert packages are project-present but have not been opened or forward-converted under UE 5.8",
            "Nwiro has not been launched or proven to use a metadata-only existing-asset workflow",
            "no map was created or modified and no candidate is approved",
        ],
    }
    manifest["semantic_sha256"] = sha256_bytes(
        canonical_json_bytes({key: value for key, value in manifest.items() if key != "semantic_sha256"})
    )
    return manifest


def validate_output_path(
    output_path: Path, diagnostics_root: Path = DEFAULT_DIAGNOSTICS_ROOT
) -> Path:
    resolved = output_path.resolve()
    root = diagnostics_root.resolve()
    try:
        resolved.relative_to(root)
    except ValueError as error:
        raise CrosspackSelectionError(
            f"output must remain under diagnostics root {root}: {resolved}"
        ) from error
    if resolved.suffix.casefold() != ".json":
        raise CrosspackSelectionError("output must use a .json suffix")
    if resolved.exists():
        raise CrosspackSelectionError(f"refusing to overwrite output: {resolved}")
    return resolved


def write_manifest_no_clobber(
    output_path: Path,
    manifest: Mapping[str, object],
    diagnostics_root: Path = DEFAULT_DIAGNOSTICS_ROOT,
) -> str:
    output = validate_output_path(output_path, diagnostics_root)
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = canonical_json_bytes(manifest)
    try:
        with output.open("xb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError as error:
        raise CrosspackSelectionError(
            f"refusing to overwrite output: {output}"
        ) from error
    return sha256_bytes(payload)


def verify_pinned_sources(
    manifest: Mapping[str, object],
    roots_by_pack: Mapping[str, Path],
) -> None:
    if set(roots_by_pack) != set(PACK_CONTRACTS):
        raise CrosspackSelectionError("roots_by_pack must bind both exact packs")
    roots = {
        pack_id: validate_source_root(path, pack_id)
        for pack_id, path in roots_by_pack.items()
    }
    pack_records = _require_plain_list(manifest.get("packs"), "manifest packs")
    by_pack: dict[str, dict[str, object]] = {}
    for raw_record in pack_records:
        record = _require_plain_mapping(raw_record, "manifest pack record")
        pack_id = record.get("pack_id")
        if type(pack_id) is not str or pack_id in by_pack:
            raise CrosspackSelectionError("manifest pack identities are invalid")
        by_pack[pack_id] = record
    if set(by_pack) != set(PACK_CONTRACTS):
        raise CrosspackSelectionError("manifest does not contain both exact packs")

    for pack_id in sorted(PACK_CONTRACTS):
        records, tree_sha256 = _walk_source_tree(roots[pack_id], {})
        observed = {
            "source_file_count": len(records),
            "source_bytes": sum(int(record["bytes"]) for record in records),
            "source_tree_sha256": tree_sha256,
        }
        identity = SOURCE_IDENTITY_CONTRACTS[pack_id]
        expected = {
            "source_file_count": identity["source_file_count"],
            "source_bytes": identity["source_bytes"],
            "source_tree_sha256": identity["source_tree_sha256"],
        }
        manifest_identity = {
            key: by_pack[pack_id].get(key)
            for key in (
                "source_file_count",
                "source_bytes",
                "source_tree_sha256",
            )
        }
        if observed != expected or manifest_identity != expected:
            raise CrosspackSelectionError(
                f"source tree is not publication-stable: {pack_id}"
            )
        descriptor = (
            _load_tropical_project_descriptor(roots[pack_id])
            if pack_id == "fab.934c1286-7388-4aa5-a300-e0a7cdf65675"
            else None
        )
        if (
            descriptor != identity["source_project_descriptor"]
            or by_pack[pack_id].get("source_project_descriptor") != descriptor
        ):
            raise CrosspackSelectionError(
                f"source descriptor is not publication-stable: {pack_id}"
            )


def write_authenticated_manifest_no_clobber(
    output_path: Path,
    manifest: Mapping[str, object],
    roots_by_pack: Mapping[str, Path],
    diagnostics_root: Path = DEFAULT_DIAGNOSTICS_ROOT,
) -> str:
    output = validate_output_path(output_path, diagnostics_root)
    verify_pinned_sources(manifest, roots_by_pack)
    digest = write_manifest_no_clobber(output, manifest, diagnostics_root)
    try:
        verify_pinned_sources(manifest, roots_by_pack)
    except BaseException:
        try:
            output.unlink(missing_ok=True)
        except OSError as cleanup_error:
            raise CrosspackSelectionError(
                f"source changed after publication and cleanup failed: {output}: "
                f"{cleanup_error}"
            ) from cleanup_error
        raise
    return digest


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", required=True, type=Path)
    parser.add_argument("--desert-root", required=True, type=Path)
    parser.add_argument("--tropical-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    request, request_payload = load_request(args.request.resolve())
    roots = {
        "fab.12ec20bd-ce21-4d3d-8051-13ffb0fe851e": args.desert_root,
        "fab.934c1286-7388-4aa5-a300-e0a7cdf65675": args.tropical_root,
    }
    manifest = build_manifest(
        request,
        request_sha256=sha256_bytes(request_payload),
        roots_by_pack=roots,
    )
    output_sha256 = write_authenticated_manifest_no_clobber(
        args.output,
        manifest,
        roots,
    )
    print(
        json.dumps(
            {
                "output": str(args.output.resolve()),
                "output_sha256": output_sha256,
                "semantic_sha256": manifest["semantic_sha256"],
                "selected_primary_count": manifest["summary"][
                    "selected_primary_count"
                ],
                "offline_reference_closure_count": manifest["summary"][
                    "offline_reference_closure_count"
                ],
                "selection_ready": False,
                "migration_ready": False,
                "nwiro_ready": False,
                "map_authoring_ready": False,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
