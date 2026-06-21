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

# Standard Imports
import logging
import time
from typing import Any, Dict, List, Optional

# Local Imports
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

        if response and response.status_code == HTTPStatus.OK:
            zones = response.json()
            self.logger.debug(f"Retrieved {len(zones)} zones from provider")
            return zones
        elif response:
            self.logger.error(
                f"Failed to fetch zones: {response.status_code} - {response.text}"
            )
            return None
        else:
            self.logger.error("Failed to fetch zones: No response from provider")
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

        if response and response.status_code == HTTPStatus.OK:
            zone_data = response.json()
            records = zone_data.get("records", [])
            self.logger.debug(
                f"Retrieved {len(records)} records for zone {zone_id}"
            )
            return records
        elif response and response.status_code == HTTPStatus.NOT_FOUND:
            self.logger.error(f"Zone not found: {zone_id}")
            raise ZoneNotFoundError(f"Zone {zone_id} not found")
        elif response:
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
        self.logger.debug(
            f"Updating record {record_id} in zone {zone_id} to {content}"
        )

        if ttl is None:
            ttl = self.config.dns_default_ttl

        json_data = {"content": content, "ttl": ttl, "disabled": disabled}

        # Retry logic for transient errors (401 can be temporary)
        max_retries = ProviderAPI.AUTH_MAX_RETRIES
        for attempt in range(max_retries):
            response = self.client.put(
                endpoint=f"/zones/{zone_id}/records/{record_id}",
                headers=self.headers,
                json_data=json_data,
            )

            if response and response.status_code == HTTPStatus.OK:
                self.logger.debug(
                    f"Successfully updated record {record_id} to {content}"
                )
                return True
            elif response and response.status_code == HTTPStatus.UNAUTHORIZED:
                if attempt < max_retries - 1:
                    self.logger.warning(
                        "Authentication failed (401) - retrying... "
                        f"(attempt {attempt + 1}/{max_retries})"
                    )
                    time.sleep(ProviderAPI.AUTH_RETRY_DELAY)  # Short delay before retry
                    continue
                else:
                    self.logger.error(
                        "Authentication failed (401 Unauthorized) - check API key"
                    )
                    return False
            elif response and response.status_code == HTTPStatus.TOO_MANY_REQUESTS:
                self.logger.error("Rate limit exceeded (429) - too many requests")
                return False
            elif response and response.status_code == HTTPStatus.NOT_FOUND:
                error_data = response.json() if response.text else {}
                error_code = error_data.get("code", "UNKNOWN")
                if error_code == ProviderAPI.ERR_RECORD_NOT_FOUND:
                    self.logger.warning(
                        f"Record not found: {record_id} - Provider IDs may be outdated"
                    )
                    raise RecordNotFoundError(
                        f"Record {record_id} not found - re-sync required"
                    )
                else:
                    self.logger.error(f"Zone or record not found: {response.text}")
                    return False
            elif response:
                self.logger.error(
                    f"Failed to update record: {response.status_code} - {response.text}"
                )
                return False
            else:
                self.logger.error("Failed to update record: No response from provider")
                return False

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

        if response and response.status_code == HTTPStatus.CREATED:
            self.logger.debug(f"Successfully created {len(records)} records")
            return True
        elif response:
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

        if response and response.status_code == HTTPStatus.OK:
            self.logger.debug(f"Successfully deleted record {record_id}")
            return True
        elif response:
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
