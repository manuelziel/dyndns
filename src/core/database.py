#!/usr/bin/env python3
"""SQLite database manager with connection pooling.

This module provides thread-safe database operations using a connection pool.
Supports multi-threaded applications with automatic connection management.

Typical usage:
    >>> db = Database('/var/lib/dyndns/dyndns.db')
    >>> with db.get_connection() as conn:
    ...     cursor = conn.cursor()
    ...     cursor.execute('SELECT * FROM domains')

Author: Manuel Ziel
License: MIT
"""

################################################################################
# IMPORTS & DEPENDENCIES
################################################################################

from contextlib import contextmanager
import json
import logging
import os
import queue
import shutil
import sqlite3
import threading
from typing import Any, Dict, Generator, List, Optional, Tuple

from .encryption import EncryptionManager
from .constants import SyncStatus, UpdateStatus, DatabaseDefaults, StorageConstants
from .exceptions import DatabaseError, DatabaseLockedError, EncryptionError
from .ownership import ensure_service_ownership


################################################################################
# DATABASE CLASS - SQLite with Connection Pooling
################################################################################

class Database:
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
        logger: Optional[Any] = None,
        config: Optional[Any] = None,
    ) -> None:
        """Initialize database with connection pooling and schema verification.

        Args:
            db_file: Path to SQLite database file. Created if not exists.
            max_connections: Maximum number of connections in pool. Defaults to 5.
            logger: Logger instance for logging. Creates default if None.
            config: Configuration object for additional settings.

        Raises:
            DatabaseError: If connection pool initialization or migration fails.
        """
        self.db_file = db_file
        self.max_connections = max_connections
        self.logger = logger or logging.getLogger(__name__)
        self.config = config
        self._pool: queue.Queue[sqlite3.Connection] = queue.Queue(maxsize=max_connections)
        self._local = threading.local()
        self._encryption = EncryptionManager(self.config.encryption_key_path, self.logger)

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
        """Close all database connections when the object is destroyed."""
        self.close()


    ############################################################################
    # PUBLIC CONNECTION & TRANSACTION INTERFACE - Context Managers
    ############################################################################

    @contextmanager
    def get_connection(self) -> Generator[sqlite3.Connection, None, None]:
        """Get a connection from the pool as a re-entrant context manager.

        Yields:
            sqlite3.Connection: Active database connection from the pool.

        Raises:
            DatabaseLockedError: If the database is locked beyond busy_timeout.
            DatabaseError: If pool is exhausted or a database error occurs.
        """
        if getattr(self._local, "active_conn", None) is not None:
            try:
                yield self._local.active_conn
            except sqlite3.Error as exc:
                self._raise_database_error(exc)
            return
        conn = self._acquire_valid_connection()
        self._local.active_conn = conn
        try:
            yield conn
        except sqlite3.Error as exc:
            self._safe_rollback(conn)
            self._raise_database_error(exc)
        except BaseException:
            self._safe_rollback(conn)
            raise
        finally:
            self._release_connection(conn)


    @contextmanager
    def transaction(self) -> Generator[None, None, None]:
        """Execute a block of operations inside a single atomic transaction.

        Yields:
            None

        Raises:
            DatabaseLockedError: If the database is locked beyond busy_timeout.
            DatabaseError: If pool is exhausted or a database error occurs.
        """
        if getattr(self._local, "in_transaction", False):
            yield
            return
        with self.get_connection() as conn:
            self._local.in_transaction = True
            try:
                if not conn.in_transaction:
                    conn.execute("BEGIN IMMEDIATE")
                yield
                if conn.in_transaction:
                    conn.commit()
            except BaseException:
                self._safe_rollback(conn)
                raise
            finally:
                self._local.in_transaction = False


    ############################################################################
    # QUERY EXECUTION METHODS - Public Database Operations
    ############################################################################

    def execute_query(self, query: str, params: Optional[Tuple[Any, ...]] = None) -> List[sqlite3.Row]:
        """Execute a SELECT query and return results.

        Thread-safe method to execute read operations.

        Args:
            query: SQL SELECT statement to execute.
            params: Optional query parameters for parameterized queries.

        Returns:
            List of sqlite3.Row objects containing query results.

        Raises:
            DatabaseError: If database query execution fails.
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params or ())
            return cursor.fetchall()


    def execute_update(self, query: str, params: Optional[Tuple[Any, ...]] = None) -> int:
        """Execute an INSERT, UPDATE, DELETE, or DDL query.

        Thread-safe method to execute write operations with automatic commit.

        Args:
            query: SQL modification statement to execute.
            params: Optional query parameters for parameterized queries.

        Returns:
            Number of rows affected by the operation.

        Raises:
            DatabaseError: If database update execution fails.
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params or ())
            self._commit(conn)
            return cursor.rowcount


    def execute_many(self, query: str, params_list: List[Tuple[Any, ...]]) -> int:
        """Execute a query with multiple parameter sets.

        Thread-safe batch operation for efficient bulk inserts or updates.

        Args:
            query: SQL statement to execute repeatedly.
            params_list: List of parameter tuples for each execution.

        Returns:
            Total number of rows affected by all operations.

        Raises:
            DatabaseError: If database batch update execution fails.
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.executemany(query, params_list)
            self._commit(conn)
            return cursor.rowcount


    ############################################################################
    # RESOURCE MANAGEMENT & STORAGE DIAGNOSTICS
    ############################################################################

    def close(self) -> None:
        """Close all connections in the pool and release resources."""
        pool = getattr(self, "_pool", None)
        if pool is None:
            return
        try:
            while not pool.empty():
                try:
                    self._pool.get_nowait().close()
                except queue.Empty:
                    break
                except (sqlite3.Error, OSError) as exc:
                    if self.logger:
                        self.logger.warning(f"Error closing connection: {exc}")
            if self.logger:
                self.logger.debug("All database connections closed")
        except (sqlite3.Error, OSError) as exc:
            if self.logger:
                self.logger.error(f"Error during database cleanup: {exc}")


    def get_storage_stats(self) -> Dict[str, Any]:
        """Collect database file sizes, dynamic table row counts, and host disk usage.

        Returns:
            Dictionary with 'database' and 'disk' metrics for system diagnostics.
        """
        db_path = os.path.abspath(self.db_file)
        db_size = os.path.getsize(db_path) if os.path.exists(db_path) else 0
        wal_size = os.path.getsize(f"{db_path}-wal") if os.path.exists(f"{db_path}-wal") else 0
        shm_size = os.path.getsize(f"{db_path}-shm") if os.path.exists(f"{db_path}-shm") else 0
        total_size = db_size + wal_size + shm_size
        db_dir = os.path.dirname(db_path) or "."
        usage = shutil.disk_usage(db_dir if os.path.exists(db_dir) else ".")
        used_pct = round(
            (usage.used / usage.total) * StorageConstants.PERCENTAGE_FACTOR, StorageConstants.DISK_PERCENT_DECIMALS
        ) if usage.total > 0 else 0.0
        return {
            "database": {
                "path": db_path, "db_size_bytes": db_size, "db_size_human": self._format_bytes(db_size),
                "wal_size_bytes": wal_size, "wal_size_human": self._format_bytes(wal_size),
                "shm_size_bytes": shm_size, "shm_size_human": self._format_bytes(shm_size),
                "total_size_bytes": total_size, "total_size_human": self._format_bytes(total_size),
                "row_counts": self._get_table_row_counts(),
            },
            "disk": {
                "mount_point": db_dir, "free_bytes": usage.free, "free_human": self._format_bytes(usage.free),
                "total_bytes": usage.total, "total_human": self._format_bytes(usage.total), "used_percent": used_pct,
            },
        }


    ############################################################################
    # TABLE MANAGEMENT - Schema Creation and Management
    ############################################################################

    def create_tables(self) -> None:
        """Create DynDNS database tables.

        Creates all required tables for the application including zones,
        records, IP addresses, update history, and configuration tables.
        Thread-safe operation supporting multi-subdomain architecture.
        """
        with self.transaction():
            self._create_zone_and_record_tables()
            self._create_ip_and_history_tables()
            self._create_config_and_log_tables()
            self.create_indexes()


    def _create_zone_and_record_tables(self) -> None:
        """Create zones and DNS records tables."""
        self.create_table("zones", [
            ("id", "INTEGER PRIMARY KEY AUTOINCREMENT"),
            ("zone_name", "TEXT UNIQUE NOT NULL"),              # Root domain: 'website.com'
            ("provider_zone_id", "TEXT"),                       # Provider Zone ID (from API, can be NULL until fetched)
            ("enabled", "INTEGER DEFAULT 1"),                   # 1=active, 0=disabled
            ("created_at", "DATETIME DEFAULT CURRENT_TIMESTAMP"),
            ("updated_at", "DATETIME DEFAULT CURRENT_TIMESTAMP")
        ])

        self.create_table("records", [
            ("id", "INTEGER PRIMARY KEY AUTOINCREMENT"),
            ("zone_id", "INTEGER NOT NULL"),                    # Foreign Key to zones
            ("record_name", "TEXT NOT NULL"),                   # Full FQDN: 'www.website.com', 'api.blog.website.com'
            ("record_type", "TEXT NOT NULL"),                   # 'A' or 'AAAA'
            ("provider_record_id", "TEXT"),                     # Provider Record ID (from API)
            ("ttl", "INTEGER DEFAULT 3600"),                    # Time to live (recommended: 3600)
            ("enabled", "INTEGER DEFAULT 1"),                   # 1=active, 0=disabled
            ("managed", "INTEGER DEFAULT 1"),                   # 1=managed by us, 0=read-only observation
            ("sync_status", "TEXT DEFAULT 'synced'"),           # 'synced', 'local_only', 'orphaned', 'conflict'
            ("last_synced_at", "DATETIME"),                     # Last provider synchronization (NULL=never)
            ("created_at", "DATETIME DEFAULT CURRENT_TIMESTAMP"),
            ("updated_at", "DATETIME DEFAULT CURRENT_TIMESTAMP"),
            ("FOREIGN KEY (zone_id)", "REFERENCES zones(id) ON DELETE CASCADE"),
            ("UNIQUE (zone_id, record_name, record_type)", "")  # Unique constraint
        ])


    def _create_ip_and_history_tables(self) -> None:
        """Create IP addresses and DNS update audit history tables."""
        self.create_table("ip_addresses", [
            ("id", "INTEGER PRIMARY KEY AUTOINCREMENT"),
            ("record_id", "INTEGER NOT NULL"),                  # Foreign Key to records
            ("ip_address", "TEXT NOT NULL"),                    # IPv4 or IPv6 address
            ("last_checked_at", "DATETIME DEFAULT CURRENT_TIMESTAMP"),
            ("last_changed_at", "DATETIME DEFAULT CURRENT_TIMESTAMP"),
            ("FOREIGN KEY (record_id)", "REFERENCES records(id) ON DELETE CASCADE"),
            ("UNIQUE (record_id)", "")                          # One IP per record
        ])

        self.create_table("dns_updates", [
            ("id", "INTEGER PRIMARY KEY AUTOINCREMENT"),
            ("record_id", "INTEGER NOT NULL"),                  # Foreign Key to records
            ("old_ip", "TEXT"),
            ("new_ip", "TEXT"),
            ("status", "TEXT NOT NULL"),                        # 'success', 'failed', 'skipped'
            ("error_message", "TEXT"),
            ("updated_at", "DATETIME DEFAULT CURRENT_TIMESTAMP"),
            ("FOREIGN KEY (record_id)", "REFERENCES records(id) ON DELETE CASCADE")
        ])


    def _create_config_and_log_tables(self) -> None:
        """Create DynDNS configuration and application configuration tables."""
        self.create_table("dyndns_config", [
            ("id", "INTEGER PRIMARY KEY AUTOINCREMENT"),
            ("zone_id", "INTEGER NOT NULL"),                    # Foreign Key to zones
            ("bulk_id", "TEXT UNIQUE NOT NULL"),                # Provider bulkId (Prefix)
            ("api_key", "TEXT NOT NULL"),                       # API Key (Encryption)
            ("update_url", "TEXT"),                             # Provider updateUrl
            ("description", "TEXT"),                            # "My DynamicDns"
            ("domains", "TEXT NOT NULL"),                       # JSON array: ["website.com", "www.website.com"]
            ("enabled", "INTEGER DEFAULT 1"),                   # 1=DynDNS active, 0=disabled
            ("created_at", "DATETIME DEFAULT CURRENT_TIMESTAMP"),
            ("updated_at", "DATETIME DEFAULT CURRENT_TIMESTAMP"),
            ("FOREIGN KEY (zone_id)", "REFERENCES zones(id) ON DELETE CASCADE")
        ])

        self.create_table("app_config", [
            ("id", "INTEGER PRIMARY KEY AUTOINCREMENT"),
            ("key", "TEXT UNIQUE NOT NULL"),
            ("value", "TEXT"),
            ("created_at", "DATETIME DEFAULT CURRENT_TIMESTAMP"),
        ])


    def create_table(self, table_name: str, columns: List[Tuple[str, str]]) -> None:
        """Create a table if it does not exist.

        Thread-safe method to create database tables idempotently.

        Args:
            table_name: Alphanumeric/underscore name of the table to create.
            columns: List of (column_name, type_definition) tuples.

        Raises:
            DatabaseError: If table_name contains invalid characters or DDL fails.
        """
        if not table_name or not table_name.replace("_", "").isalnum():
            raise DatabaseError(f"Invalid SQLite table identifier: {table_name}")
        columns_sql = ", ".join([f"{name} {type_}".strip() for name, type_ in columns])
        self.execute_update(f"CREATE TABLE IF NOT EXISTS {table_name} ({columns_sql});")


    def create_indexes(self) -> None:
        """Create database indexes for performance optimization.

        Thread-safe method to idempotently create necessary indexes on high-traffic queries.
        """
        self.logger.debug("Creating database indexes...")
        indexes = [
            ("idx_records_zone_enabled", "records", "zone_id, enabled"),
            ("idx_records_provider_id", "records", "provider_record_id"),
            ("idx_dns_updates_record_time", "dns_updates", "record_id, updated_at"),
            ("idx_dyndns_config_zone_id", "dyndns_config", "zone_id"),
        ]
        for index_name, table_name, columns in indexes:
            sql = f"CREATE INDEX IF NOT EXISTS {index_name} ON {table_name} ({columns});"
            self.execute_update(sql)


    def get_schema_version(self) -> int:
        """Get the current schema version (PRAGMA user_version) of the database.

        Returns:
            int: Current integer schema version (0 if unversioned).
        """
        try:
            rows = self.execute_query("PRAGMA user_version")
            return int(rows[0][0]) if rows else DatabaseDefaults.UNVERSIONED_SCHEMA
        except DatabaseError as exc:
            self.logger.error(f"Failed to read schema version: {exc}")
            return DatabaseDefaults.UNVERSIONED_SCHEMA


    def run_migrations(self) -> None:
        """Check current schema version and execute required SQL migrations.

        Raises:
            DatabaseError: If database migrations fail.
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
        except (DatabaseError, sqlite3.Error) as e:
            self.logger.error(f"Database migration failed: {e}")
            raise DatabaseError(f"Database migration failed: {e}") from e


    def _init_unversioned_schema_if_empty(self, expected: int) -> bool:
        """Initialize schema tables if database is completely new and unversioned.

        Args:
            expected: Target schema version to set.

        Returns:
            True if a fresh schema was initialized, False if legacy tables exist.
        """
        try:
            rows = self.execute_query("SELECT name FROM sqlite_master WHERE type='table' AND name='zones'")
            if not rows:
                self.logger.info("Unversioned database detected. Initializing schema tables...")
                self.create_tables()
                self.execute_update(f"PRAGMA user_version = {expected}")
                return True
        except (DatabaseError, sqlite3.Error):
            pass
        return False


    def _apply_schema_migrations(self, current: int, expected: int) -> None:
        """Execute incremental ALTER TABLE statements up to expected schema version.

        Args:
            current: Current database schema version.
            expected: Target database schema version.
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if current < 2:
                self._execute_migration_statements(cursor, "v2", [
                    "ALTER TABLE records ADD COLUMN managed INTEGER DEFAULT 1",
                    "ALTER TABLE records ADD COLUMN sync_status TEXT DEFAULT 'synced'",
                    "ALTER TABLE records ADD COLUMN last_synced_at DATETIME",
                ])
            if current < 3:
                self._execute_migration_statements(cursor, "v3", [
                    "ALTER TABLE dyndns_config ADD COLUMN update_url TEXT",
                    "ALTER TABLE dyndns_config ADD COLUMN description TEXT",
                ])
            cursor.execute(f"PRAGMA user_version = {expected}")
            conn.commit()


    def _execute_migration_statements(
        self, cursor: sqlite3.Cursor, version_label: str, statements: List[str]
    ) -> None:
        """Execute a list of SQL migration statements, ignoring duplicate column errors.

        Args:
            cursor: Active SQLite cursor.
            version_label: Schema version label for debug logging (e.g., 'v2').
            statements: List of SQL ALTER TABLE statements to execute.
        """
        self.logger.debug(f"Migrating schema to {version_label}...")
        for col_sql in statements:
            try:
                cursor.execute(col_sql)
            except sqlite3.OperationalError as e:
                self.logger.debug(f"Migration notice for {version_label} ({col_sql}): {e}")


    def check_schema_compatibility(self) -> bool:
        """Check if database schema matches expected version and migrate if needed.

        Returns:
            bool: True if compatible or migrated successfully, False otherwise.
        """
        db_version = self.get_schema_version()
        expected = DatabaseDefaults.DB_SCHEMA_VERSION

        if db_version < expected:
            try:
                self.run_migrations()
                return True
            except DatabaseError as e:
                self.logger.error(f"Automated migration failed: {e}")
                return False

        if db_version > expected:
            self.logger.error(f"Schema mismatch! DB is v{db_version}, but app requires v{expected}.")
            return False

        return True


    ############################################################################
    # APPLICATION-SPECIFIC METHODS - Configuration Management
    ############################################################################

    def get_config_by_key(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """Get configuration value by key.

        Thread-safe method to retrieve application configuration values.

        Args:
            key: Configuration key to retrieve.
            default: Default value if key not found. Defaults to None.

        Returns:
            Configuration value string or default if not found.
        """
        rows = self.execute_query("SELECT value FROM app_config WHERE key = ?", (key,))
        return rows[0]["value"] if rows else default


    def set_config_by_key(self, key: str, value: str) -> None:
        """Insert or update a configuration key-value pair atomically.

        Args:
            key: Configuration key to set.
            value: Configuration value to store.
        """
        sql = (
            "INSERT INTO app_config (key, value) VALUES (?, ?) ON CONFLICT(key) "
            "DO UPDATE SET value = excluded.value WHERE app_config.value IS NOT excluded.value"
        )
        self.execute_update(sql, (key, value))


    def delete_config_by_key(self, key: str) -> bool:
        """Delete configuration entry by key.

        Thread-safe method to remove application configuration entries.

        Args:
            key: Configuration key to delete.

        Returns:
            True if entry was deleted, False if key not found.
        """
        return self.execute_update("DELETE FROM app_config WHERE key = ?", (key,)) > 0


    ############################################################################
    # ZONE MANAGEMENT - DNS Zones (Root Domains)
    ############################################################################
    
    def get_zone_by_id(self, zone_id: int) -> Optional[Dict[str, Any]]:
        """Get zone by database ID.

        Args:
            zone_id: Zone database ID to retrieve.

        Returns:
            Zone dictionary or None if not found.
        """
        rows = self.execute_query("SELECT * FROM zones WHERE id = ?", (zone_id,))
        return dict(rows[0]) if rows else None
    

    def get_zone_by_name(self, zone_name: str) -> Optional[Dict[str, Any]]:
        """Get zone by domain name.

        Args:
            zone_name: Zone domain name to retrieve.

        Returns:
            Zone dictionary or None if not found.
        """
        rows = self.execute_query("SELECT * FROM zones WHERE zone_name = ?", (zone_name,))
        return dict(rows[0]) if rows else None
    

    def get_all_zones(self) -> List[Dict[str, Any]]:
        """Get all zones ordered by name.

        Returns:
            List of all zone dictionaries.
        """
        rows = self.execute_query("SELECT * FROM zones ORDER BY zone_name")
        return [dict(row) for row in rows]
    

    def get_all_enabled_zones(self) -> List[Dict[str, Any]]:
        """Get all enabled zones ordered by name.

        Returns:
            List of all enabled zone dictionaries.
        """
        rows = self.execute_query("SELECT * FROM zones WHERE enabled = 1 ORDER BY zone_name")
        return [dict(row) for row in rows]
    

    def add_zone(self, zone_name: str, provider_zone_id: Optional[str] = None, enabled: bool = True) -> Optional[int]:
        """Add a new DNS zone.

        Args:
            zone_name: Zone domain name (e.g., 'example.com').
            provider_zone_id: Provider's zone identifier from API.
            enabled: Whether zone is enabled. Defaults to True.

        Returns:
            New zone ID or None on failure.
        """
        enabled_int = 1 if enabled else 0
        sql = """INSERT INTO zones (zone_name, provider_zone_id, enabled, created_at, updated_at)
                 VALUES (?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"""
        self.execute_update(sql, (zone_name, provider_zone_id, enabled_int))
        
        rows = self.execute_query("SELECT id FROM zones WHERE zone_name = ?", (zone_name,))
        return rows[0]["id"] if rows else None
    

    def update_zone_status(self, zone_id: int, enabled: bool) -> int:
        """Enable or disable a DNS zone.

        Args:
            zone_id: Zone database ID to update.
            enabled: New enabled state.

        Returns:
            Number of rows affected (0 or 1).
        """
        sql = """UPDATE zones SET enabled = ?, updated_at = CURRENT_TIMESTAMP 
                 WHERE id = ?"""
        return self.execute_update(sql, (1 if enabled else 0, zone_id))
    

    def update_zone(self, zone_id: int, **kwargs: Any) -> int:
        """Update zone fields.

        Args:
            zone_id: Zone database ID to update.
            **kwargs: Fields to update (zone_name, provider_zone_id, enabled).

        Returns:
            Number of rows affected (0 or 1).
        """
        allowed_fields = {'zone_name', 'provider_zone_id', 'enabled'}
        updates = {k: v for k, v in kwargs.items() if k in allowed_fields}
        
        if not updates:
            return 0
        
        if 'enabled' in updates:
            updates['enabled'] = 1 if updates['enabled'] else 0
        
        set_clause = ", ".join(f"{field} = ?" for field in updates.keys())
        set_clause += ", updated_at = CURRENT_TIMESTAMP"
        
        sql = f"UPDATE zones SET {set_clause} WHERE id = ?"
        
        values = list(updates.values()) + [zone_id]
        return self.execute_update(sql, tuple(values))
    

    def delete_zone(self, zone_id: int) -> int:
        """Delete a zone and all related data.

        Cascading delete removes zone, records, IP addresses, update history,
        and DynDNS configuration associated with this zone.

        Args:
            zone_id: Zone database ID to delete.

        Returns:
            Number of zones deleted (0 or 1).
        """
        sql = "DELETE FROM zones WHERE id = ?"
        deleted = self.execute_update(sql, (zone_id,))
        self.delete_config_by_key(f"{DatabaseDefaults.DYNDNS_BUNDLE_ID_PREFIX}{zone_id}")
        return deleted
    

    ############################################################################
    # RECORD MANAGEMENT - DNS Records (Root + Subdomains)
    ############################################################################
    
    def get_record_by_id(self, record_id: int) -> Optional[Dict[str, Any]]:
        """Get DNS record by database ID.

        Args:
            record_id: Record database ID to retrieve.

        Returns:
            Record dictionary or None if not found.
        """
        rows = self.execute_query("SELECT * FROM records WHERE id = ?", (record_id,))
        return dict(rows[0]) if rows else None
    

    def get_records_by_zone(self, zone_id: int, enabled_only: bool = True) -> List[Dict[str, Any]]:
        """Get all DNS records for a zone with their stored IP metadata.

        Args:
            zone_id: Zone database ID to filter by.
            enabled_only: If True, only return enabled records. Defaults to True.

        Returns:
            List of record dictionaries ordered by name and type.
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
    

    def get_record_by_name_and_type(self, zone_id: int, record_name: str, record_type: str) -> Optional[Dict[str, Any]]:
        """Get a specific record by FQDN and type.

        Args:
            zone_id: Zone database ID to search in.
            record_name: Full FQDN (e.g., 'www.example.com').
            record_type: DNS record type ('A' or 'AAAA').

        Returns:
            Record dictionary or None if not found.
        """
        sql = "SELECT * FROM records WHERE zone_id = ? AND record_name = ? AND record_type = ?"
        rows = self.execute_query(sql, (zone_id, record_name, record_type))
        return dict(rows[0]) if rows else None
    

    def add_record(self, zone_id: int, record_name: str, record_type: str, provider_record_id: Optional[str] = None, 
                   ttl: Optional[int] = None, enabled: bool = True, managed: bool = True, sync_status: str = SyncStatus.SYNCED) -> Optional[int]:
        """Add a new DNS record with sync tracking.

        Args:
            zone_id: Zone database ID to add record to.
            record_name: Full FQDN (e.g., 'www.example.com').
            record_type: DNS record type ('A' or 'AAAA').
            provider_record_id: Provider's record identifier. Defaults to None.
            ttl: Time to live in seconds. Uses config default if None.
            enabled: Whether record is enabled. Defaults to True.
            managed: Whether record is managed by DynDNS. Defaults to True.
            sync_status: Initial sync status. Defaults to SyncStatus.SYNCED.

        Returns:
            New record ID or None on failure.
        """
        if ttl is None:
            ttl = self.config.dns_default_ttl
        
        enabled_int = 1 if enabled else 0
        managed_int = 1 if managed else 0
        sql = """INSERT INTO records (zone_id, record_name, record_type, provider_record_id, ttl, 
                                      enabled, managed, sync_status, last_synced_at, created_at, updated_at)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"""
        self.execute_update(sql, (zone_id, record_name, record_type, provider_record_id, ttl, enabled_int, managed_int, sync_status))
        
        rows = self.execute_query(
            "SELECT id FROM records WHERE zone_id = ? AND record_name = ? AND record_type = ?",
            (zone_id, record_name, record_type)
        )
        return rows[0]["id"] if rows else None
    

    def update_record_provider_id(self, record_id: int, provider_record_id: str) -> int:
        """Update Provider Record ID if changed.

        Args:
            record_id: Record database ID to update.
            provider_record_id: Provider's record identifier from API.

        Returns:
            Number of rows affected (0 or 1).
        """
        sql = (
            "UPDATE records SET provider_record_id = ?, updated_at = CURRENT_TIMESTAMP "
            "WHERE id = ? AND provider_record_id IS NOT ?"
        )
        return self.execute_update(sql, (provider_record_id, record_id, provider_record_id))
    

    def update_record_status(self, record_id: int, enabled: bool) -> int:
        """Enable or disable a DNS record.

        Args:
            record_id: Record database ID to update.
            enabled: New enabled state.

        Returns:
            Number of rows affected (0 or 1).
        """
        sql = "UPDATE records SET enabled = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?"
        return self.execute_update(sql, (1 if enabled else 0, record_id))
    

    def update_record(self, record_id: int, **kwargs: Any) -> int:
        """Update DNS record fields including sync tracking.

        Args:
            record_id: Record database ID to update.
            **kwargs: Fields to update (record_name, record_type, provider_record_id,
                ttl, enabled, managed, sync_status, last_synced_at).

        Returns:
            Number of rows affected (0 or 1).
        """
        allowed_fields = {'record_name', 'record_type', 'provider_record_id', 'ttl', 'enabled', 
                          'managed', 'sync_status', 'last_synced_at'}
        updates = {k: v for k, v in kwargs.items() if k in allowed_fields}
        
        if not updates:
            return 0
        
        if 'enabled' in updates:
            updates['enabled'] = 1 if updates['enabled'] else 0
        
        if 'managed' in updates:
            updates['managed'] = 1 if updates['managed'] else 0
        
        set_clause = ", ".join(f"{field} = ?" for field in updates.keys())
        set_clause += ", updated_at = CURRENT_TIMESTAMP"
        
        sql = f"UPDATE records SET {set_clause} WHERE id = ?"
        
        values = list(updates.values()) + [record_id]
        return self.execute_update(sql, tuple(values))
    

    def delete_record(self, record_id: int) -> int:
        """Delete a DNS record and all related data.

        Cascading delete removes record, IP addresses, and update history.

        Args:
            record_id: Record database ID to delete.

        Returns:
            Number of records deleted (0 or 1).
        """
        sql = "DELETE FROM records WHERE id = ?"
        return self.execute_update(sql, (record_id,))
    

    def get_orphaned_records(self, zone_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """Get all orphaned records.

        Args:
            zone_id: Optional zone ID to filter by. Returns all if None.

        Returns:
            List of orphaned record dictionaries.
        """
        if zone_id:
            sql = "SELECT * FROM records WHERE sync_status = ? AND zone_id = ? ORDER BY record_name"
            rows = self.execute_query(sql, (SyncStatus.ORPHANED, zone_id))
        else:
            sql = "SELECT * FROM records WHERE sync_status = ? ORDER BY zone_id, record_name"
            rows = self.execute_query(sql, (SyncStatus.ORPHANED,))
        return [dict(row) for row in rows]
    

    def update_sync_status(self, record_id: int, sync_status: str, last_synced_at: Optional[str] = None) -> int:
        """Update sync status and optionally last_synced_at timestamp.

        Args:
            record_id: Record database ID to update.
            sync_status: New sync status value.
            last_synced_at: Optional timestamp string. Defaults to None.

        Returns:
            Number of rows affected (0 or 1).
        """
        if last_synced_at:
            sql = "UPDATE records SET sync_status = ?, last_synced_at = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?"
            return self.execute_update(sql, (sync_status, last_synced_at, record_id))
        else:
            sql = "UPDATE records SET sync_status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?"
            return self.execute_update(sql, (sync_status, record_id))
    

    ############################################################################
    # IP ADDRESS MANAGEMENT - Current state per record
    ############################################################################
    
    def get_ip_address(self, record_id: int) -> Optional[Dict[str, Any]]:
        """Get current IP address for a record.

        Args:
            record_id: Record database ID to retrieve IP for.

        Returns:
            Dictionary with ip_address, last_checked_at, last_changed_at, or None.
        """
        rows = self.execute_query(
            "SELECT ip_address, last_checked_at, last_changed_at FROM ip_addresses WHERE record_id = ?",
            (record_id,)
        )
        return dict(rows[0]) if rows else None
    

    def update_ip_address(self, record_id: int, ip_address: str, changed: bool = True) -> None:
        """Insert or update IP address for a record only when the IP changes.

        Args:
            record_id: Record database ID to update.
            ip_address: New IP address string.
            changed: Legacy flag kept for signature compatibility.
        """
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
    

    ############################################################################
    # DNS UPDATE HISTORY - Audit trail per record
    ############################################################################
    
    def log_dns_update(self, record_id: int, old_ip: Optional[str], new_ip: str, status: str = UpdateStatus.SUCCESS, error_message: Optional[str] = None) -> None:
        """Log a DNS update to history.

        Args:
            record_id: Record database ID that was updated.
            old_ip: Previous IP address before update.
            new_ip: New IP address after update.
            status: Update status. Defaults to UpdateStatus.SUCCESS.
            error_message: Optional error message for failed updates.
        """
        sql = """INSERT INTO dns_updates (record_id, old_ip, new_ip, status, error_message, updated_at)
                 VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)"""
        self.execute_update(sql, (record_id, old_ip, new_ip, status, error_message))
    

    def get_dns_update_history(self, record_id: Optional[int] = None, zone_id: Optional[int] = None, limit: int = 100) -> List[Dict[str, Any]]:
        """Get DNS update history.

        Args:
            record_id: Optional record ID to filter by. Defaults to None.
            zone_id: Optional zone ID to filter by. Defaults to None.
            limit: Maximum number of records to return. Defaults to 100.

        Returns:
            List of update records ordered by timestamp (newest first).
        """
        if record_id:
            sql = """SELECT * FROM dns_updates 
                     WHERE record_id = ?
                     ORDER BY updated_at DESC LIMIT ?"""
            rows = self.execute_query(sql, (record_id, limit))
        elif zone_id:
            sql = """SELECT du.* FROM dns_updates du
                     JOIN records r ON du.record_id = r.id
                     WHERE r.zone_id = ?
                     ORDER BY du.updated_at DESC LIMIT ?"""
            rows = self.execute_query(sql, (zone_id, limit))
        else:
            sql = """SELECT * FROM dns_updates 
                     ORDER BY updated_at DESC LIMIT ?"""
            rows = self.execute_query(sql, (limit,))
        return [dict(row) for row in rows]
    

    ############################################################################
    # DYNDNS CONFIG - DynDNS Bulk Configuration
    ############################################################################
    
    def get_dyndns_config_by_zone(self, zone_id: int) -> Optional[Dict[str, Any]]:
        """Get DynDNS configuration for a zone.

        Args:
            zone_id: Zone database ID to retrieve config for.

        Returns:
            Config dictionary with decrypted api_key, or None if not found.
        """
        rows = self.execute_query("SELECT * FROM dyndns_config WHERE zone_id = ?", (zone_id,))
        return self._decrypt_dyndns_config_row(rows[0], f"zone_id={zone_id}") if rows else None


    def get_dyndns_config_by_bulk_id(self, bulk_id: str) -> Optional[Dict[str, Any]]:
        """Get DynDNS configuration by bulkId.

        Args:
            bulk_id: Provider bulk ID to search for.

        Returns:
            Config dictionary with decrypted api_key, or None if not found.
        """
        rows = self.execute_query("SELECT * FROM dyndns_config WHERE bulk_id = ?", (bulk_id,))
        return self._decrypt_dyndns_config_row(rows[0], f"bulk_id={bulk_id}") if rows else None


    def _decrypt_dyndns_config_row(
        self, row: sqlite3.Row, context: str
    ) -> Optional[Dict[str, Any]]:
        """Convert a dyndns_config row to dictionary and decrypt its API key.

        Args:
            row: Database row from dyndns_config table.
            context: Identifier context for error logging (e.g., 'zone_id=1').

        Returns:
            Config dictionary with decrypted api_key, or None if decryption fails.
        """
        config = dict(row)
        if config.get('api_key'):
            try:
                config['api_key'] = self._encryption.decrypt(config['api_key'])
            except EncryptionError as e:
                self.logger.error(f"Failed to decrypt api_key for {context}: {e}")
                return None
        return config
    

    def set_dyndns_config(self, zone_id: int, bulk_id: str, api_key: str, update_url: Optional[str] = None, 
                          description: Optional[str] = None, domains: Optional[List[str]] = None) -> None:
        """Set or update DynDNS configuration for a zone.

        Creates new configuration if none exists, updates existing otherwise.
        API key is automatically encrypted before storage.

        Args:
            zone_id: Zone database ID to configure.
            bulk_id: Provider bulk ID.
            api_key: Plain text API key (will be encrypted).
            update_url: Optional provider update URL. Defaults to None.
            description: Optional description. Defaults to None.
            domains: Optional list of domain names. Defaults to None.

        Raises:
            EncryptionError: If API key encryption fails.
        """
        try:
            api_key_encrypted = self._encryption.encrypt(api_key)
        except EncryptionError as e:
            self.logger.error(f"Failed to encrypt api_key for zone_id={zone_id}: {e}")
            raise EncryptionError(f"API key encryption failed: {e}")
        
        if domains is None:
            domains = []
        
        if isinstance(domains, list):
            domains_json = json.dumps(domains)
        else:
            domains_json = domains
        
        existing = self.get_dyndns_config_by_zone(zone_id)
        
        if existing:
            sql = """UPDATE dyndns_config 
                     SET bulk_id = ?, api_key = ?, update_url = ?, description = ?, 
                         domains = ?, updated_at = CURRENT_TIMESTAMP
                     WHERE zone_id = ?"""
            self.execute_update(sql, (bulk_id, api_key_encrypted, update_url, description, 
                                      domains_json, zone_id))
        else:
            sql = """INSERT INTO dyndns_config (zone_id, bulk_id, api_key, update_url, 
                                                description, domains, enabled, created_at, updated_at)
                     VALUES (?, ?, ?, ?, ?, ?, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"""
            self.execute_update(sql, (zone_id, bulk_id, api_key_encrypted, update_url, 
                                      description, domains_json))
    

    def update_dyndns_status(self, zone_id: int, enabled: bool) -> int:
        """Enable or disable DynDNS for a zone.

        Args:
            zone_id: Zone database ID to update.
            enabled: New enabled state.

        Returns:
            Number of rows affected (0 or 1).
        """
        sql = """UPDATE dyndns_config SET enabled = ?, updated_at = CURRENT_TIMESTAMP 
                 WHERE zone_id = ?"""
        return self.execute_update(sql, (1 if enabled else 0, zone_id))


    ############################################################################
    # PRIVATE METHODS - Connection Pool & Error Handling
    ############################################################################

    @staticmethod
    def _format_bytes(size_bytes: int) -> str:
        """Format a byte count into a human-readable string (e.g. '14.06 MB').

        Args:
            size_bytes: Byte count to format.

        Returns:
            Human-readable size string.
        """
        val = float(max(0, size_bytes))
        for unit in StorageConstants.UNITS:
            if val < StorageConstants.BYTES_PER_KB or unit == StorageConstants.UNITS[-1]:
                return f"{val:.{StorageConstants.DEFAULT_DECIMALS}f} {unit}"
            val /= StorageConstants.BYTES_PER_KB
        return f"{val:.{StorageConstants.DEFAULT_DECIMALS}f} B"


    def _get_table_row_counts(self) -> Dict[str, int]:
        """Count rows across all user tables in the SQLite database.

        Returns:
            Dictionary mapping table names to row counts.
        """
        counts: Dict[str, int] = {}
        try:
            sql = "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            for row in self.execute_query(sql):
                t_name = str(row["name"])
                if t_name.replace("_", "").isalnum():
                    cnt_rows = self.execute_query(f"SELECT COUNT(*) FROM {t_name}")
                    counts[t_name] = int(cnt_rows[0][0] or 0) if cnt_rows else 0
        except DatabaseError as exc:
            self.logger.warning(f"Failed to query table row counts: {exc}")
        return counts


    def _acquire_valid_connection(self) -> sqlite3.Connection:
        """Acquire a connection from the pool without redundant ping queries.

        Returns:
            sqlite3.Connection: Active connection from pool.

        Raises:
            DatabaseError: If connection pool is exhausted.
        """
        try:
            return self._pool.get(timeout=DatabaseDefaults.POOL_GET_TIMEOUT)
        except queue.Empty as exc:
            raise DatabaseError("Connection pool exhausted - no connections available") from exc


    def _raise_database_error(self, exc: sqlite3.Error) -> None:
        """Translate a sqlite3 error into the project exception hierarchy.

        Args:
            exc: Original SQLite exception.

        Raises:
            DatabaseLockedError: If the database is locked.
            DatabaseError: For all other SQLite errors.
        """
        if isinstance(exc, sqlite3.OperationalError) and "database is locked" in str(exc).lower():
            self.logger.error(f"Database lock timeout: {exc}")
            raise DatabaseLockedError(str(exc)) from exc
        self.logger.error(f"Database operation failed: {exc}")
        raise DatabaseError(str(exc)) from exc


    def _safe_rollback(self, conn: Optional[sqlite3.Connection]) -> None:
        """Roll back an uncommitted transaction without masking caller errors.

        Args:
            conn: Active SQLite connection, if acquired.
        """
        if conn:
            try:
                conn.rollback()
            except sqlite3.Error as rollback_error:
                self.logger.warning(f"Rollback failed during exception propagation: {rollback_error}")


    def _release_connection(self, conn: Optional[sqlite3.Connection]) -> None:
        """Return a connection to the pool or close it if full.

        Args:
            conn: Active SQLite connection to release.
        """
        if not conn:
            return
        self._local.active_conn = None
        if conn.in_transaction:
            self._safe_rollback(conn)
        try:
            self._pool.put(conn, timeout=DatabaseDefaults.POOL_PUT_TIMEOUT)
        except queue.Full:
            conn.close()


    def _commit(self, conn: sqlite3.Connection) -> None:
        """Commit changes unless running inside an outer transaction() block.

        Args:
            conn: Active SQLite connection.
        """
        if not getattr(self._local, "in_transaction", False):
            conn.commit()


    def _initialize_pool(self) -> None:
        """Initialize the connection pool with max_connections connections.

        Raises:
            DatabaseError: If pool initialization fails.
        """
        try:
            for _ in range(self.max_connections):
                self._pool.put(self._create_connection())
        except (DatabaseError, sqlite3.Error, OSError) as exc:
            self.close()
            raise DatabaseError(f"Failed to initialize connection pool: {exc}") from exc


    def _create_connection(self) -> sqlite3.Connection:
        """Create a new SQLite connection tuned for SSD/SD-card longevity.

        Returns:
            Configured sqlite3.Connection instance.

        Raises:
            DatabaseError: If connection creation fails.
        """
        try:
            conn = sqlite3.connect(
                self.db_file,
                check_same_thread=False,
                timeout=DatabaseDefaults.CONNECT_TIMEOUT,
            )
            conn.row_factory = sqlite3.Row
            for pragma in (
                "PRAGMA journal_mode = WAL",
                "PRAGMA synchronous = NORMAL",
                f"PRAGMA busy_timeout = {DatabaseDefaults.BUSY_TIMEOUT_MS}",
                f"PRAGMA journal_size_limit = {DatabaseDefaults.JOURNAL_SIZE_LIMIT}",
                f"PRAGMA cache_size = {DatabaseDefaults.CACHE_SIZE_KB}",
                "PRAGMA temp_store = MEMORY",
                f"PRAGMA mmap_size = {DatabaseDefaults.MMAP_SIZE}",
                "PRAGMA foreign_keys = ON",
            ):
                conn.execute(pragma)
            return conn
        except sqlite3.Error as exc:
            raise DatabaseError(f"Failed to create database connection: {exc}") from exc