#!/usr/bin/env python3
"""Helper class for provider REST API zone and record synchronization.

Encapsulates direct REST calls to IONOS DNS API endpoints for fetching zones,
matching record IDs, recreating missing records, and updating individual IP
records via ``PUT`` requests.

Author: Manuel Ziel
License: MIT
"""

################################################################################
# IMPORTS & DEPENDENCIES
################################################################################

from datetime import datetime
from typing import Any

from ...api.provider import ProviderDNSClient
from ...core.constants import DatabaseDefaults, PlaceholderIP, RecordType, SyncStatus
from ...core.exceptions import DynDNSException, ValidationError
from ...utils.colors import LOG_SYMBOLS

################################################################################
# REST RECORD HANDLER CLASS
################################################################################


class RESTRecordHandler:
    """Handles direct REST API operations for DNS zones and records.

    Attributes:
        config: ``ConfigManager`` instance.
        database: ``Database`` manager instance.
        network: ``NetworkData`` instance.
        logger: Logger instance.
    """

    def __init__(
        self, config: Any, database: Any, network: Any, logger: Any
    ) -> None:
        """Initialize REST record handler.

        Args:
            config: ``ConfigManager`` instance.
            database: ``Database`` manager instance.
            network: ``NetworkData`` instance.
            logger: Logger instance.
        """
        self.config = config
        self.database = database
        self.network = network
        self.logger = logger

    ############################################################################
    # ZONE & RECORD MATCHING
    ############################################################################

    def sync_zone_records(
        self,
        client: ProviderDNSClient,
        zone: dict[str, Any],
        is_startup: bool = False,
    ) -> dict[str, Any] | None:
        """Fetch zones and records from the REST API and match local SQLite rows.

        Args:
            client: Active ``ProviderDNSClient``.
            zone: Zone dictionary.
            is_startup: True during the initial daemon startup cycle.

        Returns:
            Reconciliation summary dictionary or ``None`` on error.
        """
        try:
            provider_zone_id = self._resolve_provider_zone_id(client, zone)
            if not provider_zone_id:
                return None
            provider_records = client.get_zone_records(provider_zone_id)
            if provider_records is None:
                self.logger.error(f"Failed to fetch records for zone '{zone['zone_name']}'")
                return None
            if is_startup:
                self.logger.info(
                    f"Startup Verification: Found {len(provider_records)} "
                    f"total record(s) on provider IONOS for zone '{zone['zone_name']}'"
                )
            db_records = self.database.get_records_by_zone(zone["id"], enabled_only=False)
            matched_count, missing_records = self._match_records_with_provider(
                db_records, provider_records
            )
            return {
                "provider_zone_id": provider_zone_id,
                "provider_records": provider_records,
                "missing_records": missing_records,
                "matched_count": matched_count,
            }
        except DynDNSException as exc:
            self.logger.error(f"Failed to sync REST records for '{zone['zone_name']}': {exc}")
            return None

    def _resolve_provider_zone_id(
        self, client: ProviderDNSClient, zone: dict[str, Any]
    ) -> str | None:
        """Resolve and persist ``provider_zone_id`` for ``zone``.

        Args:
            client: Active ``ProviderDNSClient``.
            zone: Zone dictionary.

        Returns:
            Provider zone ID string or ``None`` if unavailable.
        """
        self.logger.debug(f"{LOG_SYMBOLS['ARROW']} Fetching zones from provider...")
        provider_zones = client.get_zones()
        if not provider_zones:
            self.logger.error(f"Failed to fetch zones from provider for '{zone['zone_name']}'")
            return None
        provider_zone = next(
            (pz for pz in provider_zones if pz["name"] == zone["zone_name"]), None
        )
        if not provider_zone:
            available = [pz["name"] for pz in provider_zones]
            self.logger.error(
                f"Zone '{zone['zone_name']}' not found in provider. Available: {available}"
            )
            return None
        provider_zone_id = str(provider_zone["id"])
        if zone.get("provider_zone_id") != provider_zone_id:
            self.database.update_zone(zone["id"], provider_zone_id=provider_zone_id)
        return provider_zone_id

    def _match_records_with_provider(
        self,
        db_records: list[dict[str, Any]],
        provider_records: list[dict[str, Any]],
    ) -> tuple[int, list[dict[str, Any]]]:
        """Match local SQLite records against provider API records.

        Args:
            db_records: Local database record dictionaries.
            provider_records: Provider API record dictionaries.

        Returns:
            Tuple ``(matched_count, missing_records)``.
        """
        matched_count = 0
        missing_records: list[dict[str, Any]] = []
        for db_record in db_records:
            db_name = db_record["record_name"].rstrip(".")
            provider_record = next(
                (
                    pr
                    for pr in provider_records
                    if pr["name"].rstrip(".") == db_name
                    and pr["type"] == db_record["record_type"]
                ),
                None,
            )
            if provider_record:
                if db_record.get("provider_record_id") != provider_record["id"]:
                    self.database.update_record_provider_id(
                        db_record["id"], provider_record["id"]
                    )
                matched_count += 1
                self.logger.debug(
                    f"  Matched '{db_record['record_name']}' ({db_record['record_type']}) "
                    f"{LOG_SYMBOLS['ARROW']} ID: {provider_record['id']}"
                )
            else:
                missing_records.append(db_record)
                self.logger.warning(
                    f"  Record '{db_record['record_name']}' ({db_record['record_type']}) "
                    "not found in provider"
                )
        return matched_count, missing_records

    ############################################################################
    # RECORD CREATION & INDIVIDUAL REST UPDATES
    ############################################################################

    def create_missing_records(
        self,
        client: ProviderDNSClient,
        zone: dict[str, Any],
        missing_records: list[dict[str, Any]],
    ) -> int:
        """Create ``missing_records`` on the provider via ``POST``.

        Args:
            client: Active ``ProviderDNSClient``.
            zone: Zone dictionary containing ``provider_zone_id``.
            missing_records: Local records missing from the provider.

        Returns:
            Number of created records.
        """
        if not missing_records:
            return 0
        try:
            self.logger.info(
                f"Creating {len(missing_records)} missing record(s) in provider..."
            )
            api_records = self._build_api_records_payload(missing_records)
            if not api_records:
                return 0
            if client.create_records(
                zone_id=zone["provider_zone_id"], records=api_records
            ):
                self.logger.info(f"Successfully created {len(api_records)} record(s)")
                return len(api_records)
            self.logger.error("Failed to create records in provider")
            return 0
        except DynDNSException as exc:
            self.logger.error(f"Failed to create missing records: {exc}")
            return 0

    def _build_api_records_payload(
        self, missing_records: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Build REST ``POST`` payload dictionaries for ``missing_records``.

        Args:
            missing_records: Local record dictionaries.

        Returns:
            List of provider-ready record payload dictionaries.
        """
        api_records: list[dict[str, Any]] = []
        for db_record_row in missing_records:
            db_record = dict(db_record_row)
            content = self._resolve_initial_content(db_record)
            if content is None:
                continue
            api_records.append(
                {
                    "name": db_record["record_name"],
                    "type": db_record["record_type"],
                    "content": content,
                    "ttl": db_record.get("ttl", self.config.dns_default_ttl),
                    "disabled": not db_record.get("enabled", True),
                }
            )
        return api_records

    def _resolve_initial_content(self, db_record: dict[str, Any]) -> str | None:
        """Determine initial IP content or placeholder for ``db_record``.

        Args:
            db_record: Local record dictionary.

        Returns:
            IP address string or ``None`` if record type is unsupported.
        """
        try:
            if db_record["record_type"] == RecordType.A:
                return self.network.ipv4_address or PlaceholderIP.get(RecordType.A)
            if db_record["record_type"] == RecordType.AAAA:
                return self.network.ipv6_address or PlaceholderIP.get(RecordType.AAAA)
            self.logger.warning(f"Unsupported record type '{db_record['record_type']}'")
            return None
        except (ValidationError, ValueError) as exc:
            self.logger.error(f"Invalid record type for '{db_record['record_name']}': {exc}")
            return None

    def rematch_created_records(
        self,
        client: ProviderDNSClient,
        provider_zone_id: str,
        missing_records: list[dict[str, Any]],
    ) -> int:
        """Re-fetch zone records after creation and store new provider IDs.

        Args:
            client: Active ``ProviderDNSClient``.
            provider_zone_id: Provider zone identifier.
            missing_records: Records that were just created.

        Returns:
            Count of newly matched records.
        """
        self.logger.debug("Re-fetching provider records to get new IDs...")
        provider_records = client.get_zone_records(provider_zone_id)
        if not provider_records:
            return 0
        matched_count = 0
        for db_record_row in missing_records:
            db_record = dict(db_record_row)
            db_name = db_record["record_name"].rstrip(".")
            provider_record = next(
                (
                    pr
                    for pr in provider_records
                    if pr["name"].rstrip(".") == db_name
                    and pr["type"] == db_record["record_type"]
                ),
                None,
            )
            if provider_record:
                self.database.update_record_provider_id(
                    db_record["id"], provider_record["id"]
                )
                matched_count += 1
            else:
                self.logger.warning(
                    f"  Newly created '{db_record['record_name']}' still not found"
                )
        return matched_count

    def update_record_ip(
        self,
        client: ProviderDNSClient,
        zone: dict[str, Any],
        record: dict[str, Any],
        new_ip: str,
    ) -> bool:
        """Update a single DNS record IP on the provider via REST ``PUT``.

        Args:
            client: Active ``ProviderDNSClient``.
            zone: Zone dictionary.
            record: Record dictionary.
            new_ip: Target IPv4/IPv6 address string.

        Returns:
            True on success, False otherwise.
        """
        if not record.get("provider_record_id") or not zone.get("provider_zone_id"):
            return False
        try:
            success = client.update_record(
                zone_id=zone["provider_zone_id"],
                record_id=record["provider_record_id"],
                content=new_ip,
                ttl=record.get("ttl", self.config.dns_default_ttl),
            )
            if success:
                if self.config.daemon_sync_checks:
                    self.database.update_record(
                        record["id"],
                        sync_status=SyncStatus.SYNCED,
                        last_synced_at=datetime.now().strftime(
                            DatabaseDefaults.DB_TIMESTAMP_FORMAT
                        ),
                    )
                return True
            if self.config.daemon_sync_checks:
                self._check_and_clear_orphaned_record(client, zone, record)
            return False
        except DynDNSException as exc:
            self.logger.error(
                f"Provider API update failed for '{record['record_name']}': {exc}"
            )
            return False

    def _check_and_clear_orphaned_record(
        self,
        client: ProviderDNSClient,
        zone: dict[str, Any],
        record: dict[str, Any],
    ) -> None:
        """Mark ``record`` as ``orphaned`` in SQLite if deleted on the provider.

        Args:
            client: Active ``ProviderDNSClient``.
            zone: Zone dictionary.
            record: Record dictionary.
        """
        self.logger.warning(
            f"Update failed for '{record['record_name']}' - verifying existence"
        )
        provider_records = client.get_zone_records(zone["provider_zone_id"])
        if provider_records is None:
            return
        if not any(pr["id"] == record["provider_record_id"] for pr in provider_records):
            self.logger.warning(
                f"Record '{record['record_name']}' orphaned at provider - "
                "clearing provider_record_id for re-sync"
            )
            self.database.update_record(
                record["id"],
                provider_record_id=None,
                sync_status=SyncStatus.ORPHANED,
            )
