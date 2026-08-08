"""RBAC service: role-to-capability mapping and capability computation."""

VALID_ROLES = frozenset({"super_admin", "admin", "tester", "viewer"})

CAPABILITIES = frozenset(
    {
        "instance:read",
        "instance:write",
        "session:run",
        "chat:use",
        "image:use",
        "resource:read:all",
        "dashboard:read",
        "user:manage",
        "role:manage",
        "sso:manage",
    }
)

ROLE_CAPABILITIES: dict[str, frozenset[str]] = {
    "super_admin": CAPABILITIES,  # 全部，含 resource:read:all
    "admin": frozenset(
        {
            "instance:read",
            "instance:write",
            "session:run",
            "chat:use",
            "image:use",
            "resource:read:all",
            "dashboard:read",
        }
    ),
    "tester": frozenset(
        {
            "instance:read",
            "instance:write",
            "session:run",
            "chat:use",
            "image:use",
            "dashboard:read",
        }
    ),
    "viewer": frozenset({"instance:read", "dashboard:read"}),
}


def capabilities_for(roles: set[str]) -> frozenset[str]:
    """Return the union of capabilities for the given roles (Requirement 6.7)."""
    result: set[str] = set()
    for role in roles:
        result |= ROLE_CAPABILITIES.get(role, frozenset())
    return frozenset(result)
