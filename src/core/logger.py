#!/usr/bin/env python3
"""Pure-Python logging factory with ANSI stderr formatting and journald integration.

Provides thread-safe logger management with TTY-aware ANSI console formatting on
``stderr``, native systemd journald datagram logging via ``src.core.journal``,
automatic URI secret redaction, and bounded in-memory ring buffers.

Author: Manuel Ziel
License: MIT
"""

################################################################################
# IMPORTS & DEPENDENCIES
################################################################################

from collections import deque
import logging
import os
import sys
import threading
from typing import Any

from ..utils.colors import LOG_COLORS, LOG_SYMBOLS
from .constants import AppSettings, LoggingDefaults
from .exceptions import ConfigError
from .journal import JournaldSocketHandler, RingBufferHandler
from .security import sanitize_log_uri

__syslog_identifier__ = (
    os.environ.get("SYSLOG_IDENTIFIER") or AppSettings.SYSLOG_IDENTIFIER
)

################################################################################
# FORMATTER CLASSES - Plain & ANSI Color Formatting
################################################################################


class PlainFormatter(logging.Formatter):
    """Plain text formatter without ANSI escape codes for journald and non-TTY streams."""

    def __init__(self) -> None:
        """Initialize plain formatter with message-only format."""
        super().__init__("%(message)s")

    def format(self, record: logging.LogRecord) -> str:
        """Format and URI-sanitize log record as plain text.

        Args:
            record: Log record to format.

        Returns:
            Sanitized plain-text log message.
        """
        return sanitize_log_uri(super().format(record))


class ColoredFormatter(logging.Formatter):
    """Formatter with ANSI colors and Unicode symbols for terminal output."""

    COLORS = LOG_COLORS
    SYMBOLS = LOG_SYMBOLS

    def __init__(self, include_timestamp: bool = False) -> None:
        """Initialize colored formatter with optional HH:MM:SS timestamp.

        Args:
            include_timestamp: Prepend ``HH:MM:SS`` timestamp when True.
        """
        self.include_timestamp = include_timestamp
        fmt = "%(asctime)s - %(message)s" if include_timestamp else "%(message)s"
        super().__init__(fmt, datefmt="%H:%M:%S")

    def format(self, record: logging.LogRecord) -> str:
        """Format log record with ANSI colors without mutating shared record state.

        Args:
            record: Log record to format.

        Returns:
            Formatted message string with ANSI color codes.
        """
        color = self.COLORS.get(record.levelname, "")
        symbol = self.SYMBOLS.get(record.levelname, "")
        reset = self.COLORS["RESET"]
        original_msg, original_args = record.msg, record.args
        rendered = sanitize_log_uri(record.getMessage())

        record.msg = (
            f"{color}{symbol} {rendered}{reset}"
            if symbol
            else f"{color}{rendered}{reset}"
        )
        record.args = None
        try:
            return super().format(record)
        finally:
            record.msg, record.args = original_msg, original_args


################################################################################
# LOGGER MANAGER - Thread-Safe Logger Factory
################################################################################


class LoggerManager:
    """Thread-safe logger factory with console, native journald, and ring handlers."""

    _loggers: dict[str, logging.Logger] = {}
    _lock = threading.Lock()
    _recent_records: deque[dict[str, str]] = deque(
        maxlen=LoggingDefaults.MAX_LOG_LIMIT
    )
    _recent_error_records: deque[dict[str, str]] = deque(
        maxlen=LoggingDefaults.MAX_LOG_LIMIT
    )

    ############################################################################
    # PUBLIC CLASS METHODS - Logger Factory & Ring Buffer Access
    ############################################################################

    @classmethod
    def get_recent_logs(
        cls, limit: int = LoggingDefaults.DEFAULT_LOG_LIMIT
    ) -> list[dict[str, str]]:
        """Return recent in-memory log entries.

        Args:
            limit: Maximum number of log entries to return.

        Returns:
            Chronological list of recent log dictionaries.
        """
        safe_limit = max(1, min(int(limit), LoggingDefaults.MAX_LOG_LIMIT))
        with cls._lock:
            items = list(cls._recent_records)
        return items[-safe_limit:]

    @classmethod
    def get_recent_error_logs(
        cls, limit: int = LoggingDefaults.DEFAULT_LOG_LIMIT
    ) -> list[dict[str, str]]:
        """Return recent in-memory WARNING/ERROR/CRITICAL log entries.

        Args:
            limit: Maximum number of warning/error log entries to return.

        Returns:
            Chronological list of recent warning/error log dictionaries.
        """
        safe_limit = max(1, min(int(limit), LoggingDefaults.MAX_LOG_LIMIT))
        with cls._lock:
            items = list(cls._recent_error_records)
        return items[-safe_limit:]

    @classmethod
    def get_logger(cls, name: str, **kwargs: Any) -> logging.Logger:
        """Get or create a cached logger instance in a thread-safe manner.

        Args:
            name: Logger name, typically the application or module name.
            **kwargs: Optional configuration (``level``, ``daemon_mode``, ``console_colors``).

        Returns:
            Configured ``logging.Logger`` instance.
        """
        with cls._lock:
            if name not in cls._loggers:
                cls._loggers[name] = cls._create_logger(name, **kwargs)
            else:
                if kwargs.get("level") is not None:
                    cls.set_level(cls._loggers[name], kwargs["level"])
                if kwargs.get("console_colors") is not None:
                    cls.set_console_colors(
                        cls._loggers[name], bool(kwargs["console_colors"])
                    )
            return cls._loggers[name]

    @classmethod
    def set_level(cls, logger: logging.Logger, level: int | str) -> None:
        """Update the log level of a logger and all its attached handlers.

        Args:
            logger: Logger instance to update.
            level: Numeric logging level or level name string.
        """
        numeric_level = (
            getattr(logging, level.upper(), logging.INFO)
            if isinstance(level, str)
            else int(level)
        )
        logger.setLevel(numeric_level)
        for handler in logger.handlers:
            handler.setLevel(numeric_level)

    @staticmethod
    def _should_use_ansi(stream: Any, requested: bool) -> bool:
        """Check whether ANSI colors are allowed on ``stream`` (TTY, NO_COLOR, daemon).

        Args:
            stream: Target output stream.
            requested: Whether console colors were requested in configuration.

        Returns:
            True if ANSI escape sequences should be emitted.
        """
        if (
            not requested
            or os.environ.get("NO_COLOR")
            or os.environ.get("TERM") == "dumb"
        ):
            return False
        if (
            os.environ.get("DAEMON_MODE") == "1"
            or os.environ.get("INVOCATION_ID")
            or os.environ.get("JOURNAL_STREAM")
        ):
            return False
        isatty_fn = getattr(stream, "isatty", None)
        return bool(callable(isatty_fn) and isatty_fn())

    @classmethod
    def set_console_colors(cls, logger: logging.Logger, console_colors: bool) -> None:
        """Update console handler formatter based on ``console_colors`` and TTY state.

        Args:
            logger: Logger instance to update.
            console_colors: Whether ANSI colors are enabled in configuration.
        """
        for handler in logger.handlers:
            if type(handler) is logging.StreamHandler:
                use_ansi = cls._should_use_ansi(handler.stream, console_colors)
                handler.setFormatter(
                    ColoredFormatter(include_timestamp=False)
                    if use_ansi
                    else PlainFormatter()
                )

    ############################################################################
    # PRIVATE CLASS METHODS - Logger Configuration
    ############################################################################

    @classmethod
    def _create_logger(cls, name: str, **kwargs: Any) -> logging.Logger:
        """Create and configure a new logger instance with console/journal/ring handlers.

        Args:
            name: Logger name.
            **kwargs: Optional configuration overrides.

        Returns:
            Configured ``logging.Logger`` instance.
        """
        running_under_systemd = bool(
            os.environ.get("INVOCATION_ID")
            or os.environ.get("JOURNAL_STREAM")
            or os.environ.get("DAEMON_MODE") == "1"
        )
        daemon_mode = bool(kwargs.get("daemon_mode", running_under_systemd))
        console_colors = bool(
            kwargs.get("console_colors", LoggingDefaults.CONSOLE_COLORS)
        )
        log_level = cls._resolve_log_level(kwargs.get("level"))

        logger = logging.getLogger(name)
        logger.setLevel(log_level)
        logger.propagate = False
        for handler in logger.handlers[:]:
            handler.close()
            logger.removeHandler(handler)

        journal_attached = cls._setup_journal_handler(logger, name, log_level)
        if not daemon_mode:
            cls._setup_console_handler(
                logger, log_level, console_colors=console_colors
            )
        elif not journal_attached:
            cls._setup_console_handler(logger, log_level, console_colors=False)

        ring_handler = RingBufferHandler(
            cls._recent_records, cls._recent_error_records, cls._lock
        )
        ring_handler.setLevel(log_level)
        logger.addHandler(ring_handler)
        cls._setup_live_logging()
        return logger

    @classmethod
    def _resolve_log_level(cls, level: Any) -> int:
        """Resolve numeric logging level from explicit argument or environment.

        Args:
            level: Optional explicit level (int or level name string).

        Returns:
            Numeric logging level constant.
        """
        if level is not None:
            if isinstance(level, str):
                return getattr(logging, level.upper(), logging.INFO)
            return int(level)
        if os.environ.get("DEBUG", "0") == "1":
            return logging.DEBUG
        if os.environ.get("VERBOSE", "0") == "1":
            return logging.INFO
        return logging.WARNING

    @classmethod
    def _setup_console_handler(
        cls,
        logger: logging.Logger,
        level: int,
        console_colors: bool = LoggingDefaults.CONSOLE_COLORS,
    ) -> None:
        """Attach stderr console ``StreamHandler`` with TTY-aware ANSI color formatting.

        Args:
            logger: Logger instance to configure.
            level: Minimum log level for the handler.
            console_colors: Whether ANSI colors are requested.
        """
        console_handler = logging.StreamHandler(sys.stderr)
        console_handler.setLevel(level)
        use_ansi = cls._should_use_ansi(sys.stderr, console_colors)
        formatter = (
            ColoredFormatter(include_timestamp=False) if use_ansi else PlainFormatter()
        )
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    @classmethod
    def _setup_journal_handler(
        cls, logger: logging.Logger, name: str, level: int
    ) -> bool:
        """Attach pure-Python ``JournaldSocketHandler`` when journald socket exists.

        Args:
            logger: Logger instance to configure.
            name: Logger name (kept for signature compatibility).
            level: Minimum log level for the handler.

        Returns:
            True if the journald handler was attached, False when unavailable.

        Raises:
            ConfigError: If socket initialization fails unexpectedly.
        """
        del name
        socket_path = LoggingDefaults.JOURNAL_SOCKET_PATH
        if not os.path.exists(socket_path):
            return False
        try:
            journal_handler = JournaldSocketHandler(
                syslog_identifier=__syslog_identifier__,
                socket_path=socket_path,
            )
            journal_handler.setLevel(level)
            journal_handler.setFormatter(PlainFormatter())
            logger.addHandler(journal_handler)
            return True
        except OSError:
            return False
        except Exception as exc:
            raise ConfigError(f"Failed to setup journal logging: {exc}") from exc

    @classmethod
    def _setup_live_logging(cls) -> None:
        """Configure line buffering on standard streams for real-time log visibility."""
        for stream in (sys.stdout, sys.stderr):
            reconfigure = getattr(stream, "reconfigure", None)
            if callable(reconfigure):
                try:
                    reconfigure(line_buffering=True)
                except Exception:
                    pass


################################################################################
# CUSTOM LOG LEVELS - Extended Logging Functionality
################################################################################

logging.addLevelName(LoggingDefaults.SUCCESS_LEVEL, "SUCCESS")


def success(self: logging.Logger, message: object, *args: Any, **kwargs: Any) -> None:
    """Log a success message at custom SUCCESS level (25).

    Args:
        message: Message to log.
        *args: Positional arguments for message formatting.
        **kwargs: Keyword arguments forwarded to ``_log()``.
    """
    if self.isEnabledFor(LoggingDefaults.SUCCESS_LEVEL):
        self._log(LoggingDefaults.SUCCESS_LEVEL, message, args, **kwargs)


logging.Logger.success = success  # type: ignore[attr-defined]
