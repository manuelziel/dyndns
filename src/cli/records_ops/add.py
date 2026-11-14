#!/usr/bin/env python3
"""Interactive DNS record creation workflows for RecordManager.

Handles adding records in native DynDNS bundle mode, offline local-only mode,
and provider-first REST synchronization mode (import existing or create new).

Author: Manuel Ziel
License: MIT
"""

################################################################################
# IMPORTS & DEPENDENCIES
################################################################################

from typing import Any

from src.api import ProviderDNSClient
from src.core.constants import (
    PlaceholderIP,
    RecordType,
    Subdomain,
    SyncStatus,
    UpdateMethod,
)
from src.core.exceptions import APIError, DatabaseError, ZoneNotFoundError
from src.network import NetworkData
from src.utils.colors import Colors

from ..helpers.input import (
    confirm_action,
    get_placeholder_ip,
    safe_input,
    select_zone,
    wait_for_enter,
)
from ..helpers.output import (
    print_error,
    print_info,
    print_section,
    print_subsection,
    print_success,
    print_warning,
)

################################################################################
# RECORD CREATE MIXIN
################################################################################


class RecordCreateMixin:
    """Mixin providing interactive DNS record creation workflows."""

    config: Any
    logger: Any
    db: Any

    def add_record(self) -> None:
        """Add a new DNS record using the configured update mode."""
        print_section("Add DNS Record")
        zone = select_zone(self.db, prompt="Select zone")
        if not zone:
            return

        self._print_dns_record_explanation(zone["zone_name"])
        subdomain = safe_input(
            f"\n{Colors.BOLD}Enter subdomain{Colors.NC} (or @ for root): "
        ).strip()
        record_name = (
            zone["zone_name"]
            if subdomain in (Subdomain.ROOT, "")
            else f"{subdomain}.{zone['zone_name']}"
        )

        raw_type = (
            safe_input(
                f"{Colors.BOLD}Record Type{Colors.NC} (A for IPv4, AAAA for IPv6) [A]: "
            )
            .strip()
            .upper()
        )
        record_type = raw_type if RecordType.is_supported(raw_type) else RecordType.A

        if self._check_record_exists_locally(zone["id"], record_name, record_type):
            return

        ttl_str = safe_input(
            f"{Colors.BOLD}TTL{Colors.NC} in seconds [{self.config.dns_default_ttl}]: "
        ).strip()
        ttl = int(ttl_str) if ttl_str.isdigit() else self.config.dns_default_ttl
        self._execute_record_addition_flow(zone, record_name, record_type, ttl)

    ############################################################################
    # Record Addition Helpers
    ############################################################################

    def _print_dns_record_explanation(self, zone_name: str) -> None:
        """Display guidance and subdomain examples for ``zone_name``.

        Args:
            zone_name: Domain name of the selected zone.
        """
        print(f"\n{Colors.BOLD}Zone:{Colors.NC} {Colors.CYAN}{zone_name}{Colors.NC}\n")
        print(f"{Colors.BOLD}What is a DNS Record?{Colors.NC}")
        print(f"{Colors.DIM}A DNS record points a domain/subdomain to an IP address.{Colors.NC}")
        print(
            f"{Colors.DIM}DynDNS will automatically update this record when your IP changes.{Colors.NC}\n"
        )
        print(f"{Colors.BOLD}Common examples:{Colors.NC}")
        print(f"  • Root domain:      {Colors.BOLD}@{Colors.NC} or leave empty -> {zone_name}")
        print(f"  • WWW subdomain:    {Colors.BOLD}www{Colors.NC} -> www.{zone_name}")
        print(f"  • Mail subdomain:   {Colors.BOLD}mail{Colors.NC} -> mail.{zone_name}")

    def _check_record_exists_locally(
        self, zone_id: int, record_name: str, record_type: str
    ) -> bool:
        """Check whether ``(record_name, record_type)`` already exists in SQLite.

        Args:
            zone_id: Database zone ID.
            record_name: Fully qualified record name.
            record_type: DNS record type.

        Returns:
            True if the record already exists locally, False otherwise.
        """
        existing = self.db.get_record_by_name_and_type(zone_id, record_name, record_type)
        if existing:
            print_warning(
                f"Record '{record_name}' ({record_type}) already exists in database!"
            )
            print_info("Use option '3) Edit record' to update TTL or status.")
            wait_for_enter()
            return True
        return False

    def _execute_record_addition_flow(
        self,
        zone: dict[str, Any],
        record_name: str,
        record_type: str,
        ttl: int,
    ) -> None:
        """Confirm creation parameters and dispatch to DynDNS, local, or REST flow.

        Args:
            zone: Zone dictionary.
            record_name: Fully qualified record name.
            record_type: DNS record type.
            ttl: Record TTL in seconds.
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
            self._add_record_dyndns_mode(zone["id"], record_name, record_type, ttl)
            return

        provider = self._get_provider_with_credentials(  # type: ignore[attr-defined]
            zone, warn_on_missing=True, require_zone_id=True
        )
        if not provider:
            self._add_record_locally_only(zone["id"], record_name, record_type, ttl)
            return
        try:
            self._add_record_with_provider_flow(
                zone, provider, record_name, record_type, ttl
            )
        finally:
            provider.close()

    def _add_record_dyndns_mode(
        self, zone_id: int, record_name: str, record_type: str, ttl: int
    ) -> None:
        """Insert record locally and synchronize the native DynDNS bundle.

        Args:
            zone_id: Database zone ID.
            record_name: Fully qualified record name.
            record_type: DNS record type.
            ttl: Record TTL in seconds.
        """
        try:
            record_id = self.db.add_record(
                zone_id=zone_id,
                record_name=record_name,
                record_type=record_type,
                ttl=ttl,
                managed=True,
                sync_status=SyncStatus.SYNCED,
            )
            if record_id is None:
                raise DatabaseError("Failed to insert record into database")
            print_success(f"Record added locally! (ID: {record_id})")
            self._sync_dyndns_bundle_if_needed(zone_id)  # type: ignore[attr-defined]
        except (ValueError, TypeError, DatabaseError) as exc:
            print_error(f"Error adding record: {exc}")
            self.logger.error(f"Failed to add record '{record_name}': {exc}")
        wait_for_enter()

    def _add_record_locally_only(
        self, zone_id: int, record_name: str, record_type: str, ttl: int
    ) -> None:
        """Insert record in local-only mode when provider credentials are absent.

        Args:
            zone_id: Database zone ID.
            record_name: Fully qualified record name.
            record_type: DNS record type.
            ttl: Record TTL in seconds.
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
                sync_status=SyncStatus.LOCAL_ONLY,
            )
            if record_id is None:
                raise DatabaseError("Failed to insert record into database")
            print_success(f"Record added locally! (ID: {record_id})")
            print_warning(
                "Note: Record not created at provider. Configure API credentials to sync."
            )
        except (ValueError, TypeError, DatabaseError) as exc:
            print_error(f"Error adding record: {exc}")
            self.logger.error(f"Failed to add record '{record_name}': {exc}")
        wait_for_enter()

    def _add_record_with_provider_flow(
        self,
        zone: dict[str, Any],
        provider: ProviderDNSClient,
        record_name: str,
        record_type: str,
        ttl: int,
    ) -> None:
        """Import an existing provider record or create a new one via REST API.

        Args:
            zone: Zone dictionary.
            provider: Active provider client.
            record_name: Fully qualified record name.
            record_type: DNS record type.
            ttl: Record TTL in seconds.
        """
        print_info("Checking if record exists at provider...")
        existing_provider_id = provider.find_record_id(
            zone_id=zone["provider_zone_id"],
            record_name=record_name,
            record_type=record_type,
        )
        if existing_provider_id:
            self._import_existing_provider_record(
                zone, provider, existing_provider_id, record_name, record_type, ttl
            )
        else:
            self._create_new_provider_record_workflow(
                zone, provider, record_name, record_type, ttl
            )
        wait_for_enter()

    def _import_existing_provider_record(
        self,
        zone: dict[str, Any],
        provider: ProviderDNSClient,
        provider_id: str,
        record_name: str,
        record_type: str,
        ttl: int,
    ) -> None:
        """Import a pre-existing remote provider record into SQLite.

        Args:
            zone: Zone dictionary.
            provider: Active provider client.
            provider_id: Remote provider record ID.
            record_name: Fully qualified record name.
            record_type: DNS record type.
            ttl: Record TTL in seconds.
        """
        print_warning(
            f"Record '{record_name}' ({record_type}) already exists at provider!"
        )
        print_info(f"Provider Record ID: {provider_id}")
        if not confirm_action("Import this existing record to database?", default=True):
            print_info(
                "Cancelled. Use 'Sync records from provider' to import existing records."
            )
            return

        try:
            record_id = self.db.add_record(
                zone_id=zone["id"],
                record_name=record_name,
                record_type=record_type,
                provider_record_id=provider_id,
                ttl=ttl,
                enabled=True,
                managed=True,
                sync_status=SyncStatus.SYNCED,
            )
            if record_id is None:
                raise DatabaseError("Failed to insert record into database")
            print_success(f"Existing record imported! (ID: {record_id})")
            self._fetch_and_store_provider_record_ip(
                zone["provider_zone_id"], provider, provider_id, record_id
            )
        except (ValueError, TypeError, DatabaseError) as exc:
            print_error(f"Error importing record: {exc}")
            self.logger.error(f"Failed to import record '{record_name}': {exc}")

    def _fetch_and_store_provider_record_ip(
        self,
        provider_zone_id: str,
        provider: ProviderDNSClient,
        provider_record_id: str,
        record_id: int,
    ) -> None:
        """Fetch current remote IP content for ``provider_record_id`` and store locally.

        Args:
            provider_zone_id: Remote zone identifier.
            provider: Active provider client.
            provider_record_id: Remote record identifier.
            record_id: Local database record ID.
        """
        try:
            records = provider.get_zone_records(provider_zone_id) or []
            for rec in records:
                if rec.get("id") == provider_record_id:
                    ip_addr = rec.get("content", "")
                    if ip_addr and ip_addr not in (
                        PlaceholderIP.IPV4,
                        PlaceholderIP.IPV6,
                    ):
                        self.db.update_ip_address(record_id, ip_addr)
                        print_info(f"Current IP stored: {ip_addr}")
                    break
        except ZoneNotFoundError as exc:
            print_warning(f"Could not fetch current IP from provider: {exc}")
            self.logger.warning(f"Zone not found when fetching records: {exc}")

    def _create_new_provider_record_workflow(
        self,
        zone: dict[str, Any],
        provider: ProviderDNSClient,
        record_name: str,
        record_type: str,
        ttl: int,
    ) -> None:
        """Detect public IP (or placeholder) and create the record at the provider.

        Args:
            zone: Zone dictionary.
            provider: Active provider client.
            record_name: Fully qualified record name.
            record_type: DNS record type.
            ttl: Record TTL in seconds.
        """
        print_info("Detecting current IP address...")
        network = NetworkData(config=self.config, logger=self.logger)
        network.load_current_ip_addresses()

        current_ip = (
            network.ipv4_address
            if record_type == RecordType.A
            else network.ipv6_address
        )
        if not current_ip:
            placeholder = get_placeholder_ip(record_type)
            print_warning(
                f"{record_type} not detected! Using placeholder {placeholder}"
            )
            current_ip = placeholder
        else:
            print_success(f"Using {record_type}: {current_ip}")

        self._execute_provider_record_creation(
            zone, provider, record_name, record_type, current_ip, ttl
        )

    def _execute_provider_record_creation(
        self,
        zone: dict[str, Any],
        provider: ProviderDNSClient,
        record_name: str,
        record_type: str,
        current_ip: str,
        ttl: int,
    ) -> None:
        """Create the record remotely via REST API and persist the synced record locally.

        Args:
            zone: Zone dictionary.
            provider: Active provider client.
            record_name: Fully qualified record name.
            record_type: DNS record type.
            current_ip: Initial IP content to assign.
            ttl: Record TTL in seconds.
        """
        try:
            print_info("Creating record at provider...")
            api_record = provider.build_record_dict(
                record_name, record_type, current_ip, ttl, False
            )
            if not provider.create_records(zone["provider_zone_id"], [api_record]):
                raise APIError("Provider record creation failed")
            print_success("Record created at provider!")
            print_info("Syncing to retrieve provider record ID...")
            self._sync_zone_with_provider(zone, provider)  # type: ignore[attr-defined]
            prov_id = provider.find_record_id(
                zone["provider_zone_id"], record_name, record_type
            )
            self._save_created_provider_record(
                zone["id"], record_name, record_type, prov_id, current_ip, ttl
            )
        except (ValueError, TypeError, KeyError, APIError, DatabaseError) as exc:
            print_error(f"Error creating record: {exc}")
            self.logger.error(f"Failed to create record '{record_name}': {exc}")
            print_warning(
                "Record may have been created at provider but not in local database."
            )
            print_info("Use 'Sync records from provider' to reconcile.")

    def _save_created_provider_record(
        self,
        zone_id: int,
        record_name: str,
        record_type: str,
        prov_id: str | None,
        current_ip: str,
        ttl: int,
    ) -> None:
        """Persist newly created provider record and non-placeholder IP in SQLite.

        Args:
            zone_id: Local database zone ID.
            record_name: Fully qualified record name.
            record_type: DNS record type.
            prov_id: Resolved remote provider record ID, if found.
            current_ip: Initial IP address written to the provider.
            ttl: Record TTL in seconds.
        """
        record_id = self.db.add_record(
            zone_id=zone_id,
            record_name=record_name,
            record_type=record_type,
            provider_record_id=prov_id,
            ttl=ttl,
            enabled=True,
            managed=True,
            sync_status=SyncStatus.SYNCED,
        )
        if record_id is None:
            raise DatabaseError("Failed to insert record into database")
        if current_ip not in (PlaceholderIP.IPV4, PlaceholderIP.IPV6):
            self.db.update_ip_address(record_id, current_ip)
            print_success(f"IP address stored: {current_ip}")
        print_success(f"Record added successfully! (ID: {record_id})")
        if prov_id:
            print_info(f"Provider Record ID: {prov_id}")
        else:
            print_warning(
                "Note: Could not retrieve provider_record_id. "
                "Use 'Sync records from provider' to update."
            )
