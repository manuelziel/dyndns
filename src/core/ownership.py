#!/usr/bin/env python3
"""File ownership helper for service user handoff.

When an admin CLI action runs as root (e.g. ``sudo dyndns config``, ``import``,
``export``), the application may create or modify files that the systemd
service — which runs as the unprivileged SERVICE_USER — needs to access at
runtime. This module fixes ownership and permissions on such files so the
service user retains read/write access.

Rationale:
    Similar to how ``nginx -s reload`` runs as root while the worker runs as
    www-data, or how ``mysqldump`` runs as the caller while the daemon runs
    as ``mysql``: administrative commands run with elevated privileges and
    hand off their output to the service user.

Typical usage:
    >>> from src.core.ownership import ensure_service_ownership
    >>> ensure_service_ownership('/var/lib/dyndns/dyndns.db')

Environment variables (exported by bash wrapper):
    SERVICE_USER: Target owner username. Empty/"root"/unset -> no-op.
    SERVICE_GROUP: Target owner group. Defaults to SERVICE_USER.

Author: Manuel Ziel
License: MIT
"""

################################################################################
# IMPORTS & DEPENDENCIES
################################################################################

# Standard Imports
import logging
import os
import pwd
import grp
from typing import Optional, Any

# Local Imports
from .constants import EnvKeys, SystemDefaults


################################################################################
# PUBLIC API
################################################################################

def ensure_service_ownership(
    path: str,
    mode: Optional[int] = None,
    logger: Optional[Any] = None,
) -> bool:
    """Chown ``path`` to the configured service user when running as root.

    No-op when any of the following are true:
        - Current process is not root (EUID != 0)
        - ``SERVICE_USER`` env var is unset, empty, or equals ``root``
        - ``SERVICE_USER`` does not resolve to a local account
        - ``path`` does not exist

    Args:
        path: Absolute path to the file or directory to adjust.
        mode: Optional explicit chmod value. Defaults to ``0o660`` for files
            and ``0o770`` for directories.
        logger: Optional logger for diagnostic messages.

    Returns:
        True on success, False on any failure or no-op.
    """
    if os.geteuid() != 0:
        return False

    service_user = os.environ.get(EnvKeys.SERVICE_USER, "").strip()
    if not service_user or service_user == SystemDefaults.ROOT_USER:
        return False

    service_group = os.environ.get(EnvKeys.SERVICE_GROUP, "").strip() or service_user

    if not os.path.exists(path):
        return False

    try:
        uid = pwd.getpwnam(service_user).pw_uid
        gid = grp.getgrnam(service_group).gr_gid
    except KeyError:
        if logger:
            logger.debug(
                f"Service user/group not found: {service_user}:{service_group}"
            )
        return False

    try:
        os.chown(path, uid, gid)
    except OSError as exc:
        if logger:
            logger.warning(f"Failed to chown {path} to {service_user}: {exc}")
        return False

    if mode is None:
        mode = SystemDefaults.DIR_MODE_GROUP_WRITE if os.path.isdir(path) else SystemDefaults.FILE_MODE_GROUP_WRITE
    try:
        os.chmod(path, mode)
    except OSError as exc:
        if logger:
            logger.warning(f"Failed to chmod {path}: {exc}")
        return False

    return True
