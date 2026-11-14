#!/usr/bin/env python3
"""Constants and StrEnum namespaces for the DynDNS CLI interface.

Centralizes menu choices, subcommand identifiers, table widths, ANSI terminal
sequences, and input validation bounds separately from core business logic.

Author: Manuel Ziel
License: MIT
"""

################################################################################
# IMPORTS & DEPENDENCIES
################################################################################

from enum import StrEnum

################################################################################
# CLI MENU CHOICES & PROMPTS
################################################################################


class PromptDefaults:
    """Default affirmative and negative CLI prompt tokens."""

    YES = ("y", "yes")
    NO = ("n", "no")


class SelectionChoices(StrEnum):
    """Generic numbered list selection tokens."""

    ALL = "0"
    CANCEL = "0"


class ZoneMenuChoices(StrEnum):
    """Zone management submenu option keys."""

    EXIT = "0"
    LIST = "1"
    ADD = "2"
    EDIT = "3"
    DELETE = "4"


class EditZoneMenuChoices(StrEnum):
    """Zone editing submenu option keys."""

    EXIT = "0"
    UPDATE_ZONE_ID = "1"
    UPDATE_CREDENTIALS = "2"
    TOGGLE_STATUS = "3"


class RecordMenuChoices(StrEnum):
    """Record management submenu option keys."""

    EXIT = "0"
    LIST = "1"
    ADD = "2"
    EDIT = "3"
    DELETE = "4"
    SYNC = "5"


class EditRecordMenuChoices(StrEnum):
    """Record editing submenu option keys."""

    EXIT = "0"
    TTL = "1"
    STATUS = "2"


class SetupMenuChoices(StrEnum):
    """Post-zone-creation record wizard option keys."""

    SKIP = "0"
    STANDARD = "1"
    ROOT_ONLY = "2"


class SettingsMenuChoices(StrEnum):
    """Global DNS settings submenu option keys."""

    EXIT = "0"
    UPDATE_METHOD = "1"
    DEFAULT_TTL = "2"


class UpdateMethodMenuChoices(StrEnum):
    """Update method picker option keys."""

    CANCEL = "0"
    DYNDNS = "1"
    REST = "2"


class MenuChoices(StrEnum):
    """Top-level interactive configuration menu option keys."""

    EXIT = "0"
    VIEW_IP = "1"
    MANAGE_ZONES = "2"
    MANAGE_RECORDS = "3"
    FORCE_UPDATE = "4"
    SETTINGS = "5"
    EXPORT = "6"
    IMPORT = "7"


class PaginationChoices(StrEnum):
    """Paginated list navigation option keys."""

    NEXT = "n"
    PREV = "p"
    BACK = "0"


################################################################################
# MENU LABELS
################################################################################


class MenuLabels:
    """Human-readable labels for interactive CLI menus."""

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
    """Human-readable descriptions for supported DNS update methods."""

    DYNDNS_DESC = "recommended"
    REST_DESC = "fallback / single records"
    UNKNOWN_DESC = "unknown"

    MENU_OPTIONS = {
        UpdateMethodMenuChoices.DYNDNS: (
            "dyndns",
            "Native IONOS DynDNS API (recommended)",
        ),
        UpdateMethodMenuChoices.REST: ("rest", "Classic REST API"),
    }


################################################################################
# CLI COMMANDS, SYMBOLS & FORMATTING
################################################################################


class CLICommands(StrEnum):
    """Top-level command-line subcommands."""

    CONFIG = "config"
    IMPORT = "import"
    EXPORT = "export"
    VALIDATE = "validate"


class StatusSymbols:
    """Unicode status indicator glyphs for CLI status and list displays."""

    SUCCESS = "✓"
    ERROR = "✗"
    WARNING = "✗"
    INFO = "ℹ"
    ACTIVE = "●"
    INACTIVE = "○"


class CLIConfig:
    """CLI layout dimensions, masks, and terminal control constants."""

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
    DEFAULT_PAGE_SIZE = 10
    JSON_INDENT = 2
    EXPORT_SCHEMA_VERSION = "1.0"
    SUPPORTED_EXPORT_FORMATS = ("yaml", "json")
    ANSI_CLEAR_SCREEN = "\033[H\033[2J"


################################################################################
# VALIDATION PATTERNS & NUMERIC LIMITS
################################################################################


class ValidationRegex:
    """Regular expressions for domain name validation."""

    DOMAIN = r"^(?=.{1,253}$)(?!-)[a-z0-9-]{1,63}(?<!-)(\.[a-z0-9-]{1,63})*$"


class ValidationLimits:
    """Numeric validation bounds for DNS settings."""

    TTL_MIN = 60
    TTL_MAX = 86400
