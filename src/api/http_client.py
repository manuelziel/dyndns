#!/usr/bin/env python3
"""HTTP client module with retry logic for reliable API communication.

This module provides an HTTP client class with automatic retry mechanism,
exponential backoff, and comprehensive error handling for external API calls.

Author: Manuel Ziel
License: MIT
"""

################################################################################
# IMPORTS & DEPENDENCIES
################################################################################

# Standard Imports
import logging
import time
from typing import Any, Dict, Optional

# Third-Party Imports
import requests

# Local Imports
from src.core.exceptions import ValidationError
from src.core.constants import HTTPMethod


################################################################################
# HTTP CLIENT CLASS - API Communication with Retry Logic
################################################################################

class HTTPClient:
    """HTTP client with automatic retry and exponential backoff.

    Provides reliable HTTP communication with configurable retries,
    timeouts, and error handling for external API integrations.

    Attributes:
        base_url: Base URL for API requests.
        timeout: Request timeout in seconds.
        retries: Maximum number of retry attempts.
        logger: Logger instance for request logging.
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        timeout: int = 30,
        retries: int = 3,
        logger: Optional[Any] = None,
    ) -> None:
        """Initialize HTTP client.

        Args:
            base_url: Base URL for all requests. Defaults to None.
            timeout: Request timeout in seconds. Defaults to 30.
            retries: Maximum retry attempts. Defaults to 3.
            logger: Logger instance. Creates default if None.
        """
        self.base_url = base_url
        self.timeout = timeout
        self.retries = retries

        if logger:
            self.logger = logger
        else:
            self.logger = logging.getLogger(__name__)


    def request_with_retry(
        self,
        method: str,
        endpoint: Optional[str] = None,
        url: Optional[str] = None,
        headers: Optional[Dict[str, str]] = None,
        json_data: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> Optional[requests.Response]:
        """Make HTTP request with automatic retry on failure.

        Implements exponential backoff between retries. Either url or endpoint
        (with base_url) must be provided.

        Args:
            method: HTTP method (GET, POST, PUT, DELETE).
            endpoint: API endpoint path (combined with base_url).
            url: Full URL (overrides base_url + endpoint).
            headers: Request headers dictionary.
            json_data: JSON payload for POST/PUT requests.
            **kwargs: Additional arguments passed to requests.

        Returns:
            requests.Response object if successful, None if all retries failed.

        Raises:
            ValidationError: If an unsupported HTTP method is provided.
        """
        if url:
            final_url = url
        elif self.base_url and endpoint:
            final_url = f"{self.base_url.rstrip('/')}/{endpoint.lstrip('/')}"
        elif endpoint:
            final_url = endpoint
        else:
            self.logger.error(
                "Either 'url' or 'endpoint' (with base_url) must be provided"
            )
            return None

        retries = kwargs.pop("retries", self.retries)
        timeout = kwargs.pop("timeout", self.timeout)

        for attempt in range(retries):
            try:
                if method.upper() == "GET":
                    response = requests.get(
                        final_url, headers=headers, timeout=timeout, **kwargs
                    )
                elif method.upper() == "POST":
                    response = requests.post(
                        final_url,
                        headers=headers,
                        json=json_data,
                        timeout=timeout,
                        **kwargs,
                    )
                elif method.upper() == "PUT":
                    response = requests.put(
                        final_url,
                        headers=headers,
                        json=json_data,
                        timeout=timeout,
                        **kwargs,
                    )
                elif method.upper() == "DELETE":
                    response = requests.delete(
                        final_url, headers=headers, timeout=timeout, **kwargs
                    )
                else:
                    raise ValidationError(f"Unsupported HTTP method: {method}")

                self.logger.debug(
                    f"{method.upper()} {final_url} - Status: {response.status_code}"
                )
                return response

            except requests.exceptions.Timeout:
                self.logger.warning(
                    f"Request timeout (attempt {attempt + 1}/{retries}) - {final_url}"
                )
                if attempt < retries - 1:
                    time.sleep(2**attempt)

            except requests.exceptions.RequestException as e:
                self.logger.warning(
                    f"Request failed (attempt {attempt + 1}/{retries}): {e}"
                )
                if attempt < retries - 1:
                    time.sleep(2**attempt)

        self.logger.error(
            f"All {retries} retry attempts failed for {method.upper()} {final_url}"
        )
        return None


    ################################################################################
    # HTTP METHOD CONVENIENCE WRAPPERS - Simplified API
    ################################################################################

    def get(
        self, endpoint: Optional[str] = None, url: Optional[str] = None, **kwargs: Any
    ) -> Optional[requests.Response]:
        """GET request wrapper.

        Args:
            endpoint: API endpoint path.
            url: Full URL (overrides endpoint).
            **kwargs: Additional arguments passed to requests.

        Returns:
            requests.Response object or None on failure.
        """
        return self.request_with_retry(
            HTTPMethod.GET, endpoint=endpoint, url=url, **kwargs
        )


    def post(
        self,
        endpoint: Optional[str] = None,
        url: Optional[str] = None,
        json_data: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> Optional[requests.Response]:
        """POST request wrapper.

        Args:
            endpoint: API endpoint path.
            url: Full URL (overrides endpoint).
            json_data: JSON payload for request body.
            **kwargs: Additional arguments passed to requests.

        Returns:
            requests.Response object or None on failure.
        """
        return self.request_with_retry(
            HTTPMethod.POST, endpoint=endpoint, url=url, json_data=json_data, **kwargs
        )


    def put(
        self,
        endpoint: Optional[str] = None,
        url: Optional[str] = None,
        json_data: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> Optional[requests.Response]:
        """PUT request wrapper.

        Args:
            endpoint: API endpoint path.
            url: Full URL (overrides endpoint).
            json_data: JSON payload for request body.
            **kwargs: Additional arguments passed to requests.

        Returns:
            requests.Response object or None on failure.
        """
        return self.request_with_retry(
            HTTPMethod.PUT, endpoint=endpoint, url=url, json_data=json_data, **kwargs
        )


    def delete(
        self, endpoint: Optional[str] = None, url: Optional[str] = None, **kwargs: Any
    ) -> Optional[requests.Response]:
        """DELETE request wrapper.

        Args:
            endpoint: API endpoint path.
            url: Full URL (overrides endpoint).
            **kwargs: Additional arguments passed to requests.

        Returns:
            requests.Response object or None on failure.
        """
        return self.request_with_retry(
            HTTPMethod.DELETE, endpoint=endpoint, url=url, **kwargs
        )
