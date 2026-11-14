#!/usr/bin/env python3
"""Configuration manager for TOML-based application settings.

Handles loading, runtime reloading, and comment-preserving updates of TOML
configuration files with FHS 3.0 environment variable integration and database
initialization.

Typical usage:
    >>> config = ConfigManager('/app', '/etc/dyndns/config.toml')
    >>> print(config.log_level)
    'INFO'

Author: Manuel Ziel
License: MIT
"""

################################################################################
# IMPORTS & DEPENDENCIES
################################################################################

import logging
import os
import re
import tomllib
from typing import Any

from .constants import (
    AppPaths,
    DaemonDefaults,
    DNSDefaults,
    EnvKeys,
    LoggingDefaults,
    NetworkAPI,
    OwnershipDefaults,
    ProviderAPI,
)
from .database import Database
from .exceptions import ConfigError, DatabaseError, EncryptionError
from .ownership import ensure_service_ownership

################################################################################
# CONFIGURATION MANAGER CLASS
################################################################################


class ConfigManager:
    """Configuration handler for TOML settings, FHS paths, and database setup.

    Attributes:
        config: Raw configuration dictionary loaded from the TOML file.
        log_level: Configured logging verbosity level.
        console_colors: Whether colored console output is enabled.
        db: Initialized ``Database`` instance.
    """

    def __init__(
        self,
        current_dir: str,
        config_path: str,
        logger: logging.Logger | None = None,
    ) -> None:
        """Initialize configuration manager, parse TOML, and connect SQLite.

        Args:
            current_dir: Base directory path for relative path resolution.
            config_path: Absolute path to the TOML configuration file.
            logger: Optional logger instance.

        Raises:
            ConfigError: If configuration loading or database setup fails.
        """
        self.current_dir = current_dir
        self.config_path = config_path
        self.logger = logger or logging.getLogger(__name__)
        self.config = self.load_config(config_path)

        self._apply_config()
        self._init_database()

    ############################################################################
    # PUBLIC INTERFACE - Configuration Loading and Reloading
    ############################################################################

    def reload(self) -> None:
        """Reload configuration from the TOML file at runtime.

        Raises:
            ConfigError: If the configuration file cannot be reloaded.
        """
        self.config = self.load_config(self.config_path)
        self._apply_config()

    def load_config(self, path: str) -> dict[str, Any]:
        """Load and parse configuration from a TOML file with symlink & mode checks.

        Args:
            path: Path to the TOML configuration file.

        Returns:
            Parsed TOML configuration dictionary.

        Raises:
            ConfigError: If the file is a symlink, missing, unreadable, or invalid TOML.
        """
        if os.path.islink(path):
            raise ConfigError(f"Refusing to load symlinked configuration file: {path}")
        try:
            with open(path, "rb") as file_handle:
                parsed = tomllib.load(file_handle)
            self._enforce_config_permissions(path)
            return parsed
        except FileNotFoundError as exc:
            raise ConfigError(f"Configuration file not found: {path}") from exc
        except tomllib.TOMLDecodeError as exc:
            raise ConfigError(f"Invalid TOML syntax in {path}: {exc}") from exc
        except OSError as exc:
            raise ConfigError(f"Error loading configuration from {path}: {exc}") from exc

    def _enforce_config_permissions(self, path: str) -> None:
        """Restrict ``path`` permissions to ``0640`` when owned by current user or root.

        Args:
            path: Path to the TOML configuration file.
        """
        try:
            st = os.lstat(path)
            if st.st_uid == os.geteuid():
                os.chmod(path, OwnershipDefaults.FILE_MODE_GROUP_READ)
            ensure_service_ownership(
                path, mode=OwnershipDefaults.FILE_MODE_GROUP_READ, logger=self.logger
            )
        except OSError:
            pass

    ############################################################################
    # PRIVATE METHODS - Configuration Initialization
    ############################################################################

    def _apply_config(self) -> None:
        """Apply parsed TOML sections to typed instance attributes."""
        self._load_debug_config()
        self._load_api_config()
        self._load_network_config()
        self._load_dns_config()
        self._load_daemon_config()
        self._load_database_config(self.current_dir)

    def _init_database(self) -> None:
        """Initialize the SQLite ``Database`` connection pool.

        Raises:
            ConfigError: If database or encryption initialization fails.
        """
        try:
            self.db = Database(self.db_path, logger=self.logger, config=self)
        except (DatabaseError, EncryptionError, OSError) as exc:
            raise ConfigError(f"Database initialization failed: {exc}") from exc

    ############################################################################
    # PRIVATE METHODS - Configuration Section Loaders
    ############################################################################

    def _load_debug_config(self) -> None:
        """Load ``[debug]`` settings from TOML."""
        debug_cfg = self.config.get("debug", {})
        self.log_level = debug_cfg.get("level", LoggingDefaults.LEVEL)
        self.console_colors = debug_cfg.get("console_colors", LoggingDefaults.CONSOLE_COLORS)

    def _load_api_config(self) -> None:
        """Load ``[provider_api]`` settings from TOML."""
        api_cfg = self.config.get("provider_api", {})
        self.provider_api_base_url = api_cfg.get("base_url", ProviderAPI.BASE_URL)
        self.provider_api_timeout = api_cfg.get("timeout", ProviderAPI.TIMEOUT)
        self.provider_api_retry_attempts = api_cfg.get(
            "retry_attempts", ProviderAPI.RETRY_ATTEMPTS
        )

    def _load_network_config(self) -> None:
        """Load ``[network]`` settings from TOML."""
        net_cfg = self.config.get("network", {})
        self.network_ipv4_enabled = net_cfg.get("ipv4_enabled", NetworkAPI.IPV4_ENABLED)
        self.network_ipv6_enabled = net_cfg.get("ipv6_enabled", NetworkAPI.IPV6_ENABLED)
        self.network_ipv4_detection_url = net_cfg.get("ipv4_detection_url", NetworkAPI.IPV4_URL)
        self.network_ipv6_detection_url = net_cfg.get("ipv6_detection_url", NetworkAPI.IPV6_URL)
        self.network_timeout = net_cfg.get("timeout", NetworkAPI.TIMEOUT)
        self.network_retry_attempts = net_cfg.get("retry_attempts", NetworkAPI.RETRY_ATTEMPTS)

    def _load_dns_config(self) -> None:
        """Load ``[dns]`` settings from TOML."""
        dns_cfg = self.config.get("dns", {})
        self.dns_default_ttl = dns_cfg.get("default_ttl", DNSDefaults.DEFAULT_TTL)
        self.dns_update_method = dns_cfg.get("update_method", str(DNSDefaults.DEFAULT_UPDATE_METHOD))

    def _load_daemon_config(self) -> None:
        """Load ``[daemon]`` settings from TOML."""
        daemon_cfg = self.config.get("daemon", {})
        self.daemon_enabled = daemon_cfg.get("enabled", DaemonDefaults.ENABLED)
        self.daemon_check_interval = daemon_cfg.get("check_interval", DaemonDefaults.CHECK_INTERVAL)
        self.daemon_max_retries = daemon_cfg.get("max_retries", DaemonDefaults.MAX_RETRIES)
        self.daemon_retry_delay = daemon_cfg.get("retry_delay", DaemonDefaults.RETRY_DELAY)
        self.daemon_sync_checks = daemon_cfg.get("sync_checks", DaemonDefaults.SYNC_CHECKS)

    def _load_database_config(self, current_dir: str) -> None:
        """Load ``[database]`` settings with FHS-compliant path resolution.

        Args:
            current_dir: Base directory (retained for signature compatibility).
        """
        _ = current_dir
        db_cfg = self.config.get("database", {})
        data_dir = os.environ.get(EnvKeys.DATA_DIR, AppPaths.DATA_DIR)
        self.data_dir = data_dir
        db_path = db_cfg.get("db_path", AppPaths.DB_FILE)
        self.db_path = db_path if os.path.isabs(db_path) else os.path.join(data_dir, db_path)
        self.runtime_dir = os.environ.get(EnvKeys.RUNTIME_DIR, AppPaths.RUNTIME_DIR)
        key_file = db_cfg.get("encryption_key_path", AppPaths.ENCRYPTION_KEY_FILE)
        self.encryption_key_path = (
            key_file if os.path.isabs(key_file) else os.path.join(data_dir, key_file)
        )

    ############################################################################
    # PUBLIC INTERFACE - Configuration Modification
    ############################################################################

    def update_setting(self, section: str, key: str, value: Any) -> bool:
        """Update a setting in the TOML file while preserving comments and ``0640`` mode.

        Args:
            section: Target TOML section name (e.g. ``'dns'``).
            key: Setting key within ``section`` (e.g. ``'update_method'``).
            value: New value to persist.

        Returns:
            True if written and reloaded in memory, False on error.
        """
        if os.path.islink(self.config_path):
            self.logger.error(f"Refusing to modify symlinked config file: {self.config_path}")
            return False
        try:
            with open(self.config_path, "r", encoding="utf-8") as file_handle:
                lines = file_handle.readlines()
            formatted_value = self._format_toml_value(value)
            new_lines = self._update_toml_lines(lines, section, key, formatted_value)
            with open(self.config_path, "w", encoding="utf-8") as file_handle:
                file_handle.writelines(new_lines)
            self._enforce_config_permissions(self.config_path)
            self.config.setdefault(section, {})[key] = value
            self._apply_config()
            self.logger.info(f"Updated config setting {section}.{key} = {formatted_value}")
            return True
        except OSError as exc:
            self.logger.error(f"Failed to update setting {section}.{key}: {exc}")
            return False

    def _format_toml_value(self, value: Any) -> str:
        """Format a Python primitive as a safe TOML literal string.

        Args:
            value: Primitive value (``str``, ``bool``, ``int``, ``float``).

        Returns:
            TOML-formatted string literal.
        """
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, str):
            escaped = value.replace("\\", "\\\\").replace('"', '\\"')
            return f'"{escaped}"'
        return str(value)

    def _update_toml_lines(
        self, lines: list[str], section: str, key: str, formatted_value: str
    ) -> list[str]:
        """Replace or append ``key = formatted_value`` inside ``[section]``.

        Args:
            lines: Existing TOML lines.
            section: Target TOML section name.
            key: Setting key name.
            formatted_value: TOML literal string.

        Returns:
            Updated list of TOML lines.
        """
        section_header = f"[{section}]"
        in_section = False
        key_updated = False
        new_lines: list[str] = []
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("[") and stripped.endswith("]"):
                if in_section and not key_updated:
                    new_lines.append(f"{key} = {formatted_value}\n")
                    key_updated = True
                in_section = stripped == section_header
            elif in_section and re.match(rf"^{re.escape(key)}\s*=", stripped):
                line = f"{key} = {formatted_value}\n"
                key_updated = True
            new_lines.append(line)
        if in_section and not key_updated:
            new_lines.append(f"{key} = {formatted_value}\n")
        elif not key_updated:
            new_lines.append(f"\n[{section}]\n{key} = {formatted_value}\n")
        return new_lines
