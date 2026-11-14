#!/usr/bin/env python3
"""Repository mixin for DNS records, IP state tracking, and update audit logs.

Encapsulates SQLite persistence operations for ``records``, ``ip_addresses``,
and ``dns_updates`` tables.

Author: Manuel Ziel
License: MIT
"""

################################################################################
# IMPORTS & DEPENDENCIES
################################################################################

import sqlite3
from typing import Any

from ..constants import DNSDefaults, SyncStatus, UpdateStatus

################################################################################
# RECORD, IP & HISTORY REPOSITORY MIXIN
################################################################################


class RecordRepositoryMixin:
    """Database repository methods for DNS records, IP state, and history."""

    config: Any

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
    # DNS RECORD REPOSITORY METHODS
    ############################################################################

    def get_record_by_id(self, record_id: int) -> dict[str, Any] | None:
        """Retrieve a DNS record by its primary key ID.

        Args:
            record_id: Record database ID.

        Returns:
            Record dictionary or ``None`` if not found.
        """
        rows = self.execute_query("SELECT * FROM records WHERE id = ?", (record_id,))
        return dict(rows[0]) if rows else None

    def get_records_by_zone(
        self, zone_id: int, enabled_only: bool = True
    ) -> list[dict[str, Any]]:
        """Retrieve DNS records for a zone joined with their stored IP metadata.

        Args:
            zone_id: Zone database ID to filter by.
            enabled_only: When True, return only enabled records.

        Returns:
            List of record dictionaries ordered by name and record type.
        """
        base_sql = (
            "SELECT r.*, ip.ip_address, ip.last_checked_at, ip.last_changed_at "
            "FROM records r LEFT JOIN ip_addresses ip ON ip.record_id = r.id "
            "WHERE r.zone_id = ?"
        )
        order_sql = " ORDER BY r.record_name, r.record_type"
        sql = f"{base_sql} AND r.enabled = 1{order_sql}" if enabled_only else f"{base_sql}{order_sql}"
        rows = self.execute_query(sql, (zone_id,))
        return [dict(row) for row in rows]

    def get_record_by_name_and_type(
        self, zone_id: int, record_name: str, record_type: str
    ) -> dict[str, Any] | None:
        """Retrieve a specific DNS record by zone, FQDN, and record type.

        Args:
            zone_id: Zone database ID.
            record_name: Full FQDN (e.g. ``'www.example.com'``).
            record_type: DNS record type (``'A'`` or ``'AAAA'``).

        Returns:
            Record dictionary or ``None`` if not found.
        """
        sql = "SELECT * FROM records WHERE zone_id = ? AND record_name = ? AND record_type = ?"
        rows = self.execute_query(sql, (zone_id, record_name, record_type))
        return dict(rows[0]) if rows else None

    def add_record(
        self,
        zone_id: int,
        record_name: str,
        record_type: str,
        provider_record_id: str | None = None,
        ttl: int | None = None,
        enabled: bool = True,
        managed: bool = True,
        sync_status: str = SyncStatus.SYNCED,
    ) -> int | None:
        """Insert a new DNS record with synchronization metadata.

        Args:
            zone_id: Zone database ID to attach the record to.
            record_name: Full FQDN (e.g. ``'www.example.com'``).
            record_type: DNS record type (``'A'`` or ``'AAAA'``).
            provider_record_id: Optional provider record identifier.
            ttl: Time-to-live in seconds (falls back to configured default).
            enabled: Whether the record starts enabled.
            managed: Whether DynDNS actively manages the record.
            sync_status: Initial synchronization state.

        Returns:
            Newly created record ID or ``None`` on failure.
        """
        resolved_ttl = ttl
        if resolved_ttl is None:
            resolved_ttl = (
                self.config.dns_default_ttl
                if getattr(self, "config", None) is not None
                else DNSDefaults.DEFAULT_TTL
            )
        sql = (
            "INSERT INTO records (zone_id, record_name, record_type, provider_record_id, ttl, "
            "enabled, managed, sync_status, last_synced_at, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
        )
        params = (
            zone_id,
            record_name,
            record_type,
            provider_record_id,
            resolved_ttl,
            1 if enabled else 0,
            1 if managed else 0,
            sync_status,
        )
        self.execute_update(sql, params)
        rows = self.execute_query(
            "SELECT id FROM records WHERE zone_id = ? AND record_name = ? AND record_type = ?",
            (zone_id, record_name, record_type),
        )
        return int(rows[0]["id"]) if rows else None

    def update_record_provider_id(self, record_id: int, provider_record_id: str) -> int:
        """Update a record's provider identifier only when it changed.

        Args:
            record_id: Record database ID.
            provider_record_id: Provider record identifier from the DNS API.

        Returns:
            Number of rows modified (0 or 1).
        """
        sql = (
            "UPDATE records SET provider_record_id = ?, updated_at = CURRENT_TIMESTAMP "
            "WHERE id = ? AND provider_record_id IS NOT ?"
        )
        return self.execute_update(sql, (provider_record_id, record_id, provider_record_id))

    def update_record_status(self, record_id: int, enabled: bool) -> int:
        """Enable or disable a DNS record.

        Args:
            record_id: Record database ID.
            enabled: Target enabled state.

        Returns:
            Number of rows modified (0 or 1).
        """
        sql = "UPDATE records SET enabled = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?"
        return self.execute_update(sql, (1 if enabled else 0, record_id))

    def update_record(self, record_id: int, **kwargs: Any) -> int:
        """Update permitted DNS record fields dynamically.

        Args:
            record_id: Record database ID.
            **kwargs: Subset of permitted record columns to modify.

        Returns:
            Number of rows modified (0 or 1).
        """
        allowed_fields = {
            "record_name",
            "record_type",
            "provider_record_id",
            "ttl",
            "enabled",
            "managed",
            "sync_status",
            "last_synced_at",
        }
        updates = {k: v for k, v in kwargs.items() if k in allowed_fields}
        if not updates:
            return 0
        if "enabled" in updates:
            updates["enabled"] = 1 if updates["enabled"] else 0
        if "managed" in updates:
            updates["managed"] = 1 if updates["managed"] else 0
        set_clause = ", ".join(f"{field} = ?" for field in updates)
        sql = f"UPDATE records SET {set_clause}, updated_at = CURRENT_TIMESTAMP WHERE id = ?"
        return self.execute_update(sql, (*updates.values(), record_id))

    def delete_record(self, record_id: int) -> int:
        """Delete a DNS record and cascade-remove its IP and history rows.

        Args:
            record_id: Record database ID to delete.

        Returns:
            Number of deleted record rows (0 or 1).
        """
        return self.execute_update("DELETE FROM records WHERE id = ?", (record_id,))

    def get_orphaned_records(self, zone_id: int | None = None) -> list[dict[str, Any]]:
        """Retrieve DNS records marked as ``orphaned`` on the provider.

        Args:
            zone_id: Optional zone ID filter.

        Returns:
            List of orphaned record dictionaries.
        """
        if zone_id is not None:
            sql = "SELECT * FROM records WHERE sync_status = ? AND zone_id = ? ORDER BY record_name"
            rows = self.execute_query(sql, (SyncStatus.ORPHANED, zone_id))
        else:
            sql = "SELECT * FROM records WHERE sync_status = ? ORDER BY zone_id, record_name"
            rows = self.execute_query(sql, (SyncStatus.ORPHANED,))
        return [dict(row) for row in rows]

    def update_sync_status(
        self,
        record_id: int,
        sync_status: str,
        last_synced_at: str | None = None,
    ) -> int:
        """Update synchronization state and optional sync timestamp for a record.

        Args:
            record_id: Record database ID.
            sync_status: New synchronization status string.
            last_synced_at: Optional synchronization timestamp string.

        Returns:
            Number of rows modified (0 or 1).
        """
        if last_synced_at:
            sql = (
                "UPDATE records SET sync_status = ?, last_synced_at = ?, "
                "updated_at = CURRENT_TIMESTAMP WHERE id = ?"
            )
            return self.execute_update(sql, (sync_status, last_synced_at, record_id))
        sql = "UPDATE records SET sync_status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?"
        return self.execute_update(sql, (sync_status, record_id))

    ############################################################################
    # IP ADDRESS STATE & DNS UPDATE AUDIT HISTORY
    ############################################################################

    def get_ip_address(self, record_id: int) -> dict[str, Any] | None:
        """Retrieve the currently recorded IP address for a DNS record.

        Args:
            record_id: Record database ID.

        Returns:
            Dictionary with ``ip_address`` and timestamps, or ``None``.
        """
        rows = self.execute_query(
            "SELECT ip_address, last_checked_at, last_changed_at FROM ip_addresses WHERE record_id = ?",
            (record_id,),
        )
        return dict(rows[0]) if rows else None

    def update_ip_address(
        self, record_id: int, ip_address: str, changed: bool = True
    ) -> None:
        """Insert or update a record's IP address only when the IP value changes.

        Args:
            record_id: Record database ID.
            ip_address: Detected or synced IP address string.
            changed: Retained for backward-compatible method signature.
        """
        _ = changed
        sql = (
            "INSERT INTO ip_addresses (record_id, ip_address, last_checked_at, last_changed_at) "
            "VALUES (?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP) "
            "ON CONFLICT(record_id) DO UPDATE SET "
            "ip_address = excluded.ip_address, "
            "last_checked_at = CURRENT_TIMESTAMP, "
            "last_changed_at = CURRENT_TIMESTAMP "
            "WHERE ip_addresses.ip_address IS NOT excluded.ip_address"
        )
        self.execute_update(sql, (record_id, ip_address))

    def log_dns_update(
        self,
        record_id: int,
        old_ip: str | None,
        new_ip: str,
        status: str = UpdateStatus.SUCCESS,
        error_message: str | None = None,
    ) -> None:
        """Append an audit log entry to ``dns_updates``.

        Args:
            record_id: Record database ID that was updated.
            old_ip: Previous IP address before the update attempt.
            new_ip: Target IP address for the update attempt.
            status: Outcome status (``success``, ``failed``, ``skipped``).
            error_message: Optional failure diagnostic message.
        """
        sql = (
            "INSERT INTO dns_updates (record_id, old_ip, new_ip, status, error_message, updated_at) "
            "VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)"
        )
        self.execute_update(sql, (record_id, old_ip, new_ip, status, error_message))

    def get_dns_update_history(
        self,
        record_id: int | None = None,
        zone_id: int | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Query recent DNS update audit entries ordered newest first.

        Args:
            record_id: Optional record ID filter.
            zone_id: Optional zone ID filter.
            limit: Maximum number of audit rows to return.

        Returns:
            List of DNS update history dictionaries.
        """
        if record_id is not None:
            sql = "SELECT * FROM dns_updates WHERE record_id = ? ORDER BY updated_at DESC LIMIT ?"
            rows = self.execute_query(sql, (record_id, limit))
        elif zone_id is not None:
            sql = (
                "SELECT du.* FROM dns_updates du JOIN records r ON du.record_id = r.id "
                "WHERE r.zone_id = ? ORDER BY du.updated_at DESC LIMIT ?"
            )
            rows = self.execute_query(sql, (zone_id, limit))
        else:
            sql = "SELECT * FROM dns_updates ORDER BY updated_at DESC LIMIT ?"
            rows = self.execute_query(sql, (limit,))
        return [dict(row) for row in rows]
