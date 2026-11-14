#!/usr/bin/env python3
"""HTTP client module with persistent session pooling and retry backoff.

Provides ``HTTPClient`` with connection reuse via ``requests.Session``,
exponential backoff with ``Retry-After`` support on ``429``/``5xx`` responses,
and automatic URI secret redaction in log output.

Author: Manuel Ziel
License: MIT
"""

################################################################################
# IMPORTS & DEPENDENCIES
################################################################################

import logging
import time
from typing import Any

import requests

from ..core.constants import HTTPHeader, HTTPMethod, ProviderAPI
from ..core.exceptions import ValidationError
from ..core.security import sanitize_log_uri

################################################################################
# HTTP CLIENT CLASS
################################################################################


class HTTPClient:
    """Session-backed HTTP client with retry, ``Retry-After``, and URI redaction.

    Attributes:
        base_url: Optional base URL prepended to relative endpoints.
        timeout: Default request timeout in seconds.
        retries: Default maximum number of retry attempts.
        logger: Logger instance for HTTP diagnostics.
    """

    def __init__(
        self,
        base_url: str | None = None,
        timeout: int = ProviderAPI.TIMEOUT,
        retries: int = ProviderAPI.RETRY_ATTEMPTS,
        logger: logging.Logger | None = None,
    ) -> None:
        """Initialize HTTP client and underlying ``requests.Session``.

        Args:
            base_url: Optional base URL for relative API endpoints.
            timeout: Request timeout in seconds.
            retries: Maximum number of retry attempts.
            logger: Optional logger instance.
        """
        self.base_url = base_url
        self.timeout = timeout
        self.retries = retries
        self.logger = logger or logging.getLogger(__name__)
        self._session = requests.Session()

    def __enter__(self) -> "HTTPClient":
        """Enter context manager returning ``self``."""
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Close underlying HTTP session upon context exit."""
        _ = (exc_type, exc_val, exc_tb)
        self.close()

    def __del__(self) -> None:
        """Ensure pooled sockets are closed when garbage-collected."""
        self.close()

    def close(self) -> None:
        """Close the persistent ``requests.Session`` and release sockets."""
        session = getattr(self, "_session", None)
        if session is not None:
            session.close()

    ############################################################################
    # CORE RETRY & DISPATCH PIPELINE
    ############################################################################

    def request_with_retry(
        self,
        method: str,
        endpoint: str | None = None,
        url: str | None = None,
        headers: dict[str, str] | None = None,
        json_data: dict[str, Any] | list[Any] | None = None,
        **kwargs: Any,
    ) -> requests.Response | None:
        """Execute an HTTP request with exponential backoff and rate-limit retry.

        Args:
            method: HTTP verb (``GET``, ``POST``, ``PUT``, ``PATCH``, ``DELETE``).
            endpoint: Relative API endpoint combined with ``base_url``.
            url: Full request URL overriding ``base_url + endpoint``.
            headers: Optional HTTP request headers.
            json_data: Optional JSON body dictionary or list.
            **kwargs: Additional keyword arguments forwarded to ``requests``.

        Returns:
            ``requests.Response`` on completion, or ``None`` if all retries fail.

        Raises:
            ValidationError: If ``method`` is not a supported HTTP verb.
        """
        upper_method = method.upper()
        if upper_method not in ProviderAPI.SUPPORTED_METHODS:
            raise ValidationError(f"Unsupported HTTP method: {method}")
        final_url = self._resolve_request_url(endpoint, url)
        if not final_url:
            return None

        max_retries = max(1, int(kwargs.pop("retries", self.retries)))
        req_timeout = kwargs.pop("timeout", self.timeout)
        safe_url = sanitize_log_uri(final_url)
        last_response: requests.Response | None = None

        for attempt in range(max_retries):
            response, should_retry, delay = self._attempt_request(
                upper_method, final_url, safe_url, headers, json_data, req_timeout, attempt, max_retries, **kwargs
            )
            if response is not None and not should_retry:
                return response
            if response is not None:
                last_response = response
            if attempt < max_retries - 1:
                time.sleep(delay)

        self.logger.error(f"All {max_retries} retry attempts failed for {upper_method} {safe_url}")
        return last_response

    def _attempt_request(
        self,
        method: str,
        final_url: str,
        safe_url: str,
        headers: dict[str, str] | None,
        json_data: dict[str, Any] | list[Any] | None,
        timeout: int,
        attempt: int,
        max_retries: int,
        **kwargs: Any,
    ) -> tuple[requests.Response | None, bool, float]:
        """Execute one HTTP attempt and compute retry decision and backoff delay.

        Args:
            method: Validated uppercase HTTP verb.
            final_url: Target request URL.
            safe_url: Sanitized URL safe for log output.
            headers: Optional request headers.
            json_data: Optional JSON payload.
            timeout: Request timeout in seconds.
            attempt: Zero-based attempt counter.
            max_retries: Maximum configured attempts.
            **kwargs: Extra ``requests`` keyword arguments.

        Returns:
            Tuple ``(response, should_retry, backoff_seconds)``.
        """
        default_delay = min(
            float(ProviderAPI.BACKOFF_BASE**attempt), ProviderAPI.MAX_RETRY_DELAY
        )
        try:
            response = self._session.request(
                method=method,
                url=final_url,
                headers=headers,
                json=json_data,
                timeout=timeout,
                **kwargs,
            )
            self.logger.debug(f"{method} {safe_url} - Status: {response.status_code}")
            if response.status_code in ProviderAPI.RETRYABLE_STATUS_CODES and attempt < max_retries - 1:
                delay = self._compute_retry_delay(response, attempt)
                self.logger.warning(
                    f"Transient HTTP {response.status_code} (attempt {attempt + 1}/{max_retries}) "
                    f"for {safe_url}, retrying in {delay:.1f}s"
                )
                return response, True, delay
            return response, False, 0.0
        except requests.exceptions.Timeout:
            self.logger.warning(
                f"Request timeout (attempt {attempt + 1}/{max_retries}) - {safe_url}"
            )
        except requests.exceptions.RequestException as exc:
            self.logger.warning(
                f"Request failed (attempt {attempt + 1}/{max_retries}): {sanitize_log_uri(str(exc))}"
            )
        return None, True, default_delay

    def _compute_retry_delay(self, response: requests.Response, attempt: int) -> float:
        """Determine sleep duration from ``Retry-After`` or exponential backoff.

        Args:
            response: HTTP response carrying optional ``Retry-After`` header.
            attempt: Zero-based attempt index.

        Returns:
            Bounded delay in seconds.
        """
        retry_after = response.headers.get(HTTPHeader.RETRY_AFTER)
        if retry_after:
            try:
                parsed = float(retry_after.strip())
                if parsed >= 0:
                    return min(parsed, ProviderAPI.MAX_RETRY_DELAY)
            except ValueError:
                pass
        return min(float(ProviderAPI.BACKOFF_BASE**attempt), ProviderAPI.MAX_RETRY_DELAY)

    def _resolve_request_url(
        self, endpoint: str | None, url: str | None
    ) -> str | None:
        """Resolve the target URL from ``url`` or ``base_url + endpoint``.

        Args:
            endpoint: Relative API endpoint path.
            url: Full URL override.

        Returns:
            Resolved URL string, or ``None`` when neither is usable.
        """
        if url:
            return url
        if self.base_url and endpoint:
            return f"{self.base_url.rstrip('/')}/{endpoint.lstrip('/')}"
        if endpoint:
            return endpoint
        self.logger.error("Either 'url' or 'endpoint' (with base_url) must be provided")
        return None

    ############################################################################
    # HTTP VERB CONVENIENCE WRAPPERS
    ############################################################################

    def get(
        self, endpoint: str | None = None, url: str | None = None, **kwargs: Any
    ) -> requests.Response | None:
        """Send an HTTP ``GET`` request with retry."""
        return self.request_with_retry(HTTPMethod.GET, endpoint=endpoint, url=url, **kwargs)

    def post(
        self,
        endpoint: str | None = None,
        url: str | None = None,
        json_data: dict[str, Any] | list[Any] | None = None,
        **kwargs: Any,
    ) -> requests.Response | None:
        """Send an HTTP ``POST`` request with retry."""
        return self.request_with_retry(
            HTTPMethod.POST, endpoint=endpoint, url=url, json_data=json_data, **kwargs
        )

    def put(
        self,
        endpoint: str | None = None,
        url: str | None = None,
        json_data: dict[str, Any] | list[Any] | None = None,
        **kwargs: Any,
    ) -> requests.Response | None:
        """Send an HTTP ``PUT`` request with retry."""
        return self.request_with_retry(
            HTTPMethod.PUT, endpoint=endpoint, url=url, json_data=json_data, **kwargs
        )

    def patch(
        self,
        endpoint: str | None = None,
        url: str | None = None,
        json_data: dict[str, Any] | list[Any] | None = None,
        **kwargs: Any,
    ) -> requests.Response | None:
        """Send an HTTP ``PATCH`` request with retry."""
        return self.request_with_retry(
            HTTPMethod.PATCH, endpoint=endpoint, url=url, json_data=json_data, **kwargs
        )

    def delete(
        self, endpoint: str | None = None, url: str | None = None, **kwargs: Any
    ) -> requests.Response | None:
        """Send an HTTP ``DELETE`` request with retry."""
        return self.request_with_retry(HTTPMethod.DELETE, endpoint=endpoint, url=url, **kwargs)
