#!/usr/bin/env python3
"""RecordManager class implementing CRUD submenus and update actions for DNS records.

This module provides interactive submenus and helper methods for listing,
adding, editing, and deleting DNS records, as well as initiating forced updates.

Author: Manuel Ziel
License: MIT
"""

################################################################################
# IMPORTS & DEPENDENCIES
################################################################################

from datetime import datetime
from typing import Any, Dict, List, Optional

from src.core.exceptions import DatabaseError, RecordNotFoundError, ZoneNotFoundError, APIError, DynDNSException, NetworkError
from src.core.constants import SyncStatus, UpdateStatus, RecordType, Subdomain, PlaceholderIP, DatabaseDefaults, UpdateMethod
from src.cli.constants import RecordMenuChoices, EditRecordMenuChoices, CLIConfig, MenuLabels, ValidationLimits, SelectionChoices
from src.network import NetworkData
from src.api import ProviderDNSClient
from src.services.helpers.dyndns_helper import DynDNSBundleHandler
from src.utils.colors import Colors

from .helpers.input import (
    safe_input, confirm_action, wait_for_enter, select_zone, select_record, get_placeholder_ip, get_valid_int
)
from .helpers.output import (
    print_success, print_error, print_warning, print_info,
    print_section, print_subsection, clear_screen, row_to_dict
)


################################################################################
# RECORD MANAGER CLASS
################################################################################

class RecordManager:
    """Manager class for interactive DNS records management.

    Handles listing, creation, modification, deletion, provider synchronization
    and manual forced updates of DNS records.

    Attributes:
        config: ConfigManager instance with settings.
        logger: Logger instance for system journal logs.
        db: DatabaseManager instance for SQLite operations.
    """

    def __init__(self, config: Any, logger: Any, db: Any) -> None:
        """Initialize RecordManager.

        Args:
            config: ConfigManager instance.
            logger: Logger instance.
            db: DatabaseManager instance.
        """
        self.config = config
        self.logger = logger
        self.db = db

    def manage_records(self) -> None:
        """Display and handle the record management submenu."""
        while True:
            clear_screen()
            print_section("Manage DNS Records")
            print(f"\n{Colors.DIM}DNS Records define which domains/subdomains are managed by DynDNS.{Colors.NC}")
            print(f"{Colors.DIM}Each record will be automatically updated with your current IP address.{Colors.NC}\n")
            print(f"{Colors.BLUE}Available options:{Colors.NC}")

            menu_items = list(MenuLabels.RECORD_MENU.values())
            for i, item in enumerate(menu_items, 1):
                print(f"  {i}) {item}")
            print("  0) Back\n")

            choice = safe_input(f"Enter your choice (0-{len(menu_items)}): ").strip()
            if choice == RecordMenuChoices.EXIT:
                break
            self._handle_record_menu_choice(choice)


    def list_records(self) -> None:
        """List DNS records by zone with current IP addresses."""
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


    def add_record(self) -> None:
        """Add a new DNS record using provider-first approach."""
        print_section("Add DNS Record")
        zone = select_zone(self.db, prompt="Select zone")
        if not zone:
            return

        self._print_dns_record_explanation(zone['zone_name'])
        subdomain = safe_input(f"\n{Colors.BOLD}Enter subdomain{Colors.NC} (or @ for root): ").strip()
        record_name = zone['zone_name'] if subdomain in [Subdomain.ROOT, ''] else f"{subdomain}.{zone['zone_name']}"

        record_type = safe_input(f"{Colors.BOLD}Record Type{Colors.NC} (A for IPv4, AAAA for IPv6) [A]: ").strip().upper()
        record_type = record_type if RecordType.is_supported(record_type) else RecordType.A

        if self._check_record_exists_locally(zone['id'], record_name, record_type):
            return

        ttl_str = safe_input(f"{Colors.BOLD}TTL{Colors.NC} in seconds [{self.config.dns_default_ttl}]: ").strip()
        ttl = int(ttl_str) if ttl_str.isdigit() else self.config.dns_default_ttl

        self._execute_record_addition_flow(zone, record_name, record_type, ttl)


    def edit_record(self) -> None:
        """Edit an existing DNS record's TTL or enabled status."""
        print_section("Edit Record")
        zone = select_zone(self.db, prompt="Select zone")
        if not zone:
            return
        record_row = select_record(self.db, zone['id'], prompt="Select record to edit")
        if not record_row:
            return

        record = row_to_dict(record_row)
        self._print_current_record_details(record)

        print(f"\n{Colors.BOLD}What to edit?{Colors.NC}\n")
        print(f"{Colors.BLUE}Available options:{Colors.NC}")
        menu_items = list(MenuLabels.EDIT_RECORD_MENU.values())
        for i, item in enumerate(menu_items, 1):
            print(f"  {i}) {item}")
        print("  0) Cancel\n")

        choice = safe_input(f"Enter your choice (0-{len(menu_items)}): ").strip()
        self._execute_record_edit_choice(choice, zone, record)
        wait_for_enter()


    def delete_record(self) -> None:
        """Delete a DNS record from database and provider."""
        print_section("Delete Record")
        zone = select_zone(self.db, prompt="Select zone")
        if not zone:
            return
        record_row = select_record(self.db, zone['id'], prompt="Select record to DELETE")
        if not record_row:
            return

        record = row_to_dict(record_row)
        self._print_delete_warnings(record)

        if not confirm_action(f"Really delete record '{record['record_name']}'?", default=False):
            print_info("Cancelled.")
            wait_for_enter()
            return

        self._execute_record_deletion(zone, record)
        wait_for_enter()


    def sync_zone_from_provider(self) -> None:
        """Sync records from provider - compare provider state with local database."""
        print_section("Sync Records from Provider")
        zone = select_zone(self.db, prompt="Select zone to sync")
        if not zone:
            return

        provider = self._get_provider_with_credentials(zone, warn_on_missing=True, require_zone_id=False)
        if not provider:
            wait_for_enter()
            return

        zone = self._ensure_provider_zone_id_on_sync(zone, provider)
        if not zone:
            wait_for_enter()
            return

        self._reconcile_zone_records(zone, provider)
        wait_for_enter()


    def force_dns_update(self) -> None:
        """Force immediate DNS update for all enabled records."""
        print_section("Force DNS Update")
        print(f"\n{Colors.YELLOW}WARNING{Colors.NC}")
        print(f"{Colors.DIM}This will immediately update ALL enabled DNS records with current IP addresses.{Colors.NC}")
        print(f"{Colors.DIM}Use this when records are out of sync or manually deleted.{Colors.NC}\n")

        if not confirm_action("Force update all DNS records now?", default=False):
            print_info("Cancelled.")
            wait_for_enter()
            return

        print()
        if confirm_action("Sync records with provider first?", default=True):
            self._pre_sync_all_enabled_zones()

        network = self._detect_ip_addresses()
        if not network:
            wait_for_enter()
            return

        zones = self.db.get_all_enabled_zones()
        if not zones:
            print_warning("No enabled zones found.")
            wait_for_enter()
            return

        print_subsection("Processing DNS Records")
        stats = self._process_all_zones(zones, network)
        self._display_update_summary(stats)
        wait_for_enter()


    ############################################################################
    # Private Helper Methods
    ############################################################################

    def _handle_record_menu_choice(self, choice: str) -> None:
        """Handle record menu choices.

        Args:
            choice: Selected menu option.
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


    def _print_zone_selection_list(self, zones_list: List[Dict[str, Any]]) -> None:
        """Print zones list for selection.

        Args:
            zones_list: List of zones dictionaries.
        """
        print(f"\n{Colors.BOLD}Select Zone:{Colors.NC}")
        for idx, z in enumerate(zones_list, start=1):
            status = f"{Colors.GREEN}Enabled{Colors.NC}" if z['enabled'] else f"{Colors.DIM}Disabled{Colors.NC}"
            print(f" {idx}) {z['zone_name']:<{CLIConfig.ZONE_NAME_WIDTH}} [{status}]")
        print(f" {SelectionChoices.ALL}) All zones")


    def _list_all_zones_records(self, zones_list: List[Dict[str, Any]]) -> None:
        """List records for all zones.

        Args:
            zones_list: List of zone dictionaries.
        """
        for z in zones_list:
            records = self.db.get_records_by_zone(z['id'], enabled_only=False)
            if records:
                print(f"\n{Colors.CYAN}═══ {z['zone_name']} ═══{Colors.NC}")
                self._print_records_list(records)


    def _list_single_zone_records(self, choice_str: str, zones_list: List[Dict[str, Any]]) -> None:
        """List records for a selected zone.

        Args:
            choice_str: User's choice index.
            zones_list: List of zone dictionaries.
        """
        if not choice_str.isdigit():
            print_error("Invalid choice")
            return

        idx = int(choice_str)
        if idx < 1 or idx > len(zones_list):
            print_error(f"Select 1-{len(zones_list)}")
            return

        z = zones_list[idx - 1]
        records = self.db.get_records_by_zone(z['id'], enabled_only=False)
        if not records:
            print_info(f"No records configured for {z['zone_name']}")
            return

        print(f"\n{Colors.CYAN}═══ {z['zone_name']} ═══{Colors.NC}")
        self._print_records_list(records, show_ip=True)


    def _print_records_list(self, records: List[Any], show_ip: bool = False) -> None:
        """Print details of a list of records.

        Args:
            records: List of record rows/dicts.
            show_ip: Whether to fetch and print the IP address from DB.
        """
        for idx, r_row in enumerate(records, start=1):
            r = row_to_dict(r_row)
            status = f"{Colors.GREEN}Enabled{Colors.NC}" if r.get('enabled', True) else f"{Colors.DIM}Disabled{Colors.NC}"
            ttl = r.get('ttl', self.config.dns_default_ttl)
            print(f"  {idx:3d}. {r['record_name']:{CLIConfig.RECORD_NAME_WIDTH}s} {r['record_type']:{CLIConfig.RECORD_TYPE_WIDTH}s} TTL:{ttl:5d} [{status}]")
            if show_ip:
                ip_row = self.db.get_ip_address(r['id'])
                if ip_row:
                    ip_info = row_to_dict(ip_row)
                    if ip_info.get('ip_address'):
                        print(f"     └─ Current IP: {ip_info['ip_address']}")


    def _print_dns_record_explanation(self, zone_name: str) -> None:
        """Print details and examples about DNS records.

        Args:
            zone_name: The name of the zone.
        """
        print(f"\n{Colors.BOLD}Zone:{Colors.NC} {Colors.CYAN}{zone_name}{Colors.NC}\n")
        print(f"{Colors.BOLD}What is a DNS Record?{Colors.NC}")
        print(f"{Colors.DIM}A DNS record points a domain/subdomain to an IP address.{Colors.NC}")
        print(f"{Colors.DIM}DynDNS will automatically update this record when your IP changes.{Colors.NC}\n")
        print(f"{Colors.BOLD}Common examples:{Colors.NC}")
        print(f"  • Root domain:      {Colors.BOLD}@{Colors.NC} or leave empty -> {zone_name}")
        print(f"  • WWW subdomain:    {Colors.BOLD}www{Colors.NC} -> www.{zone_name}")
        print(f"  • Mail subdomain:   {Colors.BOLD}mail{Colors.NC} -> mail.{zone_name}")


    def _check_record_exists_locally(self, zone_id: int, record_name: str, record_type: str) -> bool:
        """Check if a record already exists in database.

        Args:
            zone_id: Database zone ID.
            record_name: Record name.
            record_type: Record type.

        Returns:
            True if exists, False otherwise.
        """
        existing = self.db.get_record_by_name_and_type(zone_id, record_name, record_type)
        if existing:
            print_warning(f"Record '{record_name}' ({record_type}) already exists in database!")
            print_info("Use option '3) Edit record' to update TTL or status.")
            wait_for_enter()
            return True
        return False


    def _execute_record_addition_flow(self, zone: Dict[str, Any], record_name: str, record_type: str, ttl: int) -> None:
        """Execute confirmation and proceed with provider/local record addition.

        Args:
            zone: Zone dictionary.
            record_name: Record name.
            record_type: Record type.
            ttl: TTL value.
        """
        print_subsection("Confirmation")
        print(f"{Colors.BOLD}Record Name:{Colors.NC} {Colors.GREEN}{record_name}{Colors.NC}")
        print(f"{Colors.BOLD}Record Type:{Colors.NC} {record_type}")
        print(f"{Colors.BOLD}TTL:{Colors.NC}         {ttl} seconds")

        if not confirm_action("Create this record?", default=False):
            print_info("Cancelled.")
            wait_for_enter()
            return

        if self.config.dns_update_method == UpdateMethod.DYNDNS:
            self._add_record_dyndns_mode(zone['id'], record_name, record_type, ttl)
            return

        provider = self._get_provider_with_credentials(zone, warn_on_missing=True, require_zone_id=True)
        if not provider:
            self._add_record_locally_only(zone['id'], record_name, record_type, ttl)
        else:
            self._add_record_with_provider_flow(zone, provider, record_name, record_type, ttl)


    def _add_record_dyndns_mode(self, zone_id: int, record_name: str, record_type: str, ttl: int) -> None:
        """Add record locally and synchronize the native DynDNS bundle on provider.

        Args:
            zone_id: Database zone ID.
            record_name: Record name.
            record_type: Record type.
            ttl: TTL value.
        """
        try:
            record_id = self.db.add_record(
                zone_id=zone_id, record_name=record_name, record_type=record_type,
                ttl=ttl, managed=True, sync_status=SyncStatus.SYNCED
            )
            if record_id is None:
                raise DatabaseError("Failed to insert record into database")
            print_success(f"Record added locally! (ID: {record_id})")
            self._sync_dyndns_bundle_if_needed(zone_id)
        except (ValueError, TypeError, DatabaseError) as e:
            print_error(f"Error adding record: {e}")
            self.logger.error(f"Failed to add record '{record_name}': {e}")
        wait_for_enter()


    def _add_record_locally_only(self, zone_id: int, record_name: str, record_type: str, ttl: int) -> None:
        """Add record in local mode only.

        Args:
            zone_id: Database zone ID.
            record_name: Record name.
            record_type: Record type.
            ttl: TTL value.
        """
        print_info("Record will be created in database only (local mode).")
        if not confirm_action("Continue without provider sync?", default=False):
            print_info("Cancelled.")
            wait_for_enter()
            return

        try:
            record_id = self.db.add_record(
                zone_id=zone_id,
                record_name=record_name,
                record_type=record_type,
                ttl=ttl,
                managed=True,
                sync_status=SyncStatus.LOCAL_ONLY
            )
            if record_id is None:
                raise DatabaseError("Failed to insert record into database")
            print_success(f"Record added locally! (ID: {record_id})")
            print_warning("Note: Record not created at provider. Configure API credentials to sync.")
        except (ValueError, TypeError, DatabaseError) as e:
            print_error(f"Error adding record: {e}")
            self.logger.error(f"Failed to add record '{record_name}': {e}")
        wait_for_enter()


    def _add_record_with_provider_flow(self, zone: Dict[str, Any], provider: ProviderDNSClient, record_name: str, record_type: str, ttl: int) -> None:
        """Reconcile and add record through the provider API.

        Args:
            zone: Zone dictionary.
            provider: Provider client.
            record_name: Record name.
            record_type: Record type.
            ttl: TTL value.
        """
        print_info("Checking if record exists at provider...")
        existing_provider_id = provider.find_record_id(
            zone_id=zone['provider_zone_id'],
            record_name=record_name,
            record_type=record_type
        )
        if existing_provider_id:
            self._import_existing_provider_record(zone, provider, existing_provider_id, record_name, record_type, ttl)
        else:
            self._create_new_provider_record_workflow(zone, provider, record_name, record_type, ttl)
        wait_for_enter()


    def _import_existing_provider_record(self, zone: Dict[str, Any], provider: ProviderDNSClient, provider_id: str, record_name: str, record_type: str, ttl: int) -> None:
        """Import a record that already exists at the provider.

        Args:
            zone: Zone dictionary.
            provider: Provider client.
            provider_id: Provider record ID.
            record_name: Record name.
            record_type: Record type.
            ttl: TTL value.
        """
        print_warning(f"Record '{record_name}' ({record_type}) already exists at provider!")
        print_info(f"Provider Record ID: {provider_id}")

        if not confirm_action("Import this existing record to database?", default=True):
            print_info("Cancelled. Use 'Sync records from provider' to import existing records.")
            return

        try:
            record_id = self.db.add_record(
                zone_id=zone['id'],
                record_name=record_name,
                record_type=record_type,
                provider_record_id=provider_id,
                ttl=ttl,
                enabled=True,
                managed=True,
                sync_status=SyncStatus.SYNCED
            )
            if record_id is None:
                raise DatabaseError("Failed to insert record into database")
            print_success(f"Existing record imported! (ID: {record_id})")
            self._fetch_and_store_provider_record_ip(zone['provider_zone_id'], provider, provider_id, record_id)
        except (ValueError, TypeError, DatabaseError) as e:
            print_error(f"Error importing record: {e}")
            self.logger.error(f"Failed to import record '{record_name}': {e}")


    def _fetch_and_store_provider_record_ip(self, provider_zone_id: str, provider: ProviderDNSClient, provider_record_id: str, record_id: int) -> None:
        """Fetch IP of existing provider record and save to database.

        Args:
            provider_zone_id: Provider zone ID.
            provider: Provider client.
            provider_record_id: Provider record ID.
            record_id: Local record database ID.
        """
        try:
            records = provider.get_zone_records(provider_zone_id)
            if records:
                for rec in records:
                    if rec.get('id') == provider_record_id:
                        ip = rec.get('content', '')
                        if ip and ip not in [PlaceholderIP.IPV4, PlaceholderIP.IPV6]:
                            self.db.update_ip_address(record_id, ip)
                            print_info(f"Current IP stored: {ip}")
                        break
        except ZoneNotFoundError as e:
            print_warning(f"Could not fetch current IP from provider: {e}")
            self.logger.warning(f"Zone not found when fetching records: {e}")


    def _create_new_provider_record_workflow(self, zone: Dict[str, Any], provider: ProviderDNSClient, record_name: str, record_type: str, ttl: int) -> None:
        """Detect IP, create record at provider and save to DB.

        Args:
            zone: Zone dictionary.
            provider: Provider client.
            record_name: Record name.
            record_type: Record type.
            ttl: TTL value.
        """
        print_info("Detecting current IP address...")
        network = NetworkData(config=self.config, logger=self.logger)
        network.load_current_ip_addresses()

        current_ip = network.ipv4_address if record_type == RecordType.A else network.ipv6_address
        if not current_ip:
            placeholder = get_placeholder_ip(record_type)
            print_warning(f"{record_type} not detected! Using placeholder {placeholder}")
            current_ip = placeholder
        else:
            print_success(f"Using {record_type}: {current_ip}")

        self._execute_provider_record_creation(zone, provider, record_name, record_type, current_ip, ttl)


    def _execute_provider_record_creation(self, zone: Dict[str, Any], provider: ProviderDNSClient, record_name: str, record_type: str, current_ip: str, ttl: int) -> None:
        """Send the record creation API request and record results in DB.

        Args:
            zone: Zone dictionary.
            provider: Provider client.
            record_name: Record name.
            record_type: Record type.
            current_ip: IP to write.
            ttl: TTL value.
        """
        try:
            print_info("Creating record at provider...")
            api_record = provider.build_record_dict(record_name, record_type, current_ip, ttl, False)
            if not provider.create_records(zone['provider_zone_id'], [api_record]):
                raise APIError("Provider record creation failed")
            print_success("Record created at provider!")
            print_info("Syncing to retrieve provider record ID...")
            self._sync_zone_with_provider(zone, provider)
            prov_id = provider.find_record_id(zone['provider_zone_id'], record_name, record_type)
            record_id = self.db.add_record(
                zone_id=zone['id'], record_name=record_name, record_type=record_type,
                provider_record_id=prov_id, ttl=ttl, enabled=True, managed=True, sync_status=SyncStatus.SYNCED
            )
            if record_id is None:
                raise DatabaseError("Failed to insert record into database")
            if current_ip not in [PlaceholderIP.IPV4, PlaceholderIP.IPV6]:
                self.db.update_ip_address(record_id, current_ip)
                print_success(f"IP address stored: {current_ip}")
            print_success(f"Record added successfully! (ID: {record_id})")
            if prov_id:
                print_info(f"Provider Record ID: {prov_id}")
            else:
                print_warning("Note: Could not retrieve provider_record_id. Use 'Sync records from provider' to update.")
        except (ValueError, TypeError, KeyError, APIError, DatabaseError) as e:
            print_error(f"Error creating record: {e}")
            self.logger.error(f"Failed to create record '{record_name}': {e}")
            print_warning("Record may have been created at provider but not in local database.")
            print_info("Use 'Sync records from provider' to reconcile.")


    def _print_current_record_details(self, record: Dict[str, Any]) -> None:
        """Print current details of the record.

        Args:
            record: Record dictionary.
        """
        status_color = Colors.GREEN if record.get('enabled', True) else Colors.DIM
        status_text = 'Enabled' if record.get('enabled', True) else 'Disabled'
        print_subsection("Current Record")
        print(f"{Colors.BOLD}Name:{Colors.NC}   {Colors.CYAN}{record['record_name']}{Colors.NC}")
        print(f"{Colors.BOLD}Type:{Colors.NC}   {record['record_type']}")
        print(f"{Colors.BOLD}TTL:{Colors.NC}    {record.get('ttl', self.config.dns_default_ttl)} seconds")
        print(f"{Colors.BOLD}Status:{Colors.NC} {status_color}{status_text}{Colors.NC}")


    def _execute_record_edit_choice(self, choice: str, zone: Dict[str, Any], record: Dict[str, Any]) -> None:
        """Execute selected edit choice.

        Args:
            choice: Selected menu option.
            zone: Zone dictionary.
            record: Record dictionary.
        """
        if choice == EditRecordMenuChoices.TTL:
            self._edit_record_ttl(zone, record)
        elif choice == EditRecordMenuChoices.STATUS:
            self._edit_record_status(zone, record)
        elif choice == EditRecordMenuChoices.EXIT:
            print_info("Cancelled.")
        else:
            print_error("Invalid choice!")


    def _edit_record_ttl(self, zone: Dict[str, Any], record: Dict[str, Any]) -> None:
        """Change record TTL locally and optionally sync.

        Args:
            zone: Zone dictionary.
            record: Record dictionary.
        """
        current_ttl = record.get('ttl', self.config.dns_default_ttl)
        default_ttl = self.config.dns_default_ttl
        print(f"\n{Colors.BOLD}TTL Guidelines:{Colors.NC}")
        print(f"  • {Colors.BOLD}{ValidationLimits.TTL_MIN}{Colors.NC}     = 1 minute  {Colors.DIM}(frequent updates){Colors.NC}")
        print(f"  • {Colors.BOLD}300{Colors.NC}    = 5 minutes")
        print(f"  • {Colors.BOLD}{default_ttl}{Colors.NC}   = 1 hour    {Colors.GREEN}(recommended){Colors.NC}")
        print(f"  • {Colors.BOLD}{ValidationLimits.TTL_MAX}{Colors.NC}  = 24 hours")

        new_ttl = get_valid_int(
            prompt=f"\nNew TTL in seconds [current: {current_ttl}]",
            default=current_ttl, min_val=ValidationLimits.TTL_MIN, max_val=ValidationLimits.TTL_MAX
        )
        if new_ttl and new_ttl != current_ttl:
            self._confirm_and_update_ttl(zone, record, new_ttl)
        else:
            print_info("No change.")


    def _confirm_and_update_ttl(self, zone: Dict[str, Any], record: Dict[str, Any], new_ttl: int) -> None:
        """Confirm and execute TTL update.

        Args:
            zone: Zone dictionary.
            record: Record dictionary.
            new_ttl: The target TTL.
        """
        if not confirm_action(f"Update TTL to {new_ttl} seconds?", default=False):
            print_info("Cancelled.")
            return
        try:
            self.db.update_record(record['id'], ttl=new_ttl)
            print_success(f"TTL updated to {new_ttl} seconds in database!\n")
            print_info("TTL change will be applied at provider during next DNS update.")

            if confirm_action("Sync TTL to provider immediately?", default=False):
                self._sync_ttl_to_provider(zone, record, new_ttl)
        except (ValueError, TypeError, DatabaseError) as e:
            print_error(f"Error updating record: {e}")
            self.logger.error(f"Failed to update record {record['id']}: {e}")


    def _sync_ttl_to_provider(self, zone: Dict[str, Any], record: Dict[str, Any], new_ttl: int) -> None:
        """Sync the updated TTL to the DNS provider.

        Args:
            zone: Zone dictionary.
            record: Record dictionary.
            new_ttl: The updated TTL.
        """
        provider = self._get_provider_with_credentials(zone, warn_on_missing=True, require_zone_id=True)
        if not provider:
            print_warning("Cannot sync to provider without credentials.")
            return

        try:
            if not record.get('provider_record_id'):
                raise APIError("Record has no provider_record_id")

            ip_info_row = self.db.get_ip_address(record['id'])
            current_ip = PlaceholderIP.IPV4
            if ip_info_row:
                ip_info = row_to_dict(ip_info_row)
                if ip_info.get('ip_address'):
                    current_ip = ip_info['ip_address']

            print_info("Updating TTL at provider...")
            success = provider.update_record(
                zone_id=zone['provider_zone_id'], record_id=record['provider_record_id'],
                content=current_ip, ttl=new_ttl
            )
            if success:
                print_success("TTL synced to provider successfully!")
            else:
                print_warning("Failed to sync TTL to provider")
        except (ValueError, TypeError, KeyError, APIError) as e:
            print_error(f"Error syncing TTL: {e}")
            self.logger.error(f"Failed to sync TTL for record {record['id']}: {e}")


    def _edit_record_status(self, zone: Dict[str, Any], record: Dict[str, Any]) -> None:
        """Enable or disable record with bidirectional sync.

        Args:
            zone: Zone dictionary.
            record: Record dictionary.
        """
        current_status = record.get('enabled', True)
        new_status = not current_status
        action = "enable" if new_status else "disable"

        print(f"\n{Colors.YELLOW}WARNING{Colors.NC}")
        print(f"Bidirectional sync: This will {action} the record at provider AND in database.")
        if new_status:
            print_info("  • Record will be recreated at provider")
            print_info("  • Database will be updated with new provider_record_id")
        else:
            print_info("  • Record will be deleted from provider")
            print_info("  • Database record kept for history (enabled=0)\n")

        if not confirm_action(f"Really {action} this record?", default=False):
            print_info("Cancelled.")
            return

        provider = self._get_provider_with_credentials(zone, warn_on_missing=True, require_zone_id=True)
        if not provider:
            self._local_only_record_toggle(record['id'], new_status, action)
        else:
            self._sync_record_toggle_with_provider(zone, provider, record, new_status, action)


    def _local_only_record_toggle(self, record_id: int, new_status: bool, action: str) -> None:
        """Toggle status locally without provider.

        Args:
            record_id: Database record ID.
            new_status: Target status.
            action: Action name ('enable' / 'disable').
        """
        print_info("Record will be updated in database only (local mode).")
        if not confirm_action("Continue without provider sync?", default=False):
            print_info("Cancelled.")
            return
        try:
            self.db.update_record(record_id, enabled=new_status)
            print_success(f"Record {action}d locally!")
            print_warning("Note: Provider not updated. Configure API credentials to sync.")
        except (ValueError, TypeError, DatabaseError) as e:
            print_error(f"Error updating record: {e}")
            self.logger.error(f"Failed to {action} record {record_id}: {e}")


    def _sync_record_toggle_with_provider(self, zone: Dict[str, Any], provider: ProviderDNSClient, record: Dict[str, Any], new_status: bool, action: str) -> None:
        """Toggle record state and sync with provider.

        Args:
            zone: Zone dictionary.
            provider: Provider client.
            record: Record dictionary.
            new_status: Target status.
            action: Action name ('enable' / 'disable').
        """
        try:
            if new_status:
                self._enable_record_at_provider(zone, provider, record)
            else:
                self._disable_record_at_provider(zone, provider, record)
        except (ValueError, TypeError, KeyError, APIError, DatabaseError) as e:
            print_error(f"Error during {action}: {e}")
            self.logger.error(f"Failed to {action} record {record['id']}: {e}")
            print_warning("Record state may be inconsistent. Use 'Sync records from provider' to reconcile.")


    def _enable_record_at_provider(self, zone: Dict[str, Any], provider: ProviderDNSClient, record: Dict[str, Any]) -> None:
        """Recreate record at provider and mark as enabled in DB.

        Args:
            zone: Zone dictionary.
            provider: Provider client.
            record: Record dictionary.
        """
        print_info("Enabling: Creating record at provider...")
        current_ip = self._get_current_or_detect_ip(record)
        api_record = provider.build_record_dict(
            record['record_name'], record['record_type'], current_ip,
            record.get('ttl', self.config.dns_default_ttl), False
        )
        success = provider.create_records(zone['provider_zone_id'], [api_record])
        if not success:
            raise APIError("Failed to recreate record at provider")

        print_success(f"Record created at provider with IP {current_ip}!")
        self._sync_zone_with_provider(zone, provider)
        new_prov_id = provider.find_record_id(zone['provider_zone_id'], record['record_name'], record['record_type'])

        self.db.update_record(record['id'], enabled=True, provider_record_id=new_prov_id, sync_status=SyncStatus.SYNCED)
        if new_prov_id:
            print_success(f"Record enabled! (Provider ID: {new_prov_id})")
        else:
            print_success("Record enabled!")
            print_warning("Note: Could not retrieve provider_record_id. Use 'Sync records from provider' to update.")


    def _disable_record_at_provider(self, zone: Dict[str, Any], provider: ProviderDNSClient, record: Dict[str, Any]) -> None:
        """Delete record at provider and mark as disabled in DB.

        Args:
            zone: Zone dictionary.
            provider: Provider client.
            record: Record dictionary.
        """
        if record.get('provider_record_id'):
            print_info("Disabling: Deleting record from provider...")
            if provider.delete_record(zone['provider_zone_id'], record['provider_record_id']):
                print_success("Record deleted from provider!")
            else:
                print_warning("Failed to delete from provider (may not exist)")
        else:
            print_info("No provider_record_id - skipping provider deletion")

        self.db.update_record(record['id'], enabled=False, provider_record_id=None, sync_status=SyncStatus.LOCAL_ONLY)
        print_success("Record disabled! (kept in database for history)")


    def _print_delete_warnings(self, record: Dict[str, Any]) -> None:
        """Print warnings prior to record deletion.

        Args:
            record: Record dictionary.
        """
        print_warning("WARNING: This will delete:")
        print(f"   {Colors.RED}•{Colors.NC} Record: {Colors.BOLD}{record['record_name']}{Colors.NC} ({record['record_type']})")
        print(f"   {Colors.RED}•{Colors.NC} From local database")
        print(f"   {Colors.RED}•{Colors.NC} From DNS provider (if exists)")
        print(f"   {Colors.RED}•{Colors.NC} IP address history")
        print(f"   {Colors.RED}•{Colors.NC} Update history")


    def _execute_record_deletion(self, zone: Dict[str, Any], record: Dict[str, Any]) -> None:
        """Delete the record from the provider and DB.

        Args:
            zone: Zone dictionary.
            record: Record dictionary.
        """
        try:
            if record.get('provider_record_id'):
                provider = self._get_provider_with_credentials(zone, warn_on_missing=False, require_zone_id=False)
                if provider and zone.get('provider_zone_id'):
                    print_info("Deleting record from provider...")
                    if provider.delete_record(zone['provider_zone_id'], record['provider_record_id']):
                        print_success("Deleted from provider")
                    else:
                        print_warning("Failed to delete from provider (record may not exist)")
                else:
                    print_warning("Cannot delete from provider (missing credentials or zone ID)")

            self.db.delete_record(record['id'])
            print_success(f"Record '{record['record_name']}' deleted successfully!")
            if self.config.dns_update_method == UpdateMethod.DYNDNS:
                self._sync_dyndns_bundle_if_needed(zone['id'])
        except (ValueError, TypeError, APIError, DatabaseError) as e:
            print_error(f"Error deleting record: {e}")
            self.logger.error(f"Failed to delete record {record['id']}: {e}")


    def _ensure_provider_zone_id_on_sync(self, zone: Dict[str, Any], provider: ProviderDNSClient) -> Optional[Dict[str, Any]]:
        """Ensure provider zone ID exists during sync, fetch it if missing.

        Args:
            zone: Zone dictionary.
            provider: Provider client.

        Returns:
            Updated zone dictionary, or None if failed.
        """
        if not zone.get('provider_zone_id'):
            print_info("Zone has no provider_zone_id - fetching from provider...")
            if not self._sync_zone_id(zone, provider):
                print_error("Failed to fetch provider_zone_id from provider.")
                return None
            zone_row = self.db.get_zone_by_id(zone['id'])
            if not zone_row:
                print_error("Failed to reload zone after sync.")
                return None
            return row_to_dict(zone_row)
        return zone


    def _reconcile_zone_records(self, zone: Dict[str, Any], provider: ProviderDNSClient) -> None:
        """Fetch and reconcile records between provider and database.

        Args:
            zone: Zone dictionary.
            provider: Provider client.
        """
        try:
            print_info(f"Fetching records from provider for zone '{zone['zone_name']}'...")
            provider_records = provider.get_zone_records(zone['provider_zone_id'])
            if provider_records is None:
                print_error("Failed to fetch records from provider")
                return

            local_records = self.db.get_records_by_zone(zone['id'], enabled_only=False)
            local_records_dict = {row_to_dict(r)['id']: row_to_dict(r) for r in local_records}

            stats = {SyncStatus.SYNCED: 0, SyncStatus.NEW: 0, SyncStatus.ORPHANED: 0, SyncStatus.UPDATED: 0}
            matched_local_ids = self._match_provider_to_local_records(provider_records, local_records_dict, stats)

            self._mark_orphaned_local_records(local_records_dict, matched_local_ids, stats)
            self._print_sync_results_summary(stats)
        except ZoneNotFoundError as e:
            print_error(f"Zone not found at provider: {e}")
            self.logger.error(f"Zone not found during sync: {e}")
        except (ValueError, KeyError, TypeError, DatabaseError) as e:
            print_error(f"Error during zone sync: {e}")
            self.logger.error(f"Failed to sync zone {zone['id']}: {e}")


    def _match_provider_to_local_records(self, provider_records: List[Dict[str, Any]], local_records_dict: Dict[int, Dict[str, Any]], stats: Dict[str, int]) -> set:
        """Compare provider records against local database and update matches.

        Args:
            provider_records: List of provider records.
            local_records_dict: Dict mapping local ID to local record dict.
            stats: Statistics tracker.

        Returns:
            Set of matched local record IDs.
        """
        matched_local_ids = set()
        print_info(f"Analyzing {len(provider_records)} provider records...\n")

        for p_rec in provider_records:
            matched = False
            for l_id, l_rec in local_records_dict.items():
                if l_rec['record_name'] == p_rec['name'] and l_rec['record_type'] == p_rec['type']:
                    matched = True
                    matched_local_ids.add(l_id)

                    if l_rec.get('provider_record_id') != p_rec['id'] or l_rec.get('sync_status') != SyncStatus.SYNCED:
                        self.db.update_record(
                            l_id, provider_record_id=p_rec['id'], sync_status=SyncStatus.SYNCED,
                            last_synced_at=datetime.now().strftime(DatabaseDefaults.DB_TIMESTAMP_FORMAT)
                        )
                        stats[SyncStatus.UPDATED] += 1
                        print_success(f"  Synced: {p_rec['name']} ({p_rec['type']})")
                    else:
                        stats[SyncStatus.SYNCED] += 1
                    break
            if not matched:
                stats[SyncStatus.NEW] += 1
                print_info(f"  New at provider: {p_rec['name']} ({p_rec['type']}) - ID: {p_rec['id']}")
        return matched_local_ids


    def _mark_orphaned_local_records(self, local_records_dict: Dict[int, Dict[str, Any]], matched_local_ids: set, stats: Dict[str, int]) -> None:
        """Mark local records as orphaned if they don't exist at provider.

        Args:
            local_records_dict: Dict of local records.
            matched_local_ids: Set of matched local IDs.
            stats: Statistics tracker.
        """
        for l_id, l_rec in local_records_dict.items():
            if l_id not in matched_local_ids:
                if l_rec.get('sync_status') != SyncStatus.ORPHANED:
                    self.db.update_sync_status(
                        l_id, sync_status=SyncStatus.ORPHANED,
                        last_synced_at=datetime.now().strftime(DatabaseDefaults.DB_TIMESTAMP_FORMAT)
                    )
                stats[SyncStatus.ORPHANED] += 1
                print_warning(f"  Orphaned: {l_rec['record_name']} ({l_rec['record_type']}) - Not found at provider")


    def _print_sync_results_summary(self, stats: Dict[str, int]) -> None:
        """Print results overview of the synchronization process.

        Args:
            stats: Synchronisation statistics dictionary.
        """
        print()
        print_subsection("Sync Statistics")
        print(f"  {Colors.GREEN}Already synced:{Colors.NC}  {stats[SyncStatus.SYNCED]}")
        print(f"  {Colors.GREEN}Updated:{Colors.NC}         {stats[SyncStatus.UPDATED]}")
        print(f"  {Colors.BLUE}New at provider:{Colors.NC} {stats[SyncStatus.NEW]}")
        print(f"  {Colors.YELLOW}Orphaned:{Colors.NC}        {stats[SyncStatus.ORPHANED]}\n")

        if stats[SyncStatus.NEW] > 0:
            print_info("Note: 'New at provider' records exist remotely but not locally.")
            print_info("      Use 'Add record' to import them if needed.\n")
        if stats[SyncStatus.ORPHANED] > 0:
            print_warning("Warning: 'Orphaned' records exist locally but not at provider.")
            print_warning("         They may have been deleted remotely.\n")
        print_success("Zone sync completed!")


    def _pre_sync_all_enabled_zones(self) -> None:
        """Sync all enabled zones with provider prior to updating."""
        print_subsection("Pre-Sync: Syncing Zones from Provider")
        zones_to_sync = self.db.get_all_enabled_zones()
        if not zones_to_sync:
            print_warning("No enabled zones to sync.")
            return

        synced_count = 0
        failed_count = 0
        for zone_row in zones_to_sync:
            zone = row_to_dict(zone_row)
            provider = self._get_provider_with_credentials(zone, warn_on_missing=False, require_zone_id=True)
            if provider:
                print_info(f"Syncing zone: {zone['zone_name']}...")
                stats = self._sync_zone_with_provider(zone, provider)
                if stats and stats.get(SyncStatus.SYNCED, 0) > 0:
                    synced_count += stats.get(SyncStatus.SYNCED, 0)
                    print_success(f"{zone['zone_name']}: {stats.get(SyncStatus.SYNCED, 0)} records synced")
                else:
                    failed_count += 1
                    print_warning(f"{zone['zone_name']}: Sync failed or no records")
            else:
                print_warning(f"{zone['zone_name']}: Skipped (no credentials)")

        print(f"\n{Colors.GREEN}✓{Colors.NC} Synced: {synced_count} records")
        if failed_count > 0:
            print(f"{Colors.YELLOW}!{Colors.NC} Failed: {failed_count} zones")
        print()


    def _detect_ip_addresses(self) -> Optional[NetworkData]:
        """Detect current public IP addresses.

        Returns:
            NetworkData instance or None if detection failed.
        """
        print_subsection("Detecting Current IP Addresses")
        try:
            network = NetworkData(config=self.config, logger=self.logger)
            network.load_current_ip_addresses()

            if network.ipv4_address:
                print_success(f"IPv4: {network.ipv4_address}")
            else:
                print_warning("IPv4: Not detected")

            if network.ipv6_address:
                print_success(f"IPv6: {network.ipv6_address}")
            else:
                print_warning("IPv6: Not detected")

            if not network.ipv4_address and not network.ipv6_address:
                print_error("No IP addresses detected! Cannot proceed.")
                return None
            return network
        except NetworkError as e:
            print_error(f"Failed to detect IP addresses: {e}")
            self.logger.error(f"IP detection failed in force update: {e}")
            return None


    def _process_all_zones(self, zones: List[Any], network: NetworkData) -> Dict[str, int]:
        """Process all zones and update DNS records.

        Args:
            zones: List of zone database rows.
            network: NetworkData instance.

        Returns:
            Dict of statistics.
        """
        stats = {UpdateStatus.TOTAL: 0, UpdateStatus.UPDATED: 0, UpdateStatus.FAILED: 0, UpdateStatus.SKIPPED: 0}
        for zone_row in zones:
            zone = row_to_dict(zone_row)
            dyndns_config = self.db.get_dyndns_config_by_zone(zone['id'])
            if not dyndns_config:
                print_warning(f"Zone '{zone['zone_name']}' has no API credentials - skipping")
                continue

            provider = self._create_provider_client(zone, row_to_dict(dyndns_config))
            if not provider:
                continue

            zone = self._ensure_provider_zone_id_on_process(zone, provider)
            if not zone:
                continue

            print(f"\n{Colors.BOLD}Zone: {zone['zone_name']}{Colors.NC}")
            self._process_zone_records(zone, provider, network, stats)
        return stats


    def _ensure_provider_zone_id_on_process(self, zone: Dict[str, Any], provider: ProviderDNSClient) -> Optional[Dict[str, Any]]:
        """Sync provider_zone_id if missing during update process.

        Args:
            zone: Zone dictionary.
            provider: Provider client.

        Returns:
            Updated zone dictionary, or None if failed.
        """
        if not zone.get('provider_zone_id'):
            print_info(f"Syncing zone '{zone['zone_name']}' with provider...")
            if not self._sync_zone_id(zone, provider):
                print_error(f"Failed to sync zone '{zone['zone_name']}' - skipping")
                return None
            zone_row = self.db.get_zone_by_id(zone['id'])
            if zone_row:
                return row_to_dict(zone_row)
        return zone


    def _create_provider_client(self, zone: Dict[str, Any], dyndns: Dict[str, Any]) -> Optional[ProviderDNSClient]:
        """Create provider API client from zone credentials.

        Args:
            zone: Zone dictionary.
            dyndns: DynDNS configuration dictionary.

        Returns:
            ProviderDNSClient instance or None.
        """
        try:
            api_key = f"{dyndns['bulk_id']}.{dyndns['api_key']}"
            return ProviderDNSClient(api_key=api_key, config=self.config, logger=self.logger)
        except DynDNSException as e:
            print_error(f"Failed to initialize API client for zone '{zone['zone_name']}': {e}")
            self.logger.error(f"Provider client creation failed for zone {zone['id']}: {e}")
            return None


    def _get_provider_with_credentials(self, zone: Dict[str, Any], warn_on_missing: bool = True, require_zone_id: bool = True) -> Optional[ProviderDNSClient]:
        """Get provider client with credentials validation.

        Args:
            zone: Zone dictionary.
            warn_on_missing: Whether to print warnings.
            require_zone_id: Whether to require provider_zone_id.

        Returns:
            ProviderDNSClient instance or None.
        """
        dyndns_config = self.db.get_dyndns_config_by_zone(zone['id'])
        if not dyndns_config:
            if warn_on_missing:
                print_warning("No API credentials configured for this zone.")
                print_info("Configure API credentials to enable provider sync.")
            return None

        provider = self._create_provider_client(zone, row_to_dict(dyndns_config))
        if not provider:
            if warn_on_missing:
                print_error("Failed to create provider client")
            return None

        if require_zone_id and not zone.get('provider_zone_id'):
            if not self._sync_and_update_zone_credentials(zone, provider, warn_on_missing):
                return None
        return provider


    def _sync_and_update_zone_credentials(self, zone: Dict[str, Any], provider: ProviderDNSClient, warn_on_missing: bool) -> bool:
        """Sync zone ID and update the passed zone dict.

        Args:
            zone: Zone dictionary to update.
            provider: Provider client.
            warn_on_missing: Whether to show warnings.

        Returns:
            True if successful, False otherwise.
        """
        if warn_on_missing:
            print_info(f"Zone '{zone['zone_name']}' has no provider_zone_id - fetching from provider...")
        if self._sync_zone_id(zone, provider):
            zone_row = self.db.get_zone_by_id(zone['id'])
            if zone_row:
                zone.update(row_to_dict(zone_row))
                return True
        if warn_on_missing:
            print_error("Failed to sync/reload provider_zone_id from provider")
        return False


    def _sync_zone_id(self, zone: Dict[str, Any], provider: ProviderDNSClient) -> bool:
        """Sync provider_zone_id for a zone by fetching from provider API.

        Args:
            zone: Zone dictionary.
            provider: Provider client.

        Returns:
            True if successful, False otherwise.
        """
        try:
            provider_zones = provider.get_zones()
            if not provider_zones:
                raise APIError("Failed to fetch zones from provider")

            provider_zone = next((pz for pz in provider_zones if pz['name'] == zone['zone_name']), None)
            if not provider_zone:
                raise ZoneNotFoundError(f"Zone '{zone['zone_name']}' not found in provider")

            self.db.update_zone(zone['id'], provider_zone_id=provider_zone['id'])
            print_success("Synced zone with provider")
            self.logger.info(f"Synced provider_zone_id for zone {zone['zone_name']}: {provider_zone['id']}")
            return True
        except (APIError, ZoneNotFoundError, DatabaseError, KeyError, TypeError) as e:
            print_error(f"Zone sync failed: {e}")
            self.logger.error(f"Failed to sync zone {zone['zone_name']}: {e}")
            return False


    def _sync_zone_with_provider(self, zone: Dict[str, Any], provider: ProviderDNSClient) -> Dict[str, int]:
        """Sync all records in a zone with provider to update provider_record_ids.

        Args:
            zone: Zone dictionary.
            provider: Provider client.

        Returns:
            Dict with sync statistics.
        """
        stats = {SyncStatus.SYNCED: 0, UpdateStatus.FAILED: 0}
        try:
            if not zone.get('provider_zone_id'):
                raise APIError(f"Zone '{zone['zone_name']}' has no provider_zone_id")
            provider_records = provider.get_zone_records(zone['provider_zone_id'])
            if not provider_records:
                raise APIError("Failed to fetch records from provider")

            local_records = self.db.get_records_by_zone(zone['id'], enabled_only=False)
            self._reconcile_local_records_to_provider(local_records, provider_records, zone['zone_name'], stats)
            return stats
        except (ZoneNotFoundError, APIError, DatabaseError, ValueError, KeyError, TypeError) as e:
            self.logger.error(f"Failed to sync zone records with provider: {e}")
            return {}


    def _reconcile_local_records_to_provider(self, local_records: List[Any], provider_records: List[Dict[str, Any]], zone_name: str, stats: Dict[str, int]) -> None:
        """Compare local records against provider records to reconcile IDs.

        Args:
            local_records: List of local record rows.
            provider_records: List of provider records.
            zone_name: Name of the zone.
            stats: Statistics dictionary.
        """
        for local_row in local_records:
            local = row_to_dict(local_row)
            matched = False
            for p_rec in provider_records:
                if p_rec['name'] == local['record_name'] and p_rec['type'] == local['record_type']:
                    self.db.update_record(
                        local['id'], provider_record_id=p_rec['id'], sync_status=SyncStatus.SYNCED,
                        last_synced_at=datetime.now().strftime(DatabaseDefaults.DB_TIMESTAMP_FORMAT)
                    )
                    stats[SyncStatus.SYNCED] += 1
                    matched = True
                    break
            if not matched:
                self._mark_local_record_as_orphaned(local)
                stats[UpdateStatus.FAILED] += 1
        self.logger.info(f"Synced {stats[SyncStatus.SYNCED]} records for zone '{zone_name}'")


    def _mark_local_record_as_orphaned(self, record: Dict[str, Any]) -> None:
        """Mark local record as orphaned if it has provider_record_id.

        Args:
            record: Record dictionary.
        """
        if record.get('provider_record_id'):
            self.logger.info(f"Record '{record['record_name']}' ({record['record_type']}) not found at provider - marking orphaned")
            self.db.update_record(record['id'], provider_record_id=None, sync_status=SyncStatus.ORPHANED)


    def _sync_dyndns_bundle_if_needed(self, zone_id: int) -> None:
        """Synchronize native DynDNS bundle domains with provider after local record modifications.

        Args:
            zone_id: Database zone ID.
        """
        if self.config.dns_update_method != UpdateMethod.DYNDNS:
            return

        zone = self.db.get_zone_by_id(zone_id)
        dyndns_config = self.db.get_dyndns_config_by_zone(zone_id)
        if not zone or not dyndns_config:
            return

        zone_dict = dict(zone)
        provider = self._create_provider_client(zone_dict, dict(dyndns_config))
        if not provider:
            return

        try:
            network = NetworkData(config=self.config, logger=self.logger)
            network.load_current_ip_addresses()
            handler = DynDNSBundleHandler(self.config, self.db, network, self.logger)
            print_info(f"Synchronizing DynDNS bundle on provider for '{zone_dict['zone_name']}'...")
            update_url = handler.sync_or_activate_dyndns_bundle(provider, zone_dict, force_sync=True)
            if update_url and provider.execute_dyndns_update_url(
                update_url, ipv4=network.ipv4_address, ipv6=network.ipv6_address
            ):
                print_success("Synchronized DynDNS bundle and verified updateUrl on provider.")
        except DynDNSException as e:
            print_warning(f"Failed to synchronize DynDNS bundle: {e}")


    def _process_zone_records(self, zone: Dict[str, Any], provider: ProviderDNSClient, network: NetworkData, stats: Dict[str, int]) -> None:
        """Process all records for a specific zone.

        Args:
            zone: Zone dictionary.
            provider: Provider client.
            network: NetworkData instance.
            stats: Statistics dictionary.
        """
        records = self.db.get_records_by_zone(zone['id'], enabled_only=True)
        if not records:
            return

        if self.config.dns_update_method == UpdateMethod.DYNDNS:
            if self._process_dyndns_zone_records(zone, records, provider, network, stats):
                return

        for record_row in records:
            record = row_to_dict(record_row)
            stats[UpdateStatus.TOTAL] += 1

            new_ip = self._get_target_ip(record, network)
            if not new_ip:
                print_warning(f"  {record['record_name']} ({record['record_type']}) - No IP available")
                stats[UpdateStatus.SKIPPED] += 1
                continue

            old_ip = self._get_current_ip(record)
            if not self._ensure_provider_record_id(record, provider):
                stats[UpdateStatus.FAILED] += 1
                continue

            if self._update_dns_record(record, provider, old_ip, new_ip):
                stats[UpdateStatus.UPDATED] += 1
            else:
                stats[UpdateStatus.FAILED] += 1


    def _process_dyndns_zone_records(
        self,
        zone: Dict[str, Any],
        records: List[Dict[str, Any]],
        provider: ProviderDNSClient,
        network: NetworkData,
        stats: Dict[str, int],
    ) -> bool:
        """Process zone records using native DynDNS bundle updateUrl.

        Args:
            zone: Zone dictionary.
            records: List of enabled record dictionaries for the zone.
            provider: Provider client.
            network: NetworkData instance.
            stats: Statistics dictionary.

        Returns:
            True if handled via DynDNS updateUrl, False to fall back to REST.
        """
        if not self.db.get_dyndns_config_by_zone(zone['id']):
            return False

        handler = DynDNSBundleHandler(self.config, self.db, network, self.logger)
        print_info(f"Verifying/synchronizing DynDNS bundle for '{zone['zone_name']}'...")
        update_url = handler.sync_or_activate_dyndns_bundle(provider, zone)
        if not update_url:
            return False

        print_info("Executing native DynDNS update via updateUrl...")
        if not provider.execute_dyndns_update_url(
            update_url, ipv4=network.ipv4_address, ipv6=network.ipv6_address
        ):
            print_warning("Native DynDNS updateUrl request failed. Falling back to REST API record updates.")
            return False

        print_success("Native DynDNS update URL executed successfully.")
        self._apply_dyndns_record_updates(records, network, stats)
        return True


    def _apply_dyndns_record_updates(
        self, records: List[Dict[str, Any]], network: NetworkData, stats: Dict[str, int]
    ) -> None:
        """Update local IP state and audit history after successful DynDNS bundle update.

        Args:
            records: List of enabled record dictionaries.
            network: NetworkData instance.
            stats: Statistics dictionary.
        """
        for record_row in records:
            record = row_to_dict(record_row)
            stats[UpdateStatus.TOTAL] += 1
            new_ip = self._get_target_ip(record, network)
            if new_ip:
                old_ip = self._get_current_ip(record)
                self.db.update_ip_address(record['id'], new_ip, changed=True)
                self.db.log_dns_update(record['id'], old_ip, new_ip, UpdateStatus.SUCCESS)
                stats[UpdateStatus.UPDATED] += 1
                print_success(f"  Updated {record['record_name']} ({record['record_type']}) -> {new_ip}")
            else:
                stats[UpdateStatus.SKIPPED] += 1


    def _get_target_ip(self, record: Dict[str, Any], network: NetworkData) -> Optional[str]:
        """Get target IP address for record type.

        Args:
            record: Record dictionary.
            network: NetworkData instance.

        Returns:
            IP address string or None.
        """
        if record['record_type'] == RecordType.A:
            return network.ipv4_address
        elif record['record_type'] == RecordType.AAAA:
            return network.ipv6_address
        else:
            print_warning(f"{record['record_name']} ({record['record_type']}) - Unsupported record type")
            return None


    def _get_current_ip(self, record: Dict[str, Any]) -> Optional[str]:
        """Get current IP from database for record.

        Args:
            record: Record dictionary.

        Returns:
            IP address string or None.
        """
        ip_info_row = self.db.get_ip_address(record['id'])
        if ip_info_row:
            ip_info = row_to_dict(ip_info_row)
            return ip_info.get('ip_address')
        return None


    def _get_current_or_detect_ip(self, record: Dict[str, Any]) -> str:
        """Get current IP from database or detect new IP address.

        Args:
            record: Record dictionary.

        Returns:
            IP address string.
        """
        current_ip = self._get_current_ip(record)
        if current_ip:
            return current_ip

        print_info(f"Detecting current {record['record_type']} address...")
        net = NetworkData(
            config=self.config, logger=self.logger,
            ipv4_enabled=(record['record_type'] == RecordType.A),
            ipv6_enabled=(record['record_type'] == RecordType.AAAA)
        )
        if record['record_type'] == RecordType.A:
            current_ip = net.get_current_public_ipv4_address()
        else:
            current_ip = net.get_current_public_ipv6_address()

        if not current_ip:
            placeholder = get_placeholder_ip(record['record_type'])
            print_warning(f"Could not detect {record['record_type']} address. Using placeholder {placeholder}")
            return placeholder

        print_success(f"Detected {record['record_type']}: {current_ip}")
        return current_ip


    def _ensure_provider_record_id(self, record: Dict[str, Any], provider: ProviderDNSClient) -> bool:
        """Ensure record has provider_record_id, sync or create if missing.

        Args:
            record: Record dictionary.
            provider: Provider client.

        Returns:
            True if record has valid ID, False otherwise.
        """
        if record.get('provider_record_id'):
            return True

        print_info(f"{record['record_name']} ({record['record_type']}) - Syncing with provider...")
        try:
            zone_row = self.db.get_zone_by_id(record['zone_id'])
            if not zone_row:
                raise ZoneNotFoundError(f"Zone {record['zone_id']} not found")
            zone = row_to_dict(zone_row)
            if not zone.get('provider_zone_id'):
                raise APIError(f"Zone '{zone['zone_name']}' has no provider_zone_id")

            provider_record_id = provider.find_record_id(zone['provider_zone_id'], record['record_name'], record['record_type'])
            if provider_record_id:
                self.db.update_record(record['id'], provider_record_id=provider_record_id)
                record['provider_record_id'] = provider_record_id
                return True

            return self._create_provider_record_and_update(record, zone, provider)
        except (ValueError, KeyError, TypeError, APIError, ZoneNotFoundError, DatabaseError) as e:
            print_error(f"{record['record_name']} ({record['record_type']}) - Sync failed: {e}")
            self.logger.error(f"Provider sync failed for record {record['id']}: {e}")
            return False


    def _create_provider_record_and_update(self, record: Dict[str, Any], zone: Dict[str, Any], provider: ProviderDNSClient) -> bool:
        """Create a DNS record in the provider and update local DB.

        Args:
            record: Record dictionary.
            zone: Zone dictionary.
            provider: Provider client.

        Returns:
            True if successful, False otherwise.
        """
        print_warning(f"{record['record_name']} ({record['record_type']}) - Not found in provider, creating...")
        if self._create_provider_record(record, zone, provider):
            provider_record_id = provider.find_record_id(zone['provider_zone_id'], record['record_name'], record['record_type'])
            if provider_record_id:
                self.db.update_record(record['id'], provider_record_id=provider_record_id)
                record['provider_record_id'] = provider_record_id
                print_success(f"{record['record_name']} ({record['record_type']}) - Created successfully")
                return True
        print_error(f"{record['record_name']} ({record['record_type']}) - Failed to create record in provider")
        return False


    def _create_provider_record(self, record: Dict[str, Any], zone: Dict[str, Any], provider: ProviderDNSClient) -> bool:
        """Create a DNS record in the provider.

        Args:
            record: Record dictionary.
            zone: Zone dictionary.
            provider: Provider client.

        Returns:
            True if successful, False otherwise.
        """
        try:
            content = get_placeholder_ip(record['record_type'])
            api_record = provider.build_record_dict(
                record['record_name'], record['record_type'], content,
                record.get('ttl', self.config.dns_default_ttl), not record.get('enabled', True)
            )
            success = provider.create_records(zone['provider_zone_id'], [api_record])
            if success:
                self.logger.info(f"Created record '{record['record_name']}' ({record['record_type']}) in provider zone {zone['zone_name']}")
                return True
            self.logger.error("Provider API returned failure for record creation")
            return False
        except (ValueError, KeyError, TypeError, APIError) as e:
            self.logger.error(f"Failed to create record '{record['record_name']}': {e}")
            return False


    def _update_dns_record(self, record: Dict[str, Any], provider: ProviderDNSClient, old_ip: Optional[str], new_ip: str) -> bool:
        """Update DNS record via provider API with automatic error recovery.

        Args:
            record: Record dictionary.
            provider: Provider client.
            old_ip: Previous IP address or None.
            new_ip: New IP address to set.

        Returns:
            True if successful, False otherwise.
        """
        try:
            zone_row = self.db.get_zone_by_id(record['zone_id'])
            if not zone_row:
                raise ZoneNotFoundError(f"Zone {record['zone_id']} not found")
            zone = row_to_dict(zone_row)
            if not zone.get('provider_zone_id') or not record.get('provider_record_id'):
                raise APIError("Missing provider_zone_id or provider_record_id")

            try:
                success = provider.update_record(
                    zone_id=zone['provider_zone_id'], record_id=record['provider_record_id'],
                    content=new_ip, ttl=record.get('ttl', self.config.dns_default_ttl)
                )
                if not success:
                    raise APIError("Provider API update failed")
            except RecordNotFoundError:
                return self._recreate_and_update_dns_record(zone, record, provider, old_ip, new_ip)

            self._save_dns_update_success(record, old_ip, new_ip)
            return True
        except (ValueError, TypeError, APIError, ZoneNotFoundError, DatabaseError) as e:
            self._save_dns_update_failure(record, old_ip, new_ip, e)
            return False


    def _recreate_and_update_dns_record(self, zone: Dict[str, Any], record: Dict[str, Any], provider: ProviderDNSClient, old_ip: Optional[str], new_ip: str) -> bool:
        """Recreate and sync DNS record at provider.

        Args:
            zone: Zone dictionary.
            record: Record dictionary.
            provider: Provider client.
            old_ip: Previous IP.
            new_ip: Target IP.

        Returns:
            True if successful, False otherwise.
        """
        print_warning(f"{record['record_name']} ({record['record_type']}) - Record not found at provider, recreating...")
        self.db.update_record_provider_id(record['id'], None)

        api_record = {
            "name": record['record_name'], "type": record['record_type'], "content": new_ip,
            "ttl": record.get('ttl', self.config.dns_default_ttl), "disabled": not record.get('enabled', True)
        }
        success = provider.create_records(zone['provider_zone_id'], [api_record])
        if not success:
            raise APIError("Failed to recreate record at provider")

        sync_stats = self._sync_zone_with_provider(zone, provider)
        if not sync_stats or sync_stats.get(SyncStatus.SYNCED, 0) == 0:
            raise APIError("Failed to sync after record recreation")

        self._save_dns_update_success(record, old_ip, new_ip)
        print_success(f"{record['record_name']} ({record['record_type']}) - Recreated and updated to {new_ip}")
        return True


    def _save_dns_update_success(self, record: Dict[str, Any], old_ip: Optional[str], new_ip: str) -> None:
        """Save successful IP update to database.

        Args:
            record: Record dictionary.
            old_ip: Previous IP.
            new_ip: Target IP.
        """
        self.db.update_ip_address(record_id=record['id'], ip_address=new_ip, changed=True)
        self.db.log_dns_update(record_id=record['id'], old_ip=old_ip, new_ip=new_ip, status=UpdateStatus.SUCCESS, error_message=None)
        print_success(f"{record['record_name']} ({record['record_type']}) - Updated to {new_ip}")


    def _save_dns_update_failure(self, record: Dict[str, Any], old_ip: Optional[str], new_ip: str, e: Exception) -> None:
        """Save failed IP update to database.

        Args:
            record: Record dictionary.
            old_ip: Previous IP.
            new_ip: Target IP.
            e: Caught exception.
        """
        print_error(f"{record['record_name']} ({record['record_type']}) - Update failed: {e}")
        self.db.log_dns_update(record_id=record['id'], old_ip=old_ip, new_ip=new_ip, status=UpdateStatus.FAILED, error_message=str(e))
        self.logger.error(f"DNS update failed for record {record['id']}: {e}")


    def _display_update_summary(self, stats: Dict[str, int]) -> None:
        """Display update summary statistics.

        Args:
            stats: Statistics dictionary.
        """
        print_subsection("Update Summary")
        print(f"{Colors.BOLD}Total records:{Colors.NC}    {stats[UpdateStatus.TOTAL]}")
        print(f"{Colors.GREEN}Updated:{Colors.NC}        {stats[UpdateStatus.UPDATED]}")
        print(f"{Colors.RED}Failed:{Colors.NC}         {stats[UpdateStatus.FAILED]}")
        print(f"{Colors.YELLOW}Skipped:{Colors.NC}        {stats[UpdateStatus.SKIPPED]}\n")

        if stats[UpdateStatus.UPDATED] > 0:
            print_success(f"Force update completed! {stats[UpdateStatus.UPDATED]} records updated.")
        elif stats[UpdateStatus.FAILED] > 0:
            print_error("Force update completed with errors. Check logs for details.")
        else:
            print_info("No records were updated.")