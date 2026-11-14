#!/usr/bin/env python3
"""ZoneManager class implementing CRUD submenus for DynDNS zones.

Provides interactive submenus for listing, adding, editing, and deleting DNS
zones while delegating post-creation record setup to ``ZoneSetupWizardMixin``
and redacting sensitive ``update_url`` tokens on screen.

Author: Manuel Ziel
License: MIT
"""

################################################################################
# IMPORTS & DEPENDENCIES
################################################################################

import getpass
import json
from typing import Any

from ..core.exceptions import DatabaseError, DynDNSException
from ..core.security import sanitize_log_uri
from ..utils.colors import Colors
from .constants import (
    CLIConfig,
    EditZoneMenuChoices,
    MenuLabels,
    ZoneMenuChoices,
)
from .helpers.input import confirm_action, safe_input, select_zone, wait_for_enter
from .helpers.output import (
    clear_screen,
    print_error,
    print_info,
    print_section,
    print_subsection,
    print_success,
    print_warning,
    row_to_dict,
)
from .helpers.validate import is_valid_domain
from .zone_wizard import ZoneSetupWizardMixin

################################################################################
# ZONE MANAGER CLASS
################################################################################


class ZoneManager(ZoneSetupWizardMixin):
    """Interactive CRUD manager for DynDNS zones and encrypted API credentials.

    Attributes:
        config: ``ConfigManager`` instance.
        logger: Logger instance.
        db: ``Database`` connection pool.
    """

    def __init__(self, config: Any, logger: Any, db: Any) -> None:
        """Initialize ``ZoneManager``.

        Args:
            config: ``ConfigManager`` instance.
            logger: Logger instance.
            db: ``Database`` connection pool.

        Raises:
            DatabaseError: If ``db`` is ``None``.
        """
        self.config = config
        self.logger = logger
        self.db = db
        if self.db is None:
            raise DatabaseError("Database not initialized.")

    ############################################################################
    # PUBLIC MENU METHODS
    ############################################################################

    def manage_zones(self) -> None:
        """Run the interactive zone management submenu loop."""
        while True:
            clear_screen()
            print_section("Manage Zones")
            print(f"\n{Colors.DIM}Zones represent your root domains (e.g., example.com).{Colors.NC}")
            print(
                f"{Colors.DIM}Each zone requires provider API credentials for DynDNS updates.{Colors.NC}\n"
            )
            self._print_zone_menu()
            choice = safe_input("Enter your choice (0-4): ").strip()
            if choice == ZoneMenuChoices.EXIT:
                break
            self._dispatch_zone_menu(choice)

    def _dispatch_zone_menu(self, choice: str) -> None:
        """Route a zone submenu choice to the corresponding CRUD action.

        Args:
            choice: User-entered menu option key.
        """
        if choice == ZoneMenuChoices.LIST:
            self.list_zones()
        elif choice == ZoneMenuChoices.ADD:
            self.add_zone()
        elif choice == ZoneMenuChoices.EDIT:
            self.edit_zone()
        elif choice == ZoneMenuChoices.DELETE:
            self.delete_zone()
        else:
            print_error("Invalid choice!")
            wait_for_enter()

    def list_zones(self) -> None:
        """Display all configured DNS zones with masked credentials and counts."""
        print_section("Current Zones")
        zones = self.db.get_all_zones()
        if not zones:
            print_info("No zones configured.")
            wait_for_enter()
            return
        for idx, row in enumerate(zones, start=1):
            zone = row_to_dict(row)
            if zone:
                self._display_zone_summary(idx, zone)
        wait_for_enter()

    def add_zone(self) -> None:
        """Prompt for domain and credentials to create a new DNS zone."""
        print_section("Add New Zone")
        zone_name = safe_input("Zone Name (e.g., example-zone.com): ").strip().lower()
        if not zone_name or not is_valid_domain(zone_name):
            print_error("Enter a valid RFC 1035 domain name (e.g., example.com)!")
            wait_for_enter()
            return
        if self.db.get_zone_by_name(zone_name):
            print_warning(f"Zone '{zone_name}' already exists!")
            print_info("Use option '3) Edit zone' to update API credentials.")
            wait_for_enter()
            return
        self._prompt_and_create_zone(zone_name)

    def edit_zone(self) -> None:
        """Edit an existing zone's provider ID, credentials, or enabled state."""
        print_section("Edit Zone")
        zone = select_zone(self.db, prompt="Select zone to edit")
        if not zone:
            return
        status_text = "Enabled" if zone["enabled"] else "Disabled"
        status_color = Colors.GREEN if zone["enabled"] else Colors.DIM
        print_subsection("Current Zone")
        print(f"{Colors.BOLD}Name:{Colors.NC}   {Colors.CYAN}{zone['zone_name']}{Colors.NC}")
        print(f"{Colors.BOLD}Status:{Colors.NC} {status_color}{status_text}{Colors.NC}")
        self._print_edit_options()
        choice = safe_input("Enter your choice (0-3): ").strip()
        if choice == EditZoneMenuChoices.UPDATE_ZONE_ID:
            self._edit_zone_id(zone)
        elif choice == EditZoneMenuChoices.UPDATE_CREDENTIALS:
            self._edit_zone_credentials(zone)
        elif choice == EditZoneMenuChoices.TOGGLE_STATUS:
            self._toggle_zone_status(zone)
        elif choice == EditZoneMenuChoices.EXIT:
            print_info("Cancelled.")
        else:
            print_error("Invalid choice!")
        wait_for_enter()

    def delete_zone(self) -> None:
        """Delete a DNS zone after explicit domain-name confirmation."""
        print_section("Delete Zone")
        zone = select_zone(self.db, prompt="Select zone to DELETE")
        if not zone:
            return
        records = self.db.get_records_by_zone(zone["id"], enabled_only=False)
        print_warning("WARNING: This will delete:")
        print(f"   {Colors.RED}*{Colors.NC} Zone: {Colors.BOLD}{zone['zone_name']}{Colors.NC}")
        print(f"   {Colors.RED}*{Colors.NC} {len(records)} DNS record(s) and all IP/update history")

        confirm = safe_input(
            f"\n{Colors.BOLD}Type zone name to confirm deletion:{Colors.NC} "
        ).strip()
        if confirm != zone["zone_name"]:
            print_error("Zone name does not match. Deletion cancelled.")
            wait_for_enter()
            return
        try:
            self.db.delete_zone(zone["id"])
            print_success(f"Zone '{zone['zone_name']}' deleted successfully!")
        except (ValueError, TypeError, DatabaseError) as exc:
            print_error(f"Error deleting zone: {exc}")
            self.logger.error(f"Failed to delete zone {zone['id']}: {exc}")
        wait_for_enter()

    ############################################################################
    # PRIVATE DISPLAY & EDIT HELPERS
    ############################################################################

    @staticmethod
    def _print_zone_menu() -> None:
        """Render the zone management menu options."""
        print(f"{Colors.BLUE}Available options:{Colors.NC}")
        for idx, item in enumerate(MenuLabels.ZONE_MENU.values(), start=1):
            print(f"  {idx}) {item}")
        print(f"  {ZoneMenuChoices.EXIT}) Back\n")

    def _display_zone_summary(self, idx: int, zone: dict[str, Any]) -> None:
        """Render summary details for one zone in ``list_zones``.

        Args:
            idx: 1-based display index.
            zone: Zone dictionary.
        """
        status = (
            f"{Colors.GREEN}Enabled{Colors.NC}"
            if zone["enabled"]
            else f"{Colors.DIM}Disabled{Colors.NC}"
        )
        print(f"\n{Colors.BOLD}{idx}) {zone['zone_name']}{Colors.NC} [{status}]")
        provider_zone_id = zone.get("provider_zone_id") or "N/A"
        print(f"    Zone ID: {Colors.DIM}{provider_zone_id}{Colors.NC}")
        self._display_zone_dyndns_config(zone["id"])
        records = self.db.get_records_by_zone(zone["id"], enabled_only=False)
        cnt_color = Colors.GREEN if records else Colors.DIM
        print(f"    Records: {cnt_color}{len(records)} configured{Colors.NC}")

    def _display_zone_dyndns_config(self, zone_id: int) -> None:
        """Display masked DynDNS credentials and sanitized ``update_url``.

        Args:
            zone_id: Database zone ID.
        """
        dyndns = row_to_dict(self.db.get_dyndns_config_by_zone(zone_id))
        if not dyndns:
            return
        bulk_id = dyndns.get("bulk_id") or "N/A"
        print(f"    Bulk ID: {Colors.DIM}{bulk_id}{Colors.NC}")
        print(f"    API Key: {Colors.DIM}{'*' * CLIConfig.MASK_LENGTH} (encrypted){Colors.NC}")
        domains_field = dyndns.get("domains")
        if domains_field:
            try:
                domains = (
                    json.loads(domains_field)
                    if isinstance(domains_field, str)
                    else domains_field
                )
                if domains:
                    print(f"    Domains: {Colors.DIM}{', '.join(domains)}{Colors.NC}")
            except (json.JSONDecodeError, ValueError, TypeError):
                pass
        update_url = dyndns.get("update_url")
        if update_url:
            print(f"    Update URL: {Colors.DIM}{sanitize_log_uri(str(update_url))}{Colors.NC}")

    def _prompt_and_create_zone(self, zone_name: str) -> None:
        """Prompt for provider ID and encrypted API credentials for ``zone_name``.

        Args:
            zone_name: Validated root domain name.
        """
        provider_zone_id = safe_input(
            "Zone ID (optional, leave empty to auto-fetch): "
        ).strip()
        print_subsection("API Credentials")
        bulk_id = safe_input("Bulk ID: ").strip()
        print(f"{Colors.DIM}Paste your API Key below (input hidden, press Enter when done){Colors.NC}")
        api_key = getpass.getpass("API Key: ")
        if not bulk_id or not api_key:
            print_error("Bulk ID and API Key are required!")
            wait_for_enter()
            return
        self._confirm_and_save_zone(zone_name, provider_zone_id, bulk_id, api_key)

    def _confirm_and_save_zone(
        self, zone_name: str, provider_zone_id: str, bulk_id: str, api_key: str
    ) -> None:
        """Confirm zone parameters, auto-fetch Zone ID if needed, and save.

        Args:
            zone_name: Root domain name.
            provider_zone_id: Optional explicit provider zone ID.
            bulk_id: Provider API prefix / bulk ID.
            api_key: Provider API secret key.
        """
        zone_id_label = provider_zone_id or f"{Colors.DIM}(auto-fetch){Colors.NC}"
        masked = "*" * min(len(api_key), CLIConfig.MAX_MASK_LENGTH)
        print_subsection("Confirmation")
        print(f"{Colors.BOLD}Zone Name:{Colors.NC}     {zone_name}")
        print(f"{Colors.BOLD}Zone ID:{Colors.NC}       {zone_id_label}")
        print(f"{Colors.BOLD}Bulk ID:{Colors.NC}       {bulk_id}")
        print(
            f"{Colors.BOLD}API Key:{Colors.NC}       "
            f"{Colors.DIM}{masked} ({len(api_key)} chars, will be encrypted){Colors.NC}"
        )
        if not confirm_action("Proceed with zone creation?", default=False):
            print_info("Cancelled.")
            wait_for_enter()
            return
        resolved_zone_id: str | None = provider_zone_id or self._fetch_zone_id_from_provider(
            zone_name, bulk_id, api_key
        )
        self._execute_zone_creation(zone_name, resolved_zone_id, bulk_id, api_key)
        wait_for_enter()

    def _execute_zone_creation(
        self,
        zone_name: str,
        provider_zone_id: str | None,
        bulk_id: str,
        api_key: str,
    ) -> None:
        """Insert the zone and encrypted credentials, then launch the record wizard.

        Args:
            zone_name: Root domain name.
            provider_zone_id: Optional provider zone ID.
            bulk_id: Provider API prefix / bulk ID.
            api_key: Provider API secret key.
        """
        try:
            zone_id = self.db.add_zone(zone_name, provider_zone_id or None)
            if zone_id is None:
                raise DatabaseError("Failed to retrieve zone ID after insertion.")
            self.db.set_dyndns_config(zone_id=zone_id, bulk_id=bulk_id, api_key=api_key)
            print_success(f"Zone '{zone_name}' added successfully!")
            if provider_zone_id:
                print_info(f"Provider Zone ID: {provider_zone_id}")
            self._prompt_create_dyndns_records(
                zone_id, zone_name, provider_zone_id, bulk_id, api_key
            )
        except (ValueError, TypeError, DatabaseError, DynDNSException) as exc:
            print_error(f"Error adding zone: {exc}")
            self.logger.error(f"Failed to add zone '{zone_name}': {exc}")

    @staticmethod
    def _print_edit_options() -> None:
        """Render the zone editing submenu options."""
        print(f"\n{Colors.BOLD}What to edit?{Colors.NC}\n")
        print(f"{Colors.BLUE}Available options:{Colors.NC}")
        for key, label in MenuLabels.EDIT_ZONE_MENU.items():
            print(f"  {key}) {label}")
        print(f"  {EditZoneMenuChoices.EXIT}) Cancel\n")

    def _edit_zone_id(self, zone: dict[str, Any]) -> None:
        """Prompt for and update ``provider_zone_id`` on ``zone``.

        Args:
            zone: Zone dictionary.
        """
        current_id = zone.get("provider_zone_id") or "N/A"
        new_provider_id = safe_input(f"New Zone ID [{current_id}]: ").strip()
        if not new_provider_id:
            print_info("No change.")
            return
        try:
            self.db.update_zone(zone["id"], provider_zone_id=new_provider_id)
            print_success("Zone ID updated")
        except DatabaseError as exc:
            print_error(f"Error updating zone ID: {exc}")
            self.logger.error(f"Failed to update zone ID for zone {zone['id']}: {exc}")

    def _edit_zone_credentials(self, zone: dict[str, Any]) -> None:
        """Prompt for and update encrypted API credentials on ``zone``.

        Args:
            zone: Zone dictionary.
        """
        print_subsection("Update API Credentials")
        existing = self.db.get_dyndns_config_by_zone(zone["id"])
        current_bulk = existing.get("bulk_id") if existing else None
        prompt = f"New Bulk ID [{current_bulk}]: " if current_bulk else "New Bulk ID: "
        bulk_id = safe_input(prompt).strip() or (current_bulk or "")
        print(f"{Colors.DIM}Paste your new API Key (input hidden, press Enter when done){Colors.NC}")
        api_key = getpass.getpass("New API Key: ")
        if not bulk_id or not api_key:
            print_error("Both Bulk ID and API Key are required!")
            return
        try:
            self.db.set_dyndns_config(
                zone_id=zone["id"],
                bulk_id=bulk_id,
                api_key=api_key,
                update_url=existing.get("update_url") if existing else None,
                description=existing.get("description") if existing else None,
                domains=existing.get("domains") if existing else None,
            )
            print_success("API credentials updated")
        except DynDNSException as exc:
            print_error(f"Error updating credentials: {exc}")
            self.logger.error(f"Failed to update credentials for zone {zone['id']}: {exc}")

    def _toggle_zone_status(self, zone: dict[str, Any]) -> None:
        """Flip the enabled/disabled state of ``zone`` in SQLite.

        Args:
            zone: Zone dictionary.
        """
        new_status = not bool(zone["enabled"])
        try:
            self.db.update_zone_status(zone["id"], new_status)
            print_success(f"Zone {'enabled' if new_status else 'disabled'}")
        except DatabaseError as exc:
            print_error(f"Error updating zone status: {exc}")
            self.logger.error(f"Failed to update status for zone {zone['id']}: {exc}")
