#!/usr/bin/env python3
"""DNS Provider API Client for zone and record management.

Provides methods for interacting with the IONOS DNS API, including
zone retrieval, record management, and DynDNS updates.

Author: Manuel Ziel
License: MIT
"""

################################################################################
# IMPORTS & DEPENDENCIES
################################################################################

import logging
import time
from typing import Any, Dict, List, Optional

from src.core.exceptions import RecordNotFoundError, ZoneNotFoundError, APIError
from src.core.constants import HTTPStatus, HTTPHeader, HTTPHeaderValue, ProviderAPI
from .http_client import HTTPClient


################################################################################
# PROVIDER DNS API CLIENT - DNS Provider Integration
################################################################################

class ProviderDNSClient:
    """DNS Provider API Client for zone and record management.

    Provides methods for interacting with the IONOS DNS API, including
    zone retrieval, record management, and DynDNS updates.

    Attributes:
        api_key: Full API key (bulk_id.api_key format).
        config: Configuration object with provider settings.
        logger: Logger instance for API logging.
        client: HTTPClient instance for requests.
        headers: Default HTTP headers for API requests.
    """

    def __init__(self, api_key: str, config: Any, logger: Optional[Any] = None) -> None:
        """Initialize provider DNS API client.

        Args:
            api_key: Full API key (bulk_id.api_key format).
            config: ConfigManager instance with provider settings.
            logger: Logger instance. Creates default if None.
        """
        self.api_key = api_key
        self.config = config
        self.logger = logger if logger else logging.getLogger(__name__)

        self.client = HTTPClient(
            base_url=config.provider_api_base_url,
            timeout=config.provider_api_timeout,
            retries=config.provider_api_retry_attempts,
            logger=self.logger,
        )

        self.headers = {
            HTTPHeader.ACCEPT: HTTPHeaderValue.APPLICATION_JSON,
            HTTPHeader.X_API_KEY: self.api_key,
            HTTPHeader.CONTENT_TYPE: HTTPHeaderValue.APPLICATION_JSON,
        }


    def get_zones(self) -> Optional[List[Dict[str, Any]]]:
        """Fetch all DNS zones from provider.

        Returns:
            List of zone dictionaries or None on failure.
        """
        self.logger.debug("Fetching zones from provider API...")
        response = self.client.get(endpoint="/zones", headers=self.headers)

        if response is not None and response.status_code == HTTPStatus.OK:
            zones = response.json()
            self.logger.debug(f"Retrieved {len(zones)} zones from provider")
            return zones
        elif response is not None:
            self.logger.warning(
                f"Failed to fetch zones: {response.status_code} - {response.text}"
            )
            return None
        else:
            self.logger.warning("Failed to fetch zones: No response from provider")
            return None


    def get_zone_records(self, zone_id: str) -> Optional[List[Dict[str, Any]]]:
        """Fetch all records for a specific zone.

        Args:
            zone_id: Provider zone ID.

        Returns:
            List of record dictionaries or None on failure.

        Raises:
            ZoneNotFoundError: If zone not found (404).
        """
        self.logger.debug(f"Fetching records for zone: {zone_id}")
        response = self.client.get(
            endpoint=f"/zones/{zone_id}", headers=self.headers
        )

        if response is not None and response.status_code == HTTPStatus.OK:
            zone_data = response.json()
            records = zone_data.get("records", [])
            self.logger.debug(
                f"Retrieved {len(records)} records for zone {zone_id}"
            )
            return records
        elif response is not None and response.status_code == HTTPStatus.NOT_FOUND:
            self.logger.error(f"Zone not found: {zone_id}")
            raise ZoneNotFoundError(f"Zone {zone_id} not found")
        elif response is not None:
            self.logger.error(
                f"Failed to fetch zone records: {response.status_code} - {response.text}"
            )
            return None
        else:
            self.logger.error(
                "Failed to fetch zone records: No response from provider"
            )
            return None


    def update_record(
        self,
        zone_id: str,
        record_id: str,
        content: str,
        ttl: Optional[int] = None,
        disabled: bool = False,
    ) -> bool:
        """Update DNS record's IP address.

        Args:
            zone_id: Provider zone ID.
            record_id: Provider record ID.
            content: New IP address.
            ttl: Time to live in seconds. Uses config default if None.
            disabled: Whether record is disabled. Defaults to False.

        Returns:
            True if successful, False otherwise.

        Raises:
            RecordNotFoundError: If record not found (404).
        """
        self.logger.debug(f"Updating record {record_id} in zone {zone_id} to {content}")
        if ttl is None:
            ttl = self.config.dns_default_ttl
        json_data = {"content": content, "ttl": ttl, "disabled": disabled}

        max_retries = ProviderAPI.AUTH_MAX_RETRIES
        for attempt in range(max_retries):
            response = self.client.put(
                endpoint=f"/zones/{zone_id}/records/{record_id}",
                headers=self.headers,
                json_data=json_data,
            )
            if response is not None and response.status_code == HTTPStatus.OK:
                self.logger.debug(f"Successfully updated record {record_id} to {content}")
                return True
            if not self._should_retry_update_record(response, record_id, attempt, max_retries):
                return False
        return False


    def _should_retry_update_record(
        self,
        response: Optional[Any],
        record_id: str,
        attempt: int,
        max_retries: int,
    ) -> bool:
        """Evaluate failed record update response and determine whether to retry.

        Args:
            response: HTTP response object or None.
            record_id: Provider record ID.
            attempt: Current zero-based attempt index.
            max_retries: Maximum retry attempts configured.

        Returns:
            True if caller should retry after sleeping, False to abort.

        Raises:
            RecordNotFoundError: If provider reports ERR_RECORD_NOT_FOUND (404).
        """
        if response is None:
            self.logger.error("Failed to update record: No response from provider")
            return False
        if response.status_code == HTTPStatus.UNAUTHORIZED:
            if attempt < max_retries - 1:
                self.logger.warning(f"Authentication failed (401) - retrying... (attempt {attempt + 1}/{max_retries})")
                time.sleep(ProviderAPI.AUTH_RETRY_DELAY)
                return True
            self.logger.error("Authentication failed (401 Unauthorized) - check API key")
            return False
        if response.status_code == HTTPStatus.TOO_MANY_REQUESTS:
            self.logger.error("Rate limit exceeded (429) - too many requests")
            return False
        if response.status_code == HTTPStatus.NOT_FOUND:
            error_data = response.json() if response.text else {}
            if error_data.get("code", "UNKNOWN") == ProviderAPI.ERR_RECORD_NOT_FOUND:
                self.logger.warning(f"Record not found: {record_id} - Provider IDs may be outdated")
                raise RecordNotFoundError(f"Record {record_id} not found - re-sync required")
            self.logger.error(f"Zone or record not found: {response.text}")
            return False
        self.logger.error(f"Failed to update record: {response.status_code} - {response.text}")
        return False


    def create_records(self, zone_id: str, records: List[Dict[str, Any]]) -> bool:
        """Create one or more DNS records.

        Args:
            zone_id: Provider zone ID.
            records: List of record dictionaries with name, type, content, ttl.

        Returns:
            True if successful, False otherwise.
        """
        self.logger.debug(f"Creating {len(records)} records in zone {zone_id}")

        response = self.client.post(
            endpoint=f"/zones/{zone_id}/records",
            headers=self.headers,
            json_data=records,
        )

        if response is not None and response.status_code == HTTPStatus.CREATED:
            self.logger.debug(f"Successfully created {len(records)} records")
            return True
        elif response is not None:
            self.logger.error(
                f"Failed to create records: {response.status_code} - {response.text}"
            )
            return False
        else:
            self.logger.error("Failed to create records: No response from provider")
            return False


    def delete_record(self, zone_id: str, record_id: str) -> bool:
        """Delete a DNS record.

        Args:
            zone_id: Provider zone ID.
            record_id: Provider record ID.

        Returns:
            True if successful, False otherwise.
        """
        self.logger.debug(f"Deleting record {record_id} from zone {zone_id}")

        response = self.client.delete(
            endpoint=f"/zones/{zone_id}/records/{record_id}",
            headers=self.headers,
        )

        if response is not None and response.status_code == HTTPStatus.OK:
            self.logger.debug(f"Successfully deleted record {record_id}")
            return True
        elif response is not None:
            self.logger.error(
                f"Failed to delete record: {response.status_code} - {response.text}"
            )
            return False
        else:
            self.logger.error("Failed to delete record: No response from provider")
            return False


    def build_record_dict(
        self,
        record_name: str,
        record_type: str,
        content: str,
        ttl: int,
        disabled: bool = False,
    ) -> Dict[str, Any]:
        """Build API record dictionary for provider API.

        Args:
            record_name: Full DNS record name (e.g., www.example.com).
            record_type: Record type (A, AAAA, etc.).
            content: IP address or content value.
            ttl: Time to live in seconds.
            disabled: Whether record is disabled. Defaults to False.

        Returns:
            Dictionary formatted for provider API.
        """
        return {
            "name": record_name,
            "type": record_type,
            "content": content,
            "ttl": ttl,
            "disabled": disabled,
        }


    def find_record_id(
        self, zone_id: str, record_name: str, record_type: str
    ) -> Optional[str]:
        """Find record ID by name and type in a zone.

        Args:
            zone_id: Provider zone ID to search in.
            record_name: Full record name to search for.
            record_type: Record type to search for (A, AAAA, etc.).

        Returns:
            Provider record ID string or None if not found.
        """
        try:
            records = self.get_zone_records(zone_id)
            if not records:
                return None

            for record in records:
                if (
                    record.get("name") == record_name
                    and record.get("type") == record_type
                ):
                    return record.get("id")

            return None

        except APIError as e:
            self.logger.error(
                f"Failed to find record ID for {record_name} ({record_type}): {e}"
            )
            return None


    ############################################################################
    # DYNDNS API INTERFACE - Dynamic DNS Configuration & URL Updates
    ############################################################################

    def activate_dyndns(
        self, domains: List[str], description: str = "Dynamic DNS by daemon"
    ) -> Optional[Dict[str, Any]]:
        """Activate Dynamic DNS for a bundle of (sub)domains.

        Calls POST /v1/dyndns to obtain a bulkId and the GET updateUrl.

        Args:
            domains: List of domain or subdomain names to include.
            description: Description for the DynDNS bundle.

        Returns:
            Dictionary with DynDNS config (bulkId, updateUrl, domains) or None on error.
        """
        self.logger.debug(f"Activating DynDNS for {len(domains)} domain(s)...")
        payload = {"domains": domains, "description": description}
        response = self.client.post(
            endpoint="/dyndns", headers=self.headers, json_data=payload
        )

        if response is not None and response.status_code == HTTPStatus.OK:
            data = response.json()
            self.logger.info(
                f"Successfully activated DynDNS (bulkId: {data.get('bulkId')})"
            )
            return data
        elif response is not None:
            self.logger.error(
                f"Failed to activate DynDNS: {response.status_code} - {response.text}"
            )
            return None
        else:
            self.logger.error("Failed to activate DynDNS: No response from provider")
            return None


    def update_dyndns_config(
        self, bulk_id: str, domains: List[str], description: str = "Dynamic DNS by daemon"
    ) -> bool:
        """Update existing Dynamic DNS bundle configuration.

        Calls PUT /v1/dyndns/{bulkId}.

        Args:
            bulk_id: The DynDNS configuration bulk identifier.
            domains: Updated list of domain/subdomain names.
            description: Updated description.

        Returns:
            True if successful, False otherwise.
        """
        self.logger.debug(f"Updating DynDNS bundle {bulk_id}...")
        payload = {"domains": domains, "description": description}
        response = self.client.put(
            endpoint=f"/dyndns/{bulk_id}", headers=self.headers, json_data=payload
        )

        if response is not None and response.status_code == HTTPStatus.OK:
            self.logger.info(f"Successfully updated DynDNS bundle {bulk_id}")
            return True
        elif response is not None:
            self.logger.error(
                f"Failed to update DynDNS bundle {bulk_id}: {response.status_code} - {response.text}"
            )
            return False
        else:
            self.logger.error(
                f"Failed to update DynDNS bundle {bulk_id}: No response from provider"
            )
            return False


    def disable_dyndns(self) -> bool:
        """Disable all Dynamic DNS bundles for this API key.

        Calls DELETE /v1/dyndns.

        Returns:
            True if successful, False otherwise.
        """
        self.logger.debug("Disabling all DynDNS configurations...")
        response = self.client.delete(endpoint="/dyndns", headers=self.headers)

        if response is not None and response.status_code == HTTPStatus.OK:
            self.logger.info("Successfully disabled all DynDNS configurations")
            return True
        elif response is not None:
            self.logger.error(
                f"Failed to disable DynDNS: {response.status_code} - {response.text}"
            )
            return False
        else:
            self.logger.error("Failed to disable DynDNS: No response from provider")
            return False


    def disable_dyndns_bulk(self, bulk_id: str) -> bool:
        """Disable a specific Dynamic DNS bundle.

        Calls DELETE /v1/dyndns/{bulkId}.

        Args:
            bulk_id: The DynDNS configuration bulk identifier.

        Returns:
            True if successful, False otherwise.
        """
        self.logger.debug(f"Disabling DynDNS bundle {bulk_id}...")
        response = self.client.delete(
            endpoint=f"/dyndns/{bulk_id}", headers=self.headers
        )

        if response is not None and response.status_code == HTTPStatus.OK:
            self.logger.info(f"Successfully disabled DynDNS bundle {bulk_id}")
            return True
        elif response is not None:
            self.logger.error(
                f"Failed to disable DynDNS bundle {bulk_id}: {response.status_code} - {response.text}"
            )
            return False
        else:
            self.logger.error(
                f"Failed to disable DynDNS bundle {bulk_id}: No response from provider"
            )
            return False


    def execute_dyndns_update_url(
        self,
        update_url: str,
        ipv4: Optional[str] = None,
        ipv6: Optional[str] = None,
    ) -> bool:
        """Execute the native DynDNS updateUrl via HTTP GET.

        The updateUrl returned by IONOS (e.g. https://ipv4.api.hosting.ionos.com/dns/v1/dyndns?q=...)
        can be called directly. Query parameters `ipv4` and/or `ipv6` can optionally be appended
        if specific IPs need to be set instead of auto-detecting the calling IP.

        Args:
            update_url: The full GET URL obtained from activate_dyndns.
            ipv4: Optional explicit IPv4 address to append to query parameters.
            ipv6: Optional explicit IPv6 address to append to query parameters.

        Returns:
            True if update request returned 200/204, False otherwise.
        """
        self.logger.debug(f"Executing native DynDNS update URL: {update_url}")
        params: Dict[str, str] = {}
        if ipv4:
            params["ipv4"] = ipv4
        if ipv6:
            params["ipv6"] = ipv6

        response = self.client.get(url=update_url, params=params if params else None)

        if response is not None and response.status_code in (HTTPStatus.OK, HTTPStatus.NO_CONTENT):
            self.logger.debug("Successfully executed native DynDNS URL HTTP GET request")
            return True
        elif response is not None:
            self.logger.error(
                f"Failed native DynDNS URL update: {response.status_code} - {response.text}"
            )
            return False
        else:
            self.logger.error(
                "Failed native DynDNS URL update: No response from endpoint"
            )
            return False
