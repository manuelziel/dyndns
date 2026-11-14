#!/usr/bin/env python3
"""REST record recovery, audit persistence, and summary helpers for forced updates.

Handles per-record REST API ID resolution, missing record creation, automatic
404 recreation, SQLite IP/audit logging, and CLI update summary output.

Author: Manuel Ziel
License: MIT
"""

################################################################################
# IMPORTS & DEPENDENCIES
################################################################################

from typing import Any

from src.api import ProviderDNSClient
from src.core.constants import RecordType, SyncStatus, UpdateStatus
from src.core.exceptions import (
    APIError,
    DatabaseError,
    RecordNotFoundError,
    ZoneNotFoundError,
)
from src.network import NetworkData
from src.utils.colors import Colors

from ..helpers.input import get_placeholder_ip
from ..helpers.output import (
    print_error,
    print_info,
    print_subsection,
    print_success,
    print_warning,
    row_to_dict,
)

################################################################################
# RECORD REST RECOVERY MIXIN
################################################################################


class RecordRestRecoveryMixin:
    """Mixin providing per-record REST recovery and update audit helpers."""

    config: Any
    logger: Any
    db: Any

    def _get_target_ip(
        self, record: dict[str, Any], network: NetworkData
    ) -> str | None:
        """Return detected public IP matching ``record['record_type']``.

        Args:
            record: Record dictionary.
            network: Detected public IP data.

        Returns:
            Target IP string or ``None`` if unavailable/unsupported.
        """
        if record["record_type"] == RecordType.A:
            return network.ipv4_address
        if record["record_type"] == RecordType.AAAA:
            return network.ipv6_address
        print_warning(
            f"{record['record_name']} ({record['record_type']}) - Unsupported record type"
        )
        return None

    def _ensure_provider_record_id(
        self, record: dict[str, Any], provider: ProviderDNSClient
    ) -> bool:
        """Ensure ``record`` has ``provider_record_id``, resolving or creating it.

        Args:
            record: Record dictionary (mutated in-place when resolved).
            provider: Active provider client.

        Returns:
            True if ``provider_record_id`` is available, False otherwise.
        """
        if record.get("provider_record_id"):
            return True
        print_info(
            f"{record['record_name']} ({record['record_type']}) - Syncing with provider..."
        )
        sync_errors = (ValueError, KeyError, TypeError, APIError, ZoneNotFoundError, DatabaseError)
        try:
            zone_row = self.db.get_zone_by_id(record["zone_id"])
            if not zone_row:
                raise ZoneNotFoundError(f"Zone {record['zone_id']} not found")
            zone = row_to_dict(zone_row)
            if not zone.get("provider_zone_id"):
                raise APIError(f"Zone '{zone['zone_name']}' has no provider_zone_id")

            prov_id = provider.find_record_id(
                zone["provider_zone_id"], record["record_name"], record["record_type"]
            )
            if prov_id:
                self.db.update_record(record["id"], provider_record_id=prov_id)
                record["provider_record_id"] = prov_id
                return True
            return self._create_provider_record_and_update(record, zone, provider)
        except sync_errors as exc:
            print_error(f"{record['record_name']} ({record['record_type']}) - Sync failed: {exc}")
            self.logger.error(f"Provider sync failed for record {record['id']}: {exc}")
            return False

    def _create_provider_record_and_update(
        self,
        record: dict[str, Any],
        zone: dict[str, Any],
        provider: ProviderDNSClient,
    ) -> bool:
        """Create missing record at the provider and store its ``provider_record_id``.

        Args:
            record: Record dictionary.
            zone: Zone dictionary.
            provider: Active provider client.

        Returns:
            True if created and linked, False otherwise.
        """
        print_warning(
            f"{record['record_name']} ({record['record_type']}) "
            "- Not found in provider, creating..."
        )
        if self._create_provider_record(record, zone, provider):
            prov_id = provider.find_record_id(
                zone["provider_zone_id"], record["record_name"], record["record_type"]
            )
            if prov_id:
                self.db.update_record(record["id"], provider_record_id=prov_id)
                record["provider_record_id"] = prov_id
                print_success(
                    f"{record['record_name']} ({record['record_type']}) - Created successfully"
                )
                return True
        print_error(
            f"{record['record_name']} ({record['record_type']}) "
            "- Failed to create record in provider"
        )
        return False

    def _create_provider_record(
        self,
        record: dict[str, Any],
        zone: dict[str, Any],
        provider: ProviderDNSClient,
    ) -> bool:
        """Create ``record`` remotely with a placeholder IP address.

        Args:
            record: Record dictionary.
            zone: Zone dictionary.
            provider: Active provider client.

        Returns:
            True on API creation success, False otherwise.
        """
        try:
            content = get_placeholder_ip(record["record_type"])
            api_record = provider.build_record_dict(
                record["record_name"],
                record["record_type"],
                content,
                record.get("ttl", self.config.dns_default_ttl),
                not record.get("enabled", True),
            )
            if provider.create_records(zone["provider_zone_id"], [api_record]):
                self.logger.info(
                    f"Created record '{record['record_name']}' ({record['record_type']}) "
                    f"in provider zone {zone['zone_name']}"
                )
                return True
            self.logger.error("Provider API returned failure for record creation")
            return False
        except (ValueError, KeyError, TypeError, APIError) as exc:
            self.logger.error(f"Failed to create record '{record['record_name']}': {exc}")
            return False

    def _update_dns_record(
        self,
        record: dict[str, Any],
        provider: ProviderDNSClient,
        old_ip: str | None,
        new_ip: str,
    ) -> bool:
        """Update ``record`` via REST API, recreating automatically on ``404``.

        Args:
            record: Record dictionary.
            provider: Active provider client.
            old_ip: Previous IP address or ``None``.
            new_ip: Target IP address.

        Returns:
            True on success, False otherwise.
        """
        try:
            zone_row = self.db.get_zone_by_id(record["zone_id"])
            if not zone_row:
                raise ZoneNotFoundError(f"Zone {record['zone_id']} not found")
            zone = row_to_dict(zone_row)
            if not zone.get("provider_zone_id") or not record.get("provider_record_id"):
                raise APIError("Missing provider_zone_id or provider_record_id")
            try:
                if not provider.update_record(
                    zone_id=zone["provider_zone_id"],
                    record_id=record["provider_record_id"],
                    content=new_ip,
                    ttl=record.get("ttl", self.config.dns_default_ttl),
                ):
                    raise APIError("Provider API update failed")
            except RecordNotFoundError:
                return self._recreate_and_update_dns_record(
                    zone, record, provider, old_ip, new_ip
                )
            self._save_dns_update_success(record, old_ip, new_ip)
            return True
        except (ValueError, TypeError, APIError, ZoneNotFoundError, DatabaseError) as exc:
            self._save_dns_update_failure(record, old_ip, new_ip, exc)
            return False

    def _recreate_and_update_dns_record(
        self,
        zone: dict[str, Any],
        record: dict[str, Any],
        provider: ProviderDNSClient,
        old_ip: str | None,
        new_ip: str,
    ) -> bool:
        """Recreate a deleted remote record and persist the updated IP.

        Args:
            zone: Zone dictionary.
            record: Record dictionary.
            provider: Active provider client.
            old_ip: Previous IP address or ``None``.
            new_ip: Target IP address.

        Returns:
            True on successful recreation and sync.
        """
        print_warning(
            f"{record['record_name']} ({record['record_type']}) "
            "- Record not found at provider, recreating..."
        )
        self.db.update_record(record["id"], provider_record_id=None)
        api_record = provider.build_record_dict(
            record["record_name"],
            record["record_type"],
            new_ip,
            record.get("ttl", self.config.dns_default_ttl),
            not record.get("enabled", True),
        )
        if not provider.create_records(zone["provider_zone_id"], [api_record]):
            raise APIError("Failed to recreate record at provider")

        sync_stats = self._sync_zone_with_provider(zone, provider)  # type: ignore[attr-defined]
        if not sync_stats or sync_stats.get(SyncStatus.SYNCED, 0) == 0:
            raise APIError("Failed to sync after record recreation")
        self._save_dns_update_success(record, old_ip, new_ip)
        print_success(
            f"{record['record_name']} ({record['record_type']}) "
            f"- Recreated and updated to {new_ip}"
        )
        return True

    def _save_dns_update_success(
        self, record: dict[str, Any], old_ip: str | None, new_ip: str
    ) -> None:
        """Record a successful DNS update in SQLite and print confirmation.

        Args:
            record: Record dictionary.
            old_ip: Previous IP address or ``None``.
            new_ip: Newly applied IP address.
        """
        self.db.update_ip_address(
            record_id=record["id"], ip_address=new_ip, changed=True
        )
        self.db.log_dns_update(
            record_id=record["id"],
            old_ip=old_ip,
            new_ip=new_ip,
            status=UpdateStatus.SUCCESS,
            error_message=None,
        )
        print_success(
            f"{record['record_name']} ({record['record_type']}) - Updated to {new_ip}"
        )

    def _save_dns_update_failure(
        self,
        record: dict[str, Any],
        old_ip: str | None,
        new_ip: str,
        exc: Exception,
    ) -> None:
        """Record a failed DNS update attempt in SQLite and journal logs.

        Args:
            record: Record dictionary.
            old_ip: Previous IP address or ``None``.
            new_ip: Attempted IP address.
            exc: Raised exception instance.
        """
        print_error(
            f"{record['record_name']} ({record['record_type']}) - Update failed: {exc}"
        )
        self.db.log_dns_update(
            record_id=record["id"],
            old_ip=old_ip,
            new_ip=new_ip,
            status=UpdateStatus.FAILED,
            error_message=str(exc),
        )
        self.logger.error(f"DNS update failed for record {record['id']}: {exc}")

    def _display_update_summary(self, stats: dict[str, int]) -> None:
        """Display aggregate forced DNS update summary statistics.

        Args:
            stats: Completed update statistics dictionary.
        """
        print_subsection("Update Summary")
        print(f"{Colors.BOLD}Total records:{Colors.NC}    {stats[UpdateStatus.TOTAL]}")
        print(f"{Colors.GREEN}Updated:{Colors.NC}        {stats[UpdateStatus.UPDATED]}")
        print(f"{Colors.RED}Failed:{Colors.NC}         {stats[UpdateStatus.FAILED]}")
        print(f"{Colors.YELLOW}Skipped:{Colors.NC}        {stats[UpdateStatus.SKIPPED]}\n")

        if stats[UpdateStatus.UPDATED] > 0:
            print_success(
                f"Force update completed! {stats[UpdateStatus.UPDATED]} records updated."
            )
        elif stats[UpdateStatus.FAILED] > 0:
            print_error("Force update completed with errors. Check logs for details.")
        else:
            print_info("No records were updated.")
