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

# Standard Imports
import json
import logging
import os
import queue
import sqlite3
import threading
from contextlib import contextmanager
from typing import Optional, List, Dict, Any

# Local Imports
from .encryption import EncryptionManager
from .constants import SyncStatus, UpdateStatus, DatabaseDefaults
from .exceptions import DatabaseError, EncryptionError
from .ownership import ensure_service_ownership


################################################################################
# DATABASE CLASS - SQLite with Connection Pooling
################################################################################

class Database:
    """SQLite database handler with connection pooling for thread safety.

    Provides thread-safe database operations using a connection pool with
    configurable size. Supports WAL mode for improved concurrency.

    Attributes:
        db_file: Path to the SQLite database file.
        max_connections: Maximum connections in the pool.
        logger: Logger instance for database operations.
        config: Configuration object reference.
    """

    def __init__(self, db_file: str, max_connections: int = DatabaseDefaults.MAX_CONNECTIONS, logger: Optional[Any] = None, config: Optional[Any] = None) -> None:
        """Initialize database with connection pooling.

        Args:
            db_file: Path to SQLite database file. Created if not exists.
            max_connections: Maximum number of connections in pool. Defaults to 5.
            logger: Logger instance for logging. Creates default if None.
            config: Configuration object for additional settings.

        Raises:
            DatabaseError: If connection pool initialization fails.
        """
        self.db_file = db_file
        self.max_connections = max_connections
        self.logger = logger
        self.config = config
        
        self._pool = queue.Queue(maxsize=max_connections)
        self._pool_lock = threading.Lock()
        self._created_connections = 0
        
        if logger:
            self.logger = logger
        else:
            self.logger = logging.getLogger(__name__)
        
        self._encryption = EncryptionManager(self.config.encryption_key_path, self.logger)
        
        db_exists = os.path.exists(db_file)

        self._initialize_pool()

        if not db_exists:
            self.logger.info("Database does not exist. Creating a new one...")
            self.create_tables()

        # Hand off DB file ownership to the service user when running as
        # root (admin CLI such as import/export). No-op otherwise. Also
        # covers the WAL/SHM sidecar files if present.
        ensure_service_ownership(db_file, logger=self.logger)
        for sidecar in (f"{db_file}-wal", f"{db_file}-shm"):
            ensure_service_ownership(sidecar, logger=self.logger)

        self.logger.info(f"Database initialized with connection pool (max: {max_connections})")


    def __del__(self) -> None:
        """Close all database connections when the object is destroyed."""
        self.close()


    ################################################################################
    # PUBLIC CONNECTION INTERFACE - Context Manager
    ################################################################################
    
    @contextmanager
    def get_connection(self) -> Any:
        """Get a connection from the pool as a context manager.

        Thread-safe method to acquire a database connection. The connection
        is automatically returned to the pool when the context exits.

        Yields:
            SQLite connection from pool.

        Raises:
            DatabaseError: If connection pool exhausted.
        """
        conn = None
        try:
            try:
                conn = self._pool.get(timeout=DatabaseDefaults.POOL_GET_TIMEOUT)
            except queue.Empty:
                raise DatabaseError("Connection pool exhausted - no connections available")
            
            try:
                conn.execute("SELECT 1")
            except sqlite3.Error:
                try:
                    conn.close()
                except Exception:
                    pass
                conn = None
                conn = self._create_connection()
                
            yield conn
            
        except BaseException:
            if conn:
                try:
                    conn.rollback()
                except sqlite3.Error:
                    pass
            raise
            
        finally:
            if conn:
                try:
                    self._pool.put(conn, timeout=DatabaseDefaults.POOL_PUT_TIMEOUT)
                except queue.Full:
                    conn.close()


    ################################################################################
    # QUERY EXECUTION METHODS - Public Database Operations
    ################################################################################
    
    def execute_query(self, query: str, params: Optional[tuple] = None) -> List[sqlite3.Row]:
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
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query, params or ())
                return cursor.fetchall()
        except sqlite3.Error as e:
            self.logger.error(f"Database query failed: {e} | Query: {query} | Params: {params}")
            raise DatabaseError(f"Database query failed: {e}") from e
    

    def execute_update(self, query: str, params: Optional[tuple] = None) -> int:
        """Execute an INSERT, UPDATE, or DELETE query.

        Thread-safe method to execute write operations with automatic commit.

        Args:
            query: SQL modification statement to execute.
            params: Optional query parameters for parameterized queries.

        Returns:
            Number of rows affected by the operation.

        Raises:
            DatabaseError: If database update execution fails.
        """
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query, params or ())
                conn.commit()
                return cursor.rowcount
        except sqlite3.Error as e:
            self.logger.error(f"Database update failed: {e} | Query: {query} | Params: {params}")
            raise DatabaseError(f"Database update failed: {e}") from e
    

    def execute_many(self, query: str, params_list: List[tuple]) -> int:
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
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.executemany(query, params_list)
                conn.commit()
                return cursor.rowcount            
        except sqlite3.Error as e:
            self.logger.error(f"Database batch update failed: {e} | Query: {query}")
            raise DatabaseError(f"Database batch update failed: {e}") from e


    ################################################################################
    # RESOURCE MANAGEMENT - Cleanup Methods
    ################################################################################

    def close(self) -> None:
        """Close all connections in the pool."""
        try:
            while not self._pool.empty():
                try:
                    conn = self._pool.get_nowait()
                    conn.close()
                except queue.Empty:
                    break
                except Exception as e:
                    if self.logger:
                        self.logger.warning(f"Error closing connection: {e}")
            
            if self.logger:
                self.logger.info("All database connections closed")
                
        except Exception as e:
            if self.logger:
                self.logger.error(f"Error during database cleanup: {e}")


    ################################################################################
    # TABLE MANAGEMENT - Schema Creation and Management
    ################################################################################

    def create_tables(self) -> None:
        """Create DynDNS database tables.

        Creates all required tables for the application including zones,
        records, IP addresses, update history, and configuration tables.
        Thread-safe operation supporting multi-subdomain architecture.
        """
        
        # ===================================================================
        # ZONES - DNS Zones (Root Domains)
        # ===================================================================
        self.create_table("zones", [
            ("id", "INTEGER PRIMARY KEY AUTOINCREMENT"),
            ("zone_name", "TEXT UNIQUE NOT NULL"),              # Root domain: 'website.com'
            ("provider_zone_id", "TEXT"),                       # Provider Zone ID (from API, can be NULL until fetched)
            ("enabled", "INTEGER DEFAULT 1"),                   # 1=active, 0=disabled
            ("created_at", "DATETIME DEFAULT CURRENT_TIMESTAMP"),
            ("updated_at", "DATETIME DEFAULT CURRENT_TIMESTAMP")
        ])
        
        # ===================================================================
        # RECORDS - DNS Records (Root + All Subdomains)
        # ===================================================================
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
        
        # ===================================================================
        # IP ADDRESSES - Current State per Record
        # ===================================================================
        self.create_table("ip_addresses", [
            ("id", "INTEGER PRIMARY KEY AUTOINCREMENT"),
            ("record_id", "INTEGER NOT NULL"),                  # Foreign Key to records
            ("ip_address", "TEXT NOT NULL"),                    # IPv4 or IPv6 address
            ("last_checked_at", "DATETIME DEFAULT CURRENT_TIMESTAMP"),
            ("last_changed_at", "DATETIME DEFAULT CURRENT_TIMESTAMP"),
            ("FOREIGN KEY (record_id)", "REFERENCES records(id) ON DELETE CASCADE"),
            ("UNIQUE (record_id)", "")                          # One IP per record
        ])
        
        # ===================================================================
        # DNS UPDATE HISTORY - Audit Trail for all changes
        # ===================================================================
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
        
        # ===================================================================
        # DYNDNS CONFIG - DynDNS Bulk Configuration per Zone
        # ===================================================================
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
        
        # ===================================================================
        # APP CONFIG - Generic application settings
        # ===================================================================
        self.create_table("app_config", [
            ("id", "INTEGER PRIMARY KEY AUTOINCREMENT"),
            ("key", "TEXT UNIQUE NOT NULL"),
            ("value", "TEXT"),
            ("created_at", "DATETIME DEFAULT CURRENT_TIMESTAMP"),
        ])
        
        # ===================================================================
        # APP LOGS - Optional: Database logging
        # ===================================================================
        self.create_table("app_logs", [
            ("id", "INTEGER PRIMARY KEY AUTOINCREMENT"),
            ("level", "TEXT NOT NULL"),
            ("message", "TEXT NOT NULL"),
            ("created_at", "DATETIME DEFAULT CURRENT_TIMESTAMP"),
        ])


    def create_table(self, table_name: str, columns: List[tuple]) -> None:
        """Create a table if it does not exist.

        Thread-safe method to create database tables idempotently.

        Args:
            table_name: Name of the table to create.
            columns: List of (column_name, type_definition) tuples.
        """
        columns_sql = ", ".join([f"{name} {type_}" for name, type_ in columns])
        sql = f"CREATE TABLE IF NOT EXISTS {table_name} ({columns_sql});"
        
        self.execute_update(sql)


    ################################################################################
    # APPLICATION-SPECIFIC METHODS - Configuration Management
    ################################################################################

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
        """Set or update configuration value by key.

        Thread-safe method to store application configuration. Creates new
        entry if key doesn't exist, updates existing entry otherwise.

        Args:
            key: Configuration key to set.
            value: Configuration value to store.
        """
        affected = self.execute_update("UPDATE app_config SET value = ? WHERE key = ?", (value, key))
        
        if affected == 0:
            self.execute_update("INSERT INTO app_config (key, value) VALUES (?, ?)", (key, value))


    def delete_config_by_key(self, key: str) -> bool:
        """Delete configuration entry by key.

        Thread-safe method to remove application configuration entries.

        Args:
            key: Configuration key to delete.

        Returns:
            True if entry was deleted, False if key not found.
        """
        affected = self.execute_update("DELETE FROM app_config WHERE key = ?", (key,))
        return affected > 0


    ################################################################################
    # APPLICATION-SPECIFIC METHODS - DynDNS Operations
    ################################################################################
    
    # ===================================================================
    # ZONE MANAGEMENT - DNS Zones (Root Domains)
    # ===================================================================
    
    def get_zone_by_id(self, zone_id: int) -> Optional[Dict[str, Any]]:
        """Get zone by database ID.

        Args:
            zone_id: Zone database ID to retrieve.

        Returns:
            Zone dictionary or None if not found.
        """
        rows = self.execute_query("SELECT * FROM zones WHERE id = ?", (zone_id,))
        return rows[0] if rows else None
    

    def get_zone_by_name(self, zone_name: str) -> Optional[Dict[str, Any]]:
        """Get zone by domain name.

        Args:
            zone_name: Zone domain name to retrieve.

        Returns:
            Zone dictionary or None if not found.
        """
        rows = self.execute_query("SELECT * FROM zones WHERE zone_name = ?", (zone_name,))
        return rows[0] if rows else None
    

    def get_all_zones(self) -> List[Dict[str, Any]]:
        """Get all zones ordered by name.

        Returns:
            List of all zone dictionaries.
        """
        return self.execute_query("SELECT * FROM zones ORDER BY zone_name")
    

    def get_all_enabled_zones(self) -> List[Dict[str, Any]]:
        """Get all enabled zones ordered by name.

        Returns:
            List of all enabled zone dictionaries.
        """
        return self.execute_query("SELECT * FROM zones WHERE enabled = 1 ORDER BY zone_name")
    

    def add_zone(self, zone_name: str, provider_zone_id: str, enabled: bool = True) -> Optional[int]:
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
        return self.execute_update(sql, (zone_id,))
    

    # ===================================================================
    # RECORD MANAGEMENT - DNS Records (Root + Subdomains)
    # ===================================================================
    
    def get_record_by_id(self, record_id: int) -> Optional[Dict[str, Any]]:
        """Get DNS record by database ID.

        Args:
            record_id: Record database ID to retrieve.

        Returns:
            Record dictionary or None if not found.
        """
        rows = self.execute_query("SELECT * FROM records WHERE id = ?", (record_id,))
        return rows[0] if rows else None
    

    def get_records_by_zone(self, zone_id: int, enabled_only: bool = True) -> List[Dict[str, Any]]:
        """Get all DNS records for a zone.

        Args:
            zone_id: Zone database ID to filter by.
            enabled_only: If True, only return enabled records. Defaults to True.

        Returns:
            List of record dictionaries ordered by name and type.
        """
        if enabled_only:
            sql = "SELECT * FROM records WHERE zone_id = ? AND enabled = 1 ORDER BY record_name, record_type"
        else:
            sql = "SELECT * FROM records WHERE zone_id = ? ORDER BY record_name, record_type"
        return self.execute_query(sql, (zone_id,))
    

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
        return rows[0] if rows else None
    

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
        """Update Provider Record ID.

        Args:
            record_id: Record database ID to update.
            provider_record_id: Provider's record identifier from API.

        Returns:
            Number of rows affected (0 or 1).
        """
        sql = "UPDATE records SET provider_record_id = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?"
        return self.execute_update(sql, (provider_record_id, record_id))
    

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
            sql = f"SELECT * FROM records WHERE sync_status = '{SyncStatus.ORPHANED}' AND zone_id = ? ORDER BY record_name"
            rows = self.execute_query(sql, (zone_id,))
        else:
            sql = f"SELECT * FROM records WHERE sync_status = '{SyncStatus.ORPHANED}' ORDER BY zone_id, record_name"
            rows = self.execute_query(sql)
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
    

    # ===================================================================
    # IP ADDRESS MANAGEMENT - Current state per record
    # ===================================================================
    
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
        return rows[0] if rows else None
    

    def update_ip_address(self, record_id: int, ip_address: str, changed: bool = False) -> None:
        """Update or insert IP address for a record.

        Creates new entry if record has no IP, updates existing otherwise.

        Args:
            record_id: Record database ID to update.
            ip_address: New IP address string.
            changed: If True, update last_changed_at timestamp. Defaults to False.
        """
        existing = self.get_ip_address(record_id)
        
        if existing:
            if changed:
                sql = """UPDATE ip_addresses 
                         SET ip_address = ?, 
                             last_checked_at = CURRENT_TIMESTAMP,
                             last_changed_at = CURRENT_TIMESTAMP
                         WHERE record_id = ?"""
            else:
                sql = """UPDATE ip_addresses 
                         SET ip_address = ?, 
                             last_checked_at = CURRENT_TIMESTAMP
                         WHERE record_id = ?"""
            self.execute_update(sql, (ip_address, record_id))
        else:
            sql = """INSERT INTO ip_addresses (record_id, ip_address, last_checked_at, last_changed_at)
                     VALUES (?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"""
            self.execute_update(sql, (record_id, ip_address))
    

    # ===================================================================
    # DNS UPDATE HISTORY - Audit trail per record
    # ===================================================================
    
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
            return self.execute_query(sql, (record_id, limit))
        elif zone_id:
            sql = """SELECT du.* FROM dns_updates du
                     JOIN records r ON du.record_id = r.id
                     WHERE r.zone_id = ?
                     ORDER BY du.updated_at DESC LIMIT ?"""
            return self.execute_query(sql, (zone_id, limit))
        else:
            sql = """SELECT * FROM dns_updates 
                     ORDER BY updated_at DESC LIMIT ?"""
            return self.execute_query(sql, (limit,))
    

    # ===================================================================
    # DYNDNS CONFIG - DynDNS Bulk Configuration
    # ===================================================================
    
    def get_dyndns_config_by_zone(self, zone_id: int) -> Optional[Dict[str, Any]]:
        """Get DynDNS configuration for a zone.

        Args:
            zone_id: Zone database ID to retrieve config for.

        Returns:
            Config dictionary with decrypted api_key, or None if not found.
        """
        rows = self.execute_query("SELECT * FROM dyndns_config WHERE zone_id = ?", (zone_id,))
        if not rows:
            return None
        
        config = dict(rows[0])
        if config.get('api_key'):
            try:
                config['api_key'] = self._encryption.decrypt(config['api_key'])
            except EncryptionError as e:
                self.logger.error(f"Failed to decrypt api_key for zone_id={zone_id}: {e}")
                return None
        return config
    

    def get_dyndns_config_by_bulk_id(self, bulk_id: str) -> Optional[Dict[str, Any]]:
        """Get DynDNS configuration by bulkId.

        Args:
            bulk_id: Provider bulk ID to search for.

        Returns:
            Config dictionary with decrypted api_key, or None if not found.
        """
        rows = self.execute_query("SELECT * FROM dyndns_config WHERE bulk_id = ?", (bulk_id,))
        if not rows:
            return None
        
        config = dict(rows[0])
        if config.get('api_key'):
            try:
                config['api_key'] = self._encryption.decrypt(config['api_key'])
            except EncryptionError as e:
                self.logger.error(f"Failed to decrypt api_key for bulk_id={bulk_id}: {e}")
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


    ################################################################################
    # PRIVATE METHODS - Internal Implementation
    ################################################################################
    
    def _initialize_pool(self) -> None:
        """Initialize the connection pool with connections.

        Creates max_connections number of database connections and adds
        them to the pool for thread-safe access.

        Raises:
            DatabaseError: If pool initialization fails.
        """
        try:
            for _ in range(self.max_connections):
                conn = self._create_connection()
                self._pool.put(conn)
                self._created_connections += 1
        except DatabaseError as e:
            while not self._pool.empty():
                try:
                    conn = self._pool.get_nowait()
                    conn.close()
                except queue.Empty:
                    break
                except Exception:
                    pass
            raise DatabaseError(f"Failed to initialize connection pool: {e}")
    

    def _create_connection(self) -> sqlite3.Connection:
        """Create a new database connection with proper settings.

        Configures connection for thread-safety, WAL mode, and foreign keys.

        Returns:
            Configured SQLite connection with Row factory.

        Raises:
            DatabaseError: If connection creation fails.
        """
        try:
            conn = sqlite3.connect(
                self.db_file, 
                check_same_thread=False,
                timeout=DatabaseDefaults.CONNECT_TIMEOUT
            )
            conn.row_factory = sqlite3.Row
            
            # Enable foreign key constraints for CASCADE
            conn.execute("PRAGMA foreign_keys = ON")
            
            # This makes SQLite wait and retry if database is locked
            conn.execute("PRAGMA busy_timeout = 30000") # 30000ms
            
            # Enable WAL mode for better concurrency
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA temp_store=memory")
            conn.execute(f"PRAGMA mmap_size={DatabaseDefaults.MMAP_SIZE}")
            
            return conn
            
        except sqlite3.Error as e:
            raise DatabaseError(f"Failed to create database connection: {e}")