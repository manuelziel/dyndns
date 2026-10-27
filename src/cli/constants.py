#!/usr/bin/env python3
"""Constants for the CLI interface.

This module centralizes all CLI-specific constants, such as menu choices,
formatting widths, and other UI-related settings, separating presentation
from core business logic.

Typical usage:
    >>> from src.cli.constants import MenuChoices, CLIConfig
    >>> if choice == MenuChoices.EXIT:
    >>>     sys.exit(0)

Author: Manuel Ziel
License: MIT
"""

################################################################################
# CLI MENU EXTENSIONS - Submenu Choices & Prompts
################################################################################

class PromptDefaults:
    """Namespace for default CLI prompt inputs."""
    YES = ['y', 'yes']
    NO = ['n', 'no']


class SelectionChoices:
    """Namespace for list selection choices."""
    ALL = '0'
    CANCEL = '0'


class ZoneMenuChoices:
    """Namespace for zone management menu choices."""
    EXIT = '0'
    LIST = '1'
    ADD = '2'
    EDIT = '3'
    DELETE = '4'


class EditZoneMenuChoices:
    """Namespace for zone editing menu choices."""
    EXIT = '0'
    UPDATE_ZONE_ID = '1'
    UPDATE_CREDENTIALS = '2'
    TOGGLE_STATUS = '3'


class RecordMenuChoices:
    """Namespace for record management menu choices."""
    EXIT = '0'
    LIST = '1'
    ADD = '2'
    EDIT = '3'
    DELETE = '4'
    SYNC = '5'


class EditRecordMenuChoices:
    """Namespace for record editing menu choices."""
    EXIT = '0'
    TTL = '1'
    STATUS = '2'


class SetupMenuChoices:
    """Namespace for setup wizard choices."""
    SKIP = '0'
    STANDARD = '1'
    ROOT_ONLY = '2'


class SettingsMenuChoices:
    """Namespace for DNS settings menu choices."""
    EXIT = '0'
    UPDATE_METHOD = '1'
    DEFAULT_TTL = '2'


class UpdateMethodMenuChoices:
    """Namespace for update method selection choices."""
    CANCEL = '0'
    DYNDNS = '1'
    REST = '2'


class MenuChoices:
    """Namespace for main menu choices."""
    EXIT = '0'
    VIEW_IP = '1'
    MANAGE_ZONES = '2'
    MANAGE_RECORDS = '3'
    FORCE_UPDATE = '4'
    SETTINGS = '5'
    EXPORT = '6'
    IMPORT = '7'


class MenuLabels:
    """Namespace for menu item labels."""
    
    MAIN_MENU = {
        MenuChoices.VIEW_IP: "View Current Status",
        MenuChoices.MANAGE_ZONES: "Manage Zones",
        MenuChoices.MANAGE_RECORDS: "Manage DNS Records",
        MenuChoices.FORCE_UPDATE: "Force DNS Update",
        MenuChoices.SETTINGS: "Configure DNS Settings",
        MenuChoices.EXPORT: "Export Configuration",
        MenuChoices.IMPORT: "Import Configuration",
    }
    
    SETTINGS_MENU = {
        SettingsMenuChoices.UPDATE_METHOD: "Change Update Method",
        SettingsMenuChoices.DEFAULT_TTL: "Change Default TTL",
    }
    
    ZONE_MENU = {
        ZoneMenuChoices.LIST: "List all zones",
        ZoneMenuChoices.ADD: "Add new zone",
        ZoneMenuChoices.EDIT: "Edit zone",
        ZoneMenuChoices.DELETE: "Delete zone",
    }
    
    EDIT_ZONE_MENU = {
        EditZoneMenuChoices.UPDATE_ZONE_ID: "Update Zone ID",
        EditZoneMenuChoices.UPDATE_CREDENTIALS: "Update API Credentials",
        EditZoneMenuChoices.TOGGLE_STATUS: "Enable/Disable Zone",
    }
    
    RECORD_MENU = {
        RecordMenuChoices.LIST: "List all records",
        RecordMenuChoices.ADD: "Add new record",
        RecordMenuChoices.EDIT: "Edit record",
        RecordMenuChoices.DELETE: "Delete record",
        RecordMenuChoices.SYNC: "Sync records from provider",
    }
    
    EDIT_RECORD_MENU = {
        EditRecordMenuChoices.TTL: "TTL",
        EditRecordMenuChoices.STATUS: "Enable/Disable record",
    }


class UpdateMethodLabels:
    """Namespace for update method menu labels and descriptions."""
    DYNDNS_DESC = "recommended"
    REST_DESC = "fallback / single records"
    UNKNOWN_DESC = "unknown"
    
    MENU_OPTIONS = {
        UpdateMethodMenuChoices.DYNDNS: ("dyndns", "Native IONOS DynDNS API (recommended)"),
        UpdateMethodMenuChoices.REST: ("rest", "Classic REST API"),
    }


################################################################################
# CLI COMMANDS - Main Entrypoint Commands
################################################################################

class CLICommands:
    """Namespace for command-line arguments and subcommands."""
    CONFIG = "config"
    IMPORT = "import"
    EXPORT = "export"


################################################################################
# UI CONFIGURATION - CLI Formatting Constants
################################################################################

class CLIConfig:
    """Namespace for CLI UI configuration settings."""
    BANNER_WIDTH = 63
    SECTION_SEP_WIDTH = 80
    SUBSECTION_SEP_WIDTH = 76
    TIMESTAMP_FORMAT = "%Y%m%d_%H%M%S"
    LABEL_WIDTH = 15
    MASK_LENGTH = 20
    MAX_MASK_LENGTH = 64
    ZONE_NAME_WIDTH = 30
    RECORD_NAME_WIDTH = 40
    RECORD_TYPE_WIDTH = 5


################################################################################
# VALIDATION CONFIGURATION - Regex and Limits
################################################################################

class ValidationRegex:
    """Namespace for input validation regular expressions."""
    DOMAIN = r'^(?=.{1,253}$)(?!-)[a-z0-9-]{1,63}(?<!-)(\.[a-z0-9-]{1,63})*$'
    IPV4 = r'^(\d{1,3}\.){3}\d{1,3}$'
    IPV6 = r'^([0-9a-fA-F]{0,4}:){2,7}[0-9a-fA-F]{0,4}$'


class ValidationLimits:
    """Namespace for input validation numeric limits."""
    IPV4_MIN_OCTET = 0
    IPV4_MAX_OCTET = 255
    TTL_MIN = 60
    TTL_MAX = 86400
