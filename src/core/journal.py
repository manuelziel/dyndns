#!/usr/bin/env python3
"""Native systemd journald socket and bounded ring-buffer logging handlers.

Implements the systemd Native Journal Protocol over ``AF_UNIX`` ``SOCK_DGRAM``
(``/run/systemd/journal/socket``) in pure Python without C extensions, alongside
thread-safe bounded in-memory log ring buffers.

Author: Manuel Ziel
License: MIT
"""

################################################################################
# IMPORTS & DEPENDENCIES
################################################################################

from collections import deque
from datetime import datetime, timezone
import logging
import socket
import struct
import threading

from .constants import LoggingDefaults
from .security import sanitize_log_uri

################################################################################
# NATIVE JOURNALD SOCKET & RING BUFFER HANDLERS
################################################################################


class JournaldSocketHandler(logging.Handler):
    """Pure-Python handler speaking the systemd Native Journal Protocol over AF_UNIX."""

    def __init__(
        self,
        syslog_identifier: str,
        socket_path: str = LoggingDefaults.JOURNAL_SOCKET_PATH,
    ) -> None:
        """Initialize Unix datagram socket for ``systemd-journald``.

        Args:
            syslog_identifier: Identifier stored in ``SYSLOG_IDENTIFIER``.
            socket_path: Filesystem path to the journald Unix datagram socket.
        """
        super().__init__()
        self._syslog_identifier = syslog_identifier
        self._socket_path = socket_path
        self._sock: socket.socket | None = socket.socket(
            socket.AF_UNIX, socket.SOCK_DGRAM
        )

    def emit(self, record: logging.LogRecord) -> None:
        """Serialize and send a structured log record to ``systemd-journald``.

        Args:
            record: Log record to emit.
        """
        if self._sock is None:
            return
        try:
            message = self._truncate_utf8(
                self.format(record), LoggingDefaults.MAX_JOURNAL_MESSAGE_BYTES
            )
            payload = self._encode_datagram(self._build_fields(record, message))
            self._sock.sendto(payload, self._socket_path)
        except OSError:
            pass
        except Exception:
            self.handleError(record)

    def close(self) -> None:
        """Close the underlying Unix datagram socket cleanly."""
        self.acquire()
        try:
            if self._sock is not None:
                try:
                    self._sock.close()
                except OSError:
                    pass
                self._sock = None
        finally:
            self.release()
            super().close()

    @staticmethod
    def _truncate_utf8(text: str, max_bytes: int) -> str:
        """Truncate UTF-8 string cleanly at character boundaries within ``max_bytes``.

        Args:
            text: UTF-8 string to bound.
            max_bytes: Maximum encoded byte length.

        Returns:
            Truncated UTF-8 string.
        """
        encoded = text.encode("utf-8", errors="replace")
        if len(encoded) <= max_bytes:
            return text
        return encoded[:max_bytes].decode("utf-8", errors="ignore")

    @staticmethod
    def _map_priority(levelno: int) -> str:
        """Map Python logging level number to RFC 5424 syslog priority code.

        Args:
            levelno: Numeric Python logging level.

        Returns:
            Syslog priority string (``'2'`` through ``'7'``).
        """
        if levelno >= logging.CRITICAL:
            return LoggingDefaults.SYSLOG_PRIORITY_CRITICAL
        if levelno >= logging.ERROR:
            return LoggingDefaults.SYSLOG_PRIORITY_ERROR
        if levelno >= logging.WARNING:
            return LoggingDefaults.SYSLOG_PRIORITY_WARNING
        if levelno >= LoggingDefaults.SUCCESS_LEVEL:
            return LoggingDefaults.SYSLOG_PRIORITY_NOTICE
        if levelno >= logging.INFO:
            return LoggingDefaults.SYSLOG_PRIORITY_INFO
        return LoggingDefaults.SYSLOG_PRIORITY_DEBUG

    def _build_fields(
        self, record: logging.LogRecord, message: str
    ) -> dict[str, str]:
        """Build structured journald key-value fields for a ``LogRecord``.

        Args:
            record: Source log record.
            message: Formatted and sanitized message string.

        Returns:
            Mapping of journald protocol keys to string values.
        """
        return {
            "MESSAGE": message,
            "PRIORITY": self._map_priority(record.levelno),
            "SYSLOG_IDENTIFIER": self._syslog_identifier,
            "LOGGER_NAME": str(record.name or ""),
            "CODE_FILE": str(record.pathname or ""),
            "CODE_LINE": str(record.lineno or 0),
            "CODE_FUNC": str(record.funcName or ""),
        }

    @staticmethod
    def _encode_field(key: str, value: str) -> bytes:
        """Encode one journald field according to the Native Journal Protocol.

        Args:
            key: Uppercase ASCII field name.
            value: UTF-8 field value.

        Returns:
            Serialized binary field bytes.
        """
        key_bytes = key.encode("ascii", errors="ignore")
        val_bytes = value.encode("utf-8", errors="replace")
        if b"\n" not in val_bytes:
            return key_bytes + b"=" + val_bytes + b"\n"
        return (
            key_bytes + b"\n" + struct.pack("<Q", len(val_bytes)) + val_bytes + b"\n"
        )

    @classmethod
    def _encode_datagram(cls, fields: dict[str, str]) -> bytes:
        """Encode all structured journal fields into a single datagram payload.

        Args:
            fields: Mapping of journal field names to values.

        Returns:
            Concatenated journald datagram payload.
        """
        return b"".join(cls._encode_field(key, val) for key, val in fields.items())


class RingBufferHandler(logging.Handler):
    """In-memory ring buffer handler storing recent sanitized records."""

    def __init__(
        self,
        buffer: deque[dict[str, str]],
        error_buffer: deque[dict[str, str]],
        lock: threading.Lock,
    ) -> None:
        """Initialize ring buffer handler with shared bounded deques and lock.

        Args:
            buffer: Bounded deque for all recent records.
            error_buffer: Bounded deque for warning/error records.
            lock: Shared synchronization lock.
        """
        super().__init__()
        self._buffer = buffer
        self._error_buffer = error_buffer
        self._lock = lock

    def emit(self, record: logging.LogRecord) -> None:
        """Append formatted and URI-sanitized log record into bounded ring buffers.

        Args:
            record: Log record to store.
        """
        try:
            ts = datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat()
            msg = sanitize_log_uri(record.getMessage())
            entry = {"timestamp": ts, "priority": record.levelname, "message": msg}
            with self._lock:
                self._buffer.append(entry)
                if record.levelno >= logging.WARNING:
                    self._error_buffer.append(entry)
        except Exception:
            pass
