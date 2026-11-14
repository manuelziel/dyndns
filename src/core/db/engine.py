#!/usr/bin/env python3
"""SQLite connection pool engine, transactions, and storage diagnostics.

Provides the low-level thread-safe connection pool, atomic transaction context
managers, validated DDL execution, and SSD/SD-card wear-leveling PRAGMAs.

Author: Manuel Ziel
License: MIT
"""

################################################################################
# IMPORTS & DEPENDENCIES
################################################################################

from collections.abc import Generator
from contextlib import contextmanager
import logging
import queue
import sqlite3
import threading
from typing import Any

from ..constants import DatabaseDefaults
from ..exceptions import DatabaseError, DatabaseLockedError
from .ddl import (
    build_storage_metrics,
    is_valid_sql_identifier,
    validate_column_or_constraint,
    validate_table_constraint,
)

################################################################################
# DATABASE ENGINE BASE CLASS
################################################################################


class DatabaseEngine:
    """Thread-safe SQLite connection pool and transaction engine.

    Attributes:
        db_file: Path to the SQLite database file.
        max_connections: Maximum connections maintained in the pool.
        logger: Logger instance for database operations.
    """

    db_file: str
    max_connections: int
    logger: logging.Logger
    _pool: queue.Queue[sqlite3.Connection]
    _local: threading.local

    ############################################################################
    # PUBLIC CONNECTION & TRANSACTION INTERFACE
    ############################################################################

    @contextmanager
    def get_connection(self) -> Generator[sqlite3.Connection, None, None]:
        """Acquire a connection from the pool as a re-entrant context manager.

        Yields:
            Active ``sqlite3.Connection`` from the connection pool.

        Raises:
            DatabaseLockedError: If the database remains locked past busy_timeout.
            DatabaseError: If pool is exhausted or a SQLite error occurs.
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
        """Execute a block of operations inside an atomic transaction.

        Yields:
            None.

        Raises:
            DatabaseLockedError: If the database remains locked past busy_timeout.
            DatabaseError: If pool is exhausted or a SQLite error occurs.
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
    # QUERY EXECUTION & VALIDATED DDL METHODS
    ############################################################################

    def execute_query(
        self, query: str, params: tuple[Any, ...] | None = None
    ) -> list[sqlite3.Row]:
        """Execute a parameterized ``SELECT`` query and return rows.

        Args:
            query: SQL ``SELECT`` statement to execute.
            params: Optional query parameter tuple.

        Returns:
            List of ``sqlite3.Row`` result objects.

        Raises:
            DatabaseError: If query execution fails.
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params or ())
            return cursor.fetchall()

    def execute_update(
        self, query: str, params: tuple[Any, ...] | None = None
    ) -> int:
        """Execute a parameterized write or DDL statement with auto-commit.

        Args:
            query: SQL modification statement to execute.
            params: Optional query parameter tuple.

        Returns:
            Number of rows affected by the statement.

        Raises:
            DatabaseError: If statement execution fails.
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params or ())
            self._commit(conn)
            return cursor.rowcount

    def execute_many(self, query: str, params_list: list[tuple[Any, ...]]) -> int:
        """Execute a parameterized statement across a batch of parameter tuples.

        Args:
            query: SQL statement to execute repeatedly.
            params_list: Sequence of parameter tuples for batch execution.

        Returns:
            Total number of rows affected across the batch.

        Raises:
            DatabaseError: If batch execution fails.
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.executemany(query, params_list)
            self._commit(conn)
            return cursor.rowcount

    def create_table(
        self,
        table_name: str,
        columns: list[tuple[str, str]],
        constraints: list[str] | None = None,
    ) -> None:
        """Create a SQLite table idempotently after validating identifiers.

        Args:
            table_name: Valid ASCII identifier for the table.
            columns: List of ``(column_name, column_definition)`` tuples.
            constraints: Optional list of validated table-level constraints.

        Raises:
            DatabaseError: If any identifier or constraint fails validation.
        """
        if not is_valid_sql_identifier(table_name):
            raise DatabaseError(f"Invalid SQLite table identifier: {table_name}")
        if not columns:
            raise DatabaseError(f"Cannot create table without columns: {table_name}")
        parts = [validate_column_or_constraint(name, spec) for name, spec in columns]
        if constraints:
            parts.extend(validate_table_constraint(item) for item in constraints)
        columns_sql = ", ".join(parts)
        self.execute_update(
            f"CREATE TABLE IF NOT EXISTS {table_name} ({columns_sql});"
        )

    ############################################################################
    # RESOURCE MANAGEMENT & STORAGE DIAGNOSTICS
    ############################################################################

    def close(self) -> None:
        """Close all pooled SQLite connections and release resources."""
        pool = getattr(self, "_pool", None)
        if pool is None:
            return
        try:
            while not pool.empty():
                try:
                    pool.get_nowait().close()
                except queue.Empty:
                    break
                except (sqlite3.Error, OSError) as exc:
                    if getattr(self, "logger", None):
                        self.logger.warning(f"Error closing connection: {exc}")
            if getattr(self, "logger", None):
                self.logger.debug("All database connections closed")
        except (sqlite3.Error, OSError) as exc:
            if getattr(self, "logger", None):
                self.logger.error(f"Error during database cleanup: {exc}")

    def get_storage_stats(self) -> dict[str, Any]:
        """Collect database file sizes, table row counts, and host disk usage.

        Returns:
            Dictionary containing ``database`` and ``disk`` diagnostic metrics.
        """
        return build_storage_metrics(self.db_file, self._get_table_row_counts())

    ############################################################################
    # PRIVATE CONNECTION POOL & ERROR HELPERS
    ############################################################################

    def _get_table_row_counts(self) -> dict[str, int]:
        """Count rows across all application tables in SQLite.

        Returns:
            Mapping of validated table names to integer row counts.
        """
        counts: dict[str, int] = {}
        try:
            sql = (
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
            for row in self.execute_query(sql):
                table_name = str(row["name"])
                if is_valid_sql_identifier(table_name):
                    cnt_rows = self.execute_query(f"SELECT COUNT(*) FROM {table_name}")
                    counts[table_name] = int(cnt_rows[0][0] or 0) if cnt_rows else 0
        except DatabaseError as exc:
            self.logger.warning(f"Failed to query table row counts: {exc}")
        return counts

    def _acquire_valid_connection(self) -> sqlite3.Connection:
        """Acquire an active connection from the pool within timeout.

        Returns:
            Pooled ``sqlite3.Connection`` instance.

        Raises:
            DatabaseError: If no connection becomes available before timeout.
        """
        try:
            return self._pool.get(timeout=DatabaseDefaults.POOL_GET_TIMEOUT)
        except queue.Empty as exc:
            raise DatabaseError(
                "Connection pool exhausted - no connections available"
            ) from exc

    def _raise_database_error(self, exc: sqlite3.Error) -> None:
        """Translate a ``sqlite3.Error`` into the project exception hierarchy.

        Args:
            exc: Original SQLite error.

        Raises:
            DatabaseLockedError: When SQLite reports a lock contention timeout.
            DatabaseError: For all other SQLite errors.
        """
        if (
            isinstance(exc, sqlite3.OperationalError)
            and "database is locked" in str(exc).lower()
        ):
            self.logger.error(f"Database lock timeout: {exc}")
            raise DatabaseLockedError(str(exc)) from exc
        self.logger.error(f"Database operation failed: {exc}")
        raise DatabaseError(str(exc)) from exc

    def _safe_rollback(self, conn: sqlite3.Connection | None) -> None:
        """Roll back an uncommitted transaction without masking caller errors.

        Args:
            conn: Active SQLite connection, if acquired.
        """
        if conn is not None:
            try:
                conn.rollback()
            except sqlite3.Error as rollback_error:
                self.logger.warning(
                    f"Rollback failed during exception propagation: {rollback_error}"
                )

    def _release_connection(self, conn: sqlite3.Connection | None) -> None:
        """Return a connection to the pool or close it if the pool is full.

        Args:
            conn: Active SQLite connection to release.
        """
        if conn is None:
            return
        self._local.active_conn = None
        if conn.in_transaction:
            self._safe_rollback(conn)
        try:
            self._pool.put(conn, timeout=DatabaseDefaults.POOL_PUT_TIMEOUT)
        except queue.Full:
            conn.close()

    def _commit(self, conn: sqlite3.Connection) -> None:
        """Commit changes unless inside an outer ``transaction()`` block.

        Args:
            conn: Active SQLite connection.
        """
        if not getattr(self._local, "in_transaction", False):
            conn.commit()

    def _initialize_pool(self) -> None:
        """Populate the connection pool with ``max_connections`` connections.

        Raises:
            DatabaseError: If connection creation fails during startup.
        """
        try:
            for _ in range(self.max_connections):
                self._pool.put(self._create_connection())
        except (DatabaseError, sqlite3.Error, OSError) as exc:
            self.close()
            raise DatabaseError(
                f"Failed to initialize connection pool: {exc}"
            ) from exc

    def _create_connection(self) -> sqlite3.Connection:
        """Create a SQLite connection configured with WAL and wear-leveling PRAGMAs.

        Returns:
            Configured ``sqlite3.Connection`` instance.

        Raises:
            DatabaseError: If opening or configuring the connection fails.
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
            raise DatabaseError(
                f"Failed to create database connection: {exc}"
            ) from exc
