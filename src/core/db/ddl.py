#!/usr/bin/env python3
"""Pure SQLite DDL validation and storage-metric formatting helpers.

Provides stateless ASCII SQL identifier/constraint validation for ``create_table``
and disk/SQLite byte-size calculation utilities for ``DatabaseEngine``.

Author: Manuel Ziel
License: MIT
"""

################################################################################
# IMPORTS & DEPENDENCIES
################################################################################

import os
import re
import shutil
from typing import Any

from ..constants import StorageConstants
from ..exceptions import DatabaseError

################################################################################
# MODULE CONSTANTS
################################################################################

_TABLE_CONSTRAINT_RE = re.compile(
    r"^(UNIQUE\s*\([a-zA-Z_][a-zA-Z0-9_]*(,\s*[a-zA-Z_][a-zA-Z0-9_]*)*\)|"
    r"FOREIGN KEY\s*\([a-zA-Z_][a-zA-Z0-9_]*\)\s*REFERENCES\s+"
    r"[a-zA-Z_][a-zA-Z0-9_]*\([a-zA-Z_][a-zA-Z0-9_]*\)"
    r"(\s+ON DELETE\s+(CASCADE|SET NULL|RESTRICT|NO ACTION))?)$"
)

################################################################################
# SQL IDENTIFIER & DDL VALIDATION HELPERS
################################################################################


def is_valid_sql_identifier(name: str) -> bool:
    """Return True if ``name`` is a safe ASCII SQL identifier.

    Args:
        name: Candidate table or column identifier.

    Returns:
        True when ``name`` consists solely of ASCII identifier characters.
    """
    return bool(name and name.isascii() and name.isidentifier())


def validate_column_or_constraint(col_name: str, col_type: str) -> str:
    """Validate and format a single column definition or table constraint tuple.

    Args:
        col_name: Column identifier or legacy constraint prefix.
        col_type: SQLite column type/constraint clause.

    Returns:
        Validated SQL fragment for ``CREATE TABLE``.

    Raises:
        DatabaseError: If identifier or type clause contains unsafe syntax.
    """
    combined = f"{col_name} {col_type}".strip()
    if ";" in combined or "\x00" in combined or "--" in combined or "/*" in combined:
        raise DatabaseError(f"Unsafe SQLite DDL definition rejected: {combined}")
    if is_valid_sql_identifier(col_name):
        if not col_type or not col_type.strip():
            raise DatabaseError(f"Empty SQLite column type for column: {col_name}")
        return f"{col_name} {col_type.strip()}"
    if _TABLE_CONSTRAINT_RE.fullmatch(combined):
        return combined
    raise DatabaseError(f"Invalid SQLite column identifier or constraint: {combined}")


def validate_table_constraint(constraint: str) -> str:
    """Validate an explicit table-level ``UNIQUE`` or ``FOREIGN KEY`` clause.

    Args:
        constraint: Table-level SQL constraint expression.

    Returns:
        Cleaned SQL constraint expression.

    Raises:
        DatabaseError: If ``constraint`` does not match safe constraint syntax.
    """
    cleaned = constraint.strip()
    if not _TABLE_CONSTRAINT_RE.fullmatch(cleaned):
        raise DatabaseError(f"Invalid SQLite table constraint: {constraint}")
    return cleaned


################################################################################
# STORAGE SIZE & FORMATTING HELPERS
################################################################################


def format_storage_bytes(size_bytes: int) -> str:
    """Format a byte count into a human-readable unit string.

    Args:
        size_bytes: Raw byte count to format.

    Returns:
        Formatted byte size string (e.g. ``'14.06 MB'``).
    """
    val = float(max(0, size_bytes))
    for unit in StorageConstants.UNITS:
        if val < StorageConstants.BYTES_PER_KB or unit == StorageConstants.UNITS[-1]:
            return f"{val:.{StorageConstants.DEFAULT_DECIMALS}f} {unit}"
        val /= StorageConstants.BYTES_PER_KB
    return f"{val:.{StorageConstants.DEFAULT_DECIMALS}f} B"


def _build_disk_metrics(db_dir: str) -> dict[str, Any]:
    """Build filesystem free/total disk usage dictionary for ``db_dir``.

    Args:
        db_dir: Directory containing the SQLite database.

    Returns:
        Dictionary of host mount disk usage metrics.
    """
    usage = shutil.disk_usage(db_dir if os.path.exists(db_dir) else ".")
    used_pct = (
        round(
            (usage.used / usage.total) * StorageConstants.PERCENTAGE_FACTOR,
            StorageConstants.DISK_PERCENT_DECIMALS,
        )
        if usage.total > 0
        else 0.0
    )
    return {
        "mount_point": db_dir,
        "free_bytes": usage.free,
        "free_human": format_storage_bytes(usage.free),
        "total_bytes": usage.total,
        "total_human": format_storage_bytes(usage.total),
        "used_percent": used_pct,
    }


def build_storage_metrics(
    db_file: str, row_counts: dict[str, int]
) -> dict[str, Any]:
    """Build combined SQLite file and filesystem disk usage diagnostic dictionary.

    Args:
        db_file: Path to the SQLite database file.
        row_counts: Mapping of table names to row counts.

    Returns:
        Dictionary with ``database`` and ``disk`` diagnostic blocks.
    """
    db_path = os.path.abspath(db_file)
    db_s = os.path.getsize(db_path) if os.path.exists(db_path) else 0
    wal_s = os.path.getsize(f"{db_path}-wal") if os.path.exists(f"{db_path}-wal") else 0
    shm_s = os.path.getsize(f"{db_path}-shm") if os.path.exists(f"{db_path}-shm") else 0
    total_s = db_s + wal_s + shm_s
    db_dir = os.path.dirname(db_path) or "."
    return {
        "database": {
            "path": db_path,
            "db_size_bytes": db_s,
            "db_size_human": format_storage_bytes(db_s),
            "wal_size_bytes": wal_s,
            "wal_size_human": format_storage_bytes(wal_s),
            "shm_size_bytes": shm_s,
            "shm_size_human": format_storage_bytes(shm_s),
            "total_size_bytes": total_s,
            "total_size_human": format_storage_bytes(total_s),
            "row_counts": row_counts,
        },
        "disk": _build_disk_metrics(db_dir),
    }
