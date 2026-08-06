"""Extract the unchanged weapon pixels from the two differently coloured cards.

The Epic and Legendary source cards were rendered from the same weapon layer on
different backgrounds.  Pixels belonging to the weapon therefore agree between
the two images, while the stripes, frame, number, and card fill do not.  This
builds a connected, antialiased alpha matte from that difference and keeps the
original weapon RGB pixels exactly; no generative redraw or colour replacement
is involved.
"""

from __future__ import annotations

from pathlib import Path
from shutil import copy2

import numpy as np
from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = ROOT / "Saved" / "VibeEngine" / "Generated"
EPIC = SOURCE_DIR / "weapon_slot_epic.png"
LEGENDARY = SOURCE_DIR / "weapon_slot_legendary.png"


def largest_component(mask: np.ndarray) -> np.ndarray:
    """Return only the largest 8-connected component of a small boolean image."""
    height, width = mask.shape
    seen = np.zeros_like(mask, dtype=bool)
    best: list[tuple[int, int]] = []

    for y in range(height):
        for x in range(width):
            if not mask[y, x] or seen[y, x]:
                continue

            component: list[tuple[int, int]] = []
            stack = [(y, x)]
            seen[y, x] = True
            while stack:
                cy, cx = stack.pop()
                component.append((cy, cx))
                for dy in (-1, 0, 1):
                    for dx in (-1, 0, 1):
                        if dx == 0 and dy == 0:
                            continue
                        ny, nx = cy + dy, cx + dx
                        if (
                            0 <= ny < height
                            and 0 <= nx < width
                            and mask[ny, nx]
                            and not seen[ny, nx]
                        ):
                            seen[ny, nx] = True
                            stack.append((ny, nx))
            if len(component) > len(best):
                best = component

    result = np.zeros_like(mask, dtype=bool)
    if best:
        ys, xs = zip(*best)
        result[np.asarray(ys), np.asarray(xs)] = True
    return result


def main() -> None:
    epic = np.asarray(Image.open(EPIC).convert("RGBA"), dtype=np.uint8)
    legendary = np.asarray(Image.open(LEGENDARY).convert("RGBA"), dtype=np.uint8)
    if epic.shape != legendary.shape:
        raise RuntimeError(f"Weapon cards do not match: {epic.shape} vs {legendary.shape}")

    rgb_delta = np.max(
        np.abs(epic[:, :, :3].astype(np.int16) - legendary[:, :, :3].astype(np.int16)),
        axis=2,
    )

    # The stable weapon island remains the largest component even at a generous
    # threshold.  Keeping only that island discards the frame and slot numeral.
    # Forty-five preserves the antialiased weapon edge but rejects the soft card
    # drop shadow, leaving only the weapon silhouette over the runtime rarity fill.
    support = largest_component(rgb_delta <= 45)
    alpha = np.clip((45.0 - rgb_delta.astype(np.float32)) / 35.0, 0.0, 1.0)
    alpha = np.where(support, alpha, 0.0)
    alpha = np.rint(alpha * 255.0).astype(np.uint8)

    # Preserve the source cards once.  The live source names remain unchanged so
    # Unreal's existing import data can perform a deterministic reimport.
    for path in (EPIC, LEGENDARY):
        backup = path.with_name(path.stem + "_card_original.png")
        if not backup.exists():
            copy2(path, backup)

    for source, output in ((epic, EPIC), (legendary, LEGENDARY)):
        cutout = source.copy()
        cutout[:, :, 3] = alpha
        Image.fromarray(cutout, mode="RGBA").save(output, optimize=True)

    ys, xs = np.where(alpha > 0)
    bounds = (int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max()))
    print(
        f"Extracted exact weapon silhouette: bounds={bounds}, "
        f"opaque={(alpha == 255).sum()}, partial={((alpha > 0) & (alpha < 255)).sum()}"
    )


if __name__ == "__main__":
    main()
