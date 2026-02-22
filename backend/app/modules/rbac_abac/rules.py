BASE_PERMISSIONS: set[str] = {
    "templates:read",
    "templates:write",
    "documents:read",
    "documents:write",
    "files:read",
    "files:write",
    "jobs:manage",
    "audit:read",
}

ROLE_PERMISSIONS: dict[str, set[str]] = {
    "owner": BASE_PERMISSIONS,
    "admin": BASE_PERMISSIONS,
    "auditor_ro": {"templates:read", "documents:read", "files:read", "audit:read"},
    "manager": {"templates:read", "templates:write", "documents:read", "documents:write", "files:read"},
}
