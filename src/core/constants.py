#!/usr/bin/env python3
"""Application constants, enums, and default settings for DynDNS.

Centralizes all application metadata, status enumerations, HTTP constants,
security redaction defaults, database wear-leveling parameters, and service defaults.

Author: Manuel Ziel
License: MIT
"""

################################################################################
# IMPORTS & DEPENDENCIES
################################################################################

from enum import StrEnum

################################################################################
# APPLICATION SETTINGS
################################################################################


class AppSettings:
    """Global application metadata and settings."""

    VERSION = "1.0.4"
    AUTHOR = "Manuel Ziel"
    EMAIL = "manuelziel@gmail.com"
    DESCRIPTION = "Dynamic DNS Client"
    SOFTWARE_NAME = "DynDNS"
    SYSLOG_IDENTIFIER = "dyndns"


################################################################################
# SYNC & UPDATE STATUS ENUMERATIONS
################################################################################


class SyncStatus(StrEnum):
    """DNS record synchronization status constants."""

    SYNCED = "synced"
    ORPHANED = "orphaned"
    LOCAL_ONLY = "local_only"
    CONFLICT = "conflict"
    PENDING_SYNC = "pending_sync"
    NEW = "new"
    UPDATED = "updated"


class UpdateStatus(StrEnum):
    """DNS update operation result status constants."""

    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"
    UPDATED = "updated"
    TOTAL = "total"


class Subdomain(StrEnum):
    """Common subdomain constants for DynDNS records."""

    ROOT = "@"
    WWW = "www"


class RecordType(StrEnum):
    """Supported DNS record type constants."""

    A = "A"
    AAAA = "AAAA"

    @classmethod
    def is_supported(cls, record_type: str) -> bool:
        """Check whether ``record_type`` is supported for DynDNS updates.

        Args:
            record_type: DNS record type string to validate.

        Returns:
            True if supported (``'A'`` or ``'AAAA'``), False otherwise.
        """
        return record_type in (cls.A, cls.AAAA)


class PlaceholderIP:
    """Placeholder IP addresses for initial DNS record creation."""

    IPV4 = "0.0.0.0"
    IPV6 = "::"

    @classmethod
    def get(cls, record_type: str) -> str:
        """Return placeholder IP address matching ``record_type``.

        Args:
            record_type: DNS record type (``'A'`` or ``'AAAA'``).

        Returns:
            Placeholder IP address string.

        Raises:
            ValueError: If ``record_type`` is not supported.
        """
        if record_type == RecordType.A:
            return cls.IPV4
        if record_type == RecordType.AAAA:
            return cls.IPV6
        raise ValueError(f"Unsupported record type: {record_type}")


################################################################################
# HTTP CONSTANTS
################################################################################


class HTTPMethod(StrEnum):
    """Standard HTTP request verbs."""

    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    PATCH = "PATCH"
    DELETE = "DELETE"


class HTTPStatus:
    """Standard HTTP response status codes."""

    OK = 200
    CREATED = 201
    NO_CONTENT = 204
    BAD_REQUEST = 400
    UNAUTHORIZED = 401
    FORBIDDEN = 403
    NOT_FOUND = 404
    TOO_MANY_REQUESTS = 429
    INTERNAL_SERVER_ERROR = 500
    BAD_GATEWAY = 502
    SERVICE_UNAVAILABLE = 503
    GATEWAY_TIMEOUT = 504


class HTTPHeader:
    """Standard HTTP header names."""

    ACCEPT = "accept"
    CONTENT_TYPE = "Content-Type"
    X_API_KEY = "X-API-Key"
    RETRY_AFTER = "Retry-After"


class HTTPHeaderValue:
    """Standard HTTP header values."""

    APPLICATION_JSON = "application/json"


################################################################################
# ENVIRONMENT, OWNERSHIP & SECURITY DEFAULTS
################################################################################


class EnvKeys(StrEnum):
    """Environment variable keys exported by the Bash runtime wrapper."""

    SERVICE_USER = "SERVICE_USER"
    SERVICE_GROUP = "SERVICE_GROUP"
    DAEMON_MODE = "DAEMON_MODE"
    CONFIG_FILE = "CONFIG_FILE"
    DATA_DIR = "DATA_DIR"
    RUNTIME_DIR = "RUNTIME_DIR"


class OwnershipDefaults:
    """Default permissions and account names for service ownership handoff."""

    FILE_MODE_PRIVATE = 0o600
    FILE_MODE_GROUP_READ = 0o640
    FILE_MODE_GROUP_WRITE = 0o660
    DIR_MODE_GROUP_WRITE = 0o770
    ROOT_USER = "root"
    PLACEHOLDER_USER = "[SERVICE_USER]"
    PLACEHOLDER_GROUP = "[SERVICE_GROUP]"


class EncryptionDefaults:
    """Default values for Fernet encryption key management."""

    KEY_FILE_MODE = 0o600
    FERNET_KEY_LENGTH = 44


class SecurityDefaults:
    """Default log sanitization and secret redaction settings."""

    REDACTED_VALUE = "**REDACTED**"
    SENSITIVE_QUERY_KEYS = (
        "q",
        "api_key",
        "apikey",
        "token",
        "access_token",
        "auth",
        "key",
        "secret",
        "password",
        "passwd",
        "pwd",
        "pass",
        "authorization",
        "sig",
        "signature",
    )


################################################################################
# EXPORT FORMAT CONSTANTS
################################################################################


class ExportFormat:
    """Configuration export and import serialization format constants."""

    YAML = "yaml"
    JSON = "json"
    EXT_YAML = ".yaml"
    EXT_YML = ".yml"
    EXT_JSON = ".json"

    @classmethod
    def from_extension(cls, ext: str) -> str:
        """Resolve export format from a file extension.

        Args:
            ext: Lowercase file extension (e.g. ``'.yaml'`` or ``'.json'``).

        Returns:
            Resolved format identifier (defaults to ``'yaml'``).
        """
        if ext in (cls.EXT_YAML, cls.EXT_YML):
            return cls.YAML
        if ext == cls.EXT_JSON:
            return cls.JSON
        return cls.YAML

    @classmethod
    def is_valid(cls, format_type: str) -> bool:
        """Check whether ``format_type`` is a supported export format.

        Args:
            format_type: Format identifier string.

        Returns:
            True if ``'yaml'`` or ``'json'``, False otherwise.
        """
        return format_type in (cls.YAML, cls.JSON)


################################################################################
# DATABASE & STORAGE DEFAULTS
################################################################################


class DatabaseDefaults:
    """Default values for SQLite connection pooling and wear-leveling."""

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
    """Units and conversion factors for disk and database storage metrics."""

    BYTES_PER_KB = 1024.0
    BYTES_PER_MB = 1024.0**2
    BYTES_PER_GB = 1024.0**3
    PERCENTAGE_FACTOR = 100.0
    DEFAULT_DECIMALS = 2
    DISK_PERCENT_DECIMALS = 1
    UNITS = ("B", "KB", "MB", "GB", "TB", "PB")


################################################################################
# DNS, LOGGING, DAEMON, PATHS & NETWORK DEFAULTS
################################################################################


class UpdateMethod(StrEnum):
    """Supported DNS update methods."""

    DYNDNS = "dyndns"
    REST = "rest"


class DNSDefaults:
    """Default DNS synchronization settings."""

    DEFAULT_TTL = 3600
    DEFAULT_UPDATE_METHOD = UpdateMethod.DYNDNS


class LoggingDefaults:
    """Default logging and native systemd journald socket configuration."""

    LEVEL = "INFO"
    CONSOLE_COLORS = True
    SUCCESS_LEVEL = 25
    JOURNAL_SOCKET_PATH = "/run/systemd/journal/socket"
    MAX_JOURNAL_MESSAGE_BYTES = 65536
    DEFAULT_LOG_LIMIT = 25
    MAX_LOG_LIMIT = 200
    SYSLOG_PRIORITY_CRITICAL = "2"
    SYSLOG_PRIORITY_ERROR = "3"
    SYSLOG_PRIORITY_WARNING = "4"
    SYSLOG_PRIORITY_NOTICE = "5"
    SYSLOG_PRIORITY_INFO = "6"
    SYSLOG_PRIORITY_DEBUG = "7"


class DaemonDefaults:
    """Default daemon lifecycle and interval settings."""

    ENABLED = False
    CHECK_INTERVAL = 300
    DEFAULT_CYCLE_INTERVAL = 300
    MAX_RETRIES = 3
    RETRY_DELAY = 60
    ERROR_RETRY_DELAY = 10
    SYNC_CHECKS = True
    STOP_TIMEOUT = 30
    STOP_CHECK_INTERVAL = 1


class AppPaths:
    """Default FHS 3.0 application paths and filenames."""

    DATA_DIR = "/var/lib/dyndns"
    RUNTIME_DIR = "/run/dyndns"
    DB_FILE = "dyndns.db"
    CONFIG_FILE = "config.toml"
    ENCRYPTION_KEY_FILE = ".encryption_key"


class ProviderAPI:
    """Default DNS Provider API client and retry configuration."""

    BASE_URL = "https://api.hosting.ionos.com/dns/v1"
    TIMEOUT = 30
    RETRY_ATTEMPTS = 3
    AUTH_MAX_RETRIES = 2
    AUTH_RETRY_DELAY = 2
    BACKOFF_BASE = 2
    MAX_RETRY_DELAY = 60.0
    SUPPORTED_METHODS = ("GET", "POST", "PUT", "PATCH", "DELETE")
    RETRYABLE_STATUS_CODES = (429, 500, 502, 503, 504)
    ERR_RECORD_NOT_FOUND = "RECORD_NOT_FOUND"


class NetworkAPI:
    """Default public IP detection endpoints and retry configuration."""

    IPV4_URL = "https://api.ipify.org"
    IPV6_URL = "https://api6.ipify.org"
    IPV4_ENABLED = True
    IPV6_ENABLED = True
    TIMEOUT = 10
    RETRY_ATTEMPTS = 3
    RETRY_DELAY = 2


################################################################################
# EXCEPTION DEFAULTS
################################################################################


class ExceptionMessages:
    """Default error messages for the custom exception hierarchy."""

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
