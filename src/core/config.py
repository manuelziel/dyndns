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

# Standard library imports
import logging
import os
import tomllib
from typing import Dict, Any, Optional

# Local imports
from .exceptions import ConfigError
from .database import Database

################################################################################
# CONSTANTS - Default Values & Internal Settings
################################################################################

# Default app settings
DEFAULT_APP_NAME = "IONOS DynDNS"
DEFAULT_APP_AUTHOR = "Manuel Ziel"

# Default data directory
# All relative paths are resolved relative to this base directory
DEFAULT_DATA_DIR = "/var/lib/ionos-dyndns/"

# Default database path
DEFAULT_DB_PATH = "ionos-dyndns.db"

# Default debug level
DEFAULT_LOG_LEVEL = "INFO"
DEFAULT_CONSOLE_COLORS = True

# Default API settings
DEFAULT_API_BASE_URL = "https://api.hosting.ionos.com/dns/v1"
DEFAULT_API_TIMEOUT = 30  # seconds
DEFAULT_API_RETRY_ATTEMPTS = 3

# Default network settings
DEFAULT_IPV4_ENABLED = True
DEFAULT_IPV6_ENABLED = True
DEFAULT_IPV4_DETECTION_URL = "https://api.ipify.org"
DEFAULT_IPV6_DETECTION_URL = "https://api6.ipify.org"
DEFAULT_NETWORK_TIMEOUT = 10  # seconds
DEFAULT_NETWORK_RETRY_ATTEMPTS = 3

# Default dns settings
DEFAULT_DNS_DEFAULT_TTL = 3600  # seconds

# Default daemon settings
DEFAULT_DEAMON_ENABLED = False
DEFAULT_DAEMON_CHECK_INTERVAL = 300  # seconds
DEFAULT_DAEMON_MAX_RETRIES = 3
DEFAULT_DAEMON_RETRY_DELAY = 60  # seconds
DEFAULT_FORCE_UPDATE_INTERVAL = 86400  # seconds
DEFAULT_DAEMON_SYNC_CHECKS = True

# DEFAULT ENCRYPTION SETTINGS
DEFAULT_ENCRYPTION_KEY_PATH = ".encryption_key"

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
        self.log_level = self.config.get("debug", {}).get("level", DEFAULT_LOG_LEVEL)
        self.console_colors = self.config.get("debug", {}).get("console_colors", DEFAULT_CONSOLE_COLORS)

    def _load_api_config(self) -> None:
        """Load API configuration settings from TOML."""
        self.provider_api_base_url = self.config.get("provider_api", {}).get("base_url", DEFAULT_API_BASE_URL)
        self.provider_api_timeout = self.config.get("provider_api", {}).get("timeout", DEFAULT_API_TIMEOUT)
        self.provider_api_retry_attempts = self.config.get("provider_api", {}).get("retry_attempts", DEFAULT_API_RETRY_ATTEMPTS)

    def _load_network_config(self) -> None:
        """Load network configuration settings from TOML."""
        self.network_ipv4_enabled = self.config.get("network", {}).get("ipv4_enabled", DEFAULT_IPV4_ENABLED)
        self.network_ipv6_enabled = self.config.get("network", {}).get("ipv6_enabled", DEFAULT_IPV6_ENABLED)
        self.network_ipv4_detection_url = self.config.get("network", {}).get("ipv4_detection_url", DEFAULT_IPV4_DETECTION_URL)
        self.network_ipv6_detection_url = self.config.get("network", {}).get("ipv6_detection_url", DEFAULT_IPV6_DETECTION_URL)
        self.network_timeout = self.config.get("network", {}).get("timeout", DEFAULT_NETWORK_TIMEOUT)
        self.network_retry_attempts = self.config.get("network", {}).get("retry_attempts", DEFAULT_NETWORK_RETRY_ATTEMPTS)

    def _load_dns_config(self) -> None:
        """Load DNS configuration settings from TOML."""
        self.dns_default_ttl = self.config.get("dns", {}).get("default_ttl", DEFAULT_DNS_DEFAULT_TTL)

    def _load_daemon_config(self) -> None:
        """Load daemon configuration settings from TOML."""
        self.daemon_enabled = self.config.get("daemon", {}).get("enabled", DEFAULT_DEAMON_ENABLED)
        self.daemon_check_interval = self.config.get("daemon", {}).get("check_interval", DEFAULT_DAEMON_CHECK_INTERVAL)
        self.daemon_max_retries = self.config.get("daemon", {}).get("max_retries", DEFAULT_DAEMON_MAX_RETRIES)
        self.daemon_retry_delay = self.config.get("daemon", {}).get("retry_delay", DEFAULT_DAEMON_RETRY_DELAY)
        self.force_update_interval = self.config.get("daemon", {}).get("force_update_interval", DEFAULT_FORCE_UPDATE_INTERVAL)
        self.daemon_sync_checks = self.config.get("daemon", {}).get("sync_checks", DEFAULT_DAEMON_SYNC_CHECKS)
        
    def _load_database_config(self, current_dir: str) -> None:
        """Load database configuration with FHS-compliant path resolution.

        Resolves database path from configuration. Absolute paths are used
        directly, relative paths are resolved against DEFAULT_DATA_DIR.

        Args:
            current_dir: Base directory (unused, kept for API compatibility).
        """
        db_path = self.config.get("database", {}).get("db_path", DEFAULT_DB_PATH)
        self.db_path = db_path if os.path.isabs(db_path) else os.path.join(DEFAULT_DATA_DIR, db_path)
        
        key_file = self.config.get("database", {}).get("encryption_key_path", DEFAULT_ENCRYPTION_KEY_PATH)
        self.encryption_key_path = key_file if os.path.isabs(key_file) else os.path.join(DEFAULT_DATA_DIR, key_file)