#!/usr/bin/env python3
"""
DynDNS CLI Configuration Module

Interactive menu system for managing DNS zones, records, and API credentials.
Provides CRUD operations for database entities and import/export functionality.

Created: 2025-10-27
Author: Manuel Ziel
License: MIT
"""

################################################################################
# IMPORTS & DEPENDENCIES
################################################################################

# Standard library imports
import getpass
import json
import os
import sys
from datetime import datetime
from typing import Optional, Dict, Any, List

# Local imports
from exceptions import DatabaseError, RecordNotFoundError, ZoneNotFoundError
from network import NetworkData
from api import ProviderDNSClient
from colors import LOG_SYMBOLS
from cli_helpers import (
    Colors,
    get_placeholder_ip,
    row_to_dict,
    print_success, print_error, print_warning, print_info,
    print_status_line, print_section, print_subsection, clear_screen,
    wait_for_enter, confirm_action, get_valid_int,
    select_zone, select_record
)

try:
    import yaml
except ImportError:
    yaml = None

################################################################################
# DYNDNS CONFIGURATION MENU
################################################################################

class ConfigMenu:
    """Interactive configuration menu for DynDNS zones and records management."""
    
    def __init__(self, config: Any, logger: Any) -> None:
        """Initialize configuration menu."""
        self.config = config
        self.logger = logger
        self.db = config.db
        
        if self.db is None:
            raise DatabaseError("Database not initialized. Run 'ionos-dyndns config' first.")
    
    def run(self) -> int:
        """Main menu loop."""
        while True:
            clear_screen()
            #self.print_header()
            max_choice = self.print_menu()
            
            choice = input(f"Enter your choice (0-{max_choice}): ").strip()
            
            try:
                if choice == '1':
                    self.manage_zones()
                elif choice == '2':
                    self.manage_records()
                elif choice == '3':
                    self.view_current_ips()
                elif choice == '4':
                    self.force_dns_update()
                elif choice == '5':
                    self.import_config()
                elif choice == '6':
                    self.export_config()
                elif choice == '0':
                    break
                else:
                    print_error("Invalid choice!")
                    wait_for_enter()
            except KeyboardInterrupt:
                print("\n\nOperation cancelled by user.")
                wait_for_enter()
            except (AttributeError, ValueError, TypeError) as e:
                print_error(f"Error: {e}")
                self.logger.error(f"Menu error: {e}")
                wait_for_enter()
        
        return 0
    
    ################################################################################
    # UI DISPLAY METHODS
    ################################################################################
    
    def print_header(self) -> None:
        """Print DynDNS banner."""

        #print_banner(
        #    software_name="[SOFTWARE_NAME]",
        #    mode="[Configuration]",
        #    description="[DESCRIPTION]",
        #    version="[VERSION]"
        #)

    def print_menu(self) -> None:
        """Print main menu options."""
        print_section("Configuration")
        print()
        print(f"{Colors.BLUE}Available options:{Colors.NC}")
        menu_items = [
            "Manage Zones (Domains)",
            "Manage DNS Records",
            "View Current IP Addresses",
            "Force DNS Update (Re-sync All Records)",
            "Import Configuration",
            "Export Configuration"
        ]
        for i, item in enumerate(menu_items, 1):
            print(f"  {i}) {item}")
        print(f"  0) Exit")
        print()
        return len(menu_items)
    
    ################################################################################
    # ZONE MANAGEMENT (CRUD OPERATIONS)
    ################################################################################
    
    def manage_zones(self) -> None:
        """Zone management submenu."""
        while True:
            clear_screen()
            print_section("Manage Zones")
            print()
            print(f"{Colors.DIM}Zones represent your root domains (e.g., example.com).{Colors.NC}")
            print(f"{Colors.DIM}Each zone requires provider API credentials for DynDNS updates.{Colors.NC}")
            print()
            print(f"{Colors.BLUE}Available options:{Colors.NC}")
            menu_items = [
                "List all zones",
                "Add new zone",
                "Edit zone",
                "Delete zone"
            ]
            for i, item in enumerate(menu_items, 1):
                print(f"  {i}) {item}")
            print(f"  0) Back")
            print()
            
            max_choice = len(menu_items)
            choice = input(f"Enter your choice (0-{max_choice}): ").strip()
            
            if choice == '1':
                self.list_zones()
            elif choice == '2':
                self.add_zone()
            elif choice == '3':
                self.edit_zone()
            elif choice == '4':
                self.delete_zone()
            elif choice == '0':
                break
    
    def list_zones(self) -> None:
        """List all configured zones."""
        print_section("Current Zones")
        
        zones = self.db.get_all_zones()
        
        if not zones:
            print_info("No zones configured.")
        else:
            for idx, row in enumerate(zones, start=1):
                z = row_to_dict(row)
                
                if z['enabled']:
                    status = f"{Colors.GREEN}{LOG_SYMBOLS['SUCCESS']} Enabled{Colors.NC}"
                else:
                    status = f"{Colors.DIM}{LOG_SYMBOLS['ERROR']} Disabled{Colors.NC}"
                
                print(f"\n{Colors.BOLD}{idx:2d}. {z['zone_name']}{Colors.NC} [{status}]")
                
                provider_zone_id = z.get('provider_zone_id') or 'N/A'
                print(f"    Zone ID: {Colors.DIM}{provider_zone_id}{Colors.NC}")
                
                dyndns_row = self.db.get_dyndns_config_by_zone(z['id'])
                if dyndns_row:
                    dyndns = row_to_dict(dyndns_row)
                    bulk_id = dyndns.get('bulk_id') or 'N/A'
                    print(f"    Bulk ID: {Colors.DIM}{bulk_id}{Colors.NC}")
                    print(f"    API Key: {Colors.DIM}{'*' * 20} (encrypted){Colors.NC}")
                    
                    domains_field = dyndns.get('domains')
                    if domains_field:
                        try:
                            domains = json.loads(domains_field) if isinstance(domains_field, str) else domains_field
                            if domains:
                                print(f"    Domains: {Colors.DIM}{', '.join(domains)}{Colors.NC}")
                        except (json.JSONDecodeError, ValueError, TypeError):
                            pass
                
                records = self.db.get_records_by_zone(z['id'], enabled_only=False)
                record_count_color = Colors.GREEN if len(records) > 0 else Colors.DIM
                print(f"    Records: {record_count_color}{len(records)} configured{Colors.NC}")
        
        wait_for_enter()
    
    def add_zone(self) -> None:
        """Add a new zone with provider credentials."""
        print_section("Add New Zone")

        zone_name = input("Zone Name (e.g., example-zone.com): ").strip()
        if not zone_name:
            print_error("Zone name is required!")
            wait_for_enter()
            return
        
        existing_zone = self.db.get_zone_by_name(zone_name)
        if existing_zone:
            print_warning(f"Zone '{zone_name}' already exists!")
            print_info("Use option '3) Edit zone' to update API credentials.")
            wait_for_enter()
            return
        
        provider_zone_id = input("Zone ID (optional, leave empty to auto-fetch): ").strip()
        
        print_subsection("API Credentials")
        bulk_id = input("Bulk ID: ").strip()
        
        print(f"{Colors.DIM}Paste your API Key below (input hidden, press Enter when done){Colors.NC}")
        api_key = getpass.getpass("API Key: ")
        
        if api_key:
            key_length = len(api_key)
            print(f"{Colors.GREEN}{LOG_SYMBOLS['SUCCESS']}{Colors.NC} API Key received ({key_length} characters)")
        else:
            print(f"{Colors.YELLOW}{LOG_SYMBOLS['ERROR']}{Colors.NC} No API Key entered")
        
        if not bulk_id or not api_key:
            print_error("Bulk ID and API Key are required!")
            wait_for_enter()
            return
        
        print_subsection("Confirmation")
        print(f"{Colors.BOLD}Zone Name:{Colors.NC}     {zone_name}")
        print(f"{Colors.BOLD}Zone ID:{Colors.NC}       {provider_zone_id if provider_zone_id else Colors.DIM + '(auto-fetch)' + Colors.NC}")
        print(f"{Colors.BOLD}Bulk ID:{Colors.NC}       {bulk_id}")
        print(f"{Colors.BOLD}API Key:{Colors.NC}       {Colors.DIM}{'*' * min(len(api_key), 64)} ({len(api_key)} chars, will be encrypted){Colors.NC}")
        
        if not confirm_action("Proceed with zone creation?", default=False):
            print_info("Cancelled.")
            wait_for_enter()
            return
        
        try:
            zone_id = self.db.add_zone(zone_name, provider_zone_id if provider_zone_id else None)
            
            self.db.set_dyndns_config(
                zone_id=zone_id,
                bulk_id=bulk_id,
                api_key=api_key
            )
            
            print_success(f"Zone '{zone_name}' added successfully! (ID: {zone_id})")
        except (ValueError, TypeError) as e:
            print_error(f"Error adding zone: {e}")
            self.logger.error(f"Failed to add zone '{zone_name}': {e}")
        
        wait_for_enter()
    
    def edit_zone(self) -> None:
        """Edit an existing zone."""
        print_section("Edit Zone")
        
        zone = select_zone(self.db, prompt="Select zone to edit")
        if not zone:
            return
        
        status_symbol = LOG_SYMBOLS['SUCCESS'] if zone['enabled'] else LOG_SYMBOLS['ERROR']
        status_color = Colors.GREEN if zone['enabled'] else Colors.DIM
        status_text = 'Enabled' if zone['enabled'] else 'Disabled'
        
        print_subsection("Current Zone")
        print(f"{Colors.BOLD}Name:{Colors.NC}   {Colors.CYAN}{zone['zone_name']}{Colors.NC}")
        print(f"{Colors.BOLD}Status:{Colors.NC} {status_color}{status_symbol} {status_text}{Colors.NC}")
        
        print(f"\n{Colors.BOLD}What to edit?{Colors.NC}")
        print()
        print(f"{Colors.BLUE}Available options:{Colors.NC}")
        menu_items = [
            "Update Zone ID",
            "Update API Credentials (Bulk ID + API Key)",
            "Enable/Disable Zone"
        ]
        for i, item in enumerate(menu_items, 1):
            print(f"  {i}) {item}")
        print(f"  0) Cancel")
        print()
        
        max_choice = len(menu_items)
        choice = input(f"Enter your choice (0-{max_choice}): ").strip()
        
        if choice == '1':
            new_provider_id = input(f"New Zone ID [{zone.get('provider_zone_id', '')}]: ").strip()
            if new_provider_id:
                self.db.update_zone(zone['id'], provider_zone_id=new_provider_id)
                print_success("Zone ID updated")
        
        elif choice == '2':
            print_subsection("Update API Credentials")
            bulk_id = input("New Bulk ID: ").strip()
            
            print(f"{Colors.DIM}Paste your new API Key (input hidden, press Enter when done){Colors.NC}")
            api_key = getpass.getpass("New API Key: ")
            
            if api_key:
                print(f"{Colors.GREEN}{LOG_SYMBOLS['SUCCESS']}{Colors.NC} API Key received ({len(api_key)} characters)")
            else:
                print(f"{Colors.YELLOW}{LOG_SYMBOLS['ERROR']}{Colors.NC} No API Key entered")
            
            if bulk_id and api_key:
                self.db.set_dyndns_config(
                    zone_id=zone['id'],
                    bulk_id=bulk_id,
                    api_key=api_key
                )
                print_success("API credentials updated")
        
        elif choice == '3':
            new_status = not zone['enabled']
            self.db.update_zone_status(zone['id'], new_status)
            status_text = "enabled" if new_status else "disabled"
            print_success(f"Zone {status_text}")
        
        wait_for_enter()
    
    def delete_zone(self) -> None:
        """Delete a zone (with confirmation)."""
        print_section("Delete Zone")
        
        zone = select_zone(self.db, prompt="Select zone to DELETE")
        if not zone:
            return
        
        records = self.db.get_records_by_zone(zone['id'], enabled_only=False)
        
        print_warning("WARNING: This will delete:")
        print(f"   {Colors.RED}{LOG_SYMBOLS['BULLET']}{Colors.NC} Zone: {Colors.BOLD}{zone['zone_name']}{Colors.NC}")
        print(f"   {Colors.RED}{LOG_SYMBOLS['BULLET']}{Colors.NC} {len(records)} DNS record(s)")
        print(f"   {Colors.RED}{LOG_SYMBOLS['BULLET']}{Colors.NC} All IP address history")
        print(f"   {Colors.RED}{LOG_SYMBOLS['BULLET']}{Colors.NC} All update history")
        
        confirm = input(f"\n{Colors.BOLD}Type zone name to confirm deletion:{Colors.NC} ").strip()
        
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
    
    ################################################################################
    # RECORD MANAGEMENT (CRUD OPERATIONS)
    ################################################################################
    
    def manage_records(self) -> None:
        """Record management submenu."""
        while True:
            clear_screen()
            print_section("Manage DNS Records")
            print()
            print(f"{Colors.DIM}DNS Records define which domains/subdomains are managed by DynDNS.{Colors.NC}")
            print(f"{Colors.DIM}Each record will be automatically updated with your current IP address.{Colors.NC}")
            print()
            print(f"{Colors.BLUE}Available options:{Colors.NC}")
            menu_items = [
                "List all records",
                "Add new record",
                "Edit record",
                "Delete record",
                "Sync records from provider"
            ]
            for i, item in enumerate(menu_items, 1):
                print(f"  {i}) {item}")
            print(f"  0) Back")
            print()
            
            max_choice = len(menu_items)
            choice = input(f"Enter your choice (0-{max_choice}): ").strip()
            
            if choice == '1':
                self.list_records()
            elif choice == '2':
                self.add_record()
            elif choice == '3':
                self.edit_record()
            elif choice == '4':
                self.delete_record()
            elif choice == '5':
                self.sync_zone_from_provider()
            elif choice == '0':
                break
    
    def list_records(self) -> None:
        """List DNS records by zone."""
        print_section("DNS Records")
        
        zones = self.db.get_all_zones()
        if not zones:
            print_info("No zones configured.")
            wait_for_enter()
            return
        
        print(f"\n{Colors.BOLD}Select Zone:{Colors.NC}")
        zones_list = [row_to_dict(z) for z in zones]
        for idx, z_dict in enumerate(zones_list, start=1):
            status = f"{Colors.GREEN}{LOG_SYMBOLS['SUCCESS']} Enabled{Colors.NC}" if z_dict['enabled'] else f"{Colors.DIM}{LOG_SYMBOLS['ERROR']} Disabled{Colors.NC}"
            print(f" {idx:2d}. {z_dict['zone_name']:<30} [{status}]")
        print(f"  0. All zones")
        
        zone_choice_str = input("\nYour choice: ").strip()
        
        if zone_choice_str == '0':
            for z_dict in zones_list:
                records = self.db.get_records_by_zone(z_dict['id'], enabled_only=False)
                if records:
                    print(f"\n{Colors.CYAN}═══ {z_dict['zone_name']} ═══{Colors.NC}")
                    for idx, r_row in enumerate(records, start=1):
                        r = row_to_dict(r_row)
                        if r.get('enabled', True):
                            status = f"{Colors.GREEN}{LOG_SYMBOLS['SUCCESS']} Enabled{Colors.NC}"
                        else:
                            status = f"{Colors.DIM}{LOG_SYMBOLS['ERROR']} Disabled{Colors.NC}"
                        
                        print(f"  {idx:3d}. {r['record_name']:40s} {r['record_type']:5s} TTL:{r.get('ttl', self.config.dns_default_ttl):5d} [{status}]")
        else:
            if not zone_choice_str.isdigit():
                print_error("Invalid choice")
                wait_for_enter()
                return
            
            zone_choice = int(zone_choice_str)
            
            if zone_choice < 1 or zone_choice > len(zones_list):
                print_error(f"Please select 1-{len(zones_list)}")
                wait_for_enter()
                return
            
            z_dict = zones_list[zone_choice - 1]
            zone = self.db.get_zone_by_id(z_dict['id'])
            
            if not zone:
                print_error(f"Zone not found!")
                wait_for_enter()
                return
            
            records = self.db.get_records_by_zone(z_dict['id'], enabled_only=False)
            
            if not records:
                print_info(f"No records configured for {zone['zone_name']}")
            else:
                print(f"\n{Colors.CYAN}═══ {zone['zone_name']} ═══{Colors.NC}")
                for idx, r_row in enumerate(records, start=1):
                    r = row_to_dict(r_row)
                    if r.get('enabled', True):
                        status = f"{Colors.GREEN}{LOG_SYMBOLS['SUCCESS']} Enabled{Colors.NC}"
                    else:
                        status = f"{Colors.DIM}{LOG_SYMBOLS['ERROR']} Disabled{Colors.NC}"
                    
                    print(f"{idx:3d}. {r['record_name']:40s} {r['record_type']:5s} TTL:{r.get('ttl', self.config.dns_default_ttl):5d} [{status}]")
                    
                    ip_info_row = self.db.get_ip_address(r['id'])
                    if ip_info_row:
                        ip_info = row_to_dict(ip_info_row)
                        if ip_info.get('ip_address'):
                            print(f"     └─ Current IP: {ip_info['ip_address']}")
        
        wait_for_enter()
    
    def add_record(self) -> None:
        """Add a new DNS record/subdomain - PROVIDER-FIRST approach."""
        print_section("Add DNS Record")
        
        zone = select_zone(self.db, prompt="Select zone")
        if not zone:
            return
        
        zone_name = zone['zone_name']
        
        print(f"\n{Colors.BOLD}Zone:{Colors.NC} {Colors.CYAN}{zone_name}{Colors.NC}")
        print()
        print(f"{Colors.BOLD}What is a DNS Record?{Colors.NC}")
        print(f"{Colors.DIM}A DNS record points a domain/subdomain to an IP address.{Colors.NC}")
        print(f"{Colors.DIM}DynDNS will automatically update this record when your IP changes.{Colors.NC}")
        print()
        print(f"{Colors.BOLD}Common examples:{Colors.NC}")
        print(f"  {Colors.DIM}{LOG_SYMBOLS['BULLET']}{Colors.NC} Root domain:      {Colors.BOLD}@{Colors.NC} or leave empty {Colors.DIM}{LOG_SYMBOLS['ARROW']}{Colors.NC} {zone_name}")
        print(f"  {Colors.DIM}{LOG_SYMBOLS['BULLET']}{Colors.NC} WWW subdomain:    {Colors.BOLD}www{Colors.NC} {Colors.DIM}{LOG_SYMBOLS['ARROW']}{Colors.NC} www.{zone_name}")
        print(f"  {Colors.DIM}{LOG_SYMBOLS['BULLET']}{Colors.NC} Mail subdomain:   {Colors.BOLD}mail{Colors.NC} {Colors.DIM}{LOG_SYMBOLS['ARROW']}{Colors.NC} mail.{zone_name}")
        print(f"  {Colors.DIM}{LOG_SYMBOLS['BULLET']}{Colors.NC} Nested subdomain: {Colors.BOLD}api.v2{Colors.NC} {Colors.DIM}{LOG_SYMBOLS['ARROW']}{Colors.NC} api.v2.{zone_name}")
        
        subdomain = input(f"\n{Colors.BOLD}Enter subdomain{Colors.NC} (or @ for root): ").strip()
        
        if subdomain in ['@', '']:
            record_name = zone_name
            print(f"{Colors.DIM}{LOG_SYMBOLS['ARROW']} Creating root record: {Colors.CYAN}{record_name}{Colors.NC}")
        else:
            record_name = f"{subdomain}.{zone_name}"
            print(f"{Colors.DIM}{LOG_SYMBOLS['ARROW']} Creating subdomain record: {Colors.CYAN}{record_name}{Colors.NC}")
        
        print()
        record_type = input(f"{Colors.BOLD}Record Type{Colors.NC} (A for IPv4, AAAA for IPv6) [A]: ").strip().upper()
        record_type = record_type if record_type in ['A', 'AAAA'] else 'A'
        
        existing_record = self.db.get_record_by_name_and_type(zone['id'], record_name, record_type)
        if existing_record:
            print_warning(f"Record '{record_name}' ({record_type}) already exists in database!")
            print_info("Use option '3) Edit record' to update TTL or status.")
            wait_for_enter()
            return
        
        ttl_str = input(f"{Colors.BOLD}TTL{Colors.NC} in seconds [{self.config.dns_default_ttl}]: ").strip()
        ttl = int(ttl_str) if ttl_str.isdigit() else self.config.dns_default_ttl
        
        print_subsection("Confirmation")
        print(f"{Colors.BOLD}Record Name:{Colors.NC} {Colors.GREEN}{record_name}{Colors.NC}")
        print(f"{Colors.BOLD}Record Type:{Colors.NC} {record_type}")
        print(f"{Colors.BOLD}TTL:{Colors.NC}         {ttl} seconds")
        
        if not confirm_action("Create this record?", default=False):
            print_info("Cancelled.")
            wait_for_enter()
            return
        
        # Get provider client with credentials validation
        provider = self._get_provider_with_credentials(zone, warn_on_missing=True, require_zone_id=True)
        
        if not provider:
            # Fallback: Create in database only (local mode)
            print_info("Record will be created in database only (local mode).")
            if not confirm_action("Continue without provider sync?", default=False):
                print_info("Cancelled.")
                wait_for_enter()
                return
            
            try:
                record_id = self.db.add_record(
                    zone_id=zone['id'],
                    record_name=record_name,
                    record_type=record_type,
                    ttl=ttl,
                    managed=True,
                    sync_status='local_only'
                )
                print_success(f"Record added locally! (ID: {record_id})")
                print_warning("Note: Record not created at provider. Configure API credentials to sync.")
            except (ValueError, TypeError) as e:
                print_error(f"Error adding record: {e}")
                self.logger.error(f"Failed to add record '{record_name}': {e}")
            
            wait_for_enter()
            return
        
        # Check if record already exists at provider
        print_info("Checking if record exists at provider...")
        existing_provider_record_id = provider.find_record_id(
            zone_id=zone['provider_zone_id'],
            record_name=record_name,
            record_type=record_type
        )
        
        if existing_provider_record_id:
            print_warning(f"Record '{record_name}' ({record_type}) already exists at provider!")
            print_info(f"Provider Record ID: {existing_provider_record_id}")
            
            if confirm_action("Import this existing record to database?", default=True):
                try:
                    # Add existing record to database
                    record_id = self.db.add_record(
                        zone_id=zone['id'],
                        record_name=record_name,
                        record_type=record_type,
                        provider_record_id=existing_provider_record_id,
                        ttl=ttl,
                        enabled=True,
                        managed=True,
                        sync_status='synced'
                    )
                    print_success(f"Existing record imported! (ID: {record_id})")
                    
                    # Try to get and store current IP from provider's zone records
                    try:
                        provider_zone_records = provider.get_zone_records(zone['provider_zone_id'])
                        if provider_zone_records:
                            for rec in provider_zone_records:
                                if rec.get('id') == existing_provider_record_id:
                                    current_ip = rec.get('content', '')
                                    if current_ip and current_ip not in ["0.0.0.0", "::"]:
                                        self.db.update_ip_address(record_id, current_ip)
                                        print_info(f"Current IP stored: {current_ip}")
                                    break
                    except ZoneNotFoundError as e:
                        print_warning(f"Could not fetch current IP from provider: {e}")
                        self.logger.warning(f"Zone not found when fetching records: {e}")
                    
                except (ValueError, TypeError) as e:
                    print_error(f"Error importing record: {e}")
                    self.logger.error(f"Failed to import record '{record_name}': {e}")
            else:
                print_info("Cancelled. Use 'Sync records from provider' to import existing records.")
            
            wait_for_enter()
            return
        
        # Provider-First: Create at provider first
        try:
            # Detect current IP address first
            print_info(f"Detecting current IP address...")
            network = NetworkData()
            network.setup(
                ipv4_enabled=self.config.network_ipv4_enabled,
                ipv6_enabled=self.config.network_ipv6_enabled,
                ipv4_detection_url=self.config.network_ipv4_detection_url,
                ipv6_detection_url=self.config.network_ipv6_detection_url,
                timeout=self.config.network_timeout,
                retry_attempts=self.config.network_retry_attempts,
                logger=self.logger
            )
            
            current_ipv4, current_ipv6 = network.load_current_ip_addresses()
            
            # Get appropriate IP for record type
            if record_type == 'A':
                current_ip = current_ipv4
                if not current_ip:
                    placeholder = get_placeholder_ip('A')
                    print_warning(f"IPv4 not detected! Using placeholder {placeholder}")
                    current_ip = placeholder
                else:
                    print_success(f"Using IPv4: {current_ip}")
            else:  # AAAA
                current_ip = current_ipv6
                if not current_ip:
                    placeholder = get_placeholder_ip('AAAA')
                    print_warning(f"IPv6 not detected! Using placeholder {placeholder}")
                    current_ip = placeholder
                else:
                    print_success(f"Using IPv6: {current_ip}")
            
            print_info(f"Creating record at provider...")
            
            # Build API record using provider helper
            api_record = provider.build_record_dict(
                record_name=record_name,
                record_type=record_type,
                content=current_ip,
                ttl=ttl,
                disabled=False
            )
            
            # Create at provider
            success = provider.create_records(
                zone_id=zone['provider_zone_id'],
                records=[api_record]
            )
            
            if not success:
                raise ValueError("Provider record creation failed")
            
            print_success(f"Record created at provider!")
            
            # Sync to get provider_record_id
            print_info(f"Syncing to retrieve provider record ID...")
            sync_stats = self._sync_zone_with_provider(zone, provider)
            
            if not sync_stats or sync_stats.get('synced', 0) == 0:
                print_warning("Warning: Could not retrieve provider_record_id via sync")
            
            # Find provider_record_id using provider helper
            provider_record_id = provider.find_record_id(
                zone_id=zone['provider_zone_id'],
                record_name=record_name,
                record_type=record_type
            )
            
            # Add to local database with provider_record_id
            record_id = self.db.add_record(
                zone_id=zone['id'],
                record_name=record_name,
                record_type=record_type,
                provider_record_id=provider_record_id,
                ttl=ttl,
                enabled=True,
                managed=True,
                sync_status='synced'
            )
            
            # Store current IP in database (if not placeholder)
            if current_ip not in ["0.0.0.0", "::"]:
                self.db.update_ip_address(record_id, current_ip)
                print_success(f"IP address stored: {current_ip}")
            
            print_success(f"Record added successfully! (ID: {record_id})")
            if provider_record_id:
                print_info(f"Provider Record ID: {provider_record_id}")
            else:
                print_warning("Note: Could not retrieve provider_record_id. Use 'Sync records from provider' to update.")
            
        except (ValueError, TypeError, KeyError) as e:
            print_error(f"Error creating record: {e}")
            self.logger.error(f"Failed to create record '{record_name}': {e}")
            print_warning("Record may have been created at provider but not in local database.")
            print_info("Use 'Sync records from provider' to reconcile.")
        
        wait_for_enter()
    
    def edit_record(self) -> None:
        """Edit an existing DNS record."""
        print_section("Edit Record")
        zone = select_zone(self.db, prompt="Select zone")
        if not zone:
            return
        record_row = select_record(self.db, zone['id'], prompt="Select record to edit")
        if not record_row:
            return
        
        record = row_to_dict(record_row)
        
        status_symbol = LOG_SYMBOLS['SUCCESS'] if record.get('enabled', True) else LOG_SYMBOLS['ERROR']
        status_color = Colors.GREEN if record.get('enabled', True) else Colors.DIM
        status_text = 'Enabled' if record.get('enabled', True) else 'Disabled'
        
        print_subsection("Current Record")
        print(f"{Colors.BOLD}Name:{Colors.NC}   {Colors.CYAN}{record['record_name']}{Colors.NC}")
        print(f"{Colors.BOLD}Type:{Colors.NC}   {record['record_type']}")
        print(f"{Colors.BOLD}TTL:{Colors.NC}    {record.get('ttl', self.config.dns_default_ttl)} seconds")
        print(f"{Colors.BOLD}Status:{Colors.NC} {status_color}{status_symbol} {status_text}{Colors.NC}")
        
        print(f"\n{Colors.BOLD}What to edit?{Colors.NC}")
        print()
        print(f"{Colors.BLUE}Available options:{Colors.NC}")
        menu_items = [
            "TTL (Time To Live)",
            "Enable/Disable record"
        ]
        for i, item in enumerate(menu_items, 1):
            print(f"  {i}) {item}")
        print(f"  0) Cancel")
        print()
        
        max_choice = len(menu_items)
        choice = input(f"Enter your choice (0-{max_choice}): ").strip()
        
        if choice == '1':
            current_ttl = record.get('ttl', self.config.dns_default_ttl)
            default_ttl = self.config.dns_default_ttl
            print(f"\n{Colors.BOLD}TTL Guidelines:{Colors.NC}")
            print(f"  {Colors.DIM}{LOG_SYMBOLS['BULLET']}{Colors.NC} {Colors.BOLD}60{Colors.NC}     = 1 minute  {Colors.DIM}(frequent updates){Colors.NC}")
            print(f"  {Colors.DIM}{LOG_SYMBOLS['BULLET']}{Colors.NC} {Colors.BOLD}300{Colors.NC}    = 5 minutes")
            print(f"  {Colors.DIM}{LOG_SYMBOLS['BULLET']}{Colors.NC} {Colors.BOLD}{default_ttl}{Colors.NC}   = 1 hour    {Colors.GREEN}(recommended){Colors.NC}")
            print(f"  {Colors.DIM}{LOG_SYMBOLS['BULLET']}{Colors.NC} {Colors.BOLD}86400{Colors.NC}  = 24 hours")
            
            new_ttl = get_valid_int(
                prompt=f"\nNew TTL in seconds [current: {current_ttl}]",
                default=current_ttl,
                min_val=60,
                max_val=86400
            )
            
            if new_ttl and new_ttl != current_ttl:
                if confirm_action(f"Update TTL to {new_ttl} seconds?", default=False):
                    try:
                        # Update database first
                        self.db.update_record(record['id'], ttl=new_ttl)
                        print_success(f"TTL updated to {new_ttl} seconds in database!")
                        
                        # Ask if user wants to sync to provider immediately
                        print()
                        print_info("TTL change will be applied at provider during next DNS update.")
                        if confirm_action("Sync TTL to provider immediately?", default=False):
                            # Get provider client with credentials
                            provider = self._get_provider_with_credentials(zone, warn_on_missing=True, require_zone_id=True)
                            
                            if not provider:
                                print_warning("Cannot sync to provider without credentials.")
                            else:
                                try:
                                    if not record.get('provider_record_id'):
                                        raise ValueError("Record has no provider_record_id")
                                    
                                    # Get current IP for the record
                                    ip_info_row = self.db.get_ip_address(record['id'])
                                    current_ip = "0.0.0.0"  # Default fallback
                                    
                                    if ip_info_row:
                                        ip_info = row_to_dict(ip_info_row)
                                        if ip_info.get('ip_address'):
                                            current_ip = ip_info['ip_address']
                                    
                                    print_info(f"Updating TTL at provider...")
                                    
                                    # Update record at provider with new TTL
                                    success = provider.update_record(
                                        zone_id=zone['provider_zone_id'],
                                        record_id=record['provider_record_id'],
                                        content=current_ip,
                                        ttl=new_ttl
                                    )
                                    
                                    if success:
                                        print_success(f"TTL synced to provider successfully!")
                                    else:
                                        print_warning(f"Failed to sync TTL to provider")
                                        
                                except (ValueError, TypeError, KeyError) as e:
                                    print_error(f"Error syncing TTL: {e}")
                                    self.logger.error(f"Failed to sync TTL for record {record['id']}: {e}")
                        
                    except (ValueError, TypeError) as e:
                        print_error(f"Error updating record: {e}")
                        self.logger.error(f"Failed to update record {record['id']}: {e}")
                else:
                    print_info("Cancelled.")
            else:
                print_info("No change.")
        
        elif choice == '2':
            current_status = record.get('enabled', True)
            new_status = not current_status
            action = "enable" if new_status else "disable"
            
            print()
            print_warning(f"Bidirectional sync: This will {action} the record at provider AND in database.")
            if new_status:
                print_info(f"  {LOG_SYMBOLS['ARROW']} Record will be recreated at provider")
                print_info(f"  {LOG_SYMBOLS['ARROW']} Database will be updated with new provider_record_id")
            else:
                print_info(f"  {LOG_SYMBOLS['ARROW']} Record will be deleted from provider")
                print_info(f"  {LOG_SYMBOLS['ARROW']} Database record kept for history (enabled=0)")
            print()
            
            if not confirm_action(f"Really {action} this record?", default=False):
                print_info("Cancelled.")
                wait_for_enter()
                return
            
            # Get provider client with credentials
            provider = self._get_provider_with_credentials(zone, warn_on_missing=True, require_zone_id=True)
            
            if not provider:
                # Fallback: Update database only (local mode)
                print_info("Record will be updated in database only (local mode).")
                if not confirm_action("Continue without provider sync?", default=False):
                    print_info("Cancelled.")
                    wait_for_enter()
                    return
                
                try:
                    self.db.update_record(record['id'], enabled=new_status)
                    print_success(f"Record {action}d locally!")
                    print_warning("Note: Provider not updated. Configure API credentials to sync.")
                except (ValueError, TypeError) as e:
                    print_error(f"Error updating record: {e}")
                    self.logger.error(f"Failed to {action} record {record['id']}: {e}")
                
                wait_for_enter()
                return
            
            # Bidirectional sync with provider
            try:
                if new_status:
                    # ENABLE: Recreate record at provider with current IP
                    print_info(f"Enabling: Creating record at provider...")
                    
                    # Step 1: Get current IP (from DB or detect)
                    current_ip = self._get_current_or_detect_ip(record)
                    
                    # Step 2: Create record at provider
                    api_record = provider.build_record_dict(
                        record_name=record['record_name'],
                        record_type=record['record_type'],
                        content=current_ip,
                        ttl=record.get('ttl', self.config.dns_default_ttl),
                        disabled=False
                    )
                    
                    success = provider.create_records(
                        zone_id=zone['provider_zone_id'],
                        records=[api_record]
                    )
                    
                    if not success:
                        raise ValueError("Failed to recreate record at provider")
                    
                    print_success(f"Record created at provider with IP {current_ip}!")
                    
                    # Step 3: Sync to retrieve new provider_record_id
                    sync_stats = self._sync_zone_with_provider(zone, provider)
                    
                    new_provider_record_id = provider.find_record_id(
                        zone_id=zone['provider_zone_id'],
                        record_name=record['record_name'],
                        record_type=record['record_type']
                    )
                    
                    self.db.update_record(
                        record['id'],
                        enabled=True,
                        provider_record_id=new_provider_record_id,
                        sync_status='synced'
                    )
                    
                    if new_provider_record_id:
                        print_success(f"Record enabled! (Provider ID: {new_provider_record_id})")
                    else:
                        print_success(f"Record enabled!")
                        print_warning("Note: Could not retrieve provider_record_id. Use 'Sync records from provider' to update.")
                    
                # DISABLE: Delete from provider
                else:
                    if record.get('provider_record_id'):
                        print_info(f"Disabling: Deleting record from provider...")
                        
                        if provider.delete_record(zone['provider_zone_id'], record['provider_record_id']):
                            print_success(f"Record deleted from provider!")
                        else:
                            print_warning(f"Failed to delete from provider (may not exist)")
                    else:
                        print_info("No provider_record_id - skipping provider deletion")
                    
                    self.db.update_record(
                        record['id'],
                        enabled=False,
                        provider_record_id=None,
                        sync_status='local_only'
                    )
                    
                    print_success(f"Record disabled! (kept in database for history)")
                
            except (ValueError, TypeError, KeyError) as e:
                print_error(f"Error during {action}: {e}")
                self.logger.error(f"Failed to {action} record {record['id']}: {e}")
                print_warning("Record state may be inconsistent. Use 'Sync records from provider' to reconcile.")
        
        elif choice == '0':
            print_info("Cancelled.")
        else:
            print_error("Invalid choice!")
        
        wait_for_enter()
    
    def delete_record(self) -> None:
        """Delete a DNS record from database AND provider."""
        print_section("Delete Record")
        zone = select_zone(self.db, prompt="Select zone")
        if not zone:
            return
        record_row = select_record(self.db, zone['id'], prompt="Select record to DELETE")
        if not record_row:
            return
        
        record = row_to_dict(record_row)
        
        print_warning("WARNING: This will delete:")
        print(f"   {Colors.RED}{LOG_SYMBOLS['BULLET']}{Colors.NC} Record: {Colors.BOLD}{record['record_name']}{Colors.NC} ({record['record_type']})")
        print(f"   {Colors.RED}{LOG_SYMBOLS['BULLET']}{Colors.NC} From local database")
        print(f"   {Colors.RED}{LOG_SYMBOLS['BULLET']}{Colors.NC} From DNS provider (if exists)")
        print(f"   {Colors.RED}{LOG_SYMBOLS['BULLET']}{Colors.NC} IP address history")
        print(f"   {Colors.RED}{LOG_SYMBOLS['BULLET']}{Colors.NC} Update history")
        
        if not confirm_action(f"Really delete record '{record['record_name']}'?", default=False):
            print_info("Cancelled.")
            wait_for_enter()
            return
        
        try:
            # Step 1: Delete from provider if provider_record_id exists
            if record.get('provider_record_id'):
                provider = self._get_provider_with_credentials(zone, warn_on_missing=False, require_zone_id=False)
                
                if provider and zone.get('provider_zone_id'):
                    print_info(f"Deleting record from provider...")
                    if provider.delete_record(zone['provider_zone_id'], record['provider_record_id']):
                        print_success(f"Deleted from provider")
                    else:
                        print_warning(f"Failed to delete from provider (record may not exist)")
                else:
                    print_warning(f"Cannot delete from provider (missing credentials or zone ID)")
            
            # Step 2: Delete from database (cascades to IP history and update logs)
            self.db.delete_record(record['id'])
            print_success(f"Record '{record['record_name']}' deleted successfully!")
            
        except (ValueError, TypeError) as e:
            print_error(f"Error deleting record: {e}")
            self.logger.error(f"Failed to delete record {record['id']}: {e}")
        
        wait_for_enter()
    
    def sync_zone_from_provider(self) -> None:
        """Sync records from provider - compare provider state with local database.
        
        This performs a full reconciliation:
        - Fetches all records from provider
        - Compares with local database
        - Categorizes records: synced/new/orphaned
        - Updates sync_status and last_synced_at fields
        - Displays detailed statistics
        """
        print_section("Sync Records from Provider")
        
        zone = select_zone(self.db, prompt="Select zone to sync")
        if not zone:
            return
        
        provider = self._get_provider_with_credentials(zone, warn_on_missing=True, require_zone_id=False)
        if not provider:
            wait_for_enter()
            return
        
        # Auto-sync provider_zone_id if missing
        if not zone.get('provider_zone_id'):
            print_info("Zone has no provider_zone_id - fetching from provider...")
            if not self._sync_zone_id(zone, provider):
                print_error("Failed to fetch provider_zone_id from provider.")
                wait_for_enter()
                return
            
            # Reload zone with updated provider_zone_id
            zone_row = self.db.get_zone_by_id(zone['id'])
            if zone_row:
                zone = row_to_dict(zone_row)
            else:
                print_error("Failed to reload zone after sync.")
                wait_for_enter()
                return
        
        try:
            print_info(f"Fetching records from provider for zone '{zone['zone_name']}'...")
            
            provider_records = provider.get_zone_records(zone['provider_zone_id'])
            if provider_records is None:
                print_error("Failed to fetch records from provider")
                wait_for_enter()
                return
            
            local_records = self.db.get_records_by_zone(zone['id'], enabled_only=False)
            local_records_dict = {row_to_dict(r)['id']: row_to_dict(r) for r in local_records}
            
            stats = {
                'synced': 0,
                'new': 0,
                'orphaned': 0,
                'updated': 0
            }
            
            # Track which local records were found at provider
            matched_local_ids = set()
            
            print_info(f"Analyzing {len(provider_records)} provider records...")
            print()
            
            for provider_record in provider_records:
                provider_name = provider_record['name']
                provider_type = provider_record['type']
                provider_id = provider_record['id']
                
                # Find matching local record by name and type
                matched = False
                for local_id, local_record in local_records_dict.items():
                    if (local_record['record_name'] == provider_name and 
                        local_record['record_type'] == provider_type):
                        matched = True
                        matched_local_ids.add(local_id)
                        
                        # Update database with current provider_record_id and sync status
                        update_needed = False
                        if local_record.get('provider_record_id') != provider_id:
                            update_needed = True
                        if local_record.get('sync_status') != 'synced':
                            update_needed = True
                        
                        if update_needed:
                            self.db.update_record(
                                local_id,
                                provider_record_id=provider_id,
                                sync_status='synced',
                                last_synced_at=datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                            )
                            stats['updated'] += 1
                            print_success(f"  {LOG_SYMBOLS['SUCCESS']} Synced: {provider_name} ({provider_type})")
                        else:
                            stats['synced'] += 1
                        
                        break
                
                if not matched:
                    stats['new'] += 1
                    print_info(f"  {LOG_SYMBOLS['INFO']} New at provider: {provider_name} ({provider_type}) - ID: {provider_id}")
            
            # Check for orphaned local records (not found at provider)
            for local_id, local_record in local_records_dict.items():
                if local_id not in matched_local_ids:
                    # This record exists locally but not at provider
                    if local_record.get('sync_status') != 'orphaned':
                        self.db.update_sync_status(
                            local_id,
                            sync_status='orphaned',
                            last_synced_at=datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                        )
                    stats['orphaned'] += 1
                    print_warning(f"  {LOG_SYMBOLS['WARNING']} Orphaned: {local_record['record_name']} ({local_record['record_type']}) - Not found at provider")
            
            print()
            print_subsection("Sync Statistics")
            print(f"  {Colors.GREEN}{LOG_SYMBOLS['SUCCESS']} Already synced:{Colors.NC}  {stats['synced']}")
            print(f"  {Colors.GREEN}{LOG_SYMBOLS['SUCCESS']} Updated:{Colors.NC}         {stats['updated']}")
            print(f"  {Colors.BLUE}{LOG_SYMBOLS['INFO']} New at provider:{Colors.NC} {stats['new']}")
            print(f"  {Colors.YELLOW}{LOG_SYMBOLS['WARNING']} Orphaned:{Colors.NC}        {stats['orphaned']}")
            print()
            
            if stats['new'] > 0:
                print_info("Note: 'New at provider' records exist remotely but not locally.")
                print_info("      Use 'Add record' to import them if needed.")
                print()
            
            if stats['orphaned'] > 0:
                print_warning("Warning: 'Orphaned' records exist locally but not at provider.")
                print_warning("         They may have been deleted remotely.")
                print()
            
            print_success(f"Zone sync completed!")
            
        except ZoneNotFoundError as e:
            print_error(f"Zone not found at provider: {e}")
            self.logger.error(f"Zone not found during sync: {e}")
        except (ValueError, KeyError, TypeError) as e:
            print_error(f"Error during zone sync: {e}")
            self.logger.error(f"Failed to sync zone {zone['id']}: {e}")
        
        wait_for_enter()
    
    ################################################################################
    # IP ADDRESS VIEWING
    ################################################################################
    
    def view_current_ips(self) -> None:
        """View current IP addresses for all records."""        
        print_subsection("Detecting Current IP Addresses")
        
        network = NetworkData()
        network.setup(
            ipv4_enabled=self.config.network_ipv4_enabled,
            ipv6_enabled=self.config.network_ipv6_enabled,
            ipv4_detection_url=self.config.network_ipv4_detection_url,
            ipv6_detection_url=self.config.network_ipv6_detection_url,
            timeout=self.config.network_timeout,
            retry_attempts=self.config.network_retry_attempts,
            logger=self.logger
        )
        
        current_ipv4, current_ipv6 = network.load_current_ip_addresses()
        
        if current_ipv4:
            print_success(f"IPv4: {current_ipv4}")
        else:
            print_warning("IPv4: Not detected")
        
        if current_ipv6:
            print_success(f"IPv6: {current_ipv6}")
        else:
            print_warning("IPv6: Not detected")
        
        # Display stored IPs per zone/record
        zones = self.db.get_all_zones()
        
        print_subsection("Stored DNS Record IPs")
        
        if not zones:
            print_info("No zones configured.")
            wait_for_enter()
            return
        
        has_any_records = False
        
        for zone_row in zones:
            zone = row_to_dict(zone_row)
            records = self.db.get_records_by_zone(zone['id'], enabled_only=True)
            
            if records:
                has_any_records = True
                print(f"\n{Colors.CYAN}═══ {zone['zone_name']} ═══{Colors.NC}")
                for record_row in records:
                    record = row_to_dict(record_row)
                    ip_info_row = self.db.get_ip_address(record['id'])
                    
                    if ip_info_row:
                        ip_info = row_to_dict(ip_info_row)
                        if ip_info.get('ip_address'):
                            changed_at = ip_info.get('last_changed_at', 'N/A')
                            
                            # Compare with current network IP
                            record_type = record['record_type']
                            stored_ip = ip_info['ip_address']
                            current_ip = current_ipv4 if record_type == 'A' else current_ipv6
                            
                            if current_ip and stored_ip != current_ip:
                                # IP mismatch - needs update
                                print(f"  {record['record_name']:<40s} {record_type:5s} {Colors.YELLOW}{LOG_SYMBOLS['WARNING']} {stored_ip} (outdated, current: {current_ip}){Colors.NC}")
                            else:
                                # IP matches or current IP not available
                                print(f"  {record['record_name']:<40s} {record_type:5s} {Colors.GREEN}{LOG_SYMBOLS['SUCCESS']} {stored_ip}{Colors.NC} (changed: {changed_at})")
                    else:
                        print(f"  {record['record_name']:<40s} {record['record_type']:5s} {Colors.DIM}○ (no IP stored yet){Colors.NC}")
        
        # If no records were found at all
        if not has_any_records:
            print_info("No records configured for any zone.")
        
        wait_for_enter()
    
    ################################################################################
    # FORCE DNS UPDATE (MANUAL SYNC)
    ################################################################################
    
    def force_dns_update(self) -> None:
        """Force immediate DNS update for all enabled records."""
        print_section("Force DNS Update")
        print()
        print(f"{Colors.YELLOW}WARNING{Colors.NC}")
        print(f"{Colors.DIM}This will immediately update ALL enabled DNS records with current IP addresses.{Colors.NC}")
        print(f"{Colors.DIM}Use this when:{Colors.NC}")
        print(f"  {Colors.DIM}• DNS records were manually deleted from provider{Colors.NC}")
        print(f"  {Colors.DIM}• Records are out of sync{Colors.NC}")
        print(f"  {Colors.DIM}• You want to force a refresh regardless of IP changes{Colors.NC}")
        print()
        
        if not confirm_action("Force update all DNS records now?", default=False):
            print_info("Cancelled.")
            wait_for_enter()
            return
        
        # Optional: Sync zones from provider first
        print()
        if confirm_action("Sync records with provider first? (Recommended to detect orphaned records)", default=True):
            print_subsection("Pre-Sync: Syncing Zones from Provider")
            zones_to_sync = self.db.get_all_enabled_zones()
            
            if not zones_to_sync:
                print_warning("No enabled zones to sync.")
            else:
                synced_count = 0
                failed_count = 0
                
                for zone_row in zones_to_sync:
                    zone = row_to_dict(zone_row)
                    
                    # Get provider with credentials
                    provider = self._get_provider_with_credentials(
                        zone=zone,
                        warn_on_missing=False,
                        require_zone_id=True
                    )
                    
                    if provider:
                        print_info(f"Syncing zone: {zone['zone_name']}...")
                        sync_stats = self._sync_zone_with_provider(zone, provider)
                        
                        if sync_stats and sync_stats.get('synced', 0) > 0:
                            synced_count += sync_stats.get('synced', 0)
                            print_success(
                                f"{zone['zone_name']}: "
                                f"{sync_stats.get('synced', 0)} records synced"
                            )
                        else:
                            failed_count += 1
                            print_warning(f"{zone['zone_name']}: Sync failed or no records")
                    else:
                        print_warning(f"{zone['zone_name']}: Skipped (no credentials)")
                
                print()
                print_section("Pre-Sync Summary")
                print(f"{Colors.GREEN}✓{Colors.NC} Synced: {synced_count} records")
                if failed_count > 0:
                    print(f"{Colors.YELLOW}!{Colors.NC} Failed: {failed_count} zones")
                print()
        
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
    
    def _detect_ip_addresses(self) -> Optional[NetworkData]:
        """Detect current public IP addresses."""

        print_subsection("Detecting Current IP Addresses")
        
        try:
            network = NetworkData()
            network.setup(
                ipv4_enabled=self.config.network_ipv4_enabled,
                ipv6_enabled=self.config.network_ipv6_enabled,
                ipv4_detection_url=self.config.network_ipv4_detection_url,
                ipv6_detection_url=self.config.network_ipv6_detection_url,
                timeout=self.config.network_timeout,
                retry_attempts=self.config.network_retry_attempts,
                logger=self.logger
            )
            
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
            
        except Exception as e:
            print_error(f"Failed to detect IP addresses: {e}")
            self.logger.error(f"IP detection failed in force update: {e}")
            return None
    
    def _process_all_zones(self, zones: List[Any], network: NetworkData) -> Dict[str, int]:
        """Process all zones and update DNS records."""

        stats = {
            'total': 0,
            'updated': 0,
            'failed': 0,
            'skipped': 0
        }
        
        for zone_row in zones:
            zone = row_to_dict(zone_row)
            
            dyndns_config = self.db.get_dyndns_config_by_zone(zone['id'])
            if not dyndns_config:
                print_warning(f"Zone '{zone['zone_name']}' has no API credentials - skipping")
                continue
            
            dyndns = row_to_dict(dyndns_config)
            
            provider = self._create_provider_client(zone, dyndns)
            if not provider:
                continue
            
            if not zone.get('provider_zone_id'):
                print_info(f"Syncing zone '{zone['zone_name']}' with provider...")
                if not self._sync_zone_id(zone, provider):
                    print_error(f"Failed to sync zone '{zone['zone_name']}' - skipping")
                    continue
                zone_row = self.db.get_zone_by_id(zone['id'])
                if zone_row:
                    zone = row_to_dict(zone_row)
            
            print(f"\n{Colors.BOLD}Zone: {zone['zone_name']}{Colors.NC}")
            self._process_zone_records(zone, provider, network, stats)
        
        return stats
    
    def _create_provider_client(self, zone: Dict[str, Any], dyndns: Dict[str, Any]) -> Optional[ProviderDNSClient]:
        """Create and setup provider API client."""
        try:
            api_key = f"{dyndns['bulk_id']}.{dyndns['api_key']}"
            
            provider = ProviderDNSClient(
                api_key=api_key,
                base_url=self.config.provider_api_base_url,
                timeout=self.config.provider_api_timeout,
                retries=self.config.provider_api_retry_attempts,
                logger=self.logger
            )
            return provider
            
        except Exception as e:
            print_error(f"Failed to initialize API client for zone '{zone['zone_name']}': {e}")
            self.logger.error(f"Provider client creation failed for zone {zone['id']}: {e}")
            return None
    
    def _get_provider_with_credentials(self, zone: Dict[str, Any], warn_on_missing: bool = True, 
                                       require_zone_id: bool = True) -> Optional[ProviderDNSClient]:
        """Get provider client with credentials validation."""
        dyndns_config = self.db.get_dyndns_config_by_zone(zone['id'])
        if not dyndns_config:
            if warn_on_missing:
                print_warning("No API credentials configured for this zone.")
                print_info("Configure API credentials to enable provider sync.")
            return None
        
        # Create provider client
        dyndns = row_to_dict(dyndns_config)
        provider = self._create_provider_client(zone, dyndns)
        
        if not provider:
            if warn_on_missing:
                print_error("Failed to create provider client")
            return None
        
        if require_zone_id and not zone.get('provider_zone_id'):
            if warn_on_missing:
                print_info(f"Zone '{zone['zone_name']}' has no provider_zone_id - fetching from provider...")
            
            if self._sync_zone_id(zone, provider):
                zone_row = self.db.get_zone_by_id(zone['id'])
                if zone_row:
                    updated_zone = row_to_dict(zone_row)
                    zone.update(updated_zone)
                else:
                    if warn_on_missing:
                        print_error("Failed to reload zone after sync")
                    return None
            else:
                if warn_on_missing:
                    print_error("Failed to fetch provider_zone_id from provider")
                return None
        
        return provider
    
    def _sync_zone_id(self, zone: Dict[str, Any], provider: ProviderDNSClient) -> bool:
        """Sync provider_zone_id for a zone by fetching from provider API."""
        try:
            provider_zones = provider.get_zones()
            if not provider_zones:
                raise ValueError("Failed to fetch zones from provider")
            
            provider_zone = next(
                (pz for pz in provider_zones if pz['name'] == zone['zone_name']),
                None
            )
            
            if not provider_zone:
                raise ValueError(f"Zone '{zone['zone_name']}' not found in provider")
            
            self.db.update_zone(zone['id'], provider_zone_id=provider_zone['id'])
            
            print_success(f"Synced zone with provider")
            self.logger.info(f"Synced provider_zone_id for zone {zone['zone_name']}: {provider_zone['id']}")
            return True
            
        except (ValueError, KeyError, TypeError) as e:
            print_error(f"Zone sync failed: {e}")
            self.logger.error(f"Failed to sync zone {zone['zone_name']}: {e}")
            return False
    
    def _sync_zone_with_provider(self, zone: Dict[str, Any], provider: ProviderDNSClient) -> Dict[str, int]:
        """Sync all records in a zone with provider to update provider_record_ids."""
        stats = {'synced': 0, 'failed': 0}
        
        try:
            if not zone.get('provider_zone_id'):
                raise ValueError(f"Zone '{zone['zone_name']}' has no provider_zone_id")
            
            # Fetch all records from provider
            provider_records = provider.get_zone_records(zone['provider_zone_id'])
            if not provider_records:
                raise ValueError("Failed to fetch records from provider")
            
            # Get all local records for this zone
            local_records = self.db.get_records_by_zone(zone['id'], enabled_only=False)
            
            # Update provider_record_ids for matching records
            for local_record_row in local_records:
                local_record = row_to_dict(local_record_row)
                
                # Find matching provider record by name and type
                matched = False
                for provider_record in provider_records:
                    if (provider_record['name'] == local_record['record_name'] and 
                        provider_record['type'] == local_record['record_type']):
                        self.db.update_record(
                            local_record['id'],
                            provider_record_id=provider_record['id'],
                            sync_status='synced',
                            last_synced_at=datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                        )
                        stats['synced'] += 1
                        matched = True
                        break
                
                if not matched:
                    # Record exists in DB but not at provider → Mark as orphaned
                    if local_record.get('provider_record_id'):
                        self.logger.info(
                            f"Record '{local_record['record_name']}' ({local_record['record_type']}) "
                            f"not found at provider - marking as orphaned"
                        )
                        self.db.update_record(
                            local_record['id'],
                            provider_record_id=None,
                            sync_status='orphaned'
                        )
                    stats['failed'] += 1
            
            self.logger.info(f"Synced {stats['synced']} records for zone '{zone['zone_name']}' ({stats['failed']} not found)")
            return stats
            
        except ZoneNotFoundError as e:
            self.logger.error(f"Zone not found at provider during sync: {e}")
            return {}
        except (ValueError, KeyError, TypeError) as e:
            self.logger.error(f"Failed to sync zone records with provider: {e}")
            return {}
    
    def _process_zone_records(self, zone: Dict[str, Any], provider: ProviderDNSClient, network: NetworkData, stats: Dict[str, int]) -> None:
        """Process all records for a specific zone."""
        records = self.db.get_records_by_zone(zone['id'], enabled_only=True)
        if not records:
            return
        
        for record_row in records:
            record = row_to_dict(record_row)
            stats['total'] += 1
            
            new_ip = self._get_target_ip(record, network)
            if not new_ip:
                print_warning(
                    f"  {LOG_SYMBOLS['ERROR']} {record['record_name']} ({record['record_type']}) - "
                    f"No IP available"
                )
                stats['skipped'] += 1
                continue
            
            old_ip = self._get_current_ip(record)
            
            if not self._ensure_provider_record_id(record, provider):
                stats['failed'] += 1
                continue
            
            if self._update_dns_record(record, provider, old_ip, new_ip):
                stats['updated'] += 1
            else:
                stats['failed'] += 1
    
    def _get_target_ip(self, record: Dict[str, Any], network: NetworkData) -> Optional[str]:
        """Get target IP address for record type."""
        if record['record_type'] == 'A':
            return network.ipv4_address
        elif record['record_type'] == 'AAAA':
            return network.ipv6_address
        else:
            print_warning(
                f"{record['record_name']} ({record['record_type']}) - "
                f"Unsupported record type"
            )
            return None
    
    def _get_current_ip(self, record: Dict[str, Any]) -> Optional[str]:
        """Get current IP from database for record."""
        ip_info_row = self.db.get_ip_address(record['id'])
        if ip_info_row:
            ip_info = row_to_dict(ip_info_row)
            return ip_info.get('ip_address')
        return None
    
    def _get_current_or_detect_ip(self, record: Dict[str, Any]) -> str:
        """Get current IP from database or detect new IP address."""
        current_ip = self._get_current_ip(record)
        if current_ip:
            return current_ip
        
        print_info(f"Detecting current {record['record_type']} address...")
        
        net = NetworkData()
        net.setup(
            ipv4_enabled=(record['record_type'] == 'A'),
            ipv6_enabled=(record['record_type'] == 'AAAA'),
            timeout=self.config.network_timeout,
            retry_attempts=self.config.network_retry_attempts,
            logger=self.logger
        )
        
        if record['record_type'] == 'A':
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
        """Ensure record has provider_record_id, sync if missing."""
        if record.get('provider_record_id'):
            return True
        
        print_info(
            f"{record['record_name']} ({record['record_type']}) - "
            f"Syncing with provider..."
        )
        
        try:
            zone_row = self.db.get_zone_by_id(record['zone_id'])
            if not zone_row:
                raise ValueError(f"Zone {record['zone_id']} not found")
            
            zone = row_to_dict(zone_row)
            
            if not zone.get('provider_zone_id'):
                raise ValueError(f"Zone '{zone['zone_name']}' has no provider_zone_id")
            
            # Using provider helper to find record ID
            provider_record_id = provider.find_record_id(
                zone['provider_zone_id'],
                record['record_name'],
                record['record_type']
            )
            
            if provider_record_id:
                self.db.update_record(
                    record['id'],
                    provider_record_id=provider_record_id
                )
                record['provider_record_id'] = provider_record_id
                return True
            
            print_warning(f"{record['record_name']} ({record['record_type']}) - Not found in provider, creating...")
            
            if self._create_provider_record(record, zone, provider):
                # Using provider helper to find newly created record ID
                provider_record_id = provider.find_record_id(
                    zone['provider_zone_id'],
                    record['record_name'],
                    record['record_type']
                )
                
                if provider_record_id:
                    self.db.update_record(
                        record['id'],
                        provider_record_id=provider_record_id
                    )
                    record['provider_record_id'] = provider_record_id
                    print_success(
                        f"{record['record_name']} ({record['record_type']}) - "
                        f"Created successfully"
                    )
                    return True
            
            print_error(
                f"{record['record_name']} ({record['record_type']}) - "
                f"Failed to create record in provider"
            )
            return False
            
        except (ValueError, KeyError, TypeError) as e:
            print_error(
                f"{record['record_name']} ({record['record_type']}) - "
                f"Sync failed: {e}"
            )
            self.logger.error(f"Provider sync failed for record {record['id']}: {e}")
            return False
    
    def _create_provider_record(self, record: Dict[str, Any], zone: Dict[str, Any], provider: ProviderDNSClient) -> bool:
        """Create a DNS record in the provider."""
        try:
            content = get_placeholder_ip(record['record_type'])
            
            api_record = provider.build_record_dict(
                record['record_name'],
                record['record_type'],
                content,
                record.get('ttl', self.config.dns_default_ttl),
                not record.get('enabled', True)
            )
            
            success = provider.create_records(
                zone_id=zone['provider_zone_id'],
                records=[api_record]
            )
            
            if success:
                self.logger.info(
                    f"Created record '{record['record_name']}' ({record['record_type']}) "
                    f"in provider zone {zone['zone_name']}"
                )
                return True
            else:
                self.logger.error(f"Provider API returned failure for record creation")
                return False
                
        except (ValueError, KeyError, TypeError) as e:
            self.logger.error(f"Failed to create record '{record['record_name']}': {e}")
            return False
    
    def _update_dns_record(self, record: Dict[str, Any], provider: ProviderDNSClient, old_ip: Optional[str], new_ip: str) -> bool:
        """Update DNS record via provider API with automatic error recovery."""
        try:
            zone_row = self.db.get_zone_by_id(record['zone_id'])
            if not zone_row:
                raise ValueError(f"Zone {record['zone_id']} not found")
            
            zone = row_to_dict(zone_row)
            
            if not zone.get('provider_zone_id'):
                raise ValueError(f"Zone '{zone['zone_name']}' has no provider_zone_id")
            
            if not record.get('provider_record_id'):
                raise ValueError("Record has no provider_record_id")
            
            try:
                success = provider.update_record(
                    zone_id=zone['provider_zone_id'],
                    record_id=record['provider_record_id'],
                    content=new_ip,
                    ttl=record.get('ttl', self.config.dns_default_ttl)
                )
                
                if not success:
                    raise ValueError("Provider API update failed")
                    
            except RecordNotFoundError:
                print_warning(
                    f"{record['record_name']} ({record['record_type']}) - "
                    f"Record not found at provider, recreating..."
                )
                
                self.db.update_record_provider_id(record['id'], None)
                
                api_record = {
                    "name": record['record_name'],
                    "type": record['record_type'],
                    "content": new_ip,
                    "ttl": record.get('ttl', self.config.dns_default_ttl),
                    "disabled": not record.get('enabled', True)
                }
                
                success = provider.create_records(
                    zone_id=zone['provider_zone_id'],
                    records=[api_record]
                )
                
                if not success:
                    raise ValueError("Failed to recreate record at provider")
                
                sync_stats = self._sync_zone_with_provider(zone, provider)
                if not sync_stats or sync_stats.get('synced', 0) == 0:
                    raise ValueError("Failed to sync after record recreation")
                
                self.db.update_ip_address(
                    record_id=record['id'],
                    ip_address=new_ip,
                    changed=True
                )
                
                self.db.log_dns_update(
                    record_id=record['id'],
                    old_ip=old_ip,
                    new_ip=new_ip,
                    status='success',
                    error_message=None
                )
                
                print_success(
                    f"{record['record_name']} ({record['record_type']}) - "
                    f"Recreated and updated to {new_ip}"
                )
                return True
            
            self.db.update_ip_address(
                record_id=record['id'],
                ip_address=new_ip,
                changed=True
            )
            
            self.db.log_dns_update(
                record_id=record['id'],
                old_ip=old_ip,
                new_ip=new_ip,
                status='success',
                error_message=None
            )
            
            print_success(
                f"{record['record_name']} ({record['record_type']}) - "
                f"Updated to {new_ip}"
            )
            return True
            
        except (ValueError, TypeError) as e:
            print_error(
                f"{record['record_name']} ({record['record_type']}) - "
                f"Update failed: {e}"
            )
            
            self.db.log_dns_update(
                record_id=record['id'],
                old_ip=old_ip,
                new_ip=new_ip,
                status='failed',
                error_message=str(e)
            )
            
            self.logger.error(f"DNS update failed for record {record['id']}: {e}")
            return False
    
    def _display_update_summary(self, stats: Dict[str, int]) -> None:
        """Display update summary statistics."""
        print_subsection("Update Summary")
        print(f"{Colors.BOLD}Total records:{Colors.NC}    {stats['total']}")
        print(f"{Colors.GREEN}{LOG_SYMBOLS['SUCCESS']} Updated:{Colors.NC}        {stats['updated']}")
        print(f"{Colors.RED}{LOG_SYMBOLS['ERROR']} Failed:{Colors.NC}         {stats['failed']}")
        print(f"{Colors.YELLOW}{LOG_SYMBOLS['ERROR']} Skipped:{Colors.NC}        {stats['skipped']}")
        print()
        
        if stats['updated'] > 0:
            print_success(f"Force update completed! {stats['updated']} records updated.")
        elif stats['failed'] > 0:
            print_error("Force update completed with errors. Check logs for details.")
        else:
            print_info("No records were updated.")
    
    ################################################################################
    # IMPORT/EXPORT CONFIGURATION
    ################################################################################
    
    def import_config(self) -> None:
        """Launch configuration importer."""
        print_section("Import Configuration")
        
        file_path = input("Enter file path to import: ").strip()
        if not file_path:
            print_error("No file specified.")
            wait_for_enter()
            return
        
        if not os.path.exists(file_path):
            print_error(f"File not found: {file_path}")
            wait_for_enter()
            return
        
        overwrite = confirm_action("Overwrite existing data?", default=False)
        
        print(f"\nImporting from {file_path}...")
        importer = ConfigImporter(self.config, self.logger)
        result = importer.import_from_file(file_path, overwrite=overwrite)
        
        if result == 0:
            print_success("Import completed successfully!")
        else:
            print_error("Import failed. Check logs for details.")
        
        wait_for_enter()
    
    def export_config(self) -> None:
        """Launch configuration exporter."""
        print_section("Export Configuration")
        print()
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        default_filename = f"dyndns-export_{timestamp}.yaml"
        default_path = os.path.expanduser(f"~/{default_filename}")
        
        print(f"{Colors.DIM}Default location:{Colors.NC} {Colors.CYAN}{default_path}{Colors.NC}")
        print()
        print(f"{Colors.DIM}Options:{Colors.NC}")
        print(f"{Colors.DIM}  • Press Enter: Use default location{Colors.NC}")
        print(f"{Colors.DIM}  • Enter custom path: {Colors.CYAN}/path/to/your/dyndns-export.yaml{Colors.NC}")
        print()
        
        output_file = input(f"Output file path [default: {default_filename}]: ").strip()
        
        if not output_file:
            output_file = default_path
        else:
            output_file = os.path.expanduser(output_file)
            output_file = os.path.abspath(output_file)
        
        file_ext = os.path.splitext(output_file)[1].lower()
        if file_ext in ['.yaml', '.yml']:
            format_type = 'yaml'
        elif file_ext == '.json':
            format_type = 'json'
        else:
            format_choice = input("Format (yaml/json) [yaml]: ").strip().lower()
            format_type = format_choice if format_choice in ['yaml', 'json'] else 'yaml'
        
        print(f"\nExporting configuration...")
        exporter = ConfigExporter(self.config, self.logger)
        result = exporter.export_to_file(
            output_file,
            format=format_type
        )
        
        if result == 0:
            print_success(f"Configuration exported to: {output_file}")
        else:
            print_error("Export failed. Check logs for details.")
        
        wait_for_enter()

################################################################################
# DYNDNS CONFIGURATION IMPORTER
################################################################################

class ConfigImporter:
    """Import DynDNS configuration from YAML/JSON files."""
    
    def __init__(self, config: Any, logger: Any) -> None:
        self.config = config
        self.logger = logger
        self.db = config.db
        
        if self.db is None:
            raise DatabaseError("Database not initialized. Run 'ionos-dyndns config' first.")
    
    def import_from_file(self, file_path: str, overwrite: bool = False) -> int:
        """Import configuration from YAML/JSON file."""
        try:
            self.logger.info(f"Importing configuration from {file_path}")
            
            data = self._parse_file(file_path)
            
            if not data:
                print_error("No data found in file")
                return 1
            
            if not self._validate_import_data(data):
                print_error("Invalid data structure")
                return 1
            
            result = self._process_zones(data, overwrite)
            
            return result
            
        except FileNotFoundError:
            print_error(f"File not found: {file_path}")
            self.logger.debug(f"Import file not found: {file_path}")
            return 1
        except json.JSONDecodeError as e:
            print_error(f"Invalid JSON format: {e}")
            self.logger.error(f"JSON decode error: {e}")
            return 1
        except (AttributeError, ImportError) as e:
            print_error(f"Import error: {e}")
            self.logger.error(f"Import failed: {e}")
            return 1
    
    def _parse_file(self, file_path: str) -> Optional[Dict[str, Any]]:
        """Parse YAML or JSON file."""
        with open(file_path, 'r') as f:
            if file_path.endswith('.json'):
                return json.load(f)
            else:
                if yaml is None:
                    raise ImportError("PyYAML not installed. Install with: pip install pyyaml")
                return yaml.safe_load(f)
    
    def _validate_import_data(self, data: Dict[str, Any]) -> bool:
        """Validate import data structure."""
        if not isinstance(data, dict):
            return False
        
        if 'zones' not in data or not isinstance(data['zones'], list):
            print_error("Missing or invalid 'zones' array")
            return False
        
        for zone_data in data['zones']:
            if not isinstance(zone_data, dict):
                return False
            if 'zone_name' not in zone_data:
                print_error(f"Zone missing 'zone_name': {zone_data}")
                return False
            if 'records' in zone_data and not isinstance(zone_data['records'], list):
                print_error(f"Invalid 'records' in zone '{zone_data['zone_name']}'")
                return False
        
        return True
    
    def _process_zones(self, data: Dict[str, Any], overwrite: bool) -> int:
        """Process and import zones with records."""
        zones_data = data.get('zones', [])
        
        if not zones_data:
            print_error("No zones found in file")
            return 1
        
        imported_zones = 0
        imported_records = 0
        updated_zones = 0
        
        for zone_data in zones_data:
            try:
                zone_name = zone_data['zone_name']
                
                existing_zone = self.db.get_zone_by_name(zone_name)
                
                if existing_zone:
                    if overwrite:
                        zone_id = existing_zone['id']
                        self.db.update_zone(
                            zone_id,
                            provider_zone_id=zone_data.get('provider_zone_id'),
                            enabled=zone_data.get('enabled', True)
                        )
                        updated_zones += 1
                        print_info(f"Zone updated: {zone_name}")
                    else:
                        print_warning(f"Zone exists (skipped): {zone_name}")
                        continue
                else:
                    zone_id = self.db.add_zone(
                        zone_name=zone_name,
                        provider_zone_id=zone_data.get('provider_zone_id'),
                        enabled=zone_data.get('enabled', True)
                    )
                    imported_zones += 1
                    print_success(f"Zone added: {zone_name}")
                
                if 'bulk_id' in zone_data and 'api_key' in zone_data:
                    self.db.set_dyndns_config(
                        zone_id=zone_id,
                        bulk_id=zone_data['bulk_id'],
                        api_key=zone_data['api_key']
                    )
                
                record_count = self._process_records(zone_id, zone_data.get('records', []), overwrite)
                imported_records += record_count
            
            except (KeyError, ValueError, TypeError) as e:
                print_error(f"Error importing zone '{zone_data.get('zone_name', '?')}': {e}")
                self.logger.error(f"Zone import error: {e}")
        
        print_subsection("Import Summary")
        print(f"{Colors.BOLD}Zones added:{Colors.NC}     {Colors.GREEN}{imported_zones}{Colors.NC}")
        print(f"{Colors.BOLD}Zones updated:{Colors.NC}   {Colors.CYAN}{updated_zones}{Colors.NC}")
        print(f"{Colors.BOLD}Records total:{Colors.NC}   {Colors.GREEN}{imported_records}{Colors.NC}")
        
        self.logger.info(f"Import completed: {imported_zones} new, {updated_zones} updated zones, {imported_records} records")
        return 0
    
    def _process_records(self, zone_id: int, records_data: List[Dict[str, Any]], overwrite: bool) -> int:
        """Process and import records for a zone."""
        imported_count = 0
        
        for record_data in records_data:
            try:
                record_name = record_data['record_name']
                record_type = record_data['record_type']
                
                existing_record = self.db.get_record_by_name_and_type(zone_id, record_name, record_type)
                
                if existing_record:
                    if overwrite:
                        self.db.update_record(
                            existing_record['id'],
                            ttl=record_data.get('ttl', self.config.dns_default_ttl),
                            enabled=record_data.get('enabled', True)
                        )
                        imported_count += 1
                        print(f"  {Colors.DIM}├─ Record updated: {record_name} ({record_type}){Colors.NC}")
                    else:
                        print(f"  {Colors.DIM}├─ Record exists (skipped): {record_name} ({record_type}){Colors.NC}")
                else:
                    self.db.add_record(
                        zone_id=zone_id,
                        record_name=record_name,
                        record_type=record_type,
                        ttl=record_data.get('ttl', self.config.dns_default_ttl),
                        enabled=record_data.get('enabled', True)
                    )
                    imported_count += 1
                    print(f"  {Colors.DIM}├─ Record added: {record_name} ({record_type}){Colors.NC}")
                    
            except (KeyError, ValueError, TypeError) as e:
                print_error(f"  Error importing record: {e}")
                self.logger.error(f"Record import error: {e}")
        
        return imported_count


################################################################################
# DYNDNS CONFIGURATION EXPORTER
################################################################################

class ConfigExporter:
    """Export DynDNS configuration to YAML/JSON files."""
    
    def __init__(self, config: Any, logger: Any) -> None:
        self.config = config
        self.logger = logger
        self.db = config.db
        
        if self.db is None:
            raise DatabaseError("Database not initialized. Run 'ionos-dyndns config' first.")
    
    def export_to_file(self, output_file: Optional[str] = None, format: str = 'yaml') -> int:
        """Export configuration to file or stdout."""
        try:
            self.logger.info("Exporting configuration")
            
            config_data = self._build_export_data()
            
            if format == 'json':
                output = json.dumps(config_data, indent=2)
            else:
                if yaml is None:
                    raise ImportError("PyYAML not installed. Install with: pip install pyyaml")
                output = yaml.dump(config_data, default_flow_style=False, sort_keys=False)
            
            if output_file:
                with open(output_file, 'w') as f:
                    f.write(output)
                self.logger.info(f"Configuration exported to {output_file}")
            else:
                print(output)
            
            return 0
            
        except FileNotFoundError:
            print_error(f"Cannot write to file: {output_file}")
            self.logger.error(f"Export file write error: {output_file}")
            return 1
        except (ImportError, AttributeError) as e:
            print_error(f"Export error: {e}")
            self.logger.error(f"Export failed: {e}")
            return 1
    
    def _build_export_data(self) -> Dict[str, Any]:
        """Build export structure."""
        data = {
            'version': '1.0',
            'exported_at': datetime.utcnow().isoformat() + 'Z',
            'zones': []
        }
        
        zones = self.db.get_all_zones()
        
        for zone_row in zones:
            zone = row_to_dict(zone_row)
            
            zone_config = {
                'zone_name': zone['zone_name'],
                'provider_zone_id': zone.get('provider_zone_id', ''),
                'enabled': bool(zone.get('enabled', True))
            }
            
            dyndns_row = self.db.get_dyndns_config_by_zone(zone['id'])
            if dyndns_row:
                dyndns = row_to_dict(dyndns_row)
                zone_config['bulk_id'] = dyndns.get('bulk_id', '')
                zone_config['api_key'] = dyndns.get('api_key', '')
                
                if dyndns.get('domains'):
                    try:
                        domains = json.loads(dyndns['domains']) if isinstance(dyndns['domains'], str) else dyndns['domains']
                        if domains:
                            zone_config['domains'] = domains
                    except (json.JSONDecodeError, ValueError, TypeError):
                        pass
            
            records = self.db.get_records_by_zone(zone['id'], enabled_only=False)
            zone_config['records'] = []
            
            for record_row in records:
                record = row_to_dict(record_row)
                
                record_config = {
                    'record_name': record['record_name'],
                    'record_type': record['record_type'],
                    'ttl': record.get('ttl', self.config.dns_default_ttl)
                }
                
                if record.get('provider_record_id'):
                    record_config['provider_record_id'] = record['provider_record_id']
                
                if record.get('enabled') is not None:
                    record_config['enabled'] = bool(record['enabled'])
                
                zone_config['records'].append(record_config)
            
            data['zones'].append(zone_config)
        
        return data