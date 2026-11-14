#!/usr/bin/env python3
"""Helper class for native DynDNS URL bundle lifecycle management.

Encapsulates activation, URL caching, domain synchronization, and execution of
provider native DynDNS update URLs (``GET updateUrl?q=...``).

Author: Manuel Ziel
License: MIT
"""

################################################################################
# IMPORTS & DEPENDENCIES
################################################################################

import json
from typing import Any

from ...api.provider import ProviderDNSClient
from ...core.constants import DatabaseDefaults, RecordType, SyncStatus, UpdateStatus
from ...core.exceptions import APIError, DatabaseError, DynDNSException
from ...utils.colors import LOG_SYMBOLS

################################################################################
# DYNDNS BUNDLE HANDLER CLASS
################################################################################


class DynDNSBundleHandler:
    """Manages IONOS DynDNS bundle activation and ``updateUrl`` execution.

    Attributes:
        config: ``ConfigManager`` instance.
        database: ``Database`` manager instance.
        network: ``NetworkData`` instance.
        logger: Logger instance.
    """

    def __init__(
        self, config: Any, database: Any, network: Any, logger: Any
    ) -> None:
        """Initialize DynDNS bundle handler.

        Args:
            config: ``ConfigManager`` instance.
            database: ``Database`` manager instance.
            network: ``NetworkData`` instance.
            logger: Logger instance.
        """
        self.config = config
        self.database = database
        self.network = network
        self.logger = logger

    ############################################################################
    # BUNDLE METADATA HELPERS
    ############################################################################

    def _get_bundle_domain_names(self, zone: dict[str, Any]) -> list[str]:
        """Resolve sorted unique enabled domain names for ``zone``'s bundle.

        Args:
            zone: Zone dictionary.

        Returns:
            Sorted list of unique domain/subdomain FQDNs.
        """
        records = zone.get("records") or [
            dict(r) for r in self.database.get_records_by_zone(zone["id"], enabled_only=True)
        ]
        domain_names = sorted({r["record_name"] for r in records if r.get("record_name")})
        return domain_names or [zone["zone_name"]]

    def _get_stored_bundle_domains(self, dyndns_config: dict[str, Any]) -> list[str]:
        """Parse the stored JSON domain list from ``dyndns_config``.

        Args:
            dyndns_config: DynDNS configuration dictionary from SQLite.

        Returns:
            Sorted list of stored domain names.
        """
        raw_domains = dyndns_config.get("domains")
        if not raw_domains:
            return []
        try:
            parsed = json.loads(raw_domains) if isinstance(raw_domains, str) else raw_domains
            if isinstance(parsed, list):
                return sorted({str(d) for d in parsed if d})
        except (json.JSONDecodeError, TypeError, ValueError):
            pass
        return []

    @staticmethod
    def _get_bundle_id_key(zone_id: int) -> str:
        """Build the ``app_config`` key storing ``zone_id``'s provider bundle UUID.

        Args:
            zone_id: Database zone ID.

        Returns:
            ``app_config`` key string.
        """
        return f"{DatabaseDefaults.DYNDNS_BUNDLE_ID_PREFIX}{zone_id}"

    ############################################################################
    # BUNDLE ACTIVATION & SYNCHRONIZATION
    ############################################################################

    def get_or_activate_bundle(
        self,
        client: ProviderDNSClient,
        zone: dict[str, Any],
        dyndns_config: dict[str, Any],
        force_activate: bool = False,
    ) -> str | None:
        """Return cached ``updateUrl`` or activate a new bundle on the provider.

        Args:
            client: Active ``ProviderDNSClient``.
            zone: Zone dictionary.
            dyndns_config: Decrypted ``dyndns_config`` dictionary.
            force_activate: When True, re-activates even if ``update_url`` is cached.

        Returns:
            Active ``updateUrl`` string or ``None`` on error.
        """
        update_url = dyndns_config.get("update_url")
        if update_url and not force_activate:
            return str(update_url)

        self.logger.info(
            f"Activating DynDNS bundle on provider for zone '{zone['zone_name']}'..."
        )
        domain_names = self._get_bundle_domain_names(zone)
        try:
            activation = client.activate_dyndns(
                domains=domain_names, description=f"DynDNS {zone['zone_name']}"
            )
            if activation and activation.get("updateUrl"):
                return self._save_activated_bundle(
                    zone, dyndns_config, activation, domain_names
                )
            self.logger.error(
                f"Provider activate_dyndns returned no updateUrl for zone '{zone['zone_name']}'"
            )
            return None
        except (APIError, DatabaseError, DynDNSException) as exc:
            self.logger.error(f"Error activating DynDNS bundle for '{zone['zone_name']}': {exc}")
            return None

    def _save_activated_bundle(
        self,
        zone: dict[str, Any],
        dyndns_config: dict[str, Any],
        activation: dict[str, Any],
        domain_names: list[str],
    ) -> str:
        """Persist newly activated bundle metadata and ``updateUrl`` in SQLite.

        Args:
            zone: Zone dictionary.
            dyndns_config: Existing decrypted ``dyndns_config`` dictionary.
            activation: Provider response dictionary from ``activate_dyndns``.
            domain_names: Included domain names.

        Returns:
            Newly stored ``updateUrl`` string.
        """
        update_url = str(activation["updateUrl"])
        self.database.set_dyndns_config(
            zone_id=zone["id"],
            bulk_id=dyndns_config.get("bulk_id", ""),
            api_key=dyndns_config["api_key"],
            update_url=update_url,
            description=f"DynDNS {zone['zone_name']}",
            domains=activation.get("domains", domain_names),
        )
        bundle_id = activation.get("bulkId")
        if bundle_id:
            self.database.set_config_by_key(
                self._get_bundle_id_key(zone["id"]), str(bundle_id)
            )
        self.logger.info(f"Saved new updateUrl to database for zone '{zone['zone_name']}'")
        return update_url

    def sync_or_activate_dyndns_bundle(
        self,
        client: ProviderDNSClient,
        zone: dict[str, Any],
        force_sync: bool = False,
    ) -> str | None:
        """Verify and synchronize native DynDNS bundle domains on the provider.

        Args:
            client: Active ``ProviderDNSClient``.
            zone: Zone dictionary containing ``records`` and ``zone_name``.
            force_sync: Force provider bundle update even when domains match.

        Returns:
            Active ``updateUrl`` string or ``None`` on failure.
        """
        dyndns_row = self.database.get_dyndns_config_by_zone(zone["id"])
        if not dyndns_row:
            self.logger.warning(
                f"No DynDNS config found in database for zone '{zone['zone_name']}'"
            )
            return None
        dyndns_config = dict(dyndns_row)
        domain_names = self._get_bundle_domain_names(zone)
        stored_domains = self._get_stored_bundle_domains(dyndns_config)
        update_url = dyndns_config.get("update_url")

        if update_url and not force_sync and stored_domains == domain_names:
            self.logger.info(
                f"Verified DynDNS bundle for zone '{zone['zone_name']}' "
                f"({len(domain_names)} domain(s))"
            )
            return str(update_url)
        if update_url and self._try_update_existing_bundle(
            client, zone, dyndns_config, domain_names
        ):
            return str(update_url)
        return self.get_or_activate_bundle(
            client, zone, dyndns_config, force_activate=True
        )

    def _try_update_existing_bundle(
        self,
        client: ProviderDNSClient,
        zone: dict[str, Any],
        dyndns_config: dict[str, Any],
        domain_names: list[str],
    ) -> bool:
        """Update an existing DynDNS bundle in-place via ``PUT /dyndns/{bulkId}``.

        Args:
            client: Active ``ProviderDNSClient``.
            zone: Zone dictionary.
            dyndns_config: Decrypted ``dyndns_config`` dictionary.
            domain_names: Target domain list.

        Returns:
            True if updated in-place, False if full re-activation is needed.
        """
        bundle_id = self.database.get_config_by_key(self._get_bundle_id_key(zone["id"]))
        if not bundle_id:
            return False
        try:
            if client.update_dyndns_config(
                bulk_id=bundle_id,
                domains=domain_names,
                description=f"DynDNS {zone['zone_name']}",
            ):
                self.database.set_dyndns_config(
                    zone_id=zone["id"],
                    bulk_id=dyndns_config.get("bulk_id", ""),
                    api_key=dyndns_config["api_key"],
                    update_url=dyndns_config.get("update_url"),
                    description=f"DynDNS {zone['zone_name']}",
                    domains=domain_names,
                )
                self.logger.info(
                    f"Synchronized DynDNS bundle {bundle_id} ({len(domain_names)} domain(s))"
                )
                return True
        except (APIError, DatabaseError, DynDNSException) as exc:
            self.logger.warning(f"Failed to update existing bundle {bundle_id}: {exc}")
        return False

    ############################################################################
    # UPDATE URL EXECUTION & CACHE RESET
    ############################################################################

    def execute_dyndns_update(
        self,
        client: ProviderDNSClient,
        zone: dict[str, Any],
        target_records: list[dict[str, Any]],
    ) -> tuple[bool, int, int]:
        """Execute a zone's DynDNS ``updateUrl`` and record outcomes in SQLite.

        Args:
            client: Active ``ProviderDNSClient``.
            zone: Zone dictionary.
            target_records: Record dictionaries covered by the update.

        Returns:
            Tuple ``(success, updates_succeeded, updates_failed)``.
        """
        dyndns_row = self.database.get_dyndns_config_by_zone(zone["id"])
        if not dyndns_row:
            self.logger.debug(f"No DynDNS config found for zone {zone['id']}")
            return False, 0, 0
        dyndns_config = dict(dyndns_row)
        had_cached_url = bool(dyndns_config.get("update_url"))
        update_url = self.get_or_activate_bundle(client, zone, dyndns_config)
        if not update_url:
            return False, 0, 0

        success = client.execute_dyndns_update_url(
            update_url=update_url,
            ipv4=self.network.ipv4_address,
            ipv6=self.network.ipv6_address,
        )
        if not success and had_cached_url:
            update_url = self.get_or_activate_bundle(
                client, zone, dyndns_config, force_activate=True
            )
            if update_url:
                success = client.execute_dyndns_update_url(
                    update_url=update_url,
                    ipv4=self.network.ipv4_address,
                    ipv6=self.network.ipv6_address,
                )
        if not success:
            return False, 0, 0
        succeeded, failed = self._record_successful_update(target_records)
        return True, succeeded, failed

    def _record_successful_update(
        self, target_records: list[dict[str, Any]]
    ) -> tuple[int, int]:
        """Persist successful DynDNS URL updates across ``target_records``.

        Args:
            target_records: Record dictionaries updated by the bundle call.

        Returns:
            Tuple ``(updates_succeeded, updates_failed)``.
        """
        updates_succeeded = 0
        updates_failed = 0
        for record in target_records:
            new_ip = record.get("new_ip") or (
                self.network.ipv4_address
                if record["record_type"] == RecordType.A
                else self.network.ipv6_address
            )
            if not new_ip:
                continue
            if self._persist_dyndns_record_update(record, new_ip):
                if record.get("needs_update"):
                    updates_succeeded += 1
            else:
                updates_failed += 1
        return updates_succeeded, updates_failed

    def _persist_dyndns_record_update(
        self, record: dict[str, Any], new_ip: str
    ) -> bool:
        """Persist IP state and audit history for one record after DynDNS GET.

        Args:
            record: Record dictionary.
            new_ip: Propagated IP address string.

        Returns:
            True if SQLite updates succeeded, False otherwise.
        """
        old_ip = record.get("old_ip")
        try:
            self.database.update_ip_address(
                record["id"], ip_address=new_ip, changed=bool(record.get("needs_update"))
            )
            if record.get("sync_status") != SyncStatus.SYNCED:
                self.database.update_sync_status(record["id"], SyncStatus.SYNCED)
            if record.get("needs_update"):
                self.database.log_dns_update(
                    record_id=record["id"],
                    old_ip=old_ip,
                    new_ip=new_ip,
                    status=UpdateStatus.SUCCESS,
                )
                self.logger.success(
                    f"[DYNDNS TRIGGERED] Record '{record['record_name']}' "
                    f"({record['record_type']}) updated: {old_ip or 'none'} "
                    f"{LOG_SYMBOLS['ARROW']} {new_ip}"
                )
            else:
                self.logger.debug(
                    f"Record '{record['record_name']}' ({record['record_type']}) "
                    f"verified via DynDNS URL ({new_ip})"
                )
            return True
        except DatabaseError as exc:
            self.logger.error(f"Database error updating '{record['record_name']}': {exc}")
            return False

    def reset_cached_url(self, zone_id: int, zone_name: str) -> bool:
        """Clear cached ``updateUrl`` and bundle UUID for ``zone_id`` in SQLite.

        Args:
            zone_id: Database zone ID.
            zone_name: Zone domain name for log output.

        Returns:
            True if cleared, False on missing config or database error.
        """
        try:
            dyndns_config = self.database.get_dyndns_config_by_zone(zone_id)
            if not dyndns_config:
                return False
            self.database.set_dyndns_config(
                zone_id=zone_id,
                bulk_id=dyndns_config.get("bulk_id", ""),
                api_key=dyndns_config["api_key"],
                update_url=None,
                description=dyndns_config.get("description"),
                domains=dyndns_config.get("domains"),
            )
            self.database.delete_config_by_key(self._get_bundle_id_key(zone_id))
            self.logger.info(
                f"Reset cached DynDNS updateUrl for zone '{zone_name}' "
                "to rebind newly created records on provider"
            )
            return True
        except DatabaseError as exc:
            self.logger.error(
                f"Failed to reset cached DynDNS updateUrl for '{zone_name}': {exc}"
            )
            return False
