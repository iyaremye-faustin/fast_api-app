"""Hardcoded values shared across layers. Environment-dependent values go in config.py."""

from enum import Enum


class UserStatus(str, Enum):
    """Lifecycle state of a user account."""

    ACTIVE = "ACTIVE"
    BLOCKED = "BLOCKED"
    PENDING = "PENDING"
