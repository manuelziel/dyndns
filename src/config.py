#!/usr/bin/env python3
"""
Configuration Manager

Handles TOML configuration loading with bash environment integration.

Created: 2025-10-27
Author: Manuel Ziel
License: MIT
"""

################################################################################
# IMPORTS & DEPENDENCIES
################################################################################

# Standard library imports
import logging
import os
import time
import tomllib
from typing import Dict, Any, Optional
from colors import Colors
from exceptions import ConfigError

################################################################################
# CONFIGURATION MANAGER CLASS - TOML Configuration with Environment Integration
################################################################################

class ConfigManager:
    """Configuration handler for TOML config, database, and external services."""

    def __init__(self, current_dir: str, config_path: str) -> None:
        """Initialize configuration handler, load TOML config, and setup database."""
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
        """Load configuration from TOML file."""
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
    # PRIVATE METHODS - Internal Implementation
    ################################################################################

    def _init_database(self) -> None:
        """Initialize database connection if configured."""
        try:
            try:
                from .database import Database
            except ImportError:
                from database import Database
            
            if hasattr(self, 'log_level'):
                db_logger = logging.getLogger('database')
                db_logger.setLevel(getattr(logging, self.log_level, logging.INFO))
            else:
                db_logger = None
                
            self.db = Database(self.db_path, logger=db_logger, config=self)
            
            self.db.set_config_by_key("initialized", "true")
            self.db.set_config_by_key("init_timestamp", str(time.time()))
            
        except Exception as e:
            print(f"Warning: Database initialization failed: {e}")
            self.db = None

    def _load_debug_config(self) -> None:
        """Load debug config from [debug] section."""
        self.log_level = self.config.get("debug", {}).get("level", "INFO")
        self.console_colors = self.config.get("debug", {}).get("console_colors", True)

    def _load_api_config(self) -> None:
        """Load API config from [provider_api] section."""
        self.provider_api_base_url = self.config.get("provider_api", {}).get("base_url", "https://api.hosting.ionos.com/dns/v1")
        self.provider_api_timeout = self.config.get("provider_api", {}).get("timeout", 30)
        self.provider_api_retry_attempts = self.config.get("provider_api", {}).get("retry_attempts", 3)

    def _load_network_config(self) -> None:
        """Load network config from [network] section."""
        self.network_ipv4_enabled = self.config.get("network", {}).get("ipv4_enabled", True)
        self.network_ipv6_enabled = self.config.get("network", {}).get("ipv6_enabled", True)
        self.network_ipv4_detection_url = self.config.get("network", {}).get("ipv4_detection_url", "https://api.ipify.org")
        self.network_ipv6_detection_url = self.config.get("network", {}).get("ipv6_detection_url", "https://api6.ipify.org")
        self.network_timeout = self.config.get("network", {}).get("timeout", 10)
        self.network_retry_attempts = self.config.get("network", {}).get("retry_attempts", 3)

    def _load_dns_config(self) -> None:
        """Load DNS config from [dns] section."""
        self.dns_default_ttl = self.config.get("dns", {}).get("default_ttl", 3600)

    def _load_daemon_config(self) -> None:
        """Load daemon config from [daemon] section."""
        self.daemon_enabled = self.config.get("daemon", {}).get("enabled", False)
        self.daemon_check_interval = self.config.get("daemon", {}).get("check_interval", 300)
        self.daemon_max_retries = self.config.get("daemon", {}).get("max_retries", 3)
        self.daemon_retry_delay = self.config.get("daemon", {}).get("retry_delay", 60)
        self.force_update_interval = self.config.get("daemon", {}).get("force_update_interval", 86400)
        self.daemon_sync_checks = self.config.get("daemon", {}).get("sync_checks", True)
        
    def _load_database_config(self, current_dir: str) -> None:
        """Load database config from [database] section, resolve paths."""
        db_path = self.config.get("database", {}).get("db_path", "db.db")
        self.db_path = os.path.join(current_dir, db_path)
        
        key_file = self.config.get("database", {}).get("encryption_key_path", ".encryption_key")
        
        if not os.path.isabs(key_file):
            db_dir = os.path.dirname(os.path.abspath(self.db_path))
            self.encryption_key_path = os.path.join(db_dir, key_file)
        else:
            self.encryption_key_path = key_file