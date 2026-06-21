#!/usr/bin/env python3
"""DynDNS - Main entry point for Dynamic DNS Client.

This is the main entry point for the DynDNS application. It handles
argument parsing, configuration loading, and dispatches to appropriate
command handlers or starts the daemon.

Typical usage:
    $ ./dyndns.py                    # Single update run
    $ ./dyndns.py config             # Open configuration menu
    $ ./dyndns.py import config.yaml # Import configuration
    $ ./dyndns.py export --format json

Note:
    Use bash wrapper (dyndns) for daemon mode:
    $ dyndns start --daemon

Author: Manuel Ziel
License: MIT
"""

################################################################################
# IMPORTS
################################################################################

# Standard Imports
import sys
import os
import argparse
import logging
import signal
from typing import Optional, Any

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'src'))

# Local Imports
from src import __version__, __author__, __software_name__
from src.core import ConfigManager, LoggerManager, AppPaths, ExportFormat
from src.daemon import DaemonManager
from src.application import Application
from src.cli import ConfigMenu, ConfigImporter, ConfigExporter
from src.cli.constants import CLICommands

################################################################################
# ARGUMENT PARSING
################################################################################

def parse_arguments() -> argparse.Namespace:
    """Parse command-line arguments.

    Supports multiple subcommands:
        config: Interactive CLI configuration menu.
        import: Import configuration from YAML/JSON file.
        export: Export current configuration to file.
        (no command): Start application (default single run).

    Returns:
        Parsed command-line arguments namespace.
    """
    parser = argparse.ArgumentParser(
        description='Provider DynDNS - Dynamic DNS Client for DNS Providers',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                          # Start DynDNS (single run)
  %(prog)s config                   # Interactive configuration
  %(prog)s import config.yaml       # Import configuration
  %(prog)s export --output backup.yaml  # Export configuration

Note: Use bash wrapper (dyndns) for daemon mode:
  dyndns start --daemon       # Continuous monitoring via systemd
        """
    )
    
    parser.add_argument('-v', '--version', action='version', version=f'%(prog)s {__version__}')
    
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    subparsers.add_parser('config', help='Open interactive configuration menu')
    
    parser_import = subparsers.add_parser('import', help='Import configuration from YAML/JSON file')
    parser_import.add_argument('file', type=str, help='Path to configuration file (YAML or JSON)')
    parser_import.add_argument('--overwrite', action='store_true', help='Overwrite existing configuration (default: merge)')
    
    parser_export = subparsers.add_parser('export', help='Export current configuration to file')
    parser_export.add_argument('--output', type=str, default=None, help='Output file path (default: stdout)')
    parser_export.add_argument('--format', type=str, choices=[ExportFormat.YAML, ExportFormat.JSON], default=ExportFormat.YAML, help='Output format: yaml or json (default: yaml)')
    
    return parser.parse_args()


################################################################################
# CLI COMMAND HANDLERS
################################################################################

def handle_cli_command(args: argparse.Namespace, config: ConfigManager, logger: logging.Logger) -> int:
    """Handle CLI subcommands (config, import, export).

    Args:
        args: Parsed command-line arguments.
        config: Configuration manager instance.
        logger: Logger instance.

    Returns:
        Exit code (0 for success, 1 for error).
    """
    if args.command == CLICommands.CONFIG:
        logger.debug("Starting interactive configuration menu...")
        try:
            menu = ConfigMenu(config, logger)
            menu.run()
            return 0
        except Exception as e:
            logger.error(f"Unexpected error: Configuration menu failed: {e}")
            return 1
        
    elif args.command == CLICommands.IMPORT:
        try:
            importer = ConfigImporter(config, logger)
            result = importer.import_from_file(args.file, overwrite=args.overwrite)
            if result == 0:
                logger.info("Configuration imported successfully")
                return 0
            else:
                logger.error("Configuration import failed")
                return 1
        except Exception as e:
            logger.error(f"Unexpected error: Import failed: {e}")
            return 1
            
    elif args.command == CLICommands.EXPORT:
        try:
            exporter = ConfigExporter(config, logger)
            exporter.export_to_file(output_file=args.output, format=args.format)
            logger.info("Configuration exported successfully")
            return 0
        except Exception as e:
            logger.error(f"Unexpected error: Export failed: {e}")
            return 1
    
    return 0


################################################################################
# SIGNAL HANDLING
################################################################################

def shutdown_handler(signum: int, frame: Any) -> None:
    """Signal handler for graceful shutdown.

    Handles SIGTERM and SIGINT signals for graceful application shutdown.
    This is a fallback for direct Python execution without daemon mode.

    Args:
        signum: Signal number received.
        frame: Current stack frame.

    Note:
        DaemonManager in src/daemon.py handles signals in daemon mode.
    """
    try:
        logger = logging.getLogger(__software_name__)
        if logger.hasHandlers():
            logger.info(f"Received signal {signum}, shutting down gracefully...")
    except Exception:
        pass
    
    sys.exit(0)


################################################################################
# MAIN APPLICATION
################################################################################

def main() -> int:
    """Main application entry point.

    Initializes configuration, logging, and dispatches to command handlers
    or starts the DynDNS application in single-run or daemon mode.

    Returns:
        Exit code (0 for success, non-zero for errors).

    Note:
        Daemon mode is controlled by DAEMON_MODE environment variable,
        which is set by the bash wrapper (dyndns.sh).
    """
    version = __version__
    software_name = __software_name__

    args = parse_arguments()

    current_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.environ.get("CONFIG_FILE", os.path.join(current_dir, AppPaths.CONFIG_FILE))
    config = ConfigManager(current_dir, config_path)
    
    log_level = getattr(logging, config.log_level, logging.INFO)
    
    # Check environment variable for daemon mode (set by bash wrapper)
    daemon_mode = os.environ.get('DAEMON_MODE', '0') == '1'
    logger = LoggerManager.get_logger(software_name, level=log_level, daemon_mode=daemon_mode)
    
    if args.command:
        return handle_cli_command(args, config, logger)
    
    run_mode = "daemon" if daemon_mode else "once"
    
    logger.info(f"{software_name} starting... (mode: {run_mode})")
    logger.info(f"Version: {version}")
    logger.info(f"Log level: {config.log_level}")
    
    # Register signal handlers for graceful shutdown (fallback for non-daemon mode)
    # BEST PRACTICE: Always handle SIGTERM/SIGINT, never use SIG_IGN
    # Note: DaemonManager registers its own handlers in daemon mode
    signal.signal(signal.SIGINT, shutdown_handler)
    signal.signal(signal.SIGTERM, shutdown_handler)
    
    logger.debug("Initializing application services...")
    app = Application(config, logger)
    
    logger.debug("Setting up daemon manager...")
    daemon = DaemonManager(app, config, logger)
    if daemon_mode:
        logger.debug("Starting daemon mode (continuous monitoring)...")
        daemon.run_forever()
        logger.debug("DynDNS daemon shutdown complete")
    else:
        logger.debug("Starting single-run mode...")
        
        try:
            if app.run_cycle():
                logger.info("Single update completed successfully")
            else:
                logger.warning("Single update completed with warnings")
                return 1
        except Exception as e:
            logger.error(f"Unexpected error: Single update failed: {e}")
            return 1
    
    return 0


################################################################################
# ENTRY POINT
################################################################################

if __name__ == "__main__":
    logger: Optional[logging.Logger] = None
    
    try:
        exit_code = main()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        if logger is None:
            logger = LoggerManager.get_logger(__software_name__)
        logger.warning("Application interrupted by user")
        sys.exit(130)
    except Exception as e:
        if logger is None:
            logger = LoggerManager.get_logger(__software_name__)
        logger.error(f"Unexpected error: {e}", exc_info=True)
        sys.exit(1)