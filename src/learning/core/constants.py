"""Hardcoded values shared across layers. Environment-dependent values go in config.py."""

from enum import Enum

# Pagination
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100


class UserStatus(str, Enum):
    """Lifecycle state of a user account."""

    ACTIVE = "ACTIVE"
    BLOCKED = "BLOCKED"
    PENDING = "PENDING"
