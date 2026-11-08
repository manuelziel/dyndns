#!/usr/bin/env python3
"""Application constants for magic strings and status values.

This module provides centralized constants for sync status values, update
status codes, DNS record types, and configuration export formats.

Typical usage:
    >>> from src.core.constants import SyncStatus, RecordType
    >>> status = SyncStatus.SYNCED
    >>> if RecordType.is_supported('A'):
    ...     print('Supported')

Author: Manuel Ziel
License: MIT
"""

################################################################################
# APPLICATION SETTINGS
################################################################################

class AppSettings:
    """Global application metadata and settings.

    Attributes:
        VERSION: Current software version.
        AUTHOR: Author's name.
        EMAIL: Author's email.
        DESCRIPTION: Brief description of the software.
        SOFTWARE_NAME: Name of the application.
        SYSLOG_IDENTIFIER: Systemd syslog identifier.
    """
    VERSION = "1.0.3"
    AUTHOR = "Manuel Ziel"
    EMAIL = "manuelziel@gmail.com"
    DESCRIPTION = "Dynamic DNS Client"
    SOFTWARE_NAME = "DynDNS"
    SYSLOG_IDENTIFIER = "dyndns"


################################################################################
# SYNC STATUS - Record synchronization states
################################################################################

class SyncStatus:
    """DNS Record synchronization status constants.

    Attributes:
        SYNCED: Record is synchronized with provider.
        ORPHANED: Record exists at provider but not locally.
        LOCAL_ONLY: Record exists locally but not at provider.
        CONFLICT: Record has conflicting local and provider states.
        PENDING_SYNC: Record is waiting to be synchronized.
        NEW: Newly created record.
        UPDATED: Recently updated record.
    """
    SYNCED = 'synced'
    ORPHANED = 'orphaned'
    LOCAL_ONLY = 'local_only'
    CONFLICT = 'conflict'
    PENDING_SYNC = 'pending_sync'
    NEW = 'new'
    UPDATED = 'updated'


################################################################################
# UPDATE STATUS - DNS update operation results
################################################################################

class UpdateStatus:
    """DNS update operation result status constants.

    Attributes:
        SUCCESS: Update completed successfully.
        FAILED: Update failed with error.
        SKIPPED: Update was skipped (no change needed).
        UPDATED: Record was updated.
        TOTAL: Used for counting total operations.
    """
    SUCCESS = 'success'
    FAILED = 'failed'
    SKIPPED = 'skipped'
    UPDATED = 'updated'
    TOTAL = 'total'


################################################################################
# SUBDOMAIN - Common subdomain constants
################################################################################

class Subdomain:
    """Common subdomain constants for DynDNS records.

    Attributes:
        ROOT: Root domain marker ('@' for example.com).
        WWW: WWW subdomain prefix.
    """
    ROOT = '@'      # Root domain (e.g., example.com)
    WWW = 'www'     # WWW subdomain (e.g., www.example.com)


################################################################################
# RECORD TYPES - Supported DNS record types
################################################################################

class RecordType:
    """DNS record type constants.

    Attributes:
        A: IPv4 address record type.
        AAAA: IPv6 address record type.
    """
    A = 'A'
    AAAA = 'AAAA'
    
    @classmethod
    def is_supported(cls, record_type: str) -> bool:
        """Check if record type is supported for DynDNS.

        Args:
            record_type: DNS record type string to validate.

        Returns:
            True if supported (A or AAAA), False otherwise.
        """
        return record_type in (cls.A, cls.AAAA)


################################################################################
# PLACEHOLDER IPS - Default IPs for record creation
################################################################################

class PlaceholderIP:
    """Placeholder IP addresses for initial record creation.

    Attributes:
        IPV4: Default IPv4 placeholder ('0.0.0.0').
        IPV6: Default IPv6 placeholder ('::').
    """
    IPV4 = '0.0.0.0'
    IPV6 = '::'
    
    @classmethod
    def get(cls, record_type: str) -> str:
        """Get placeholder IP for record type.

        Args:
            record_type: DNS record type ('A' or 'AAAA').

        Returns:
            Placeholder IP address string.

        Raises:
            ValueError: If record_type is not supported.
        """
        if record_type == RecordType.A:
            return cls.IPV4
        elif record_type == RecordType.AAAA:
            return cls.IPV6
        else:
            raise ValueError(f"Unsupported record type: {record_type}")


################################################################################
# HTTP METHODS - Standard HTTP Verbs
################################################################################

class HTTPMethod:
    """Namespace for standard HTTP methods."""
    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    DELETE = "DELETE"


################################################################################
# HTTP STATUS CODES - Standard HTTP Response Codes
################################################################################

class HTTPStatus:
    """Namespace for HTTP response status codes.

    Attributes:
        OK: Request succeeded (200).
        CREATED: Request succeeded and resource created (201).
        NO_CONTENT: Request succeeded with no response content (204).
        BAD_REQUEST: Malformed request or invalid parameters (400).
        UNAUTHORIZED: Authentication failed (401).
        FORBIDDEN: Permission denied (403).
        NOT_FOUND: Resource not found (404).
        TOO_MANY_REQUESTS: Rate limit exceeded (429).
        INTERNAL_SERVER_ERROR: Server encountered an error (500).
    """
    OK = 200
    CREATED = 201
    NO_CONTENT = 204
    BAD_REQUEST = 400
    UNAUTHORIZED = 401
    FORBIDDEN = 403
    NOT_FOUND = 404
    TOO_MANY_REQUESTS = 429
    INTERNAL_SERVER_ERROR = 500


################################################################################
# HTTP HEADERS - Standard HTTP Header Names and Values
################################################################################

class HTTPHeader:
    """Namespace for standard HTTP headers."""
    ACCEPT = "accept"
    CONTENT_TYPE = "Content-Type"
    X_API_KEY = "X-API-Key"


class HTTPHeaderValue:
    """Namespace for standard HTTP header values."""
    APPLICATION_JSON = "application/json"


################################################################################
# ENVIRONMENT VARIABLES - System Environment Keys
################################################################################

class EnvKeys:
    """Namespace for environment variable keys."""
    SERVICE_USER = "SERVICE_USER"
    SERVICE_GROUP = "SERVICE_GROUP"


################################################################################
# SYSTEM DEFAULTS - User Account and Permission Defaults
################################################################################

class OwnershipDefaults:
    """Default permissions and user names for ownership handoff."""
    FILE_MODE_GROUP_WRITE = 0o660
    DIR_MODE_GROUP_WRITE = 0o770
    ROOT_USER = "root"
    PLACEHOLDER_USER = "[SERVICE_USER]"
    PLACEHOLDER_GROUP = "[SERVICE_GROUP]"


################################################################################
# ENCRYPTION SETTINGS - Encryption Specifications
################################################################################

class EncryptionDefaults:
    """Default values for Fernet encryption key management."""
    KEY_FILE_MODE = 0o600
    FERNET_KEY_LENGTH = 44


################################################################################
# EXPORT FORMAT - Configuration export/import formats
################################################################################

class ExportFormat:
    """Configuration export/import format constants.

    Attributes:
        YAML: YAML format identifier.
        JSON: JSON format identifier.
        EXT_YAML: YAML file extension (.yaml).
        EXT_YML: Alternative YAML extension (.yml).
        EXT_JSON: JSON file extension (.json).
    """
    YAML = 'yaml'
    JSON = 'json'
    
    # File extensions
    EXT_YAML = '.yaml'
    EXT_YML = '.yml'
    EXT_JSON = '.json'
    
    @classmethod
    def from_extension(cls, ext: str) -> str:
        """Get format type from file extension.

        Args:
            ext: File extension (e.g., '.yaml', '.json').

        Returns:
            Format type constant (YAML or JSON). Defaults to YAML.
        """
        if ext in (cls.EXT_YAML, cls.EXT_YML):
            return cls.YAML
        elif ext == cls.EXT_JSON:
            return cls.JSON
        return cls.YAML  # Default
    
    @classmethod
    def is_valid(cls, format_type: str) -> bool:
        """Check if format type is valid.

        Args:
            format_type: Format type string to validate.

        Returns:
            True if valid (YAML or JSON), False otherwise.
        """
        return format_type in (cls.YAML, cls.JSON)


################################################################################
# DATABASE DEFAULTS - SQLite Connection Pool Config
################################################################################

class DatabaseDefaults:
    """Default values for SQLite database configuration and wear-leveling.

    Attributes:
        DB_SCHEMA_VERSION: Current database schema version (PRAGMA user_version).
        UNVERSIONED_SCHEMA: Initial schema version for new databases (0).
        MAX_CONNECTIONS: Maximum connections in the pool.
        CONNECT_TIMEOUT: SQLite connect timeout in seconds.
        POOL_GET_TIMEOUT: Timeout to acquire a connection from pool.
        POOL_PUT_TIMEOUT: Timeout to return a connection to pool.
        BUSY_TIMEOUT_MS: SQLite lock wait timeout in milliseconds (5 s).
        JOURNAL_SIZE_LIMIT: Maximum WAL file size after checkpoints (64 MB).
        CACHE_SIZE_KB: Negative value sets RAM page cache in KiB (16 MB).
        MMAP_SIZE: Memory-mapped Read-I/O size in bytes (128 MB).
        DB_TIMESTAMP_FORMAT: Timestamp format used for database entries.
        DYNDNS_BUNDLE_ID_PREFIX: Key prefix in app_config for DynDNS bundle UUIDs.
    """
    DB_SCHEMA_VERSION = 3
    UNVERSIONED_SCHEMA = 0
    MAX_CONNECTIONS = 5
    CONNECT_TIMEOUT = 5.0
    POOL_GET_TIMEOUT = 10.0
    POOL_PUT_TIMEOUT = 1.0
    BUSY_TIMEOUT_MS = 5000
    JOURNAL_SIZE_LIMIT = 67108864
    CACHE_SIZE_KB = -16384
    MMAP_SIZE = 134217728
    DB_TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S"
    DYNDNS_BUNDLE_ID_PREFIX = "dyndns_bundle_id_"


class StorageConstants:
    """Units and conversion factors for disk and database storage calculations."""
    BYTES_PER_KB = 1024.0
    BYTES_PER_MB = 1024.0 ** 2
    BYTES_PER_GB = 1024.0 ** 3
    PERCENTAGE_FACTOR = 100.0
    DEFAULT_DECIMALS = 2
    DISK_PERCENT_DECIMALS = 1
    UNITS = ("B", "KB", "MB", "GB", "TB", "PB")


################################################################################
# DNS SETTINGS - Default DNS Configuration
################################################################################

class DNSDefaults:
    """Namespace for default DNS settings."""
    DEFAULT_TTL = 3600  # seconds
    DEFAULT_UPDATE_METHOD = "dyndns"


class UpdateMethod:
    """Namespace for DNS update method options."""
    DYNDNS = "dyndns"
    REST = "rest"


################################################################################
# LOGGING SETTINGS - Default Logging Configuration
################################################################################

class LoggingDefaults:
    """Namespace for default logging configuration."""
    LEVEL = "INFO"
    CONSOLE_COLORS = True
    SUCCESS_LEVEL = 25


################################################################################
# DAEMON SETTINGS - Default Daemon Configuration
################################################################################

class DaemonDefaults:
    """Namespace for default daemon settings."""
    ENABLED = False
    CHECK_INTERVAL = 300  # seconds
    MAX_RETRIES = 3
    RETRY_DELAY = 60  # seconds
    SYNC_CHECKS = True
    STOP_TIMEOUT = 30  # seconds
    STOP_CHECK_INTERVAL = 1  # seconds


################################################################################
# APPLICATION PATHS - Default File & Directory Paths
################################################################################

class AppPaths:
    """Namespace for default application paths and filenames."""
    DATA_DIR = "/var/lib/dyndns"
    RUNTIME_DIR = "/run/dyndns"
    DB_FILE = "dyndns.db"
    CONFIG_FILE = "config.toml"
    ENCRYPTION_KEY_FILE = ".encryption_key"


################################################################################
# API SETTINGS - Default Provider API Configuration
################################################################################

class ProviderAPI:
    """Namespace for DNS Provider API defaults."""
    BASE_URL = "https://api.hosting.ionos.com/dns/v1"
    TIMEOUT = 30  # seconds
    RETRY_ATTEMPTS = 3
    AUTH_MAX_RETRIES = 2
    AUTH_RETRY_DELAY = 2  # seconds

    # Error codes
    ERR_RECORD_NOT_FOUND = "RECORD_NOT_FOUND"


################################################################################
# NETWORK SETTINGS - Default Network & IP Detection Configuration
################################################################################

class NetworkAPI:
    """Namespace for IP detection service defaults."""
    IPV4_URL = "https://api.ipify.org"
    IPV6_URL = "https://api6.ipify.org"
    IPV4_ENABLED = True
    IPV6_ENABLED = True
    TIMEOUT = 10  # seconds
    RETRY_ATTEMPTS = 3
    RETRY_DELAY = 2  # seconds


################################################################################
# EXCEPTION DEFAULTS - Default Exception Messages
################################################################################

class ExceptionMessages:
    """Default error messages for custom exceptions."""
    DEFAULT = "An application error occurred"
    DATABASE = "Database operation failed"
    DATABASE_LOCKED = "Database is currently locked by another process"
    CONFIG = "Configuration error"
    ENCRYPTION = "Encryption operation failed"
    NETWORK = "Network operation failed"
    API = "Provider API communication failed"
    RECORD_NOT_FOUND = "DNS record not found on provider"
    ZONE_NOT_FOUND = "DNS zone not found on provider"
    VALIDATION = "Input validation failed"