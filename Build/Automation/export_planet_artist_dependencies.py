"""Write recursive project-content dependencies for the artist planet handoff."""

import json
import os
import unreal


DEFAULT_ROOTS = [
    "/Game/RedMMO/Maps/RedPlanetGen_50km_ArtistCanvas",
    "/Game/RedMMO/Environment/DA_RED_Planet50Km_FusedHeightfield",
]
FORBIDDEN_PACKAGE_MARKERS = (
    "/Ships/",
    "/UI/",
    "/Characters/",
    "/Weapons/",
    "/SpaceShip/",
    "/Action_",
    "/Jet_Packs",
    "/Projectiles",
    "/Vefects/",
    "/StylizedFX_2/",
)
ROOTS_FILE = os.environ.get("RED_ARTIST_DEPENDENCY_ROOTS")
if ROOTS_FILE:
    with open(ROOTS_FILE, "r", encoding="utf-8") as roots_handle:
        ROOTS = [line.strip() for line in roots_handle if line.strip().startswith("/Game/")]
else:
    ROOTS = DEFAULT_ROOTS
ROOTS = sorted(set(ROOTS))
OUTPUT = os.environ.get(
    "RED_ARTIST_DEPENDENCY_OUTPUT",
    r"D:\RedMMOTitanWindowsData\ArtistHandoff\planet_asset_dependencies.json",
)

registry = unreal.AssetRegistryHelpers.get_asset_registry()
missing_required_assets = sorted(
    package for package in ROOTS if not unreal.EditorAssetLibrary.does_asset_exist(package)
)
if missing_required_assets:
    raise RuntimeError(
        "Required artist roots do not exist: " + ", ".join(missing_required_assets)
    )
options = unreal.AssetRegistryDependencyOptions(
    include_soft_package_references=True,
    include_hard_package_references=True,
    include_searchable_names=False,
    include_soft_management_references=True,
    include_hard_management_references=True,
)

pending = list(ROOTS)
seen = set()
while pending:
    package = pending.pop()
    if package in seen:
        continue
    seen.add(package)
    for dependency in (registry.get_dependencies(package, options) or []):
        name = str(dependency)
        if name.startswith("/Game/") and name not in seen:
            pending.append(name)

missing_required_dependencies = sorted(set(ROOTS) - seen)
if missing_required_dependencies:
    raise RuntimeError(
        "Required artist roots were not collected: "
        + ", ".join(missing_required_dependencies)
    )

forbidden_dependencies = sorted(
    package
    for package in seen
    if any(marker.lower() in package.lower() for marker in FORBIDDEN_PACKAGE_MARKERS)
)
if forbidden_dependencies:
    raise RuntimeError(
        "Artist dependency closure contains gameplay-only packages: "
        + ", ".join(forbidden_dependencies)
    )

payload = {
    "roots": ROOTS,
    "project_packages": sorted(seen),
    "count": len(seen),
}
os.makedirs(os.path.dirname(OUTPUT), exist_ok=True)
with open(OUTPUT, "w", encoding="utf-8") as handle:
    json.dump(payload, handle, ensure_ascii=False, indent=2)
unreal.log_warning(f"RED_ARTIST_DEPENDENCIES_READY count={len(seen)} output={OUTPUT}")
