#!/usr/bin/env python3
"""Concrete ``ConfigMenu`` implementation for the DynDNS interactive CLI.

Assembles zone, record, settings, status, import, and export managers into the
top-level administration menu.

Author: Manuel Ziel
License: MIT
"""

################################################################################
# IMPORTS & DEPENDENCIES
################################################################################

from typing import Any

from ..core.exceptions import DatabaseError
from .constants import MenuChoices, MenuLabels
from .exporter import ConfigExporter
from .helpers.input import wait_for_enter
from .helpers.output import print_error, print_section
from .importer import ConfigImporter
from .menu import ConfigMenu as BaseMenu
from .records import RecordManager
from .settings import SettingsManager
from .status import StatusDisplay
from .zones import ZoneManager

################################################################################
# CONFIGURATION MENU IMPLEMENTATION
################################################################################


class ConfigMenu(BaseMenu):
    """Top-level interactive TUI menu for DynDNS administration."""

    importer_class = ConfigImporter
    exporter_class = ConfigExporter

    def __init__(self, config: Any, logger: Any) -> None:
        """Initialize configuration menu and domain entity managers.

        Args:
            config: ``ConfigManager`` instance.
            logger: Logger instance.

        Raises:
            DatabaseError: If database schema validation fails.
        """
        super().__init__(config, logger)
        if not self.db.check_schema_compatibility():
            raise DatabaseError("Database schema validation or migration failed.")
        self.zone_manager = ZoneManager(config, logger, self.db)
        self.record_manager = RecordManager(config, logger, self.db)
        self.settings_manager = SettingsManager(config, logger)

    def print_menu(self) -> int:
        """Render top-level menu options and return option count.

        Returns:
            Highest valid menu option integer.
        """
        print_section("Configuration")
        print("\nAvailable options:")
        menu_items = list(MenuLabels.MAIN_MENU.values())
        for idx, item in enumerate(menu_items, start=1):
            print(f"  {idx}) {item}")
        print(f"  {MenuChoices.EXIT}) Exit\n")
        return len(menu_items)

    def handle_choice(self, choice: str) -> None:
        """Dispatch user's main menu ``choice`` to the matching handler.

        Args:
            choice: Selected option key string.
        """
        dispatch = {
            MenuChoices.VIEW_IP: self.view_status,
            MenuChoices.MANAGE_ZONES: self.manage_zones,
            MenuChoices.MANAGE_RECORDS: self.manage_records,
            MenuChoices.FORCE_UPDATE: self.force_dns_update,
            MenuChoices.SETTINGS: self.manage_settings,
            MenuChoices.EXPORT: self.export_config,
            MenuChoices.IMPORT: self.import_config,
        }
        handler = dispatch.get(choice)  # type: ignore[arg-type]
        if handler is not None:
            handler()
        else:
            print_error("Invalid choice!")
            wait_for_enter()

    def manage_settings(self) -> None:
        """Open the global DNS settings submenu."""
        self.settings_manager.manage_settings()

    def manage_zones(self) -> None:
        """Open the DNS zones management submenu."""
        self.zone_manager.manage_zones()

    def manage_records(self) -> None:
        """Open the DNS records management submenu."""
        self.record_manager.manage_records()

    def force_dns_update(self) -> None:
        """Trigger an immediate interactive DNS update workflow."""
        self.record_manager.force_dns_update()

    def view_status(self) -> None:
        """Display live public IPs and stored DNS record state."""
        StatusDisplay(self.config, self.logger, self.db).show()
