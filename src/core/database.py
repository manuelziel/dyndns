#!/usr/bin/env python3
"""SQLite database manager with connection pooling and schema migrations.

Composes ``DatabaseEngine``, ``ZoneRepositoryMixin``, and ``RecordRepositoryMixin``
into the unified thread-safe ``Database`` facade for DynDNS.

Typical usage:
    >>> db = Database('/var/lib/dyndns/dyndns.db')
    >>> zones = db.get_all_zones()

Author: Manuel Ziel
License: MIT
"""

################################################################################
# IMPORTS & DEPENDENCIES
################################################################################

import logging
import os
import queue
import sqlite3
import threading
from typing import Any

from .constants import AppPaths, DatabaseDefaults
from .db import DatabaseEngine, RecordRepositoryMixin, ZoneRepositoryMixin
from .encryption import EncryptionManager
from .exceptions import DatabaseError
from .ownership import ensure_service_ownership

################################################################################
# DATABASE FACADE CLASS
################################################################################


class Database(DatabaseEngine, ZoneRepositoryMixin, RecordRepositoryMixin):
    """SQLite database handler with re-entrant connection pooling.

    Provides thread-safe database operations using a connection pool with
    configurable size, atomic transactions, and WAL/RAM-cache PRAGMAs optimized
    for Linux daemons and SSD/SD-card longevity.

    Attributes:
        db_file: Path to the SQLite database file.
        max_connections: Maximum connections in the pool.
        logger: Logger instance for database operations.
        config: Configuration object reference.
    """

    DB_SCHEMA_VERSION: int = DatabaseDefaults.DB_SCHEMA_VERSION

    def __init__(
        self,
        db_file: str,
        max_connections: int = DatabaseDefaults.MAX_CONNECTIONS,
        logger: logging.Logger | None = None,
        config: Any | None = None,
    ) -> None:
        """Initialize database connection pool, encryption, and schema.

        Args:
            db_file: Path to SQLite database file (created if missing).
            max_connections: Maximum number of pooled connections.
            logger: Optional logger instance.
            config: Optional ``ConfigManager`` instance.

        Raises:
            DatabaseError: If pool initialization or schema migration fails.
        """
        self.db_file = db_file
        self.max_connections = max_connections
        self.logger = logger or logging.getLogger(__name__)
        self.config = config
        self._pool = queue.Queue(maxsize=max_connections)
        self._local = threading.local()

        key_path = (
            self.config.encryption_key_path
            if self.config is not None and hasattr(self.config, "encryption_key_path")
            else os.path.join(os.path.dirname(os.path.abspath(db_file)), AppPaths.ENCRYPTION_KEY_FILE)
        )
        self._encryption = EncryptionManager(key_path, self.logger)

        db_exists = os.path.exists(db_file)
        self._initialize_pool()
        if not db_exists:
            self.logger.info("Database does not exist. Creating a new one...")
            self.create_tables()
            self.execute_update(f"PRAGMA user_version = {self.DB_SCHEMA_VERSION}")
        else:
            self.run_migrations()

        for path in (db_file, f"{db_file}-wal", f"{db_file}-shm"):
            ensure_service_ownership(path, logger=self.logger)
        self.logger.info(f"Database initialized with connection pool (max: {max_connections})")

    def __del__(self) -> None:
        """Close all pooled database connections when garbage-collected."""
        self.close()

    ############################################################################
    # SCHEMA CREATION & INDEX MANAGEMENT
    ############################################################################

    def create_tables(self) -> None:
        """Create all DynDNS schema tables and performance indexes atomically."""
        with self.transaction():
            self._create_zone_and_record_tables()
            self._create_ip_and_history_tables()
            self._create_config_and_log_tables()
            self.create_indexes()

    def _create_zone_and_record_tables(self) -> None:
        """Create ``zones`` and ``records`` tables with foreign key cascades."""
        self.create_table(
            "zones",
            [
                ("id", "INTEGER PRIMARY KEY AUTOINCREMENT"),
                ("zone_name", "TEXT UNIQUE NOT NULL"),
                ("provider_zone_id", "TEXT"),
                ("enabled", "INTEGER DEFAULT 1"),
                ("created_at", "DATETIME DEFAULT CURRENT_TIMESTAMP"),
                ("updated_at", "DATETIME DEFAULT CURRENT_TIMESTAMP"),
            ],
        )
        self.create_table(
            "records",
            [
                ("id", "INTEGER PRIMARY KEY AUTOINCREMENT"),
                ("zone_id", "INTEGER NOT NULL REFERENCES zones(id) ON DELETE CASCADE"),
                ("record_name", "TEXT NOT NULL"),
                ("record_type", "TEXT NOT NULL"),
                ("provider_record_id", "TEXT"),
                ("ttl", "INTEGER DEFAULT 3600"),
                ("enabled", "INTEGER DEFAULT 1"),
                ("managed", "INTEGER DEFAULT 1"),
                ("sync_status", "TEXT DEFAULT 'synced'"),
                ("last_synced_at", "DATETIME"),
                ("created_at", "DATETIME DEFAULT CURRENT_TIMESTAMP"),
                ("updated_at", "DATETIME DEFAULT CURRENT_TIMESTAMP"),
            ],
            constraints=["UNIQUE (zone_id, record_name, record_type)"],
        )

    def _create_ip_and_history_tables(self) -> None:
        """Create ``ip_addresses`` and ``dns_updates`` audit history tables."""
        self.create_table(
            "ip_addresses",
            [
                ("id", "INTEGER PRIMARY KEY AUTOINCREMENT"),
                ("record_id", "INTEGER NOT NULL REFERENCES records(id) ON DELETE CASCADE"),
                ("ip_address", "TEXT NOT NULL"),
                ("last_checked_at", "DATETIME DEFAULT CURRENT_TIMESTAMP"),
                ("last_changed_at", "DATETIME DEFAULT CURRENT_TIMESTAMP"),
            ],
            constraints=["UNIQUE (record_id)"],
        )
        self.create_table(
            "dns_updates",
            [
                ("id", "INTEGER PRIMARY KEY AUTOINCREMENT"),
                ("record_id", "INTEGER NOT NULL REFERENCES records(id) ON DELETE CASCADE"),
                ("old_ip", "TEXT"),
                ("new_ip", "TEXT"),
                ("status", "TEXT NOT NULL"),
                ("error_message", "TEXT"),
                ("updated_at", "DATETIME DEFAULT CURRENT_TIMESTAMP"),
            ],
        )

    def _create_config_and_log_tables(self) -> None:
        """Create ``dyndns_config`` and ``app_config`` tables."""
        self.create_table(
            "dyndns_config",
            [
                ("id", "INTEGER PRIMARY KEY AUTOINCREMENT"),
                ("zone_id", "INTEGER NOT NULL REFERENCES zones(id) ON DELETE CASCADE"),
                ("bulk_id", "TEXT UNIQUE NOT NULL"),
                ("api_key", "TEXT NOT NULL"),
                ("update_url", "TEXT"),
                ("description", "TEXT"),
                ("domains", "TEXT NOT NULL"),
                ("enabled", "INTEGER DEFAULT 1"),
                ("created_at", "DATETIME DEFAULT CURRENT_TIMESTAMP"),
                ("updated_at", "DATETIME DEFAULT CURRENT_TIMESTAMP"),
            ],
        )
        self.create_table(
            "app_config",
            [
                ("id", "INTEGER PRIMARY KEY AUTOINCREMENT"),
                ("key", "TEXT UNIQUE NOT NULL"),
                ("value", "TEXT"),
                ("created_at", "DATETIME DEFAULT CURRENT_TIMESTAMP"),
            ],
        )

    def create_indexes(self) -> None:
        """Create SQLite indexes idempotently for high-traffic queries."""
        self.logger.debug("Creating database indexes...")
        indexes = (
            ("idx_records_zone_enabled", "records", "zone_id, enabled"),
            ("idx_records_provider_id", "records", "provider_record_id"),
            ("idx_dns_updates_record_time", "dns_updates", "record_id, updated_at"),
            ("idx_dyndns_config_zone_id", "dyndns_config", "zone_id"),
        )
        for index_name, table_name, columns in indexes:
            self.execute_update(
                f"CREATE INDEX IF NOT EXISTS {index_name} ON {table_name} ({columns});"
            )

    ############################################################################
    # SCHEMA VERSIONING & MIGRATIONS
    ############################################################################

    def get_schema_version(self) -> int:
        """Read ``PRAGMA user_version`` from the SQLite database.

        Returns:
            Current integer schema version (``0`` if unversioned).
        """
        try:
            rows = self.execute_query("PRAGMA user_version")
            return int(rows[0][0]) if rows else DatabaseDefaults.UNVERSIONED_SCHEMA
        except DatabaseError as exc:
            self.logger.error(f"Failed to read schema version: {exc}")
            return DatabaseDefaults.UNVERSIONED_SCHEMA

    def run_migrations(self) -> None:
        """Verify current schema version and apply incremental migrations.

        Raises:
            DatabaseError: If schema migration fails.
        """
        current = self.get_schema_version()
        expected = DatabaseDefaults.DB_SCHEMA_VERSION
        if current == DatabaseDefaults.UNVERSIONED_SCHEMA:
            if self._init_unversioned_schema_if_empty(expected):
                return
            self.logger.info("Legacy unversioned database detected. Setting base schema version to 1...")
            current = 1
        if current >= expected:
            self.create_indexes()
            return
        self.logger.info(f"Applying schema migrations (v{current} -> v{expected})...")
        try:
            with self.transaction():
                self.create_tables()
                self._apply_schema_migrations(current, expected)
                self.create_indexes()
            self.logger.info(f"Successfully migrated schema to v{expected}")
        except (DatabaseError, sqlite3.Error) as exc:
            self.logger.error(f"Database migration failed: {exc}")
            raise DatabaseError(f"Database migration failed: {exc}") from exc

    def _init_unversioned_schema_if_empty(self, expected: int) -> bool:
        """Initialize fresh tables when an unversioned database file is empty.

        Args:
            expected: Target schema version to stamp.

        Returns:
            True if a fresh schema was initialized, False if legacy tables exist.
        """
        try:
            rows = self.execute_query(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='zones'"
            )
            if not rows:
                self.logger.info("Unversioned database detected. Initializing schema tables...")
                self.create_tables()
                self.execute_update(f"PRAGMA user_version = {expected}")
                return True
        except (DatabaseError, sqlite3.Error):
            pass
        return False

    def _apply_schema_migrations(self, current: int, expected: int) -> None:
        """Execute incremental ``ALTER TABLE`` statements up to ``expected``.

        Args:
            current: Current schema version in SQLite.
            expected: Target schema version required by the application.
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if current < 2:
                self._execute_migration_statements(
                    cursor,
                    "v2",
                    [
                        "ALTER TABLE records ADD COLUMN managed INTEGER DEFAULT 1",
                        "ALTER TABLE records ADD COLUMN sync_status TEXT DEFAULT 'synced'",
                        "ALTER TABLE records ADD COLUMN last_synced_at DATETIME",
                    ],
                )
            if current < 3:
                self._execute_migration_statements(
                    cursor,
                    "v3",
                    [
                        "ALTER TABLE dyndns_config ADD COLUMN update_url TEXT",
                        "ALTER TABLE dyndns_config ADD COLUMN description TEXT",
                    ],
                )
            cursor.execute(f"PRAGMA user_version = {expected}")
            self._commit(conn)

    def _execute_migration_statements(
        self, cursor: sqlite3.Cursor, version_label: str, statements: list[str]
    ) -> None:
        """Execute migration ``ALTER TABLE`` statements tolerating existing columns.

        Args:
            cursor: Active SQLite cursor.
            version_label: Target schema version label for logging.
            statements: Ordered list of ``ALTER TABLE`` SQL strings.
        """
        self.logger.debug(f"Migrating schema to {version_label}...")
        for col_sql in statements:
            try:
                cursor.execute(col_sql)
            except sqlite3.OperationalError as exc:
                self.logger.debug(f"Migration notice for {version_label} ({col_sql}): {exc}")

    def check_schema_compatibility(self) -> bool:
        """Verify schema compatibility and migrate older versions automatically.

        Returns:
            True when compatible or migrated, False on newer/incompatible schema.
        """
        db_version = self.get_schema_version()
        expected = DatabaseDefaults.DB_SCHEMA_VERSION
        if db_version < expected:
            try:
                self.run_migrations()
                return True
            except DatabaseError as exc:
                self.logger.error(f"Automated migration failed: {exc}")
                return False
        if db_version > expected:
            self.logger.error(
                f"Schema mismatch! DB is v{db_version}, but app requires v{expected}."
            )
            return False
        return True
