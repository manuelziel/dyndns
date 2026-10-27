#!/usr/bin/env python3
"""CLI Settings Manager for configuring global DNS settings.

Provides interactive menus to view and update global application settings
such as `dns.update_method` and `dns.default_ttl`.

Author: Manuel Ziel
License: MIT
"""

################################################################################
# IMPORTS & DEPENDENCIES
################################################################################

import logging
from typing import Any, Optional

from src.cli.constants import (
    MenuLabels,
    SettingsMenuChoices,
    UpdateMethodLabels,
    UpdateMethodMenuChoices,
    ValidationLimits,
)
from src.cli.helpers import (
    clear_screen,
    print_section,
    print_success,
    print_error,
    print_warning,
    safe_input,
    wait_for_enter,
)
from src.core.constants import UpdateMethod
from src.utils.colors import Colors


################################################################################
# SETTINGS MANAGER CLASS - Interactive Global Settings Submenu
################################################################################

class SettingsManager:
    """Manages global application settings in the interactive TUI.

    Attributes:
        config: ConfigManager instance.
        logger: Logger instance.
    """

    def __init__(self, config: Any, logger: Optional[logging.Logger] = None) -> None:
        """Initialize settings manager.

        Args:
            config: ConfigManager instance.
            logger: Optional logger instance.
        """
        self.config = config
        self.logger = logger or logging.getLogger(__name__)


    def manage_settings(self) -> None:
        """Run interactive DNS settings submenu."""
        while True:
            clear_screen()
            print_section("DNS & Update Settings")
            print("\nCurrent Global Settings:")
            print(f"  {Colors.BOLD}Update Method:{Colors.NC}  {Colors.CYAN}{self.config.dns_update_method}{Colors.NC} "
                  f"({self._get_method_desc(self.config.dns_update_method)})")
            print(f"  {Colors.BOLD}Default TTL:{Colors.NC}    {Colors.CYAN}{self.config.dns_default_ttl}s{Colors.NC}\n")
            print("Available options:")
            for choice, label in MenuLabels.SETTINGS_MENU.items():
                print(f"  {choice}) {label}")
            print(f"  {SettingsMenuChoices.EXIT}) Back to Main Menu\n")

            choice = safe_input("Enter your choice (0-2): ").strip()
            try:
                if choice == SettingsMenuChoices.EXIT:
                    break
                elif choice == SettingsMenuChoices.UPDATE_METHOD:
                    self._change_update_method()
                elif choice == SettingsMenuChoices.DEFAULT_TTL:
                    self._change_default_ttl()
                else:
                    print_error("Invalid choice!")
                    wait_for_enter()
            except KeyboardInterrupt:
                print("\nOperation cancelled.")
                wait_for_enter()
            except (ValueError, KeyError, OSError) as e:
                print_error(f"Error updating settings: {e}")
                wait_for_enter()


    def _get_method_desc(self, method: str) -> str:
        """Get human-readable description for update method.

        Args:
            method: The update method identifier string (`dyndns` or `rest`).

        Returns:
            Human-readable description string for the update method.
        """
        if method == UpdateMethod.DYNDNS:
            return UpdateMethodLabels.DYNDNS_DESC
        elif method == UpdateMethod.REST:
            return UpdateMethodLabels.REST_DESC
        return UpdateMethodLabels.UNKNOWN_DESC


    def _change_update_method(self) -> None:
        """Toggle or select the DNS update method."""
        print()
        print_section("Change Update Method")
        print("Select new default update method:")
        for choice_key, (name, desc) in UpdateMethodLabels.MENU_OPTIONS.items():
            print(f"  {choice_key}) {Colors.BOLD}{name}{Colors.NC} - {desc}")
        print(f"  {UpdateMethodMenuChoices.CANCEL}) Cancel")
        print()

        choice = safe_input(f"Enter choice ({UpdateMethodMenuChoices.CANCEL}-{UpdateMethodMenuChoices.REST}): ").strip()
        if choice == UpdateMethodMenuChoices.DYNDNS:
            new_method = UpdateMethod.DYNDNS
        elif choice == UpdateMethodMenuChoices.REST:
            new_method = UpdateMethod.REST
        elif choice == UpdateMethodMenuChoices.CANCEL:
            return
        else:
            print_error("Invalid selection.")
            wait_for_enter()
            return

        if new_method == self.config.dns_update_method:
            print_warning(f"Update method is already set to '{new_method}'.")
            wait_for_enter()
            return

        if self.config.update_setting("dns", "update_method", new_method):
            print_success(f"Update method changed to '{new_method}' and saved to config.toml.")
        else:
            print_error("Failed to save setting to config.toml.")
        wait_for_enter()


    def _change_default_ttl(self) -> None:
        """Change the default DNS Time To Live (TTL)."""
        print_section("Change Default TTL")
        print(f"Current default TTL: {self.config.dns_default_ttl} seconds")
        print(f"Valid range: {ValidationLimits.TTL_MIN} - {ValidationLimits.TTL_MAX} seconds")
        print("Enter 0 to cancel.\n")

        input_str = safe_input("New default TTL (seconds): ").strip()
        if not input_str or input_str == "0":
            return
        try:
            new_ttl = int(input_str)
            if not (ValidationLimits.TTL_MIN <= new_ttl <= ValidationLimits.TTL_MAX):
                print_error(f"TTL must be between {ValidationLimits.TTL_MIN} and {ValidationLimits.TTL_MAX}.")
                wait_for_enter()
                return
        except ValueError:
            print_error("Enter a valid integer.")
            wait_for_enter()
            return

        if new_ttl == self.config.dns_default_ttl:
            print_warning(f"Default TTL is already set to {new_ttl}s.")
            wait_for_enter()
            return
        if self.config.update_setting("dns", "default_ttl", new_ttl):
            print_success(f"Default TTL changed to {new_ttl}s and saved to config.toml.")
        else:
            print_error("Failed to save setting to config.toml.")
        wait_for_enter()
