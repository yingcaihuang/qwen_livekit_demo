"""SSO user provisioning: auto-create accounts and compute roles from group mappings."""

import json
import logging
import secrets

import aiosqlite

from app.services.rbac import VALID_ROLES

logger = logging.getLogger(__name__)


async def provision_sso_user(
    db: aiosqlite.Connection,
    *,
    subject: str,
    username: str,
    email: str | None,
    groups: list[str],
    auth_source: str = "sso",
) -> str:
    """Provision or update an SSO user based on OIDC userinfo.

    - If the user (by sso_subject) doesn't exist, creates a new account.
    - Computes roles from group_role_mappings; defaults to 'viewer' if no match.
    - On re-login, updates roles to match current groups (convergent).
    - Returns the user_id.
    """
    # Check if user already exists
    cursor = await db.execute("SELECT id FROM users WHERE sso_subject = ?", (subject,))
    row = await cursor.fetchone()

    if row:
        user_id = row[0]
        # Update email/username if changed
        await db.execute(
            "UPDATE users SET username = ?, email = ?, updated_at = datetime('now') WHERE id = ?",
            (username, email, user_id),
        )
    else:
        # Create new SSO user
        user_id = secrets.token_hex(16)
        await db.execute(
            "INSERT INTO users (id, username, email, auth_source, sso_subject) "
            "VALUES (?, ?, ?, ?, ?)",
            (user_id, username, email, auth_source, subject),
        )

    # Compute roles from group_role_mappings
    roles = await _compute_roles(db, groups)

    # Save only the groups that have a configured mapping (filter out unmapped groups)
    if groups:
        placeholders = ",".join("?" for _ in groups)
        cursor = await db.execute(
            f"SELECT group_name FROM group_role_mappings WHERE group_name IN ({placeholders})",
            groups,
        )
        mapped_groups = [row[0] for row in await cursor.fetchall()]
    else:
        mapped_groups = []
    await db.execute(
        "UPDATE users SET sso_groups = ? WHERE id = ?",
        (json.dumps(mapped_groups), user_id),
    )

    # Check if roles are manually overridden (skip auto-update if so)
    cursor = await db.execute("SELECT role_override FROM users WHERE id = ?", (user_id,))
    override_row = await cursor.fetchone()
    if not (override_row and override_row[0]):
        # Replace all existing roles with computed ones (convergent update)
        await db.execute("DELETE FROM user_roles WHERE user_id = ?", (user_id,))
        for role in roles:
            await db.execute(
                "INSERT INTO user_roles (user_id, role) VALUES (?, ?)", (user_id, role)
            )

    await db.commit()
    return user_id


async def _compute_roles(db: aiosqlite.Connection, groups: list[str]) -> set[str]:
    """Compute platform roles from Authentik groups via group_role_mappings.

    Returns the set of matched roles, or {'viewer'} if no mapping matches.
    """
    if not groups:
        return {"viewer"}

    # Build placeholders for IN query
    placeholders = ",".join("?" for _ in groups)
    cursor = await db.execute(
        f"SELECT DISTINCT role FROM group_role_mappings WHERE group_name IN ({placeholders})",
        groups,
    )
    rows = await cursor.fetchall()
    matched_roles = {row[0] for row in rows if row[0] in VALID_ROLES}

    if not matched_roles:
        return {"viewer"}
    return matched_roles
