#!/usr/bin/env python3
"""Post-zone-creation record wizard mixin for ``ZoneManager``.

Handles optional automatic Zone ID discovery and initial ``@`` / ``www``
``A`` + ``AAAA`` record provisioning when adding a new DNS zone.

Author: Manuel Ziel
License: MIT
"""

################################################################################
# IMPORTS & DEPENDENCIES
################################################################################

from typing import Any

from ..api import ProviderDNSClient
from ..core.constants import RecordType, Subdomain, SyncStatus
from ..core.exceptions import DatabaseError, DynDNSException, NetworkError
from ..network import NetworkData
from ..utils.colors import Colors
from .constants import SetupMenuChoices
from .helpers.input import get_placeholder_ip, safe_input
from .helpers.output import (
    print_error,
    print_info,
    print_section,
    print_success,
    print_warning,
)

################################################################################
# ZONE SETUP WIZARD MIXIN
################################################################################


class ZoneSetupWizardMixin:
    """Interactive post-zone-creation record setup helpers for ``ZoneManager``."""

    config: Any
    logger: Any
    db: Any

    def _fetch_zone_id_from_provider(
        self, zone_name: str, bulk_id: str, api_key: str
    ) -> str | None:
        """Query the provider API to auto-discover ``provider_zone_id``.

        Args:
            zone_name: Root domain name to look up.
            bulk_id: Provider API prefix / bulk ID.
            api_key: Provider API secret key.

        Returns:
            Discovered provider zone ID string or ``None``.
        """
        print_info("Fetching Zone ID from provider...")
        temp_client: ProviderDNSClient | None = None
        try:
            temp_client = ProviderDNSClient(
                api_key=f"{bulk_id}.{api_key}",
                config=self.config,
                logger=self.logger,
            )
            provider_zones = temp_client.get_zones()
            if provider_zones:
                match = next(
                    (pz for pz in provider_zones if pz.get("name") == zone_name), None
                )
                if match and match.get("id"):
                    print_success(f"Zone ID fetched: {match['id']}")
                    return str(match["id"])
                print_warning(f"Zone '{zone_name}' not found at provider.")
            else:
                print_warning("Failed to fetch zones from provider - check credentials.")
        except DynDNSException as exc:
            print_warning(f"Auto-fetch failed: {exc}")
        finally:
            if temp_client is not None:
                temp_client.close()
        print_info("Zone will be created locally. Zone ID can be synced later.")
        return None

    def _prompt_create_dyndns_records(
        self,
        zone_id: int,
        zone_name: str,
        provider_zone_id: str | None,
        bulk_id: str,
        api_key: str,
    ) -> None:
        """Prompt user to create standard ``@`` / ``www`` DynDNS records.

        Args:
            zone_id: Newly created database zone ID.
            zone_name: Root domain name.
            provider_zone_id: Optional provider zone ID.
            bulk_id: Provider API prefix / bulk ID.
            api_key: Provider API secret key.
        """
        print_section("DynDNS Records")
        print(f"{Colors.DIM}These records will be automatically updated when your IP changes.{Colors.NC}\n")
        self._print_record_setup_menu(zone_name)
        choice = safe_input("Enter your choice (0-2): ").strip()
        if choice == SetupMenuChoices.SKIP:
            print_info("You can add records later via 'Records' > 'Add record'")
            return
        if choice not in (SetupMenuChoices.STANDARD, SetupMenuChoices.ROOT_ONLY):
            print_warning("Invalid choice. Skipping record creation.")
            return
        self._create_selected_records(
            choice, zone_id, zone_name, provider_zone_id, bulk_id, api_key
        )

    @staticmethod
    def _print_record_setup_menu(zone_name: str) -> None:
        """Render the record setup options menu for ``zone_name``.

        Args:
            zone_name: Root domain name.
        """
        print(f"{Colors.BLUE}Available options:{Colors.NC}")
        print(f"  {SetupMenuChoices.STANDARD}) Standard setup (recommended)")
        print(f"     {Colors.DIM}Creates A + AAAA records for:{Colors.NC}")
        print(f"     {Colors.DIM}- @ ({zone_name}){Colors.NC}")
        print(f"     {Colors.DIM}- www (www.{zone_name}){Colors.NC}")
        print(f"  {SetupMenuChoices.ROOT_ONLY}) Root domain only (@)")
        print(f"     {Colors.DIM}Creates A + AAAA for {zone_name}{Colors.NC}")
        print(f"  {SetupMenuChoices.SKIP}) Skip\n")

    def _create_selected_records(
        self,
        choice: str,
        zone_id: int,
        zone_name: str,
        provider_zone_id: str | None,
        bulk_id: str,
        api_key: str,
    ) -> None:
        """Detect live IPs and create the selected initial DynDNS records.

        Args:
            choice: User choice (``STANDARD`` or ``ROOT_ONLY``).
            zone_id: Database zone ID.
            zone_name: Root domain name.
            provider_zone_id: Optional provider zone ID.
            bulk_id: Provider API prefix / bulk ID.
            api_key: Provider API secret key.
        """
        subdomains = (
            [str(Subdomain.ROOT), str(Subdomain.WWW)]
            if choice == SetupMenuChoices.STANDARD
            else [str(Subdomain.ROOT)]
        )
        setup_name = (
            "Standard setup" if choice == SetupMenuChoices.STANDARD else "Root domain only"
        )
        if not provider_zone_id:
            print_warning("No Provider Zone ID available - records will be created locally only.")
            print_info("Sync with provider later to create records at IONOS.")
        print("\n")
        print_info("Detecting current IP addresses...")
        current_ipv4, current_ipv6 = self._detect_ips()
        provider = self._init_provider_client(provider_zone_id, bulk_id, api_key)
        try:
            print()
            print_info(f"Creating {setup_name} records...")
            self._execute_records_creation(
                zone_id, zone_name, provider_zone_id, provider, subdomains, current_ipv4, current_ipv6
            )
        finally:
            if provider is not None:
                provider.close()

    def _detect_ips(self) -> tuple[str | None, str | None]:
        """Probe current public IPv4 and IPv6 addresses for wizard setup.

        Returns:
            Tuple ``(current_ipv4, current_ipv6)``.
        """
        try:
            network = NetworkData(config=self.config, logger=self.logger)
            current_ipv4, current_ipv6 = network.load_current_ip_addresses()
        except NetworkError as exc:
            self.logger.warning(f"IP detection failed: {exc}")
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

    def _init_provider_client(
        self, provider_zone_id: str | None, bulk_id: str, api_key: str
    ) -> ProviderDNSClient | None:
        """Instantiate ``ProviderDNSClient`` when ``provider_zone_id`` is present.

        Args:
            provider_zone_id: Optional provider zone ID.
            bulk_id: Provider API prefix / bulk ID.
            api_key: Provider API secret key.

        Returns:
            ``ProviderDNSClient`` instance or ``None``.
        """
        if not provider_zone_id:
            return None
        try:
            return ProviderDNSClient(
                api_key=f"{bulk_id}.{api_key}",
                config=self.config,
                logger=self.logger,
            )
        except DynDNSException as exc:
            self.logger.warning(f"Failed to create provider client: {exc}")
            return None

    def _execute_records_creation(
        self,
        zone_id: int,
        zone_name: str,
        provider_zone_id: str | None,
        provider: ProviderDNSClient | None,
        subdomains: list[str],
        current_ipv4: str | None,
        current_ipv6: str | None,
    ) -> None:
        """Provision enabled ``A``/``AAAA`` records for each requested subdomain.

        Args:
            zone_id: Database zone ID.
            zone_name: Root domain name.
            provider_zone_id: Optional provider zone ID.
            provider: Optional ``ProviderDNSClient``.
            subdomains: Subdomain labels (``'@'``, ``'www'``).
            current_ipv4: Detected IPv4 address.
            current_ipv6: Detected IPv6 address.
        """
        created = 0
        failed = 0
        for subdomain in subdomains:
            name = zone_name if subdomain == Subdomain.ROOT else f"{subdomain}.{zone_name}"
            disp = (
                f"{Subdomain.ROOT} ({zone_name})"
                if subdomain == Subdomain.ROOT
                else f"{subdomain} ({name})"
            )
            if self.config.network_ipv4_enabled:
                ok = self._create_single_dyndns_record(
                    zone_id, provider_zone_id, provider, name, RecordType.A, current_ipv4, disp
                )
                created, failed = (created + 1, failed) if ok else (created, failed + 1)
            if self.config.network_ipv6_enabled:
                ok = self._create_single_dyndns_record(
                    zone_id, provider_zone_id, provider, name, RecordType.AAAA, current_ipv6, disp
                )
                created, failed = (created + 1, failed) if ok else (created, failed + 1)
        self._print_creation_summary(created, failed)

    @staticmethod
    def _print_creation_summary(created: int, failed: int) -> None:
        """Print final wizard record creation statistics.

        Args:
            created: Successfully created record count.
            failed: Failed record count.
        """
        print()
        if created > 0:
            print_success(f"{created} record(s) created successfully!")
        if failed > 0:
            print_warning(f"{failed} record(s) failed to create")
        if created > 0:
            print_info(
                "The daemon will now automatically update these records when your IP changes."
            )

    def _create_single_dyndns_record(
        self,
        zone_id: int,
        provider_zone_id: str | None,
        provider: ProviderDNSClient | None,
        record_name: str,
        record_type: str,
        current_ip: str | None,
        display_name: str,
    ) -> bool:
        """Create one ``A`` or ``AAAA`` record at the provider and in SQLite.

        Args:
            zone_id: Database zone ID.
            provider_zone_id: Optional provider zone ID.
            provider: Optional ``ProviderDNSClient``.
            record_name: Full FQDN.
            record_type: ``'A'`` or ``'AAAA'``.
            current_ip: Detected public IP or ``None``.
            display_name: Human-readable label for CLI output.

        Returns:
            True on success, False on failure.
        """
        if self.db.get_record_by_name_and_type(zone_id, record_name, record_type):
            print_info(f"  {display_name} {record_type}: Already exists, skipping")
            return True
        ip_to_use = current_ip or get_placeholder_ip(record_type)
        provider_record_id, sync_status = self._sync_new_record_with_provider(
            provider, provider_zone_id, record_name, record_type, ip_to_use, display_name
        )
        return self._save_single_dyndns_record(
            zone_id, record_name, record_type, provider_record_id, sync_status, current_ip, display_name
        )

    def _sync_new_record_with_provider(
        self,
        provider: ProviderDNSClient | None,
        provider_zone_id: str | None,
        record_name: str,
        record_type: str,
        ip_to_use: str,
        display_name: str,
    ) -> tuple[str | None, str]:
        """Find or create ``record_name`` on the provider API.

        Args:
            provider: Optional ``ProviderDNSClient``.
            provider_zone_id: Optional provider zone ID.
            record_name: Full FQDN.
            record_type: ``'A'`` or ``'AAAA'``.
            ip_to_use: Initial IP or placeholder string.
            display_name: Human-readable label for CLI output.

        Returns:
            Tuple ``(provider_record_id, sync_status)``.
        """
        if not provider or not provider_zone_id:
            return None, str(SyncStatus.LOCAL_ONLY)
        try:
            provider_record_id = provider.find_record_id(
                provider_zone_id, record_name, record_type
            )
            if provider_record_id:
                print_info(f"  {display_name} {record_type}: Found at provider, importing...")
                return provider_record_id, str(SyncStatus.SYNCED)
            api_record = provider.build_record_dict(
                record_name=record_name,
                record_type=record_type,
                content=ip_to_use,
                ttl=self.config.dns_default_ttl,
                disabled=False,
            )
            if provider.create_records(provider_zone_id, [api_record]):
                found_id = provider.find_record_id(provider_zone_id, record_name, record_type)
                status = SyncStatus.SYNCED if found_id else SyncStatus.PENDING_SYNC
                return found_id, str(status)
        except DynDNSException as exc:
            self.logger.warning(
                f"Provider operation failed for {record_name} {record_type}: {exc}"
            )
        return None, str(SyncStatus.LOCAL_ONLY)

    def _save_single_dyndns_record(
        self,
        zone_id: int,
        record_name: str,
        record_type: str,
        provider_record_id: str | None,
        sync_status: str,
        current_ip: str | None,
        display_name: str,
    ) -> bool:
        """Insert a wizard-provisioned record and its detected IP into SQLite.

        Args:
            zone_id: Database zone ID.
            record_name: Full FQDN.
            record_type: ``'A'`` or ``'AAAA'``.
            provider_record_id: Optional provider record ID.
            sync_status: Synchronization state string.
            current_ip: Detected public IP or ``None``.
            display_name: Human-readable label for CLI output.

        Returns:
            True on success, False on database error.
        """
        try:
            record_id = self.db.add_record(
                zone_id=zone_id,
                record_name=record_name,
                record_type=record_type,
                provider_record_id=provider_record_id,
                ttl=self.config.dns_default_ttl,
                enabled=True,
                managed=True,
                sync_status=sync_status,
            )
            if record_id is None:
                raise DatabaseError("Failed to retrieve record ID after insertion.")
            if current_ip and current_ip != get_placeholder_ip(record_type):
                self.db.update_ip_address(record_id, current_ip)
            msg = (
                "Created and synced with provider"
                if sync_status == SyncStatus.SYNCED
                else "Created locally"
            )
            print_success(f"  {display_name} {record_type}: {msg}")
            return True
        except DynDNSException as exc:
            self.logger.error(f"Failed to create record {record_name} ({record_type}): {exc}")
            print_error(f"  {display_name} {record_type}: Failed - {exc}")
            return False
