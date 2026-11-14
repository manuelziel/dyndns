#!/usr/bin/env python3
"""RecordManager class implementing CRUD submenus and update actions for DNS records.

Composes modular mixins from ``src.cli.records_ops`` for record creation, editing,
deletion, provider synchronization, and forced DNS updates while handling top-level
record submenu navigation and listing.

Author: Manuel Ziel
License: MIT
"""

################################################################################
# IMPORTS & DEPENDENCIES
################################################################################

from typing import Any

from src.cli.constants import (
    CLIConfig,
    MenuLabels,
    RecordMenuChoices,
    SelectionChoices,
)
from src.utils.colors import Colors

from .helpers.input import safe_input, wait_for_enter
from .helpers.output import (
    clear_screen,
    print_error,
    print_info,
    print_section,
    row_to_dict,
)
from .records_ops import (
    RecordCreateMixin,
    RecordDeleteSyncMixin,
    RecordEditMixin,
    RecordForceUpdateMixin,
    RecordProviderClientMixin,
    RecordRestRecoveryMixin,
)

################################################################################
# RECORD MANAGER CLASS
################################################################################


class RecordManager(
    RecordProviderClientMixin,
    RecordRestRecoveryMixin,
    RecordCreateMixin,
    RecordEditMixin,
    RecordDeleteSyncMixin,
    RecordForceUpdateMixin,
):
    """Interactive manager for DNS record listing, CRUD, sync, and forced updates.

    Attributes:
        config: ``ConfigManager`` instance.
        logger: Application logger instance.
        db: ``Database`` instance for SQLite storage.
    """

    def __init__(self, config: Any, logger: Any, db: Any) -> None:
        """Initialize ``RecordManager``.

        Args:
            config: ``ConfigManager`` instance.
            logger: Application logger instance.
            db: ``Database`` instance.
        """
        self.config = config
        self.logger = logger
        self.db = db

    def manage_records(self) -> None:
        """Display and handle the interactive record management submenu."""
        while True:
            clear_screen()
            print_section("Manage DNS Records")
            print(
                f"\n{Colors.DIM}DNS Records define which domains/subdomains are managed by DynDNS.{Colors.NC}"
            )
            print(
                f"{Colors.DIM}Each record will be automatically updated with your current IP address.{Colors.NC}\n"
            )
            print(f"{Colors.BLUE}Available options:{Colors.NC}")

            menu_items = list(MenuLabels.RECORD_MENU.values())
            for idx, item in enumerate(menu_items, 1):
                print(f"  {idx}) {item}")
            print("  0) Back\n")

            choice = safe_input(f"Enter your choice (0-{len(menu_items)}): ").strip()
            if choice == RecordMenuChoices.EXIT:
                break
            self._handle_record_menu_choice(choice)

    def list_records(self) -> None:
        """List DNS records across all zones or for a selected zone."""
        print_section("DNS Records")
        zones = self.db.get_all_zones()
        if not zones:
            print_info("No zones configured.")
            wait_for_enter()
            return

        zones_list = [row_to_dict(z) for z in zones]
        self._print_zone_selection_list(zones_list)
        choice_str = safe_input("\nYour choice: ").strip()
        if choice_str == SelectionChoices.ALL:
            self._list_all_zones_records(zones_list)
        else:
            self._list_single_zone_records(choice_str, zones_list)
        wait_for_enter()

    ############################################################################
    # Record Menu & Listing Helpers
    ############################################################################

    def _handle_record_menu_choice(self, choice: str) -> None:
        """Dispatch a record management submenu option.

        Args:
            choice: Selected menu key.
        """
        if choice == RecordMenuChoices.LIST:
            self.list_records()
        elif choice == RecordMenuChoices.ADD:
            self.add_record()
        elif choice == RecordMenuChoices.EDIT:
            self.edit_record()
        elif choice == RecordMenuChoices.DELETE:
            self.delete_record()
        elif choice == RecordMenuChoices.SYNC:
            self.sync_zone_from_provider()
        else:
            print_error("Invalid choice!")
            wait_for_enter()

    def _print_zone_selection_list(self, zones_list: list[dict[str, Any]]) -> None:
        """Display numbered zone selection prompt including 'All zones'.

        Args:
            zones_list: List of zone dictionaries.
        """
        print(f"\n{Colors.BOLD}Select Zone:{Colors.NC}")
        for idx, z_dict in enumerate(zones_list, start=1):
            status = (
                f"{Colors.GREEN}Enabled{Colors.NC}"
                if z_dict["enabled"]
                else f"{Colors.DIM}Disabled{Colors.NC}"
            )
            print(
                f" {idx}) {z_dict['zone_name']:<{CLIConfig.ZONE_NAME_WIDTH}} [{status}]"
            )
        print(f" {SelectionChoices.ALL}) All zones")

    def _list_all_zones_records(self, zones_list: list[dict[str, Any]]) -> None:
        """Print configured records grouped under each zone in ``zones_list``.

        Args:
            zones_list: List of zone dictionaries.
        """
        for z_dict in zones_list:
            records = self.db.get_records_by_zone(z_dict["id"], enabled_only=False)
            if records:
                print(f"\n{Colors.CYAN}═══ {z_dict['zone_name']} ═══{Colors.NC}")
                self._print_records_list(records)

    def _list_single_zone_records(
        self, choice_str: str, zones_list: list[dict[str, Any]]
    ) -> None:
        """Print configured records and stored IPs for a single selected zone.

        Args:
            choice_str: Raw user index selection.
            zones_list: List of zone dictionaries.
        """
        if not choice_str.isdigit():
            print_error("Invalid choice")
            return
        idx = int(choice_str)
        if idx < 1 or idx > len(zones_list):
            print_error(f"Select 1-{len(zones_list)}")
            return

        z_dict = zones_list[idx - 1]
        records = self.db.get_records_by_zone(z_dict["id"], enabled_only=False)
        if not records:
            print_info(f"No records configured for {z_dict['zone_name']}")
            return
        print(f"\n{Colors.CYAN}═══ {z_dict['zone_name']} ═══{Colors.NC}")
        self._print_records_list(records, show_ip=True)

    def _print_records_list(
        self, records: list[Any], show_ip: bool = False
    ) -> None:
        """Print formatted rows for ``records`` and optional stored IP lines.

        Args:
            records: List of record dictionaries/rows.
            show_ip: Whether to display each record's stored IP address.
        """
        for idx, r_row in enumerate(records, start=1):
            rec = row_to_dict(r_row)
            status = (
                f"{Colors.GREEN}Enabled{Colors.NC}"
                if rec.get("enabled", True)
                else f"{Colors.DIM}Disabled{Colors.NC}"
            )
            ttl = rec.get("ttl", self.config.dns_default_ttl)
            print(
                f"  {idx:3d}. {rec['record_name']:{CLIConfig.RECORD_NAME_WIDTH}s} "
                f"{rec['record_type']:{CLIConfig.RECORD_TYPE_WIDTH}s} TTL:{ttl:5d} [{status}]"
            )
            if show_ip:
                stored_ip = rec.get("ip_address") or self._get_current_ip(rec)
                if stored_ip:
                    print(f"     └─ Current IP: {stored_ip}")
