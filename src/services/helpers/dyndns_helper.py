#!/usr/bin/env python3
"""Helper class for native DynDNS URL bundle lifecycle management.

Encapsulates activation, URL caching, and execution of provider native DynDNS
update URLs (`GET updateUrl?q=...`), ensuring high cohesion and decoupling
from direct REST API record manipulation.

Author: Manuel Ziel
License: MIT
"""

################################################################################
# IMPORTS
################################################################################

import json
from typing import Any, Dict, List, Optional, Tuple

from src.api.provider import ProviderDNSClient
from src.core.constants import DatabaseDefaults, RecordType, SyncStatus, UpdateStatus
from src.core.exceptions import DatabaseError, DynDNSException, APIError
from src.utils.colors import LOG_SYMBOLS

################################################################################
# DYNDNS BUNDLE HANDLER CLASS
################################################################################


class DynDNSBundleHandler:
    """Handler encapsulating DynDNS bundle activation and updateUrl execution.

    Attributes:
        config: Configuration object.
        database: Database manager instance.
        network: NetworkData instance for IPs.
        logger: Logger instance.
    """

    def __init__(
        self, config: Any, database: Any, network: Any, logger: Any
    ) -> None:
        """Initialize DynDNS bundle handler.

        Args:
            config: Configuration object.
            database: Database manager instance.
            network: NetworkData instance.
            logger: Logger instance.
        """
        self.config = config
        self.database = database
        self.network = network
        self.logger = logger


    def _get_bundle_domain_names(self, zone: Dict[str, Any]) -> List[str]:
        """Resolve sorted list of enabled domain names for a zone's DynDNS bundle.

        Args:
            zone: Zone dictionary.

        Returns:
            Sorted list of unique domain names.
        """
        records = zone.get("records") or [
            dict(r) for r in self.database.get_records_by_zone(zone["id"], enabled_only=True)
        ]
        domain_names = sorted(list({r["record_name"] for r in records if r.get("record_name")}))
        return domain_names or [zone["zone_name"]]


    def _get_stored_bundle_domains(self, dyndns_config: Dict[str, Any]) -> List[str]:
        """Parse the stored domain list from a dyndns_config dictionary.

        Args:
            dyndns_config: DynDNS configuration dictionary from database.

        Returns:
            Sorted list of unique stored domain names.
        """
        raw_domains = dyndns_config.get("domains")
        if not raw_domains:
            return []
        try:
            parsed = json.loads(raw_domains) if isinstance(raw_domains, str) else raw_domains
            if isinstance(parsed, list):
                return sorted(list({str(d) for d in parsed if d}))
        except (json.JSONDecodeError, TypeError, ValueError):
            pass
        return []


    def _get_bundle_id_key(self, zone_id: int) -> str:
        """Build the app_config key used to store a zone's DynDNS bundle UUID.

        Args:
            zone_id: Database zone ID.

        Returns:
            Configuration key string for the zone's provider bundle bulkId.
        """
        return f"{DatabaseDefaults.DYNDNS_BUNDLE_ID_PREFIX}{zone_id}"


    def get_or_activate_bundle(
        self,
        client: ProviderDNSClient,
        zone: Dict[str, Any],
        dyndns_config: Dict[str, Any],
        force_activate: bool = False,
    ) -> Optional[str]:
        """Obtain cached updateUrl or activate DynDNS bundle on provider.

        Args:
            client: Provider client instance.
            zone: Zone dictionary.
            dyndns_config: DynDNS configuration dictionary.
            force_activate: If True, bypasses cached update_url and re-activates bundle.

        Returns:
            Active updateUrl string or None if activation failed.
        """
        update_url = dyndns_config.get("update_url")
        if update_url and not force_activate:
            return update_url

        self.logger.info(f"Activating DynDNS bundle on provider for zone '{zone['zone_name']}'...")
        domain_names = self._get_bundle_domain_names(zone)

        try:
            activation = client.activate_dyndns(domains=domain_names, description=f"DynDNS {zone['zone_name']}")
            if activation and activation.get("updateUrl"):
                return self._save_activated_bundle(zone, dyndns_config, activation, domain_names)

            self.logger.error(f"Provider activate_dyndns returned no updateUrl for zone '{zone['zone_name']}'")
            return None
        except (APIError, DatabaseError, DynDNSException) as e:
            self.logger.error(f"Error activating DynDNS bundle for '{zone['zone_name']}': {e}")
            return None


    def _save_activated_bundle(
        self,
        zone: Dict[str, Any],
        dyndns_config: Dict[str, Any],
        activation: Dict[str, Any],
        domain_names: List[str],
    ) -> str:
        """Persist newly activated DynDNS bundle metadata and updateUrl in database.

        Args:
            zone: Zone dictionary.
            dyndns_config: Existing DynDNS config dictionary.
            activation: Response dictionary from provider activate_dyndns call.
            domain_names: List of domain names included in the bundle.

        Returns:
            The new updateUrl string.
        """
        update_url = activation["updateUrl"]
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
            self.database.set_config_by_key(self._get_bundle_id_key(zone["id"]), str(bundle_id))
        self.logger.info(f"Saved new updateUrl to database for zone '{zone['zone_name']}'")
        return update_url


    def sync_or_activate_dyndns_bundle(
        self,
        client: ProviderDNSClient,
        zone: Dict[str, Any],
        force_sync: bool = False,
    ) -> Optional[str]:
        """Verify and synchronize native DynDNS bundle domains on provider.

        Args:
            client: Provider client instance.
            zone: Zone dictionary containing records and zone_name.
            force_sync: If True, forces provider bundle update even if domain list is unchanged.

        Returns:
            Active updateUrl string or None on failure.
        """
        dyndns_row = self.database.get_dyndns_config_by_zone(zone["id"])
        if not dyndns_row:
            self.logger.warning(f"No DynDNS config found in database for zone '{zone['zone_name']}'")
            return None

        dyndns_config = dict(dyndns_row)
        domain_names = self._get_bundle_domain_names(zone)
        stored_domains = self._get_stored_bundle_domains(dyndns_config)
        update_url = dyndns_config.get("update_url")

        if update_url and not force_sync and stored_domains == domain_names:
            self.logger.info(
                f"Verified DynDNS bundle for zone '{zone['zone_name']}' ({len(domain_names)} domain(s))"
            )
            return update_url

        if update_url and self._try_update_existing_bundle(client, zone, dyndns_config, domain_names):
            return update_url

        return self.get_or_activate_bundle(client, zone, dyndns_config, force_activate=True)


    def _try_update_existing_bundle(
        self,
        client: ProviderDNSClient,
        zone: Dict[str, Any],
        dyndns_config: Dict[str, Any],
        domain_names: List[str],
    ) -> bool:
        """Attempt to update an existing DynDNS bundle in-place via PUT /v1/dyndns/{bulkId}.

        Args:
            client: Provider client instance.
            zone: Zone dictionary.
            dyndns_config: DynDNS configuration dictionary.
            domain_names: Updated list of domain names for the bundle.

        Returns:
            True if updated in-place successfully, False if re-activation via POST is needed.
        """
        bundle_id = self.database.get_config_by_key(self._get_bundle_id_key(zone["id"]))
        if not bundle_id:
            return False

        try:
            if client.update_dyndns_config(
                bulk_id=bundle_id, domains=domain_names, description=f"DynDNS {zone['zone_name']}"
            ):
                self.database.set_dyndns_config(
                    zone_id=zone["id"],
                    bulk_id=dyndns_config.get("bulk_id", ""),
                    api_key=dyndns_config["api_key"],
                    update_url=dyndns_config.get("update_url"),
                    description=f"DynDNS {zone['zone_name']}",
                    domains=domain_names,
                )
                self.logger.info(f"Synchronized DynDNS bundle {bundle_id} ({len(domain_names)} domain(s))")
                return True
        except (APIError, DatabaseError, DynDNSException) as e:
            self.logger.warning(f"Failed to update existing bundle {bundle_id}: {e}")
        return False


    def execute_dyndns_update(
        self,
        client: ProviderDNSClient,
        zone: Dict[str, Any],
        target_records: List[Dict[str, Any]],
    ) -> Tuple[bool, int, int]:
        """Execute DynDNS update URL for a zone and update local database.

        Args:
            client: Provider client instance.
            zone: Zone dictionary.
            target_records: List of record dictionaries to update in DB.

        Returns:
            Tuple of (success boolean, updates_succeeded count, updates_failed count).
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
            update_url=update_url, ipv4=self.network.ipv4_address, ipv6=self.network.ipv6_address
        )
        if not success and had_cached_url:
            update_url = self.get_or_activate_bundle(client, zone, dyndns_config, force_activate=True)
            if update_url:
                success = client.execute_dyndns_update_url(
                    update_url=update_url, ipv4=self.network.ipv4_address, ipv6=self.network.ipv6_address
                )
        if not success:
            return False, 0, 0

        succeeded, failed = self._record_successful_update(target_records)
        return True, succeeded, failed


    def _record_successful_update(
        self, target_records: List[Dict[str, Any]]
    ) -> Tuple[int, int]:
        """Record successful DynDNS URL updates in local SQLite database.

        Args:
            target_records: List of target record dictionaries.

        Returns:
            Tuple of (succeeded count, failed count).
        """
        updates_succeeded, updates_failed = 0, 0
        for record in target_records:
            old_ip = record.get("old_ip")
            new_ip = record.get("new_ip") or (
                self.network.ipv4_address if record["record_type"] == RecordType.A else self.network.ipv6_address
            )
            try:
                self.database.update_ip_address(record["id"], ip_address=new_ip, changed=bool(record.get("needs_update")))
                self.database.update_sync_status(record["id"], SyncStatus.SYNCED)
                if record.get("needs_update"):
                    self.database.log_dns_update(
                        record_id=record["id"], old_ip=old_ip, new_ip=new_ip, status=UpdateStatus.SUCCESS
                    )
                    updates_succeeded += 1
                    self.logger.success(
                        f"[DYNDNS TRIGGERED] Record '{record['record_name']}' ({record['record_type']}) updated: "
                        f"{old_ip or 'none'} {LOG_SYMBOLS['ARROW']} {new_ip}"
                    )
                else:
                    self.logger.debug(f"Record '{record['record_name']}' ({record['record_type']}) verified via DynDNS URL ({new_ip})")
            except DatabaseError as e:
                self.logger.error(f"Database error updating '{record['record_name']}': {e}")
                updates_failed += 1
        return updates_succeeded, updates_failed


    def reset_cached_url(self, zone_id: int, zone_name: str) -> bool:
        """Reset cached DynDNS updateUrl for a zone in database.

        Args:
            zone_id: Database zone ID.
            zone_name: Human-readable zone name for logging.

        Returns:
            True if reset successfully, False otherwise.
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
                f"to rebind newly created records on provider"
            )
            return True

        except DatabaseError as e:
            self.logger.error(
                f"Failed to reset cached DynDNS updateUrl for '{zone_name}': {e}"
            )
            return False
