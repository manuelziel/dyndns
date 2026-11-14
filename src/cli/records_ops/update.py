#!/usr/bin/env python3
"""Interactive forced DNS update orchestration for RecordManager.

Coordinates optional pre-sync, public IPv4/IPv6 detection, and zone-level
dispatch to native IONOS DynDNS ``updateUrl`` bundles or per-record REST updates.

Author: Manuel Ziel
License: MIT
"""

################################################################################
# IMPORTS & DEPENDENCIES
################################################################################

from typing import Any

from src.api import ProviderDNSClient
from src.core.constants import SyncStatus, UpdateMethod, UpdateStatus
from src.core.exceptions import NetworkError
from src.network import NetworkData
from src.services.helpers.dyndns_helper import DynDNSBundleHandler
from src.utils.colors import Colors

from ..helpers.input import confirm_action, wait_for_enter
from ..helpers.output import (
    print_error,
    print_info,
    print_section,
    print_subsection,
    print_success,
    print_warning,
    row_to_dict,
)

################################################################################
# RECORD FORCE UPDATE MIXIN
################################################################################


class RecordForceUpdateMixin:
    """Mixin providing manual forced DNS record updates across enabled zones."""

    config: Any
    logger: Any
    db: Any

    def force_dns_update(self) -> None:
        """Force immediate DNS update for all enabled zones and records."""
        print_section("Force DNS Update")
        print(f"\n{Colors.YELLOW}WARNING{Colors.NC}")
        print(
            f"{Colors.DIM}This will immediately update ALL enabled DNS records "
            f"with current IP addresses.{Colors.NC}"
        )
        print(
            f"{Colors.DIM}Use this when records are out of sync or manually deleted.{Colors.NC}\n"
        )

        if not confirm_action("Force update all DNS records now?", default=False):
            print_info("Cancelled.")
            wait_for_enter()
            return

        print()
        if confirm_action("Sync records with provider first?", default=True):
            self._pre_sync_all_enabled_zones()

        network = self._detect_ip_addresses()
        if not network:
            wait_for_enter()
            return

        zones = self.db.get_all_enabled_zones()
        if not zones:
            print_warning("No enabled zones found.")
            wait_for_enter()
            return

        print_subsection("Processing DNS Records")
        stats = self._process_all_zones(zones, network)
        self._display_update_summary(stats)  # type: ignore[attr-defined]
        wait_for_enter()

    ############################################################################
    # Pre-Sync & Public IP Detection
    ############################################################################

    def _pre_sync_all_enabled_zones(self) -> None:
        """Synchronize all enabled zones with the provider prior to updating."""
        print_subsection("Pre-Sync: Syncing Zones from Provider")
        zones_to_sync = self.db.get_all_enabled_zones()
        if not zones_to_sync:
            print_warning("No enabled zones to sync.")
            return

        synced_count = 0
        failed_count = 0
        for zone_row in zones_to_sync:
            synced, failed = self._pre_sync_single_zone(row_to_dict(zone_row))
            synced_count += synced
            failed_count += failed

        print()
        print_success(f"Synced: {synced_count} records")
        if failed_count > 0:
            print_warning(f"Failed: {failed_count} zones")
        print()

    def _pre_sync_single_zone(self, zone: dict[str, Any]) -> tuple[int, int]:
        """Run pre-sync for ``zone`` and return ``(synced_records, failed_zones)``.

        Args:
            zone: Zone dictionary.

        Returns:
            Tuple of ``(synced_record_count, failed_zone_count)``.
        """
        provider = self._get_provider_with_credentials(  # type: ignore[attr-defined]
            zone, warn_on_missing=False, require_zone_id=True
        )
        if not provider:
            print_warning(f"{zone['zone_name']}: Skipped (no credentials)")
            return 0, 0
        try:
            print_info(f"Syncing zone: {zone['zone_name']}...")
            stats = self._sync_zone_with_provider(zone, provider)  # type: ignore[attr-defined]
            synced = stats.get(SyncStatus.SYNCED, 0) if stats else 0
            if synced > 0:
                print_success(f"{zone['zone_name']}: {synced} records synced")
                return synced, 0
            print_warning(f"{zone['zone_name']}: Sync failed or no records")
            return 0, 1
        finally:
            provider.close()

    def _detect_ip_addresses(self) -> NetworkData | None:
        """Detect current public IPv4/IPv6 addresses for forced updates.

        Returns:
            Populated ``NetworkData`` instance, or ``None`` if detection failed.
        """
        print_subsection("Detecting Current IP Addresses")
        try:
            network = NetworkData(config=self.config, logger=self.logger)
            network.load_current_ip_addresses()
            if network.ipv4_address:
                print_success(f"IPv4: {network.ipv4_address}")
            else:
                print_warning("IPv4: Not detected")
            if network.ipv6_address:
                print_success(f"IPv6: {network.ipv6_address}")
            else:
                print_warning("IPv6: Not detected")
            if not network.ipv4_address and not network.ipv6_address:
                print_error("No IP addresses detected! Cannot proceed.")
                return None
            return network
        except NetworkError as exc:
            print_error(f"Failed to detect IP addresses: {exc}")
            self.logger.error(f"IP detection failed in force update: {exc}")
            return None

    ############################################################################
    # Zone & Record Update Dispatch
    ############################################################################

    def _process_all_zones(
        self, zones: list[Any], network: NetworkData
    ) -> dict[str, int]:
        """Process all enabled zones and return aggregate update counters.

        Args:
            zones: Enabled zone dictionaries/rows.
            network: Detected public IP data.

        Returns:
            Dictionary of update statistics.
        """
        stats = {
            UpdateStatus.TOTAL: 0,
            UpdateStatus.UPDATED: 0,
            UpdateStatus.FAILED: 0,
            UpdateStatus.SKIPPED: 0,
        }
        for zone_row in zones:
            self._process_single_zone(row_to_dict(zone_row), network, stats)
        return stats

    def _process_single_zone(
        self,
        zone: dict[str, Any],
        network: NetworkData,
        stats: dict[str, int],
    ) -> None:
        """Create a scoped provider client and process all records for ``zone``.

        Args:
            zone: Zone dictionary.
            network: Detected public IP data.
            stats: Mutable update statistics dictionary.
        """
        dyndns_config = self.db.get_dyndns_config_by_zone(zone["id"])
        if not dyndns_config:
            print_warning(
                f"Zone '{zone['zone_name']}' has no API credentials - skipping"
            )
            return
        provider = self._create_provider_client(  # type: ignore[attr-defined]
            zone, row_to_dict(dyndns_config)
        )
        if not provider:
            return
        try:
            synced_zone = self._ensure_provider_zone_id_on_process(zone, provider)
            if synced_zone:
                print(f"\n{Colors.BOLD}Zone: {synced_zone['zone_name']}{Colors.NC}")
                self._process_zone_records(synced_zone, provider, network, stats)
        finally:
            provider.close()

    def _ensure_provider_zone_id_on_process(
        self, zone: dict[str, Any], provider: ProviderDNSClient
    ) -> dict[str, Any] | None:
        """Ensure ``provider_zone_id`` exists for ``zone`` before record updates.

        Args:
            zone: Zone dictionary.
            provider: Active provider client.

        Returns:
            Zone dictionary with ``provider_zone_id``, or ``None`` on error.
        """
        if not zone.get("provider_zone_id"):
            print_info(f"Syncing zone '{zone['zone_name']}' with provider...")
            if not self._sync_zone_id(zone, provider):  # type: ignore[attr-defined]
                print_error(f"Failed to sync zone '{zone['zone_name']}' - skipping")
                return None
            zone_row = self.db.get_zone_by_id(zone["id"])
            if zone_row:
                return row_to_dict(zone_row)
        return zone

    def _process_zone_records(
        self,
        zone: dict[str, Any],
        provider: ProviderDNSClient,
        network: NetworkData,
        stats: dict[str, int],
    ) -> None:
        """Update all enabled records in ``zone`` via DynDNS bundle or REST API.

        Args:
            zone: Zone dictionary.
            provider: Active provider client.
            network: Detected public IP data.
            stats: Mutable update statistics dictionary.
        """
        records = self.db.get_records_by_zone(zone["id"], enabled_only=True)
        if not records:
            return
        if self.config.dns_update_method == UpdateMethod.DYNDNS:
            if self._process_dyndns_zone_records(
                zone, records, provider, network, stats
            ):
                return

        for record_row in records:
            self._process_single_rest_record(
                row_to_dict(record_row), provider, network, stats
            )

    def _process_single_rest_record(
        self,
        record: dict[str, Any],
        provider: ProviderDNSClient,
        network: NetworkData,
        stats: dict[str, int],
    ) -> None:
        """Update a single DNS record via REST API and update ``stats``.

        Args:
            record: Record dictionary.
            provider: Active provider client.
            network: Detected public IP data.
            stats: Mutable update statistics dictionary.
        """
        stats[UpdateStatus.TOTAL] += 1
        new_ip = self._get_target_ip(record, network)  # type: ignore[attr-defined]
        if not new_ip:
            print_warning(
                f"  {record['record_name']} ({record['record_type']}) - No IP available"
            )
            stats[UpdateStatus.SKIPPED] += 1
            return

        old_ip = self._get_current_ip(record)  # type: ignore[attr-defined]
        if not self._ensure_provider_record_id(record, provider):  # type: ignore[attr-defined]
            stats[UpdateStatus.FAILED] += 1
            return
        if self._update_dns_record(record, provider, old_ip, new_ip):  # type: ignore[attr-defined]
            stats[UpdateStatus.UPDATED] += 1
        else:
            stats[UpdateStatus.FAILED] += 1

    def _process_dyndns_zone_records(
        self,
        zone: dict[str, Any],
        records: list[dict[str, Any]],
        provider: ProviderDNSClient,
        network: NetworkData,
        stats: dict[str, int],
    ) -> bool:
        """Execute native IONOS DynDNS ``updateUrl`` for ``zone``.

        Args:
            zone: Zone dictionary.
            records: Enabled records in ``zone``.
            provider: Active provider client.
            network: Detected public IP data.
            stats: Mutable update statistics dictionary.

        Returns:
            True if updated via ``updateUrl``, False to fall back to REST API.
        """
        if not self.db.get_dyndns_config_by_zone(zone["id"]):
            return False
        handler = DynDNSBundleHandler(self.config, self.db, network, self.logger)
        print_info(
            f"Verifying/synchronizing DynDNS bundle for '{zone['zone_name']}'..."
        )
        update_url = handler.sync_or_activate_dyndns_bundle(provider, zone)
        if not update_url:
            return False

        print_info("Executing native DynDNS update via updateUrl...")
        if not provider.execute_dyndns_update_url(
            update_url, ipv4=network.ipv4_address, ipv6=network.ipv6_address
        ):
            print_warning(
                "Native DynDNS updateUrl request failed. "
                "Falling back to REST API record updates."
            )
            return False

        print_success("Native DynDNS update URL executed successfully.")
        self._apply_dyndns_record_updates(records, network, stats)
        return True

    def _apply_dyndns_record_updates(
        self,
        records: list[dict[str, Any]],
        network: NetworkData,
        stats: dict[str, int],
    ) -> None:
        """Persist local IP state and audit history after a DynDNS bundle update.

        Args:
            records: Enabled records in the updated zone.
            network: Detected public IP data.
            stats: Mutable update statistics dictionary.
        """
        for record_row in records:
            record = row_to_dict(record_row)
            stats[UpdateStatus.TOTAL] += 1
            new_ip = self._get_target_ip(record, network)  # type: ignore[attr-defined]
            if new_ip:
                old_ip = self._get_current_ip(record)  # type: ignore[attr-defined]
                self.db.update_ip_address(record["id"], new_ip, changed=True)
                self.db.log_dns_update(
                    record["id"], old_ip, new_ip, UpdateStatus.SUCCESS
                )
                stats[UpdateStatus.UPDATED] += 1
                print_success(
                    f"  Updated {record['record_name']} ({record['record_type']}) -> {new_ip}"
                )
            else:
                stats[UpdateStatus.SKIPPED] += 1
