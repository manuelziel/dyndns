#!/usr/bin/env python3
"""CLI Settings Manager for configuring global DynDNS settings.

Provides interactive menus to inspect and update ``dns.update_method`` and
``dns.default_ttl`` in ``config.toml``.

Author: Manuel Ziel
License: MIT
"""

################################################################################
# IMPORTS & DEPENDENCIES
################################################################################

import logging
from typing import Any

from ..core.constants import UpdateMethod
from ..utils.colors import Colors
from .constants import (
    MenuLabels,
    SettingsMenuChoices,
    UpdateMethodLabels,
    UpdateMethodMenuChoices,
    ValidationLimits,
)
from .helpers import (
    clear_screen,
    print_error,
    print_section,
    print_success,
    print_warning,
    safe_input,
    wait_for_enter,
)

################################################################################
# SETTINGS MANAGER CLASS
################################################################################


class SettingsManager:
    """Manages global DNS settings in the interactive CLI.

    Attributes:
        config: ``ConfigManager`` instance.
        logger: Logger instance.
    """

    def __init__(
        self, config: Any, logger: logging.Logger | None = None
    ) -> None:
        """Initialize ``SettingsManager``.

        Args:
            config: ``ConfigManager`` instance.
            logger: Optional logger instance.
        """
        self.config = config
        self.logger = logger or logging.getLogger(__name__)

    def manage_settings(self) -> None:
        """Run the interactive DNS settings submenu loop."""
        while True:
            self._render_settings_menu()
            choice = safe_input("Enter your choice (0-2): ").strip()
            try:
                if choice == SettingsMenuChoices.EXIT:
                    break
                if choice == SettingsMenuChoices.UPDATE_METHOD:
                    self._change_update_method()
                elif choice == SettingsMenuChoices.DEFAULT_TTL:
                    self._change_default_ttl()
                else:
                    print_error("Invalid choice!")
                    wait_for_enter()
            except KeyboardInterrupt:
                print("\nOperation cancelled.")
                wait_for_enter()
            except (ValueError, KeyError, OSError) as exc:
                print_error(f"Error updating settings: {exc}")
                wait_for_enter()

    def _render_settings_menu(self) -> None:
        """Render current global DNS settings and submenu options."""
        clear_screen()
        print_section("DNS & Update Settings")
        print("\nCurrent Global Settings:")
        desc = self._get_method_desc(self.config.dns_update_method)
        print(
            f"  {Colors.BOLD}Update Method:{Colors.NC}  "
            f"{Colors.CYAN}{self.config.dns_update_method}{Colors.NC} ({desc})"
        )
        print(
            f"  {Colors.BOLD}Default TTL:{Colors.NC}    "
            f"{Colors.CYAN}{self.config.dns_default_ttl}s{Colors.NC}\n"
        )
        print("Available options:")
        for key, label in MenuLabels.SETTINGS_MENU.items():
            print(f"  {key}) {label}")
        print(f"  {SettingsMenuChoices.EXIT}) Back to Main Menu\n")

    @staticmethod
    def _get_method_desc(method: str) -> str:
        """Return a short description for ``method``.

        Args:
            method: Update method identifier (``'dyndns'`` or ``'rest'``).

        Returns:
            Human-readable method description.
        """
        if method == UpdateMethod.DYNDNS:
            return UpdateMethodLabels.DYNDNS_DESC
        if method == UpdateMethod.REST:
            return UpdateMethodLabels.REST_DESC
        return UpdateMethodLabels.UNKNOWN_DESC

    def _change_update_method(self) -> None:
        """Prompt user to select and persist ``dns.update_method``."""
        print_section("Change Update Method")
        print("Select new default update method:")
        for choice_key, (name, desc) in UpdateMethodLabels.MENU_OPTIONS.items():
            print(f"  {choice_key}) {Colors.BOLD}{name}{Colors.NC} - {desc}")
        print(f"  {UpdateMethodMenuChoices.CANCEL}) Cancel\n")

        prompt = f"Enter choice ({UpdateMethodMenuChoices.CANCEL}-{UpdateMethodMenuChoices.REST}): "
        choice = safe_input(prompt).strip()
        if choice == UpdateMethodMenuChoices.CANCEL:
            return
        method_map = {
            UpdateMethodMenuChoices.DYNDNS: str(UpdateMethod.DYNDNS),
            UpdateMethodMenuChoices.REST: str(UpdateMethod.REST),
        }
        new_method = method_map.get(choice)  # type: ignore[arg-type]
        if not new_method:
            print_error("Invalid selection.")
            wait_for_enter()
            return
        if new_method == self.config.dns_update_method:
            print_warning(f"Update method is already set to '{new_method}'.")
        elif self.config.update_setting("dns", "update_method", new_method):
            print_success(f"Update method changed to '{new_method}' and saved to config.toml.")
        else:
            print_error("Failed to save setting to config.toml.")
        wait_for_enter()

    def _change_default_ttl(self) -> None:
        """Prompt user to update and persist ``dns.default_ttl``."""
        print_section("Change Default TTL")
        print(f"Current default TTL: {self.config.dns_default_ttl} seconds")
        print(f"Valid range: {ValidationLimits.TTL_MIN} - {ValidationLimits.TTL_MAX} seconds")
        print("Enter 0 to cancel.\n")

        input_str = safe_input("New default TTL (seconds): ").strip()
        if not input_str or input_str == "0":
            return
        new_ttl = self._parse_ttl_input(input_str)
        if new_ttl is None:
            wait_for_enter()
            return
        if new_ttl == self.config.dns_default_ttl:
            print_warning(f"Default TTL is already set to {new_ttl}s.")
        elif self.config.update_setting("dns", "default_ttl", new_ttl):
            print_success(f"Default TTL changed to {new_ttl}s and saved to config.toml.")
        else:
            print_error("Failed to save setting to config.toml.")
        wait_for_enter()

    @staticmethod
    def _parse_ttl_input(input_str: str) -> int | None:
        """Parse and validate a user-entered TTL integer string.

        Args:
            input_str: Raw numeric string entered by the user.

        Returns:
            Validated TTL integer or ``None`` if invalid.
        """
        try:
            new_ttl = int(input_str)
        except ValueError:
            print_error("Enter a valid integer.")
            return None
        if not ValidationLimits.TTL_MIN <= new_ttl <= ValidationLimits.TTL_MAX:
            print_error(
                f"TTL must be between {ValidationLimits.TTL_MIN} and {ValidationLimits.TTL_MAX}."
            )
            return None
        return new_ttl
