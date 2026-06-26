#!/usr/bin/env python3
"""Configuration manager for TOML-based application settings.

This module handles loading and managing application configuration from TOML
files with support for environment variable integration and database setup.

Typical usage:
    >>> config = ConfigManager('/app', '/app/config.toml')
    >>> print(config.log_level)
    'INFO'

Author: Manuel Ziel
License: MIT
"""

################################################################################
# IMPORTS & DEPENDENCIES
################################################################################

# Standard Imports
import logging
import os
import tomllib
from typing import Dict, Any, Optional

# Local Imports
from .exceptions import ConfigError
from .database import Database
from .constants import (
    AppPaths,
    ProviderAPI,
    NetworkAPI,
    DaemonDefaults,
    DNSDefaults,
    LoggingDefaults
)


################################################################################
# CONFIGURATION MANAGER CLASS - TOML Configuration with Environment Integration
################################################################################

class ConfigManager:
    """Configuration handler for TOML config, database, and external services.

    Loads configuration from a TOML file and initializes database connections.
    Supports debug, API, network, DNS, daemon, and database configuration sections.

    Attributes:
        config: Raw configuration dictionary from TOML file.
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
        console_colors: Whether to use colored console output.
        db: Database instance (initialized after config load).
    """

    def __init__(self, current_dir: str, config_path: str, logger: Optional[logging.Logger] = None) -> None:
        """Initialize configuration handler and load TOML config.

        Args:
            current_dir: Base directory path for relative path resolution.
            config_path: Absolute path to TOML configuration file.
            logger: Optional logger instance. Creates default logger if None.

        Raises:
            ConfigError: If configuration file cannot be loaded or parsed.
        """
        self.logger = logger or logging.getLogger(__name__)
        self.config = self.load_config(config_path)
        
        self._load_debug_config()
        self._load_api_config()
        self._load_network_config()
        self._load_dns_config()
        self._load_daemon_config()
        self._load_database_config(current_dir)

        self._init_database()


    ################################################################################
    # PUBLIC INTERFACE - Configuration Loading and Management
    ################################################################################

    def load_config(self, path: str) -> Dict[str, Any]:
        """Load configuration from a TOML file.

        Args:
            path: Absolute path to the TOML configuration file.

        Returns:
            Dictionary containing the parsed TOML configuration.

        Raises:
            ConfigError: If file not found, invalid TOML syntax, or read error.
        """
        try:
            with open(path, "rb") as f:
                config = tomllib.load(f)
            return config
        except FileNotFoundError:
            raise ConfigError(f"Configuration file not found: {path}")
        except tomllib.TOMLDecodeError as e:
            raise ConfigError(f"Invalid TOML syntax in {path}: {e}")
        except Exception as e:
            raise ConfigError(f"Error loading configuration from {path}: {e}")


    ################################################################################
    # PRIVATE METHODS - Configuration Initialization
    ################################################################################

    def _init_database(self) -> None:
        """Initialize database connection.

        Creates a Database instance using the configured database path.

        Raises:
            ConfigError: If database initialization fails.
        """
        try:
            self.db = Database(self.db_path, logger=self.logger, config=self)
        except Exception as e:
            raise ConfigError(f"Database initialization failed: {e}")


    ################################################################################
    # PRIVATE METHODS - Configuration Section Loaders
    ################################################################################

    def _load_debug_config(self) -> None:
        """Load debug configuration settings from TOML."""
        self.log_level = self.config.get("debug", {}).get("level", LoggingDefaults.LEVEL)
        self.console_colors = self.config.get("debug", {}).get("console_colors", LoggingDefaults.CONSOLE_COLORS)


    def _load_api_config(self) -> None:
        """Load API configuration settings from TOML."""
        self.provider_api_base_url = self.config.get("provider_api", {}).get("base_url", ProviderAPI.BASE_URL)
        self.provider_api_timeout = self.config.get("provider_api", {}).get("timeout", ProviderAPI.TIMEOUT)
        self.provider_api_retry_attempts = self.config.get("provider_api", {}).get("retry_attempts", ProviderAPI.RETRY_ATTEMPTS)


    def _load_network_config(self) -> None:
        """Load network configuration settings from TOML."""
        self.network_ipv4_enabled = self.config.get("network", {}).get("ipv4_enabled", NetworkAPI.IPV4_ENABLED)
        self.network_ipv6_enabled = self.config.get("network", {}).get("ipv6_enabled", NetworkAPI.IPV6_ENABLED)
        self.network_ipv4_detection_url = self.config.get("network", {}).get("ipv4_detection_url", NetworkAPI.IPV4_URL)
        self.network_ipv6_detection_url = self.config.get("network", {}).get("ipv6_detection_url", NetworkAPI.IPV6_URL)
        self.network_timeout = self.config.get("network", {}).get("timeout", NetworkAPI.TIMEOUT)
        self.network_retry_attempts = self.config.get("network", {}).get("retry_attempts", NetworkAPI.RETRY_ATTEMPTS)


    def _load_dns_config(self) -> None:
        """Load DNS configuration settings from TOML."""
        self.dns_default_ttl = self.config.get("dns", {}).get("default_ttl", DNSDefaults.DEFAULT_TTL)


    def _load_daemon_config(self) -> None:
        """Load daemon configuration settings from TOML."""
        self.daemon_enabled = self.config.get("daemon", {}).get("enabled", DaemonDefaults.ENABLED)
        self.daemon_check_interval = self.config.get("daemon", {}).get("check_interval", DaemonDefaults.CHECK_INTERVAL)
        self.daemon_max_retries = self.config.get("daemon", {}).get("max_retries", DaemonDefaults.MAX_RETRIES)
        self.daemon_retry_delay = self.config.get("daemon", {}).get("retry_delay", DaemonDefaults.RETRY_DELAY)
        self.force_update_interval = self.config.get("daemon", {}).get("force_update_interval", DaemonDefaults.FORCE_UPDATE_INTERVAL)
        self.daemon_sync_checks = self.config.get("daemon", {}).get("sync_checks", DaemonDefaults.SYNC_CHECKS)
        
        
    def _load_database_config(self, current_dir: str) -> None:
        """Load database configuration with FHS-compliant path resolution.

        Resolves database path from configuration. Absolute paths are used
        directly, relative paths are resolved against DEFAULT_DATA_DIR.

        Args:
            current_dir: Base directory (unused, kept for API compatibility).
        """
        db_path = self.config.get("database", {}).get("db_path", AppPaths.DB_FILE)
        self.db_path = db_path if os.path.isabs(db_path) else os.path.join(AppPaths.DATA_DIR, db_path)
        
        key_file = self.config.get("database", {}).get("encryption_key_path", AppPaths.ENCRYPTION_KEY_FILE)
        self.encryption_key_path = key_file if os.path.isabs(key_file) else os.path.join(AppPaths.DATA_DIR, key_file)