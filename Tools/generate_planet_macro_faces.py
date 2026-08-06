"""Generate a deterministic seam-safe macro planet source set.

This produces six square 16-bit cube-face height maps sampled from one continuous
spherical function.  It is an original RED blockout used to validate the import,
water, collision and seam pipeline; it is not final biome art.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw


FACE_FRAMES = (
    ("PX", (1, 0, 0), (0, 1, 0), (0, 0, 1)),
    ("NX", (-1, 0, 0), (0, -1, 0), (0, 0, 1)),
    ("PY", (0, 1, 0), (-1, 0, 0), (0, 0, 1)),
    ("NY", (0, -1, 0), (1, 0, 0), (0, 0, 1)),
    ("PZ", (0, 0, 1), (1, 0, 0), (0, 1, 0)),
    ("NZ", (0, 0, -1), (1, 0, 0), (0, -1, 0)),
)

MIN_HEIGHT_CM = -30_000.0
MAX_HEIGHT_CM = 30_000.0
SEA_HEIGHT_CM = 0.0


def _unit(value: tuple[float, float, float]) -> np.ndarray:
    vector = np.asarray(value, dtype=np.float64)
    return vector / np.linalg.norm(vector)


CONTINENTS = (
    (_unit((1.0, 0.22, 0.18)), 0.73, 1.00),
    (_unit((-0.92, 0.34, 0.14)), 0.67, 0.95),
    (_unit((0.08, 1.0, -0.25)), 0.62, 0.92),
    (_unit((0.15, -0.88, 0.44)), 0.58, 0.88),
    (_unit((0.22, 0.06, -1.0)), 0.48, 0.76),
)

ISLANDS = tuple(
    (_unit(center), radius, strength)
    for center, radius, strength in (
        ((0.64, -0.32, 0.70), 0.18, 0.58),
        ((0.45, -0.45, 0.78), 0.15, 0.50),
        ((0.24, -0.55, 0.82), 0.13, 0.46),
        ((-0.55, -0.72, -0.25), 0.17, 0.52),
        ((-0.38, -0.82, -0.34), 0.14, 0.45),
        ((-0.18, -0.88, -0.42), 0.12, 0.40),
        ((-0.22, 0.74, 0.68), 0.14, 0.45),
    )
)

MOUNTAIN_CENTERS = (
    (_unit((0.96, 0.08, 0.28)), 0.24, 18_000.0),
    (_unit((-0.84, 0.46, 0.30)), 0.21, 20_000.0),
    (_unit((0.02, 0.96, -0.28)), 0.20, 15_000.0),
    (_unit((0.06, -0.78, 0.62)), 0.18, 17_000.0),
)


def _smoothstep(edge0: float, edge1: float, value: np.ndarray) -> np.ndarray:
    alpha = np.clip((value - edge0) / (edge1 - edge0), 0.0, 1.0)
    return alpha * alpha * (3.0 - 2.0 * alpha)


def _angle_to(directions: np.ndarray, center: np.ndarray) -> np.ndarray:
    return np.arccos(np.clip(np.sum(directions * center, axis=-1), -1.0, 1.0))


def _directional_noise(directions: np.ndarray) -> np.ndarray:
    x, y, z = directions[..., 0], directions[..., 1], directions[..., 2]
    value = (
        0.44 * np.sin(5.7 * x + 2.8 * y - 1.7 * z)
        + 0.27 * np.sin(-8.1 * x + 4.6 * y + 5.2 * z + 0.7)
        + 0.18 * np.sin(13.4 * x - 9.3 * y + 3.1 * z + 1.9)
        + 0.11 * np.sin(-21.0 * x - 7.5 * y + 14.2 * z + 0.2)
    )
    return value


def evaluate_world(directions: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    noise = _directional_noise(directions)
    signed_coast = np.full(directions.shape[:-1], -10.0, dtype=np.float64)

    for center, radius, strength in CONTINENTS + ISLANDS:
        angle = _angle_to(directions, center)
        local = (radius - angle) * strength
        signed_coast = np.maximum(signed_coast, local)

    signed_coast += noise * 0.055
    land = _smoothstep(-0.035, 0.045, signed_coast)

    ocean_detail = 1_200.0 * noise
    land_detail = 1_450.0 * noise + 700.0 * np.sin(
        18.0 * directions[..., 0] + 11.0 * directions[..., 1]
    )
    height = (-11_500.0 + ocean_detail) * (1.0 - land)
    height += (900.0 + land_detail) * land

    for center, radius, amplitude in MOUNTAIN_CENTERS:
        angle = _angle_to(directions, center)
        envelope = np.exp(-np.square(angle / radius) * 2.25)
        ridge = np.power(
            np.abs(
                np.sin(36.0 * directions[..., 0] - 23.0 * directions[..., 1]
                       + 17.0 * directions[..., 2])
            ),
            2.7,
        )
        height += land * envelope * (0.35 + 0.65 * ridge) * amplitude

    # Give the ocean floor broad trenches without disturbing the authored shoreline.
    trench = np.exp(-np.square(_angle_to(directions, _unit((-0.15, -0.2, -0.97))) / 0.34))
    height -= (1.0 - land) * trench * 8_000.0
    height = np.clip(height, MIN_HEIGHT_CM, MAX_HEIGHT_CM)

    latitude = np.abs(directions[..., 2])
    desert_axis = np.clip(0.5 + 0.5 * np.sum(directions * _unit((1.0, 0.25, 0.05)), axis=-1), 0.0, 1.0)
    desert = land * _smoothstep(0.52, 0.78, desert_axis) * (1.0 - _smoothstep(0.72, 0.90, latitude))
    snow = land * _smoothstep(0.67, 0.86, latitude)
    mountain = land * _smoothstep(7_000.0, 16_000.0, height)
    temperate = land * np.clip(1.0 - desert - snow, 0.0, 1.0)
    alien = land * np.clip(0.5 + 0.5 * np.sin(
        7.0 * directions[..., 0] - 5.0 * directions[..., 1] + 4.0 * directions[..., 2]
    ), 0.0, 1.0) * 0.72

    masks = np.stack((desert, temperate, np.maximum(snow, mountain), alien), axis=-1)
    return height, np.clip(masks, 0.0, 1.0)


def make_face_directions(resolution: int, normal: tuple[int, int, int],
                         axis_u: tuple[int, int, int], axis_v: tuple[int, int, int]) -> np.ndarray:
    coordinate = np.linspace(-1.0, 1.0, resolution, dtype=np.float64)
    u, v = np.meshgrid(coordinate, coordinate)
    tangent_u = np.tan(u * math.pi * 0.25)
    tangent_v = np.tan(v * math.pi * 0.25)
    n = np.asarray(normal, dtype=np.float64)
    au = np.asarray(axis_u, dtype=np.float64)
    av = np.asarray(axis_v, dtype=np.float64)
    cube = n + tangent_u[..., None] * au + tangent_v[..., None] * av
    return cube / np.linalg.norm(cube, axis=-1, keepdims=True)


def encode_height(height_cm: np.ndarray) -> np.ndarray:
    normalized = np.clip(
        (height_cm - MIN_HEIGHT_CM) / (MAX_HEIGHT_CM - MIN_HEIGHT_CM), 0.0, 1.0
    )
    return np.rint(normalized * 65535.0).astype(np.uint16)


def colorize(height_cm: np.ndarray, masks: np.ndarray) -> np.ndarray:
    land = height_cm >= SEA_HEIGHT_CM
    depth = np.clip((-height_cm) / 16_000.0, 0.0, 1.0)
    elevation = np.clip(height_cm / 24_000.0, 0.0, 1.0)
    result = np.zeros((*height_cm.shape, 3), dtype=np.float64)
    result[..., :] = np.stack((0.02 + 0.03 * depth, 0.28 - 0.18 * depth, 0.52 - 0.25 * depth), axis=-1)
    desert, temperate, cold, alien = [masks[..., index] for index in range(4)]
    land_rgb = np.stack(
        (
            0.24 + 0.58 * desert + 0.18 * alien + 0.35 * cold,
            0.30 + 0.42 * temperate + 0.06 * desert + 0.25 * cold,
            0.16 + 0.13 * temperate + 0.28 * alien + 0.45 * cold,
        ),
        axis=-1,
    )
    land_rgb *= (0.78 + 0.22 * elevation)[..., None]
    result[land] = land_rgb[land]
    shore = np.abs(height_cm) < 1_400.0
    result[shore & land] = (0.86, 0.70, 0.38)
    return np.rint(np.clip(result, 0.0, 1.0) * 255.0).astype(np.uint8)


def write_world_preview(output: Path, width: int = 2048, height: int = 1024) -> None:
    longitude = np.linspace(-math.pi, math.pi, width, endpoint=False, dtype=np.float64)
    latitude = np.linspace(math.pi * 0.5, -math.pi * 0.5, height, dtype=np.float64)
    lon, lat = np.meshgrid(longitude, latitude)
    cos_lat = np.cos(lat)
    directions = np.stack((cos_lat * np.cos(lon), cos_lat * np.sin(lon), np.sin(lat)), axis=-1)
    height_cm, masks = evaluate_world(directions)
    Image.fromarray(colorize(height_cm, masks), mode="RGB").save(output / "RED_MacroWorld_Preview.png")


def generate(output: Path, resolution: int) -> None:
    output.mkdir(parents=True, exist_ok=True)
    face_records: list[dict[str, object]] = []
    preview_faces: list[tuple[str, Image.Image]] = []
    boundary_samples: dict[tuple[int, int, int], int] = {}
    seam_comparisons = 0
    max_seam_delta_u16 = 0

    for index, (name, normal, axis_u, axis_v) in enumerate(FACE_FRAMES):
        directions = make_face_directions(resolution, normal, axis_u, axis_v)
        height_cm, masks = evaluate_world(directions)
        encoded = encode_height(height_cm)
        land_mask = np.where(height_cm >= SEA_HEIGHT_CM, 255, 0).astype(np.uint8)
        mask_rgba = np.rint(masks * 255.0).astype(np.uint8)

        Image.fromarray(encoded).save(output / f"RED_Height_{name}_16.png")
        # Unreal's editor importer consumes a headerless, row-major little-endian
        # uint16 stream.  Keep the PNG for visual inspection, but do not depend on
        # image-library bit-depth/channel conversion for authoritative samples.
        raw_height_file = f"RED_Height_{name}.r16"
        encoded.astype("<u2", copy=False).tofile(output / raw_height_file)
        Image.fromarray(land_mask, mode="L").save(output / f"RED_Land_{name}.png")
        Image.fromarray(mask_rgba, mode="RGBA").save(output / f"RED_Biomes_{name}.png")
        face_preview = Image.fromarray(colorize(height_cm, masks), mode="RGB")
        face_preview.save(output / f"RED_Preview_{name}.png")
        preview_faces.append((name, face_preview))

        boundary = np.zeros((resolution, resolution), dtype=bool)
        boundary[0, :] = True
        boundary[-1, :] = True
        boundary[:, 0] = True
        boundary[:, -1] = True
        for direction, value in zip(directions[boundary], encoded[boundary], strict=True):
            key = tuple(np.rint(direction * 1_000_000_000_000.0).astype(np.int64).tolist())
            previous = boundary_samples.get(key)
            if previous is not None:
                seam_comparisons += 1
                max_seam_delta_u16 = max(max_seam_delta_u16, abs(previous - int(value)))
            else:
                boundary_samples[key] = int(value)

        face_records.append(
            {
                "face_index": index,
                "name": name,
                "normal": normal,
                "axis_u": axis_u,
                "axis_v": axis_v,
                "height_file": f"RED_Height_{name}_16.png",
                "raw_height_file": raw_height_file,
                "land_file": f"RED_Land_{name}.png",
                "biome_file": f"RED_Biomes_{name}.png",
            }
        )

    write_world_preview(output)
    label_height = 30
    contact = Image.new("RGB", (resolution * 3, (resolution + label_height) * 2), (8, 12, 20))
    draw = ImageDraw.Draw(contact)
    for index, (name, face_preview) in enumerate(preview_faces):
        column = index % 3
        row = index // 3
        x = column * resolution
        y = row * (resolution + label_height)
        contact.paste(face_preview, (x, y + label_height))
        draw.text((x + 10, y + 7), f"Face {index}: {name}", fill=(230, 238, 248))
    contact.save(output / "RED_CubeFaces_ContactSheet.png")
    metadata = {
        "schema": "redmmotitan.macro_planet_faces.v1",
        "purpose": "original seam-safe pipeline blockout; not final terrain art",
        "resolution": resolution,
        "height_encoding": "unsigned 16-bit normalized",
        "raw_height_encoding": "little-endian unsigned 16-bit row-major",
        "min_height_cm": MIN_HEIGHT_CM,
        "max_height_cm": MAX_HEIGHT_CM,
        "sea_height_cm": SEA_HEIGHT_CM,
        "projection": "cube face with tan(uv*pi/4), matching PlanetGen chunk projection",
        "seam_validation": {
            "shared_boundary_comparisons": seam_comparisons,
            "max_height_delta_u16": max_seam_delta_u16,
            "passed": max_seam_delta_u16 == 0,
        },
        "biome_channels": {"r": "desert", "g": "temperate", "b": "cold_or_mountain", "a": "alien"},
        "faces": face_records,
    }
    (output / "RED_MacroWorld.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    if max_seam_delta_u16 != 0:
        raise RuntimeError(f"cube-face seam validation failed: max delta {max_seam_delta_u16}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("SourceArt/Planet50Km/MacroFaces"))
    parser.add_argument("--resolution", type=int, default=513)
    args = parser.parse_args()
    if args.resolution < 3 or args.resolution % 2 == 0:
        raise SystemExit("resolution must be an odd integer >= 3")
    generate(args.output.resolve(), args.resolution)
    print(f"RED_MACRO_FACES_READY output={args.output.resolve()} resolution={args.resolution}")


if __name__ == "__main__":
    main()
