#!/usr/bin/env python3
"""Configuration exporter base module.

This module defines the abstract base class and the concrete implementation
for exporting configuration data from the DynDNS database.

Author: Manuel Ziel
License: MIT
"""

################################################################################
# IMPORTS & DEPENDENCIES
################################################################################

import json
import os
from typing import Any, Dict, Optional
from datetime import datetime, timezone
from abc import ABC, abstractmethod

try:
    import yaml
except ImportError:
    yaml = None

from src.core.exceptions import DatabaseError
from src.core.constants import ExportFormat
from src.core.ownership import ensure_service_ownership
from .helpers.output import print_error, row_to_dict


################################################################################
# BASE EXPORTER CLASS
################################################################################

class BaseExporter(ABC):
    """Abstract base class for configuration exporters.

    Attributes:
        config: ConfigManager instance with database access.
        logger: LoggerManager instance for logging.
        db: Database connection from config.
    """

    ############################################################################
    # Lifecycle Methods
    ############################################################################

    def __init__(self, config: Any, logger: Any) -> None:
        """Initialize exporter.

        Args:
            config: ConfigManager instance with database access.
            logger: LoggerManager instance for logging.

        Raises:
            DatabaseError: If database is not initialized.
        """
        self.config = config
        self.logger = logger
        self.db = config.db
        
        if self.db is None:
            raise DatabaseError("Database not initialized.")

    ############################################################################
    # Concrete Implementations
    ############################################################################

    def export_to_file(self, output_file: Optional[str] = None, format_type: str = ExportFormat.YAML) -> int:
        """Export configuration to file or stdout.

        Args:
            output_file: Output file path (None for stdout).
            format_type: Export format ('yaml' or 'json').

        Returns:
            Exit code (0 for success, 1 for failure).
        """
        try:
            self.logger.info("Exporting configuration")
            
            config_data = self._build_export_data()
            
            if format_type.lower() == ExportFormat.JSON:
                output = json.dumps(config_data, indent=2)
            else:
                if yaml is None:
                    raise ImportError("PyYAML not installed. Install with: pip install pyyaml")
                output = yaml.dump(config_data, default_flow_style=False, sort_keys=False)
            
            if output_file:
                resolved_path = os.path.abspath(os.path.expanduser(output_file))
                with open(resolved_path, 'w', encoding='utf-8') as f:
                    f.write(output)
                ensure_service_ownership(resolved_path, logger=self.logger)
                self.logger.info(f"Configuration exported to {resolved_path}")
            else:
                print(output)
            
            return 0
            
        except PermissionError:
            print_error(f"Permission denied: Cannot write to {output_file}")
            return 1
        except Exception as e:
            print_error(f"Export error: {e}")
            self.logger.error(f"Export failed: {e}")
            return 1

    ############################################################################
    # Abstract Methods - Must be implemented in subclass
    ############################################################################

    @abstractmethod
    def _build_export_data(self) -> Dict[str, Any]:
        """Build export data structure from database.

        Returns:
            Dictionary representing the export configuration schema.
        """
        pass

################################################################################
# CONCRETE CONFIGURATION EXPORTER
################################################################################

class ConfigExporter(BaseExporter):
    """Concrete implementation of the configuration exporter.

    Serializes database configurations to export structures.
    """

    def _build_export_data(self) -> Dict[str, Any]:
        """Build the export data structure with all zones and records.

        Returns:
            Dictionary containing version, timestamp, and zones array.
        """
        data = {
            'version': '1.0',
            'exported_at': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
            'zones': []
        }

        zones = self.db.get_all_zones()
        for zone_row in zones:
            zone_config = self._export_zone(row_to_dict(zone_row))
            data['zones'].append(zone_config)

        return data

    def _export_zone(self, zone: Dict[str, Any]) -> Dict[str, Any]:
        """Build configuration dictionary for a single zone.

        Args:
            zone: Dictionary representing database zone row.

        Returns:
            Formatted dictionary ready for export.
        """
        zone_config = {
            'zone_name': zone['zone_name'],
            'provider_zone_id': zone.get('provider_zone_id', ''),
            'enabled': bool(zone.get('enabled', True))
        }

        self._export_zone_dyndns(zone['id'], zone_config)
        self._export_zone_records(zone['id'], zone_config)

        return zone_config

    def _export_zone_dyndns(self, zone_id: int, zone_config: Dict[str, Any]) -> None:
        """Fetch and inject DynDNS configuration fields.

        Args:
            zone_id: Database zone ID.
            zone_config: Target zone export configuration dictionary.
        """
        dyndns_row = self.db.get_dyndns_config_by_zone(zone_id)
        if not dyndns_row:
            return

        dyndns = row_to_dict(dyndns_row)
        zone_config['bulk_id'] = dyndns.get('bulk_id', '')
        zone_config['api_key'] = dyndns.get('api_key', '')

        if dyndns.get('domains'):
            try:
                domains = json.loads(dyndns['domains']) if isinstance(dyndns['domains'], str) else dyndns['domains']
                if domains:
                    zone_config['domains'] = domains
            except (json.JSONDecodeError, ValueError, TypeError):
                pass

    def _export_zone_records(self, zone_id: int, zone_config: Dict[str, Any]) -> None:
        """Fetch and inject DNS records into a zone export dictionary.

        Args:
            zone_id: Database zone ID.
            zone_config: Target zone export configuration dictionary.
        """
        records = self.db.get_records_by_zone(zone_id, enabled_only=False)
        zone_config['records'] = []

        for record_row in records:
            record = row_to_dict(record_row)
            record_config = {
                'record_name': record['record_name'],
                'record_type': record['record_type'],
                'ttl': record.get('ttl', self.config.dns_default_ttl)
            }

            if record.get('provider_record_id'):
                record_config['provider_record_id'] = record['provider_record_id']

            if record.get('enabled') is not None:
                record_config['enabled'] = bool(record['enabled'])

            zone_config['records'].append(record_config)
