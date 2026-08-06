"""Python 3.8-compatible validation and queue helpers for CC5.

There are deliberately no network, subprocess, dynamic-import, or code
execution facilities in this module.
"""

import hmac
import hashlib
import json
import math
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

try:
    from .windows_security import (
        FIXED_STORAGE_ROOT,
        WindowsSecurityError,
        publish_file_no_replace,
        require_fixed_ntfs_storage,
        require_private_windows_acl,
        secure_child,
        secure_storage_path,
    )
except ImportError:
    from windows_security import (
        FIXED_STORAGE_ROOT,
        WindowsSecurityError,
        publish_file_no_replace,
        require_fixed_ntfs_storage,
        require_private_windows_acl,
        secure_child,
        secure_storage_path,
    )


PROTOCOL_VERSION = "1.2"
DEFAULT_CONFIG_PATH = Path(
    r"D:\RedMMOTitanWindowsData\CC5MCPBridge\config.json"
)
ALLOWED_STORAGE_ROOT = FIXED_STORAGE_ROOT
TOKEN_RE = re.compile(r"^[0-9a-fA-F]{64}$")
REQUEST_ID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)
ALIAS_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
MORPH_ID_RE = re.compile(r"^[A-Za-z0-9_.:/() +\-]{1,160}$")
OBJECT_ID_RE = re.compile(r"^[0-9]{1,20}$")
PROJECT_IDENTITY_RE = re.compile(r"^[0-9a-f]{64}$")
REQUEST_FIELDS = {
    "protocol_version",
    "request_id",
    "operation",
    "created_utc",
    "expires_utc",
    "payload",
    "request_mac",
}
ALLOWED_OPERATIONS = {
    "inspect_active_character",
    "list_active_character_morphs",
    "set_approved_morph",
    "apply_approved_linked_preset",
    "save_project_as",
}


class BridgeValidationError(Exception):
    def __init__(self, code, message):
        Exception.__init__(self, message)
        self.code = code
        self.message = message


def _storage_path(value, label, allow_root=False):
    try:
        return secure_storage_path(
            value,
            storage_root=ALLOWED_STORAGE_ROOT,
            label=label,
            allow_root=allow_root,
        )
    except WindowsSecurityError as exc:
        raise BridgeValidationError("path_invalid", str(exc))


def _confined_path(value, root, label):
    try:
        return secure_child(
            value,
            root,
            storage_root=ALLOWED_STORAGE_ROOT,
            label=label,
        )
    except WindowsSecurityError as exc:
        raise BridgeValidationError("path_invalid", str(exc))


def _runtime_directories(config):
    return (
        config["queue_root"],
        config["save_root"],
    ) + tuple(
        config["queue_root"] / name
        for name in (
            "requests",
            "processing",
            "responses",
            "completed",
            "quarantine",
            "status",
        )
    )


def require_private_runtime_layout(config, config_path=DEFAULT_CONFIG_PATH):
    try:
        checked_config = secure_child(
            config_path,
            ALLOWED_STORAGE_ROOT,
            storage_root=ALLOWED_STORAGE_ROOT,
            label="config file",
        )
        require_private_windows_acl(
            ALLOWED_STORAGE_ROOT,
            require_protected=True,
        )
        require_fixed_ntfs_storage(ALLOWED_STORAGE_ROOT)
        require_private_windows_acl(checked_config, single_link=True)
        for directory in _runtime_directories(config):
            checked = secure_storage_path(
                directory,
                storage_root=ALLOWED_STORAGE_ROOT,
                label="runtime directory",
            )
            require_private_windows_acl(checked)
    except WindowsSecurityError as exc:
        raise BridgeValidationError("storage_security_invalid", str(exc))


def _finite_number(value, label, minimum, maximum):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise BridgeValidationError(
            "config_invalid", "%s must be numeric." % label
        )
    result = float(value)
    if not math.isfinite(result) or not minimum <= result <= maximum:
        raise BridgeValidationError(
            "config_invalid",
            "%s must be between %s and %s." % (label, minimum, maximum),
        )
    return result


def read_json_limited(path, max_bytes):
    try:
        size = path.stat().st_size
    except FileNotFoundError:
        raise BridgeValidationError(
            "file_missing", "Required bridge file does not exist."
        )
    if size > max_bytes:
        raise BridgeValidationError(
            "message_too_large", "JSON file exceeds the configured size limit."
        )
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, UnicodeError, ValueError):
        raise BridgeValidationError("json_invalid", "Bridge JSON is invalid.")


def atomic_write_json(path, value, max_bytes):
    encoded = (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        + "\n"
    ).encode("utf-8")
    if len(encoded) > max_bytes:
        raise BridgeValidationError(
            "message_too_large", "JSON message exceeds the configured size limit."
        )
    if not path.parent.is_dir():
        raise BridgeValidationError(
            "storage_missing",
            "A required private bridge directory is missing.",
        )
    temporary = path.with_name(
        ".%s.%s.tmp" % (path.name, uuid.uuid4().hex)
    )
    try:
        with temporary.open("xb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(str(temporary), str(path))
    finally:
        if temporary.exists():
            temporary.unlink()


def load_config(path=DEFAULT_CONFIG_PATH):
    config_path = _confined_path(path, ALLOWED_STORAGE_ROOT, "config file")
    raw = read_json_limited(config_path, 128 * 1024)
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
    if not isinstance(raw, dict) or set(raw) != expected:
        raise BridgeValidationError(
            "config_invalid", "Bridge config fields are invalid."
        )
    if not isinstance(raw["enabled"], bool):
        raise BridgeValidationError(
            "config_invalid", "enabled must be true or false."
        )
    queue_root = _storage_path(raw["queue_root"], "queue_root")
    save_root = _storage_path(raw["save_root"], "save_root")
    if queue_root == save_root:
        raise BridgeValidationError(
            "config_invalid", "queue_root and save_root must differ."
        )
    token = raw["bridge_token"]
    if not isinstance(token, str) or not TOKEN_RE.fullmatch(token):
        raise BridgeValidationError(
            "config_invalid",
            "bridge_token must be exactly 64 hexadecimal characters.",
        )
    request_timeout = _finite_number(
        raw["request_timeout_seconds"],
        "request_timeout_seconds",
        1.0,
        30.0,
    )
    poll_interval = _finite_number(
        raw["poll_interval_seconds"],
        "poll_interval_seconds",
        0.05,
        1.0,
    )
    max_bytes = raw["max_message_bytes"]
    if (
        isinstance(max_bytes, bool)
        or not isinstance(max_bytes, int)
        or not 4096 <= max_bytes <= 262144
    ):
        raise BridgeValidationError(
            "config_invalid", "max_message_bytes is outside the allowed range."
        )
    allowlist = raw["morph_allowlist"]
    if not isinstance(allowlist, dict) or len(allowlist) > 256:
        raise BridgeValidationError(
            "config_invalid", "morph_allowlist must contain at most 256 rules."
        )
    validated_rules = {}
    for alias, rule in allowlist.items():
        if not isinstance(alias, str) or not ALIAS_RE.fullmatch(alias):
            raise BridgeValidationError(
                "config_invalid", "A morph alias is invalid."
            )
        if not isinstance(rule, dict) or set(rule) != {
            "morph_id",
            "minimum",
            "maximum",
            "label",
        }:
            raise BridgeValidationError(
                "config_invalid", "Morph rule %s has invalid fields." % alias
            )
        morph_id = rule["morph_id"]
        label = rule["label"]
        if not isinstance(morph_id, str) or not MORPH_ID_RE.fullmatch(morph_id):
            raise BridgeValidationError(
                "config_invalid", "Morph rule %s has an invalid ID." % alias
            )
        if not isinstance(label, str) or not 1 <= len(label) <= 160:
            raise BridgeValidationError(
                "config_invalid", "Morph rule %s has an invalid label." % alias
            )
        minimum = _finite_number(
            rule["minimum"], "%s.minimum" % alias, -1000.0, 1000.0
        )
        maximum = _finite_number(
            rule["maximum"], "%s.maximum" % alias, -1000.0, 1000.0
        )
        if minimum >= maximum:
            raise BridgeValidationError(
                "config_invalid",
                "Morph rule %s has an inverted range." % alias,
            )
        validated_rules[alias] = {
            "morph_id": morph_id,
            "minimum": minimum,
            "maximum": maximum,
            "label": label,
        }
    presets = raw["linked_presets"]
    if not isinstance(presets, dict) or len(presets) > 64:
        raise BridgeValidationError(
            "config_invalid", "linked_presets must contain at most 64 presets."
        )
    validated_presets = {}
    for preset_alias, preset in presets.items():
        if (
            not isinstance(preset_alias, str)
            or not ALIAS_RE.fullmatch(preset_alias)
        ):
            raise BridgeValidationError(
                "config_invalid", "A linked preset alias is invalid."
            )
        if not isinstance(preset, dict) or set(preset) != {
            "required_character_signature",
            "label",
            "body",
            "head",
        }:
            raise BridgeValidationError(
                "config_invalid",
                "Linked preset %s has invalid fields." % preset_alias,
            )
        signature = preset["required_character_signature"]
        label = preset["label"]
        if (
            not isinstance(signature, str)
            or not PROJECT_IDENTITY_RE.fullmatch(signature)
        ):
            raise BridgeValidationError(
                "config_invalid",
                "Linked preset %s has an invalid character signature."
                % preset_alias,
            )
        if not isinstance(label, str) or not 1 <= len(label) <= 160:
            raise BridgeValidationError(
                "config_invalid",
                "Linked preset %s has an invalid label." % preset_alias,
            )
        validated_members = {}
        for role in ("body", "head"):
            member = preset[role]
            if not isinstance(member, dict) or set(member) != {
                "morph_alias",
                "value",
            }:
                raise BridgeValidationError(
                    "config_invalid",
                    "Linked preset %s %s member is invalid."
                    % (preset_alias, role),
                )
            morph_alias = member["morph_alias"]
            if (
                not isinstance(morph_alias, str)
                or not ALIAS_RE.fullmatch(morph_alias)
                or morph_alias not in validated_rules
            ):
                raise BridgeValidationError(
                    "config_invalid",
                    "Linked preset %s %s morph is not allowlisted."
                    % (preset_alias, role),
                )
            rule = validated_rules[morph_alias]
            value = _finite_number(
                member["value"],
                "%s.%s.value" % (preset_alias, role),
                rule["minimum"],
                rule["maximum"],
            )
            validated_members[role] = {
                "morph_alias": morph_alias,
                "value": value,
            }
        if (
            validated_members["body"]["morph_alias"]
            == validated_members["head"]["morph_alias"]
        ):
            raise BridgeValidationError(
                "config_invalid",
                "Linked preset %s must use distinct body and head morphs."
                % preset_alias,
            )
        if (
            validated_rules[
                validated_members["body"]["morph_alias"]
            ]["morph_id"]
            == validated_rules[
                validated_members["head"]["morph_alias"]
            ]["morph_id"]
        ):
            raise BridgeValidationError(
                "config_invalid",
                "Linked preset %s resolves to one morph ID twice."
                % preset_alias,
            )
        definition = {
            "preset_alias": preset_alias,
            "required_character_signature": signature,
            "label": label,
            "body": {
                "morph_alias": validated_members["body"]["morph_alias"],
                "value": validated_members["body"]["value"],
                "rule": validated_rules[
                    validated_members["body"]["morph_alias"]
                ],
            },
            "head": {
                "morph_alias": validated_members["head"]["morph_alias"],
                "value": validated_members["head"]["value"],
                "rule": validated_rules[
                    validated_members["head"]["morph_alias"]
                ],
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
        validated_presets[preset_alias] = {
            "required_character_signature": signature,
            "label": label,
            "body": validated_members["body"],
            "head": validated_members["head"],
            "definition_digest": definition_digest,
        }
    config = {
        "enabled": raw["enabled"],
        "queue_root": queue_root,
        "save_root": save_root,
        "bridge_token": token.lower(),
        "request_timeout_seconds": request_timeout,
        "poll_interval_seconds": poll_interval,
        "max_message_bytes": max_bytes,
        "morph_allowlist": validated_rules,
        "linked_presets": validated_presets,
    }
    if config["enabled"]:
        require_private_runtime_layout(config, config_path)
    return config


def _parse_utc(value, label):
    if not isinstance(value, str) or len(value) > 40:
        raise BridgeValidationError(
            "message_invalid", "%s is not a UTC timestamp." % label
        )
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise BridgeValidationError(
            "message_invalid", "%s is not a valid timestamp." % label
        )
    if parsed.tzinfo is None:
        raise BridgeValidationError(
            "message_invalid", "%s must include a timezone." % label
        )
    return parsed.astimezone(timezone.utc)


def _validate_payload(operation, payload):
    if not isinstance(payload, dict):
        raise BridgeValidationError(
            "message_invalid", "payload must be an object."
        )
    if operation == "inspect_active_character":
        expected = set()
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
        raise BridgeValidationError(
            "operation_denied", "Operation is not allowlisted."
        )
    if set(payload) != expected:
        raise BridgeValidationError(
            "message_invalid", "Payload fields do not match the operation."
        )
    if operation == "list_active_character_morphs":
        if not isinstance(payload["category"], str) or len(payload["category"]) > 160:
            raise BridgeValidationError("message_invalid", "category is invalid.")
        if (
            isinstance(payload["offset"], bool)
            or not isinstance(payload["offset"], int)
            or not 0 <= payload["offset"] <= 10000
        ):
            raise BridgeValidationError("message_invalid", "offset is invalid.")
        if (
            isinstance(payload["limit"], bool)
            or not isinstance(payload["limit"], int)
            or not 1 <= payload["limit"] <= 250
        ):
            raise BridgeValidationError("message_invalid", "limit is invalid.")
    elif operation in {
        "set_approved_morph",
        "apply_approved_linked_preset",
    }:
        if (
            not isinstance(payload["expected_character_id"], str)
            or not OBJECT_ID_RE.fullmatch(payload["expected_character_id"])
        ):
            raise BridgeValidationError(
                "message_invalid", "expected_character_id is invalid."
            )
        if (
            not isinstance(payload["expected_project_identity"], str)
            or not PROJECT_IDENTITY_RE.fullmatch(
                payload["expected_project_identity"]
            )
        ):
            raise BridgeValidationError(
                "message_invalid", "expected_project_identity is invalid."
            )
        alias_field = (
            "morph_alias"
            if operation == "set_approved_morph"
            else "preset_alias"
        )
        if (
            not isinstance(payload[alias_field], str)
            or not ALIAS_RE.fullmatch(payload[alias_field])
        ):
            raise BridgeValidationError(
                "message_invalid", "%s is invalid." % alias_field
            )
        if operation == "set_approved_morph":
            value = payload["value"]
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(float(value))
            ):
                raise BridgeValidationError(
                    "message_invalid", "value is invalid."
                )
        else:
            preset_digest = payload["expected_preset_digest"]
            if (
                not isinstance(preset_digest, str)
                or not PROJECT_IDENTITY_RE.fullmatch(preset_digest)
            ):
                raise BridgeValidationError(
                    "message_invalid",
                    "expected_preset_digest is invalid.",
                )
    elif operation == "save_project_as":
        if (
            not isinstance(payload["expected_project_identity"], str)
            or not PROJECT_IDENTITY_RE.fullmatch(
                payload["expected_project_identity"]
            )
        ):
            raise BridgeValidationError(
                "message_invalid", "expected_project_identity is invalid."
            )
        validate_version_name(payload["version_name"])


def validate_request(message, config, now=None):
    if not isinstance(message, dict) or set(message) != REQUEST_FIELDS:
        raise BridgeValidationError(
            "message_invalid", "Request envelope fields are invalid."
        )
    if message["protocol_version"] != PROTOCOL_VERSION:
        raise BridgeValidationError(
            "protocol_mismatch", "Request protocol version is unsupported."
        )
    request_id = message["request_id"]
    if not isinstance(request_id, str) or not REQUEST_ID_RE.fullmatch(request_id):
        raise BridgeValidationError(
            "message_invalid", "request_id must be a UUIDv4."
        )
    operation = message["operation"]
    if operation not in ALLOWED_OPERATIONS:
        raise BridgeValidationError(
            "operation_denied", "Operation is not allowlisted."
        )
    request_mac = message["request_mac"]
    unsigned_request = dict(message)
    unsigned_request.pop("request_mac", None)
    expected_mac = message_mac(unsigned_request, config["bridge_token"])
    if (
        not isinstance(request_mac, str)
        or not hmac.compare_digest(request_mac.lower(), expected_mac)
    ):
        raise BridgeValidationError(
            "authentication_failed", "Request authentication failed."
        )
    created = _parse_utc(message["created_utc"], "created_utc")
    expires = _parse_utc(message["expires_utc"], "expires_utc")
    current = now or datetime.now(timezone.utc)
    lifetime = (expires - created).total_seconds()
    if lifetime <= 0 or lifetime > 31:
        raise BridgeValidationError(
            "message_invalid", "Request lifetime is invalid."
        )
    if current > expires:
        raise BridgeValidationError(
            "request_expired", "Request expired before CC5 processed it."
        )
    if (created - current).total_seconds() > 5:
        raise BridgeValidationError(
            "message_invalid", "Request creation time is in the future."
        )
    _validate_payload(operation, message["payload"])
    return message


def validate_version_name(value):
    if (
        not isinstance(value, str)
        or not ALIAS_RE.fullmatch(value)
        or value in {".", ".."}
        or value.lower().endswith(".ccproject")
    ):
        raise BridgeValidationError(
            "version_name_invalid",
            "version_name must be a simple 1-64 character name without an extension.",
        )
    return value


def safe_save_target(config, version_name):
    name = validate_version_name(version_name)
    target = _confined_path(
        str(config["save_root"] / (name + ".ccProject")),
        config["save_root"],
        "save target",
    )
    if target.exists():
        raise BridgeValidationError(
            "save_target_exists", "The requested project version already exists."
        )
    return target


def unique_save_staging_target(config):
    return _confined_path(
        str(
            config["save_root"]
            / (".cc5mcp-" + uuid.uuid4().hex + ".ccProject")
        ),
        config["save_root"],
        "save staging target",
    )


def cleanup_owned_file(path, owned):
    if not owned:
        return False
    try:
        if path.exists():
            path.unlink()
            return True
    except OSError:
        return False
    return False


def interval_due(now_value, last_value, interval_seconds):
    return last_value <= 0.0 or now_value - last_value >= interval_seconds


def format_utc(value=None):
    current = value or datetime.now(timezone.utc)
    return current.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def message_mac(message, token):
    encoded = json.dumps(
        message,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hmac.new(
        bytes.fromhex(token),
        encoded,
        hashlib.sha256,
    ).hexdigest()


def success_response(request, result, token):
    response = {
        "protocol_version": PROTOCOL_VERSION,
        "request_id": request["request_id"],
        "operation": request["operation"],
        "ok": True,
        "completed_utc": format_utc(),
        "result": result,
        "error": None,
    }
    response["response_mac"] = message_mac(response, token)
    return response


def failure_response(request_id, operation, code, message, token):
    response = {
        "protocol_version": PROTOCOL_VERSION,
        "request_id": request_id,
        "operation": operation,
        "ok": False,
        "completed_utc": format_utc(),
        "result": None,
        "error": {"code": code, "message": message},
    }
    response["response_mac"] = message_mac(response, token)
    return response
