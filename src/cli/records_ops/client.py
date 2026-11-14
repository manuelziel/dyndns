#!/usr/bin/env python3
"""Shared provider client, IP lookup, and zone-sync helpers for RecordManager.

Provides credential-backed ProviderDNSClient instantiation, zone ID discovery,
record-ID reconciliation, and native DynDNS bundle synchronization.

Author: Manuel Ziel
License: MIT
"""

################################################################################
# IMPORTS & DEPENDENCIES
################################################################################

from datetime import datetime
from typing import Any

from src.api import ProviderDNSClient
from src.core.constants import (
    DatabaseDefaults,
    RecordType,
    SyncStatus,
    UpdateMethod,
    UpdateStatus,
)
from src.core.exceptions import (
    APIError,
    DatabaseError,
    DynDNSException,
    ZoneNotFoundError,
)
from src.network import NetworkData
from src.services.helpers.dyndns_helper import DynDNSBundleHandler

from ..helpers.input import get_placeholder_ip
from ..helpers.output import (
    print_error,
    print_info,
    print_success,
    print_warning,
    row_to_dict,
)

################################################################################
# RECORD PROVIDER CLIENT MIXIN
################################################################################


class RecordProviderClientMixin:
    """Mixin providing provider client setup and zone synchronization helpers."""

    config: Any
    logger: Any
    db: Any

    ############################################################################
    # Provider Client Initialization & Zone ID Sync
    ############################################################################

    def _create_provider_client(
        self, zone: dict[str, Any], dyndns: dict[str, Any]
    ) -> ProviderDNSClient | None:
        """Instantiate ``ProviderDNSClient`` from decrypted zone credentials.

        Args:
            zone: Zone dictionary.
            dyndns: Decrypted DynDNS credentials dictionary.

        Returns:
            Initialized ``ProviderDNSClient`` or ``None`` on error.
        """
        try:
            api_key = f"{dyndns['bulk_id']}.{dyndns['api_key']}"
            return ProviderDNSClient(
                api_key=api_key, config=self.config, logger=self.logger
            )
        except DynDNSException as exc:
            print_error(
                f"Failed to initialize API client for zone '{zone['zone_name']}': {exc}"
            )
            self.logger.error(
                f"Provider client creation failed for zone {zone['id']}: {exc}"
            )
            return None

    def _get_provider_with_credentials(
        self,
        zone: dict[str, Any],
        warn_on_missing: bool = True,
        require_zone_id: bool = True,
    ) -> ProviderDNSClient | None:
        """Return a validated ``ProviderDNSClient`` for ``zone``.

        Args:
            zone: Zone dictionary (updated in-place if ``provider_zone_id`` is synced).
            warn_on_missing: Whether to display CLI warnings on missing credentials.
            require_zone_id: Whether ``provider_zone_id`` must be present/synced.

        Returns:
            Configured ``ProviderDNSClient`` or ``None`` if unavailable.
        """
        dyndns_config = self.db.get_dyndns_config_by_zone(zone["id"])
        if not dyndns_config:
            if warn_on_missing:
                print_warning("No API credentials configured for this zone.")
                print_info("Configure API credentials to enable provider sync.")
            return None

        provider = self._create_provider_client(zone, row_to_dict(dyndns_config))
        if not provider:
            if warn_on_missing:
                print_error("Failed to create provider client")
            return None

        if require_zone_id and not zone.get("provider_zone_id"):
            if not self._sync_and_update_zone_credentials(
                zone, provider, warn_on_missing
            ):
                provider.close()
                return None
        return provider

    def _sync_and_update_zone_credentials(
        self,
        zone: dict[str, Any],
        provider: ProviderDNSClient,
        warn_on_missing: bool,
    ) -> bool:
        """Fetch ``provider_zone_id`` from the provider and refresh ``zone`` in-place.

        Args:
            zone: Zone dictionary to update in-place.
            provider: Active provider client.
            warn_on_missing: Whether to emit CLI messages.

        Returns:
            True if ``provider_zone_id`` was resolved and reloaded, False otherwise.
        """
        if warn_on_missing:
            print_info(
                f"Zone '{zone['zone_name']}' has no provider_zone_id - fetching from provider..."
            )
        if self._sync_zone_id(zone, provider):
            zone_row = self.db.get_zone_by_id(zone["id"])
            if zone_row:
                zone.update(row_to_dict(zone_row))
                return True
        if warn_on_missing:
            print_error("Failed to sync/reload provider_zone_id from provider")
        return False

    def _sync_zone_id(
        self, zone: dict[str, Any], provider: ProviderDNSClient
    ) -> bool:
        """Resolve and persist ``provider_zone_id`` by querying provider zones.

        Args:
            zone: Zone dictionary.
            provider: Active provider client.

        Returns:
            True on success, False otherwise.
        """
        try:
            provider_zones = provider.get_zones()
            if not provider_zones:
                raise APIError("Failed to fetch zones from provider")
            provider_zone = next(
                (pz for pz in provider_zones if pz["name"] == zone["zone_name"]),
                None,
            )
            if not provider_zone:
                raise ZoneNotFoundError(
                    f"Zone '{zone['zone_name']}' not found in provider"
                )
            self.db.update_zone(zone["id"], provider_zone_id=provider_zone["id"])
            print_success("Synced zone with provider")
            self.logger.info(
                f"Synced provider_zone_id for zone {zone['zone_name']}: {provider_zone['id']}"
            )
            return True
        except (APIError, ZoneNotFoundError, DatabaseError, KeyError, TypeError) as exc:
            print_error(f"Zone sync failed: {exc}")
            self.logger.error(f"Failed to sync zone {zone['zone_name']}: {exc}")
            return False

    ############################################################################
    # Record Reconciliation & DynDNS Bundle Helpers
    ############################################################################

    def _sync_zone_with_provider(
        self, zone: dict[str, Any], provider: ProviderDNSClient
    ) -> dict[str, int]:
        """Reconcile all local records in ``zone`` with provider record IDs.

        Args:
            zone: Zone dictionary.
            provider: Active provider client.

        Returns:
            Dictionary of sync statistics, or empty dict on error.
        """
        stats = {SyncStatus.SYNCED: 0, UpdateStatus.FAILED: 0}
        try:
            if not zone.get("provider_zone_id"):
                raise APIError(f"Zone '{zone['zone_name']}' has no provider_zone_id")
            provider_records = provider.get_zone_records(zone["provider_zone_id"])
            if not provider_records:
                raise APIError("Failed to fetch records from provider")
            local_records = self.db.get_records_by_zone(zone["id"], enabled_only=False)
            self._reconcile_local_records_to_provider(
                local_records, provider_records, zone["zone_name"], stats
            )
            return stats
        except (
            ZoneNotFoundError,
            APIError,
            DatabaseError,
            ValueError,
            KeyError,
            TypeError,
        ) as exc:
            self.logger.error(f"Failed to sync zone records with provider: {exc}")
            return {}

    def _reconcile_local_records_to_provider(
        self,
        local_records: list[Any],
        provider_records: list[dict[str, Any]],
        zone_name: str,
        stats: dict[str, int],
    ) -> None:
        """Match local record rows against provider records and update IDs.

        Args:
            local_records: Local record dictionaries/rows.
            provider_records: Provider record dictionaries.
            zone_name: Domain name for logging.
            stats: Mutable sync counter dictionary.
        """
        now_ts = datetime.now().strftime(DatabaseDefaults.DB_TIMESTAMP_FORMAT)
        for local_row in local_records:
            local = row_to_dict(local_row)
            match = next(
                (
                    p_rec
                    for p_rec in provider_records
                    if p_rec["name"] == local["record_name"]
                    and p_rec["type"] == local["record_type"]
                ),
                None,
            )
            if match:
                self.db.update_record(
                    local["id"],
                    provider_record_id=match["id"],
                    sync_status=SyncStatus.SYNCED,
                    last_synced_at=now_ts,
                )
                stats[SyncStatus.SYNCED] += 1
            else:
                self._mark_local_record_as_orphaned(local)
                stats[UpdateStatus.FAILED] += 1
        self.logger.info(
            f"Synced {stats[SyncStatus.SYNCED]} records for zone '{zone_name}'"
        )

    def _mark_local_record_as_orphaned(self, record: dict[str, Any]) -> None:
        """Mark ``record`` as orphaned when its ``provider_record_id`` disappeared.

        Args:
            record: Local record dictionary.
        """
        if record.get("provider_record_id"):
            self.logger.info(
                f"Record '{record['record_name']}' ({record['record_type']}) "
                "not found at provider - marking orphaned"
            )
            self.db.update_record(
                record["id"],
                provider_record_id=None,
                sync_status=SyncStatus.ORPHANED,
            )

    def _sync_dyndns_bundle_if_needed(self, zone_id: int) -> None:
        """Synchronize native IONOS DynDNS bundle domains after local record edits.

        Args:
            zone_id: Database zone ID.
        """
        if self.config.dns_update_method != UpdateMethod.DYNDNS:
            return
        zone = self.db.get_zone_by_id(zone_id)
        dyndns_config = self.db.get_dyndns_config_by_zone(zone_id)
        if not zone or not dyndns_config:
            return

        zone_dict = row_to_dict(zone)
        provider = self._create_provider_client(zone_dict, row_to_dict(dyndns_config))
        if not provider:
            return
        try:
            self._run_dyndns_bundle_sync(provider, zone_dict)
        except DynDNSException as exc:
            print_warning(f"Failed to synchronize DynDNS bundle: {exc}")
        finally:
            provider.close()

    def _run_dyndns_bundle_sync(
        self, provider: ProviderDNSClient, zone_dict: dict[str, Any]
    ) -> None:
        """Execute bundle synchronization and trigger ``updateUrl`` verification.

        Args:
            provider: Active provider client.
            zone_dict: Zone dictionary.
        """
        network = NetworkData(config=self.config, logger=self.logger)
        network.load_current_ip_addresses()
        handler = DynDNSBundleHandler(self.config, self.db, network, self.logger)
        print_info(
            f"Synchronizing DynDNS bundle on provider for '{zone_dict['zone_name']}'..."
        )
        update_url = handler.sync_or_activate_dyndns_bundle(
            provider, zone_dict, force_sync=True
        )
        if update_url and provider.execute_dyndns_update_url(
            update_url, ipv4=network.ipv4_address, ipv6=network.ipv6_address
        ):
            print_success(
                "Synchronized DynDNS bundle and verified updateUrl on provider."
            )

    ############################################################################
    # Shared IP Lookup Helpers
    ############################################################################

    def _get_current_ip(self, record: dict[str, Any]) -> str | None:
        """Return the stored IP address for ``record`` from the local database.

        Args:
            record: Record dictionary.

        Returns:
            Stored IP address string or ``None``.
        """
        ip_info_row = self.db.get_ip_address(record["id"])
        if ip_info_row:
            return row_to_dict(ip_info_row).get("ip_address")
        return None

    def _get_current_or_detect_ip(self, record: dict[str, Any]) -> str:
        """Return stored IP for ``record`` or detect public IP with placeholder fallback.

        Args:
            record: Record dictionary.

        Returns:
            Public IP address string or protocol placeholder IP.
        """
        current_ip = self._get_current_ip(record)
        if current_ip:
            return current_ip

        rec_type = record["record_type"]
        print_info(f"Detecting current {rec_type} address...")
        net = NetworkData(
            config=self.config,
            logger=self.logger,
            ipv4_enabled=(rec_type == RecordType.A),
            ipv6_enabled=(rec_type == RecordType.AAAA),
        )
        detected = (
            net.get_current_public_ipv4_address()
            if rec_type == RecordType.A
            else net.get_current_public_ipv6_address()
        )
        if not detected:
            placeholder = get_placeholder_ip(rec_type)
            print_warning(
                f"Could not detect {rec_type} address. Using placeholder {placeholder}"
            )
            return placeholder
        print_success(f"Detected {rec_type}: {detected}")
        return detected
