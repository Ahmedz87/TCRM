"""Role-based data visibility for the sales hierarchy.

- super_admin / admin / director  -> see ALL data (returns None = no filter)
- sales_manager / team leader      -> see SELF + ALL descendants (recursive subtree)
- sales_agent                      -> see SELF only

Hierarchy is encoded in users.manager_id (agent -> team leader -> sales manager -> director).
Clients/leads are linked to an agent via assigned_agent_id.
"""
from sqlalchemy import text

# Roles that see ALL client data (no agent-scoping). Sales/retention are the exception:
# they are scoped to their own/team book. Ops roles work across the whole client base.
ALL_ACCESS_ROLES = {"super_admin", "admin", "director",
                    "backoffice", "validation", "customer_care", "vps", "marketing"}


def _role(user):
    r = getattr(user, "role", None)
    r = r.value if hasattr(r, "value") else r
    return (r or "").lower()


def scope_agent_ids(db, user):
    """List of user ids whose clients/leads this user may see, or None for full access."""
    if _role(user) in ALL_ACCESS_ROLES:
        return None
    rows = db.execute(text("""
        WITH RECURSIVE sub AS (
            SELECT id FROM users WHERE id = :uid
            UNION ALL
            SELECT u.id FROM users u JOIN sub ON u.manager_id = sub.id
        )
        SELECT id FROM sub
    """), {"uid": user.id}).fetchall()
    return [r[0] for r in rows]


def agent_filter(agent_ids, col="c.assigned_agent_id"):
    """SQL snippet + params to restrict `col` to the visible agent ids.
    Returns ('', {}) for full access. Uses a unique param name to avoid clashes."""
    if agent_ids is None:
        return "", {}
    if not agent_ids:
        return f" AND {col} = -1 ", {}
    return f" AND {col} = ANY(:rbac_agent_ids) ", {"rbac_agent_ids": agent_ids}


def can_see_agent(db, user, agent_id):
    """True if `user` is allowed to see data owned by `agent_id`."""
    ids = scope_agent_ids(db, user)
    return ids is None or (agent_id in ids)
