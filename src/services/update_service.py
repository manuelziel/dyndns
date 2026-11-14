#!/usr/bin/env python3
"""Update service for orchestrating IP propagation and SQLite audit updates.

Coordinates DNS record updates across ``UpdateMethod.DYNDNS`` and
``UpdateMethod.REST`` by delegating execution to ``DynDNSBundleHandler`` and
``RESTRecordHandler``.

Author: Manuel Ziel
License: MIT
"""

################################################################################
# IMPORTS & DEPENDENCIES
################################################################################

from typing import Any

from ..core.constants import RecordType, SyncStatus, UpdateMethod, UpdateStatus
from ..core.exceptions import APIError, DatabaseError, DynDNSException, RecordNotFoundError
from ..utils.colors import LOG_SYMBOLS
from .helpers.dyndns_helper import DynDNSBundleHandler
from .helpers.rest_helper import RESTRecordHandler

################################################################################
# UPDATE SERVICE CLASS
################################################################################


class UpdateService:
    """Orchestrates DNS IP updates and local database synchronization.

    Attributes:
        config: ``ConfigManager`` instance.
        database: ``Database`` manager instance.
        network: ``NetworkData`` instance.
        logger: Logger instance.
        sync_service: ``SyncService`` instance.
        dyndns_helper: Strategy handler for native DynDNS URL updates.
        rest_helper: Strategy handler for direct REST record updates.
    """

    def __init__(
        self,
        config: Any,
        database: Any,
        network: Any,
        logger: Any,
        sync_service: Any,
        dyndns_helper: DynDNSBundleHandler | None = None,
        rest_helper: RESTRecordHandler | None = None,
    ) -> None:
        """Initialize update service reusing shared strategy handlers when available.

        Args:
            config: ``ConfigManager`` instance.
            database: ``Database`` manager instance.
            network: ``NetworkData`` instance.
            logger: Logger instance.
            sync_service: ``SyncService`` instance.
            dyndns_helper: Optional injected ``DynDNSBundleHandler``.
            rest_helper: Optional injected ``RESTRecordHandler``.
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

    ############################################################################
    # RECORD EVALUATION PIPELINE
    ############################################################################

    def process_records(self, enabled_zones: list[dict[str, Any]]) -> bool:
        """Compare local record IPs against detected network IPs.

        Args:
            enabled_zones: Active zone dictionaries for the current cycle.

        Returns:
            True when evaluation completes without error, False otherwise.
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
        except (KeyError, TypeError, ValueError, DynDNSException) as exc:
            self.logger.error(f"Error processing records: {exc}")
            return False

    def _evaluate_record_update(self, record: dict[str, Any]) -> None:
        """Annotate ``record`` in-place with ``needs_update``, ``old_ip``, and ``new_ip``.

        Args:
            record: DNS record dictionary to inspect.
        """
        current_ip = self._resolve_target_ip_for_record(record)
        if not current_ip:
            self.logger.debug(
                f"Skipping '{record['record_name']}' ({record['record_type']}) - no local IP available"
            )
            return
        curr_ip_row = record.get("current_ip")
        old_ip = (
            curr_ip_row.get("ip_address")
            if isinstance(curr_ip_row, dict)
            else record.get("ip_address")
        )
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
            self.logger.debug(
                f"Record '{record['record_name']}' ({record['record_type']}) up-to-date ({current_ip})"
            )

    def _resolve_target_ip_for_record(self, record: dict[str, Any]) -> str | None:
        """Return the detected public IP matching ``record['record_type']``.

        Args:
            record: DNS record dictionary.

        Returns:
            IPv4 or IPv6 address string, or ``None``.
        """
        if record["record_type"] == RecordType.A:
            return self.network.ipv4_address
        if record["record_type"] == RecordType.AAAA:
            return self.network.ipv6_address
        return None

    ############################################################################
    # PROVIDER & DATABASE UPDATE EXECUTION
    ############################################################################

    def save_updates(
        self,
        enabled_zones: list[dict[str, Any]],
        is_startup: bool = False,
    ) -> bool:
        """Propagate pending DNS updates to the provider and SQLite database.

        Args:
            enabled_zones: Active zone dictionaries.
            is_startup: True during the initial daemon startup cycle.

        Returns:
            True if propagation completed without fatal error, False otherwise.
        """
        try:
            zones_to_sync = self.sync_service.collect_zones_needing_sync(
                enabled_zones, is_startup=is_startup
            )
            if zones_to_sync:
                self._run_pre_update_sync(zones_to_sync, enabled_zones, is_startup)
            updates_succeeded, updates_failed = self._dispatch_zone_updates(enabled_zones)
            if updates_succeeded > 0 or updates_failed > 0:
                self.logger.info(
                    f"Database updates: {updates_succeeded} succeeded, {updates_failed} failed"
                )
            self.logger.debug("Updates saved successfully")
            return True
        except (DatabaseError, APIError, DynDNSException) as exc:
            self.logger.error(f"Failed to save updates: {exc}")
            return False
        except Exception as exc:
            self.logger.error(f"Unexpected error saving updates: {exc}")
            return False

    def _dispatch_zone_updates(
        self, enabled_zones: list[dict[str, Any]]
    ) -> tuple[int, int]:
        """Dispatch DynDNS or REST updates across all ``enabled_zones``.

        Args:
            enabled_zones: Active zone dictionaries.

        Returns:
            Tuple ``(updates_succeeded, updates_failed)``.
        """
        updates_succeeded = 0
        updates_failed = 0
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
        return updates_succeeded, updates_failed

    def _run_pre_update_sync(
        self,
        zones_to_sync: set[int],
        enabled_zones: list[dict[str, Any]],
        is_startup: bool,
    ) -> None:
        """Run pre-update provider reconciliation for ``zones_to_sync``.

        Args:
            zones_to_sync: Set of database zone IDs to synchronize.
            enabled_zones: Active zone dictionaries.
            is_startup: True during the initial daemon startup cycle.
        """
        count = len(zones_to_sync)
        if is_startup:
            target = (
                f"Verifying native DynDNS updateUrl bundles for {count} zone(s)..."
                if self.config.dns_update_method == UpdateMethod.DYNDNS
                else f"Checking {count} zone(s) to verify managed records on provider IONOS..."
            )
            self.logger.info(f"Startup Verification: {target}")
        elif self.config.daemon_sync_checks:
            self.logger.info(
                f"Reconciliation: Syncing {count} zone(s) to restore missing provider_record_ids"
            )
        else:
            self.logger.debug(f"Need to sync {count} zone(s) before updates")

        self.sync_service.sync_zones_and_refresh_records(
            zones_to_sync, enabled_zones, is_startup=is_startup
        )
        if is_startup:
            done_msg = (
                "DynDNS bundle check completed"
                if self.config.dns_update_method == UpdateMethod.DYNDNS
                else "Zone check completed"
            )
            self.logger.info(f"Startup Verification: {done_msg}")
        elif self.config.daemon_sync_checks:
            self.logger.info("Reconciliation: Zone sync completed")

    def _process_dyndns_zone(self, zone: dict[str, Any]) -> tuple[bool, int, int]:
        """Update ``zone`` via its native DynDNS ``updateUrl`` bundle.

        Args:
            zone: Zone dictionary with ``records``.

        Returns:
            Tuple ``(handled, updates_succeeded, updates_failed)``.
        """
        records_needing_update = [
            r
            for r in zone["records"]
            if r.get("needs_update")
            or r.get("sync_status") in (SyncStatus.PENDING_SYNC, SyncStatus.NEW)
        ]
        dyndns_row = self.database.get_dyndns_config_by_zone(zone["id"])
        if not records_needing_update and bool(dyndns_row and dict(dyndns_row).get("update_url")):
            self.logger.debug(f"Zone '{zone['zone_name']}': All DynDNS records up-to-date")
            return True, 0, 0

        self.logger.info(f"Executing DynDNS update URL for zone '{zone['zone_name']}'...")
        target_records = records_needing_update or zone["records"]
        client = self.sync_service.get_provider_client(zone["id"])
        if not client:
            return False, 0, 0
        success, succ, fail = self.dyndns_helper.execute_dyndns_update(
            client, zone, target_records
        )
        if success:
            return True, succ, fail
        self.logger.warning(
            f"DynDNS updateUrl failed for zone '{zone['zone_name']}'. "
            "Falling back to REST API record updates."
        )
        return False, 0, 0

    def _process_rest_zone(self, zone: dict[str, Any]) -> tuple[int, int]:
        """Update modified records in ``zone`` individually via REST ``PUT``.

        Args:
            zone: Zone dictionary with ``records``.

        Returns:
            Tuple ``(updates_succeeded, updates_failed)``.
        """
        updates_succeeded = 0
        updates_failed = 0
        client = self.sync_service.get_provider_client(zone["id"])
        for record in zone["records"]:
            if not record.get("needs_update"):
                continue
            if self._update_single_rest_record(client, zone, record):
                updates_succeeded += 1
            else:
                updates_failed += 1
        return updates_succeeded, updates_failed

    def _update_single_rest_record(
        self,
        client: Any | None,
        zone: dict[str, Any],
        record: dict[str, Any],
    ) -> bool:
        """Update a single DNS record via REST API and log the audit entry.

        Args:
            client: ``ProviderDNSClient`` or ``None``.
            zone: Zone dictionary.
            record: Record dictionary to update.

        Returns:
            True if updated and persisted in SQLite, False otherwise.
        """
        old_ip, new_ip = record.get("old_ip"), record.get("new_ip")
        try:
            if not record.get("provider_record_id"):
                raise APIError("Missing provider_record_id after sync")
            if not client or not new_ip:
                raise APIError("Cannot obtain provider client or target IP")
            if not self.rest_helper.update_record_ip(client, zone, record, new_ip):
                raise APIError("Provider API update failed")
            self._record_rest_update_success(record, old_ip, new_ip)
            return True
        except (APIError, RecordNotFoundError) as exc:
            self._log_update_failure(record, old_ip, new_ip or "", str(exc))
        except DatabaseError as exc:
            self.logger.error(f"Database error updating '{record['record_name']}': {exc}")
        except Exception as exc:
            self.logger.error(f"Unexpected error updating '{record['record_name']}': {exc}")
        return False

    def _record_rest_update_success(
        self, record: dict[str, Any], old_ip: str | None, new_ip: str
    ) -> None:
        """Persist a successful REST record IP update and emit a success log.

        Args:
            record: Updated record dictionary.
            old_ip: Previous IP address.
            new_ip: Applied IP address.
        """
        self.database.update_ip_address(
            record_id=record["id"], ip_address=new_ip, changed=True
        )
        self.database.log_dns_update(
            record_id=record["id"],
            old_ip=old_ip,
            new_ip=new_ip,
            status=UpdateStatus.SUCCESS,
        )
        self.logger.success(
            f"[REST API TRIGGERED] Record '{record['record_name']}' "
            f"({record['record_type']}) updated: {old_ip or 'none'} "
            f"{LOG_SYMBOLS['ARROW']} {new_ip}"
        )

    def _log_update_failure(
        self,
        record: dict[str, Any],
        old_ip: str | None,
        new_ip: str,
        error_msg: str,
    ) -> None:
        """Record a failed DNS update attempt in logs and ``dns_updates``.

        Args:
            record: Record dictionary.
            old_ip: Previous IP address.
            new_ip: Target IP address.
            error_msg: Failure message.
        """
        self.logger.error(
            f"Failed to update '{record['record_name']}' ({record['record_type']}): {error_msg}"
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

    def update_provider_record(self, record: dict[str, Any], new_ip: str) -> bool:
        """Update a single provider record via ``RESTRecordHandler``.

        Args:
            record: Record dictionary with ``provider_record_id`` and ``zone_id``.
            new_ip: Target IP address string.

        Returns:
            True on success, False otherwise.
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
