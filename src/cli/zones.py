#!/usr/bin/env python3
"""ZoneManager class implementing CRUD submenus for DynDNS zones.

This module provides interactive submenus and helper methods for listing,
adding, editing, and deleting DynDNS zones.

Author: Manuel Ziel
License: MIT
"""

################################################################################
# IMPORTS & DEPENDENCIES
################################################################################

# Standard Imports
import getpass
import json
from typing import Any, Dict, List, Optional, Tuple

# Local Imports
from src.core.exceptions import DatabaseError, DynDNSException, NetworkError
from src.core.constants import Subdomain, PlaceholderIP, RecordType
from src.cli.constants import ZoneMenuChoices, EditZoneMenuChoices, SetupMenuChoices, CLIConfig, MenuLabels
from src.core import SyncStatus
from src.network import NetworkData
from src.api import ProviderDNSClient
from src.utils.colors import Colors

from .helpers.input import safe_input, confirm_action, wait_for_enter, select_zone, get_placeholder_ip
from .helpers.output import (
    print_success, print_error, print_warning, print_info,
    print_section, print_subsection, clear_screen, row_to_dict
)

################################################################################
# ZONE MANAGER CLASS
################################################################################

class ZoneManager:
    """Manager class for DynDNS zone CRUD and management operations.

    Attributes:
        config: ConfigManager instance with application settings.
        logger: Logger instance for debug and error messages.
        db: DatabaseManager instance for zone operations.
    """

    def __init__(self, config: Any, logger: Any, db: Any) -> None:
        """Initialize zone manager.

        Args:
            config: ConfigManager instance with application settings.
            logger: Logger instance for logging.
            db: DatabaseManager instance for zone operations.

        Raises:
            DatabaseError: If database is not initialized.
        """
        self.config = config
        self.logger = logger
        self.db = db

        if self.db is None:
            raise DatabaseError("Database not initialized.")


    ############################################################################
    # Public Menu Methods
    ############################################################################

    def manage_zones(self) -> None:
        """Display and handle the zone management submenu."""
        while True:
            clear_screen()
            print_section("Manage Zones")
            print()
            print(f"{Colors.DIM}Zones represent your root domains (e.g., example.com).{Colors.NC}")
            print(f"{Colors.DIM}Each zone requires provider API credentials for DynDNS updates.{Colors.NC}")
            print()
            self._print_zone_menu()

            choice = safe_input("Enter your choice (0-4): ").strip()
            if choice == ZoneMenuChoices.LIST:
                self.list_zones()
            elif choice == ZoneMenuChoices.ADD:
                self.add_zone()
            elif choice == ZoneMenuChoices.EDIT:
                self.edit_zone()
            elif choice == ZoneMenuChoices.DELETE:
                self.delete_zone()
            elif choice == ZoneMenuChoices.EXIT:
                break


    def list_zones(self) -> None:
        """List all configured zones with their status and record counts."""
        print_section("Current Zones")
        zones = self.db.get_all_zones()

        if not zones:
            print_info("No zones configured.")
            wait_for_enter()
            return

        for idx, row in enumerate(zones, start=1):
            self._display_zone_summary(idx, row_to_dict(row))

        wait_for_enter()


    def add_zone(self) -> None:
        """Add a new zone with provider API credentials.

        Prompts for zone details, confirms, auto-fetches zone ID and sets it up.
        """
        print_section("Add New Zone")
        zone_name = safe_input("Zone Name (e.g., example-zone.com): ").strip()
        if not zone_name:
            print_error("Zone name is required!")
            wait_for_enter()
            return

        if self.db.get_zone_by_name(zone_name):
            print_warning(f"Zone '{zone_name}' already exists!")
            print_info("Use option '3) Edit zone' to update API credentials.")
            wait_for_enter()
            return

        self._prompt_and_create_zone(zone_name)


    def edit_zone(self) -> None:
        """Edit an existing zone's settings."""
        print_section("Edit Zone")
        zone = select_zone(self.db, prompt="Select zone to edit")
        if not zone:
            return

        status_text = 'Enabled' if zone['enabled'] else 'Disabled'
        print_subsection("Current Zone")
        print(f"{Colors.BOLD}Name:{Colors.NC}   {Colors.CYAN}{zone['zone_name']}{Colors.NC}")
        print(f"{Colors.BOLD}Status:{Colors.NC} {Colors.GREEN if zone['enabled'] else Colors.DIM}{status_text}{Colors.NC}")

        self._print_edit_options()
        choice = safe_input("Enter your choice (0-3): ").strip()

        if choice == EditZoneMenuChoices.CHANGE_API_KEY:
            self._update_zone_api_key(zone)
        elif choice == EditZoneMenuChoices.CHANGE_SECRET:
            self._update_zone_secret(zone)
        elif choice == EditZoneMenuChoices.TOGGLE_IPV4_V6:
            self._toggle_zone_status(zone)

        wait_for_enter()


    def delete_zone(self) -> None:
        """Delete a zone with confirmation."""
        print_section("Delete Zone")
        zone = select_zone(self.db, prompt="Select zone to DELETE")
        if not zone:
            return

        records = self.db.get_records_by_zone(zone['id'], enabled_only=False)
        print_warning("WARNING: This will delete:")
        print(f"   {Colors.RED}*{Colors.NC} Zone: {Colors.BOLD}{zone['zone_name']}{Colors.NC}")
        print(f"   {Colors.RED}*{Colors.NC} {len(records)} DNS record(s)")
        print(f"   {Colors.RED}*{Colors.NC} All IP address history")
        print(f"   {Colors.RED}*{Colors.NC} All update history")

        confirm = safe_input(f"\n{Colors.BOLD}Type zone name to confirm deletion:{Colors.NC} ").strip()
        if confirm != zone['zone_name']:
            print_error("Zone name does not match. Deletion cancelled.")
            wait_for_enter()
            return

        try:
            self.db.delete_zone(zone['id'])
            print_success(f"Zone '{zone['zone_name']}' deleted successfully!")
        except (ValueError, TypeError) as e:
            print_error(f"Error deleting zone: {e}")
            self.logger.error(f"Failed to delete zone {zone['id']}: {e}")
        wait_for_enter()


    ############################################################################
    # Private Helper Methods
    ############################################################################

    def _print_zone_menu(self) -> None:
        """Print the options available in the zone menu."""
        print(f"{Colors.BLUE}Available options:{Colors.NC}")
        menu_items = list(MenuLabels.ZONE_MENU.values())
        for idx, item in enumerate(menu_items, start=1):
            print(f"  {idx}) {item}")
        print(f"  {ZoneMenuChoices.EXIT}) Back")
        print()


    def _display_zone_summary(self, idx: int, zone: Dict[str, Any]) -> None:
        """Display details for a single zone in the list view.

        Args:
            idx: Index of the zone in the list.
            zone: Dictionary representing the zone.
        """
        status = f"{Colors.GREEN}Enabled{Colors.NC}" if zone['enabled'] else f"{Colors.DIM}Disabled{Colors.NC}"
        print(f"\n{Colors.BOLD}{idx}) {zone['zone_name']}{Colors.NC} [{status}]")

        provider_zone_id = zone.get('provider_zone_id') or 'N/A'
        print(f"    Zone ID: {Colors.DIM}{provider_zone_id}{Colors.NC}")

        self._display_zone_dyndns_config(zone['id'])

        records = self.db.get_records_by_zone(zone['id'], enabled_only=False)
        record_count_color = Colors.GREEN if len(records) > 0 else Colors.DIM
        print(f"    Records: {record_count_color}{len(records)} configured{Colors.NC}")


    def _display_zone_dyndns_config(self, zone_id: int) -> None:
        """Display DynDNS settings for a zone.

        Args:
            zone_id: Database zone ID.
        """
        dyndns_row = self.db.get_dyndns_config_by_zone(zone_id)
        if not dyndns_row:
            return

        dyndns = row_to_dict(dyndns_row)
        bulk_id = dyndns.get('bulk_id') or 'N/A'
        print(f"    Bulk ID: {Colors.DIM}{bulk_id}{Colors.NC}")
        print(f"    API Key: {Colors.DIM}{'*' * CLIConfig.MASK_LENGTH} (encrypted){Colors.NC}")

        domains_field = dyndns.get('domains')
        if domains_field:
            try:
                domains = json.loads(domains_field) if isinstance(domains_field, str) else domains_field
                if domains:
                    print(f"    Domains: {Colors.DIM}{', '.join(domains)}{Colors.NC}")
            except (json.JSONDecodeError, ValueError, TypeError):
                pass


    def _prompt_and_create_zone(self, zone_name: str) -> None:
        """Prompt for credentials, confirm, and insert the new zone.

        Args:
            zone_name: The name of the zone to create.
        """
        provider_zone_id = safe_input("Zone ID (optional, leave empty to auto-fetch): ").strip()

        print_subsection("API Credentials")
        bulk_id = safe_input("Bulk ID: ").strip()

        print(f"{Colors.DIM}Paste your API Key below (input hidden, press Enter when done){Colors.NC}")
        api_key = getpass.getpass("API Key: ")

        if not bulk_id or not api_key:
            print_error("Bulk ID and API Key are required!")
            wait_for_enter()
            return

        self._confirm_and_save_zone(zone_name, provider_zone_id, bulk_id, api_key)


    def _confirm_and_save_zone(self, zone_name: str, provider_zone_id: str, bulk_id: str, api_key: str) -> None:
        """Confirm with the user and execute zone creation in DB and provider check.

        Args:
            zone_name: Zone name.
            provider_zone_id: Provider zone ID (optional).
            bulk_id: Bulk ID.
            api_key: API Key.
        """
        print_subsection("Confirmation")
        print(f"{Colors.BOLD}Zone Name:{Colors.NC}     {zone_name}")
        print(f"{Colors.BOLD}Zone ID:{Colors.NC}       {provider_zone_id if provider_zone_id else Colors.DIM + '(auto-fetch)' + Colors.NC}")
        print(f"{Colors.BOLD}Bulk ID:{Colors.NC}       {bulk_id}")
        print(f"{Colors.BOLD}API Key:{Colors.NC}       {Colors.DIM}{'*' * min(len(api_key), 64)} ({len(api_key)} chars, will be encrypted){Colors.NC}")

        if not confirm_action("Proceed with zone creation?", default=False):
            print_info("Cancelled.")
            wait_for_enter()
            return

        if not provider_zone_id:
            provider_zone_id = self._fetch_zone_id_from_provider(zone_name, bulk_id, api_key)

        self._execute_zone_creation(zone_name, provider_zone_id, bulk_id, api_key)
        wait_for_enter()


    def _fetch_zone_id_from_provider(self, zone_name: str, bulk_id: str, api_key: str) -> Optional[str]:
        """Fetch the zone ID from provider using the given credentials.

        Args:
            zone_name: The zone name to look up.
            bulk_id: Bulk ID.
            api_key: API Key.

        Returns:
            The provider zone ID if found, else None.
        """
        print_info("Fetching Zone ID from provider...")
        try:
            full_api_key = f"{bulk_id}.{api_key}"
            temp_client = ProviderDNSClient(
                api_key=full_api_key,
                config=self.config,
                logger=self.logger
            )
            provider_zones = temp_client.get_zones()
            if provider_zones:
                provider_zone = next(
                    (pz for pz in provider_zones if pz['name'] == zone_name),
                    None
                )
                if provider_zone:
                    print_success(f"Zone ID fetched: {provider_zone['id']}")
                    return provider_zone['id']
                print_warning(f"Zone '{zone_name}' not found at provider.")
            else:
                print_warning("Failed to fetch zones from provider - check credentials.")
        except DynDNSException as e:
            print_warning(f"Auto-fetch failed: {e}")

        print_info("Zone will be created locally. Zone ID can be synced later.")
        return None


    def _execute_zone_creation(self, zone_name: str, provider_zone_id: Optional[str], bulk_id: str, api_key: str) -> None:
        """Create the zone record and dyndns configuration in the database.

        Args:
            zone_name: Zone name.
            provider_zone_id: Provider zone ID.
            bulk_id: Bulk ID.
            api_key: API Key.
        """
        try:
            zone_id = self.db.add_zone(zone_name, provider_zone_id if provider_zone_id else None)
            if zone_id is None:
                raise DatabaseError("Failed to retrieve zone ID after insertion.")
            self.db.set_dyndns_config(
                zone_id=zone_id,
                bulk_id=bulk_id,
                api_key=api_key
            )
            print_success(f"Zone '{zone_name}' added successfully!")
            if provider_zone_id:
                print_info(f"Provider Zone ID: {provider_zone_id}")
            self._prompt_create_dyndns_records(zone_id, zone_name, provider_zone_id, bulk_id, api_key)
        except (ValueError, TypeError, DatabaseError) as e:
            print_error(f"Error adding zone: {e}")
            self.logger.error(f"Failed to add zone '{zone_name}': {e}")


    def _prompt_create_dyndns_records(self, zone_id: int, zone_name: str,
                                       provider_zone_id: Optional[str],
                                       bulk_id: str, api_key: str) -> None:
        """Prompt user to create standard DynDNS records after zone creation.

        Args:
            zone_id: Database zone ID for the new zone.
            zone_name: Zone name.
            provider_zone_id: Provider zone ID.
            bulk_id: IONOS Bulk ID.
            api_key: IONOS API Key.
        """
        print()
        print_section("DynDNS Records")
        print(f"{Colors.DIM}These records will be automatically updated when your IP changes.{Colors.NC}")
        print()
        self._print_record_setup_menu(zone_name)

        choice = safe_input("Enter your choice (0-2): ").strip()
        if choice == ZoneMenuChoices.EXIT:
            print_info("You can add records later via 'Records' > 'Add record'")
            return
        if choice not in ['1', '2']:
            print_warning("Invalid choice. Skipping record creation.")
            return

        self._create_selected_records(choice, zone_id, zone_name, provider_zone_id, bulk_id, api_key)


    def _print_record_setup_menu(self, zone_name: str) -> None:
        """Print the record setup options menu.

        Args:
            zone_name: Zone name.
        """
        print(f"{Colors.BLUE}Available options:{Colors.NC}")
        print(f"  {SetupMenuChoices.STANDARD}) Standard setup (recommended)")
        print(f"     {Colors.DIM}Creates A + AAAA records for:{Colors.NC}")
        print(f"     {Colors.DIM}- @ ({zone_name}){Colors.NC}")
        print(f"     {Colors.DIM}- www (www.{zone_name}){Colors.NC}")
        print(f"  {SetupMenuChoices.ROOT_ONLY}) Root domain only (@)")
        print(f"     {Colors.DIM}Creates A + AAAA for {zone_name}{Colors.NC}")
        print(f"  {SetupMenuChoices.SKIP}) Skip")
        print()


    def _create_selected_records(self, choice: str, zone_id: int, zone_name: str,
                                 provider_zone_id: Optional[str], bulk_id: str, api_key: str) -> None:
        """Determine and create the chosen records.

        Args:
            choice: User selection ('1' or '2').
            zone_id: Zone ID.
            zone_name: Zone name.
            provider_zone_id: Provider zone ID.
            bulk_id: Bulk ID.
            api_key: API Key.
        """
        subdomains = [Subdomain.ROOT, Subdomain.WWW] if choice == SetupMenuChoices.STANDARD else [Subdomain.ROOT]
        setup_name = "Standard setup" if choice == SetupMenuChoices.STANDARD else "Root domain only"

        if not provider_zone_id:
            print_warning("No Provider Zone ID available - records will be created locally only.")
            print_info("Sync with provider later to create records at IONOS.")

        print()
        print_info("Detecting current IP addresses...")
        current_ipv4, current_ipv6 = self._detect_ips()

        provider = self._init_provider_client(provider_zone_id, bulk_id, api_key)

        print()
        print_info(f"Creating {setup_name} records...")
        self._execute_records_creation(zone_id, zone_name, provider_zone_id, provider, subdomains, current_ipv4, current_ipv6)


    def _detect_ips(self) -> Tuple[Optional[str], Optional[str]]:
        """Detect current local and external IP addresses.

        Returns:
            Tuple containing detected IPv4 and IPv6 strings (or None).
        """
        try:
            network = NetworkData(config=self.config, logger=self.logger)
            current_ipv4, current_ipv6 = network.load_current_ip_addresses()
        except NetworkError as e:
            self.logger.warning(f"IP detection failed: {e}")
            current_ipv4, current_ipv6 = None, None

        if current_ipv4:
            print_success(f"IPv4: {current_ipv4}")
        else:
            print_warning("IPv4 not detected")

        if current_ipv6:
            print_success(f"IPv6: {current_ipv6}")
        else:
            print_warning("IPv6 not detected")

        return current_ipv4, current_ipv6


    def _init_provider_client(self, provider_zone_id: Optional[str], bulk_id: str, api_key: str) -> Optional[ProviderDNSClient]:
        """Initialize provider client if zone ID is available.

        Args:
            provider_zone_id: Provider zone ID.
            bulk_id: Bulk ID.
            api_key: API Key.

        Returns:
            ProviderDNSClient instance or None.
        """
        if not provider_zone_id:
            return None
        try:
            full_api_key = f"{bulk_id}.{api_key}"
            return ProviderDNSClient(
                api_key=full_api_key,
                config=self.config,
                logger=self.logger
            )
        except DynDNSException as e:
            self.logger.warning(f"Failed to create provider client: {e}")
            return None


    def _execute_records_creation(self, zone_id: int, zone_name: str, provider_zone_id: Optional[str],
                                  provider: Optional[ProviderDNSClient], subdomains: List[str],
                                  current_ipv4: Optional[str], current_ipv6: Optional[str]) -> None:
        """Create each subdomain record in DB and remotely.

        Args:
            zone_id: Zone database ID.
            zone_name: Zone name.
            provider_zone_id: Provider zone ID.
            provider: Provider client.
            subdomains: List of subdomains.
            current_ipv4: Detected IPv4.
            current_ipv6: Detected IPv6.
        """
        created, failed = 0, 0
        for subdomain in subdomains:
            name = zone_name if subdomain == Subdomain.ROOT else f"{subdomain}.{zone_name}"
            disp = f"{Subdomain.ROOT} ({zone_name})" if subdomain == Subdomain.ROOT else f"{subdomain} ({name})"

            if self.config.network_ipv4_enabled:
                succ = self._create_single_dyndns_record(
                    zone_id, zone_name, provider_zone_id, provider,
                    name, RecordType.A, current_ipv4, disp
                )
                created, failed = (created + 1, failed) if succ else (created, failed + 1)

            if self.config.network_ipv6_enabled:
                succ = self._create_single_dyndns_record(
                    zone_id, zone_name, provider_zone_id, provider,
                    name, RecordType.AAAA, current_ipv6, disp
                )
                created, failed = (created + 1, failed) if succ else (created, failed + 1)

        self._print_creation_summary(created, failed)


    def _print_creation_summary(self, created: int, failed: int) -> None:
        """Print summary of records created and failed.

        Args:
            created: Count of successfully created records.
            failed: Count of failed records.
        """
        print()
        if created > 0:
            print_success(f"{created} record(s) created successfully!")
        if failed > 0:
            print_warning(f"{failed} record(s) failed to create")
        if created > 0:
            print_info("The daemon will now automatically update these records when your IP changes.")


    def _create_single_dyndns_record(self, zone_id: int, zone_name: str,
                                      provider_zone_id: Optional[str],
                                      provider: Optional[ProviderDNSClient],
                                      record_name: str, record_type: str,
                                      current_ip: Optional[str],
                                      display_name: str) -> bool:
        """Create a single DynDNS record (A or AAAA) locally and remotely.

        Args:
            zone_id: Database zone ID.
            zone_name: Zone name.
            provider_zone_id: Provider zone ID.
            provider: Provider client.
            record_name: Full record name.
            record_type: Record type.
            current_ip: Current IP.
            display_name: Display name.

        Returns:
            True if successful, False otherwise.
        """
        if self.db.get_record_by_name_and_type(zone_id, record_name, record_type):
            print_info(f"  {display_name} {record_type}: Already exists, skipping")
            return True

        ip_to_use = current_ip if current_ip else get_placeholder_ip(record_type)
        provider_record_id, sync_status = self._sync_new_record_with_provider(
            provider, provider_zone_id, record_name, record_type, ip_to_use, display_name
        )

        return self._save_single_dyndns_record(
            zone_id, record_name, record_type, provider_record_id, sync_status, ip_to_use, current_ip, display_name
        )


    def _sync_new_record_with_provider(self, provider: Optional[ProviderDNSClient], provider_zone_id: Optional[str],
                                       record_name: str, record_type: str, ip_to_use: str, display_name: str) -> Tuple[Optional[str], str]:
        """Create the record on the provider and return provider_record_id and sync_status.

        Args:
            provider: Provider client.
            provider_zone_id: Provider zone ID.
            record_name: Record name.
            record_type: Record type.
            ip_to_use: IP address to set.
            display_name: Display name.

        Returns:
            Tuple of (provider_record_id, sync_status).
        """
        provider_record_id = None
        sync_status = SyncStatus.LOCAL_ONLY

        if not provider or not provider_zone_id:
            return provider_record_id, sync_status

        try:
            provider_record_id = provider.find_record_id(provider_zone_id, record_name, record_type)
            if provider_record_id:
                sync_status = SyncStatus.SYNCED
                print_info(f"  {display_name} {record_type}: Found at provider, importing...")
            else:
                api_record = provider.build_record_dict(
                    record_name=record_name, record_type=record_type,
                    content=ip_to_use, ttl=self.config.dns_default_ttl, disabled=False
                )
                if provider.create_records(provider_zone_id, [api_record]):
                    provider_record_id = provider.find_record_id(provider_zone_id, record_name, record_type)
                    sync_status = SyncStatus.SYNCED if provider_record_id else SyncStatus.PENDING_SYNC
        except DynDNSException as e:
            self.logger.warning(f"Provider operation failed for {record_name} {record_type}: {e}")

        return provider_record_id, sync_status


    def _save_single_dyndns_record(self, zone_id: int, record_name: str, record_type: str,
                                   provider_record_id: Optional[str], sync_status: str,
                                   ip_to_use: str, current_ip: Optional[str], display_name: str) -> bool:
        """Save the record locally in the database.

        Args:
            zone_id: Zone ID.
            record_name: Record name.
            record_type: Record type.
            provider_record_id: Provider record ID.
            sync_status: Sync status.
            ip_to_use: IP to use.
            current_ip: Current IP.
            display_name: Display name.

        Returns:
            True if saved successfully, False otherwise.
        """
        try:
            record_id = self.db.add_record(
                zone_id=zone_id, record_name=record_name, record_type=record_type,
                provider_record_id=provider_record_id, ttl=self.config.dns_default_ttl,
                enabled=True, managed=True, sync_status=sync_status
            )
            if record_id is None:
                raise DatabaseError("Failed to retrieve record ID after insertion.")

            if current_ip and current_ip != get_placeholder_ip(record_type):
                self.db.update_ip_address(record_id, current_ip)

            if sync_status == SyncStatus.SYNCED:
                print_success(f"  {display_name} {record_type}: Created and synced with provider")
            else:
                print_success(f"  {display_name} {record_type}: Created locally")
            return True
        except DynDNSException as e:
            self.logger.error(f"Failed to create record {record_name} ({record_type}): {e}")
            print_error(f"  {display_name} {record_type}: Failed - {e}")
            return False


    def _print_edit_options(self) -> None:
        """Print options for editing a zone."""
        print(f"\n{Colors.BOLD}What to edit?{Colors.NC}")
        print()
        print(f"{Colors.BLUE}Available options:{Colors.NC}")
        print(f"  {EditZoneMenuChoices.CHANGE_API_KEY}) {MenuLabels.EDIT_ZONE_MENU[EditZoneMenuChoices.CHANGE_API_KEY]}")
        print(f"  {EditZoneMenuChoices.CHANGE_SECRET}) {MenuLabels.EDIT_ZONE_MENU[EditZoneMenuChoices.CHANGE_SECRET]}")
        print(f"  {EditZoneMenuChoices.TOGGLE_IPV4_V6}) {MenuLabels.EDIT_ZONE_MENU[EditZoneMenuChoices.TOGGLE_IPV4_V6]}")
        print(f"  {EditZoneMenuChoices.EXIT}) Cancel")
        print()


    def _edit_zone_id(self, zone: Dict[str, Any]) -> None:
        """Update provider zone ID.

        Args:
            zone: Zone dictionary.
        """
        new_provider_id = safe_input(f"New Zone ID [{zone.get('provider_zone_id', '')}]: ").strip()
        if new_provider_id:
            self.db.update_zone(zone['id'], provider_zone_id=new_provider_id)
            print_success("Zone ID updated")


    def _edit_zone_credentials(self, zone: Dict[str, Any]) -> None:
        """Update zone provider credentials.

        Args:
            zone: Zone dictionary.
        """
        print_subsection("Update API Credentials")
        bulk_id = safe_input("New Bulk ID: ").strip()

        print(f"{Colors.DIM}Paste your new API Key (input hidden, press Enter when done){Colors.NC}")
        api_key = getpass.getpass("New API Key: ")

        if api_key:
            print_success(f"API Key received ({len(api_key)} characters)")
        else:
            print_warning("No API Key entered")

        if bulk_id and api_key:
            self.db.set_dyndns_config(zone_id=zone['id'], bulk_id=bulk_id, api_key=api_key)
            print_success("API credentials updated")


    def _toggle_zone_status(self, zone: Dict[str, Any]) -> None:
        """Toggle active/disabled status of a zone.

        Args:
            zone: Zone dictionary.
        """
        new_status = not zone['enabled']
        self.db.update_zone_status(zone['id'], new_status)
        status_text = "enabled" if new_status else "disabled"
        print_success(f"Zone {status_text}")