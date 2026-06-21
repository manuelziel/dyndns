#!/usr/bin/env python3
"""Update Service for managing IP comparisons and DNS updates.

This service is responsible for comparing current IPs with local DB,
determining necessary updates, and pushing changes to the provider API.

Author: Manuel Ziel
License: MIT
"""

################################################################################
# IMPORTS & DEPENDENCIES
################################################################################

# Standard Imports
import logging
import time
from typing import Any, Dict, List, Optional

# Local Imports
from src.core.constants import RecordType, SyncStatus, UpdateStatus
from src.core.exceptions import APIError, DatabaseError, RecordNotFoundError, DynDNSException
from src.utils.colors import LOG_SYMBOLS


################################################################################
# UPDATE SERVICE CLASS
################################################################################

class UpdateService:
    """Service handling IP change detection and DNS updates.

    Attributes:
        config: Configuration object.
        database: Database manager instance.
        network: NetworkData instance for IPs.
        sync_service: SyncService instance for reconciliation.
        logger: Logger instance.
    """

    def __init__(
        self,
        config: Any,
        database: Any,
        network: Any,
        sync_service: Any,
        logger: Any,
    ) -> None:
        """Initialize update service.

        Args:
            config: Configuration object.
            database: Database manager instance.
            network: NetworkData instance.
            sync_service: SyncService instance.
            logger: Logger instance.
        """
        self.config = config
        self.database = database
        self.network = network
        self.sync_service = sync_service
        self.logger = logger


    def process_records(self, enabled_zones: List[Dict[str, Any]]) -> bool:
        """Compare detected IPs with database records.

        Determines which records need updates based on IP changes.
        Modifies enabled_zones records in-place by adding 'needs_update',
        'old_ip', and 'new_ip' flags.

        Args:
            enabled_zones: List of currently enabled zone dictionaries.

        Returns:
            True if processing completed successfully, False otherwise.
        """
        try:
            if not enabled_zones:
                self.logger.debug("No zones to process")
                return True

            self.logger.debug("Processing DNS records...")

            total_records = 0
            records_need_update = 0
            new_ip = None
            old_ip = None

            for zone in enabled_zones:
                if not zone.get("records"):
                    continue

                self.logger.debug(
                    f"Processing zone '{zone['zone_name']}' with "
                    f"{len(zone['records'])} records"
                )

                for record in zone["records"]:
                    total_records += 1

                    if record["record_type"] == RecordType.A:
                        new_ip = self.network.ipv4_address
                        if not new_ip:
                            self.logger.debug(
                                f"Skipping A record '{record['record_name']}' - "
                                f"no IPv4 detected"
                            )
                            continue

                    elif record["record_type"] == RecordType.AAAA:
                        new_ip = self.network.ipv6_address
                        if not new_ip:
                            self.logger.debug(
                                f"Skipping AAAA record '{record['record_name']}' - "
                                f"no IPv6 detected"
                            )
                            continue
                    else:
                        self.logger.debug(
                            f"Skipping record type '{record['record_type']}' "
                            f"for '{record['record_name']}'"
                        )
                        continue

                    old_ip = (
                        record["current_ip"].get("ip_address")
                        if record.get("current_ip")
                        else None
                    )

                    if not record.get("provider_record_id"):
                        self.logger.warning(
                            f"Record '{record['record_name']}' "
                            f"({record['record_type']}) missing provider_record_id - "
                            f"will re-sync and update"
                        )
                        record["needs_update"] = True
                        record["old_ip"] = old_ip
                        record["new_ip"] = new_ip
                        records_need_update += 1

                        if old_ip:
                            self.logger.info(
                                f"Record '{record['record_name']}' "
                                f"({record['record_type']}) will be recreated: "
                                f"{old_ip} {LOG_SYMBOLS['ARROW']} {new_ip}"
                            )
                        else:
                            self.logger.info(
                                f"Record '{record['record_name']}' "
                                f"({record['record_type']}) will be created: "
                                f"{LOG_SYMBOLS['ARROW']} {new_ip}"
                            )
                        continue

                    if old_ip != new_ip:
                        record["needs_update"] = True
                        record["old_ip"] = old_ip
                        record["new_ip"] = new_ip
                        records_need_update += 1

                        if old_ip:
                            self.logger.info(
                                f"Record '{record['record_name']}' "
                                f"({record['record_type']}) needs update: "
                                f"{old_ip} {LOG_SYMBOLS['ARROW']} {new_ip}"
                            )
                        else:
                            self.logger.info(
                                f"Record '{record['record_name']}' "
                                f"({record['record_type']}) needs initial IP: "
                                f"{LOG_SYMBOLS['ARROW']} {new_ip}"
                            )
                    else:
                        record["needs_update"] = False
                        self.logger.debug(
                            f"Record '{record['record_name']}' "
                            f"({record['record_type']}) unchanged: {old_ip}"
                        )

            if records_need_update > 0:
                self.logger.info(
                    f"Found {records_need_update}/{total_records} records "
                    f"requiring updates"
                )
            else:
                self.logger.debug(f"All {total_records} records up-to-date")

            self.logger.debug("Data processing completed")
            return True

        except DynDNSException as e:
            self.logger.error(f"Data processing failed: {e}")
            return False


    def save_updates(self, enabled_zones: List[Dict[str, Any]]) -> bool:
        """Update database and provider DNS with new IPs.

        Synchronizes zones if needed and pushes IP updates to the provider API.

        Args:
            enabled_zones: List of currently enabled zone dictionaries.

        Returns:
            True if all updates completed successfully, False otherwise.
        """
        try:
            if not enabled_zones:
                self.logger.debug("No zones to save")
                return True

            self.logger.debug("Saving results to database...")

            updates_succeeded = 0
            updates_failed = 0
            old_ip = None
            new_ip = None
            error_msg = None

            zones_to_sync = self.sync_service.collect_zones_needing_sync(
                enabled_zones
            )

            if zones_to_sync:
                if self.config.daemon_sync_checks:
                    self.logger.info(
                        f"Reconciliation: Syncing {len(zones_to_sync)} zone(s) "
                        f"to restore missing provider_record_ids"
                    )
                else:
                    self.logger.debug(
                        f"Need to sync {len(zones_to_sync)} zone(s) before updates"
                    )

                self.sync_service.sync_zones_and_refresh_records(
                    zones_to_sync, enabled_zones
                )

                if self.config.daemon_sync_checks:
                    self.logger.info("Reconciliation: Zone sync completed")

            for zone in enabled_zones:
                if not zone.get("records"):
                    continue

                for record in zone["records"]:

                    if not record.get("needs_update"):
                        try:
                            if (
                                record["record_type"] == RecordType.A
                                and self.network.ipv4_address
                            ):
                                self.database.update_ip_address(
                                    record_id=record["id"],
                                    ip_address=self.network.ipv4_address,
                                    changed=False,
                                )
                            elif (
                                record["record_type"] == RecordType.AAAA
                                and self.network.ipv6_address
                            ):
                                self.database.update_ip_address(
                                    record_id=record["id"],
                                    ip_address=self.network.ipv6_address,
                                    changed=False,
                                )
                        except DatabaseError as e:
                            self.logger.warning(
                                f"Failed to update last_checked_at for "
                                f"'{record['record_name']}': {e}"
                            )
                        continue

                    old_ip = record.get("old_ip")
                    new_ip = record.get("new_ip")

                    try:
                        if not record.get("provider_record_id"):
                            self.logger.error(
                                f"Record '{record['record_name']}' still missing "
                                f"provider_record_id after sync - skipping"
                            )
                            raise APIError("Missing provider_record_id after sync")

                        provider_update_success = self.update_provider_record(
                            record, new_ip
                        )

                        if not provider_update_success:
                            raise APIError("Provider API update failed")

                        self.database.update_ip_address(
                            record_id=record["id"], ip_address=new_ip, changed=True
                        )

                        self.database.log_dns_update(
                            record_id=record["id"],
                            old_ip=old_ip,
                            new_ip=new_ip,
                            status=UpdateStatus.SUCCESS,
                        )

                        updates_succeeded += 1
                        self.logger.info(
                            f"Updated '{record['record_name']}' "
                            f"({record['record_type']}): "
                            f"{old_ip} {LOG_SYMBOLS['ARROW']} {new_ip}"
                        )

                    except (APIError, RecordNotFoundError) as e:
                        updates_failed += 1
                        error_msg = str(e)
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
                            self.logger.error(
                                f"Failed to log update failure: {log_error}"
                            )
                    except DatabaseError as e:
                        updates_failed += 1
                        self.logger.error(
                            f"Database error updating '{record['record_name']}': {e}"
                        )
                    except Exception as e:
                        updates_failed += 1
                        self.logger.error(
                            f"Unexpected error updating '{record['record_name']}': {e}"
                        )

            if updates_succeeded > 0 or updates_failed > 0:
                self.logger.info(
                    f"Database updates: {updates_succeeded} succeeded, "
                    f"{updates_failed} failed"
                )

            self.logger.debug("Updates saved successfully")
            return True

        except (DatabaseError, APIError) as e:
            self.logger.error(f"Failed to save updates: {e}")
            return False
        except Exception as e:
            self.logger.error(f"Unexpected error saving updates: {e}")
            return False


    def update_provider_record(
        self, record: Dict[str, Any], new_ip: str
    ) -> bool:
        """Update single DNS record in provider with orphan detection.

        Args:
            record: Record dictionary with provider_record_id and zone_id.
            new_ip: New IP address to set.

        Returns:
            True if update successful, False otherwise.
        """
        try:
            if not record.get("provider_record_id"):
                self.logger.error(
                    f"Record '{record['record_name']}' missing provider_record_id"
                )
                return False

            zone_row = self.database.get_zone_by_id(record["zone_id"])
            if not zone_row:
                self.logger.error(f"Zone {record['zone_id']} not found")
                return False

            zone = dict(zone_row)

            if not zone.get("provider_zone_id"):
                self.logger.error(f"Zone {record['zone_id']} has no provider_zone_id")
                return False

            client = self.sync_service.get_provider_client(zone["id"])
            if not client:
                self.logger.error(
                    f"Cannot get API client for zone {zone['zone_name']}"
                )
                return False

            try:
                success = client.update_record(
                    zone_id=zone["provider_zone_id"],
                    record_id=record["provider_record_id"],
                    content=new_ip,
                    ttl=record.get("ttl", self.config.dns_default_ttl),
                )

                if success:
                    self.logger.debug(
                        f"Provider API confirmed update for '{record['record_name']}' "
                        f"({record['record_type']}) to {new_ip}"
                    )

                    if self.config.daemon_sync_checks:
                        self.database.update_record(
                            record["id"],
                            sync_status=SyncStatus.SYNCED,
                            last_synced_at=time.time(),
                        )

                    return True
                else:
                    if self.config.daemon_sync_checks:
                        self.logger.warning(
                            f"Update failed for '{record['record_name']}' - "
                            f"verifying record exists at provider"
                        )

                        try:
                            provider_records = client.get_zone_records(
                                zone["provider_zone_id"]
                            )
                            if provider_records is not None:
                                record_exists = any(
                                    pr["id"] == record["provider_record_id"]
                                    for pr in provider_records
                                )

                                if not record_exists:
                                    self.logger.warning(
                                        f"Record '{record['record_name']}' not found "
                                        f"at provider (orphaned) - clearing "
                                        f"provider_record_id for re-sync"
                                    )

                                    self.database.update_record(
                                        record["id"],
                                        provider_record_id=None,
                                        sync_status=SyncStatus.ORPHANED,
                                    )

                                    self.logger.info(
                                        f"Record '{record['record_name']}' marked "
                                        f"as orphaned - will be recreated in next cycle"
                                    )
                        except APIError as verify_error:
                            self.logger.debug(
                                f"Could not verify record existence: {verify_error}"
                            )

                    return False

            except RecordNotFoundError:
                if self.config.daemon_sync_checks:
                    self.logger.warning(
                        f"Record '{record['record_name']}' not found at provider "
                        f"(orphaned) - clearing provider_record_id for re-sync"
                    )

                    self.database.update_record(
                        record["id"],
                        provider_record_id=None,
                        sync_status=SyncStatus.ORPHANED,
                    )

                    self.logger.info(
                        f"Record '{record['record_name']}' marked as orphaned - "
                        f"will be recreated in next cycle"
                    )

                    return False
                else:
                    self.logger.error(
                        f"Provider returned RECORD_NOT_FOUND for "
                        f"'{record['record_name']}' - enable daemon_sync_checks "
                        f"for automatic recovery"
                    )
                    return False

        except DynDNSException as e:
            self.logger.error(
                f"Failed to update provider record '{record['record_name']}': {e}"
            )
            return False
