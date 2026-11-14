#!/usr/bin/env python3
"""Interactive DNS record deletion and manual zone-sync workflows.

Handles destructive record removal across local SQLite and remote provider APIs,
plus interactive provider-to-local record reconciliation.

Author: Manuel Ziel
License: MIT
"""

################################################################################
# IMPORTS & DEPENDENCIES
################################################################################

from datetime import datetime
from typing import Any

from src.api import ProviderDNSClient
from src.core.constants import DatabaseDefaults, SyncStatus, UpdateMethod
from src.core.exceptions import APIError, DatabaseError, ZoneNotFoundError
from src.utils.colors import Colors

from ..helpers.input import confirm_action, select_record, select_zone, wait_for_enter
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
# RECORD DELETE & SYNC MIXIN
################################################################################


class RecordDeleteSyncMixin:
    """Mixin providing interactive DNS record deletion and zone synchronization."""

    config: Any
    logger: Any
    db: Any

    def delete_record(self) -> None:
        """Delete a DNS record from the local database and remote provider."""
        print_section("Delete Record")
        zone = select_zone(self.db, prompt="Select zone")
        if not zone:
            return
        record_row = select_record(
            self.db, zone["id"], prompt="Select record to DELETE"
        )
        if not record_row:
            return

        record = row_to_dict(record_row)
        self._print_delete_warnings(record)
        if not confirm_action(
            f"Really delete record '{record['record_name']}'?", default=False
        ):
            print_info("Cancelled.")
            wait_for_enter()
            return

        self._execute_record_deletion(zone, record)
        wait_for_enter()

    def sync_zone_from_provider(self) -> None:
        """Compare remote provider records against local database state."""
        print_section("Sync Records from Provider")
        zone = select_zone(self.db, prompt="Select zone to sync")
        if not zone:
            return

        provider = self._get_provider_with_credentials(  # type: ignore[attr-defined]
            zone, warn_on_missing=True, require_zone_id=False
        )
        if not provider:
            wait_for_enter()
            return

        try:
            synced_zone = self._ensure_provider_zone_id_on_sync(zone, provider)
            if synced_zone:
                self._reconcile_zone_records(synced_zone, provider)
        finally:
            provider.close()
        wait_for_enter()

    ############################################################################
    # Delete & Zone Sync Helpers
    ############################################################################

    def _print_delete_warnings(self, record: dict[str, Any]) -> None:
        """Print destructive deletion warning summary for ``record``.

        Args:
            record: Record dictionary.
        """
        print_warning("WARNING: This will delete:")
        print(
            f"   {Colors.RED}•{Colors.NC} Record: "
            f"{Colors.BOLD}{record['record_name']}{Colors.NC} ({record['record_type']})"
        )
        print(f"   {Colors.RED}•{Colors.NC} From local database")
        print(f"   {Colors.RED}•{Colors.NC} From DNS provider (if exists)")
        print(f"   {Colors.RED}•{Colors.NC} IP address history")
        print(f"   {Colors.RED}•{Colors.NC} Update history")

    def _execute_record_deletion(
        self, zone: dict[str, Any], record: dict[str, Any]
    ) -> None:
        """Delete ``record`` remotely (if linked) and remove it from SQLite.

        Args:
            zone: Zone dictionary.
            record: Record dictionary.
        """
        try:
            if record.get("provider_record_id"):
                self._delete_remote_provider_record(zone, record)
            self.db.delete_record(record["id"])
            print_success(f"Record '{record['record_name']}' deleted successfully!")
            if self.config.dns_update_method == UpdateMethod.DYNDNS:
                self._sync_dyndns_bundle_if_needed(zone["id"])  # type: ignore[attr-defined]
        except (ValueError, TypeError, APIError, DatabaseError) as exc:
            print_error(f"Error deleting record: {exc}")
            self.logger.error(f"Failed to delete record {record['id']}: {exc}")

    def _delete_remote_provider_record(
        self, zone: dict[str, Any], record: dict[str, Any]
    ) -> None:
        """Delete ``record`` at the remote DNS provider when credentials exist.

        Args:
            zone: Zone dictionary.
            record: Record dictionary with ``provider_record_id``.
        """
        provider = self._get_provider_with_credentials(  # type: ignore[attr-defined]
            zone, warn_on_missing=False, require_zone_id=False
        )
        if not provider:
            print_warning("Cannot delete from provider (missing credentials or zone ID)")
            return
        try:
            if not zone.get("provider_zone_id"):
                print_warning(
                    "Cannot delete from provider (missing credentials or zone ID)"
                )
                return
            print_info("Deleting record from provider...")
            if provider.delete_record(
                zone["provider_zone_id"], record["provider_record_id"]
            ):
                print_success("Deleted from provider")
            else:
                print_warning("Failed to delete from provider (record may not exist)")
        finally:
            provider.close()

    def _ensure_provider_zone_id_on_sync(
        self, zone: dict[str, Any], provider: ProviderDNSClient
    ) -> dict[str, Any] | None:
        """Ensure ``provider_zone_id`` is populated before manual zone sync.

        Args:
            zone: Zone dictionary.
            provider: Active provider client.

        Returns:
            Reloaded zone dictionary, or ``None`` if resolution failed.
        """
        if zone.get("provider_zone_id"):
            return zone
        print_info("Zone has no provider_zone_id - fetching from provider...")
        if not self._sync_zone_id(zone, provider):  # type: ignore[attr-defined]
            print_error("Failed to fetch provider_zone_id from provider.")
            return None
        zone_row = self.db.get_zone_by_id(zone["id"])
        if not zone_row:
            print_error("Failed to reload zone after sync.")
            return None
        return row_to_dict(zone_row)

    def _reconcile_zone_records(
        self, zone: dict[str, Any], provider: ProviderDNSClient
    ) -> None:
        """Fetch provider records for ``zone`` and reconcile sync statuses.

        Args:
            zone: Zone dictionary.
            provider: Active provider client.
        """
        try:
            print_info(
                f"Fetching records from provider for zone '{zone['zone_name']}'..."
            )
            provider_records = provider.get_zone_records(zone["provider_zone_id"])
            if provider_records is None:
                print_error("Failed to fetch records from provider")
                return

            local_rows = self.db.get_records_by_zone(zone["id"], enabled_only=False)
            local_map = {row_to_dict(r)["id"]: row_to_dict(r) for r in local_rows}
            stats = {
                SyncStatus.SYNCED: 0,
                SyncStatus.NEW: 0,
                SyncStatus.ORPHANED: 0,
                SyncStatus.UPDATED: 0,
            }
            matched_ids = self._match_provider_to_local_records(
                provider_records, local_map, stats
            )
            self._mark_orphaned_local_records(local_map, matched_ids, stats)
            self._print_sync_results_summary(stats)
        except ZoneNotFoundError as exc:
            print_error(f"Zone not found at provider: {exc}")
            self.logger.error(f"Zone not found during sync: {exc}")
        except (ValueError, KeyError, TypeError, DatabaseError) as exc:
            print_error(f"Error during zone sync: {exc}")
            self.logger.error(f"Failed to sync zone {zone['id']}: {exc}")

    def _match_provider_to_local_records(
        self,
        provider_records: list[dict[str, Any]],
        local_records_dict: dict[int, dict[str, Any]],
        stats: dict[str, int],
    ) -> set[int]:
        """Match remote provider records against ``local_records_dict``.

        Args:
            provider_records: Remote provider record dictionaries.
            local_records_dict: Mapping of local record ID to record dict.
            stats: Mutable sync statistics dictionary.

        Returns:
            Set of local record IDs matched at the provider.
        """
        matched_local_ids: set[int] = set()
        print_info(f"Analyzing {len(provider_records)} provider records...\n")
        for p_rec in provider_records:
            local_id = self._try_match_provider_record(p_rec, local_records_dict, stats)
            if local_id is not None:
                matched_local_ids.add(local_id)
            else:
                stats[SyncStatus.NEW] += 1
                print_info(
                    f"  New at provider: {p_rec['name']} ({p_rec['type']}) - ID: {p_rec['id']}"
                )
        return matched_local_ids

    def _try_match_provider_record(
        self,
        p_rec: dict[str, Any],
        local_records_dict: dict[int, dict[str, Any]],
        stats: dict[str, int],
    ) -> int | None:
        """Find matching local record for ``p_rec`` and update its sync state.

        Args:
            p_rec: Single remote provider record dictionary.
            local_records_dict: Mapping of local record ID to record dict.
            stats: Mutable sync statistics dictionary.

        Returns:
            Matched local record ID or ``None`` when unmatched.
        """
        for l_id, l_rec in local_records_dict.items():
            if (
                l_rec["record_name"] == p_rec["name"]
                and l_rec["record_type"] == p_rec["type"]
            ):
                if (
                    l_rec.get("provider_record_id") != p_rec["id"]
                    or l_rec.get("sync_status") != SyncStatus.SYNCED
                ):
                    self.db.update_record(
                        l_id,
                        provider_record_id=p_rec["id"],
                        sync_status=SyncStatus.SYNCED,
                        last_synced_at=datetime.now().strftime(
                            DatabaseDefaults.DB_TIMESTAMP_FORMAT
                        ),
                    )
                    stats[SyncStatus.UPDATED] += 1
                    print_success(f"  Synced: {p_rec['name']} ({p_rec['type']})")
                else:
                    stats[SyncStatus.SYNCED] += 1
                return l_id
        return None

    def _mark_orphaned_local_records(
        self,
        local_records_dict: dict[int, dict[str, Any]],
        matched_local_ids: set[int],
        stats: dict[str, int],
    ) -> None:
        """Mark unmatched local records as orphaned in SQLite.

        Args:
            local_records_dict: Mapping of local record ID to record dict.
            matched_local_ids: Set of matched local record IDs.
            stats: Mutable sync statistics dictionary.
        """
        now_ts = datetime.now().strftime(DatabaseDefaults.DB_TIMESTAMP_FORMAT)
        for l_id, l_rec in local_records_dict.items():
            if l_id not in matched_local_ids:
                if l_rec.get("sync_status") != SyncStatus.ORPHANED:
                    self.db.update_sync_status(
                        l_id, sync_status=SyncStatus.ORPHANED, last_synced_at=now_ts
                    )
                stats[SyncStatus.ORPHANED] += 1
                print_warning(
                    f"  Orphaned: {l_rec['record_name']} ({l_rec['record_type']}) "
                    "- Not found at provider"
                )

    def _print_sync_results_summary(self, stats: dict[str, int]) -> None:
        """Display formatted zone synchronization summary statistics.

        Args:
            stats: Completed sync statistics dictionary.
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
