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
# IMPORTS & DEPENDENCIES
################################################################################

from .exceptions import ValidationError

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
            ValidationError: If record_type is not supported.
        """
        if record_type == RecordType.A:
            return cls.IPV4
        elif record_type == RecordType.AAAA:
            return cls.IPV6
        else:
            raise ValidationError(f"Unsupported record type: {record_type}")


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