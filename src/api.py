#!/usr/bin/env python3
"""
API Client Module

HTTP client with retry logic for reliable API communication.

Created: 2025-10-27
Author: Manuel Ziel
License: MIT
"""

################################################################################
# IMPORTS & DEPENDENCIES
################################################################################

# Standard library imports
import time
import logging
from typing import Optional, Dict, Any, List

# Third-party imports
import requests

# Internal imports
from exceptions import RecordNotFoundError, ZoneNotFoundError

################################################################################
# HTTP CLIENT CLASS - API Communication with Retry Logic
################################################################################

class HTTPClient:
    """HTTP client with retry logic and error handling."""
    
    def __init__(self, base_url: Optional[str] = None, timeout: int = 10, retries: int = 3, logger: Optional[Any] = None) -> None:
        self.base_url = base_url
        self.timeout = timeout  
        self.retries = retries
        
        if logger:
            self.logger = logger
        else:
            self.logger = logging.getLogger(__name__)

    def request_with_retry(self, method: str, endpoint: Optional[str] = None, url: Optional[str] = None, headers: Optional[Dict[str, str]] = None, json_data: Optional[Dict[str, Any]] = None, **kwargs: Any) -> Optional[requests.Response]:
        """Make HTTP request with exponential backoff retry logic."""
        if url:
            final_url = url
        elif self.base_url and endpoint:
            final_url = f"{self.base_url.rstrip('/')}/{endpoint.lstrip('/')}"
        elif endpoint:
            final_url = endpoint
        else:
            self.logger.error("Either 'url' or 'endpoint' (with base_url) must be provided")
            return None
        
        retries = kwargs.pop('retries', self.retries)
        timeout = kwargs.pop('timeout', self.timeout)
        
        for attempt in range(retries):
            try:
                if method.upper() == "GET":
                    response = requests.get(final_url, headers=headers, timeout=timeout, **kwargs)
                elif method.upper() == "POST":
                    response = requests.post(final_url, headers=headers, json=json_data, timeout=timeout, **kwargs)
                elif method.upper() == "PUT":
                    response = requests.put(final_url, headers=headers, json=json_data, timeout=timeout, **kwargs)
                elif method.upper() == "DELETE":
                    response = requests.delete(final_url, headers=headers, timeout=timeout, **kwargs)
                else:
                    raise ValueError(f"Unsupported HTTP method: {method}")
                
                self.logger.debug(f"{method.upper()} {final_url} - Status: {response.status_code}")
                return response
                
            except requests.exceptions.Timeout:
                self.logger.warning(f"Request timeout (attempt {attempt + 1}/{retries}) - {final_url}")
                if attempt < retries - 1:  # Don't sleep on last attempt
                    time.sleep(2 ** attempt)  # Exponential backoff
                    
            except requests.exceptions.RequestException as e:
                self.logger.warning(f"Request failed (attempt {attempt + 1}/{retries}): {e}")
                if attempt < retries - 1:  # Don't sleep on last attempt
                    time.sleep(2 ** attempt)  # Exponential backoff
        
        self.logger.error(f"All {retries} retry attempts failed for {method.upper()} {final_url}")
        return None

    ################################################################################
    # HTTP METHOD CONVENIENCE WRAPPERS - Simplified API
    ################################################################################

    def get(self, endpoint: Optional[str] = None, url: Optional[str] = None, **kwargs: Any) -> Optional[requests.Response]:
        """GET request wrapper."""
        return self.request_with_retry("GET", endpoint=endpoint, url=url, **kwargs)
    
    def post(self, endpoint: Optional[str] = None, url: Optional[str] = None, json_data: Optional[Dict[str, Any]] = None, **kwargs: Any) -> Optional[requests.Response]:
        """POST request wrapper."""
        return self.request_with_retry("POST", endpoint=endpoint, url=url, json_data=json_data, **kwargs)
    
    def put(self, endpoint: Optional[str] = None, url: Optional[str] = None, json_data: Optional[Dict[str, Any]] = None, **kwargs: Any) -> Optional[requests.Response]:
        """PUT request wrapper."""
        return self.request_with_retry("PUT", endpoint=endpoint, url=url, json_data=json_data, **kwargs)
    
    def delete(self, endpoint: Optional[str] = None, url: Optional[str] = None, **kwargs: Any) -> Optional[requests.Response]:
        """DELETE request wrapper."""
        return self.request_with_retry("DELETE", endpoint=endpoint, url=url, **kwargs)

################################################################################
# PROVIDER DNS API CLIENT - DNS Provider Integration
################################################################################

class ProviderDNSClient:
    """DNS Provider API Client for zone and record management."""
    
    def __init__(self, api_key: str, base_url: str, timeout: int = 30, retries: int = 3, logger: Optional[Any] = None) -> None:
        """Initialize provider DNS API client."""
        self.api_key = api_key
        self.base_url = base_url
        self.logger = logger if logger else logging.getLogger(__name__)
        
        self.client = HTTPClient(
            base_url=base_url,
            timeout=timeout,
            retries=retries,
            logger=self.logger
        )
        
        self.headers = {
            "accept": "application/json",
            "X-API-Key": self.api_key,
            "Content-Type": "application/json"
        }
    
    def get_zones(self) -> Optional[List[Dict[str, Any]]]:
        """Fetch all DNS zones from provider."""
        self.logger.debug("Fetching zones from provider API...")
        response = self.client.get(endpoint="/zones", headers=self.headers)
        
        if response and response.status_code == 200:
            zones = response.json()
            self.logger.debug(f"Retrieved {len(zones)} zones from provider")
            return zones
        elif response:
            self.logger.error(f"Failed to fetch zones: {response.status_code} - {response.text}")
            return None
        else:
            self.logger.error("Failed to fetch zones: No response from provider")
            return None
    
    def get_zone_records(self, zone_id: str) -> Optional[List[Dict[str, Any]]]:
        """Fetch all records for a specific zone."""
        self.logger.debug(f"Fetching records for zone: {zone_id}")
        response = self.client.get(endpoint=f"/zones/{zone_id}", headers=self.headers)
        
        if response and response.status_code == 200:
            zone_data = response.json()
            records = zone_data.get("records", [])
            self.logger.debug(f"Retrieved {len(records)} records for zone {zone_id}")
            return records
        elif response and response.status_code == 404:
            self.logger.error(f"Zone not found: {zone_id}")
            raise ZoneNotFoundError(f"Zone {zone_id} not found")
        elif response:
            self.logger.error(f"Failed to fetch zone records: {response.status_code} - {response.text}")
            return None
        else:
            self.logger.error("Failed to fetch zone records: No response from provider")
            return None
    
    def update_record(self, zone_id: str, record_id: str, content: str, ttl: int = 3600, disabled: bool = False) -> bool:
        """Update DNS record's IP address."""
        self.logger.debug(f"Updating record {record_id} in zone {zone_id} to {content}")
        
        json_data = {
            "content": content,
            "ttl": ttl,
            "disabled": disabled
        }
        
        # Retry logic for transient errors (401 can be temporary)
        max_retries = 2
        for attempt in range(max_retries):
            response = self.client.put(
                endpoint=f"/zones/{zone_id}/records/{record_id}",
                headers=self.headers,
                json_data=json_data
            )
            
            if response and response.status_code == 200:
                self.logger.debug(f"Successfully updated record {record_id} to {content}")
                return True
            elif response and response.status_code == 401:
                if attempt < max_retries - 1:
                    self.logger.warning(f"Authentication failed (401) - retrying... (attempt {attempt + 1}/{max_retries})")
                    time.sleep(2)  # Short delay before retry
                    continue
                else:
                    self.logger.error(f"Authentication failed (401 Unauthorized) - check API key")
                    return False
            elif response and response.status_code == 429:
                self.logger.error(f"Rate limit exceeded (429) - too many requests")
                return False
            elif response and response.status_code == 404:
                error_data = response.json() if response.text else {}
                error_code = error_data.get("code", "UNKNOWN")
                if error_code == "RECORD_NOT_FOUND":
                    self.logger.warning(f"Record not found: {record_id} - Provider IDs may be outdated")
                    raise RecordNotFoundError(f"Record {record_id} not found - re-sync required")
                else:
                    self.logger.error(f"Zone or record not found: {response.text}")
                    return False
            elif response:
                self.logger.error(f"Failed to update record: {response.status_code} - {response.text}")
                return False
            else:
                self.logger.error("Failed to update record: No response from provider")
                return False
        
        return False
    
    def create_records(self, zone_id: str, records: List[Dict[str, Any]]) -> bool:
        """Create one or more DNS records."""
        self.logger.debug(f"Creating {len(records)} records in zone {zone_id}")
        
        response = self.client.post(
            endpoint=f"/zones/{zone_id}/records",
            headers=self.headers,
            json_data=records
        )
        
        if response and response.status_code == 201:
            self.logger.debug(f"Successfully created {len(records)} records")
            return True
        elif response:
            self.logger.error(f"Failed to create records: {response.status_code} - {response.text}")
            return False
        else:
            self.logger.error("Failed to create records: No response from provider")
            return False
    
    def delete_record(self, zone_id: str, record_id: str) -> bool:
        """Delete a DNS record."""
        self.logger.debug(f"Deleting record {record_id} from zone {zone_id}")
        
        response = self.client.delete(
            endpoint=f"/zones/{zone_id}/records/{record_id}",
            headers=self.headers
        )
        
        if response and response.status_code == 200:
            self.logger.debug(f"Successfully deleted record {record_id}")
            return True
        elif response:
            self.logger.error(f"Failed to delete record: {response.status_code} - {response.text}")
            return False
        else:
            self.logger.error("Failed to delete record: No response from provider")
            return False
    
    def build_record_dict(self, record_name: str, record_type: str, content: str, 
                         ttl: int, disabled: bool = False) -> Dict[str, Any]:
        """Build API record dictionary for provider API.
        
        Args:
            record_name: Full DNS record name (e.g., www.example.com)
            record_type: Record type (A, AAAA, etc.)
            content: IP address or content
            ttl: Time to live in seconds
            disabled: Whether record is disabled
            
        Returns:
            Dictionary formatted for provider API
        """
        return {
            "name": record_name,
            "type": record_type,
            "content": content,
            "ttl": ttl,
            "disabled": disabled
        }
    
    def find_record_id(self, zone_id: str, record_name: str, record_type: str) -> Optional[str]:
        """Find record ID by name and type in a zone.
        
        Args:
            zone_id: Provider zone ID
            record_name: Full record name to search for
            record_type: Record type to search for (A, AAAA, etc.)
            
        Returns:
            Provider record ID or None if not found
        """
        try:
            records = self.get_zone_records(zone_id)
            if not records:
                return None
            
            for record in records:
                if record['name'] == record_name and record['type'] == record_type:
                    return record['id']
            
            return None
            
        except Exception as e:
            self.logger.error(f"Failed to find record ID for {record_name} ({record_type}): {e}")
            return None