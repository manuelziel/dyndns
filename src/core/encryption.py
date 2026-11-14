#!/usr/bin/env python3
"""Encryption manager for sensitive data protection.

Provides symmetric encryption and decryption of sensitive data using Fernet
(AES-128-CBC with HMAC-SHA256). Auto-generates the encryption key if missing
and enforces symlink-safe ``0o600`` permissions.

Author: Manuel Ziel
License: MIT
"""

################################################################################
# IMPORTS & DEPENDENCIES
################################################################################

import os
from typing import Any

try:
    from cryptography.fernet import Fernet
except ImportError:
    Fernet = None  # type: ignore[assignment]

from .constants import EncryptionDefaults
from .exceptions import EncryptionError, ValidationError
from .ownership import ensure_service_ownership

################################################################################
# ENCRYPTION MANAGER CLASS
################################################################################


class EncryptionManager:
    """Encryption manager using Fernet (AES-128-CBC + HMAC-SHA256).

    Attributes:
        key_file: Path to the encryption key file.
        logger: Optional logger instance for error reporting.
    """

    def __init__(self, key_file_path: str, logger: Any | None = None) -> None:
        """Initialize encryption manager and load or generate the Fernet key.

        Args:
            key_file_path: Absolute path to encryption key file.
            logger: Optional logger instance for error reporting.

        Raises:
            EncryptionError: If encryption setup fails.
        """
        self.key_file = key_file_path
        self.logger = logger
        self._encryption_key: bytes | None = None
        self._cipher: Any | None = None

        self._setup_encryption()

    ############################################################################
    # PUBLIC INTERFACE - Encryption/Decryption Operations
    ############################################################################

    def encrypt(self, data: str) -> str:
        """Encrypt a plain-text string using Fernet symmetric encryption.

        Args:
            data: Plain text string to encrypt (must not be empty).

        Returns:
            Base64-encoded encrypted string.

        Raises:
            EncryptionError: If encryption fails or cipher is uninitialized.
            ValidationError: If ``data`` is empty.
        """
        if not self._cipher:
            raise EncryptionError("Encryption not initialized")
        if not data:
            raise ValidationError("Cannot encrypt empty data")
        try:
            return self._cipher.encrypt(data.encode()).decode()
        except Exception as exc:
            if self.logger:
                self.logger.error(f"Encryption failed: {exc}")
            raise EncryptionError(f"Encryption failed: {exc}") from exc

    def decrypt(self, encrypted_data: str) -> str:
        """Decrypt Fernet-encrypted data back to plain text.

        Args:
            encrypted_data: Base64-encoded encrypted string.

        Returns:
            Decrypted plain text string.

        Raises:
            EncryptionError: If decryption fails or cipher is uninitialized.
            ValidationError: If ``encrypted_data`` is empty.
        """
        if not self._cipher:
            raise EncryptionError("Encryption not initialized")
        if not encrypted_data:
            raise ValidationError("Cannot decrypt empty data")
        try:
            return self._cipher.decrypt(encrypted_data.encode()).decode()
        except Exception as exc:
            if self.logger:
                self.logger.error(f"Decryption failed: {exc}")
            raise EncryptionError(f"Decryption failed: {exc}") from exc

    def rotate_key(self, new_key_file_path: str) -> None:
        """Rotate the encryption key (not yet implemented).

        Args:
            new_key_file_path: Path for the new encryption key file.

        Raises:
            NotImplementedError: Always raised as key rotation is not implemented.
        """
        del new_key_file_path
        raise NotImplementedError("Key rotation not yet implemented")

    ############################################################################
    # PRIVATE METHODS - Internal Implementation
    ############################################################################

    def _setup_encryption(self) -> None:
        """Load or generate the Fernet key and initialize the cipher instance.

        Raises:
            EncryptionError: If key loading, validation, or generation fails.
        """
        if Fernet is None:
            raise EncryptionError("cryptography package is required for EncryptionManager")
        try:
            self._encryption_key = self._load_or_generate_key()
            expected_len = EncryptionDefaults.FERNET_KEY_LENGTH
            if len(self._encryption_key) != expected_len:
                raise ValidationError(
                    f"Invalid encryption key length: {len(self._encryption_key)} (expected {expected_len})"
                )
            self._cipher = Fernet(self._encryption_key)
        except Exception as exc:
            if self.logger:
                self.logger.error(f"Encryption setup failed: {exc}")
            raise EncryptionError(f"Failed to setup encryption: {exc}") from exc

    def _load_or_generate_key(self) -> bytes:
        """Load existing Fernet key from disk or generate and persist a new one.

        Returns:
            Raw Fernet key bytes.

        Raises:
            OSError: If the key path is a symbolic link or file I/O fails.
        """
        key_mode = EncryptionDefaults.KEY_FILE_MODE
        if os.path.islink(self.key_file):
            raise OSError(f"Refusing to use symlinked encryption key file: {self.key_file}")
        if os.path.exists(self.key_file):
            return self._read_existing_key(key_mode)
        return self._generate_and_save_key(key_mode)

    def _read_existing_key(self, key_mode: int) -> bytes:
        """Read an existing encryption key file safely without following symlinks.

        Args:
            key_mode: Target octal file mode to enforce.

        Returns:
            Raw Fernet key bytes.
        """
        fd = os.open(self.key_file, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(fd, "rb") as handle:
            key = handle.read()
        if self.logger:
            self.logger.debug(f"Encryption key loaded from {self.key_file}")
        ensure_service_ownership(
            self.key_file, mode=key_mode, logger=self.logger, private_group=True
        )
        return key

    def _generate_and_save_key(self, key_mode: int) -> bytes:
        """Generate a fresh Fernet key and persist it atomically with ``0600`` mode.

        Args:
            key_mode: Target octal file mode to enforce.

        Returns:
            Newly generated Fernet key bytes.
        """
        key = Fernet.generate_key()
        parent_dir = os.path.dirname(self.key_file)
        if parent_dir:
            os.makedirs(parent_dir, exist_ok=True)
        flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW
        fd = os.open(self.key_file, flags, key_mode)
        with os.fdopen(fd, "wb") as handle:
            os.fchmod(handle.fileno(), key_mode)
            handle.write(key)
        ensure_service_ownership(
            self.key_file, mode=key_mode, logger=self.logger, private_group=True
        )
        if self.logger:
            self.logger.info(f"Encryption key generated and saved to {self.key_file}")
            self.logger.warning(
                "IMPORTANT: Backup encryption key - data cannot be decrypted without it"
            )
        return key
