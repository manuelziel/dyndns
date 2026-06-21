#!/usr/bin/env python3
"""Main application module containing core business logic.

This module provides the Application class which acts as an orchestrator
for the DynDNS daemon. It coordinates data loading, delegates logic to
services, and manages the daemon cycle lifecycle.

Author: Manuel Ziel
License: MIT
"""

################################################################################
# IMPORTS & DEPENDENCIES
################################################################################

# Standard Imports
import time
import threading
from typing import Optional, Dict, List, Any

# Local Imports
from .utils.colors import LOG_SYMBOLS
from .core.exceptions import (
    DatabaseError,
    NetworkError,
    APIError,
)
from .core.constants import DaemonDefaults
from .network import NetworkData
from .services.sync_service import SyncService
from .services.update_service import UpdateService


################################################################################
# APPLICATION CLASS - Core Business Logic
################################################################################

class Application:
    """Main application class for DynDNS daemon cycle management.

    Provides orchestration for IP detection, DNS record synchronization,
    and automatic DNS updates by delegating to specialized services.

    Attributes:
        config: Configuration object from ConfigManager.
        logger: Logger instance from LoggerManager.
        running: Whether the application is currently running.
        database: Database instance for zone and record storage.
        network: NetworkData instance for IP detection.
        sync_service: Service for provider API reconciliation.
        update_service: Service for IP comparisons and DNS updates.
        enabled_zones: Cached list of zones being processed in the current cycle.
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
        
        self.sync_service = SyncService(
            config=self.config,
            database=self.database,
            network=self.network,
            logger=self.logger,
        )
        
        self.update_service = UpdateService(
            config=self.config,
            database=self.database,
            network=self.network,
            sync_service=self.sync_service,
            logger=self.logger,
        )
        
        self.enabled_zones = None
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

            if not self.update_service.process_records(self.enabled_zones):
                self.logger.warning("Data processing failed")
                self._reset_state()
                return False

            if not self.update_service.save_updates(self.enabled_zones):
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

        max_wait = DaemonDefaults.STOP_TIMEOUT
        wait_count = 0

        while self.running and wait_count < max_wait:
            self.logger.debug(
                f"Waiting for application to stop... ({wait_count}/{max_wait})"
            )
            time.sleep(DaemonDefaults.STOP_CHECK_INTERVAL)
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

            if changes["ipv4_changed"]:
                self.logger.info(
                    f"IPv4 address changed: {self.network.last_ipv4_address} "
                    f"{LOG_SYMBOLS['ARROW']} {ipv4}"
                )
            else:
                self.logger.debug(f"IPv4 address unchanged: {ipv4}")

            if changes["ipv6_changed"]:
                self.logger.info(
                    f"IPv6 address changed: {self.network.last_ipv6_address} "
                    f"{LOG_SYMBOLS['ARROW']} {ipv6}"
                )
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
                records_from_db = self.database.get_records_by_zone(
                    zone["id"], enabled_only=True
                )
                zone["records"] = [dict(record) for record in records_from_db]

                for record in zone["records"]:
                    current_ip = self.database.get_ip_address(record["id"])
                    record["current_ip"] = dict(current_ip) if current_ip else None
                    total_records += 1

                self.logger.debug(
                    f"Loaded zone '{zone['zone_name']}' with "
                    f"{len(zone['records'])} records"
                )

            self.logger.debug(
                f"Loaded {len(self.enabled_zones)} zones with {total_records} total records"
            )
            self.logger.debug("Data loading completed")
            return True

        except (NetworkError, DatabaseError) as e:
            self.logger.error(f"Network check or database load failed: {e}")
            return False


    def _finalize_cycle(self) -> bool:
        """Save IP state and cleanup temporary data.

        Stores current IPs as last-known values for next cycle comparison.

        Returns:
            True if finalization completed successfully, False otherwise.
        """
        try:
            self.network.save_current_as_last()
            self.logger.debug(
                f"Saved IPs for next cycle: IPv4={self.network.last_ipv4_address}, "
                f"IPv6={self.network.last_ipv6_address}"
            )

            self.enabled_zones = None

            self.logger.debug("Cycle finalized")
            return True

        except (NetworkError, DatabaseError) as e:
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
            self.logger.error(f"Unexpected error resetting state: {e}")