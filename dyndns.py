#!/usr/bin/env python3
"""DynDNS - Main entry point for Dynamic DNS Client.

Handles command-line argument parsing, stateless TOML configuration validation,
interactive CLI dispatch, import/export operations, single-run execution, and
continuous systemd daemon startup.

Typical usage:
    $ ./dyndns.py                           # Single update run
    $ ./dyndns.py config                    # Open configuration menu
    $ ./dyndns.py validate                  # Validate config.toml
    $ ./dyndns.py import config.yaml        # Import configuration
    $ ./dyndns.py export --format json      # Export configuration

Author: Manuel Ziel
License: MIT
"""

################################################################################
# IMPORTS & DEPENDENCIES
################################################################################

import argparse
import logging
import os
import signal
import sys
from typing import Any

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

from src import __software_name__, __version__
from src.application import Application
from src.cli import ConfigExporter, ConfigImporter, ConfigMenu, run_validate_cli
from src.cli.constants import CLICommands
from src.core import AppPaths, ConfigManager, EnvKeys, ExportFormat, LoggerManager
from src.daemon import DaemonManager

logger: logging.Logger | None = None

################################################################################
# ARGUMENT PARSING
################################################################################


def _register_subcommands(parser: argparse.ArgumentParser) -> None:
    """Register CLI subcommands on ``parser``.

    Args:
        parser: Root ``ArgumentParser`` instance.
    """
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    subparsers.add_parser(
        CLICommands.CONFIG, help="Open interactive configuration menu"
    )
    parser_validate = subparsers.add_parser(
        CLICommands.VALIDATE, help="Validate TOML configuration syntax and schema"
    )
    parser_validate.add_argument(
        "--file",
        type=str,
        default=None,
        help="Path to TOML configuration file (default: active config.toml)",
    )
    _register_transfer_subcommands(subparsers)


def _register_transfer_subcommands(subparsers: Any) -> None:
    """Register ``import`` and ``export`` subcommands on ``subparsers``.

    Args:
        subparsers: ``argparse`` subparsers action object.
    """
    parser_import = subparsers.add_parser(
        CLICommands.IMPORT, help="Import configuration from YAML/JSON file"
    )
    parser_import.add_argument(
        "file", type=str, help="Path to configuration file (YAML or JSON)"
    )
    parser_import.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing configuration (default: merge)",
    )
    parser_export = subparsers.add_parser(
        CLICommands.EXPORT, help="Export current configuration to file"
    )
    parser_export.add_argument(
        "--output", type=str, default=None, help="Output file path (default: stdout)"
    )
    parser_export.add_argument(
        "--format",
        type=str,
        choices=[ExportFormat.YAML, ExportFormat.JSON],
        default=ExportFormat.YAML,
        help="Output format: yaml or json (default: yaml)",
    )


def parse_arguments() -> argparse.Namespace:
    """Parse command-line arguments and subcommands.

    Returns:
        Parsed command-line arguments namespace.
    """
    parser = argparse.ArgumentParser(
        description="DynDNS - Dynamic DNS Client for DNS Providers",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  %(prog)s                          # Start DynDNS (single run)\n"
            "  %(prog)s config                   # Interactive configuration\n"
            "  %(prog)s validate                 # Validate config.toml\n"
            "  %(prog)s import config.yaml       # Import configuration\n"
            "  %(prog)s export --output bkp.yaml # Export configuration\n"
        ),
    )
    parser.add_argument(
        "-v", "--version", action="version", version=f"%(prog)s {__version__}"
    )
    _register_subcommands(parser)
    return parser.parse_args()


################################################################################
# CLI COMMAND & SIGNAL HANDLERS
################################################################################


def handle_cli_command(
    args: argparse.Namespace, config: ConfigManager, app_logger: logging.Logger
) -> int:
    """Dispatch stateful CLI subcommands (``config``, ``import``, ``export``).

    Args:
        args: Parsed command-line arguments.
        config: Initialized ``ConfigManager`` instance.
        app_logger: Application logger instance.

    Returns:
        Process exit code (``0`` on success, ``1`` on failure).
    """
    try:
        if args.command == CLICommands.CONFIG:
            app_logger.debug("Starting interactive configuration menu...")
            ConfigMenu(config, app_logger).run()
            return 0
        if args.command == CLICommands.IMPORT:
            rc = ConfigImporter(config, app_logger).import_from_file(
                args.file, overwrite=args.overwrite
            )
            app_logger.info(
                "Configuration imported successfully"
            ) if rc == 0 else app_logger.error("Configuration import failed")
            return 0 if rc == 0 else 1
        if args.command == CLICommands.EXPORT:
            rc = ConfigExporter(config, app_logger).export_to_file(
                output_file=args.output, format_type=args.format
            )
            app_logger.info(
                "Configuration exported successfully"
            ) if rc == 0 else app_logger.error("Configuration export failed")
            return 0 if rc == 0 else 1
    except Exception as exc:
        app_logger.error(f"Unexpected error: CLI command '{args.command}' failed: {exc}")
        return 1
    return 0


def shutdown_handler(signum: int, _frame: Any) -> None:
    """Handle ``SIGTERM`` and ``SIGINT`` during non-daemon single-run execution.

    Args:
        signum: Received POSIX signal number.
        _frame: Interrupted stack frame (unused).
    """
    sys.exit(128 + signum)


################################################################################
# RUNTIME EXECUTION
################################################################################


def _is_daemon_mode() -> bool:
    """Return True when ``DAEMON_MODE`` environment variable enables daemon mode.

    Returns:
        True if running as a background daemon, False otherwise.
    """
    return os.environ.get(EnvKeys.DAEMON_MODE, "0").strip().lower() in (
        "1",
        "true",
        "yes",
    )


def _run_service_or_single_cycle(
    config: ConfigManager, app_logger: logging.Logger, daemon_mode: bool
) -> int:
    """Start continuous daemon monitoring or execute a single update cycle.

    Args:
        config: Initialized ``ConfigManager`` instance.
        app_logger: Application logger instance.
        daemon_mode: True for daemon loop, False for one-shot cycle.

    Returns:
        Process exit code (``0`` on success, ``1`` on failure).
    """
    app_logger.debug("Initializing application services...")
    app = Application(config, app_logger)
    if daemon_mode:
        daemon = DaemonManager(app, config, app_logger)
        daemon.run_forever()
        return 0

    app_logger.debug("Starting single-run mode...")
    try:
        if app.run_cycle():
            app_logger.info("Single update completed successfully")
            return 0
        app_logger.warning("Single update completed with warnings")
        return 1
    except Exception as exc:
        app_logger.error(f"Unexpected error: Single update failed: {exc}")
        return 1
    finally:
        app.cleanup()


def main() -> int:
    """Initialize logging/configuration and dispatch the requested execution mode.

    Returns:
        Process exit code (``0`` for success, non-zero on error).
    """
    global logger

    signal.signal(signal.SIGINT, shutdown_handler)
    signal.signal(signal.SIGTERM, shutdown_handler)

    args = parse_arguments()
    current_dir = os.path.dirname(os.path.abspath(__file__))
    default_cfg = os.environ.get(
        EnvKeys.CONFIG_FILE, os.path.join(current_dir, AppPaths.CONFIG_FILE)
    )
    if args.command == CLICommands.VALIDATE:
        return run_validate_cli(args.file or default_cfg)

    daemon_mode = _is_daemon_mode()
    logger = LoggerManager.get_logger(
        __software_name__, level=logging.INFO, daemon_mode=daemon_mode
    )
    config = ConfigManager(current_dir, default_cfg, logger=logger)
    LoggerManager.set_level(logger, config.log_level)
    LoggerManager.set_console_colors(logger, config.console_colors)

    if args.command:
        try:
            return handle_cli_command(args, config, logger)
        finally:
            if getattr(config, "db", None):
                config.db.close()

    run_mode = "daemon" if daemon_mode else "once"
    logger.info(
        f"{__software_name__} v{__version__} starting "
        f"(mode: {run_mode}, log_level: {config.log_level})"
    )
    return _run_service_or_single_cycle(config, logger, daemon_mode)


################################################################################
# ENTRY POINT
################################################################################

if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        if logger is not None:
            logger.warning("Application interrupted by user")
        else:
            print("Application interrupted by user", file=sys.stderr)
        sys.exit(130)
    except Exception as exc:
        if logger is not None:
            logger.error(f"Unexpected error: {exc}", exc_info=True)
        else:
            print(f"Unexpected error: {exc}", file=sys.stderr)
        sys.exit(1)
