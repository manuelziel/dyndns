#!/usr/bin/env python3
"""Abstract base menu class for interactive TUI administration.

Provides the main menu event loop and shared import/export workflows for
concrete CLI menu implementations.

Author: Manuel Ziel
License: MIT
"""

################################################################################
# IMPORTS & DEPENDENCIES
################################################################################

from abc import ABC, abstractmethod
from datetime import datetime
import os
from typing import Any

from ..core.constants import ExportFormat
from ..core.exceptions import DatabaseError
from ..utils.colors import Colors
from .constants import CLIConfig, MenuChoices
from .helpers.input import (
    confirm_action,
    is_valid_file_path,
    resolve_path,
    safe_input,
    wait_for_enter,
)
from .helpers.output import clear_screen, print_error, print_section, print_success

################################################################################
# BASE CONFIGURATION MENU CLASS
################################################################################


class ConfigMenu(ABC):
    """Abstract base class for interactive TUI configuration menus.

    Attributes:
        config: ``ConfigManager`` instance.
        logger: Logger instance.
        db: ``Database`` connection pool.
        importer_class: Concrete ``BaseImporter`` subclass.
        exporter_class: Concrete ``BaseExporter`` subclass.
    """

    importer_class: Any = None
    exporter_class: Any = None

    def __init__(self, config: Any, logger: Any) -> None:
        """Initialize configuration menu and verify database availability.

        Args:
            config: ``ConfigManager`` instance.
            logger: Logger instance.

        Raises:
            DatabaseError: If ``config.db`` is ``None``.
        """
        self.config = config
        self.logger = logger
        self.db = config.db
        if self.db is None:
            raise DatabaseError("Database not initialized.")

    def run(self) -> int:
        """Execute the interactive main menu loop until exit or EOF.

        Returns:
            Exit code (``0`` on clean exit).
        """
        while True:
            clear_screen()
            self.print_header()
            max_choice = self.print_menu()
            try:
                choice = safe_input(
                    f"Enter your choice ({MenuChoices.EXIT}-{max_choice}): "
                ).strip()
            except KeyboardInterrupt:
                print()
                break
            if choice == MenuChoices.EXIT:
                break
            self._dispatch_choice_safely(choice)
        return 0

    def _dispatch_choice_safely(self, choice: str) -> None:
        """Invoke ``handle_choice`` while catching interactive cancellations/errors.

        Args:
            choice: User-entered option key.
        """
        try:
            self.handle_choice(choice)
        except KeyboardInterrupt:
            print("\n\nOperation cancelled by user.")
            wait_for_enter()
        except Exception as exc:
            print_error(f"Critical Error: {exc}")
            self.logger.error(f"Menu error: {exc}")
            wait_for_enter()

    ############################################################################
    # ABSTRACT INTERFACE
    ############################################################################

    @abstractmethod
    def print_menu(self) -> int:
        """Render menu options and return the highest valid option number."""

    @abstractmethod
    def handle_choice(self, choice: str) -> None:
        """Dispatch a single user menu selection."""

    @abstractmethod
    def manage_zones(self) -> None:
        """Open the DNS zone management submenu."""

    @abstractmethod
    def manage_records(self) -> None:
        """Open the DNS record management submenu."""

    @abstractmethod
    def view_status(self) -> None:
        """Display live public IPs and stored DNS record status."""

    ############################################################################
    # SHARED IMPORT & EXPORT WORKFLOWS
    ############################################################################

    def print_header(self) -> None:
        """Optional header hook prior to ``print_menu``."""

    def import_config(self) -> None:
        """Prompt for a backup file path and run ``importer_class``."""
        if not self.importer_class:
            print_error("Importer class not configured.")
            wait_for_enter()
            return
        print_section("Import Configuration")
        raw_path = safe_input("\nEnter file path to import: ").strip()
        if not raw_path or not is_valid_file_path(raw_path, must_exist=True):
            print_error(f"File not found or invalid: {raw_path or '(empty)'}")
            wait_for_enter()
            return
        file_path = resolve_path(raw_path)
        overwrite = confirm_action("Overwrite existing data?", default=False)
        print(f"\nImporting from {file_path}...")
        result = self.importer_class(self.config, self.logger).import_from_file(
            file_path, overwrite=overwrite
        )
        if result == 0:
            print_success("Import completed successfully!")
        else:
            print_error("Import failed. Check logs for details.")
        wait_for_enter()

    def export_config(self) -> None:
        """Prompt for an export path/format and run ``exporter_class``."""
        if not self.exporter_class:
            print_error("Exporter class not configured.")
            wait_for_enter()
            return
        output_file = self._prompt_export_path()
        if not output_file:
            return
        format_type = self._resolve_export_format(output_file)
        print("\nExporting configuration...")
        result = self.exporter_class(self.config, self.logger).export_to_file(
            output_file, format_type=format_type
        )
        if result == 0:
            print_success(f"Configuration exported to: {output_file}")
        else:
            print_error("Export failed. Check logs for details.")
        wait_for_enter()

    def _prompt_export_path(self) -> str | None:
        """Prompt user for a writable export file path with timestamped default.

        Returns:
            Resolved file path or ``None`` if invalid.
        """
        print_section("Export Configuration")
        timestamp = datetime.now().strftime(CLIConfig.TIMESTAMP_FORMAT)
        default_filename = f"config-export_{timestamp}{ExportFormat.EXT_YAML}"
        default_path = os.path.expanduser(f"~/{default_filename}")
        print(f"\n{Colors.DIM}Default location:{Colors.NC} {Colors.CYAN}{default_path}{Colors.NC}\n")
        output_file = safe_input(f"Output file path [default: {default_filename}]: ").strip()
        if not output_file:
            return default_path
        if not is_valid_file_path(output_file, must_exist=False):
            print_error(f"Target path is invalid or directory not writable: {output_file}")
            wait_for_enter()
            return None
        return resolve_path(output_file)

    @staticmethod
    def _resolve_export_format(output_file: str) -> str:
        """Infer export format from file extension or prompt the user.

        Args:
            output_file: Target export file path.

        Returns:
            ``'yaml'`` or ``'json'``.
        """
        file_ext = os.path.splitext(output_file)[1].lower()
        if file_ext in (ExportFormat.EXT_YAML, ExportFormat.EXT_YML):
            return ExportFormat.YAML
        if file_ext == ExportFormat.EXT_JSON:
            return ExportFormat.JSON
        choice = (
            safe_input(
                f"Format ({ExportFormat.YAML}/{ExportFormat.JSON}) [{ExportFormat.YAML}]: "
            )
            .strip()
            .lower()
        )
        return choice if ExportFormat.is_valid(choice) else ExportFormat.YAML
