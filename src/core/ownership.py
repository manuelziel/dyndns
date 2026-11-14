#!/usr/bin/env python3
"""File ownership helper for service user handoff.

When an admin CLI action runs as root (e.g. ``sudo dyndns config``, ``import``,
``export``), the application may create or modify files that the systemd
service — which runs as the unprivileged ``SERVICE_USER`` — needs to access at
runtime. This module fixes ownership and permissions on such files safely
without following symbolic links (CWE-59).

Author: Manuel Ziel
License: MIT
"""

################################################################################
# IMPORTS & DEPENDENCIES
################################################################################

import grp
import os
import pwd
import stat
from typing import Any

from .constants import EnvKeys, OwnershipDefaults

################################################################################
# PUBLIC API
################################################################################


def ensure_service_ownership(
    path: str,
    mode: int | None = None,
    logger: Any | None = None,
    private_group: bool = False,
) -> bool:
    """Chown ``path`` to the configured service user when running as root.

    Rejects symbolic links (CWE-59) and applies ownership and permissions
    without following symlinks. No-op when not running as root, when
    ``SERVICE_USER`` is unset/``root``/placeholder, or when ``path`` is missing.

    Args:
        path: Absolute path to the file or directory to adjust.
        mode: Optional explicit chmod value. Defaults to ``0o660`` for files
            and ``0o770`` for directories.
        logger: Optional logger for diagnostic messages.
        private_group: If True, prefer ``SERVICE_USER``'s private/primary group
            instead of a shared ``SERVICE_GROUP`` (used for ``0o600`` key files).

    Returns:
        True on success, False on any failure, symlink rejection, or no-op.
    """
    if os.geteuid() != 0 or not path:
        return False
    if os.path.islink(path):
        if logger:
            logger.warning(f"Refusing ownership change on symlink: {path}")
        return False
    if not os.path.exists(path):
        return False
    resolved = _resolve_service_ids(logger=logger, private_group=private_group)
    if resolved is None:
        return False
    service_user, uid, gid = resolved
    return _apply_ownership_and_mode(path, uid, gid, mode, service_user, logger)


################################################################################
# PRIVATE HELPERS
################################################################################


def _resolve_service_ids(
    logger: Any | None = None,
    private_group: bool = False,
) -> tuple[str, int, int] | None:
    """Resolve configured service user UID and target group GID.

    Args:
        logger: Optional logger for diagnostic messages.
        private_group: If True, resolve user's own group rather than SERVICE_GROUP.

    Returns:
        Tuple of ``(service_user, uid, gid)``, or ``None`` if unresolvable.
    """
    service_user = os.environ.get(EnvKeys.SERVICE_USER, "").strip()
    if not service_user or service_user in (
        OwnershipDefaults.ROOT_USER,
        OwnershipDefaults.PLACEHOLDER_USER,
    ):
        return None
    raw_group = os.environ.get(EnvKeys.SERVICE_GROUP, "").strip()
    use_default_group = (
        private_group or not raw_group or raw_group == OwnershipDefaults.PLACEHOLDER_GROUP
    )
    service_group = service_user if use_default_group else raw_group
    try:
        pw_entry = pwd.getpwnam(service_user)
        gid = (
            _resolve_private_gid(service_user, pw_entry.pw_gid)
            if private_group
            else grp.getgrnam(service_group).gr_gid
        )
        return service_user, pw_entry.pw_uid, gid
    except KeyError:
        if logger:
            logger.debug(f"Service user/group not found: {service_user}:{service_group}")
        return None


def _resolve_private_gid(service_user: str, fallback_gid: int) -> int:
    """Resolve user-named group GID with fallback to passwd primary GID.

    Args:
        service_user: Target service account username.
        fallback_gid: Primary GID from the passwd entry.

    Returns:
        Numeric GID for exclusive key ownership.
    """
    try:
        return grp.getgrnam(service_user).gr_gid
    except KeyError:
        return fallback_gid


def _apply_ownership_and_mode(
    path: str,
    uid: int,
    gid: int,
    mode: int | None,
    service_user: str,
    logger: Any | None,
) -> bool:
    """Apply symlink-safe chown and descriptor-bound fchmod on ``path``.

    Args:
        path: Target file or directory path.
        uid: Numeric target user ID.
        gid: Numeric target group ID.
        mode: Explicit permission bits, or None for default group-write mode.
        service_user: Target username for warning logs.
        logger: Optional logger instance.

    Returns:
        True on success, False if chown, O_NOFOLLOW open, or fchmod fails.
    """
    try:
        os.chown(path, uid, gid, follow_symlinks=False)
    except OSError as exc:
        if logger:
            logger.warning(f"Failed to chown {path} to {service_user}: {exc}")
        return False
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        try:
            is_dir = stat.S_ISDIR(os.fstat(fd).st_mode)
            default_mode = (
                OwnershipDefaults.DIR_MODE_GROUP_WRITE
                if is_dir
                else OwnershipDefaults.FILE_MODE_GROUP_WRITE
            )
            os.fchmod(fd, default_mode if mode is None else mode)
        finally:
            os.close(fd)
    except OSError as exc:
        if logger:
            logger.warning(f"Failed to chmod {path}: {exc}")
        return False
    return True
