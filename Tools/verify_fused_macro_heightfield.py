"""Fresh-process verification for the isolated fused PlanetGen data asset."""

from __future__ import annotations

from pathlib import Path
import sys

import unreal

TOOLS_DIR = Path(__file__).resolve().parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from import_fused_macro_heightfield import (
    ASSET_PACKAGE,
    sha256_file,
    verify_imported_asset,
)


asset = unreal.load_asset(ASSET_PACKAGE)
resolution, samples_per_face = verify_imported_asset(asset)
asset_filename = (
    Path(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_content_dir()))
    / "RedMMO"
    / "Environment"
    / "DA_RED_Planet50Km_FusedHeightfield.uasset"
)
if not asset_filename.is_file():
    raise RuntimeError(f"Fused asset package is missing: {asset_filename}")

unreal.log(
    "RED_FUSED_MACRO_FRESH_VERIFY "
    f"asset={ASSET_PACKAGE} resolution={resolution} "
    f"height_faces=6 land_faces=6 biome_faces=6 "
    f"samples_per_face={samples_per_face} "
    f"asset_sha256={sha256_file(asset_filename)}"
)
