#!/usr/bin/env python3
"""
Database Manager

Handles database operations and interactions.

Created: 2025-10-27
Author: Manuel Ziel
License: MIT
"""

################################################################################
# IMPORTS & DEPENDENCIES
################################################################################

# Standard library imports
import json
import logging
import os
import queue
import sqlite3
import threading
from contextlib import contextmanager
from typing import Optional, List, Dict, Any

# Third-party imports
import bcrypt
from encryption import EncryptionManager
from exceptions import DatabaseError

################################################################################
# DATABASE CLASS - SQLite with Connection Pooling
################################################################################

class Database:
    """Database handler for SQLite operations with connection pooling and thread safety."""
    
    def __init__(self, db_file: str, max_connections: int = 5, logger: Optional[Any] = None, config: Optional[Any] = None) -> None:
        """Initialize database with connection pooling.
        
        Args:
            db_file: Path to SQLite database file
            max_connections: Maximum number of connections in pool (default: 5)
            logger: Logger instance
            config: Configuration object
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
            
        self.logger.info(f"Database initialized with connection pool (max: {max_connections})")

    def __del__(self) -> None:
        """Close all database connections when the object is destroyed."""
        self.close()

    ################################################################################
    # PUBLIC CONNECTION INTERFACE - Context Manager
    ################################################################################
    
    @contextmanager
    def get_connection(self) -> Any:
        """Get a connection from the pool (thread-safe context manager)."""
        conn = None
        try:
            try:
                conn = self._pool.get(timeout=10.0)
            except queue.Empty:
                raise DatabaseError("Connection pool exhausted - no connections available")
            
            try:
                conn.execute("SELECT 1")
            except sqlite3.Error:
                conn.close()
                conn = self._create_connection()
                
            yield conn
            
        except Exception as e:
            if conn:
                try:
                    conn.rollback()
                except sqlite3.Error:
                    pass
            raise
            
        finally:
            if conn:
                try:
                    self._pool.put(conn, timeout=1.0)
                except queue.Full:
                    conn.close()

    ################################################################################
    # QUERY EXECUTION METHODS - Public Database Operations
    ################################################################################
    
    def execute_query(self, query: str, params: Optional[tuple] = None) -> List[sqlite3.Row]:
        """Execute a SELECT query and return results (thread-safe)."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params or ())
            return cursor.fetchall()
    
    def execute_update(self, query: str, params: Optional[tuple] = None) -> int:
        """Execute an INSERT/UPDATE/DELETE query (thread-safe). Returns number of affected rows."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params or ())
            conn.commit()
            return cursor.rowcount
    
    def execute_many(self, query: str, params_list: List[tuple]) -> int:
        """Execute a query with multiple parameter sets (thread-safe). Returns number of affected rows."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.executemany(query, params_list)
            conn.commit()
            return cursor.rowcount            

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
        """Create DynDNS database tables (thread-safe, multi-subdomain ready)."""
        
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
        """Create a table if it does not exist (thread-safe)."""
        columns_sql = ", ".join([f"{name} {type_}" for name, type_ in columns])
        sql = f"CREATE TABLE IF NOT EXISTS {table_name} ({columns_sql});"
        
        self.execute_update(sql)

    ################################################################################
    # APPLICATION-SPECIFIC METHODS - Configuration Management
    ################################################################################

    def get_config_by_key(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """Get configuration value by key (thread-safe)."""
        rows = self.execute_query("SELECT value FROM app_config WHERE key = ?", (key,))
        return rows[0]["value"] if rows else default

    def set_config_by_key(self, key: str, value: str) -> None:
        """Set or update configuration value by key (thread-safe)."""
        affected = self.execute_update("UPDATE app_config SET value = ? WHERE key = ?", (value, key))
        
        if affected == 0:
            self.execute_update("INSERT INTO app_config (key, value) VALUES (?, ?)", (key, value))

    def delete_config_by_key(self, key: str) -> bool:
        """Delete configuration entry by key (thread-safe)."""
        affected = self.execute_update("DELETE FROM app_config WHERE key = ?", (key,))
        return affected > 0

    ################################################################################
    # APPLICATION-SPECIFIC METHODS - DynDNS Operations
    ################################################################################
    
    # ===================================================================
    # ZONE MANAGEMENT - DNS Zones (Root Domains)
    # ===================================================================
    
    def get_zone_by_id(self, zone_id: int) -> Optional[Dict[str, Any]]:
        """Get zone by ID (thread-safe)."""
        rows = self.execute_query("SELECT * FROM zones WHERE id = ?", (zone_id,))
        return rows[0] if rows else None
    
    def get_zone_by_name(self, zone_name: str) -> Optional[Dict[str, Any]]:
        """Get zone by name (thread-safe)."""
        rows = self.execute_query("SELECT * FROM zones WHERE zone_name = ?", (zone_name,))
        return rows[0] if rows else None
    
    def get_all_zones(self) -> List[Dict[str, Any]]:
        """Get all zones (thread-safe)."""
        return self.execute_query("SELECT * FROM zones ORDER BY zone_name")
    
    def get_all_enabled_zones(self) -> List[Dict[str, Any]]:
        """Get all enabled zones (thread-safe)."""
        return self.execute_query("SELECT * FROM zones WHERE enabled = 1 ORDER BY zone_name")
    
    def add_zone(self, zone_name: str, provider_zone_id: str, enabled: bool = True) -> Optional[int]:
        """Add a new zone (thread-safe)."""
        enabled_int = 1 if enabled else 0
        sql = """INSERT INTO zones (zone_name, provider_zone_id, enabled, created_at, updated_at)
                 VALUES (?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"""
        self.execute_update(sql, (zone_name, provider_zone_id, enabled_int))
        
        rows = self.execute_query("SELECT id FROM zones WHERE zone_name = ?", (zone_name,))
        return rows[0]["id"] if rows else None
    
    def update_zone_status(self, zone_id: int, enabled: bool) -> int:
        """Enable or disable a zone (thread-safe)."""
        sql = """UPDATE zones SET enabled = ?, updated_at = CURRENT_TIMESTAMP 
                 WHERE id = ?"""
        return self.execute_update(sql, (1 if enabled else 0, zone_id))
    
    def update_zone(self, zone_id: int, **kwargs: Any) -> int:
        """Update zone fields (thread-safe). Returns number of rows affected."""
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
        """Delete a zone and all related data (CASCADE): zone, records, IP addresses, update history, DynDNS config. Returns number of rows affected."""
        sql = "DELETE FROM zones WHERE id = ?"
        return self.execute_update(sql, (zone_id,))
    
    # ===================================================================
    # RECORD MANAGEMENT - DNS Records (Root + Subdomains)
    # ===================================================================
    
    def get_record_by_id(self, record_id: int) -> Optional[Dict[str, Any]]:
        """Get record by ID (thread-safe)."""
        rows = self.execute_query("SELECT * FROM records WHERE id = ?", (record_id,))
        return rows[0] if rows else None
    
    def get_records_by_zone(self, zone_id: int, enabled_only: bool = True) -> List[Dict[str, Any]]:
        """Get all records for a zone (thread-safe). Set enabled_only=False to include disabled records."""
        if enabled_only:
            sql = "SELECT * FROM records WHERE zone_id = ? AND enabled = 1 ORDER BY record_name, record_type"
        else:
            sql = "SELECT * FROM records WHERE zone_id = ? ORDER BY record_name, record_type"
        return self.execute_query(sql, (zone_id,))
    
    def get_record_by_name_and_type(self, zone_id: int, record_name: str, record_type: str) -> Optional[Dict[str, Any]]:
        """Get a specific record by FQDN and type (thread-safe). Returns record dict or None."""
        sql = "SELECT * FROM records WHERE zone_id = ? AND record_name = ? AND record_type = ?"
        rows = self.execute_query(sql, (zone_id, record_name, record_type))
        return rows[0] if rows else None
    
    def add_record(self, zone_id: int, record_name: str, record_type: str, provider_record_id: Optional[str] = None, 
                   ttl: int = 3600, enabled: bool = True, managed: bool = True, sync_status: str = 'synced') -> Optional[int]:
        """Add a new DNS record with sync tracking (thread-safe). Returns record ID of newly created record."""
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
        """Update Provider Record ID (thread-safe)."""
        sql = "UPDATE records SET provider_record_id = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?"
        return self.execute_update(sql, (provider_record_id, record_id))
    
    def update_record_status(self, record_id: int, enabled: bool) -> int:
        """Enable or disable a record (thread-safe)."""
        sql = "UPDATE records SET enabled = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?"
        return self.execute_update(sql, (1 if enabled else 0, record_id))
    
    def update_record(self, record_id: int, **kwargs: Any) -> int:
        """Update record fields including sync tracking (thread-safe). Returns number of rows affected."""
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
        """Delete a DNS record and all related data (CASCADE): record, IP addresses, update history. Returns number of rows affected."""
        sql = "DELETE FROM records WHERE id = ?"
        return self.execute_update(sql, (record_id,))
    
    def get_orphaned_records(self, zone_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """Get all orphaned records (sync_status='orphaned'). Optionally filter by zone."""
        if zone_id:
            sql = "SELECT * FROM records WHERE sync_status = 'orphaned' AND zone_id = ? ORDER BY record_name"
            rows = self.execute_query(sql, (zone_id,))
        else:
            sql = "SELECT * FROM records WHERE sync_status = 'orphaned' ORDER BY zone_id, record_name"
            rows = self.execute_query(sql)
        return [dict(row) for row in rows]
    
    def update_sync_status(self, record_id: int, sync_status: str, last_synced_at: Optional[str] = None) -> int:
        """Update sync status and optionally last_synced_at timestamp."""
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
        """Get current IP address for a record (thread-safe). Returns dict with ip_address, last_checked_at, last_changed_at or None."""
        rows = self.execute_query(
            "SELECT ip_address, last_checked_at, last_changed_at FROM ip_addresses WHERE record_id = ?",
            (record_id,)
        )
        return rows[0] if rows else None
    
    def update_ip_address(self, record_id: int, ip_address: str, changed: bool = False) -> None:
        """Update or insert IP address for a record (thread-safe). Set changed=True to update last_changed_at."""
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
    
    def log_dns_update(self, record_id: int, old_ip: Optional[str], new_ip: str, status: str = 'success', error_message: Optional[str] = None) -> None:
        """Log a DNS update to history (thread-safe). Status: 'success', 'failed', or 'skipped'."""
        sql = """INSERT INTO dns_updates (record_id, old_ip, new_ip, status, error_message, updated_at)
                 VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)"""
        self.execute_update(sql, (record_id, old_ip, new_ip, status, error_message))
    
    def get_dns_update_history(self, record_id: Optional[int] = None, zone_id: Optional[int] = None, limit: int = 100) -> List[Dict[str, Any]]:
        """Get DNS update history (thread-safe). Returns list of update records (newest first)."""
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
        """Get DynDNS configuration for a zone (thread-safe). Decrypts api_key, returns None if decryption fails."""
        rows = self.execute_query("SELECT * FROM dyndns_config WHERE zone_id = ?", (zone_id,))
        if not rows:
            return None
        
        config = dict(rows[0])
        if config.get('api_key'):
            try:
                config['api_key'] = self._encryption.decrypt(config['api_key'])
            except Exception as e:
                self.logger.error(f"Failed to decrypt api_key for zone_id={zone_id}: {e}")
                return None
        return config
    
    def get_dyndns_config_by_bulk_id(self, bulk_id: str) -> Optional[Dict[str, Any]]:
        """Get DynDNS configuration by bulkId (thread-safe). Decrypts api_key, returns None if decryption fails."""
        rows = self.execute_query("SELECT * FROM dyndns_config WHERE bulk_id = ?", (bulk_id,))
        if not rows:
            return None
        
        config = dict(rows[0])
        if config.get('api_key'):
            try:
                config['api_key'] = self._encryption.decrypt(config['api_key'])
            except Exception as e:
                self.logger.error(f"Failed to decrypt api_key for bulk_id={bulk_id}: {e}")
                return None
        return config
    
    def set_dyndns_config(self, zone_id: int, bulk_id: str, api_key: str, update_url: Optional[str] = None, 
                          description: Optional[str] = None, domains: Optional[List[str]] = None) -> None:
        """Set or update DynDNS configuration for a zone (thread-safe). Encrypts api_key before storage. Raises ValueError if encryption fails."""
        try:
            api_key_encrypted = self._encryption.encrypt(api_key)
        except Exception as e:
            self.logger.error(f"Failed to encrypt api_key for zone_id={zone_id}: {e}")
            raise ValueError(f"API key encryption failed: {e}")
        
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
        """Enable or disable DynDNS for a zone (thread-safe)."""
        sql = """UPDATE dyndns_config SET enabled = ?, updated_at = CURRENT_TIMESTAMP 
                 WHERE zone_id = ?"""
        return self.execute_update(sql, (1 if enabled else 0, zone_id))

    ################################################################################
    # PRIVATE METHODS - Internal Implementation
    ################################################################################
    
    def _initialize_pool(self) -> None:
        """Initialize the connection pool with connections."""
        try:
            for _ in range(self.max_connections):
                conn = self._create_connection()
                self._pool.put(conn)
                self._created_connections += 1
        except Exception as e:
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
        """Create a new database connection with proper settings."""
        try:
            conn = sqlite3.connect(
                self.db_file, 
                check_same_thread=False,
                timeout=30.0  # 30 second timeout
            )
            conn.row_factory = sqlite3.Row
            
            # Enable foreign key constraints (required for CASCADE)
            conn.execute("PRAGMA foreign_keys = ON")
            
            # Set busy timeout for concurrent access (30 seconds = 30000ms)
            # This makes SQLite wait and retry if database is locked
            conn.execute("PRAGMA busy_timeout = 30000")
            
            # Enable WAL mode for better concurrency
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA temp_store=memory")
            conn.execute("PRAGMA mmap_size=268435456")  # 256MB
            
            return conn
            
        except sqlite3.Error as e:
            raise DatabaseError(f"Failed to create database connection: {e}")

    def _convert_to_int(self, value: Any) -> Optional[int]:
        """Convert value to integer if possible, otherwise return None."""
        try:
            return int(value)
        except (ValueError, TypeError):
            error_msg = f"Database error: invalid format to convert to integer: {value}"
            
            if self.logger:
                self.logger.error(error_msg)
            else:
                print(error_msg)
            return None