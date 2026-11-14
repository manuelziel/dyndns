#!/usr/bin/env python3
"""Sync service for reconciling local SQLite state with the provider API.

Coordinates discovery of orphaned records, matches provider IDs with local
records, recreates missing records, and manages cached ``ProviderDNSClient``
sessions via modular ``RESTRecordHandler`` and ``DynDNSBundleHandler`` helpers.

Author: Manuel Ziel
License: MIT
"""

################################################################################
# IMPORTS & DEPENDENCIES
################################################################################

from typing import Any

from ..api.provider import ProviderDNSClient
from ..core.constants import SyncStatus, UpdateMethod
from ..core.exceptions import DynDNSException
from .helpers.dyndns_helper import DynDNSBundleHandler
from .helpers.rest_helper import RESTRecordHandler

################################################################################
# SYNC SERVICE CLASS
################################################################################


class SyncService:
    """Synchronizes local DNS zones and records with the provider API.

    Attributes:
        config: ``ConfigManager`` instance.
        database: ``Database`` manager instance.
        network: ``NetworkData`` instance.
        logger: Logger instance.
        rest_helper: Strategy handler for REST DNS record operations.
        dyndns_helper: Strategy handler for native DynDNS bundle operations.
    """

    def __init__(
        self,
        config: Any,
        database: Any,
        network: Any,
        logger: Any,
        rest_helper: RESTRecordHandler | None = None,
        dyndns_helper: DynDNSBundleHandler | None = None,
    ) -> None:
        """Initialize sync service and strategy handlers.

        Args:
            config: ``ConfigManager`` instance.
            database: ``Database`` manager instance.
            network: ``NetworkData`` instance.
            logger: Logger instance.
            rest_helper: Optional injected ``RESTRecordHandler``.
            dyndns_helper: Optional injected ``DynDNSBundleHandler``.
        """
        self.config = config
        self.database = database
        self.network = network
        self.logger = logger
        self._provider_clients: dict[int, ProviderDNSClient] = {}
        self.rest_helper = rest_helper or RESTRecordHandler(
            config, database, network, logger
        )
        self.dyndns_helper = dyndns_helper or DynDNSBundleHandler(
            config, database, network, logger
        )

    def close(self) -> None:
        """Close all cached ``ProviderDNSClient`` HTTP sessions and clear cache."""
        for client in self._provider_clients.values():
            client.close()
        self._provider_clients.clear()

    ############################################################################
    # PROVIDER CLIENT CACHE & ZONE SELECTION
    ############################################################################

    def get_provider_client(self, zone_id: int) -> ProviderDNSClient | None:
        """Retrieve or create a cached ``ProviderDNSClient`` for ``zone_id``.

        Args:
            zone_id: Database zone ID.

        Returns:
            Initialized ``ProviderDNSClient`` or ``None`` if unconfigured.
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
        except DynDNSException as exc:
            self.logger.error(f"Failed to create provider client for zone {zone_id}: {exc}")
            return None

    def collect_zones_needing_sync(
        self, enabled_zones: list[dict[str, Any]], is_startup: bool = False
    ) -> set[int]:
        """Determine which active zones require provider reconciliation.

        Args:
            enabled_zones: Active zone dictionaries in the current cycle.
            is_startup: True during the initial daemon startup cycle.

        Returns:
            Set of database zone IDs needing synchronization.
        """
        zones_to_sync: set[int] = set()
        for zone in enabled_zones:
            if not zone.get("records"):
                continue
            if self._zone_requires_sync(zone, is_startup):
                zones_to_sync.add(zone["id"])
        return zones_to_sync

    def _zone_requires_sync(self, zone: dict[str, Any], is_startup: bool) -> bool:
        """Return True when ``zone`` needs a provider sync pass.

        Args:
            zone: Enabled zone dictionary with ``records``.
            is_startup: True during the initial daemon startup cycle.

        Returns:
            Boolean sync decision.
        """
        if self.config.dns_update_method == UpdateMethod.DYNDNS:
            dyndns_row = self.database.get_dyndns_config_by_zone(zone["id"])
            return bool(not dyndns_row or not dict(dyndns_row).get("update_url") or is_startup)
        if is_startup or self.config.daemon_sync_checks:
            return True
        return any(
            not r.get("provider_record_id")
            or r.get("sync_status") != SyncStatus.SYNCED
            or r.get("needs_update")
            for r in zone["records"]
        )

    ############################################################################
    # ZONE & RECORD RECONCILIATION PIPELINE
    ############################################################################

    def sync_zones_and_refresh_records(
        self,
        zone_ids: set[int],
        enabled_zones: list[dict[str, Any]],
        is_startup: bool = False,
    ) -> None:
        """Synchronize ``zone_ids`` against the provider and refresh memory state.

        Args:
            zone_ids: Set of database zone IDs to synchronize.
            enabled_zones: Active zone dictionaries in the current cycle.
            is_startup: True during the initial daemon startup cycle.
        """
        for zone_id in zone_ids:
            provider_sync_ok = self.sync_provider_ids(zone_id, is_startup=is_startup)
            if not provider_sync_ok and self.config.dns_update_method != UpdateMethod.DYNDNS:
                msg = (
                    f"Reconciliation failed for zone {zone_id}"
                    if (is_startup or self.config.daemon_sync_checks)
                    else f"Failed to sync zone {zone_id}"
                )
                self.logger.error(msg)
                continue
            if self.config.dns_update_method == UpdateMethod.DYNDNS:
                self._sync_dyndns_zone_bundle(zone_id, enabled_zones, is_startup)
            self._refresh_zone_records_in_memory(zone_id, enabled_zones, is_startup)

    def _sync_dyndns_zone_bundle(
        self, zone_id: int, enabled_zones: list[dict[str, Any]], is_startup: bool
    ) -> None:
        """Synchronize and optionally startup-verify a zone's DynDNS bundle.

        Args:
            zone_id: Database zone ID.
            enabled_zones: Active zone dictionaries in the current cycle.
            is_startup: True during the initial daemon startup cycle.
        """
        client = self.get_provider_client(zone_id)
        zone_data = self._resolve_zone_with_records(zone_id, enabled_zones)
        if not client or not zone_data:
            return
        update_url = self.dyndns_helper.sync_or_activate_dyndns_bundle(client, zone_data)
        if is_startup and update_url:
            self._verify_startup_dyndns_url(client, zone_data, update_url)

    def _resolve_zone_with_records(
        self, zone_id: int, enabled_zones: list[dict[str, Any]]
    ) -> dict[str, Any] | None:
        """Locate ``zone_id`` in ``enabled_zones`` or load it with records from SQLite.

        Args:
            zone_id: Database zone ID.
            enabled_zones: Active zone dictionaries in memory.

        Returns:
            Zone dictionary containing ``records``, or ``None``.
        """
        existing = next((z for z in enabled_zones if z["id"] == zone_id), None)
        if existing is not None:
            return existing
        zone_row = self.database.get_zone_by_id(zone_id)
        if not zone_row:
            return None
        zone_data = dict(zone_row)
        zone_data["records"] = [
            dict(r) for r in self.database.get_records_by_zone(zone_id, enabled_only=True)
        ]
        return zone_data

    def _verify_startup_dyndns_url(
        self, client: ProviderDNSClient, zone_data: dict[str, Any], update_url: str
    ) -> None:
        """Execute startup verification GET on ``update_url`` and rebind if stale.

        Args:
            client: Active ``ProviderDNSClient``.
            zone_data: Zone dictionary with ``id`` and ``zone_name``.
            update_url: Cached or newly activated DynDNS ``updateUrl``.
        """
        self.logger.info(
            f"Startup Verification: Executing DynDNS update URL for zone '{zone_data['zone_name']}'..."
        )
        if client.execute_dyndns_update_url(
            update_url=update_url,
            ipv4=self.network.ipv4_address,
            ipv6=self.network.ipv6_address,
        ):
            return
        self.dyndns_helper.reset_cached_url(zone_data["id"], zone_data["zone_name"])
        fresh_url = self.dyndns_helper.sync_or_activate_dyndns_bundle(
            client, zone_data, force_sync=True
        )
        if fresh_url:
            client.execute_dyndns_update_url(
                update_url=fresh_url,
                ipv4=self.network.ipv4_address,
                ipv6=self.network.ipv6_address,
            )

    def _refresh_zone_records_in_memory(
        self, zone_id: int, enabled_zones: list[dict[str, Any]], is_startup: bool
    ) -> None:
        """Refresh in-memory record dictionaries from SQLite after provider sync.

        Args:
            zone_id: Database zone ID.
            enabled_zones: Active zone dictionaries in memory.
            is_startup: True during the initial daemon startup cycle.
        """
        zone = next((z for z in enabled_zones if z["id"] == zone_id), None)
        if not zone:
            return
        for record in zone["records"]:
            record_row = self.database.get_record_by_id(record["id"])
            if record_row:
                record.update(dict(record_row))
                if is_startup or self.config.daemon_sync_checks:
                    self.logger.debug(
                        f"Reconciliation: Refreshed '{record['record_name']}' "
                        f"(provider_record_id: {record.get('provider_record_id', 'still missing')})"
                    )

    def sync_provider_ids(
        self, zone_id: int | None = None, is_startup: bool = False
    ) -> bool:
        """Synchronize provider zone and record IDs from the REST API to SQLite.

        Args:
            zone_id: Optional single zone ID (syncs all enabled zones if ``None``).
            is_startup: True during the initial daemon startup cycle.

        Returns:
            True if synchronization ran cleanly, False otherwise.
        """
        try:
            zones = self._get_target_zones(zone_id)
            if not zones:
                return False
            self.logger.info(f"Synchronizing provider IDs for {len(zones)} zone(s)...")
            for zone in zones:
                self._sync_single_zone_ids(zone, is_startup)
            self.logger.info("Provider ID synchronization completed")
            return True
        except DynDNSException as exc:
            self.logger.error(f"Provider ID synchronization failed: {exc}")
            return False

    def _sync_single_zone_ids(self, zone: dict[str, Any], is_startup: bool) -> None:
        """Synchronize provider IDs and missing records for a single zone.

        Args:
            zone: Zone dictionary from SQLite.
            is_startup: True during the initial daemon startup cycle.
        """
        self.logger.debug(
            f"-------- Syncing zone '{zone['zone_name']}' (ID: {zone['id']}) --------"
        )
        client = self.get_provider_client(zone["id"])
        if not client:
            self.logger.error(f"Cannot sync zone '{zone['zone_name']}' - no API client")
            return
        sync_data = self.rest_helper.sync_zone_records(client, zone, is_startup=is_startup)
        if sync_data:
            self._handle_missing_and_created_records(client, zone, sync_data, is_startup)

    def _get_target_zones(self, zone_id: int | None) -> list[dict[str, Any]]:
        """Resolve target zone list for ``sync_provider_ids``.

        Args:
            zone_id: Optional specific database zone ID.

        Returns:
            List of zone dictionaries.
        """
        if zone_id is not None:
            zone = self.database.get_zone_by_id(zone_id)
            if not zone:
                self.logger.error(f"Zone with ID {zone_id} not found in database")
                return []
            return [dict(zone)]
        zones = [dict(z) for z in self.database.get_all_enabled_zones()]
        if not zones:
            self.logger.warning("No zones to synchronize")
        return zones

    def _handle_missing_and_created_records(
        self,
        client: ProviderDNSClient,
        zone: dict[str, Any],
        sync_data: dict[str, Any],
        is_startup: bool,
    ) -> None:
        """Create missing records on the provider and rematch their new IDs.

        Args:
            client: Active ``ProviderDNSClient``.
            zone: Zone dictionary.
            sync_data: Reconciliation summary from ``RESTRecordHandler``.
            is_startup: True during the initial daemon startup cycle.
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
                self.logger.info(
                    f"Attempting to create {len(missing_records)} missing record(s)..."
                )
            zone_dict = dict(zone, provider_zone_id=provider_zone_id)
            created_count = self.rest_helper.create_missing_records(
                client, zone_dict, missing_records
            )
            if created_count > 0:
                matched_count += self.rest_helper.rematch_created_records(
                    client, provider_zone_id, missing_records
                )
                if self.config.dns_update_method == UpdateMethod.DYNDNS:
                    self.dyndns_helper.reset_cached_url(zone["id"], zone["zone_name"])
        self._log_sync_outcome(zone, is_startup, missing_records, created_count, matched_count)

    def _log_sync_outcome(
        self,
        zone: dict[str, Any],
        is_startup: bool,
        missing_records: list[dict[str, Any]],
        created_count: int,
        matched_count: int,
    ) -> None:
        """Log a concise summary of a zone synchronization pass.

        Args:
            zone: Zone dictionary.
            is_startup: True during the initial daemon startup cycle.
            missing_records: List of missing records detected prior to creation.
            created_count: Number of missing records recreated.
            matched_count: Total records matched with provider IDs.
        """
        if not is_startup:
            self.logger.info(f"Successfully synced provider IDs for zone '{zone['zone_name']}'")
            return
        if missing_records and created_count > 0:
            self.logger.success(
                f"Startup Verification: Recreated {created_count} missing record(s) "
                f"and synced zone '{zone['zone_name']}'"
            )
        elif not missing_records:
            self.logger.info(
                f"Startup Verification: All {matched_count} managed record(s) verified "
                f"on provider IONOS for zone '{zone['zone_name']}'"
            )
        else:
            remaining = len(missing_records) - created_count
            self.logger.warning(
                f"Startup Verification: Synced zone '{zone['zone_name']}', "
                f"but {remaining} missing record(s) could not be created"
            )

    def create_missing_records(
        self,
        client: ProviderDNSClient,
        zone: dict[str, Any],
        missing_records: list[dict[str, Any]],
    ) -> int:
        """Delegate missing record creation to ``RESTRecordHandler``.

        Args:
            client: Active ``ProviderDNSClient``.
            zone: Zone dictionary containing ``provider_zone_id``.
            missing_records: Local records missing on the provider.

        Returns:
            Count of successfully created records.
        """
        return self.rest_helper.create_missing_records(client, zone, missing_records)
