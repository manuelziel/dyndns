#!/usr/bin/env python3
"""Base CLI menu module.

This module provides base CLI classes for database-driven applications
with interactive TUI menus, configuration import/export, and entity management.

Typical usage:
    >>> menu = ConfigMenu(config, logger)
    >>> menu.run()

Author: Manuel Ziel
License: MIT
"""

################################################################################
# IMPORTS & DEPENDENCIES
################################################################################

import os
from datetime import datetime
from typing import Any, Optional
from abc import ABC, abstractmethod

from ..core.exceptions import DatabaseError
from ..utils.colors import Colors
from .helpers.output import (
    print_section, print_error, print_success,
    clear_screen
)
from .helpers.input import (
    confirm_action, wait_for_enter, safe_input,
    resolve_path, is_valid_file_path
)
from src.core.constants import ExportFormat
from src.cli.constants import MenuChoices, CLIConfig

################################################################################
# BASE CONFIGURATION MENU CLASS
################################################################################

class ConfigMenu(ABC):
    """Abstract base class for interactive TUI menus.

    Provides a menu-driven interface for managing database entities,
    viewing data, and importing/exporting configuration.

    Attributes:
        config: ConfigManager instance with database access.
        logger: LoggerManager instance for logging.
        db: Database connection from config.
        importer_class: Concrete importer class to use (must be overridden).
        exporter_class: Concrete exporter class to use (must be overridden).
    """

    importer_class: Any = None
    exporter_class: Any = None

    ############################################################################
    # Lifecycle Methods
    ############################################################################

    def __init__(self, config: Any, logger: Any) -> None:
        """Initialize configuration menu.

        Args:
            config: ConfigManager instance with database access.
            logger: LoggerManager instance for logging.

        Raises:
            DatabaseError: If database is not initialized.
        """
        self.config = config
        self.logger = logger
        self.db = config.db
        
        if self.db is None:
            raise DatabaseError("Database not initialized.")
    

    def run(self) -> int:
        """Run main menu loop.

        Returns:
            Exit code (0 for success).
        """
        while True:
            clear_screen()
            self.print_header()
            max_choice = self.print_menu()
            
            choice = safe_input(f"Enter your choice ({MenuChoices.EXIT}-{max_choice}): ").strip()
            
            try:
                if choice == MenuChoices.EXIT:
                    break
                self.handle_choice(choice)
            except KeyboardInterrupt:
                print("\n\nOperation cancelled by user.")
                wait_for_enter()
            except Exception as e:
                print_error(f"Critical Error: {e}")
                self.logger.error(f"Menu error: {e}")
                wait_for_enter()
        
        return 0


    ############################################################################
    # Abstract Methods - Must be implemented in subclass
    ############################################################################

    @abstractmethod
    def print_menu(self) -> int:
        """Print main menu options.

        Returns:
            Maximum valid choice number.
        """
        pass


    @abstractmethod
    def handle_choice(self, choice: str) -> None:
        """Handle user menu choice.

        Args:
            choice: The user's input string.
        """
        pass


    @abstractmethod
    def manage_zones(self) -> None:
        """Manage configured zones."""
        pass


    @abstractmethod
    def manage_records(self) -> None:
        """Manage DNS records."""
        pass


    @abstractmethod
    def view_status(self) -> None:
        """View current IP addresses and database record statuses."""
        pass


    ############################################################################
    # Concrete Implementations
    ############################################################################

    def print_header(self) -> None:
        """Print menu header (optional override).

        Modern CLIs skip banners for cleaner output.
        """
        pass


    def import_config(self) -> None:
        """Launch configuration importer.

        Uses the class-linked importer specified in importer_class.
        """
        if not self.importer_class:
            print_error("Importer class not configured.")
            wait_for_enter()
            return

        print_section("Import Configuration")
        file_path = safe_input("\nEnter file path to import: ").strip()
        if not file_path:
            print_error("No file specified.")
            wait_for_enter()
            return
        if not is_valid_file_path(file_path, must_exist=True):
            print_error(f"File not found or invalid: {file_path}")
            wait_for_enter()
            return

        file_path = resolve_path(file_path)
        overwrite = confirm_action("Overwrite existing data?", default=False)
        print(f"\nImporting from {file_path}...")
        importer = self.importer_class(self.config, self.logger)
        result = importer.import_from_file(file_path, overwrite=overwrite)
        if result == 0:
            print_success("Import completed successfully!")
        else:
            print_error("Import failed. Check logs for details.")
        wait_for_enter()


    def export_config(self) -> None:
        """Launch configuration exporter with smart defaults.

        Uses the class-linked exporter specified in exporter_class.
        """
        if not self.exporter_class:
            print_error("Exporter class not configured.")
            wait_for_enter()
            return

        output_file = self._prompt_export_path()
        if not output_file:
            return

        format_type = self._resolve_export_format(output_file)
        print("\nExporting configuration...")
        exporter = self.exporter_class(self.config, self.logger)
        result = exporter.export_to_file(output_file, format_type=format_type)
        if result == 0:
            print_success(f"Configuration exported to: {output_file}")
        else:
            print_error("Export failed. Check logs for details.")
        wait_for_enter()


    def _prompt_export_path(self) -> Optional[str]:
        """Prompt user for configuration export file path.

        Returns:
            Resolved output file path string or None if invalid.
        """
        print_section("Export Configuration")
        timestamp = datetime.now().strftime(CLIConfig.TIMESTAMP_FORMAT)
        default_filename = f"config-export_{timestamp}{ExportFormat.EXT_YAML}"
        default_path = os.path.expanduser(f"~/{default_filename}")
        print(f"\n{Colors.DIM}Default location:{Colors.NC} {Colors.CYAN}{default_path}{Colors.NC}\n")
        print(f"{Colors.DIM}Options:{Colors.NC}")
        print(f"{Colors.DIM}  • Press Enter: Use default location{Colors.NC}")
        print(f"{Colors.DIM}  • Enter custom path: {Colors.CYAN}/path/to/your/config{ExportFormat.EXT_YAML}{Colors.NC}\n")

        output_file = safe_input(f"Output file path [default: {default_filename}]: ").strip()
        if not output_file:
            return default_path
        if not is_valid_file_path(output_file, must_exist=False):
            print_error(f"Target path is invalid or directory not writable: {output_file}")
            wait_for_enter()
            return None
        return resolve_path(output_file)


    def _resolve_export_format(self, output_file: str) -> str:
        """Determine export format from file extension or user prompt.

        Args:
            output_file: Target file path.

        Returns:
            Export format identifier (`yaml` or `json`).
        """
        file_ext = os.path.splitext(output_file)[1].lower()
        if file_ext in [ExportFormat.EXT_YAML, ExportFormat.EXT_YML]:
            return ExportFormat.YAML
        if file_ext == ExportFormat.EXT_JSON:
            return ExportFormat.JSON
        choice = safe_input(f"Format ({ExportFormat.YAML}/{ExportFormat.JSON}) [{ExportFormat.YAML}]: ").strip().lower()
        return choice if choice in [ExportFormat.YAML, ExportFormat.JSON] else ExportFormat.YAML
