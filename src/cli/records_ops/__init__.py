#!/usr/bin/env python3
"""Modular operation mixins composing the interactive CLI RecordManager.

Author: Manuel Ziel
License: MIT
"""

################################################################################
# IMPORTS & EXPORTS
################################################################################

from .add import RecordCreateMixin
from .client import RecordProviderClientMixin
from .edit import RecordEditMixin
from .sync import RecordDeleteSyncMixin
from .update import RecordForceUpdateMixin
from .update_rest import RecordRestRecoveryMixin

__all__ = [
    "RecordCreateMixin",
    "RecordDeleteSyncMixin",
    "RecordEditMixin",
    "RecordForceUpdateMixin",
    "RecordProviderClientMixin",
    "RecordRestRecoveryMixin",
]
