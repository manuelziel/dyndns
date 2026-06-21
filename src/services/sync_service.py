#!/usr/bin/env python3
"""Sync Service for matching local database state with the provider API.

This service is responsible for discovering orphaned records, ensuring
provider IDs are matched with the local database, and creating missing
records dynamically using the provider API.

Author: Manuel Ziel
License: MIT
"""

################################################################################
# IMPORTS & DEPENDENCIES
################################################################################

# Standard Imports
import logging
from typing import Any, Dict, List, Optional, Set

# Local Imports
from src.api.provider import ProviderDNSClient
from src.core.constants import RecordType, PlaceholderIP
from src.core.exceptions import ValidationError, DynDNSException
from src.utils.colors import LOG_SYMBOLS


################################################################################
# SYNC SERVICE CLASS
################################################################################

class SyncService:
    """Service handling synchronization between local database and provider API.

    Attributes:
        config: Configuration object.
        database: Database manager instance.
        network: NetworkData instance for IPs.
        logger: Logger instance.
    """

    def __init__(
        self, config: Any, database: Any, network: Any, logger: Any
    ) -> None:
        """Initialize sync service.

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
        self._provider_clients: Dict[int, ProviderDNSClient] = {}


    def get_provider_client(self, zone_id: int) -> Optional[ProviderDNSClient]:
        """Get or create cached provider API client for zone.

        Args:
            zone_id: Database zone ID.

        Returns:
            ProviderDNSClient instance or None if creation fails.
        """
        if zone_id in self._provider_clients:
            return self._provider_clients[zone_id]

        try:
            dyndns_config = self.database.get_dyndns_config_by_zone(zone_id)

            if not dyndns_config:
                self.logger.warning(f"No DynDNS config found for zone {zone_id}")
                return None

            api_key = f"{dyndns_config['bulk_id']}.{dyndns_config['api_key']}"

            client = ProviderDNSClient(
                api_key=api_key, config=self.config, logger=self.logger
            )
            self._provider_clients[zone_id] = client

            self.logger.debug(f"Created provider API client for zone {zone_id}")
            return client

        except DynDNSException as e:
            self.logger.error(
                f"Failed to create provider client for zone {zone_id}: {e}"
            )
            return None


    def collect_zones_needing_sync(
        self, enabled_zones: List[Dict[str, Any]]
    ) -> Set[int]:
        """Collect zones that need sync due to missing provider_record_ids.

        Args:
            enabled_zones: List of currently enabled zone dictionaries.

        Returns:
            Set of zone IDs that need syncing with provider.
        """
        zones_to_sync = set()

        for zone in enabled_zones:
            if not zone.get("records"):
                continue

            for record in zone["records"]:
                if record.get("needs_update") and not record.get("provider_record_id"):
                    zones_to_sync.add(zone["id"])

                    if self.config.daemon_sync_checks:
                        self.logger.info(
                            f"Reconciliation: Record '{record['record_name']}' missing "
                            f"provider_record_id - zone {zone['zone_name']} will be synced"
                        )
                    break

        return zones_to_sync


    def sync_zones_and_refresh_records(
        self, zone_ids: Set[int], enabled_zones: List[Dict[str, Any]]
    ) -> None:
        """Sync zones and refresh record data from database.

        Args:
            zone_ids: Set of zone IDs to synchronize.
            enabled_zones: List of active zones in the current cycle.
        """
        for zone_id in zone_ids:
            if not self.sync_provider_ids(zone_id):
                if self.config.daemon_sync_checks:
                    self.logger.error(f"Reconciliation failed for zone {zone_id}")
                else:
                    self.logger.error(f"Failed to sync zone {zone_id}")
                continue

            for zone in enabled_zones:
                if zone["id"] == zone_id:
                    for record in zone["records"]:
                        record_row = self.database.get_record_by_id(record["id"])
                        if record_row:
                            record.update(dict(record_row))

                            if self.config.daemon_sync_checks:
                                self.logger.debug(
                                    f"Reconciliation: Refreshed record '{record['record_name']}' "
                                    f"(provider_record_id: {record.get('provider_record_id', 'still missing')})"
                                )
                    break


    def sync_provider_ids(self, zone_id: Optional[int] = None) -> bool:
        """Sync provider zone_id and record_ids from API to database.

        Args:
            zone_id: Optional specific zone ID. Syncs all enabled zones if None.

        Returns:
            True if sync completed successfully, False otherwise.
        """
        try:
            if zone_id:
                zone = self.database.get_zone_by_id(zone_id)
                if not zone:
                    self.logger.error(
                        f"Zone with ID {zone_id} not found in database"
                    )
                    return False
                zones = [zone]
            else:
                zones = self.database.get_all_enabled_zones()

            if not zones:
                self.logger.warning("No zones to synchronize")
                return False

            self.logger.info(
                f"Synchronizing provider IDs for {len(zones)} zone(s)..."
            )

            for zone in zones:
                self.logger.debug(
                    f"════════ Syncing zone '{zone['zone_name']}' "
                    f"(ID: {zone['id']}) ════════"
                )
                try:
                    self.logger.debug(
                        f"{LOG_SYMBOLS['ARROW']} Getting provider API client "
                        f"for zone {zone['id']}"
                    )
                    client = self.get_provider_client(zone["id"])
                    if not client:
                        self.logger.error(
                            f"Cannot sync zone {zone['zone_name']} - no API client"
                        )
                        continue
                    self.logger.debug("API client created successfully")

                    self.logger.debug(
                        f"{LOG_SYMBOLS['ARROW']} Fetching zones from provider..."
                    )
                    provider_zones = client.get_zones()
                    if not provider_zones:
                        self.logger.error(
                            f"Failed to fetch zones from provider for {zone['zone_name']}"
                        )
                        continue
                    self.logger.debug(
                        f"Retrieved {len(provider_zones)} zones from provider"
                    )

                    self.logger.debug(
                        f"{LOG_SYMBOLS['ARROW']} Finding zone "
                        f"'{zone['zone_name']}' in provider zones..."
                    )
                    provider_zone = next(
                        (
                            pz
                            for pz in provider_zones
                            if pz["name"] == zone["zone_name"]
                        ),
                        None,
                    )

                    if not provider_zone:
                        self.logger.error(
                            f"Zone '{zone['zone_name']}' not found in provider"
                        )
                        self.logger.error(
                            f"Available zones: {[pz['name'] for pz in provider_zones]}"
                        )
                        continue

                    provider_zone_id = provider_zone["id"]
                    self.logger.debug(
                        f"Found zone with provider ID: {provider_zone_id}"
                    )

                    self.logger.debug(
                        f"{LOG_SYMBOLS['ARROW']} Updating database with provider_zone_id..."
                    )
                    self.database.update_zone(
                        zone["id"], provider_zone_id=provider_zone_id
                    )
                    self.logger.debug("Database updated with provider zone ID")

                    self.logger.debug(
                        f"{LOG_SYMBOLS['ARROW']} Fetching records for zone ID: "
                        f"{provider_zone_id}"
                    )
                    provider_records = client.get_zone_records(provider_zone_id)
                    if provider_records is None:
                        self.logger.error(
                            f"Failed to fetch records for zone '{zone['zone_name']}'"
                        )
                        continue

                    self.logger.debug(
                        f"Retrieved {len(provider_records)} records from provider"
                    )

                    self.logger.debug(
                        f"{LOG_SYMBOLS['ARROW']} Loading database records for zone..."
                    )
                    db_records = self.database.get_records_by_zone(
                        zone["id"], enabled_only=False
                    )
                    self.logger.debug(
                        f"Retrieved {len(db_records)} records from database"
                    )

                    self.logger.debug(
                        f"{LOG_SYMBOLS['ARROW']} Matching {len(db_records)} DB "
                        f"records with {len(provider_records)} provider records..."
                    )

                    matched_count = 0
                    unmatched_count = 0
                    missing_records = []

                    for db_record in db_records:
                        db_name = db_record["record_name"].rstrip(".")

                        self.logger.debug(
                            f"  Matching DB record: '{db_name}' "
                            f"({db_record['record_type']})"
                        )

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
                            rows_updated = self.database.update_record_provider_id(
                                db_record["id"], provider_record["id"]
                            )
                            matched_count += 1
                            self.logger.debug(
                                f"  Matched '{db_record['record_name']}' "
                                f"({db_record['record_type']}) "
                                f"{LOG_SYMBOLS['ARROW']} provider ID: "
                                f"{provider_record['id']} (updated: {rows_updated} rows)"
                            )
                        else:
                            unmatched_count += 1
                            missing_records.append(db_record)
                            self.logger.warning(
                                f"  Record '{db_record['record_name']}' "
                                f"({db_record['record_type']}) not found in provider"
                            )

                    self.logger.debug(
                        f"Matching complete: {matched_count} matched, "
                        f"{unmatched_count} not found"
                    )

                    if missing_records:
                        self.logger.info(
                            f"Attempting to create {len(missing_records)} "
                            f"missing record(s)..."
                        )

                        zone_dict = dict(zone)
                        zone_dict["provider_zone_id"] = provider_zone_id

                        created_count = self.create_missing_records(
                            client, zone_dict, missing_records
                        )

                        if created_count > 0:
                            self.logger.debug(
                                "Re-fetching provider records to get new IDs..."
                            )
                            provider_records = client.get_zone_records(
                                provider_zone_id
                            )

                            if provider_records:
                                self.logger.debug(
                                    f"Re-matching {len(missing_records)} newly "
                                    f"created records..."
                                )

                                for db_record_row in missing_records:
                                    db_record = dict(db_record_row)
                                    db_name = db_record["record_name"].rstrip(".")

                                    provider_record = next(
                                        (
                                            pr
                                            for pr in provider_records
                                            if pr["name"].rstrip(".") == db_name
                                            and pr["type"]
                                            == db_record["record_type"]
                                        ),
                                        None,
                                    )

                                    if provider_record:
                                        rows_updated = self.database.update_record_provider_id(
                                            db_record["id"], provider_record["id"]
                                        )
                                        matched_count += 1
                                        self.logger.debug(
                                            f"  Matched newly created "
                                            f"'{db_record['record_name']}' "
                                            f"({db_record['record_type']}) "
                                            f"{LOG_SYMBOLS['ARROW']} provider ID: "
                                            f"{provider_record['id']}"
                                        )
                                    else:
                                        self.logger.warning(
                                            f"  Newly created record "
                                            f"'{db_record['record_name']}' "
                                            f"still not found in provider"
                                        )

                    self.logger.info(
                        f"Successfully synced provider IDs for zone '{zone['zone_name']}'"
                    )
                    self.logger.debug(
                        f"════════════════════════════════════════════════════════════"
                    )

                except DynDNSException as e:
                    self.logger.error(
                        f"Failed to sync zone '{zone.get('zone_name', 'unknown')}': {e}"
                    )
                    continue

            self.logger.info("Provider ID synchronization completed")
            return True

        except DynDNSException as e:
            self.logger.error(f"Provider ID synchronization failed: {e}")
            return False


    def create_missing_records(
        self,
        client: ProviderDNSClient,
        zone: Dict[str, Any],
        missing_records: List[Dict[str, Any]],
    ) -> int:
        """Create missing DNS records in provider.

        Args:
            client: ProviderDNSClient instance for API calls.
            zone: Zone dictionary with provider_zone_id.
            missing_records: List of database records to create.

        Returns:
            Number of records successfully created.
        """
        if not missing_records:
            return 0

        try:
            self.logger.info(
                f"Creating {len(missing_records)} missing record(s) in provider..."
            )

            api_records = []
            for db_record_row in missing_records:
                db_record = dict(db_record_row)

                try:
                    if db_record["record_type"] == RecordType.A:
                        content = (
                            self.network.ipv4_address
                            or PlaceholderIP.get(RecordType.A)
                        )
                    elif db_record["record_type"] == RecordType.AAAA:
                        content = (
                            self.network.ipv6_address
                            or PlaceholderIP.get(RecordType.AAAA)
                        )
                    else:
                        self.logger.warning(
                            f"Unsupported record type '{db_record['record_type']}' "
                            f"- skipping"
                        )
                        continue
                except ValidationError as e:
                    self.logger.error(
                        f"Invalid record type for '{db_record['record_name']}': {e}"
                    )
                    continue

                api_record = {
                    "name": db_record["record_name"],
                    "type": db_record["record_type"],
                    "content": content,
                    "ttl": db_record.get("ttl", self.config.dns_default_ttl),
                    "disabled": not db_record.get("enabled", True),
                }
                api_records.append(api_record)

                self.logger.debug(
                    f"  Prepared record: '{api_record['name']}' "
                    f"({api_record['type']}) "
                    f"{LOG_SYMBOLS['ARROW']} {content}"
                )

            if not api_records:
                self.logger.warning("No valid records to create")
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
