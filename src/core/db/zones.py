#!/usr/bin/env python3
"""Repository mixin for DNS zones, encrypted DynDNS bundles, and app_config.

Encapsulates SQLite persistence operations for ``zones``, ``dyndns_config``,
and ``app_config`` tables with transparent Fernet API-key encryption.

Author: Manuel Ziel
License: MIT
"""

################################################################################
# IMPORTS & DEPENDENCIES
################################################################################

import json
import logging
import sqlite3
from typing import Any

from ..constants import DatabaseDefaults
from ..encryption import EncryptionManager
from ..exceptions import EncryptionError

################################################################################
# ZONE, DYNDNS CONFIG & APP CONFIG REPOSITORY MIXIN
################################################################################


class ZoneRepositoryMixin:
    """Database repository methods for zones, DynDNS credentials, and settings."""

    logger: logging.Logger
    _encryption: EncryptionManager

    def execute_query(
        self, query: str, params: tuple[Any, ...] | None = None
    ) -> list[sqlite3.Row]:
        """Execute a SELECT query (implemented by ``DatabaseEngine``)."""
        raise NotImplementedError

    def execute_update(
        self, query: str, params: tuple[Any, ...] | None = None
    ) -> int:
        """Execute an INSERT/UPDATE/DELETE query (implemented by ``DatabaseEngine``)."""
        raise NotImplementedError

    ############################################################################
    # APPLICATION KEY-VALUE CONFIGURATION (app_config)
    ############################################################################

    def get_config_by_key(
        self, key: str, default: str | None = None
    ) -> str | None:
        """Retrieve a string configuration value from ``app_config`` by key.

        Args:
            key: Configuration key to retrieve.
            default: Fallback value when ``key`` is absent.

        Returns:
            Stored configuration value string or ``default``.
        """
        rows = self.execute_query(
            "SELECT value FROM app_config WHERE key = ?", (key,)
        )
        return str(rows[0]["value"]) if rows and rows[0]["value"] is not None else default

    def set_config_by_key(self, key: str, value: str) -> None:
        """Insert or update a configuration key-value pair only when changed.

        Args:
            key: Configuration key to store.
            value: Configuration value string.
        """
        sql = (
            "INSERT INTO app_config (key, value) VALUES (?, ?) ON CONFLICT(key) "
            "DO UPDATE SET value = excluded.value "
            "WHERE app_config.value IS NOT excluded.value"
        )
        self.execute_update(sql, (key, value))

    def delete_config_by_key(self, key: str) -> bool:
        """Delete an ``app_config`` entry by key.

        Args:
            key: Configuration key to remove.

        Returns:
            True if a row was deleted, False otherwise.
        """
        return self.execute_update("DELETE FROM app_config WHERE key = ?", (key,)) > 0

    ############################################################################
    # DNS ZONE REPOSITORY METHODS
    ############################################################################

    def get_zone_by_id(self, zone_id: int) -> dict[str, Any] | None:
        """Retrieve a DNS zone by its primary key ID.

        Args:
            zone_id: Zone database ID.

        Returns:
            Zone dictionary or ``None`` if not found.
        """
        rows = self.execute_query("SELECT * FROM zones WHERE id = ?", (zone_id,))
        return dict(rows[0]) if rows else None

    def get_zone_by_name(self, zone_name: str) -> dict[str, Any] | None:
        """Retrieve a DNS zone by its domain name.

        Args:
            zone_name: Domain name (e.g. ``'example.com'``).

        Returns:
            Zone dictionary or ``None`` if not found.
        """
        rows = self.execute_query(
            "SELECT * FROM zones WHERE zone_name = ?", (zone_name,)
        )
        return dict(rows[0]) if rows else None

    def get_all_zones(self) -> list[dict[str, Any]]:
        """Retrieve all configured DNS zones ordered alphabetically.

        Returns:
            List of zone dictionaries.
        """
        rows = self.execute_query("SELECT * FROM zones ORDER BY zone_name")
        return [dict(row) for row in rows]

    def get_all_enabled_zones(self) -> list[dict[str, Any]]:
        """Retrieve all enabled DNS zones ordered alphabetically.

        Returns:
            List of enabled zone dictionaries.
        """
        rows = self.execute_query(
            "SELECT * FROM zones WHERE enabled = 1 ORDER BY zone_name"
        )
        return [dict(row) for row in rows]

    def add_zone(
        self,
        zone_name: str,
        provider_zone_id: str | None = None,
        enabled: bool = True,
    ) -> int | None:
        """Insert a new DNS zone and return its generated primary key ID.

        Args:
            zone_name: Domain name (e.g. ``'example.com'``).
            provider_zone_id: Optional remote provider zone identifier.
            enabled: Whether the zone starts enabled.

        Returns:
            Newly created zone ID or ``None`` on failure.
        """
        sql = (
            "INSERT INTO zones (zone_name, provider_zone_id, enabled, created_at, updated_at) "
            "VALUES (?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
        )
        self.execute_update(sql, (zone_name, provider_zone_id, 1 if enabled else 0))
        rows = self.execute_query(
            "SELECT id FROM zones WHERE zone_name = ?", (zone_name,)
        )
        return int(rows[0]["id"]) if rows else None

    def update_zone_status(self, zone_id: int, enabled: bool) -> int:
        """Enable or disable a DNS zone by ID.

        Args:
            zone_id: Zone database ID.
            enabled: Target enabled state.

        Returns:
            Number of rows modified (0 or 1).
        """
        sql = "UPDATE zones SET enabled = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?"
        return self.execute_update(sql, (1 if enabled else 0, zone_id))

    def update_zone(self, zone_id: int, **kwargs: Any) -> int:
        """Update permitted DNS zone fields dynamically.

        Args:
            zone_id: Zone database ID.
            **kwargs: Subset of ``zone_name``, ``provider_zone_id``, ``enabled``.

        Returns:
            Number of rows modified (0 or 1).
        """
        allowed_fields = {"zone_name", "provider_zone_id", "enabled"}
        updates = {k: v for k, v in kwargs.items() if k in allowed_fields}
        if not updates:
            return 0
        if "enabled" in updates:
            updates["enabled"] = 1 if updates["enabled"] else 0
        set_clause = ", ".join(f"{field} = ?" for field in updates)
        sql = f"UPDATE zones SET {set_clause}, updated_at = CURRENT_TIMESTAMP WHERE id = ?"
        return self.execute_update(sql, (*updates.values(), zone_id))

    def delete_zone(self, zone_id: int) -> int:
        """Delete a DNS zone, cascading records/credentials, and bundle metadata.

        Args:
            zone_id: Zone database ID to delete.

        Returns:
            Number of deleted zone rows (0 or 1).
        """
        deleted = self.execute_update("DELETE FROM zones WHERE id = ?", (zone_id,))
        self.delete_config_by_key(
            f"{DatabaseDefaults.DYNDNS_BUNDLE_ID_PREFIX}{zone_id}"
        )
        return deleted

    ############################################################################
    # DYNDNS BUNDLE CREDENTIALS REPOSITORY (dyndns_config)
    ############################################################################

    def get_dyndns_config_by_zone(self, zone_id: int) -> dict[str, Any] | None:
        """Retrieve decrypted DynDNS credentials for ``zone_id``.

        Args:
            zone_id: Zone database ID.

        Returns:
            Configuration dictionary with decrypted ``api_key``, or ``None``.
        """
        rows = self.execute_query(
            "SELECT * FROM dyndns_config WHERE zone_id = ?", (zone_id,)
        )
        return (
            self._decrypt_dyndns_config_row(rows[0], f"zone_id={zone_id}")
            if rows
            else None
        )

    def get_dyndns_config_by_bulk_id(self, bulk_id: str) -> dict[str, Any] | None:
        """Retrieve decrypted DynDNS credentials by provider ``bulk_id``.

        Args:
            bulk_id: Provider bulk identifier prefix.

        Returns:
            Configuration dictionary with decrypted ``api_key``, or ``None``.
        """
        rows = self.execute_query(
            "SELECT * FROM dyndns_config WHERE bulk_id = ?", (bulk_id,)
        )
        return (
            self._decrypt_dyndns_config_row(rows[0], f"bulk_id={bulk_id}")
            if rows
            else None
        )

    def _decrypt_dyndns_config_row(
        self, row: sqlite3.Row, context: str
    ) -> dict[str, Any] | None:
        """Convert a ``dyndns_config`` row to dict and decrypt its ``api_key``.

        Args:
            row: Raw SQLite row from ``dyndns_config``.
            context: Diagnostic identifier string for error logs.

        Returns:
            Decrypted configuration dictionary, or ``None`` if decryption fails.
        """
        config = dict(row)
        if config.get("api_key"):
            try:
                config["api_key"] = self._encryption.decrypt(config["api_key"])
            except EncryptionError as exc:
                self.logger.error(f"Failed to decrypt api_key for {context}: {exc}")
                return None
        return config

    def set_dyndns_config(
        self,
        zone_id: int,
        bulk_id: str,
        api_key: str,
        update_url: str | None = None,
        description: str | None = None,
        domains: list[str] | str | None = None,
    ) -> None:
        """Insert or update encrypted DynDNS credentials for ``zone_id``.

        Args:
            zone_id: Zone database ID.
            bulk_id: Provider API key prefix / bulk identifier.
            api_key: Plaintext API secret (encrypted with Fernet before storage).
            update_url: Optional native IONOS DynDNS ``updateUrl``.
            description: Optional bundle description.
            domains: Optional domain list or serialized JSON array string.

        Raises:
            EncryptionError: If Fernet encryption of ``api_key`` fails.
        """
        try:
            api_key_encrypted = self._encryption.encrypt(api_key)
        except EncryptionError as exc:
            self.logger.error(f"Failed to encrypt api_key for zone_id={zone_id}: {exc}")
            raise EncryptionError(f"API key encryption failed: {exc}") from exc

        domains_json = domains if isinstance(domains, str) else json.dumps(domains or [])
        exists = self.execute_query("SELECT id FROM dyndns_config WHERE zone_id = ?", (zone_id,))
        if exists:
            sql = (
                "UPDATE dyndns_config SET bulk_id = ?, api_key = ?, update_url = ?, "
                "description = ?, domains = ?, updated_at = CURRENT_TIMESTAMP WHERE zone_id = ?"
            )
            self.execute_update(
                sql, (bulk_id, api_key_encrypted, update_url, description, domains_json, zone_id)
            )
        else:
            sql = (
                "INSERT INTO dyndns_config (zone_id, bulk_id, api_key, update_url, "
                "description, domains, enabled, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            )
            self.execute_update(
                sql, (zone_id, bulk_id, api_key_encrypted, update_url, description, domains_json)
            )

    def update_dyndns_status(self, zone_id: int, enabled: bool) -> int:
        """Enable or disable DynDNS configuration for ``zone_id``.

        Args:
            zone_id: Zone database ID.
            enabled: Target enabled state.

        Returns:
            Number of rows modified (0 or 1).
        """
        sql = (
            "UPDATE dyndns_config SET enabled = ?, updated_at = CURRENT_TIMESTAMP "
            "WHERE zone_id = ?"
        )
        return self.execute_update(sql, (1 if enabled else 0, zone_id))
