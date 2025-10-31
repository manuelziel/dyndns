#!/usr/bin/env python3
"""
Provider-DYNDNS - Dynamic DNS Client for DNS Providers

Integrates with bash setup/runtime system for consistent logging,
configuration management, and daemon operations.

Created: 2025-10-27
Author: Manuel Ziel
License: MIT

This program is free software: you can redistribute it and/or modify
"""

################################################################################
# IMPORTS & DEPENDENCIES
################################################################################

# Standard library imports
import sys
import os
import argparse
import logging

# Add src directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'src'))

from logger import LoggerManager
from config import ConfigManager
from application import Application
from daemon import DaemonManager
from cli import ConfigMenu, ConfigImporter, ConfigExporter
from src import __version__, __author__, __software_name__

################################################################################
# ARGUMENT PARSING - Command-Line Interface
################################################################################

def parse_arguments() -> argparse.Namespace:
    """Parse CLI arguments with subcommands (config, import, export, daemon)."""
    parser = argparse.ArgumentParser(
        description='Provider DynDNS - Dynamic DNS Client for DNS Providers',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                          # Start DynDNS (single run)
  %(prog)s --daemon                 # Continuous monitoring mode
  %(prog)s config                   # Interactive configuration
  %(prog)s import config.yaml       # Import configuration
  %(prog)s export --output backup.yaml  # Export configuration
        """
    )
    
    parser.add_argument('-v', '--version', action='version', version=f'%(prog)s {__version__}')
    parser.add_argument('--daemon', '-d', action='store_true', help='Run in daemon mode (continuous monitoring)')
    
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    subparsers.add_parser('config', help='Open interactive configuration menu')
    
    parser_import = subparsers.add_parser('import', help='Import configuration from YAML/JSON file')
    parser_import.add_argument('file', type=str, help='Path to configuration file (YAML or JSON)')
    parser_import.add_argument('--overwrite', action='store_true', help='Overwrite existing configuration (default: merge)')
    
    parser_export = subparsers.add_parser('export', help='Export current configuration to file')
    parser_export.add_argument('--output', type=str, default=None, help='Output file path (default: stdout)')
    parser_export.add_argument('--format', type=str, choices=['yaml', 'json'], default='yaml', help='Output format: yaml or json (default: yaml)')
    
    return parser.parse_args()

################################################################################
# CLI COMMAND HANDLERS - Subcommand Processing
################################################################################

def handle_cli_command(args: argparse.Namespace, config: ConfigManager, logger: logging.Logger) -> int:
    """Handle CLI subcommands (config, import, export). Returns: Exit code (0=success)."""
    if args.command == 'config':
        logger.debug("Starting interactive configuration menu...")
        try:
            menu = ConfigMenu(config, logger)
            menu.run()
            return 0
        except Exception as e:
            logger.error(f"Configuration menu failed: {e}")
            return 1
        
    elif args.command == 'import':
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
            logger.error(f"Import failed: {e}")
            return 1
            
    elif args.command == 'export':
        try:
            exporter = ConfigExporter(config, logger)
            exporter.export_to_file(output_file=args.output, format=args.format)
            logger.info("Configuration exported successfully")
            return 0
        except Exception as e:
            logger.error(f"Export failed: {e}")
            return 1
    
    return 0

################################################################################
# MAIN APPLICATION - Entry Point and Initialization
################################################################################

def main() -> int:
    """Main entry point. Initialize config/logger, handle CLI commands, start daemon or single-run mode. Returns: Exit code (0=success)."""
    version = __version__
    software_name = __software_name__

    args = parse_arguments()

    current_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(current_dir, "config.toml")
    config = ConfigManager(current_dir, config_path)
    
    log_level = getattr(logging, config.log_level, logging.INFO)
    daemon_mode = args.daemon
    logger = LoggerManager.get_logger(software_name, level=log_level, daemon_mode=daemon_mode)
    
    if args.command:
        return handle_cli_command(args, config, logger)
    
    run_mode = "daemon" if args.daemon else "once"
    
    logger.info(f"{software_name} starting... (mode: {run_mode})")
    logger.info(f"Version: {version}")
    logger.info(f"Log level: {config.log_level}")
    
    logger.debug("Initializing application services...")
    app = Application(config, logger)
    
    logger.debug("Setting up daemon manager...")
    daemon = DaemonManager(app, config, logger)
    if run_mode == "daemon":
        logger.debug("Starting daemon mode (continuous monitoring)...")
        daemon.start()
        logger.debug("DynDNS daemon initialized and running")
    else:
        logger.debug("Starting single-run mode...")
        
        try:
            if app.run_cycle():
                logger.info("Single update completed successfully")
            else:
                logger.warning("Single update completed with warnings")
                return 1
        except Exception as e:
            logger.error(f"Single update failed: {e}")
            return 1
    
    return 0

################################################################################
# ENTRY POINT - Script Execution Handler
################################################################################

if __name__ == "__main__":
    try:
        exit_code = main()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        logger = LoggerManager.get_logger(__software_name__)
        logger.warning("Application interrupted by user")
        sys.exit(130)
    except Exception as e:
        logger = LoggerManager.get_logger(__software_name__)
        logger.error(f"Unexpected error: {e}", exc_info=True)
        sys.exit(1)