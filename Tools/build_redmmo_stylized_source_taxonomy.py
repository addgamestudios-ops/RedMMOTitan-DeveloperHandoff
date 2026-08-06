"""Build a deterministic semantic taxonomy overlay for stylized source textures.

The authenticated v2 import plan preserves the immutable source tree's first
directory as its import category. That is useful provenance, but it is not a
safe object-family taxonomy: a texture made of wood can belong to a door rather
than a tree. This offline overlay keeps source category, object family, and
material substance separate and marks conflicts for human review.

The tool never changes the v2 plan, source files, Unreal packages, or maps.
"""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
from typing import Any, Mapping, Sequence

try:
    from Tools import import_redmmo_stylized_source_library as source_import
except ModuleNotFoundError as exc:
    if exc.name != "Tools":
        raise
    import import_redmmo_stylized_source_library as source_import


TAXONOMY_SCHEMA = "redmmotitan.stylized_source_taxonomy.v3"
RULESET_VERSION = "redmmo-object-family-material-substance-v1"
TAXONOMY_DIAGNOSTICS_ROOT = (
    source_import.DEFAULT_DIAGNOSTICS_ROOT / "Taxonomy"
)
_SHA256 = re.compile(r"^[0-9A-F]{64}$")
_CAMEL_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
_TOKEN = re.compile(r"[a-z0-9]+")


SPECIFIC_FAMILY_TOKENS: tuple[tuple[str, frozenset[str]], ...] = (
    (
        "architecture_door",
        frozenset({"door", "doorway", "entry", "entrance", "gate", "gateway"}),
    ),
    ("architecture_window", frozenset({"window"})),
    (
        "architecture_wall",
        frozenset({"wall", "fence", "barricade", "railing", "balustrade"}),
    ),
    ("architecture_roof", frozenset({"roof", "ceiling"})),
    (
        "architecture_floor_path",
        frozenset(
            {
                "floor",
                "road",
                "path",
                "walkway",
                "bridge",
                "stairs",
                "stair",
                "ramp",
            }
        ),
    ),
    (
        "architecture_building",
        frozenset(
            {"building", "house", "hut", "temple", "tower", "castle", "fort"}
        ),
    ),
    (
        "vegetation_tree",
        frozenset({"tree", "trunk", "branch", "stump", "log", "sapling"}),
    ),
    ("vegetation_grass", frozenset({"grass"})),
    (
        "vegetation_foliage",
        frozenset(
            {
                "foliage",
                "leaf",
                "leaves",
                "bush",
                "shrub",
                "fern",
                "plant",
                "vine",
                "flower",
                "moss",
            }
        ),
    ),
    (
        "geology_rock",
        frozenset({"rock", "boulder", "cliff", "outcrop", "pebble"}),
    ),
    (
        "environment_water",
        frozenset(
            {
                "water",
                "ocean",
                "river",
                "lake",
                "waterfall",
                "falls",
                "shoreline",
                "wave",
            }
        ),
    ),
    (
        "terrain_surface",
        frozenset(
            {
                "terrain",
                "ground",
                "soil",
                "dirt",
                "sand",
                "dune",
                "mud",
                "snow",
                "ice",
                "lava",
            }
        ),
    ),
    ("mineral_crystal", frozenset({"crystal", "ore", "mineral"})),
    ("fx", frozenset({"particle", "vfx"})),
)

GENERIC_PROP_TOKENS = frozenset({"prp", "prop", "dec", "decor", "decoration"})
TECHNICAL_TOKENS = frozenset({"icon", "ui", "atlas", "worldmap", "minimap"})

MATERIAL_TOKEN_RULES: tuple[tuple[str, frozenset[str]], ...] = (
    ("wood", frozenset({"wood", "wooden", "timber", "plank", "bark"})),
    (
        "metal",
        frozenset(
            {
                "metal",
                "iron",
                "steel",
                "brass",
                "copper",
                "bronze",
                "gold",
                "silver",
            }
        ),
    ),
    (
        "masonry",
        frozenset({"stone", "brick", "masonry", "concrete", "stucco"}),
    ),
    (
        "organic_vegetation",
        frozenset(
            {
                "grass",
                "foliage",
                "leaf",
                "leaves",
                "bush",
                "shrub",
                "fern",
                "plant",
                "vine",
                "flower",
                "moss",
            }
        ),
    ),
    ("soil", frozenset({"soil", "dirt", "mud", "ground"})),
    ("sand", frozenset({"sand", "dune"})),
    ("snow_ice", frozenset({"snow", "ice", "frost"})),
    ("water", frozenset({"water", "ocean", "river", "lake", "wet"})),
    ("lava", frozenset({"lava", "magma"})),
    ("crystal", frozenset({"crystal", "ore", "mineral", "gem"})),
    ("fabric", frozenset({"fabric", "cloth", "leather", "canvas"})),
    ("glass", frozenset({"glass"})),
    ("ceramic", frozenset({"ceramic", "tile", "porcelain"})),
)

SOURCE_CATEGORY_KINDS: Mapping[str, str] = {
    "Stylized_Crystal": "object_family",
    "Stylized_Fabric": "material_substance",
    "Stylized_Foliage": "object_family",
    "Stylized_FX": "object_family",
    "Stylized_Grass": "object_family",
    "Stylized_Ground": "object_family",
    "Stylized_Lava": "object_family",
    "Stylized_Maps": "technical_or_mixed",
    "Stylized_Masonry": "material_substance",
    "Stylized_Metal": "material_substance",
    "Stylized_Props": "mixed_object_family",
    "Stylized_Rock": "object_family",
    "Stylized_Sand": "object_family",
    "Stylized_Sky": "object_family",
    "Stylized_SnowIce": "object_family",
    "Stylized_Structure": "mixed_object_family",
    "Stylized_Terrain": "object_family",
    "Stylized_Trees": "object_family",
    "Stylized_Water": "object_family",
}

SOURCE_CATEGORY_ALLOWED_FAMILIES: Mapping[str, frozenset[str]] = {
    "Stylized_Crystal": frozenset({"mineral_crystal"}),
    "Stylized_Foliage": frozenset(
        {"vegetation_foliage", "vegetation_grass", "vegetation_tree"}
    ),
    "Stylized_FX": frozenset({"fx"}),
    "Stylized_Grass": frozenset({"vegetation_grass", "vegetation_foliage"}),
    "Stylized_Ground": frozenset({"terrain_surface"}),
    "Stylized_Lava": frozenset({"terrain_surface"}),
    "Stylized_Rock": frozenset({"geology_rock"}),
    "Stylized_Sand": frozenset({"terrain_surface"}),
    "Stylized_SnowIce": frozenset({"terrain_surface"}),
    "Stylized_Terrain": frozenset({"terrain_surface"}),
    "Stylized_Trees": frozenset({"vegetation_tree"}),
    "Stylized_Water": frozenset({"environment_water"}),
}

FAMILY_LIBRARY_PATHS: Mapping[str, str] = {
    "architecture_door": "Architecture/Doors",
    "architecture_window": "Architecture/Windows",
    "architecture_wall": "Architecture/Walls",
    "architecture_roof": "Architecture/Roofs",
    "architecture_floor_path": "Architecture/Floors_Paths",
    "architecture_building": "Architecture/Buildings",
    "vegetation_tree": "Environment/Vegetation/Trees",
    "vegetation_grass": "Environment/Vegetation/Grass",
    "vegetation_foliage": "Environment/Vegetation/Foliage",
    "geology_rock": "Environment/Geology/Rocks",
    "environment_water": "Environment/Water",
    "terrain_surface": "Environment/Terrain",
    "mineral_crystal": "Environment/Geology/Crystals",
    "fx": "FX",
    "prop_generic": "Props/Unsorted",
    "technical_ui": "Technical/UI",
}


@dataclass(frozen=True)
class TaxonomyRecord:
    index: int
    stable_source_id: str
    relative_path: str
    source_sha256: str
    source_category: str
    source_category_kind: str
    texture_semantic: str
    v2_object_path: str
    object_family: str
    classification_confidence: str
    matched_family_tokens: tuple[str, ...]
    material_tags: tuple[str, ...]
    review_required: bool
    review_reasons: tuple[str, ...]
    recommended_library_path: str | None


def _canonical_json_bytes(payload: object) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
        allow_nan=False,
    ).encode("utf-8")


def _digest(payload: object) -> str:
    return hashlib.sha256(_canonical_json_bytes(payload)).hexdigest().upper()


def _record_payload(record: TaxonomyRecord) -> dict[str, object]:
    payload: dict[str, object] = asdict(record)
    payload["matched_family_tokens"] = list(record.matched_family_tokens)
    payload["material_tags"] = list(record.material_tags)
    payload["review_reasons"] = list(record.review_reasons)
    return payload


def _ruleset_payload() -> dict[str, object]:
    return {
        "version": RULESET_VERSION,
        "specific_family_tokens": {
            family: sorted(tokens) for family, tokens in SPECIFIC_FAMILY_TOKENS
        },
        "generic_prop_tokens": sorted(GENERIC_PROP_TOKENS),
        "technical_tokens": sorted(TECHNICAL_TOKENS),
        "material_token_rules": {
            tag: sorted(tokens) for tag, tokens in MATERIAL_TOKEN_RULES
        },
        "source_category_kinds": dict(sorted(SOURCE_CATEGORY_KINDS.items())),
        "source_category_allowed_families": {
            category: sorted(families)
            for category, families in sorted(
                SOURCE_CATEGORY_ALLOWED_FAMILIES.items()
            )
        },
        "family_library_paths": dict(sorted(FAMILY_LIBRARY_PATHS.items())),
        "policy": {
            "exclude_source_category_from_object_tokens": True,
            "material_tokens_never_imply_object_family": True,
            "multiple_specific_families_require_review": True,
            "source_object_category_conflicts_require_review": True,
            "review_required_records_have_no_recommended_library_path": True,
        },
    }


RULESET_SHA256 = _digest(_ruleset_payload())


def tokenize_record(relative_path: str) -> tuple[str, ...]:
    relative = PurePosixPath(relative_path)
    if relative.is_absolute() or len(relative.parts) < 2:
        raise RuntimeError(f"Taxonomy path must include a source category: {relative_path}")
    # The first directory is provenance, not evidence of object identity.
    descriptive = "/".join(relative.parts[1:])
    descriptive = _CAMEL_BOUNDARY.sub(" ", descriptive)
    return tuple(_TOKEN.findall(descriptive.casefold()))


def classify_record(record: source_import.ImportRecord) -> TaxonomyRecord:
    tokens = tokenize_record(record.relative_path)
    token_set = frozenset(tokens)
    family_matches: list[tuple[str, tuple[str, ...]]] = []
    for family, rule_tokens in SPECIFIC_FAMILY_TOKENS:
        matched = tuple(sorted(token_set & rule_tokens))
        if matched:
            family_matches.append((family, matched))

    reasons: list[str] = []
    if len(family_matches) == 1:
        object_family, matched_family_tokens = family_matches[0]
        confidence = "high"
    elif len(family_matches) > 1:
        object_family = "ambiguous"
        matched_family_tokens = tuple(
            sorted(
                token
                for _, matched in family_matches
                for token in matched
            )
        )
        confidence = "ambiguous"
        reasons.append("multiple_object_family_matches")
    elif token_set & TECHNICAL_TOKENS:
        object_family = "technical_ui"
        matched_family_tokens = tuple(sorted(token_set & TECHNICAL_TOKENS))
        confidence = "medium"
        reasons.append("technical_name_requires_review")
    elif token_set & GENERIC_PROP_TOKENS:
        object_family = "prop_generic"
        matched_family_tokens = tuple(sorted(token_set & GENERIC_PROP_TOKENS))
        confidence = "medium"
        reasons.append("generic_prop_family_requires_review")
    else:
        object_family = "unresolved"
        matched_family_tokens = ()
        confidence = "none"
        reasons.append("no_high_confidence_object_family_token")

    material_tags = tuple(
        sorted(
            tag
            for tag, rule_tokens in MATERIAL_TOKEN_RULES
            if token_set & rule_tokens
        )
    )
    category_kind = SOURCE_CATEGORY_KINDS.get(
        record.category, "unknown_requires_review"
    )
    if category_kind == "unknown_requires_review":
        reasons.append("unknown_source_category")

    allowed_families = SOURCE_CATEGORY_ALLOWED_FAMILIES.get(record.category)
    if (
        allowed_families is not None
        and object_family not in {"ambiguous", "unresolved"}
        and object_family not in allowed_families
    ):
        reasons.append("source_category_conflicts_object_family")

    review_reasons = tuple(sorted(set(reasons)))
    review_required = bool(review_reasons)
    recommended = (
        None
        if review_required
        else FAMILY_LIBRARY_PATHS.get(object_family)
    )
    if not review_required and recommended is None:
        review_required = True
        review_reasons = ("missing_project_library_mapping",)

    return TaxonomyRecord(
        index=record.index,
        stable_source_id=record.stable_source_id,
        relative_path=record.relative_path,
        source_sha256=record.source_sha256,
        source_category=record.category,
        source_category_kind=category_kind,
        texture_semantic=record.semantic,
        v2_object_path=record.object_path,
        object_family=object_family,
        classification_confidence=confidence,
        matched_family_tokens=matched_family_tokens,
        material_tags=material_tags,
        review_required=review_required,
        review_reasons=review_reasons,
        recommended_library_path=recommended,
    )


def build_taxonomy(
    *,
    plan_path: str | Path,
    plan_file_sha256: str,
    plan: Mapping[str, Any],
    records: Sequence[source_import.ImportRecord],
) -> dict[str, object]:
    normalized_plan_sha = plan_file_sha256.strip().upper()
    if not _SHA256.fullmatch(normalized_plan_sha):
        raise RuntimeError("Plan file SHA256 must be exactly 64 uppercase hex characters")
    taxonomy_records = [classify_record(record) for record in records]
    object_family_counts = Counter(
        record.object_family for record in taxonomy_records
    )
    material_tag_counts = Counter(
        tag for record in taxonomy_records for tag in record.material_tags
    )
    review_reason_counts = Counter(
        reason
        for record in taxonomy_records
        for reason in record.review_reasons
    )
    base: dict[str, object] = {
        "schema": TAXONOMY_SCHEMA,
        "ruleset_version": RULESET_VERSION,
        "ruleset_sha256": RULESET_SHA256,
        "plan_path": Path(plan_path).resolve(strict=False).as_posix(),
        "plan_file_sha256": normalized_plan_sha,
        "plan_sha256": plan.get("plan_sha256"),
        "dataset_sha256": plan.get("dataset_sha256"),
        "source_root": plan.get("source_root"),
        "source_provenance": plan.get("source_provenance"),
        "source_policy": plan.get("source_policy"),
        "record_count": len(taxonomy_records),
        "object_family_counts": dict(sorted(object_family_counts.items())),
        "material_tag_counts": dict(sorted(material_tag_counts.items())),
        "review_reason_counts": dict(sorted(review_reason_counts.items())),
        "review_required_count": sum(
            record.review_required for record in taxonomy_records
        ),
        "promotion_candidate_count": sum(
            not record.review_required for record in taxonomy_records
        ),
        "source_category_conflict_count": sum(
            "source_category_conflicts_object_family" in record.review_reasons
            for record in taxonomy_records
        ),
        "unresolved_count": object_family_counts.get("unresolved", 0),
        "records": [_record_payload(record) for record in taxonomy_records],
    }
    base["taxonomy_sha256"] = _digest(base)
    return base


def validate_taxonomy(
    taxonomy: Mapping[str, Any],
    *,
    plan_path: str | Path,
    plan_file_sha256: str,
    plan: Mapping[str, Any],
    records: Sequence[source_import.ImportRecord],
) -> None:
    expected = build_taxonomy(
        plan_path=plan_path,
        plan_file_sha256=plan_file_sha256,
        plan=plan,
        records=records,
    )
    if dict(taxonomy) != expected:
        raise RuntimeError(
            "Taxonomy overlay is not the exact deterministic result for its plan"
        )


def _validate_taxonomy_path(path: str | Path, *, must_exist: bool) -> Path:
    candidate = source_import._validate_diagnostics_path(
        path, must_exist=must_exist
    )
    taxonomy_root = TAXONOMY_DIAGNOSTICS_ROOT.resolve(strict=False)
    try:
        relative = candidate.relative_to(taxonomy_root)
    except ValueError as exc:
        raise RuntimeError(
            f"Taxonomy file must be below {taxonomy_root}: {candidate}"
        ) from exc
    if not relative.parts:
        raise RuntimeError("Taxonomy output must be a strict child file")
    if candidate.suffix.casefold() != ".json":
        raise RuntimeError("Taxonomy file must use a .json suffix")
    return candidate


def _load_authenticated_plan(
    path: str | Path,
    expected_file_sha256: str,
) -> tuple[Path, str, dict[str, Any], list[source_import.ImportRecord]]:
    expected = expected_file_sha256.strip().upper()
    if not _SHA256.fullmatch(expected):
        raise RuntimeError(
            "Expected plan file SHA256 must be exactly 64 uppercase hex characters"
        )
    plan_path = source_import._validate_diagnostics_path(path, must_exist=True)
    actual = source_import.sha256_file(plan_path)
    if actual != expected:
        raise RuntimeError(
            f"Authenticated plan file SHA256 mismatch: expected {expected}, got {actual}"
        )
    plan, records = source_import._load_plan(
        plan_path,
        verify_source_metadata=False,
        verify_source_hashes=False,
    )
    return plan_path, actual, plan, records


def _load_taxonomy(path: str | Path, expected_file_sha256: str) -> dict[str, Any]:
    expected = expected_file_sha256.strip().upper()
    if not _SHA256.fullmatch(expected):
        raise RuntimeError(
            "Expected taxonomy file SHA256 must be exactly 64 uppercase hex characters"
        )
    taxonomy_path = _validate_taxonomy_path(path, must_exist=True)
    actual = source_import.sha256_file(taxonomy_path)
    if actual != expected:
        raise RuntimeError(
            "Authenticated taxonomy file SHA256 mismatch: "
            f"expected {expected}, got {actual}"
        )
    with taxonomy_path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise RuntimeError("Taxonomy root must be an object")
    return payload


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    build_parser = subparsers.add_parser(
        "build", help="Create a deterministic no-clobber taxonomy overlay"
    )
    build_parser.add_argument("--plan", required=True)
    build_parser.add_argument("--expected-plan-file-sha256", required=True)
    build_parser.add_argument("--output", required=True)

    verify_parser = subparsers.add_parser(
        "verify", help="Verify an existing taxonomy against its plan"
    )
    verify_parser.add_argument("--plan", required=True)
    verify_parser.add_argument("--expected-plan-file-sha256", required=True)
    verify_parser.add_argument("--taxonomy", required=True)
    verify_parser.add_argument("--expected-taxonomy-file-sha256", required=True)
    return parser


def cli(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    plan_path, plan_file_sha, plan, records = _load_authenticated_plan(
        args.plan, args.expected_plan_file_sha256
    )
    if args.command == "build":
        output = _validate_taxonomy_path(args.output, must_exist=False)
        payload = build_taxonomy(
            plan_path=plan_path,
            plan_file_sha256=plan_file_sha,
            plan=plan,
            records=records,
        )
        source_import.write_json_no_clobber(output, payload)
        print(
            "RED_STYLIZED_TAXONOMY_READY "
            f"records={payload['record_count']} "
            f"review_required={payload['review_required_count']} "
            f"conflicts={payload['source_category_conflict_count']} "
            f"sha256={payload['taxonomy_sha256']} output={output}"
        )
        return 0

    taxonomy_path = _validate_taxonomy_path(args.taxonomy, must_exist=True)
    taxonomy = _load_taxonomy(
        taxonomy_path, args.expected_taxonomy_file_sha256
    )
    validate_taxonomy(
        taxonomy,
        plan_path=plan_path,
        plan_file_sha256=plan_file_sha,
        plan=plan,
        records=records,
    )
    print(
        "RED_STYLIZED_TAXONOMY_VALID "
        f"records={taxonomy['record_count']} "
        f"review_required={taxonomy['review_required_count']} "
        f"sha256={taxonomy['taxonomy_sha256']} taxonomy={taxonomy_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(cli())
