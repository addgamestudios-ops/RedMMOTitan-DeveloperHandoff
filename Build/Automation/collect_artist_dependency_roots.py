"""Write the deliberately small root set for the environment-artist handoff.

Never discover roots by scanning gameplay source: a string reference in a C++
test, comment, or class default is not an artist-project dependency.
"""

import pathlib


output = pathlib.Path(
    r"D:\RedMMOTitanWindowsData\ArtistHandoff\planet_dependency_roots.txt"
)
roots = (
    "/Game/RedMMO/Maps/RedPlanetGen_50km_ArtistCanvas",
    "/Game/RedMMO/Environment/DA_RED_Planet50Km_FusedHeightfield",
)

output.parent.mkdir(parents=True, exist_ok=True)
output.write_text("\n".join(roots) + "\n", encoding="utf-8")
print(f"{output} roots={len(roots)}")
