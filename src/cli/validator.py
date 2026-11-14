#!/usr/bin/env python3
"""Stateless TOML configuration schema validator for ``dyndns validate``.

Validates ``config.toml`` syntax, types, value ranges, and URL schemes without
initializing SQLite connections or modifying runtime state.

Author: Manuel Ziel
License: MIT
"""

################################################################################
# IMPORTS & DEPENDENCIES
################################################################################

import os
import sys
import tomllib
from typing import Any

from src.cli.constants import ValidationLimits
from src.cli.helpers.output import print_error, print_success
from src.core.constants import UpdateMethod

################################################################################
# VALIDATION CONSTANTS
################################################################################

_VALID_LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL", "NOTSET")
_VALID_URL_PREFIXES = ("https://", "http://")

################################################################################
# PURE SCHEMA VALIDATION HELPERS
################################################################################


def _is_strict_int(value: Any) -> bool:
    """Return True when ``value`` is an ``int`` and not a ``bool``.

    Args:
        value: Value to test.

    Returns:
        True if ``value`` is a non-boolean integer.
    """
    return isinstance(value, int) and not isinstance(value, bool)


def _check_positive_int(section: str, key: str, data: dict[str, Any], errors: list[str]) -> None:
    """Append an error if ``data[key]`` exists and is not a positive integer.

    Args:
        section: TOML section name.
        key: Key within ``data``.
        data: Parsed TOML section dictionary.
        errors: Mutable list of validation error strings.
    """
    if key in data and (not _is_strict_int(data[key]) or data[key] <= 0):
        errors.append(f"[{section}].{key} must be a positive integer")


def _check_bool(section: str, key: str, data: dict[str, Any], errors: list[str]) -> None:
    """Append an error if ``data[key]`` exists and is not a boolean.

    Args:
        section: TOML section name.
        key: Key within ``data``.
        data: Parsed TOML section dictionary.
        errors: Mutable list of validation error strings.
    """
    if key in data and not isinstance(data[key], bool):
        errors.append(f"[{section}].{key} must be a boolean")


def _check_url(section: str, key: str, data: dict[str, Any], errors: list[str]) -> None:
    """Append an error if ``data[key]`` exists and is not an HTTP(S) URL string.

    Args:
        section: TOML section name.
        key: Key within ``data``.
        data: Parsed TOML section dictionary.
        errors: Mutable list of validation error strings.
    """
    if key not in data:
        return
    val = data[key]
    if not isinstance(val, str) or not val.strip().startswith(_VALID_URL_PREFIXES):
        errors.append(f"[{section}].{key} must be a valid HTTP(S) URL string")


def _validate_debug_and_dns(raw: dict[str, Any], errors: list[str]) -> None:
    """Validate ``[debug]`` and ``[dns]`` sections of parsed TOML config.

    Args:
        raw: Root parsed TOML dictionary.
        errors: Mutable list of validation error strings.
    """
    debug = raw.get("debug", {})
    if not isinstance(debug, dict):
        errors.append("[debug] must be a TOML table")
    else:
        if "level" in debug and (
            not isinstance(debug["level"], str)
            or debug["level"].upper() not in _VALID_LOG_LEVELS
        ):
            errors.append(f"[debug].level must be one of {_VALID_LOG_LEVELS}")
        _check_bool("debug", "console_colors", debug, errors)

    dns = raw.get("dns", {})
    if not isinstance(dns, dict):
        errors.append("[dns] must be a TOML table")
    else:
        valid_methods = (UpdateMethod.DYNDNS.value, UpdateMethod.REST.value)
        if "update_method" in dns and dns["update_method"] not in valid_methods:
            errors.append(f"[dns].update_method must be one of {valid_methods}")
        if "default_ttl" in dns and (
            not _is_strict_int(dns["default_ttl"])
            or not (
                ValidationLimits.TTL_MIN
                <= dns["default_ttl"]
                <= ValidationLimits.TTL_MAX
            )
        ):
            errors.append(
                f"[dns].default_ttl must be an integer between "
                f"{ValidationLimits.TTL_MIN} and {ValidationLimits.TTL_MAX}"
            )


def _validate_network_and_api(raw: dict[str, Any], errors: list[str]) -> None:
    """Validate ``[provider_api]`` and ``[network]`` sections of parsed TOML config.

    Args:
        raw: Root parsed TOML dictionary.
        errors: Mutable list of validation error strings.
    """
    api = raw.get("provider_api", {})
    if not isinstance(api, dict):
        errors.append("[provider_api] must be a TOML table")
    else:
        _check_url("provider_api", "base_url", api, errors)
        _check_positive_int("provider_api", "timeout", api, errors)
        _check_positive_int("provider_api", "retry_attempts", api, errors)

    net = raw.get("network", {})
    if not isinstance(net, dict):
        errors.append("[network] must be a TOML table")
    else:
        _check_bool("network", "ipv4_enabled", net, errors)
        _check_bool("network", "ipv6_enabled", net, errors)
        _check_url("network", "ipv4_detection_url", net, errors)
        _check_url("network", "ipv6_detection_url", net, errors)
        _check_positive_int("network", "timeout", net, errors)
        _check_positive_int("network", "retry_attempts", net, errors)


def _validate_daemon_and_db(raw: dict[str, Any], errors: list[str]) -> None:
    """Validate ``[daemon]`` and ``[database]`` sections of parsed TOML config.

    Args:
        raw: Root parsed TOML dictionary.
        errors: Mutable list of validation error strings.
    """
    daemon = raw.get("daemon", {})
    if not isinstance(daemon, dict):
        errors.append("[daemon] must be a TOML table")
    else:
        _check_bool("daemon", "enabled", daemon, errors)
        _check_bool("daemon", "sync_checks", daemon, errors)
        _check_positive_int("daemon", "check_interval", daemon, errors)
        _check_positive_int("daemon", "retry_delay", daemon, errors)
        if "max_retries" in daemon and (
            not _is_strict_int(daemon["max_retries"]) or daemon["max_retries"] < 0
        ):
            errors.append("[daemon].max_retries must be a non-negative integer")

    db_cfg = raw.get("database", {})
    if not isinstance(db_cfg, dict):
        errors.append("[database] must be a TOML table")
    else:
        for key in ("db_path", "encryption_key_path"):
            if key in db_cfg and (
                not isinstance(db_cfg[key], str) or not db_cfg[key].strip()
            ):
                errors.append(f"[database].{key} must be a non-empty string")


################################################################################
# PUBLIC VALIDATION API
################################################################################


def validate_config_file(config_path: str) -> tuple[bool, list[str]]:
    """Validate ``config_path`` for TOML syntax and DynDNS schema compliance.

    Args:
        config_path: Filesystem path to the TOML configuration file.

    Returns:
        Tuple ``(is_valid, error_messages)``.
    """
    if not os.path.exists(config_path):
        return False, [f"Configuration file not found: {config_path}"]
    if os.path.islink(config_path):
        return False, [f"Refusing symlinked configuration file: {config_path}"]
    if not os.path.isfile(config_path):
        return False, [f"Configuration path is not a regular file: {config_path}"]

    try:
        with open(config_path, "rb") as file_handle:
            raw = tomllib.load(file_handle)
    except (tomllib.TOMLDecodeError, OSError) as exc:
        return False, [f"TOML parse error in '{config_path}': {exc}"]

    errors: list[str] = []
    _validate_debug_and_dns(raw, errors)
    _validate_network_and_api(raw, errors)
    _validate_daemon_and_db(raw, errors)
    return len(errors) == 0, errors


def run_validate_cli(config_path: str) -> int:
    """Execute CLI validation for ``config_path`` and print results.

    Args:
        config_path: Path to the TOML configuration file.

    Returns:
        Exit code ``0`` when valid, ``1`` when invalid.
    """
    is_valid, errors = validate_config_file(config_path)
    if is_valid:
        print_success(f"Configuration valid: {config_path}")
        return 0

    print_error(f"Configuration invalid: {config_path}")
    for err in errors:
        print(f"  - {err}", file=sys.stderr)
    return 1
