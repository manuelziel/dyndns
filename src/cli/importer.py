#!/usr/bin/env python3
"""Configuration importer module with atomic SQLite transaction support.

Parses YAML or JSON configuration backups, validates schema invariants, and
imports zones, credentials, and DNS records inside an atomic transaction.

Author: Manuel Ziel
License: MIT
"""

################################################################################
# IMPORTS & DEPENDENCIES
################################################################################

from abc import ABC, abstractmethod
import json
import os
from typing import Any

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore[assignment]

from ..core.constants import ExportFormat
from ..core.exceptions import DatabaseError
from ..utils.colors import Colors
from .helpers.output import (
    print_error,
    print_info,
    print_status,
    print_subsection,
    print_success,
    print_warning,
)

################################################################################
# BASE IMPORTER CLASS
################################################################################


class BaseImporter(ABC):
    """Abstract base class for configuration file importers.

    Attributes:
        config: ``ConfigManager`` instance.
        logger: Logger instance.
        db: ``Database`` connection pool.
    """

    def __init__(self, config: Any, logger: Any) -> None:
        """Initialize importer and verify database availability.

        Args:
            config: ``ConfigManager`` instance.
            logger: Logger instance.

        Raises:
            DatabaseError: If ``config.db`` is ``None``.
        """
        self.config = config
        self.logger = logger
        self.db = config.db
        if self.db is None:
            raise DatabaseError("Database not initialized.")

    def import_from_file(self, file_path: str, overwrite: bool = False) -> int:
        """Parse, validate, and import configuration from ``file_path``.

        Args:
            file_path: Path to YAML or JSON backup file.
            overwrite: Update pre-existing zones and records when True.

        Returns:
            Exit code (``0`` on success, ``1`` on failure).
        """
        try:
            self.logger.info(f"Initiating import from {file_path}")
            data = self._parse_file(file_path)
            if not data:
                print_error("Parsed file is empty or invalid.")
                return 1
            if not self._validate_import_data(data):
                print_error("Data structure validation failed.")
                return 1
            self._process_data(data, overwrite)
            self.logger.info(f"Successfully imported configuration from {file_path}")
            return 0
        except FileNotFoundError:
            print_error(f"File not found: {file_path}")
            return 1
        except Exception as exc:
            print_error(f"Import process failed: {exc}")
            self.logger.error(f"Import error during processing: {exc}")
            return 1

    def _parse_file(self, file_path: str) -> dict[str, Any] | None:
        """Parse JSON or YAML configuration file safely without symlink traversal.

        Args:
            file_path: Path to configuration file.

        Returns:
            Parsed top-level dictionary or ``None``.

        Raises:
            OSError: If ``file_path`` is a symbolic link.
            ImportError: If YAML parsing is needed without PyYAML installed.
        """
        resolved_path = os.path.abspath(os.path.expanduser(file_path))
        if os.path.islink(resolved_path):
            raise OSError(f"Refusing to import from symlinked file: {resolved_path}")
        with open(resolved_path, "r", encoding="utf-8") as file_handle:
            if resolved_path.lower().endswith(ExportFormat.EXT_JSON):
                parsed = json.load(file_handle)
            else:
                if yaml is None:
                    raise ImportError("PyYAML is not installed. YAML support is disabled.")
                parsed = yaml.safe_load(file_handle)
        return parsed if isinstance(parsed, dict) else None

    def _validate_import_data(self, data: dict[str, Any]) -> bool:
        """Validate the top-level ``zones`` schema of ``data``.

        Args:
            data: Parsed configuration dictionary.

        Returns:
            True if schema invariants hold, False otherwise.
        """
        if "zones" not in data or not isinstance(data["zones"], list):
            print_error("Missing or invalid 'zones' array")
            return False
        for zone_data in data["zones"]:
            if not isinstance(zone_data, dict) or "zone_name" not in zone_data:
                print_error(f"Zone entry missing 'zone_name': {zone_data}")
                return False
            if "records" in zone_data and not isinstance(zone_data["records"], list):
                print_error(f"Invalid 'records' in zone '{zone_data['zone_name']}'")
                return False
        return True

    @abstractmethod
    def _process_data(self, data: dict[str, Any], overwrite: bool) -> None:
        """Persist validated import ``data`` into SQLite."""


################################################################################
# CONCRETE CONFIGURATION IMPORTER
################################################################################


class ConfigImporter(BaseImporter):
    """Imports DynDNS zones, credentials, and DNS records into SQLite."""

    def _process_data(self, data: dict[str, Any], overwrite: bool) -> None:
        """Import all zones and records inside a single SQLite transaction.

        Args:
            data: Validated import dictionary.
            overwrite: Overwrite existing zones and records when True.
        """
        zones_data: list[dict[str, Any]] = data.get("zones", [])
        if not zones_data:
            print_error("No zones found in file")
            return
        stats = {"added": 0, "updated": 0, "records": 0}
        with self.db.transaction():
            self._import_zones(zones_data, overwrite, stats)
        print_subsection("Import Summary")
        print_status(f"Zones added:     {stats['added']}", Colors.GREEN)
        print_status(f"Zones updated:   {stats['updated']}", Colors.CYAN)
        print_status(f"Records total:   {stats['records']}", Colors.GREEN)
        self.logger.info(
            f"Import completed: {stats['added']} added, "
            f"{stats['updated']} updated, {stats['records']} records"
        )

    def _import_zones(
        self,
        zones_data: list[dict[str, Any]],
        overwrite: bool,
        stats: dict[str, int],
    ) -> None:
        """Import each zone entry in ``zones_data``.

        Args:
            zones_data: List of zone dictionaries.
            overwrite: Overwrite existing entries when True.
            stats: Mutable import counter dictionary.
        """
        for zone_data in zones_data:
            try:
                self._import_single_zone(zone_data, overwrite, stats)
            except (KeyError, ValueError, TypeError) as exc:
                print_error(f"Error importing zone '{zone_data.get('zone_name', '?')}': {exc}")
                self.logger.error(f"Zone import error: {exc}")

    def _import_single_zone(
        self,
        zone_data: dict[str, Any],
        overwrite: bool,
        stats: dict[str, int],
    ) -> None:
        """Insert or update a single zone, its credentials, and its records.

        Args:
            zone_data: Zone configuration dictionary.
            overwrite: Overwrite existing entries when True.
            stats: Mutable import counter dictionary.
        """
        zone_id = self._upsert_imported_zone(zone_data, overwrite, stats)
        if zone_id is None:
            return
        if zone_data.get("bulk_id") and zone_data.get("api_key"):
            self.db.set_dyndns_config(
                zone_id=zone_id,
                bulk_id=zone_data["bulk_id"],
                api_key=zone_data["api_key"],
                domains=zone_data.get("domains"),
            )
        stats["records"] += self._import_zone_records(
            zone_id, zone_data.get("records", []), overwrite
        )

    def _upsert_imported_zone(
        self,
        zone_data: dict[str, Any],
        overwrite: bool,
        stats: dict[str, int],
    ) -> int | None:
        """Create or update the zone entry for ``zone_data`` and return its ID.

        Args:
            zone_data: Zone configuration dictionary.
            overwrite: Overwrite existing zone when True.
            stats: Mutable import counter dictionary.

        Returns:
            Zone database ID, or ``None`` if skipped.
        """
        zone_name = zone_data["zone_name"]
        existing_zone = self.db.get_zone_by_name(zone_name)
        if existing_zone:
            if not overwrite:
                print_warning(f"Zone exists (skipped): {zone_name}")
                return None
            zone_id = int(existing_zone["id"])
            self.db.update_zone(
                zone_id,
                provider_zone_id=zone_data.get("provider_zone_id"),
                enabled=zone_data.get("enabled", True),
            )
            stats["updated"] += 1
            print_info(f"Zone updated: {zone_name}")
            return zone_id

        created_id = self.db.add_zone(
            zone_name=zone_name,
            provider_zone_id=zone_data.get("provider_zone_id"),
            enabled=zone_data.get("enabled", True),
        )
        if created_id is None:
            raise DatabaseError(f"Failed to create zone '{zone_name}'")
        stats["added"] += 1
        print_success(f"Zone added: {zone_name}")
        return created_id

    def _import_zone_records(
        self,
        zone_id: int,
        records_data: list[dict[str, Any]],
        overwrite: bool,
    ) -> int:
        """Import DNS records belonging to ``zone_id``.

        Args:
            zone_id: Database zone ID.
            records_data: List of record dictionaries.
            overwrite: Overwrite existing records when True.

        Returns:
            Number of added or updated records.
        """
        imported_count = 0
        for record_data in records_data:
            try:
                if self._import_single_record(zone_id, record_data, overwrite):
                    imported_count += 1
            except (KeyError, ValueError, TypeError) as exc:
                print_error(f"  Error importing record: {exc}")
                self.logger.error(f"Record import error: {exc}")
        return imported_count

    def _import_single_record(
        self, zone_id: int, record_data: dict[str, Any], overwrite: bool
    ) -> bool:
        """Insert or update a single DNS record in SQLite.

        Args:
            zone_id: Database zone ID.
            record_data: Record configuration dictionary.
            overwrite: Overwrite existing record attributes when True.

        Returns:
            True if inserted or updated, False when skipped.
        """
        record_name = record_data["record_name"]
        record_type = record_data["record_type"]
        existing = self.db.get_record_by_name_and_type(zone_id, record_name, record_type)
        if existing:
            if not overwrite:
                print_status(
                    f"  |-- Record exists (skipped): {record_name} ({record_type})",
                    Colors.DIM,
                )
                return False
            self.db.update_record(
                existing["id"],
                ttl=record_data.get("ttl", self.config.dns_default_ttl),
                enabled=record_data.get("enabled", True),
            )
            print_status(
                f"  |-- Record updated: {record_name} ({record_type})", Colors.DIM
            )
            return True

        self.db.add_record(
            zone_id=zone_id,
            record_name=record_name,
            record_type=record_type,
            provider_record_id=record_data.get("provider_record_id"),
            ttl=record_data.get("ttl", self.config.dns_default_ttl),
            enabled=record_data.get("enabled", True),
        )
        print_status(
            f"  |-- Record added: {record_name} ({record_type})", Colors.DIM
        )
        return True
