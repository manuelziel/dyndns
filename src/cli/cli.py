#!/usr/bin/env python3
"""ConfigMenu implementation for the DynDNS CLI.

Assembles the DynDNS main configuration menu and links entity managers.

Author: Manuel Ziel
License: MIT
"""

################################################################################
# IMPORTS & DEPENDENCIES
################################################################################

# Standard Imports
from typing import Any

# Local Imports
from .menu import ConfigMenu as BaseMenu
from .importer import ConfigImporter
from .exporter import ConfigExporter
from .zones import ZoneManager
from .records import RecordManager
from src.cli.constants import MenuChoices, MenuLabels
from .helpers.output import print_error, print_section
from .helpers.input import wait_for_enter
from .status import StatusDisplay

################################################################################
# CONFIGURATION MENU IMPLEMENTATION
################################################################################

class ConfigMenu(BaseMenu):
    """Concrete implementation of the DynDNS TUI configuration menu.

    Links importer, exporter, zone, and record managers.
    """

    # Link concrete classes for the base menu to use
    importer_class = ConfigImporter
    exporter_class = ConfigExporter

    def __init__(self, config: Any, logger: Any) -> None:
        """Initialize configuration menu with entity managers.

        Args:
            config: ConfigManager instance.
            logger: Logger instance.
        """
        super().__init__(config, logger)
        self.zone_manager = ZoneManager(config, logger, self.db)
        self.record_manager = RecordManager(config, logger, self.db)


    def print_menu(self) -> int:
        """Print main menu options.

        Returns:
            Maximum valid choice number.
        """
        print_section("Configuration")
        print()
        print(f"Available options:")
        menu_items = list(MenuLabels.MAIN_MENU.values())
        for idx, item in enumerate(menu_items, start=1):
            print(f"  {idx}) {item}")
        print(f"  {MenuChoices.EXIT}) Exit")
        print()
        return len(menu_items)


    def handle_choice(self, choice: str) -> None:
        """Handle user menu choice.

        Args:
            choice: Selected option key.
        """
        if choice == MenuChoices.MANAGE_ZONES:
            self.manage_zones()
        elif choice == MenuChoices.MANAGE_RECORDS:
            self.manage_records()
        elif choice == MenuChoices.VIEW_IP:
            self.view_status()
        elif choice == MenuChoices.FORCE_UPDATE:
            self.force_dns_update()
        elif choice == MenuChoices.IMPORT:
            self.import_config()
        elif choice == MenuChoices.EXPORT:
            self.export_config()
        else:
            print_error("Invalid choice!")
            wait_for_enter()


    def manage_zones(self) -> None:
        """Manage primary database entities (Zones)."""
        self.zone_manager.manage_zones()


    def manage_records(self) -> None:
        """Manage secondary database entities (Records)."""
        self.record_manager.manage_records()


    def force_dns_update(self) -> None:
        """Manually trigger forced DNS updates."""
        self.record_manager.force_dns_update()


    def view_status(self) -> None:
        """View current IP addresses and database record statuses."""
        display = StatusDisplay(self.config, self.logger, self.db)
        display.show()
