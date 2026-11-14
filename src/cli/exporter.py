#!/usr/bin/env python3
"""Configuration exporter module with hardened ``0600`` secret file permissions.

Serializes DynDNS zones, records, and credentials to YAML or JSON while
ensuring pure ``stdout`` output for Unix pipelines and ``O_NOFOLLOW``/``0600``
permissions on exported backup files.

Author: Manuel Ziel
License: MIT
"""

################################################################################
# IMPORTS & DEPENDENCIES
################################################################################

from abc import ABC, abstractmethod
from datetime import datetime, timezone
import json
import os
import sys
from typing import Any

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore[assignment]

from ..core.constants import ExportFormat, OwnershipDefaults
from ..core.exceptions import DatabaseError
from ..core.ownership import ensure_service_ownership
from .constants import CLIConfig
from .helpers.output import print_error, row_to_dict

################################################################################
# BASE EXPORTER CLASS
################################################################################


class BaseExporter(ABC):
    """Abstract base class for database configuration exporters.

    Attributes:
        config: ``ConfigManager`` instance.
        logger: Logger instance.
        db: ``Database`` connection pool.
    """

    def __init__(self, config: Any, logger: Any) -> None:
        """Initialize exporter and verify database availability.

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

    def export_to_file(
        self,
        output_file: str | None = None,
        format_type: str = ExportFormat.YAML,
    ) -> int:
        """Export serialized configuration to ``output_file`` or pure ``stdout``.

        Args:
            output_file: Optional output file path (``None`` writes to ``stdout``).
            format_type: Serialization format (``'yaml'`` or ``'json'``).

        Returns:
            Exit code (``0`` on success, ``1`` on failure).
        """
        try:
            config_data = self._build_export_data()
            rendered = self._serialize_data(config_data, format_type)
            if output_file:
                self._write_private_export_file(output_file, rendered)
            else:
                sys.stdout.write(rendered if rendered.endswith("\n") else f"{rendered}\n")
                sys.stdout.flush()
            return 0
        except PermissionError:
            print_error(f"Permission denied: Cannot write to {output_file}")
            return 1
        except Exception as exc:
            print_error(f"Export error: {exc}")
            self.logger.error(f"Export failed: {exc}")
            return 1

    def _serialize_data(self, config_data: dict[str, Any], format_type: str) -> str:
        """Serialize ``config_data`` as formatted JSON or YAML text.

        Args:
            config_data: Structured export payload dictionary.
            format_type: Target format (``'yaml'`` or ``'json'``).

        Returns:
            Serialized configuration string.

        Raises:
            ImportError: If YAML export is requested without PyYAML installed.
        """
        if format_type.lower() == ExportFormat.JSON:
            return json.dumps(config_data, indent=CLIConfig.JSON_INDENT)
        if yaml is None:
            raise ImportError("PyYAML not installed. Install with: pip install pyyaml")
        return str(yaml.dump(config_data, default_flow_style=False, sort_keys=False))

    def _write_private_export_file(self, output_file: str, rendered: str) -> None:
        """Write ``rendered`` to ``output_file`` with ``0600`` ``O_NOFOLLOW`` safety.

        Args:
            output_file: Target export file path.
            rendered: Serialized configuration payload.

        Raises:
            OSError: If ``output_file`` is a symbolic link or cannot be written.
        """
        resolved_path = os.path.abspath(os.path.expanduser(output_file))
        if os.path.islink(resolved_path):
            raise OSError(f"Refusing to write export through symlink: {resolved_path}")
        flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(resolved_path, flags, OwnershipDefaults.FILE_MODE_PRIVATE)
        os.fchmod(fd, OwnershipDefaults.FILE_MODE_PRIVATE)
        with os.fdopen(fd, "w", encoding="utf-8") as file_handle:
            file_handle.write(rendered if rendered.endswith("\n") else f"{rendered}\n")
        ensure_service_ownership(
            resolved_path,
            mode=OwnershipDefaults.FILE_MODE_PRIVATE,
            logger=self.logger,
            private_group=True,
        )
        self.logger.info(f"Configuration exported to {resolved_path}")

    @abstractmethod
    def _build_export_data(self) -> dict[str, Any]:
        """Construct the export data dictionary from SQLite."""


################################################################################
# CONCRETE CONFIGURATION EXPORTER
################################################################################


class ConfigExporter(BaseExporter):
    """Exports DynDNS zones, credentials, and DNS records."""

    def _build_export_data(self) -> dict[str, Any]:
        """Build the complete DynDNS export dictionary.

        Returns:
            Dictionary containing version, UTC timestamp, and ``zones`` list.
        """
        data: dict[str, Any] = {
            "version": CLIConfig.EXPORT_SCHEMA_VERSION,
            "exported_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "zones": [],
        }
        for zone_row in self.db.get_all_zones():
            zone_dict = row_to_dict(zone_row)
            if zone_dict:
                data["zones"].append(self._export_zone(zone_dict))
        return data

    def _export_zone(self, zone: dict[str, Any]) -> dict[str, Any]:
        """Build the export dictionary for a single DNS zone.

        Args:
            zone: Zone row dictionary.

        Returns:
            Exportable zone configuration dictionary.
        """
        zone_config: dict[str, Any] = {
            "zone_name": zone["zone_name"],
            "provider_zone_id": zone.get("provider_zone_id") or "",
            "enabled": bool(zone.get("enabled", True)),
        }
        self._export_zone_dyndns(zone["id"], zone_config)
        self._export_zone_records(zone["id"], zone_config)
        return zone_config

    def _export_zone_dyndns(self, zone_id: int, zone_config: dict[str, Any]) -> None:
        """Populate ``zone_config`` with decrypted DynDNS bundle credentials.

        Args:
            zone_id: Database zone ID.
            zone_config: Target zone export dictionary.
        """
        dyndns = row_to_dict(self.db.get_dyndns_config_by_zone(zone_id))
        if not dyndns:
            return
        zone_config["bulk_id"] = dyndns.get("bulk_id") or ""
        zone_config["api_key"] = dyndns.get("api_key") or ""
        if dyndns.get("domains"):
            try:
                raw = dyndns["domains"]
                domains = json.loads(raw) if isinstance(raw, str) else raw
                if domains:
                    zone_config["domains"] = domains
            except (json.JSONDecodeError, ValueError, TypeError):
                pass

    def _export_zone_records(self, zone_id: int, zone_config: dict[str, Any]) -> None:
        """Populate ``zone_config['records']`` with all configured DNS records.

        Args:
            zone_id: Database zone ID.
            zone_config: Target zone export dictionary.
        """
        records = self.db.get_records_by_zone(zone_id, enabled_only=False)
        zone_config["records"] = []
        for record_row in records:
            record = row_to_dict(record_row)
            if not record:
                continue
            record_config: dict[str, Any] = {
                "record_name": record["record_name"],
                "record_type": record["record_type"],
                "ttl": record.get("ttl", self.config.dns_default_ttl),
            }
            if record.get("provider_record_id"):
                record_config["provider_record_id"] = record["provider_record_id"]
            if record.get("enabled") is not None:
                record_config["enabled"] = bool(record["enabled"])
            zone_config["records"].append(record_config)
