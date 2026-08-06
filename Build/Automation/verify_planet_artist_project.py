import unreal

MAP = "/Game/RedMMO/Maps/RedPlanetGen_50km_ArtistCanvas"
DATA = "/Game/RedMMO/Environment/DA_RED_Planet50Km_FusedHeightfield"
REQUIRED_ASSETS = [
    MAP,
    DATA,
]

for package in REQUIRED_ASSETS:
    if not unreal.EditorAssetLibrary.does_asset_exist(package):
        raise RuntimeError(f"Missing required artist-handoff asset: {package}")
    asset = unreal.EditorAssetLibrary.load_asset(package)
    if asset is None:
        raise RuntimeError(f"Could not load required artist-handoff asset: {package}")

unreal.log("RED_ARTIST_HANDOFF_VERIFY: PASS")
