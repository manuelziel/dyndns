#!/usr/bin/env python3
"""
Encryption Manager

Handles encryption and decryption of sensitive data using Fernet (AES-128 CBC).

Created: 2025-10-27
Author: Manuel Ziel
License: MIT
"""

################################################################################
# IMPORTS & DEPENDENCIES
################################################################################

import os
from typing import Optional, Any
from cryptography.fernet import Fernet
from exceptions import EncryptionError

################################################################################
# ENCRYPTION MANAGER CLASS
################################################################################

class EncryptionManager:
    """Manages encryption/decryption using Fernet (AES-128 CBC + HMAC-SHA256). Auto-generates key, enforces 0o600 permissions."""
    
    def __init__(self, key_file_path: str, logger: Optional[Any] = None) -> None:
        """Initialize encryption manager. Creates key file if not exists. Raises RuntimeError if setup fails."""
        self.key_file = key_file_path
        self.logger = logger
        self._encryption_key = None
        self._cipher = None
        
        self._setup_encryption()
    
    ################################################################################
    # PUBLIC METHODS - Encryption and Decryption
    ################################################################################
    
    def encrypt(self, data: str) -> str:
        """Encrypt string data using Fernet. Returns base64 encoded string. Raises EncryptionError."""
        if not self._cipher:
            raise EncryptionError("Encryption not initialized")
        
        if not data:
            raise ValueError("Cannot encrypt empty data")
        
        try:
            encrypted = self._cipher.encrypt(data.encode()).decode()
            return encrypted
        except Exception as e:
            if self.logger:
                self.logger.error(f"Encryption failed: {e}")
            raise EncryptionError(f"Encryption failed: {e}")
    
    def decrypt(self, encrypted_data: str) -> str:
        """Decrypt Fernet-encrypted data. Returns plain text string. Raises EncryptionError."""
        if not self._cipher:
            raise EncryptionError("Encryption not initialized")
        
        if not encrypted_data:
            raise ValueError("Cannot decrypt empty data")
        
        try:
            decrypted = self._cipher.decrypt(encrypted_data.encode()).decode()
            return decrypted
        except Exception as e:
            if self.logger:
                self.logger.error(f"Decryption failed: {e}")
            raise EncryptionError(f"Decryption failed: {e}")
    
    def rotate_key(self, new_key_file_path: str) -> None:
        """Rotate encryption key. Not yet implemented - requires re-encrypting all data."""
        raise NotImplementedError("Key rotation not yet implemented")
    
    ################################################################################
    # PRIVATE METHODS - Encryption Setup and Key Management
    ################################################################################
    
    def _setup_encryption(self) -> None:
        """Setup Fernet encryption. Loads or generates key, enforces 0o600 permissions, initializes cipher. Raises RuntimeError if fails."""
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
                raise ValueError(
                    f"Invalid encryption key length: {len(self._encryption_key)} (expected 44)"
                )
            
            self._cipher = Fernet(self._encryption_key)
            
        except Exception as e:
            if self.logger:
                self.logger.error(f"Encryption setup failed: {e}")
            raise EncryptionError(f"Failed to setup encryption: {e}")