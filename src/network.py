#!/usr/bin/env python3
"""Network utilities module for public IP detection and change tracking.

Provides ``NetworkData`` for probing external IPv4/IPv6 detection endpoints,
validating returned IP literals via ``ipaddress``, redacting sensitive URIs in
logs, and preserving known-good state across transient network outages.

Author: Manuel Ziel
License: MIT
"""

################################################################################
# IMPORTS & DEPENDENCIES
################################################################################

import ipaddress
import logging
import time
from typing import Any

import requests

from .core.constants import HTTPStatus, NetworkAPI
from .core.security import sanitize_log_uri

################################################################################
# NETWORK DATA CLASS
################################################################################


class NetworkData:
    """Public IPv4/IPv6 address detector and change-state tracker.

    Attributes:
        config: Optional ``ConfigManager`` instance.
        logger: Logger instance for network diagnostics.
        ipv4_address: Latest validated public IPv4 address or ``None``.
        ipv6_address: Latest validated public IPv6 address or ``None``.
        last_ipv4_address: Previously committed IPv4 address or ``None``.
        last_ipv6_address: Previously committed IPv6 address or ``None``.
        ipv4_enabled: Whether IPv4 probing is enabled.
        ipv6_enabled: Whether IPv6 probing is enabled.
        ipv4_detection_url: Endpoint URL for public IPv4 lookup.
        ipv6_detection_url: Endpoint URL for public IPv6 lookup.
        timeout: HTTP probe timeout in seconds.
        retry_attempts: Number of retry attempts per probe.
    """

    def __init__(
        self,
        config: Any | None = None,
        logger: logging.Logger | None = None,
        ipv4_enabled: bool | None = None,
        ipv6_enabled: bool | None = None,
    ) -> None:
        """Initialize ``NetworkData`` from optional ``ConfigManager`` defaults.

        Args:
            config: Optional ``ConfigManager`` instance with network settings.
            logger: Optional logger instance.
            ipv4_enabled: Explicit override for ``ipv4_enabled``.
            ipv6_enabled: Explicit override for ``ipv6_enabled``.
        """
        self.config = config
        self.logger = logger or logging.getLogger(__name__)
        self.ipv4_address: str | None = None
        self.ipv6_address: str | None = None
        self.last_ipv4_address: str | None = None
        self.last_ipv6_address: str | None = None

        self.ipv4_enabled = (
            ipv4_enabled
            if ipv4_enabled is not None
            else getattr(config, "network_ipv4_enabled", NetworkAPI.IPV4_ENABLED)
        )
        self.ipv6_enabled = (
            ipv6_enabled
            if ipv6_enabled is not None
            else getattr(config, "network_ipv6_enabled", NetworkAPI.IPV6_ENABLED)
        )
        self.ipv4_detection_url = getattr(
            config, "network_ipv4_detection_url", NetworkAPI.IPV4_URL
        )
        self.ipv6_detection_url = getattr(
            config, "network_ipv6_detection_url", NetworkAPI.IPV6_URL
        )
        self.timeout = getattr(config, "network_timeout", NetworkAPI.TIMEOUT)
        self.retry_attempts = getattr(
            config, "network_retry_attempts", NetworkAPI.RETRY_ATTEMPTS
        )

    def setup(
        self,
        ipv4_enabled: bool,
        ipv6_enabled: bool,
        ipv4_url: str,
        ipv6_url: str,
        timeout: int,
        retries: int,
        logger: logging.Logger | None = None,
    ) -> None:
        """Configure or hot-reload network detection parameters explicitly.

        Args:
            ipv4_enabled: Whether IPv4 detection is enabled.
            ipv6_enabled: Whether IPv6 detection is enabled.
            ipv4_url: Endpoint URL for IPv4 detection.
            ipv6_url: Endpoint URL for IPv6 detection.
            timeout: Request timeout in seconds.
            retries: Maximum retry attempts per probe.
            logger: Optional replacement logger instance.
        """
        self.ipv4_enabled = ipv4_enabled
        self.ipv6_enabled = ipv6_enabled
        self.ipv4_detection_url = ipv4_url
        self.ipv6_detection_url = ipv6_url
        self.timeout = timeout
        self.retry_attempts = retries
        if logger is not None:
            self.logger = logger

    ############################################################################
    # PUBLIC IP DETECTION
    ############################################################################

    def load_current_ip_addresses(self) -> tuple[str | None, str | None]:
        """Probe enabled public IP endpoints while preserving last-known IPs on outage.

        Returns:
            Tuple ``(ipv4_address, ipv6_address)``.
        """
        if self.ipv4_enabled:
            detected_v4 = self.get_current_public_ipv4_address()
            if detected_v4 is not None:
                self.ipv4_address = detected_v4
        else:
            self.ipv4_address = None

        if self.ipv6_enabled:
            detected_v6 = self.get_current_public_ipv6_address()
            if detected_v6 is not None:
                self.ipv6_address = detected_v6
        else:
            self.ipv6_address = None

        return self.ipv4_address, self.ipv6_address

    def get_current_public_ipv4_address(
        self, retries: int | None = None, timeout: int | None = None
    ) -> str | None:
        """Fetch and validate the current public IPv4 address.

        Args:
            retries: Optional retry count override.
            timeout: Optional timeout override in seconds.

        Returns:
            Canonical IPv4 address string or ``None`` if all attempts fail.
        """
        return self._fetch_public_ip(
            self.ipv4_detection_url, "IPv4", retries=retries, timeout=timeout
        )

    def get_current_public_ipv6_address(
        self, retries: int | None = None, timeout: int | None = None
    ) -> str | None:
        """Fetch and validate the current public IPv6 address.

        Args:
            retries: Optional retry count override.
            timeout: Optional timeout override in seconds.

        Returns:
            Canonical IPv6 address string or ``None`` if all attempts fail.
        """
        return self._fetch_public_ip(
            self.ipv6_detection_url, "IPv6", retries=retries, timeout=timeout
        )

    def _fetch_public_ip(
        self,
        url: str,
        protocol: str,
        retries: int | None = None,
        timeout: int | None = None,
    ) -> str | None:
        """Query an IP detection URL with retries and strict address validation.

        Args:
            url: Detection endpoint URL.
            protocol: Protocol label (``'IPv4'`` or ``'IPv6'``).
            retries: Optional retry count override.
            timeout: Optional request timeout override in seconds.

        Returns:
            Validated IP string or ``None`` when detection fails.
        """
        max_retries = retries if retries is not None else self.retry_attempts
        req_timeout = timeout if timeout is not None else self.timeout
        safe_url = sanitize_log_uri(url)

        for attempt in range(max_retries):
            validated = self._probe_ip_once(url, safe_url, protocol, req_timeout, attempt, max_retries)
            if validated is not None:
                return validated
            if attempt < max_retries - 1:
                time.sleep(NetworkAPI.RETRY_DELAY)

        self.logger.error(f"Failed to fetch {protocol} address from {safe_url}")
        return None

    def _probe_ip_once(
        self,
        url: str,
        safe_url: str,
        protocol: str,
        timeout: int,
        attempt: int,
        max_retries: int,
    ) -> str | None:
        """Perform a single HTTP GET probe and validate the returned IP payload.

        Args:
            url: Raw detection endpoint URL.
            safe_url: Redacted URL safe for logging.
            protocol: Protocol label (``'IPv4'`` or ``'IPv6'``).
            timeout: Request timeout in seconds.
            attempt: Zero-based attempt index.
            max_retries: Total configured retry attempts.

        Returns:
            Canonical IP string if valid, ``None`` otherwise.
        """
        try:
            response = requests.get(url, timeout=timeout)
            if response.status_code == HTTPStatus.OK and response.text:
                validated = self._validate_ip_response(response.text, protocol)
                if validated is not None:
                    self.logger.debug(f"{protocol} address detected: {validated}")
                    return validated
                self.logger.warning(f"Malformed {protocol} payload from {safe_url}")
            else:
                self.logger.warning(
                    f"Invalid {protocol} response ({response.status_code}) from {safe_url}"
                )
        except requests.exceptions.Timeout:
            self.logger.warning(
                f"{protocol} detection timeout (attempt {attempt + 1}/{max_retries}) from {safe_url}"
            )
        except requests.exceptions.RequestException as exc:
            self.logger.warning(
                f"{protocol} detection error (attempt {attempt + 1}/{max_retries}): "
                f"{sanitize_log_uri(str(exc))}"
            )
        return None

    @staticmethod
    def _validate_ip_response(raw_text: str, protocol: str) -> str | None:
        """Parse and validate a raw text response as a canonical IP literal.

        Args:
            raw_text: Raw HTTP body returned by the IP detection service.
            protocol: Expected address family (``'IPv4'`` or ``'IPv6'``).

        Returns:
            Canonical IP string, or ``None`` if parsing fails.
        """
        candidate = raw_text.strip()
        try:
            if protocol == "IPv4":
                return str(ipaddress.IPv4Address(candidate))
            return str(ipaddress.IPv6Address(candidate))
        except ipaddress.AddressValueError:
            return None

    ############################################################################
    # STATE MANAGEMENT & DIAGNOSTICS
    ############################################################################

    def save_current_as_last(self) -> None:
        """Record the currently detected IP addresses as the last committed state."""
        self.last_ipv4_address = self.ipv4_address
        self.last_ipv6_address = self.ipv6_address

    def has_ip_changed(self) -> dict[str, bool]:
        """Compare active non-null IP addresses against last saved addresses.

        Returns:
            Dictionary with ``ipv4_changed`` and ``ipv6_changed`` flags.
        """
        return {
            "ipv4_changed": (
                self.ipv4_address is not None
                and self.ipv4_address != self.last_ipv4_address
            ),
            "ipv6_changed": (
                self.ipv6_address is not None
                and self.ipv6_address != self.last_ipv6_address
            ),
        }

    def get_status(self) -> dict[str, Any]:
        """Return a snapshot dictionary of current and previous IP state.

        Returns:
            Dictionary of IPv4/IPv6 addresses and enabled flags.
        """
        return {
            "ipv4_address": self.ipv4_address,
            "ipv6_address": self.ipv6_address,
            "last_ipv4_address": self.last_ipv4_address,
            "last_ipv6_address": self.last_ipv6_address,
            "ipv4_enabled": self.ipv4_enabled,
            "ipv6_enabled": self.ipv6_enabled,
        }
