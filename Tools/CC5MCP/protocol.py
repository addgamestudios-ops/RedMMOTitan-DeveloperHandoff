"""Validated filesystem IPC used by the external CC5 MCP server.

This module intentionally uses only the Python standard library.  The MCP
process never imports RLPy; Character Creator owns all RLPy calls.
"""

from __future__ import annotations

import json
import hashlib
import hmac
import math
import os
import re
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

from .cc5_plugin.windows_security import (
    FIXED_STORAGE_ROOT,
    WindowsSecurityError,
    require_fixed_ntfs_storage,
    require_private_windows_acl,
    secure_child,
    secure_storage_path,
)


PROTOCOL_VERSION = "1.2"
DEFAULT_CONFIG_PATH = Path(
    r"D:\RedMMOTitanWindowsData\CC5MCPBridge\config.json"
)
DEFAULT_ALLOWED_STORAGE_ROOT = FIXED_STORAGE_ROOT
TOKEN_RE = re.compile(r"^[0-9a-fA-F]{64}$")
MORPH_ID_RE = re.compile(r"^[A-Za-z0-9_.:/() +\-]{1,160}$")
VERSION_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
OBJECT_ID_RE = re.compile(r"^[0-9]{1,20}$")
PROJECT_IDENTITY_RE = re.compile(r"^[0-9a-f]{64}$")
REQUEST_ID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)
ALLOWED_OPERATIONS = frozenset(
    {
        "inspect_active_character",
        "list_active_character_morphs",
        "set_approved_morph",
        "apply_approved_linked_preset",
        "save_project_as",
    }
)
REQUEST_FIELDS = frozenset(
    {
        "protocol_version",
        "request_id",
        "operation",
        "created_utc",
        "expires_utc",
        "payload",
        "request_mac",
    }
)
RESPONSE_FIELDS = frozenset(
    {
        "protocol_version",
        "request_id",
        "operation",
        "ok",
        "completed_utc",
        "result",
        "error",
        "response_mac",
    }
)


class BridgeError(RuntimeError):
    """A safe, user-presentable bridge failure."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class MorphRule:
    morph_id: str
    minimum: float
    maximum: float
    label: str


@dataclass(frozen=True)
class LinkedPresetMember:
    morph_alias: str
    value: float


@dataclass(frozen=True)
class LinkedPreset:
    required_character_signature: str
    label: str
    body: LinkedPresetMember
    head: LinkedPresetMember
    definition_digest: str


@dataclass(frozen=True)
class BridgeConfig:
    enabled: bool
    queue_root: Path
    save_root: Path
    bridge_token: str
    request_timeout_seconds: float
    poll_interval_seconds: float
    max_message_bytes: int
    morph_allowlist: Mapping[str, MorphRule]
    linked_presets: Mapping[str, LinkedPreset]
    allowed_storage_root: Path

    @classmethod
    def from_file(
        cls,
        path: Path,
        *,
        allowed_storage_root: Path = DEFAULT_ALLOWED_STORAGE_ROOT,
    ) -> "BridgeConfig":
        try:
            checked_path = secure_child(
                path,
                allowed_storage_root,
                storage_root=allowed_storage_root,
                label="config file",
            )
        except WindowsSecurityError as exc:
            raise BridgeError("path_invalid", str(exc)) from exc
        raw = read_json_limited(checked_path, 128 * 1024)
        if not isinstance(raw, dict):
            raise BridgeError("config_invalid", "Bridge config must be a JSON object.")
        config = cls.from_mapping(
            raw,
            allowed_storage_root=allowed_storage_root,
        )
        if config.enabled:
            _require_private_runtime_layout(checked_path, config)
        return config

    @classmethod
    def from_mapping(
        cls,
        raw: Mapping[str, Any],
        *,
        allowed_storage_root: Path = DEFAULT_ALLOWED_STORAGE_ROOT,
    ) -> "BridgeConfig":
        expected = {
            "enabled",
            "queue_root",
            "save_root",
            "bridge_token",
            "request_timeout_seconds",
            "poll_interval_seconds",
            "max_message_bytes",
            "morph_allowlist",
            "linked_presets",
        }
        unknown = set(raw) - expected
        missing = expected - set(raw)
        if unknown or missing:
            raise BridgeError(
                "config_invalid",
                f"Config keys mismatch; missing={sorted(missing)}, unknown={sorted(unknown)}.",
            )

        enabled = raw["enabled"]
        if not isinstance(enabled, bool):
            raise BridgeError("config_invalid", "enabled must be true or false.")

        try:
            allowed_root = secure_storage_path(
                allowed_storage_root,
                storage_root=allowed_storage_root,
                label="allowed_storage_root",
                allow_root=True,
            )
            queue_root = secure_storage_path(
                raw["queue_root"],
                storage_root=allowed_root,
                label="queue_root",
            )
            save_root = secure_storage_path(
                raw["save_root"],
                storage_root=allowed_root,
                label="save_root",
            )
        except WindowsSecurityError as exc:
            raise BridgeError("path_invalid", str(exc)) from exc
        if queue_root == save_root:
            raise BridgeError(
                "config_invalid", "queue_root and save_root must be different directories."
            )

        bridge_token = raw["bridge_token"]
        if not isinstance(bridge_token, str) or not TOKEN_RE.fullmatch(bridge_token):
            raise BridgeError(
                "config_invalid",
                "bridge_token must be exactly 64 hexadecimal characters.",
            )

        request_timeout = _bounded_number(
            raw["request_timeout_seconds"],
            "request_timeout_seconds",
            1.0,
            30.0,
        )
        poll_interval = _bounded_number(
            raw["poll_interval_seconds"],
            "poll_interval_seconds",
            0.05,
            1.0,
        )
        max_message_bytes = raw["max_message_bytes"]
        if (
            isinstance(max_message_bytes, bool)
            or not isinstance(max_message_bytes, int)
            or not 4096 <= max_message_bytes <= 262144
        ):
            raise BridgeError(
                "config_invalid",
                "max_message_bytes must be an integer from 4096 through 262144.",
            )

        raw_allowlist = raw["morph_allowlist"]
        if not isinstance(raw_allowlist, dict):
            raise BridgeError("config_invalid", "morph_allowlist must be an object.")
        if len(raw_allowlist) > 256:
            raise BridgeError("config_invalid", "morph_allowlist exceeds 256 entries.")

        allowlist: dict[str, MorphRule] = {}
        for alias, rule_raw in raw_allowlist.items():
            if not isinstance(alias, str) or not VERSION_NAME_RE.fullmatch(alias):
                raise BridgeError(
                    "config_invalid",
                    "Morph aliases must use 1-64 letters, digits, dots, underscores, or hyphens.",
                )
            if not isinstance(rule_raw, dict) or set(rule_raw) != {
                "morph_id",
                "minimum",
                "maximum",
                "label",
            }:
                raise BridgeError(
                    "config_invalid",
                    f"Morph rule {alias!r} has invalid fields.",
                )
            morph_id = rule_raw["morph_id"]
            label = rule_raw["label"]
            if not isinstance(morph_id, str) or not MORPH_ID_RE.fullmatch(morph_id):
                raise BridgeError(
                    "config_invalid", f"Morph rule {alias!r} has an invalid morph_id."
                )
            if not isinstance(label, str) or not 1 <= len(label) <= 160:
                raise BridgeError(
                    "config_invalid", f"Morph rule {alias!r} has an invalid label."
                )
            minimum = _bounded_number(
                rule_raw["minimum"], f"{alias}.minimum", -1000.0, 1000.0
            )
            maximum = _bounded_number(
                rule_raw["maximum"], f"{alias}.maximum", -1000.0, 1000.0
            )
            if minimum >= maximum:
                raise BridgeError(
                    "config_invalid",
                    f"Morph rule {alias!r} minimum must be below maximum.",
                )
            allowlist[alias] = MorphRule(
                morph_id=morph_id,
                minimum=minimum,
                maximum=maximum,
                label=label,
            )

        raw_presets = raw["linked_presets"]
        if not isinstance(raw_presets, dict):
            raise BridgeError("config_invalid", "linked_presets must be an object.")
        if len(raw_presets) > 64:
            raise BridgeError("config_invalid", "linked_presets exceeds 64 entries.")
        linked_presets: dict[str, LinkedPreset] = {}
        for preset_alias, preset_raw in raw_presets.items():
            if (
                not isinstance(preset_alias, str)
                or not VERSION_NAME_RE.fullmatch(preset_alias)
            ):
                raise BridgeError(
                    "config_invalid",
                    "Linked preset aliases must use 1-64 safe characters.",
                )
            if not isinstance(preset_raw, dict) or set(preset_raw) != {
                "required_character_signature",
                "label",
                "body",
                "head",
            }:
                raise BridgeError(
                    "config_invalid",
                    f"Linked preset {preset_alias!r} has invalid fields.",
                )
            signature = preset_raw["required_character_signature"]
            label = preset_raw["label"]
            if (
                not isinstance(signature, str)
                or not PROJECT_IDENTITY_RE.fullmatch(signature)
            ):
                raise BridgeError(
                    "config_invalid",
                    f"Linked preset {preset_alias!r} has an invalid character signature.",
                )
            if not isinstance(label, str) or not 1 <= len(label) <= 160:
                raise BridgeError(
                    "config_invalid",
                    f"Linked preset {preset_alias!r} has an invalid label.",
                )
            members: dict[str, LinkedPresetMember] = {}
            for role in ("body", "head"):
                member_raw = preset_raw[role]
                if not isinstance(member_raw, dict) or set(member_raw) != {
                    "morph_alias",
                    "value",
                }:
                    raise BridgeError(
                        "config_invalid",
                        f"Linked preset {preset_alias!r} {role} member is invalid.",
                    )
                morph_alias = member_raw["morph_alias"]
                if (
                    not isinstance(morph_alias, str)
                    or not VERSION_NAME_RE.fullmatch(morph_alias)
                    or morph_alias not in allowlist
                ):
                    raise BridgeError(
                        "config_invalid",
                        f"Linked preset {preset_alias!r} {role} morph is not allowlisted.",
                    )
                morph_rule = allowlist[morph_alias]
                value = _bounded_number(
                    member_raw["value"],
                    f"{preset_alias}.{role}.value",
                    morph_rule.minimum,
                    morph_rule.maximum,
                )
                members[role] = LinkedPresetMember(
                    morph_alias=morph_alias,
                    value=value,
                )
            if members["body"].morph_alias == members["head"].morph_alias:
                raise BridgeError(
                    "config_invalid",
                    f"Linked preset {preset_alias!r} must use distinct body and head morphs.",
                )
            if (
                allowlist[members["body"].morph_alias].morph_id
                == allowlist[members["head"].morph_alias].morph_id
            ):
                raise BridgeError(
                    "config_invalid",
                    f"Linked preset {preset_alias!r} resolves to one morph ID twice.",
                )
            definition = {
                "preset_alias": preset_alias,
                "required_character_signature": signature,
                "label": label,
                "body": {
                    "morph_alias": members["body"].morph_alias,
                    "value": members["body"].value,
                    "rule": {
                        "morph_id": allowlist[
                            members["body"].morph_alias
                        ].morph_id,
                        "minimum": allowlist[
                            members["body"].morph_alias
                        ].minimum,
                        "maximum": allowlist[
                            members["body"].morph_alias
                        ].maximum,
                        "label": allowlist[
                            members["body"].morph_alias
                        ].label,
                    },
                },
                "head": {
                    "morph_alias": members["head"].morph_alias,
                    "value": members["head"].value,
                    "rule": {
                        "morph_id": allowlist[
                            members["head"].morph_alias
                        ].morph_id,
                        "minimum": allowlist[
                            members["head"].morph_alias
                        ].minimum,
                        "maximum": allowlist[
                            members["head"].morph_alias
                        ].maximum,
                        "label": allowlist[
                            members["head"].morph_alias
                        ].label,
                    },
                },
            }
            definition_digest = hashlib.sha256(
                json.dumps(
                    definition,
                    ensure_ascii=True,
                    allow_nan=False,
                    separators=(",", ":"),
                    sort_keys=True,
                ).encode("utf-8")
            ).hexdigest()
            linked_presets[preset_alias] = LinkedPreset(
                required_character_signature=signature,
                label=label,
                body=members["body"],
                head=members["head"],
                definition_digest=definition_digest,
            )

        return cls(
            enabled=enabled,
            queue_root=queue_root,
            save_root=save_root,
            bridge_token=bridge_token.lower(),
            request_timeout_seconds=request_timeout,
            poll_interval_seconds=poll_interval,
            max_message_bytes=max_message_bytes,
            morph_allowlist=allowlist,
            linked_presets=linked_presets,
            allowed_storage_root=allowed_root,
        )


def _bounded_number(value: Any, name: str, minimum: float, maximum: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise BridgeError("config_invalid", f"{name} must be numeric.")
    result = float(value)
    if not math.isfinite(result) or not minimum <= result <= maximum:
        raise BridgeError(
            "config_invalid", f"{name} must be between {minimum} and {maximum}."
        )
    return result


def confined_path(
    value: Any,
    root: Path,
    label: str,
    *,
    allowed_storage_root: Path = DEFAULT_ALLOWED_STORAGE_ROOT,
) -> Path:
    try:
        return secure_child(
            value,
            root,
            storage_root=allowed_storage_root,
            label=label,
        )
    except WindowsSecurityError as exc:
        raise BridgeError("path_invalid", str(exc)) from exc


def _runtime_directories(config: BridgeConfig) -> tuple[Path, ...]:
    return (
        config.queue_root,
        config.save_root,
        *(config.queue_root / name for name in (
            "requests",
            "processing",
            "responses",
            "completed",
            "quarantine",
            "status",
        )),
    )


def _require_private_runtime_layout(
    config_path: Path,
    config: BridgeConfig,
) -> None:
    try:
        checked_config = secure_child(
            config_path,
            config.allowed_storage_root,
            storage_root=config.allowed_storage_root,
            label="config file",
        )
        require_private_windows_acl(
            config.allowed_storage_root,
            require_protected=True,
        )
        require_fixed_ntfs_storage(config.allowed_storage_root)
        require_private_windows_acl(checked_config, single_link=True)
        for directory in _runtime_directories(config):
            checked = secure_storage_path(
                directory,
                storage_root=config.allowed_storage_root,
                label="runtime directory",
            )
            require_private_windows_acl(checked)
    except WindowsSecurityError as exc:
        raise BridgeError("storage_security_invalid", str(exc)) from exc


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def format_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_utc(value: Any, label: str) -> datetime:
    if not isinstance(value, str) or len(value) > 40:
        raise BridgeError("message_invalid", f"{label} must be an ISO UTC timestamp.")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise BridgeError("message_invalid", f"{label} is not a valid timestamp.") from exc
    if parsed.tzinfo is None:
        raise BridgeError("message_invalid", f"{label} must include a timezone.")
    return parsed.astimezone(timezone.utc)


def validate_version_name(value: Any) -> str:
    if not isinstance(value, str) or not VERSION_NAME_RE.fullmatch(value):
        raise BridgeError(
            "version_name_invalid",
            "version_name must use 1-64 letters, digits, dots, underscores, or hyphens.",
        )
    if value in {".", ".."} or value.lower().endswith(".ccproject"):
        raise BridgeError(
            "version_name_invalid",
            "Provide only the version name; .ccProject is added by the bridge.",
        )
    return value


def validate_payload(operation: str, payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise BridgeError("message_invalid", "payload must be an object.")
    if operation == "inspect_active_character":
        expected: set[str] = set()
    elif operation == "list_active_character_morphs":
        expected = {"category", "offset", "limit"}
    elif operation == "set_approved_morph":
        expected = {
            "expected_character_id",
            "expected_project_identity",
            "morph_alias",
            "value",
        }
    elif operation == "apply_approved_linked_preset":
        expected = {
            "expected_character_id",
            "expected_project_identity",
            "preset_alias",
            "expected_preset_digest",
        }
    elif operation == "save_project_as":
        expected = {"expected_project_identity", "version_name"}
    else:
        raise BridgeError("operation_denied", "Operation is not allowlisted.")
    if set(payload) != expected:
        raise BridgeError(
            "message_invalid",
            f"Payload fields for {operation} must be exactly {sorted(expected)}.",
        )

    if operation == "list_active_character_morphs":
        category = payload["category"]
        offset = payload["offset"]
        limit = payload["limit"]
        if not isinstance(category, str) or len(category) > 160:
            raise BridgeError("message_invalid", "category is invalid.")
        if isinstance(offset, bool) or not isinstance(offset, int) or not 0 <= offset <= 10000:
            raise BridgeError("message_invalid", "offset must be from 0 through 10000.")
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 250:
            raise BridgeError("message_invalid", "limit must be from 1 through 250.")
    elif operation in {"set_approved_morph", "apply_approved_linked_preset"}:
        expected_character_id = payload["expected_character_id"]
        expected_project_identity = payload["expected_project_identity"]
        if (
            not isinstance(expected_character_id, str)
            or not OBJECT_ID_RE.fullmatch(expected_character_id)
        ):
            raise BridgeError("message_invalid", "expected_character_id is invalid.")
        if (
            not isinstance(expected_project_identity, str)
            or not PROJECT_IDENTITY_RE.fullmatch(expected_project_identity)
        ):
            raise BridgeError(
                "message_invalid", "expected_project_identity is invalid."
            )
        alias_field = (
            "morph_alias"
            if operation == "set_approved_morph"
            else "preset_alias"
        )
        alias = payload[alias_field]
        if not isinstance(alias, str) or not VERSION_NAME_RE.fullmatch(alias):
            raise BridgeError(
                "message_invalid",
                f"{alias_field} is invalid.",
            )
        if operation == "set_approved_morph":
            value = payload["value"]
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(float(value))
            ):
                raise BridgeError(
                    "message_invalid",
                    "value must be a finite number.",
                )
        else:
            preset_digest = payload["expected_preset_digest"]
            if (
                not isinstance(preset_digest, str)
                or not PROJECT_IDENTITY_RE.fullmatch(preset_digest)
            ):
                raise BridgeError(
                    "message_invalid",
                    "expected_preset_digest is invalid.",
                )
    elif operation == "save_project_as":
        project_identity = payload["expected_project_identity"]
        if (
            not isinstance(project_identity, str)
            or not PROJECT_IDENTITY_RE.fullmatch(project_identity)
        ):
            raise BridgeError(
                "message_invalid", "expected_project_identity is invalid."
            )
        validate_version_name(payload["version_name"])
    return dict(payload)


def build_request(
    config: BridgeConfig,
    operation: str,
    payload: Mapping[str, Any],
    *,
    now: datetime | None = None,
    request_id: str | None = None,
) -> dict[str, Any]:
    if operation not in ALLOWED_OPERATIONS:
        raise BridgeError("operation_denied", "Operation is not allowlisted.")
    payload_dict = validate_payload(operation, dict(payload))
    current = now or utc_now()
    identifier = request_id or str(uuid.uuid4())
    if not REQUEST_ID_RE.fullmatch(identifier):
        raise BridgeError("message_invalid", "request_id must be a UUIDv4.")
    request = {
        "protocol_version": PROTOCOL_VERSION,
        "request_id": identifier,
        "operation": operation,
        "created_utc": format_utc(current),
        "expires_utc": format_utc(
            current + timedelta(seconds=config.request_timeout_seconds)
        ),
        "payload": payload_dict,
    }
    request["request_mac"] = message_mac(request, config.bridge_token)
    return request


def validate_request(
    message: Any,
    config: BridgeConfig,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    if not isinstance(message, dict) or set(message) != REQUEST_FIELDS:
        raise BridgeError("message_invalid", "Request envelope fields are invalid.")
    if message["protocol_version"] != PROTOCOL_VERSION:
        raise BridgeError("protocol_mismatch", "Request protocol version is unsupported.")
    identifier = message["request_id"]
    if not isinstance(identifier, str) or not REQUEST_ID_RE.fullmatch(identifier):
        raise BridgeError("message_invalid", "request_id must be a UUIDv4.")
    operation = message["operation"]
    if operation not in ALLOWED_OPERATIONS:
        raise BridgeError("operation_denied", "Operation is not allowlisted.")
    request_mac = message["request_mac"]
    unsigned_request = dict(message)
    unsigned_request.pop("request_mac", None)
    expected_mac = message_mac(unsigned_request, config.bridge_token)
    if (
        not isinstance(request_mac, str)
        or not hmac.compare_digest(request_mac.lower(), expected_mac)
    ):
        raise BridgeError("authentication_failed", "Request authentication failed.")
    created = parse_utc(message["created_utc"], "created_utc")
    expires = parse_utc(message["expires_utc"], "expires_utc")
    current = now or utc_now()
    if expires <= created or expires - created > timedelta(seconds=31):
        raise BridgeError("message_invalid", "Request lifetime is invalid.")
    if current > expires:
        raise BridgeError("request_expired", "Request expired before CC5 processed it.")
    if created - current > timedelta(seconds=5):
        raise BridgeError("message_invalid", "Request creation time is in the future.")
    validate_payload(operation, message["payload"])
    return dict(message)


def validate_response(
    message: Any,
    request: Mapping[str, Any],
    config: BridgeConfig,
) -> dict[str, Any]:
    if not isinstance(message, dict) or set(message) != RESPONSE_FIELDS:
        raise BridgeError("response_invalid", "Response envelope fields are invalid.")
    if message["protocol_version"] != PROTOCOL_VERSION:
        raise BridgeError("protocol_mismatch", "Response protocol version is unsupported.")
    if message["request_id"] != request["request_id"]:
        raise BridgeError("response_invalid", "Response request_id does not match.")
    if message["operation"] != request["operation"]:
        raise BridgeError("response_invalid", "Response operation does not match.")
    response_mac = message["response_mac"]
    unsigned_response = dict(message)
    unsigned_response.pop("response_mac", None)
    expected_mac = message_mac(unsigned_response, config.bridge_token)
    if (
        not isinstance(response_mac, str)
        or not hmac.compare_digest(response_mac.lower(), expected_mac)
    ):
        raise BridgeError(
            "authentication_failed", "Response authentication failed."
        )
    if not isinstance(message["ok"], bool):
        raise BridgeError("response_invalid", "Response ok field is invalid.")
    parse_utc(message["completed_utc"], "completed_utc")
    if message["ok"]:
        if not isinstance(message["result"], dict) or message["error"] is not None:
            raise BridgeError("response_invalid", "Successful response body is invalid.")
    else:
        error = message["error"]
        if (
            message["result"] is not None
            or not isinstance(error, dict)
            or set(error) != {"code", "message"}
            or not isinstance(error["code"], str)
            or not isinstance(error["message"], str)
        ):
            raise BridgeError("response_invalid", "Failure response body is invalid.")
    return dict(message)


def message_mac(message: Mapping[str, Any], token: str) -> str:
    encoded = json.dumps(
        message,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hmac.new(bytes.fromhex(token), encoded, hashlib.sha256).hexdigest()


def read_json_limited(path: Path, max_bytes: int) -> Any:
    try:
        size = path.stat().st_size
    except FileNotFoundError as exc:
        raise BridgeError("file_missing", f"Required file does not exist: {path}") from exc
    if size > max_bytes:
        raise BridgeError("message_too_large", f"JSON file exceeds {max_bytes} bytes.")
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise BridgeError("json_invalid", f"Could not read valid JSON from {path}.") from exc


def atomic_write_json(path: Path, value: Mapping[str, Any], max_bytes: int) -> None:
    encoded = (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        + "\n"
    ).encode("utf-8")
    if len(encoded) > max_bytes:
        raise BridgeError("message_too_large", f"JSON message exceeds {max_bytes} bytes.")
    if not path.parent.is_dir():
        raise BridgeError(
            "storage_missing",
            "A required private bridge directory is missing.",
        )
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("xb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(str(temporary), str(path))
    finally:
        if temporary.exists():
            temporary.unlink()


class QueueBridgeClient:
    """Synchronous request/response client for FastMCP tool handlers."""

    def __init__(self, config: BridgeConfig):
        self.config = config

    @property
    def requests_dir(self) -> Path:
        return confined_path(
            self.config.queue_root / "requests",
            self.config.queue_root,
            "requests directory",
            allowed_storage_root=self.config.allowed_storage_root,
        )

    @property
    def responses_dir(self) -> Path:
        return confined_path(
            self.config.queue_root / "responses",
            self.config.queue_root,
            "responses directory",
            allowed_storage_root=self.config.allowed_storage_root,
        )

    @property
    def status_file(self) -> Path:
        status_dir = confined_path(
            self.config.queue_root / "status",
            self.config.queue_root,
            "status directory",
            allowed_storage_root=self.config.allowed_storage_root,
        )
        return status_dir / "cc5_bridge_status.json"

    def require_enabled(self) -> None:
        if not self.config.enabled:
            raise BridgeError(
                "bridge_disabled", "The CC5 bridge is disabled in its local config."
            )
        _require_private_runtime_layout(DEFAULT_CONFIG_PATH, self.config)

    def read_status(self) -> dict[str, Any]:
        self.require_enabled()
        status = read_json_limited(
            self.status_file,
            self.config.max_message_bytes,
        )
        if not isinstance(status, dict):
            raise BridgeError("status_invalid", "CC5 status is not a JSON object.")
        status_mac = status.get("status_mac")
        unsigned_status = dict(status)
        unsigned_status.pop("status_mac", None)
        expected_mac = message_mac(unsigned_status, self.config.bridge_token)
        if (
            not isinstance(status_mac, str)
            or not hmac.compare_digest(status_mac.lower(), expected_mac)
        ):
            raise BridgeError(
                "authentication_failed", "CC5 status authentication failed."
            )
        safe_status = {
            key: status.get(key)
            for key in (
                "protocol_version",
                "state",
                "heartbeat_utc",
                "product_name",
                "product_version",
                "api_version",
                "bridge_instance_id",
                "project_epoch",
                "capabilities",
                "last_error",
                "requests_processed",
            )
        }
        heartbeat = parse_utc(safe_status["heartbeat_utc"], "heartbeat_utc")
        age = max(0.0, (utc_now() - heartbeat).total_seconds())
        safe_status["heartbeat_age_seconds"] = round(age, 3)
        safe_status["live"] = (
            safe_status["protocol_version"] == PROTOCOL_VERSION
            and safe_status["state"] == "running"
            and age <= 3.0
        )
        return safe_status

    def call(self, operation: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        self.require_enabled()
        request = build_request(self.config, operation, payload)
        request_id = request["request_id"]
        request_path = self.requests_dir / f"{request_id}.request.json"
        response_path = self.responses_dir / f"{request_id}.response.json"
        atomic_write_json(
            request_path,
            request,
            self.config.max_message_bytes,
        )
        deadline = time.monotonic() + self.config.request_timeout_seconds
        while time.monotonic() < deadline:
            if response_path.is_file():
                response = read_json_limited(
                    response_path,
                    self.config.max_message_bytes,
                )
                validated = validate_response(response, request, self.config)
                if not validated["ok"]:
                    error = validated["error"]
                    raise BridgeError(error["code"], error["message"])
                return validated["result"]
            time.sleep(self.config.poll_interval_seconds)
        raise BridgeError(
            "cc5_timeout",
            "CC5 did not answer before the local request deadline.",
        )
