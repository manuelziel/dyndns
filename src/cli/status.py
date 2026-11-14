#!/usr/bin/env python3
"""StatusDisplay implementation for the DynDNS interactive CLI.

Detects live public IPv4/IPv6 addresses and compares them against stored SQLite
record state.

Author: Manuel Ziel
License: MIT
"""

################################################################################
# IMPORTS & DEPENDENCIES
################################################################################

from typing import Any

from ..core.constants import RecordType
from ..network import NetworkData
from ..utils.colors import Colors
from .constants import CLIConfig, StatusSymbols
from .helpers.input import wait_for_enter
from .helpers.output import (
    print_info,
    print_subsection,
    print_success,
    print_warning,
    row_to_dict,
)

################################################################################
# STATUS DISPLAY CLASS
################################################################################


class StatusDisplay:
    """Visualizes live public IPs and stored DNS record synchronization state.

    Attributes:
        config: ``ConfigManager`` instance.
        logger: Logger instance.
        db: ``Database`` connection pool.
    """

    def __init__(self, config: Any, logger: Any, db: Any) -> None:
        """Initialize ``StatusDisplay``.

        Args:
            config: ``ConfigManager`` instance.
            logger: Logger instance.
            db: ``Database`` connection pool.
        """
        self.config = config
        self.logger = logger
        self.db = db

    def show(self) -> None:
        """Probe public IPs and render status for all enabled DNS records."""
        print_subsection("Detecting Current IP Addresses")
        current_ipv4, current_ipv6 = self._detect_and_print_ips()
        zones = self.db.get_all_zones()
        print_subsection("Stored DNS Record IPs")
        if not zones:
            print_info("No zones configured.")
            wait_for_enter()
            return
        self._print_stored_record_ips(zones, current_ipv4, current_ipv6)
        wait_for_enter()

    def _detect_and_print_ips(self) -> tuple[str | None, str | None]:
        """Probe and print current public IPv4 and IPv6 addresses.

        Returns:
            Tuple ``(current_ipv4, current_ipv6)``.
        """
        network = NetworkData(config=self.config, logger=self.logger)
        current_ipv4, current_ipv6 = network.load_current_ip_addresses()
        if current_ipv4:
            print_success(f"IPv4: {current_ipv4}")
        else:
            print_warning("IPv4: Not detected")
        if current_ipv6:
            print_success(f"IPv6: {current_ipv6}")
        else:
            print_warning("IPv6: Not detected")
        return current_ipv4, current_ipv6

    def _print_stored_record_ips(
        self,
        zones: list[Any],
        current_ipv4: str | None,
        current_ipv6: str | None,
    ) -> None:
        """Print stored IP status lines grouped by zone.

        Args:
            zones: Zone rows from SQLite.
            current_ipv4: Detected public IPv4 address.
            current_ipv6: Detected public IPv6 address.
        """
        has_any_records = False
        for zone_row in zones:
            zone = row_to_dict(zone_row)
            if not zone:
                continue
            records = self.db.get_records_by_zone(zone["id"], enabled_only=True)
            if records:
                has_any_records = True
                print(f"\n{Colors.CYAN}--- {zone['zone_name']} ---{Colors.NC}")
                for record_row in records:
                    rec = row_to_dict(record_row)
                    if rec:
                        self._print_zone_record_ip(rec, current_ipv4, current_ipv6)
        if not has_any_records:
            print_info("No records configured for any zone.")

    def _print_zone_record_ip(
        self,
        record: dict[str, Any],
        current_ipv4: str | None,
        current_ipv6: str | None,
    ) -> None:
        """Render the stored IP comparison line for a single DNS record.

        Args:
            record: Record dictionary.
            current_ipv4: Detected public IPv4 address.
            current_ipv6: Detected public IPv6 address.
        """
        record_name = record["record_name"]
        record_type = record["record_type"]
        stored_ip = record.get("ip_address")
        changed_at = record.get("last_changed_at")
        if not stored_ip and "ip_address" not in record:
            ip_info = row_to_dict(self.db.get_ip_address(record["id"]))
            if ip_info:
                stored_ip = ip_info.get("ip_address")
                changed_at = ip_info.get("last_changed_at")

        prefix = f"  {record_name:<{CLIConfig.RECORD_NAME_WIDTH}s} {record_type:{CLIConfig.RECORD_TYPE_WIDTH}s}"
        if not stored_ip:
            print(f"{prefix} {Colors.DIM}{StatusSymbols.INACTIVE} (no IP stored yet){Colors.NC}")
            return
        changed_label = changed_at or "N/A"
        current_ip = current_ipv4 if record_type == RecordType.A else current_ipv6
        if current_ip and stored_ip != current_ip:
            print(
                f"{prefix} {Colors.YELLOW}{stored_ip} (outdated, current: {current_ip}){Colors.NC}"
            )
        else:
            print(f"{prefix} {Colors.GREEN}{stored_ip}{Colors.NC} (changed: {changed_label})")
