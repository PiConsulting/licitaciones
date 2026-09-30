from enum import StrEnum


class UserRole(StrEnum):
    SUPERADMIN = "superadmin"
    MIEMBRO = "miembro"


USER_ROLES: tuple[str, ...] = tuple(role.value for role in UserRole)
