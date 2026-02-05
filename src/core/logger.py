#!/usr/bin/env python3
"""Advanced logging system with systemd journal integration.

This module provides a sophisticated logging system that integrates with
both console output (with ANSI colors) and systemd journal for persistent
logging in daemon mode.

Features:
    - Thread-safe logger factory with caching.
    - ANSI color-coded console output.
    - Systemd journal integration for daemon mode.
    - Custom SUCCESS log level.
    - Bash environment variable integration (DEBUG, VERBOSE).

Typical usage:
    >>> from src.core.logger import LoggerManager
    >>> logger = LoggerManager.get_logger('myapp', level='DEBUG')
    >>> logger.info('Application started')
    >>> logger.success('Operation completed')  # Custom level

Author: Manuel Ziel
License: MIT
"""

################################################################################
# IMPORTS & DEPENDENCIES
################################################################################

import os
import sys
import logging
import threading
from typing import Dict, Any
from systemd import journal

# Local imports
from ..utils.colors import LOG_COLORS, LOG_SYMBOLS
from .exceptions import ConfigError

# Import syslog identifier for consistent logging
try:
    __syslog_identifier__ = os.environ.get('SYSLOG_IDENTIFIER')
    if not __syslog_identifier__:
        from src import __syslog_identifier__
except ImportError:
    sys.stderr.write("Warning: SYSLOG_IDENTIFIER not found in environment or package metadata.\n")

################################################################################
# FORMATTER CLASSES - ANSI Color Formatting
################################################################################

class PlainFormatter(logging.Formatter):
    """Plain text formatter without colors for systemd journal.

    Systemd journal adds its own metadata (timestamp, priority), so this
    formatter outputs only the message text without ANSI escape codes.
    """

    def __init__(self) -> None:
        """Initialize plain formatter with message-only format."""
        super().__init__('%(message)s')

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as plain text.

        Args:
            record: Log record to format.

        Returns:
            Plain message string without formatting.
        """
        return record.getMessage()


class ColoredFormatter(logging.Formatter):
    """Formatter with ANSI colors and symbols for console output.

    Compatible with bash colors.sh for consistent terminal appearance.
    Adds level-specific colors and symbols (✓, ✗, ℹ) to log messages.

    Attributes:
        COLORS: Mapping of log levels to ANSI color codes.
        SYMBOLS: Mapping of log levels to Unicode symbols.
    """

    COLORS = LOG_COLORS
    SYMBOLS = LOG_SYMBOLS

    def __init__(self, include_timestamp: bool = False) -> None:
        """Initialize colored formatter.

        Args:
            include_timestamp: If True, prepend timestamp to messages.
                Defaults to False.
        """
        self.include_timestamp = include_timestamp
        format_string = '%(asctime)s - %(message)s' if include_timestamp else '%(message)s'
        super().__init__(format_string, datefmt='%H:%M:%S')

    def format(self, record: logging.LogRecord) -> str:
        """Format log record with colors and symbols.

        Args:
            record: Log record to format.

        Returns:
            Formatted message string with ANSI color codes.
        """
        level_name = record.levelname
        color = self.COLORS.get(level_name, '')
        symbol = self.SYMBOLS.get(level_name, '')
        reset = self.COLORS['RESET']
        
        original_msg = record.getMessage()
        
        if symbol:
            formatted_msg = f"{color}{symbol} {original_msg}{reset}"
        else:
            formatted_msg = f"{color}{original_msg}{reset}"
        
        record.msg = formatted_msg
        record.args = None
        
        return super().format(record)


class LoggerManager:
    """Thread-safe logger factory with bash environment integration.

    Provides centralized logger management with support for console and
    systemd journal handlers. Loggers are cached and reused.

    Class Attributes:
        _loggers: Cache of created logger instances.
        _lock: Thread lock for safe logger creation.
    """

    _loggers: Dict[str, logging.Logger] = {}
    _lock = threading.Lock()

    ################################################################################
    # PUBLIC CLASS METHODS - Logger Factory
    ################################################################################

    @classmethod
    def get_logger(cls, name: str, **kwargs) -> logging.Logger:
        """Get or create a logger instance.

        Thread-safe factory method that returns cached loggers or creates
        new ones with the specified configuration.

        Args:
            name: Logger name, typically the application or module name.
            **kwargs: Configuration options:
                level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
                daemon_mode: If True, only use journal handler (no console).

        Returns:
            Configured logging.Logger instance.

        Typical usage:
            >>> logger = LoggerManager.get_logger('myapp', level='DEBUG')
            >>> logger.info('Application started')
        """
        with cls._lock:
            if name not in cls._loggers:
                cls._loggers[name] = cls._create_logger(name, **kwargs)
            return cls._loggers[name]

    ################################################################################
    # PRIVATE CLASS METHODS - Logger Configuration
    ################################################################################

    @classmethod
    def _create_logger(cls, name: str, **kwargs) -> logging.Logger:
        """Create and configure a new logger instance.

        Args:
            name: Logger name for identification.
            **kwargs: Configuration options (level, daemon_mode).

        Returns:
            Configured logging.Logger instance with handlers.
        """
        daemon_mode = kwargs.get('daemon_mode', False)
        log_level = kwargs.get('level', None)
        
        if log_level is None:
            debug_mode = os.getenv('DEBUG', '0') == '1'
            verbose_mode = os.getenv('VERBOSE', '0') == '1'
            
            if debug_mode:
                log_level = logging.DEBUG
            elif verbose_mode:
                log_level = logging.INFO
            else:
                log_level = logging.INFO
        
        logger = logging.getLogger(name)
        logger.setLevel(log_level)
        
        for handler in logger.handlers[:]:
            logger.removeHandler(handler)
        
        if not daemon_mode:
            cls._setup_console_handler(logger, log_level)
        
        cls._setup_journal_handler(logger, name, log_level)
        cls._setup_live_logging()
        
        return logger
    
    @classmethod
    def _setup_console_handler(cls, logger: logging.Logger, level: int) -> None:
        """Setup console handler with ANSI color formatting.

        Args:
            logger: Logger instance to configure.
            level: Minimum log level for the handler.
        """
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(level)
        console_formatter = ColoredFormatter(include_timestamp=False)
        console_handler.setFormatter(console_formatter)
        logger.addHandler(console_handler)
    
    @classmethod
    def _setup_journal_handler(cls, logger: logging.Logger, name: str, level: int) -> None:
        """Setup systemd journal handler if available.

        Uses SYSLOG_IDENTIFIER from environment for consistent journal entries.
        Falls back gracefully if systemd is not available.

        Args:
            logger: Logger instance to configure.
            name: Logger name (unused, kept for API compatibility).
            level: Minimum log level for the handler.

        Raises:
            ConfigError: If journal setup fails unexpectedly.
        """
        try:
            journal_handler = journal.JournalHandler(SYSLOG_IDENTIFIER=__syslog_identifier__)
            journal_handler.setLevel(level)

            journal_formatter = PlainFormatter()
            journal_handler.setFormatter(journal_formatter)
            logger.addHandler(journal_handler)

        except ImportError:
            # systemd journal not available, skip silently
            pass
        except Exception as e:
            raise ConfigError(f"Failed to setup journal logging: {e}")
    
    @classmethod
    def _setup_live_logging(cls) -> None:
        """Configure line buffering for real-time log output.

        Enables immediate log visibility by setting stdout/stderr to
        line-buffered mode. Essential for live log viewing with journalctl -f.
        """
        try:
            sys.stdout.reconfigure(line_buffering=True)
            sys.stderr.reconfigure(line_buffering=True)
        except Exception:
            sys.stdout = os.fdopen(sys.stdout.fileno(), 'w', 1)
            sys.stderr = os.fdopen(sys.stderr.fileno(), 'w', 1)

################################################################################
# CUSTOM LOG LEVELS - Extended Logging Functionality
################################################################################

# Add SUCCESS log level
SUCCESS_LEVEL = 25  # Between INFO (20) and WARNING (30)
logging.addLevelName(SUCCESS_LEVEL, 'SUCCESS')

def success(self, message: str, *args: Any, **kwargs: Any) -> None:
    """Log a success message at SUCCESS level (25).

    Custom log level between INFO (20) and WARNING (30) for indicating
    successful operations.

    Args:
        message: Message to log.
        *args: Additional positional arguments for string formatting.
        **kwargs: Additional keyword arguments passed to _log().
    """
    if self.isEnabledFor(SUCCESS_LEVEL):
        self._log(SUCCESS_LEVEL, message, args, **kwargs)

# Add success method to Logger class
logging.Logger.success = success