from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import struct
import tempfile
import unittest
import zlib
from pathlib import Path
from unittest import mock

from Tools import postflight_m07_tropical_planetary_biome_live as postflight


PostflightError = postflight.PostflightError
parse_png_ihdr = postflight.parse_png_ihdr
scan_unreal_log = postflight.scan_unreal_log


def _chunk(kind: bytes, payload: bytes) -> bytes:
    crc = zlib.crc32(kind)
    crc = zlib.crc32(payload, crc) & 0xFFFFFFFF
    return (
        struct.pack(">I", len(payload))
        + kind
        + payload
        + struct.pack(">I", crc)
    )


def _png_bytes(
    *,
    width: int = 1920,
    height: int = 1080,
    rgba: bytes = b"\x10\x20\x30\xff",
    idat_override: bytes | None = None,
) -> bytes:
    if len(rgba) != 4:
        raise ValueError("rgba must contain four bytes")
    ihdr = struct.pack(">II", width, height) + bytes((8, 6, 0, 0, 0))
    raw = (b"\x00" + rgba * width) * height
    compressed = (
        zlib.compress(raw, level=1)
        if idat_override is None
        else idat_override
    )
    return (
        b"\x89PNG\r\n\x1a\n"
        + _chunk(b"IHDR", ihdr)
        + _chunk(b"IDAT", compressed)
        + _chunk(b"IEND", b"")
    )


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def _record(path: Path) -> dict[str, object]:
    return {
        "path": str(path),
        "bytes": path.stat().st_size,
        "sha256": _sha(path),
    }


def _good_log(command_line: str = "") -> str:
    disabled = ",".join(postflight.REQUIRED_DISABLED_PLUGINS)
    command_line = command_line or (
        f"-d3d12 -sm6 -DisablePlugins={disabled}"
    )
    return "\n".join(
        (
            f"LogInit: Command Line: {command_line}",
            "LogRHI: Display: RHI Selected: D3D12 with Feature Level SM6",
            "LogD3D12RHI: Found D3D12 adapter 0: "
            "NVIDIA GeForce RTX 3080",
            "LogD3D12RHI: Chosen D3D12 Adapter Id = 0",
            "LogShaderCompilers: Display: Shader format PCD3D_SM6 selected",
            postflight.DESTINATION_MAP,
            "RED_M07_TROPICAL_LIVE_VALIDATION_STARTED",
            "RED_M07_TROPICAL_NATIVE_SNAP_VERIFIED",
            "RED_M07_TROPICAL_HIGHRESSHOT_ISSUED view=ground",
            "RED_M07_TROPICAL_HIGHRESSHOT_FILE_VERIFIED view=ground",
            "RED_M07_TROPICAL_HIGHRESSHOT_ISSUED view=curvature",
            "RED_M07_TROPICAL_HIGHRESSHOT_FILE_VERIFIED view=curvature",
            "RED_M07_TROPICAL_HIGHRESSHOT_ISSUED view=horizon",
            "RED_M07_TROPICAL_HIGHRESSHOT_FILE_VERIFIED view=horizon",
            "RED_M07_TROPICAL_LIVE_VALIDATION_READY",
        )
    )


class PngParserTests(unittest.TestCase):
    def test_accepts_genuine_exact_png_and_decodes_pixels(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "capture.png"
            path.write_bytes(_png_bytes())
            record = parse_png_ihdr(path)
        self.assertEqual(record["width"], 1920)
        self.assertEqual(record["height"], 1080)
        self.assertEqual(record["png_magic"], "89504E470D0A1A0A")
        self.assertTrue(record["full_png_crc_and_pixel_decode_verified"])
        self.assertEqual(record["decoded_pixel_bytes"], 1920 * 1080 * 4)
        self.assertEqual(len(record["decoded_pixel_sha256"]), 64)

    def test_rejects_wrong_dimensions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "capture.png"
            path.write_bytes(_png_bytes(width=1280, height=720))
            with self.assertRaisesRegex(PostflightError, "dimensions drifted"):
                parse_png_ihdr(path)

    def test_rejects_bad_magic(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "capture.png"
            payload = _png_bytes()
            path.write_bytes(b"NOTAPNG!" + payload[8:])
            with self.assertRaisesRegex(PostflightError, "magic is invalid"):
                parse_png_ihdr(path)

    def test_rejects_corrupt_crc(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "capture.png"
            payload = bytearray(_png_bytes())
            idat = payload.index(b"IDAT")
            payload[idat + 5] ^= 0x01
            path.write_bytes(payload)
            with self.assertRaisesRegex(PostflightError, "CRC is invalid"):
                parse_png_ihdr(path)

    def test_rejects_truncated_png(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "capture.png"
            path.write_bytes(_png_bytes()[:-5])
            with self.assertRaisesRegex(
                PostflightError, "truncated|lacks required"
            ):
                parse_png_ihdr(path)

    def test_rejects_valid_crc_but_invalid_zlib_stream(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "capture.png"
            path.write_bytes(_png_bytes(idat_override=b"not-a-zlib-stream"))
            with self.assertRaisesRegex(PostflightError, "zlib decode failed"):
                parse_png_ihdr(path)


class LogScannerTests(unittest.TestCase):
    def test_good_log_satisfies_positive_runtime_bindings(self) -> None:
        scan = scan_unreal_log(_good_log())
        self.assertTrue(scan["rhi"]["positive_binding_passed"])
        self.assertTrue(scan["destination_map_present"])
        self.assertTrue(all(scan["required_markers"].values()))
        self.assertEqual(
            scan["provider_off"]["exact_disable_line_count"], 1
        )
        self.assertFalse(scan["provider_off"]["unapproved_mentions"])
        self.assertTrue(
            all(not findings for findings in scan["hard_findings"].values())
        )

    def test_rhi_fallback_invalidates_positive_selection(self) -> None:
        scan = scan_unreal_log(
            _good_log()
            + "\nLogRHI: Warning: SM6 unsupported; falling back to SM5"
        )
        self.assertFalse(scan["rhi"]["positive_binding_passed"])
        self.assertTrue(scan["rhi"]["fallback_or_rejection_lines"])

    def test_later_rhi_will_not_be_used_rejects_prior_good_binding(
        self,
    ) -> None:
        scan = scan_unreal_log(
            _good_log()
            + "\nLogRHI: RHI Selected: D3D12 with Feature Level SM6 "
            "will not be used"
        )
        self.assertFalse(scan["rhi"]["positive_binding_passed"])
        self.assertTrue(scan["rhi"]["fallback_or_rejection_lines"])

    def test_sm6_capability_or_support_only_is_not_final_selection(
        self,
    ) -> None:
        lines = [
            line
            for line in _good_log().splitlines()
            if "RHI Selected: D3D12 with Feature Level SM6" not in line
        ]
        lines.extend(
            (
                "LogRHI: Using Default RHI: D3D12",
                "LogRHI: Checking if RHI D3D12 with Feature Level SM6 "
                "is supported by your system.",
                "LogD3D12RHI: Max supported Feature Level 12_2, "
                "shader model 6.7",
            )
        )
        scan = scan_unreal_log("\n".join(lines))
        self.assertFalse(scan["rhi"]["positive_binding_passed"])
        self.assertFalse(
            scan["rhi"]["canonical_d3d12_sm6_final_selected_lines"]
        )

    def test_exact_final_rhi_allowlist_accepts_historical_ue_grammars(
        self,
    ) -> None:
        accepted_lines = (
            "LogRHI: Display: RHI Selected: D3D12 with Feature Level SM6",
            "LogRHI: RHI D3D12 with Feature Level SM6 is supported "
            "and will be used.",
            "LogD3D12RHI: Display: Creating D3D12 RHI with Max "
            "Feature Level SM6",
        )
        base_lines = [
            line
            for line in _good_log().splitlines()
            if "RHI Selected: D3D12 with Feature Level SM6" not in line
        ]
        for line in accepted_lines:
            with self.subTest(line=line):
                scan = scan_unreal_log("\n".join((*base_lines, line)))
                self.assertTrue(scan["rhi"]["positive_binding_passed"])
                self.assertEqual(
                    scan["rhi"][
                        "canonical_d3d12_sm6_final_selected_lines"
                    ][0]["text"],
                    line,
                )

    def test_rhi_selection_rejects_adversarial_token_cooccurrence(
        self,
    ) -> None:
        adversarial_lines = (
            "LogRHI: RHI Selected: NullRHI; "
            "D3D12 with SM6 support available",
            "LogRHI: RHI Selected: D3D12 with Feature Level SM6 "
            "will not be used",
        )
        base_lines = [
            line
            for line in _good_log().splitlines()
            if "RHI Selected: D3D12 with Feature Level SM6" not in line
        ]
        for line in adversarial_lines:
            with self.subTest(line=line):
                scan = scan_unreal_log("\n".join((*base_lines, line)))
                self.assertFalse(scan["rhi"]["positive_binding_passed"])
                self.assertFalse(
                    scan["rhi"][
                        "canonical_d3d12_sm6_final_selected_lines"
                    ]
                )

    def test_selected_sm5_invalidates_otherwise_positive_rhi(self) -> None:
        scan = scan_unreal_log(
            _good_log()
            + "\nLogRHI: RHI D3D12 with Feature Level SM5 "
            "is supported and will be used."
        )
        self.assertFalse(scan["rhi"]["positive_binding_passed"])
        self.assertTrue(scan["rhi"]["selected_non_sm6_lines"])

    def test_inactive_sm6_invalidates_otherwise_positive_rhi(self) -> None:
        scan = scan_unreal_log(
            _good_log() + "\nLogRHI: SM6 is inactive; D3D12 selected"
        )
        self.assertFalse(scan["rhi"]["positive_binding_passed"])
        self.assertTrue(scan["rhi"]["fallback_or_rejection_lines"])

    def test_enumerated_rtx_is_not_selected_when_other_adapter_is_chosen(
        self,
    ) -> None:
        lines = [
            line
            for line in _good_log().splitlines()
            if "RHI Selected:" not in line
            and "Found D3D12 adapter" not in line
            and "Chosen D3D12 Adapter Id" not in line
        ]
        lines.extend(
            (
                "LogRHI: Using Default RHI: D3D12",
                "LogRHI: Using Highest Feature Level of D3D12: SM6",
                "LogD3D12RHI: Found D3D12 adapter 0: "
                "NVIDIA GeForce RTX 3080",
                "LogD3D12RHI: Found D3D12 adapter 1: AMD Radeon RX 7900",
                "LogD3D12RHI: Chosen D3D12 Adapter Id = 1",
            )
        )
        scan = scan_unreal_log("\n".join(lines))
        self.assertFalse(scan["rhi"]["positive_binding_passed"])
        self.assertFalse(scan["rhi"]["rtx_3080"])
        self.assertTrue(scan["rhi"]["chosen_id_has_competing_binding"])

    def test_free_form_rtx_selected_text_is_not_a_canonical_binding(
        self,
    ) -> None:
        lines = [
            line
            for line in _good_log().splitlines()
            if "Found D3D12 adapter" not in line
            and "Chosen D3D12 Adapter Id" not in line
        ]
        lines.append(
            "LogD3D12RHI: Chosen D3D12 Adapter: "
            "NVIDIA GeForce RTX 3080"
        )
        scan = scan_unreal_log("\n".join(lines))
        self.assertFalse(scan["rhi"]["positive_binding_passed"])
        self.assertFalse(scan["rhi"]["rtx_3080"])
        self.assertFalse(scan["rhi"]["chosen_id_bound_to_rtx_3080"])

    def test_negative_rtx_state_invalidates_canonical_binding(self) -> None:
        adversarial_lines = (
            "LogD3D12RHI: NVIDIA GeForce RTX 3080 is not selected",
            "LogD3D12RHI: No active RTX 3080",
            "LogD3D12RHI: RTX 3080 is not active",
            "LogD3D12RHI: NVIDIA GeForce RTX 3080 is not the "
            "active adapter",
            "LogD3D12RHI: NVIDIA GeForce RTX 3080 is not active device",
            "LogD3D12RHI: RTX 3080 unselected",
        )
        for line in adversarial_lines:
            with self.subTest(line=line):
                scan = scan_unreal_log(_good_log() + "\n" + line)
                self.assertFalse(scan["rhi"]["positive_binding_passed"])
                self.assertTrue(
                    scan["rhi"]["rtx_3080_negative_or_inactive_lines"]
                )

    def test_competing_selected_backend_fails_closed(self) -> None:
        adversarial_lines = (
            "LogRHI: RHI Selected: Vulkan",
            "LogRHI: RHI D3D11 with Feature Level SM5 is supported "
            "and will be used.",
            "LogVulkanRHI: Vulkan RHI will be used",
            "LogRHI: D3D11 RHI Selected",
            "LogD3D11RHI: Creating D3D11 RHI",
        )
        for line in adversarial_lines:
            with self.subTest(line=line):
                scan = scan_unreal_log(_good_log() + "\n" + line)
                self.assertFalse(scan["rhi"]["positive_binding_passed"])
                self.assertTrue(
                    scan["rhi"]["competing_selected_backend_lines"]
                )

    def test_later_null_or_competing_rhi_state_rejects_prior_good_binding(
        self,
    ) -> None:
        adversarial_lines = (
            "LogRHI: Display: RHI Selected: NullRHI",
            "LogRHI: NullRHI will be used",
            "LogInit: RHI Selected: NullRHI",
            "LogRenderer: NullRHI will be used",
            "LogNullRHI: Using NullRHI",
            "LogRHI: Active RHI: Vulkan",
            "LogRHI: Selected backend = D3D11",
            "LogOpenGL: OpenGL RHI is the active RHI",
            "LogVulkanRHI: Vulkan RHI started",
            "LogMetalRHI: Active renderer is Metal",
            "LogRHI: Current RHI = NullRHI",
            "LogRHI: Using RHI: Vulkan",
            "LogRHI: Switching the renderer to OpenGL",
        )
        for line in adversarial_lines:
            with self.subTest(line=line):
                scan = scan_unreal_log(_good_log() + "\n" + line)
                self.assertFalse(scan["rhi"]["positive_binding_passed"])
                self.assertTrue(
                    scan["rhi"]["competing_selected_backend_lines"]
                )

    def test_later_d3d12_negation_rejects_prior_good_binding(self) -> None:
        adversarial_lines = (
            "LogRHI: D3D12 RHI is not the active RHI",
            "LogRHI: No active D3D12 RHI",
            "LogRHI: D3D12 is no longer active",
            "LogRHI: D3D12 RHI is not currently active",
            "LogRHI: D3D12 is no longer the selected RHI",
            "LogRHI: D3D12 is not the current RHI",
            "LogRHI: No D3D12 RHI is active",
            "LogRHI: Active RHI is not D3D12",
            "LogRenderer: Active RHI is not D3D12",
            "LogRHI: Selected backend = not D3D12",
            "LogRHI: SM6 is not the selected shader model",
            "LogShaderCompilers: PCD3D_SM6 is not in use",
        )
        for line in adversarial_lines:
            with self.subTest(line=line):
                scan = scan_unreal_log(_good_log() + "\n" + line)
                self.assertFalse(scan["rhi"]["positive_binding_passed"])
                self.assertTrue(
                    scan["rhi"]["fallback_or_rejection_lines"]
                    or scan["rhi"]["inactive_or_unselected_d3d12_lines"]
                )

    def test_negative_competing_backend_mentions_do_not_override_good_rhi(
        self,
    ) -> None:
        informational_lines = (
            "LogVulkanRHI: Vulkan RHI is not selected",
            "LogRHI: NullRHI will not be used",
            "LogD3D11RHI: D3D11 RHI is inactive",
            "LogOpenGL: OpenGL support is available",
            "LogRHI: RHI Selected: not Vulkan",
        )
        scan = scan_unreal_log(
            "\n".join((_good_log(), *informational_lines))
        )
        self.assertTrue(scan["rhi"]["positive_binding_passed"])
        self.assertFalse(scan["rhi"]["competing_selected_backend_lines"])

    def test_hard_failures_and_soft_pack_warnings_are_separate(self) -> None:
        text = "\n".join(
            (
                _good_log(),
                "LogWindows: Error: Fatal error: GPU Crashed "
                "DXGI_ERROR_DEVICE_REMOVED",
                "LogMaterial: Warning: MM_Sun fell back",
                "LogVirtualTexture: Warning: RVT producer unavailable",
                "LogFoliage: Warning: foliage instance base cache mismatch",
            )
        )
        scan = scan_unreal_log(text)
        self.assertTrue(scan["hard_findings"]["fatal"])
        self.assertTrue(scan["hard_findings"]["gpu_loss"])
        self.assertTrue(scan["warning_findings"]["mm_sun"])
        self.assertTrue(scan["warning_findings"]["rvt"])
        self.assertTrue(scan["warning_findings"]["foliage"])

    def test_provider_ready_server_endpoint_is_unapproved_activation(self) -> None:
        scan = scan_unreal_log(
            _good_log()
            + "\nLogNwiro: NwiroIntegrationKit server READY; "
            "endpoint bound and serving"
        )
        self.assertEqual(
            len(scan["provider_off"]["activation_findings"]), 1
        )
        self.assertEqual(
            len(scan["provider_off"]["unapproved_mentions"]), 1
        )

    def test_provider_activation_cannot_hide_behind_disable_option(self) -> None:
        disabled = ",".join(postflight.REQUIRED_DISABLED_PLUGINS)
        scan = scan_unreal_log(
            _good_log()
            + "\nLogNwiro: NwiroIntegrationKit server READY; "
            f"endpoint bound; -DisablePlugins={disabled}"
        )
        self.assertEqual(
            len(scan["provider_off"]["activation_findings"]), 1
        )
        self.assertEqual(
            len(scan["provider_off"]["unapproved_mentions"]), 1
        )

    def test_obvious_provider_service_activation_phrases_fail_closed(
        self,
    ) -> None:
        adversarial_lines = (
            "LogNwiro: NwiroIntegrationKit server online",
            "LogMCP: ModelContextProtocol endpoint live",
            "LogUAIP: UnrealAIIntegrationPlatform MCP server launched",
            "LogNwiro: NwiroIntegrationKit accepting connections",
            "LogMCP: ModelContextProtocol endpoint ready",
            "LogMCP: ModelContextProtocol endpoint listening",
            "LogMCP: ModelContextProtocol endpoint bound",
            "LogMCP: ModelContextProtocol server started",
            "LogMCP: ModelContextProtocol server running",
            "LogMCP: ModelContextProtocol provider active",
            "LogMCP: ModelContextProtocol endpoint serving",
            "LogMCP: ModelContextProtocol endpoint serves requests",
            "LogMCP: ModelContextProtocol accepts connections",
            "LogMCP: ModelContextProtocol connection accepted",
        )
        for line in adversarial_lines:
            with self.subTest(line=line):
                scan = scan_unreal_log(_good_log() + "\n" + line)
                self.assertEqual(
                    len(scan["provider_off"]["activation_findings"]), 1
                )
                self.assertEqual(
                    len(scan["provider_off"]["unapproved_mentions"]), 1
                )

    def test_provider_descriptor_metadata_is_retained_not_activation(
        self,
    ) -> None:
        benign_lines = (
            "LogPluginManager: Display: By default, prioritizing project "
            "plugin (Plugins/SteamIntegrationKit/"
            "SteamIntegrationKit.uplugin) over the corresponding engine "
            "version (Engine/Plugins/Marketplace/SteamIntegrationKit.uplugin).",
            "LogPluginManager: Display: Module OnlineSubsystemSteam from "
            "plugin SteamIntegrationKit is already associated with plugin "
            "OnlineSubsystemSteam (maybe because the plugin should be using "
            "bIsPluginExtension)",
            "LogPluginManager: Display: Module SteamSockets from plugin "
            "SteamSockets is already associated with plugin "
            "SteamIntegrationKit (maybe because the plugin should be using "
            "bIsPluginExtension)",
            "LogGameProjectGeneration: Project Titan requires update. Plugin "
            "UnrealAIIntegrationPlatform MarketplaceURL value in project "
            "descriptor () differs from value in plugin descriptor "
            "(https://www.fab.com/listings/example)",
            "LogGameProjectGeneration: Project Titan requires update. Plugin "
            "SteamIntegrationKit MarketplaceURL value in project descriptor "
            "() differs from value in plugin descriptor "
            "(com.epicgames.launcher://ue/marketplace/product/example)",
            "LogPluginManager: Loaded plugin descriptor for "
            "NwiroIntegrationKit",
            "LogPluginManager: NwiroIntegrationKit plugin descriptor "
            "default priority is PreDefault",
            "LogGameProjectGeneration: ModelContextProtocol MarketplaceURL "
            "value is https://example.invalid/live-provider-listing",
        )
        scan = scan_unreal_log(
            "\n".join((_good_log(), *benign_lines))
        )
        self.assertFalse(scan["provider_off"]["activation_findings"])
        self.assertFalse(scan["provider_off"]["unapproved_mentions"])
        self.assertEqual(
            len(scan["provider_off"]["nonactivation_mentions"]),
            len(benign_lines),
        )
        warning_categories = {
            finding["category"]
            for finding in postflight._warning_summary(scan)
        }
        self.assertIn(
            "provider_nonactivation_metadata", warning_categories
        )

    def test_explicitly_skipped_provider_is_not_activation(self) -> None:
        scan = scan_unreal_log(
            _good_log()
            + "\nLogPluginManager: Skipping disabled plugin "
            "NwiroIntegrationKit"
        )
        self.assertFalse(scan["provider_off"]["unapproved_mentions"])
        self.assertEqual(
            len(
                scan["provider_off"][
                    "explicitly_disabled_or_skipped_mentions"
                ]
            ),
            1,
        )

    def test_negative_disabled_states_fail_closed(self) -> None:
        adversarial_lines = (
            "LogNwiro: Nwiro disabled=false; server READY and endpoint bound",
            "LogNwiro: NwiroIntegrationKit is not disabled; provider enabled",
            "LogNwiro: NwiroIntegrationKit is not currently disabled",
            "LogNwiro: NwiroIntegrationKit isn't disabled",
            "LogNwiro: NwiroIntegrationKit disabled status: false",
            "LogNwiro: NwiroIntegrationKit disabled? false",
            "LogNwiro: NwiroIntegrationKit disabled plugin setting=false",
            "LogNwiro: NwiroIntegrationKit Skipping "
            "provider-disable enforcement",
        )
        for line in adversarial_lines:
            with self.subTest(line=line):
                scan = scan_unreal_log(_good_log() + "\n" + line)
                self.assertEqual(
                    len(scan["provider_off"]["unapproved_mentions"]), 1
                )
                self.assertFalse(
                    scan["provider_off"][
                        "explicitly_disabled_or_skipped_mentions"
                    ]
                )

    def test_narrow_negative_runtime_provider_state_is_safe(self) -> None:
        safe_lines = (
            "LogNwiro: NwiroIntegrationKit is not loaded",
            "LogPluginManager: Skipping disabled plugin "
            "NwiroIntegrationKit",
            "LogNwiro: NwiroIntegrationKit server offline",
            "LogMCP: ModelContextProtocol endpoint not live",
            "LogUAIP: UnrealAIIntegrationPlatform server was not launched",
            "LogNwiro: NwiroIntegrationKit not accepting connections",
        )
        for line in safe_lines:
            with self.subTest(line=line):
                scan = scan_unreal_log(_good_log() + "\n" + line)
                self.assertFalse(scan["provider_off"]["unapproved_mentions"])
                self.assertFalse(scan["provider_off"]["activation_findings"])
                self.assertEqual(
                    len(
                        scan["provider_off"][
                            "explicitly_disabled_or_skipped_mentions"
                        ]
                    ),
                    1,
                )

    def test_disabled_provider_with_ready_bound_state_fails_closed(
        self,
    ) -> None:
        scan = scan_unreal_log(
            _good_log()
            + "\nLogNwiro: NwiroIntegrationKit is disabled; "
            "server READY and endpoint bound"
        )
        self.assertEqual(
            len(scan["provider_off"]["unapproved_mentions"]), 1
        )
        self.assertEqual(
            len(scan["provider_off"]["activation_findings"]), 1
        )
        self.assertFalse(
            scan["provider_off"]["explicitly_disabled_or_skipped_mentions"]
        )


class EditorIdentityBindingTests(unittest.TestCase):
    def _fixture(
        self,
        root: Path,
    ) -> tuple[dict[str, object], dict[str, object], Path, Path]:
        project_root = root / "ScratchProject"
        run_dir = root / "Diagnostics" / "Run"
        project_root.mkdir(parents=True)
        run_dir.mkdir(parents=True)
        project_file = project_root / "Titan.uproject"
        project_file.write_text("{}", encoding="utf-8")
        disabled = ",".join(postflight.REQUIRED_DISABLED_PLUGINS)
        abs_log = run_dir / "UnrealEditor.log"
        current_command_line = " ".join(
            (
                str(postflight.EXPECTED_EDITOR_EXE),
                str(project_file),
                postflight.DESTINATION_MAP,
                "-d3d12",
                "-sm6",
                f"-DisablePlugins={disabled}",
                f"-ExecutePythonScript={postflight.EXPECTED_LIVE_VALIDATOR}",
                f"-AbsLog={abs_log}",
            )
        )
        audited_command_line = current_command_line.replace(
            f"{project_file} ", "", 1
        )
        now = dt.datetime.now(dt.timezone.utc)
        process: dict[str, object] = {
            "pid": 42,
            "alive_at_postflight": True,
            "image_path": str(postflight.EXPECTED_EDITOR_EXE),
            "creation_utc": (now - dt.timedelta(minutes=2)).isoformat(),
            "command_line": current_command_line,
            "command_line_sha256": hashlib.sha256(
                current_command_line.encode("utf-8")
            ).hexdigest().upper(),
        }
        audit: dict[str, object] = {
            "captured_utc": (now - dt.timedelta(minutes=1)).isoformat(),
            "completed_utc": (now - dt.timedelta(seconds=30)).isoformat(),
            "command_line": {
                "command_line": audited_command_line,
                "project_binding": {
                    "path": str(project_file),
                    "authority": "unreal.Paths.get_project_file_path",
                    "in_process_command_line_project_tokens": [],
                },
            },
        }
        return process, audit, project_root, run_dir

    def test_win32_project_token_and_audit_project_binding_are_distinct(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            process, audit, project_root, run_dir = self._fixture(
                Path(directory)
            )
            result = postflight._validate_editor_identity_binding(
                process=process,
                audit=audit,
                project_root=project_root,
                run_dir=run_dir,
            )
        self.assertEqual(len(result["win32_process_project_tokens"]), 1)
        self.assertEqual(result["audit_in_process_project_tokens"], [])
        self.assertEqual(
            result["audit_project_binding"]["authority"],
            "unreal.Paths.get_project_file_path",
        )

    def test_missing_or_wrong_audit_project_binding_fails_closed(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            process, audit, project_root, run_dir = self._fixture(
                Path(directory)
            )
            audit["command_line"]["project_binding"]["authority"] = (
                "command_line_guess"
            )
            with self.assertRaisesRegex(
                PostflightError, "project_binding"
            ):
                postflight._validate_editor_identity_binding(
                    process=process,
                    audit=audit,
                    project_root=project_root,
                    run_dir=run_dir,
                )

    def test_win32_process_must_retain_exact_project_token(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            process, audit, project_root, run_dir = self._fixture(
                Path(directory)
            )
            process["command_line"] = str(process["command_line"]).replace(
                f"{project_root / 'Titan.uproject'} ", "", 1
            )
            with self.assertRaisesRegex(
                PostflightError, "process command line must contain"
            ):
                postflight._validate_editor_identity_binding(
                    process=process,
                    audit=audit,
                    project_root=project_root,
                    run_dir=run_dir,
                )


class EndToEndFixtureTests(unittest.TestCase):
    def test_exact_fixture_passes_and_output_is_no_clobber(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            diagnostics = root / "Diagnostics"
            run_dir = diagnostics / "M07_Live"
            project = root / "Scratch" / "TropBiomeV1A"
            production = root / "Production"
            run_dir.mkdir(parents=True)
            project.mkdir(parents=True)
            production.mkdir(parents=True)
            (project / "Titan.uproject").write_text("{}", encoding="utf-8")

            protected_relative = Path("Content/Protected/Planet.umap")
            vendor_relative = Path(
                "Content/Zenscape_Island/Model/TestRoot.uasset"
            )
            scratch_protected = project / protected_relative
            production_protected = production / protected_relative
            vendor = project / vendor_relative
            for path, payload in (
                (scratch_protected, b"protected-baseline"),
                (production_protected, b"protected-baseline"),
                (vendor, b"reviewed-vendor-root"),
            ):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(payload)

            pre_snap = b"pre-snap-map"
            backup = run_dir / postflight.BACKUP_FILENAME
            backup.write_bytes(pre_snap)
            stage_map = project / postflight.DESTINATION_MAP_RELATIVE
            stage_map.parent.mkdir(parents=True, exist_ok=True)
            stage_map.write_bytes(b"post-snap-map-with-native-delta")

            screenshot_records: list[dict[str, object]] = []
            for index, (view, filename) in enumerate(
                zip(
                    postflight.SCREENSHOT_VIEW_NAMES,
                    postflight.SCREENSHOT_FILENAMES,
                )
            ):
                path = run_dir / filename
                path.write_bytes(
                    _png_bytes(
                        rgba=bytes((16 + index, 32 + index, 48 + index, 255))
                    )
                )
                screenshot_records.append(
                    {
                        "name": view,
                        "expected_screenshot_path": str(path),
                        "high_res_shot_issued": True,
                        "high_res_shot_command": (
                            f'HighResShot filename="{path}" 1920x1080'
                        ),
                        "screenshot_existence":
                            "verified_exact_nonempty_stable_file",
                        "screenshot_pixels_inspected": False,
                        "pixel_review": "pending_external_inspection",
                        "screenshot_file": _record(path),
                    }
                )

            validator = root / "validator.py"
            validator.write_text("# fixture", encoding="utf-8")
            disabled = ",".join(postflight.REQUIRED_DISABLED_PLUGINS)
            abs_log = run_dir / "UnrealEditor.log"
            command_line = " ".join(
                (
                    r'"D:\UE_5.8\Engine\Binaries\Win64\UnrealEditor.exe"',
                    f'"{project / "Titan.uproject"}"',
                    postflight.DESTINATION_MAP,
                    "-d3d12",
                    "-sm6",
                    f"-DisablePlugins={disabled}",
                    f'-ExecutePythonScript="{validator}"',
                    f'-AbsLog="{abs_log}"',
                )
            )
            audit_command_line = command_line.replace(
                f'"{project / "Titan.uproject"}" ', "", 1
            )
            abs_log.write_text(_good_log(command_line), encoding="utf-8")

            protected_key = str(protected_relative).replace("\\", "/")
            vendor_key = str(vendor_relative).replace("\\", "/")
            files = {
                "protected": {protected_key: _record(scratch_protected)},
                "canonical_protected": {
                    protected_key: _record(production_protected)
                },
                "vendor": {vendor_key: _record(vendor)},
            }
            creation = dt.datetime.now(dt.timezone.utc) - dt.timedelta(
                minutes=2
            )
            captured = creation + dt.timedelta(seconds=30)
            completed = captured + dt.timedelta(minutes=1)
            authoring_hash = "A" * 64
            audit = {
                "schema_version": 1,
                "module": "M07",
                "operation":
                    "tropical_planetary_biome_live_snap_visual_validation_v1",
                "result": "passed_pending_screenshot_pixel_inspection",
                "captured_utc": captured.isoformat(),
                "completed_utc": completed.isoformat(),
                "project_root": str(project),
                "map": postflight.DESTINATION_MAP,
                "scratch_only": True,
                "PIE_started": False,
                "providers_used": False,
                "water_or_cloud_assets_applied": False,
                "command_line": {
                    "command_line": audit_command_line,
                    "project_binding": {
                        "path": str(project / "Titan.uproject"),
                        "authority": "unreal.Paths.get_project_file_path",
                        "in_process_command_line_project_tokens": [],
                        "note": (
                            "UE may strip the launch-time .uproject token "
                            "from its in-process command-line view."
                        ),
                    },
                },
                "authoring_audit": {
                    "path": str(root / "authoring_audit.json"),
                    "bytes": 1,
                    "sha256": authoring_hash,
                    "authenticated_operation":
                        "tropical_planetary_biome_scratch_stage_v1",
                    "authenticated_result": "passed",
                },
                "pre_snap_backup": {"backup": _record(backup)},
                "files_before": files,
                "files_after": files,
                "snap": {
                    "post_save_map": _record(stage_map),
                    "captured_managed_state_delta_exact": True,
                    "captured_managed_state_delta": (
                        "native location/rotation snap plus exact "
                        "PendingNativePlanetSnap-to-"
                        "NativePlanetSnapComplete replacement"
                    ),
                },
                "viewport_captures": screenshot_records,
                "claims": {
                    "scratch_map_native_snap_saved": True,
                    "managed_actors_snapped": 17,
                    "captured_managed_state_delta_exact": True,
                    "managed_state_delta": (
                        "native transform snap plus exact "
                        "pending-to-complete tag transition"
                    ),
                    "collision_accepted": False,
                    "screenshot_commands_issued": 3,
                    "screenshot_files_verified": True,
                    "screenshot_pixels_inspected": False,
                    "real_gpu_pixels_verified": False,
                    "PIE_or_gameplay_accepted": False,
                    "water_integrated": False,
                    "cloud_integrated": False,
                    "performance_accepted": False,
                    "surface_to_orbit_accepted": False,
                    "production_integration_accepted": False,
                },
            }
            audit_path = run_dir / postflight.LIVE_AUDIT_FILENAME
            audit_path.write_text(
                json.dumps(audit, indent=2), encoding="utf-8"
            )

            process = {
                "pid": 43210,
                "alive_at_postflight": True,
                "image_path": str(postflight.EXPECTED_EDITOR_EXE),
                "creation_utc": creation.isoformat(),
                "command_line": command_line,
                "command_line_sha256": hashlib.sha256(
                    command_line.encode("utf-8")
                ).hexdigest().upper(),
            }
            launcher = run_dir / "launcher_evidence.json"
            launcher.write_text(
                json.dumps(
                    {
                        "editor_pid": process["pid"],
                        "editor_creation_utc": process["creation_utc"],
                        "editor_image_path": process["image_path"],
                        "editor_command_line_sha256":
                            process["command_line_sha256"],
                        "listeners_before": [],
                        "listeners_after": [
                            {
                                "pid": 999,
                                "address": "127.0.0.1",
                                "port": 12345,
                            }
                        ],
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
            args = argparse.Namespace(
                run_dir=str(run_dir),
                editor_pid=process["pid"],
                project_root=str(project),
                production_root=str(production),
                launcher_evidence=str(launcher),
            )

            with (
                mock.patch.object(
                    postflight, "DIAGNOSTICS_ROOT", diagnostics
                ),
                mock.patch.object(
                    postflight, "EXPECTED_PROJECT_ROOT", project
                ),
                mock.patch.object(
                    postflight, "EXPECTED_PRODUCTION_ROOT", production
                ),
                mock.patch.object(
                    postflight, "EXPECTED_LIVE_VALIDATOR", validator
                ),
                mock.patch.object(
                    postflight,
                    "EXPECTED_LIVE_VALIDATOR_SHA256",
                    _sha(validator),
                ),
                mock.patch.object(
                    postflight,
                    "EXPECTED_PRE_SNAP_MAP_SHA256",
                    hashlib.sha256(pre_snap).hexdigest().upper(),
                ),
                mock.patch.object(
                    postflight, "EXPECTED_PRE_SNAP_MAP_BYTES", len(pre_snap)
                ),
                mock.patch.object(
                    postflight,
                    "EXPECTED_AUTHORING_AUDIT_SHA256",
                    authoring_hash,
                ),
                mock.patch.object(
                    postflight,
                    "PROTECTED_PROJECT_FILES",
                    {protected_relative: _sha(scratch_protected)},
                ),
                mock.patch.object(
                    postflight,
                    "VENDOR_ROOT_FILES",
                    {vendor_relative: (vendor.stat().st_size, _sha(vendor))},
                ),
                mock.patch.object(
                    postflight,
                    "_query_editor_process",
                    return_value=process,
                ),
            ):
                report, passed = postflight._run(args)
                self.assertTrue(passed)
                self.assertEqual(report["evidence_class"], "real_gpu_visual")
                self.assertTrue(
                    report["launcher_network_evidence"]["passed"]
                )
                self.assertEqual(
                    report["screenshot_gate"]["distinct_sha256_count"], 3
                )
                postflight._write_no_clobber_json(
                    run_dir / postflight.POSTFLIGHT_FILENAME, report
                )
                with self.assertRaisesRegex(
                    PostflightError, "no-clobber"
                ):
                    postflight._run(args)

    def test_launcher_new_editor_listener_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "launcher.json"
            process = {
                "pid": 73,
                "creation_utc": "2026-07-26T00:00:00+00:00",
                "image_path": str(postflight.EXPECTED_EDITOR_EXE),
                "command_line": "editor command",
                "command_line_sha256": hashlib.sha256(
                    b"editor command"
                ).hexdigest().upper(),
            }
            path.write_text(
                json.dumps(
                    {
                        "editor_pid": 73,
                        "editor_creation_utc": process["creation_utc"],
                        "editor_image_path": process["image_path"],
                        "editor_command_line_sha256":
                            process["command_line_sha256"],
                        "listeners_before": [],
                        "listeners_after": [
                            {
                                "pid": 73,
                                "address": "127.0.0.1",
                                "port": 8000,
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                PostflightError, "new editor-owned listeners"
            ):
                postflight._validate_launcher_evidence(path, process)


if __name__ == "__main__":
    unittest.main()
