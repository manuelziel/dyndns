#!/usr/bin/env python3
"""Update Service for managing IP propagation and record state updates.

Orchestrates IP updates across multiple providers/strategies (`UpdateMethod.REST`
and `UpdateMethod.DYNDNS`) by delegating to modular strategy handlers
(`DynDNSBundleHandler` and `RESTRecordHandler`), ensuring zero duplication and
high cohesion.

Author: Manuel Ziel
License: MIT
"""

################################################################################
# IMPORTS & DEPENDENCIES
################################################################################

from typing import Any, Dict, List, Optional, Set, Tuple

from src.core.constants import (
    RecordType,
    SyncStatus,
    UpdateMethod,
    UpdateStatus,
)
from src.core.exceptions import (
    APIError,
    DatabaseError,
    DynDNSException,
    RecordNotFoundError,
)
from src.services.helpers.dyndns_helper import DynDNSBundleHandler
from src.services.helpers.rest_helper import RESTRecordHandler
from src.utils.colors import LOG_SYMBOLS

################################################################################
# UPDATE SERVICE CLASS
################################################################################

class UpdateService:
    """Service orchestrating DNS updates and database synchronization.

    Attributes:
        config: Configuration object.
        database: Database manager instance.
        network: NetworkData instance for IPs.
        logger: Logger instance.
        sync_service: SyncService instance.
        dyndns_helper: Handler for native DynDNS URL updates.
        rest_helper: Handler for direct REST API updates.
    """

    def __init__(
        self,
        config: Any,
        database: Any,
        network: Any,
        logger: Any,
        sync_service: Any,
        dyndns_helper: Optional[DynDNSBundleHandler] = None,
        rest_helper: Optional[RESTRecordHandler] = None,
    ) -> None:
        """Initialize update service with modular handlers.

        Args:
            config: Configuration object.
            database: Database manager instance.
            network: NetworkData instance.
            logger: Logger instance.
            sync_service: SyncService instance.
            dyndns_helper: Optional injected DynDNSBundleHandler instance.
            rest_helper: Optional injected RESTRecordHandler instance.
        """
        self.config = config
        self.database = database
        self.network = network
        self.logger = logger
        self.sync_service = sync_service
        self.dyndns_helper = (
            dyndns_helper
            or getattr(sync_service, "dyndns_helper", None)
            or DynDNSBundleHandler(config, database, network, logger)
        )
        self.rest_helper = (
            rest_helper
            or getattr(sync_service, "rest_helper", None)
            or RESTRecordHandler(config, database, network, logger)
        )


    def process_records(self, enabled_zones: List[Dict[str, Any]]) -> bool:
        """Evaluate local records against network state to detect needed IP updates.

        Args:
            enabled_zones: List of active zone dictionaries.

        Returns:
            True if processing completed without errors, False otherwise.
        """
        try:
            self.logger.debug("Processing records across enabled zones...")
            if not enabled_zones:
                self.logger.warning("No enabled zones to process")
                return True

            for zone in enabled_zones:
                for record in zone.get("records") or []:
                    self._evaluate_record_update(record)
            return True
        except (KeyError, TypeError, ValueError, DynDNSException) as e:
            self.logger.error(f"Error processing records: {e}")
            return False


    def _evaluate_record_update(self, record: Dict[str, Any]) -> None:
        """Evaluate a single record against current network IP addresses.

        Args:
            record: DNS record dictionary to update in-place.
        """
        current_ip = self._resolve_target_ip_for_record(record)
        if not current_ip:
            self.logger.debug(f"Skipping '{record['record_name']}' ({record['record_type']}) - no local IP available")
            return

        curr_ip_row = record.get("current_ip")
        old_ip = curr_ip_row.get("ip_address") if isinstance(curr_ip_row, dict) else record.get("ip_address")
        needs_update = old_ip != current_ip
        record["needs_update"] = needs_update
        record["old_ip"] = old_ip
        record["new_ip"] = current_ip

        if needs_update:
            self.logger.info(
                f"Record '{record['record_name']}' ({record['record_type']}) needs update: "
                f"{old_ip or 'none'} {LOG_SYMBOLS['ARROW']} {current_ip}"
            )
        else:
            self.logger.debug(f"Record '{record['record_name']}' ({record['record_type']}) up-to-date ({current_ip})")


    def _resolve_target_ip_for_record(
        self, record: Dict[str, Any]
    ) -> Optional[str]:
        """Determine target network IP address based on record type.

        Args:
            record: DNS record dictionary.

        Returns:
            IP string or None if unsupported or unavailable.
        """
        if record["record_type"] == RecordType.A:
            return self.network.ipv4_address
        if record["record_type"] == RecordType.AAAA:
            return self.network.ipv6_address
        return None


    def save_updates(
        self,
        enabled_zones: List[Dict[str, Any]],
        is_startup: bool = False,
    ) -> bool:
        """Save DNS record IP updates to provider and local database.

        Args:
            enabled_zones: List of enabled zone dictionaries.
            is_startup: True if running during initial daemon verification.

        Returns:
            True if all processing completed without fatal error.
        """
        try:
            zones_to_sync = self.sync_service.collect_zones_needing_sync(enabled_zones, is_startup=is_startup)
            if zones_to_sync:
                self._run_pre_update_sync(zones_to_sync, enabled_zones, is_startup)

            updates_succeeded, updates_failed = 0, 0
            for zone in enabled_zones:
                if not zone.get("records"):
                    continue
                if self.config.dns_update_method == UpdateMethod.DYNDNS:
                    handled, succ, fail = self._process_dyndns_zone(zone)
                    if handled:
                        updates_succeeded += succ
                        updates_failed += fail
                        continue
                succ, fail = self._process_rest_zone(zone)
                updates_succeeded += succ
                updates_failed += fail

            if updates_succeeded > 0 or updates_failed > 0:
                self.logger.info(f"Database updates: {updates_succeeded} succeeded, {updates_failed} failed")
            self.logger.debug("Updates saved successfully")
            return True
        except (DatabaseError, APIError, DynDNSException) as e:
            self.logger.error(f"Failed to save updates: {e}")
            return False
        except Exception as e:
            self.logger.error(f"Unexpected error saving updates: {e}")
            return False


    def _run_pre_update_sync(
        self,
        zones_to_sync: Set[int],
        enabled_zones: List[Dict[str, Any]],
        is_startup: bool,
    ) -> None:
        """Execute pre-update provider synchronization for zones.

        Args:
            zones_to_sync: Set of zone IDs to synchronize.
            enabled_zones: List of active zones.
            is_startup: True if running on startup check cycle.
        """
        count = len(zones_to_sync)
        if is_startup:
            if self.config.dns_update_method == UpdateMethod.DYNDNS:
                self.logger.info(f"Startup Verification: Verifying native DynDNS updateUrl bundles for {count} zone(s)...")
            else:
                self.logger.info(f"Startup Verification: Checking {count} zone(s) to verify all managed records exist on provider IONOS...")
        elif self.config.daemon_sync_checks:
            self.logger.info(f"Reconciliation: Syncing {count} zone(s) to restore missing provider_record_ids")
        else:
            self.logger.debug(f"Need to sync {count} zone(s) before updates")

        self.sync_service.sync_zones_and_refresh_records(zones_to_sync, enabled_zones, is_startup=is_startup)

        if is_startup:
            msg = "DynDNS bundle check completed" if self.config.dns_update_method == UpdateMethod.DYNDNS else "Zone check completed"
            self.logger.info(f"Startup Verification: {msg}")
        elif self.config.daemon_sync_checks:
            self.logger.info("Reconciliation: Zone sync completed")


    def _process_dyndns_zone(
        self, zone: Dict[str, Any]
    ) -> Tuple[bool, int, int]:
        """Process zone updates via native DynDNS update URL (`GET updateUrl`).

        Args:
            zone: Zone dictionary.

        Returns:
            Tuple of (handled boolean, updates_succeeded, updates_failed).
        """
        records_needing_update = [
            r for r in zone["records"]
            if r.get("needs_update") or r.get("sync_status") in (SyncStatus.PENDING_SYNC, SyncStatus.NEW)
        ]
        dyndns_row = self.database.get_dyndns_config_by_zone(zone["id"])
        if not records_needing_update and bool(dyndns_row and dict(dyndns_row).get("update_url")):
            self._mark_records_checked(zone["records"])
            self.logger.debug(f"Zone '{zone['zone_name']}': All DynDNS records up-to-date")
            return True, 0, 0

        self.logger.info(f"Executing DynDNS update URL for zone '{zone['zone_name']}'...")
        target_records = records_needing_update or zone["records"]
        client = self.sync_service.get_provider_client(zone["id"])
        if not client:
            return False, 0, 0

        success, succ, fail = self.dyndns_helper.execute_dyndns_update(client, zone, target_records)
        if success:
            return True, succ, fail

        self.logger.warning(
            f"DynDNS updateUrl failed or not configured for zone '{zone['zone_name']}'. "
            "Falling back to REST API record updates."
        )
        return False, 0, 0


    def _mark_records_checked(self, records: List[Dict[str, Any]]) -> None:
        """Mark records as checked when no IP change is required.

        Args:
            records: List of record dictionaries.
        """
        for record in records:
            try:
                if (
                    record["record_type"] == RecordType.A
                    and self.network.ipv4_address
                ):
                    self.database.update_ip_address(
                        record["id"], self.network.ipv4_address, changed=False
                    )
                elif (
                    record["record_type"] == RecordType.AAAA
                    and self.network.ipv6_address
                ):
                    self.database.update_ip_address(
                        record["id"], self.network.ipv6_address, changed=False
                    )
            except DatabaseError as e:
                self.logger.warning(
                    f"Failed to update last_checked_at for '{record['record_name']}': {e}"
                )


    def _process_rest_zone(
        self, zone: Dict[str, Any]
    ) -> Tuple[int, int]:
        """Process zone updates via direct REST API record PUT requests.

        Args:
            zone: Zone dictionary.

        Returns:
            Tuple of (updates_succeeded count, updates_failed count).
        """
        updates_succeeded = 0
        updates_failed = 0
        client = self.sync_service.get_provider_client(zone["id"])

        for record in zone["records"]:
            if not record.get("needs_update"):
                self._mark_records_checked([record])
                continue

            if self._update_single_rest_record(client, zone, record):
                updates_succeeded += 1
            else:
                updates_failed += 1

        return updates_succeeded, updates_failed


    def _update_single_rest_record(
        self,
        client: Optional[Any],
        zone: Dict[str, Any],
        record: Dict[str, Any],
    ) -> bool:
        """Update a single DNS record via REST API and record the result in DB.

        Args:
            client: Provider client instance or None.
            zone: Zone dictionary.
            record: Record dictionary to update.

        Returns:
            True if updated and persisted successfully, False otherwise.
        """
        old_ip = record.get("old_ip")
        new_ip = record.get("new_ip")
        try:
            if not record.get("provider_record_id"):
                self.logger.error(f"Record '{record['record_name']}' missing provider_record_id after sync - skipping")
                raise APIError("Missing provider_record_id after sync")
            if not client:
                raise APIError("Cannot obtain provider client")
            if not self.rest_helper.update_record_ip(client, zone, record, new_ip):
                raise APIError("Provider API update failed")

            self.database.update_ip_address(record_id=record["id"], ip_address=new_ip, changed=True)
            self.database.log_dns_update(
                record_id=record["id"], old_ip=old_ip, new_ip=new_ip, status=UpdateStatus.SUCCESS
            )
            self.logger.success(
                f"[REST API TRIGGERED] Record '{record['record_name']}' "
                f"({record['record_type']}) updated: {old_ip or 'none'} {LOG_SYMBOLS['ARROW']} {new_ip}"
            )
            return True
        except (APIError, RecordNotFoundError) as e:
            self._log_update_failure(record, old_ip, new_ip, str(e))
        except DatabaseError as e:
            self.logger.error(f"Database error updating '{record['record_name']}': {e}")
        except Exception as e:
            self.logger.error(f"Unexpected error updating '{record['record_name']}': {e}")
        return False


    def _log_update_failure(
        self,
        record: Dict[str, Any],
        old_ip: Optional[str],
        new_ip: Optional[str],
        error_msg: str,
    ) -> None:
        """Log failure of a DNS update attempt.

        Args:
            record: Record dictionary.
            old_ip: Previous IP address.
            new_ip: Target IP address.
            error_msg: Error message string.
        """
        self.logger.error(
            f"Failed to update '{record['record_name']}' "
            f"({record['record_type']}): {error_msg}"
        )
        try:
            self.database.log_dns_update(
                record_id=record["id"],
                old_ip=old_ip,
                new_ip=new_ip,
                status=UpdateStatus.FAILED,
                error_message=error_msg,
            )
        except DatabaseError as log_error:
            self.logger.error(f"Failed to log update failure: {log_error}")


    def update_provider_record(
        self, record: Dict[str, Any], new_ip: str
    ) -> bool:
        """Backward-compatibility proxy for single provider record updates.

        Delegates directly to `self.rest_helper.update_record_ip()`.

        Args:
            record: Record dictionary with provider_record_id and zone_id.
            new_ip: Target IP address.

        Returns:
            True if successful, False otherwise.
        """
        if not record.get("provider_record_id"):
            return False

        zone_row = self.database.get_zone_by_id(record["zone_id"])
        if not zone_row:
            return False

        zone = dict(zone_row)
        client = self.sync_service.get_provider_client(zone["id"])
        if not client:
            return False

        return self.rest_helper.update_record_ip(client, zone, record, new_ip)
