#!/usr/bin/env python3
"""
Advanced Logger Module

Enhanced logging system with bash integration, live logging support,
consistent color formatting, and systemd journal integration.

Created: 2025-10-27
Author: Manuel Ziel
License: MIT

This program is free software: you can redistribute it and/or modify
"""

################################################################################
# IMPORTS & DEPENDENCIES
################################################################################

import os
import sys
import logging
import threading
from typing import Optional, Dict, Any
from colors import Colors, LOG_COLORS, LOG_SYMBOLS

# Import syslog identifier for consistent logging (from environment or package metadata)
try:
    __syslog_identifier__ = os.environ.get('SYSLOG_IDENTIFIER')
    if not __syslog_identifier__:
        from src import __syslog_identifier__
except ImportError:
    print("Warning: SYSLOG_IDENTIFIER not found in environment or package metadata.")

################################################################################
# FORMATTER CLASSES - ANSI Color Formatting
################################################################################

class ColoredFormatter(logging.Formatter):
    """Custom formatter with ANSI colors compatible with bash colors.sh."""
    
    COLORS = LOG_COLORS
    SYMBOLS = LOG_SYMBOLS
    
    def __init__(self, include_timestamp: bool = False) -> None:
        """Initialize formatter with optional timestamp."""
        self.include_timestamp = include_timestamp
        format_string = '%(asctime)s - %(message)s' if include_timestamp else '%(message)s'
        super().__init__(format_string, datefmt='%H:%M:%S')
    
    def format(self, record: logging.LogRecord) -> str:
        """Format log record with colors and symbols."""
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
    """Logger manager with bash environment integration and systemd journal support."""
    
    _loggers: Dict[str, logging.Logger] = {}
    _lock = threading.Lock()

    ################################################################################
    # PUBLIC CLASS METHODS - Logger Factory
    ################################################################################

    @classmethod
    def get_logger(cls, name: str, **kwargs) -> logging.Logger:
        """Get or create logger instance (thread-safe). Use daemon_mode=True to skip console output."""
        with cls._lock:
            if name not in cls._loggers:
                cls._loggers[name] = cls._create_logger(name, **kwargs)
            return cls._loggers[name]

    ################################################################################
    # PRIVATE CLASS METHODS - Logger Configuration
    ################################################################################

    @classmethod
    def _create_logger(cls, name: str, **kwargs) -> logging.Logger:
        """Create and configure new logger instance. Respects daemon_mode, level from config or DEBUG/VERBOSE env vars."""
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
        """Setup console handler with ANSI colors."""
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(level)
        console_formatter = ColoredFormatter(include_timestamp=False)
        console_handler.setFormatter(console_formatter)
        logger.addHandler(console_handler)
    
    @classmethod
    def _setup_journal_handler(cls, logger: logging.Logger, name: str, level: int) -> None:
        """Setup systemd journal handler if available. Uses SYSLOG_IDENTIFIER from environment."""
        try:
            from systemd import journal
            journal_handler = journal.JournalHandler(SYSLOG_IDENTIFIER=__syslog_identifier__)
            journal_handler.setLevel(level)
            
            journal_formatter = logging.Formatter('%(levelname)s: %(message)s')
            journal_handler.setFormatter(journal_formatter)
            logger.addHandler(journal_handler)
            
        except ImportError:
            pass
        except Exception as e:
            print(f"Warning: Could not setup journal logging: {e}", file=sys.stderr)
    
    @classmethod
    def _setup_live_logging(cls) -> None:
        """Configure live logging with line buffering for real-time output."""
        try:
            sys.stdout.reconfigure(line_buffering=True)
            sys.stderr.reconfigure(line_buffering=True)
        except Exception:
            sys.stdout = os.fdopen(sys.stdout.fileno(), 'w', 1)
            sys.stderr = os.fdopen(sys.stderr.fileno(), 'w', 1)


# Add SUCCESS log level
SUCCESS_LEVEL = 25  # Between INFO (20) and WARNING (30)
logging.addLevelName(SUCCESS_LEVEL, 'SUCCESS')

def success(self, message: str, *args: Any, **kwargs: Any) -> None:
    """Log a success message."""
    if self.isEnabledFor(SUCCESS_LEVEL):
        self._log(SUCCESS_LEVEL, message, args, **kwargs)

# Add success method to Logger class
logging.Logger.success = success