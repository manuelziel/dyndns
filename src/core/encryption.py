#!/usr/bin/env python3
"""Encryption manager for sensitive data protection.

This module provides encryption and decryption of sensitive data using
Fernet symmetric encryption (AES-128-CBC with HMAC-SHA256).

The encryption key is auto-generated if not exists and stored with
secure permissions (0o600). Key rotation is not yet implemented.

Typical usage:
    >>> enc = EncryptionManager('/var/lib/ionos-dyndns/.encryption_key')
    >>> encrypted = enc.encrypt('api-secret-key')
    >>> decrypted = enc.decrypt(encrypted)

Author: Manuel Ziel
License: MIT
"""

################################################################################
# IMPORTS & DEPENDENCIES
################################################################################

import os
from typing import Optional, Any
from cryptography.fernet import Fernet

# Local imports
from .exceptions import EncryptionError, ValidationError

################################################################################
# ENCRYPTION MANAGER CLASS
################################################################################

class EncryptionManager:
    """Encryption manager using Fernet (AES-128-CBC + HMAC-SHA256).

    Provides symmetric encryption for sensitive data. Auto-generates
    encryption key if not exists and enforces 0o600 permissions.

    Attributes:
        key_file: Path to the encryption key file.
        logger: Optional logger instance for error reporting.
    """
    
    def __init__(self, key_file_path: str, logger: Optional[Any] = None) -> None:
        """Initialize encryption manager.

        Creates the encryption key file if it does not exist.

        Args:
            key_file_path: Absolute path to encryption key file.
            logger: Optional logger instance for error reporting.

        Raises:
            EncryptionError: If encryption setup fails.
        """
        self.key_file = key_file_path
        self.logger = logger
        self._encryption_key = None
        self._cipher = None
        
        self._setup_encryption()
    
    ################################################################################
    # PUBLIC INTERFACE - Encryption/Decryption Operations
    ################################################################################
    
    def encrypt(self, data: str) -> str:
        """Encrypt a string using Fernet encryption.

        Args:
            data: Plain text string to encrypt. Must not be empty.

        Returns:
            Base64-encoded encrypted string.

        Raises:
            EncryptionError: If encryption fails or cipher not initialized.
            ValidationError: If data is empty.
        """
        if not self._cipher:
            raise EncryptionError("Encryption not initialized")
        
        if not data:
            raise ValidationError("Cannot encrypt empty data")
        
        try:
            encrypted = self._cipher.encrypt(data.encode()).decode()
            return encrypted
        except Exception as e:
            if self.logger:
                self.logger.error(f"Encryption failed: {e}")
            raise EncryptionError(f"Encryption failed: {e}")
    
    def decrypt(self, encrypted_data: str) -> str:
        """Decrypt Fernet-encrypted data.

        Args:
            encrypted_data: Base64-encoded encrypted string.

        Returns:
            Decrypted plain text string.

        Raises:
            EncryptionError: If decryption fails or cipher not initialized.
            ValidationError: If encrypted_data is empty.
        """
        if not self._cipher:
            raise EncryptionError("Encryption not initialized")
        
        if not encrypted_data:
            raise ValidationError("Cannot decrypt empty data")
        
        try:
            decrypted = self._cipher.decrypt(encrypted_data.encode()).decode()
            return decrypted
        except Exception as e:
            if self.logger:
                self.logger.error(f"Decryption failed: {e}")
            raise EncryptionError(f"Decryption failed: {e}")
    
    def rotate_key(self, new_key_file_path: str) -> None:
        """Rotate the encryption key.

        Note:
            NOT YET IMPLEMENTED. Requires re-encrypting all existing
            encrypted data in the database.

        Args:
            new_key_file_path: Path for the new encryption key file.

        Raises:
            NotImplementedError: Always raised as feature is not implemented.
        """
        raise NotImplementedError("Key rotation not yet implemented")
    
    ################################################################################
    # PRIVATE METHODS - Internal Implementation
    ################################################################################
    
    def _setup_encryption(self) -> None:
        """Setup encryption key and cipher instance.

        Loads existing key from file or generates a new one. Sets file
        permissions to 0o600 for security.

        Raises:
            EncryptionError: If key loading or generation fails.
        """
        try:
            if os.path.exists(self.key_file):
                with open(self.key_file, 'rb') as f:
                    self._encryption_key = f.read()
                
                current_perms = os.stat(self.key_file).st_mode & 0o777
                if current_perms != 0o600:
                    os.chmod(self.key_file, 0o600)
                    if self.logger:
                        self.logger.warning(f"Fixed encryption key permissions: {self.key_file}")
            else:
                self._encryption_key = Fernet.generate_key()
                
                key_dir = os.path.dirname(self.key_file)
                if key_dir and not os.path.exists(key_dir):
                    os.makedirs(key_dir, mode=0o700, exist_ok=True)
                
                with open(self.key_file, 'wb') as f:
                    f.write(self._encryption_key)
                
                os.chmod(self.key_file, 0o600)
                
                if self.logger:
                    self.logger.info(f"Generated new encryption key: {self.key_file}")
            
            # Fernet keys are always 32 bytes URL-safe base64 (44 chars)
            if len(self._encryption_key) != 44:
                raise ValidationError(
                    f"Invalid encryption key length: {len(self._encryption_key)} (expected 44)"
                )
            
            self._cipher = Fernet(self._encryption_key)
            
        except Exception as e:
            if self.logger:
                self.logger.error(f"Encryption setup failed: {e}")
            raise EncryptionError(f"Failed to setup encryption: {e}")