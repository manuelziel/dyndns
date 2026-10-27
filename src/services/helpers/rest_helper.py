#!/usr/bin/env python3
"""Helper class for provider REST API zone and record synchronization.

Encapsulates all direct REST calls to IONOS DNS API endpoints for fetching
zones, matching record IDs, recreating missing records, and updating individual
IP records via PUT requests.

Author: Manuel Ziel
License: MIT
"""

################################################################################
# IMPORTS
################################################################################

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from src.api.provider import ProviderDNSClient
from src.core.constants import (
    DatabaseDefaults,
    PlaceholderIP,
    RecordType,
    SyncStatus,
)
from src.core.exceptions import ValidationError, DynDNSException
from src.utils.colors import LOG_SYMBOLS

################################################################################
# REST RECORD HANDLER CLASS
################################################################################


class RESTRecordHandler:
    """Handler encapsulating direct REST API interactions for zones and records.

    Attributes:
        config: Configuration object.
        database: Database manager instance.
        network: NetworkData instance for IPs.
        logger: Logger instance.
    """

    def __init__(
        self, config: Any, database: Any, network: Any, logger: Any
    ) -> None:
        """Initialize REST record handler.

        Args:
            config: Configuration object.
            database: Database manager instance.
            network: NetworkData instance.
            logger: Logger instance.
        """
        self.config = config
        self.database = database
        self.network = network
        self.logger = logger


    def sync_zone_records(
        self,
        client: ProviderDNSClient,
        zone: Dict[str, Any],
        is_startup: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """Fetch zones and records from REST API and match with local database.

        Args:
            client: Provider client instance.
            zone: Zone dictionary.
            is_startup: True if running during daemon startup check.

        Returns:
            Dictionary with matching results or None on error.
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
            matched_count, missing_records = self._match_records_with_provider(db_records, provider_records)
            return {
                "provider_zone_id": provider_zone_id,
                "provider_records": provider_records,
                "missing_records": missing_records,
                "matched_count": matched_count,
            }
        except DynDNSException as e:
            self.logger.error(f"Failed to sync REST records for '{zone['zone_name']}': {e}")
            return None


    def _resolve_provider_zone_id(
        self, client: ProviderDNSClient, zone: Dict[str, Any]
    ) -> Optional[str]:
        """Resolve provider_zone_id for a zone via REST API.

        Args:
            client: Provider client instance.
            zone: Zone dictionary.

        Returns:
            Provider zone ID string or None if not found.
        """
        self.logger.debug(f"{LOG_SYMBOLS['ARROW']} Fetching zones from provider...")
        provider_zones = client.get_zones()
        if not provider_zones:
            self.logger.error(
                f"Failed to fetch zones from provider for '{zone['zone_name']}'"
            )
            return None

        provider_zone = next(
            (pz for pz in provider_zones if pz["name"] == zone["zone_name"]),
            None,
        )

        if not provider_zone:
            self.logger.error(
                f"Zone '{zone['zone_name']}' not found in provider. "
                f"Available: {[pz['name'] for pz in provider_zones]}"
            )
            return None

        provider_zone_id = provider_zone["id"]
        self.database.update_zone(zone["id"], provider_zone_id=provider_zone_id)
        return provider_zone_id


    def _match_records_with_provider(
        self,
        db_records: List[Dict[str, Any]],
        provider_records: List[Dict[str, Any]],
    ) -> Tuple[int, List[Dict[str, Any]]]:
        """Match local database records with provider API records.

        Args:
            db_records: List of local database records.
            provider_records: List of provider API records.

        Returns:
            Tuple of (matched_count, list of missing database records).
        """
        matched_count = 0
        missing_records = []
        for db_record in db_records:
            db_name = db_record["record_name"].rstrip(".")
            provider_record = next(
                (
                    pr for pr in provider_records
                    if pr["name"].rstrip(".") == db_name and pr["type"] == db_record["record_type"]
                ),
                None,
            )
            if provider_record:
                self.database.update_record_provider_id(db_record["id"], provider_record["id"])
                matched_count += 1
                self.logger.debug(
                    f"  Matched '{db_record['record_name']}' ({db_record['record_type']}) "
                    f"{LOG_SYMBOLS['ARROW']} ID: {provider_record['id']}"
                )
            else:
                missing_records.append(db_record)
                self.logger.warning(f"  Record '{db_record['record_name']}' ({db_record['record_type']}) not found in provider")
        return matched_count, missing_records


    def create_missing_records(
        self,
        client: ProviderDNSClient,
        zone: Dict[str, Any],
        missing_records: List[Dict[str, Any]],
    ) -> int:
        """Create missing DNS records in provider via REST POST API.

        Args:
            client: Provider client instance.
            zone: Zone dictionary containing provider_zone_id.
            missing_records: List of local records to create.

        Returns:
            Number of records successfully created.
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

            success = client.create_records(
                zone_id=zone["provider_zone_id"], records=api_records
            )
            if success:
                self.logger.info(f"Successfully created {len(api_records)} record(s)")
                return len(api_records)
            else:
                self.logger.error("Failed to create records in provider")
                return 0

        except DynDNSException as e:
            self.logger.error(f"Failed to create missing records: {e}")
            return 0


    def _build_api_records_payload(
        self, missing_records: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Build API payload list for missing record creation.

        Args:
            missing_records: List of database records.

        Returns:
            List of API-ready record dictionaries.
        """
        api_records = []
        for db_record_row in missing_records:
            db_record = dict(db_record_row)
            try:
                if db_record["record_type"] == RecordType.A:
                    content = self.network.ipv4_address or PlaceholderIP.get(RecordType.A)
                elif db_record["record_type"] == RecordType.AAAA:
                    content = self.network.ipv6_address or PlaceholderIP.get(RecordType.AAAA)
                else:
                    self.logger.warning(f"Unsupported record type '{db_record['record_type']}'")
                    continue
            except (ValidationError, ValueError) as e:
                self.logger.error(f"Invalid record type for '{db_record['record_name']}': {e}")
                continue

            api_records.append({
                "name": db_record["record_name"],
                "type": db_record["record_type"],
                "content": content,
                "ttl": db_record.get("ttl", self.config.dns_default_ttl),
                "disabled": not db_record.get("enabled", True),
            })
        return api_records


    def rematch_created_records(
        self,
        client: ProviderDNSClient,
        provider_zone_id: str,
        missing_records: List[Dict[str, Any]],
    ) -> int:
        """Re-fetch records after creation and update local SQLite provider IDs.

        Args:
            client: Provider client instance.
            provider_zone_id: Provider zone identifier string.
            missing_records: List of records that were created.

        Returns:
            Number of newly created records successfully matched.
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
        zone: Dict[str, Any],
        record: Dict[str, Any],
        new_ip: str,
    ) -> bool:
        """Update single DNS record IP in provider via REST API.

        Args:
            client: Provider client instance.
            zone: Zone dictionary.
            record: Record dictionary.
            new_ip: Target IP address.

        Returns:
            True if successful, False otherwise.
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
                        last_synced_at=datetime.now().strftime(DatabaseDefaults.DB_TIMESTAMP_FORMAT),
                    )
                return True
            if self.config.daemon_sync_checks:
                self._check_and_clear_orphaned_record(client, zone, record)
            return False
        except DynDNSException as e:
            self.logger.error(f"Provider API update failed for '{record['record_name']}': {e}")
            return False


    def _check_and_clear_orphaned_record(
        self,
        client: ProviderDNSClient,
        zone: Dict[str, Any],
        record: Dict[str, Any],
    ) -> None:
        """Check if record was deleted at provider and clear ID if orphaned.

        Args:
            client: Provider client instance.
            zone: Zone dictionary.
            record: Record dictionary.
        """
        self.logger.warning(
            f"Update failed for '{record['record_name']}' - verifying existence"
        )
        provider_records = client.get_zone_records(zone["provider_zone_id"])
        if provider_records is not None:
            record_exists = any(
                pr["id"] == record["provider_record_id"] for pr in provider_records
            )
            if not record_exists:
                self.logger.warning(
                    f"Record '{record['record_name']}' orphaned at provider - "
                    f"clearing provider_record_id for re-sync"
                )
                self.database.update_record(
                    record["id"],
                    provider_record_id=None,
                    sync_status=SyncStatus.ORPHANED,
                )
