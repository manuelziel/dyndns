#!/usr/bin/env python3
"""Network utilities module for IP detection and connectivity.

This module provides the NetworkData class for detecting public IP addresses,
tracking IP changes, and managing network configuration state.

Typical usage:
    >>> network = NetworkData(config, logger)
    >>> ipv4, ipv6 = network.load_current_ip_addresses()

Author: Manuel Ziel
License: MIT
"""

################################################################################
# IMPORTS & DEPENDENCIES
################################################################################

# Standard Imports
import requests
import time
import logging
from typing import Optional, Tuple, Dict, Any

# Local Imports
from src.core.constants import HTTPStatus, NetworkAPI

################################################################################
# NETWORK DATA CLASS - IP Detection and State Management
################################################################################

class NetworkData:
    """Network data container for IP addresses and network configuration.

    Attributes:
        config: ConfigManager instance with network settings.
        logger: Logger instance for debug and error messages.
        ipv4_address: Current detected IPv4 address or None.
        ipv6_address: Current detected IPv6 address or None.
        last_ipv4_address: Previously saved IPv4 address or None.
        last_ipv6_address: Previously saved IPv6 address or None.
        ipv4_enabled: Whether IPv4 detection is enabled.
        ipv6_enabled: Whether IPv6 detection is enabled.
        ipv4_detection_url: URL for IPv4 address detection service.
        ipv6_detection_url: URL for IPv6 address detection service.
        timeout: Request timeout in seconds.
        retry_attempts: Number of retry attempts for failed requests.
    """
    
    def __init__(self, config: Any, logger: Optional[Any] = None,
                 ipv4_enabled: Optional[bool] = None, ipv6_enabled: Optional[bool] = None) -> None:
        """Initialize NetworkData with configuration object.

        Args:
            config: ConfigManager instance with network settings.
            logger: Optional logger instance for logging output.
            ipv4_enabled: Override config.network_ipv4_enabled if set.
            ipv6_enabled: Override config.network_ipv6_enabled if set.
        """
        self.config = config
        self.logger = logger if logger else logging.getLogger(__name__)
        
        self.ipv4_address: Optional[str] = None
        self.ipv6_address: Optional[str] = None
        self.last_ipv4_address: Optional[str] = None
        self.last_ipv6_address: Optional[str] = None
        
        self.ipv4_enabled = ipv4_enabled if ipv4_enabled is not None else config.network_ipv4_enabled
        self.ipv6_enabled = ipv6_enabled if ipv6_enabled is not None else config.network_ipv6_enabled
        self.ipv4_detection_url = config.network_ipv4_detection_url
        self.ipv6_detection_url = config.network_ipv6_detection_url
        self.timeout = config.network_timeout
        self.retry_attempts = config.network_retry_attempts


    ################################################################################
    # IP ADDRESS DETECTION - Public IP Retrieval
    ################################################################################
    
    def load_current_ip_addresses(self) -> Tuple[Optional[str], Optional[str]]:
        """Load current public IP addresses from detection services.

        Fetches IPv4 and/or IPv6 addresses based on enabled settings.

        Returns:
            Tuple of (ipv4_address, ipv6_address), either may be None
            if detection failed or is disabled.
        """
        if self.ipv4_enabled:
            self.ipv4_address = self.get_current_public_ipv4_address()
        
        if self.ipv6_enabled:
            self.ipv6_address = self.get_current_public_ipv6_address()
            
        return self.ipv4_address, self.ipv6_address


    def get_current_public_ipv4_address(self, retries: Optional[int] = None, timeout: Optional[int] = None) -> Optional[str]:
        """Get current public IPv4 address with retry logic.

        Args:
            retries: Number of retry attempts, defaults to config value.
            timeout: Request timeout in seconds, defaults to config value.

        Returns:
            IPv4 address string if successful, None if all attempts failed.
        """
        retries = retries if retries is not None else self.retry_attempts
        timeout = timeout if timeout is not None else self.timeout
        
        for attempt in range(retries):
            try:
                response = requests.get(self.ipv4_detection_url, timeout=timeout)
                if response.status_code == HTTPStatus.OK and response.text:
                    ipv4_address = response.text.strip()
                    self.logger.debug(f"IPv4 address detected: {ipv4_address}")
                    return ipv4_address
                else:
                    self.logger.warning(f"Invalid IPv4 response: {response.status_code}")
                    
            except requests.exceptions.Timeout:
                self.logger.warning(f"IPv4 detection timeout (attempt {attempt + 1}/{retries})")
            except requests.exceptions.RequestException as e:
                self.logger.warning(f"IPv4 detection error (attempt {attempt + 1}/{retries}): {e}")
                
            if attempt < retries - 1:
                time.sleep(NetworkAPI.RETRY_DELAY)
                
        self.logger.error("Failed to fetch IPv4 address after multiple attempts")
        return None


    def get_current_public_ipv6_address(self, retries: Optional[int] = None, timeout: Optional[int] = None) -> Optional[str]:
        """Get current public IPv6 address with retry logic.

        Args:
            retries: Number of retry attempts, defaults to config value.
            timeout: Request timeout in seconds, defaults to config value.

        Returns:
            IPv6 address string if successful, None if all attempts failed.
        """
        retries = retries if retries is not None else self.retry_attempts
        timeout = timeout if timeout is not None else self.timeout
        
        for attempt in range(retries):
            try:
                response = requests.get(self.ipv6_detection_url, timeout=timeout)
                if response.status_code == HTTPStatus.OK and response.text:
                    ipv6_address = response.text.strip()
                    self.logger.debug(f"IPv6 address detected: {ipv6_address}")
                    return ipv6_address
                else:
                    self.logger.warning(f"Invalid IPv6 response: {response.status_code}")
                    
            except requests.exceptions.Timeout:
                self.logger.warning(f"IPv6 detection timeout (attempt {attempt + 1}/{retries})")
            except requests.exceptions.RequestException as e:
                self.logger.warning(f"IPv6 detection error (attempt {attempt + 1}/{retries}): {e}")
                
            if attempt < retries - 1:
                time.sleep(NetworkAPI.RETRY_DELAY)
                
        self.logger.error("Failed to fetch IPv6 address after multiple attempts")
        return None


    ################################################################################
    # STATE MANAGEMENT - IP Change Detection
    ################################################################################
        
    def save_current_as_last(self) -> None:
        """Save current IP addresses as last known addresses.

        Copies ipv4_address to last_ipv4_address and ipv6_address to
        last_ipv6_address for change detection.
        """
        self.last_ipv4_address = self.ipv4_address
        self.last_ipv6_address = self.ipv6_address
        

    def has_ip_changed(self) -> Dict[str, bool]:
        """Check if IP addresses have changed since last save.

        Returns:
            Dictionary with 'ipv4_changed' and 'ipv6_changed' boolean values
            indicating whether each address type has changed.
        """
        return {
            'ipv4_changed': self.ipv4_address != self.last_ipv4_address,
            'ipv6_changed': self.ipv6_address != self.last_ipv6_address
        }


    ################################################################################
    # STATUS & INFORMATION - Network Status Reporting
    ################################################################################
        
    def get_status(self) -> Dict[str, Any]:
        """Get current network status information.

        Returns:
            Dictionary containing current and last IP addresses for both
            IPv4 and IPv6, plus enabled flags for each protocol.
        """
        return {
            'ipv4_address': self.ipv4_address,
            'ipv6_address': self.ipv6_address,
            'last_ipv4_address': self.last_ipv4_address,
            'last_ipv6_address': self.last_ipv6_address,
            'ipv4_enabled': self.ipv4_enabled,
            'ipv6_enabled': self.ipv6_enabled
        }