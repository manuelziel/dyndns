#!/usr/bin/env python3
"""Sync Service for matching local database state with the provider API.

This service coordinates discovery of orphaned records, ensures provider IDs
are matched with local database records, and creates missing records via
modular REST API and DynDNS handlers (`RESTRecordHandler`, `DynDNSBundleHandler`).

Author: Manuel Ziel
License: MIT
"""

################################################################################
# IMPORTS & DEPENDENCIES
################################################################################

from typing import Any, Dict, List, Optional, Set

from src.api.provider import ProviderDNSClient
from src.core.constants import SyncStatus, UpdateMethod
from src.core.exceptions import DynDNSException
from src.services.helpers.rest_helper import RESTRecordHandler
from src.services.helpers.dyndns_helper import DynDNSBundleHandler

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
        rest_helper: Handler for direct REST record interactions.
        dyndns_helper: Handler for native DynDNS bundle lifecycle.
    """

    def __init__(
        self,
        config: Any,
        database: Any,
        network: Any,
        logger: Any,
        rest_helper: Optional[RESTRecordHandler] = None,
        dyndns_helper: Optional[DynDNSBundleHandler] = None,
    ) -> None:
        """Initialize sync service with modular handlers.

        Args:
            config: Configuration object.
            database: Database manager instance.
            network: NetworkData instance.
            logger: Logger instance.
            rest_helper: Optional injected RESTRecordHandler instance.
            dyndns_helper: Optional injected DynDNSBundleHandler instance.
        """
        self.config = config
        self.database = database
        self.network = network
        self.logger = logger
        self._provider_clients: Dict[int, ProviderDNSClient] = {}
        self.rest_helper = rest_helper or RESTRecordHandler(
            config, database, network, logger
        )
        self.dyndns_helper = dyndns_helper or DynDNSBundleHandler(
            config, database, network, logger
        )


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
        self, enabled_zones: List[Dict[str, Any]], is_startup: bool = False
    ) -> Set[int]:
        """Collect zones requiring sync due to missing IDs or startup verification.

        Args:
            enabled_zones: List of currently enabled zone dictionaries.
            is_startup: True if running on initial daemon check cycle.

        Returns:
            Set of zone IDs needing provider reconciliation.
        """
        zones_to_sync = set()
        for zone in enabled_zones:
            if not zone.get("records"):
                continue
            if self.config.dns_update_method == UpdateMethod.DYNDNS:
                dyndns_row = self.database.get_dyndns_config_by_zone(zone["id"])
                if not dyndns_row or not dict(dyndns_row).get("update_url") or is_startup:
                    zones_to_sync.add(zone["id"])
                continue
            if is_startup:
                zones_to_sync.add(zone["id"])
                continue

            has_missing_id_or_status = any(
                not r.get("provider_record_id") or r.get("sync_status") != SyncStatus.SYNCED
                for r in zone["records"]
            )
            if has_missing_id_or_status or any(r.get("needs_update") for r in zone["records"]) or self.config.daemon_sync_checks:
                zones_to_sync.add(zone["id"])
        return zones_to_sync


    def sync_zones_and_refresh_records(
        self,
        zone_ids: Set[int],
        enabled_zones: List[Dict[str, Any]],
        is_startup: bool = False,
    ) -> None:
        """Sync zones and refresh record data from database.

        Args:
            zone_ids: Set of zone IDs to synchronize.
            enabled_zones: List of active zones in the current cycle.
            is_startup: True if running on initial daemon check cycle.
        """
        for zone_id in zone_ids:
            provider_sync_ok = self.sync_provider_ids(zone_id, is_startup=is_startup)
            if not provider_sync_ok and self.config.dns_update_method != UpdateMethod.DYNDNS:
                msg = f"Reconciliation failed for zone {zone_id}" if (is_startup or self.config.daemon_sync_checks) else f"Failed to sync zone {zone_id}"
                self.logger.error(msg)
                continue

            if self.config.dns_update_method == UpdateMethod.DYNDNS:
                self._sync_dyndns_zone_bundle(zone_id, enabled_zones, is_startup)
            self._refresh_zone_records_in_memory(zone_id, enabled_zones, is_startup)


    def _sync_dyndns_zone_bundle(
        self, zone_id: int, enabled_zones: List[Dict[str, Any]], is_startup: bool
    ) -> None:
        """Synchronize and optionally verify the native DynDNS bundle for a zone.

        Args:
            zone_id: Database zone ID.
            enabled_zones: List of active zones in the current cycle.
            is_startup: True if running on initial daemon check cycle.
        """
        client = self.get_provider_client(zone_id)
        zone_data = next((z for z in enabled_zones if z["id"] == zone_id), None)
        if not zone_data:
            zone_row = self.database.get_zone_by_id(zone_id)
            if zone_row:
                zone_data = dict(zone_row)
                zone_data["records"] = [dict(r) for r in self.database.get_records_by_zone(zone_id, enabled_only=True)]
        if client and zone_data:
            update_url = self.dyndns_helper.sync_or_activate_dyndns_bundle(client, zone_data)
            if is_startup and update_url:
                self.logger.info(f"Startup Verification: Executing DynDNS update URL for zone '{zone_data['zone_name']}'...")
                if not client.execute_dyndns_update_url(
                    update_url=update_url, ipv4=self.network.ipv4_address, ipv6=self.network.ipv6_address
                ):
                    self.dyndns_helper.reset_cached_url(zone_id, zone_data["zone_name"])
                    update_url = self.dyndns_helper.sync_or_activate_dyndns_bundle(client, zone_data, force_sync=True)
                    if update_url:
                        client.execute_dyndns_update_url(
                            update_url=update_url, ipv4=self.network.ipv4_address, ipv6=self.network.ipv6_address
                        )


    def _refresh_zone_records_in_memory(
        self, zone_id: int, enabled_zones: List[Dict[str, Any]], is_startup: bool
    ) -> None:
        """Refresh in-memory record dictionaries from database after sync.

        Args:
            zone_id: Database zone ID.
            enabled_zones: List of active zones in the current cycle.
            is_startup: True if running on initial daemon check cycle.
        """
        for zone in enabled_zones:
            if zone["id"] == zone_id:
                for record in zone["records"]:
                    record_row = self.database.get_record_by_id(record["id"])
                    if record_row:
                        record.update(dict(record_row))
                        if is_startup or self.config.daemon_sync_checks:
                            self.logger.debug(
                                f"Reconciliation: Refreshed '{record['record_name']}' "
                                f"(provider_record_id: {record.get('provider_record_id', 'still missing')})"
                            )
                break


    def sync_provider_ids(
        self, zone_id: Optional[int] = None, is_startup: bool = False
    ) -> bool:
        """Sync provider zone_id and record_ids from API to database.

        Delegates matching and creation to `self.rest_helper` and URL resets
        to `self.dyndns_helper`.

        Args:
            zone_id: Optional specific zone ID. Syncs all enabled zones if None.
            is_startup: True if running on initial daemon check cycle.

        Returns:
            True if sync completed successfully, False otherwise.
        """
        try:
            zones = self._get_target_zones(zone_id)
            if not zones:
                return False

            self.logger.info(f"Synchronizing provider IDs for {len(zones)} zone(s)...")
            for zone in zones:
                self.logger.debug(f"════════ Syncing zone '{zone['zone_name']}' (ID: {zone['id']}) ════════")
                client = self.get_provider_client(zone["id"])
                if not client:
                    self.logger.error(f"Cannot sync zone '{zone['zone_name']}' - no API client")
                    continue

                sync_data = self.rest_helper.sync_zone_records(client, zone, is_startup=is_startup)
                if sync_data:
                    self._handle_missing_and_created_records(client, zone, sync_data, is_startup)
                    self.logger.debug("════════════════════════════════════════════════════════════")

            self.logger.info("Provider ID synchronization completed")
            return True
        except DynDNSException as e:
            self.logger.error(f"Provider ID synchronization failed: {e}")
            return False


    def _get_target_zones(
        self, zone_id: Optional[int]
    ) -> List[Dict[str, Any]]:
        """Retrieve target zones for provider synchronization.

        Args:
            zone_id: Optional specific zone ID.

        Returns:
            List of zone dictionaries.
        """
        if zone_id:
            zone = self.database.get_zone_by_id(zone_id)
            if not zone:
                self.logger.error(
                    f"Zone with ID {zone_id} not found in database"
                )
                return []
            return [dict(zone)]

        zones = [dict(z) for z in self.database.get_all_enabled_zones()]
        if not zones:
            self.logger.warning("No zones to synchronize")
        return zones


    def _handle_missing_and_created_records(
        self,
        client: ProviderDNSClient,
        zone: Dict[str, Any],
        sync_data: Dict[str, Any],
        is_startup: bool,
    ) -> None:
        """Process missing records, create on provider, and verify results.

        Args:
            client: Provider client instance.
            zone: Zone dictionary.
            sync_data: Result dictionary from rest_helper.sync_zone_records.
            is_startup: True if running on initial daemon check cycle.
        """
        missing_records = sync_data["missing_records"]
        matched_count = sync_data["matched_count"]
        provider_zone_id = sync_data["provider_zone_id"]
        created_count = 0

        if missing_records:
            if is_startup:
                self.logger.warning(
                    f"Startup Verification: Found {len(missing_records)} "
                    "configured record(s) missing on provider IONOS - recreating now..."
                )
            else:
                self.logger.info(f"Attempting to create {len(missing_records)} missing record(s)...")

            zone_dict = dict(zone, provider_zone_id=provider_zone_id)
            created_count = self.rest_helper.create_missing_records(client, zone_dict, missing_records)
            if created_count > 0:
                matched_count += self.rest_helper.rematch_created_records(client, provider_zone_id, missing_records)
                if self.config.dns_update_method == UpdateMethod.DYNDNS:
                    self.dyndns_helper.reset_cached_url(zone["id"], zone["zone_name"])

        self._log_sync_outcome(zone, is_startup, missing_records, created_count, matched_count)


    def _log_sync_outcome(
        self,
        zone: Dict[str, Any],
        is_startup: bool,
        missing_records: List[Dict[str, Any]],
        created_count: int,
        matched_count: int,
    ) -> None:
        """Log final outcome of zone synchronization check.

        Args:
            zone: Zone dictionary.
            is_startup: True if running on initial daemon check cycle.
            missing_records: List of missing records found.
            created_count: Number of missing records recreated.
            matched_count: Total records matched with provider IDs.
        """
        if is_startup:
            if missing_records and created_count > 0:
                self.logger.success(
                    f"Startup Verification: Successfully recreated {created_count} "
                    f"missing record(s) and synced zone '{zone['zone_name']}'"
                )
            elif not missing_records:
                self.logger.info(
                    f"Startup Verification: All {matched_count} managed record(s) "
                    f"verified and present on provider IONOS for zone '{zone['zone_name']}'"
                )
            else:
                self.logger.warning(
                    f"Startup Verification: Synced zone '{zone['zone_name']}', but "
                    f"{len(missing_records) - created_count} missing record(s) "
                    f"could not be created"
                )
        else:
            self.logger.info(
                f"Successfully synced provider IDs for zone '{zone['zone_name']}'"
            )


    def create_missing_records(
        self,
        client: ProviderDNSClient,
        zone: Dict[str, Any],
        missing_records: List[Dict[str, Any]],
    ) -> int:
        """Backward-compatibility proxy for creating missing DNS records.

        Delegates directly to `self.rest_helper.create_missing_records()`.

        Args:
            client: Provider client instance.
            zone: Zone dictionary with provider_zone_id.
            missing_records: List of database records to create.

        Returns:
            Number of records successfully created.
        """
        return self.rest_helper.create_missing_records(
            client, zone, missing_records
        )
