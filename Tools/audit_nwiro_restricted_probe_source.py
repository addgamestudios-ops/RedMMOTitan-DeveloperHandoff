"""Fail-closed baseline audit for NWIRO's future restricted metadata probe.

This tool is intentionally offline.  It does not import Unreal modules, start
NWIRO, open a socket, dispatch a tool, or modify the Marketplace plugin.  It
authenticates the reviewed Nwiro Integration Kit 1.0.9 source revision and
records the missing source controls that block the M07 ``find_assets`` probe.

This version can never report a candidate as ready. The source-shape checks are
diagnostic requirements, not a C++ semantic proof or authorization mechanism.
A separately reviewed candidate-source contract, complete critical-tree
manifest, build/binary attestation, and runtime acceptance must be implemented
before any later version can add a positive state. Source drift is neither
ready nor the reviewed blocked baseline.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PLUGIN_ROOT = Path(
    "D:/UE_5.8/Engine/Plugins/Marketplace/NWIROAIIf0b7fbfe049eV4"
)
PRIVATE_SOURCE = Path("Source/NwiroIntegrationKit/Private")
PINNED_FILES: dict[str, str] = {
    "NwiroIntegrationKit.uplugin": (
        "D6CCBFA2F08D478F0C53C67E0D8FCD5FF275C57948425D55D560309AD1C60B2E"
    ),
    "Source/NwiroIntegrationKit/Private/NwiroIKMCPServer.cpp": (
        "34C1BB2E81A7FFF742D043EC8E983783C047BA9C5ABBA4BE9CDB4806AD7CD8D7"
    ),
    "Source/NwiroIntegrationKit/Private/NwiroIKMCPServer.h": (
        "CB310B6A8857AD8824F5899C13C263FEE5EF5558F3F7BCE9E8EA0198B7272498"
    ),
    "Source/NwiroIntegrationKit/Private/NwiroIKBridge.cpp": (
        "80C8A3194148C86D1F4E1D479133BB2B76A627698F2E35DC4D6CE822E5FC1AA1"
    ),
    "Source/NwiroIntegrationKit/Private/NwiroIKBridge.h": (
        "36F575E5419F0CFFB713623CF127E9D3196B6F184AC2C5DE718E4AB9AF4149A8"
    ),
    "Source/NwiroIntegrationKit/Private/NwiroIntegrationKit.cpp": (
        "0AF1C0174BB2AF09A9555D6E6EBB471E0F9C1FF43B3E1537A0EFA415C0AA2BCF"
    ),
    "Source/NwiroIntegrationKit/Private/NwiroIKToolRegistry.cpp": (
        "433F109135398BDA67BC3E6F45809A1AB46BE900BC1D81D0713F6E980EC490F6"
    ),
    "Source/NwiroIntegrationKit/Private/NwiroIKToolRegistry.h": (
        "2305196855A310FED385FB8E745C7F6F5B86F9D0B1E71EB316E7502535524DC1"
    ),
    "Source/NwiroIntegrationKit/Private/NwiroIKAssetTools.cpp": (
        "E30B47D984781D45B5C34B9C8F595AED9769725F80F2BB7223889C1E6C5FC519"
    ),
    "Source/NwiroIntegrationKit/Private/NwiroIKAssetTools.h": (
        "46374513B2AE5A821844E20622ECD886F125A8DCCD40A1567B2965E1B7CA0546"
    ),
    "Source/NwiroIntegrationKit/NwiroIntegrationKit.Build.cs": (
        "58558909E21B8F856B5EECAB6A8C1043D32C85DAEC9526BA1021E98FCD74CA57"
    ),
}
MAX_SOURCE_BYTES = 8 * 1024 * 1024
EXPECTED_FAIL_OPEN_EXTENSION_GATES = 7


class NwiroSourceAuditError(RuntimeError):
    """The source could not be authenticated or parsed unambiguously."""


@dataclass(frozen=True)
class SourceCheck:
    control: str
    source_shape_observed: bool
    evidence: str


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest().upper()


def _read_bounded(path: Path) -> bytes:
    size = path.stat().st_size
    if size <= 0:
        raise NwiroSourceAuditError(f"source file is empty: {path}")
    if size > MAX_SOURCE_BYTES:
        raise NwiroSourceAuditError(
            f"source file exceeds {MAX_SOURCE_BYTES} bytes: {path}"
        )
    payload = path.read_bytes()
    if len(payload) != size:
        raise NwiroSourceAuditError(f"source file changed while reading: {path}")
    return payload


def _decode_source(payload: bytes, label: str) -> str:
    try:
        return payload.decode("utf-8")
    except UnicodeDecodeError as error:
        raise NwiroSourceAuditError(f"{label} is not UTF-8: {error}") from error


def _mask_cpp_noncode(source: str) -> str:
    """Replace comments and quoted literals while preserving offsets/newlines."""

    output = list(source)
    state = "code"
    index = 0
    while index < len(source):
        char = source[index]
        following = source[index + 1] if index + 1 < len(source) else ""

        if state == "code":
            if char == "/" and following == "/":
                output[index] = output[index + 1] = " "
                state = "line_comment"
                index += 2
                continue
            if char == "/" and following == "*":
                output[index] = output[index + 1] = " "
                state = "block_comment"
                index += 2
                continue
            if char == '"':
                output[index] = " "
                state = "string"
                index += 1
                continue
            if char == "'":
                output[index] = " "
                state = "character"
                index += 1
                continue
            index += 1
            continue

        if state == "line_comment":
            if char == "\n":
                state = "code"
            else:
                output[index] = " "
            index += 1
            continue

        if state == "block_comment":
            if char == "*" and following == "/":
                output[index] = output[index + 1] = " "
                state = "code"
                index += 2
            else:
                if char != "\n":
                    output[index] = " "
                index += 1
            continue

        if state in {"string", "character"}:
            terminator = '"' if state == "string" else "'"
            if char == "\\":
                output[index] = " "
                if index + 1 < len(source):
                    if source[index + 1] != "\n":
                        output[index + 1] = " "
                    index += 2
                else:
                    index += 1
                continue
            if char == terminator:
                output[index] = " "
                state = "code"
            elif char != "\n":
                output[index] = " "
            index += 1
            continue

    if state in {"block_comment", "string", "character"}:
        raise NwiroSourceAuditError(f"unterminated C++ lexical construct: {state}")
    return "".join(output)


def _extract_function(source: str, qualified_name: str) -> str:
    """Extract one C++ function definition by its exact qualified name."""

    masked = _mask_cpp_noncode(source)
    matches = list(re.finditer(re.escape(qualified_name), masked))
    definitions: list[tuple[int, int]] = []
    for match in matches:
        open_brace = masked.find("{", match.end())
        semicolon = masked.find(";", match.end())
        if open_brace < 0 or (semicolon >= 0 and semicolon < open_brace):
            continue
        depth = 0
        for index in range(open_brace, len(masked)):
            if masked[index] == "{":
                depth += 1
            elif masked[index] == "}":
                depth -= 1
                if depth == 0:
                    definitions.append((match.start(), index + 1))
                    break
        else:
            raise NwiroSourceAuditError(
                f"unbalanced function body for {qualified_name}"
            )
    if len(definitions) != 1:
        raise NwiroSourceAuditError(
            f"expected one definition for {qualified_name}, found {len(definitions)}"
        )
    start, end = definitions[0]
    return source[start:end]


def _ordered(body: str, *tokens: str) -> bool:
    cursor = -1
    for token in tokens:
        cursor = body.find(token, cursor + 1)
        if cursor < 0:
            return False
    return True


def _contains_guarded_call(
    body: str, condition: str, call: str, *, negated: bool = False
) -> bool:
    condition_text = rf"!\s*{re.escape(condition)}" if negated else re.escape(condition)
    pattern = re.compile(
        rf"if\s*\(\s*{condition_text}\s*\(\s*\)\s*\)\s*"
        rf"(?:\{{\s*)?{re.escape(call)}\s*\(\s*\)\s*;",
        re.DOTALL,
    )
    return pattern.search(body) is not None


def evaluate_source_controls(server_cpp: str, bridge_cpp: str) -> list[SourceCheck]:
    """Inventory source shapes; this function cannot authorize a candidate."""

    # All control checks operate on lexical code only. Comments and quoted
    # strings must not be able to satisfy a future authorization invariant.
    server_code = _mask_cpp_noncode(server_cpp)
    bridge_code = _mask_cpp_noncode(bridge_cpp)
    start = _mask_cpp_noncode(
        _extract_function(server_cpp, "FNwiroIKMCPServer::Start")
    )
    post = _mask_cpp_noncode(
        _extract_function(server_cpp, "FNwiroIKMCPServer::HandleMCPPost")
    )
    process = _mask_cpp_noncode(
        _extract_function(server_cpp, "FNwiroIKMCPServer::ProcessJsonRpc")
    )
    tools_list = _mask_cpp_noncode(
        _extract_function(server_cpp, "FNwiroIKMCPServer::HandleToolsList")
    )
    dispatch = _mask_cpp_noncode(
        _extract_function(server_cpp, "FNwiroIKMCPServer::DispatchTool")
    )

    mode_references = server_code.count("IsRestrictedMetadataProbeMode")
    mode_declared = mode_references >= 5

    lock_before_listener = (
        "AcquireRestrictedProbeProcessLock" in start
        and _ordered(
            start,
            "AcquireRestrictedProbeProcessLock",
            "BindRestrictedMetadataProbeRoute",
            "StartAllListeners",
        )
    )

    alternate_routes_suppressed = (
        "BindRestrictedMetadataProbeRoute" in start
        and "BindStandardMcpRoutes" in start
        and "VERB_GET" not in start
        and "VERB_OPTIONS" not in start
        and "VERB_DELETE" not in start
    )

    config_suppressed = _contains_guarded_call(
        start, "IsRestrictedMetadataProbeMode", "WriteClaudeConfig", negated=True
    )

    process_gated = (
        "ValidateRestrictedProbeJsonRpc" in process
        and _ordered(
            process,
            "ValidateRestrictedProbeJsonRpc",
            "GetStringField",
            "HandleToolsCall",
        )
    )

    registry_bound = (
        "GetRestrictedProbeToolDefinitionsJson" in tools_list
        and _ordered(
            tools_list,
            "GetRestrictedProbeToolDefinitionsJson",
            "GetEnabledToolDefinitionsJson",
        )
    )

    dispatch_allowlisted = (
        "ValidateRestrictedFindAssetsCall" in dispatch
        and _ordered(
            dispatch,
            "ValidateRestrictedFindAssetsCall",
            "DispatchToolImpl",
        )
    )

    headless_fail_closed = (
        "RejectRestrictedProbeWithoutInteractiveApproval" in post
        and _ordered(
            post,
            "RejectRestrictedProbeWithoutInteractiveApproval",
            "bool bBypass",
        )
        and not re.search(
            r"else\s*\{[^{}]*bBypass\s*=\s*true\s*;",
            post,
            flags=re.DOTALL,
        )
    )

    fail_open_pattern = re.compile(
        r"UNwiroIKBridge::Instance\s*&&\s*"
        r"!UNwiroIKBridge::Instance->IsChatExtensionEnabled"
    )
    fail_closed_pattern = re.compile(
        r"!UNwiroIKBridge::Instance\s*\|\|\s*"
        r"!UNwiroIKBridge::Instance->IsChatExtensionEnabled"
    )
    fail_open_count = len(fail_open_pattern.findall(server_code))
    fail_closed_count = len(fail_closed_pattern.findall(server_code))
    provider_bridge_null_closed = (
        fail_open_count == 0
        and fail_closed_count >= EXPECTED_FAIL_OPEN_EXTENSION_GATES
    )

    acp_calls_process = "FNwiroIKMCPServer::ProcessJsonRpc" in bridge_code
    acp_suppressed = not acp_calls_process

    controls = [
        SourceCheck(
            "restricted_mode_declared",
            mode_declared,
            f"IsRestrictedMetadataProbeMode references={mode_references}; required>=5",
        ),
        SourceCheck(
            "exclusive_process_lock_before_listener",
            lock_before_listener,
            "AcquireRestrictedProbeProcessLock must precede restricted route binding "
            "and StartAllListeners",
        ),
        SourceCheck(
            "alternate_http_routes_suppressed",
            alternate_routes_suppressed,
            "restricted and standard route helpers must be separated; Start must "
            "not directly bind GET/OPTIONS/DELETE",
        ),
        SourceCheck(
            "vendor_config_publication_suppressed",
            config_suppressed,
            "WriteClaudeConfig must run only when restricted mode is false",
        ),
        SourceCheck(
            "process_jsonrpc_predispatch_gate",
            process_gated,
            "ValidateRestrictedProbeJsonRpc must run before method extraction and "
            "all handlers",
        ),
        SourceCheck(
            "runtime_tool_registry_generation_bound",
            registry_bound,
            "restricted single-tool definitions must be selected before the vendor "
            "enabled-tool registry",
        ),
        SourceCheck(
            "dispatch_tool_exact_allowlist",
            dispatch_allowlisted,
            "ValidateRestrictedFindAssetsCall must run before DispatchToolImpl",
        ),
        SourceCheck(
            "headless_permission_fail_closed",
            headless_fail_closed,
            "restricted no-approval rejection must precede permission bypass; "
            "no unconditional else bBypass=true is permitted",
        ),
        SourceCheck(
            "bridge_null_extension_fail_closed",
            provider_bridge_null_closed,
            f"fail-open gates={fail_open_count}; fail-closed gates={fail_closed_count}; "
            f"required fail-closed>={EXPECTED_FAIL_OPEN_EXTENSION_GATES}",
        ),
        SourceCheck(
            "acp_direct_dispatch_suppressed",
            acp_suppressed,
            f"ACP calls ProcessJsonRpc={acp_calls_process}; required=False",
        ),
    ]
    return controls


def audit_installed_source(plugin_root: Path = DEFAULT_PLUGIN_ROOT) -> dict[str, object]:
    """Authenticate and audit one exact installed Integration Kit tree."""

    if not plugin_root.is_absolute():
        raise NwiroSourceAuditError("plugin root must be absolute")
    resolved = plugin_root.resolve(strict=True)

    file_records: list[dict[str, object]] = []
    payloads: dict[str, bytes] = {}
    source_drift = False
    for relative, expected_hash in PINNED_FILES.items():
        path = resolved / Path(relative)
        payload = _read_bounded(path)
        actual_hash = _sha256_bytes(payload)
        matches = actual_hash == expected_hash
        source_drift = source_drift or not matches
        payloads[relative] = payload
        file_records.append(
            {
                "relative_path": relative,
                "sha256": actual_hash,
                "expected_sha256": expected_hash,
                "matches_reviewed_revision": matches,
                "bytes": len(payload),
            }
        )

    if source_drift:
        return {
            "schema_version": 1,
            "audit": "redmmo_nwiro_restricted_metadata_probe_source",
            "plugin_root": resolved.as_posix(),
            "plugin_version": "1.0.9",
            "source_revision": "drifted",
            "status": "source_drift",
            "runtime_authorized": False,
            "candidate_static_acceptance_supported": False,
            "assessment_kind": "critical_file_baseline_blocker_inventory",
            "file_scope": "named_critical_files_only_not_complete_plugin_tree",
            "running_binary_authenticated": False,
            "files": file_records,
            "checks": [],
            "blocking_controls": ["reviewed_source_revision"],
        }

    server_relative = (
        "Source/NwiroIntegrationKit/Private/NwiroIKMCPServer.cpp"
    )
    bridge_relative = "Source/NwiroIntegrationKit/Private/NwiroIKBridge.cpp"
    controls = evaluate_source_controls(
        _decode_source(payloads[server_relative], server_relative),
        _decode_source(payloads[bridge_relative], bridge_relative),
    )
    blocking = [
        "candidate_hardened_source_contract_absent",
        *[
            check.control
            for check in controls
            if not check.source_shape_observed
        ],
    ]
    return {
        "schema_version": 1,
        "audit": "redmmo_nwiro_restricted_metadata_probe_source",
        "plugin_root": resolved.as_posix(),
        "plugin_version": "1.0.9",
        "source_revision": "reviewed_blocked_baseline_critical_files_exact",
        "status": "blocked",
        "runtime_authorized": False,
        "candidate_static_acceptance_supported": False,
        "assessment_kind": "critical_file_baseline_blocker_inventory",
        "file_scope": "named_critical_files_only_not_complete_plugin_tree",
        "running_binary_authenticated": False,
        "files": file_records,
        "checks": [asdict(check) for check in controls],
        "blocking_controls": blocking,
    }


def canonical_report_bytes(report: dict[str, object]) -> bytes:
    return (
        json.dumps(report, sort_keys=True, indent=2, ensure_ascii=True) + "\n"
    ).encode("utf-8")


def _parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--plugin-root",
        type=Path,
        default=DEFAULT_PLUGIN_ROOT,
        help="Absolute Nwiro Integration Kit root (default: reviewed UE 5.8 install)",
    )
    parser.add_argument(
        "--expect",
        choices=("blocked",),
        default="blocked",
        help="Expected baseline state; this version supports blocked only",
    )
    return parser.parse_args(argv)


def main(argv: Iterable[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        report = audit_installed_source(args.plugin_root)
    except (OSError, NwiroSourceAuditError) as error:
        print(f"NWIRO source audit error: {error}", file=sys.stderr)
        return 2
    sys.stdout.buffer.write(canonical_report_bytes(report))
    return 0 if report["status"] == args.expect else 3


if __name__ == "__main__":
    raise SystemExit(main())
