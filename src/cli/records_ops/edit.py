#!/usr/bin/env python3
"""Interactive DNS record edit workflows for RecordManager.

Provides TTL updates and bidirectional enable/disable record toggling across
local SQLite storage and remote provider APIs.

Author: Manuel Ziel
License: MIT
"""

################################################################################
# IMPORTS & DEPENDENCIES
################################################################################

from typing import Any

from src.api import ProviderDNSClient
from src.cli.constants import EditRecordMenuChoices, MenuLabels, ValidationLimits
from src.core.constants import PlaceholderIP, SyncStatus
from src.core.exceptions import APIError, DatabaseError
from src.utils.colors import Colors

from ..helpers.input import (
    confirm_action,
    get_valid_int,
    safe_input,
    select_record,
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
    row_to_dict,
)

################################################################################
# RECORD EDIT MIXIN
################################################################################


class RecordEditMixin:
    """Mixin providing interactive DNS record TTL and status editing."""

    config: Any
    logger: Any
    db: Any

    def edit_record(self) -> None:
        """Edit an existing DNS record's TTL or enabled status."""
        print_section("Edit Record")
        zone = select_zone(self.db, prompt="Select zone")
        if not zone:
            return
        record_row = select_record(self.db, zone["id"], prompt="Select record to edit")
        if not record_row:
            return

        record = row_to_dict(record_row)
        self._print_current_record_details(record)
        print(f"\n{Colors.BOLD}What to edit?{Colors.NC}\n")
        print(f"{Colors.BLUE}Available options:{Colors.NC}")
        menu_items = list(MenuLabels.EDIT_RECORD_MENU.values())
        for idx, item in enumerate(menu_items, 1):
            print(f"  {idx}) {item}")
        print("  0) Cancel\n")

        choice = safe_input(f"Enter your choice (0-{len(menu_items)}): ").strip()
        self._execute_record_edit_choice(choice, zone, record)
        wait_for_enter()

    ############################################################################
    # Edit Record Helpers (TTL & Bidirectional Status Toggle)
    ############################################################################

    def _print_current_record_details(self, record: dict[str, Any]) -> None:
        """Print current summary attributes of ``record``.

        Args:
            record: Record dictionary.
        """
        is_enabled = record.get("enabled", True)
        status_color = Colors.GREEN if is_enabled else Colors.DIM
        status_text = "Enabled" if is_enabled else "Disabled"
        print_subsection("Current Record")
        print(f"{Colors.BOLD}Name:{Colors.NC}   {Colors.CYAN}{record['record_name']}{Colors.NC}")
        print(f"{Colors.BOLD}Type:{Colors.NC}   {record['record_type']}")
        print(
            f"{Colors.BOLD}TTL:{Colors.NC}    {record.get('ttl', self.config.dns_default_ttl)} seconds"
        )
        print(f"{Colors.BOLD}Status:{Colors.NC} {status_color}{status_text}{Colors.NC}")

    def _execute_record_edit_choice(
        self, choice: str, zone: dict[str, Any], record: dict[str, Any]
    ) -> None:
        """Dispatch the selected edit submenu action.

        Args:
            choice: Selected menu choice key.
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

    def _edit_record_ttl(
        self, zone: dict[str, Any], record: dict[str, Any]
    ) -> None:
        """Prompt for a new TTL value and apply it if changed.

        Args:
            zone: Zone dictionary.
            record: Record dictionary.
        """
        current_ttl = record.get("ttl", self.config.dns_default_ttl)
        default_ttl = self.config.dns_default_ttl
        print(f"\n{Colors.BOLD}TTL Guidelines:{Colors.NC}")
        print(
            f"  • {Colors.BOLD}{ValidationLimits.TTL_MIN}{Colors.NC}     = 1 minute  "
            f"{Colors.DIM}(frequent updates){Colors.NC}"
        )
        print(f"  • {Colors.BOLD}300{Colors.NC}    = 5 minutes")
        print(
            f"  • {Colors.BOLD}{default_ttl}{Colors.NC}   = 1 hour    "
            f"{Colors.GREEN}(recommended){Colors.NC}"
        )
        print(f"  • {Colors.BOLD}{ValidationLimits.TTL_MAX}{Colors.NC}  = 24 hours")

        new_ttl = get_valid_int(
            prompt=f"\nNew TTL in seconds [current: {current_ttl}]",
            default=current_ttl,
            min_val=ValidationLimits.TTL_MIN,
            max_val=ValidationLimits.TTL_MAX,
        )
        if new_ttl and new_ttl != current_ttl:
            self._confirm_and_update_ttl(zone, record, new_ttl)
        else:
            print_info("No change.")

    def _confirm_and_update_ttl(
        self, zone: dict[str, Any], record: dict[str, Any], new_ttl: int
    ) -> None:
        """Confirm and persist ``new_ttl`` locally and optionally at the provider.

        Args:
            zone: Zone dictionary.
            record: Record dictionary.
            new_ttl: New TTL in seconds.
        """
        if not confirm_action(f"Update TTL to {new_ttl} seconds?", default=False):
            print_info("Cancelled.")
            return
        try:
            self.db.update_record(record["id"], ttl=new_ttl)
            print_success(f"TTL updated to {new_ttl} seconds in database!\n")
            print_info("TTL change will be applied at provider during next DNS update.")
            if confirm_action("Sync TTL to provider immediately?", default=False):
                self._sync_ttl_to_provider(zone, record, new_ttl)
        except (ValueError, TypeError, DatabaseError) as exc:
            print_error(f"Error updating record: {exc}")
            self.logger.error(f"Failed to update record {record['id']}: {exc}")

    def _sync_ttl_to_provider(
        self, zone: dict[str, Any], record: dict[str, Any], new_ttl: int
    ) -> None:
        """Push ``new_ttl`` to the remote provider REST record.

        Args:
            zone: Zone dictionary.
            record: Record dictionary.
            new_ttl: New TTL in seconds.
        """
        provider = self._get_provider_with_credentials(  # type: ignore[attr-defined]
            zone, warn_on_missing=True, require_zone_id=True
        )
        if not provider:
            print_warning("Cannot sync to provider without credentials.")
            return

        try:
            if not record.get("provider_record_id"):
                raise APIError("Record has no provider_record_id")
            current_ip = (
                self._get_current_ip(record)  # type: ignore[attr-defined]
                or PlaceholderIP.get(record["record_type"])
            )
            print_info("Updating TTL at provider...")
            if provider.update_record(
                zone_id=zone["provider_zone_id"],
                record_id=record["provider_record_id"],
                content=current_ip,
                ttl=new_ttl,
            ):
                print_success("TTL synced to provider successfully!")
            else:
                print_warning("Failed to sync TTL to provider")
        except (ValueError, TypeError, KeyError, APIError) as exc:
            print_error(f"Error syncing TTL: {exc}")
            self.logger.error(f"Failed to sync TTL for record {record['id']}: {exc}")
        finally:
            provider.close()

    def _edit_record_status(
        self, zone: dict[str, Any], record: dict[str, Any]
    ) -> None:
        """Toggle ``record`` enabled state with bidirectional provider sync.

        Args:
            zone: Zone dictionary.
            record: Record dictionary.
        """
        new_status = not record.get("enabled", True)
        action = "enable" if new_status else "disable"
        print(f"\n{Colors.YELLOW}WARNING{Colors.NC}")
        print(
            f"Bidirectional sync: This will {action} the record at provider AND in database."
        )
        if new_status:
            print_info("  • Record will be recreated at provider")
            print_info("  • Database will be updated with new provider_record_id")
        else:
            print_info("  • Record will be deleted from provider")
            print_info("  • Database record kept for history (enabled=0)\n")

        if not confirm_action(f"Really {action} this record?", default=False):
            print_info("Cancelled.")
            return

        provider = self._get_provider_with_credentials(  # type: ignore[attr-defined]
            zone, warn_on_missing=True, require_zone_id=True
        )
        if not provider:
            self._local_only_record_toggle(record["id"], new_status, action)
            return
        try:
            self._sync_record_toggle_with_provider(
                zone, provider, record, new_status, action
            )
        finally:
            provider.close()

    def _local_only_record_toggle(
        self, record_id: int, new_status: bool, action: str
    ) -> None:
        """Toggle enabled state locally when provider credentials are unavailable.

        Args:
            record_id: Local database record ID.
            new_status: Target enabled state.
            action: Human-readable action verb (``'enable'`` or ``'disable'``).
        """
        print_info("Record will be updated in database only (local mode).")
        if not confirm_action("Continue without provider sync?", default=False):
            print_info("Cancelled.")
            return
        try:
            self.db.update_record(record_id, enabled=new_status)
            print_success(f"Record {action}d locally!")
            print_warning("Note: Provider not updated. Configure API credentials to sync.")
        except (ValueError, TypeError, DatabaseError) as exc:
            print_error(f"Error updating record: {exc}")
            self.logger.error(f"Failed to {action} record {record_id}: {exc}")

    def _sync_record_toggle_with_provider(
        self,
        zone: dict[str, Any],
        provider: ProviderDNSClient,
        record: dict[str, Any],
        new_status: bool,
        action: str,
    ) -> None:
        """Apply record enable/disable toggle at the provider and in SQLite.

        Args:
            zone: Zone dictionary.
            provider: Active provider client.
            record: Record dictionary.
            new_status: Target enabled state.
            action: Human-readable action verb.
        """
        try:
            if new_status:
                self._enable_record_at_provider(zone, provider, record)
            else:
                self._disable_record_at_provider(zone, provider, record)
        except (ValueError, TypeError, KeyError, APIError, DatabaseError) as exc:
            print_error(f"Error during {action}: {exc}")
            self.logger.error(f"Failed to {action} record {record['id']}: {exc}")
            print_warning(
                "Record state may be inconsistent. Use 'Sync records from provider' to reconcile."
            )

    def _enable_record_at_provider(
        self,
        zone: dict[str, Any],
        provider: ProviderDNSClient,
        record: dict[str, Any],
    ) -> None:
        """Recreate ``record`` at the provider and mark it enabled in SQLite.

        Args:
            zone: Zone dictionary.
            provider: Active provider client.
            record: Record dictionary.
        """
        print_info("Enabling: Creating record at provider...")
        current_ip = self._get_current_or_detect_ip(record)  # type: ignore[attr-defined]
        api_record = provider.build_record_dict(
            record["record_name"],
            record["record_type"],
            current_ip,
            record.get("ttl", self.config.dns_default_ttl),
            False,
        )
        if not provider.create_records(zone["provider_zone_id"], [api_record]):
            raise APIError("Failed to recreate record at provider")

        print_success(f"Record created at provider with IP {current_ip}!")
        self._sync_zone_with_provider(zone, provider)  # type: ignore[attr-defined]
        new_prov_id = provider.find_record_id(
            zone["provider_zone_id"], record["record_name"], record["record_type"]
        )
        self.db.update_record(
            record["id"],
            enabled=True,
            provider_record_id=new_prov_id,
            sync_status=SyncStatus.SYNCED,
        )
        if new_prov_id:
            print_success(f"Record enabled! (Provider ID: {new_prov_id})")
        else:
            print_success("Record enabled!")
            print_warning(
                "Note: Could not retrieve provider_record_id. "
                "Use 'Sync records from provider' to update."
            )

    def _disable_record_at_provider(
        self,
        zone: dict[str, Any],
        provider: ProviderDNSClient,
        record: dict[str, Any],
    ) -> None:
        """Delete ``record`` from the provider while retaining disabled local history.

        Args:
            zone: Zone dictionary.
            provider: Active provider client.
            record: Record dictionary.
        """
        if record.get("provider_record_id"):
            print_info("Disabling: Deleting record from provider...")
            if provider.delete_record(
                zone["provider_zone_id"], record["provider_record_id"]
            ):
                print_success("Record deleted from provider!")
            else:
                print_warning("Failed to delete from provider (may not exist)")
        else:
            print_info("No provider_record_id - skipping provider deletion")

        self.db.update_record(
            record["id"],
            enabled=False,
            provider_record_id=None,
            sync_status=SyncStatus.LOCAL_ONLY,
        )
        print_success("Record disabled! (kept in database for history)")
