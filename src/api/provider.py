#!/usr/bin/env python3
"""DNS Provider API Client for IONOS zone, record, and DynDNS management.

Provides ``ProviderDNSClient`` for interacting with the IONOS DNS v1 REST API
and native DynDNS ``updateUrl`` endpoints with automatic URI secret redaction.

Author: Manuel Ziel
License: MIT
"""

################################################################################
# IMPORTS & DEPENDENCIES
################################################################################

import logging
import time
from typing import Any

from ..core.constants import HTTPHeader, HTTPHeaderValue, HTTPStatus, ProviderAPI
from ..core.exceptions import APIError, RecordNotFoundError, ZoneNotFoundError
from ..core.security import sanitize_log_uri
from .http_client import HTTPClient

################################################################################
# PROVIDER DNS API CLIENT
################################################################################


class ProviderDNSClient:
    """DNS Provider API client for zone, record, and DynDNS bundle operations.

    Attributes:
        api_key: Full provider API key in ``bulk_id.api_key`` format.
        config: ``ConfigManager`` instance with provider API settings.
        logger: Logger instance for API operations.
        client: Underlying session-backed ``HTTPClient``.
        headers: Default HTTP authentication and content headers.
    """

    def __init__(
        self,
        api_key: str,
        config: Any,
        logger: logging.Logger | None = None,
    ) -> None:
        """Initialize provider DNS API client and HTTP session.

        Args:
            api_key: Full API key (``bulk_id.api_key`` format).
            config: ``ConfigManager`` instance with provider settings.
            logger: Optional logger instance.
        """
        self.api_key = api_key
        self.config = config
        self.logger = logger or logging.getLogger(__name__)
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

    def close(self) -> None:
        """Close the underlying ``HTTPClient`` session."""
        self.client.close()

    ############################################################################
    # ZONE & RECORD REST API OPERATIONS
    ############################################################################

    def get_zones(self) -> list[dict[str, Any]] | None:
        """Fetch all DNS zones accessible to the API key.

        Returns:
            List of provider zone dictionaries, or ``None`` on failure.
        """
        self.logger.debug("Fetching zones from provider API...")
        response = self.client.get(endpoint="/zones", headers=self.headers)
        if response is not None and response.status_code == HTTPStatus.OK:
            zones: list[dict[str, Any]] = response.json()
            self.logger.debug(f"Retrieved {len(zones)} zones from provider")
            return zones
        if response is not None:
            self.logger.warning(
                f"Failed to fetch zones: {response.status_code} - {response.text}"
            )
            return None
        self.logger.warning("Failed to fetch zones: No response from provider")
        return None

    def get_zone_records(self, zone_id: str) -> list[dict[str, Any]] | None:
        """Fetch all DNS records for a specific provider zone.

        Args:
            zone_id: Provider zone identifier.

        Returns:
            List of record dictionaries, or ``None`` on failure.

        Raises:
            ZoneNotFoundError: If the provider returns HTTP 404 for ``zone_id``.
        """
        self.logger.debug(f"Fetching records for zone: {zone_id}")
        response = self.client.get(endpoint=f"/zones/{zone_id}", headers=self.headers)
        if response is not None and response.status_code == HTTPStatus.OK:
            records: list[dict[str, Any]] = response.json().get("records", [])
            self.logger.debug(f"Retrieved {len(records)} records for zone {zone_id}")
            return records
        if response is not None and response.status_code == HTTPStatus.NOT_FOUND:
            self.logger.error(f"Zone not found: {zone_id}")
            raise ZoneNotFoundError(f"Zone {zone_id} not found")
        if response is not None:
            self.logger.error(
                f"Failed to fetch zone records: {response.status_code} - {response.text}"
            )
            return None
        self.logger.error("Failed to fetch zone records: No response from provider")
        return None

    def update_record(
        self,
        zone_id: str,
        record_id: str,
        content: str,
        ttl: int | None = None,
        disabled: bool = False,
    ) -> bool:
        """Update an existing DNS record's IP content via ``PUT``.

        Args:
            zone_id: Provider zone identifier.
            record_id: Provider record identifier.
            content: Target IPv4/IPv6 address string.
            ttl: Time-to-live in seconds (defaults to ``config.dns_default_ttl``).
            disabled: Whether the record should be marked disabled.

        Returns:
            True if updated, False otherwise.

        Raises:
            RecordNotFoundError: If the provider reports ``RECORD_NOT_FOUND``.
        """
        self.logger.debug(f"Updating record {record_id} in zone {zone_id} to {content}")
        resolved_ttl = self.config.dns_default_ttl if ttl is None else ttl
        json_data = {"content": content, "ttl": resolved_ttl, "disabled": disabled}
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
        response: Any | None,
        record_id: str,
        attempt: int,
        max_retries: int,
    ) -> bool:
        """Evaluate a failed ``update_record`` response and decide whether to retry.

        Args:
            response: HTTP response object or ``None``.
            record_id: Provider record identifier.
            attempt: Zero-based attempt index.
            max_retries: Configured auth retry count.

        Returns:
            True to sleep and retry, False to abort.

        Raises:
            RecordNotFoundError: When provider returns 404 ``RECORD_NOT_FOUND``.
        """
        if response is None:
            self.logger.error("Failed to update record: No response from provider")
            return False
        if response.status_code == HTTPStatus.UNAUTHORIZED:
            if attempt < max_retries - 1:
                self.logger.warning(
                    f"Authentication failed (401) - retrying ({attempt + 1}/{max_retries})"
                )
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
                self.logger.warning(f"Record not found: {record_id} - Provider IDs outdated")
                raise RecordNotFoundError(f"Record {record_id} not found - re-sync required")
            self.logger.error(f"Zone or record not found: {response.text}")
            return False
        self.logger.error(f"Failed to update record: {response.status_code} - {response.text}")
        return False

    def create_records(self, zone_id: str, records: list[dict[str, Any]]) -> bool:
        """Create one or more DNS records in ``zone_id`` via ``POST``.

        Args:
            zone_id: Provider zone identifier.
            records: List of API record payload dictionaries.

        Returns:
            True when HTTP 201 Created is returned, False otherwise.
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
        if response is not None:
            self.logger.error(
                f"Failed to create records: {response.status_code} - {response.text}"
            )
            return False
        self.logger.error("Failed to create records: No response from provider")
        return False

    def delete_record(self, zone_id: str, record_id: str) -> bool:
        """Delete a DNS record from ``zone_id`` via ``DELETE``.

        Args:
            zone_id: Provider zone identifier.
            record_id: Provider record identifier.

        Returns:
            True on HTTP 200 OK, False otherwise.
        """
        self.logger.debug(f"Deleting record {record_id} from zone {zone_id}")
        response = self.client.delete(
            endpoint=f"/zones/{zone_id}/records/{record_id}",
            headers=self.headers,
        )
        if response is not None and response.status_code == HTTPStatus.OK:
            self.logger.debug(f"Successfully deleted record {record_id}")
            return True
        if response is not None:
            self.logger.error(
                f"Failed to delete record: {response.status_code} - {response.text}"
            )
            return False
        self.logger.error("Failed to delete record: No response from provider")
        return False

    def build_record_dict(
        self,
        record_name: str,
        record_type: str,
        content: str,
        ttl: int,
        disabled: bool = False,
    ) -> dict[str, Any]:
        """Construct a provider-compatible record payload dictionary.

        Args:
            record_name: Full DNS FQDN (e.g. ``'www.example.com'``).
            record_type: DNS record type (``'A'`` or ``'AAAA'``).
            content: Target IP address or record value.
            ttl: Time-to-live in seconds.
            disabled: Whether the record starts disabled.

        Returns:
            Provider REST payload dictionary.
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
    ) -> str | None:
        """Look up a provider record ID by FQDN and record type.

        Args:
            zone_id: Provider zone identifier.
            record_name: Full DNS FQDN to match.
            record_type: Record type (``'A'`` or ``'AAAA'``).

        Returns:
            Provider record ID string, or ``None`` if not found.
        """
        try:
            records = self.get_zone_records(zone_id)
            if not records:
                return None
            for record in records:
                if record.get("name") == record_name and record.get("type") == record_type:
                    return str(record["id"]) if record.get("id") else None
            return None
        except APIError as exc:
            self.logger.error(
                f"Failed to find record ID for {record_name} ({record_type}): {exc}"
            )
            return None

    ############################################################################
    # DYNDNS BUNDLE & UPDATE URL OPERATIONS
    ############################################################################

    def activate_dyndns(
        self, domains: list[str], description: str = "Dynamic DNS by daemon"
    ) -> dict[str, Any] | None:
        """Activate a Dynamic DNS bundle via ``POST /dyndns``.

        Args:
            domains: Domain and subdomain FQDNs included in the bundle.
            description: Human-readable bundle label.

        Returns:
            Provider response dictionary containing ``bulkId`` and ``updateUrl``, or ``None``.
        """
        self.logger.debug(f"Activating DynDNS for {len(domains)} domain(s)...")
        payload = {"domains": domains, "description": description}
        response = self.client.post(
            endpoint="/dyndns", headers=self.headers, json_data=payload
        )
        if response is not None and response.status_code == HTTPStatus.OK:
            data: dict[str, Any] = response.json()
            self.logger.info(
                f"Successfully activated DynDNS (bulkId: {data.get('bulkId')})"
            )
            return data
        if response is not None:
            self.logger.error(
                f"Failed to activate DynDNS: {response.status_code} - {response.text}"
            )
            return None
        self.logger.error("Failed to activate DynDNS: No response from provider")
        return None

    def update_dyndns_config(
        self,
        bulk_id: str,
        domains: list[str],
        description: str = "Dynamic DNS by daemon",
    ) -> bool:
        """Update an existing Dynamic DNS bundle via ``PUT /dyndns/{bulkId}``.

        Args:
            bulk_id: Provider DynDNS bundle identifier.
            domains: Updated list of domain/subdomain FQDNs.
            description: Updated bundle description.

        Returns:
            True on HTTP 200 OK, False otherwise.
        """
        self.logger.debug(f"Updating DynDNS bundle {bulk_id}...")
        payload = {"domains": domains, "description": description}
        response = self.client.put(
            endpoint=f"/dyndns/{bulk_id}", headers=self.headers, json_data=payload
        )
        if response is not None and response.status_code == HTTPStatus.OK:
            self.logger.info(f"Successfully updated DynDNS bundle {bulk_id}")
            return True
        if response is not None:
            self.logger.error(
                f"Failed to update DynDNS bundle {bulk_id}: {response.status_code} - {response.text}"
            )
            return False
        self.logger.error(f"Failed to update DynDNS bundle {bulk_id}: No response")
        return False

    def disable_dyndns(self) -> bool:
        """Disable all Dynamic DNS bundles for the current API key.

        Returns:
            True on HTTP 200 OK, False otherwise.
        """
        self.logger.debug("Disabling all DynDNS configurations...")
        response = self.client.delete(endpoint="/dyndns", headers=self.headers)
        if response is not None and response.status_code == HTTPStatus.OK:
            self.logger.info("Successfully disabled all DynDNS configurations")
            return True
        if response is not None:
            self.logger.error(
                f"Failed to disable DynDNS: {response.status_code} - {response.text}"
            )
            return False
        self.logger.error("Failed to disable DynDNS: No response from provider")
        return False

    def disable_dyndns_bulk(self, bulk_id: str) -> bool:
        """Disable a single Dynamic DNS bundle via ``DELETE /dyndns/{bulkId}``.

        Args:
            bulk_id: Provider DynDNS bundle identifier.

        Returns:
            True on HTTP 200 OK, False otherwise.
        """
        self.logger.debug(f"Disabling DynDNS bundle {bulk_id}...")
        response = self.client.delete(
            endpoint=f"/dyndns/{bulk_id}", headers=self.headers
        )
        if response is not None and response.status_code == HTTPStatus.OK:
            self.logger.info(f"Successfully disabled DynDNS bundle {bulk_id}")
            return True
        if response is not None:
            self.logger.error(
                f"Failed to disable DynDNS bundle {bulk_id}: {response.status_code} - {response.text}"
            )
            return False
        self.logger.error(f"Failed to disable DynDNS bundle {bulk_id}: No response")
        return False

    def execute_dyndns_update_url(
        self,
        update_url: str,
        ipv4: str | None = None,
        ipv6: str | None = None,
    ) -> bool:
        """Invoke the native IONOS DynDNS ``updateUrl`` via HTTP ``GET``.

        Args:
            update_url: Full DynDNS update URL returned by ``activate_dyndns``.
            ipv4: Optional explicit IPv4 address query parameter.
            ipv6: Optional explicit IPv6 address query parameter.

        Returns:
            True if the endpoint responded with HTTP 200 or 204, False otherwise.
        """
        self.logger.debug(
            f"Executing native DynDNS update URL: {sanitize_log_uri(update_url)}"
        )
        params: dict[str, str] = {}
        if ipv4:
            params["ipv4"] = ipv4
        if ipv6:
            params["ipv6"] = ipv6
        response = self.client.get(url=update_url, params=params or None)
        if response is not None and response.status_code in (
            HTTPStatus.OK,
            HTTPStatus.NO_CONTENT,
        ):
            self.logger.debug("Successfully executed native DynDNS URL HTTP GET request")
            return True
        if response is not None:
            self.logger.error(
                f"Failed native DynDNS URL update: {response.status_code} - {response.text}"
            )
            return False
        self.logger.error("Failed native DynDNS URL update: No response from endpoint")
        return False
