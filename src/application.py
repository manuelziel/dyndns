#!/usr/bin/env python3
"""Main application module containing core business logic.

This module provides the Application class which contains the main business
logic for the IONOS DynDNS daemon. It handles IP detection, DNS record
synchronization, and update operations.

Typical usage:
    >>> app = Application(config, logger)
    >>> app.run_cycle()  # Single daemon cycle
    >>> # Or for interactive mode:
    >>> app.execute_update(force=True)

Author: Manuel Ziel
License: MIT
"""

################################################################################
# IMPORTS & DEPENDENCIES
################################################################################

# Standard library imports
import time
import threading
from typing import Optional, Dict, List, Any

# Local imports
from .core.exceptions import (
    DatabaseError,
    NetworkError,
    APIError,
    RecordNotFoundError
)
from .core.constants import SyncStatus, UpdateStatus, RecordType

# Local imports - Modules
from .cli_helpers import get_placeholder_ip
from .network import NetworkData
from .api import ProviderDNSClient
from .utils.colors import LOG_SYMBOLS

################################################################################
# APPLICATION CLASS - Core Business Logic
################################################################################

class Application:
    """Main application class for DynDNS daemon cycle management.

    Provides IP detection, DNS record synchronization with IONOS provider,
    and automatic DNS updates when IP addresses change.

    Attributes:
        config: Configuration object from ConfigManager.
        logger: Logger instance from LoggerManager.
        running: Whether the application is currently running.
        database: Database instance for zone and record storage.
        network: NetworkData instance for IP detection.
    """

    def __init__(self, config: Any, logger: Any) -> None:
        """Initialize application with configuration and logger.

        Args:
            config: Configuration object from ConfigManager.
            logger: Logger instance from LoggerManager.
        """
        self.config = config
        self.logger = logger
        self.running = False
        self._stop_event = threading.Event()
        self.database = config.db
        self.network = NetworkData(config=config, logger=logger)
        self.enabled_zones = None
        self._provider_clients = {}
        
        self.logger.info("Application initialized")
            
    def run_cycle(self) -> bool:
        """Execute one daemon cycle (load → process → save → finalize).

        Returns:
            True if cycle completed successfully, False otherwise.
        """
        try:
            self.logger.debug("Starting application cycle...")
            
            if not self._load_data():
                self.logger.warning("Data loading failed")
                self._reset_state()
                return False
            
            if not self._process_records():
                self.logger.warning("Data processing failed") 
                self._reset_state()
                return False
            
            if not self._save_updates():
                self.logger.warning("Saving updates failed")
                self._reset_state()
                return False
            
            if not self._finalize_cycle():
                self.logger.warning("Finalization failed")
                self._reset_state()
                return False
            
            self.logger.debug("Application cycle completed successfully")
            return True
            
        except (DatabaseError, NetworkError, APIError) as e:
            self.logger.error(f"Application cycle failed: {e}")
            self._reset_state()
            return False
        except Exception as e:
            self.logger.error(f"Unexpected error in application cycle: {e}")
            self._reset_state()
            return False

    ################################################################################
    # PUBLIC INTERFACE - Lifecycle Management
    ################################################################################

    def stop(self) -> bool:
        """Stop application gracefully with timeout.

        Waits up to 30 seconds for pending operations to complete.

        Returns:
            True if stopped gracefully, False if timeout reached.
        """
        self.logger.info("Stopping application...")
        self._stop_event.set()
        self.running = False
        
        max_wait = 30
        wait_count = 0
        
        while self.running and wait_count < max_wait:
            self.logger.debug(f"Waiting for application to stop... ({wait_count}/{max_wait})")
            time.sleep(1)
            wait_count += 1
            
        if wait_count >= max_wait:
            self.logger.warning("Application did not stop gracefully within timeout")
            return False
        
        self.logger.info("Application stopped successfully")
        return True

    def cleanup(self) -> None:
        """Cleanup resources (database connections, etc.).

        Stops the application if running and closes all open connections.
        """
        self.logger.info("Cleaning up application resources...")
        
        try:
            if self.running:
                self.stop()

            if self.database:
                self.database.close()
                self.logger.debug("Database connections closed")
            
            self.logger.info("Application cleanup completed")
            
        except Exception as e:
            self.logger.error(f"Error during application cleanup: {e}")
            
    ################################################################################
    # PUBLIC INTERFACE - Status and Configuration
    ################################################################################

    def is_running(self) -> bool:
        """Return current running state.

        Returns:
            True if application is running, False otherwise.
        """
        return self.running

    ################################################################################
    # PRIVATE METHODS - Cycle Pipeline
    ################################################################################

    def _load_data(self) -> bool:
        """Load current IP addresses and database state.

        Detects current public IP addresses and loads enabled zones with
        their records from the database.

        Returns:
            True if data loaded successfully, False otherwise.
        """
        try:
            self.logger.debug("Checking network and IP addresses...")
            
            ipv4, ipv6 = self.network.load_current_ip_addresses()
            
            if ipv4:
                self.logger.debug(f"IPv4 address detected: {ipv4}")
            else:
                self.logger.warning("No IPv4 address detected")
                
            if ipv6:
                self.logger.debug(f"IPv6 address detected: {ipv6}")
            else:
                self.logger.warning("No IPv6 address detected")
            
            if not ipv4 and not ipv6:
                self.logger.error("No IP addresses detected - cannot proceed")
                return False
            
            changes = self.network.has_ip_changed()
            
            if changes['ipv4_changed']:
                self.logger.info(f"IPv4 address changed: {self.network.last_ipv4_address} {LOG_SYMBOLS['ARROW']} {ipv4}")
            else:
                self.logger.debug(f"IPv4 address unchanged: {ipv4}")
                
            if changes['ipv6_changed']:
                self.logger.info(f"IPv6 address changed: {self.network.last_ipv6_address} {LOG_SYMBOLS['ARROW']} {ipv6}")
            else:
                self.logger.debug(f"IPv6 address unchanged: {ipv6}")
            
            self.logger.debug("Loading database state...")
            zones_from_db = self.database.get_all_enabled_zones()
            
            if not zones_from_db:
                self.logger.warning("No enabled zones found in database")
                return True
            
            self.enabled_zones = [dict(zone) for zone in zones_from_db]
            
            total_records = 0
            for zone in self.enabled_zones:
                records_from_db = self.database.get_records_by_zone(zone['id'], enabled_only=True)
                zone['records'] = [dict(record) for record in records_from_db]
                
                for record in zone['records']:
                    current_ip = self.database.get_ip_address(record['id'])
                    record['current_ip'] = dict(current_ip) if current_ip else None
                    total_records += 1
                
                self.logger.debug(f"Loaded zone '{zone['zone_name']}' with {len(zone['records'])} records")
            
            self.logger.debug(f"Loaded {len(self.enabled_zones)} zones with {total_records} total records")
            self.logger.debug("Data loading completed")
            return True
            
        except Exception as e:
            self.logger.error(f"Network check or database load failed: {e}")
            return False
    
    def _process_records(self) -> bool:
        """Compare detected IPs with database records.

        Determines which records need updates based on IP changes.

        Returns:
            True if processing completed successfully, False otherwise.
        """
        try:
            if not self.enabled_zones:
                self.logger.debug("No zones to process")
                return True
            
            self.logger.debug("Processing DNS records...")
            
            total_records = 0
            records_need_update = 0
            new_ip = None
            old_ip = None
            
            for zone in self.enabled_zones:
                if not zone.get('records'):
                    continue
                
                self.logger.debug(f"Processing zone '{zone['zone_name']}' with {len(zone['records'])} records")
                
                for record in zone['records']:
                    total_records += 1
                    
                    if record['record_type'] == RecordType.A:
                        new_ip = self.network.ipv4_address
                        if not new_ip:
                            self.logger.debug(f"Skipping A record '{record['record_name']}' - no IPv4 detected")
                            continue
                            
                    elif record['record_type'] == RecordType.AAAA:
                        new_ip = self.network.ipv6_address
                        if not new_ip:
                            self.logger.debug(f"Skipping AAAA record '{record['record_name']}' - no IPv6 detected")
                            continue
                    else:
                        self.logger.debug(f"Skipping record type '{record['record_type']}' for '{record['record_name']}'")
                        continue
                    
                    old_ip = record['current_ip'].get('ip_address') if record.get('current_ip') else None
                    
                    if not record.get('provider_record_id'):
                        self.logger.warning(
                            f"Record '{record['record_name']}' ({record['record_type']}) "
                            f"missing provider_record_id - will re-sync and update"
                        )
                        record['needs_update'] = True
                        record['old_ip'] = old_ip
                        record['new_ip'] = new_ip
                        records_need_update += 1
                        
                        if old_ip:
                            self.logger.info(
                                f"Record '{record['record_name']}' ({record['record_type']}) "
                                f"will be recreated: {old_ip} {LOG_SYMBOLS['ARROW']} {new_ip}"
                            )
                        else:
                            self.logger.info(
                                f"Record '{record['record_name']}' ({record['record_type']}) "
                                f"will be created: {LOG_SYMBOLS['ARROW']} {new_ip}"
                            )
                        continue
                    
                    if old_ip != new_ip:
                        record['needs_update'] = True
                        record['old_ip'] = old_ip
                        record['new_ip'] = new_ip
                        records_need_update += 1
                        
                        if old_ip:
                            self.logger.info(
                                f"Record '{record['record_name']}' ({record['record_type']}) "
                                f"needs update: {old_ip} {LOG_SYMBOLS['ARROW']} {new_ip}"
                            )
                        else:
                            self.logger.info(
                                f"Record '{record['record_name']}' ({record['record_type']}) "
                                f"needs initial IP: {LOG_SYMBOLS['ARROW']} {new_ip}"
                            )
                    else:
                        record['needs_update'] = False
                        self.logger.debug(
                            f"Record '{record['record_name']}' ({record['record_type']}) "
                            f"unchanged: {old_ip}"
                        )
            
            if records_need_update > 0:
                self.logger.info(f"Found {records_need_update}/{total_records} records requiring updates")
            else:
                self.logger.debug(f"All {total_records} records up-to-date")
            
            self.logger.debug("Data processing completed")
            return True
            
        except Exception as e:
            self.logger.error(f"Data processing failed: {e}")
            return False
    
    def _save_updates(self) -> bool:
        """Update database and provider DNS with new IPs.

        Synchronizes zones if needed and pushes IP updates to the provider API.

        Returns:
            True if all updates completed successfully, False otherwise.
        """
        try:
            if not self.enabled_zones:
                self.logger.debug("No zones to save")
                return True
            
            self.logger.debug("Saving results to database...")
            
            updates_succeeded = 0
            updates_failed = 0
            old_ip = None
            new_ip = None
            error_msg = None
            
            zones_to_sync = self._collect_zones_needing_sync()
            
            if zones_to_sync:
                if self.config.daemon_sync_checks:
                    self.logger.info(
                        f"Reconciliation: Syncing {len(zones_to_sync)} zone(s) to restore "
                        f"missing provider_record_ids"
                    )
                else:
                    self.logger.debug(f"Need to sync {len(zones_to_sync)} zone(s) before updates")
                
                self._sync_zones_and_refresh_records(zones_to_sync)
                
                if self.config.daemon_sync_checks:
                    self.logger.info("Reconciliation: Zone sync completed")
            
            for zone in self.enabled_zones:
                if not zone.get('records'):
                    continue
                
                for record in zone['records']:
                    
                    if not record.get('needs_update'):
                        try:
                            if record['record_type'] == RecordType.A and self.network.ipv4_address:
                                self.database.update_ip_address(
                                    record_id=record['id'],
                                    ip_address=self.network.ipv4_address,
                                    changed=False
                                )
                            elif record['record_type'] == RecordType.AAAA and self.network.ipv6_address:
                                self.database.update_ip_address(
                                    record_id=record['id'],
                                    ip_address=self.network.ipv6_address,
                                    changed=False
                                )
                        except Exception as e:
                            self.logger.warning(f"Failed to update last_checked_at for '{record['record_name']}': {e}")
                        continue
                    
                    old_ip = record.get('old_ip')
                    new_ip = record.get('new_ip')
                    
                    try:
                        if not record.get('provider_record_id'):
                            self.logger.error(
                                f"Record '{record['record_name']}' still missing provider_record_id "
                                f"after sync - skipping"
                            )
                            raise APIError("Missing provider_record_id after sync")
                        
                        provider_update_success = self._update_provider_record(record, new_ip)
                        
                        if not provider_update_success:
                            raise APIError("Provider API update failed")
                        
                        self.database.update_ip_address(
                            record_id=record['id'],
                            ip_address=new_ip,
                            changed=True
                        )
                        
                        self.database.log_dns_update(
                            record_id=record['id'],
                            old_ip=old_ip,
                            new_ip=new_ip,
                            status=UpdateStatus.SUCCESS
                        )
                        
                        updates_succeeded += 1
                        self.logger.info(f"{LOG_SYMBOLS['SUCCESS']} Updated '{record['record_name']}' ({record['record_type']}): {old_ip} {LOG_SYMBOLS['ARROW']} {new_ip}")
                        
                    except (APIError, RecordNotFoundError) as e:
                        updates_failed += 1
                        error_msg = str(e)
                        self.logger.error(f"{LOG_SYMBOLS['ERROR']} Failed to update '{record['record_name']}' ({record['record_type']}): {error_msg}")
                        
                        try:
                            self.database.log_dns_update(
                                record_id=record['id'],
                                old_ip=old_ip,
                                new_ip=new_ip,
                                status=UpdateStatus.FAILED,
                                error_message=error_msg
                            )
                        except DatabaseError as log_error:
                            self.logger.error(f"Failed to log update failure: {log_error}")
                    except Exception as e:
                        updates_failed += 1
                        self.logger.error(f"{LOG_SYMBOLS['ERROR']} Unexpected error updating '{record['record_name']}': {e}")
            
            if updates_succeeded > 0 or updates_failed > 0:
                self.logger.info(f"Database updates: {updates_succeeded} succeeded, {updates_failed} failed")
            
            self.logger.debug("Updates saved successfully")
            return True
            
        except (DatabaseError, APIError) as e:
            self.logger.error(f"Failed to save updates: {e}")
            return False
        except Exception as e:
            self.logger.error(f"Unexpected error saving updates: {e}")
            return False
    
    def _finalize_cycle(self) -> bool:
        """Save IP state and cleanup temporary data.

        Stores current IPs as last-known values for next cycle comparison.

        Returns:
            True if finalization completed successfully, False otherwise.
        """
        try:
            self.network.save_current_as_last()
            self.logger.debug(f"Saved IPs for next cycle: IPv4={self.network.last_ipv4_address}, IPv6={self.network.last_ipv6_address}")
            
            self.enabled_zones = None
            
            self.logger.debug("Cycle finalized")
            return True
            
        except Exception as e:
            self.logger.error(f"Finalization failed: {e}")
            return False
    
    def _reset_state(self) -> None:
        """Reset application state after errors.

        Clears cached zones and records to ensure clean state for next cycle.
        """
        try:
            self.enabled_zones = None
            
            self.logger.debug("Application state reset")
            
        except Exception as e:
            self.logger.error(f"Failed to reset state: {e}")

    ################################################################################
    # PRIVATE METHODS - Provider API Integration
    ################################################################################
    
    def _collect_zones_needing_sync(self) -> set:
        """Collect zones that need sync due to missing provider_record_ids.

        Returns:
            Set of zone IDs that need syncing with provider.
        """
        zones_to_sync = set()
        
        for zone in self.enabled_zones:
            if not zone.get('records'):
                continue
            
            for record in zone['records']:
                if record.get('needs_update') and not record.get('provider_record_id'):
                    zones_to_sync.add(zone['id'])
                    
                    if self.config.daemon_sync_checks:
                        self.logger.info(
                            f"Reconciliation: Record '{record['record_name']}' missing "
                            f"provider_record_id - zone {zone['zone_name']} will be synced"
                        )
                    break
        
        return zones_to_sync
    
    def _sync_zones_and_refresh_records(self, zone_ids: set) -> None:
        """Sync zones and refresh record data from database.

        Args:
            zone_ids: Set of zone IDs to synchronize.
        """
        for zone_id in zone_ids:
            if not self._sync_provider_ids(zone_id):
                if self.config.daemon_sync_checks:
                    self.logger.error(f"Reconciliation failed for zone {zone_id}")
                else:
                    self.logger.error(f"Failed to sync zone {zone_id}")
                continue
            
            for zone in self.enabled_zones:
                if zone['id'] == zone_id:
                    for record in zone['records']:
                        record_row = self.database.get_record_by_id(record['id'])
                        if record_row:
                            record.update(dict(record_row))
                            
                            if self.config.daemon_sync_checks:
                                self.logger.debug(
                                    f"Reconciliation: Refreshed record '{record['record_name']}' "
                                    f"(provider_record_id: {record.get('provider_record_id', 'still missing')})"
                                )
                    break
    
    def _get_provider_client(self, zone_id: int) -> Optional[ProviderDNSClient]:
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
                api_key=api_key,
                config=self.config,
                logger=self.logger
            )
            self._provider_clients[zone_id] = client
            
            self.logger.debug(f"Created provider API client for zone {zone_id}")
            return client
            
        except Exception as e:
            self.logger.error(f"Failed to create provider client for zone {zone_id}: {e}")
            return None
    
    def _sync_provider_ids(self, zone_id: Optional[int] = None) -> bool:
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
                    self.logger.error(f"Zone with ID {zone_id} not found in database")
                    return False
                zones = [zone]
            else:
                zones = self.database.get_all_enabled_zones()
            
            if not zones:
                self.logger.warning("No zones to synchronize")
                return False
            
            self.logger.info(f"Synchronizing provider IDs for {len(zones)} zone(s)...")
            
            for zone in zones:
                self.logger.debug(f"════════ Syncing zone '{zone['zone_name']}' (ID: {zone['id']}) ════════")
                try:
                    self.logger.debug(f"{LOG_SYMBOLS['ARROW']} Getting provider API client for zone {zone['id']}")
                    client = self._get_provider_client(zone['id'])
                    if not client:
                        self.logger.error(f"{LOG_SYMBOLS['ERROR']} Cannot sync zone {zone['zone_name']} - no API client")
                        continue
                    self.logger.debug(f"{LOG_SYMBOLS['SUCCESS']} API client created successfully")
                    
                    self.logger.debug(f"{LOG_SYMBOLS['ARROW']} Fetching zones from provider...")
                    provider_zones = client.get_zones()
                    if not provider_zones:
                        self.logger.error(f"{LOG_SYMBOLS['ERROR']} Failed to fetch zones from provider for {zone['zone_name']}")
                        continue
                    self.logger.debug(f"{LOG_SYMBOLS['SUCCESS']} Retrieved {len(provider_zones)} zones from provider")
                    
                    self.logger.debug(f"{LOG_SYMBOLS['ARROW']} Finding zone '{zone['zone_name']}' in provider zones...")
                    provider_zone = next(
                        (pz for pz in provider_zones if pz['name'] == zone['zone_name']),
                        None
                    )
                    
                    if not provider_zone:
                        self.logger.error(f"{LOG_SYMBOLS['ERROR']} Zone '{zone['zone_name']}' not found in provider")
                        self.logger.error(f"Available zones: {[pz['name'] for pz in provider_zones]}")
                        continue
                    
                    provider_zone_id = provider_zone['id']
                    self.logger.debug(f"{LOG_SYMBOLS['SUCCESS']} Found zone with provider ID: {provider_zone_id}")
                    
                    self.logger.debug(f"{LOG_SYMBOLS['ARROW']} Updating database with provider_zone_id...")
                    self.database.update_zone(zone['id'], provider_zone_id=provider_zone_id)
                    self.logger.debug(f"{LOG_SYMBOLS['SUCCESS']} Database updated with provider zone ID")
                    
                    self.logger.debug(f"{LOG_SYMBOLS['ARROW']} Fetching records for zone ID: {provider_zone_id}")
                    provider_records = client.get_zone_records(provider_zone_id)
                    if provider_records is None:
                        self.logger.error(f"{LOG_SYMBOLS['ERROR']} Failed to fetch records for zone '{zone['zone_name']}'")
                        continue
                    
                    self.logger.debug(f"{LOG_SYMBOLS['SUCCESS']} Retrieved {len(provider_records)} records from provider")
                    
                    self.logger.debug(f"{LOG_SYMBOLS['ARROW']} Loading database records for zone...")
                    db_records = self.database.get_records_by_zone(zone['id'], enabled_only=False)
                    self.logger.debug(f"{LOG_SYMBOLS['SUCCESS']} Retrieved {len(db_records)} records from database")
                    
                    self.logger.debug(f"{LOG_SYMBOLS['ARROW']} Matching {len(db_records)} DB records with {len(provider_records)} provider records...")
                    
                    matched_count = 0
                    unmatched_count = 0
                    missing_records = []
                    
                    for db_record in db_records:
                        db_name = db_record['record_name'].rstrip('.')
                        
                        self.logger.debug(f"  Matching DB record: '{db_name}' ({db_record['record_type']})")
                        
                        provider_record = next(
                            (pr for pr in provider_records 
                             if pr['name'].rstrip('.') == db_name
                             and pr['type'] == db_record['record_type']),
                            None
                        )
                        
                        if provider_record:
                            rows_updated = self.database.update_record_provider_id(
                                db_record['id'],
                                provider_record['id']
                            )
                            matched_count += 1
                            self.logger.debug(
                                f"  {LOG_SYMBOLS['SUCCESS']} Matched '{db_record['record_name']}' ({db_record['record_type']}) "
                                f"{LOG_SYMBOLS['ARROW']} provider ID: {provider_record['id']} (updated: {rows_updated} rows)"
                            )
                        else:
                            unmatched_count += 1
                            missing_records.append(db_record)
                            self.logger.warning(
                                f"  {LOG_SYMBOLS['ERROR']} Record '{db_record['record_name']}' ({db_record['record_type']}) "
                                f"not found in provider"
                            )
                    
                    self.logger.debug(f"{LOG_SYMBOLS['SUCCESS']} Matching complete: {matched_count} matched, {unmatched_count} not found")
                    
                    if missing_records:
                        self.logger.info(f"Attempting to create {len(missing_records)} missing record(s)...")
                        
                        zone_dict = dict(zone)
                        zone_dict['provider_zone_id'] = provider_zone_id
                        
                        created_count = self._create_missing_records(client, zone_dict, missing_records)
                        
                        if created_count > 0:
                            self.logger.debug(f"Re-fetching provider records to get new IDs...")
                            provider_records = client.get_zone_records(provider_zone_id)
                            
                            if provider_records:
                                self.logger.debug(f"Re-matching {len(missing_records)} newly created records...")
                                
                                for db_record_row in missing_records:
                                    db_record = dict(db_record_row)
                                    db_name = db_record['record_name'].rstrip('.')
                                    
                                    provider_record = next(
                                        (pr for pr in provider_records 
                                         if pr['name'].rstrip('.') == db_name
                                         and pr['type'] == db_record['record_type']),
                                        None
                                    )
                                    
                                    if provider_record:
                                        rows_updated = self.database.update_record_provider_id(
                                            db_record['id'],
                                            provider_record['id']
                                        )
                                        matched_count += 1
                                        self.logger.debug(
                                            f"  {LOG_SYMBOLS['SUCCESS']} Matched newly created '{db_record['record_name']}' "
                                            f"({db_record['record_type']}) {LOG_SYMBOLS['ARROW']} provider ID: {provider_record['id']}"
                                        )
                                    else:
                                        self.logger.warning(
                                            f"  {LOG_SYMBOLS['ERROR']} Newly created record '{db_record['record_name']}' "
                                            f"still not found in provider"
                                        )
                    
                    self.logger.info(f"Successfully synced provider IDs for zone '{zone['zone_name']}'")
                    self.logger.debug(f"════════════════════════════════════════════════════════════")
                    
                except Exception as e:
                    self.logger.error(f"Failed to sync zone '{zone.get('zone_name', 'unknown')}': {e}")
                    continue
            
            self.logger.info("Provider ID synchronization completed")
            return True
            
        except Exception as e:
            self.logger.error(f"Provider ID synchronization failed: {e}")
            return False
    
    def _create_missing_records(self, client: ProviderDNSClient, zone: Dict[str, Any], missing_records: List[Dict[str, Any]]) -> int:
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
            self.logger.info(f"Creating {len(missing_records)} missing record(s) in provider...")
            
            api_records = []
            for db_record_row in missing_records:
                db_record = dict(db_record_row)
                
                try:
                    if db_record['record_type'] == RecordType.A:
                        content = self.network.ipv4_address or get_placeholder_ip(RecordType.A)
                    elif db_record['record_type'] == RecordType.AAAA:
                        content = self.network.ipv6_address or get_placeholder_ip(RecordType.AAAA)
                    else:
                        self.logger.warning(f"Unsupported record type '{db_record['record_type']}' - skipping")
                        continue
                except ValueError as e:
                    self.logger.error(f"Invalid record type for '{db_record['record_name']}': {e}")
                    continue
                
                api_record = {
                    "name": db_record['record_name'],
                    "type": db_record['record_type'],
                    "content": content,
                    "ttl": db_record.get('ttl', self.config.dns_default_ttl),
                    "disabled": not db_record.get('enabled', True)
                }
                api_records.append(api_record)
                
                self.logger.debug(
                    f"  Prepared record: '{api_record['name']}' ({api_record['type']}) "
                    f"{LOG_SYMBOLS['ARROW']} {content}"
                )
            
            if not api_records:
                self.logger.warning("No valid records to create")
                return 0
            
            success = client.create_records(
                zone_id=zone['provider_zone_id'],
                records=api_records
            )
            
            if success:
                self.logger.info(f"{LOG_SYMBOLS['SUCCESS']} Successfully created {len(api_records)} record(s)")
                return len(api_records)
            else:
                self.logger.error(f"{LOG_SYMBOLS['ERROR']} Failed to create records in provider")
                return 0
                
        except Exception as e:
            self.logger.error(f"Failed to create missing records: {e}")
            return 0
    
    def _update_provider_record(self, record: Dict[str, Any], new_ip: str) -> bool:
        """Update single DNS record in provider with orphan detection.

        Args:
            record: Record dictionary with provider_record_id and zone_id.
            new_ip: New IP address to set.

        Returns:
            True if update successful, False otherwise.
        """
        try:
            if not record.get('provider_record_id'):
                self.logger.error(f"Record '{record['record_name']}' missing provider_record_id")
                return False
            
            zone_row = self.database.get_zone_by_id(record['zone_id'])
            if not zone_row:
                self.logger.error(f"Zone {record['zone_id']} not found")
                return False
            
            zone = dict(zone_row)
            
            if not zone.get('provider_zone_id'):
                self.logger.error(f"Zone {record['zone_id']} has no provider_zone_id")
                return False
            
            client = self._get_provider_client(zone['id'])
            if not client:
                self.logger.error(f"Cannot get API client for zone {zone['zone_name']}")
                return False
            
            try:
                success = client.update_record(
                    zone_id=zone['provider_zone_id'],
                    record_id=record['provider_record_id'],
                    content=new_ip,
                    ttl=record.get('ttl', self.config.dns_default_ttl)
                )
                
                if success:
                    self.logger.debug(
                        f"Provider API confirmed update for '{record['record_name']}' "
                        f"({record['record_type']}) to {new_ip}"
                    )
                    
                    if self.config.daemon_sync_checks:
                        self.database.update_record(
                            record['id'],
                            sync_status=SyncStatus.SYNCED,
                            last_synced_at=time.time()
                        )
                    
                    return True
                else:
                    if self.config.daemon_sync_checks:
                        self.logger.warning(
                            f"Update failed for '{record['record_name']}' - verifying record exists at provider"
                        )
                        
                        try:
                            provider_records = client.get_zone_records(zone['provider_zone_id'])
                            if provider_records is not None:
                                record_exists = any(
                                    pr['id'] == record['provider_record_id']
                                    for pr in provider_records
                                )
                                
                                if not record_exists:
                                    self.logger.warning(
                                        f"Record '{record['record_name']}' not found at provider (orphaned) - "
                                        f"clearing provider_record_id for re-sync"
                                    )
                                    
                                    self.database.update_record(
                                        record['id'],
                                        provider_record_id=None,
                                        sync_status=SyncStatus.ORPHANED
                                    )
                                    
                                    self.logger.info(
                                        f"Record '{record['record_name']}' marked as orphaned - "
                                        f"will be recreated in next cycle"
                                    )
                        except Exception as verify_error:
                            self.logger.debug(f"Could not verify record existence: {verify_error}")
                    
                    return False
                    
            except RecordNotFoundError:
                if self.config.daemon_sync_checks:
                    self.logger.warning(
                        f"Record '{record['record_name']}' not found at provider (orphaned) - "
                        f"clearing provider_record_id for re-sync"
                    )
                    
                    self.database.update_record(
                        record['id'],
                        provider_record_id=None,
                        sync_status=SyncStatus.ORPHANED
                    )
                    
                    self.logger.info(
                        f"Record '{record['record_name']}' marked as orphaned - "
                        f"will be recreated in next cycle"
                    )
                    
                    return False
                else:
                    self.logger.error(
                        f"Provider returned RECORD_NOT_FOUND for '{record['record_name']}' - "
                        f"enable daemon_sync_checks for automatic recovery"
                    )
                    return False
                    
        except Exception as e:
            self.logger.error(f"Failed to update provider record '{record['record_name']}': {e}")
            return False