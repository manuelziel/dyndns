#!/usr/bin/env python3
"""
Network Utilities Module

Network-related utilities like IP detection, connectivity checks, etc.

Created: 2025-10-27
Author: Manuel Ziel
License: MIT
"""

################################################################################
# IMPORTS & DEPENDENCIES
################################################################################

import requests
import time
import logging
from typing import Optional, Tuple, Dict, Any
from exceptions import NetworkError

################################################################################
# NETWORK DATA CLASS - IP Detection and State Management
################################################################################

class NetworkData:
    """Network data container for IP addresses and network configuration."""
    
    def __init__(self, ipv4_address: Optional[str] = None, ipv6_address: Optional[str] = None, 
                 last_ipv4_address: Optional[str] = None, last_ipv6_address: Optional[str] = None) -> None:
        self.ipv4_address = ipv4_address
        self.ipv6_address = ipv6_address
        self.last_ipv4_address = last_ipv4_address
        self.last_ipv6_address = last_ipv6_address
        
        self.ipv4_enabled = True
        self.ipv6_enabled = True
        self.ipv4_detection_url = "https://api.ipify.org"
        self.ipv6_detection_url = "https://api6.ipify.org"
        self.timeout = 10
        self.retry_attempts = 3
        self.logger = logging.getLogger(__name__)

    ################################################################################
    # CONFIGURATION METHODS - Setup and Initialization
    ################################################################################
        
    def setup(self, ipv4_enabled: bool = True, ipv6_enabled: bool = True, 
              ipv4_detection_url: Optional[str] = None, ipv6_detection_url: Optional[str] = None,
              timeout: Optional[int] = None, retry_attempts: Optional[int] = None, logger: Optional[Any] = None) -> bool:
        """Configure network data collection. Sets IPv4/IPv6 detection URLs, timeout, retry attempts, and logger."""
        self.ipv4_enabled = ipv4_enabled
        self.ipv6_enabled = ipv6_enabled
        
        if ipv4_detection_url:
            self.ipv4_detection_url = ipv4_detection_url
        if ipv6_detection_url:
            self.ipv6_detection_url = ipv6_detection_url
        if timeout is not None:
            self.timeout = timeout
        if retry_attempts is not None:
            self.retry_attempts = retry_attempts
        if logger:
            self.logger = logger
            
        return True

    ################################################################################
    # IP ADDRESS DETECTION - Public IP Retrieval
    ################################################################################
    
    def load_current_ip_addresses(self) -> Tuple[Optional[str], Optional[str]]:
        """Load current public IP addresses. Returns tuple (ipv4_address, ipv6_address)."""
        if self.ipv4_enabled:
            self.ipv4_address = self.get_current_public_ipv4_address()
        
        if self.ipv6_enabled:
            self.ipv6_address = self.get_current_public_ipv6_address()
            
        return self.ipv4_address, self.ipv6_address

    def get_current_public_ipv4_address(self, retries: Optional[int] = None, timeout: Optional[int] = None) -> Optional[str]:
        """Get current public IPv4 address with retry logic. Returns IPv4 string or None if failed."""
        retries = retries if retries is not None else self.retry_attempts
        timeout = timeout if timeout is not None else self.timeout
        
        for attempt in range(retries):
            try:
                response = requests.get(self.ipv4_detection_url, timeout=timeout)
                if response.status_code == 200 and response.text:
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
                time.sleep(2)
                
        self.logger.error("Failed to fetch IPv4 address after multiple attempts")
        return None

    def get_current_public_ipv6_address(self, retries: Optional[int] = None, timeout: Optional[int] = None) -> Optional[str]:
        """Get current public IPv6 address with retry logic. Returns IPv6 string or None if failed."""
        retries = retries if retries is not None else self.retry_attempts
        timeout = timeout if timeout is not None else self.timeout
        
        for attempt in range(retries):
            try:
                response = requests.get(self.ipv6_detection_url, timeout=timeout)
                if response.status_code == 200 and response.text:
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
                time.sleep(2)
                
        self.logger.error("Failed to fetch IPv6 address after multiple attempts")
        return None

    ################################################################################
    # STATE MANAGEMENT - IP Change Detection
    ################################################################################
        
    def save_current_as_last(self) -> None:
        """Save current IP addresses as last known addresses."""
        self.last_ipv4_address = self.ipv4_address
        self.last_ipv6_address = self.ipv6_address
        
    def has_ip_changed(self) -> Dict[str, bool]:
        """Check if IP addresses have changed since last save. Returns dict with 'ipv4_changed' and 'ipv6_changed' bools."""
        return {
            'ipv4_changed': self.ipv4_address != self.last_ipv4_address,
            'ipv6_changed': self.ipv6_address != self.last_ipv6_address
        }

    ################################################################################
    # STATUS & INFORMATION - Network Status Reporting
    ################################################################################
        
    def get_status(self) -> Dict[str, Any]:
        """Get current network status. Returns dict with all IP addresses and enabled flags."""
        return {
            'ipv4_address': self.ipv4_address,
            'ipv6_address': self.ipv6_address,
            'last_ipv4_address': self.last_ipv4_address,
            'last_ipv6_address': self.last_ipv6_address,
            'ipv4_enabled': self.ipv4_enabled,
            'ipv6_enabled': self.ipv6_enabled
        }