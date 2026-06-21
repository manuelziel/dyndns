#!/usr/bin/env python3
"""StatusDisplay implementation for the DynDNS CLI.

Handles public IP detection and database records status visualization.

Author: Manuel Ziel
License: MIT
"""

################################################################################
# IMPORTS & DEPENDENCIES
################################################################################

# Standard Imports
from typing import Any, List, Optional, Dict

# Local Imports
from src.core.constants import RecordType
from src.cli.constants import CLIConfig
from src.network import NetworkData
from src.utils.colors import Colors
from .helpers.output import (
    print_subsection, print_success, print_warning, print_info, row_to_dict
)
from .helpers.input import wait_for_enter

################################################################################
# STATUS DISPLAY CLASS
################################################################################

class StatusDisplay:
    """Handles status visualization for IPs and stored DNS configurations.

    Attributes:
        config: ConfigManager instance.
        logger: LoggerManager instance.
        db: Active database connection.
    """

    def __init__(self, config: Any, logger: Any, db: Any) -> None:
        """Initialize the StatusDisplay.

        Args:
            config: ConfigManager instance.
            logger: Logger instance.
            db: Database connection.
        """
        self.config = config
        self.logger = logger
        self.db = db


    def show(self) -> None:
        """Query public IPs and display status of all configured DNS records."""
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


    def _detect_and_print_ips(self) -> tuple:
        """Query current public IPv4 and IPv6 addresses.

        Returns:
            Tuple containing detected (current_ipv4, current_ipv6).
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
        self, zones: List[Any], current_ipv4: Optional[str], current_ipv6: Optional[str]
    ) -> None:
        """Print the configured zones and their stored DNS records.

        Args:
            zones: List of zones rows from database.
            current_ipv4: Detected current IPv4.
            current_ipv6: Detected current IPv6.
        """
        has_any_records = False
        for zone_row in zones:
            zone = row_to_dict(zone_row)
            records = self.db.get_records_by_zone(zone['id'], enabled_only=True)

            if records:
                has_any_records = True
                print(f"\n{Colors.CYAN}═══ {zone['zone_name']} ═══{Colors.NC}")
                for record_row in records:
                    self._print_zone_record_ip(row_to_dict(record_row), current_ipv4, current_ipv6)

        if not has_any_records:
            print_info("No records configured for any zone.")


    def _print_zone_record_ip(
        self, record: Dict[str, Any], current_ipv4: Optional[str], current_ipv6: Optional[str]
    ) -> None:
        """Print the stored IP for a single DNS record.

        Args:
            record: Target record dictionary.
            current_ipv4: Current public IPv4.
            current_ipv6: Current public IPv6.
        """
        ip_info_row = self.db.get_ip_address(record['id'])
        record_name = record['record_name']
        record_type = record['record_type']

        if not ip_info_row:
            print(f"  {record_name:<{CLIConfig.RECORD_NAME_WIDTH}s} {record_type:{CLIConfig.RECORD_TYPE_WIDTH}s} {Colors.DIM}○ (no IP stored yet){Colors.NC}")
            return

        ip_info = row_to_dict(ip_info_row)
        stored_ip = ip_info.get('ip_address', '')
        changed_at = ip_info.get('last_changed_at', 'N/A')
        current_ip = current_ipv4 if record_type == RecordType.A else current_ipv6

        if current_ip and stored_ip != current_ip:
            print(
                f"  {record_name:<{CLIConfig.RECORD_NAME_WIDTH}s} {record_type:{CLIConfig.RECORD_TYPE_WIDTH}s} "
                f"{Colors.YELLOW}{stored_ip} (outdated, current: {current_ip}){Colors.NC}"
            )
        else:
            print(f"  {record_name:<{CLIConfig.RECORD_NAME_WIDTH}s} {record_type:{CLIConfig.RECORD_TYPE_WIDTH}s} {Colors.GREEN}{stored_ip}{Colors.NC} (changed: {changed_at})")
