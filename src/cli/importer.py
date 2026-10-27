#!/usr/bin/env python3
"""Configuration importer module.

This module defines the abstract base class and the concrete implementation
for importing configuration data into the DynDNS database.

Author: Manuel Ziel
License: MIT
"""

################################################################################
# IMPORTS & DEPENDENCIES
################################################################################

import json
import os
from typing import Any, Dict, List, Optional
from abc import ABC, abstractmethod

try:
    import yaml
except ImportError:
    yaml = None

from src.core.exceptions import DatabaseError
from src.core.constants import ExportFormat
from src.utils.colors import Colors
from .helpers.output import (
    print_error, print_success, print_info, print_warning,
    print_subsection
)

################################################################################
# BASE IMPORTER CLASS
################################################################################

class BaseImporter(ABC):
    """Abstract base class for configuration data ingestion.

    Encapsulates the file parsing logic for multiple formats and defines
    the interface for data processing and validation.

    Attributes:
        config: ConfigManager instance for system settings.
        logger: LoggerManager instance for operational tracking.
        db: Active database connection.
    """

    def __init__(self, config: Any, logger: Any) -> None:
        """Initialize the importer instance.

        Args:
            config: ConfigManager instance with database access.
            logger: LoggerManager instance for logging.

        Raises:
            DatabaseError: If the database is not initialized.
        """
        self.config = config
        self.logger = logger
        self.db = config.db
        
        if self.db is None:
            raise DatabaseError("Database not initialized.")
    

    def import_from_file(self, file_path: str, overwrite: bool = False) -> int:
        """Execute the full import workflow from a file.

        Parses the file, validates the structure, and dispatches the data
        to the concrete processing logic.

        Args:
            file_path: Path to the YAML or JSON file.
            overwrite: Whether to overwrite existing database records.

        Returns:
            int: 0 if the import was successful, 1 otherwise.
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
        except Exception as e:
            print_error(f"Import process failed: {e}")
            self.logger.error(f"Import error during processing: {e}")
            return 1
    

    def _parse_file(self, file_path: str) -> Optional[Dict[str, Any]]:
        """Parse file content based on extension (JSON or YAML).

        Args:
            file_path: Path to the file.

        Returns:
            Optional[Dict[str, Any]]: The parsed data dictionary.

        Raises:
            ImportError: If PyYAML is required but not installed.
            FileNotFoundError: If the file is missing.
        """
        resolved_path = os.path.abspath(os.path.expanduser(file_path))
        with open(resolved_path, 'r', encoding='utf-8') as f:
            if resolved_path.endswith(ExportFormat.EXT_JSON):
                if json is None:
                    raise ImportError("json module not available")
                return json.load(f)
            else:
                if yaml is None:
                    raise ImportError("PyYAML is not installed. YAML support is disabled.")
                return yaml.safe_load(f)
    

    def _validate_import_data(self, data: Dict[str, Any]) -> bool:
        """Perform high-level validation on the parsed data.

        Args:
            data: The parsed dictionary to check.

        Returns:
            bool: True if the structure is acceptable for processing.
        """
        if not isinstance(data, dict):
            return False
        
        if 'zones' not in data or not isinstance(data['zones'], list):
            print_error("Missing or invalid 'zones' array")
            return False
        
        for zone_data in data['zones']:
            if not isinstance(zone_data, dict):
                return False
            if 'zone_name' not in zone_data:
                print_error(f"Zone missing 'zone_name': {zone_data}")
                return False
            if 'records' in zone_data and not isinstance(zone_data['records'], list):
                print_error(f"Invalid 'records' in zone '{zone_data['zone_name']}'")
                return False
        
        return True


    @abstractmethod
    def _process_data(self, data: Dict[str, Any], overwrite: bool) -> None:
        """Concrete logic for storing data in the database.

        This method must be implemented by subclasses to handle specific
        entity mapping and storage rules.

        Args:
            data: The parsed configuration data dictionary.
            overwrite: Flag indicating whether to update existing entries.
        """
        pass

################################################################################
# CONCRETE CONFIGURATION IMPORTER
################################################################################

class ConfigImporter(BaseImporter):
    """Concrete implementation of the configuration importer.

    Imports zones, records, and credentials from a parsed dict structure.
    """

    def _process_data(self, data: Dict[str, Any], overwrite: bool) -> None:
        """Process and import zones with their associated records.

        Args:
            data: Validated import data containing zones array.
            overwrite: If True, update existing zones and records.
        """
        zones_data = data.get('zones', [])
        if not zones_data:
            print_error("No zones found in file")
            return

        stats: Dict[str, int] = {"added": 0, "updated": 0, "records": 0}
        self._import_zones(zones_data, overwrite, stats)

        print_subsection("Import Summary")
        print(f"{Colors.BOLD}Zones added:{Colors.NC}     {Colors.GREEN}{stats['added']}{Colors.NC}")
        print(f"{Colors.BOLD}Zones updated:{Colors.NC}   {Colors.CYAN}{stats['updated']}{Colors.NC}")
        print(f"{Colors.BOLD}Records total:{Colors.NC}   {Colors.GREEN}{stats['records']}{Colors.NC}")

        self.logger.info(
            f"Import completed: {stats['added']} added, {stats['updated']} updated, {stats['records']} records"
        )


    def _import_zones(self, zones_data: List[Dict[str, Any]], overwrite: bool, stats: Dict[str, int]) -> None:
        """Iterate and process each zone in the import dataset.

        Args:
            zones_data: List of zones to import.
            overwrite: If True, update existing records/settings.
            stats: Status counter tracking import metrics.
        """
        for zone_data in zones_data:
            try:
                self._import_single_zone(zone_data, overwrite, stats)
            except (KeyError, ValueError, TypeError) as e:
                print_error(f"Error importing zone '{zone_data.get('zone_name', '?')}': {e}")
                self.logger.error(f"Zone import error: {e}")


    def _import_single_zone(self, zone_data: Dict[str, Any], overwrite: bool, stats: Dict[str, int]) -> None:
        """Process a single zone's database insertion/updating and credentials.

        Args:
            zone_data: Data dictionary for a single zone.
            overwrite: If True, overwrite existing keys.
            stats: Status counter tracking import metrics.
        """
        zone_name = zone_data['zone_name']
        existing_zone = self.db.get_zone_by_name(zone_name)

        if existing_zone:
            if not overwrite:
                print_warning(f"Zone exists (skipped): {zone_name}")
                return
            zone_id = existing_zone['id']
            self.db.update_zone(zone_id, provider_zone_id=zone_data.get('provider_zone_id'), enabled=zone_data.get('enabled', True))
            stats['updated'] += 1
            print_info(f"Zone updated: {zone_name}")
        else:
            zone_id = self.db.add_zone(zone_name=zone_name, provider_zone_id=zone_data.get('provider_zone_id'), enabled=zone_data.get('enabled', True))
            stats['added'] += 1
            print_success(f"Zone added: {zone_name}")

        if 'bulk_id' in zone_data and 'api_key' in zone_data:
            self.db.set_dyndns_config(zone_id=zone_id, bulk_id=zone_data['bulk_id'], api_key=zone_data['api_key'])

        record_count = self._import_zone_records(zone_id, zone_data.get('records', []), overwrite)
        stats['records'] += record_count


    def _import_zone_records(self, zone_id: int, records_data: List[Dict[str, Any]], overwrite: bool) -> int:
        """Process and import DNS records for a specific zone.

        Args:
            zone_id: Database zone ID.
            records_data: List of record data dicts.
            overwrite: If True, overwrite existing record attributes.

        Returns:
            Number of imported or updated records.
        """
        imported_count = 0
        for record_data in records_data:
            try:
                if self._import_single_record(zone_id, record_data, overwrite):
                    imported_count += 1
            except (KeyError, ValueError, TypeError) as e:
                print_error(f"  Error importing record: {e}")
                self.logger.error(f"Record import error: {e}")
        return imported_count


    def _import_single_record(self, zone_id: int, record_data: Dict[str, Any], overwrite: bool) -> bool:
        """Add or update a single record in the database.

        Args:
            zone_id: Zone database ID.
            record_data: Record attributes dictionary.
            overwrite: Whether to overwrite existing settings.

        Returns:
            True if record was imported/updated, False otherwise.
        """
        record_name = record_data['record_name']
        record_type = record_data['record_type']
        existing = self.db.get_record_by_name_and_type(zone_id, record_name, record_type)

        if existing:
            if not overwrite:
                print(f"  {Colors.DIM}├─ Record exists (skipped): {record_name} ({record_type}){Colors.NC}")
                return False
            self.db.update_record(
                existing['id'],
                ttl=record_data.get('ttl', self.config.dns_default_ttl),
                enabled=record_data.get('enabled', True)
            )
            print(f"  {Colors.DIM}├─ Record updated: {record_name} ({record_type}){Colors.NC}")
        else:
            self.db.add_record(
                zone_id=zone_id,
                record_name=record_name,
                record_type=record_type,
                ttl=record_data.get('ttl', self.config.dns_default_ttl),
                enabled=record_data.get('enabled', True)
            )
            print(f"  {Colors.DIM}├─ Record added: {record_name} ({record_type}){Colors.NC}")

        return True