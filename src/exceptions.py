"""
Custom Exception Classes for IONOS DynDNS.

Exception Hierarchy:
    DynDNSException (Base)
    ├─ DatabaseError         - Database operations (sqlite3 errors)
    ├─ ConfigError          - Configuration issues (TOML parsing, missing keys)
    ├─ EncryptionError      - Encryption/Decryption failures
    ├─ NetworkError         - IP detection, network connectivity
    ├─ APIError             - Provider API communication
    │  ├─ RecordNotFoundError  - DNS record not found on provider
    │  └─ ZoneNotFoundError    - DNS zone not found on provider
    └─ ValidationError      - Input validation failures
"""


class DynDNSException(Exception):
    """Base exception for all IONOS DynDNS errors."""
    pass


class DatabaseError(DynDNSException):
    """Database operation failed (SQLite errors, connection issues)."""
    pass


class ConfigError(DynDNSException):
    """Configuration error (TOML parsing, missing keys, invalid values)."""
    pass


class EncryptionError(DynDNSException):
    """Encryption/Decryption operation failed."""
    pass


class NetworkError(DynDNSException):
    """Network operation failed (IP detection, connectivity issues)."""
    pass


class APIError(DynDNSException):
    """Provider API communication error."""
    pass


class RecordNotFoundError(APIError):
    """DNS record not found on provider (404)."""
    pass


class ZoneNotFoundError(APIError):
    """DNS zone not found on provider (404)."""
    pass


class ValidationError(DynDNSException):
    """Input validation failed (invalid domain, IP, zone ID)."""
    pass
