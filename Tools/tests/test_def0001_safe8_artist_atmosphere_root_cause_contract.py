"""Static contract for the protected SAFE8 artist-atmosphere authoring path."""

import hashlib
import json
import re
import unittest
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
ARCHIVE = Path(
    r"D:/RedMMOTitanWindowsData/ArtistHandoff/RED_Mars_27Patch_ArtistB_UE58_SAFE8.zip"
)
RELOAD_REPORT = Path(
    r"D:/RedMMOTitanWindowsData/ArtistHandoff/artist_canvas_surface_reload_verify.json"
)
MAIN_ARTIST_MAP = ROOT / "Content/RedMMO/Maps/RedPlanetGen_50km_ArtistCanvas.umap"
QUEUE = ROOT / "Build/Automation/redmmotitan_module_queue.json"
DEFECT = ROOT / "ProjectKnowledge/defects/DEF-0001-artist-atmosphere-scale.yaml"
PREFIX = "RED_Mars_27Patch_ArtistB_UE58_SAFE8/"
CONFIG_MEMBER = PREFIX + "Build/Verification/configure_artist_blank_canvas.py"
HEADER_MEMBER = (
    PREFIX
    + "Plugins/PlanetGenPinned_1_4_0_RedMMO/Source/PlanetGen/Public/PlanetGen/CLMPlanetSunSky.h"
)
CPP_MEMBER = (
    PREFIX
    + "Plugins/PlanetGenPinned_1_4_0_RedMMO/Source/PlanetGen/Private/PlanetGen/CLMPlanetSunSky.cpp"
)
MANIFEST_MEMBER = PREFIX + "MANIFEST_SHA256.txt"
ARCHIVED_MAP_MEMBER = (
    PREFIX + "Content/RedMMO/Maps/RedPlanetGen_50km_ArtistCanvas.umap"
)
EXPECTED_ARCHIVE_SHA256 = (
    "7EDC9324F1B0AD9C20F5C925B9FA7D8A19A66C5DA2C0A33BFCE0C4F302E4B784"
)
EXPECTED_RELOAD_SHA256 = (
    "35BA5394C1C6F486F60D202EE9A334F8442633ADC46F961B91C4055044C2508B"
)
EXPECTED_ARCHIVED_MAP_SHA256 = (
    "B23473BA8C7AD498F5FCBF351B976B5BDC89712D26606C4D5C47287B55856933"
)
EXPECTED_MAIN_MAP_SHA256 = (
    "E51C976D0D55524521C6A1A69C7D4FC9827FAB1C6791B2276462A4504476E97F"
)
EXPECTED_MEMBER_SHA256 = {
    CONFIG_MEMBER: "86483CAA805B9399F000031EBE6FA81E30763ACD9F096B622E179C211C6BB796",
    HEADER_MEMBER: "14515DE56249DA89CB1A88897D8C8573A20E735C34E284C97F1D55E3120212A6",
    CPP_MEMBER: "48C741D1B7FC3F2804FA5BB9A9459E47D1370D8A73BFD5A0AFB9E42F0E8C6427",
}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def sha256_zip_member(archive: zipfile.ZipFile, member: str) -> str:
    digest = hashlib.sha256()
    with archive.open(member) as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


class Def0001SAFE8ArtistAtmosphereRootCauseContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not ARCHIVE.is_file():
            raise AssertionError(f"protected SAFE8 archive is missing: {ARCHIVE}")
        if not RELOAD_REPORT.is_file():
            raise AssertionError(f"artist reload report is missing: {RELOAD_REPORT}")
        with zipfile.ZipFile(ARCHIVE) as archive:
            cls.config_bytes = archive.read(CONFIG_MEMBER)
            cls.header_bytes = archive.read(HEADER_MEMBER)
            cls.cpp_bytes = archive.read(CPP_MEMBER)
            cls.manifest = archive.read(MANIFEST_MEMBER).decode("utf-8", errors="strict")
        cls.config = cls.config_bytes.decode("utf-8", errors="strict")
        cls.header = cls.header_bytes.decode("utf-8", errors="strict")
        cls.cpp = cls.cpp_bytes.decode("utf-8", errors="strict")
        cls.reload = json.loads(RELOAD_REPORT.read_text(encoding="utf-8"))
        cls.queue = json.loads(QUEUE.read_text(encoding="utf-8"))

    def test_protected_archive_and_relevant_embedded_members_are_exact(self):
        self.assertEqual(sha256_file(ARCHIVE), EXPECTED_ARCHIVE_SHA256)
        for member, expected_hash in EXPECTED_MEMBER_SHA256.items():
            with self.subTest(member=member):
                data = {
                    CONFIG_MEMBER: self.config_bytes,
                    HEADER_MEMBER: self.header_bytes,
                    CPP_MEMBER: self.cpp_bytes,
                }[member]
                self.assertEqual(sha256_bytes(data), expected_hash)
                relative = member.removeprefix(PREFIX)
                manifest_line = f"{expected_hash.lower()} *{relative}"
                self.assertIn(manifest_line, self.manifest)

    def test_all_embedded_manifest_members_are_exact_without_extraction(self):
        manifest_entries = []
        for line in self.manifest.splitlines():
            if not line.strip():
                continue
            expected_hash, relative = line.split(" *", maxsplit=1)
            manifest_entries.append((expected_hash.upper(), relative))

        self.assertEqual(len(manifest_entries), 338)
        with zipfile.ZipFile(ARCHIVE) as archive:
            archive_names = set(archive.namelist())
            for expected_hash, relative in manifest_entries:
                member = PREFIX + relative.replace("\\", "/")
                with self.subTest(member=member):
                    self.assertIn(member, archive_names)
                    digest = hashlib.sha256()
                    with archive.open(member) as handle:
                        for block in iter(lambda: handle.read(1024 * 1024), b""):
                            digest.update(block)
                    self.assertEqual(digest.hexdigest().upper(), expected_hash)

    def test_external_reload_report_does_not_authenticate_the_safe8_map(self):
        self.assertEqual(sha256_file(RELOAD_REPORT), EXPECTED_RELOAD_SHA256)
        self.assertEqual(sha256_file(MAIN_ARTIST_MAP), EXPECTED_MAIN_MAP_SHA256)
        with zipfile.ZipFile(ARCHIVE) as archive:
            archived_map_hash = sha256_zip_member(archive, ARCHIVED_MAP_MEMBER)
        self.assertEqual(archived_map_hash, EXPECTED_ARCHIVED_MAP_SHA256)
        self.assertNotEqual(archived_map_hash, EXPECTED_MAIN_MAP_SHA256)
        self.assertNotIn("map_sha256", self.reload)
        self.assertNotIn("atmosphere_height_km", self.reload)
        self.assertNotIn("atmosphere_bottom_radius_km", self.reload)
        self.assertNotIn("atmosphere_component_scale", self.reload)

    def test_blank_canvas_script_sets_eight_km_then_previews_and_saves(self):
        set_height = 'set_prop(planet, "atmosphere_height_km", 8.0)'
        preview = "planet.preview_planet()"
        save = "level.save_current_level()"
        self.assertIn(set_height, self.config)
        self.assertIn('len(atmospheres) != 1', self.config)
        self.assertIn('set_prop(planet, "target_atmosphere", atmospheres[0])', self.config)
        self.assertLess(self.config.index(set_height), self.config.index(preview))
        self.assertLess(self.config.index(preview), self.config.index(save))

    def test_embedded_planetgen_builds_outer_radius_from_radius_plus_height(self):
        self.assertIn("float AtmosphereHeightKm = 8.f;", self.header)
        for token in (
            "const float RadiusKm = PlanetRadius / 100000.f;",
            "const float AtmoHeight = (AtmosphereHeightKm > 0.f) ? AtmosphereHeightKm : 8.f;",
            "const float AtmosphereOuterKm = RadiusKm + AtmoHeight;",
            "Atmo->SetBottomRadius(AtmosphereGroundKm);",
            "Atmo->SetAtmosphereHeight(AtmosphereOuterKm - AtmosphereGroundKm);",
            "ESkyAtmosphereTransformMode::PlanetCenterAtComponentTransform",
        ):
            self.assertIn(token, self.cpp)

    def test_external_reload_report_records_one_planet_and_atmosphere(self):
        self.assertTrue(self.reload["passed"])
        self.assertEqual(
            self.reload["map"], "/Game/RedMMO/Maps/RedPlanetGen_50km_ArtistCanvas"
        )
        self.assertEqual(
            self.reload["planet_class"],
            "/PlanetGen/Blueprints/BP_CLMPlanetSunSky.BP_CLMPlanetSunSky_C",
        )
        self.assertEqual(self.reload["planet_radius_cm"], 795774.6875)
        self.assertEqual(len(self.reload["visible_atmospheres"]), 1)
        self.assertTrue(self.reload["acceptance"]["exactly_one_visible_atmosphere"])

    def test_bundled_configuration_would_double_the_canonical_target_radius(self):
        height_match = re.search(
            r'set_prop\(planet, "atmosphere_height_km", ([0-9.]+)\)', self.config
        )
        self.assertIsNotNone(height_match)
        height_km = float(height_match.group(1))
        radius_km = float(self.queue["planet_target"]["radius_km"])
        outer_km = radius_km + height_km
        outer_to_body = outer_km / radius_km

        self.assertAlmostEqual(radius_km, 7.9577471546, places=9)
        self.assertAlmostEqual(height_km, 8.0, places=9)
        self.assertAlmostEqual(outer_km, 15.9577471546, places=9)
        self.assertAlmostEqual(outer_to_body, 2.0053096491, places=9)
        self.assertGreater(height_km, radius_km)

    def test_static_root_cause_does_not_close_the_real_gpu_defect(self):
        defect = DEFECT.read_text(encoding="utf-8", errors="strict")
        self.assertRegex(defect, r"(?m)^status: open$")
        self.assertIn("visual_evidence: pending", defect)
        self.assertIn("Capture surface and orbit views on a real GPU", defect)


if __name__ == "__main__":
    unittest.main()
