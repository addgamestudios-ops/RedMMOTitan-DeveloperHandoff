import hashlib
import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DATA_ROOT = Path("D:/RedMMOTitanWindowsData")

CURRENT_HASH = "4C84D7752C87854C70987ED9988C64C124C577FBE1DE3DEF3CC826F81B0B6284"
PRIOR_WATER_HASH = "211429783F757F3CD8DE4A37B1E37B4A117125BF26EBFCBACF97CCFA9EFBE8D7"
PRE_WATER_HASH = "A9C42C0D1B0429DD1018F00F0D2AB8A18F66C07291611964EFF5F9710F3B0C6A"
PRODUCTION_HASH = "1DF9E6ED913A267875F1EF452F6ED51DAF337DBBAAE4C6EC3379EA6299346724"
CHECKPOINT_HASH = "DA5987012EEB8F550254F5FCF0F47F42B8F5E03428CF4881C83D8687537F6E7D"
FUSED_ASSET_HASH = "412E26B75DAD95CE0EF4FA63BFF21CCA0EDB755B5D08BA1A4CFA3EEFEC06E562"
AUTHORING_SCRIPT_HASH = "93AEA69128DA62C188F35A78F2FC7A98C8FA66BC56FE1456E8202B42CB81CDDF"
SAVE_LOG_HASH = "FDCBADA5A922481F76A920920D578B7BB8135BEE7D502ADD18B01907B370A1D0"
FAILED_AUTOMATION_LOG_HASH = "69986622318F3DCB8A7A027ACF3E7C47529722E5E250896AB154FC8556D14C27"
READY_MARKER_HASH = "26B00A20C4B18717CEC36B5CA289CC9001AE1E65DA649404ACC8721F14EF26E8"
RESERVATIONS_HASH = "8E2952B8CB6530019BD9D1FFCAB526FB483B448B2B8D48164CCD10D00A78EDA8"
PATCH_PROFILE_HASH = "1CB393D6A9C6C713BD5543830AE7B29ADB5F8F140B7E526D9AC7774D300C7EB5"
PATCH_MANIFEST_HASH = "929433D8E612B82FA60C9BA9599452788E09F59929D212454237E7F31DE3A14D"
EMPTY_AUTHORITY_HASH = "C86F9760AD0441C3310FF498884D9993CD9E18F8C2B0E375F554CEE299BD948D"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def read_log(path: Path) -> str:
    return path.read_bytes().decode("utf-8", errors="replace")


class FusedPrototypeProvenanceTests(unittest.TestCase):
    def test_current_and_retained_packages_have_pinned_hashes(self):
        expected = {
            ROOT / "Content/RedMMO/Maps/RedPlanetGen_50km_FusedPrototype.umap": CURRENT_HASH,
            ROOT
            / "Content/RedMMO/Maps/Tests/RedPlanetGen_50km_FusedPrototype_Night_T03.umap": PRIOR_WATER_HASH,
            DATA_ROOT
            / "Rollback/BeforeCoastDatum_20260714/RedPlanetGen_50km_FusedPrototype.umap": PRE_WATER_HASH,
            ROOT / "Content/RedMMO/Maps/RedPlanetGen.umap": PRODUCTION_HASH,
            ROOT / "Content/RedMMO/Maps/RedPlanetGen_50km_Test.umap": CHECKPOINT_HASH,
            ROOT
            / "Content/RedMMO/Environment/DA_RED_Planet50Km_FusedHeightfield.uasset": FUSED_ASSET_HASH,
        }
        for path, expected_hash in expected.items():
            with self.subTest(path=path):
                self.assertTrue(path.is_file(), f"missing provenance artifact: {path}")
                self.assertEqual(sha256(path), expected_hash)

    def test_artist_staging_copy_matches_current_intentional_save(self):
        staging_copy = (
            DATA_ROOT
            / "ArtistHandoff/RED_Mars_PlanetArtist_UE58_20260719"
            / "Content/RedMMO/Maps/RedPlanetGen_50km_FusedPrototype.umap"
        )
        self.assertTrue(staging_copy.is_file())
        self.assertEqual(sha256(staging_copy), CURRENT_HASH)

    def test_protected_foundation_and_all_135_source_rasters_match(self):
        authoring_root = ROOT / "SourceArt/Planet50Km/AuthoringPatches"
        profile = authoring_root / "RED_PatchProfile.json"
        manifest_path = authoring_root / "RED_PatchRasters.json"
        reservations = ROOT / "docs/PLANET_50KM_PCG_RESERVATIONS.json"
        ready_marker = (
            DATA_ROOT
            / "PackagedBuilds/Development_50KM_FOUNDATION_20260716_064703"
            / "REDMMO_PACKAGE_READY.txt"
        )
        for path, expected_hash in (
            (profile, PATCH_PROFILE_HASH),
            (manifest_path, PATCH_MANIFEST_HASH),
            (reservations, RESERVATIONS_HASH),
            (ready_marker, READY_MARKER_HASH),
        ):
            with self.subTest(protected_artifact=path):
                self.assertTrue(path.is_file())
                self.assertEqual(sha256(path), expected_hash)

        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(manifest["patch_count"], 27)
        raster_records = [
            (role, record)
            for patch in manifest["patches"]
            for role, record in patch["files"].items()
        ]
        self.assertEqual(len(raster_records), 135)
        authority_count = 0
        for role, record in raster_records:
            raster = authoring_root / record["file"]
            with self.subTest(raster=raster):
                self.assertTrue(raster.is_file())
                self.assertEqual(sha256(raster), record["sha256"])
            if role == "authority":
                authority_count += 1
                self.assertEqual(record["sha256"], EMPTY_AUTHORITY_HASH)
        self.assertEqual(authority_count, 27)

    def test_save_log_authenticates_the_intentional_hash_transition(self):
        log_path = DATA_ROOT / "BuildLogs/FixFusedAscentWater_20260719.log"
        self.assertEqual(sha256(log_path), SAVE_LOG_HASH)
        log = read_log(log_path)
        marker = (
            "RED_FUSED_50KM_PROTOTYPE_READY "
            "map=/Game/RedMMO/Maps/RedPlanetGen_50km_FusedPrototype"
        )
        self.assertIn(marker, log)
        for token in (
            "sea_level=0.5 stamps=27 changed=1",
            f"prototype_sha256={CURRENT_HASH}",
            f"production_sha256={PRODUCTION_HASH}",
            f"checkpoint_sha256={CHECKPOINT_HASH}",
            "Python script executed successfully",
            "Success - 0 error(s), 21 warning(s)",
        ):
            self.assertIn(token, log)

    def test_authoring_source_pins_the_ascent_water_intent(self):
        script = ROOT / "Tools/create_fused_50km_prototype.py"
        self.assertEqual(sha256(script), AUTHORING_SCRIPT_HASH)
        source = script.read_text(encoding="utf-8")
        self.assertIn('set_if_different("enable_water", False)', source)
        self.assertIn("overhead shell", source)

    def test_immediate_automation_is_recorded_as_failed_not_acceptance(self):
        log_path = DATA_ROOT / "BuildLogs/FusedAscentFix_Automation_20260719.log"
        self.assertEqual(sha256(log_path), FAILED_AUTOMATION_LOG_HASH)
        log = read_log(log_path)
        self.assertIn("Automation RunTests RedMMO.Planet.FusedTerrain", log)
        self.assertIn("NotNull.cpp", log)
        self.assertIn("Null assigned to TNotNull", log)
        self.assertNotRegex(log, re.compile(r"Test Completed.*Result=\{Success\}"))

    def test_guard_and_spec_distinguish_current_from_retained_rollback(self):
        guard = (
            ROOT / "Build/Automation/verify_packaged_fused_prototype.ps1"
        ).read_text(encoding="utf-8-sig")
        expected_entry = re.compile(
            r"'Content\\RedMMO\\Maps\\RedPlanetGen_50km_FusedPrototype\.umap'\s*=\s*'"
            + CURRENT_HASH
            + r"'"
        )
        self.assertRegex(guard, expected_entry)
        for token in (
            "fused_prototype_source_sha256=$ExpectedFusedPrototypeHash",
            "$MarkerLines -notcontains $ExpectedMarker",
            "Assert-PackagedSourceCurrency -ReadyMarker $ReadyMarker",
            "Older archives without this package-time input marker fail closed",
        ):
            self.assertIn(token, guard)
        currency_check = guard.index(
            "Assert-PackagedSourceCurrency -ReadyMarker $ReadyMarker"
        )
        container_list = guard.index("& $UnrealPak $Container -List")
        packaged_launch = guard.index("Start-Process -FilePath $Executable")
        self.assertLess(currency_check, container_list)
        self.assertLess(currency_check, packaged_launch)

        spec = (ROOT / "docs/PLANET_50KM_IMPLEMENTATION_SPEC.md").read_text(
            encoding="utf-8"
        )
        for token in (
            CURRENT_HASH,
            PRIOR_WATER_HASH,
            PRE_WATER_HASH,
            "RedPlanetGen_50km_FusedPrototype_Night_T03.umap",
            "does not validate the July 19 change",
            "did not decode or accept terrain, shoreline, or water behavior",
        ):
            self.assertIn(token, spec)


if __name__ == "__main__":
    unittest.main()
