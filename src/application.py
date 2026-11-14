#!/usr/bin/env python3
"""Main application orchestrator for DynDNS daemon and single-shot cycles.

Coordinates public IP detection, SQLite state loading, provider synchronization,
and DNS record updates by delegating domain work to ``SyncService`` and
``UpdateService``.

Author: Manuel Ziel
License: MIT
"""

################################################################################
# IMPORTS & DEPENDENCIES
################################################################################

import threading
import time
from typing import Any

from .core.constants import DaemonDefaults
from .core.exceptions import APIError, ConfigError, DatabaseError, NetworkError
from .core.logger import LoggerManager
from .network import NetworkData
from .services.sync_service import SyncService
from .services.update_service import UpdateService
from .utils.colors import LOG_SYMBOLS

################################################################################
# APPLICATION CLASS
################################################################################


class Application:
    """Main orchestrator for DynDNS IP detection and DNS update cycles.

    Attributes:
        config: ``ConfigManager`` instance.
        logger: Application logger instance.
        running: Whether a cycle is actively executing.
        database: ``Database`` instance for zone and record persistence.
        network: ``NetworkData`` instance for public IP probing.
        sync_service: ``SyncService`` for provider reconciliation.
        update_service: ``UpdateService`` for DNS update execution.
        enabled_zones: Cached enabled zone list for the active cycle.
    """

    def __init__(self, config: Any, logger: Any) -> None:
        """Initialize application services and verify database schema.

        Args:
            config: ``ConfigManager`` instance.
            logger: Logger instance from ``LoggerManager``.

        Raises:
            DatabaseError: If schema compatibility verification fails.
        """
        self.config = config
        self.logger = logger
        self.running = False
        self._stop_event = threading.Event()
        self._cycle_thread: threading.Thread | None = None
        self.database = config.db
        if not self.database.check_schema_compatibility():
            raise DatabaseError("Database schema validation or migration failed.")
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
        self.enabled_zones: list[dict[str, Any]] | None = None
        self._is_first_cycle = True
        self.logger.info("Application initialized")

    ############################################################################
    # PUBLIC INTERFACE - Cycle Execution & Lifecycle
    ############################################################################

    def run_cycle(self) -> bool:
        """Execute one full load -> process -> save -> finalize cycle.

        Returns:
            True if the cycle completed without error, False otherwise.
        """
        self.running = True
        self._cycle_thread = threading.current_thread()
        try:
            self.logger.debug("Starting application cycle...")
            if not self._execute_cycle_steps():
                self._reset_state()
                return False
            self.logger.debug("Application cycle completed successfully")
            return True
        except (DatabaseError, NetworkError, APIError) as exc:
            self.logger.error(f"Application cycle failed: {exc}")
            self._reset_state()
            return False
        except Exception as exc:
            self.logger.error(f"Unexpected error in application cycle: {exc}")
            self._reset_state()
            return False
        finally:
            self.running = False
            self._cycle_thread = None

    def _execute_cycle_steps(self) -> bool:
        """Run sequential cycle stages while honoring ``_stop_event``.

        Returns:
            True if all stages succeeded, False otherwise.
        """
        if self._stop_event.is_set() or not self._load_data():
            self.logger.warning("Data loading failed")
            return False
        zones = self.enabled_zones or []
        if self._stop_event.is_set() or not self.update_service.process_records(zones):
            self.logger.warning("Data processing failed")
            return False
        is_startup = self._is_first_cycle
        self._is_first_cycle = False
        if self._stop_event.is_set() or not self.update_service.save_updates(
            zones, is_startup=is_startup
        ):
            self.logger.warning("Saving updates failed")
            return False
        if not self._finalize_cycle():
            self.logger.warning("Finalization failed")
            return False
        return True

    def stop(self) -> bool:
        """Request cycle stop and wait up to ``DaemonDefaults.STOP_TIMEOUT``.

        Returns:
            True if stopped within timeout, False otherwise.
        """
        self.logger.info("Stopping application...")
        self._stop_event.set()
        max_wait = DaemonDefaults.STOP_TIMEOUT
        wait_count = 0
        is_other_thread = (
            self._cycle_thread is not None
            and self._cycle_thread is not threading.current_thread()
        )
        while self.running and is_other_thread and wait_count < max_wait:
            self.logger.debug(f"Waiting for application to stop... ({wait_count}/{max_wait})")
            time.sleep(DaemonDefaults.STOP_CHECK_INTERVAL)
            wait_count += 1
        self.running = False
        if wait_count >= max_wait:
            self.logger.warning("Application did not stop gracefully within timeout")
            return False
        self.logger.info("Application stopped successfully")
        return True

    def cleanup(self) -> None:
        """Close cached HTTP sessions and pooled SQLite database connections."""
        self.logger.info("Cleaning up application resources...")
        try:
            if self.running:
                self.stop()
            if self.sync_service:
                self.sync_service.close()
            if self.database:
                self.database.close()
                self.logger.debug("Database connections closed")
            self.logger.info("Application cleanup completed")
        except Exception as exc:
            self.logger.error(f"Error during application cleanup: {exc}")

    def is_running(self) -> bool:
        """Return whether an application cycle is currently executing.

        Returns:
            Boolean running state.
        """
        return self.running

    def reload_config(self) -> None:
        """Hot-reload TOML configuration, logger levels, and HTTP client cache."""
        self.logger.info("Reloading application configuration...")
        try:
            if hasattr(self.config, "reload"):
                self.config.reload()
            LoggerManager.set_level(self.logger, self.config.log_level)
            LoggerManager.set_console_colors(self.logger, self.config.console_colors)
            self.network.setup(
                ipv4_enabled=self.config.network_ipv4_enabled,
                ipv6_enabled=self.config.network_ipv6_enabled,
                ipv4_url=self.config.network_ipv4_detection_url,
                ipv6_url=self.config.network_ipv6_detection_url,
                timeout=self.config.network_timeout,
                retries=self.config.network_retry_attempts,
                logger=self.logger,
            )
            self.sync_service.close()
            self.logger.info("Configuration reloaded successfully")
        except ConfigError as exc:
            self.logger.error(f"Failed to reload configuration: {exc}")
        except Exception as exc:
            self.logger.error(f"Unexpected error reloading configuration: {exc}")

    ############################################################################
    # PRIVATE METHODS - Cycle Data Pipeline
    ############################################################################

    def _load_data(self) -> bool:
        """Detect public IP addresses and load enabled zones and records.

        Returns:
            True if at least one IP was detected and DB loaded cleanly.
        """
        try:
            if not self._detect_and_log_ips():
                return False
            return self._load_zones_and_records()
        except (NetworkError, DatabaseError) as exc:
            self.logger.error(f"Network check or database load failed: {exc}")
            return False

    def _detect_and_log_ips(self) -> bool:
        """Probe public IPv4/IPv6 addresses and log address transitions.

        Returns:
            True if at least one protocol yielded a valid IP address.
        """
        self.logger.debug("Checking network and IP addresses...")
        ipv4, ipv6 = self.network.load_current_ip_addresses()
        self._log_detected_protocol("IPv4", ipv4, self.network.ipv4_enabled)
        self._log_detected_protocol("IPv6", ipv6, self.network.ipv6_enabled)
        if not ipv4 and not ipv6:
            self.logger.error("No IP addresses detected - cannot proceed")
            return False
        changes = self.network.has_ip_changed()
        self._log_ip_transition("IPv4", self.network.last_ipv4_address, ipv4, changes["ipv4_changed"])
        self._log_ip_transition("IPv6", self.network.last_ipv6_address, ipv6, changes["ipv6_changed"])
        return True

    def _log_detected_protocol(
        self, label: str, address: str | None, enabled: bool
    ) -> None:
        """Log detection status for a single IP protocol family.

        Args:
            label: Protocol label (``'IPv4'`` or ``'IPv6'``).
            address: Detected IP address or ``None``.
            enabled: Whether probing for ``label`` is enabled.
        """
        if address:
            self.logger.debug(f"{label} address detected: {address}")
        elif enabled:
            self.logger.warning(f"No {label} address detected")

    def _log_ip_transition(
        self, label: str, previous: str | None, current: str | None, changed: bool
    ) -> None:
        """Log whether an IP protocol address changed since the previous cycle.

        Args:
            label: Protocol label (``'IPv4'`` or ``'IPv6'``).
            previous: Previously saved IP address.
            current: Newly detected IP address.
            changed: Boolean change flag from ``NetworkData.has_ip_changed()``.
        """
        if current is None:
            return
        if changed:
            self.logger.info(
                f"{label} address changed: {previous} {LOG_SYMBOLS['ARROW']} {current}"
            )
        else:
            self.logger.debug(f"{label} address unchanged: {current}")

    def _load_zones_and_records(self) -> bool:
        """Load enabled zones and their active records from SQLite.

        Returns:
            True once zone and record structures are populated.
        """
        self.logger.debug("Loading database state...")
        zones_from_db = self.database.get_all_enabled_zones()
        if not zones_from_db:
            self.enabled_zones = []
            self.logger.warning("No enabled zones found in database")
            return True
        self.enabled_zones = [dict(zone) for zone in zones_from_db]
        total_records = 0
        for zone in self.enabled_zones:
            zone["records"] = self._load_zone_records_with_ip(zone["id"])
            total_records += len(zone["records"])
            self.logger.debug(
                f"Loaded zone '{zone['zone_name']}' with {len(zone['records'])} records"
            )
        self.logger.debug(
            f"Loaded {len(self.enabled_zones)} zones with {total_records} total records"
        )
        return True

    def _load_zone_records_with_ip(self, zone_id: int) -> list[dict[str, Any]]:
        """Fetch enabled records for ``zone_id`` with nested ``current_ip`` metadata.

        Args:
            zone_id: Database zone ID.

        Returns:
            List of enriched record dictionaries.
        """
        records = [dict(row) for row in self.database.get_records_by_zone(zone_id, enabled_only=True)]
        for record in records:
            record["current_ip"] = (
                {
                    "ip_address": record["ip_address"],
                    "last_checked_at": record.get("last_checked_at"),
                    "last_changed_at": record.get("last_changed_at"),
                }
                if record.get("ip_address")
                else None
            )
        return records

    def _finalize_cycle(self) -> bool:
        """Commit detected IPs as last-known values and clear cycle state.

        Returns:
            True on success, False if state persistence fails.
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
        except (NetworkError, DatabaseError) as exc:
            self.logger.error(f"Finalization failed: {exc}")
            return False

    def _reset_state(self) -> None:
        """Clear transient per-cycle zone cache after an error."""
        self.enabled_zones = None
        self.logger.debug("Application state reset")
